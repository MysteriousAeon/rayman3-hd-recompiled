#!/usr/bin/env python3
"""Resolution chain of one run, read from its log, with a mechanical verdict (M15, D-042).

    python tools/m15_resolution_check.py RUN_DIR [--scale N] [--json OUT]

RUN_DIR is a hidden run directory (private/work/m6_runs/NAME) or a playtest session
(private/play/sessions/STAMP). The log lines come from tools/m15_runtime_patch.py and the M3 swap trace:

  M15 window / M3 host_swapchain_create     window, display mode, swap chain
  M15 draw_scale                            scale in effect after the device clamp
  M15 rt_create                             every host render target, guest size against host size
  M15 viewport                              host viewport / scissor per distinct tuple
  M3 swap                                   guest front buffer (packet), scaled source, guest output image
  M15 present                               guest output image -> rectangle in the swap chain

Checks (PASS only if all hold; --scale N also requires that scale):
  scale       draw_scale is uniform, was not clamped, no "reducing" warning
  targets     every host render target is exactly guest size x scale, colour and depth alike
  main_3d     a draw on the 1280-pitch surface has a host viewport of 1280*scale x 720*scale
  scissors    no host scissor on the 1280-pitch surface exceeds 1280*scale x 720*scale
  swap        every swap: packet 1280x720 (guest-visible size unchanged), source and output = x scale
  present     the guest output keeps its aspect ratio in the swap chain and is neither cropped nor offset
              beyond centred letterboxing
  native      (reported, not a failure) present ratio 1.000: one rendered pixel per displayed pixel

Reads text logs only; starts nothing. Prints a table and RESOLUTION_CHECK PASS|FAIL.
"""
import argparse
import json
import re
import sys
from pathlib import Path

GUEST_W, GUEST_H = 1280, 720


def fields(line: str) -> dict:
    return dict(re.findall(r"(\w+)=([^\s]+)", line))


def size(text: str):
    w, h = text.split("x")[:2]
    return int(w), int(re.match(r"\d+", h).group())


def parse_scale(text: str):
    t = str(text).strip().lower()
    if t in ("0", ""):
        return (0, 1)
    if t in ("1.5", "3:2", "3/2"):
        return (3, 2)
    return (int(t), 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--scale", type=parse_scale, default=(0, 1))
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    logs = sorted(a.run_dir.glob("runtime*.log"))
    if not logs:
        print(f"no runtime log in {a.run_dir}")
        return 2
    window = draw_scale = None
    swapchains, targets, viewports, swaps, presents, warnings = [], [], [], {}, [], 0
    swap_count = 0
    scale32_active = False
    scale32_refusals = 0
    for log in logs:
        with log.open(errors="replace") as handle:
            for line in handle:
                if "M15 window " in line:
                    window = fields(line)
                elif "M3 host_swapchain_create" in line:
                    swapchains.append(size(fields(line)["size"]))
                elif "M15 draw_scale" in line:
                    draw_scale = fields(line)
                elif "G6P89 active=1" in line:
                    scale32_active = True
                elif "G6P89 REFUSE" in line:
                    scale32_refusals += 1
                elif "M15 rt_create" in line:
                    f = fields(line)
                    targets.append({"kind": f["kind"], "msaa": int(f["msaa"]), "samples": int(f["samples"]),
                                    "dxgi_format": int(f["dxgi_format"]), "guest": size(f["guest"]),
                                    "host": size(f["host"])})
                elif "M15 viewport" in line:
                    m = re.search(r"guest_pitch=(\d+) msaa=(\d+) host_viewport=(\d+),(\d+) (\d+)x(\d+) "
                                  r"host_scissor=(\d+),(\d+) (\d+)x(\d+)", line)
                    if m:
                        v = [int(x) for x in m.groups()]
                        viewports.append({"pitch": v[0], "msaa": v[1], "viewport": v[2:6], "scissor": v[6:10]})
                elif "M3 swap " in line:
                    f = fields(line)
                    swap_count += 1
                    key = (f["packet"], f["source"], f["output"], f["display"])
                    swaps[key] = swaps.get(key, 0) + 1
                elif "M15 present" in line:
                    m = re.search(r"guest_output=(\d+)x(\d+) aspect=(\d+):(\d+) swap_chain=(\d+)x(\d+) "
                                  r"surface=(\d+)x(\d+) output_rect=(-?\d+),(-?\d+) (\d+)x(\d+)", line)
                    if m:
                        presents.append([int(x) for x in m.groups()])
                elif "The requested draw resolution scale is not supported" in line:
                    warnings += 1

    checks, notes = {}, []
    if not draw_scale:
        print("no M15 draw_scale line: the run predates the M15 instrumentation")
        return 2
    sx, sy = int(draw_scale["x"]), int(draw_scale["y"])
    den = 2 if scale32_active else 1
    req_num, req_den = a.scale
    checks["scale"] = sx == sy and draw_scale["as_requested"] == "true" and warnings == 0 and scale32_refusals == 0 and \
        (req_num == 0 or (sx == req_num and den == req_den))
    checks["targets"] = bool(targets) and all(
        t["host"][0] * den == t["guest"][0] * sx and t["host"][1] * den == t["guest"][1] * sy for t in targets)
    want_w, want_h = (GUEST_W * sx) // den, (GUEST_H * sy) // den
    main_views = [v for v in viewports if v["pitch"] == GUEST_W and v["msaa"] == 0]
    checks["main_3d"] = any(v["viewport"][2:] == [want_w, want_h] for v in main_views)
    checks["scissors"] = bool(main_views) and all(
        v["scissor"][0] + v["scissor"][2] <= want_w and v["scissor"][1] + v["scissor"][3] <= want_h
        for v in main_views)
    want = f"{want_w}x{want_h}"
    checks["swap"] = bool(swaps) and all(
        k[0] == f"{GUEST_W}x{GUEST_H}" and k[1] == want and k[2] == want for k in swaps)
    present_ok, native = bool(presents), bool(presents)
    for gw, gh, ax, ay, cw, ch, _sw, _sh, ox, oy, ow, oh in presents:
        aspect_ok = abs(ow * ay - oh * ax) <= max(ax, ay) * 2
        centred = abs((cw - ow) - 2 * ox) <= 2 and abs((ch - oh) - 2 * oy) <= 2 and ox >= 0 and oy >= 0
        present_ok &= aspect_ok and centred and gw * GUEST_H == gh * GUEST_W
        native &= (ow, oh) == (gw, gh)
    checks["present"] = present_ok

    result = {
        "run": a.run_dir.name, "window": window, "swap_chains": swapchains,
        "draw_scale": [sx, sy] if den == 1 else [sx, sy, den], "render_targets": targets,
        "viewports_1280_pitch": main_views, "viewports_other": [v for v in viewports if v not in main_views],
        "swaps": [{"packet": k[0], "source": k[1], "guest_output": k[2], "display": k[3], "logged": n}
                  for k, n in swaps.items()],
        "presents": [{"guest_output": [p[0], p[1]], "swap_chain": [p[4], p[5]], "output_rect": p[8:12]}
                     for p in presents],
        "native_pixel_mapping": native, "checks": checks, "pass": all(checks.values()),
    }
    if a.json:
        a.json.write_text(json.dumps(result, indent=1))

    print(f"run            {a.run_dir.name}")
    if window:
        print(f"window         {window.get('size')} points, {window.get('pixels')} pixels, fullscreen requested "
              f"{window.get('fullscreen_requested')}, SDL fullscreen {window.get('sdl_fullscreen')}, exclusive mode "
              f"{window.get('exclusive_mode')}")
        print(f"display mode   {window.get('desktop_mode')} Hz, pixel density {window.get('pixel_density')}")
    print(f"swap chain     {', '.join(f'{w}x{h}' for w, h in swapchains) or 'none logged'}")
    scale_label = f"{sx}/{den}x{sy}/{den}" if den != 1 else f"{sx}x{sy}"
    print(f"draw scale     {scale_label} (as requested: {draw_scale['as_requested']})")
    print("render targets (guest -> host):")
    seen = set()
    for t in targets:
        row = (t["kind"], t["guest"], t["host"], t["samples"])
        if row in seen:
            continue
        seen.add(row)
        print(f"  {t['kind']:5s} {t['guest'][0]}x{t['guest'][1]} -> {t['host'][0]}x{t['host'][1]}  "
              f"samples {t['samples']}  dxgi {t['dxgi_format']}")
    print("host viewports on the 1280-pitch surface:")
    for v in main_views:
        print(f"  viewport {v['viewport'][0]},{v['viewport'][1]} {v['viewport'][2]}x{v['viewport'][3]}   "
              f"scissor {v['scissor'][0]},{v['scissor'][1]} {v['scissor'][2]}x{v['scissor'][3]}")
    for k, n in swaps.items():
        print(f"swap           packet {k[0]}  scaled source {k[1]}  guest output {k[2]}  ({n} logged)")
    for p in presents:
        print(f"present        guest output {p[0]}x{p[1]} -> swap chain {p[4]}x{p[5]} at {p[8]},{p[9]} "
              f"{p[10]}x{p[11]}")
    print(f"native pixel mapping (1 rendered pixel = 1 displayed pixel): {native}")
    for name, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    print("RESOLUTION_CHECK", "PASS" if result["pass"] else "FAIL")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

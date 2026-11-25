"""G6-P89 (test only): run and read the experimental native 3:2 renderer (tools/g6p89_scale32.h).

  run TAG [--scenario swamp60|knaar10] [--seconds N]
                                               one hidden run through the established chain
                                               (tools/m24_pause_resume.py -> m9_license_run.py -> run_milestone6.ps1;
                                               hidden, non-activating, scoped input, genuine-save working copy, zero
                                               captures) with R3HD_TEST_G6P89_SCALE_3_2=1 and the integer scale left at
                                               1, so a refused activation can only fall back to 1x (visible as
                                               `G6P89 active=0`), never to 2x. The hidden window is 1920x1080.
  analyze RUN [--json OUT] [--require-edge]    structural acceptance from the run's runtime.log (no image, no dump);
                                               --require-edge (G6-P92) also requires an executed resolve whose host
                                               height is not a multiple of 8 rows (stats edge_resolves > 0 and a
                                               resolve_map line of that class)
  selftest                                     analyzer on synthetic lines

Acceptance (analyze): `G6P89 active=1`; no `G6P89 REFUSE`; every rt_create host size = guest x 3/2; the main colour
viewport and the presented swap source are 1920x1080; the resolve map is 9/4 (whole 64-byte groups); resolves, scaled
loads and transfers all > 0; no D3D12 device-removal / error lines; the M23 haptics policy line present.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
RUNS = ROOT / "private" / "work" / "m6_runs"
FLAG = "R3HD_RENDER_SCALE_3_2"
SCENARIOS = {
    "swamp60": ("swamp_60_human", ROOT / "config" / "g6p84" / "swamp60_play.txt", 140),
    # G6-P92: the G6-P88 knaar_10 census route (genuine-save working copy, six pauses); its 640x360 resolve family
    # first appeared near swap 2225 in the census.
    "knaar10": ("knaar_10_human", ROOT / "config" / "m24" / "pause_lengths_knaar10.txt", 220),
}
DEVICE_ERRORS = re.compile(r"DXGI_ERROR|DEVICE_REMOVED|device removed|GetDeviceRemovedReason|D3D12 ERROR", re.I)


def cmd_run(a) -> int:
    import m24_pause_resume as m24
    entry, steps, seconds = SCENARIOS[a.scenario]
    tag = f"g6p89_{a.tag}"
    args = SimpleNamespace(tag=tag, entry=entry, steps=steps, seconds=a.seconds or seconds, scale=1,
                           layer_coords="separate", audio=False, gpu=False,
                           env=[f"{FLAG}=1", "R3HD_HIDDEN_EXTRA=--window_width=1920,--window_height=1080"])
    code = m24.cmd_run(args)
    print(f"G6P89_RUN m24_{tag} scenario={a.scenario} driver_exit={code}")
    return code


def kv(line: str) -> dict:
    return dict(re.findall(r"(\w+)=([^\s]+)", line))


def analyze_lines(lines: list, require_edge: bool = False) -> dict:
    out = {"active": None, "inactive_reason": None, "refuse": [], "rt_create": [], "rt_bad": [],
           "m15_rt": [], "viewports": [], "swap_sources": [], "resolve_map": [], "resolve_map_bad": [],
           "stats": None, "device_errors": [], "haptics_policy": False}
    for ln in lines:
        if "G6P89 active=1" in ln:
            out["active"] = True
        elif "G6P89 active=0" in ln:
            out["active"] = False
            out["inactive_reason"] = kv(ln).get("reason")
        elif "G6P89 REFUSE" in ln:
            out["refuse"].append(ln[ln.index("G6P89"):][:300])
        elif "G6P89 rt_create" in ln:
            f = kv(ln)
            gw, gh = map(int, f["guest"].split("x"))
            hw, hh = map(int, f["host"].split("x"))
            row = {"msaa": int(f["msaa"]), "depth": int(f["depth"]), "guest": [gw, gh], "host": [hw, hh]}
            out["rt_create"].append(row)
            if hw * 2 != gw * 3 or hh * 2 != gh * 3:
                out["rt_bad"].append(row)
        elif "M15 rt_create" in ln:
            f = kv(ln)
            out["m15_rt"].append({"kind": f.get("kind"), "msaa": f.get("msaa"), "guest": f.get("guest"),
                                  "host": f.get("host")})
        elif "M15 viewport" in ln:
            m = re.search(r"surface_info=(\w+).*host_viewport=(\d+),(\d+) (\d+)x(\d+) host_scissor=(\d+),(\d+) "
                          r"(\d+)x(\d+)", ln)
            if m:
                out["viewports"].append({"surface_info": m.group(1), "viewport": [int(x) for x in m.groups()[1:5]],
                                         "scissor": [int(x) for x in m.groups()[5:9]]})
        elif "G6P89 swap_source" in ln:
            out["swap_sources"].append(kv(ln).get("host"))
        elif "G6P89 resolve_map" in ln:
            f = kv(ln)
            m = re.search(r"scaled_bytes=\[(\d+),(\d+)\)", ln)
            first, end = int(m.group(1)), int(m.group(2))
            ext, length = f["extent"].split("+")
            start = int(ext, 16)
            length = int(length)
            g0, g1 = start // 64, (start + length + 63) // 64
            row = {"guest": f["guest"], "host": f["host"], "extent_length": length, "scaled_bytes": end - first}
            out["resolve_map"].append(row)
            gw, gh = map(int, f["guest"].split("x"))
            hw, hh = map(int, f["host"].split("x"))
            if first != g0 * 144 or end != g1 * 144 or hw * 2 != gw * 3 or hh * 2 != gh * 3:
                out["resolve_map_bad"].append(row)
        elif "G6P89 stats" in ln:
            out["stats"] = {k: int(v) for k, v in kv(ln[ln.index("G6P89"):]).items() if v.isdigit()}
        if DEVICE_ERRORS.search(ln):
            out["device_errors"].append(ln[-200:])
        if "M23 haptics policy=suppressed physical_pad_drivers=none" in ln:
            out["haptics_policy"] = True
    main_vp = [v for v in out["viewports"] if v["viewport"][2:] == [1920, 1080]]
    s = out["stats"] or {}
    checks = {
        "active": out["active"] is True,
        "no_refusal": not out["refuse"],
        "rt_sizes_x1.5": bool(out["rt_create"]) and not out["rt_bad"],
        "main_viewport_1920x1080": bool(main_vp),
        "swap_source_1920x1080": "1920x1080" in out["swap_sources"],
        "resolve_map_9_4": bool(out["resolve_map"]) and not out["resolve_map_bad"],
        "work_counts": s.get("resolves", 0) > 0 and s.get("scaled_loads", 0) > 0 and s.get("transfers", 0) > 0,
        "no_device_errors": not out["device_errors"],
        "haptics_policy": out["haptics_policy"],
    }
    edge_maps = [r for r in out["resolve_map"] if int(r["host"].split("x")[1]) % 8]
    out["edge_resolve_maps"] = edge_maps[:8]
    if require_edge:
        checks["edge_resolve_executed"] = s.get("edge_resolves", 0) > 0 and bool(edge_maps)
    out["checks"] = checks
    out["verdict"] = "PASS" if all(checks.values()) else "FAIL"
    out["rt_create"] = out["rt_create"][:24]
    out["viewports"] = out["viewports"][:24]
    return out


def analyze(run: str, require_edge: bool = False) -> dict:
    p = Path(run)
    log = p if p.is_file() else (p if p.is_dir() else RUNS / run) / "runtime.log"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    r = analyze_lines(lines, require_edge)
    r["run"] = str(run)
    return r


def selftest() -> int:
    good = [
        "[gpu] G6P89 active=1 scale=3/2 path=host_render_targets backend=d3d12 group_bytes=64->144 exit_code=137",
        "[gpu] G6P89 rt_create base_tiles=0 pitch_tiles=16 msaa=0 depth=0 format=0 guest=1280x2048 host=1920x3072",
        "[gpu] M15 viewport draw=9 surface_info=14000500 guest_pitch=1280 msaa=0 host_viewport=0,0 1920x1080 "
        "host_scissor=0,0 1920x1080 scale=3x3",
        "[gpu] G6P89 resolve_map base=1EAE1000 extent=1EAE1000+3768320 guest=1280x720 host=1920x1080 "
        "scaled_bytes=[1158128640,1166607360) ratio_num=8478720 ratio_den=3768320",
        "[gpu] G6P89 swap_source swap=1 host=1920x1080",
        "[gpu] G6P89 stats swap=600 resolves=4000 scaled_loads=4000 transfers=8000 draws=90000 refusals=0",
        "[kernel] M23 haptics policy=suppressed physical_pad_drivers=none",
    ]
    r = analyze_lines(good)
    assert r["verdict"] == "PASS", r["checks"]
    bad = good + ["[gpu] G6P89 REFUSE reason=resolve_size a=1 b=2 swap=3"]
    assert analyze_lines(bad)["verdict"] == "FAIL"
    odd = [x.replace("host=1920x3072", "host=2560x4096") for x in good]
    assert not analyze_lines(odd)["checks"]["rt_sizes_x1.5"]
    off = [x.replace("G6P89 active=1", "G6P89 active=0 requested=1 reason=x") for x in good]
    assert analyze_lines(off)["verdict"] == "FAIL"
    # G6-P92: an executed edge-class resolve (host height not a multiple of 8) is required only on request.
    assert analyze_lines(good, require_edge=True)["verdict"] == "FAIL"
    edge = good + ["[gpu] G6P89 resolve_map base=1F214000 extent=1F214000+983040 guest=640x360 host=960x540 "
                   "scaled_bytes=[1175113728,1177325568) ratio_num=2211840 ratio_den=983040",
                   "[gpu] G6P89 stats swap=1200 resolves=8000 scaled_loads=8000 transfers=16000 draws=180000 "
                   "edge_resolves=600 refusals=0"]
    assert analyze_lines(edge, require_edge=True)["verdict"] == "PASS", analyze_lines(edge, True)["checks"]
    no_count = [x.replace("edge_resolves=600", "edge_resolves=0") for x in edge]
    assert analyze_lines(no_count, require_edge=True)["verdict"] == "FAIL"
    print("G6P89 analyzer selftest PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("tag")
    r.add_argument("--scenario", default="swamp60", choices=sorted(SCENARIOS))
    r.add_argument("--seconds", type=int, default=0)
    an = sub.add_parser("analyze")
    an.add_argument("run")
    an.add_argument("--json")
    an.add_argument("--require-edge", action="store_true")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "selftest":
        return selftest()
    res = analyze(a.run, a.require_edge)
    text = json.dumps(res, indent=1)
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

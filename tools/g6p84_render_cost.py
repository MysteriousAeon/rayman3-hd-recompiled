#!/usr/bin/env python3
"""G6-P84: steady-play render cost per draw scale, and the Auto rendering-resolution contract.

    python tools/g6p84_render_cost.py run TAG --scale N [--window WxH] [--seconds 140]
    python tools/g6p84_render_cost.py analyze RUN [--json OUT]
    python tools/g6p84_render_cost.py auto-table
    python tools/g6p84_render_cost.py selftest

`run` is one hidden run through tools/m24_pause_resume.py (m9_license_run.py -> run_milestone6.ps1: hidden window,
scoped input, muted, no physical controller, zero captures) on a working copy of the genuine `swamp_60_human` save
with config/g6p84/swamp60_play.txt (60 s of uninterrupted play). It sets R3HD_HIDDEN_EXTRA to
`--resolution_scale=N,--window_width=W,--window_height=H` (default window 1280N x 720N) and keeps everything else
at the M24 defaults (layer coords `separate`, adapter sampling on). tools/m11_perf_sample.py samples the process
beside it (CPU, working set, private bytes, WDDM per-process GPU engine and memory counters). Run name `m24_TAG`.

`analyze` takes the last uninterrupted stretch of play-class command-processor frames, drops its first 5 s and last
1 s, caps it at 45 s, and reports: guest swap (VdSwap), command-processor swap and host present intervals
(median / p95 / p99 / max / >20 ms / >30 ms), Direct3D submission-fence waits (the host GPU was late), title
GPU-progress spin waits, texture loads and pipeline creations per second, the adapter's clock / power / load
(nvidia-smi, 10 Hz), the process's CPU, working set, private bytes and WDDM GPU counters over the same wall-clock
span, and from runtime.log the M15 draw-scale / presentation geometry, M24 gpu_bound lines and device-loss text.

`auto-table` prints the G6-P84 whole-target Auto rule (D-042 / D-146) beside the aspect-aware rule that
tools/play.ps1 uses since G6-P85 (D-333 Policy A, adopted as D-334) for common display modes. It changes nothing. Everything printed is times, counts and sizes; traces stay under private/.
"""
import argparse
import bisect
import json
import math
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m24_pause_resume as m24  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "private" / "work" / "m6_runs"
STEPS = ROOT / "config" / "g6p84" / "swamp60_play.txt"
SKIP_HEAD_S, SKIP_TAIL_S, CAP_S, MIN_PLAY_FRAMES = 5.0, 1.0, 45.0, 600
DEVICE_LOSS = re.compile(r"DEVICE_REMOVED|DEVICE_HUNG|DEVICE_RESET|device (was )?(lost|removed)|TDR", re.I)

# Common display modes (physical pixels). The game's guest output is 1280x720 at 16:9 (M15 log `aspect=1280:720`).
DISPLAYS = [("1280x720", 1280, 720), ("1366x768", 1366, 768), ("1600x900", 1600, 900), ("1920x1080", 1920, 1080),
            ("1920x1200 (16:10)", 1920, 1200), ("2560x1080 (21:9)", 2560, 1080), ("2560x1440", 2560, 1440),
            ("2256x1504 (3:2)", 2256, 1504), ("2560x1600 (16:10)", 2560, 1600), ("2880x1800 (16:10)", 2880, 1800),
            ("3440x1440 (21:9)", 3440, 1440), ("3840x1600 (24:10)", 3840, 1600), ("3840x2160", 3840, 2160),
            ("5120x1440 (32:9)", 5120, 1440), ("1280x800 (16:10)", 1280, 800), ("1280x1024 (5:4)", 1280, 1024)]


def auto_scale(width: int, height: int) -> int:
    """The G6-P84 (pre-G6-P85) -RenderScale auto rule: the smallest integer scale whose 1280N x 720N image covers
    the whole target on both axes, clamped 1..3. Superseded in tools/play.ps1 by aspect_scale (D-334)."""
    return int(min(3, max(1, max(math.ceil(width / 1280.0), math.ceil(height / 720.0)))))


def fitted_image(width: int, height: int) -> tuple:
    """The 16:9 rectangle the SDK presenter shows the guest image in (present_letterbox on, overscan cutoff off:
    the SDK defaults, not overridden by the port): the largest 16:9 rectangle inside the surface."""
    if width * 9 > height * 16:
        return (round(height * 16 / 9), height)
    return (width, round(width * 9 / 16))


def aspect_scale(width: int, height: int) -> int:
    """tools/play.ps1 -RenderScale auto since G6-P85 (D-333 Policy A, D-334): the smallest integer scale whose
    image covers the rectangle actually shown, clamped 1..3."""
    w, h = fitted_image(width, height)
    return int(min(3, max(1, max(math.ceil(w / 1280.0), math.ceil(h / 720.0)))))


def pct(values: list, q: float):
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))], 3)


def stats(values: list) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "median": pct(values, 0.5), "p95": pct(values, 0.95), "p99": pct(values, 0.99),
            "max": round(max(values), 3), "over_20ms": sum(v > 20.0 for v in values),
            "over_30ms": sum(v > 30.0 for v in values)}


def intervals_ms(rows: list, lo: float, hi: float) -> list:
    t = [r[0] for r in rows if lo <= r[0] <= hi]
    return [(t[i] - t[i - 1]) * 1000.0 for i in range(1, len(t))]


def play_window(cpswap: list):
    """(lo, hi) seconds of the last uninterrupted run of play-class frames, trimmed and capped; None if too short."""
    classes = [m24.frame_class(a, b) for _, a, b in cpswap]
    end = len(classes)
    while end and classes[end - 1] != "play":
        end -= 1
    start = end
    while start and classes[start - 1] == "play":
        start -= 1
    if end - start < MIN_PLAY_FRAMES:
        return None
    lo, hi = cpswap[start][0] + SKIP_HEAD_S, cpswap[end - 1][0] - SKIP_TAIL_S
    return (max(lo, hi - CAP_S), hi) if hi > lo else None


def per_frame_texloads(ev: dict, lo: float, hi: float) -> dict:
    """{"resolves:texloads": frames} over command-processor frames in the window: whether each frame's host
    texture loads match its resolve (copy) count, i.e. render-to-texture outputs sampled again (E-532)."""
    times = [t for t, _, _ in ev["texload"]]
    frames = [r for r in ev["cpswap"] if lo <= r[0] <= hi]
    counts = {}
    for prev, cur in zip(frames, frames[1:]):
        n = bisect.bisect_right(times, cur[0]) - bisect.bisect_right(times, prev[0])
        key = f"{cur[2] >> 16}:{n}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1])[:6])


def log_facts(run_dir: Path) -> dict:
    path = run_dir / "runtime.log"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    grab = lambda key: [line.split(key, 1)[1].strip() for line in text if key in line]  # noqa: E731
    return {"draw_scale": grab("M15 draw_scale"), "present": grab("M15 present"), "gpu_bound": grab("M24 gpu_bound"),
            "haptics_policy": any("M23 haptics policy=suppressed physical_pad_drivers=none" in line for line in text),
            "device_loss_lines": sum(bool(DEVICE_LOSS.search(line)) for line in text),
            "error_lines": sum("[error]" in line or "[critical]" in line for line in text), "lines": len(text)}


def perf_facts(run_dir: Path, wall_lo: float, wall_hi: float) -> dict:
    path = run_dir / "perf_samples.json"
    if not path.is_file():
        return {}
    samples = json.loads(path.read_text(encoding="utf-8"))["samples"]
    stamp = lambda s: datetime.strptime(s["local"], "%Y-%m-%d %H:%M:%S.%f").timestamp()  # noqa: E731
    inside = [s for s in samples if wall_lo <= stamp(s) <= wall_hi]
    col = lambda key: [s[key] for s in inside if s.get(key) is not None]  # noqa: E731
    mib = lambda v: None if v is None else round(v / 1048576, 1)  # noqa: E731
    out = {"samples": len(inside), "cpu_percent_one_core_median": pct(col("cpu_percent_one_core"), 0.5),
           "working_set_mib_max": mib(max(col("working_set"), default=None)),
           "private_mib_max": mib(max(col("private_bytes"), default=None)),
           "private_mib_first": mib(col("private_bytes")[0] if col("private_bytes") else None),
           "private_mib_last": mib(col("private_bytes")[-1] if col("private_bytes") else None),
           "peak_commit_mib_run": mib(max((s["peak_commit"] for s in samples), default=None)),
           "gpu_util_3d_median": pct(col("gpu_util_3d"), 0.5),
           "gpu_dedicated_mib_max": mib(max(col("gpu_dedicated_bytes"), default=None)),
           "gpu_dedicated_mib_first": mib(col("gpu_dedicated_bytes")[0] if col("gpu_dedicated_bytes") else None),
           "gpu_dedicated_mib_last": mib(col("gpu_dedicated_bytes")[-1] if col("gpu_dedicated_bytes") else None),
           "gpu_shared_mib_max": mib(max(col("gpu_shared_bytes"), default=None))}
    return out


def analyze(run: str) -> dict:
    run_dir = RUNS / run
    events = m24.WORK / f"{run}.r3ev"
    ev = m24.read_events(events)
    window = play_window(ev["cpswap"])
    result = {"run": run, "log": log_facts(run_dir)}
    if not window:
        result["error"] = "no uninterrupted play stretch"
        return result
    lo, hi = window
    fence = [a for t, a, _ in ev["fencewait"] if lo <= t <= hi]
    spin = [a for t, a, _ in ev["gpuwait"] if lo <= t <= hi]
    cycles = [a * 1024 / 1e6 for t, a, _ in ev["vdswap"] if lo <= t <= hi and a]
    span = hi - lo
    result.update({
        "window_s": [round(lo, 2), round(hi, 2)], "seconds": round(span, 1),
        "vdswap_ms": stats(intervals_ms(ev["vdswap"], lo, hi)),
        "cpswap_ms": stats(intervals_ms(ev["cpswap"], lo, hi)),
        "present_ms": stats(intervals_ms(ev["present"], lo, hi)),
        "present_call_us": {k: v for k, v in stats([a for t, a, _ in ev["present"] if lo <= t <= hi]).items()
                            if not k.startswith("over_")},
        "resolves_per_frame": sorted({b >> 16 for t, _, b in ev["cpswap"] if lo <= t <= hi}),
        "texloads_per_frame": per_frame_texloads(ev, lo, hi),
        "fence_waits": len(fence), "fence_waits_over_4ms": sum(a >= m24.FENCE_SLOW_US for a in fence),
        "fence_wait_ms_total": round(sum(fence) / 1000.0, 1),
        "guest_spin_waits_over_20ms": sum(us > 20000 for us in spin),
        "guest_megacycles_per_frame_median": pct(cycles, 0.5),
        "texloads_per_s": round(sum(lo <= t <= hi for t, _, _ in ev["texload"]) / span, 1),
        "pipelines_in_window": sum(lo <= t <= hi for t, _, _ in ev["pipeline"]),
        "pipelines_total": len(ev["pipeline"]),
    })
    gpu = m24.gpu_samples(run, ev)
    if gpu:
        rows = [r for r in gpu if lo <= r[0] <= hi]
        result["adapter"] = {"samples": len(rows), "clock_mhz_median": pct([r[1] for r in rows], 0.5),
                             "power_w_median": pct([r[2] for r in rows], 0.5),
                             "utilization_median": pct([r[3] for r in rows], 0.5),
                             "utilization_p95": pct([r[3] for r in rows], 0.95),
                             "pstates": sorted({r[4] for r in rows})}
        # wall-clock span of the window for the process sampler: same offset the adapter mapping used
        record = json.loads((run_dir / "license_run.json").read_text(encoding="utf-8"))
        presses = [datetime.fromisoformat(e["utc"]).timestamp() for e in record["events"] if e.get("step") == "press"]
        seen = [t for t, a, _ in ev["buttons"] if a]
        offset = m24.median([p - s for p, s in zip(presses, seen)])
        result["process"] = perf_facts(run_dir, lo + offset, hi + offset)
    return result


def cmd_run(a) -> int:
    width, height = (1280 * a.scale, 720 * a.scale)
    if a.window:
        width, height = (int(x) for x in a.window.lower().split("x"))
    run = f"m24_{a.tag}"
    sampler_log = m24.WORK / f"{run}.sampler.log"
    m24.WORK.mkdir(parents=True, exist_ok=True)
    sampler = subprocess.Popen([sys.executable, str(ROOT / "tools" / "m11_perf_sample.py"), run, "--wait", "180"],
                               cwd=ROOT, stdout=sampler_log.open("w"), stderr=subprocess.STDOUT)
    extra = f"--resolution_scale={a.scale},--window_width={width},--window_height={height}"
    args = SimpleNamespace(tag=a.tag, entry="swamp_60_human", steps=STEPS, seconds=a.seconds, scale=a.scale,
                           layer_coords="separate", audio=False, gpu=True, env=[f"R3HD_HIDDEN_EXTRA={extra}"])
    try:
        code = m24.cmd_run(args)
    finally:
        try:
            sampler.wait(timeout=60)
        except subprocess.TimeoutExpired:
            sampler.terminate()
    print(f"G6P84_RUN {run} scale={a.scale} window={width}x{height} driver_exit={code} sampler_exit={sampler.returncode}")
    return code


def cmd_analyze(a) -> int:
    result = analyze(a.run)
    text = json.dumps(result, indent=1)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if "error" not in result else 1


def cmd_auto_table(_a) -> int:
    print(f"{'display':22} {'shown image':>11} {'G6-P84':>6} {'Auto (D-334)':>13}  G6-P84 internal / shown pixels")
    for name, w, h in DISPLAYS:
        fw, fh = fitted_image(w, h)
        s, t = auto_scale(w, h), aspect_scale(w, h)
        print(f"{name:22} {fw:>5}x{fh:<5} {s:>6} {t:>13}  {1280 * s}x{720 * s} = {1280 * s * 720 * s / (fw * fh):.2f}x"
              f"{'   <- differs' if s != t else ''}")
    return 0


def cmd_selftest(_a) -> int:
    failures = []

    def check(ok, label):
        if not ok:
            failures.append(label)

    play = (ROOT / "tools" / "play.ps1").read_text(encoding="utf-8")
    # G6-P85 (D-334): play.ps1 Auto is the aspect-aware rule, min(ceil(w/1280), ceil(h/720)) clamped 1..3, in one
    # helper. tools/m15_resolution_regression.py runs the helper itself.
    check("function Get-AutoRenderScale($Width, $Height)" in play
          and "if ($RenderScale -eq 'auto') { $scale = Get-AutoRenderScale $target.width $target.height }" in play,
          "play.ps1 Auto goes through Get-AutoRenderScale")
    check("[Math]::Min($nw, $nh)" in play and "[int][Math]::Min([long]3, [Math]::Max([long]1," in play,
          "play.ps1 Auto rule is min(ceil(w/1280), ceil(h/720)) clamped 1..3")
    check("[Math]::Ceiling($target.width / 1280.0)" not in play, "the G6-P84 whole-target formula is gone from play.ps1")
    presenter = (ROOT / "external" / "rexglue-sdk" / "src" / "ui" / "presenter.cpp")
    if presenter.is_file():
        p = presenter.read_text(encoding="utf-8", errors="replace")
        check("REXCVAR_DEFINE_BOOL(present_letterbox, true" in p, "SDK letterbox default on")
        check("REXCVAR_DEFINE_BOOL(present_allow_overscan_cutoff, false" in p, "SDK overscan cutoff default off")
    for name, w, h in DISPLAYS:
        if name in ("1920x1080", "2560x1440", "3840x2160", "1280x720"):
            check(auto_scale(w, h) == aspect_scale(w, h), f"16:9 {name}: both rules agree")
    check(auto_scale(1920, 1080) == 2 and auto_scale(1366, 768) == 2 and auto_scale(3840, 2160) == 3, "D-146 cases")
    check(auto_scale(2560, 1600) == 3 and aspect_scale(2560, 1600) == 2, "16:10 2560x1600 differs 3 vs 2")
    check(auto_scale(3440, 1440) == 3 and aspect_scale(3440, 1440) == 2, "21:9 3440x1440 differs 3 vs 2")
    check(fitted_image(2560, 1600) == (2560, 1440) and fitted_image(3440, 1440) == (2560, 1440), "fitted image")
    check(stats([16.6, 16.7, 16.8, 33.4])["over_30ms"] == 1 and pct([1, 2, 3, 4], 0.5) == 2, "stats")
    cp = [(i / 60.0, 100, 270 if i < 100 else (7 << 16 | 1)) for i in range(100 + 60 * 60)]
    w = play_window(cp)
    check(w is not None and abs((w[1] - w[0]) - CAP_S) < 1e-6, "play window capped at 45 s")
    for f in failures:
        print("FAIL", f)
    print(f"G6P84_SELFTEST {'FAIL' if failures else 'PASS'} failures={len(failures)}")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("tag")
    r.add_argument("--scale", type=int, choices=(1, 2, 3), required=True)
    r.add_argument("--window", help="WxH physical client size (default 1280N x 720N)")
    r.add_argument("--seconds", type=int, default=140)
    an = sub.add_parser("analyze")
    an.add_argument("run")
    an.add_argument("--json", type=Path)
    sub.add_parser("auto-table")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "run":
        if not re.fullmatch(r"g6p84_[A-Za-z0-9_]+", a.tag) or (a.window and not re.fullmatch(r"\d{3,4}x\d{3,4}", a.window)):
            ap.error("tag must start with g6p84_; window WxH")
        return cmd_run(a)
    return {"analyze": cmd_analyze, "auto-table": cmd_auto_table, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())

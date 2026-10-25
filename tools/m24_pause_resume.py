#!/usr/bin/env python3
"""Milestone 24: pause / Resume Game timing on a working copy of a genuine save entry.

    python tools/m24_pause_resume.py run TAG [--entry swamp_60_human] [--steps config/m24/pause_lengths_swamp60.txt]
                                             [--seconds 200] [--scale 2] [--layer-coords separate] [--gpu] [--audio]
    python tools/m24_pause_resume.py analyze RUN [--json OUT] [--expect clean|gpu_bound]
    python tools/m24_pause_resume.py selftest

`run` is one hidden run (m9_license_run.py: hidden window, scoped input, muted, no physical controller, no
captures) with the host event trace (tools/m24_event_trace.h, R3HD_M24_EVENTS) and the M17 per-frame guest trace
(R3HD_FRAME_TRACE, engine timer) on. `--scale 2` runs the renderer at 2560x1440 through R3HD_HIDDEN_EXTRA, as the
human sessions do; `--gpu` samples the adapter's clock, power and load ten times a second beside the run
(nvidia-smi, read-only). Records: private/work/m24/RUN.r3ev, .r3ft, .gpu.csv; run directory private/work/m6_runs/RUN.

`analyze` finds every pause in the trace (a stretch of menu-class frames between two stretches of play-class
frames, left by a pad button) and, for the two seconds after each exit: the command processor's swap intervals,
the host present intervals, the guest's VdSwap intervals, the waits for the host GPU (Direct3D submission
fence), the guest thread's waits at the title's GPU-progress spin and its processor time per frame, host
pipeline creations and texture loads, vibration changes, and the adapter state at the end of the menu and after
it. The same figures for play away from every pause are the control. An exit is `gpu_bound` when its slow
frames come with fence waits: the host GPU, not the guest and not the command processor, was the late party.
`--expect clean` passes when no exit has a slow frame, `--expect gpu_bound` when every exit with slow frames is
gpu_bound (M24_PAUSE_CHECK PASS / FAIL); without it the tool only reports.

Everything printed is times and counts. Traces describe a run of the game and stay under private/.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import m17_frame_trace as m17  # noqa: E402
from m19_campaign_check import SWITCHES as m19_switches  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "m24"
TOOLS = ROOT / "tools"
# removed from the environment of a run: the campaign runner's list (revisit switches) and what this tool sets
SWITCHES = m19_switches + ("R3HD_VBLANK", "R3HD_FRAME_TRACE", "R3HD_HIDDEN_EXTRA", "R3HD_LAYER_COORDS",
                           "R3HD_WATER_LAYERS", "R3HD_M22_AUDIO", "R3HD_M24_EVENTS")

# kind number -> (name here, enumerator in tools/m24_event_trace.h); kind 9 (kImportWait) is read separately
KINDS = {1: ("vdswap", "kVdSwap"), 2: ("cpswap", "kCpSwap"), 3: ("present", "kPresent"), 4: ("buttons", "kButtons"),
         5: ("vibration", "kVibration"), 6: ("pipeline", "kPipeline"), 7: ("texload", "kTextureLoad"),
         8: ("cpwait", "kCpWait"), 10: ("gpuwait", "kGpuWait"), 11: ("fencewait", "kFenceWait")}
BUTTON_NAMES = {0x0010: "Start", 0x1000: "A", 0x2000: "B", 0x4000: "X", 0x8000: "Y"}
SLOW_MS = 20.0        # an interval over this is not a 60 Hz frame
AFTER_S = 2.0         # the stretch after a pause exit that is judged
MIN_RUN = 20          # frames of one class on both sides for a change to count as a pause entry / exit
FENCE_SLOW_US = 4000  # tools/m24_event_trace.h kFenceSlowUs


def cmd_run(a) -> int:
    run = f"m24_{a.tag}"
    run_dir = m12.RUNS / run
    profile = m12.PROFILES / run
    if run_dir.exists() or profile.exists():
        raise SystemExit(f"run or profile already exists: {run}")
    entry = m12.load_entry(a.entry)
    if not m12.stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {a.entry} no longer matches entry.json")
    shutil.copytree(m12.SAVES / a.entry / "profile", profile)
    WORK.mkdir(parents=True, exist_ok=True)
    trace, events = WORK / f"{run}.r3ft", WORK / f"{run}.r3ev"
    if events.exists():
        raise SystemExit(f"event trace already exists: {events}")  # the game appends to it
    m17.write_watch(trace, m17.TIMER_WATCH)
    env = {k: v for k, v in os.environ.items() if k not in SWITCHES}
    env["R3HD_FRAME_TRACE"] = str(trace)
    env["R3HD_M24_EVENTS"] = str(events)
    if a.scale != 1:
        env["R3HD_HIDDEN_EXTRA"] = (f"--resolution_scale={a.scale},--window_width={1280 * a.scale},"
                                    f"--window_height={720 * a.scale}")
    if a.layer_coords != "original":
        env["R3HD_LAYER_COORDS"] = a.layer_coords
    if a.audio:
        env["R3HD_M22_AUDIO"] = "1"
    for item in a.env:
        key, _, value = item.partition("=")
        env[key] = value
    command = [sys.executable, str(TOOLS / "m9_license_run.py"), run, str(a.steps), "--license-mask", "1",
               "--seconds", str(a.seconds), "--play", "--user-root", run]
    sampler = gpu_log = None
    if a.gpu:  # adapter clock, power and load ten times a second, beside the run (read-only, NVIDIA only)
        gpu_log = (WORK / f"{run}.gpu.csv").open("w", encoding="ascii")
        try:
            sampler = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,clocks.current.graphics,power.draw,utilization.gpu,pstate",
                                        "--format=csv,noheader,nounits", "-lms", "100"], stdout=gpu_log, stderr=subprocess.DEVNULL)
        except OSError:
            print("nvidia-smi not available: no adapter samples")
    try:
        with (WORK / f"{run}.driver.log").open("w", encoding="utf-8") as log:
            game = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            beside = getattr(a, "beside", None)  # read-only work beside the run (tools/m24_resume_state.py)
            if beside:
                beside(run_dir, trace, game, log)
            code = game.wait()
    finally:
        if sampler:
            sampler.terminate()
            sampler.wait(timeout=10)
        if gpu_log:
            gpu_log.close()
    print(f"M24_PAUSE_RUN {run} driver_exit={code} events={events.relative_to(ROOT)}")
    return code


# ---------------------------------------------------------------------------------------------------------------
# analyze: the host event trace (tools/m24_event_trace.h)

def name_hash(text: str) -> int:
    h = 2166136261
    for byte in text.encode():
        h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
    return h & 0xFFFFFF


def import_names() -> dict:
    """{24-bit FNV-1a of "__imp__NAME": NAME} for the title's imports (reports/milestone1/import_surface.csv)."""
    listing = ROOT / "reports" / "milestone1" / "import_surface.csv"
    return {name_hash(f"__imp__{line.split(',')[2]}"): line.split(",")[2]
            for line in listing.read_text(encoding="utf-8").splitlines()[1:]}


def read_events(path: Path) -> dict:
    """{kind name: [(seconds, a, b)]} in time order, plus "import": [(seconds, microseconds, caller, name,
    thread)]. The file is records only (several modules append to it); kind 0 carries the counter frequency."""
    data = Path(path).read_bytes()
    records = [struct.unpack_from("<IIqII", data, offset) for offset in range(0, len(data) - 23, 24)]
    frequency = next(((b << 32) | a for kind, _, _, a, b in records if kind == 0), 0)
    if not frequency or any((kind & 0xFF) > 64 for kind, *_ in records):
        raise SystemExit(f"{path}: not an M24 event trace")
    records.sort(key=lambda r: r[2])
    first = records[0][2]
    out = {name: [] for name, _ in KINDS.values()}
    out["import"] = []
    names = import_names()
    for kind, thread, counter, a, b in records:
        if kind & 0xFF == 9:
            out["import"].append(((counter - first) / frequency, a, b, names.get(kind >> 8, f"hash_{kind >> 8:06X}"), thread))
        elif kind in KINDS:
            out[KINDS[kind][0]].append(((counter - first) / frequency, a, b))
    return out


def frame_class(a: int, b: int) -> str:
    """Class of one command-processor frame from its draw / copy / clear counts: `play` (a scene: resolves and
    a clear), `menu` (the pause menu and the front end draw over a kept picture: no clear, at most one copy)."""
    copies, clears = b >> 16, b & 0xFFFF
    return "play" if clears >= 1 and copies >= 2 else "menu"


def intervals(series, lo: float, hi: float) -> list:
    times = [row[0] for row in series]
    return [(times[i] - times[i - 1]) * 1000.0 for i in range(1, len(times)) if lo <= times[i] <= hi]


def describe(values: list) -> dict:
    if not values:
        return {"n": 0, "over_20ms": 0, "over_30ms": 0, "lost_ms": 0.0}
    slow = [v for v in values if v > SLOW_MS]
    return {"n": len(values), "max_ms": round(max(values), 2), "min_ms": round(min(values), 2),
            "over_20ms": len(slow), "over_30ms": sum(v > 30.0 for v in values),
            "lost_ms": round(sum(v - 1000.0 / 60.0 for v in slow), 1)}


def median(values: list):
    return sorted(values)[len(values) // 2] if values else None


def window(ev: dict, lo: float, hi: float) -> dict:
    """What the host and the guest did between two times."""
    fence = [a for t, a, _ in ev["fencewait"] if lo <= t <= hi and a >= FENCE_SLOW_US]
    spin = [a for t, a, _ in ev["gpuwait"] if lo <= t <= hi]
    cycles = [a * 1024 / 1e6 for t, a, _ in ev["vdswap"] if lo <= t <= hi and a]
    return {"cpswap": describe(intervals(ev["cpswap"], lo, hi)), "present": describe(intervals(ev["present"], lo, hi)),
            "vdswap": describe(intervals(ev["vdswap"], lo, hi)),
            "present_call_max_us": max([a for t, a, _ in ev["present"] if lo <= t <= hi] or [0]),
            "fence_waits": len(fence), "fence_wait_ms": round(sum(fence) / 1000.0, 1),
            "fence_longest_ms": round(max(fence) / 1000.0, 1) if fence else 0.0,
            "guest_spin_waits_over_20ms": sum(us > 20000 for us in spin),
            "guest_megacycles_per_frame_median": round(median(cycles), 2) if cycles else None,
            "pipelines": sum(lo <= t <= hi for t, _, _ in ev["pipeline"]),
            "texloads": sum(lo <= t <= hi for t, _, _ in ev["texload"]),
            "vibration_changes": sum(lo <= t <= hi for t, _, _ in ev["vibration"])}


def analyze_events(path: Path, gpu: list | None = None) -> dict:
    ev = read_events(path)
    swaps = ev["cpswap"]
    classes = [frame_class(a, b) for _, a, b in swaps]
    runs, start = [], 0
    for i in range(1, len(classes) + 1):
        if i == len(classes) or classes[i] != classes[start]:
            runs.append((classes[start], start, i))
            start = i
    pauses = []
    for index in range(1, len(runs) - 1):
        kind, lo, hi = runs[index]
        before, after = runs[index - 1], runs[index + 1]
        if kind != "menu" or hi - lo < MIN_RUN or before[0] != "play" or after[0] != "play":
            continue
        if before[2] - before[1] < MIN_RUN or after[2] - after[1] < MIN_RUN:
            continue
        entered, left = swaps[lo][0], swaps[hi][0]
        keys = [BUTTON_NAMES.get(a, f"{a:04X}") for t, a, _ in ev["buttons"] if a and left - 0.5 <= t <= left]
        if not keys:
            continue  # the front end handing over to a level load, not a pause
        exit_facts = window(ev, left - 0.1, left + AFTER_S)
        slow = exit_facts["cpswap"]["over_20ms"]
        verdict = "clean" if not slow else ("gpu_bound" if exit_facts["fence_waits"] * 2 >= slow else "unexplained")
        pause = {"entered_s": round(entered, 3), "left_s": round(left, 3), "menu_s": round(left - entered, 2),
                 "exit_key": keys[-1], "menu_draws": swaps[lo + (hi - lo) // 2][1],
                 "entry": {"cpswap": describe(intervals(swaps, entered - 0.1, entered + 0.5)),
                           "vdswap": describe(intervals(ev["vdswap"], entered - 0.1, entered + 0.5))},
                 "exit": exit_facts, "verdict": verdict}
        if gpu:
            def state(lo_t, hi_t):
                rows = [row for row in gpu if lo_t <= row[0] <= hi_t]
                if not rows:
                    return None
                return {"clock_mhz": [min(r[1] for r in rows), max(r[1] for r in rows)],
                        "power_w": [round(min(r[2] for r in rows)), round(max(r[2] for r in rows))],
                        "utilization_max": max(r[3] for r in rows)}
            pause["gpu"] = {"play_before": state(entered - 1.0, entered), "menu_end": state(left - 0.5, left),
                            "after_exit": state(left, left + 1.0)}
        pauses.append(pause)
    control = {}
    if pauses:
        excluded = ([(p["entered_s"] - 0.5, p["entered_s"] + 0.5) for p in pauses]
                    + [(p["left_s"] - 0.5, p["left_s"] + AFTER_S) for p in pauses])
        lo_t, hi_t = pauses[0]["entered_s"] - 8.0, swaps[-1][0]
        inside = lambda t: lo_t <= t <= hi_t and not any(a <= t <= b for a, b in excluded)  # noqa: E731
        values = [(swaps[i][0] - swaps[i - 1][0]) * 1000.0 for i in range(1, len(swaps))
                  if classes[i] == "play" and classes[i - 1] == "play" and inside(swaps[i][0])]
        span = sum(values) / 1000.0
        cycles = [a * 1024 / 1e6 for t, a, _ in ev["vdswap"] if a and inside(t)]
        control = {**describe(values), "seconds": round(span, 1),
                   "fence_waits": sum(a >= FENCE_SLOW_US and inside(t) for t, a, _ in ev["fencewait"]),
                   "texloads_per_2s": round(sum(inside(t) for t, _, _ in ev["texload"]) / span * AFTER_S, 1) if span else None,
                   "guest_megacycles_per_frame_median": round(median(cycles), 2) if cycles else None}
    return {"events": {name: len(rows) for name, rows in ev.items()}, "pauses": pauses, "control_play": control,
            "pipelines_total": len(ev["pipeline"])}


def gpu_samples(run: str, events: dict) -> list | None:
    """Adapter samples [(trace seconds, clock MHz, watts, utilisation %, power state)] of a run made with --gpu.
    The sampler's wall clock is mapped to trace time through the pad presses: the driver notes when it wrote
    each one, the trace when the title read it (a few tens of milliseconds apart)."""
    listing, record = WORK / f"{run}.gpu.csv", m12.RUNS / run / "license_run.json"
    if not listing.is_file() or not record.is_file():
        return None
    presses = [datetime.fromisoformat(e["utc"]).timestamp() for e in json.loads(record.read_text(encoding="utf-8"))["events"]
               if e.get("step") == "press"]
    seen = [t for t, a, _ in events["buttons"] if a]
    if not presses or len(presses) != len(seen):
        return None
    offset = median([p - s for p, s in zip(presses, seen)])
    rows = []
    for line in listing.read_text(encoding="ascii", errors="replace").splitlines():
        fields = [x.strip() for x in line.split(",")]
        try:
            stamp = datetime.strptime(fields[0], "%Y/%m/%d %H:%M:%S.%f").timestamp()
            rows.append((stamp - offset, int(fields[1]), float(fields[2]), int(fields[3]), fields[4]))
        except (ValueError, IndexError):
            continue
    return rows


def report(name: str, result: dict) -> None:
    print(f"{name}: events {result['events']}")
    for i, p in enumerate(result["pauses"], 1):
        x = p["exit"]
        line = (f"  pause {i}: {p['menu_s']:6.2f} s in the menu, left with {p['exit_key']}: {p['verdict']}; next {AFTER_S:.0f} s: "
                f"swap >20 ms {x['cpswap']['over_20ms']} (max {x['cpswap'].get('max_ms')}, lost {x['cpswap']['lost_ms']} ms), "
                f"present >20 ms {x['present']['over_20ms']}, GPU fence waits {x['fence_waits']} ({x['fence_wait_ms']} ms, "
                f"longest {x['fence_longest_ms']}), guest spin waits >20 ms {x['guest_spin_waits_over_20ms']}, guest "
                f"{x['guest_megacycles_per_frame_median']} Mcycles/frame, pipelines {x['pipelines']}, texture loads {x['texloads']}, "
                f"vibration {x['vibration_changes']}")
        if p.get("gpu") and p["gpu"]["menu_end"] and p["gpu"]["after_exit"]:
            g = p["gpu"]
            line += (f"; adapter at the end of the menu {g['menu_end']['clock_mhz'][0]} MHz / {g['menu_end']['power_w'][0]} W, "
                     f"after the exit up to {g['after_exit']['utilization_max']} % at {g['after_exit']['clock_mhz'][1]} MHz")
        print(line)
    c = result["control_play"]
    if c:
        print(f"  control (play, {c['seconds']} s away from pause changes): swap >20 ms {c['over_20ms']} of {c['n']} "
              f"(max {c.get('max_ms')}), GPU fence waits {c['fence_waits']}, guest {c['guest_megacycles_per_frame_median']} "
              f"Mcycles/frame, texture loads per {AFTER_S:.0f} s {c['texloads_per_2s']}; pipelines in the run {result['pipelines_total']}")


def judge(result: dict, expect: str | None) -> list:
    """Reasons why a run is not what `expect` says (empty = pass)."""
    pauses = result["pauses"]
    reasons = [] if len(pauses) >= 2 else [f"only {len(pauses)} pause(s) found"]
    if expect == "clean":
        reasons += [f"pause {i}: {p['verdict']}" for i, p in enumerate(pauses, 1) if p["verdict"] != "clean"]
    elif expect == "gpu_bound":
        reasons += [f"pause {i}: slow frames without GPU fence waits" for i, p in enumerate(pauses, 1) if p["verdict"] == "unexplained"]
    return reasons


def cmd_analyze(a) -> int:
    name = a.run if a.run.startswith("m24_") else f"m24_{a.run}"
    path = WORK / f"{name}.r3ev"
    result = analyze_events(path, gpu_samples(name, read_events(path)))
    result["run"] = name
    if a.json:
        a.json.write_text(json.dumps(result, indent=1) + chr(10), encoding="utf-8")
    report(name, result)
    counts = {v: sum(p["verdict"] == v for p in result["pauses"]) for v in ("clean", "gpu_bound", "unexplained")}
    print(f"M24_PAUSE_ANALYZE {name} pauses={len(result['pauses'])} clean={counts['clean']} gpu_bound={counts['gpu_bound']} "
          f"unexplained={counts['unexplained']}")
    if not a.expect:
        return 0
    reasons = judge(result, a.expect)
    print(f"M24_PAUSE_CHECK {'FAIL' if reasons else 'PASS'} expect={a.expect} reasons={reasons}")
    return 1 if reasons else 0


# ---------------------------------------------------------------------------------------------------------------
# selftest: the reader and the judge on synthetic traces (no game, no private data)

def synthetic(slow_exit: bool, fence: bool) -> bytes:
    """A trace of 10 s of play, then three pauses of 3 s each followed by 5 s of play, 60 frames a second; with
    `slow_exit` twelve frames after every exit take two vblanks, with `fence` each of them waited for the GPU."""
    frequency, tick = 10_000_000, 166_667
    records = [(0, 1, 0, frequency & 0xFFFFFFFF, frequency >> 32)]
    now, plan = 0, [("play", 600, False)]
    for _ in range(3):
        plan += [("menu", 180, False), ("play", 300, True)]
    for kind, frames, after_pause in plan:
        if kind == "menu":
            records.append((4, 1, now - tick // 2, 0x0010, 0))
        for frame in range(frames):
            slow = after_pause and slow_exit and 5 <= frame < 17
            if slow and fence:
                records.append((11, 2, now + tick // 4, 20000, 1))
            now += tick * (2 if slow else 1)
            records.append((1, 3, now - tick // 8, 5400, 0))
            records.append((2, 2, now, 122 if kind == "play" else 270, (7 << 16 | 1) if kind == "play" else (1 << 16)))
            records.append((3, 4, now + 100, 200, 0))
            if kind == "menu" and frame == frames - 3:
                records.append((4, 1, now, 0x1000, 0))
    return b"".join(struct.pack("<IIqII", *r) for r in records)


def cmd_selftest(_a) -> int:
    failures = []

    def check(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    with tempfile.TemporaryDirectory() as folder:
        cases = {"clean": (False, False), "gpu_bound": (True, True), "unexplained": (True, False)}
        for verdict, (slow, fence) in cases.items():
            path = Path(folder) / f"{verdict}.r3ev"
            path.write_bytes(synthetic(slow, fence))
            result = analyze_events(path)
            pauses = result["pauses"]
            check(len(pauses) == 3, f"{verdict}: three pauses found ({len(pauses)})")
            check(all(p["verdict"] == verdict for p in pauses), f"{verdict}: every exit judged {verdict}")
            check(all(p["exit_key"] == "A" for p in pauses), f"{verdict}: exit key A")
            check(all(abs(p["menu_s"] - 3.0) < 0.05 for p in pauses), f"{verdict}: pause length 3 s")
            check(all(p["exit"]["cpswap"]["over_20ms"] == (12 if slow else 0) for p in pauses), f"{verdict}: slow frame count")
            check(all(p["exit"]["fence_waits"] == (12 if fence else 0) for p in pauses), f"{verdict}: fence wait count")
            check(result["control_play"].get("over_20ms") == 0, f"{verdict}: control has no slow frame")
            check(bool(judge(result, "clean")) == slow, f"{verdict}: judged against clean")
            check(bool(judge(result, "gpu_bound")) == (verdict == "unexplained"), f"{verdict}: judged against gpu_bound")
        bad = Path(folder) / "bad.r3ev"
        bad.write_bytes(bytes(48))
        try:
            read_events(bad)
            check(False, "a file without a frequency record is refused")
        except SystemExit:
            pass
    check(name_hash("__imp__VdSwap") != name_hash("__imp__NtClose"), "import name hash")
    check("VdSwap" in import_names().values(), "import list read")
    header = (TOOLS / "m24_event_trace.h").read_text(encoding="utf-8")
    check(f"kFenceSlowUs = {FENCE_SLOW_US};" in header, "fence threshold equals the header's")
    check("static_assert(sizeof(Record) == 24" in header, "record size stated in the header")
    check("kImportWait = 9" in header, "kind 9 (import wait) in the header")
    for number, (name, enumerator) in KINDS.items():
        check(f"{enumerator} = {number}" in header, f"kind {number} ({name}) in the header")
    for label in failures:
        print("FAIL", label)
    print(f"M24_PAUSE_SELFTEST {'FAIL' if failures else 'PASS'} failures={len(failures)}")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("tag")
    r.add_argument("--entry", default="swamp_60_human")
    r.add_argument("--steps", type=Path, default=ROOT / "config" / "m24" / "pause_lengths_swamp60.txt")
    r.add_argument("--seconds", type=int, default=200)
    r.add_argument("--scale", type=int, choices=(1, 2, 3), default=2)
    r.add_argument("--layer-coords", choices=("original", "separate"), default="separate")
    r.add_argument("--audio", action="store_true")
    r.add_argument("--gpu", action="store_true", help="sample the adapter's clock, power and load beside the run")
    r.add_argument("--env", action="append", default=[], help="KEY=VALUE for a bounded A/B (hidden tools only)")
    an = sub.add_parser("analyze")
    an.add_argument("run")
    an.add_argument("--json", type=Path)
    an.add_argument("--expect", choices=("clean", "gpu_bound"))
    sub.add_parser("selftest")
    a = ap.parse_args()
    return {"run": cmd_run, "analyze": cmd_analyze, "selftest": cmd_selftest}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Isolated test-only level smoke runs through the title's own "-level:NAME" developer option (M13, D-040).

    python tools/m13_level_sweep.py TAG LEVEL [LEVEL ...] [--idle 45] [--frame] [--steps FILE --seconds N]
    python tools/m13_level_sweep.py TAG --all [--skip-done]
    python tools/m13_level_sweep.py --summarize TAG [TAG ...] --out reports/milestone13/level_smoke.json

One hidden run per level (run name m13_<TAG>_<level>): the hidden runner passes "-level:<level>" on the guest
command line (run_milestone6.ps1 -TestLevel), the title starts in that level without its front end, the run
idles for --idle seconds (or executes --steps), the game is closed by the runner's timer, and the run directory
is evaluated mechanically. tools/m11_perf_sample.py runs beside it. --frame requests ONE explicit frame per run
(private) five seconds before the end.

This is NOT normal progression: no title screen, no profile / storage device selection, no save, and the level
starts with the engine's default game state instead of the state a player would bring. A row here says "this
level's content loads and the engine runs it on this runtime", nothing about playability or progression.

Result rows (private/work/m13/sweep_<TAG>.json, metadata only): load order, exit code, stub / fatal / trap /
invalid-target / exception-code census, imports not seen in any earlier kept run, failed file opens by
extension, guest frame pacing, draws per frame, audio activity, CPU and memory from the sampler.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m12_save_entry import FATAL_NEEDLES, INVALID_TARGET, PACING, ROUTINE_FAULTS, RUNS, TRAP, fault_codes, load_bursts, run_lines  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "m13"
LEVELS_DIR = ROOT / "private" / "extracted" / "5841123F" / "GamedataBIN"
SWAP = re.compile(r"M3 swap count=(\d+) .*draws_since=(\d+)")
AUDIO = re.compile(r"M4 audio_output frames=(\d+) nonzero=(\d+) .* energy=([0-9.e+-]+) peak=([0-9.e+-]+)")
XMA = re.compile(r"M4 xma_decoded frames=(\d+) context=(\d+)")
FAILED = re.compile(r"\[NtCreateFile\] FAILED: path='([^']*)' -> 0x([0-9a-fA-F]{8})")


def level_names() -> list[str]:
    return sorted(p.name for p in LEVELS_DIR.iterdir() if p.is_dir() and (p / f"{p.name}.lvl").is_file())


def known_imports() -> set[str]:
    """Imports reached by any kept run or session that is not an M13 run (cached)."""
    cache = WORK / "known_imports.json"
    if cache.is_file():
        return set(json.loads(cache.read_text()))
    names: set[str] = set()
    logs = [p for run in RUNS.iterdir() if run.is_dir() and not run.name.startswith("m13_") for p in run.glob("runtime*.log")]
    logs += list((ROOT / "private" / "play" / "sessions").glob("*/*.log"))
    for path in logs:
        with path.open(errors="replace") as stream:
            for line in stream:
                if "import=__imp__" in line:
                    m = re.search(r"import=__imp__(\w+)", line)
                    if m:
                        names.add(m[1])
    WORK.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(sorted(names)))
    return names


def evaluate(run_name: str, level: str, known: set[str]) -> dict:
    run = RUNS / run_name
    row: dict = {"run": run_name, "level": level, "entry": "isolated test-only (-level:)"}
    reasons: list[str] = []
    meta_path = run / "run.json"
    if not meta_path.is_file():
        row["reasons"] = ["run.json missing"]
        return row
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    lines = run_lines(run)
    row.update(executable_sha256=meta.get("executable_sha256"), test_level=meta.get("test_level"),
               exit_code=meta.get("exit_code"), forced_termination=meta.get("forced_termination"),
               game_foreground_events=meta.get("game_foreground_events"),
               game_foreground_samples=meta.get("game_foreground_samples"), log_lines=len(lines))
    if meta.get("test_level") != level:
        reasons.append("run was not started with this test level")
    if meta.get("exit_code") != 0:
        reasons.append(f"exit_code={meta.get('exit_code')}")
    if meta.get("forced_termination"):
        reasons.append("forced_termination")
    if meta.get("error") is not None:
        reasons.append(f"runner error {meta['error'].get('kind')}")
    if meta.get("game_foreground_events") or meta.get("game_foreground_samples"):
        reasons.append("game foreground event")
    bursts = load_bursts(lines)
    row["loads"] = bursts
    if level.lower() not in bursts:
        reasons.append("level never opened")
    stubs = sorted({m[1] for line in lines if " stub=true " in line and (m := re.search(r"import=__imp__(\w+)", line))})
    imports = {m[1] for line in lines if (m := re.search(r"import=__imp__(\w+)", line))}
    fatal = sum(any(n in line for n in FATAL_NEEDLES) for line in lines)
    traps = sum(bool(TRAP.search(line)) for line in lines)
    invalid = sum(bool(INVALID_TARGET.search(line)) for line in lines)
    codes = fault_codes(run)
    other = {c: n for c, n in codes.items() if c not in ROUTINE_FAULTS}
    errors = Counter(re.sub(r"^\[[^\]]*\] ", "", line)[:120] for line in lines if "] [error] " in line)
    row.update(stub_imports=stubs, imports_distinct=len(imports), new_imports=sorted(imports - known),
               fatal_lines=fatal, trap_lines=traps, invalid_target_lines=invalid, fault_codes=codes,
               error_lines=sum(errors.values()), error_kinds=len(errors),
               frames_saved=len(list(run.glob("m3_frame_*.bmp"))))
    for label, count in (("fatal/critical lines", fatal), ("trap lines", traps), ("invalid-target lines", invalid)):
        if count:
            reasons.append(f"{label}={count}")
    if stubs:
        reasons.append("stubbed imports " + ",".join(stubs))
    if other:
        reasons.append("exception codes " + ",".join(f"{c}x{n}" for c, n in sorted(other.items())))

    failed = Counter()
    for line in lines:
        m = FAILED.search(line)
        if m:
            name = m[1].replace("/", "\\").rsplit("\\", 1)[-1].lower()
            failed[(name.rsplit(".", 1)[-1] if "." in name else "(none)") + ":" + m[2].lower()] += 1
    row["failed_opens_by_extension"] = dict(sorted(failed.items()))

    windows = [(int(m[3]), int(m[4]), int(m[9]), int(m[11])) for line in lines
               if (m := PACING.search(line)) and m[1] == "guest_swap"]
    steady = windows[1:] or windows  # the first window contains the load
    total = sum(w[0] for w in steady)
    row["guest_swap"] = {"windows": len(windows), "steady_n": total,
                         "steady_mean_us": round(sum(w[0] * w[1] for w in steady) / total) if total else None,
                         "steady_max_us": max((w[2] for w in steady), default=None),
                         "steady_over_33ms": sum(w[3] for w in steady)}
    swaps = [(int(m[1]), int(m[2])) for line in lines if (m := SWAP.search(line))]
    row["swaps_logged_last"] = swaps[-1][0] if swaps else 0
    row["draws_in_last_logged_frame"] = swaps[-1][1] if swaps else None
    if not swaps or swaps[-1][0] < 600:
        reasons.append("fewer than 600 guest frames presented")
    audio = [(int(m[1]), int(m[2]), float(m[3]), float(m[4])) for line in lines if (m := AUDIO.search(line))]
    xma = [(int(m[1]), int(m[2])) for line in lines if (m := XMA.search(line))]
    row["audio_output"] = {"frames_logged_last": audio[-1][0] if audio else 0,
                           "nonzero_frames_last": audio[-1][1] if audio else 0,
                           "peak_max": max((a[3] for a in audio), default=0.0)}
    row["xma"] = {"decoded_frames_logged_last": max((x[0] for x in xma), default=0), "contexts_seen": len({x[1] for x in xma})}

    perf_path = run / "perf_samples.json"
    if perf_path.is_file():
        samples = json.loads(perf_path.read_text())["samples"]
        tail = samples[len(samples) // 2:]
        cpu = [s["cpu_percent_one_core"] for s in tail if s.get("cpu_percent_one_core") is not None]
        row["perf"] = {"seconds": samples[-1]["t"] if samples else 0,
                       "cpu_percent_one_core_second_half": round(sum(cpu) / len(cpu), 1) if cpu else None,
                       "private_mb_max": round(max(s["private_bytes"] for s in samples) / 1048576) if samples else None,
                       "working_set_mb_max": round(max(s["working_set"] for s in samples) / 1048576) if samples else None,
                       "gpu_dedicated_mb_max": round(max((s.get("gpu_dedicated_bytes", 0) for s in samples), default=0) / 1048576),
                       "threads_last": samples[-1]["threads"] if samples else None,
                       "handles_last": samples[-1]["handles"] if samples else None}
    row["reasons"] = reasons
    return row


def run_level(tag: str, level: str, idle: int, frame: bool, steps: Path | None, seconds: int | None, known: set[str]) -> dict:
    run_name = f"m13_{tag}_{level}"
    if (RUNS / run_name).exists():
        raise SystemExit(f"run directory exists: {run_name}")
    WORK.mkdir(parents=True, exist_ok=True)
    if steps is None:
        steps = WORK / f"steps_{run_name}.txt"
        body = [f"wait {max(1, idle - 5)}", "frame end" if frame else "wait 0.1", "wait 5"]
        steps.write_text("\n".join(body) + "\n", encoding="ascii")
        seconds = idle + 15
    py = sys.executable
    perf = subprocess.Popen([py, str(ROOT / "tools" / "m11_perf_sample.py"), run_name], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with (WORK / f"{run_name}.driver.log").open("w") as log:
        try:
            subprocess.run([py, str(ROOT / "tools" / "m9_license_run.py"), run_name, str(steps), "--license-mask", "1",
                            "--seconds", str(seconds), "--play", "--test-level", level], cwd=ROOT, stdout=log,
                           stderr=subprocess.STDOUT, timeout=seconds + 300)
        except subprocess.TimeoutExpired:
            pass
    try:
        perf.wait(timeout=90)
    except subprocess.TimeoutExpired:
        perf.kill()
    row = evaluate(run_name, level, known)
    if (RUNS / run_name).is_dir():
        (RUNS / run_name / "m13_level.json").write_text(json.dumps(row, indent=1) + "\n", encoding="utf-8")
    state = "FAIL" if row["reasons"] else "PASS"
    swap = row.get("guest_swap") or {}
    print(f"M13_LEVEL {state} {level} loads={','.join(row.get('loads', []))} frames={row.get('swaps_logged_last')} "
          f"mean_us={swap.get('steady_mean_us')} over33={swap.get('steady_over_33ms')} new_imports={row.get('new_imports')} "
          f"private_mb={(row.get('perf') or {}).get('private_mb_max')}"
          + (f" reasons={';'.join(row['reasons'])}" if row["reasons"] else ""), flush=True)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("levels", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--skip-done", action="store_true", help="skip levels already present in this tag's result file")
    ap.add_argument("--idle", type=int, default=45)
    ap.add_argument("--frame", action="store_true")
    ap.add_argument("--steps", type=Path)
    ap.add_argument("--seconds", type=int)
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if a.summarize:
        rows = []
        for tag in [a.tag, *a.levels]:
            rows += json.loads((WORK / f"sweep_{tag}.json").read_text())
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
        passed = sum(not r["reasons"] for r in rows)
        print(f"{len(rows)} rows, {passed} PASS, {len(rows) - passed} FAIL")
        return 0
    if not re.fullmatch(r"[A-Za-z0-9]+", a.tag) or not 10 <= a.idle <= 900 or bool(a.steps) != bool(a.seconds):
        ap.error("invalid TAG, --idle (10..900), or --steps without --seconds")
    available = level_names()
    levels = available if a.all else a.levels
    unknown = [name for name in levels if name not in available]
    if unknown or not levels:
        ap.error(f"unknown or missing levels: {unknown}")
    result = WORK / f"sweep_{a.tag}.json"
    rows = json.loads(result.read_text()) if result.is_file() else []
    done = {row["level"] for row in rows}
    known = known_imports()
    for level in levels:
        if a.skip_done and level in done:
            continue
        rows.append(run_level(a.tag, level, a.idle, a.frame, a.steps, a.seconds, known))
        result.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
        time.sleep(2)
    return 1 if any(row["reasons"] for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())

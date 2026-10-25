"""Private save-entry registry and hidden regression checks for saves (M12).

An entry is a copy of a profile ("user root") with exactly one save slot, kept under private/saves/NAME/ together
with entry.json (hashes, level name read from the save header, provenance). Entries are never run on directly: a
smoke run works on a copy under private/work/m9_profiles/RUN. Only metadata is printed or stored (magic and level
name); no other save bytes. Nothing here is committed.

  register NAME --profile DIR --source TEXT [--source-run RUN]
  list [--json]
  smoke NAME RUN [--idle 30] [--dry-run]    load the entry's save from the title, stand idle, evaluate
  evaluate NAME RUN                         evaluate an existing run directory against an entry (no launch)
  roundtrip RUN [--dry-run]                 fresh New Game -> save -> clean exit -> relaunch -> Load -> evaluate
  scenario NAME RUN --steps FILE --seconds N --expect A,B,...
                                            run a step file (no frame / probe steps) on a copy of the entry and
                                            require the content loads A,B,... in that order, e.g.
                                            --steps config/m12/pause_reload_exit.txt --seconds 300
                                            --expect menumap,intro_15,intro_15,menumap

Usage: python tools/m12_save_entry.py {register,list,smoke,evaluate,roundtrip,scenario} ...

Final lines: M12_SMOKE / M12_ROUNDTRIP / M12_SCENARIO PASS|FAIL ...; exit code 0 on PASS, 1 on FAIL.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAVES = ROOT / "private" / "saves"
RUNS = ROOT / "private" / "work" / "m6_runs"
PROFILES = ROOT / "private" / "work" / "m9_profiles"
STEPS = ROOT / "private" / "work" / "m12_steps"
EXE = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release" / "r3hd.exe"
NAME_RE = re.compile(r"[A-Za-z0-9_-]+")
PACING = re.compile(r"M11 pacing series=(\w+) window=(\d+) n=(\d+) mean_us=(\d+) min_us=(\d+) p50_us=(\d+) "
                    r"p95_us=(\d+) p99_us=(\d+) max_us=(\d+) over_20ms=(\d+) over_33ms=(\d+) over_50ms=(\d+) "
                    r"over_100ms=(\d+)")
FATAL_NEEDLES = ("] [critical] ", "[FATAL]", "M2 fatal")
TRAP = re.compile(r"tw/td trap hit \(type \d+\)|Unknown trap type \d+")
INVALID_TARGET = re.compile(r"[Ii]nvalid.*(indirect|function)|Unresolved indirect")
# Thread naming, and the host transport code of guest-raised records (tools/m4_seh.h); as in play.ps1 -Summarize.
ROUTINE_FAULTS = ("406D1388", "E0473458")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exe_sha() -> str | None:
    return sha256(EXE) if EXE.is_file() else None


def find_saves(profile: Path) -> list[Path]:
    """Save slots: <XUID>/5841123F/00000001/<SLOT>/<SLOT>."""
    return sorted(p for p in profile.glob("*/5841123F/00000001/*/*") if p.is_file() and p.name == p.parent.name)


def read_save_meta(save: Path) -> tuple[bool, str | None]:
    data = save.read_bytes()
    if data[:4] != b"AAAA":
        return False, None
    end = data.find(b"\0", 152)
    raw = data[152:end if end >= 0 else len(data)]
    return True, raw.decode("ascii", errors="replace")


def profile_files(profile: Path) -> list[dict]:
    return [{"path": p.relative_to(profile).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(profile.rglob("*")) if p.is_file()]


def load_entry(name: str) -> dict:
    path = SAVES / name / "entry.json"
    if not NAME_RE.fullmatch(name) or not path.is_file():
        raise SystemExit(f"no such entry: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_lines(run: Path) -> list[str]:
    rotated = sorted(run.glob("runtime.*.log"), key=lambda p: -int(p.name.split(".")[1])
                     if p.name.split(".")[1].isdigit() else 0)
    parts = rotated + ([run / "runtime.log"] if (run / "runtime.log").exists() else [])
    if not parts:
        parts = sorted(run.glob("runtime*.log"))
    lines: list[str] = []
    for part in parts:
        lines += part.read_text(errors="replace").splitlines()
    return lines


def stamp(line: str) -> datetime | None:
    try:
        return datetime.strptime(line[1:24], "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return None


def opened_in_order(lines: list[str]) -> list[str]:
    opened: list[str] = []
    for line in lines:
        m = re.search(r"vfs_open path=.*?([A-Za-z_0-9]+\.(?:lvl|bik)) result=00000000", line)
        if m and m[1] not in ("fix.lvl", "transit.lvl") and (not opened or opened[-1] != m[1]):
            opened.append(m[1])
    return opened


def load_bursts(lines: list[str]) -> list[str]:
    """Levels and movies loaded, in order. Unlike opened_in_order a repeated load counts again: one load is a
    burst of opens of the same file, and a new burst starts after more than five seconds without one."""
    bursts: list[str] = []
    last_name, last_time = None, None
    for line in lines:
        m = re.search(r"vfs_open path=.*?([A-Za-z_0-9]+)\.(?:lvl|bik) result=00000000", line)
        if not m or m[1].lower() in ("fix", "transit"):
            continue
        when = stamp(line)
        if m[1].lower() != last_name or (when and last_time and (when - last_time).total_seconds() > 5):
            bursts.append(m[1].lower())
        last_name, last_time = m[1].lower(), when or last_time
    return bursts


def fault_codes(run: Path) -> dict[str, int]:
    codes: dict[str, int] = {}
    log = run / "m2_faults.log"
    if log.is_file():
        for line in log.read_text(errors="replace").splitlines():
            m = re.match(r"M2 exception code=([0-9A-Fa-f]{8})", line)
            if m:
                code = m[1].upper()
                codes[code] = codes.get(code, 0) + 1
    return codes


def working_profile(meta: dict, run_name: str) -> Path:
    user_root = meta.get("user_root")
    return PROFILES / (Path(str(user_root)).name if user_root else run_name)


def evaluate_run(run_name: str, level_key: str, reference_sha: str | None, forbid_movie: str | None = None) -> dict:
    """Common checks on a finished run directory. Returns facts and failure reasons; never raises on bad runs."""
    run = RUNS / run_name
    reasons: list[str] = []
    facts: dict = {"run": run_name, "level_key": level_key}
    meta_path = run / "run.json"
    if not meta_path.is_file():
        reasons.append("run.json missing")
        facts["reasons"] = reasons
        return facts
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    lines = run_lines(run)
    facts.update(executable_sha256=meta.get("executable_sha256"), log_lines=len(lines),
                 exit_code=meta.get("exit_code"), forced_termination=meta.get("forced_termination"))
    if meta.get("exit_code") != 0:
        reasons.append(f"exit_code={meta.get('exit_code')}")
    if meta.get("forced_termination"):
        reasons.append("forced_termination")
    if meta.get("error") is not None:
        reasons.append("run.json error")
    driver = run / "license_run.json"
    if driver.is_file():
        error = json.loads(driver.read_text(encoding="utf-8-sig")).get("error")
        if error is not None:
            reasons.append(f"driver error {error.get('type')}")
    if meta.get("game_foreground_events") != 0 or meta.get("game_foreground_samples") != 0:
        reasons.append(f"foreground events={meta.get('game_foreground_events')} samples={meta.get('game_foreground_samples')}")

    level_open = re.compile(rf"vfs_open path=.*?[\\/]{re.escape(level_key)}[\\/]{re.escape(level_key)}\.lvl "
                            r"result=00000000", re.IGNORECASE)
    first_open = next((i for i, line in enumerate(lines) if level_open.search(line)), None)
    if first_open is None:
        reasons.append(f"level {level_key} never opened")
    if forbid_movie:
        movie = re.compile(rf"[\\/]{re.escape(forbid_movie)} result=00000000", re.IGNORECASE)
        facts["forbidden_movie_opens"] = sum(bool(movie.search(line)) for line in lines)
        if facts["forbidden_movie_opens"]:
            reasons.append(f"{forbid_movie} opened")
    stubs = sum(" stub=true " in line for line in lines)
    fatal = sum(any(n in line for n in FATAL_NEEDLES) for line in lines)
    traps = sum(bool(TRAP.search(line)) for line in lines)
    invalid = sum(bool(INVALID_TARGET.search(line)) for line in lines)
    frames = len(list(run.glob("m3_frame_*.bmp")))
    codes = fault_codes(run)
    other_codes = {c: n for c, n in codes.items() if c not in ROUTINE_FAULTS}
    facts.update(stub_import_lines=stubs, fatal_lines=fatal, trap_lines=traps, invalid_target_lines=invalid,
                 frames_saved=frames, fault_codes=codes)
    for label, count in (("stubbed import lines", stubs), ("fatal/critical lines", fatal), ("trap lines", traps),
                         ("invalid-target lines", invalid), ("frame captures", frames)):
        if count:
            reasons.append(f"{label}={count}")
    if other_codes:
        reasons.append("exception codes " + ",".join(f"{c}x{n}" for c, n in sorted(other_codes.items())))

    profile = working_profile(meta, run_name)
    saves = find_saves(profile) if profile.is_dir() else []
    valid = [s for s in saves if read_save_meta(s)[0]]
    facts["profile"] = profile.name
    if not valid:
        reasons.append("working profile has no save with valid magic")
    else:
        facts["save_sha256"] = sha256(valid[0])
        facts["save_level_now"] = read_save_meta(valid[0])[1]
        facts["save_unchanged"] = reference_sha is not None and facts["save_sha256"] == reference_sha

    imports = {m[1] for line in lines if (m := re.search(r"import=__imp__(\w+)", line))}
    facts["imports_distinct"] = len(imports)
    facts["opened_in_order"] = opened_in_order(lines)
    if first_open is not None:
        t0 = stamp(lines[first_open])
        t1 = next((t for t in map(stamp, reversed(lines)) if t), None)
        facts["seconds_from_level_open"] = round((t1 - t0).total_seconds(), 1) if t0 and t1 else None
        windows = []
        for line in lines[first_open:]:
            m = PACING.search(line)
            if m and m[1] == "guest_swap":
                windows.append((int(m[3]), int(m[4]), int(m[11])))
        total = sum(n for n, _, _ in windows)
        facts["guest_swap"] = {"windows": len(windows), "n": total,
                               "mean_us": round(sum(n * mean for n, mean, _ in windows) / total) if total else None,
                               "over_33ms": sum(o for _, _, o in windows)}
    facts["reasons"] = reasons
    return facts


def write_smoke(run_name: str, facts: dict) -> None:
    if (RUNS / run_name).is_dir():
        (RUNS / run_name / "m12_smoke.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")


def smoke_line(entry: dict, run_name: str, facts: dict) -> str:
    reasons = facts["reasons"]
    head = f"M12_SMOKE {'FAIL' if reasons else 'PASS'} name={entry['name']} level={entry['level']} run={run_name}"
    return head + (f" reasons={';'.join(reasons)}" if reasons else "")


def evaluate_entry(entry: dict, run_name: str) -> dict:
    reference = next((f["sha256"] for f in entry["files"] if f["path"].endswith(f"/{entry['slot']}")
                      and "/Headers/" not in f["path"]), None)
    facts = evaluate_run(run_name, entry["level_key"], reference)
    write_smoke(run_name, facts)
    return facts


def load_steps(idle: int) -> list[str]:
    return [
        "# M12 smoke: relaunch on a copy of a registered save -> Load -> slot -> stand idle. No frames, no probes.",
        r"log VIDEOS\ubi.bik result=00000000",
        r"log menumap\menumap.lvl result=00000000",
        "wait 10", "press 40", "wait 12",
        "axis 301 -32767", "wait 0.3", "axis 301 0",
        "wait 2", "press 44", "wait 8", "press 44",
        f"wait {20 + idle}",
    ]


def driver_command(run_name: str, steps: Path, seconds: int, user_root: str) -> list[str]:
    return [sys.executable, str(ROOT / "tools" / "m9_license_run.py"), run_name, str(steps), "--license-mask", "1",
            "--seconds", str(seconds), "--user-root", user_root, "--play"]


def run_driver(command: list[str], log: Path, seconds: int) -> str | None:
    """Runs the driver; returns an error text (or None). A failing driver is evaluated afterwards, not raised."""
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log.open("w", encoding="utf-8") as output:
            done = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=seconds + 300)
        return None if done.returncode == 0 else f"driver exit code {done.returncode}"
    except subprocess.TimeoutExpired:
        return "driver timeout"
    except OSError as exc:
        return f"driver start failed: {exc}"


def cmd_register(args) -> int:
    if not NAME_RE.fullmatch(args.name):
        raise SystemExit("invalid NAME")
    target = SAVES / args.name
    if target.exists():
        raise SystemExit(f"entry already exists: {target}")
    profile = Path(args.profile)
    profile = profile if profile.is_absolute() else ROOT / profile
    saves = find_saves(profile) if profile.is_dir() else []
    if len(saves) != 1:
        raise SystemExit(f"expected exactly one save slot in {profile}, found {len(saves)}")
    valid, level = read_save_meta(saves[0])
    if not valid or not level:
        raise SystemExit("save has no valid magic or level name")
    target.mkdir(parents=True)
    shutil.copytree(profile, target / "profile")
    source_exe = None
    if args.source_run:
        meta_path = RUNS / args.source_run / "run.json"
        if meta_path.is_file():
            source_exe = json.loads(meta_path.read_text(encoding="utf-8-sig")).get("executable_sha256")
    entry = {
        "name": args.name, "created_utc": datetime.now(timezone.utc).isoformat(), "source": args.source,
        "source_run": args.source_run, "source_run_executable_sha256": source_exe,
        "executable_sha256": exe_sha(), "files": profile_files(target / "profile"),
        "slot": saves[0].name, "level": level, "level_key": level.lower(),
    }
    (target / "entry.json").write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    print(f"registered {args.name}: slot={entry['slot']} level={level} files={len(entry['files'])}")
    return 0


def cmd_list(args) -> int:
    entries = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SAVES.glob("*/entry.json"))]
    if args.json:
        print(json.dumps(entries, indent=2))
        return 0
    for e in entries:
        save = next((f["sha256"] for f in e["files"] if f["path"].endswith(f"/{e['slot']}")
                     and "/Headers/" not in f["path"]), "")
        print(f"{e['name']}  level={e['level']}  save={save[:12]}  source={e['source']}")
    return 0


def stored_profile_matches(entry: dict) -> bool:
    profile = SAVES / entry["name"] / "profile"
    return profile.is_dir() and profile_files(profile) == entry["files"]


def cmd_smoke(args) -> int:
    entry = load_entry(args.name)
    run = args.run
    if not NAME_RE.fullmatch(run) or not 5 <= args.idle <= 600:
        raise SystemExit("invalid RUN or --idle (5..600)")
    steps = STEPS / f"{run}.txt"
    work = PROFILES / run
    if (RUNS / run).exists() or work.exists() or steps.exists():
        raise SystemExit(f"run, profile or step file already exists for {run}")
    if not stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {args.name} no longer matches entry.json")
    seconds = args.idle + 85
    command = driver_command(run, steps, seconds, run)
    created_steps_dir = not STEPS.exists()
    shutil.copytree(SAVES / args.name / "profile", work)
    STEPS.mkdir(parents=True, exist_ok=True)
    steps.write_text("\n".join(load_steps(args.idle)) + "\n", encoding="ascii")
    if args.dry_run:
        print(" ".join(command))
        shutil.rmtree(work)
        steps.unlink()
        if created_steps_dir and not any(STEPS.iterdir()):
            STEPS.rmdir()
        return 0
    error = run_driver(command, ROOT / "private" / "work" / f"m12_{run}.driver.log", seconds)
    if error:
        print(f"driver problem: {error}")
    facts = evaluate_entry(entry, run)
    if error and not (RUNS / run / "run.json").is_file():
        facts["reasons"].append(error)
    print(smoke_line(entry, run, facts))
    return 1 if facts["reasons"] else 0


def cmd_scenario(args) -> int:
    entry = load_entry(args.name)
    run, source = args.run, Path(args.steps)
    source = source if source.is_absolute() else ROOT / source
    expect = [name.strip().lower() for name in args.expect.split(",") if name.strip()]
    if not NAME_RE.fullmatch(run) or not 30 <= args.seconds <= 1500 or not expect:
        raise SystemExit("invalid RUN, --seconds (30..1500) or --expect")
    words = [line.split("#", 1)[0].split() for line in source.read_text().splitlines()]
    if any(step and step[0] in ("frame", "probe") for step in words):
        raise SystemExit("a scenario step file may not contain frame or probe steps")
    work = PROFILES / run
    if (RUNS / run).exists() or work.exists():
        raise SystemExit(f"run or profile already exists for {run}")
    if not stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {args.name} no longer matches entry.json")
    shutil.copytree(SAVES / args.name / "profile", work)
    error = run_driver(driver_command(run, source, args.seconds, run), ROOT / "private" / "work" / f"m12_{run}.driver.log",
                       args.seconds)
    if error:
        print(f"driver problem: {error}")
    facts = evaluate_entry(entry, run)
    if error and not (RUNS / run / "run.json").is_file():
        facts["reasons"].append(error)
    bursts = load_bursts(run_lines(RUNS / run)) if (RUNS / run).is_dir() else []
    remaining = iter(bursts)
    if not all(any(name == seen for seen in remaining) for name in expect):
        facts["reasons"].append("expected loads not observed in order")
    facts.update(steps=str(args.steps), expected_loads=expect, load_bursts=bursts)
    write_smoke(run, facts)
    state = "FAIL" if facts["reasons"] else "PASS"
    print(f"M12_SCENARIO {state} name={entry['name']} run={run} loads={','.join(bursts)}"
          + (f" reasons={';'.join(facts['reasons'])}" if facts["reasons"] else ""))
    return 1 if facts["reasons"] else 0


def cmd_evaluate(args) -> int:
    entry = load_entry(args.name)
    facts = evaluate_entry(entry, args.run)
    print(smoke_line(entry, args.run, facts))
    return 1 if facts["reasons"] else 0


def one_valid_save(profile: Path) -> tuple[Path | None, str | None]:
    saves = find_saves(profile) if profile.is_dir() else []
    if len(saves) != 1 or not read_save_meta(saves[0])[0]:
        return None, None
    return saves[0], read_save_meta(saves[0])[1]


def cmd_roundtrip(args) -> int:
    run = args.run
    if not NAME_RE.fullmatch(run):
        raise SystemExit("invalid RUN")
    run_a, run_b = f"{run}_a", f"{run}_b"
    steps_a = ROOT / "config" / "m12" / "newgame_save.txt"
    steps_b = STEPS / f"{run_b}.txt"
    if (RUNS / run_a).exists() or (RUNS / run_b).exists() or (PROFILES / run).exists() or steps_b.exists():
        raise SystemExit(f"run, profile or step file already exists for {run}")
    if not steps_a.is_file():
        raise SystemExit(f"missing {steps_a}")
    command_a = driver_command(run_a, steps_a, 80, run)
    command_b = driver_command(run_b, steps_b, 95, run)
    if args.dry_run:
        print(" ".join(command_a))
        print(" ".join(command_b))
        return 0
    reasons: list[str] = []
    record: dict = {"run": run}
    error = run_driver(command_a, ROOT / "private" / "work" / f"m12_{run_a}.driver.log", 80)
    a_facts = {"run": run_a, "driver_error": error}
    meta_path = RUNS / run_a / "run.json"
    if not meta_path.is_file():
        reasons.append("run A: run.json missing")
    else:
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        a_facts.update(exit_code=meta.get("exit_code"), forced_termination=meta.get("forced_termination"),
                       game_foreground_events=meta.get("game_foreground_events"),
                       game_foreground_samples=meta.get("game_foreground_samples"),
                       executable_sha256=meta.get("executable_sha256"))
        if meta.get("exit_code") != 0 or meta.get("forced_termination"):
            reasons.append(f"run A: exit_code={meta.get('exit_code')} forced={meta.get('forced_termination')}")
        if meta.get("game_foreground_events") != 0 or meta.get("game_foreground_samples") != 0:
            reasons.append("run A: foreground events/samples")
        driver = RUNS / run_a / "license_run.json"
        if driver.is_file() and json.loads(driver.read_text(encoding="utf-8-sig")).get("error") is not None:
            reasons.append("run A: driver error")
    if error and not meta_path.is_file():
        reasons.append(f"run A: {error}")
    save, level = one_valid_save(PROFILES / run)
    if save is None or not level:
        reasons.append("run A: no single save with valid magic")
    else:
        a_facts.update(save_sha256=sha256(save), level=level)
    record["run_a"] = a_facts
    final_level = a_facts.get("level")
    if reasons or save is None or not level:
        record["reasons"] = reasons
        return finish_roundtrip(run, run_b, record, final_level, reasons)

    STEPS.mkdir(parents=True, exist_ok=True)
    steps_b.write_text("\n".join(load_steps(10)) + "\n", encoding="ascii")
    error = run_driver(command_b, ROOT / "private" / "work" / f"m12_{run_b}.driver.log", 95)
    facts = evaluate_run(run_b, level.lower(), a_facts["save_sha256"], forbid_movie="intro.bik")
    write_smoke(run_b, facts)
    if error and not (RUNS / run_b / "run.json").is_file():
        facts["reasons"].append(error)
    if facts.get("save_sha256") is not None and facts["save_sha256"] != a_facts["save_sha256"]:
        facts["reasons"].append("save changed during run B")
    record["run_b"] = facts
    reasons += [f"run B: {r}" for r in facts["reasons"]]
    return finish_roundtrip(run, run_b, record, level, reasons)


def finish_roundtrip(run: str, run_b: str, record: dict, level: str | None, reasons: list[str]) -> int:
    record["reasons"] = reasons
    record["result"] = "FAIL" if reasons else "PASS"
    out_dir = RUNS / run_b
    if not out_dir.is_dir():
        out_dir = RUNS / f"{run}_a"
    if out_dir.is_dir():
        (out_dir / "m12_roundtrip.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if reasons:
        print(f"M12_ROUNDTRIP FAIL run={run} reasons={';'.join(reasons)}")
        return 1
    print(f"M12_ROUNDTRIP PASS run={run} level={level}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("register")
    p.add_argument("name")
    p.add_argument("--profile", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--source-run", default=None)
    p.set_defaults(func=cmd_register)
    p = sub.add_parser("list")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("smoke")
    p.add_argument("name")
    p.add_argument("run")
    p.add_argument("--idle", type=int, default=30)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_smoke)
    p = sub.add_parser("evaluate")
    p.add_argument("name")
    p.add_argument("run")
    p.set_defaults(func=cmd_evaluate)
    p = sub.add_parser("roundtrip")
    p.add_argument("run")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_roundtrip)
    p = sub.add_parser("scenario")
    p.add_argument("name")
    p.add_argument("run")
    p.add_argument("--steps", required=True)
    p.add_argument("--seconds", type=int, required=True)
    p.add_argument("--expect", required=True)
    p.set_defaults(func=cmd_scenario)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

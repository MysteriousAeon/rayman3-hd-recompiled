#!/usr/bin/env python3
"""Hidden campaign-compatibility scenarios of Milestone 19.

    python tools/m19_campaign_check.py TAG [SCENARIO ...]      -> M19_CAMPAIGN_CHECK PASS n/n
    python tools/m19_campaign_check.py --list

Every scenario is one or two hidden runs (m9_license_run.py: hidden window, scoped input, no captures) with
tools/m18_progress_watch.py reading the title's progression state beside them. Campaign scenarios run on a
working copy of the private save entry `wood_11_human`; the entry and the human profile are hashed before and
after and never opened for writing. Scenarios marked isolated use the test-only level entry (D-040) and are
not progression. What each one establishes is in its `about` text; records go to private/work/m19/check/.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
from m5_live import Actor, Process  # noqa: E402
from m18_revisit_check import HUMAN, ENTRY, REDIRECT, NO_SAVE, save_fields, tree_hashes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "m19" / "check"
CONFIG = ROOT / "config" / "m19"
TOOLS = ROOT / "tools"
SWITCHES = ("R3HD_TEST_WORLD_END", "R3HD_REVISIT")


def states_of(run: str) -> list:
    """The watcher's change records of one run, folded into full states."""
    out, state = [], {}
    watch = WORK / f"{run}.jsonl"
    for line in watch.read_text(encoding="utf-8").splitlines() if watch.is_file() else []:
        record = json.loads(line)
        record.pop("wall", None)
        state = {**state, **record}
        out.append(state)
    return out


def ever(states: list, **want) -> bool:
    return any(all(str(s.get(k)).lower() == str(v).lower() for k, v in want.items()) for s in states)


def wait_for_log(run_dir: Path, needle: str, game: subprocess.Popen, seconds: float) -> bool:
    pattern, end = re.compile(re.escape(needle), re.IGNORECASE), time.monotonic() + seconds
    while time.monotonic() < end and game.poll() is None:
        if any(pattern.search(p.read_text(errors="replace")) for p in run_dir.glob("runtime*.log")):
            return True
        time.sleep(1)
    return False


def attach(run_dir: Path) -> tuple[int, str]:
    pid = int(json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"])
    for path in sorted(run_dir.glob("runtime*.log")):
        m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", path.read_text(errors="replace"))
        if m:
            return pid, m.group(1)
    raise RuntimeError("guest base not in the runtime log")


def hidden_run(run: str, steps: Path, seconds: int, *, user_root: str = "", test_level: str = "", env: dict | None = None,
               beside=None) -> list:
    """One hidden run with the progression watcher. `beside(run_dir, game, log)` may drive read-only tools and
    scoped input while the game runs; it returns failure reasons. Returns the driver-side reasons."""
    WORK.mkdir(parents=True, exist_ok=True)
    run_dir = m12.RUNS / run
    if run_dir.exists():
        raise SystemExit(f"run already exists: {run}")
    command = [sys.executable, str(TOOLS / "m9_license_run.py"), run, str(steps), "--license-mask", "1",
               "--seconds", str(seconds), "--play"]
    command += ["--test-level", test_level] if test_level else ["--user-root", user_root]
    environment = {k: v for k, v in os.environ.items() if k not in SWITCHES}
    environment.update(env or {})
    reasons = []
    watcher = subprocess.Popen([sys.executable, str(TOOLS / "m18_progress_watch.py"), str(run_dir), str(WORK / f"{run}.jsonl"),
                                "--seconds", str(seconds), "--wait", "180"], cwd=ROOT, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    with (WORK / f"{run}.driver.log").open("w", encoding="utf-8") as log:
        game = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            if beside is not None:
                reasons += beside(run_dir, game, log) or []
        except (OSError, RuntimeError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as exc:
            reasons.append(f"beside-run tool failed: {type(exc).__name__}: {exc}")
        finally:
            try:
                game.wait(timeout=seconds + 300)
            except subprocess.TimeoutExpired:
                (run_dir / "cancel.request").write_text("m19 abort\n", encoding="ascii")
                try:
                    game.wait(timeout=60)
                except subprocess.TimeoutExpired:  # last resort, this driver's own process tree only
                    subprocess.run(["taskkill", "/PID", str(game.pid), "/T", "/F"], capture_output=True, check=False)
                reasons.append("driver timeout")
        if game.returncode != 0:
            reasons.append(f"driver exit code {game.returncode}")
    try:
        watcher.wait(timeout=30)
    except subprocess.TimeoutExpired:
        watcher.kill()
    return reasons


def mechanical(run: str, level: str, isolated: bool) -> tuple[dict, list]:
    facts = m12.evaluate_run(run, level, None)
    return facts, [r for r in facts["reasons"] if not (isolated and r == NO_SAVE)]


def fly_intro_10(run_dir: Path, game: subprocess.Popen, log) -> list:
    """Intro_10 by the M5 flight pilot: read-only probes, left-stick keys through the run's own schedule."""
    if not wait_for_log(run_dir, r"intro_10\intro_10.lvl result=00000000", game, 240):
        return ["Intro_10 did not open"]
    time.sleep(22)
    pid, base = attach(run_dir)
    actors = run_dir / "actors.json"
    subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(actors), "--regions"],
                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    subprocess.run([sys.executable, str(TOOLS / "m5_flight_pilot.py"), str(pid), base, str(actors),
                    str(run_dir / "schedule.txt"), str(run_dir / "pilot.log"), "--seconds", "200"],
                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=260)
    lums = 0
    for line in (run_dir / "pilot.log").read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            lums = max(lums, int(json.loads(line).get("lums") or 0))
        except (ValueError, TypeError):
            pass
    return [] if lums >= 6 else [f"flight pilot collected {lums} of 6 red lums (pilot variance, not a title result)"]


def revisit_save_reload(tag: str) -> dict:
    """T1. Run A: Revisit the Fairy Council from the genuine wood_11 save, fly Intro_10 to its end with normal
    input, let the title save at the level change. Run B: relaunch on that profile, Load, "continue your game"."""
    name = f"m19_{tag}_revisit_save"
    run_a, run_b, profile = f"{name}_a", f"{name}_b", m12.PROFILES / name
    if profile.exists():
        raise SystemExit(f"profile already exists: {name}")
    entry = m12.load_entry(ENTRY)
    if not m12.stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {ENTRY} no longer matches entry.json")
    shutil.copytree(m12.SAVES / ENTRY / "profile", profile)
    before = save_fields(profile)
    reasons = hidden_run(run_a, CONFIG / "revisit_enter.txt", 420, user_root=name, beside=fly_intro_10)
    facts_a, mech = mechanical(run_a, "intro_15", False)
    reasons += [f"run A: {r}" for r in mech]
    a, saved = states_of(run_a), save_fields(profile)
    lines_a = m12.run_lines(m12.RUNS / run_a) if (m12.RUNS / run_a).is_dir() else []
    checks = [
        ("A: revisit entered from the campaign (flag 1, world 1, backup wood_11)",
         ever(a, revisit=1, rev_world=1, int_world=2, backup="wood_11", current="intro_10")),
        ("A: intro_15 reached in revisit mode", ever(a, revisit=1, current="intro_15")),
        ("A: loads end with wood_11, intro_10, intro_15", m12.load_bursts(lines_a)[-3:] == ["wood_11", "intro_10", "intro_15"]),
        ("A: the redirect site was not reached", not any(REDIRECT.search(line) for line in lines_a)),
        ("A: the title rewrote the save", saved is not None and before is not None and saved["sha256"] != before["sha256"]),
        ("A: save resumes intro_15 in revisit mode with the campaign on record", saved is not None
         and saved["resume"].lower() == "intro_15" and saved["revisit"] == 1 and saved["rev_world"] == 1
         and saved["int_world"] == 2 and saved["backup"].lower() == "wood_11" and saved["end_of_game"] == 0
         and saved["max_world"] <= 2),
    ]
    record = {"scenario": "revisit_save_reload", "runs": [run_a], "save_before": before, "save_after_a": saved,
              "executable_sha256": facts_a.get("executable_sha256")}
    if all(ok for _, ok in checks) and not reasons:
        reasons += hidden_run(run_b, CONFIG / "revisit_continue.txt", 260, user_root=name)
        _, mech = mechanical(run_b, "intro_15", False)
        reasons += [f"run B: {r}" for r in mech]
        b, final = states_of(run_b), save_fields(profile)
        lines_b = m12.run_lines(m12.RUNS / run_b) if (m12.RUNS / run_b).is_dir() else []
        last = b[-1] if b else {}
        checks += [
            ("B: the loader restored the revisit state", ever(b, revisit=1, rev_world=1, int_world=2, backup="wood_11", current="intro_15")),
            ("B: loads are menumap, intro_15, wood_11", m12.load_bursts(lines_b)[-3:] == ["menumap", "intro_15", "wood_11"]),
            ("B: back in the campaign (flag 0, wood_11, world 2, highest 2, end-of-game 0)", last.get("revisit") == 0
             and str(last.get("current", "")).lower() == "wood_11" and last.get("world") == 2 and last.get("max_world") == 2
             and last.get("end_of_game") == 0),
            ("B: endgame never loaded, redirect site not reached", "endgame" not in m12.load_bursts(lines_b)
             and not any(REDIRECT.search(line) for line in lines_b)),
        ]
        record.update(runs=[run_a, run_b], save_after_b=final, final_state=last)
    reasons += [f"expected: {label}" for label, ok in checks if not ok]
    record.update(reasons=reasons, checks={label: ok for label, ok in checks})
    return record


def revisit_death(tag: str, mode: str) -> dict:
    """T2 (isolated hub): Revisit the Bog of Murk, die in its first level, let the title restart it."""
    run = f"m19_{tag}_revisit_death_{mode}"
    reasons = hidden_run(run, CONFIG / "revisit_death.txt", 200, test_level="endgame",
                         env={"R3HD_REVISIT": "original"} if mode == "original" else {})
    facts, mech = mechanical(run, "swamp_60", True)
    reasons += mech
    states = states_of(run)
    lines = m12.run_lines(m12.RUNS / run) if (m12.RUNS / run).is_dir() else []
    loads = m12.load_bursts(lines)
    redirects = [m.groups() for line in lines if (m := REDIRECT.search(line))]
    last = states[-1] if states else {}
    checks = [
        ("revisit entered into Swamp_60 (flag 1, world 3)", ever(states, revisit=1, rev_world=3, current="swamp_60")),
        ("the level was loaded a second time", loads[:2] == ["endgame", "swamp_60"] and len(loads) >= 3),
    ]
    if mode == "fixed":
        checks += [
            ("the restart reached the redirect site once: swamp_60, world 3, pass", [g[:2] + g[5:] for g in redirects] == [("swamp_60", "3", "pass")]),
            ("the restart reloaded Swamp_60", loads == ["endgame", "swamp_60", "swamp_60"]),
            ("still in revisit mode in Swamp_60", last.get("revisit") == 1 and last.get("rev_world") == 3
             and str(last.get("current", "")).lower() == "swamp_60"),
        ]
    else:
        checks += [
            ("the restart reached the redirect site once: original", [g[5] for g in redirects] == ["original"]),
            ("the restart was replaced by endgame", loads == ["endgame", "swamp_60", "endgame"]),
            ("flag cleared by the title, hub entered", last.get("revisit") == 0 and str(last.get("current", "")).lower() == "endgame"),
        ]
    reasons += [f"expected: {label}" for label, ok in checks if not ok]
    return {"scenario": f"revisit_death_{mode}", "runs": [run], "loads": loads, "redirects": redirects, "final_state": last,
            "reasons": reasons, "checks": {label: ok for label, ok in checks}, "executable_sha256": facts.get("executable_sha256")}


def watched_level(run: str, level: str, steps: Path, seconds: int, models: str, act, settle: int = 6) -> tuple[list, list]:
    """An isolated test-only run of one level with the M14 actor watch; `act(run_dir, actors, log)` drives scoped
    input once the actors are known. Returns (reasons, watch rows)."""
    watchers = []

    def beside(run_dir: Path, game: subprocess.Popen, log) -> list:
        if not wait_for_log(run_dir, f"{level}\\{level}.lvl result=00000000", game, 90):
            return [f"{level} did not open"]
        time.sleep(settle)
        pid, base = attach(run_dir)
        actors = run_dir / f"actors_{level}.json"
        subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(actors), "--regions"],
                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        watchers.append(subprocess.Popen([sys.executable, str(TOOLS / "m14_combat_watch.py"), str(run_dir), str(actors),
                                          str(run_dir / "watch.jsonl"), "--models", models, "--seconds", str(seconds),
                                          "--player-dsg", str(run_dir / "player_dsg.jsonl")],
                                         cwd=ROOT, stdout=log, stderr=subprocess.STDOUT))
        return act(run_dir, actors, log, Process(pid, int(base, 16))) or []

    reasons = hidden_run(run, steps, seconds, test_level=level, beside=beside)
    for watcher in watchers:
        try:
            watcher.wait(timeout=30)
        except subprocess.TimeoutExpired:
            watcher.kill()
    rows, watch = [], m12.RUNS / run / "watch.jsonl"
    for line in watch.read_text(encoding="utf-8").splitlines()[1:] if watch.is_file() else []:
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return reasons, rows


CAN = "YAM_mPowerz"


def live_actors(process, actors: Path, model: str) -> list:
    """Live actors of one model from an m5_memory_probe.py discovery file."""
    out = []
    for record in json.loads(actors.read_text(encoding="utf-8"))["actors"]:
        try:
            actor = Actor(process, int(record["so"], 16))
        except (TypeError, ValueError, IndexError, OSError):
            continue
        if actor.alive() and actor.model == model:
            out.append(actor)
    return out


def player_variable(path: Path, index: int) -> list:
    """[t, value] at every change of one 32-bit designer variable in a player_dsg.jsonl of m14_combat_watch.py."""
    out, offset = [], None
    for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
        record = json.loads(line)
        if record.get("offsets"):
            offset = record["offsets"][index]
        if offset is None:
            continue
        value = int.from_bytes(bytes.fromhex(record["buffer"])[offset:offset + 4], "big")
        if not out or out[-1][1] != value:
            out.append([record["t"], value])
    return out


def power_can(tag: str) -> dict:
    """T4 (isolated menu_20): walk into the power-up can 4 units from the spawn."""
    run = f"m19_{tag}_power_can"

    def act(run_dir: Path, actors: Path, log, process) -> list:
        done = subprocess.run([sys.executable, str(TOOLS / "m19_walk_to.py"), str(run_dir), str(actors), CAN,
                               "--seconds", "8", "--stop", "0.8", "--log", str(run_dir / "walk.json")],
                              cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=60)
        return [] if done.returncode == 0 else ["the walk did not reach the can"]

    reasons, rows = watched_level(run, "menu_20", ROOT / "config" / "m14" / "idle60.txt", 75, CAN, act)
    facts, mech = mechanical(run, "menu_20", True)
    reasons += mech
    taken = {}
    for r in rows:
        if r.get("model") == CAN and r.get("comport"):
            names = taken.setdefault(r["perso"], [])
            if not names or names[-1] != r["comport"]:
                names.append(r["comport"])
    walk_log = m12.RUNS / run / "walk.json"
    walk = json.loads(walk_log.read_text(encoding="utf-8")) if walk_log.is_file() else {}
    names = taken.get(walk.get("target_perso"), [])
    power = player_variable(m12.RUNS / run / "player_dsg.jsonl", 2)
    checks = [
        ("the walk reached the can it aimed at", walk.get("result") == "reached"),
        ("that can went from its Wait behaviour to a Cine or Go behaviour", len(names) > 1 and "Wait" in names[0]
         and all("Cine" in n or "Go" in n for n in names[1:])),
        ("the level was loaded once (no restart behind the change)",
         m12.load_bursts(m12.run_lines(m12.RUNS / run)).count("menu_20") == 1),
        ("the player's designer variable 2 went 5 -> 3 and stayed", [value for _, value in power] == [5, 3]),
    ]
    reasons += [f"expected: {label}" for label, ok in checks if not ok]
    return {"scenario": "power_can", "runs": [run], "reasons": reasons, "checks": {label: ok for label, ok in checks},
            "can_behaviours": taken, "player_variable_2": power, "executable_sha256": facts.get("executable_sha256")}


def damage_empty(data: bytes) -> bytes:
    return b""


def damage_truncated(data: bytes) -> bytes:
    return data[:100]


def damage_magic(data: bytes) -> bytes:
    return bytes(4) + data[4:]


def damage_check_bytes(data: bytes) -> bytes:
    return data[:96] + bytes([data[96] ^ 0x01]) + data[97:]


DAMAGE = {"empty": damage_empty, "truncated": damage_truncated, "bad_magic": damage_magic, "missing_file": None,
          "flipped_bit": damage_check_bytes}


def damaged_save(tag: str) -> dict:
    """T3. Fault injection on copies of the wood_11 entry: what an interrupted save write can leave behind (empty
    file, short file, missing file), a wrong header word and one flipped bit. Not a played state."""
    entry = m12.load_entry(ENTRY)
    if not m12.stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {ENTRY} no longer matches entry.json")
    reasons, runs, cases, checks = [], [], {}, {}
    for case, damage in DAMAGE.items():
        run = f"m19_{tag}_damaged_{case}"
        profile = m12.PROFILES / run
        if profile.exists():
            raise SystemExit(f"profile already exists: {run}")
        shutil.copytree(m12.SAVES / ENTRY / "profile", profile)
        save = m12.find_saves(profile)[0]
        if damage is None:
            save.unlink()
        else:
            save.write_bytes(damage(save.read_bytes()))
        before = tree_hashes(profile)
        problems = hidden_run(run, CONFIG / "damaged_load.txt", 70, user_root=run)
        facts, mech = mechanical(run, "menumap", case != "flipped_bit")
        problems += mech
        lines = m12.run_lines(m12.RUNS / run) if (m12.RUNS / run).is_dir() else []
        loads, states = m12.load_bursts(lines), states_of(run)
        last = states[-1] if states else {}
        cases[case] = {"run": run, "loads": loads, "final_level": last.get("current"), "profile_unchanged": tree_hashes(profile) == before,
                       "executable_sha256": facts.get("executable_sha256")}
        if case == "flipped_bit":  # the title keeps no check value over this byte: the save is accepted
            ok = {"the save was accepted and wood_11 loaded": loads[-2:] == ["menumap", "wood_11"]}
        else:
            ok = {"no level was loaded from the damaged slot": "wood_11" not in loads
                  and str(last.get("current", "")).lower() == "menumap"}
        ok["the Load page was opened and the title examined the slot"] = ever(states, page=12) and any(
            "vfs_open path=rayman3:" in line for line in lines)
        ok["the title left the profile files as they were"] = cases[case]["profile_unchanged"]
        checks.update({f"{case}: {label}": value for label, value in ok.items()})
        reasons += [f"{case}: {r}" for r in problems] + [f"{case}: expected: {label}" for label, value in ok.items() if not value]
        runs.append(run)
    return {"scenario": "damaged_save", "runs": runs, "cases": cases, "reasons": reasons, "checks": checks}


RAIL = "Mic_mRailsurf"


def rail_surf(tag: str) -> dict:
    """T5 (isolated sk8_10): the rail-surf section without input."""
    run = f"m19_{tag}_rail_surf"
    reasons, rows = watched_level(run, "sk8_10", ROOT / "config" / "m14" / "idle60.txt", 75,
                                  f"Mic_mCheckPointSk8,{RAIL},Mic_mGuard", lambda *_: [])
    facts, mech = mechanical(run, "sk8_10", True)
    reasons += mech
    seen = lambda model, name: any(r.get("model") == model and name in (r.get("comport") or "") for r in rows)  # noqa: E731
    xs = [r["position"][0] for r in rows if r.get("model") == "YLT_RaymanModel" and r.get("position")]
    resumes = sum(1 for before, after in zip(xs, xs[1:]) if after < before - 60)
    catches = sum(1 for r in rows if r.get("model") == "Mic_mGuard" and "skg_catch" in (r.get("comport") or "")
                  and "comport" in r.get("changed", []))
    checks = [
        ("the player is carried forward without input (more than 80 units)", bool(xs) and max(xs) - min(xs) > 80),
        ("the rail actor reaches its jump behaviour", seen(RAIL, "rm_jump")),
        ("the guard catches the falling player", seen("Mic_mGuard", "skg_catch") and seen(RAIL, "rm_froozen")),
        ("the run resumes from the checkpoint at least twice without a level reload", resumes >= 2 and catches >= 2
         and m12.load_bursts(m12.run_lines(m12.RUNS / run)).count("sk8_10") == 1),
    ]
    reasons += [f"expected: {label}" for label, ok in checks if not ok]
    return {"scenario": "rail_surf", "runs": [run], "reasons": reasons, "checks": {label: ok for label, ok in checks},
            "x_min": min(xs) if xs else None, "x_max": max(xs) if xs else None, "checkpoint_resumes": resumes, "guard_catches": catches, "watch_rows": len(rows),
            "executable_sha256": facts.get("executable_sha256")}


SCENARIOS = {
    "rail_surf": dict(
        about="isolated sk8_10 (test-only entry): rail surfing without input: carried forward, fall at the first "
              "gap, caught by the guard, resumed from the checkpoint without a level reload",
        run=rail_surf),
    "damaged_save": dict(
        about="fault injection on campaign copies (not a played state): Load on an empty, short, missing, wrongly "
              "headed save file is refused without a fault and left alone; one flipped bit in the body is accepted",
        run=damaged_save),
    "power_can": dict(
        about="isolated menu_20 (test-only entry): the player walks into a power-up can; pickup and power state",
        run=power_can),
    "revisit_death_fixed": dict(
        about="isolated hub (test-only entry): death in the first level of a revisited world; with the correction "
              "the title's restart request passes and the level restarts in revisit mode",
        run=lambda tag: revisit_death(tag, "fixed")),
    "revisit_death_original": dict(
        about="isolated hub (test-only entry), R3HD_REVISIT=original: the same restart request is replaced by endgame "
              "(the title's own behaviour, M18 path c)",
        run=lambda tag: revisit_death(tag, "original")),
    "revisit_save_reload": dict(
        about="campaign copy, normal input: a level played to its end in revisit mode, the title's save there, "
              "relaunch, Load, the title's own return to the campaign",
        run=revisit_save_reload),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", nargs="?")
    ap.add_argument("scenarios", nargs="*")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.tag:
        for name, spec in SCENARIOS.items():
            print(f"{name:22s} {spec['about']}")
        return 0
    if not m12.NAME_RE.fullmatch(a.tag):
        raise SystemExit("invalid TAG")
    names = a.scenarios or list(SCENARIOS)
    unknown = [name for name in names if name not in SCENARIOS]
    if unknown:
        raise SystemExit(f"unknown scenario(s): {', '.join(unknown)}")
    human_before, entry_before = tree_hashes(HUMAN), tree_hashes(m12.SAVES / ENTRY / "profile")
    passed = 0
    for name in names:
        record = SCENARIOS[name]["run"](a.tag)
        record["about"] = SCENARIOS[name]["about"]
        WORK.mkdir(parents=True, exist_ok=True)
        (WORK / f"m19_{a.tag}_{name}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        ok = not record["reasons"]
        passed += ok
        print(f"M19_SCENARIO {'PASS' if ok else 'FAIL'} {name} runs={','.join(record['runs'])}"
              + ("" if ok else " reasons=" + "; ".join(record["reasons"])))
    intact = tree_hashes(HUMAN) == human_before and tree_hashes(m12.SAVES / ENTRY / "profile") == entry_before
    print(f"human profile and save entry unchanged: {intact} ({len(human_before)} + {len(entry_before)} files)")
    state = "PASS" if passed == len(names) and intact else "FAIL"
    print(f"M19_CAMPAIGN_CHECK {state} {passed}/{len(names)}")
    return 0 if state == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

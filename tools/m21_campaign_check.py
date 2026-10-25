#!/usr/bin/env python3
"""Hidden scenarios of Milestone 21 on the save entries of the human session 20261011-143342.

    python tools/m21_campaign_check.py TAG [SCENARIO ...]      -> M21_CAMPAIGN_CHECK PASS n/n
    python tools/m21_campaign_check.py --list

Every scenario is one hidden run (m9_license_run.py: hidden window, scoped input, no captures) on a working
copy of a private save entry registered from that session's save history, with tools/m18_progress_watch.py
reading the title's progression state beside it. The entries, the save history and the human profile are
hashed before and after and never opened for writing. Entry class of every scenario: genuine save (a state a
person reached by play), scripted input from there. Step files: config/m21. Records: private/work/m21/check/.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import m19_campaign_check as m19  # noqa: E402
from m18_revisit_check import HUMAN, REDIRECT, save_fields, tree_hashes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "m21" / "check"
CONFIG = ROOT / "config" / "m21"
TOOLS = ROOT / "tools"
HISTORY = ROOT / "private" / "play" / "save_history" / "20261011-143342"
ENTRIES = ("wood_10_human", "wood_19_human", "wood_50_human", "menu_10_human", "sk8_10_human", "swamp_60_human")
m19.WORK = WORK  # the shared runner and state reader keep their records with this milestone's


def working_copy(entry: str, name: str) -> Path:
    profile = m12.PROFILES / name
    if profile.exists():
        raise SystemExit(f"profile already exists: {name}")
    if not m12.stored_profile_matches(m12.load_entry(entry)):
        raise SystemExit(f"stored profile of {entry} no longer matches entry.json")
    shutil.copytree(m12.SAVES / entry / "profile", profile)
    return profile


def evidence(run: str) -> tuple[list, list, list, dict]:
    lines = m12.run_lines(m12.RUNS / run) if (m12.RUNS / run).is_dir() else []
    states = m19.states_of(run)
    return lines, [name.lower() for name in m12.load_bursts(lines)], states, (states[-1] if states else {})


def finish(name: str, run: str, level: str, reasons: list, checks: list, **extra) -> dict:
    facts, mech = m19.mechanical(run, level, False)
    lines = m12.run_lines(m12.RUNS / run) if (m12.RUNS / run).is_dir() else []
    checks = checks + [
        ("hidden run: the cursor was never touched", sum("M21 cursor policy=untouched" in line for line in lines) == 1
         and not any("M21 cursor action=" in line for line in lines)),
        ("no save commit other than ok", all("result=ok" in line for line in lines if "M20 save " in line)),
    ]
    reasons = reasons + mech + [f"expected: {label}" for label, ok in checks if not ok]
    return {"scenario": name, "runs": [run], "reasons": reasons, "checks": {label: ok for label, ok in checks},
            "executable_sha256": facts.get("executable_sha256"), **extra}


def bog_revisit_clearleaf(tag: str) -> dict:
    """From the Bog of Murk save: Revisit Clearleaf Forest (a world pair never tried: the M18 / M19 scenarios
    revisit The Fairy Council from Clearleaf Forest), then the title's own "continue your game"."""
    run = f"m21_{tag}_bog_revisit"
    profile = working_copy("swamp_60_human", run)
    before = save_fields(profile)
    reasons = m19.hidden_run(run, CONFIG / "bog_revisit_clearleaf.txt", 260, user_root=run)
    lines, loads, states, last = evidence(run)
    redirects = [m.groups() for line in lines if (m := REDIRECT.search(line))]
    after = save_fields(profile)
    checks = [
        ("the save resumed the Bog of Murk as a campaign (flag 0, world 3)", m19.ever(states, revisit=0, current="swamp_60", world=3)),
        ("revisit entered into Clearleaf Forest's first level (flag 1, revisited world 2, interrupted world 3, backup swamp_60)",
         m19.ever(states, revisit=1, rev_world=2, int_world=3, backup="swamp_60", current="wood_11")),
        ("loads are menumap, swamp_60, wood_11, swamp_60", loads[-4:] == ["menumap", "swamp_60", "wood_11", "swamp_60"]),
        ("back in the campaign (flag 0, swamp_60, world 3, end-of-game 0)", last.get("revisit") == 0
         and str(last.get("current", "")).lower() == "swamp_60" and last.get("world") == 3 and last.get("end_of_game") == 0),
        ("highest world still 3", last.get("max_world") == 3),
        ("endgame never loaded", "endgame" not in loads),
        ("no redirect decision other than pass", all(g[5] == "pass" for g in redirects)),
        ("neither transition wrote a save", before is not None and after is not None and before["sha256"] == after["sha256"]),
    ]
    return finish("bog_revisit_clearleaf", run, "swamp_60", reasons, checks, loads=loads, redirects=redirects, final_state=last)


def bog_reload_exit(tag: str) -> dict:
    """From the Bog of Murk save: pause, Load the slot again (level reload in the same process), pause, Exit Game
    to the title screen. The save was written by a staged commit in the human session."""
    run = f"m21_{tag}_bog_reload"
    profile = working_copy("swamp_60_human", run)
    before = tree_hashes(profile)
    reasons = m19.hidden_run(run, CONFIG / "bog_pause_reload_exit.txt", 280, user_root=run)
    lines, loads, states, last = evidence(run)
    checks = [
        ("loads are menumap, swamp_60, swamp_60, menumap", loads[-4:] == ["menumap", "swamp_60", "swamp_60", "menumap"]),
        ("the pause menu's Load page was used inside the level", m19.ever(states, page=12, current="swamp_60")),
        ("the campaign state survived the reload (flag 0, world 3 in swamp_60 after the second load)",
         sum(1 for a, b in zip(states, states[1:]) if str(b.get("current", "")).lower() == "swamp_60"
             and str(a.get("current", "")).lower() != "swamp_60") >= 1 and m19.ever(states, revisit=0, world=3, current="swamp_60")),
        ("the title screen was reached at the end", str(last.get("current", "")).lower() == "menumap"),
        ("loading and leaving wrote nothing to the profile", tree_hashes(profile) == before),
        ("the redirect site was not reached", not any(REDIRECT.search(line) for line in lines)),
    ]
    return finish("bog_reload_exit", run, "swamp_60", reasons, checks, loads=loads, final_state=last)


def bog_hazard_restart(tag: str) -> dict:
    """From the Bog of Murk save: the left stick held forward into the toxic water at the level start (the M13
    control check's input), death, and the title's restart of the level in a campaign that is not revisiting."""
    run = f"m21_{tag}_bog_hazard"
    profile = working_copy("swamp_60_human", run)
    before = tree_hashes(profile)
    reasons = m19.hidden_run(run, CONFIG / "bog_hazard_restart.txt", 220, user_root=run)
    lines, loads, states, last = evidence(run)
    checks = [
        ("the level was loaded again by the title (once per death)", loads[:2] == ["ubi", "menumap"] and len(loads) >= 4
         and set(loads[2:]) == {"swamp_60"}),
        ("still the campaign after the restart (flag 0, swamp_60, world 3)", last.get("revisit") == 0
         and str(last.get("current", "")).lower() == "swamp_60" and last.get("world") == 3),
        ("the restart did not reach the redirect site (not a revisit)", not any(REDIRECT.search(line) for line in lines)),
        ("endgame never loaded", "endgame" not in loads),
        ("the death wrote nothing to the profile", tree_hashes(profile) == before),
    ]
    return finish("bog_hazard_restart", run, "swamp_60", reasons, checks, loads=loads, final_state=last)


RAIL = "Mic_mRailsurf"


def rail_from_save(tag: str) -> dict:
    """From the sk8_10 save (written inside menu_10 by the human session): the rail-surf section without input.
    The M19 observation (isolated entry) repeated from a state a person reached."""
    run = f"m21_{tag}_rail_save"
    profile = working_copy("sk8_10_human", run)
    before = tree_hashes(profile)
    watchers = []

    def beside(run_dir: Path, game: subprocess.Popen, log) -> list:
        if not m19.wait_for_log(run_dir, r"sk8_10\sk8_10.lvl result=00000000", game, 150):
            return ["sk8_10 did not open"]
        time.sleep(6)
        pid, base = m19.attach(run_dir)
        actors = run_dir / "actors_sk8_10.json"
        subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(actors), "--regions"],
                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        watchers.append(subprocess.Popen([sys.executable, str(TOOLS / "m14_combat_watch.py"), str(run_dir), str(actors),
                                          str(run_dir / "watch.jsonl"), "--models", f"Mic_mCheckPointSk8,{RAIL},Mic_mGuard",
                                          "--seconds", "80"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT))
        return []

    reasons = m19.hidden_run(run, CONFIG / "rail_from_save.txt", 190, user_root=run, beside=beside)
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
    lines, loads, states, last = evidence(run)
    seen = lambda model, name: any(r.get("model") == model and name in (r.get("comport") or "") for r in rows)  # noqa: E731
    xs = [r["position"][0] for r in rows if r.get("model") == "YLT_RaymanModel" and r.get("position")]
    resumes = sum(1 for a, b in zip(xs, xs[1:]) if b < a - 60)
    catches = sum(1 for r in rows if r.get("model") == "Mic_mGuard" and "skg_catch" in (r.get("comport") or "")
                  and "comport" in r.get("changed", []))
    checks = [
        ("the save resumed sk8_10 as a campaign", m19.ever(states, revisit=0, current="sk8_10")),
        ("the player is carried forward without input (more than 80 units)", bool(xs) and max(xs) - min(xs) > 80),
        ("the rail actor reaches its jump behaviour", seen(RAIL, "rm_jump")),
        ("the guard catches the falling player", seen("Mic_mGuard", "skg_catch") and seen(RAIL, "rm_froozen")),
        ("the run resumes from the checkpoint without a level reload", resumes >= 1 and catches >= 1 and loads.count("sk8_10") == 1),
        ("nothing was written to the profile", tree_hashes(profile) == before),
    ]
    return finish("rail_from_save", run, "sk8_10", reasons, checks, loads=loads, x_min=min(xs) if xs else None,
                  x_max=max(xs) if xs else None, checkpoint_resumes=resumes, guard_catches=catches, watch_rows=len(rows))


SCENARIOS = {
    "bog_revisit_clearleaf": dict(
        about="genuine save (The Bog of Murk): Revisit Clearleaf Forest from the pause menu, then the title's own "
              "return to the interrupted game; state, loads and the D-047 site observed",
        run=bog_revisit_clearleaf),
    "bog_reload_exit": dict(
        about="genuine save (The Bog of Murk): pause, Load the slot again in the same process, pause, Exit Game "
              "to the title screen",
        run=bog_reload_exit),
    "bog_hazard_restart": dict(
        about="genuine save (The Bog of Murk): walk into the toxic water at the start, death, the title's level "
              "restart in a campaign that is not revisiting",
        run=bog_hazard_restart),
    "rail_from_save": dict(
        about="genuine save (sk8_10, second rail section): carried forward without input, fall, guard catch, "
              "checkpoint restart without a level reload",
        run=rail_from_save),
}


def protected() -> dict:
    out = {"human": tree_hashes(HUMAN), "history": tree_hashes(HISTORY)}
    out.update({entry: tree_hashes(m12.SAVES / entry) for entry in ENTRIES})
    return out


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
    before = protected()
    passed = 0
    for name in names:
        record = SCENARIOS[name]["run"](a.tag)
        record["about"] = SCENARIOS[name]["about"]
        WORK.mkdir(parents=True, exist_ok=True)
        (WORK / f"m21_{a.tag}_{name}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        ok = not record["reasons"]
        passed += ok
        print(f"M21_SCENARIO {'PASS' if ok else 'FAIL'} {name} runs={','.join(record['runs'])}"
              + ("" if ok else " reasons=" + "; ".join(record["reasons"])))
    after = protected()
    intact = after == before and all(before.values())
    print(f"human profile, save history and save entries unchanged: {intact} "
          f"({len(before['human'])} + {len(before['history'])} + {sum(len(before[e]) for e in ENTRIES)} files)")
    state = "PASS" if passed == len(names) and intact else "FAIL"
    print(f"M21_CAMPAIGN_CHECK {state} {passed}/{len(names)}")
    return 0 if state == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

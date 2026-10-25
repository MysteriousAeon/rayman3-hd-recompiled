#!/usr/bin/env python3
"""Hidden regression for revisit mode and its compatibility correction (M18, D-047).

    python tools/m18_revisit_check.py TAG [SCENARIO ...]      -> M18_REVISIT_CHECK PASS n/n
    python tools/m18_revisit_check.py --list

One hidden run per scenario (run name m18_<TAG>_<scenario>), driven by a step file from config/m18 through
m9_license_run.py, with tools/m18_progress_watch.py reading the title's progression state beside it. Campaign
scenarios run on a working copy of the private save entry `wood_11_human` (the entry itself and the human
profile are never opened for writing; both are hashed before and after). Hub scenarios use the isolated
test-only entry into `endgame` (D-040): they show what the title's menu does, they are not progression.

What each scenario establishes is in its `about` text. Two of them set R3HD_TEST_WORLD_END=1: the title then
receives, from the menu's "Revisit" chosen a second time, the request that the last level of the revisited world
makes (config/rexglue/r3hd_compat.toml). That replaces playing a whole world; it writes no guest memory and
changes no save. Results obtained with it are labelled `test trigger` and are not a played world end.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "m18" / "check"
HUMAN = ROOT / "private" / "play" / "profiles" / "default"
ENTRY = "wood_11_human"
REDIRECT = re.compile(r"M18 revisit redirect name=(\S+) revisited_world=(\d+) end_of_game=(\d+) backup=(\S*) mode=(\w+) action=(\w+)")
NO_SAVE = "working profile has no save with valid magic"


def tree_hashes(root: Path) -> dict:
    return {str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()} if root.is_dir() else {}


def save_fields(profile: Path) -> dict | None:
    saves = [s for s in m12.find_saves(profile) if m12.read_save_meta(s)[0]] if profile.is_dir() else []
    if len(saves) != 1:
        return None
    data = saves[0].read_bytes()
    word = lambda offset: struct.unpack_from(">I", data, offset)[0]  # noqa: E731
    text = lambda offset: data[offset:offset + 0x1E].split(b"\0", 1)[0].decode("latin-1")  # noqa: E731
    return {"sha256": hashlib.sha256(data).hexdigest(), "end_of_game": word(104), "max_world": word(108),
            "revisit": word(132), "rev_world": word(144), "int_world": word(148), "resume": text(152), "backup": text(172)}


class Result:
    """Evidence of one finished run: load order, state timeline, hook decisions, save fields."""

    def __init__(self, run: str, isolated: bool):
        self.run, self.isolated = run, isolated
        lines = m12.run_lines(m12.RUNS / run) if (m12.RUNS / run).is_dir() else []
        self.loads = [name.lower() for name in m12.load_bursts(lines)]
        self.redirects = [m.groups() for line in lines if (m := REDIRECT.search(line))]
        self.triggers = sum("M18 test world_end" in line for line in lines)
        self.states, state = [], {}
        watch = WORK / f"{run}.jsonl"
        for line in watch.read_text(encoding="utf-8").splitlines() if watch.is_file() else []:
            record = json.loads(line)
            record.pop("t", None), record.pop("wall", None)
            state = {**state, **record}
            self.states.append(state)
        self.final = self.states[-1] if self.states else {}
        self.save = None if isolated else save_fields(m12.PROFILES / run)

    def ever(self, **want) -> bool:
        return any(all(s.get(k) == v for k, v in want.items()) for s in self.states)

    def after(self, first: dict, then: dict) -> bool:
        """A state matching `then` occurs later than one matching `first`."""
        seen = False
        for s in self.states:
            if seen and all(s.get(k) == v for k, v in then.items()):
                return True
            seen = seen or all(s.get(k) == v for k, v in first.items())
        return False

    def actions(self) -> list:
        return [groups[5] for groups in self.redirects]


CAMPAIGN = {"world": 2, "max_world": 2, "end_of_game": 0}
SCENARIOS = {
    "enter_return": dict(
        about="campaign copy: Revisit the Fairy Council from Clearleaf Forest, then the title's own return to the "
              "current game (legitimate revisit, unchanged title paths)",
        steps="enter_return.txt", seconds=200, isolated=False, env={},
        expect=[
            ("loads wood_11, intro_10, wood_11", lambda r: r.loads[-3:] == ["wood_11", "intro_10", "wood_11"]),
            ("revisit entered with the campaign on record", lambda r: r.ever(revisit=1, rev_world=1, int_world=2, backup="wood_11", current="Intro_10")),
            ("revisit left: flag 0, back in wood_11", lambda r: r.final.get("revisit") == 0 and r.final.get("current", "").lower() == "wood_11"),
            ("campaign state intact", lambda r: all(r.final.get(k) == v for k, v in CAMPAIGN.items())),
            ("the redirect site was never reached", lambda r: r.redirects == []),
            ("endgame never loaded", lambda r: "endgame" not in r.loads),
            ("save names wood_11, no revisit, highest world not raised", lambda r: r.save is not None and r.save["resume"].lower() == "wood_11"
             and r.save["revisit"] == 0 and r.save["end_of_game"] == 0 and r.save["max_world"] <= 2),
        ]),
    "world_end_fixed": dict(
        about="campaign copy, test trigger: the revisited Fairy Council asks for the next world's first level; the "
              "correction returns to the interrupted campaign level",
        steps="world_end.txt", seconds=200, isolated=False, env={"R3HD_TEST_WORLD_END": "1"},
        expect=[
            ("test trigger fired once", lambda r: r.triggers == 1),
            ("one redirect decision: return_to_campaign", lambda r: r.actions() == ["return_to_campaign"]),
            ("decision saw world 1, unfinished campaign, backup wood_11", lambda r: r.redirects[0][:5] == ("wood_11", "1", "0", "wood_11", "fixed")),
            ("loads wood_11, intro_10, wood_11", lambda r: r.loads[-3:] == ["wood_11", "intro_10", "wood_11"]),
            ("endgame never loaded", lambda r: "endgame" not in r.loads),
            ("back in the campaign: flag 0, world 2", lambda r: r.final.get("revisit") == 0 and r.final.get("rev_world") == 0
             and r.final.get("current", "").lower() == "wood_11" and all(r.final.get(k) == v for k, v in CAMPAIGN.items())),
            ("no world unlocked at any time", lambda r: all(s.get("max_world", 0) <= 2 for s in r.states)),
            ("save still names the campaign level", lambda r: r.save is not None and r.save["resume"].lower() == "wood_11"
             and r.save["revisit"] == 0 and r.save["end_of_game"] == 0 and r.save["max_world"] <= 2),
        ]),
    "world_end_original": dict(
        about="campaign copy, test trigger, R3HD_REVISIT=original: the same request under the title's own behaviour "
              "(reproduction of the softlock state)",
        steps="world_end.txt", seconds=200, isolated=False, env={"R3HD_TEST_WORLD_END": "1", "R3HD_REVISIT": "original"},
        expect=[
            ("test trigger fired once", lambda r: r.triggers == 1),
            ("one redirect decision: original", lambda r: r.actions() == ["original"] and r.redirects[0][4] == "original"),
            ("loads wood_11, intro_10, endgame", lambda r: r.loads[-3:] == ["wood_11", "intro_10", "endgame"]),
            ("flag cleared, hub entered", lambda r: r.final.get("revisit") == 0 and r.final.get("current", "").lower() == "endgame"),
            ("hub raised the world counter to 9 with the campaign unfinished", lambda r: r.final.get("world") == 9
             and r.final.get("max_world") == 9 and r.final.get("end_of_game") == 0),
        ]),
    "rechoose_fixed": dict(
        about="isolated hub (test-only entry): Revisit Clearleaf Forest, then Revisit the Bog of Murk from inside it; "
              "the correction lets the second choice through",
        steps="rechoose.txt", seconds=190, isolated=True, env={},
        expect=[
            ("one redirect decision: pass", lambda r: r.actions() == ["pass"]),
            ("decision saw swamp_60 as the revisited world's own entry", lambda r: r.redirects[0][:2] == ("swamp_60", "3")),
            ("loads endgame, wood_11, swamp_60", lambda r: r.loads == ["endgame", "wood_11", "swamp_60"]),
            ("still in revisit mode, world 3", lambda r: r.final.get("revisit") == 1 and r.final.get("rev_world") == 3
             and r.final.get("current", "").lower() == "swamp_60"),
        ]),
    "rechoose_original": dict(
        about="isolated hub (test-only entry), R3HD_REVISIT=original: the second Revisit is replaced by endgame "
              "(the title's own behaviour)",
        steps="rechoose.txt", seconds=190, isolated=True, env={"R3HD_REVISIT": "original"},
        expect=[
            ("one redirect decision: original", lambda r: r.actions() == ["original"]),
            ("loads endgame, wood_11, endgame", lambda r: r.loads == ["endgame", "wood_11", "endgame"]),
            ("flag cleared by the title", lambda r: r.final.get("revisit") == 0 and r.final.get("current", "").lower() == "endgame"),
        ]),
    "hub_tower": dict(
        about="isolated hub (test-only entry): with the campaign unfinished the hub sets world 9 and the Tower page "
              "takes no action, while the page before it offers Revisit",
        steps="hub_tower.txt", seconds=100, isolated=True, env={},
        expect=[
            ("hub sets world 9 / highest 9 with end-of-game 0", lambda r: r.ever(current="endgame", world=9, max_world=9, end_of_game=0)),
            ("A on the Tower page changes nothing", lambda r: r.ever(page=8) and not r.after({"page": 8}, {"revisit": 1, "rev_world": 9})),
            ("A + confirm on the Hoodlum Headquarters page enters revisit", lambda r: r.after({"page": 7}, {"revisit": 1, "rev_world": 8})),
            ("loads endgame, fact_40", lambda r: r.loads == ["endgame", "fact_40"]),
            ("the redirect site was never reached", lambda r: r.redirects == []),
        ]),
}


def run_scenario(tag: str, name: str) -> tuple[bool, list]:
    spec = SCENARIOS[name]
    run, steps = f"m18_{tag}_{name}", ROOT / "config" / "m18" / spec["steps"]
    work = m12.PROFILES / run
    if (m12.RUNS / run).exists() or work.exists():
        raise SystemExit(f"run or profile already exists for {run}")
    WORK.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(ROOT / "tools" / "m9_license_run.py"), run, str(steps), "--license-mask", "1",
               "--seconds", str(spec["seconds"])]
    if spec["isolated"]:
        command += ["--test-level", "endgame"]
    else:
        entry = m12.load_entry(ENTRY)
        if not m12.stored_profile_matches(entry):
            raise SystemExit(f"stored profile of {ENTRY} no longer matches entry.json")
        shutil.copytree(m12.SAVES / ENTRY / "profile", work)
        command += ["--user-root", run, "--play"]
    env = {k: v for k, v in os.environ.items() if k not in ("R3HD_TEST_WORLD_END", "R3HD_REVISIT")}
    env.update(spec["env"])
    watcher = subprocess.Popen([sys.executable, str(ROOT / "tools" / "m18_progress_watch.py"), str(m12.RUNS / run),
                                str(WORK / f"{run}.jsonl"), "--seconds", str(spec["seconds"]), "--wait", "180"],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with (WORK / f"{run}.driver.log").open("w", encoding="utf-8") as log:
        try:
            done = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=spec["seconds"] + 300)
            error = None if done.returncode == 0 else f"driver exit code {done.returncode}"
        except subprocess.TimeoutExpired:
            error = "driver timeout"
    try:
        watcher.wait(timeout=30)
    except subprocess.TimeoutExpired:
        watcher.kill()
    facts = m12.evaluate_run(run, "endgame" if spec["isolated"] else "wood_11", None)
    reasons = [reason for reason in facts["reasons"] if not (spec["isolated"] and reason == NO_SAVE)]
    if error:
        reasons.append(error)
    result = Result(run, spec["isolated"])
    for label, test in spec["expect"]:
        try:
            ok = bool(test(result))
        except (IndexError, KeyError, TypeError, AttributeError):
            ok = False
        if not ok:
            reasons.append(f"expected: {label}")
    record = {"scenario": name, "run": run, "about": spec["about"], "env": spec["env"], "reasons": reasons,
              "loads": result.loads, "redirects": result.redirects, "test_triggers": result.triggers,
              "final_state": result.final, "save": result.save, "executable_sha256": facts.get("executable_sha256"),
              "exit_code": facts.get("exit_code")}
    (WORK / f"{run}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return not reasons, reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", nargs="?")
    ap.add_argument("scenarios", nargs="*")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.tag:
        for name, spec in SCENARIOS.items():
            print(f"{name:20s} {spec['about']}")
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
        ok, reasons = run_scenario(a.tag, name)
        passed += ok
        print(f"M18_SCENARIO {'PASS' if ok else 'FAIL'} {name} run=m18_{a.tag}_{name}" + ("" if ok else " reasons=" + "; ".join(reasons)))
    intact = tree_hashes(HUMAN) == human_before and tree_hashes(m12.SAVES / ENTRY / "profile") == entry_before
    print(f"human profile and save entry unchanged: {intact} ({len(human_before)} + {len(entry_before)} files)")
    state = "PASS" if passed == len(names) and intact else "FAIL"
    print(f"M18_REVISIT_CHECK {state} {passed}/{len(names)}")
    return 0 if state == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

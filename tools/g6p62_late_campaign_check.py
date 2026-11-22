#!/usr/bin/env python3
"""G6-P62: hidden relaunch / Load checks on genuine late-campaign saves (session 20261013-202020).

    python tools/g6p62_late_campaign_check.py TAG [SCENARIO ...]   -> G6P62_LATE_CAMPAIGN_CHECK PASS n/n
    python tools/g6p62_late_campaign_check.py --list
    python tools/g6p62_late_campaign_check.py --selftest           -> G6P62_SELFTEST PASS n/n (no game process)

Entry class of every scenario: genuine save (a state a person reached by normal play in the M25 session, one-slot
staging copy of a save-history snapshot, registered with tools/m12_save_entry.py), relaunched in a new hidden
process and loaded from the title's own Load menu. Not isolated entry, not a converted PC save, not fault injection.

Each run: m9_license_run.py (hidden window, scoped XAM input, foreground monitor, zero captures) on a working copy
of the entry, with the read-only progression watcher tools/m18_progress_watch.py beside it. The title's restored
state is compared with the save record (tools/m18_revisit_check.save_fields): the level named by the save opens
first after the menu, without the new-game movie; the guest's end-of-game flag and revisit flag equal the save's;
its highest world is never below the save's. Entries, the M25 save history and the human profile are hashed
before and after and never opened for writing. Records: private/work/g6p62/check/.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import m19_campaign_check as m19  # noqa: E402
from m18_revisit_check import HUMAN, REDIRECT, save_fields, tree_hashes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "g6p62" / "check"
HISTORY = ROOT / "private" / "play" / "save_history" / "20261013-202020"
IDLE = 45
LOAD_ENTRIES = ("knaar_30_human", "knaar_60_human", "menu_30_human", "flash_20_human", "sea_10_human",
                "mount_50_human", "fact_40_human", "tower_10_human", "lept_15_human", "endgame_finished_human")
FINISHED = "endgame_finished_human"
NEW_GAME_MOVIE = "intro"
MENU_LOADS = ("ubi", "menumap")
SETTLE = 10.0  # seconds after the level first becomes current in which the restored state is judged (input: 15 s)


def scenarios() -> dict:
    out = {f"load_{entry[:-6] if entry.endswith('_human') else entry}": dict(
        entry=entry, steps=None, seconds=IDLE + 85, kind="load",
        about=f"relaunch, Load the genuine save {entry}, stand idle {IDLE} s") for entry in LOAD_ENTRIES}
    out["finished_tower_revisit"] = dict(
        entry=FINISHED, steps=ROOT / "config" / "g6p62" / "finished_tower_revisit.txt", seconds=200, kind="tower",
        about="finished campaign loaded from its genuine save: the hub's Tower page offers Revisit (end-of-game "
              "flag 1) and Tower_10 loads in revisit mode")
    return out


def first_level_after_menu(loads: list) -> str | None:
    """The first load after the title's menu map that is not the menu itself."""
    if "menumap" not in loads:
        return None
    rest = loads[loads.index("menumap") + 1:]
    rest = [name for name in rest if name not in MENU_LOADS]
    return rest[0] if rest else None


def judge_load(save: dict, level_key: str, loads: list, states: list, lines: list) -> list:
    """Checks that relate the title's restored state to the save record. Returns (label, ok) pairs."""
    current = [s for s in states if str(s.get("current", "")).lower() == level_key]
    start = current[0].get("t", 0.0) if current else 0.0
    after_open = [s for s in current if s.get("t", 0.0) <= start + SETTLE]
    return [
        (f"the save's level {level_key} is the first level loaded after the menu",
         first_level_after_menu(loads) == level_key),
        ("no new-game movie", NEW_GAME_MOVIE not in loads),
        ("watcher saw the level current", bool(after_open)),
        (f"end-of-game flag restored ({save['end_of_game']})",
         bool(after_open) and all(s.get("end_of_game") == save["end_of_game"] for s in after_open)),
        (f"revisit flag restored ({save['revisit']})",
         bool(after_open) and all(s.get("revisit") == save["revisit"] for s in after_open)),
        (f"highest world never below the save's ({save['max_world']})",
         bool(after_open) and all(isinstance(s.get("max_world"), int) and s["max_world"] >= save["max_world"]
                                  for s in after_open)),
        ("hidden run: the cursor was never touched",
         sum("M21 cursor policy=untouched" in line for line in lines) == 1
         and not any("M21 cursor action=" in line for line in lines)),
        ("no save commit other than ok", all("result=ok" in line for line in lines if "M20 save " in line)),
    ]


def ever(states: list, **want) -> bool:
    return any(all(s.get(k) == v for k, v in want.items()) for s in states)


def after(states: list, first: dict, then: dict) -> bool:
    seen = False
    for s in states:
        if seen and all(s.get(k) == v for k, v in then.items()):
            return True
        seen = seen or all(s.get(k) == v for k, v in first.items())
    return False


def lower_names(states: list) -> list:
    return [{k: (v.lower() if isinstance(v, str) else v) for k, v in s.items()} for s in states]


def judge_tower(save: dict, loads: list, states: list, lines: list) -> list:
    low = lower_names(states)
    return judge_load(save, "endgame", loads, states, lines) + [
        ("hub with the campaign finished: world 9, highest 9, end-of-game 1",
         ever(low, current="endgame", world=9, max_world=9, end_of_game=1)),
        ("A on the Tower page enters revisit of world 9 with backup endgame",
         after(low, {"page": 8}, {"revisit": 1, "rev_world": 9, "backup": "endgame"})),
        ("loads end with endgame, tower_10", loads[-2:] == ["endgame", "tower_10"]),
        ("Tower_10 current in revisit mode, end-of-game still 1",
         ever(low, current="tower_10", revisit=1, end_of_game=1)),
    ]


def run_scenario(tag: str, name: str, spec: dict) -> dict:
    entry = m12.load_entry(spec["entry"])
    if not m12.stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {spec['entry']} no longer matches entry.json")
    run = f"g6p62_{tag}_{name}"
    work = m12.PROFILES / run
    if (m12.RUNS / run).exists() or work.exists():
        raise SystemExit(f"run or profile already exists for {run}")
    save = save_fields(m12.SAVES / spec["entry"] / "profile")
    if save is None:
        raise SystemExit(f"entry {spec['entry']} has no single valid save")
    steps = spec["steps"]
    if steps is None:
        steps = WORK / f"{run}.steps.txt"
        steps.write_text("\n".join(m12.load_steps(IDLE)) + "\n", encoding="ascii")
    shutil.copytree(m12.SAVES / spec["entry"] / "profile", work)
    driver = m19.hidden_run(run, steps, spec["seconds"], user_root=run)
    reference = next((f["sha256"] for f in entry["files"] if f["path"].endswith(f"/{entry['slot']}")
                      and "/Headers/" not in f["path"]), None)
    level_key = entry["level_key"]
    facts = m12.evaluate_run(run, level_key, reference)
    lines = m12.run_lines(m12.RUNS / run) if (m12.RUNS / run).is_dir() else []
    loads = [n.lower() for n in m12.load_bursts(lines)]
    states = m19.states_of(run)
    checks = judge_tower(save, loads, states, lines) if spec["kind"] == "tower" else \
        judge_load(save, level_key, loads, states, lines)
    reasons = driver + facts["reasons"] + [f"expected: {label}" for label, ok in checks if not ok]
    final = states[-1] if states else {}
    return {"scenario": name, "run": run, "entry": spec["entry"], "class": "genuine save, relaunch + Load",
            "save": {k: v for k, v in save.items() if k != "sha256"}, "save_sha256": save["sha256"],
            "save_unchanged": facts.get("save_unchanged"), "save_level_now": facts.get("save_level_now"),
            "loads": loads, "redirects": [m.groups() for line in lines if (m := REDIRECT.search(line))],
            "final_state": {k: final.get(k) for k in ("current", "world", "max_world", "end_of_game", "revisit",
                                                      "rev_world", "backup")},
            "checks": {label: ok for label, ok in checks}, "reasons": reasons,
            "executable_sha256": facts.get("executable_sha256"), "exit_code": facts.get("exit_code"),
            "fault_codes": facts.get("fault_codes"), "guest_swap": facts.get("guest_swap")}


def guarded_trees() -> dict:
    trees = {"human_profile": tree_hashes(HUMAN), "m25_history": tree_hashes(HISTORY)}
    for name in {spec["entry"] for spec in scenarios().values()}:
        trees[f"entry:{name}"] = tree_hashes(m12.SAVES / name / "profile")
    return trees


def selftest() -> int:
    """Offline: the judges on synthetic states and log lines, including mutations that must fail."""
    save = {"end_of_game": 1, "revisit": 0, "max_world": 9, "rev_world": 0, "int_world": 0, "resume": "endgame",
            "backup": ""}
    lines = ["[x] M21 cursor policy=untouched", "[x] M20 save commit result=ok"]
    loads = ["ubi", "menumap", "endgame", "tower_10"]
    good = [{"t": 30.0, "current": "menumap", "end_of_game": 0, "revisit": 0, "max_world": 1, "world": 1, "page": 10},
            {"t": 60.0, "current": "endgame", "end_of_game": 1, "revisit": 0, "max_world": 9, "world": 9, "page": 10},
            {"t": 78.0, "current": "endgame", "end_of_game": 1, "revisit": 0, "max_world": 9, "world": 9, "page": 8},
            {"t": 82.0, "current": "endgame", "end_of_game": 1, "revisit": 1, "rev_world": 9, "backup": "endgame",
             "max_world": 9, "world": 9, "page": 8},
            {"t": 90.0, "current": "Tower_10", "end_of_game": 1, "revisit": 1, "rev_world": 9, "backup": "endgame",
             "max_world": 9, "world": 9}]
    cases = []

    def case(label: str, ok_expected: bool, checks: list) -> None:
        cases.append((label, all(ok for _, ok in checks) == ok_expected))

    case("tower: good", True, judge_tower(save, loads, good, lines))
    case("tower: flag lost by the loader", False,
         judge_tower(save, loads, [{**s, "end_of_game": 0} if s["current"] != "menumap" else s for s in good], lines))
    case("tower: flag restored late (outside the settle window)", False,
         judge_tower(save, loads, [good[0], {**good[1], "end_of_game": 0}, {**good[1], "t": 75.0}] + good[2:], lines))
    case("tower: page 8 takes no action", False, judge_tower(save, ["ubi", "menumap", "endgame"], good[:3], lines))
    case("tower: new-game movie", False, judge_tower(save, ["ubi", "menumap", "intro", "endgame", "tower_10"],
                                                      good, lines))
    plain = {**save, "end_of_game": 0, "max_world": 5, "resume": "Knaar_30"}
    lvl = [{"current": "menumap", "end_of_game": 0, "revisit": 0, "max_world": 1},
           {"current": "Knaar_30", "end_of_game": 0, "revisit": 0, "max_world": 5}]
    case("load: good", True, judge_load(plain, "knaar_30", ["ubi", "menumap", "knaar_30"], lvl, lines))
    case("load: other level first", False, judge_load(plain, "knaar_30", ["ubi", "menumap", "intro_10", "knaar_30"],
                                                       lvl, lines))
    case("load: highest world lowered", False,
         judge_load(plain, "knaar_30", ["ubi", "menumap", "knaar_30"], [lvl[0], {**lvl[1], "max_world": 4}], lines))
    case("load: revisit flag set", False,
         judge_load(plain, "knaar_30", ["ubi", "menumap", "knaar_30"], [lvl[0], {**lvl[1], "revisit": 1}], lines))
    case("load: watcher never saw the level", False, judge_load(plain, "knaar_30", ["ubi", "menumap", "knaar_30"],
                                                                 lvl[:1], lines))
    case("load: failed save commit", False, judge_load(plain, "knaar_30", ["ubi", "menumap", "knaar_30"], lvl,
                                                       lines + ["[x] M20 save commit result=failed"]))
    case("load: cursor touched", False, judge_load(plain, "knaar_30", ["ubi", "menumap", "knaar_30"], lvl,
                                                   lines + ["[x] M21 cursor action=move"]))
    passed = sum(ok for _, ok in cases)
    for label, ok in cases:
        print(f"{'ok  ' if ok else 'FAIL'} {label}")
    print(f"G6P62_SELFTEST {'PASS' if passed == len(cases) else 'FAIL'} {passed}/{len(cases)}")
    return 0 if passed == len(cases) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", nargs="?")
    parser.add_argument("names", nargs="*")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    specs = scenarios()
    if args.list:
        for name, spec in specs.items():
            print(f"{name}: {spec['about']}")
        return 0
    if args.selftest:
        return selftest()
    if not args.tag or not m12.NAME_RE.fullmatch(args.tag):
        raise SystemExit("TAG required ([A-Za-z0-9_-]+)")
    names = args.names or list(specs)
    unknown = [n for n in names if n not in specs]
    if unknown:
        raise SystemExit(f"unknown scenario(s): {', '.join(unknown)}")
    WORK.mkdir(parents=True, exist_ok=True)
    m19.WORK = WORK  # the shared runner and state reader keep their records with this checkpoint's
    before = guarded_trees()
    results = []
    for name in names:
        result = run_scenario(args.tag, name, specs[name])
        results.append(result)
        state = "FAIL" if result["reasons"] else "PASS"
        print(f"{state} {name} run={result['run']} loads={','.join(result['loads'])}"
              + (f" reasons={';'.join(result['reasons'])}" if result["reasons"] else ""), flush=True)
    after_trees = guarded_trees()
    guard_ok = before == after_trees and all(before.values())
    record = {"tag": args.tag, "results": results, "guarded_trees_unchanged": guard_ok,
              "guarded_file_counts": {k: len(v) for k, v in before.items()}}
    (WORK / f"g6p62_{args.tag}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    passed = sum(not r["reasons"] for r in results)
    ok = passed == len(results) and guard_ok
    print(f"guarded trees unchanged: {guard_ok} ({', '.join(f'{k}={len(v)}' for k, v in before.items())})")
    print(f"G6P62_LATE_CAMPAIGN_CHECK {'PASS' if ok else 'FAIL'} {passed}/{len(results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

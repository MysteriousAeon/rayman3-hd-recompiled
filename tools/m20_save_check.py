#!/usr/bin/env python3
"""Hidden save-replacement scenarios of Milestone 20 (D-049).

    python tools/m20_save_check.py TAG [SCENARIO ...]      -> M20_SAVE_CHECK PASS n/n
    python tools/m20_save_check.py --list

Every scenario replaces an existing save by the title's own autosave: a working copy of the private entry
`wood_11_human` is loaded, The Fairy Council is revisited and Intro_10 is flown to its end by the M5 pilot (the
M19 sequence, normal input, hidden window). The save written at that level change is the replacement under
test. Fault scenarios arm one test-only fault point (R3HD_SAVE_FAULT, tools/m20_save_commit.h) in that run.
They are fault injection: nothing they leave behind is a played state.

The pilot fails to finish Intro_10 in about one run of three; such an attempt never reaches the save and is
repeated (at most three attempts), it is not a result. The entry and the human profile are hashed before and
after and never opened for writing. Records: private/work/m20/check/.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import m19_campaign_check as m19  # noqa: E402
from m18_revisit_check import HUMAN, ENTRY, save_fields, tree_hashes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "m20" / "check"
CONFIG19 = ROOT / "config" / "m19"
SWITCHES = ("R3HD_SAVE_FAULT", "R3HD_SAVE_COMMIT")
EXIT_CODE = 0x4D20
ATTEMPTS = 3
m19.WORK = WORK  # watcher and driver logs of these runs belong to this milestone


def clean_env(extra: dict) -> dict:
    return {**{name: "" for name in SWITCHES}, **extra}


def staging_dirs(profile: Path) -> list:
    return sorted(str(p.relative_to(profile)).replace("\\", "/") for p in profile.glob("*/5841123F/.staging/*"))


def slot_dirs(profile: Path) -> list:
    return sorted(p.name for p in profile.glob("*/5841123F/00000001/*"))


def save_tree(profile: Path) -> dict:
    """Hashes of everything the title or the content manager owns in the profile, staging excluded."""
    return {k: v for k, v in tree_hashes(profile).items() if "/.staging/" not in k}


def lines_of(run: str) -> list:
    return m12.run_lines(m12.RUNS / run) if (m12.RUNS / run).is_dir() else []


def m20_lines(lines: list) -> list:
    return [line.split("] ", 4)[-1] for line in lines if "M20 save " in line]


def content_calls(lines: list) -> list:
    out = []
    for line in lines:
        if "M6 content api=" in line:
            text = line.split("M6 content ", 1)[1]
            fields = dict(part.split("=", 1) for part in text.split() if "=" in part)
            out.append((fields.get("api"), fields.get("arg6"), fields.get("result")))
    return out


def reached_save(lines: list, run: str) -> bool:
    """The title asked for the replacement: a CREATE_ALWAYS create (flags 0x12) returned in this run, or the
    process ended inside it at an exit fault point (the line is flushed before the end; the exit code agrees)."""
    if any("M6 content api=XamContentCreateEx" in line and "arg6=00000012" in line for line in lines):
        return True
    return any("M20 save fault=exit" in line for line in lines) and run_exit_code(run) == EXIT_CODE


def replacement_run(tag: str, name: str, env: dict, seconds: int = 420) -> dict:
    """Run A of the M19 sequence on a fresh working copy, repeated while the pilot does not reach the save."""
    entry = m12.load_entry(ENTRY)
    if not m12.stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {ENTRY} no longer matches entry.json")
    attempts = []
    for attempt in range(1, ATTEMPTS + 1):
        run = f"m20_{tag}_{name}_{attempt}"
        profile = m12.PROFILES / run
        if profile.exists():
            raise SystemExit(f"profile already exists: {run}")
        shutil.copytree(m12.SAVES / ENTRY / "profile", profile)
        before_tree, before = save_tree(profile), save_fields(profile)
        driver = m19.hidden_run(run, CONFIG19 / "revisit_enter.txt", seconds, user_root=run, env=clean_env(env),
                                beside=m19.fly_intro_10)
        lines = lines_of(run)
        result = dict(run=run, profile=profile, driver=driver, lines=lines, before_tree=before_tree, before=before,
                      after_tree=save_tree(profile), after=save_fields(profile), staging=staging_dirs(profile),
                      slots=slot_dirs(profile), m20=m20_lines(lines), calls=content_calls(lines))
        attempts.append(run)
        if reached_save(lines, run):
            result["attempts"] = attempts
            return result
    result["attempts"] = attempts
    result["driver"] = result["driver"] + [f"the save was not reached in {ATTEMPTS} attempts (pilot variance)"]
    return result


def run_exit_code(run: str) -> int | None:
    path = m12.RUNS / run / "run.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig")).get("exit_code")


def record_of(scenario: str, r: dict, checks: list, reasons: list, **extra) -> dict:
    reasons = reasons + [f"expected: {label}" for label, ok in checks if not ok]
    return {"scenario": scenario, "runs": r["attempts"] + extra.pop("more_runs", []), "reasons": reasons,
            "checks": {label: ok for label, ok in checks}, "m20_log": r["m20"], "content_calls": r["calls"][-6:],
            "save_before": r["before"], "save_after": r["after"], "staging_after": r["staging"], "slots_after": r["slots"],
            **extra}


def reload_run(tag: str, name: str, profile_name: str) -> tuple[list, list, list]:
    """A new process on the same profile: title -> Load -> the slot. Returns reasons, load order, lines."""
    run = f"m20_{tag}_{name}_reload"
    reasons = m19.hidden_run(run, CONFIG19 / "damaged_load.txt", 70, user_root=profile_name, env=clean_env({}))
    facts, mech = m19.mechanical(run, "menumap", False)
    lines = lines_of(run)
    return reasons + mech, m12.load_bursts(lines), lines


def normal_replace(tag: str) -> dict:
    """The replacement without a fault, then a new process that loads the new save."""
    r = replacement_run(tag, "normal", {})
    facts, mech = m19.mechanical(r["run"], "intro_15", False)
    reasons = r["driver"] + [f"run: {x}" for x in mech]
    after = r["after"] or {}
    creates = [c for c in r["calls"] if c[0] == "XamContentCreateEx" and c[1] == "00000012"]
    closes = [c for c in r["calls"] if c[0] == "XamContentClose"]
    checks = [
        ("the create was staged over the existing save", any("stage result=ok" in x and "replaces_existing=true" in x for x in r["m20"])),
        ("the commit replaced one file and rewrote the header after it", any("commit result=ok files=1 header=written" in x for x in r["m20"])),
        ("the guest saw success from the create and from the close", bool(creates) and creates[-1][2] == "00000000"
         and bool(closes) and closes[-1][2] == "00000000"),
        ("the save is the title's new record (intro_15, revisit fields)", r["before"] is not None and bool(after)
         and after.get("sha256") != r["before"]["sha256"] and after.get("resume", "").lower() == "intro_15"
         and after.get("revisit") == 1 and after.get("backup", "").lower() == "wood_11"),
        ("only the slot's save file and header file changed in the profile", sorted(r["after_tree"]) == sorted(r["before_tree"])
         and {k.rsplit("/", 1)[-1] for k in r["after_tree"] if r["after_tree"][k] != r["before_tree"][k]} == {"RAY1", "RAY1.header"}),
        ("no staging directory and no extra slot left", not r["staging"] and r["slots"] == ["RAY1"]),
    ]
    more, loads = [], []
    if all(ok for _, ok in checks) and not reasons:
        problems, loads, lines = reload_run(tag, "normal", r["run"])
        reasons += [f"reload: {x}" for x in problems]
        more = [f"m20_{tag}_normal_reload"]
        checks.append(("a new process loads the replaced save (intro_15)", loads[-2:] == ["menumap", "intro_15"]))
        checks.append(("loading did not rewrite the save", save_tree(r["profile"]) == r["after_tree"]))
    return record_of("normal_replace", r, checks, reasons, more_runs=more, reload_loads=loads,
                     executable_sha256=facts.get("executable_sha256"))


def exit_after_create(tag: str, mode: str) -> dict:
    """The process ends between the create and the first write (the M19 hazard), on either write path."""
    env = {"R3HD_SAVE_FAULT": "exit_after_create"}
    if mode == "legacy":
        env["R3HD_SAVE_COMMIT"] = "legacy"
    r = replacement_run(tag, f"exit_{mode}", env)
    fired = any("fault=exit point=after_create" in x for x in r["m20"])
    # The driver reports the game's exit code; everything else it says about a killed run is expected.
    reasons = [x for x in r["driver"] if "pilot variance" in x or "not reached" in x]
    save_file = r["profile"] / "B13EBABEBABEBABE" / "5841123F" / "00000001" / "RAY1" / "RAY1"
    checks = [("the process ended at the fault point (log line and exit code 0x4D20)",
               fired and run_exit_code(r["run"]) == EXIT_CODE)]
    more, loads = [], []
    if mode == "legacy":
        checks += [
            ("pinned sequence: the previous save file is gone", not save_file.exists()),
            ("pinned sequence: the slot directory is still listed", r["slots"] == ["RAY1"]),
        ]
    else:
        checks += [
            ("staged: save file and header byte-identical to before", r["after_tree"] == r["before_tree"]),
            ("staged: the dead process left one stage, outside the slot list", len(r["staging"]) == 1 and r["slots"] == ["RAY1"]),
        ]
        if all(ok for _, ok in checks) and not reasons:
            problems, loads, lines = reload_run(tag, f"exit_{mode}", r["run"])
            reasons += [f"reload: {x}" for x in problems]
            more = [f"m20_{tag}_exit_{mode}_reload"]
            checks += [
                ("staged: the next process removed the leftover stage", any("sweep removed=" in x for x in m20_lines(lines))
                 and not staging_dirs(r["profile"])),
                ("staged: the next process loads the previous save (wood_11)", loads[-2:] == ["menumap", "wood_11"]),
                ("staged: the profile is still byte-identical", save_tree(r["profile"]) == r["before_tree"]),
            ]
    return record_of(f"exit_after_create_{mode}", r, checks, reasons, more_runs=more, reload_loads=loads)


def refused_commit(tag: str, fault: str) -> dict:
    """A host failure while the title saves: the commit is refused and the title goes on."""
    r = replacement_run(tag, fault, {"R3HD_SAVE_FAULT": fault})
    facts, mech = m19.mechanical(r["run"], "intro_15", False)
    # The save was deliberately not written: the M12 "save changed" style criteria do not apply.
    reasons = r["driver"] + [f"run: {x}" for x in mech if "save" not in x.lower()]
    closes = [c for c in r["calls"] if c[0] == "XamContentClose"]
    expect = {"replace": "commit result=replace_failed", "write": "commit result=write_failed",
              "flush": "commit result=flush_failed", "stage_create": "stage result=failed"}[fault]
    checks = [
        ("the injected failure was reported by the host", any(expect in x for x in r["m20"])),
        ("the previous save and its header are byte-identical", r["after_tree"] == r["before_tree"]),
        ("no staging directory and no extra slot left", not r["staging"] and r["slots"] == ["RAY1"]),
        ("the title went on to intro_15 without a fault", m12.load_bursts(r["lines"])[-1:] == ["intro_15"]),
    ]
    if fault == "stage_create":
        creates = [c for c in r["calls"] if c[0] == "XamContentCreateEx" and c[1] == "00000012"]
        checks.append(("the guest was told the create failed (ERROR_ACCESS_DENIED)", bool(creates) and creates[-1][2] == "00000005"))
    else:
        checks.append(("the guest was told the close failed (ERROR_ACCESS_DENIED)", bool(closes) and closes[-1][2] == "00000005"))
    return record_of(f"refused_{fault}", r, checks, reasons, executable_sha256=facts.get("executable_sha256"))


SCENARIOS = {
    "normal_replace": dict(
        about="campaign copy, normal input: the title's autosave replaces the existing save through the staged "
              "commit; a new process loads it",
        run=normal_replace),
    "exit_after_create_legacy": dict(
        about="fault injection, R3HD_SAVE_COMMIT=legacy: the process ends between create and write on the pinned "
              "write path; the previous save is lost (the M19 hazard, reproduced)",
        run=lambda tag: exit_after_create(tag, "legacy")),
    "exit_after_create_staged": dict(
        about="fault injection: the same end of the process on the staged path; the previous save is byte-identical, "
              "the next process removes the leftover and loads it",
        run=lambda tag: exit_after_create(tag, "staged")),
    "refused_replace": dict(
        about="fault injection: the rename onto the live file fails; close reports the failure, the previous save stays",
        run=lambda tag: refused_commit(tag, "replace")),
    "refused_write": dict(
        about="fault injection: a guest write into the staged file is cut short by the host; the commit is refused, "
              "the previous save stays",
        run=lambda tag: refused_commit(tag, "write")),
    "refused_flush": dict(
        about="fault injection: flushing the staged file fails at the close; the previous save stays",
        run=lambda tag: refused_commit(tag, "flush")),
    "refused_stage_create": dict(
        about="fault injection: the staging directory cannot be created; the create fails, nothing is deleted",
        run=lambda tag: refused_commit(tag, "stage_create")),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", nargs="?")
    ap.add_argument("scenarios", nargs="*")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.tag:
        for name, spec in SCENARIOS.items():
            print(f"{name:26s} {spec['about']}")
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
        (WORK / f"m20_{a.tag}_{name}.json").write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
        ok = not record["reasons"]
        passed += ok
        print(f"M20_SCENARIO {'PASS' if ok else 'FAIL'} {name} runs={','.join(record['runs'])}"
              + ("" if ok else " reasons=" + "; ".join(record["reasons"])), flush=True)
    intact = tree_hashes(HUMAN) == human_before and tree_hashes(m12.SAVES / ENTRY / "profile") == entry_before
    print(f"human profile and save entry unchanged: {intact} ({len(human_before)} + {len(entry_before)} files)")
    state = "PASS" if passed == len(names) and intact else "FAIL"
    print(f"M20_SAVE_CHECK {state} {passed}/{len(names)}")
    return 0 if state == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

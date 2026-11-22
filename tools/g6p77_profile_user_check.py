#!/usr/bin/env python3
"""G6-P77: does a game started from guest user 1 (a second controller's START) save and load like user 0?

    python tools/g6p77_profile_user_check.py run TAG [--users 0,1]   -> G6P77_PROFILE_USER_CHECK ... (game runs)
    python tools/g6p77_profile_user_check.py judge TAG [--users 0,1] -> re-judge recorded runs (no game process)
    python tools/g6p77_profile_user_check.py --selftest              -> G6P77_SELFTEST PASS n/n (no game process)

For each user U, on a fresh private profile private/work/m9_profiles/g6p77_TAG_uU (never a person's profile):
  run N (new):  hidden, licence mask 1, the scoped XAM schedule on guest user U (runner -TestInputUser U), the
                profile / save boundary trace on (-ProfileTrace). Title START -> New -> name -> confirm: the title
                writes its first save at the name confirmation (M9 / M12). Read-only probes (tools/m8_license_probe.py)
                at the title, after START and after the save.
  run L (load): a new process on the same profile, the same user: title START -> Load -> slot -> stand.
Control A is U=0, experiment B is U=1. Both use the same executable, game data, licence mode, fresh profile,
settings and step timing; only the schedule's guest user differs. No frames, captures, desktop input or physical
controller. Judges: runner facts (exit 0, no foreground event, the requested input user recorded), the selected
user (active pad / profile user / lock mask after START), the XAM boundary (sign-in state, profile settings, device
selector, content create / close with user and result), the save file (one valid save), and the reload
(m12_save_entry.evaluate_run: the saved level opens, no new-game movie, save byte-identical).
Records: private/work/g6p77/.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "g6p77"
RUNS = m12.RUNS
PROFILES = m12.PROFILES
NEW_SECONDS, LOAD_SECONDS = 90, 100

NEW_STEPS = [
    "# G6-P77 run N: fresh profile -> title START -> New -> name -> confirm (first save) -> intro movie.",
    r"log VIDEOS\ubi.bik result=00000000",
    r"log menumap\menumap.lvl result=00000000",
    "wait 10", "probe title",
    "press 40", "wait 12", "probe after_start",
    "press 44", "wait 8",
    "press 44", "wait 8",
    "press 44",
    r"log VIDEOS\intro.bik result=00000000 60",
    "wait 4", "probe after_save",
]
LOAD_STEPS = [
    "# G6-P77 run L: relaunch on the run-N profile -> title START -> Load -> slot -> stand.",
    r"log VIDEOS\ubi.bik result=00000000",
    r"log menumap\menumap.lvl result=00000000",
    "wait 10",
    "press 40", "wait 12", "probe after_start",
    "axis 301 -32767", "wait 0.3", "axis 301 0",
    "wait 2", "press 44", "wait 8", "press 44",
    "wait 25", "probe loaded",
]

TRACE = re.compile(r"G6P77 xam import=__imp__(\w+) caller=([0-9A-F]{8}) r3=([0-9A-F]{8}) r4=([0-9A-F]{8}) "
                   r"r5=([0-9A-F]{8}) r6=([0-9A-F]{8}) result=([0-9A-F]{8})")
CONTENT = re.compile(r"M6 content api=(\w+) caller=([0-9A-F]{8}) arg3=([0-9A-F]{8}) arg4=([0-9A-F]{8}) "
                     r"arg5=([0-9A-F]{8}) arg6=([0-9A-F]{8}) result=([0-9A-F]{8})")
INPUT_USER = re.compile(r"G6P77 test_input user=(-?\d+)")


def names(tag: str, user: int) -> dict:
    return {"profile": f"g6p77_{tag}_u{user}", "new": f"g6p77_{tag}_u{user}_n", "load": f"g6p77_{tag}_u{user}_l"}


def steps_file(name: str, lines: list) -> Path:
    path = WORK / "steps" / f"{name}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def driver(run: str, steps: Path, seconds: int, profile: str, user: int) -> str | None:
    command = [sys.executable, str(ROOT / "tools" / "m9_license_run.py"), run, str(steps), "--license-mask", "1",
               "--seconds", str(seconds), "--user-root", profile, "--play", "--input-user", str(user),
               "--profile-trace"]
    return m12.run_driver(command, WORK / f"{run}.driver.log", seconds)


def xam_calls(lines: list) -> list:
    calls = []
    for line in lines:
        if m := TRACE.search(line):
            calls.append({"api": m[1], "caller": m[2], "r3": m[3], "r4": m[4], "r5": m[5], "r6": m[6], "result": m[7]})
        elif m := CONTENT.search(line):
            calls.append({"api": m[1], "caller": m[2], "r3": m[3], "r4": m[4], "r5": m[5], "r6": m[6], "result": m[7]})
    return calls


def probes(run: str) -> dict:
    path = RUNS / run / "license_run.json"
    if not path.is_file():
        return {}
    events = json.loads(path.read_text(encoding="utf-8-sig")).get("events", [])
    return {e["label"]: e.get("state") for e in events if e.get("step") == "probe"}


def runner_facts(run: str, user: int) -> tuple[dict, list]:
    reasons, facts = [], {"run": run}
    meta_path = RUNS / run / "run.json"
    if not meta_path.is_file():
        return facts, ["run.json missing"]
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    facts.update(exit_code=meta.get("exit_code"), executable_sha256=meta.get("executable_sha256"),
                 test_input_user=meta.get("test_input_user"), profile_trace=meta.get("profile_trace"))
    if meta.get("exit_code") != 0 or meta.get("forced_termination"):
        reasons.append(f"exit_code={meta.get('exit_code')} forced={meta.get('forced_termination')}")
    if meta.get("game_foreground_events") != 0 or meta.get("game_foreground_samples") != 0:
        reasons.append("foreground events/samples")
    if meta.get("test_input_user") != user or meta.get("profile_trace") is not True:
        reasons.append(f"runner recorded input user {meta.get('test_input_user')} trace {meta.get('profile_trace')}")
    lines = m12.run_lines(RUNS / run)
    logged = [int(m[1]) for line in lines if (m := INPUT_USER.search(line))]
    facts["logged_input_user"] = logged
    if (user and logged != [user]) or (not user and logged):
        reasons.append(f"runtime input-user line {logged} for user {user}")
    driver_json = RUNS / run / "license_run.json"
    if driver_json.is_file() and json.loads(driver_json.read_text(encoding="utf-8-sig")).get("error") is not None:
        reasons.append("driver error")
    return facts, reasons


def selected(state: dict | None, user: int) -> list:
    if not state:
        return ["probe after_start missing"]
    want = {"active_pad": user, "profile_user": user, "pad_lock_mask": 1 << user}
    return [f"{k}={state.get(k)} (want {v})" for k, v in want.items() if state.get(k) != v]


def summarize(calls: list) -> dict:
    out: dict = {}
    for c in calls:
        key = c["api"]
        if key in ("XamUserGetSigninState", "XamUserGetXUID", "XamUserGetName", "XamUserCheckPrivilege",
                   "XamShowDeviceSelectorUI", "XamContentGetDeviceData"):
            entry = f"user={int(c['r3'], 16)} result={c['result']} caller={c['caller']}"
        elif key in ("XamUserReadProfileSettings",):
            entry = f"user={int(c['r4'], 16)} result={c['result']} caller={c['caller']}"
        elif key in ("XamContentCreateEx", "XamContentCreateEnumerator"):
            entry = f"user={int(c['r3'], 16)} flags={c['r6']} result={c['result']} caller={c['caller']}"
        else:
            entry = f"r3={c['r3']} result={c['result']} caller={c['caller']}"
        out.setdefault(key, [])
        if entry not in out[key]:
            out[key].append(entry)
    return out


def judge_user(tag: str, user: int) -> dict:
    n = names(tag, user)
    record: dict = {"user": user, **n}
    new_facts, new_reasons = runner_facts(n["new"], user)
    new_probes = probes(n["new"])
    new_reasons += selected(new_probes.get("after_start"), user)
    reasons = [f"new: {r}" for r in new_reasons]
    new_calls = xam_calls(m12.run_lines(RUNS / n["new"])) if (RUNS / n["new"]).is_dir() else []
    save, level = m12.one_valid_save(PROFILES / n["profile"])
    record["new"] = {**new_facts, "probes": new_probes, "xam": summarize(new_calls),
                     "save": None if save is None else {"file": save.relative_to(PROFILES / n["profile"]).as_posix(),
                                                         "sha256": m12.sha256(save), "level": level}}
    if save is None or not level:
        reasons.append("new: no single save with valid magic")
    if (RUNS / n["load"]).is_dir():
        load_facts, load_reasons = runner_facts(n["load"], user)
        load_probes = probes(n["load"])
        load_reasons += selected(load_probes.get("after_start"), user)
        load_calls = xam_calls(m12.run_lines(RUNS / n["load"]))
        evaluated = m12.evaluate_run(n["load"], level.lower(), m12.sha256(save), forbid_movie="intro.bik") \
            if save is not None and level else {"reasons": ["no save to load"]}
        load_reasons += evaluated.get("reasons", [])
        record["load"] = {**load_facts, "probes": load_probes, "xam": summarize(load_calls),
                          "evaluate": {k: evaluated.get(k) for k in ("level_key", "save_sha256", "forbidden_movie_opens",
                                                                      "stub_import_lines", "fatal_lines")}}
        reasons += [f"load: {r}" for r in load_reasons]
    else:
        reasons.append("load: run missing")
    record["reasons"] = reasons
    return record


def run_user(tag: str, user: int) -> None:
    n = names(tag, user)
    for path in (RUNS / n["new"], RUNS / n["load"], PROFILES / n["profile"]):
        if path.exists():
            raise SystemExit(f"already exists: {path}")
    error = driver(n["new"], steps_file(n["new"], NEW_STEPS), NEW_SECONDS, n["profile"], user)
    print(f"user {user} run N {n['new']}: {'ok' if error is None else error}", flush=True)
    save, _level = m12.one_valid_save(PROFILES / n["profile"])
    if save is None:
        print(f"user {user}: no valid save after run N; run L still made (a load of nothing is a finding too)")
    error = driver(n["load"], steps_file(n["load"], LOAD_STEPS), LOAD_SECONDS, n["profile"], user)
    print(f"user {user} run L {n['load']}: {'ok' if error is None else error}", flush=True)


def report(tag: str, users: list) -> int:
    results = [judge_user(tag, u) for u in users]
    exes = {r[k].get("executable_sha256") for r in results for k in ("new", "load") if k in r}
    same_exe = len(exes) == 1 and None not in exes
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"g6p77_{tag}.json"
    out.write_text(json.dumps({"tag": tag, "same_executable": same_exe, "executables": sorted(map(str, exes)),
                               "results": results}, indent=2) + "\n", encoding="utf-8")
    for r in results:
        save = r["new"].get("save")
        print(f"user {r['user']}: probes_after_start={r['new']['probes'].get('after_start')}")
        for api, entries in sorted(r["new"]["xam"].items()):
            print(f"  new  {api}: {'; '.join(entries)}")
        for api, entries in sorted(r.get("load", {}).get("xam", {}).items()):
            print(f"  load {api}: {'; '.join(entries)}")
        print(f"  save={save}")
        print(f"  {'PASS' if not r['reasons'] else 'FAIL'} user={r['user']}"
              + (f" reasons={';'.join(r['reasons'])}" if r["reasons"] else ""))
    ok = same_exe and all(not r["reasons"] for r in results)
    print(f"same executable: {same_exe}; record {out.relative_to(ROOT).as_posix()}")
    print(f"G6P77_PROFILE_USER_CHECK {'PASS' if ok else 'FAIL'} "
          f"{sum(not r['reasons'] for r in results)}/{len(results)}")
    return 0 if ok else 1


def selftest() -> int:
    checks = []

    def check(label: str, ok: bool) -> None:
        checks.append((label, ok))
        print(f"{'ok  ' if ok else 'FAIL'} {label}")

    line = ("[x] [info] [krnl] [t1] G6P77 xam import=__imp__XamUserGetSigninState caller=820F39E4 r3=00000001 "
            "r4=00000000 r5=00000000 r6=00000000 result=00000000 line=3")
    content = ("[x] [info] M6 content api=XamContentCreateEx caller=822FCF04 arg3=00000001 arg4=820A7420 "
               "arg5=70000000 arg6=00000012 result=00000000")
    calls = xam_calls([line, content, "unrelated"])
    check("trace and content lines parsed", [c["api"] for c in calls] == ["XamUserGetSigninState", "XamContentCreateEx"])
    s = summarize(calls)
    check("sign-in summarized with user and result", s["XamUserGetSigninState"] == ["user=1 result=00000000 caller=820F39E4"])
    check("content summarized with flags", s["XamContentCreateEx"] == ["user=1 flags=00000012 result=00000000 caller=822FCF04"])
    check("selection judged", selected({"active_pad": 1, "profile_user": 1, "pad_lock_mask": 2}, 1) == [])
    check("wrong selection rejected", len(selected({"active_pad": 0, "profile_user": 0, "pad_lock_mask": 1}, 1)) == 3)
    check("missing probe rejected", selected(None, 0) == ["probe after_start missing"])
    # Source pins: the facility is gated, and its default reproduces the M6 routing.
    header = (ROOT / "tools" / "m6_test_input.h").read_text(encoding="utf-8")
    patch = (ROOT / "tools" / "m6_runtime_patch.py").read_text(encoding="utf-8")
    trace = (ROOT / "tools" / "m2_runtime_import_trace.h").read_text(encoding="utf-8")
    runner = (ROOT / "tools" / "run_milestone6.ps1").read_text(encoding="utf-8-sig")
    check("default user is 0", "if (!text || !*text) return 0;" in header)
    check("invalid user fails closed", "if (test_user < 0) return kNotConnected;" in header)
    check("routing only inside the M6 gate", "  if (m6input::Enabled()) {\n    // G6-P77" in patch.replace("\r\n", "\n"))
    check("M16 / M32 anchors kept", all(a in patch for a in (
        "    auto s = m6input::Sample(bool(input_state));",
        "  if (m6input::Enabled()) return actual_user_index == 0 ? X_ERROR_EMPTY : X_ERROR_DEVICE_NOT_CONNECTED;",
        "  if (m6input::Enabled()) return user_index == 0 ? X_ERROR_EMPTY : X_ERROR_DEVICE_NOT_CONNECTED;")))
    check("trace needs both variables", 'std::getenv("R3HD_NONINTRUSIVE") != nullptr && trace && std::strcmp(trace, "1") == 0'
          in trace)
    check("trace bounded", "lines >= 256" in trace)
    check("runner validates the user", "[ValidateSet(0, 1, 2, 3)][int]$TestInputUser = 0" in runner)
    check("runner clears the variable by default",
          "[Environment]::SetEnvironmentVariable('R3HD_TEST_INPUT_USER', $null)" in runner)
    check("runner restores both variables", "'R3HD_TEST_INPUT_USER', 'R3HD_PROFILE_TRACE'" in runner)  # G6-P79 appends its flag
    passed = sum(ok for _, ok in checks)
    print(f"G6P77_SELFTEST {'PASS' if passed == len(checks) else 'FAIL'} {passed}/{len(checks)}")
    return 0 if passed == len(checks) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", nargs="?", choices=("run", "judge"))
    parser.add_argument("tag", nargs="?")
    parser.add_argument("--users", default="0,1")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not args.mode or not args.tag or not m12.NAME_RE.fullmatch(args.tag):
        raise SystemExit("usage: run|judge TAG [--users 0,1]")
    users = [int(u) for u in args.users.split(",")]
    if any(u not in (0, 1, 2, 3) for u in users):
        raise SystemExit("users must be 0-3")
    if args.mode == "run":
        for user in users:
            run_user(args.tag, user)
    return report(args.tag, users)


if __name__ == "__main__":
    raise SystemExit(main())

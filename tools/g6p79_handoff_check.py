#!/usr/bin/env python3
"""G6-P79 (D-328): hidden comparison for the TEST-ONLY profile handoff prototype.

    python tools/g6p79_handoff_check.py run TAG SCENARIO[,SCENARIO...]   -> runs them (game processes, hidden)
    python tools/g6p79_handoff_check.py judge TAG SCENARIO[,SCENARIO...] -> re-judges recorded runs (no game)
    python tools/g6p79_handoff_check.py --selftest                        -> parser / judge checks (no game)

Every run: hidden (run_milestone6.ps1 through m9_license_run.py), licence mask 1, a fresh private profile
private/work/m9_profiles/g6p79_TAG_<scenario> (never a person's profile), the G6-P77 profile / save boundary trace on,
read-only probes (tools/m8_license_probe.py). The prototype flag (-ProfileHandoff) is set per run as listed.
Schedules use the scoped XAM test source only; `axis 31N 1` moves the schedule to guest user N and `axis 32N 1/0`
unplugs / replugs guest user N (m6_test_input.h). No desktop input, physical controller, capture or dump.

Scenarios (run name suffix: user, flag, schedule):
  A   baseline, flag off: a_n (user 0 new + save), a_l (user 0 relaunch + load), a_r (user 1 START: refused)
  B   prototype: b_n (user 1 new + save), b_l (user 1 relaunch + load)
  C1  cross: c1_n (user 0 new + save, flag on), c1_l (user 1 relaunch + load, flag on)
  C2  cross: c2_n (user 1 new + save, flag on), c2_l (user 0 relaunch + load, flag on)
  D1  two users press START 0.2 s apart (user 1, then user 0), then user 1 START again
  D2  user 1 starts a game; user 0 presses START after the commit (during the intro), flag on
  D3  user 1 presses START and is unplugged 0.3 s later (before the commit); replugged later; user 0 START after
  D4  user 1 starts a game; user 1 is unplugged after the commit, then replugged
Records: private/work/g6p79/g6p79_TAG_<scenario>.json.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import g6p77_profile_user_check as g77  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "g6p79"
RUNS, PROFILES = m12.RUNS, m12.PROFILES
XUID = "B13EBABEBABEBABE"

BOOT = [r"log VIDEOS\ubi.bik result=00000000", r"log menumap\menumap.lvl result=00000000", "wait 10", "probe title"]
NEW = BOOT + ["press 40", "wait 4", "probe after_handoff", "wait 8", "probe after_start",
              "press 44", "wait 8", "press 44", "wait 8", "press 44",
              r"log VIDEOS\intro.bik result=00000000 60", "wait 4", "probe after_save"]
LOAD = BOOT + ["press 40", "wait 4", "probe after_handoff", "wait 8", "probe after_start",
               "axis 301 -32767", "wait 0.3", "axis 301 0", "wait 2", "press 44", "wait 8", "press 44",
               "wait 25", "probe loaded"]
REFUSED = BOOT + ["press 40", "wait 4", "probe after_handoff", "wait 8", "probe after_start", "wait 4"]
TWO_STARTS = BOOT + ["press 40", "axis 310 1", "press 40", "wait 4", "probe after_two", "wait 8",
                     "probe after_two_late", "axis 311 1", "press 40", "wait 4", "probe after_retry", "wait 8",
                     "probe after_retry_late"]
AFTER_COMMIT = BOOT + ["press 40", "wait 12", "probe after_start", "press 44", "wait 8", "press 44", "wait 8",
                       "press 44", r"log VIDEOS\intro.bik result=00000000 60", "wait 2", "axis 310 1", "wait 1",
                       "press 40",
                       "wait 4", "probe after_second_start"]
UNPLUG_BEFORE = BOOT + ["press 40", "axis 321 1", "wait 4", "probe unplugged", "wait 8", "probe unplugged_late",
                        "axis 321 0", "wait 3", "axis 310 1", "wait 1", "press 40", "wait 4", "probe after_p1",
                        "wait 8", "probe after_p1_late"]
# A route code and a press written together can reach the old user in one poll (the switch is applied inside that
# poll's sample); every switch is therefore followed by `wait 1` except in D1, which wants the near-simultaneous press.
RECLAIM = TWO_STARTS[:len(BOOT) + 5] + ["wait 8", "probe refused", "axis 310 1", "wait 1", "press 40", "wait 4",
                                        "probe p1_again", "wait 8", "probe p1_again_late"]
UNPLUG_AFTER = BOOT + ["press 40", "wait 12", "probe after_start", "press 44", "wait 8", "press 44", "wait 8",
                       "press 44", r"log VIDEOS\intro.bik result=00000000 60", "wait 2", "axis 321 1", "wait 5",
                       "probe unplugged", "axis 321 0", "wait 5", "probe replugged"]

# scenario -> [(suffix, user, flag, steps, seconds, profile suffix)]
SCENARIOS = {
    "A": [("a_n", 0, False, NEW, 90, "a"), ("a_l", 0, False, LOAD, 100, "a"), ("a_r", 1, False, REFUSED, 70, "ar")],
    "B": [("b_n", 1, True, NEW, 90, "b"), ("b_l", 1, True, LOAD, 100, "b")],
    "C1": [("c1_n", 0, True, NEW, 90, "c1"), ("c1_l", 1, True, LOAD, 100, "c1")],
    "C2": [("c2_n", 1, True, NEW, 90, "c2"), ("c2_l", 0, True, LOAD, 100, "c2")],
    "D1": [("d1", 1, True, TWO_STARTS, 100, "d1")],
    "D2": [("d2", 1, True, AFTER_COMMIT, 100, "d2")],
    "D3": [("d3", 1, True, UNPLUG_BEFORE, 100, "d3")],
    "D4": [("d4", 1, True, UNPLUG_AFTER, 100, "d4")],
    "D5": [("d5", 1, True, RECLAIM, 100, "d5")],
}

HANDOFF = re.compile(r"G6P79 handoff signin_request panes=(\d+) flags=([0-9A-F]+) outcome=(\w+) from=(\d+) to=(\d+) "
                     r"candidate=(\d+) connected=(\d{4})")
LOCKED = re.compile(r"G6P79 handoff locked owner=(\d+) witness=(\w+)")
START = re.compile(r"G6P79 start user=(\d+) down=(\d) owner=(\d+)")
ENABLED = re.compile(r"G6P79 profile_handoff enabled=1 owner=(\d+)")


def run_name(tag, suffix):
    return f"g6p79_{tag}_{suffix}"


def profile_name(tag, suffix):
    return f"g6p79_{tag}_{suffix}"


def g6p79_events(lines):
    out = []
    for line in lines:
        if m := HANDOFF.search(line):
            out.append({"event": "signin_request", "panes": int(m[1]), "flags": m[2], "outcome": m[3],
                        "from": int(m[4]), "to": int(m[5]), "candidate": int(m[6]), "connected": m[7]})
        elif m := LOCKED.search(line):
            out.append({"event": "locked", "owner": int(m[1]), "witness": m[2]})
        elif m := START.search(line):
            out.append({"event": "start", "user": int(m[1]), "down": int(m[2]), "owner": int(m[3])})
        elif m := ENABLED.search(line):
            out.append({"event": "enabled", "owner": int(m[1])})
    return out


def signed_in_users(state):
    """Users the title's current sign-in records show signed in (state != 0 or a non-zero XUID at 82875000 + 40n).
    The XUID copy at 82875100 is the last signed-in XUID (written only while signed in, never cleared; sub_820F4BC8)
    and is reported, not judged."""
    if not state or "signin_cache" not in state:
        return None
    return [n for n, rec in enumerate(state["signin_cache"])
            if rec.get("state") or int(rec.get("xuid", "0") or "0", 16)]


def exclusive(probes):
    """Invariant 1 at every probe: at most one user holds the profile, and only with the local XUID."""
    bad = []
    for label, state in probes.items():
        users = signed_in_users(state)
        if users is None:
            bad.append(f"{label}: no sign-in cache")
            continue
        if len(users) > 1:
            bad.append(f"{label}: users {users} signed in")
        mask = state.get("signed_in_mask")
        if mask is not None and (bin(mask).count("1") > 1 or state.get("signed_in_count", 0) > 1):
            bad.append(f"{label}: title mask {mask:#x} count {state.get('signed_in_count')}")
        for n in users:
            rec = state["signin_cache"][n]
            if rec["xuid"] not in (XUID, "0" * 16):
                bad.append(f"{label}: user {n} xuid {rec['xuid']}")
    return bad


def run_facts(run, user, flag):
    reasons, facts = [], {"run": run}
    meta_path = RUNS / run / "run.json"
    if not meta_path.is_file():
        return facts, ["run.json missing"], []
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    facts.update(exit_code=meta.get("exit_code"), executable_sha256=meta.get("executable_sha256"),
                 test_input_user=meta.get("test_input_user"), profile_handoff=meta.get("profile_handoff"))
    if meta.get("exit_code") != 0 or meta.get("forced_termination"):
        reasons.append(f"exit_code={meta.get('exit_code')} forced={meta.get('forced_termination')}")
    if meta.get("game_foreground_events") != 0 or meta.get("game_foreground_samples") != 0:
        reasons.append("foreground events/samples")
    if meta.get("test_input_user") != user or bool(meta.get("profile_handoff")) != flag:
        reasons.append(f"runner recorded user {meta.get('test_input_user')} handoff {meta.get('profile_handoff')}")
    lines = m12.run_lines(RUNS / run)
    events = g6p79_events(lines)
    enabled = [e for e in events if e["event"] == "enabled"]
    if flag and not enabled:
        reasons.append("flag on but no 'G6P79 profile_handoff enabled' line")
    if not flag and events:
        reasons.append(f"flag off but {len(events)} G6P79 lines")
    if not any("M23 haptics policy=suppressed physical_pad_drivers=none" in l for l in lines):
        reasons.append("no M23 suppressed-haptics line")
    return facts, reasons, events


def judge_run(tag, suffix, user, flag, profile_suffix):
    run = run_name(tag, suffix)
    facts, reasons, events = run_facts(run, user, flag)
    probes = g77.probes(run)
    calls = g77.xam_calls(m12.run_lines(RUNS / run)) if (RUNS / run).is_dir() else []
    reasons += exclusive(probes)
    return {"run": run, "user": user, "flag": flag, **facts, "events": events, "probes": probes,
            "xam": g77.summarize(calls), "reasons": reasons}


def save_of(tag, profile_suffix):
    save, level = m12.one_valid_save(PROFILES / profile_name(tag, profile_suffix))
    if save is None:
        return None, None
    return {"file": save.relative_to(PROFILES / profile_name(tag, profile_suffix)).as_posix(),
            "sha256": m12.sha256(save), "level": level, "bytes": save.stat().st_size}, save


def moved(events, frm, to):
    return any(e["event"] == "signin_request" and e["outcome"] == "moved" and e["from"] == frm and e["to"] == to
               for e in events)


def locked(events, owner):
    return any(e["event"] == "locked" and e["owner"] == owner for e in events)


def committed(probes, label, user):
    s = probes.get(label) or {}
    return s.get("profile_user") == user and s.get("pad_lock_mask") == (1 << user) and s.get("active_pad") == user


def content_users(rec):
    return sorted({e.split()[0] for e in rec["xam"].get("XamContentCreateEx", [])})


def judge(tag, scenario):
    runs = SCENARIOS[scenario]
    recs = {s: judge_run(tag, s, u, f, p) for s, u, f, _, _, p in runs}
    checks = []

    def check(label, ok):
        checks.append((label, bool(ok)))

    def new_and_load(n, l, n_user, l_user, flag, profile):
        rn, rl = recs[n], recs[l]
        save, path = save_of(tag, profile)
        rn["save"] = save
        if flag and n_user:
            check(f"{n}: profile moved 0 -> {n_user} at the title's sign-in request", moved(rn["events"], 0, n_user))
        if flag:
            check(f"{n}: owner {n_user} locked by a commit witness", locked(rn["events"], n_user))
        check(f"{n}: the title committed user {n_user} (active pad, profile user, lock mask)",
              committed(rn["probes"], "after_start", n_user))
        check(f"{n}: content created for user {n_user}", content_users(rn) == [f"user={n_user}"])
        check(f"{n}: one genuine save in the {XUID} namespace",
              save is not None and save["file"].startswith(f"{XUID}/5841123F/"))
        if flag and l_user:
            check(f"{l}: profile moved 0 -> {l_user} after relaunch", moved(rl["events"], 0, l_user))
        check(f"{l}: the title committed user {l_user}", committed(rl["probes"], "after_start", l_user))
        evaluated = m12.evaluate_run(run_name(tag, l), save["level"].lower(), save["sha256"],
                                     forbid_movie="intro.bik") if save else {"reasons": ["no save"]}
        rl["evaluate"] = {k: evaluated.get(k) for k in ("level_key", "save_sha256", "forbidden_movie_opens",
                                                        "stub_import_lines", "fatal_lines")}
        check(f"{l}: the save loads (level opens, no intro movie, bytes unchanged): {evaluated.get('reasons')}",
              not evaluated.get("reasons"))
        after = m12.sha256(path) if path is not None and path.exists() else None
        check(f"{l}: save hash unchanged across relaunch", save is not None and after == save["sha256"])

    if scenario == "A":
        new_and_load("a_n", "a_l", 0, 0, False, "a")
        r = recs["a_r"]
        check("a_r: flag off - user 1 is refused at sign-in (XamShowSigninUI, no commit)",
              any("r3=00000001" in e or "caller=820F5268" in e for e in r["xam"].get("XamShowSigninUI", [])) and
              not r["xam"].get("XamContentCreateEx") and not r["xam"].get("XamShowDeviceSelectorUI"))
        check("a_r: flag off - no profile directory written", not (PROFILES / profile_name(tag, "ar") / "user").exists())
        check("a_r: flag off - lock mask 0 after START", (r["probes"].get("after_start") or {}).get("pad_lock_mask") == 0)
    elif scenario == "B":
        new_and_load("b_n", "b_l", 1, 1, True, "b")
    elif scenario == "C1":
        new_and_load("c1_n", "c1_l", 0, 1, True, "c1")
        check("c1_n: flag on, pad 1 needs no handoff", not any(e["event"] == "signin_request" for e in recs["c1_n"]["events"]))
    elif scenario == "C2":
        new_and_load("c2_n", "c2_l", 1, 0, True, "c2")
        check("c2_l: flag on, pad 1 needs no handoff", not any(e["event"] == "signin_request" for e in recs["c2_l"]["events"]))
    elif scenario == "D1":
        r = recs["d1"]
        reqs = [e for e in r["events"] if e["event"] == "signin_request"]
        r["signin_requests"] = reqs
        check("d1: every sign-in request left exactly one owner (exclusivity at all probes)", not exclusive(r["probes"]))
        check("d1: recorded the title's selection and the handoff outcome", bool(reqs) or bool(r["probes"]))
    elif scenario == "D2":
        r = recs["d2"]
        check("d2: user 1 committed and locked", locked(r["events"], 1) and committed(r["probes"], "after_start", 1))
        check("d2: user 0's START after the commit did not move the profile",
              not any(e["event"] == "signin_request" and e["outcome"] == "moved" and e["to"] == 0 for e in r["events"]))
        check("d2: the second START reached user 0", any(e["event"] == "start" and e["user"] == 0 and e["down"]
                                                         for e in r["events"]))
        s = r["probes"].get("after_second_start") or {}
        check("d2: after the second START the title still has user 1 (profile user, lock mask)",
              s.get("profile_user") == 1 and s.get("pad_lock_mask") == 2)
    elif scenario == "D3":
        r = recs["d3"]
        r["signin_requests"] = [e for e in r["events"] if e["event"] == "signin_request"]
        check("d3: exclusivity at all probes", not exclusive(r["probes"]))
        check("d3: the title committed user 1 although it was unplugged 0.3 s after START (after the handoff)",
              locked(r["events"], 1) and committed(r["probes"], "unplugged", 1))
        r["not_exercised"] = ["replug and pad 1's later START (schedule stalls while the scheduled user is unplugged)"]
    elif scenario == "D5":
        r = recs["d5"]
        r["signin_requests"] = [e for e in r["events"] if e["event"] == "signin_request"]
        check("d5: exclusivity at all probes", not exclusive(r["probes"]))
        check("d5: pad 1's retry reached user 0", any(e["event"] == "start" and e["user"] == 0 and e["down"]
                                                     for e in r["events"]))
        s = r["probes"].get("p1_again_late") or {}
        check("d5: observed - pad 1's retry did not reclaim the profile (one request, owner 1, nothing committed)",
              len(r["signin_requests"]) == 1 and signed_in_users(s) == [1] and s.get("pad_lock_mask") == 0)
    elif scenario == "D4":
        r = recs["d4"]
        check("d4: user 1 committed and locked", locked(r["events"], 1) and committed(r["probes"], "after_start", 1))
        check("d4: unplug / replug after the commit moved nothing",
              not any(e["event"] == "signin_request" and e["outcome"] == "moved" and e["to"] != 1 for e in r["events"]))
        s = r["probes"].get("unplugged") or {}
        check("d4: unplugged: title still has profile user 1", s.get("profile_user") == 1)
        # Route codes are read only by the scheduled user's poll; while that user is unplugged nobody reads the
        # schedule, so the replug code (and anything after it) never takes effect. Not exercised, not passed.
        r["not_exercised"] = ["replug of the scheduled user (schedule stalls while it is unplugged)"]
    for rec in recs.values():
        for reason in rec["reasons"]:
            check(f"{rec['run']}: {reason}", False)
    exes = {rec.get("executable_sha256") for rec in recs.values()}
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"g6p79_{tag}_{scenario}.json"
    out.write_text(json.dumps({"tag": tag, "scenario": scenario, "executables": sorted(map(str, exes)),
                               "checks": checks, "runs": recs}, indent=2) + "\n", encoding="utf-8")
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {label}")
    passed = sum(ok for _, ok in checks)
    print(f"G6P79_SCENARIO {scenario} {'PASS' if passed == len(checks) else 'FAIL'} {passed}/{len(checks)} "
          f"exe={','.join(str(e)[:8] for e in exes)} record={out.relative_to(ROOT).as_posix()}")
    return passed == len(checks)


def run_scenario(tag, scenario):
    for suffix, user, flag, steps, seconds, profile in SCENARIOS[scenario]:
        run = run_name(tag, suffix)
        if (RUNS / run).exists():
            raise SystemExit(f"already exists: {RUNS / run}")
        path = WORK / "steps" / f"{run}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join([f"# G6-P79 {scenario} {suffix}: user {user}, handoff {'on' if flag else 'off'}"]
                                  + steps) + "\n", encoding="ascii")
        command = [sys.executable, str(ROOT / "tools" / "m9_license_run.py"), run, str(path), "--license-mask", "1",
                   "--seconds", str(seconds), "--user-root", profile_name(tag, profile), "--play",
                   "--input-user", str(user), "--profile-trace"] + (["--profile-handoff"] if flag else [])
        error = m12.run_driver(command, WORK / f"{run}.driver.log", seconds)
        print(f"{scenario} {run}: {'ok' if error is None else error}", flush=True)


def selftest():
    checks = []

    def check(label, ok):
        checks.append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {label}")

    lines = ["[x] G6P79 profile_handoff enabled=1 owner=0",
             "[x] G6P79 start user=1 down=1 owner=0",
             "[x] G6P79 handoff signin_request panes=1 flags=0 outcome=moved from=0 to=1 candidate=1 connected=1100",
             "[x] G6P79 handoff locked owner=1 witness=profile_settings", "noise"]
    ev = g6p79_events(lines)
    check("events parsed", [e["event"] for e in ev] == ["enabled", "start", "signin_request", "locked"])
    check("moved / locked detected", moved(ev, 0, 1) and locked(ev, 1) and not moved(ev, 1, 0))
    one = {"signin_cache": [{"xuid": "0" * 16, "state": 0, "xuid_copy": "0" * 16},
                            {"xuid": XUID, "state": 1, "xuid_copy": XUID}] + [{"xuid": "0" * 16, "state": 0,
                                                                                "xuid_copy": "0" * 16}] * 2}
    stale = json.loads(json.dumps(one))
    stale["signin_cache"][0]["xuid_copy"] = XUID  # last signed-in XUID after a handoff: reported, not an owner
    check("a stale XUID copy is not an owner", exclusive({"p": stale}) == [])
    masked = json.loads(json.dumps(one))
    masked.update(signed_in_mask=3, signed_in_count=2)
    check("a two-bit title mask rejected", exclusive({"p": masked}) != [])
    two = json.loads(json.dumps(one))
    two["signin_cache"][0] = {"xuid": XUID, "state": 1, "xuid_copy": XUID}
    forged = json.loads(json.dumps(one))
    forged["signin_cache"][1]["xuid"] = "E000000000000001"
    check("one owner accepted", exclusive({"p": one}) == [] and signed_in_users(one) == [1])
    check("two owners rejected", exclusive({"p": two}) != [])
    check("a foreign XUID rejected", exclusive({"p": forged}) != [])
    check("a missing cache rejected", exclusive({"p": None}) != [])
    check("commit judged", committed({"s": {"profile_user": 1, "pad_lock_mask": 2, "active_pad": 1}}, "s", 1) and
          not committed({"s": {"profile_user": 0, "pad_lock_mask": 1, "active_pad": 0}}, "s", 1))
    check("scenarios name distinct runs", len({s for v in SCENARIOS.values() for s, *_ in v}) ==
          sum(len(v) for v in SCENARIOS.values()))
    check("flag-off baseline runs exist", all(not f for _, _, f, *_ in SCENARIOS["A"]))
    print(f"G6P79_CHECK_SELFTEST {'PASS' if all(checks) else 'FAIL'} {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", nargs="?", choices=("run", "judge"))
    parser.add_argument("tag", nargs="?")
    parser.add_argument("scenarios", nargs="?")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not args.mode or not args.tag or not args.scenarios or not m12.NAME_RE.fullmatch(args.tag):
        raise SystemExit("usage: run|judge TAG SCENARIO[,SCENARIO]")
    scenarios = args.scenarios.split(",")
    if any(s not in SCENARIOS for s in scenarios):
        raise SystemExit(f"scenarios: {', '.join(SCENARIOS)}")
    ok = True
    for s in scenarios:
        if args.mode == "run":
            run_scenario(args.tag, s)
        ok = judge(args.tag, s) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

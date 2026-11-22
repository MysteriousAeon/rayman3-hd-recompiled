#!/usr/bin/env python3
"""G6-P82 / G6-P83 (D-331, D-332): hidden A/B of the state-change-aware XamShowSigninUI notification.

    python tools/g6p82_signin_notify_check.py run TAG SCENARIO[,SCENARIO...]   -> runs them (game processes, hidden)
    python tools/g6p82_signin_notify_check.py judge TAG SCENARIO[,SCENARIO...] -> re-judges recorded runs (no game)
    python tools/g6p82_signin_notify_check.py --selftest                        -> schedule / judge checks (no game)

Every run uses the G6-P80 harness unchanged (tools/g6p80_handoff_check.py: hidden run_milestone6.ps1 through
m9_license_run.py, licence mask 1, a fresh private profile private/work/m9_profiles/g6p82_TAG_<suffix>, the G6-P77
profile / save trace, read-only probes, user-scoped events and scripted message-box answers, delivery judges). The
only variable between a "0" and a "1" scenario is the notification policy. Since G6-P83 (D-332) "1" is the build's
default (no option) and "0" selects the switch back R3HD_SIGNIN_NOTIFY=legacy (runner -SigninNotifyLegacy, m9
--signin-notify-legacy). Before G6-P83 (D-331 binary) "1" needed --signin-notify-on-change instead; that option is
gone, so the D-331 records are re-judged with "judge", not re-run.
Each XamShowSigninUI call logs one "G6P82 signin_ui owner_before=.. owner_after=.. signinchanged=.. ui_off=1
notify_on_change=.." line in hidden runs (logging only), which gives the per-call notification sequence.

Scenarios (pad 2 = guest user 1, never signed in under the single-profile policy; handoff off unless stated):
  E0 / E1  pad 2 START refused, the title's box answered "Back", then pad 1 START (the G6-P80 E schedule)
  R0 / R1  pad 2 START, "Back", pad 2 START again (retry), "Back" if a box is open, then pad 1 START
  S0 / S1  pad 2 START, "Sign In", "Back" if a box is open, then pad 1 START
  G0 / G1  user 0: New Game + save, relaunch + Load (no user events)
  H1       genuine sign-in change: handoff on + user events + default policy: pad 2 New + save, relaunch + Load
In R / S the second answer reaches a box only if the title reopened it; a dropped second answer is an observation
(the guest-visible difference under test), not a harness failure. Records: private/work/g6p82/g6p82_TAG_<scenario>.json.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import g6p77_profile_user_check as g77  # noqa: E402
import g6p79_handoff_check as g79  # noqa: E402
import g6p80_handoff_check as g80  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "g6p82"
RUNS, PROFILES = m12.RUNS, m12.PROFILES
XUID = g79.XUID
BOOT, NEW, LOAD = g79.BOOT, g79.NEW, g79.LOAD
P1, SIGN_IN, BACK = g80.P1, g80.SIGN_IN, g80.BACK

E = g80.E
R = BOOT + ["press 40", "wait 4", "probe refused", *BACK, "wait 4", "probe after_back", "press 40", "wait 4",
            "probe after_retry", *BACK, "wait 4", "probe after_retry_back", *P1, "press 40", "wait 4", "probe after_p1",
            "wait 8", "probe after_p1_late"]
S = BOOT + ["press 40", "wait 4", "probe refused", *SIGN_IN, "wait 4", "probe after_signin", *BACK, "wait 4",
            "probe after_signin_back", *P1, "press 40", "wait 4", "probe after_p1", "wait 8", "probe after_p1_late"]

# scenario -> [(suffix, input user, handoff, user events, notify flag, steps, seconds, profile suffix)]
SCENARIOS = {
    "E0": [("e0", 1, False, True, False, E, 90, "e0")],
    "E1": [("e1", 1, False, True, True, E, 90, "e1")],
    "R0": [("r0", 1, False, True, False, R, 100, "r0")],
    "R1": [("r1", 1, False, True, True, R, 100, "r1")],
    "S0": [("s0", 1, False, True, False, S, 90, "s0")],
    "S1": [("s1", 1, False, True, True, S, 90, "s1")],
    "G0": [("g0_n", 0, False, False, False, NEW, 90, "g0"), ("g0_l", 0, False, False, False, LOAD, 100, "g0")],
    "G1": [("g1_n", 0, False, False, True, NEW, 90, "g1"), ("g1_l", 0, False, False, True, LOAD, 100, "g1")],
    "H1": [("h1_n", 1, True, True, True, NEW, 90, "h1"), ("h1_l", 1, True, True, True, LOAD, 100, "h1")],
}
SIGNIN_UI = re.compile(r"G6P82 signin_ui owner_before=(\d+) owner_after=(\d+) signinchanged=(\d) ui_off=1 "
                       r"notify_on_change=(\d)")
DROP_OK = {"R0", "R1", "S0", "S1"}  # the second answer may legitimately find no box


def name(tag, suffix):
    return f"g6p82_{tag}_{suffix}"


g80.name = name  # the G6-P80 judge / save helpers resolve run and profile names through this


P1_TARGET = re.compile(r"G6P80 event target seq=\d+ user=0 ")


def signin_calls(lines):
    """Per XamShowSigninUI call: owners, decision, flag; "after_p1" once the schedule has targeted pad 1 (user 0)."""
    out, after_p1 = [], False
    for line in lines:
        if P1_TARGET.search(line):
            after_p1 = True
        if m := SIGNIN_UI.search(line):
            out.append({"owner_before": int(m[1]), "owner_after": int(m[2]), "signinchanged": int(m[3]),
                        "notify_flag": int(m[4]), "after_p1": after_p1})
    return out


def judge_run(tag, suffix, user, handoff, ue, notify, steps, scenario):
    rec = g80.judge_run(tag, suffix, user, handoff, ue, steps)
    meta_path = RUNS / name(tag, suffix) / "run.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig")) if meta_path.is_file() else {}
    rec["signin_notify_on_change"] = meta.get("signin_notify_on_change")
    if bool(meta.get("signin_notify_on_change")) != notify:
        rec["reasons"].append(f"runner recorded signin_notify_on_change {meta.get('signin_notify_on_change')}")
    lines = m12.run_lines(RUNS / name(tag, suffix)) if meta else []
    rec["signin_calls"] = signin_calls(lines)
    if any(c["notify_flag"] != int(notify) for c in rec["signin_calls"]):
        rec["reasons"].append("a G6P82 line disagrees with the notify flag")
    if scenario in DROP_OK:  # judged by the scenario instead: the first answer must be applied
        rec["reasons"] = [r for r in rec["reasons"] if not r.startswith("exercised: answer")]
    return rec


def answers(rec):
    return [(e["button"], e["dropped"]) for e in rec["ue"] if e["kind"] == "dialog_answer"]


def boxes(rec):
    return sum(e["kind"] == "dialog_open" for e in rec["ue"])


def probe(rec, label, field):
    return (rec["probes"].get(label) or {}).get(field)


def judge(tag, scenario):
    recs = {s: judge_run(tag, s, u, h, ue, n, steps, scenario) for s, u, h, ue, n, steps, _, _ in SCENARIOS[scenario]}
    checks, observed = [], {}
    notify = SCENARIOS[scenario][0][4]

    def check(label, ok):
        checks.append((label, bool(ok)))

    def calls_ok(rec, n_calls, n_after_p1=0):
        calls = rec["signin_calls"]
        pre = [c for c in calls if not c["after_p1"]]
        check(f"{rec['run']}: {len(pre)} XamShowSigninUI call(s) before pad 1 is targeted, expected {n_calls}",
              len(pre) == n_calls)
        check(f"{rec['run']}: {len(calls) - len(pre)} call(s) after pad 1's START, expected {n_after_p1}",
              len(calls) - len(pre) == n_after_p1)
        for c in calls:
            want = 1 if not notify else int(c["owner_before"] != c["owner_after"])
            check(f"{rec['run']}: SIGNINCHANGED={c['signinchanged']} for owner {c['owner_before']}->{c['owner_after']} "
                  f"(flag {int(notify)}: expected {want})", c["signinchanged"] == want)

    if scenario[0] in "ERS":
        r = recs[scenario.lower()]
        observed["guest"] = g80.guest_state(r)
        observed["signin_calls"] = r["signin_calls"]
        observed["answers"] = answers(r)
        observed["boxes_opened"] = boxes(r)
        check(f"{scenario}: pad 2 refused: the title's sign-in error box opened (latch 0 at open)",
              boxes(r) >= 1 and probe(r, "refused", "signin_box_open") == 1)
        check(f"{scenario}: the profile never left user 0 (signed-in mask 1 at every probe)",
              all(g80.owner_at(r, k) in (0, None) for k in r["probes"]))
        first = answers(r)[:1]
        check(f"{scenario}: the first scheduled answer reached the open box", first and first[0][1] is None)
        observed["latch_with_box_open"] = probe(r, "refused", "signed_out_latch")
        if not notify:
            check(f"{scenario}: flag off - the stub sent SIGNINCHANGED with no owner change (0 -> 0)",
                  [{k: c[k] for k in ("owner_before", "owner_after", "signinchanged")} for c in r["signin_calls"][:1]] ==
                  [{"owner_before": 0, "owner_after": 0, "signinchanged": 1}])
        else:
            check(f"{scenario}: flag on - SIGNINCHANGED suppressed with no owner change (0 -> 0)",
                  r["signin_calls"] and all(c["signinchanged"] == 0 for c in r["signin_calls"]))
        if scenario[0] == "E":
            calls_ok(r, 1)
            check(f"{scenario}: latch 82836CC8 while the box is open is {'1 (refresh armed)' if not notify else '0'}",
                  probe(r, "refused", "signed_out_latch") == (0 if notify else 1))
            check(f"{scenario}: after 'Back' the title's box flag 828750C4 is {'stuck at 1' if not notify else 'cleared'}",
                  probe(r, "after_back", "signin_box_open") == (0 if notify else 1))
        elif scenario[0] == "R":
            calls_ok(r, 2 if notify else 1)
            if notify:
                check("R1: after 'Back' the box flag is cleared", probe(r, "after_back", "signin_box_open") == 0)
                check("R1: pad 2's retry START reached the title's sign-in request again and the box reopened",
                      boxes(r) == 2 and probe(r, "after_retry", "signin_box_open") == 1)
                check("R1: the second 'Back' reached the reopened box and it closed",
                      answers(r) == [(1, None), (1, None)] and probe(r, "after_retry_back", "signin_box_open") == 0)
            else:
                check("R0: after 'Back' the box flag stays 1", probe(r, "after_back", "signin_box_open") == 1)
                check("R0: pad 2's retry START made no sign-in request and opened no box (request word set, blocked)",
                      boxes(r) == 1 and probe(r, "after_retry", "signin_ui_requested") == 1)
                check("R0: the second 'Back' found no box", len(answers(r)) == 2 and answers(r)[1][1] is not None)
        else:  # S
            # S0 (E-568): the 'Sign In' request word waits behind the stuck box; after pad 1's commit the device
            # selector's close clears the box and the stale request runs (a second no-change call, awaiting left 1).
            calls_ok(r, 2 if notify else 1, 0 if notify else 1)
            if not notify:
                check("S0: the stale request leaves the awaiting word 828750C8 set after pad 1's commit",
                      probe(r, "after_p1_late", "signin_awaiting") == 1)
            if notify:
                check("S1: 'Sign In' reached the title's sign-in request again and the box reopened",
                      boxes(r) == 2 and probe(r, "after_signin", "signin_box_open") == 1)
                check("S1: 'Back' then reached the reopened box and it closed",
                      answers(r) == [(0, None), (1, None)] and probe(r, "after_signin_back", "signin_box_open") == 0)
            else:
                check("S0: 'Sign In' set the request word but no new request or box followed (box flag stuck)",
                      boxes(r) == 1 and probe(r, "after_signin", "signin_box_open") == 1 and
                      probe(r, "after_signin", "signin_ui_requested") == 1)
                check("S0: the following 'Back' found no box", len(answers(r)) == 2 and answers(r)[1][1] is not None)
        check(f"{scenario}: pad 1's START then commits user 0 in the same process",
              g80.committed(r, "after_p1_late", 0))
    elif scenario in ("G0", "G1", "H1"):
        n, l = SCENARIOS[scenario][0][0], SCENARIOS[scenario][1][0]
        user = SCENARIOS[scenario][0][1]
        rn, rl = recs[n], recs[l]
        save, path = g80.save_of(tag, SCENARIOS[scenario][0][7])
        rn["save"] = save
        if user == 0:
            check(f"{scenario}: user 0 makes no XamShowSigninUI call (the flag has nothing to act on)",
                  not rn["signin_calls"] and not rl["signin_calls"] and not rn["xam"].get("XamShowSigninUI"))
        else:
            moved = [e for e in g80.requests(rn) if e["outcome"] == "moved" and e["to"] == 1]
            check(f"{n}: the handoff moved the profile 0 -> 1 at the title's sign-in request", bool(moved))
            check(f"{n}: the genuine owner change sent SIGNINCHANGED (owner 0 -> 1, signinchanged=1)",
                  any({k: c[k] for k in ("owner_before", "owner_after", "signinchanged", "notify_flag")} ==
                      {"owner_before": 0, "owner_after": 1, "signinchanged": 1, "notify_flag": 1}
                      for c in rn["signin_calls"]))
            check(f"{n}: no same-owner call sent SIGNINCHANGED",
                  all(c["signinchanged"] == int(c["owner_before"] != c["owner_after"]) for c in rn["signin_calls"]))
            check(f"{n}: owner 1 locked by a commit witness", g79.locked(rn["events"], 1))
            check(f"{l}: profile moved 0 -> 1 after relaunch", g79.moved(rl["events"], 0, 1))
        check(f"{n}: the title committed user {user}", g80.committed(rn, "after_start", user))
        check(f"{n}: content created for user {user}", g79.content_users(rn) == [f"user={user}"])
        check(f"{n}: one genuine save in the {XUID} namespace",
              save is not None and save["file"].startswith(f"{XUID}/5841123F/"))
        check(f"{l}: the title committed user {user}", g80.committed(rl, "after_start", user))
        evaluated = m12.evaluate_run(name(tag, l), save["level"].lower(), save["sha256"],
                                     forbid_movie="intro.bik") if save else {"reasons": ["no save"]}
        rl["evaluate"] = {k: evaluated.get(k) for k in ("level_key", "save_sha256", "forbidden_movie_opens",
                                                        "stub_import_lines", "fatal_lines")}
        check(f"{l}: the save loads (level opens, no intro movie, bytes unchanged): {evaluated.get('reasons')}",
              not evaluated.get("reasons"))
        after = m12.sha256(path) if path is not None and path.exists() else None
        check(f"{l}: save hash unchanged across relaunch", save is not None and after == save["sha256"])
    for rec in recs.values():
        for reason in rec["reasons"]:
            check(f"{rec['run']}: {reason}", False)
    exes = {rec.get("executable_sha256") for rec in recs.values()}
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"g6p82_{tag}_{scenario}.json"
    out.write_text(json.dumps({"tag": tag, "scenario": scenario, "executables": sorted(map(str, exes)),
                               "checks": checks, "observed": observed, "runs": recs}, indent=2) + "\n",
                   encoding="utf-8")
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {label}")
    passed = sum(ok for _, ok in checks)
    print(f"G6P82_SCENARIO {scenario} {'PASS' if passed == len(checks) else 'FAIL'} {passed}/{len(checks)} "
          f"exe={','.join(str(e)[:8] for e in exes)} record={out.relative_to(ROOT).as_posix()}")
    return passed == len(checks)


def policy_args(notify):
    """G6-P83: the state-change-aware policy is the default; only a "0" scenario selects the legacy switch back."""
    return [] if notify else ["--signin-notify-legacy"]


def run_scenario(tag, scenario):
    for suffix, user, handoff, ue, notify, steps, seconds, profile in SCENARIOS[scenario]:
        run = name(tag, suffix)
        if (RUNS / run).exists():
            raise SystemExit(f"already exists: {RUNS / run}")
        path = WORK / "steps" / f"{run}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join([f"# G6-P82 {scenario} {suffix}: user {user}, handoff {int(handoff)}, user events "
                                   f"{int(ue)}, signin notify on change {int(notify)}"] + steps) + "\n",
                        encoding="ascii")
        command = [sys.executable, str(ROOT / "tools" / "m9_license_run.py"), run, str(path), "--license-mask", "1",
                   "--seconds", str(seconds), "--user-root", name(tag, profile), "--play",
                   "--input-user", str(user), "--profile-trace"]
        command += (["--profile-handoff"] if handoff else []) + (["--user-events"] if ue else [])
        command += policy_args(notify)
        error = m12.run_driver(command, WORK / f"{run}.driver.log", seconds)
        print(f"{scenario} {run}: {'ok' if error is None else error}", flush=True)


def selftest():
    results = []

    def check(label, ok):
        results.append(bool(ok))
        print(f"{'ok  ' if ok else 'FAIL'} {label}")

    line = "x G6P82 signin_ui owner_before=0 owner_after=1 signinchanged=1 ui_off=1 notify_on_change=1"
    check("signin_ui line parsed", signin_calls([line, "noise"]) ==
          [{"owner_before": 0, "owner_after": 1, "signinchanged": 1, "notify_flag": 1, "after_p1": False}])
    check("calls after pad 1 is targeted are marked",
          [c["after_p1"] for c in signin_calls([line, "G6P80 event target seq=1 user=0 value=1", line])] == [False, True])
    check("pairs differ only in the notify flag",
          all([(u, h, ue, st, sec) for _, u, h, ue, _, st, sec, _ in SCENARIOS[a]] ==
              [(u, h, ue, st, sec) for _, u, h, ue, _, st, sec, _ in SCENARIOS[b]] and
              not any(x[4] for x in SCENARIOS[a]) and all(x[4] for x in SCENARIOS[b])
              for a, b in (("E0", "E1"), ("R0", "R1"), ("S0", "S1"), ("G0", "G1"))))
    check("H1 is the only handoff scenario and has every flag",
          [k for k, v in SCENARIOS.items() if any(x[2] for x in v)] == ["H1"] and
          all(x[2] and x[3] and x[4] for x in SCENARIOS["H1"]))
    check("run names are distinct", len({x[0] for v in SCENARIOS.values() for x in v}) ==
          sum(len(v) for v in SCENARIOS.values()))
    check("R retries pad 2 before targeting pad 1; S answers 'Sign In' first",
          R.index("probe after_retry") < R.index(P1[0]) and S.index(SIGN_IN[0]) < S.index(BACK[0]))
    check("R / S schedule two answers; E one", len(g80.expected_answers(R)) == 2 and
          g80.expected_answers(S) == [0, 1] and g80.expected_answers(E) == [1])
    check("run names use the G6-P82 prefix through the G6-P80 helpers", g80.name("t", "e0") == "g6p82_t_e0")
    check("G6-P83: '1' runs pass no policy option (the default); '0' runs select --signin-notify-legacy",
          policy_args(True) == [] and policy_args(False) == ["--signin-notify-legacy"])
    print(f"G6P82_CHECK_SELFTEST {'PASS' if all(results) else 'FAIL'} {sum(results)}/{len(results)}")
    return 0 if all(results) else 1


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

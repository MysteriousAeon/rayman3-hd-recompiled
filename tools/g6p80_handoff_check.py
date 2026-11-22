#!/usr/bin/env python3
"""G6-P80 (D-329): hidden scenarios for the TEST-ONLY profile handoff transaction (arbitration, rollback, retry).

    python tools/g6p80_handoff_check.py run TAG SCENARIO[,SCENARIO...]   -> runs them (game processes, hidden)
    python tools/g6p80_handoff_check.py judge TAG SCENARIO[,SCENARIO...] -> re-judges recorded runs (no game)
    python tools/g6p80_handoff_check.py --selftest                        -> parser / judge checks (no game)

Every run: hidden (run_milestone6.ps1 through m9_license_run.py), licence mask 1, a fresh private profile
private/work/m9_profiles/g6p80_TAG_<suffix> (never a person's profile), the G6-P77 profile / save trace, read-only
probes (tools/m8_license_probe.py). R3HD_EXE may name a build copy (recorded per run as executable_sha256).
Schedules use the scoped XAM test source in its user-scoped mode (-UserEvents, m6_test_input.h): `axis 31N 1` targets
guest user N, `axis 32N 1/0` unplugs / replugs user N, `axis 34B 1` answers the title's open message box with button
B (0 "Sign In", 1 "Back"; g6p80_test_dialog.h). Delivery of every scheduled press to its user is asserted from the
run log ("G6P80 event queued / delivered"). No desktop input, physical controller, capture or dump.

Scenarios (all handoff flag on and user events on, except A):
  A   flag off, user events off: a_n / a_l (user 0 new + save, relaunch + load), a_r (user 1 START: refused)
  E   flag off, user events on: user 1 START refused, the box answered "Back", then user 0 START commits user 0
  B   b_n / b_l: user 1 new + save, relaunch + load
  C1  c1_n user 0 saves, c1_l user 1 loads;  C2  c2_n user 1 saves, c2_l user 0 loads
  D1  pad 2 START, pad 1 START 0.2 s later (before the commit); the title's error box answered "Sign In"
  D2  pad 2 commits a game; pad 1 START after the commit (during the intro)
  D3  pad 2 START (0.2 s press), pad 2 unplugged at the release (before the 500 ms refresh and the commit);
      box answered "Back"; pad 1 START
  D4  pad 2 commits a game; pad 2 unplugged after the commit, then replugged
  D5  as D1, but the box answered "Back" (an abandoned START); then pad 1 START again
  D6  pad 2 START, unplugged at the release; box "Back"; pad 2 replugged and START again; then pad 1 START
  D6R recovery attempt: pad 2 START, unplugged at the release; replugged; pad 2 START while the box is open; the box
      answered "Sign In" (the title's own retry path)
  D7  pad 1 START, pad 2 START 0.2 s later (the reverse order)
Every scheduled answer must reach an open box (a dropped answer fails the run) and every scheduled unplug / replug must
be applied to its user. Results the title does not reach are reported as LIMIT lines and in "limitations", never as
PASS.
Records: private/work/g6p80/g6p80_TAG_<scenario>.json.
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

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private" / "work" / "g6p80"
RUNS, PROFILES = m12.RUNS, m12.PROFILES
XUID = g79.XUID

BOOT = g79.BOOT
NEW, LOAD, REFUSED = g79.NEW, g79.LOAD, g79.REFUSED
P1, P2 = ["axis 310 1"], ["axis 311 1"]  # target pad 1 (user 0) / pad 2 (user 1)
SIGN_IN, BACK = ["axis 340 1"], ["axis 341 1"]
COMMIT_P2 = BOOT + ["press 40", "wait 12", "probe after_start", "press 44", "wait 8", "press 44", "wait 8",
                    "press 44", r"log VIDEOS\intro.bik result=00000000 60", "wait 2"]
E = BOOT + ["press 40", "wait 4", "probe refused", *BACK, "wait 4", "probe after_back", *P1, "press 40", "wait 4",
            "probe after_p1", "wait 8", "probe after_p1_late"]
D1 = BOOT + ["press 40", *P1, "press 40", "wait 3", "probe box", *SIGN_IN, "wait 4", "probe after_answer", "wait 8",
             "probe after_answer_late"]
D2 = COMMIT_P2 + [*P1, "press 40", "wait 4", "probe after_second_start"]
D3 = BOOT + ["press 40", "axis 321 1", "wait 3", "probe unplugged", *BACK, "wait 4", "probe after_back",
             *P1, "press 40", "wait 4", "probe after_p1", "wait 8", "probe after_p1_late"]
D4 = COMMIT_P2 + ["axis 321 1", "wait 5", "probe unplugged", "axis 321 0", "wait 5", "probe replugged"]
D5 = BOOT + ["press 40", *P1, "press 40", "wait 3", "probe box", *BACK, "wait 4", "probe after_back", "press 40",
             "wait 4", "probe after_retry", "wait 8", "probe after_retry_late"]
D6 = BOOT + ["press 40", "axis 321 1", "wait 3", "probe unplugged", *BACK, "wait 4", "probe after_back",
             "axis 321 0", "wait 2", "press 40", "wait 4", "probe after_replug", "wait 8", "probe after_replug_late",
             *P1, "press 40", "wait 4", "probe after_p1", "wait 8", "probe after_p1_late"]
D6R = BOOT + ["press 40", "axis 321 1", "wait 3", "probe unplugged", "axis 321 0", "wait 2", "press 40", "wait 2",
              "probe box_after_start", *SIGN_IN, "wait 4", "probe after_answer", "wait 8", "probe after_answer_late"]
D7 = BOOT + [*P1, "press 40", *P2, "press 40", "wait 4", "probe after_two", "wait 8", "probe after_two_late"]

# scenario -> [(suffix, input user, handoff flag, user events, steps, seconds, profile suffix)]
SCENARIOS = {
    "A": [("a_n", 0, False, False, NEW, 90, "a"), ("a_l", 0, False, False, LOAD, 100, "a"),
          ("a_r", 1, False, False, REFUSED, 70, "ar")],
    "E": [("e", 1, False, True, E, 90, "e")],
    "B": [("b_n", 1, True, True, NEW, 90, "b"), ("b_l", 1, True, True, LOAD, 100, "b")],
    "C1": [("c1_n", 0, True, True, NEW, 90, "c1"), ("c1_l", 1, True, True, LOAD, 100, "c1")],
    "C2": [("c2_n", 1, True, True, NEW, 90, "c2"), ("c2_l", 0, True, True, LOAD, 100, "c2")],
    "D1": [("d1", 1, True, True, D1, 90, "d1")],
    "D2": [("d2", 1, True, True, D2, 100, "d2")],
    "D3": [("d3", 1, True, True, D3, 90, "d3")],
    "D4": [("d4", 1, True, True, D4, 100, "d4")],
    "D5": [("d5", 1, True, True, D5, 90, "d5")],
    "D6": [("d6", 1, True, True, D6, 110, "d6")],
    "D6R": [("d6r", 1, True, True, D6R, 90, "d6r")],
    "D7": [("d7", 1, True, True, D7, 80, "d7")],
}

EVENT = re.compile(r"G6P80 event (\w+) seq=(\d+) user=(\d+) value=([0-9A-F]+)")
ROLLBACK = re.compile(r"G6P80 handoff rollback user=(\d+) owner=(\d+)")
DIALOG = re.compile(r"G6P80 dialog (open buttons=(\d+) active=(\d+)|answer button=(\d+)(?: dropped=(\w+))?)")
TITLE = re.compile(r"title_user=([0-9A-F]+) start_candidate=(\d+)")
UE_ON = "G6P80 user_events enabled=1"
BUTTONS = {40: 0x10, 27: 0x10, 44: 0x1000, 51: 0x1000}


def name(tag, suffix):
    return f"g6p80_{tag}_{suffix}"


def expected_presses(steps, user):
    """The (user, button) of every scheduled press, in order, from the steps (initial target = the input user).
    Presses while the target is unplugged are expected to be dropped, not delivered."""
    target, unplugged, out = user, set(), []
    for step in steps:
        parts = step.split()
        if parts[0] == "axis" and 310 <= int(parts[1]) <= 313 and parts[2] == "1":
            target = int(parts[1]) - 310
        elif parts[0] == "axis" and 320 <= int(parts[1]) <= 323:
            (unplugged.add if parts[2] == "1" else unplugged.discard)(int(parts[1]) - 320)
        elif parts[0] == "press" and int(parts[1]) in BUTTONS:
            out.append((target, BUTTONS[int(parts[1])], target in unplugged))
    return out


def expected_answers(steps):
    """The button of every scheduled dialog answer (axis 34B 1), in order."""
    return [int(p[1]) - 340 for p in (st.split() for st in steps)
            if p[0] == "axis" and 340 <= int(p[1]) <= 343 and p[2] == "1"]


def expected_connects(steps):
    """(user, connected) of every scheduled unplug (axis 32N 1 -> 0) / replug (axis 32N 0 -> 1), in order."""
    return [(int(p[1]) - 320, 0 if p[2] == "1" else 1) for p in (st.split() for st in steps)
            if p[0] == "axis" and 320 <= int(p[1]) <= 323]


def exercised(events, steps):
    """Every scheduled answer reached an open box and every scheduled unplug / replug was applied. Problems."""
    problems = []
    answers = [e for e in events if e["kind"] == "dialog_answer"]
    got = [e["button"] for e in answers if not e["dropped"]]
    if got != expected_answers(steps):
        problems.append(f"answers applied {got} != scheduled {expected_answers(steps)}")
    for e in answers:
        if e["dropped"]:
            problems.append(f"answer button={e['button']} dropped ({e['dropped']}): not exercised")
    connects = [(e["user"], e["value"]) for e in events if e["kind"] == "connect"]
    if connects != expected_connects(steps):
        problems.append(f"connects applied {connects} != scheduled {expected_connects(steps)}")
    return problems


def ue_events(lines):
    out = []
    for line in lines:
        if m := EVENT.search(line):
            out.append({"kind": m[1], "seq": int(m[2]), "user": int(m[3]), "value": int(m[4], 16)})
        elif m := ROLLBACK.search(line):
            out.append({"kind": "rollback", "user": int(m[1]), "owner": int(m[2])})
        elif m := DIALOG.search(line):
            if m[2]:
                out.append({"kind": "dialog_open", "buttons": int(m[2]), "active": int(m[3])})
            else:
                out.append({"kind": "dialog_answer", "button": int(m[4]), "dropped": m[5]})
    return out


def delivery(events, expected):
    """Every scheduled press reached exactly its user, in order (queued and delivered with the same seq), or was
    dropped because its user was unplugged. Returns a list of problems."""
    queued = [e for e in events if e["kind"] == "queued"]
    dropped = [e for e in events if e["kind"] == "dropped"]
    delivered = {(e["seq"], e["user"]) for e in events if e["kind"] == "delivered"}
    problems = []
    want = [(u, b) for u, b, gone in expected if not gone]
    got = [(e["user"], e["value"]) for e in queued]
    if got != want:
        problems.append(f"queued {got} != scheduled {want}")
    for e in queued:
        if (e["seq"], e["user"]) not in delivered and not any(d["seq"] == e["seq"] for d in dropped):
            problems.append(f"press seq={e['seq']} user={e['user']} never delivered")
    want_drop = sum(1 for *_, gone in expected if gone)
    if sum(1 for d in dropped if not any(q["seq"] == d["seq"] for q in queued)) < want_drop:
        problems.append(f"expected {want_drop} drop(s) for unplugged users")
    return problems


def judge_run(tag, suffix, user, flag, ue, steps):
    run = name(tag, suffix)
    facts, reasons, events = {"run": run}, [], []
    meta_path = RUNS / run / "run.json"
    if not meta_path.is_file():
        return {"run": run, "reasons": ["run.json missing"], "probes": {}, "events": [], "ue": [], "xam": {}}
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    facts.update(exit_code=meta.get("exit_code"), executable_sha256=meta.get("executable_sha256"),
                 test_input_user=meta.get("test_input_user"), profile_handoff=meta.get("profile_handoff"),
                 user_events=meta.get("user_events"))
    if meta.get("exit_code") != 0 or meta.get("forced_termination"):
        reasons.append(f"exit_code={meta.get('exit_code')} forced={meta.get('forced_termination')}")
    if meta.get("game_foreground_events") != 0 or meta.get("game_foreground_samples") != 0:
        reasons.append("foreground events/samples")
    if (meta.get("test_input_user") != user or bool(meta.get("profile_handoff")) != flag or
            bool(meta.get("user_events")) != ue):
        reasons.append(f"runner recorded user {meta.get('test_input_user')} handoff {meta.get('profile_handoff')} "
                       f"user_events {meta.get('user_events')}")
    lines = m12.run_lines(RUNS / run)
    events = g79.g6p79_events(lines)
    for e, line in zip([e for e in events if e["event"] == "signin_request"],
                       [l for l in lines if "G6P79 handoff signin_request" in l]):
        if m := TITLE.search(line):
            e["title_user"], e["start_candidate"] = int(m[1], 16), int(m[2])
    ue_ev = ue_events(lines)
    if flag != any(e["event"] == "enabled" for e in events):
        reasons.append("handoff 'enabled' line does not match the flag")
    if ue != any(UE_ON in l for l in lines):
        reasons.append("user-events line does not match the switch")
    if not ue and ue_ev:
        reasons.append(f"user events off but {len(ue_ev)} G6P80 lines")
    if not any("M23 haptics policy=suppressed physical_pad_drivers=none" in l for l in lines):
        reasons.append("no M23 suppressed-haptics line")
    probes = g77.probes(run)
    reasons += g79.exclusive(probes)
    if ue:
        reasons += [f"delivery: {p}" for p in delivery(ue_ev, expected_presses(steps, user))]
        reasons += [f"exercised: {p}" for p in exercised(ue_ev, steps)]
    calls = g77.xam_calls(lines)
    return {"run": run, "user": user, "flag": flag, "user_events": ue, **facts, "events": events, "ue": ue_ev,
            "probes": probes, "xam": g77.summarize(calls), "reasons": reasons}


def requests(rec):
    return [e for e in rec["events"] if e["event"] == "signin_request"]


def committed(rec, label, user):
    return g79.committed(rec["probes"], label, user)


def owner_at(rec, label):
    users = g79.signed_in_users(rec["probes"].get(label))
    return users[0] if users and len(users) == 1 else None


def box_closed(rec, label):
    s = rec["probes"].get(label) or {}
    return s.get("signin_box_open") == 0


GUEST = ("signin_box_open", "signed_out_latch", "signin_ui_requested", "signin_awaiting", "system_ui_open",
         "save_gate_user", "active_pad", "profile_user", "pad_lock_mask", "signed_in_mask")


def guest_state(rec):
    """Per probe: the title's box / latch / request words and the commit state (read-only probe fields)."""
    return {k: {f: (v or {}).get(f) for f in GUEST} for k, v in rec["probes"].items()}



def judge(tag, scenario):
    runs = SCENARIOS[scenario]
    recs = {s: judge_run(tag, s, u, f, ue, steps) for s, u, f, ue, steps, _, _ in runs}
    checks, observed, limits = [], {}, []

    def check(label, ok):
        checks.append((label, bool(ok)))

    def limit(label):
        limits.append(label)

    def new_and_load(n, l, n_user, l_user, flag, profile):
        rn, rl = recs[n], recs[l]
        save, path = save_of(tag, profile)
        rn["save"] = save
        if flag and n_user:
            check(f"{n}: profile moved 0 -> {n_user} at the title's sign-in request (title user {n_user})",
                  any(e["outcome"] == "moved" and e["to"] == n_user and e.get("title_user") == n_user
                      for e in requests(rn)))
        if flag:
            check(f"{n}: owner {n_user} locked by a commit witness", g79.locked(rn["events"], n_user))
        check(f"{n}: the title committed user {n_user} (active pad, profile user, lock mask)",
              committed(rn, "after_start", n_user))
        check(f"{n}: content created for user {n_user}", g79.content_users(rn) == [f"user={n_user}"])
        check(f"{n}: one genuine save in the {XUID} namespace",
              save is not None and save["file"].startswith(f"{XUID}/5841123F/"))
        if flag and l_user:
            check(f"{l}: profile moved 0 -> {l_user} after relaunch", g79.moved(rl["events"], 0, l_user))
        check(f"{l}: the title committed user {l_user}", committed(rl, "after_start", l_user))
        evaluated = m12.evaluate_run(name(tag, l), save["level"].lower(), save["sha256"],
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
        check("a_r: flag off - user 1 refused at sign-in (XamShowSigninUI, no content, no selector)",
              r["xam"].get("XamShowSigninUI") and not r["xam"].get("XamContentCreateEx") and
              not r["xam"].get("XamShowDeviceSelectorUI"))
        check("a_r: flag off - no profile directory written", not (PROFILES / name(tag, "ar") / "user").exists())
        check("a_r: flag off - lock mask 0 after START", (r["probes"].get("after_start") or {}).get("pad_lock_mask") == 0)
    elif scenario == "E":
        r = recs["e"]
        check("e: flag off - pad 2 refused: the title's sign-in error box opened (scripted dialog)",
              any(e["kind"] == "dialog_open" for e in r["ue"]) and (r["probes"].get("refused") or {}).get("signin_box_open") == 1)
        check("e: 'Back' reached the box", any(e["kind"] == "dialog_answer" and e["button"] == 1 and not e["dropped"]
                                                 for e in r["ue"]) and (r["probes"].get("after_back") or {}).get("signin_box_button") == 1)
        ab = r["probes"].get("after_back") or {}
        observed["after_back"] = {"signin_box_open": ab.get("signin_box_open"), "signed_out_latch": ab.get("signed_out_latch")}
        observed["guest"] = guest_state(r)
        if ab.get("signin_box_open") != 0:  # E-566 r2: the flag-off baseline of the D3 / D6 box-flag observation
            limit(f"e: flag off - after 'Back' the title's box flag 828750C4 stays {ab.get('signin_box_open')} "
                  f"(latch 82836CC8 = {ab.get('signed_out_latch')}): title behaviour without the prototype")
        check("e: flag off - pad 1's START then commits user 0 in the same process", committed(r, "after_p1_late", 0))
        check("e: flag off - the profile never left user 0", all(owner_at(r, k) in (0, None) for k in r["probes"]))
    elif scenario == "B":
        new_and_load("b_n", "b_l", 1, 1, True, "b")
    elif scenario == "C1":
        new_and_load("c1_n", "c1_l", 0, 1, True, "c1")
        check("c1_n: pad 1 needs no handoff", not requests(recs["c1_n"]))
    elif scenario == "C2":
        new_and_load("c2_n", "c2_l", 1, 0, True, "c2")
        check("c2_l: pad 1 needs no handoff", not requests(recs["c2_l"]))
    elif scenario in ("D1", "D5"):
        r = recs[scenario.lower()]
        reqs = requests(r)
        check(f"{scenario}: first request: the title selected pad 2 and the profile moved 0 -> 1",
              bool(reqs) and reqs[0]["outcome"] == "moved" and reqs[0]["to"] == 1 and reqs[0].get("title_user") == 1)
        check(f"{scenario}: pad 1's START made the title show its sign-in error box (target behaviour)",
              any(e["kind"] == "dialog_open" for e in r["ue"]) and (r["probes"].get("box") or {}).get("signin_box_open") == 1)
        if scenario == "D1":
            check("D1: 'Sign In' -> the title requested sign-in again for pad 1, and the profile followed (1 -> 0)",
                  len(reqs) >= 2 and reqs[1]["outcome"] == "moved" and reqs[1]["from"] == 1 and reqs[1]["to"] == 0 and
                  reqs[1].get("title_user") == 0)
            check("D1: the title committed pad 1 (user 0) and the owner locked there",
                  g79.locked(r["events"], 0) and committed(r, "after_answer_late", 0))
        else:
            # E-566 r1: the failed commit had already set 828750C0, so the title requests sign-in again even after
            # "Back"; the profile follows pad 1 on that request (its START is unused) or on the retry.
            moved = [e for e in reqs[1:] if e["outcome"] == "moved" and e["from"] == 1 and e["to"] == 0 and
                     e.get("title_user") == 0]
            check("D5: after 'Back' / the retry the title requested sign-in for pad 1 and the profile followed (1 -> 0)",
                  bool(moved))
            check("D5: the title committed pad 1 (user 0) and the owner locked there",
                  g79.locked(r["events"], 0) and committed(r, "after_retry_late", 0))
            check("D5: one move per START: no request after pad 1's move moved the profile again",
                  sum(e["outcome"] == "moved" for e in reqs) == 2)
            observed["after_back_committed"] = (r["probes"].get("after_back") or {}).get("pad_lock_mask") == 1
        check(f"{scenario}: every request followed the title's selected user",
              all(e.get("title_user") == e["candidate"] for e in reqs))
        check(f"{scenario}: no START was refused for its age (no recency window)",
              not any(e["outcome"] == "refused_stale_start" for e in reqs))
        observed["guest"] = guest_state(r)
    elif scenario == "D2":
        r = recs["d2"]
        check("D2: pad 2 committed and locked", g79.locked(r["events"], 1) and committed(r, "after_start", 1))
        check("D2: pad 1's START was delivered to user 0 after the commit",
              any(e["kind"] == "delivered" and e["user"] == 0 for e in r["ue"]))
        check("D2: no move after the commit",
              not any(e["outcome"] == "moved" and e["to"] != 1 for e in requests(r)))
        s = r["probes"].get("after_second_start") or {}
        check("D2: after the second START the title still has user 1", s.get("profile_user") == 1 and s.get("pad_lock_mask") == 2)
    elif scenario in ("D3", "D6"):
        r = recs[scenario.lower()]
        reqs = requests(r)
        check(f"{scenario}: pad 2's START moved the profile 0 -> 1 (pending)",
              bool(reqs) and reqs[0]["outcome"] == "moved" and reqs[0]["to"] == 1)
        check(f"{scenario}: the unplug before the commit rolled it back to user 0 (rollback line, SIGNINCHANGED)",
              any(e["kind"] == "rollback" and e["user"] == 1 and e["owner"] == 0 for e in r["ue"]))
        if scenario == "D3":
            check("D3: the unplugged pad 2 was never committed (no lock on user 1)", not g79.locked(r["events"], 1))
        s = r["probes"].get("unplugged") or {}
        check(f"{scenario}: after the unplug the profile is on user 0 and nothing is committed",
              owner_at(r, "unplugged") == 0 and s.get("pad_lock_mask") == 0)
        # E-566 r1 (observed title behaviour, not a pass condition): the rollback's SIGNINCHANGED makes the title
        # open its sign-in error box and its debounced refresh set the signed-out latch 82836CC8; "Back" then leaves
        # 828750C4 set because its XN_SYS_UI = 0 arrives while the latch is set.
        ab = r["probes"].get("after_back") or {}
        check(f"{scenario}: the rollback opened the title's error box and 'Back' reached it",
              any(e["kind"] == "dialog_open" for e in r["ue"]) and ab.get("signin_box_button") == 1)
        observed["after_back"] = {"signin_box_open": ab.get("signin_box_open"),
                                  "signed_out_latch": ab.get("signed_out_latch")}
        if ab.get("signin_box_open") != 0:
            limit(f"{scenario}: after 'Back' the title's box flag 828750C4 stays {ab.get('signin_box_open')} "
                  f"(latch 82836CC8 = {ab.get('signed_out_latch')}): no guest-visible close")
        if scenario == "D3":
            check("D3: pad 1's START then commits user 0 in the same process",
                  committed(r, "after_p1_late", 0) and g79.locked(r["events"], 0))
        else:
            check("D6: the replugged pad 2's START was delivered to user 1",
                  any(e["kind"] == "delivered" and e["user"] == 1 for e in r["ue"]) and
                  (r["probes"].get("after_replug") or {}).get("active_pad") == 1)
            retry = reqs[1:]
            rp = r["probes"].get("after_replug_late") or {}
            observed["pad2_retry"] = {"requests": retry, "signin_ui_requested": rp.get("signin_ui_requested"),
                                      "signin_box_open": rp.get("signin_box_open"),
                                      "pad_lock_mask": rp.get("pad_lock_mask")}
            if committed(r, "after_replug_late", 1):
                check("D6: pad 2's retry committed user 1 after a fresh move", any(e["outcome"] == "moved" and
                                                                                 e["to"] == 1 for e in retry))
            else:
                state = ("pending: 828750C0 set, no sign-in request (828750C4 still set)"
                         if not retry and rp.get("signin_ui_requested") == 1 else f"requests {retry}")
                limit(f"D6: pad 2's retry after the replug did not complete: {state}")
                check("D6: while pad 2's retry is blocked nothing is committed and the profile stays on user 0",
                      rp.get("pad_lock_mask") == 0 and owner_at(r, "after_replug_late") == 0)
                check("D6: pad 1's START then commits user 0 in the same process (session recovery by pad 1)",
                      committed(r, "after_p1_late", 0) and g79.locked(r["events"], 0))
        observed["refused_requests"] = [e for e in reqs if e["outcome"].startswith("refused")]
        observed["guest"] = guest_state(r)
    elif scenario == "D6R":
        r = recs["d6r"]
        reqs = requests(r)
        check("D6R: pad 2's START moved the profile 0 -> 1 (pending)",
              bool(reqs) and reqs[0]["outcome"] == "moved" and reqs[0]["to"] == 1)
        check("D6R: the unplug before the commit rolled it back to user 0",
              any(e["kind"] == "rollback" and e["user"] == 1 and e["owner"] == 0 for e in r["ue"]) and
              owner_at(r, "unplugged") == 0)
        check("D6R: the replugged pad 2's START was delivered to user 1 while the box was open",
              any(e["kind"] == "delivered" and e["user"] == 1 for e in r["ue"]) and
              (r["probes"].get("box_after_start") or {}).get("signin_box_open") == 1)
        retry = reqs[1:]
        observed["retry_requests"] = retry
        observed["guest"] = guest_state(r)
        if committed(r, "after_answer_late", 1):
            check("D6R: 'Sign In' -> the title requested sign-in for pad 2, the profile moved again and user 1 committed",
                  any(e["outcome"] == "moved" and e["to"] == 1 for e in retry) and g79.locked(r["events"], 1))
        else:
            s = r["probes"].get("after_answer_late") or {}
            limit(f"D6R: recovery not reached: requests after the answer {[e['outcome'] for e in retry]}, "
                  f"box flag {s.get('signin_box_open')}, latch {s.get('signed_out_latch')}, "
                  f"request word {s.get('signin_ui_requested')}")
            check("D6R: without recovery nothing is committed and the profile stays on user 0",
                  s.get("pad_lock_mask") == 0 and owner_at(r, "after_answer_late") == 0)
    elif scenario == "D4":
        r = recs["d4"]
        check("D4: pad 2 committed and locked", g79.locked(r["events"], 1) and committed(r, "after_start", 1))
        check("D4: unplug and replug after the commit were applied to user 1",
              any(e["kind"] == "connect" and e["user"] == 1 and e["value"] == 0 for e in r["ue"]) and
              any(e["kind"] == "connect" and e["user"] == 1 and e["value"] == 1 for e in r["ue"]))
        check("D4: no rollback and no move after the commit", not any(e["kind"] == "rollback" for e in r["ue"]) and
              not any(e["outcome"] == "moved" and e["to"] != 1 for e in requests(r)))
        for label in ("unplugged", "replugged"):
            s = r["probes"].get(label) or {}
            check(f"D4: {label}: the title still has profile user 1, owner user 1",
                  s.get("profile_user") == 1 and owner_at(r, label) == 1)
    elif scenario == "D7":
        r = recs["d7"]
        check("D7: pad 1 committed directly (signed in already, no sign-in request)",
              not requests(r) and g79.locked(r["events"], 0) and committed(r, "after_two_late", 0))
        check("D7: pad 2's later START was delivered to user 1 and moved nothing",
              any(e["kind"] == "delivered" and e["user"] == 1 for e in r["ue"]) and owner_at(r, "after_two_late") == 0)
    for rec in recs.values():
        for reason in rec["reasons"]:
            check(f"{rec['run']}: {reason}", False)
    exes = {rec.get("executable_sha256") for rec in recs.values()}
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"g6p80_{tag}_{scenario}.json"
    out.write_text(json.dumps({"tag": tag, "scenario": scenario, "executables": sorted(map(str, exes)),
                               "checks": checks, "limitations": limits, "observed": observed, "runs": recs},
                              indent=2) + "\n", encoding="utf-8")
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {label}")
    for label in limits:
        print(f"  LIMIT {label}")
    passed = sum(ok for _, ok in checks)
    print(f"G6P80_SCENARIO {scenario} {'PASS' if passed == len(checks) else 'FAIL'} {passed}/{len(checks)} "
          f"limits={len(limits)} "
          f"exe={','.join(str(e)[:8] for e in exes)} record={out.relative_to(ROOT).as_posix()}")
    return passed == len(checks)


def save_of(tag, profile_suffix):
    profile = PROFILES / name(tag, profile_suffix)
    save, level = m12.one_valid_save(profile)
    if save is None:
        return None, None
    return {"file": save.relative_to(profile).as_posix(), "sha256": m12.sha256(save), "level": level,
            "bytes": save.stat().st_size}, save


def run_scenario(tag, scenario):
    for suffix, user, flag, ue, steps, seconds, profile in SCENARIOS[scenario]:
        run = name(tag, suffix)
        if (RUNS / run).exists():
            raise SystemExit(f"already exists: {RUNS / run}")
        path = WORK / "steps" / f"{run}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join([f"# G6-P80 {scenario} {suffix}: user {user}, handoff {'on' if flag else 'off'}, "
                                   f"user events {'on' if ue else 'off'}"] + steps) + "\n", encoding="ascii")
        command = [sys.executable, str(ROOT / "tools" / "m9_license_run.py"), run, str(path), "--license-mask", "1",
                   "--seconds", str(seconds), "--user-root", name(tag, profile), "--play",
                   "--input-user", str(user), "--profile-trace"]
        command += (["--profile-handoff"] if flag else []) + (["--user-events"] if ue else [])
        error = m12.run_driver(command, WORK / f"{run}.driver.log", seconds)
        print(f"{scenario} {run}: {'ok' if error is None else error}", flush=True)


def selftest():
    checks = []

    def check(label, ok):
        checks.append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {label}")

    lines = ["G6P80 event queued seq=1 user=1 value=10", "G6P80 event target seq=1 user=0 value=1",
             "G6P80 event queued seq=2 user=0 value=10", "G6P80 event delivered seq=1 user=1 value=10",
             "G6P80 event delivered seq=2 user=0 value=10", "G6P80 handoff rollback user=1 owner=0",
             "G6P80 dialog open buttons=2 active=0", "G6P80 dialog answer button=1",
             "G6P80 dialog answer button=0 dropped=no_box", "noise"]
    ev = ue_events(lines)
    check("events parsed", [e["kind"] for e in ev] == ["queued", "target", "queued", "delivered", "delivered",
                                                         "rollback", "dialog_open", "dialog_answer", "dialog_answer"])
    check("dropped answer parsed", ev[-1]["dropped"] == "no_box" and ev[-2]["dropped"] is None)
    steps = ["press 40", "axis 310 1", "press 40"]
    exp = expected_presses(steps, 1)
    check("expected presses follow the target", exp == [(1, 0x10, False), (0, 0x10, False)])
    check("delivery accepted", delivery(ev, exp) == [])
    check("a press to the wrong user rejected", delivery(ev, expected_presses(["press 40", "press 40"], 1)) != [])
    undelivered = [e for e in ev if not (e["kind"] == "delivered" and e["seq"] == 2)]
    check("an undelivered press rejected", any("never delivered" in p for p in delivery(undelivered, exp)))
    unplug = ["axis 321 1", "press 40"]
    exp2 = expected_presses(unplug, 1)
    check("a press for an unplugged user is expected dropped", exp2 == [(1, 0x10, True)])
    check("a missing drop rejected", delivery([], exp2) != [])
    check("a reported drop accepted", delivery([{"kind": "dropped", "seq": 3, "user": 1, "value": 0x10}], exp2) == [])
    check("scenarios name distinct runs", len({s for v in SCENARIOS.values() for s, *_ in v}) ==
          sum(len(v) for v in SCENARIOS.values()))
    check("flag-off baselines exist (A without user events, E with)",
          all(not f and not ue for _, _, f, ue, *_ in SCENARIOS["A"]) and
          all(not f and ue for _, _, f, ue, *_ in SCENARIOS["E"]))
    check("every D scenario runs with the flag and user events",
          all(f and ue for k, v in SCENARIOS.items() if k.startswith("D") for _, _, f, ue, *_ in v))
    check("title-user field parsed", TITLE.search("connected=1100 title_user=1 start_candidate=0").groups() == ("1", "0"))
    sched = ["axis 321 1", "axis 341 1", "axis 321 0", "axis 340 1"]
    check("scheduled answers and connects derived", expected_answers(sched) == [1, 0] and
          expected_connects(sched) == [(1, 0), (1, 1)])
    good = [{"kind": "connect", "seq": 1, "user": 1, "value": 0}, {"kind": "dialog_answer", "button": 1, "dropped": None},
            {"kind": "connect", "seq": 1, "user": 1, "value": 1}, {"kind": "dialog_answer", "button": 0, "dropped": None}]
    check("exercised schedule accepted", exercised(good, sched) == [])
    check("a dropped answer is not exercised", exercised(
        good[:3] + [{"kind": "dialog_answer", "button": 0, "dropped": "no_box"}], sched) != [])
    check("a missing replug is not exercised", exercised([e for e in good if e.get("value") != 1 or
                                                          e["kind"] != "connect"], sched) != [])
    check("D6 ends with a pad 1 START and D6R answers 'Sign In' after the replugged START",
          D6[-6:-4] == [*P1, "press 40"][:2] and D6R.index("axis 321 0") < D6R.index("axis 340 1"))
    print(f"G6P80_CHECK_SELFTEST {'PASS' if all(checks) else 'FAIL'} {sum(checks)}/{len(checks)}")
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

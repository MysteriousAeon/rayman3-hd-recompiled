#!/usr/bin/env python3
"""Judge the private delayed Combo close against an observe-mode trace.

    python tools/combo_delayed_check.py --run RUN --control NAME
        [--require-interruption | --observer-only]

Consumes only existing M17 traces, fixture layouts, and runtime logs. It writes
one compact delayed_summary.json beside RUN and never starts a game.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import combo_countdown_check as combo  # noqa: E402


BEGIN_RE = re.compile(
    r"ComboDelayed begin\s+now=(?P<now>-?\d+)\s+start=(?P<start>-?\d+)"
    r"\s+window=(?P<window>-?\d+)\s+remaining=(?P<remaining>-?\d+)"
    r"\s+duration=(?P<duration>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s+object=(?P<object>[0-9A-Fa-f]{8})\s+score=(?P<score>-?\d+)"
    r"\s+bonus_bits=(?P<bonus_bits>[0-9A-Fa-f]{8})"
)
WINDOW_MS = 2000
THRESHOLD_AGE = (1000, 1034)
MAX_EARLY_MS = 34
POSITION_TOLERANCE = 0.00002


def _safe_name(name):
    return bool(name) and name not in (".", "..") and re.fullmatch(r"[A-Za-z0-9_.-]+", name)


def _age(row):
    return row["engine_ms"] - row["start_ms"]


def _remaining(row):
    return row["window_ms"] - _age(row)


def _open(row):
    return row["hud_position"] == row["hud_open_position"]


def _check(checks, detail, result):
    if result is None:
        status = "INCOMPLETE"
    else:
        status = "PASS" if result else "FAIL"
    checks.append({"status": status, "detail": detail})


def _verdict(checks):
    statuses = {item["status"] for item in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "INCOMPLETE" in statuses:
        return "INCOMPLETE"
    return "PASS"


def _read_runtime_logs(run_path):
    paths = sorted(run_path.glob("runtime*.log"))
    return paths, "\n".join(
        path.read_text(encoding="utf-8-sig", errors="replace") for path in paths
    )


def _begin_events(log_text):
    begins = []
    for line in log_text.splitlines():
        match = BEGIN_RE.search(line)
        if not match:
            continue
        item = match.groupdict()
        item.update({
            "now_ms": int(item.pop("now")),
            "start_ms": int(item.pop("start")),
            "window_ms": int(item.pop("window")),
            "remaining_ms": int(item.pop("remaining")),
            "duration_s": float(item["duration"]),
            "object": int(item["object"], 16),
            "score": int(item["score"]),
            "bonus_bits": int(item["bonus_bits"], 16),
        })
        begins.append(item)
    return begins


def _refreshes(rows):
    """Active score refreshes specifically observed from a preceding close."""
    found = []
    for previous, current in zip(rows, rows[1:]):
        if (previous["hud_state"] != 3 or current["start_ms"] == previous["start_ms"]
                or current["score"] <= previous["score"] or current["pending_expiry"] != 1):
            continue
        old_remaining = previous["start_ms"] + previous["window_ms"] - current["engine_ms"]
        if previous["pending_expiry"] != 1 or old_remaining <= 0:
            continue
        found.append({
            "at_engine_ms": current["engine_ms"],
            "swap": current["swap"],
            "old_start_ms": previous["start_ms"],
            "new_start_ms": current["start_ms"],
            "window_ms": current["window_ms"],
            "old_remaining_ms": old_remaining,
            "score_before": previous["score"],
            "score_after": current["score"],
            "state_before": previous["hud_state"],
            "state_after": current["hud_state"],
            "position_after": current["hud_position"],
            "open_position": current["hud_open_position"],
            "digits_after": current["hud_digits"],
            "handles_before": previous["hud_handles"],
            "handles_after": current["hud_handles"],
        })
    return found


def _event_row(event, rows):
    return next((row for row in rows
                 if row["swap"] == event["swap"] and row["start_ms"] == event["new_start_ms"]), None)


def _first_reentry(summary, rows):
    payouts = summary.get("cashout_events", [])
    if not payouts:
        return None, None
    after = [event for event in summary.get("new_combos", [])
             if event["at_engine_ms"] > payouts[0]["at_engine_ms"]]
    if not after:
        return None, None
    return after[0], _event_row(after[0], rows)


def _cycle_for(begin, rows, refreshes):
    same_timer = [row for row in rows if row["start_ms"] == begin["start_ms"]
                  and row["window_ms"] == begin["window_ms"]]
    closing = [row for row in same_timer if row["hud_state"] == 3]
    first = next((row for row in closing if row["engine_ms"] >= begin["now_ms"]), None)
    positions = sorted({row["hud_position"] for row in closing})
    interrupt = next((event for event in refreshes
                      if event["old_start_ms"] == begin["start_ms"]
                      and (first is None or event["at_engine_ms"] >= first["engine_ms"])), None)
    after_close = None
    if closing and interrupt is None:
        last_close = closing[-1]
        after_close = next((row for row in same_timer if row["swap"] > last_close["swap"]
                            and row["hud_state"] != 3), None)
    return {
        "begin": begin,
        "first_sample": first,
        "first_sample_fraction": None,
        "closing_positions": positions,
        "interrupted_by_refresh": interrupt,
        "completion_sample": after_close,
    }


def _compact_row(row):
    if row is None:
        return None
    return {key: row[key] for key in (
        "swap", "engine_ms", "engine_delta_ms", "start_ms", "window_ms", "pending_expiry",
        "hud_state", "hud_duration_s", "hud_elapsed_s", "hud_position", "hud_open_position",
        "hud_closed_position", "hud_digits", "hud_handles", "native_delta_s")}


def _load_summary(name, expected):
    # Reuse the established cashout/refresh accounting and its M17-backed
    # read_run path. The legacy checker's own assertions remain untouched.
    return combo.summarize(name, expected, write=False)


def check(run_name, control_name, require_interruption=False, observer_only=False):
    run_path, rows = combo.read_run(run_name)
    control_path, control_rows = combo.read_run(control_name)
    candidate_summary = _load_summary(run_name, "observe")
    control_summary = _load_summary(control_name, "observe")
    log_paths, log_text = _read_runtime_logs(run_path)
    control_log_paths, control_log_text = _read_runtime_logs(control_path)
    begins = _begin_events(log_text)
    control_begins = _begin_events(control_log_text)
    refreshes = _refreshes(rows)
    checks = []

    candidate_fixture = json.loads((run_path / 'fixture.json').read_text(encoding='utf-8'))
    control_fixture = json.loads((control_path / 'fixture.json').read_text(encoding='utf-8'))
    _check(checks, "candidate explicitly requested private delayed-countdown or saved production On",
           candidate_fixture.get('mode') == 'delayed-countdown' or
           (candidate_fixture.get('mode') == 'off' and (candidate_fixture.get('preset') == 'hdplus' or
             (candidate_fixture.get('settings_file') and candidate_fixture.get('profile_combo_close') == 'delayed'))
            and 'ComboClose profile_mode=delayed' in log_text and 'ComboTest command' not in log_text))
    _check(checks, "control explicitly requested observe or saved production Off",
           control_fixture.get('mode') == 'observe' or
           (control_fixture.get('mode') == 'off' and (control_fixture.get('preset') == 'vanilla' or
             (control_fixture.get('settings_file') and control_fixture.get('profile_combo_close') == 'original'))
            and 'ComboClose profile_mode=original' in control_log_text
            and 'ComboTest command' not in control_log_text))

    _check(checks, "candidate and control are distinct trace runs", run_name != control_name)
    _check(checks, "candidate runtime log evidence is present", bool(log_paths))
    _check(checks, "control runtime log evidence is present", bool(control_log_paths))
    _check(checks, "candidate contains a delayed-close initialization",
           None if not log_paths else bool(begins))
    _check(checks, "observe control did not start delayed-close initialization",
           None if not control_log_paths else not control_begins)
    observe_check = next((item["pass"] for item in control_summary.get("checks", [])
                          if item["detail"] == "control did not select fixed-duration hook"), None)
    _check(checks, "control was summarized in observe mode", observe_check)

    candidate_payouts = candidate_summary.get("cashout_events", [])
    control_payouts = control_summary.get("cashout_events", [])
    candidate_first = candidate_payouts[0] if candidate_payouts else None
    control_first = control_payouts[0] if control_payouts else None
    _check(checks, "candidate has an observed nonzero payout", bool(candidate_first))
    _check(checks, "observe control has an observed nonzero payout", bool(control_first))
    if candidate_first is None or control_first is None:
        _check(checks, "first payout comparison has both runs", None)
        _check(checks, "first payout window is the actual pending 2000 ms window", None)
        _check(checks, "first nonzero score/bonus tuple matches observe control", None)
        _check(checks, "first payout is a single payment at the original deadline crossing", None)
    else:
        _check(checks, "first payout window is the actual pending 2000 ms window",
               candidate_first["window_ms"] == WINDOW_MS and control_first["window_ms"] == WINDOW_MS)
        payout_tuple = (candidate_first["score_before"], candidate_first["score_after"],
                        candidate_first["bonus_before"])
        control_tuple = (control_first["score_before"], control_first["score_after"],
                         control_first["bonus_before"])
        _check(checks, "first nonzero score/bonus tuple matches observe control",
               payout_tuple == control_tuple)
        same_start_payments = [item for item in candidate_payouts
                               if item["start_ms"] == candidate_first["start_ms"]]
        _check(checks, "first timer start receives exactly one nonzero payment",
               len(same_start_payments) == 1)
        _check(checks, "every observed payout adds exactly its unpaid bonus",
               all(item["score_after"] - item["score_before"] == item["bonus_before"]
                   for item in candidate_payouts))
        _check(checks, "no timer start receives a repeated nonzero payment",
               len({item["start_ms"] for item in candidate_payouts}) == len(candidate_payouts))
        _check(checks, "every observed candidate payout is at its first deadline crossing",
               all(item["first_deadline_crossing"] for item in candidate_payouts))
        _check(checks, "candidate payout occurs on the first original-deadline crossing",
               candidate_first["first_deadline_crossing"])
        _check(checks, "control payout occurs on the first original-deadline crossing",
               control_first["first_deadline_crossing"])

    # Pending frames before the one-second threshold must remain fully open.
    prethreshold = [row for row in rows if row["pending_expiry"] == 1
                    and 0 <= _age(row) < 1000]
    _check(checks, "prethreshold pending frames are captured", bool(prethreshold))
    _check(checks, "every prethreshold pending frame remains state 2 at exact open position",
           None if not prethreshold else all(row["hud_state"] == 2 and _open(row)
                                             for row in prethreshold))

    # Each observed timer that reaches the threshold must have its own hook log.
    threshold_starts = sorted({(row["start_ms"], row["window_ms"]) for row in rows
                               if row["pending_expiry"] == 1 and _age(row) >= 1000
                               and _remaining(row) > 0})
    begin_starts = [(event["start_ms"], event["window_ms"]) for event in begins]
    _check(checks, "each pending timer reaching one second has a delayed initialization log",
           None if not threshold_starts or not log_paths
           else all(start in begin_starts for start in threshold_starts))
    _check(checks, "each timer has at most one delayed initialization",
           len(begin_starts) == len(set(begin_starts)))

    cycles = [_cycle_for(event, rows, refreshes) for event in begins]
    timing = {"threshold_ages_ms": [], "remaining_ms": [], "durations_s": [],
              "firstsample_fractions": [], "completion_lead_ms": []}
    for index, cycle in enumerate(cycles, start=1):
        begin = cycle["begin"]
        log_age = begin["now_ms"] - begin["start_ms"]
        log_remaining_math = begin["window_ms"] - log_age
        _check(checks, f"close {index} uses the actual pending 2000 ms window",
               begin["window_ms"] == WINDOW_MS)
        _check(checks, f"close {index} begins with 1..1000 ms remaining",
               1 <= begin["remaining_ms"] <= 1000)
        _check(checks, f"close {index} begins at observed age 1000..1034 ms",
               THRESHOLD_AGE[0] <= log_age <= THRESHOLD_AGE[1])
        _check(checks, f"close {index} remaining time matches its logged start/window",
               begin["remaining_ms"] == log_remaining_math)
        duration_matches = math.isfinite(begin["duration_s"]) and abs(
            begin["duration_s"] - begin["remaining_ms"] / 1000.0) <= 0.0000011
        _check(checks, f"close {index} native duration equals remaining gameplay time",
               duration_matches)

        first = cycle["first_sample"]
        if first is None:
            _check(checks, f"close {index} has a measured first state-3 sample", None)
            _check(checks, f"close {index} reaches its completion sample", None)
            _check(checks, f"close {index} has at least two observed positions", None)
            continue
        first_age = _age(first)
        timing["threshold_ages_ms"].append(first_age)
        timing["remaining_ms"].append(begin["remaining_ms"])
        timing["durations_s"].append(begin["duration_s"])
        _check(checks, f"close {index} sampled state-3 start is at age 1000..1034 ms",
               THRESHOLD_AGE[0] <= first_age <= THRESHOLD_AGE[1])
        _check(checks, f"close {index} sampled state 3 while its deadline was pending",
               first["pending_expiry"] == 1)
        _check(checks, f"close {index} sampled native duration matches logged remainder",
               first["hud_duration_s"] == round(begin["duration_s"], 5))
        measured_delta = first["native_delta_s"]
        _check(checks, f"close {index} first sample has a measured native delta",
               measured_delta is not None and math.isfinite(measured_delta) and measured_delta > 0)
        if measured_delta is None or not math.isfinite(measured_delta) or measured_delta <= 0:
            _check(checks, f"close {index} first-sample fraction matches native interpolation", None)
            timing["firstsample_fractions"].append(None)
        else:
            delta_fraction = first["hud_elapsed_s"] / first["hud_duration_s"] \
                if first["hud_duration_s"] > 0 else None
            cycle["first_sample_fraction"] = delta_fraction
            timing["firstsample_fractions"].append(delta_fraction)
            _check(checks, f"close {index} elapsed starts with one measured native update",
                   first["hud_elapsed_s"] == round(measured_delta, 5))
            _check(checks, f"close {index} measured first-sample fraction matches native interpolation",
                   delta_fraction is not None and delta_fraction > 0 and
                   abs(first["hud_position"] - (first["hud_open_position"] * (1 - delta_fraction)
                                                + first["hud_closed_position"] * delta_fraction))
                   <= POSITION_TOLERANCE)
        _check(checks, f"close {index} shows at least two distinct closing positions",
               len(cycle["closing_positions"]) >= 2)

        interrupt = cycle["interrupted_by_refresh"]
        if interrupt is None:
            completed = cycle["completion_sample"]
            if completed is None:
                _check(checks, f"close {index} reaches a completion sample before expiry", None)
            else:
                lead_ms = begin["start_ms"] + begin["window_ms"] - completed["engine_ms"]
                timing["completion_lead_ms"].append(lead_ms)
                # Float accumulation can finish on the expiry swap itself.
                # Require the actual native endpoint, not merely expiry's hide.
                last_closing = next(row for row in reversed(rows)
                                    if row['start_ms'] == begin['start_ms'] and row['hud_state'] == 3
                                    and row['swap'] < completed['swap'])
                reaches_end = (completed['native_delta_s'] is not None and
                               last_closing['hud_elapsed_s'] + completed['native_delta_s'] >=
                               begin['duration_s'] - 0.00001)
                _check(checks, f"close {index} reaches the native closed endpoint",
                       reaches_end and completed['hud_position'] == completed['hud_closed_position'] and
                       completed['hud_elapsed_s'] == round(begin['duration_s'], 5))
                _check(checks, f"close {index} completes at expiry or within 34 ms before it",
                       completed["hud_state"] == 0 and 0 <= lead_ms <= MAX_EARLY_MS and
                       completed['pending_expiry'] == (1 if lead_ms > 0 else 0))
        else:
            cycle["interrupted_by_refresh"] = {
                "at_engine_ms": interrupt["at_engine_ms"],
                "new_start_ms": interrupt["new_start_ms"],
                "old_remaining_ms": interrupt["old_remaining_ms"],
            }
            _check(checks, f"close {index} is explicitly cancelled by an active score refresh", True)

    # A scoring call received while the native HUD is closing must reopen that
    # same instance immediately. Its replacement timer starts the delayed close
    # around one second into the refreshed deadline, never on the next swap.
    if require_interruption:
        _check(checks, "at least one active refresh interrupted state 3", bool(refreshes))
    elif not refreshes:
        checks.append({"status": "NOT_REQUESTED", "detail": "no active refresh was required"})
    for index, event in enumerate(refreshes, start=1):
        row = _event_row({"swap": event["swap"], "new_start_ms": event["new_start_ms"]}, rows)
        _check(checks, f"refresh {index} same-frame scoring open is state 2 at exact open position",
               row is not None and row["hud_state"] == 2 and _open(row))
        _check(checks, f"refresh {index} retains the existing HUD handles",
               row is not None and row["hud_handles"] == event["handles_before"])
        control_open = next((r for previous, r in zip(control_rows, control_rows[1:])
                             if r['start_ms'] != previous['start_ms'] and
                             r['score'] == event['score_after'] and r['pending_expiry'] == 1), None)
        # Active interruption also restarts the guest-owned damped bounce at
        # object+54 (821A0098..C0 -> HUD8288D648). Unlike a fresh re-entry,
        # its phase differs from the uninterrupted control. Judge that native
        # recurrence explicitly; do not silently label all23 words identical.
        _check(checks, f"refresh {index} digits and object words match except time words and native bounce",
               row is not None and control_open is not None and
               row['hud_digits'] == control_open['hud_digits'] and
               bool(row['combo_object_words'] and control_open['combo_object_words']) and
               all(row['combo_object_words'][i] == control_open['combo_object_words'][i]
                   for i in range(23) if i not in (1, 10, 21)))
        following = next((r for r in rows if row and r['swap'] == row['swap'] + 1), None)
        def bounce(r):
            import struct
            return struct.unpack('>f', struct.pack('>I', r['combo_object_words'][21]))[0]
        _check(checks, f"refresh {index} native bounce restarts at1 and follows its measured -0.75 recurrence",
               row is not None and following is not None and bounce(row) == 1.0 and
               abs(bounce(following) + 0.75 * bounce(row)) < 0.000001)
        matching = next((begin for begin in begins if begin["start_ms"] == event["new_start_ms"]), None)
        if matching is None:
            _check(checks, f"refresh {index} starts its delayed close from the refreshed deadline", None)
        else:
            refreshed_age = matching["now_ms"] - event["new_start_ms"]
            _check(checks, f"refresh {index} next delayed start belongs to the refreshed timer after one second",
                   matching["window_ms"] == event["window_ms"]
                   and THRESHOLD_AGE[0] <= refreshed_age <= THRESHOLD_AGE[1]
                   and matching["remaining_ms"] == matching["window_ms"] - refreshed_age)

    # Re-entry after the first payout is compared with the observe run; the
    # actual score tuple is intentionally only compared at the first payout.
    candidate_event, candidate_reentry = _first_reentry(candidate_summary, rows)
    control_event, control_reentry = _first_reentry(control_summary, control_rows)
    reentry = None
    if observer_only:
        _check(checks, "observer scope: both fixtures explicitly omit the later pickup walk",
               candidate_fixture.get('first_only') is True and control_fixture.get('first_only') is True)
        _check(checks, "observer scope: no post-payout re-entry was manufactured",
               candidate_event is None and control_event is None)
    elif candidate_event is None or control_event is None or candidate_reentry is None or control_reentry is None:
        _check(checks, "both traces contain a sampled post-payout Combo re-entry", None)
    else:
        c_obj = candidate_reentry["combo_object_words"]
        o_obj = control_reentry["combo_object_words"]
        reentry = {
            "candidate": _compact_row(candidate_reentry),
            "control": _compact_row(control_reentry),
            "candidate_class": c_obj[0] if c_obj else None,
            "candidate_material": c_obj[6] if c_obj else None,
            "control_class": o_obj[0] if o_obj else None,
            "control_material": o_obj[6] if o_obj else None,
        }
        _check(checks, "re-entry HUD digits match observe control",
               candidate_reentry["hud_digits"] == control_reentry["hud_digits"] == [0, 0, 0, 0, 0])
        _check(checks, "re-entry HUD handles match observe control",
               candidate_reentry["hud_handles"] == control_reentry["hud_handles"])
        _check(checks, "re-entry Combo class and material match observe control",
               bool(c_obj and o_obj and len(c_obj) > 6 and len(o_obj) > 6)
               and c_obj[0] == o_obj[0] and c_obj[6] == o_obj[6])
        _check(checks, "re-entry returns both HUDs to their exact open position",
               _open(candidate_reentry) and _open(control_reentry))
        _check(checks, "all23 re-entry object words match except established two time words",
               bool(c_obj and o_obj) and all(c_obj[i] == o_obj[i] for i in range(23) if i not in (1, 10)))

    result = {
        "run": run_name,
        "control": control_name,
        "mode": "delayed-countdown",
        "scope": "observer-first-close" if observer_only else "expiry-refresh-reentry",
        "hook": "8219F2D8",
        "verdict": _verdict(checks),
        "cycles": [{
            "now_ms": cycle["begin"]["now_ms"],
            "start_ms": cycle["begin"]["start_ms"],
            "window_ms": cycle["begin"]["window_ms"],
            "remaining_ms": cycle["begin"]["remaining_ms"],
            "duration_s": cycle["begin"]["duration_s"],
            "object": cycle["begin"]["object"],
            "score": cycle["begin"]["score"],
            "bonus_bits": cycle["begin"]["bonus_bits"],
            "first_sample": _compact_row(cycle["first_sample"]),
            "first_sample_fraction": cycle["first_sample_fraction"],
            "closing_positions": cycle["closing_positions"],
            "interrupted_by_refresh": cycle["interrupted_by_refresh"],
            "completion_sample": _compact_row(cycle["completion_sample"]),
        } for cycle in cycles],
        "timing": timing,
        "payout": {
            "candidate_first": candidate_first,
            "control_first": control_first,
            "candidate_count": len(candidate_payouts),
            "control_count": len(control_payouts),
        },
        "active_refreshes": refreshes,
        "reentry": reentry,
        "failedchecks": [item["detail"] for item in checks if item["status"] == "FAIL"],
        "incompletechecks": [item["detail"] for item in checks if item["status"] == "INCOMPLETE"],
        "checks": checks,
    }
    return run_path, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="existing private m6_runs name")
    parser.add_argument("--control", required=True, help="existing observe-mode control run name")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--require-interruption", action="store_true",
                        help="require at least one scoring refresh while state 3 is active")
    scope.add_argument('--observer-only', action='store_true',
                       help='require two explicit first-only fixtures; judge first close, not later re-entry')
    args = parser.parse_args()
    if not _safe_name(args.run) or not _safe_name(args.control):
        parser.error("run names must be simple private run directory names")
    try:
        run_path, result = check(args.run, args.control, args.require_interruption, args.observer_only)
        output = run_path / "delayed_summary.json"
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"COMBO_DELAYED_{result['verdict']} run={args.run} control={args.control} "
              f"cycles={len(result['cycles'])} refreshes={len(result['active_refreshes'])} "
              f"payouts={result['payout']['candidate_count']}")
        for detail in result["failedchecks"]:
            print(f"FAIL {detail}")
        for detail in result["incompletechecks"]:
            print(f"INCOMPLETE {detail}")
        print(f"SUMMARY {output}")
        return 0 if result["verdict"] == "PASS" else (2 if result["verdict"] == "INCOMPLETE" else 1)
    except (OSError, ValueError, KeyError, IndexError, StopIteration, TypeError) as exc:
        print(f"COMBO_DELAYED_INCOMPLETE {exc}", file=sys.stderr)
        run_path = combo.RUNS / args.run
        if run_path.is_dir():
            result = {
                "run": args.run,
                "control": args.control,
                "mode": "delayed-countdown",
                "hook": "8219F2D8",
                "verdict": "INCOMPLETE",
                "cycles": [],
                "timing": {},
                "payout": {},
                "failedchecks": [],
                "incompletechecks": [str(exc)],
            }
            output = run_path / "delayed_summary.json"
            try:
                output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                print(f"SUMMARY {output}")
            except OSError:
                pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

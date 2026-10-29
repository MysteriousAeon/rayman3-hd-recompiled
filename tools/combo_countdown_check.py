#!/usr/bin/env python3
"""Summarize E-305 target combo countdown and HUD timing from an M17 trace.

    python tools/combo_countdown_check.py --run RUN [--control RUN]
        [--expect observe|timed|countdown]

Reads only private trace, layout, and runtime-log evidence. Writes one private
summary beside the run. It does not start or attach to a game.
"""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m17_frame_trace as ft  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "private/work/m6_runs"
TRACE_ROOT = ROOT / "private/work"
# VERIFIED timer provider 82257AE8 reads the same engine millisecond word
# watched by M17 at 82C0628C, so expiry calculations below use timer_fields().
HUD = 0x8288D528
DSG = 0x40CDD5BC


def u32(block, off):
    return struct.unpack_from(">I", block, off)[0]


def f32(block, off):
    return struct.unpack_from(">f", block, off)[0]


def i32(block, off):
    return struct.unpack_from(">i", block, off)[0]


def read_run(name):
    run = RUNS / name
    layout_path = run / "layout.json"
    trace_path = TRACE_ROOT / f"{name}.trace"
    if not layout_path.is_file() or not trace_path.is_file():
        raise ValueError(f"{name}: needs layout.json and private/work/{name}.trace")
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    base, offsets = int(layout["dsg"], 16), layout["vars"]
    if base != DSG or max(offsets) >= 325:
        raise ValueError(f"{name}: fixture designer layout differs from E-304")
    frames = []
    for swap, host, guest, ranges in ft.frames(trace_path):
        timer = ft.timer_fields(ranges)
        d, h, vis = ranges.get(base), ranges.get(HUD), ranges.get(0x82837E9C)
        if not timer or not d or len(d) < 325 or not h or len(h) < 0x134 or not vis or len(vis) < 8:
            continue
        def ivar(n):
            return i32(d, offsets[n])
        def fvar(n):
            return f32(d, offsets[n])
        state = u32(h, 0xF0)
        row = {
            "swap": swap,
            "engine_ms": timer["total_ms"],
            "engine_delta_ms": timer["delta_ms"],
            "score": ivar(36),
            "unpaid_bonus": round(fvar(24), 4),
            "window_ms": ivar(25),
            "start_ms": ivar(26),
            "pending_expiry": d[offsets[29]],
            "remaining_ms_from_start": ivar(25) - (timer["total_ms"] - ivar(26)),
            "hud_state": state,
            "hud_duration_s": round(f32(h, 0x84), 5),
            "hud_reciprocal": round(f32(h, 0x88), 6),
            "hud_elapsed_s": round(f32(h, 0xEC), 5),
            # E-304 identified the row's vertical interpolation operand as
            # guest 8288D53C (HUD base +0x14), written by native 8219F368.
            "hud_position": round(f32(h, 0x14), 5),
            "native_delta_s": f32(ranges[0x8288B414], 0) if 0x8288B414 in ranges else None,
            "hud_open_position": round(f32(h, 0x0C), 5),
            "hud_closed_position": round(f32(h, 0x04), 5),
            "hud_digits": [u32(h, 0x48 + 4 * i) for i in range(5)],
            "hud_visible": list(struct.unpack_from(">II", vis, 0)),
            "hud_handles": [u32(h, 0x12C), u32(h, 0x130)],
            "combo_object_words": list(struct.unpack_from('>23I', ranges[0x828A3E28], 0x70))
                if len(ranges.get(0x828A3E28, b'')) >= 0xCC else None,
        }
        frames.append(row)
    if not frames:
        raise ValueError(f"{name}: no complete fixture/HUD M17 frames")
    return run, frames


def events(rows):
    """Compact timeline: all state changes plus every elapsed sample during a close."""
    result = []
    last = None
    for r in rows:
        # Keep timer refreshes, event/scoring changes, state/duration transitions,
        # and elapsed/position progression during state 3.
        signature = tuple(r[k] for k in (
            "window_ms", "start_ms", "pending_expiry", "score", "unpaid_bonus",
            "hud_state", "hud_duration_s", "hud_elapsed_s", "hud_position",
            "hud_digits", "hud_visible", "hud_handles"))
        if signature != last:
            result.append(r)
            last = signature
    return result


def summarize(name, expect, *, write=True):
    run, rows = read_run(name)
    timeline = events(rows)
    positive = [r for r in rows if r["unpaid_bonus"] > 0]
    payouts = []
    for prev, cur in zip(rows, rows[1:]):
        if prev["unpaid_bonus"] > 0 and cur["unpaid_bonus"] == 0 and cur["score"] > prev["score"]:
            payouts.append({"at_engine_ms": cur["engine_ms"], "score_before": prev["score"],
                            "score_after": cur["score"], "bonus_before": prev["unpaid_bonus"],
                            "window_ms": cur["window_ms"], "start_ms": cur["start_ms"],
                            "lifetime_ms": cur["engine_ms"] - cur["start_ms"],
                            "first_deadline_crossing": prev["engine_ms"] - cur["start_ms"] < cur["window_ms"] <= cur["engine_ms"] - cur["start_ms"],
                            "pending_expiry": cur["pending_expiry"]})
    refreshes, new_combos = [], []
    for a, b in zip(rows, rows[1:]):
        changed = b["start_ms"] != a["start_ms"] and b["window_ms"] > 0 and b["pending_expiry"] == 1
        if not changed or b["score"] <= a["score"]:
            continue
        old_remaining = a["start_ms"] + a["window_ms"] - b["engine_ms"]
        event = {"at_engine_ms": b["engine_ms"], "swap": b["swap"], "old_start_ms": a["start_ms"],
                 "new_start_ms": b["start_ms"], "old_window_ms": a["window_ms"],
                 "new_window_ms": b["window_ms"], "old_remaining_ms": old_remaining,
                 "score_before": a["score"], "score_after": b["score"],
                 "pending_before": a["pending_expiry"], "hud_state_before": a["hud_state"],
                 "hud_state_after": b["hud_state"], "hud_elapsed_after_s": b["hud_elapsed_s"],
                 "hud_duration_after_s": b["hud_duration_s"], "hud_position_after": b["hud_position"],
                 "hud_visible_after": b["hud_visible"], "hud_digits_after": b["hud_digits"],
                 "hud_handles_after": b["hud_handles"], "engine_delta_ms": b["engine_delta_ms"]}
        # A refresh is only a new score inside the still-live combo. An event
        # after expiry starts a new combo and must be assessed separately.
        if a["pending_expiry"] == 1 and old_remaining > 0:
            refreshes.append(event)
        else:
            new_combos.append(event)
    state3 = [r for r in rows if r["hud_state"] == 3]
    movement = sorted({r["hud_position"] for r in state3})
    result = {
        "run": name,
        "trace_frames": len(rows),
        "observed_windows_ms": sorted({r["window_ms"] for r in rows if 0 < r["window_ms"] <= 60000}),
        "first_nonzero": positive[0] if positive else None,
        "timer_refreshes": refreshes,
        "new_combos": new_combos,
        "cashout_events": payouts,
        "hud_state3_first": state3[0] if state3 else None,
        "hud_state3_last": state3[-1] if state3 else None,
        "hud_state3_distinct_positions": movement,
        "hud_timeline": [r for r in timeline if r["hud_state"] == 3 or r["pending_expiry"] or
                          r["unpaid_bonus"] > 0 or r["hud_visible"] == [1, 1]],
        "requested_mode": expect,
    }
    log_paths = sorted(run.glob("runtime*.log"))
    result["combo_hook_log"] = "\n".join(p.read_text(encoding="utf-8-sig", errors="replace") for p in log_paths)
    checks = []
    checks.append((bool(positive), "actual nonzero combo bonus observed"))
    checks.append((bool(payouts), "at least one observed nonzero cashout"))
    checks.append((bool(payouts) and all(p['score_after'] - p['score_before'] == p['bonus_before'] for p in payouts),
                   "each observed payout adds exactly its unpaid bonus"))
    duplicate_start = len([p["start_ms"] for p in payouts]) != len({p["start_ms"] for p in payouts})
    checks.append((not duplicate_start, "no repeated nonzero payment for the same timer start"))
    if expect == "countdown":
        checks.append((bool(re.search(r"ComboCountdown begin", result["combo_hook_log"])),
                       "private countdown initialization executed"))
        checks.append((bool(payouts) and any(r["pending_expiry"] == 1 and
                       r["engine_ms"] < payouts[0]["at_engine_ms"] for r in state3),
                       "native HUD entered closing state before cashout"))
        checks.append((len(movement) >= 2, "native HUD position progressed while closing"))
        checks.append((bool(refreshes), "a scoring event refreshed an active timer before its old deadline"))
        checks.append((all(r["old_remaining_ms"] > 0 for r in refreshes),
                       "active timer refreshes occurred before the old deadline"))
        checks.append((all(p["first_deadline_crossing"] and p["pending_expiry"] == 0
                           for p in payouts),
                       "cashout occurs on the first sampled crossing of its unmodified deadline"))
        def restart_check(row, label):
            # E-305 execution: the native HUD update precedes actor scoring.
            # Open is state2 in the scoring swap; initialization is the next
            # swap. If ordering changes, state3 in the event swap is also
            # required to have a fresh first-step interpolation, not old elapsed.
            if row['hud_state'] == 2:
                checks.append((row['hud_position'] == row['hud_open_position'],
                               label + ': original open restores the exact position'))
                step = next((x for x in rows if x['swap'] == row['swap'] + 1), None)
            else:
                step = row
            valid = step is not None and step['start_ms'] == row['start_ms'] and step['hud_state'] == 3
            checks.append((valid, label + ': countdown begins in the event swap or exactly next swap'))
            if not valid:
                return
            checks.append((step['hud_visible'] == [1, 1] and step['hud_handles'] == row['hud_handles'] and
                           step['hud_digits'] == row['hud_digits'], label + ': restart preserves visible digits and handles'))
            checks.append((step['native_delta_s'] is not None and
                           step['hud_elapsed_s'] == round(step['native_delta_s'], 5),
                           label + ': elapsed restarts at one measured native update'))
            remaining = step['window_ms'] - (step['engine_ms'] - step['start_ms'])
            checks.append((step['hud_duration_s'] == round(remaining / 1000.0, 5),
                           label + ': duration equals actual remaining gameplay time'))
            fraction = step['hud_elapsed_s'] / step['hud_duration_s']
            expected_position = step['hud_open_position'] * (1-fraction) + step['hud_closed_position'] * fraction
            checks.append((abs(step['hud_position'] - expected_position) <= 0.00002,
                           label + ': position follows the native first-step interpolation'))
        # New-combo starts are reported separately; they are not timer refreshes.
        # At 8219F2D8 the native open/reset path may be followed by state3 in the
        # same sampled frame, so check the same swap and native elapsed increment.
        for r in refreshes:
            after = next((x for x in rows if x["start_ms"] == r["new_start_ms"] and
                          x["swap"] == r["swap"] and x["engine_ms"] == r["at_engine_ms"] and
                          x["hud_state"] in (2, 3) and x["hud_visible"] == [1, 1]), None)
            checks.append((after is not None, f"refresh at {r['at_engine_ms']} ms restores Combo HUD in the same sampled frame"))
            if after:
                before = next(x for x in rows if x['swap'] == r['swap'] - 1)
                checks.append((all(after["hud_handles"]) and after["hud_handles"] == before["hud_handles"],
                               f"refresh at {r['at_engine_ms']} ms retains the same HUD handles"))
                restart_check(after, f"refresh at {r['at_engine_ms']} ms")
        for event in new_combos:
            row = next((x for x in rows if x["swap"] == event["swap"] and x["start_ms"] == event["new_start_ms"]), None)
            event["hud_same_frame"] = row
        result["new_combo_reentries"] = new_combos
        reentries = [x for x in new_combos if payouts and x['at_engine_ms'] > payouts[0]['at_engine_ms']]
        checks.append((bool(reentries), 'a later actual scoring event starts a new combo'))
        for event in reentries:
            row = event['hud_same_frame']
            checks.append((row['hud_visible'] == [1, 1] and row['hud_state'] in (2, 3) and
                           row['hud_digits'] == [0, 0, 0, 0, 0] and
                           row['hud_handles'] == positive[0]['hud_handles'],
                           f"new combo at {event['at_engine_ms']} ms clears digits and restores the same visible HUD"))
            restart_check(row, f"new combo at {event['at_engine_ms']} ms")
    if expect == "timed":
        checks.append((bool(state3), "native six-second close state observed"))
        checks.append((bool(re.search(r"selected=true", result["combo_hook_log"])),
                       "fixed-duration hook selection recorded"))
    if expect == "observe":
        checks.append((not re.search(r"selected=true", result["combo_hook_log"]),
                       "control did not select fixed-duration hook"))
    result["checks"] = [{"pass": bool(ok), "detail": detail} for ok, detail in checks]
    result["verdict"] = "PASS" if checks and all(ok for ok, _ in checks) else "FAIL_OR_INCOMPLETE"
    result.pop("combo_hook_log")
    out = run / "countdown_summary.json"
    if write:
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"COMBO_COUNTDOWN_{result['verdict']} run={name} frames={len(rows)} "
          f"windows={result['observed_windows_ms']} refreshes={len(refreshes)} cashouts={len(payouts)} "
          f"state3={len(state3)} positions={len(movement)}")
    for item in result["checks"]:
        print(f"{'PASS' if item['pass'] else 'FAIL'} {item['detail']}")
    if write:
        print(f"SUMMARY {out}")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="existing private m6_runs name")
    ap.add_argument("--control", help="optional existing control run; summarize beside requested run")
    ap.add_argument("--expect", choices=("observe", "timed", "countdown"), default="observe")
    args = ap.parse_args()
    try:
        result = summarize(args.run, args.expect)
        if args.control:
            _, control_rows = read_run(args.control)
            control_result = summarize(args.control, "observe")
            result["control"] = {"run": args.control, "cashout_events": control_result["cashout_events"],
                                  "observed_windows_ms": control_result["observed_windows_ms"]}
            # Compare the first actual nonzero payout only; later pickups can
            # differ between input replays and are intentionally not whole-run gates.
            if result["cashout_events"] and control_result["cashout_events"]:
                active, baseline = result["cashout_events"][0], control_result["cashout_events"][0]
                tuple_equal = (active["score_before"], active["score_after"], active["bonus_before"]) == \
                              (baseline["score_before"], baseline["score_after"], baseline["bonus_before"])
                time_equal = active["first_deadline_crossing"] and baseline["first_deadline_crossing"]
                window_equal = active["window_ms"] == baseline["window_ms"]
                result["differential_first_cashout"] = {"prototype": active, "control": baseline,
                    "score_and_bonus_match": tuple_equal, "both_cashout_at_first_deadline_crossing": time_equal,
                    "lifetime_difference_ms": active["lifetime_ms"] - baseline["lifetime_ms"],
                    "window_matches": window_equal}
                result["checks"].extend([
                    {"pass": tuple_equal, "detail": "first score before/after and unpaid bonus match control"},
                    {"pass": time_equal, "detail": "both first cashouts occur on their original deadline-crossing frame"},
                    {"pass": window_equal, "detail": "first combo configured window matches control"},
                ])
                def first_reentry(data):
                    paid_ms = data['cashout_events'][0]['at_engine_ms']
                    event = next(x for x in data['new_combos'] if x['at_engine_ms'] > paid_ms)
                    _, event_rows = read_run(data['run'])
                    return next(x for x in event_rows if x['swap'] == event['swap'])
                arow, brow = first_reentry(result), first_reentry(control_result)
                aobj, bobj = arow['combo_object_words'], brow['combo_object_words']
                result['checks'].extend([
                    {'pass': bool(aobj and bobj) and aobj[0] == bobj[0] == 0x8200FE2C and
                        aobj[6] == bobj[6] == 0x40CB14F4 and aobj[22] == bobj[22] == 1,
                     'detail': 'exact reentry swap retains original Combo class/material/selector'},
                    {'pass': bool(aobj and bobj) and all(aobj[i] == bobj[i] for i in range(23) if i not in (1, 10)),
                     'detail': 'all23 reentry object words match control except the established two time words'},
                    {'pass': arow['hud_position'] == brow['hud_position'] == arow['hud_open_position'],
                     'detail': 'reentry restores exact original open position'},
                ])
                result["verdict"] = "PASS" if all(c["pass"] for c in result["checks"]) else "FAIL_OR_INCOMPLETE"
            else:
                result["checks"].append({"pass": False, "detail": "both runs need a first nonzero cashout for differential comparison"})
                result["verdict"] = "FAIL_OR_INCOMPLETE"
            (RUNS / args.run / "countdown_summary.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
            print(f"COMBO_DIFFERENTIAL_{result['verdict']} run={args.run} control={args.control}")
        return 0 if result["verdict"] == "PASS" else 1
    except (OSError, ValueError, KeyError, IndexError, StopIteration, struct.error, json.JSONDecodeError) as exc:
        print(f"COMBO_COUNTDOWN_FAIL_OR_INCOMPLETE {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

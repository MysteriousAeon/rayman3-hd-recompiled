#!/usr/bin/env python3
"""Check genuine scoring refreshes in a private mixed-window Combo trace.

    python tools/combo_refresh_check.py --run RUN [--require-interruption]

Reads only the existing M17 trace and fixture/layout records. It does not start
or attach to a game. Per-run payment is checked; full-session equivalence is not.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m17_frame_trace as ft  # noqa: E402
from combo_countdown_check import read_run  # noqa: E402

RUNS = ROOT / "private" / "work" / "m6_runs"


def hp_events(name, layout):
    found = []
    enemies = layout.get("enemies", [])
    if not enemies:
        return found
    last = {}
    dsg_base = int(layout["dsg"], 16)
    score_off = layout["vars"][36]
    for _, _, _, ranges in ft.frames(ROOT / "private" / "work" / f"{name}.trace"):
        timer = ft.timer_fields(ranges)
        dsg = ranges.get(dsg_base, b"")
        for enemy in enemies:
            address = int(enemy["hp_address"], 16)
            data = ranges.get(address)
            if not timer or not data:
                continue
            value = data[0]
            if last.get(address) != value:
                found.append({"model": enemy.get("model"), "perso": enemy["perso"],
                              "engine_ms": timer["total_ms"], "hp": value,
                              "score": struct.unpack_from(">i", dsg, score_off)[0]
                              if len(dsg) >= score_off + 4 else None})
                last[address] = value
    return found


def check(name, require_interruption):
    run, rows = read_run(name)
    run_dir = RUNS / name
    fixture = json.loads((run_dir / "fixture.json").read_text(encoding="utf-8"))
    layout = json.loads((run_dir / "layout.json").read_text(encoding="utf-8"))
    assertions = {}
    assertions["existing_scoped_knaar_69_combat_fixture"] = (
        fixture.get("combat_steps", "").replace("/", "\\").endswith("config\\m14\\k69_charged.txt")
        and fixture.get("mode") == "delayed-countdown"
    )

    starts = {}
    for row in rows:
        if row["pending_expiry"] and row["window_ms"] == 6000:
            starts.setdefault(row["start_ms"], []).append(row)
    first_start = next(iter(starts), None)
    assertions["real_initial_6000ms_window"] = first_start is not None
    death_timeline = hp_events(name, layout)
    if first_start is not None and layout.get("enemies"):
        assertions["observed_fixture_enemy_death_matches_first_window"] = any(
            event["hp"] == 0 and abs(event["engine_ms"] - first_start) <= 34
            and any(before["perso"] == event["perso"] and before["hp"] > 0
                    and before["engine_ms"] < event["engine_ms"] for before in death_timeline)
            for event in death_timeline
        )

    refreshes = []
    for before, after in zip(rows, rows[1:]):
        if not (before["pending_expiry"] == 1 and after["pending_expiry"] == 1
                and after["start_ms"] != before["start_ms"]
                and after["score"] > before["score"]):
            continue
        old_remaining = before["start_ms"] + before["window_ms"] - after["engine_ms"]
        expected = max(2000, before["window_ms"] - (after["start_ms"] - before["start_ms"]))
        next_row = next((r for r in rows if r["swap"] == after["swap"] + 1), None)
        obj = after["combo_object_words"] or []
        event = {
            "engine_ms": after["engine_ms"], "swap": after["swap"],
            "old_start_ms": before["start_ms"], "old_window_ms": before["window_ms"],
            "old_remaining_at_event_ms": old_remaining,
            "new_start_ms": after["start_ms"], "new_window_ms": after["window_ms"],
            "expected_refreshed_window_ms": expected,
            "score_before": before["score"], "score_after": after["score"],
            "bonus_before": before["unpaid_bonus"], "bonus_after": after["unpaid_bonus"],
            "hud_before_state": before["hud_state"], "hud_after_state": after["hud_state"],
            "hud_after_position": after["hud_position"], "hud_open_position": after["hud_open_position"],
            "hud_after_elapsed_s": after["hud_elapsed_s"],
            "handles_preserved": after["hud_handles"] == before["hud_handles"],
            "class_preserved": len(obj) > 6 and obj[0] == 0x8200FE2C,
            "material_preserved": len(obj) > 6 and obj[6] == 0x40CB14F4,
            "next_swap": next_row,
        }
        refreshes.append(event)
    assertions["two_or_more_real_scoring_refreshes"] = len(refreshes) >= 2
    for index, event in enumerate(refreshes):
        prefix = f"refresh_{index + 1}"
        assertions[prefix + "_before_old_deadline"] = event["old_remaining_at_event_ms"] > 0
        assertions[prefix + "_window_follows_guest_refresh_rule"] = event["new_window_ms"] == event["expected_refreshed_window_ms"]
        assertions[prefix + "_reopens_same_hud"] = (
            event["hud_after_state"] == 2 and event["hud_after_position"] == event["hud_open_position"]
            and event["handles_preserved"] and event["class_preserved"] and event["material_preserved"]
        )
        nxt = event["next_swap"]
        assertions[prefix + "_next_native_update_is_inactive_and_reset"] = (
            nxt is not None and nxt["start_ms"] == event["new_start_ms"]
            and nxt["hud_state"] == 2 and nxt["hud_elapsed_s"] == 0
            and nxt["hud_position"] == nxt["hud_open_position"]
        )

    if require_interruption:
        assertions["active_close_interrupted_by_real_scoring"] = any(
            event["hud_before_state"] == 3 and event["hud_after_state"] == 2 for event in refreshes
        )

    positive_cashouts = []
    for before, after in zip(rows, rows[1:]):
        if (before["unpaid_bonus"] > 0 and after["unpaid_bonus"] == 0
                and after["score"] > before["score"]):
            positive_cashouts.append({
                "engine_ms": after["engine_ms"], "start_ms": before["start_ms"],
                "window_ms": before["window_ms"], "score_before": before["score"],
                "score_after": after["score"], "bonus_paid": before["unpaid_bonus"],
                "pending_before": before["pending_expiry"], "pending_after": after["pending_expiry"],
                "age_before_ms": before["engine_ms"] - before["start_ms"],
                "age_after_ms": after["engine_ms"] - before["start_ms"],
            })
    assertions["at_least_one_positive_bonus_payout"] = bool(positive_cashouts)
    assertions["each_positive_payout_is_first_deadline_crossing"] = all(
        payout["pending_before"] == 1 and payout["pending_after"] == 0
        and payout["age_before_ms"] < payout["window_ms"] <= payout["age_after_ms"]
        and 0 <= payout["age_after_ms"] - payout["window_ms"] <= 34
        and payout["score_after"] - payout["score_before"] == payout["bonus_paid"]
        for payout in positive_cashouts
    )
    assertions["last_unpaid_bonus_is_paid_exactly_once"] = bool(positive_cashouts) and (
        positive_cashouts[-1]["score_after"] - positive_cashouts[-1]["score_before"]
        == positive_cashouts[-1]["bonus_paid"]
        and positive_cashouts[-1]["pending_before"] == 1
        and positive_cashouts[-1]["pending_after"] == 0
    )
    payout_starts = [p["start_ms"] for p in positive_cashouts]
    assertions["no_duplicate_positive_payout_per_deadline"] = len(payout_starts) == len(set(payout_starts))

    # Assess the last actual refreshed deadline: it determines the final close.
    final_start = refreshes[-1]["new_start_ms"] if refreshes else None
    final_rows = [r for r in rows if final_start is not None and r["start_ms"] == final_start
                  and r["pending_expiry"] == 1]
    final_rows.sort(key=lambda r: r["engine_ms"])
    final_close = next((r for r in final_rows if r["hud_state"] == 3), None)
    assertions["final_refreshed_window_has_pending_samples"] = bool(final_rows)
    before_close = [r for r in final_rows
                    if r["window_ms"] - (r["engine_ms"] - final_start) > 1000]
    near_threshold = [r for r in final_rows
                      if 1000 < r["window_ms"] - (r["engine_ms"] - final_start) <= 1034]
    assertions["final_window_stays_open_until_final_second"] = (
        bool(final_close) and bool(near_threshold) and all(
            r["hud_state"] == 2 and r["hud_position"] == r["hud_open_position"]
            for r in before_close
        )
    )
    remaining = (final_close["window_ms"] - (final_close["engine_ms"] - final_start)) if final_close else None
    assertions["final_close_is_one_second_at_refreshed_deadline"] = (
        final_close is not None and 966 <= remaining <= 1000
        and 0.966 <= final_close["hud_duration_s"] <= 1.0
        and abs(final_close["hud_duration_s"] - remaining / 1000) <= 0.001
    )
    moving = [r for r in final_rows if r["hud_state"] == 3]
    assertions["native_close_moves_and_finishes"] = (
        len(moving) >= 3 and len({r["hud_position"] for r in moving}) >= 3
        and (complete := next((r for r in rows if r["start_ms"] == final_start
                               and 0 <= final_rows[0]["window_ms"] - (r["engine_ms"] - final_start) <= 34
                               and r["hud_position"] == r["hud_closed_position"]
                               and r["hud_elapsed_s"] >= 0.966), None)) is not None
        and moving[-1]["hud_elapsed_s"] + (complete["native_delta_s"] or 0) + 0.00001
        >= moving[0]["hud_duration_s"]
    )

    result = {
        "run": name,
        "assessment": "per-run payment only; no whole-run control equivalence claim",
        "first_6000_start_ms": first_start,
        "enemy_hp_timeline": death_timeline,
        "scoring_refreshes": refreshes,
        "positive_cashouts": positive_cashouts,
        "final_window": {"start_ms": final_start, "rows": len(final_rows),
                         "close_start": final_close, "movement_samples": len(moving),
                         "remaining_at_close_ms": remaining},
        "assertions": assertions,
        "pass": all(assertions.values()),
    }
    output = run / "refresh_summary.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"COMBO_REFRESH_{'PASS' if result['pass'] else 'FAIL'} run={name}")
    for key, value in assertions.items():
        print(f"{'PASS' if value else 'FAIL'} {key}")
    print(f"refreshes={len(refreshes)} positive_cashouts={len(positive_cashouts)}; per-run only")
    print(f"SUMMARY {output}")
    return 0 if result["pass"] else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--require-interruption", action="store_true")
    args = parser.parse_args()
    return check(args.run, args.require_interruption)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Judge a real six-second Combo window from existing private M17 traces.

    python tools/combo_six_second_check.py --run RUN --control CONTROL

This only reads traces produced by combo_close_test.py. It never starts a game
and does not alter the existing two-second judges.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from combo_countdown_check import read_run  # noqa: E402

RUNS = ROOT / "private" / "work" / "m6_runs"


def u32(value):
    return struct.unpack(">I", value)[0]


def payment_checks(active, expiry):
    bonus = active[0]['unpaid_bonus']
    # Enemy damage can deduct points during this combat fixture. A deduction
    # is not a combo payment. Reject every early rise and require the exact
    # outstanding bonus at expiry, measured from the last active score.
    return {
        'score_after_deadline': expiry['score'] == active[-1]['score'] + bonus,
        'unpaid_bonus_after_deadline': expiry['unpaid_bonus'] == 0,
        'no_premature_payment': all(r['unpaid_bonus'] == bonus for r in active)
            and all(b['score'] <= a['score'] for a, b in zip(active, active[1:])),
    }


def payment_selftest():
    row = lambda score, bonus=0: dict(score=score, unpaid_bonus=bonus)
    assert all(payment_checks([row(100), row(100)], row(100)).values())
    assert all(payment_checks([row(100), row(99)], row(99)).values())
    assert not payment_checks([row(100), row(101)], row(101))['no_premature_payment']
    assert not payment_checks([row(100), row(99)], row(100))['score_after_deadline']
    assert all(payment_checks([row(100, 10), row(99, 10)], row(109)).values())
    assert not payment_checks([row(100, 10), row(99, 10)], row(99))['score_after_deadline']
    assert not payment_checks([row(100, 10), row(99, 0)], row(109))['no_premature_payment']
    print('COMBO_SIX_PAYMENT_SELFTEST PASS 7/7')


def evaluate(name, require_slide):
    run, rows = read_run(name)
    run_dir = RUNS / name
    layout = json.loads((run_dir / "layout.json").read_text(encoding="utf-8"))
    fixture = json.loads((run_dir / "fixture.json").read_text(encoding="utf-8"))
    checks = {}
    target = next((row for row in rows if row["window_ms"] == 6000 and row["pending_expiry"] == 1), None)
    if target is None:
        return {"run": name, "checks": {"real_6000ms_pending_window": False},
                "reason": "no sampled live target window of exactly 6000ms"}
    start = target["start_ms"]
    active = [r for r in rows if r["window_ms"] == 6000 and r["start_ms"] == start
              and r["pending_expiry"] == 1]
    if not active:
        return {"run": name, "checks": {"real_6000ms_pending_window": False}}
    scores = sorted({(r["score"], r["unpaid_bonus"]) for r in active})
    initial_score, initial_bonus = active[0]["score"], active[0]["unpaid_bonus"]
    age = lambda r: r["engine_ms"] - start
    early = [r for r in active if age(r) < 5000]
    checks["real_6000ms_pending_window"] = all(r["window_ms"] == 6000 for r in active)
    checks["scoped_existing_combat_fixture"] = (
        fixture.get("combat_steps", "").replace("/", "\\").endswith("config\\m14\\k69_charged.txt")
        and (fixture.get("mode") in (("delayed-countdown",) if require_slide else ("observe", "off"))
             or (require_slide and fixture.get("mode") == "off" and (fixture.get("preset") == "hdplus" or
                 (fixture.get('settings_file') and fixture.get('profile_combo_close') == 'delayed'))))
    )
    if fixture.get('preset') or fixture.get('settings_file'):
        log = '\n'.join(p.read_text(errors='replace') for p in run_dir.glob('runtime*.log'))
        expected = 'delayed' if require_slide else 'original'
        checks['normal_profile_runtime_selection'] = f'ComboClose profile_mode={expected}' in log
        checks['private_command_mode_absent'] = 'ComboTest command' not in log
    checks["hud_open_until_final_second"] = (
        bool(early) and max(age(r) for r in early) >= 4880
        and all(r["hud_state"] == 2 and r["hud_position"] == r["hud_open_position"]
                for r in early)
    )

    beginning = [r for r in active if 5000 <= age(r) <= 5034 and r["hud_state"] == 3]
    if require_slide:
        checks["transition_begins_in_final_second"] = bool(beginning)
        first = beginning[0] if beginning else None
        if first:
            checks["one_second_native_duration"] = 0.965 <= first["hud_duration_s"] <= 1.0
            checks["remaining_deadline_matches_duration"] = (
                966 <= first["remaining_ms_from_start"] <= 1000
                and abs(first["hud_duration_s"] - first["remaining_ms_from_start"] / 1000.0) <= 0.001
            )
        else:
            checks["one_second_native_duration"] = False
            checks["remaining_deadline_matches_duration"] = False
        moving = [r for r in active if r["hud_state"] == 3]
        checks["native_hud_interpolant_moves"] = (
            len(moving) >= 3 and len({r["hud_position"] for r in moving}) >= 3
            and max(r["hud_position"] for r in moving) - min(r["hud_position"] for r in moving) > 0.5
        )
        checks["native_animation_elapsed_advances"] = (
            len({r["hud_elapsed_s"] for r in moving if r["hud_elapsed_s"] is not None}) >= 3
        )
        endpoint = [r for r in rows if r["start_ms"] == start and 5966 <= age(r) <= 6000
                    and r["hud_position"] == r["hud_closed_position"]
                    and r["hud_elapsed_s"] >= 0.965]
        # Original expiry can reset duration to -1 on the endpoint swap.
        # Require native final elapsed and the preceding closing step as well.
        checks["native_endpoint_at_deadline"] = bool(endpoint) and bool(moving) and (
            moving[-1]["hud_elapsed_s"] + (endpoint[0]["native_delta_s"] or 0) + 0.00001
            >= moving[0]["hud_duration_s"])
    else:
        checks["control_has_no_prototype_close"] = all(r["hud_state"] != 3 for r in active)

    expiry = next((r for r in rows if r["window_ms"] == 6000 and r["start_ms"] == start
                   and age(r) >= 6000 and r["pending_expiry"] == 0), None)
    checks["cashout_or_expiry_on_original_deadline"] = expiry is not None and 6000 <= age(expiry) <= 6034
    if expiry:
        checks.update(payment_checks(active, expiry))
        checks["stable_hud_handles_and_digits"] = all(
            r['hud_handles'] == active[0]['hud_handles'] and r['hud_digits'] == active[0]['hud_digits']
            for r in active)

    hp_timeline = []
    import m17_frame_trace as ft
    for enemy in layout.get("enemies", []):
        address = int(enemy["hp_address"], 16)
        last = None
        for _, _, _, ranges in ft.frames(ROOT / "private" / "work" / f"{name}.trace"):
            data = ranges.get(address)
            if data:
                value = data[0]
                if value != last:
                    dsg = ranges.get(int(layout["dsg"], 16), b"")
                    timer = ft.timer_fields(ranges)
                    hp_timeline.append({"model": enemy["model"], "perso": enemy["perso"],
                                        "engine_ms": timer["total_ms"] if timer else None,
                                        "hp": value,
                                        "score": struct.unpack_from(">i", dsg, layout["vars"][36])[0]
                                        if len(dsg) > layout["vars"][36] + 4 else None})
                    last = value
    if require_slide:
        checks['real_enemy_death_matches_scoring_window_start'] = any(
            h['hp'] == 0 and h['engine_ms'] == start and h['score'] == initial_score
            and any(p['perso'] == h['perso'] and p['hp'] > 0 and p['engine_ms'] < start
                    for p in hp_timeline) for h in hp_timeline)
    checks['original_class_material_preserved'] = all(
        r['combo_object_words'] and r['combo_object_words'][0] == 0x8200FE2C
        and r['combo_object_words'][6] == 0x40CB14F4 for r in active)
    result = {
        "run": name,
        "scenario": "existing k69_charged isolated schedule; scoped X inputs",
        "start_ms": start,
        "active_samples": len(active),
        "first_active_age_ms": age(active[0]),
        "last_active_age_ms": age(active[-1]),
        "initial_score": initial_score,
        "initial_unpaid_bonus": initial_bonus,
        "first_expiry_score": expiry["score"] if expiry else None,
        "first_expiry_unpaid_bonus": expiry["unpaid_bonus"] if expiry else None,
        "score_bonus_values_during_window": scores,
        "enemy_hp_changes": hp_timeline,
        "slide_start": beginning[0] if require_slide and beginning else None,
        "endpoint": endpoint[0] if require_slide and endpoint else None,
        "expiry": expiry,
        "checks": checks,
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run")
    parser.add_argument("--control")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        payment_selftest()
        return 0
    if not args.run or not args.control:
        parser.error('--run and --control are required')
    delayed = evaluate(args.run, True)
    control = evaluate(args.control, False)
    same = (delayed.get("initial_score"), delayed.get("initial_unpaid_bonus"),
            delayed.get("first_expiry_score"), delayed.get("first_expiry_unpaid_bonus")) == (
            control.get("initial_score"), control.get("initial_unpaid_bonus"),
            control.get("first_expiry_score"), control.get("first_expiry_unpaid_bonus"))
    result = {"delayed": delayed, "control": control,
              "differential_checks": {"same_score_and_unpaid_bonus_at_start_and_expiry": same}}
    result["pass"] = (all(delayed.get("checks", {}).values())
                      and all(control.get("checks", {}).values()) and same)
    output = RUNS / args.run / "six_second_summary.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"COMBO_SIX_SECOND_{'PASS' if result['pass'] else 'FAIL'} run={args.run} control={args.control}")
    for label, case in (("delayed", delayed), ("control", control)):
        for key, passed in case.get("checks", {}).items():
            print(f"{'PASS' if passed else 'FAIL'} {label} {key}")
        print(f"{label} score/unpaid: {case.get('initial_score')}/{case.get('initial_unpaid_bonus')} -> "
              f"{case.get('first_expiry_score')}/{case.get('first_expiry_unpaid_bonus')}")
    print(f"{'PASS' if same else 'FAIL'} differential same_score_and_unpaid_bonus_at_start_and_expiry: {same}")
    print(f"SUMMARY {output}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

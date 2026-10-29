#!/usr/bin/env python3
"""Read-only release gate for the four saved-Settings two-second fixtures.

Uses the existing trace readers and scoring checks. This bounded gate checks
expiry and active scoring refresh, not the separate later re-entry experiment.
"""
import argparse
import json
from pathlib import Path

import combo_countdown_check as countdown
from combo_delayed_check import _begin_events, _refreshes
from combo_scoring_pair_check import sequence
import r3hd_settings as settings


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prefix', default='combo_settings')
    args = ap.parse_args()
    if not args.prefix.replace('_', '').isalnum():
        ap.error('use a simple run prefix')
    checks, evidence, payments = {}, {}, []
    for case, expected in (('vanilla', 'original'), ('hdplus', 'delayed'),
                           ('custom_on', 'delayed'), ('custom_off', 'original')):
        name = f'{args.prefix}_{case}_two_trace'
        directory, rows = countdown.read_run(name)
        fixture = json.loads((directory / 'fixture.json').read_text())
        saved = settings.load_settings_file(Path(fixture['settings_file']))
        resolved = settings.resolve(settings.load_registry(), settings=saved)['values']
        plan = (countdown.TRACE_ROOT / f'{name}_profile_plan.txt').read_text()
        log = '\n'.join(p.read_text(errors='replace') for p in directory.glob('runtime*.log'))
        begins = _begin_events(log)
        active = [r for r in rows if r['pending_expiry'] == 1 and r['window_ms'] == 2000]
        checks[case + ': persisted production configuration'] = (
            fixture['mode'] == 'off' and fixture.get('profile_combo_close') == expected
            and resolved['combo_close'] == expected and resolved['game_language'] == 'fr'
            and f'combo close: {expected}' in plan and '--user_language=4' in plan
            and f'ComboClose profile_mode={expected}' in log
            and 'ComboTest command' not in log)
        checks[case + ': real two-second combo'] = bool(active)
        early = [r for r in active if r['remaining_ms_from_start'] > 1000]
        checks[case + ': original open position before final second'] = bool(early) and all(
            r['hud_state'] == 2 and r['hud_position'] == r['hud_open_position'] for r in early)
        if expected == 'original':
            checks[case + ': abrupt original close'] = not begins and bool(active) and all(
                r['hud_state'] == 2 and r['hud_position'] == r['hud_open_position'] for r in active)
        else:
            checks[case + ': one-second production animation'] = bool(begins) and all(
                b['window_ms'] == 2000 and 966 <= b['remaining_ms'] <= 1000
                and abs(b['duration_s'] - b['remaining_ms'] / 1000) < .001 for b in begins)
            moving = [r for r in active if r['hud_state'] == 3]
            checks[case + ': native HUD moves'] = len({r['hud_position'] for r in moving}) >= 3
            refreshes = _refreshes(rows)
            checks[case + ': scoring cancels close and reopens same HUD'] = bool(refreshes) and all(
                r['state_after'] == 2 and r['position_after'] == r['open_position']
                and r['handles_after'] == r['handles_before'] for r in refreshes)
            checks[case + ': refreshed countdown starts another final-second close'] = bool(refreshes) and all(
                any(b['start_ms'] == r['new_start_ms'] for b in begins) for r in refreshes)
        _, scoring = sequence(name)
        checks[case + ': original score bonus deadline and single cash-out'] = all(scoring['checks'].values())
        summary = countdown.summarize(name, 'observe', write=False)
        payouts = summary['cashout_events']
        checks[case + ': each cash-out crosses original deadline'] = bool(payouts) and all(
            p['first_deadline_crossing'] and p['pending_expiry'] == 0 for p in payouts)
        payments.append([(p['score_before'], p['score_after'], p['bonus_before'], p['window_ms']) for p in payouts])
        evidence[case] = dict(begins=begins, refreshes=_refreshes(rows), payouts=payouts,
                              scoring=scoring, settings_file=fixture['settings_file'])
    checks['all four choices retain identical score/bonus/cash-out amounts'] = all(p == payments[0] for p in payments)
    result = dict(checks=checks, evidence=evidence, passed=sum(checks.values()), total=len(checks))
    output = countdown.TRACE_ROOT / f'{args.prefix}_runtime_summary.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"COMBO_SETTINGS_RUNTIME {'PASS' if all(checks.values()) else 'FAIL'} {result['passed']}/{result['total']}")
    for name, ok in checks.items():
        if not ok:
            print('FAIL ' + name)
    print('SUMMARY ' + str(output))
    return int(not all(checks.values()))


if __name__ == '__main__':
    raise SystemExit(main())

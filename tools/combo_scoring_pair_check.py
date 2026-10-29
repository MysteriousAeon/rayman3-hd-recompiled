"""Read-only E-312 gate: short real pickup/refresh/nonzero cash-out sequence.

No whole-session equivalence claim. Existing broader judges remain unchanged.
"""
import argparse
import json
from combo_countdown_check import read_run


def sequence(name):
    directory, rows = read_run(name)
    first = next(i for i, r in enumerate(rows) if r['pending_expiry'] == 1 and r['score'] > 0)
    payment = next(i for i in range(first + 1, len(rows))
                   if rows[i - 1]['unpaid_bonus'] > 0 and rows[i]['unpaid_bonus'] == 0
                   and rows[i]['score'] > rows[i - 1]['score'])
    active = rows[first:payment + 1]
    events, last = [], None
    origin = active[0]['start_ms']
    for row in active:
        signature = tuple(row[k] for k in ('score', 'unpaid_bonus', 'window_ms', 'start_ms', 'pending_expiry'))
        if signature != last:
            events.append(dict(score=row['score'], bonus=row['unpaid_bonus'], window=row['window_ms'],
                               start_offset=row['start_ms'] - origin, pending=row['pending_expiry']))
            last = signature
    before, paid = rows[payment - 1], rows[payment]
    end = next((i for i in range(payment + 1, len(rows)) if rows[i]['pending_expiry']), len(rows))
    after = rows[payment:end]
    checks = dict(nonzero_bonus=before['unpaid_bonus'] > 0,
                  paid_exact_bonus=paid['score'] - before['score'] == before['unpaid_bonus'],
                  pending_cleared=paid['pending_expiry'] == 0,
                  original_deadline=0 <= paid['engine_ms'] - paid['start_ms'] - paid['window_ms'] <= 34,
                  # Later enemy damage can subtract points in this fixture;
                  # it is not a second combo payment. Reject every later rise.
                  single_payment=all(r['unpaid_bonus'] == 0 for r in after) and
                      all(b['score'] <= a['score'] for a, b in zip(after, after[1:])),
                  observed_after_payment=after[-1]['engine_ms'] - paid['engine_ms'] >= 500,
                  active_refresh=len({r['start_ms'] for r in active}) >= 2)
    return directory, dict(events=events, origin=origin, payment_clock=paid['engine_ms'],
                           payment_age=paid['engine_ms'] - paid['start_ms'], checks=checks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', required=True)
    parser.add_argument('--run', required=True)
    a = parser.parse_args()
    _, control = sequence(a.control)
    directory, candidate = sequence(a.run)
    same = candidate['events'] == control['events']
    result = dict(control=control, candidate=candidate, same_events_and_relative_deadlines=same)
    result['pass'] = same and all(control['checks'].values()) and all(candidate['checks'].values())
    (directory / 'scoring_pair_summary.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print('COMBO_SCORING_PAIR', 'PASS' if result['pass'] else 'FAIL')
    raise SystemExit(not result['pass'])

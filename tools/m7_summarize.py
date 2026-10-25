"""Summarize private M7 actor/route traces into metadata, never raw DSG slices.

Usage: python tools/m7_summarize.py RUN_DIR OUTPUT_JSON
Run the retained m5/m6 summary tools separately for runtime/input/focus evidence.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = {'run': args.run.name, 'routes': {}, 'watches': {}}
    for path in sorted(args.run.glob('*route*.jsonl')):
        records = rows(path)
        samples = [r for r in records if r.get('event') == 'sample']
        result['routes'][path.name] = {
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'start': next((r for r in records if r.get('event') == 'start'), None),
            'events': [r for r in records if r.get('event') in
                       {'target_reached', 'stalled', 'actor_gone', 'collectible_change', 'error', 'end'}],
            'sample_count': len(samples),
            'first_sample': samples[0] if samples else None,
            'last_sample': samples[-1] if samples else None,
            'behaviors': sorted({r['comport'] for r in samples if r.get('comport')}),
        }
    result['pilots'] = {}
    for path in sorted(args.run.glob('*pilot*.jsonl')):
        records = rows(path)
        samples = [r for r in records if r.get('event') == 'sample']
        result['pilots'][path.name] = {
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'starts': [r for r in records if r.get('event') == 'start'],
            'ends': [r for r in records if r.get('event') == 'end'],
            'event_counts': dict(Counter(r.get('event') for r in records)),
            'milestones': [r for r in records if r.get('event') in
                           {'goal_reached', 'stop_dsg', 'follow_target_gone', 'followed_comport', 'move_blocked',
                            'replan_failed', 'error'}][:200],
            'move_results': dict(Counter((r.get('move'), r.get('event')) for r in records
                                         if r.get('event') in {'reached', 'move_failed', 'walk_failed'}).most_common())
            and {f'{move}:{event}': count for (move, event), count in
                 Counter((r.get('move') or 'walk', r.get('event')) for r in records
                         if r.get('event') in {'reached', 'move_failed', 'walk_failed'}).items()},
            'position_range': [[min(r['rayman'][axis] for r in samples), max(r['rayman'][axis] for r in samples)]
                               for axis in range(3)] if samples else None,
            'behaviors': sorted({r['comport'] for r in samples if r.get('comport')}),
        }
    completion = args.run / 'intro15_complete.json'
    if completion.is_file():
        result['intro15_complete'] = json.loads(completion.read_text())
    for path in sorted(args.run.glob('*watch*.jsonl')):
        records = rows(path)
        states = [r for r in records if r.get('event') == 'actor_state']
        positions = [r for r in records if r.get('event') == 'position_sample' and r.get('rayman')]
        actors = {}
        for record in states:
            key = record['so'] or str(record['actor_id'])
            actor = actors.setdefault(key, {'model': record.get('model'), 'behaviors': set(),
                                            'reflexes': set(), 'state_changes': 0})
            actor['state_changes'] += 1
            for source, dest in [('comport', 'behaviors'), ('reflex', 'reflexes')]:
                if record['changed'].get(source):
                    actor[dest].add(record['changed'][source])
        for actor in actors.values():
            actor['behaviors'] = sorted(actor['behaviors'])
            actor['reflexes'] = sorted(actor['reflexes'])
        dsg = {}
        for record in records:
            if record.get('event') == 'dsg_sample':
                for index, value in record.get('values', {}).items():
                    stat = dsg.setdefault(index, {'samples': 0, 'byte_lengths': set(), 'values': set()})
                    stat['samples'] += 1
                    stat['byte_lengths'].add(value['byte_length'])
                    stat['values'].add(value['raw_hex'])
        result['watches'][path.name] = {
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'start': next((r for r in records if r.get('event') == 'start'), None),
            'end': next((r for r in reversed(records) if r.get('event') == 'end'), None),
            'actors': actors,
            'read_error_count': sum(r.get('event') == 'read_error' for r in records),
            'invalidations': [r for r in records if r.get('event') == 'actor_invalidated'],
            'position_samples': len(positions),
            'position_range': [[min(r['rayman'][axis] for r in positions),
                                max(r['rayman'][axis] for r in positions)] for axis in range(3)] if positions else None,
            'dsg_statistics': {index: {'samples': stat['samples'],
                                      'byte_lengths': sorted(stat['byte_lengths']),
                                      'distinct_value_count': len(stat['values'])} for index, stat in dsg.items()},
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    companion = args.output.parent / 'compatibility.json'
    if companion.exists():
        data = json.loads(companion.read_text())
        accesses = data.get('file_access', [])
        if accesses and isinstance(accesses[0], str):
            counts = Counter(line.split('M2 vfs_open ', 1)[-1] for line in accesses)
            data['file_access_event_count'] = len(accesses)
            data['file_access'] = [{'fields': fields, 'count': count} for fields, count in sorted(counts.items())]
            companion.write_text(json.dumps(data, indent=2) + '\n')
    # Analog-stick piloting produces thousands of input events; durable metadata keeps counts,
    # the first and last entries and a hash of the full list (the raw logs stay private).
    for name in ('compatibility.json', 'observations.json'):
        path = args.output.parent / name
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        changed = False
        for key, value in list(data.items()):
            if isinstance(value, list) and len(value) > 200:
                data[key] = {'count': len(value), 'first': value[:40], 'last': value[-10:],
                             'sha256_of_full_list': hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()}
                changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({'routes': len(result['routes']), 'watches': len(result['watches']), 'pilots': len(result['pilots'])}))


if __name__ == '__main__':
    main()

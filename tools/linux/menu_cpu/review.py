"""Offline E-413 evidence review. No process inspection, execution or extraction."""
import argparse
from datetime import datetime
import io
import json
import math
from pathlib import Path
import statistics
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'menu_timing'))
import timing as T
import cpu as C

EXPECTED = '60048824012489e9c3d923bd14e7abdaadc35ce7cdbec2d2cb32cac81ebbf0d4'
MEMBERS = {'before.json', 'receipt.json', 'menu.json', 'gameplay.json'}
IDENTITY = {'accepted_evidence_sha256': T.ACCEPTED, 'portable_manifest_sha256': T.PORTABLE,
            'settings_sha256': T.SETTINGS, 'programs_checked': 56}


def authenticate(path, expected=EXPECTED):
    path = path.resolve()
    raw = T.read_stable(path, 8000000)
    T.need(T.digest(raw) == expected, 'archive identity differs')
    side = T.read_stable(Path(str(path) + '.sha256'), 1000).decode('ascii')
    T.need(side.strip() == expected + '  ' + path.name, 'sidecar differs')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        T.need(len(names) == len(set(names)) and set(names) == MEMBERS | {'SHA256SUMS'}, 'archive inventory')
        T.need(sum(i.file_size for i in z.infolist()) < 8000000 and
               all(not i.is_dir() and not i.flag_bits & 1 for i in z.infolist()), 'archive bounds')
        T.need(z.testzip() is None, 'archive CRC')
        seen = set()
        for line in z.read('SHA256SUMS').decode('ascii').splitlines():
            digest, name = line.split('  ')
            T.need(name in MEMBERS and name not in seen and T.digest(z.read(name)) == digest, 'internal ledger')
            seen.add(name)
        T.need(seen == MEMBERS, 'incomplete ledger')
        return {n: T.strict(z.read(n)) for n in MEMBERS}


def analyze(rows):
    before, r = rows['before.json'], rows['receipt.json']
    for item in (before, r):
        T.need(item['owner'] == 'R3HD_MENU_CPU_01' and item['program_identity'] == IDENTITY and
               item['helper_seal_sha256'] == C.RUNNER_SEAL and item['retained_evidence_sha256'] == C.RETAINED,
               'receipt provenance')
    T.need(r['after_program_identity'] == IDENTITY and r['complete_comparison'] is True and
           type(r['script_exit']) is int and r['script_exit'] == 0 and
           r['stop_reason'] is None and r['forced_reason'] is None and r['termination_actions'] == [] and
           'cleanup_uncertain' not in r and 'integrity_or_log_review' not in r and
           r['focus_confirmed_human'] is True and r['windows'] == ['MENU', 'GAMEPLAY'], 'protocol incomplete')
    hz = r['clock_ticks_per_second']
    T.need(type(hz) is int and 0 < hz <= 1000000, 'clock units')
    T.need(set(r['human_observations']) == {'menu_slowdown_seen', 'gameplay_speed_looked_normal'} and
           all(v in ('yes', 'no', 'unknown') for v in r['human_observations'].values()), 'human observation schema')
    result = {'scope': 'idle title menu versus ordinary gameplay; pause navigation NOT MEASURED',
              'human_observations': r['human_observations'], 'windows': {}}
    last_end = None
    for name in ('menu', 'gameplay'):
        row = rows[name + '.json']; points = row['samples']
        T.need(row['scene_human_label'] == name.upper() and row['window_complete'] is True and
               row['thread_samples_complete'] is True and len(points) == 46 and len(row['deltas']) == 45,
               'window incomplete')
        T.need(all(not p['unreadable_or_exited_tids'] for p in points), 'thread coverage incomplete')
        T.need(all(type(p['process_ticks']) is int and p['process_ticks'] >= 0 and
                   math.isfinite(p['monotonic']) and 0 <= p['counter_read_seconds'] < 1 for p in points), 'counter bounds')
        recalculated = [C.deltas(a, b, hz) for a, b in zip(points, points[1:])]
        T.need(recalculated == row['deltas'], 'stored CPU calculations differ')
        a, b = points[0], points[-1]
        elapsed = b['monotonic'] - a['monotonic']
        T.need(45 <= elapsed < 60 and (last_end is None or a['monotonic'] > last_end), 'window chronology')
        last_end = b['monotonic']
        wall_elapsed = (datetime.fromisoformat(b['wall']) - datetime.fromisoformat(a['wall'])).total_seconds()
        T.need(abs(wall_elapsed - elapsed) < .1, 'wall/monotonic discrepancy')
        common = set.intersection(*(set(p['threads']) for p in points))
        thread_cpu = {k: 100 * (b['threads'][k]['ticks'] - a['threads'][k]['ticks']) / hz / elapsed for k in common}
        process = 100 * (b['process_ticks'] - a['process_ticks']) / hz / elapsed
        result['windows'][name] = {'start': a['wall'], 'end': b['wall'], 'seconds': elapsed,
            'process_one_core_percent': process,
            'process_interval_min_max': [min(d['process_one_core_percent'] for d in recalculated),
                                         max(d['process_one_core_percent'] for d in recalculated)],
            'top_threads_one_core_percent': sorted(thread_cpu.items(), key=lambda kv: (-kv[1], kv[0]))[:5],
            'thread_count_min_max': [min(len(p['threads']) for p in points), max(len(p['threads']) for p in points)],
            'new_or_ended_thread_intervals': sum(bool(d['new_threads'] or d['ended_threads']) for d in recalculated),
            'counter_read_ms_mean_max': [statistics.mean(p['counter_read_seconds'] for p in points) * 1000,
                                         max(p['counter_read_seconds'] for p in points) * 1000]}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    print(json.dumps(analyze(authenticate(parser.parse_args().archive)), indent=2))

"""Produce metadata-only runtime summaries. Never copies game data or code."""
import argparse, collections, csv, hashlib, json, re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('run_directory', type=Path)
ap.add_argument('output', type=Path)
args = ap.parse_args()
root = Path(__file__).resolve().parents[1]
log = (args.run_directory/'runtime.log').read_text(errors='replace')
rows = list(csv.DictReader((root/'reports/milestone1/import_surface.csv').open()))
imports = {}
for line in log.splitlines():
    m = re.search(r'M2 import=(?:__imp__)?(\S+) stub=(\w+) count=(\d+) caller=([\dA-F]+) (.*)', line)
    if not m: continue
    name, stub, count, caller, registers = m.groups()
    entry = imports.setdefault(name, {'first_caller': '0x'+caller, 'first_arguments': registers,
                                      'counter_lower_bound': 0, 'macro_stub': stub == 'true'})
    entry['counter_lower_bound'] = max(entry['counter_lower_bound'], int(count))
    # Original stub macros emit a warning for every hit: exact count, even though
    # observational import counters only log powers of two.
    entry['stub_warning_count'] = len(re.findall(r'__imp__'+re.escape(name)+r' STUB\b', log))
    matching = [r for r in rows if r.get('name') == name]
    if matching: entry['m1_inventory'] = matching[0]
summary = {
    'run': json.loads((args.run_directory/'run.json').read_text(encoding='utf-8-sig')),
    'runtime_log_sha256': hashlib.sha256((args.run_directory/'runtime.log').read_bytes()).hexdigest(),
    'entrypoint_executed': 'M2 guest_entry_executed pc=820E13F8' in log,
    'runtime_initialized': 'M2 runtime_initialized' in log,
    'ring_initialized': re.findall(r'M2 ring_initialized (.*)', log),
    'shader_submissions': re.findall(r'M2 shader_submit (.*)', log),
    'file_open_results': dict(collections.Counter(re.findall(r'M2 vfs_open (.*)', log))),
    'stub_hits': {n:e for n,e in imports.items() if e['macro_stub'] or e['stub_warning_count']},
    'semantic_stub_lines': [l for l in log.splitlines() if '[STUB]' in l],
    'imports': imports,
    'fatal_lines': [l for l in log.splitlines() if '[FATAL]' in l],
    'seh_catch_lines': [l for l in log.splitlines() if 'SEH exception caught' in l],
    'bink_code_entered': 'M2 bink_code_entered' in log,
}
faults = args.run_directory/'m2_faults.log'
if faults.exists():
    summary['exception_records'] = re.findall(r'^M2 exception code=.*', faults.read_text(), re.M)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps({k:summary[k] for k in ('entrypoint_executed', 'runtime_initialized', 'stub_hits', 'bink_code_entered')}))

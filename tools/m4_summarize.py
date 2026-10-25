"""Metadata-only M4 input, exception, graphics-warning and audio smoke evidence."""
import collections, hashlib, json, re, sys
from pathlib import Path

run, output = map(Path, sys.argv[1:3])
lines = sorted(l for p in run.glob('runtime*.log') for l in p.read_text(errors='replace').splitlines())
select = lambda token: [l for l in lines if token in l]
fetch = select('M4 invalid_fetch')
slots, descriptors, masks, ps, vs, bins = [collections.Counter() for _ in range(6)]
swaps = []
legacy_labels = run.name in ('interactive1', 'interactive2')
for line in fetch:
    slots.update(re.findall(r'slot=(\d+)', line))
    descriptors.update(hashlib.sha256(d.encode()).hexdigest() for d in re.findall(r'descriptor=(\S+)', line))
    masks.update(re.findall(r'used_mask=(\w+)', line))
    ps.update(re.findall(r'last_vs=(\w+)' if legacy_labels else r'last_ps=(\w+)', line))
    vs.update(re.findall(r'last_ps=(\w+)' if legacy_labels else r'last_vs=(\w+)', line))
    n = int(re.search(r'swaps=(\d+)', line)[1]); swaps.append(n); bins[str((n // 300) * 300)] += 1
audio = []
for line in select('M4 audio_output'):
    m = re.search(r'frames=(\d+) nonzero=(\d+) channels=(\d+) rate=(\d+) samples=(\d+) energy=(\S+) peak=(\S+)', line)
    if m:
        audio.append(dict(timestamp=line[1:24], frames=int(m[1]), nonzero_frames=int(m[2]),
                          channels=int(m[3]), rate=int(m[4]), samples=int(m[5]), energy=float(m[6]), peak=float(m[7])))
result = dict(run=json.loads((run / 'run.json').read_text(encoding='utf-8-sig')),
              host_keys=select('M4 host_key'), returned_input=select('M4 input_state'),
              guest_filters=select('M4 seh_filter'), guest_cleanup=select('M4 seh_finally'),
              fatal_lines=select('M2 fatal'), stub_lines=select('STUB'),
              invalid_fetch=dict(count=len(fetch), slots=dict(slots), descriptor_sha256=dict(descriptors),
                                 corrected_legacy_shader_labels=legacy_labels,
                                 masks=dict(masks), last_pixel_shader=dict(ps), last_vertex_shader=dict(vs),
                                 first_swap=min(swaps) if swaps else None, last_swap=max(swaps) if swaps else None,
                                 swaps_300_bins=dict(bins)),
              audio_output=audio, xma_decoded=select('M4 xma_decoded'),
              audio_endpoints=select('audio endpoint'), file_access=select('M2 vfs_open'))
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ('invalid_fetch', 'audio_output', 'xma_decoded')}, indent=2))

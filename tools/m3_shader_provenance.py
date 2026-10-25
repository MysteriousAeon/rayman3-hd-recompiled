"""Milestone 3: where did each submitted Xenos microcode blob come from?

Byte-searches every distinct blob dumped by the GPU instrumentation (m3_shader_*.bin in a
private run directory) in the shipped precompiled caches, the other psm/ files and the
decrypted executable image. Output is metadata only (hashes, sizes, file names, offsets).
usage: m3_shader_provenance.py <run_dir> <extracted_root> <image> <out.json>"""
import collections, json, sys
from pathlib import Path

run, root, image, outp = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
psm = next(p for p in root.iterdir() if p.name.lower() == 'psm')
haystacks = {p.name: p.read_bytes() for p in sorted(psm.iterdir()) if p.is_file()}
haystacks['<Default.xex image>'] = image.read_bytes()
rows, tally = [], collections.Counter()
for f in sorted(run.glob('m3_shader_*.bin')):
    _, _, kind, digest = f.stem.split('_')
    blob = f.read_bytes()
    hits = {name: data.find(blob) for name, data in haystacks.items()}
    hits = {n: o for n, o in hits.items() if o >= 0}
    # A cache may store the same microcode with a differing header word: retry on the body.
    partial = {}
    if not hits and len(blob) > 32:
        partial = {n: o for n, o in ((n, d.find(blob[16:])) for n, d in haystacks.items()) if o >= 0}
    # Xbox 360 D3D patches vertex-fetch instructions when a shader is bound to a vertex
    # declaration, so a cache-derived blob need not match byte-for-byte. Measure how many
    # of its 12-byte microcode instructions occur in each shipped file.
    triples = [blob[i:i + 12] for i in range(0, len(blob) - 11, 12)]
    fraction = {n: round(sum(1 for c in triples if c in d) / max(1, len(triples)), 3)
                for n, d in haystacks.items() if 'xenon' in n or n.startswith('<')}
    best = max(fraction, key=fraction.get)
    source = ('precompiled_cache' if any('ShaderCache_xenon' in n for n in hits) else
              'executable_image' if '<Default.xex image>' in hits else
              'other_psm_file' if hits else
              'partial_match' if partial else
              'cache_derived_patched' if 'ShaderCache_xenon' in best and fraction[best] >= 0.6 else
              'not_in_shipped_files')
    tally[(('vertex', 'pixel')[int(kind)] if kind in '01' else kind, source)] += 1
    rows.append(dict(type=('vertex', 'pixel')[int(kind)] if kind in '01' else kind, hash=digest, bytes=len(blob),
                     source=source, instruction_match=fraction, exact={n: hex(o) for n, o in hits.items()}, partial={n: hex(o) for n, o in partial.items()}))
out = dict(distinct_blobs=len(rows), tally={f'{t}/{s}': n for (t, s), n in sorted(tally.items())},
           cache_sizes={n: len(d) for n, d in haystacks.items() if 'Cache' in n}, blobs=rows)
outp.parent.mkdir(parents=True, exist_ok=True)
outp.write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps({k: v for k, v in out.items() if k != 'blobs'}, indent=1))
for r in rows:
    if r['source'] != 'precompiled_cache':
        print(r)

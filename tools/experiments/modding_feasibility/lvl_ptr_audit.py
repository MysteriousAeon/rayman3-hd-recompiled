"""File-domain integrity audit of the Xbox 360 HD .lvl/.ptr pairs. Counts only.
For every level: pointer slots inside the file, target file ids, targets inside the target file,
trailing .ptr bytes, header words. Establishes whether the relocation table is a closed description
of the pointers (precondition for any relocating patcher)."""
import struct, sys, os, collections
root = sys.argv[1]
def load(p): return open(p, 'rb').read()
fix = load(os.path.join(root, 'fix.lvl'))
tot = collections.Counter(); files = collections.Counter(); rows = []
levels = sorted(d for d in os.listdir(root) if os.path.isfile(os.path.join(root, d, d + '.lvl')))
def audit(name, lvl, ptr, sizes, own):
    n = struct.unpack_from('>I', ptr, 0)[0]
    bad_slot = bad_tgt = 0; fid = collections.Counter(); seen = set(); dup = 0; unaligned = 0
    for i in range(n):
        f, loc = struct.unpack_from('>iI', ptr, 4 + 8 * i)
        fid[f] += 1
        if loc in seen: dup += 1
        seen.add(loc)
        if loc & 3: unaligned += 1
        if loc + 8 > len(lvl): bad_slot += 1; continue
        v = struct.unpack_from('>I', lvl, loc + 4)[0]
        tsize = sizes.get(f)
        if tsize is None or v + 4 > tsize: bad_tgt += 1
    rest = len(ptr) - 4 - 8 * n
    return dict(name=name, size=len(lvl), n=n, bad_slot=bad_slot, bad_tgt=bad_tgt, dup=dup, unaligned=unaligned, fid=dict(fid), rest=rest,
                hdr=struct.unpack_from('>6I', lvl, 0))
r = audit('fix', fix, load(os.path.join(root, 'fix.ptr')), {0: len(fix)}, 0)
print(r)
agg = collections.Counter(); fids = collections.Counter(); rests = collections.Counter(); hdr0 = collections.Counter()
for L in levels:
    lvl = load(os.path.join(root, L, L + '.lvl'))
    tp = os.path.join(root, L, 'transit.lvl')
    sizes = {0: len(fix), 1: len(lvl)}
    if os.path.isfile(tp): sizes[2] = os.path.getsize(tp)
    r = audit(L, lvl, load(os.path.join(root, L, L + '.ptr')), sizes, 1)
    for k in ('n', 'bad_slot', 'bad_tgt', 'dup', 'unaligned', 'size'): agg[k] += r[k]
    for k, v in r['fid'].items(): fids[k] += v
    rests[r['rest'] - 16 * r['hdr'][0]] += 1; agg['second_table_entries'] += r['hdr'][0]; hdr0[r['hdr'][2:6]] += 1
    if r['bad_slot'] or r['bad_tgt']: print('  !', r)
    if os.path.isfile(tp) and os.path.isfile(tp[:-3] + 'ptr'):
        t = load(tp)
        rt = audit(L + '/transit', t, load(tp[:-3] + 'ptr'), {0: len(fix), 1: len(lvl), 2: len(t)}, 2)
        for k, v in rt['fid'].items(): agg['transit_fid_%d' % k] += v
        agg['transit_bad'] += rt['bad_slot'] + rt['bad_tgt']
print('levels', len(levels), dict(agg))
print('target file ids', dict(fids)); print('ptr trailing bytes', dict(rests)); print('header words 2..5', dict(hdr0))

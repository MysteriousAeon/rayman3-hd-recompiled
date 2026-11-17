"""Wave-object statistics for the Xbox 360 HD Hx banks. Structure and numbers only."""
import struct, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hx_index import parse

root = sys.argv[1]
fsize = {f.upper(): os.path.getsize(os.path.join(root, f)) for f in os.listdir(root)}
waves = {}   # cuuid -> tuple
anom = collections.Counter()
hdrvals = collections.Counter(); tags = collections.Counter(); rates = collections.Counter(); chans = collections.Counter()
conts = collections.Counter(); tails = collections.Counter(); sizes_rec = collections.Counter()
per_bank_wav = {}
wavres_named = 0; wavres_lang = 0; wavres = 0
dupdiff = 0
for f in sorted(os.listdir(root)):
    if not f.lower().endswith('.hxx'): continue
    d, typ, ents, end = parse(os.path.join(root, f))
    for e in ents:
        r = d[e['off']:e['off']+e['size']]
        if e['cls'] == 'CXBoxWavResData':
            wavres += 1
            if e['langs']: wavres_lang += 1
        if 'WaveFileIdObj' not in e['cls']: continue
        n = struct.unpack_from('>I', r, 0)[0]
        o = 4 + n + 8
        off, units, z = struct.unpack_from('>III', r, o); o += 12
        pre = r[o:o+5]; o += 5            # 01 80 ff ff ff TT
        tag, ch, rate, avg, align, bits, cb = struct.unpack_from('>HHIIHHH', r, o); o += 18
        ext = r[o:o+cb]; o += cb
        rest = r[o:]
        # trailing: ... u32 namelen, name
        name = rest[-10:].decode('latin-1')
        # find container name: last length-prefixed string
        k = len(rest) - 1
        cname = None
        for L in (10, 11, 12):
            if len(rest) >= L + 4 and struct.unpack_from('>I', rest, len(rest) - L - 4)[0] == L:
                cname = rest[-L:].decode('latin-1'); break
        hdrvals[pre.hex()] += 1; tags[tag] += 1; rates[rate] += 1; chans[ch] += 1
        conts[(e['cls'], cname)] += 1; sizes_rec[(e['cls'], e['size'], cb)] += 1
        if cb == 34:
            ns, mask, enc, bpb, pb, pl, lb, ll, lc, ev, bc = struct.unpack('>HIIIIIIIBBH', ext)
            if bc * bpb != units: anom['blockcount*bpb != units*256'] += 1
            if bpb != 0x800: anom['bpb!=0x800'] += 1
            tails[(ev, lc)] += 1
        else:
            anom['cb!=34'] += 1; enc = lc = None
        if cname and cname.upper() in fsize:
            if off + units > fsize[cname.upper()]: anom['past container end'] += 1
        else:
            anom['container missing:%s' % cname] += 1
        key = e['cuuid']
        val = (cname, off, units, ch, rate, enc)
        if key in waves and waves[key] != val: dupdiff += 1
        waves[key] = val
print('wave objects (unique cuuid):', len(waves), 'conflicting duplicates:', dupdiff)
print('pre-bytes:', hdrvals.most_common(8))
print('format tag:', dict(tags)); print('channels:', dict(chans))
print('rates top:', rates.most_common(12), 'distinct', len(rates))
print('container by class:', dict(conts))
print('record size/cb:', sizes_rec.most_common(8))
print('(encoder version, loop count):', tails.most_common(8))
print('anomalies:', dict(anom))
print('WavResData', wavres, 'with language variants', wavres_lang)
# coverage / overlap per container
by = collections.defaultdict(list)
for k, (c, off, size, ch, rate, enc) in waves.items(): by[c.upper()].append((off, size))
for c, lst in by.items():
    lst = sorted(set(lst)); cov = 0; ov = 0; last = 0; gaps = 0
    for off, size in lst:
        if off < last: ov += 1
        elif off > last: gaps += off - last
        cov += size; last = max(last, off + size)
    print(c, 'ranges', len(lst), 'bytes', cov, 'file', fsize.get(c), 'overlaps', ov, 'gap bytes', gaps, 'tail', fsize.get(c, 0) - last)
# duration distribution
dur = sorted((enc / rate) for (c, off, size, ch, rate, enc) in waves.values() if enc and rate)
print('duration s: median %.2f p90 %.2f max %.1f total h %.2f' % (dur[len(dur)//2], dur[int(len(dur)*.9)], dur[-1], sum(dur)/3600))
st = [enc / rate for (c, off, size, ch, rate, enc) in waves.values() if c.upper().startswith('STREAM') and enc]
print('stream waves', len(st), 'median s %.1f' % sorted(st)[len(st)//2])

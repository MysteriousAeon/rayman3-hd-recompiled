"""Hx resource graph statistics: X360 names/categories and PC cuuid overlap. Numbers and identifiers only."""
import struct, sys, os, re, collections

def parse(path, be):
    E = '>' if be else '<'
    d = open(path, 'rb').read()
    idx = struct.unpack_from(E + 'I', d, 0)[0]
    tag = d[idx:idx+4]
    typ, cnt = struct.unpack_from(E + 'II', d, idx+4)
    o = idx + 12; ents = []
    for i in range(cnt):
        n = struct.unpack_from(E + 'I', d, o)[0]; o += 4
        cls = d[o:o+n].decode('ascii'); o += n
        c1, c2, off, size, unk, nlink = struct.unpack_from(E + 'IIIIII', d, o); o += 24
        links = [struct.unpack_from(E + 'II', d, o + 8*k) for k in range(nlink)]; o += 8*nlink
        nlang = struct.unpack_from(E + 'I', d, o)[0]; o += 4
        langs = [struct.unpack_from(E + '4sIII', d, o + 16*k) for k in range(nlang)]; o += 16*nlang
        ents.append((cls, (c1, c2), off, size, links, langs))
    return d, tag, ents, o == len(d)

x360, pc = sys.argv[1], sys.argv[2]
# --- X360
names = {}
for f in os.listdir(x360):
    if f.lower().endswith('.bnh'):
        for m in re.finditer(rb'cuuid\( 0x([0-9a-f]+), 0x([0-9a-f]+) \).*?\* file (\S+) \* subtitle 0x([0-9a-f]+)', open(os.path.join(x360, f), 'rb').read()):
            names[(int(m.group(1), 16), int(m.group(2), 16))] = m.group(3).decode('latin-1')
xcls = collections.defaultdict(set); wav2wave = collections.defaultdict(set); wavlang = {}
wave = {}
for f in os.listdir(x360):
    if not f.lower().endswith('.hxx'): continue
    d, tag, ents, exact = parse(os.path.join(x360, f), True)
    for cls, cu, off, size, links, langs in ents:
        xcls[cls].add(cu)
        r = d[off:off+size]
        if cls == 'CXBoxWavResData':
            if langs:
                wavlang[cu] = {l[0].decode().strip(): (l[2], l[3]) for l in langs}
            else:
                wav2wave[cu].add(struct.unpack('>II', r[-8:]))
        elif 'WaveFileIdObj' in cls:
            n = struct.unpack_from('>I', r, 0)[0]; o = 4 + n + 8
            woff, wsize = struct.unpack_from('>II', r, o); o += 17
            tagf, ch, rate = struct.unpack_from('>HHI', r, o)
            enc = struct.unpack_from('>I', r, o + 18 + 6)[0]
            wave[cu] = (cls, wsize, ch, rate, enc)
print('X360 unique cuuids per class:', {k: len(v) for k, v in xcls.items()})
allx = set().union(*xcls.values())
print('named by .bnh:', sum(1 for c in allx if c in names), 'of', len(allx), '(wave objects are unnamed: %d)' % len(wave))
print('WavResData single-wave ambiguous:', sum(1 for v in wav2wave.values() if len(v) > 1), 'language sets:', len(wavlang))
# name uniqueness among WavResData
n2c = collections.defaultdict(set)
for cu in xcls['CXBoxWavResData']:
    if cu in names: n2c[names[cu]].add(cu)
print('WavResData names:', len(n2c), 'names mapping to >1 cuuid:', sum(1 for v in n2c.values() if len(v) > 1))
# resolve wav -> wave (english for language sets)
def waves_of(cu):
    if cu in wavlang: return [wavlang[cu].get('en')]
    return list(wav2wave.get(cu, []))
unres = 0; cat = collections.defaultdict(lambda: [0, 0.0, 0, collections.Counter()])
for cu in xcls['CXBoxWavResData']:
    nm = names.get(cu, '?')
    pre = re.match(r'[A-Za-z]+', nm); pre = pre.group(0) if pre else '?'
    for w in waves_of(cu):
        if w not in wave: unres += 1; continue
        cls, wsize, ch, rate, enc = wave[w]
        c = cat[pre]; c[0] += 1; c[1] += enc / rate; c[2] += wsize; c[3][(ch, 'stream' if 'Stream' in cls else 'static')] += 1
print('unresolved wave links:', unres)
for k, v in sorted(cat.items(), key=lambda kv: -kv[1][1])[:16]:
    print('  %-8s n %5d  %7.1f min  %6.1f MB  %s' % (k, v[0], v[1] / 60, v[2] / 1e6, dict(v[3])))
lang_total = collections.Counter()
for cu, m in wavlang.items():
    for l, w in m.items():
        if w in wave: lang_total[l] += wave[w][4] / wave[w][3]
print('language-set minutes:', {k: round(v / 60, 1) for k, v in lang_total.items()})
# --- PC
pcls = collections.defaultdict(set); okf = 0; tags = collections.Counter()
for f in os.listdir(pc):
    if not f.lower().endswith('.hxc'): continue
    d, tag, ents, exact = parse(os.path.join(pc, f), False)
    okf += exact; tags[tag] += 1
    for cls, cu, off, size, links, langs in ents: pcls[cls].add(cu)
print('PC banks parsed exactly:', okf, 'index tags', dict(tags))
print('PC unique cuuids per class:', {k: len(v) for k, v in pcls.items()})
for a, b in (('CEventResData', 'CEventResData'), ('CXBoxWavResData', 'CPCWavResData'), ('CRandomResData', 'CRandomResData'), ('CProgramResData', 'CProgramResData')):
    A, B = xcls.get(a, set()), pcls.get(b, set())
    print('  %s vs %s: x360 %d pc %d common %d' % (a, b, len(A), len(B), len(A & B)))
xw = xcls['CXBoxStaticHWWaveFileIdObj'] | xcls['CXBoxStreamHWWaveFileIdObj']
pw = set().union(*[v for k, v in pcls.items() if 'WaveFileIdObj' in k])
print('  wave objects: x360 %d pc %d common %d' % (len(xw), len(pw), len(xw & pw)))

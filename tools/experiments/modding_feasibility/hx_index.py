"""Offline index parser for Ubisoft Hx sound banks (.hxx, big-endian, Xbox 360 HD).
Reads only structure: class names, cuuids, offsets, sizes, links. Prints statistics.
Usage: python hx_index.py SOUND_DIR [dump FILE CLASS N]
"""
import struct, sys, os, collections

def parse(path):
    d = open(path, 'rb').read()
    idx = struct.unpack_from('>I', d, 0)[0]
    assert d[idx:idx+4] == b'XDNI', (path, d[idx:idx+4])
    typ, cnt = struct.unpack_from('>II', d, idx+4)
    o = idx + 12
    ents = []
    for i in range(cnt):
        n = struct.unpack_from('>I', d, o)[0]; o += 4
        cls = d[o:o+n].decode('ascii'); o += n
        c1, c2, off, size, unk, nlink = struct.unpack_from('>IIIIII', d, o); o += 24
        links = [struct.unpack_from('>II', d, o + 8*k) for k in range(nlink)]; o += 8*nlink
        nlang = struct.unpack_from('>I', d, o)[0]; o += 4
        langs = [struct.unpack_from('>4sIII', d, o + 16*k) for k in range(nlang)]; o += 16*nlang
        ents.append(dict(cls=cls, cuuid=(c1, c2), off=off, size=size, unk=unk, links=links, langs=langs))
    return d, typ, ents, o

if __name__ == '__main__':
    root = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == 'dump':
        d, typ, ents, end = parse(os.path.join(root, sys.argv[3]))
        k = 0
        for e in ents:
            if e['cls'] == sys.argv[4]:
                print(e['cls'], '%08x:%08x' % e['cuuid'], hex(e['off']), e['size'], e['links'], e['langs'])
                print(d[e['off']:e['off']+e['size']].hex(' ', 4))
                k += 1
                if k >= int(sys.argv[5]): break
        sys.exit()
    tot = collections.Counter(); ok = 0; bad = []
    sizes = collections.defaultdict(list)
    for f in sorted(os.listdir(root)):
        if not f.lower().endswith('.hxx'): continue
        try:
            d, typ, ents, end = parse(os.path.join(root, f))
        except Exception as ex:
            bad.append((f, repr(ex)[:80])); continue
        ok += 1
        exact = (end == len(d))
        c = collections.Counter(e['cls'] for e in ents)
        tot.update(c)
        for e in ents: sizes[e['cls']].append(e['size'])
        # contiguity: records cover [4, idx)?
        cov = sum(e['size'] for e in ents)
        print(f, 'type', typ, 'n', len(ents), 'index_end_exact', exact, 'records_bytes', cov, 'idx', struct.unpack_from('>I', d, 0)[0])
    print('parsed', ok, 'bad', bad)
    for k, v in tot.most_common():
        s = sizes[k]
        print('%-34s %6d  size min %d max %d' % (k, v, min(s), max(s)))

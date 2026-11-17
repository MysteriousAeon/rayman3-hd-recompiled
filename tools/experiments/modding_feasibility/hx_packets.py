"""Packet-level checks of the Xbox 360 HD XMA2 wave ranges (E-454). Counts only; no audio is decoded or written.
For every wave-file record: frames started in its packets against ceil(SamplesEncoded / 512), duplicate 2,048-byte
packets, byte-identical waves, shared first packets.
Usage: python -I hx_packets.py <GAMEDATAbin/WORLD/SOUND>"""
import collections, hashlib, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hx_index import parse

root = sys.argv[1]
waves = {}
for f in os.listdir(root):
    if not f.lower().endswith('.hxx'):
        continue
    d, typ, ents, end = parse(os.path.join(root, f))
    for e in ents:
        if 'WaveFileIdObj' not in e['cls']:
            continue
        r = d[e['off']:e['off'] + e['size']]
        n = struct.unpack_from('>I', r, 0)[0]
        o = 4 + n + 8
        off, size = struct.unpack_from('>II', r, o)
        enc = struct.unpack_from('>I', r, o + 17 + 18 + 6)[0]
        cont = 'STATIC.HSX' if 'Static' in e['cls'] else ('STREAM.H00' if b'STREAM.H00' in r[-12:] else 'STREAM.H01')
        waves[e['cuuid']] = (cont, off, size, enc)
data = {c: open(os.path.join(root, c), 'rb').read() for c in ('STATIC.HSX', 'STREAM.H00', 'STREAM.H01')}

def h(b):
    return hashlib.blake2b(b, digest_size=8).digest()

seen = {}
dup_packets = packets = skip = exact = 0
whole = collections.defaultdict(list)
first = collections.defaultdict(list)
for cu, (cont, off, size, enc) in waves.items():
    b = data[cont][off:off + size]
    frames = 0
    for k in range(size // 2048):
        p = b[k * 2048:(k + 1) * 2048]
        packets += 1
        x = h(p)
        if x in seen and seen[x] != (cu, k):
            dup_packets += 1
        seen[x] = (cu, k)
        frames += p[0] >> 2
        skip += p[3] != 0
    exact += frames == -(-enc // 512)
    whole[h(b)].append(cu)
    first[h(b[:2048])].append(cu)
wk = {cu: k for k, v in whole.items() for cu in v}
print('waves', len(waves), 'packets', packets, 'nonzero skip', skip)
print('frames == ceil(SamplesEncoded/512):', exact, 'of', len(waves))
print('duplicate packets at another wave/position:', dup_packets)
print('byte-identical waves:', sum(len(v) for v in whole.values() if len(v) > 1), 'in groups:', sum(1 for v in whole.values() if len(v) > 1))
print('waves sharing a first packet:', sum(len(v) for v in first.values() if len(v) > 1),
      'groups differing later:', sum(1 for v in first.values() if len(v) > 1 and len({wk[c] for c in v}) > 1))

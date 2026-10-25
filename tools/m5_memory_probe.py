"""Read-only live metadata probe. Layout candidates require local validation.

Windows only. Guest arena base comes from the run's mapping log, never a guess.
usage: m5_memory_probe.py PID BASE_HEX OUTPUT_JSON [--watch DISCOVERY_JSON --seconds N]
No WriteProcessMemory, guest calls, or game-state changes.
"""
import argparse, ctypes, json, math, struct, time
import collections
from pathlib import Path
from ctypes import wintypes as wt

ap = argparse.ArgumentParser()
ap.add_argument('pid', type=int); ap.add_argument('base', type=lambda x:int(x,16)); ap.add_argument('output', type=Path)
ap.add_argument('--watch', type=Path); ap.add_argument('--seconds', type=int, default=10)
ap.add_argument('--regions', action='store_true')
ap.add_argument('--names', action='store_true')
a = ap.parse_args()
k = ctypes.WinDLL('kernel32', use_last_error=True)
k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]; k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.CloseHandle.argtypes = [wt.HANDLE]
class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress',ctypes.c_uint64),('AllocationBase',ctypes.c_uint64),('AllocationProtect',wt.DWORD),
                ('PartitionId',ctypes.c_ushort),('_pad',ctypes.c_ushort),('RegionSize',ctypes.c_uint64),
                ('State',wt.DWORD),('Protect',wt.DWORD),('Type',wt.DWORD),('_pad2',wt.DWORD)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k.VirtualQueryEx.restype = ctypes.c_size_t
h = k.OpenProcess(0x410, False, a.pid)
if not h: raise ctypes.WinError(ctypes.get_last_error())
def read(addr, length):
    b = ctypes.create_string_buffer(length); n = ctypes.c_size_t()
    if not k.ReadProcessMemory(h, a.base + addr, b, length, ctypes.byref(n)) or n.value != length: return None
    return b.raw
def words(addr, length=64):
    b = read(addr, length)
    return struct.unpack('>'+str(length//4)+'I', b) if b else None
diagnostics = collections.Counter()
examples = []
def actor(so):
    s = words(so)
    if not s or s[0] != 2: return None
    diagnostics['type2'] += 1
    p = words(s[1])
    std = words(p[1]) if p else None
    if p: diagnostics['data_readable'] += 1
    if std: diagnostics['std_readable'] += 1
    if std and so in std: diagnostics['std_contains_so'] += 1
    if std and len(examples)<20: examples.append(dict(so=hex(so), so_words=list(s), perso_words=list(p), std_words=list(std)))
    if not std or std[3] != so: return None
    m = read(s[8], 80)
    if not m: return None
    position = struct.unpack_from('>3f', m, 0x34)
    if not all(math.isfinite(x) and abs(x)<1e6 for x in position): return None
    return dict(so=f'{so:08X}', perso=f'{s[1]:08X}', std=f'{p[1]:08X}', matrix=f'{s[8]:08X}',
                object_types=list(std[:3]), matrix_type=struct.unpack_from('>I',m)[0], position=list(position))
try:
    if a.names:
        mbi = MBI()
        if not k.VirtualQueryEx(h, a.base+0x40000000, ctypes.byref(mbi), ctypes.sizeof(mbi)): raise ctypes.WinError()
        b = read(0x40000000, mbi.RegionSize)
        tables = {}
        for name in (b'Murfy\0',b'Camera\0',b'rayman\0',b'YLT_RaymanModel\0',b'GenCamera\0',b'Rayman\0',b'NIN_m_MurfyIntro10\0'):
            offset = b.find(name)
            while offset >= 0:
                needle = struct.pack('>I',0x40000000+offset)
                ref = b.find(needle)
                while ref >= 0:
                    entry = words(0x40000000+ref-12,20)
                    hdr = words(entry[2],12) if entry else None
                    if hdr and 0 < hdr[2] < 256:
                        names = []; p = hdr[0]; visited=set()
                        for _ in range(hdr[2]):
                            if p in visited: break
                            visited.add(p); w = words(p,20)
                            text = read(w[3],128) if w and w[2]==entry[2] else None
                            if not text: break
                            text = text.split(b'\0',1)[0]
                            if not text or any(c<32 or c>=127 for c in text): break
                            names.append(text.decode('ascii')); p=w[0]
                        if len(names)==hdr[2]: tables[f'{entry[2]:08X}']=names
                    ref = b.find(needle,ref+4)
                offset = b.find(name,offset+len(name))
        result = dict(pid=a.pid, base=hex(a.base), layout_status='CANDIDATE', name_tables=tables)
    elif a.watch:
        initial = json.loads(a.watch.read_text())['actors']
        samples = []
        end = time.monotonic() + a.seconds
        while time.monotonic() < end:
            samples.append(dict(time_ns=time.time_ns(), actors=[r for r in (actor(int(x['so'],16)) for x in initial) if r]))
            time.sleep(.1)
        result = dict(pid=a.pid, base=hex(a.base), layout_status='CANDIDATE', samples=samples)
    elif a.regions:
        found = {}; regions = []; addr = a.base + 0x10000000; end = a.base + 0x100000000
        while addr < end:
            mbi = MBI()
            if not k.VirtualQueryEx(h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)): break
            stop = min(mbi.BaseAddress + mbi.RegionSize, end)
            if mbi.State == 0x1000 and not mbi.Protect & 0x101:
                regions.append(dict(address=hex(addr-a.base),size=stop-addr,protection=mbi.Protect))
                for chunk in range(addr,stop,0x400000):
                    b = read(chunk-a.base,min(stop-chunk,0x400000))
                    if not b: continue
                    i = b.find(b'\0\0\0\2')
                    while i >= 0:
                        if i%4 == 0:
                            r = actor(chunk-a.base+i)
                            if r: found[r['so']] = r
                        i = b.find(b'\0\0\0\2',i+4)
            addr = stop
        result = dict(pid=a.pid, base=hex(a.base), layout_status='CANDIDATE', regions=regions, actors=list(found.values()))
    else:
        start = 0x82835C00
        b = read(start, 0x471C98)
        if not b: raise RuntimeError('Cannot read mapped image data')
        holders = {}
        for i,(p,) in enumerate(struct.iter_unpack('>I', b)):
            if 0x10000000 <= p < 0xF0000000 and p%4 == 0 and not 0x82000000 <= p < 0x82835C00:
                holders.setdefault(p, []).append(f'{start+i*4:08X}')
        # Bounded second pointer layer; a root commonly holds a container rather
        # than the actor itself. These are discovery candidates, not type proof.
        for p in list(holders):
            w = words(p)
            if not w: continue
            for q in w:
                if 0x10000000 <= q < 0xF0000000 and q%4 == 0 and not 0x82000000 <= q < 0x82835C00:
                    holders.setdefault(q, [f'via:{p:08X}'])
        found = {}
        for p, hs in holders.items():
            r = actor(p)
            if not r:
                w = words(p, 16)
                std = words(w[1],16) if w else None
                r = actor(std[3]) if std else None
            if r:
                r['holders'] = hs
                found[r['so']] = r
        result = dict(pid=a.pid, base=hex(a.base), layout_status='CANDIDATE', candidates=len(holders), actors=list(found.values()))
    result['diagnostics'] = dict(diagnostics)
    result['examples'] = examples
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(dict(actors=len(result.get('actors', [])), samples=len(result.get('samples', []))))
finally:
    k.CloseHandle(h)

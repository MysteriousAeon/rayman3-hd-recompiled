"""Read-only live AI/script probe. Layout candidates come from the pinned Raymap reader
(Perso/Brain/Mind/AIModel/Behavior/Script/ScriptNode, R3 Xbox 360 settings) and are
accepted only when the local chain validates (see checks below). Output is game-derived:
write it under private/ only.

usage: m5_script_probe.py PID BASE_HEX ACTORS_JSON OUTPUT_DIR [--watch SECONDS]
ACTORS_JSON is an m5_memory_probe.py --regions result. No WriteProcessMemory.
"""
import argparse, ctypes, json, re, struct, time
from ctypes import wintypes as wt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument('pid', type=int); ap.add_argument('base', type=lambda x: int(x, 16))
ap.add_argument('actors', type=Path); ap.add_argument('output', type=Path)
ap.add_argument('--watch', type=int, default=0)
ap.add_argument('--only', default='')
a = ap.parse_args()
k = ctypes.WinDLL('kernel32', use_last_error=True)
k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]; k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
h = k.OpenProcess(0x410, False, a.pid)
if not h: raise ctypes.WinError(ctypes.get_last_error())

def read(addr, length):
    if not 0x10000 <= addr < 0xFFFF0000: return None
    b = ctypes.create_string_buffer(length); n = ctypes.c_size_t()
    if not k.ReadProcessMemory(h, a.base + addr, b, length, ctypes.byref(n)) or n.value != length: return None
    return b.raw
def words(addr, count):
    b = read(addr, count * 4)
    return struct.unpack(f'>{count}I', b) if b else None
def cstr(addr, limit=0x100):
    b = read(addr, limit)
    if not b: return None
    b = b.split(b'\0', 1)[0]
    return b.decode('ascii') if b and all(32 <= c < 127 for c in b) else None

# Raymap tables are read from the pinned checkout, not copied into this repository.
src = (ROOT/'external/raymap/Assets/Scripts/OpenSpace/AI/AITypes/AITypes_R3.cs').read_text(encoding='utf-8', errors='replace')
def table(name):
    body = src[src.index(name + ' = new'):]
    body = body[body.index('{') + 1:body.index('};')]
    body = re.sub(r'//[^\n]*', '', body)
    return re.findall(r'"([^"]*)"|\b(?:[A-Za-z_]+\.)+([A-Za-z_0-9]+)', body)
T = {n: [x[0] or x[1] for x in table(n + 'Table' if n != 'nodeTypes' else n)]
     for n in ('keyword', 'operator', 'function', 'procedure', 'condition', 'field', 'metaAction', 'dsgVarType', 'nodeTypes')}
BY_TYPE = {'KeyWord': 'keyword', 'Condition': 'condition', 'Operator': 'operator', 'Function': 'function',
           'Procedure': 'procedure', 'MetaAction': 'metaAction', 'Field': 'field'}

behaviors = {}  # address -> name
def node_text(param, kind):
    nt = T['nodeTypes'][kind] if kind < len(T['nodeTypes']) else f'type{kind}'
    if nt in BY_TYPE:
        t = T[BY_TYPE[nt]]
        return f'{nt}:{t[param] if param < len(t) else param}'
    if nt == 'Real': return f'Real:{struct.unpack(">f", struct.pack(">I", param))[0]:g}'
    if nt == 'Constant': return f'Const:{struct.unpack(">i", struct.pack(">I", param))[0]}'
    if nt == 'String': return f'String:{cstr(param)!r}'
    if nt == 'ComportRef': return f'ComportRef:{behaviors.get(param, hex(param))}'
    if nt in ('DsgVarRef', 'DsgVar', 'DsgVarId'): return f'{nt}:{param}'
    return f'{nt}:{param:08X}'
def script(addr, limit=4000):
    out = []
    for i in range(limit):
        w = read(addr + i * 8, 8)
        if not w: break
        param, _, indent, kind = struct.unpack('>IHBB', w)
        if indent == 0 and i: break
        out.append('  ' * indent + node_text(param, kind))
    return out
def behavior(addr):
    name = cstr(addr)
    w = words(addr + 0x100, 3)
    if name is None or not w: return None
    scripts = words(w[0], w[2] >> 24) if w[2] >> 24 and w[0] else ()
    return dict(address=f'{addr:08X}', name=name, scripts=[f'{s:08X}' for s in scripts or ()], schedule=f'{w[1]:08X}')
def behavior_list(addr):
    w = words(addr, 2)
    if not w or not w[0] or not 0 < w[1] < 512: return []
    out = [behavior(w[0] + i * 0x10C) for i in range(w[1])]
    return [b for b in out if b]

def mind_of(perso):
    p = words(perso, 9)
    brain = words(p[3], 3) if p and p[3] else None
    return (brain[0], words(brain[0], 4)) if brain and brain[0] else (0, None)
def describe(actor):
    perso = int(actor['perso'], 16)
    mind_addr, mind = mind_of(perso)
    if not mind: return None
    model = words(mind[0], 5)
    if not model: return None
    normal, reflex = behavior_list(model[0]), behavior_list(model[1])
    for b in normal + reflex: behaviors[int(b['address'], 16)] = b['name']
    return dict(so=actor['so'], perso=actor['perso'], mind=f'{mind_addr:08X}', model=f'{mind[0]:08X}',
                intelligence=[f'{mind[1]:08X}', f'{mind[2]:08X}'], dsgmem=f'{mind[3]:08X}', normal=normal, reflex=reflex,
                macros=f'{model[3]:08X}')
def state(d):
    out = {}
    for label, addr in zip(('normal', 'reflex'), d['intelligence']):
        w = words(int(addr, 16), 6)
        if w: out[label] = behaviors.get(w[2], f'{w[2]:08X}')
    return out
def dsgvars(d):
    mem = words(int(d['dsgmem'], 16), 3)
    if not mem: return None
    var = words(words(mem[0], 1)[0], 4) if words(mem[0], 1) else None
    if not var: return None
    count = var[3] >> 24
    infos = [words(var[1] + i * 16, 4) for i in range(count)]
    buf = read(mem[2], var[2]) if var[2] < 0x10000 else None
    if not buf or any(i is None for i in infos): return None
    out = []
    for i, (off, typ, _, _) in enumerate(infos):
        end = min([x[0] for x in infos if x[0] > off] + [len(buf)])
        name = T['dsgVarType'][typ] if typ < len(T['dsgVarType']) else str(typ)
        out.append((i, name, buf[off:end].hex()))
    return out

actors = json.loads(a.actors.read_text())['actors']
a.output.mkdir(parents=True, exist_ok=True)
described = [d for d in map(describe, actors) if d]
summary = []
for d in described:
    current = state(d)
    names = [b['name'] for b in d['normal']]
    tag = (names[0].split('\\')[1] if names and '\\' in names[0] else d['perso'])
    summary.append(dict(so=d['so'], perso=d['perso'], model=tag, normal=len(d['normal']), reflex=len(d['reflex']), current=current))
    if a.only and a.only.lower() not in tag.lower(): continue
    lines = [json.dumps(dict(d, normal=None, reflex=None, current=current))]
    v = dsgvars(d)
    for item in v or (): lines.append('dsgvar %d %s %s' % item)
    for group in ('normal', 'reflex'):
        for b in d[group]:
            lines.append(f'## {group} {b["address"]} {b["name"]}')
            for s in b['scripts']:
                lines.append(f'# script {s}')
                lines += script(int(s, 16))
    macros = words(int(d['macros'], 16), 2)
    for i in range(macros[1] >> 24 if macros and macros[0] else 0):
        m = words(macros[0] + i * 8, 2)  # Xbox 360: no name field, two script pointers
        lines.append(f'## macro {macros[0] + i * 8:08X}')
        target = words(m[0], 1) if m and m[0] else None  # Macro -> Script -> nodes
        lines += script(target[0]) if target and target[0] else []
    (a.output/f'{tag}_{d["perso"]}.txt').write_text('\n'.join(lines) + '\n')
(a.output/'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
print(json.dumps(dict(actors=len(actors), with_mind=len(described))))
if a.watch:
    previous = {}; end = time.monotonic() + a.watch
    with open(a.output/'watch.log', 'a') as log:
        while time.monotonic() < end:
            for d in described:
                if a.only and a.only.lower() not in json.dumps(d['normal'][:1]).lower(): continue
                now = (state(d), dsgvars(d))
                if previous.get(d['perso']) != now:
                    old = previous.get(d['perso'])
                    changed = [x for x, y in zip(now[1] or (), (old[1] if old and old[1] else ())) if x != y] if old else []
                    log.write(json.dumps(dict(t=time.time(), perso=d['perso'], state=now[0], changed=changed)) + '\n'); log.flush()
                    previous[d['perso']] = now
            time.sleep(0.2)
k.CloseHandle(h)

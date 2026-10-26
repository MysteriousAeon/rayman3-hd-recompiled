"""Read-only live AI/script probe. Layout candidates came from the pinned Raymap reader
(Perso/Brain/Mind/AIModel/Behavior/Script/ScriptNode, R3 Xbox 360 settings) and were
accepted only when the local chain validated (RE_NOTES "M5"). Output is game-derived:
write it under private/ only.

Output format 2 (D-113 step 1): nothing is read from a Raymap checkout. Script nodes are printed as
`k<type byte, 2 hex>:<parameter, 8 hex>` and designer variables as `dsgvar <n> t<type> <hex>`; step 1 printed
nothing else, as the meaning of the type numbers was not yet established from the target. Behaviour names are
the title's own strings. Format 1 files (older scans) carry Raymap's names instead and have no "format" key.

D-113 step 2 (`"spec": "D-113-2"` in each file's first line): the raw `k<type>:<parameter>` stays first on every
line and a label follows only for the node types the title's script interpreter establishes (evaluator table
82839838, private spec of E-270; status of each label in OUTPUT_DIR/labels.json). Procedure calls (type 04) and
value calls (type 03) are named by their table index, `procA#<hex>` / `callB#<hex>`, with the handler address read
from the decrypted default image; designer variables of type 21 hold a text handle (`text`, or `text:none` for -1).
Text handles are printed, not resolved (m14_script_scan.py resolves them in the live run). Every other type stays
numeric.

usage: m5_script_probe.py PID BASE_HEX ACTORS_JSON OUTPUT_DIR [--watch SECONDS]
       m5_script_probe.py 0 0 ACTORS_JSON OUTPUT_DIR --snapshot SNAPSHOT_DIR   (offline, m7 snapshot layout)
ACTORS_JSON is an m5_memory_probe.py --regions result. No WriteProcessMemory.
"""
import argparse, ctypes, hashlib, json, struct, sys, time
from ctypes import wintypes as wt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMAT, SPEC = 2, 'D-113-2'
# Constants of this build (E-270), checked against the decrypted default image before they are used.
IMAGE, IMAGE_BASE = ROOT/'private/work/default_image.bin', 0x82000000
IMAGE_SHA256 = '94517a5843dcc22bf7a28646ad02e7e4d0ea434e2fe991ac4b00344b673f0847'
PROC_A, PROC_A_COUNT = 0x828398E8, 0x36F   # node type 04: {handler, flag} per procedure id
CALL_B, CALL_B_COUNT = 0x8283B460, 0x1C4   # node type 03: {handler, flag} per value-call id
TEXT_VAR_TYPE = 21                          # designer-variable type of a text handle (reader 822680D0)
# node type -> (label, evidence status); types not listed stay numeric
LABELS = {0x01: ('boolcall', 'VERIFIED'), 0x03: ('callB', 'VERIFIED'), 0x04: ('procA', 'VERIFIED'),
          0x0A: ('dsgvar', 'VERIFIED read path'), 0x0B: ('dsgvar', 'VERIFIED'), 0x0C: ('int', 'VERIFIED'),
          0x0D: ('real', 'VERIFIED'), 0x10: ('vec3', 'VERIFIED'), 0x14: ('str', 'VERIFIED'),
          0x17: ('actor', 'SUPPORTED'), 0x1C: ('text', 'VERIFIED'), 0x1D: ('behaviour', 'SUPPORTED'),
          0x29: ('macro', 'VERIFIED')}
ap = argparse.ArgumentParser()
ap.add_argument('pid', type=int); ap.add_argument('base', type=lambda x: int(x, 16))
ap.add_argument('actors', type=Path); ap.add_argument('output', type=Path)
ap.add_argument('--watch', type=int, default=0)
ap.add_argument('--only', default='')
ap.add_argument('--snapshot', type=Path, help='read guest memory from a snapshot (index.json + <ADDRESS>.bin) instead')
a = ap.parse_args()
if a.snapshot:
    if a.watch: ap.error('--watch needs a live process')
    regions = [(r['address'], (a.snapshot/f"{r['address']:08X}.bin").read_bytes())
               for r in json.loads((a.snapshot/'index.json').read_text())['regions']]
else:
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]; k.OpenProcess.restype = wt.HANDLE
    k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    h = k.OpenProcess(0x410, False, a.pid)
    if not h: raise ctypes.WinError(ctypes.get_last_error())

def read(addr, length):
    if not 0x10000 <= addr < 0xFFFF0000: return None
    if a.snapshot:
        for start, data in regions:
            if start <= addr and addr + length <= start + len(data): return data[addr - start:addr - start + length]
        return None
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

image = IMAGE.read_bytes() if IMAGE.is_file() else None
if image is not None and hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
    raise SystemExit(f'{IMAGE}: not the image the D-113-2 tables were established on')
if image is None:
    print(f'warning: {IMAGE} absent: procedure and value-call handlers are not printed', file=sys.stderr)
def handler(base, count, index):
    if index >= count: return 'out-of-range'
    return f'{struct.unpack_from(">I", image, base - IMAGE_BASE + 8 * index)[0]:08X}' if image else None

behaviors = {}  # address -> name
persos, macro_set = set(), set()
def node_label(param, kind):
    if kind == 0x01: return f'boolcall#{param:X}'
    if kind in (0x03, 0x04):
        h = handler(CALL_B, CALL_B_COUNT, param) if kind == 0x03 else handler(PROC_A, PROC_A_COUNT, param)
        return f'{LABELS[kind][0]}#{param:X}' + (f' {h}' if h else '')
    if kind in (0x0A, 0x0B): return f'dsgvar#{param & 0xFF}'
    if kind == 0x0C: return f'int:{struct.unpack(">i", struct.pack(">I", param))[0]}'
    if kind == 0x0D: return f'real:{struct.unpack(">f", struct.pack(">I", param))[0]:g}'
    if kind == 0x10: return 'vec3'
    if kind == 0x14:
        s = cstr(param)
        return f'str:{s!r}' if s is not None else 'str:?'
    if kind == 0x1C: return 'text:none' if param == 0xFFFFFFFF else 'text'
    if kind == 0x17 and param in persos: return 'actor'
    if kind == 0x1D and param in behaviors: return f'behaviour:{behaviors[param]}'
    if kind == 0x29 and param in macro_set: return 'macro'
    return None
def node_text(param, kind):
    label = node_label(param, kind)
    return f'k{kind:02X}:{param:08X}' + (f' {label}' if label else '')
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
        out.append((i, f't{typ}', buf[off:end].hex()))
    return out

actors = json.loads(a.actors.read_text())['actors']
a.output.mkdir(parents=True, exist_ok=True)
described = [d for d in map(describe, actors) if d]
persos.update(int(x['perso'], 16) for x in actors)
macro_lists = {}
for d in described:
    macros = words(int(d['macros'], 16), 2)
    macro_lists[d['perso']] = [macros[0] + i * 8 for i in range(macros[1] >> 24)] if macros and macros[0] else []
    macro_set.update(macro_lists[d['perso']])
(a.output/'labels.json').write_text(json.dumps(dict(
    format=FORMAT, spec=SPEC, image_sha256=IMAGE_SHA256 if image else None,
    labels={f'{t:02X}': dict(label=n, status=s) for t, (n, s) in LABELS.items()},
    numeric='every other node type; designer-variable types other than 21',
    notes=['procA / callB: table index (hex), then the handler address from the image (absent without the image)',
           'actor / behaviour / macro: only when the parameter is in the decoded set of this run, else numeric',
           f'dsgvar t{TEXT_VAR_TYPE}: text handle; "text" = a handle, "text:none" = -1; text content is not resolved here']),
    indent=1) + '\n')
summary = []
for d in described:
    current = state(d)
    names = [b['name'] for b in d['normal']]
    tag = (names[0].split('\\')[1] if names and '\\' in names[0] else d['perso'])
    summary.append(dict(so=d['so'], perso=d['perso'], model=tag, normal=len(d['normal']), reflex=len(d['reflex']), current=current))
    if a.only and a.only.lower() not in tag.lower(): continue
    lines = [json.dumps(dict(d, normal=None, reflex=None, current=current, format=FORMAT, spec=SPEC))]
    v = dsgvars(d)
    for item in v or ():
        text = '' if item[1] != f't{TEXT_VAR_TYPE}' else ' text:none' if item[2][:8] == 'ffffffff' else ' text'
        lines.append('dsgvar %d %s %s' % item + text)
    for group in ('normal', 'reflex'):
        for b in d[group]:
            lines.append(f'## {group} {b["address"]} {b["name"]}')
            for s in b['scripts']:
                lines.append(f'# script {s}')
                lines += script(int(s, 16))
    for address in macro_lists[d['perso']]:
        m = words(address, 2)  # Xbox 360: no name field, two script pointers
        lines.append(f'## macro {address:08X}')
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
if not a.snapshot: k.CloseHandle(h)

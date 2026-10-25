#!/usr/bin/env python3
"""Milestone 3: indirect-target completeness + exception-representation audit.

Compares every code address that the image can materialise as a pointer
(data-section words, and lis+addi/ori constants synthesised by instructions)
against the generated runtime dispatch table, and classifies the rest.
Also checks that every exception funclet named by the metadata is a generated
function and every inline __except body is translated inside its owner.
Metadata only: addresses, counts, classifications.

usage: m3_target_audit.py <generated_dir> <image> <pe_analysis.json> <eh_map.json> <out.json>
"""
import sys, glob, re, json, struct, bisect, collections

G, imgp, pep, ehp, outp = sys.argv[1:6]
img = open(imgp, 'rb').read(); PE = json.load(open(pep)); BASE = int(PE['image_base'], 16)
EH = json.load(open(ehp))
be = lambda va: struct.unpack_from('>I', img, va - BASE)[0]
secs = {s['name']: (int(s['va'], 16), int(s['vsize'], 16), s) for s in PE['sections']}
code_secs = [(va, sz) for va, sz, s in secs.values() if s['code']]
data_secs = [(n, va, min(sz, int(s['rawsize'], 16) or sz)) for n, (va, sz, s) in secs.items()
             if not s['code'] and n in ('.rdata', '.data', 'BINKCONS', 'BINKDATA', 'RADCONST', 'RADDATA', '.XBMOVIE')]
in_code = lambda a: any(va <= a < va + sz for va, sz in code_secs)

# ---- generated output: dispatch table and per-address ownership -------------
table = {}
for m in re.finditer(r'\{ 0x([0-9A-F]{8}), (\w+) \}', open(G + '/r3hd_init.cpp').read()):
    table[int(m.group(1), 16)] = m.group(2)
named = {v: k for k, v in table.items()}
owner, labels = {}, set()
rn = re.compile(r'^DEFINE_REX_FUNC\((\w+)\)'); rl = re.compile(r'^\s*loc_([0-9A-F]{8}):'); ri = re.compile(r'^\s+// [a-z.]')
for f in glob.glob(G + '/r3hd_recomp.*.cpp'):
    pc = fn = None
    for l in open(f, encoding='utf-8', errors='replace'):
        m = rn.match(l)
        if m:
            fn = pc = named.get(m.group(1)); continue
        m = rl.match(l)
        if m:
            pc = int(m.group(1), 16); labels.add(pc); continue
        if pc is not None and ri.match(l):
            owner[pc] = fn; pc += 4
thunks = {int(e['thunk'], 16): e['name'] for e in PE['imports'] if e.get('thunk')}

# ---- .pdata -------------------------------------------------------------------
p0, pn, _ = secs['.pdata']
pd = []
for off in range(0, pn, 8):
    b, w = be(p0 + off), be(p0 + off + 4)
    if b: pd.append((b, ((w >> 8) & 0x3FFFFF) * 4))
pstarts = [b for b, _ in pd]
def pdata_owner(a):
    i = bisect.bisect_right(pstarts, a) - 1
    return pd[i][0] if i >= 0 and a < pd[i][0] + pd[i][1] else None

# ---- exception metadata sets ---------------------------------------------------
H = lambda s: int(s, 16) if isinstance(s, str) else s
seh_bodies, seh_filters, seh_finally, scope_edges = {}, set(), set(), set()
for r in EH['seh']:
    for s in r['scopes']:
        scope_edges.update((H(s['begin']), H(s['end'])))
        if s['kind'] == 'finally': seh_finally.add(H(s['filter']))
        else:
            seh_filters.add(H(s['filter'])); seh_bodies[H(s['target'])] = H(r['function'])
cxx_actions, cxx_catches, cxx_ips = set(), set(), set()
rd0, rdn, _ = secs['.rdata']
for r in EH['cxx']:
    cxx_actions.update(H(a) for a in r['unwind_actions'] if H(a))
    cxx_catches.update(H(c['handler']) for c in r['catches'] if H(c['handler']))
    ipm, n = H(r['ip_map']), H(r['ip_entries'])
    if ipm and rd0 <= ipm < rd0 + rdn:
        cxx_ips.update(be(ipm + i * 8) for i in range(n))

# ---- jump tables stored as absolute words (in .text or data) --------------------
# A word belongs to an absolute jump table when it sits in a run of >=3 code
# pointers that all land inside one .pdata function away from its start.
def classify_data_pointer(holder, target):
    po = pdata_owner(target)
    if po is None or po == target: return None
    run = 1
    for d in (-4, 4):
        a = holder + d
        while BASE <= a < BASE + len(img) - 4 and in_code(be(a)) and pdata_owner(be(a)) == po:
            run += 1; a += d
    return 'jump_table_entry' if run >= 3 else None

# ---- source 1: pointers stored in data sections ----------------------------------
data_refs = collections.defaultdict(list)
for n, va, sz in data_secs:
    for a in range(va, va + sz - 3, 4):
        w = be(a)
        if in_code(w) and not w & 3: data_refs[w].append(a)
# pointers stored inside code sections (absolute jump tables kept in .text)
text_refs = collections.defaultdict(list)
for va, sz in code_secs:
    for a in range(va, va + sz - 3, 4):
        if a in owner: continue
        w = be(a)
        if in_code(w) and not w & 3: text_refs[w].append(a)

# ---- source 2: lis + addi/ori constants synthesised by instructions --------------
synth = collections.defaultdict(list)   # target -> [(site, use)]
def scan_synth():
    for va, sz in code_secs:
        reg = {}                         # reg -> (hi_value, site)
        for a in range(va, va + sz - 3, 4):
            if a not in owner: reg.clear(); continue
            w = be(a); op = w >> 26; rd = (w >> 21) & 31; ra = (w >> 16) & 31; imm = w & 0xFFFF
            simm = imm - 0x10000 if imm & 0x8000 else imm
            if op == 15 and ra == 0:     # lis
                reg[rd] = ((imm << 16) & 0xFFFFFFFF, a); continue
            if op == 14 and ra in reg:   # addi rd, ra, lo
                v = (reg[ra][0] + simm) & 0xFFFFFFFF
                if in_code(v) and not v & 3: synth[v].append((a, rd))
                if rd != ra: pass
                reg.pop(rd, None); continue
            if op == 24 and rd in reg:   # ori ra, rs(=rd field), lo
                v = reg[rd][0] | imm
                if in_code(v) and not v & 3: synth[v].append((a, ra))
                reg.pop(ra, None); continue
            # any other write to a tracked register kills it (conservative: GPR dest forms)
            if op in (10, 11, 32, 33, 34, 35, 40, 41, 42, 43, 46, 48, 50, 58):   # cmp/loads: load dests
                if op >= 32: reg.pop(rd, None)
            elif op == 31:
                xo = (w >> 1) & 0x3FF
                if xo in (444, 28, 316, 124, 476, 60, 412, 284, 24, 536, 792, 824, 26, 922, 954, 986):  # logical: dest = ra
                    reg.pop(ra, None)
                else: reg.pop(rd, None)
            elif op in (7, 8, 12, 13, 14, 15): reg.pop(rd, None)
            elif op in (20, 21, 23, 24, 25, 26, 27, 28, 29, 30): reg.pop(ra, None)
            if op in (16, 18, 19):       # control flow: block boundary
                if op == 18 and w & 1: # bl: volatile registers die
                    for r in list(reg):
                        if r < 14: reg.pop(r)
                elif not (op == 16): reg.clear()
            if a + 4 in labels: reg.clear()
scan_synth()

def use_kind(site, r, target):
    """How the synthesised address is consumed in the next few instructions."""
    for a in range(site + 4, site + 4 * 10, 4):
        w = be(a); op = w >> 26; rd = (w >> 21) & 31; ra = (w >> 16) & 31; rb = (w >> 11) & 31
        xo = (w >> 1) & 0x3FF
        if op == 31 and xo in (23, 279, 87, 343, 599, 535, 55, 119, 311, 375) and r in (ra, rb): return 'table_base_load'   # l*zx / lf*x
        if op in (32, 33, 34, 35, 40, 41, 42, 43, 48, 49, 50, 51, 58) and ra == r: return 'data_load'
        if op == 31 and xo == 266 and r in (ra, rb): return 'add_then_branch'     # add (offset jump table)
        if op == 31 and xo == 467 and rd == r and ((w >> 11) & 0x3FF) == 0x120: return 'mtctr'
        if op == 31 and xo == 467 and rd == r and ((w >> 11) & 0x3FF) == 0x100: return 'mtlr'
        if op in (36, 37, 62) and rd == r: return 'stored'
        if op in (16, 18, 19): return 'passed_or_live_at_branch'
    return 'other'

# ---- classification ---------------------------------------------------------------
def classify(target):
    if target in table: return 'function_entry'
    if target in thunks: return 'import_thunk'
    if target in seh_bodies: return 'seh_except_body'
    if target in owner: return 'inside_translated_function'
    return 'untranslated'

report = dict(dispatch_table_entries=len(table), translated_words=len(owner))
dsum, d_missing, d_inside = collections.Counter(), [], collections.Counter()
for t, holders in data_refs.items():
    c = classify(t)
    if c == 'inside_translated_function':
        k = ('seh_scope_edge' if t in scope_edges else 'cxx_ip_state_entry' if t in cxx_ips else
             classify_data_pointer(holders[0], t) or
             ('coincidental_or_embedded' if not any(pdata_owner(t) for _ in (0,)) else 'mid_function_other'))
        if t == 0x822D93E8: k = 'coincidental_value_in_constant_table'   # holder 0x8202DDAC sits among non-pointer constants
        d_inside[k] += 1
        if k == 'mid_function_other': d_missing.append(dict(target=f'0x{t:08X}', holders=[f'0x{h:08X}' for h in holders[:3]], owner=f'0x{owner[t]:08X}'))
    dsum[c] += 1
report['data_pointers'] = dict(distinct_targets=len(data_refs), by_class=dict(dsum), inside_breakdown=dict(d_inside),
                               untranslated=[f'0x{t:08X}' for t in sorted(data_refs) if classify(t) == 'untranslated'],
                               mid_function_other=d_missing[:400])
# C++ catch funclets return their continuation address in r3 (lis r3 / addi r3,r3).
cxx_continuations = set()
for h in cxx_catches:
    hi = None
    for i in range(400):
        w = be(h + i * 4); op = w >> 26; rd = (w >> 21) & 31; ra = (w >> 16) & 31; imm = w & 0xFFFF
        if op == 15 and ra == 0 and rd == 3: hi = (imm << 16) & 0xFFFFFFFF
        elif op == 14 and rd == 3 and ra == 3 and hi is not None:
            cxx_continuations.add((hi + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF); hi = None
        if w in (0x4E800020, 0): break
unwind_callees = {0x826BF880, 0x826B8828} | {t for t, n in thunks.items() if n == 'RtlUnwind'}
def feeds_unwind(site):
    for a in range(site, site + 4 * 8, 4):
        w = be(a)
        if w >> 26 == 18 and w & 1:
            d = w & 0x03FFFFFC
            return ((a + (d - 0x04000000 if d & 0x02000000 else d)) & 0xFFFFFFFF) in unwind_callees
    return False
ssum, s_inside, s_cases = collections.Counter(), collections.Counter(), []
for t, sites in synth.items():
    c = classify(t)
    ssum[c] += 1
    if c in ('inside_translated_function', 'untranslated', 'seh_except_body'):
        uses = collections.Counter(use_kind(s, r, t) for s, r in sites)
        k = uses.most_common(1)[0][0]
        if t in cxx_continuations: k = 'cxx_catch_continuation_label'
        elif c == 'inside_translated_function' and any(feeds_unwind(s) for s, _ in sites): k = 'same_function_unwind_target_label'
        s_inside[(c, k)] += 1
        s_cases.append(dict(target=f'0x{t:08X}', cls=c, uses=dict(uses), sites=[f'0x{s:08X}' for s, _ in sites[:3]],
                            owner=(f'0x{owner[t]:08X}' if owner.get(t) else None),
                            is_label=t in labels))
EXPLAINED = ('table_base_load', 'add_then_branch', 'cxx_catch_continuation_label', 'same_function_unwind_target_label')
report['unclassified_synthesised'] = [c for c in s_cases if not any(
    (max(c['uses'], key=c['uses'].get) == e) for e in EXPLAINED[:2]) and
    int(c['target'], 16) not in cxx_continuations and
    not (c['cls'] == 'inside_translated_function' and any(feeds_unwind(int(s, 16)) for s in c['sites']))]
report['cxx_catch_continuations'] = dict(distinct=len(cxx_continuations),
    untranslated=sorted(f'0x{a:08X}' for a in cxx_continuations if a not in owner))
report['synthesised_pointers'] = dict(distinct_targets=len(synth), by_class=dict(ssum),
                                      non_entry_breakdown={f'{a}/{b}': n for (a, b), n in s_inside.items()},
                                      non_entry_cases=s_cases)
tsum = collections.Counter(classify(t) for t in text_refs)
report['text_embedded_pointers'] = dict(distinct_targets=len(text_refs), by_class=dict(tsum),
                                        untranslated=[f'0x{t:08X}' for t in sorted(text_refs) if classify(t) == 'untranslated'][:50])

# ---- exception representation check --------------------------------------------------
def missing(s): return sorted(f'0x{a:08X}' for a in s if a not in table)
report['exception_representation'] = dict(
    seh_filter_funclets=len(seh_filters), seh_filter_missing=missing(seh_filters),
    seh_finally_funclets=len(seh_finally), seh_finally_missing=missing(seh_finally),
    seh_bodies=len(seh_bodies),
    seh_bodies_translated_in_owner=sum(1 for b, f in seh_bodies.items() if owner.get(b) == f),
    seh_bodies_registered_as_functions=sorted(f'0x{b:08X}' for b in seh_bodies if b in table),
    seh_bodies_untranslated=sorted(f'0x{b:08X}' for b in seh_bodies if b not in owner),
    seh_bodies_translated_elsewhere=sorted(f'0x{b:08X}' for b, f in seh_bodies.items() if b in owner and owner[b] != f),
    cxx_unwind_actions=len(cxx_actions), cxx_unwind_actions_missing=missing(cxx_actions),
    cxx_catch_funclets=len(cxx_catches), cxx_catch_missing=missing(cxx_catches))
json.dump(report, open(outp, 'w'), indent=1)
show = json.loads(json.dumps(report))
show['synthesised_pointers'].pop('non_entry_cases'); pass; show['data_pointers'].pop('mid_function_other')
print(json.dumps(show, indent=1))

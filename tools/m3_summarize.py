"""Metadata-only summary of a Milestone 3 run directory. Never copies game data, shader
microcode or frame pixels: only counts, addresses, hashes and file names.
usage: m3_summarize.py <run_dir> <eh_map.json> <out.json>"""
import collections, hashlib, json, re, sys
from pathlib import Path

run, ehp, outp = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
# The runtime rotates at 5 MB: runtime.N.log (oldest = highest N) ... runtime.1.log, runtime.log.
parts = sorted(run.glob('runtime.*.log'), key=lambda q: -int(q.name.split('.')[1])) + [run / 'runtime.log']
log = ''.join(q.read_text(errors='replace') for q in parts)
lines = log.splitlines()
EH = json.load(open(ehp))
H = lambda s: int(s, 16) if isinstance(s, str) else s
seh = sorted((H(r['function']), H(r['end']), r) for r in EH['seh'])
cxx = sorted((H(r['function']), H(r['end']), r) for r in EH['cxx'])


def scope_for(pc):
    """Map a guest return address to the enclosing EH function and its active SEH scopes."""
    for table, kind in ((seh, 'seh'), (cxx, 'cxx')):
        for b, e, r in table:
            if b <= pc < e:
                out = dict(kind=kind, function=f'0x{b:08X}', pdata=r['pdata'], handler=r['handler'], table=r['data'])
                if kind == 'seh':
                    out['active_scopes'] = [
                        dict(kind=s['kind'], begin=s['begin'], end=s['end'], filter=s['filter'], target=s['target'])
                        for s in r['scopes'] if H(s['begin']) <= pc - 4 < H(s['end'])]
                return out
    return None


def fields(prefix):
    out = []
    for l in lines:
        i = l.find(prefix)
        if i >= 0:
            out.append(dict(re.findall(r'(\w+)=(\S+)', l[i + len(prefix):])))
    return out


raises = fields('M3 guest_raise ')
raise_groups = collections.OrderedDict()
for r in raises:
    g = raise_groups.setdefault((r['code'], r['lr'], r['chain']), dict(
        code=r['code'], flags=r['flags'], nparams=r['nparams'], raise_site_lr=r['lr'],
        caller_chain=r['chain'].split(','), count=0))
    g['count'] += 1
for g in raise_groups.values():
    g['frames'] = [dict(return_address=a, eh=scope_for(int(a, 16))) for a in g['caller_chain'] if int(a, 16)]

imports = {}
for l in lines:
    m = re.search(r'M2 import=(?:__imp__)?(\S+) stub=(\w+) count=(\d+)', l)
    if m:
        e = imports.setdefault(m.group(1), dict(stub=m.group(2) == 'true', lower_bound=0))
        e['lower_bound'] = max(e['lower_bound'], int(m.group(3)))
swaps, captures, shaders = fields('M3 swap '), fields('M3 frame_capture '), fields('M3 shader_distinct ')
draws, copies, presents = fields('M3 draw '), fields('M3 copy '), fields('M3 host_present ')
probes = collections.OrderedDict()
for p in fields('M3 probe '):
    probes[p['function']] = dict(count_lower_bound=int(p['count']),
                                 first_lr=probes.get(p['function'], {}).get('first_lr', p['lr']))
opens = collections.Counter(re.findall(r'M2 vfs_open path=(.*?) result=(\w+)', log))
SWAP_KEYS = ('frontbuffer', 'packet', 'source', 'dxgi_format', 'guest_format', 'output', 'display')
swap_configs = collections.OrderedDict()
for s in swaps:
    swap_configs.setdefault(tuple((k, s.get(k)) for k in SWAP_KEYS if k != 'frontbuffer'), s['count'])
faults = run / 'm2_faults.log'
summary = dict(
    run=json.loads((run / 'run.json').read_text(encoding='utf-8-sig')),
    runtime_log_parts=[q.name for q in parts], runtime_log_sha256=hashlib.sha256(log.encode(errors='replace')).hexdigest(),
    log_lines=len(lines),
    entrypoint_executed='M2 guest_entry_executed pc=820E13F8' in log,
    runtime_initialized='M2 runtime_initialized' in log,
    fatal_lines=[l for l in lines if '[critical]' in l or '[FATAL]' in l][:20],
    host_seh_catch_lines=sorted(set(re.findall(r'SEH exception caught in sub_[0-9A-F]{8}', log))),
    semantic_stub_lines=sorted(set(re.sub(r'^.*?\] \[t\d+\] ', '', l) for l in lines if '[STUB]' in l))[:40],
    macro_stub_hits={n: e for n, e in imports.items() if e['stub']},
    invalid_indirect_lines=[l for l in lines if re.search(r'[Ii]nvalid.*(indirect|function)|Unresolved indirect', l)][:20],
    trap_lines=dict(collections.Counter(re.findall(r'(tw/td trap hit \(type \d+\)|Unknown trap type \d+)', log))),
    imports_reached=len(imports), imports=sorted(imports),
    warning_error_census=dict(collections.Counter(
        re.sub(r'[0-9A-Fa-f]{6,}|\d+', '#', m.group(1) + ' ' + m.group(2))[:110]
        for m in re.finditer(r'\[(warning|error|critical)\] \[\w+\] \[t\d+\] (.*)', log)).most_common(25)),
    guest_raise_events=len(raises), guest_raise_groups=list(raise_groups.values()),
    first_chance_records=dict(collections.Counter(re.findall(r'^M2 exception code=(\w+)', faults.read_text(), re.M)))
    if faults.exists() else {},
    probes=probes,
    ring_initialized=re.findall(r'M2 ring_initialized (.*)', log),
    gpu=dict(
        swap_count=max([int(s['count']) for s in swaps] or [0]),
        first_swap=swaps[0] if swaps else None, last_swap=swaps[-1] if swaps else None,
        swap_configs=[dict(first_seen_at_swap=n, **dict(k)) for k, n in swap_configs.items()],
        first_draw=draws[0] if draws else None, last_draw_logged=draws[-1] if draws else None,
        first_copy=copies[0] if copies else None, last_copy_logged=copies[-1] if copies else None,
        render_target_register_sets=sorted({(d['surface_info'], d['color_info'], d['depth_info']) for d in draws}),
        distinct_shaders=len(shaders),
        distinct_shaders_by_type=dict(collections.Counter(s['type'] for s in shaders)),
        shader_packets=max([int(s['packets']) for s in shaders] or [0]),
        host_swapchain=fields('M3 host_swapchain_create '),
        host_presents=presents[-1] if presents else None,
        host_present_failures=[p for p in presents if p['hresult'] != '00000000'],
        frame_captures=captures, frame_files=sorted(p.name for p in run.glob('m3_frame_*.bmp'))),
    file_opens={f'{p} -> {r}': n for (p, r), n in sorted(opens.items())},
    audio=dict(
        xaudio_submit_lower_bound=imports.get('XAudioSubmitRenderDriverFrame', {}).get('lower_bound', 0),
        xma_create_context=imports.get('XMACreateContext'), xma_release_context=imports.get('XMAReleaseContext'),
        xma_log_lines=len([l for l in lines if re.search(r'\bXMA', l)]),
        apu_debug_lines=len([l for l in lines if '[apu]' in l])),
    bink=dict(code_entered='M2 bink_code_entered' in log,
              movies_opened=[p for (p, r) in opens if p.lower().endswith('.bik') and r == '00000000']),
    thread_names=sorted(set(re.findall(r'SetThreadName\(\d+, (.*?)\)', log))),
)
outp.parent.mkdir(parents=True, exist_ok=True)
outp.write_text(json.dumps(summary, indent=1) + '\n')
g = summary['gpu']
print(json.dumps(dict(
    entry=summary['entrypoint_executed'], fatal=len(summary['fatal_lines']), seh=summary['host_seh_catch_lines'],
    stubs=list(summary['macro_stub_hits']), semantic_stubs=summary['semantic_stub_lines'][:5],
    invalid_indirect=len(summary['invalid_indirect_lines']),
    raises=[(x['code'], x['count']) for x in summary['guest_raise_groups']], imports=summary['imports_reached'],
    swaps=g['swap_count'], draws=g['last_draw_logged'] and g['last_draw_logged']['count'],
    copies=g['last_copy_logged'] and g['last_copy_logged']['count'], shaders=g['distinct_shaders'],
    packets=g['shader_packets'], presents=g['host_presents'], captures=len(g['frame_captures']),
    probes={k: v['count_lower_bound'] for k, v in probes.items()}, bik=summary['bink']['movies_opened']), indent=1))

#!/usr/bin/env python3
"""Milestone 3: map the exception model of the decrypted image (metadata only).

Reads .pdata, the per-function handler/data words stored at begin-8/begin-4,
MSVC SEH scope tables and C++ FuncInfo records. Emits addresses, counts and
structural classifications only: no code bytes.

usage: m3_eh_map.py <image> <pe_analysis.json> --out <json>
"""
import argparse, collections, json, struct

BASE = 0x82000000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image'); ap.add_argument('pe'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    img = open(a.image, 'rb').read()
    pe = json.load(open(a.pe))
    be = lambda va: struct.unpack_from('>I', img, va - BASE)[0]
    secs = {s['name']: (int(s['va'], 16), int(s['vsize'], 16)) for s in pe['sections']}
    code = [secs[n] for n in ('.text', 'BINK', 'RADCODE')]
    in_code = lambda va: any(b <= va < b + s for b, s in code)
    rd0, rdn = secs['.rdata']
    in_rdata = lambda va: rd0 <= va < rd0 + rdn
    p0, pn = secs['.pdata']
    funcs = []
    for off in range(0, pn, 8):
        begin, w = be(p0 + off), be(p0 + off + 4)
        if not begin:
            continue
        # IMAGE_CE_RUNTIME_FUNCTION, big-endian bitfield (see E-04 caveat).
        funcs.append(dict(pdata=p0 + off, begin=begin, prolog=(w & 0xFF) * 4,
                          length=((w >> 8) & 0x3FFFFF) * 4, is32=(w >> 30) & 1, eh=w >> 31))
    starts = sorted(f['begin'] for f in funcs)
    by_begin = {f['begin']: f for f in funcs}
    import bisect

    def enclosing(va):
        i = bisect.bisect_right(starts, va) - 1
        if i < 0:
            return None
        f = by_begin[starts[i]]
        return f if va < f['begin'] + f['length'] else None

    handlers = collections.Counter()
    seh, cxx, other = [], [], []
    for f in funcs:
        if not f['eh']:
            continue
        handler, data = be(f['begin'] - 8), be(f['begin'] - 4)
        handlers[handler] += 1
        rec = dict(function=f['begin'], end=f['begin'] + f['length'], pdata=f['pdata'],
                   handler=handler, data=data)
        if not in_rdata(data):
            rec['kind'] = 'no_table'; other.append(rec); continue
        first = be(data)
        if first & 0xFFFFFFF0 == 0x19930520:
            rec.update(kind='cxx', magic=first, max_state=be(data + 4), unwind_map=be(data + 8),
                       try_blocks=be(data + 12), try_map=be(data + 16),
                       ip_entries=be(data + 20), ip_map=be(data + 24))
            rec['unwind_actions'] = [be(rec['unwind_map'] + i * 8 + 4) for i in range(rec['max_state'])] \
                if rec['unwind_map'] else []
            catches = []
            for i in range(rec['try_blocks']):
                e = rec['try_map'] + i * 20
                n, ph = be(e + 12), be(e + 16)
                for j in range(n):
                    catches.append(dict(try_low=be(e), try_high=be(e + 4), catch_high=be(e + 8),
                                        adjectives=be(ph + j * 16), type=be(ph + j * 16 + 4),
                                        handler=be(ph + j * 16 + 12)))
            rec['catches'] = catches
            cxx.append(rec)
        elif 0 < first <= 100:
            scopes = []
            for i in range(first):
                b, e, flt, tgt = (be(data + 4 + i * 16 + k * 4) for k in range(4))
                if tgt == 0:
                    kind = 'finally'
                elif flt == 1:
                    kind = 'except_const_execute'
                elif flt == 0:
                    kind = 'except_const_search'
                else:
                    kind = 'except_filter'
                s = dict(begin=b, end=e, filter=flt, target=tgt, kind=kind)
                fn = flt if kind in ('finally', 'except_filter') else None
                if fn:
                    enc = enclosing(fn)
                    s['funclet_has_own_pdata'] = bool(enc and enc['begin'] == fn)
                    s['funclet_inside_owner'] = rec['function'] <= fn < rec['end']
                if tgt:
                    s['body_inside_owner'] = rec['function'] <= tgt < rec['end']
                    s['body_has_marker_before'] = be(tgt - 4) == 0x7D084378 or be(tgt) == 0x7D084378
                scopes.append(s)
            for s in scopes:
                s['depth'] = sum(1 for o in scopes if o is not s and o['begin'] <= s['begin']
                                 and s['end'] <= o['end'] and (o['begin'], o['end']) != (s['begin'], s['end']))
            rec.update(kind='seh', scopes=scopes)
            seh.append(rec)
        else:
            rec['kind'] = 'unparsed'; rec['first_word'] = first; other.append(rec)

    scope_kinds = collections.Counter(s['kind'] for r in seh for s in r['scopes'])
    shape = collections.Counter(
        '+'.join(sorted(collections.Counter(s['kind'] for s in r['scopes']).keys())) for r in seh)
    out = dict(
        pdata_entries=len(funcs), eh_flagged=sum(f['eh'] for f in funcs),
        handlers={f'{h:08X}': n for h, n in handlers.most_common()},
        seh_functions=len(seh), cxx_functions=len(cxx), other=len(other),
        seh_scope_total=sum(len(r['scopes']) for r in seh), seh_scope_kinds=dict(scope_kinds),
        seh_function_shapes=dict(shape),
        seh_max_scopes=max((len(r['scopes']) for r in seh), default=0),
        seh_nested_functions=sum(1 for r in seh if any(s['depth'] for s in r['scopes'])),
        seh_max_depth=max((s['depth'] for r in seh for s in r['scopes']), default=0),
        finally_funclets_with_own_pdata=sum(1 for r in seh for s in r['scopes']
                                            if s['kind'] == 'finally' and s['funclet_has_own_pdata']),
        finally_funclets_inside_owner=sum(1 for r in seh for s in r['scopes']
                                          if s['kind'] == 'finally' and s['funclet_inside_owner']),
        filter_funclets_with_own_pdata=sum(1 for r in seh for s in r['scopes']
                                           if s['kind'] == 'except_filter' and s['funclet_has_own_pdata']),
        filter_funclets_inside_owner=sum(1 for r in seh for s in r['scopes']
                                         if s['kind'] == 'except_filter' and s['funclet_inside_owner']),
        except_bodies=sum(1 for r in seh for s in r['scopes'] if s['target']),
        except_bodies_inside_owner=sum(1 for r in seh for s in r['scopes']
                                       if s['target'] and s['body_inside_owner']),
        distinct_except_bodies=len({s['target'] for r in seh for s in r['scopes'] if s['target']}),
        distinct_filters=len({s['filter'] for r in seh for s in r['scopes'] if s['kind'] == 'except_filter'}),
        distinct_finally=len({s['filter'] for r in seh for s in r['scopes'] if s['kind'] == 'finally'}),
        cxx_with_try_blocks=sum(1 for r in cxx if r['try_blocks']),
        cxx_catch_handlers=sum(len(r['catches']) for r in cxx),
        cxx_catch_all=sum(1 for r in cxx for c in r['catches'] if c['type'] == 0),
        cxx_unwind_actions=sum(1 for r in cxx for x in r['unwind_actions'] if x),
        cxx_magics=dict(collections.Counter(f"{r['magic']:08X}" for r in cxx)),
        seh=seh, cxx=cxx, other_records=other)
    hexify = lambda o: ({k: hexify(v) for k, v in o.items()} if isinstance(o, dict) else
                        [hexify(v) for v in o] if isinstance(o, list) else
                        f'0x{o:08X}' if isinstance(o, int) and not isinstance(o, bool) and o >= 0x10000 else o)
    json.dump(hexify(out), open(a.out, 'w'), indent=1)
    print(json.dumps({k: v for k, v in hexify(out).items() if k not in ('seh', 'cxx', 'other_records')}, indent=1))


if __name__ == '__main__':
    main()

"""Validate actual target emission; create a private executable fixture from it.

Generated target code is never copied into tracked output. Reports are metadata.
"""
import json, re, hashlib
from m2_prepare import ROOT, W, G, write_text_if_changed

def validate():
    functions = {}
    for p in G.glob('r3hd_recomp.*.cpp'):
        for m in re.finditer(r'DEFINE_REX_FUNC\((\w+)\) \{.*?^\}', p.read_text(), re.M | re.S):
            functions[m[1]] = m[0]
    eh = json.loads((ROOT / 'reports/milestone3/data/eh_map.json').read_text())
    table = {int(a, 16): n for a, n in re.findall(r'\{ 0x([0-9A-F]{8}), (\w+) \}', (G / 'r3hd_init.cpp').read_text())}
    scopes = bodies = 0
    for owner in eh['seh']:
        src = functions[table[int(owner['function'], 16)]]
        for token in ('M4SehFilter(', 'M4SehUnwind(', 'M4RestoreOwner(', 'M4BeforeCall(', 'm4.pc =', 'm4_retry:'):
            assert token in src, (owner['function'], token)
        for s in owner['scopes']:
            begin, end, filt, target = [(int(s[k], 16) if isinstance(s[k], str) else s[k]) for k in ('begin', 'end', 'filter', 'target')]
            assert f'{{0x{begin:X}, 0x{end:X}, 0x{filt:X}, 0x{target:X}}}' in src
            scopes += 1
            if target:
                assert f'case 0x{target:X}: goto loc_{target:X};' in src
                assert f'loc_{target:X}:' in src
                assert target not in table
                bodies += 1
    for owner, target in [(0x822FD930, 0x822FDC00), (0x826BA608, 0x826BA700),
                          (0x826C2948, 0x826C2A40), (0x826C57D8, 0x826C5948)]:
        assert f'case 0x{target:X}: goto loc_{target:X};' in functions[table[owner]], hex(target)
    for owner in (0x82559C48, 0x82559DA8):
        src = functions[table[owner]]
        assert 'ppc_setjmp(' in src and 'm4.in_call = false; m4.pc =' in src
    selected = ('sub_82821618', 'sub_82821684', 'sub_820E7CE0', 'sub_820E7D2C', 'sub_826D5BB0')
    prefix = '#include "../../../tools/m4_generated_fixture.h"\n'
    write_text_if_changed(W / 'm4_generated_test.cpp', prefix + '\n'.join(functions[n] for n in selected) + '\nint main() { return GeneratedTests(); }\n')
    result = dict(seh_owners=len(eh['seh']), scopes=scopes, inline_bodies=bodies,
                  same_frame_unwind_labels=4, fixture_functions=list(selected),
                  fixture_function_sha256={n: hashlib.sha256(functions[n].encode()).hexdigest() for n in selected})
    out = ROOT / 'reports/milestone4/emission.json'; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    validate()

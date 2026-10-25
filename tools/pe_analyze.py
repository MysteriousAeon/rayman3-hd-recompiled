#!/usr/bin/env python3
"""Independent static characterization of a decrypted XEX memory image (PE).

Inputs: flat image written by xex_info.py --image-out, the xex_info JSON, and a
local xenia checkout (export tables are read from it to name import ordinals).

Emits a JSON report with no code bytes: sections, .pdata stats, resolved
imports, opcode census (incl. VMX/VMX128), branch/indirect-branch statistics,
jump-table candidates, ABI helper locations, and gaps not covered by .pdata.
"""
import argparse, collections, json, re, struct, subprocess, sys


def be32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def le32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def le16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def sx(v, bits):
    return v - (1 << bits) if v >> (bits - 1) else v


def load_exports(xenia):
    out = {}
    ls = subprocess.run(["git", "-C", xenia, "ls-tree", "-r", "--name-only", "HEAD"],
                        capture_output=True, text=True, check=True).stdout.split()
    for lib, pat in (("xboxkrnl.exe", "xboxkrnl_table.inc"), ("xam.xex", "xam_table.inc")):
        path = [p for p in ls if p.endswith(pat)][0]
        src = subprocess.run(["git", "-C", xenia, "show", "HEAD:" + path],
                             capture_output=True, text=True, check=True).stdout
        t = {}
        for m in re.finditer(r"XE_EXPORT\(\s*\w+,\s*0x([0-9A-Fa-f]+),\s*(\w+),\s*k(\w+)\)", src):
            t[int(m.group(1), 16)] = (m.group(2), m.group(3))
        out[lib] = t
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("xexinfo")
    ap.add_argument("--xenia", default="external/xenia")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    img = open(a.image, "rb").read()
    info = json.load(open(a.xexinfo))
    base = int(info["image_base"], 16)
    R = {"image_base": hex(base), "image_size": hex(len(img)), "entry_point": info["entry_point"]}

    # ---- PE headers
    pe = le32(img, 0x3C)
    assert img[pe:pe + 4] == b"PE\0\0"
    machine, nsec = le16(img, pe + 4), le16(img, pe + 6)
    opt_sz = le16(img, pe + 20)
    opt = pe + 24
    R["pe"] = {"machine": hex(machine), "timestamp": le32(img, pe + 8), "characteristics": hex(le16(img, pe + 22)),
               "opt_magic": hex(le16(img, opt)), "linker": f"{img[opt + 2]}.{img[opt + 3]}",
               "pe_entry_rva": hex(le32(img, opt + 16)), "pe_image_base": hex(le32(img, opt + 28)),
               "section_alignment": hex(le32(img, opt + 32)), "file_alignment": hex(le32(img, opt + 36)),
               "size_of_image": hex(le32(img, opt + 56)), "subsystem": le16(img, opt + 68)}
    ndir = le32(img, opt + 92)
    dnames = ["export", "import", "resource", "exception", "security", "basereloc", "debug", "arch",
              "globalptr", "tls", "loadconfig", "boundimport", "iat", "delayimport", "clr", "rsvd"]
    R["pe"]["data_directories"] = {dnames[i]: [hex(le32(img, opt + 96 + i * 8)), hex(le32(img, opt + 100 + i * 8))]
                                   for i in range(min(ndir, 16)) if le32(img, opt + 100 + i * 8)}
    secs = []
    so = opt + opt_sz
    for i in range(nsec):
        o = so + i * 40
        ch = le32(img, o + 36)
        secs.append({"name": img[o:o + 8].rstrip(b"\0").decode("latin-1"), "va": base + le32(img, o + 12),
                     "vsize": le32(img, o + 8), "rawsize": le32(img, o + 16), "rawptr": le32(img, o + 20),
                     "flags": ch, "code": bool(ch & 0x20), "exec": bool(ch & 0x20000000),
                     "read": bool(ch & 0x40000000), "write": bool(ch & 0x80000000)})
    R["sections"] = [{**s, "va": hex(s["va"]), "vsize": hex(s["vsize"]), "rawsize": hex(s["rawsize"]),
                      "rawptr": hex(s["rawptr"]), "flags": hex(s["flags"])} for s in secs]
    R["writable_and_executable_sections"] = [s["name"] for s in secs if s["write"] and (s["exec"] or s["code"])]

    def rd(va):
        return be32(img, va - base)

    def sec_of(va):
        for s in secs:
            if s["va"] <= va < s["va"] + max(s["vsize"], s["rawsize"]):
                return s
        return None

    code_secs = [s for s in secs if s["code"] or s["exec"]]
    R["code_bytes_total"] = hex(sum(s["vsize"] for s in code_secs))

    # ---- .pdata
    pd = next((s for s in secs if s["name"] == ".pdata"), None)
    funcs = []
    if pd:
        o = pd["va"] - base
        for i in range(0, pd["vsize"], 8):
            beg, w = be32(img, o + i), be32(img, o + i + 4)
            if beg == 0:
                continue
            # after BE->host swap (LSB first): PrologLength:8, FunctionLength:22, ThirtyTwoBit:1, ExceptionFlag:1
            funcs.append((beg, ((w >> 8) & 0x3FFFFF) * 4, w & 0xFF, (w >> 30) & 1, w >> 31))
    funcs.sort()
    in_code = [f for f in funcs if sec_of(f[0]) and sec_of(f[0]) in code_secs]
    overlaps = sum(1 for x, y in zip(funcs, funcs[1:]) if x[0] + x[1] > y[0])
    R["pdata"] = {"entries": len(funcs), "entries_in_code_sections": len(in_code),
                  "bytes_covered": hex(sum(f[1] for f in funcs)), "exception_flag_set": sum(f[4] for f in funcs),
                  "thirtytwo_bit_set": sum(f[3] for f in funcs), "overlapping_adjacent": overlaps,
                  "first": hex(funcs[0][0]) if funcs else None, "last_end": hex(funcs[-1][0] + funcs[-1][1]) if funcs else None,
                  "max_size": hex(max((f[1] for f in funcs), default=0))}

    # ---- imports
    exports = load_exports(a.xenia)
    imps, thunk_addr = [], {}
    for lib in info.get("import_libraries", []):
        t = exports.get(lib["name"], {})
        for r in lib["records"]:
            va = int(r, 16)
            v = rd(va)
            typ, ordn = v >> 24, v & 0xFFFF
            name, kind = t.get(ordn, (None, None))
            if typ == 0:
                imps.append({"lib": lib["name"], "ordinal": ordn, "name": name, "kind": kind or "?",
                             "record": hex(va), "thunk": None})
            elif typ == 1:
                thunk_addr[va] = (lib["name"], ordn)
                for e in imps:
                    if e["lib"] == lib["name"] and e["ordinal"] == ordn and e["thunk"] is None:
                        e["thunk"] = hex(va)
                        break
                else:
                    imps.append({"lib": lib["name"], "ordinal": ordn, "name": name, "kind": "Function(thunk-only)",
                                 "record": None, "thunk": hex(va)})
    R["imports"] = imps
    R["import_summary"] = {l: {"total": sum(1 for e in imps if e["lib"] == l),
                               "functions": sum(1 for e in imps if e["lib"] == l and e["thunk"]),
                               "variables": sum(1 for e in imps if e["lib"] == l and not e["thunk"]),
                               "unnamed_in_xenia_table": [e["ordinal"] for e in imps if e["lib"] == l and not e["name"]]}
                           for l in sorted({e["lib"] for e in imps})}

    # ---- instruction census over code sections
    prim = collections.Counter()
    x31 = collections.Counter()
    x4 = collections.Counter()
    x59 = collections.Counter()
    x63 = collections.Counter()
    x19 = collections.Counter()
    st = collections.Counter()
    bl_targets = collections.Counter()
    bctr_sites, bctrl_sites, mtctr_sites = [], [], []
    bad_direct = []
    lo = min(s["va"] for s in code_secs)
    hi = max(s["va"] + s["vsize"] for s in code_secs)
    R["code_range"] = [hex(lo), hex(hi)]

    def is_code(va):
        s = sec_of(va)
        return s is not None and s in code_secs

    words = {}
    for s in code_secs:
        o = s["va"] - base
        n = s["vsize"] // 4
        ws = struct.unpack_from(f">{n}I", img, o)
        for i, w in enumerate(ws):
            pc = s["va"] + i * 4
            if w == 0:
                st["zero_words"] += 1
                continue
            st["nonzero_words"] += 1
            op = w >> 26
            prim[op] += 1
            if op == 31:
                x31[(w >> 1) & 0x3FF] += 1
                if w & 0xFC1FFFFF == 0x7C0903A6:
                    mtctr_sites.append(pc)
            elif op == 4:
                x4[w & 0x7FF] += 1
            elif op == 59:
                x59[(w >> 1) & 0x1F] += 1
            elif op == 63:
                x63[(w >> 1) & 0x3FF] += 1
            elif op == 19:
                xo = (w >> 1) & 0x3FF
                x19[xo] += 1
                if xo == 528:
                    if w & 1:
                        bctrl_sites.append(pc)
                    else:
                        bctr_sites.append(pc)
                    st["bcctr_conditional"] += ((w >> 21) & 0x14) != 0x14
                elif xo == 16:
                    st["blr" if not w & 1 else "blrl"] += 1
            elif op == 18:
                tgt = sx(w & 0x03FFFFFC, 26) + (0 if w & 2 else pc)
                tgt &= 0xFFFFFFFF
                if w & 1:
                    st["bl"] += 1
                    bl_targets[tgt] += 1
                else:
                    st["b"] += 1
                if not is_code(tgt):
                    bad_direct.append((pc, tgt, "bl" if w & 1 else "b"))
            elif op == 16:
                st["bc"] += 1
                tgt = (sx(w & 0xFFFC, 16) + (0 if w & 2 else pc)) & 0xFFFFFFFF
                if not is_code(tgt):
                    bad_direct.append((pc, tgt, "bc"))
            elif op == 17:
                st["sc"] += 1
            elif op in (2, 3):
                st["tdi/twi"] += 1
    R["stats"] = dict(st)
    R["primary_opcode_census"] = {str(k): v for k, v in sorted(prim.items())}
    R["illegal_primary_opcodes"] = {str(k): prim[k] for k in (0, 1, 5, 6, 9, 22, 56, 57, 60, 61) if prim[k]}
    R["op31_xo_census"] = {str(k): v for k, v in sorted(x31.items())}
    R["op4_census_low11"] = {hex(k): v for k, v in sorted(x4.items(), key=lambda kv: -kv[1])}
    R["op59_census"] = {str(k): v for k, v in sorted(x59.items())}
    R["op63_census"] = {str(k): v for k, v in sorted(x63.items())}
    R["op19_census"] = {str(k): v for k, v in sorted(x19.items())}
    R["vmx_words_op4"] = sum(x4.values())
    R["vmx128_words_op5_op6"] = prim[5] + prim[6]
    R["direct_branch_targets_outside_code"] = [{"pc": hex(p), "target": hex(t), "kind": k} for p, t, k in bad_direct[:200]]
    R["direct_branch_targets_outside_code_count"] = len(bad_direct)
    R["indirect"] = {"bctr": len(bctr_sites), "bctrl": len(bctrl_sites), "mtctr": len(mtctr_sites)}

    # ---- classify bctr sites (jump table vs tail call vs import thunk)
    kinds = collections.Counter()
    samples = collections.defaultdict(list)
    thunk_fn = {}
    for pc in bctr_sites:
        back = [rd(pc - 4 * k) for k in range(1, 9) if is_code(pc - 4 * k)]
        ops = [w >> 26 for w in back]
        xos = [(w >> 1) & 0x3FF if (w >> 26) == 31 else -1 for w in back]
        # import thunk: lis r11 / lwz r11,x(r11) / mtctr r11 / bctr   (original record replaced by loader)
        if pc - 12 in thunk_addr or pc - 8 in thunk_addr:
            k = "import_thunk"
        elif len(back) >= 3 and (back[0] & 0xFC1FFFFF) == 0x7C0903A6 and (
                xos[1] in (23, 279, 87, 266) or (len(xos) > 2 and xos[2] in (23, 279, 87)) or 23 in xos[:5] or 279 in xos[:5] or 87 in xos[:5]):
            k = "jump_table_like(indexed load before mtctr)"
        elif len(back) >= 2 and (back[0] & 0xFC1FFFFF) == 0x7C0903A6 and ops[1] == 32:
            k = "lwz+mtctr+bctr (vtable/fnptr tail call or thunk)"
        elif (back[0] & 0xFC1FFFFF) == 0x7C0903A6:
            k = "mtctr+bctr other"
        else:
            k = "bctr without adjacent mtctr"
        kinds[k] += 1
        if len(samples[k]) < 12:
            samples[k].append(hex(pc))
    R["bctr_classification"] = dict(kinds)
    R["bctr_samples"] = dict(samples)

    # ---- ABI helper signatures (XenonRecomp README byte patterns)
    pats = {"restgprlr_14": "e9c1ff68", "savegprlr_14": "f9c1ff68", "restfpr_14": "c9ccff70",
            "savefpr_14": "d9ccff70", "restvmx_14": "3960fee07dcb60ce", "savevmx_14": "3960fee07dcb61ce",
            "restvmx_64": "3960fc00100b60cb", "savevmx_64": "3960fc00100b61cb"}
    helpers = {}
    for n, h in pats.items():
        p, hits = bytes.fromhex(h), []
        for s in code_secs:
            o, e = s["va"] - base, s["va"] - base + s["vsize"]
            i = img.find(p, o, e)
            while i != -1:
                if (i - o) % 4 == 0:
                    hits.append(hex(base + i))
                i = img.find(p, i + 4, e)
        helpers[n] = hits
    R["abi_helpers"] = helpers

    # ---- gaps not covered by .pdata inside code sections
    cov = sorted((f[0], f[0] + f[1]) for f in funcs)
    gaps, cur = [], lo
    for b, e in cov:
        if b > cur:
            gaps.append((cur, b))
        cur = max(cur, e)
    if cur < hi:
        gaps.append((cur, hi))
    nz_gap_bytes, nz_gaps = 0, []
    for b, e in gaps:
        if not (is_code(b)):
            continue
        nz = sum(4 for va in range(b, e, 4) if is_code(va) and rd(va) != 0)
        if nz:
            nz_gap_bytes += nz
            nz_gaps.append((b, e, nz))
    nz_gaps.sort(key=lambda g: -g[2])
    R["pdata_gaps"] = {"gap_count_with_nonzero_words": len(nz_gaps), "nonzero_bytes_outside_pdata": hex(nz_gap_bytes),
                       "largest": [{"start": hex(b), "end": hex(e), "nonzero_bytes": hex(n)} for b, e, n in nz_gaps[:25]]}
    starts = {f[0] for f in funcs}
    bl_not_pdata = [t for t in bl_targets if t not in starts and is_code(t)]
    in_body = 0
    import bisect
    fs = [f[0] for f in funcs]
    for t in bl_not_pdata:
        i = bisect.bisect_right(fs, t) - 1
        if i >= 0 and funcs[i][0] < t < funcs[i][0] + funcs[i][1]:
            in_body += 1
    R["bl_targets"] = {"distinct": len(bl_targets), "distinct_not_pdata_start": len(bl_not_pdata),
                       "of_which_inside_a_pdata_function_body": in_body}

    json.dump(R, open(a.out, "w"), indent=1)
    brief = {k: R[k] for k in ("pe", "sections", "writable_and_executable_sections", "code_bytes_total", "pdata",
                               "import_summary", "stats", "illegal_primary_opcodes", "vmx_words_op4",
                               "vmx128_words_op5_op6", "direct_branch_targets_outside_code_count", "indirect",
                               "bctr_classification", "abi_helpers", "bl_targets")}
    brief["pdata_gaps"] = {k: v for k, v in R["pdata_gaps"].items() if k != "largest"}
    print(json.dumps(brief, indent=1))


if __name__ == "__main__":
    main()

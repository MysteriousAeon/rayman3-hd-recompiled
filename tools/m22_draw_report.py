"""M22: decode a one-frame draw trace (m22_draws_<swap>.bin, written by tools/m22_draw_trace.h) into metadata.

For every draw: primitive, index count, shader hashes, render state words, bound textures (named by matching the
first bytes in guest memory against the level's BTF bundles), and for a selected draw the transformed vertices
(position through the c0..c3 rows the shipped vertex shaders use, psm/*.vsh `dp4 oPos.x,v0,c0` ...), their
clip-space depth range and the vertex colours. Clears and resolves are listed in sequence.
Output is metadata; the trace itself is game-derived and stays under private/.

usage: m22_draw_report.py TRACE.bin --level wood_11 [--texture NAME] [--draw N] [--json OUT]
"""
import argparse
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "private" / "extracted" / "5841123F" / "GAMEDATAbin"
MAGIC = 0x4D323244
FORMATS = {6: "8_8_8_8", 7: "2_10_10_10", 16: "10_11_11", 17: "11_11_10", 25: "16_16", 26: "16_16_16_16",
           31: "16_16_F", 32: "16_16_16_16_F", 33: "32", 34: "32_32", 35: "32_32_32_32", 36: "32_F",
           37: "32_32_F", 38: "32_32_32_32_F", 57: "32_32_32_F"}
FLOATS = {36: 1, 37: 2, 57: 3, 38: 4}


def texture_index(level: str) -> dict:
    """First 32 bytes of every texture part of the level / fix / transit bundles -> name."""
    index = {}
    for bhf in [GAME / "fix.bhf"] + sorted((GAME / level).glob("*.bhf")):
        b = bhf.read_bytes()
        data = bhf.with_suffix(".btf").read_bytes()
        n, = struct.unpack_from(">I", b, 0)
        for i in range(n):
            o = 4 + i * 0x114
            s1, o1, s2, o2 = struct.unpack_from(">4I", b, o)
            name = b[o + 16:o + 0x114].split(b"\0")[0].decode("latin1")
            for size, off in ((s1, o1), (s2, o2)):
                if size:
                    index.setdefault(data[off:off + 32], f"{bhf.stem}:{name}")
    return index


def f32(word: int) -> float:
    return struct.unpack("<f", struct.pack("<I", word))[0]


def parse(path: Path):
    b = path.read_bytes()
    at, draws, events, shaders = 0, [], [], {}
    while at + 12 <= len(b):
        magic, kind, size = struct.unpack_from("<3I", b, at)
        assert magic == MAGIC, hex(at)
        p = b[at + 12:at + 12 + size]
        at += 12 + size
        if kind == 2:
            h, t, n = struct.unpack_from("<QII", p, 0)
            shaders[(t, h)] = n
        elif kind == 1:
            regs = struct.unpack_from("<1024I", p, 0)
            events.append(("copy", len(draws), regs))
        else:
            (draw, prim, count, indexed, ifmt, iend, ibase, ibytes, vs, ps, nb, nt) = struct.unpack_from("<8I2Q2I", p, 0)
            o = 56
            bindings = []
            for _ in range(nb):
                fc, stride, na, addr, size_b, cap = struct.unpack_from("<6I", p, o)
                o += 24
                attrs = [struct.unpack_from("<6I", p, o + 24 * k) for k in range(na)]
                o += 24 * na
                bindings.append(dict(fetch=fc, stride=stride * 4, address=addr, size=size_b, captured=cap,
                                     attributes=[dict(format=a[0], offset=a[1] * 4, signed=a[2], integer=a[3], reg=a[5])
                                                 for a in attrs]))
            textures = []
            for _ in range(nt):
                fc, base, hb = struct.unpack_from("<3I", p, o)
                textures.append(dict(fetch=fc, base=base, head=bytes(p[o + 12:o + 12 + hb])))
                o += 12 + 64
            regs = struct.unpack_from("<1024I", p, o)
            o += 4096
            consts = struct.unpack_from("<2240I", p, o)  # 0x4000 .. 0x48BF
            o += 2240 * 4
            index_bytes = p[o:o + ibytes]
            o += ibytes
            for bnd in bindings:
                bnd["data"] = p[o:o + bnd["captured"]]
                o += bnd["captured"]
            d = dict(draw=draw, primitive=prim, index_count=count, indexed=indexed, index_format=ifmt,
                     index_endian=iend, index_bytes=index_bytes, vs=vs, ps=ps, bindings=bindings, textures=textures,
                     regs=regs, consts=consts)
            draws.append(d)
            events.append(("draw", len(draws) - 1, None))
    return draws, events, shaders


def state_row(d, names):
    r = d["regs"]
    reg = lambda a: r[a - 0x2000]
    tex = [names.get(t["head"][:32], f"?{t['base']:08X}") if t["head"] else f"-{t['base']:08X}" for t in d["textures"]]
    return dict(draw=d["draw"], prim=d["primitive"], indices=d["index_count"], vs=f"{d['vs']:016X}", ps=f"{d['ps']:016X}",
                textures=tex, surface_info=f"{reg(0x2000):08X}", color_info=f"{reg(0x2001):08X}",
                depth_control=f"{reg(0x2200):08X}", blend0=f"{reg(0x2201):08X}", color_control=f"{reg(0x2202):08X}",
                clip_cntl=f"{reg(0x2204):08X}", su_sc_mode=f"{reg(0x2205):08X}", vte_cntl=f"{reg(0x2206):08X}",
                mode_control=f"{reg(0x2208):08X}", color_mask=f"{reg(0x2104):08X}",
                viewport=[round(f32(reg(a)), 3) for a in range(0x210F, 0x2115)])


def vertices(d):
    """Decode every attribute of the first binding (big-endian guest dwords); floats and 8_8_8_8 only."""
    bnd = d["bindings"][0]
    data, stride = bnd["data"], bnd["stride"]
    n = len(data) // stride if stride else 0
    out = []
    for a in bnd["attributes"]:
        fmt, off = a["format"], a["offset"]
        if fmt in FLOATS:
            k = FLOATS[fmt]
            vals = [struct.unpack_from(f">{k}f", data, i * stride + off) for i in range(n)]
        elif fmt == 6:
            vals = [tuple(data[i * stride + off:i * stride + off + 4]) for i in range(n)]
        else:
            vals = None
        out.append((a, vals))
    return n, out


def indices(d):
    if not d["indexed"]:
        return list(range(d["index_count"]))
    raw = d["index_bytes"]
    if d["index_format"]:
        code = ">I" if d["index_endian"] == 2 else "<I"
    else:
        code = ">H" if d["index_endian"] == 1 else "<H"
    return [x[0] for x in struct.iter_unpack(code, raw[:len(raw) // struct.calcsize(code) * struct.calcsize(code)])]


def analyse(d):
    n, attrs = vertices(d)
    idx = [i for i in indices(d) if i < n]
    c = d["consts"]
    rows = [[f32(c[r * 4 + k]) for k in range(4)] for r in range(4)]  # c0..c3
    pos = next((v for a, v in attrs if a["format"] in (57, 38) and v), None)
    col = [(a, v) for a, v in attrs if a["format"] == 6 and v]
    # Vertex fetch constant f: register 0x4800 + (f // 3) * 6 + (f % 3) * 2; dword 1 bits 0..1 = endian
    # (2 = 8-in-32, the big-endian dwords this decoder assumes).
    fc = d["bindings"][0]["fetch"]
    vf1 = c[0x800 + (fc // 3) * 6 + (fc % 3) * 2 + 1]
    res = dict(vertex_count=n, stride=d["bindings"][0]["stride"], used_vertices=len(set(idx)),
               vertex_fetch_endian=vf1 & 3,
               attributes=[dict(format=FORMATS.get(a["format"], a["format"]), offset=a["offset"], reg=a["reg"]) for a, _ in attrs],
               c0_c3=[[round(x, 5) for x in row] for row in rows])
    if pos is None or not idx:
        return res
    used = sorted(set(idx))
    clip = {}
    for i in used:
        x, y, z = pos[i][:3]
        clip[i] = tuple(rows[r][0] * x + rows[r][1] * y + rows[r][2] * z + rows[r][3] for r in range(4))
    w_pos = [i for i in used if clip[i][3] > 1e-6]
    zw = [clip[i][2] / clip[i][3] for i in w_pos]
    ndc_y = [clip[i][1] / clip[i][3] for i in w_pos]
    ndc_x = [clip[i][0] / clip[i][3] for i in w_pos]
    res.update(model_bounds=[[round(min(pos[i][k] for i in used), 2), round(max(pos[i][k] for i in used), 2)] for k in range(3)],
               w_range=[round(min(clip[i][3] for i in used), 3), round(max(clip[i][3] for i in used), 3)],
               vertices_w_positive=len(w_pos),
               z_over_w=[round(min(zw), 5), round(max(zw), 5)] if zw else None,
               beyond_far=sum(1 for v in zw if v > 1.0), before_near=sum(1 for v in zw if v < 0.0),
               ndc_x=[round(min(ndc_x), 3), round(max(ndc_x), 3)] if ndc_x else None,
               ndc_y=[round(min(ndc_y), 3), round(max(ndc_y), 3)] if ndc_y else None)
    for a, v in col:
        # Colour statistics over used vertices, and split by height (model z, then y) to see a gradient.
        vals = [v[i] for i in used]
        res.setdefault("colours", []).append(dict(
            offset=a["offset"], reg=a["reg"], min=[min(x[k] for x in vals) for k in range(4)],
            max=[max(x[k] for x in vals) for k in range(4)],
            dark_vertices=sum(1 for x in vals if max(x[1:]) < 16 and max(x[:3]) < 16), total=len(vals)))
        for axis in (2, 1):
            hs = sorted(used, key=lambda i: pos[i][axis])
            q = max(1, len(hs) // 5)
            res["colours"][-1][f"by_axis{axis}"] = [
                dict(range=[round(pos[part[0]][axis], 1), round(pos[part[-1]][axis], 1)],
                     mean=[round(sum(v[i][k] for i in part) / len(part), 1) for k in range(4)])
                for part in (hs[j:j + q] for j in range(0, len(hs), q))]
    # Per-vertex screen position of dark-coloured vertices (first colour attribute).
    if col:
        v = col[0][1]
        dark = [i for i in w_pos if max(v[i]) < 16 or (max(v[i][1:]) < 16)]
        if dark:
            res["dark_vertex_ndc_y"] = [round(min(clip[i][1] / clip[i][3] for i in dark), 3),
                                        round(max(clip[i][1] / clip[i][3] for i in dark), 3)]
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace", type=Path)
    ap.add_argument("--level", required=True)
    ap.add_argument("--texture", default="")
    ap.add_argument("--draw", type=int, action="append", default=[])
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    names = texture_index(a.level)
    draws, events, shaders = parse(a.trace)
    rows = [state_row(d, names) for d in draws]
    copies = [(at, f"{regs[0x318]:08X}", f"{regs[0x31E]:08X}", f"{regs[0x31F]:08X}", f"{regs[0x31B]:08X}", f"{regs[0x000]:08X}")
              for kind, at, regs in events if kind == "copy"]
    print(f"draws={len(draws)} copies={len(copies)} distinct_shaders={len(shaders)}")
    for at, cc, lo, hi, info, surf in copies:
        print(f"  copy before draw {at}: copy_control={cc} color_clear={lo} color_clear_lo={hi} dest_info={info} surface_info={surf}")
    selected = set(a.draw)
    if a.texture:
        selected |= {r["draw"] for r in rows if any(a.texture.lower() in t.lower() for t in r["textures"])}
    for r in rows:
        mark = "*" if r["draw"] in selected else " "
        print(f"{mark}{r['draw']:4d} p{r['prim']} n={r['indices']:5d} vs={r['vs'][:8]} ps={r['ps'][:8]} depth={r['depth_control']} "
              f"blend={r['blend0']} clip={r['clip_cntl']} mode={r['mode_control']} mask={r['color_mask']} surf={r['surface_info']} {','.join(r['textures'])}")
    details = {}
    for d in draws:
        if d["draw"] in selected:
            details[d["draw"]] = analyse(d)
            print(json.dumps({"draw": d["draw"], "state": rows[d["draw"]], **details[d["draw"]]}, indent=1))
    if a.json:
        a.json.write_text(json.dumps(dict(draws=rows, copies=copies, details=details), indent=1) + "\n")


if __name__ == "__main__":
    main()

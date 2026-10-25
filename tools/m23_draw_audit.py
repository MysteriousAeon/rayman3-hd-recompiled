"""M23: census of one or more M22 draw traces (m22_draws_<swap>.bin) for fidelity work.

Where m22_draw_report.py answers "which draw makes this pixel", this answers "what does the title ask of the
renderer in this frame": render passes (surface / colour / depth target changes and resolves), every texture
fetch constant decoded (format, endianness, tiling, size, mips, filters, clamp, swizzle), vertex attribute formats
with their fetch endianness, and the distinct blend / depth / alpha-test / cull states. Each row is guest state as
issued; whether the host executes it faithfully is a separate question (reports/milestone23).
Output is metadata (names, register values, counts); traces stay under private/.

usage: m23_draw_audit.py --level LEVEL TRACE.bin [TRACE.bin...] [--passes] [--json OUT]
       m23_draw_audit.py --self-test
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m22_draw_report import parse, texture_index  # noqa: E402

TEXTURE_FORMATS = {2: "k_8", 3: "k_1_5_5_5", 4: "k_5_6_5", 6: "k_8_8_8_8", 7: "k_2_10_10_10", 10: "k_8_8",
                   15: "k_4_4_4_4", 18: "k_DXT1", 19: "k_DXT2_3", 20: "k_DXT4_5", 22: "k_24_8", 23: "k_24_8_FLOAT",
                   24: "k_16", 26: "k_16_16_16_16", 32: "k_16_16_16_16_FLOAT", 36: "k_32_FLOAT", 49: "k_DXN",
                   50: "k_8_8_8_8_AS_16_16_16_16", 51: "k_DXT1_AS_16_16_16_16", 52: "k_DXT2_3_AS_16_16_16_16",
                   53: "k_DXT4_5_AS_16_16_16_16", 54: "k_2_10_10_10_AS_16_16_16_16", 58: "k_DXT3A", 59: "k_DXT5A",
                   60: "k_CTX1"}
ENDIAN = {0: "none", 1: "8in16", 2: "8in32", 3: "16in32"}
CLAMP = {0: "repeat", 1: "mirror", 2: "clamp_edge", 3: "mirror_clamp_edge", 4: "clamp_halfway", 5: "mirror_clamp_halfway",
         6: "clamp_border", 7: "mirror_clamp_border"}
FILTER = {0: "point", 1: "linear", 2: "basemap", 3: "use_fetch_const"}
SWIZZLE = "RGBA01??"
VERTEX_FORMATS = {6: "8_8_8_8", 7: "2_10_10_10", 16: "10_11_11", 17: "11_11_10", 25: "16_16", 26: "16_16_16_16",
                  31: "16_16_F", 32: "16_16_16_16_F", 33: "32", 34: "32_32", 35: "32_32_32_32", 36: "32_F",
                  37: "32_32_F", 38: "32_32_32_32_F", 57: "32_32_32_F"}
BLEND = {0: "zero", 1: "one", 4: "src_color", 5: "inv_src_color", 6: "src_alpha", 7: "inv_src_alpha", 8: "dst_color",
         9: "inv_dst_color", 10: "dst_alpha", 11: "inv_dst_alpha", 12: "const_color", 13: "inv_const_color",
         14: "const_alpha", 15: "inv_const_alpha", 16: "src_alpha_sat"}
BLEND_OP = {0: "add", 1: "sub", 2: "min", 3: "max", 4: "rev_sub"}
COMPARE = ["never", "less", "equal", "lequal", "greater", "notequal", "gequal", "always"]


def bits(word: int, at: int, n: int) -> int:
    return (word >> at) & ((1 << n) - 1)


def texture_fetch(w) -> dict:
    """Decode the six dwords of a texture fetch constant (layout: xenos.h xe_gpu_texture_fetch_t, pinned SDK)."""
    d0, d1, d2, d3, d4, d5 = w
    dimension = bits(d5, 9, 2)
    if dimension == 2:
        size = (bits(d2, 0, 11) + 1, bits(d2, 11, 11) + 1, bits(d2, 22, 10) + 1)
    else:
        size = (bits(d2, 0, 13) + 1, bits(d2, 13, 13) + 1, 1)
    fmt = bits(d1, 0, 6)
    return dict(type=bits(d0, 0, 2), sign="".join(str(bits(d0, 2 + 2 * k, 2)) for k in range(4)),
                clamp=[CLAMP[bits(d0, 10 + 3 * k, 3)] for k in range(3)], pitch=bits(d0, 22, 9) << 5,
                tiled=bits(d0, 31, 1), format=TEXTURE_FORMATS.get(fmt, f"format_{fmt}"),
                endian=ENDIAN[bits(d1, 6, 2)], stacked=bits(d1, 10, 1), base=bits(d1, 12, 20) << 12, size=size,
                swizzle="".join(SWIZZLE[bits(d3, 1 + 3 * k, 3)] for k in range(4)),
                exp_adjust=bits(d3, 13, 6) - (64 if bits(d3, 18, 1) else 0),
                mag=FILTER[bits(d3, 19, 2)], min=FILTER[bits(d3, 21, 2)], mip=FILTER[bits(d3, 23, 2)],
                aniso=bits(d3, 25, 3), border_size=bits(d3, 31, 1), mip_min=bits(d4, 2, 4), mip_max=bits(d4, 6, 4),
                lod_bias=(bits(d4, 12, 10) - (1024 if bits(d4, 21, 1) else 0)) / 32.0,
                dimension=["1D", "2D", "3D", "cube"][dimension], packed_mips=bits(d5, 11, 1),
                mip_address=bits(d5, 12, 20) << 12)


def blend_text(word: int) -> str:
    """RB_BLENDCONTROL: colour src / op / dst in bits 0..12, alpha src / op / dst in bits 16..28."""
    part = lambda at: (f"{BLEND.get(bits(word, at, 5), bits(word, at, 5))} {BLEND_OP.get(bits(word, at + 5, 3), '?')} "
                       f"{BLEND.get(bits(word, at + 8, 5), bits(word, at + 8, 5))}")
    return f"rgb[{part(0)}] a[{part(16)}]"


def depth_text(word: int) -> str:
    """RB_DEPTHCONTROL: stencil enable 0, z enable 1, z write 2, z func 4..6, backface enable 7, stencil func 8.."""
    return (f"z={'on' if bits(word, 1, 1) else 'off'} write={bits(word, 2, 1)} func={COMPARE[bits(word, 4, 3)]} "
            f"stencil={bits(word, 0, 1)}")


def audit(traces, level: str) -> dict:
    names = texture_index(level)
    textures, attributes, states, shaders, passes = {}, Counter(), Counter(), Counter(), []
    unnamed = 0
    for path in traces:
        draws, events, _ = parse(path)
        current = None
        for kind, at, regs in events:
            if kind == "copy":
                passes.append(dict(trace=path.name, kind="copy", before_draw=at, copy_control=f"{regs[0x318]:08X}",
                                   dest_info=f"{regs[0x31B]:08X}", dest_pitch=f"{regs[0x31C]:08X}",
                                   surface_info=f"{regs[0x000]:08X}"))
                current = None
                continue
            d = draws[at]
            r = d["regs"]
            reg = lambda a: r[a - 0x2000]
            key = (reg(0x2000), reg(0x2001), reg(0x2002), reg(0x2208) & 7)
            if key != current:
                passes.append(dict(trace=path.name, kind="pass", first_draw=d["draw"], draws=0,
                                   surface_info=f"{key[0]:08X}", color_info=f"{key[1]:08X}", depth_info=f"{key[2]:08X}",
                                   edram_mode=key[3], viewport_scale=[round(__import__('struct').unpack('<f', __import__('struct').pack('<I', reg(a)))[0], 2) for a in (0x210F, 0x2111)]))
                current = key
            passes[-1]["draws"] += 1
            shaders[(f"{d['vs']:016X}", f"{d['ps']:016X}")] += 1
            color_control = reg(0x2202)
            states[("blend", f"{reg(0x2201):08X}", blend_text(reg(0x2201)) if bits(key[3], 0, 3) == 4 else "-")] += 1
            states[("depth", f"{reg(0x2200):08X}", depth_text(reg(0x2200)))] += 1
            states[("alpha_test", "on" if bits(color_control, 3, 1) else "off",
                    f"{COMPARE[bits(color_control, 0, 3)]} ref={reg(0x210E):08X}" if bits(color_control, 3, 1) else "-")] += 1
            states[("cull", f"{reg(0x2205) & 7}", "bit0 front, bit1 back, bit2 front=cw")] += 1
            states[("color_mask", f"{reg(0x2104):08X}", "")] += 1
            for bnd in d["bindings"]:
                fc = bnd["fetch"]
                endian = d["consts"][0x800 + (fc // 3) * 6 + (fc % 3) * 2 + 1] & 3
                for a in bnd["attributes"]:
                    attributes[(VERTEX_FORMATS.get(a["format"], str(a["format"])), a["signed"], a["integer"],
                                ENDIAN[endian])] += 1
            for t in d["textures"]:
                if not t["head"]:
                    continue
                fc = t["fetch"]
                f = texture_fetch(d["consts"][0x800 + fc * 6:0x800 + fc * 6 + 6])
                name = names.get(t["head"][:32])
                if name is None:
                    unnamed += 1
                    name = f"(not in bundles) {f['size'][0]}x{f['size'][1]}"
                row = textures.setdefault((name, f["format"], f["size"]), dict(f, name=name, uses=0, fetch_slots=set()))
                row["uses"] += 1
                row["fetch_slots"].add(fc)
    for row in textures.values():
        row["fetch_slots"] = sorted(row["fetch_slots"])
    census = Counter()
    for row in textures.values():
        census[(row["format"], row["endian"], row["tiled"], row["dimension"], row["packed_mips"], row["swizzle"],
                row["sign"])] += 1
    return dict(level=level, traces=[p.name for p in traces], passes=passes,
                textures=sorted(textures.values(), key=lambda t: t["name"]),
                texture_census=[dict(format=k[0], endian=k[1], tiled=k[2], dimension=k[3], packed_mips=k[4], swizzle=k[5],
                                     sign=k[6], textures=n) for k, n in sorted(census.items())],
                vertex_attributes=[dict(format=k[0], signed=k[1], integer=k[2], fetch_endian=k[3], uses=n)
                                   for k, n in sorted(attributes.items())],
                states=[dict(kind=k[0], value=k[1], text=k[2], draws=n) for k, n in sorted(states.items())],
                shader_pairs=[dict(vs=k[0], ps=k[1], draws=n) for k, n in shaders.most_common()],
                textures_not_in_bundles=unnamed)


def self_test() -> int:
    """Decoder checks on constructed words (no game data)."""
    checks = []
    # 512x512 DXT1, 8-in-16, linear, 2D, swizzle RGBA, repeat, linear filters, base 0x1A2B3000.
    d0 = 2 | (16 << 22)
    d1 = 18 | (1 << 6) | (0x1A2B3 << 12)
    d2 = 511 | (511 << 13)
    d3 = (0 | 1 << 3 | 2 << 6 | 3 << 9) << 1 | (1 << 19) | (1 << 21) | (1 << 23)
    d4 = (9 << 6)
    d5 = (1 << 9) | (1 << 11) | (0x1A2B4 << 12)
    f = texture_fetch((d0, d1, d2, d3, d4, d5))
    checks += [f["type"] == 2, f["format"] == "k_DXT1", f["endian"] == "8in16", f["tiled"] == 0, f["pitch"] == 512,
               f["size"] == (512, 512, 1), f["swizzle"] == "RGBA", f["mag"] == "linear", f["mip"] == "linear",
               f["mip_max"] == 9, f["dimension"] == "2D", f["packed_mips"] == 1, f["base"] == 0x1A2B3000,
               f["mip_address"] == 0x1A2B4000, f["clamp"] == ["repeat"] * 3, f["exp_adjust"] == 0]
    g = texture_fetch((d0 | (1 << 31) | (2 << 10) | (2 << 13), 6 | (2 << 6), 1279 | (719 << 13),
                       ((2 | 1 << 3 | 0 << 6 | 3 << 9) << 1) | (0x3F << 13), 0, 1 << 9))
    checks += [g["tiled"] == 1, g["format"] == "k_8_8_8_8", g["endian"] == "8in32", g["size"] == (1280, 720, 1),
               g["swizzle"] == "BGRA", g["clamp"][:2] == ["clamp_edge", "clamp_edge"], g["exp_adjust"] == -1]
    checks += [blend_text(0x07060706) == "rgb[src_alpha add inv_src_alpha] a[src_alpha add inv_src_alpha]",
               blend_text(0x00010001) == "rgb[one add zero] a[one add zero]",
               depth_text(0x00708736) == "z=on write=1 func=lequal stencil=0",
               depth_text(0x00708732) == "z=on write=0 func=lequal stencil=0"]
    print(f"M23_DRAW_AUDIT_SELFTEST {'PASS' if all(checks) else 'FAIL'} checks={len(checks)}")
    return 0 if all(checks) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("traces", nargs="*", type=Path)
    ap.add_argument("--level", default="")
    ap.add_argument("--passes", action="store_true")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.traces or not a.level:
        ap.error("TRACE and --level are required")
    res = audit(a.traces, a.level)
    print(f"level={res['level']} traces={len(a.traces)} distinct_textures={len(res['textures'])} "
          f"not_in_bundles={res['textures_not_in_bundles']} shader_pairs={len(res['shader_pairs'])}")
    print("texture census (format endian tiled dim packed swizzle sign : textures)")
    for c in res["texture_census"]:
        print(f"  {c['format']:12s} {c['endian']:6s} tiled={c['tiled']} {c['dimension']} packed={c['packed_mips']} "
              f"{c['swizzle']} sign={c['sign']} : {c['textures']}")
    print("vertex attributes (format signed integer fetch_endian : uses)")
    for v in res["vertex_attributes"]:
        print(f"  {v['format']:14s} signed={v['signed']} int={v['integer']} {v['fetch_endian']} : {v['uses']}")
    print("states")
    for s in res["states"]:
        print(f"  {s['kind']:10s} {s['value']:9s} {s['text']} : {s['draws']}")
    if a.passes:
        print("passes")
        for p in res["passes"]:
            if p["kind"] == "copy":
                print(f"  {p['trace']} copy before {p['before_draw']}: control={p['copy_control']} dest={p['dest_info']}")
            else:
                print(f"  {p['trace']} draws {p['first_draw']}..{p['first_draw'] + p['draws'] - 1}: surface={p['surface_info']} "
                      f"color={p['color_info']} depth={p['depth_info']} mode={p['edram_mode']} vp={p['viewport_scale']}")
    if a.json:
        a.json.write_text(json.dumps(res, indent=1, default=list) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

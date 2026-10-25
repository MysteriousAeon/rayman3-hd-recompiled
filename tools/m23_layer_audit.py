#!/usr/bin/env python3
"""M23 follow-up (D-054): static and traced audit of the two-layer correction (`-LayerCoords separate`).

Reads private inputs only and prints metadata (names, hashes, counts, instruction slots):

  static, complete for the shader variant
    - the title's compiled shader caches `psm/vertexShaderCache_xenon.bin` / `pixelShaderCache_xenon.bin`
      (every shader the title can bind; entry = name, checksum, container);
    - the `psm/*.psh` sources: original stages in the comment against coordinate inputs used by `tex2D`;
    - the microcode the title actually submitted (SDK dump of a run made with `m23_trace_entry.py --shaders`)
      against the cache: the pixel shader is the cache entry unchanged; the bound vertex shader differs from
      the cache entry only in its vertex-fetch slots, its export numbers and the one instruction the
      correction restores, and the correction's words are the cache's words but for the export number.
  traced, a sample of materials and scenes
    - every draw of every `m22_draws_*.bin` under private/work/m6_runs: which vertex shader each pixel shader
      was drawn with, and for the pair's draws the vertex layout, coordinate sets, scroll constants, sampler
      addressing and render state, with and without the option.

    python tools/m23_layer_audit.py [--shaders RUN] [--json OUT]   -> M23_LAYER_AUDIT PASS checks=N failures=0

Not in the build: it needs run directories. It says nothing about levels that were never traced.
"""
import argparse
import collections
import json
import math
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m22_draw_report import f32, parse, vertices  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PSM = ROOT / "private" / "extracted" / "5841123F" / "psm"
RUNS = ROOT / "private" / "work" / "m6_runs"
VS, PS = 0x08E9BEDB27BDDEEE, 0x27336DBAE47E8650            # the title's pair
VS_FIX, PS_FIX = 0x1F165857730A3B16, 0xE4EDC04049BDF898    # the corrected copies (E-128)
checks = failures = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def cache_entries(name: str) -> dict:
    """{lower-case source name: container bytes}; the file must parse to its last byte."""
    b = (PSM / name).read_bytes()
    at, out = 0x14, {}
    while at + 4 <= len(b):
        n, = struct.unpack_from(">I", b, at)
        source = b[at + 4:at + 4 + n].decode("latin1").lower()
        _, size = struct.unpack_from(">II", b, at + 4 + n)
        at += 12 + n
        out[source] = b[at:at + size]
        at += size
    check(at == len(b), f"{name}: parsed to the end")
    return out


def dwords(b: bytes) -> list:
    return list(struct.unpack(f">{len(b) // 4}I", b[:len(b) // 4 * 4]))


def guest_order(dump: bytes) -> bytes:
    """The SDK dumps microcode in host order; the caches hold guest (big-endian) order."""
    return b"".join(dump[i:i + 4][::-1] for i in range(0, len(dump), 4))


def best_match(ucode: bytes, cache: dict):
    """(differing dword indices, source, cache dwords at the best alignment) over every entry."""
    mine, best = dwords(ucode), (None, None, None)
    for source, blob in cache.items():
        at = blob.find(ucode[:4])
        while at >= 0 and at + len(ucode) <= len(blob):
            theirs = dwords(blob[at:at + len(ucode)])
            diff = [i for i, (x, y) in enumerate(zip(mine, theirs)) if x != y]
            if best[0] is None or len(diff) < len(best[0]):
                best = (diff, source, theirs)
            at = blob.find(ucode[:4], at + 1)
    return best


def header_edits(table: str) -> list:
    text = (ROOT / "tools" / "m23_water_layers.h").read_text(encoding="utf-8")
    body = text[text.index(f"constexpr Edit {table}[]"):]
    body = body[:body.index("};")]
    return [tuple(int(v, 16) if v.startswith("0x") else int(v) for v in m)
            for m in re.findall(r"\{(\d+), (0x[0-9A-F]+)u, (0x[0-9A-F]+)u\}", body)]


def source_survey() -> dict:
    """{source: (original stages, coordinate inputs used by tex2D)} for sources with two or more stages."""
    out = {}
    for path in sorted(PSM.glob("*.psh")):
        text = path.read_text(encoding="latin1")
        comment = text[:text.index("*/")] if "*/" in text else ""
        stages = len(set(re.findall(r"^\s*tex\s+(t\d)", comment, re.M)))
        coords = set(re.findall(r"tex2D\s*\(\s*\w+\s*,\s*input\.(\w+)", text))
        if stages >= 2 and coords:
            out[path.name] = (stages, len(coords))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shaders", default="m23_bog_original", help="run directory with the SDK's shader dump")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    report = {}

    # --- 1. the compiled caches: one compile of each source ------------------------------------------------
    vs_cache, ps_cache = cache_entries("vertexShaderCache_xenon.bin"), cache_entries("pixelShaderCache_xenon.bin")
    print(f"caches: {len(vs_cache)} vertex shaders, {len(ps_cache)} pixel shaders")
    check("2t_d_sppt.vsh" in vs_cache and "tvt_tvt.psh" in ps_cache, "caches: one 2T_D_SPPT and one TVT_TVT entry")

    # --- 2. sources: who uses fewer coordinate sets than the original has stages ---------------------------
    survey = source_survey()
    fewer = sorted(n for n, (stages, coords) in survey.items() if coords < stages)
    print(f"sources: {len(survey)} pixel shader sources with two or more original stages; fewer coordinate "
          f"inputs than stages: {fewer}")
    check("tvt_tVT.psh" in fewer and set(fewer) <= {"tvt_tVT.psh", "Mirrors.psh"},
          "sources: tvt_tVT is the only material shader with fewer coordinate inputs than stages")
    report["sources_fewer_coordinates"] = fewer

    # --- 3. submitted microcode against the caches ---------------------------------------------------------
    dump = RUNS / a.shaders / "shaders"
    ps_ucode = guest_order((dump / f"shader_{PS:016X}.ucode.bin.frag").read_bytes())
    vs_ucode = guest_order((dump / f"shader_{VS:016X}.ucode.bin.vert").read_bytes())
    holders = [n for n, blob in ps_cache.items() if ps_ucode in blob]
    check(holders == ["tvt_tvt.psh"], f"pixel shader {PS:016X} is the TVT_TVT cache entry unchanged (in: {holders})")
    diff, source, cached = best_match(vs_ucode, vs_cache)
    check(source == "2t_d_sppt.vsh", f"vertex shader {VS:016X} is a bound copy of 2T_D_SPPT (best match: {source})")
    bound = dwords(vs_ucode)
    vertex_edits, pixel_edits = header_edits("kVertexEdits"), header_edits("kPixelEdits")
    slots = sorted({i // 3 for i in diff})
    edit_slot = vertex_edits[0][0] // 3
    fetch_slots = [s for s in slots if (bound[s * 3] & 0x1F) == 0 and s < edit_slot]   # vertex fetch opcode 0
    exports = [i for i in diff if i // 3 > edit_slot]
    print(f"bound 2T_D_SPPT against its cache entry: differing instruction slots {slots} "
          f"(vertex fetch {fetch_slots}, restored {edit_slot}, export numbers {sorted({i // 3 for i in exports})})")
    check(set(slots) == set(fetch_slots) | {edit_slot} | {i // 3 for i in exports},
          "bound vertex shader: only fetch slots, the removed export and later export numbers differ")
    check(all(i % 3 == 0 and (bound[i] ^ cached[i]) & ~0x3F == 0 for i in exports),
          "bound vertex shader: the later exports differ in the export number only (renumbered)")
    check(all(bound[d] == expect for d, expect, _ in vertex_edits), "bound vertex shader: the edit table's expected words")
    check(all(cached[d] & (~0x3F if k == 0 else ~0) == value & (~0x3F if k == 0 else ~0)
              for k, (d, _, value) in enumerate(vertex_edits)),
          "the corrected vertex instruction is the cache's own instruction but for the export number")
    used = {bound[i] & 0x3F for i in range(0, len(bound), 3) if (bound[i] >> 15) & 1 and (bound[i] >> 16) & 0xF
            and i // 3 > 7} - {62, 63}
    check((vertex_edits[0][2] & 0x3F) not in used, f"the restored export's number is free in the bound shader (used: {sorted(used)})")
    check(all(dwords(ps_ucode)[d] == expect for d, expect, _ in pixel_edits), "pixel shader: the edit table's expected word")
    report["bound_vertex_shader_differing_slots"] = slots

    # --- 4. traces: every draw of every traced frame -------------------------------------------------------
    sources = {}
    for f in RUNS.glob("*/shaders/shader_*.ucode.bin.*"):
        h = int(f.name.split("_")[1].split(".")[0], 16)
        if h not in sources:
            sources[h] = best_match(guest_order(f.read_bytes()), vs_cache if f.suffix == ".vert" else ps_cache)[1]
    name = lambda h: sources.get(h, "?")
    pairs, runs_of, rows = collections.Counter(), collections.defaultdict(set), []
    siblings = collections.defaultdict(collections.Counter)
    traces = sorted(RUNS.glob("*/m22_draws_*.bin"))
    for trace in traces:
        run = trace.parent.name
        for d in parse(trace)[0]:
            pairs[(d["vs"], d["ps"])] += 1
            runs_of[(d["vs"], d["ps"])].add(run)
            c = d["consts"]
            c10, c11 = [f32(c[40 + k]) for k in range(2)], [f32(c[44 + k]) for k in range(2)]
            wrap = all((c[0x800 + 6 * t["fetch"]] >> 10) & 0x3F == 0 for t in d["textures"])
            if name(d["vs"]) == "2t_d_sppt.vsh":
                n, attrs = vertices(d)
                sets = [v for at, v in attrs if at["format"] == 37]
                s = siblings[name(d["ps"])]
                s["draws"] += 1
                s["sets_equal" if len(sets) == 2 and sets[0] == sets[1] else "sets_differ"] += 1
                s["second_offset_own" if c11 != c10 else "second_offset_same"] += 1
            if d["ps"] in (PS, PS_FIX) or d["vs"] in (VS, VS_FIX):
                n, attrs = vertices(d)
                sets = [v for at, v in attrs if at["format"] == 37]
                r = d["regs"]
                rows.append(dict(
                    run=run, fixed=d["ps"] == PS_FIX, vs=d["vs"], ps=d["ps"], vertices=n, bindings=len(d["bindings"]),
                    stride=d["bindings"][0]["stride"], sets=len(sets),
                    sets_equal=len(sets) == 2 and sets[0] == sets[1],
                    finite=all(math.isfinite(x) for v in sets for uv in v for x in uv) and
                    all(math.isfinite(x) for x in c10 + c11),
                    c10=c10, c11=c11, wrap=wrap, textures=len(d["textures"]),
                    same_texture=len({t["base"] for t in d["textures"]}) == 1,
                    state=(r[0x200], r[0x201], r[0x202], r[0x104])))
    print(f"traces: {len(traces)} frames, {sum(pairs.values())} draws, {len(pairs)} shader pairs, "
          f"{len({t.parent.name for t in traces})} runs")
    for (vs, ps), n in sorted(pairs.items(), key=lambda kv: (name(kv[0][1]), name(kv[0][0]))):
        if "sppt" in name(vs) or ps in (PS, PS_FIX):
            print(f"  {name(vs):14s} {vs:016X} + {name(ps):12s} {ps:016X} draws={n:4d} runs={len(runs_of[(vs, ps)])}")
    check(bool(rows), "traces: the pair was drawn")
    check(all((x["vs"], x["ps"]) in ((VS, PS), (VS_FIX, PS_FIX)) for x in rows),
          "traces: TVT_TVT is drawn with this bound 2T_D_SPPT only, and that bound copy with TVT_TVT only")
    check(all(x["bindings"] == 1 and x["stride"] == 36 and x["sets"] == 2 and x["textures"] == 2 for x in rows),
          "pair draws: one 36-byte vertex stream with two coordinate sets, two textures")
    check(all(x["finite"] for x in rows), "pair draws: both coordinate sets and both scroll offsets are finite")
    check(all(x["wrap"] for x in rows), "pair draws: both samplers repeat in u and v (an offset coordinate is valid)")
    check(all(x["c11"] != x["c10"] and x["c11"] != [0.0, 0.0] for x in rows), "pair draws: the second layer has its own, non-zero offset")
    # Scroll speeds are material data: the ratio of the two offsets is constant per material and differs
    # between materials (the Bog sheet: -0.75 / -0.5; the moor_00 layer: -0.6 / -0.333).
    ratios = collections.defaultdict(set)
    for x in rows:
        ratios[x["vertices"]].add((round(x["c11"][0] / x["c10"][0], 2), round(x["c11"][1] / x["c10"][1], 2)))
    print("pair draws: second / first offset per material (by vertex count): "
          + ", ".join(f"{k}: {sorted(v)}" for k, v in sorted(ratios.items())))
    check(all(len(v) == 1 and all(r < 0 for r in next(iter(v))) for v in ratios.values()),
          "pair draws: per material the second layer scrolls against the first at a constant ratio")
    check(len({next(iter(v)) for v in ratios.values()}) == len(ratios), "pair draws: the ratio is the material's own")
    before, after = [x for x in rows if not x["fixed"]], [x for x in rows if x["fixed"]]
    check(bool(before) and bool(after) and {x["state"] for x in before} == {x["state"] for x in after},
          "pair draws: depth, blend, colour control and write mask are the same with and without the option")
    fixed_runs = {x["run"] for x in after}
    title_pairs = {k for k, r in runs_of.items() if r - fixed_runs}
    extra = {k for k, r in runs_of.items() if r & fixed_runs and k not in title_pairs} - {(VS_FIX, PS_FIX)}
    check(not extra and not runs_of[(VS, PS)] & fixed_runs,
          f"option runs: every other draw carries a shader pair the default runs carry too (others: {len(extra)})")
    check(all(s["second_offset_own"] == s["draws"] for s in siblings.values()) and
          any(s["sets_differ"] for n, s in siblings.items() if n != "tvt_tvt.psh"),
          "2T_D_SPPT with its other pixel shaders: second offset always its own; second set differs in some materials")
    for n, s in sorted(siblings.items()):
        print(f"  2t_d_sppt + {n:12s} {dict(s)}")
    materials = collections.Counter((x["vertices"], x["same_texture"], x["sets_equal"]) for x in before)
    print("pair materials in default runs (vertices, same texture on both layers, coordinate sets equal): "
          + ", ".join(f"{k} x{n}" for k, n in sorted(materials.items())))
    report.update(pair_draws=len(rows), traced_frames=len(traces), materials=[list(k) for k in sorted(materials)])
    if a.json:
        a.json.write_text(json.dumps(report, indent=1))
    print(f"M23_LAYER_AUDIT {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

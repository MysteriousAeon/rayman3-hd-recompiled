#!/usr/bin/env python3
"""E-519 (D-286) G6-P30: derive and check the production content policy for intro_20 terrain + FairyLight (graph A)
level transactions.

    g6p30_production_policy.py derive   compile every start-floor-v1 / v2 group configuration at the extreme and
                                        middle displacements (plus the preset) through the unchanged compiler; derive
                                        the terrain byte windows (union of terrain ranges), the pinned FairyLight-A
                                        base image hash (lvl image with every window reset to the original bytes),
                                        the pinned ptr / transit results and per-word bounds; print the C++ table
    g6p30_production_policy.py check    re-derive and compare with the table in tools/m33_mod_overlay.h
Outputs: private/work/e519/ (numbers only).
"""
import itertools
import json
import math
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402

LEVEL = "intro_20"
ROOT = rm.ROOT
GAME = ROOT / "private" / "extracted" / rm.TITLE_ID
WORK = ROOT / "private" / "work" / "e519"
HEADER = ROOT / "tools" / "m33_mod_overlay.h"


def decl(region, groups, graph=0, route=None, preset=None):
    t = ({"type": "terrain", "preset": preset} if preset else
         {"type": "terrain", "patch": {"format": rm.TERRAIN_FORMAT, "level": LEVEL,
                                       "lvl_sha256": rm.STRUCT_ALLOW[LEVEL]["lvl"][1], "region": region, "name": "p",
                                       "groups": [{"name": f"g{i}", "vertices": vs, "delta_z": dz}
                                                  for i, (vs, dz) in enumerate(groups)]}})
    d = {"format": rm.LEVEL_PATCH_FORMAT, "level": LEVEL, "id": "g6p30.policy",
         "lvl_sha256": rm.STRUCT_ALLOW[LEVEL]["lvl"][1], "ptr_sha256": rm.STRUCT_ALLOW[LEVEL]["ptr"][1],
         "transit_sha256": rm.FAIRY_ALLOW[LEVEL]["transit"][1],
         "components": [t, {"type": "fairylight", "follow_graph_of": graph}]}
    if route:
        d["components"].append({"type": "route", "waypoints": route})
    return d


def configs():
    """Every partition-free choice: each vertex of the region either unmoved or in its own group, 2..max groups,
    each displacement at its minimum, middle or maximum (vertex 6 capped)."""
    out = []
    for region, verts, gmax in (("start-floor-v1", (0, 2, 4), 3), ("start-floor-v2", (0, 2, 4, 6), 4)):
        for n in range(2, gmax + 1):
            for vs in itertools.combinations(verts, n):
                for dzs in itertools.product(*[((-0.20, -0.125, -0.05) if v == 6 else (-0.30, -0.175, -0.05))
                                               for v in vs]):
                    out.append(decl(region, [([v], dz) for v, dz in zip(vs, dzs)]))
        out.append(decl(region, [([verts[0], verts[1]], -0.30), (list(verts[2:]), -0.05 if 6 not in verts[2:]
                                                                   else -0.20)]))
    out.append(decl(None, None, preset="start-two-step-v1"))
    return out


def derive():
    WORK.mkdir(parents=True, exist_ok=True)
    lvl = (GAME / "GAMEDATAbin" / LEVEL / f"{LEVEL}.lvl").read_bytes()
    os_env = __import__("os").environ
    os_env[rm.STRUCT_ENV] = LEVEL
    windows, results, bases, deltas = {}, set(), set(), {}
    n = 0
    for d in configs():
        canon, ranges, tx = rm.compile_level_patch(d, {"game": GAME})
        img = bytearray(tx["images"]["lvl"])
        for p, o, data, w in ranges:
            if ".terrain." in w:
                windows[o] = max(windows.get(o, 0), len(data))
        results.add((rm.sha256_bytes(tx["images"]["ptr"]), rm.sha256_bytes(tx["images"]["transit"]),
                     len(img), len(tx["images"]["ptr"])))
        n += 1
    merged = []
    for o in sorted(windows):
        e = o + windows[o]
        if merged and o <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([o, e])
    # second pass: base hash and per-word deltas
    for d in configs():
        _, _, tx = rm.compile_level_patch(d, {"game": GAME})
        img = bytearray(tx["images"]["lvl"])
        for a, b in merged:
            for w in range(a, b, 4):
                v0, v1 = struct.unpack_from(">f", lvl, w)[0], struct.unpack_from(">f", img, w)[0]
                deltas[w] = max(deltas.get(w, 0.0), abs(v1 - v0))
            img[a:b] = lvl[a:b]
        bases.add(rm.sha256_bytes(bytes(img)))
    ok = len(results) == 1 and len(bases) == 1 and all((b - a) % 4 == 0 and a % 4 == 0 for a, b in merged)
    maxd = max(deltas.values())
    res = {"configurations": n, "windows": [[a, b - a] for a, b in merged], "window_bytes": sum(b - a for a, b in merged),
           "results": sorted(results), "base": sorted(bases), "max_word_delta": maxd, "invariant_ok": ok}
    (WORK / "policy.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    return res, lvl


def cpp(res):
    (ptr_sha, tl_sha, lvl_size, ptr_size), = res["results"]
    rows = ",\n".join(f"    {{0x{o:X}, {n}}}" for o, n in res["windows"])
    return (f"constexpr uint64_t kProdLvlGuest = {lvl_size}, kProdPtrGuest = {ptr_size};\n"
            f"constexpr const char* kProdPtrResult = \"{ptr_sha}\";\n"
            f"constexpr const char* kProdTransitResult = \"{tl_sha}\";\n"
            f"constexpr const char* kProdLvlBase = \"{res['base'][0]}\";\n"
            f"constexpr Window kProdTerrainWindows[] = {{\n{rows}}};\n")


POLICY_CODE = r'''
// G6-P30 (D-286): the production content policy of a level transaction. Exactly one composition is accepted: the
// intro_20 version-2 transaction of a start-floor terrain (regions start-floor-v1 / -v2, or the start-two-step-v1
// preset) + the FairyLight on graph A (tools/r3hd_mods.py level_patch_production). Derived and re-checked by
// tools/experiments/modding_feasibility/g6p30_production_policy.py over every start-floor group configuration: every
// such transaction has the same .ptr and transit.lvl results, and its .lvl image with the terrain windows below reset to
// the original bytes is one image (the FairyLight-A base); inside the windows every big-endian float word moves by at
// most kProdWordBound. Anything else (graph B, routes, intro_10, other terrain, any other byte) is refused.
struct Window {
  uint64_t offset, length;
};
@TABLE@constexpr float kProdWordBound = 0.3125f;
inline float BeFloat(const uint8_t* p) {
  const uint32_t u = uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3];
  float f;
  std::memcpy(&f, &u, 4);
  return f;
}
// "" when the declared image of member `a` meets the policy; `image` is restored before returning.
inline std::string ProductionContent(const Member& a, const std::vector<uint8_t>& orig, std::vector<uint8_t>& image,
                                     const std::string& result) {
  const std::string role = a.role;
  if (std::string(a.level) != "intro_20") return "tx_policy_level";
  if (role == "transit") return result == kProdTransitResult ? "" : "tx_policy_result";
  if (role == "ptr") return image.size() == kProdPtrGuest && result == kProdPtrResult ? "" : "tx_policy_result";
  if (role != "lvl" || image.size() != kProdLvlGuest) return "tx_policy_result";
  std::vector<uint8_t> saved;
  saved.reserve(1024);
  std::string why;
  for (const auto& w : kProdTerrainWindows) {
    if (w.offset % 4 || w.length % 4 || w.offset + w.length > orig.size()) return "tx_policy_terrain";
    for (uint64_t o = w.offset; o < w.offset + w.length && why.empty(); o += 4) {
      const float v0 = BeFloat(orig.data() + o), v1 = BeFloat(image.data() + o);
      if (!std::isfinite(v1) || !(std::fabs(v1 - v0) <= kProdWordBound)) why = "tx_policy_terrain";
    }
  }
  if (!why.empty()) return why;
  for (const auto& w : kProdTerrainWindows) {
    saved.insert(saved.end(), image.begin() + w.offset, image.begin() + w.offset + w.length);
    std::memcpy(image.data() + w.offset, orig.data() + w.offset, size_t(w.length));
  }
  const bool base = Sha256Hex(image.data(), image.size()) == kProdLvlBase;
  size_t k = 0;
  for (const auto& w : kProdTerrainWindows) {
    std::memcpy(image.data() + w.offset, saved.data() + k, size_t(w.length));
    k += size_t(w.length);
  }
  return base ? "" : "tx_policy_content";
}
'''

TOP = '''// G6-P30 (D-286): PRODUCTION level transactions. This header carries the level-transaction code that development
// builds verified at run time (G5-P1 / G5-P3 / G6-P1 / G6-P3 / G6-P20 / G6-P23 / G6-P27), with three production rules:
// no environment authorization (nothing outside the plan enables it), only the intro_20 version-2 members, and the
// content policy (ProductionContent) on every member's declared image before anything is served. The comments below
// that say "development builds only" describe the history of this code. Development builds are rendered by
// tools/experiments/modding_feasibility/g5p1_dev_gate.py from the frozen pre-G6-P30 header, unchanged.
'''


def build_header(table):
    import importlib.util
    spec = importlib.util.spec_from_file_location("dev_gate", HERE / "g5p1_dev_gate.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    t = gate.patched(define=False)
    reps = [
        ("#pragma once\n", "#pragma once\n#define R3HD_LEVEL_TX 1  // G6-P30 (D-286): production level transactions\n"),
        ("#include <fstream>\n", "#include <cmath>\n#include <fstream>\n"),
        ('''    {"intro_10", "lvl", "intro_10.lvl", 7661836, "a37638bf1370357db21f33df5c4d37ae806b3c4b9f81b331503ba62d1b19e2ee",
     4096, 3},
    {"intro_10", "ptr", "intro_10.ptr", 209068, "6c9dd70c488a1cac95efc0a55a6086255dae2d851bacd93f5abefdcc8200e940",
     1024, 3},
''', ""),
        ('''     4096, 3},
    {"intro_20", "ptr"''', '''     4096, 2},
    {"intro_20", "ptr"'''),
        ('''     1024, 3},
    // G6-P1''', '''     1024, 2},
    // G6-P1'''),
        ('''    // G6-P1 (D-251, E-484): intro_10's transit.lvl, a same-size member of version 2 only (insert-passive-lum)
    {"intro_10", "transit", "transit.lvl", 41508, "d300ba3a4a3c03cec6a73eb9da8a8d820fcc3a669591e976b357e804315bf275",
     0, 2},
''', ""),
        ('''// The level the environment enables ("" = none): read at plan load.
''', '''// G6-P30 (D-286): production builds read no environment authorization; the content policy decides.
'''),
        ('''inline std::string EnabledLevel() {
  const char* v = std::getenv("R3HD_DEV_STRUCTURAL_TX");
  return v ? std::string(v) : std::string();
}
''', '''inline std::string EnabledLevel() { return "intro_20"; }
'''),
        ('''      if (enabled.empty()) return fail("level_tx_not_enabled");
''', ""),
        ('''      if (!devtx::VersionBit(version)) return fail("tx_version");''',
         '''      if (version != "2") return fail("tx_version");  // G6-P30: production accepts version 2 only'''),
        ('''}  // namespace devtx''', POLICY_CODE.replace("@TABLE@", table) + '''}  // namespace devtx'''),
        ('''      if (devtx::Sha256Hex(image.data(), image.size()) != t->tx_result) return "tx_result_hash";
''', '''      if (devtx::Sha256Hex(image.data(), image.size()) != t->tx_result) return "tx_result_hash";
      {  // G6-P30 (D-286): the production content policy on the declared image (before any other mod's ranges)
        const std::string why = devtx::ProductionContent(a, *t->tx_snapshot, image, t->tx_result);
        if (!why.empty()) return why;
      }
'''),
        ('''    Log(s, "G6P1 level-tx version=" + s.plan.tx_version + " members=lvl,ptr,transit (development build)");''',
         '''    Log(s, "M33 level-tx version=" + s.plan.tx_version + " members=lvl,ptr,transit (production policy D-286)");'''),
        ('''    Log(s, "G5P1 level-tx active level=" + s.plan.tx_level + " mod=" + s.plan.tx_mod + " id=" + s.plan.tx_id +
               " (development build)");''',
         '''    Log(s, "M33 level-tx active level=" + s.plan.tx_level + " mod=" + s.plan.tx_mod + " id=" + s.plan.tx_id +
               " (production policy D-286)");'''),
    ]
    for old, new in reps:
        if t.count(old) != 1:
            raise SystemExit(f"anchor not unique: {old[:70]!r} ({t.count(old)})")
        t = t.replace(old, new)
    t = t.replace("#if defined(R3HD_DEV_STRUCTURAL_TX)", "#if defined(R3HD_LEVEL_TX)")
    i = t.index("#pragma once")
    t = t[:i] + TOP + t[i:]
    bad = [s for s in ("R3HD_DEV_STRUCTURAL_TX\")", "getenv(\"R3HD_DEV", "level_tx_not_enabled", "G5P1 level-tx",
                       "(development build)") if s in t]
    if bad:
        raise SystemExit(f"development strings left: {bad}")
    return t


def negtest():
    """Production overlay policy tests: the real tools/m33_mod_overlay.h (and, as a control, the frozen pre-G6-P30
    production header) built with g5p1_tx_test.cpp; plans from the real compiler, crafted variants rehashed so that
    they pass the integrity checks and reach the policy. Prints NEGTEST_G6P30 PASS|FAIL."""
    import os
    import shutil
    import subprocess
    import g5p1_pilot as p1
    import g6p3_pilot as g3
    import g6p28_fairy_route as g28
    nd = WORK / "negtest"
    if nd.exists():
        shutil.rmtree(nd)
    nd.mkdir(parents=True)
    p1.WORK = g3.WORK = WORK
    exes = {"prod": p1.build_test("prod")}
    # control: the pre-G6-P30 production header (must refuse every transaction as unknown_record)
    old = nd / "hdr_old"
    old.mkdir()
    shutil.copyfile(HERE / "m33_mod_overlay_pre_g6p30.h", old / "m33_mod_overlay.h")
    exe = nd / "g5p1_tx_test_old.exe"
    bat = nd / "build_old.bat"
    bat.write_text(f'@echo off\ncall "{p1.VCVARS}" >nul 2>&1\ncl /nologo /std:c++20 /EHsc /O2 /W3 '
                   f'/D_CRT_SECURE_NO_WARNINGS /I"{old}" "{HERE / "g5p1_tx_test.cpp"}" /Fe:"{exe}" /Fo:"{nd}\\\\" '
                   f'>"{exe}.build.log" 2>&1\nexit /b %errorlevel%\n', encoding="ascii")
    subprocess.run(["cmd", "/c", str(bat)], capture_output=True)
    exes["old"] = exe
    EX = HERE / "level_patch_examples"

    def plan(name, mods, env=None):
        with p1.dev_env(env):
            res, text, _ = g3.compile_plan(name, mods, env=env)
        if not text or "level-tx" not in text:
            raise SystemExit(f"{name}: no transaction plan ({res})")
        return p1.parse_plan(text)

    def lp(name, d, env=None):
        return plan(name, [(d["id"], [{"type": "level-patch", "patch": d}])], env)

    def write(name, m):
        q = nd / f"plan_{name}.txt"
        q.write_text(p1.emit(m), encoding="utf-8")
        return q

    def retx(m):
        """Recompute every tx-file result and the transaction id from the plan's own ranges."""
        img = p1.images(m)
        mem = []
        for f in m["files"]:
            if f["tx"]:
                role, orig, guest, _ = f["tx"][0].split(" ")
                res = rm.sha256_bytes(img[Path(f["path"]).name])
                f["tx"][0] = " ".join([role, orig, guest, res])
                mem.append((role, Path(f["path"]).name, f["size"], orig, int(guest), res))
        h = m["txs"][0].split(" ")
        h[4] = rm.tx_id(h[2], h[3], mem, int(h[1]))
        m["txs"][0] = " ".join(h)
        return m

    def tamper(m, fname, pick, fn):
        """Replace the bytes of the first range of file `fname` that `pick(offset, length)` selects by fn(bytes)."""
        f = next(x for x in m["files"] if Path(x["path"]).name == fname)
        for k, r in enumerate(f["range"]):
            off, length, gb, nb, mid, blob = r.split(" ", 5)
            if pick(int(off), int(length)):
                b = bytes(fn(bytearray(Path(blob).read_bytes()), int(off)))
                q = nd / f"blob_{len(list(nd.glob('blob_*')))}.bin"
                q.write_bytes(b)
                f["range"][k] = " ".join([off, length, gb, f"{p1.fnv(b):016x}", mid, str(q)])
                return retx(m)
        raise SystemExit(f"no range of {fname} selected")

    r = json.loads((WORK / "policy.json").read_text(encoding="utf-8"))
    win = [(o, o + n) for o, n in r["windows"]]
    inwin = lambda o, n: any(a <= o < b for a, b in win)   # noqa: E731
    basin = lp("basin", g28.doc(EX / "g6p25_west_basin_fairy.json"))
    preset = lp("preset", g28.doc(EX / "g6p20_reference.json"))
    dip = lp("dip", g28.doc(EX / "g6p22_west_dip_fairy.json"))
    ed = json.loads(json.dumps(g28.doc(EX / "g6p22_west_dip_fairy.json")))
    ed["id"] = "g6p30.editor"
    tp = next(c for c in ed["components"] if c["type"] == "terrain")["patch"]
    tp["groups"] = [{"name": "vertex-0", "vertices": [0], "delta_z": -0.3}, {"name": "vertex-4", "vertices": [4],
                                                                            "delta_z": -0.05}]
    editor = lp("editor", ed)
    graphb = lp("graphb", g28.doc(EX / "graph_b.json"), env=LEVEL)
    route = lp("route", g28.doc(EX / "g6p28_fairy_route.json"), env=LEVEL)
    mid = g3.WPOS if hasattr(g3, "WPOS") else None
    lvl = (GAME / "GAMEDATAbin" / LEVEL / f"{LEVEL}.lvl").read_bytes()
    w3, w4 = struct.unpack_from(">3f", lvl, 0x336184), struct.unpack_from(">3f", lvl, 0x336144)
    igm20 = {"type": "insert-graph-node", "level": LEVEL, "model": rm.FAIRY20, "instance": 2, "variable": 2,
             "after_node": 3, "lvl_sha256": rm.STRUCT_ALLOW[LEVEL]["lvl"][1],
             "ptr_sha256": rm.STRUCT_ALLOW[LEVEL]["ptr"][1], "position": [(a + b) / 2 for a, b in zip(w3, w4)]}
    v1 = plan("v1", [("g6p30.v1", [igm20])], env=LEVEL)
    toad = {"type": "insert-toad-intro", "level": "intro_10", "model": rm.TOAD10, "instance": 1,
            "lvl_sha256": rm.STRUCT_ALLOW["intro_10"]["lvl"][1], "ptr_sha256": rm.STRUCT_ALLOW["intro_10"]["ptr"][1],
            "transit_sha256": rm.TOAD_ALLOW["intro_10"]["transit"][1], "placement": "at_source",
            "owner": "dynamic_world"}
    i10 = plan("i10", [("g6p30.toad", [toad])], env="intro_10")
    cp = lambda m: json.loads(json.dumps(m))   # noqa: E731
    L, P_, T = f"{LEVEL}.lvl", f"{LEVEL}.ptr", "transit.lvl"
    plans = {
        "basin": write("basin", basin), "preset": write("preset", preset), "dip": write("dip", dip),
        "editor": write("editor", editor), "graphb": write("graphb", graphb), "route": write("route", route),
        "v1": write("v1", v1), "i10": write("i10", i10),
        "window_out_of_bound": write("wob", tamper(cp(basin), L, lambda o, n: inwin(o, n) and n >= 4,
                                                  lambda b, o: b[:0] + struct.pack(">f", struct.unpack(">f", b[:4])[0]
                                                                                    + 1.0) + b[4:])),
        "window_nan": write("wnan", tamper(cp(basin), L, lambda o, n: inwin(o, n) and n >= 4,
                                           lambda b, o: bytearray(b"\x7f\xc0\x00\x00") + b[4:])),
        "byte_outside_windows": write("outside", tamper(cp(basin), L, lambda o, n: o >= 6135684,
                                                        lambda b, o: b[:100] + bytes([b[100] ^ 1]) + b[101:])),
        "ptr_relocation_changed": write("ptr", tamper(cp(basin), P_, lambda o, n: o == 0,
                                                      lambda b, o: b[:8] + bytes([b[8] ^ 4]) + b[9:])),
        "transit_changed": write("transit", tamper(cp(basin), T, lambda o, n: True,
                                                   lambda b, o: b[:3] + bytes([b[3] ^ 1]))),
        "missing_transit": write("mt", (lambda m: (m["files"].pop(next(i for i, f in enumerate(m["files"])
                                                                        if Path(f["path"]).name == T)), m)[1])(cp(basin))),
        "corrupt_id": write("cid", (lambda m: (m.update(txs=[m["txs"][0][:-1] + ("0" if m["txs"][0][-1] != "0"
                                                                                  else "1")]), m)[1])(cp(basin))),
        "excessive_growth": write("grow", (lambda m: [f["tx"].__setitem__(0, " ".join(
            f["tx"][0].split(" ")[:2] + [str(int(f["tx"][0].split(" ")[2]) + 8192)] + f["tx"][0].split(" ")[3:]))
            for f in m["files"] if Path(f["path"]).name == L] and m)(cp(basin))),
        "version_3": write("v3", (lambda m: (m.update(txs=[m["txs"][0].replace("level-tx 2 ", "level-tx 3 ", 1)]),
                                             m)[1])(cp(basin))),
        "overlapping_ranges": write("ovl", (lambda m: [f["range"].append(f["range"][0]) for f in m["files"]
                                                       if Path(f["path"]).name == L] and m)(cp(basin))),
    }
    imgs = {}
    for k, m in (("basin", basin), ("preset", preset), ("dip", dip), ("editor", editor)):
        im = p1.images(m)
        imgs[k] = []
        for n in (L, P_, T):
            q = nd / f"img_{k}_{n}"
            q.write_bytes(im[n])
            imgs[k].append(str(q))
    g = GAME / "GAMEDATAbin"
    f20 = [str(g / LEVEL / L), str(g / LEVEL / P_), str(g / LEVEL / T)]
    f10 = [str(g / "intro_10" / "intro_10.lvl"), str(g / "intro_10" / "intro_10.ptr"), str(g / "intro_10" / T)]
    O = ["-", "-", "-"]
    cases = [
        ("P1 west-basin (G6-P27 images)", "basin", "-", "active", "lvl,ptr,transit", f20, imgs["basin"]),
        ("P2 preset start-two-step-v1 (G6-P20 images), transit first", "preset", "-", "active", "transit,ptr,lvl",
         f20, imgs["preset"]),
        ("P3 west-dip (G6-P23 images), ptr first", "dip", "-", "active", "ptr,lvl,transit", f20, imgs["dip"]),
        ("P4 editor-style start-floor-v1 0 -0.30 / 4 -0.05 (offline)", "editor", "-", "active", "lvl,ptr,transit",
         f20, imgs["editor"]),
        ("N1 graph B FairyLight", "graphb", "-", "tx_policy_content", "lvl,ptr,transit", f20, O),
        ("N2 graph C route (development-only)", "route", "-", "tx_policy_content", "lvl,ptr,transit", f20, O),
        ("N3 route with the old development variable set (bypass attempt)", "route", "intro_20", "tx_policy_content",
         "transit,lvl,ptr", f20, O),
        ("N4 intro_20 version-1 transaction (graph node)", "v1", "intro_20", "tx_version", "lvl,ptr", f20, O),
        ("N5 intro_10 transaction (Toad), variable set", "i10", "intro_10", "tx_level", "lvl,ptr,transit", f10, O),
        ("N6 terrain word +1.0 (rehashed)", "window_out_of_bound", "-", "tx_policy_terrain", "lvl,ptr,transit", f20,
         O),
        ("N7 terrain word NaN (rehashed)", "window_nan", "-", "tx_policy_terrain", "ptr,lvl,transit", f20, O),
        ("N8 one byte outside the windows (rehashed)", "byte_outside_windows", "-", "tx_policy_content",
         "lvl,ptr,transit", f20, O),
        ("N9 pointer table changed (rehashed)", "ptr_relocation_changed", "-", "tx_policy_result", "ptr,lvl,transit",
         f20, O),
        ("N10 transit changed (rehashed)", "transit_changed", "-", "tx_policy_result", "transit,lvl,ptr", f20, O),
        ("N11 incomplete: transit member missing", "missing_transit", "-", "tx_incomplete", "lvl,ptr,transit", f20, O),
        ("N12 corrupted transaction id", "corrupt_id", "-", "tx_id", "lvl,ptr,transit", f20, O),
        ("N13 growth beyond the member bound", "excessive_growth", "-", "tx_bounds", "lvl,ptr,transit", f20, O),
        ("N14 unknown transaction version 3", "version_3", "-", "tx_version", "lvl,ptr,transit", f20, O),
        ("N15 duplicate / overlapping range", "overlapping_ranges", "-", "ranges_overlap", "lvl,ptr,transit", f20, O),
    ]
    control = [("C1 pre-G6-P30 production header refuses west-basin", "basin", "-", "unknown_record",
                "lvl,ptr,transit", f20, O)]
    out = {}
    for kind, cs in (("prod", cases), ("old", control)):
        cf = nd / f"cases_{kind}.tsv"
        cf.write_text("".join("\t".join([n, str(plans[p]), env, want, order, f[0], f[1], e[0], e[1], f[2], e[2]]) + "\n"
                              for n, p, env, want, order, f, e in cs), encoding="utf-8")
        rr = subprocess.run([str(exes[kind]), str(cf)], capture_output=True, text=True, timeout=900)
        out[kind] = rr.stdout.strip().splitlines()
        print("\n".join(out[kind]))
    ok = all(x.rstrip().endswith(f"PASS {len(c)}/{len(c)}") for x, c in ((out["prod"][-1], cases),
                                                                       (out["old"][-1], control)))
    (nd / "summary.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print("NEGTEST_G6P30", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["negtest"]:
        sys.exit(negtest())
    if sys.argv[1:] == ["header"]:
        r = json.loads((WORK / "policy.json").read_text(encoding="utf-8"))
        HEADER.write_text(build_header(cpp(r)), encoding="utf-8", newline="\n")
        print("wrote", HEADER)
        sys.exit(0)
    if sys.argv[1:] == ["derive"]:
        r, _ = derive()
        print(json.dumps({k: v for k, v in r.items() if k != "windows"}, indent=1))
        print(len(r["windows"]), "windows")
        print(cpp(r))
        sys.exit(0 if r["invariant_ok"] else 1)
    if sys.argv[1:] == ["check"]:
        r, _ = derive()
        ok = r["invariant_ok"] and cpp(r) in HEADER.read_text(encoding="utf-8")
        print("PASS" if ok else "FAIL", r["configurations"], "configurations")
        sys.exit(0 if ok else 1)
    raise SystemExit(__doc__)

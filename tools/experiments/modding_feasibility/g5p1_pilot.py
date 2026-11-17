#!/usr/bin/env python3
"""E-476 (D-243) G5-P1: the development-only structural mod pipeline for one `insert-graph-node` (intro_10 flight
graph, one node after node 13), through the production mod compiler (tools/r3hd_mods.py, G5-P1 section) and the
development `level-tx` runtime (g5p1_dev_gate.py). The G3b constructor (g3b_ab.py, E-469) is the test oracle only;
nothing here or in the compiler imports it at plan time.

usage:
  g5p1_pilot.py check            offline: P1 equivalence with G3b, plan records, compiler / simulator refusals,
                                 composition and priority (real game data, private mods roots; no game started)
  g5p1_pilot.py negtest          deterministic runtime test: plan variants through g5p1_tx_test.cpp built against the
                                 development header and against the unchanged production header (no game started)
  g5p1_pilot.py TAG [--cases ..] hidden runs (development build, gate applied), as G3b's harness
  g5p1_pilot.py judge TAG        P1-P8
Outputs stay under private/work/e476/ (plans, range files and images are derived from the user's game files and are
never committed).

PROSPECTIVE FUNCTIONAL PROTOCOL (committed before any game run; thresholds are G3b's, E-469, unchanged)
Build: development runtime = g5p1_dev_gate.py apply + tools\\build_incremental.bat (the SDK copy of the overlay with
  R3HD_DEV_STRUCTURAL_TX defined); production restored afterwards (revert + rebuild).
Cases (one hidden run each, through g3b_ab.py's runner unchanged: m9_license_run.py, hidden non-activating window,
  muted, no physical pad, private user root, `--test-level intro_10`, no input, no captures, 150 s, the flight
  generator sampled every 0.1 s for 75 s, the appended tail read every 1 s; block-8 snapshots):
  A base: no plan.  B neutral: the compiler's plan for mod g5p1.neutral (G3b's M), R3HD_DEV_STRUCTURAL_TX=intro_10.
  C offset: the compiler's plan for g5p1.offset (G3b's M'), same variable.  D nogate: C's plan, the variable unset
  (the development runtime must refuse the whole plan: `level_tx_not_enabled`).
  Plans are written by r3hd_mods.resolve_all from installed mods (private mods roots), never by the G3b constructor.
Criteria:
  P1 compiler equivalence: `check` passes (byte-identical .lvl / .ptr images to g3b_ab.construct for both variants,
     every listed sub-check), re-run on the run's baseline.
  P2 transaction integrity: `negtest` passes on the same baseline (development 30 / 30, production 5 / 5); B and C
     logs hold `M33 mods state=active` and exactly one `G5P1 level-tx active level=intro_10 mod=g5p1.<variant> id=<the
     plan's id>`; D's log holds `state=refused reason=level_tx_not_enabled` and no `M36 grow` and no `M33 mods served`
     line; A `M33 mods=off`.
  P3 runtime growth: G3b N1 with D's refusal reason `level_tx_not_enabled` (the only change to G3b's judge): B / C
     `M36 grow size` exactly intro_10.lvl 7661836 -> 7661948 and intro_10.ptr 209068 -> 209140, grow reads of those
     two only, kind=tail, only those two served; masked read-back of the original area equal in A-D; tail fixed bytes
     equal to the expectation at every read for >= 55 s; node 13 / 14 waypoints unchanged.
  P4 relocation and registration: G3b N2, N3 and N4 (the nine new pointers at their predicted addresses, live count
     144 / 143, forward and backward walks, N at walk index 14, A's 143 nodes in order, arcs).
  P5 functional consumption: G3b N5 (generator variable 8 = N's waypoint in >= 3 samples, entered only from node 13's
     and left only for node 14's waypoint, >= 2 visits, variable 10 = M / M' within 1e-4; never in A / D).
  P6 functional effect: G3b N6 and N7 (B within 1.0 of A's path near M and 0.5 beyond 25 units, D within 0.5; C
     >= 1.5 from A within 25 units toward M', >= 1.0 closer to M' than A and B, >= 1.5 from B's path, <= 0.5 beyond
     25). Tolerances: G3b's prospective values (E-464 noise 0.15, isolation 0.5, gain 0.49); G3b k1 measured 0.586 /
     0.196 / 0.117 / 3.989, inside them.
  P7 conflict and security rejection: `check` refusal / composition / priority sub-checks and `negtest` all pass (no
     partial structural application in any refused case, both open orders); D refused whole at run time.
  P8 safety: G3b N8 (valid block-8 walks; area 7,661,944 / 7,661,832, free after load 13,088,416 / 13,088,528; M21 /
     M22 / M23 0; haptics policy line; runner exit 0; no game process left).
  Invalid (new tag, not judged): G3b's invalid conditions (file hashes, level not opened, area / generator not
  found, < 60 s of samples, first sample after A's closest approach to node 13's waypoint).
  Classes: P1-P2 + P7 = pipeline and transaction; P3-P4 = structural insertion through the pipeline; P5 = consumption;
  P6 = functional effect. All eight = G5-P1 VERIFIED.
"""
import argparse
import contextlib
import hashlib
import inspect
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
import r3hd_mods as rm  # noqa: E402
import g3a_ab as g3a  # noqa: E402
import g3b_ab as g3b  # noqa: E402

PREFIX = "e476"
WORK = ROOT / "private" / "work" / PREFIX
ENV = rm.STRUCT_ENV
LEVEL = "intro_10"
GAME = g3a.GAME
LVL_SHA = rm.STRUCT_ALLOW[LEVEL]["lvl"][1]
PTR_SHA = rm.STRUCT_ALLOW[LEVEL]["ptr"][1]
NEUTRAL_LVL_FNV, PTR_FNV_G3B = "fbb2dd5392b51146", "611fc0c224cd5100"   # G3b served payloads (E-469)
u32, fnv = g3a.u32, g3a.fnv


@contextlib.contextmanager
def dev_env(value=LEVEL):
    old = os.environ.get(ENV)
    if value is None:
        os.environ.pop(ENV, None)
    else:
        os.environ[ENV] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(ENV, None)
        else:
            os.environ[ENV] = old


def igm(variant="neutral", **kw):
    o = {"type": "insert-graph-node", "level": LEVEL, "model": rm.FLY10, "instance": 0, "variable": 0,
         "after_node": 13, "lvl_sha256": LVL_SHA, "ptr_sha256": PTR_SHA, "position": list(g3b.WPOS[variant])}
    o.update(kw)
    return o


def manifest(mid, overrides, **kw):
    m = {"format": 1, "id": mid, "name": mid, "version": "1.0.0", "overrides": overrides,
         "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids({"game": GAME}), "min_port_version": "0.0.1"}}
    m.update(kw)
    return m


def fresh(name):
    d = WORK / "roots" / name
    if d.exists():
        shutil.rmtree(d)   # our own folder under private/work/e476 (no links inside)
    d.mkdir(parents=True)
    return {"home": None, "mods": d / "mods", "cache": d / "cache", "game": GAME, "_dir": d}


def install(paths, mid, overrides, **kw):
    src = paths["_dir"] / "src" / mid
    src.mkdir(parents=True)
    (src / "mod.json").write_text(json.dumps(manifest(mid, overrides, **kw)), encoding="utf-8")
    rm.cmd_import(paths, src, enable=True)


def waypoint13():
    data = g3a.files()[0]
    return {"type": "waypoint-position", "level": LEVEL, "model": rm.FLY10, "instance": 0, "variable": 0, "node": 13,
            "waypoint_sha256": rm.sha256_bytes(data[g3b.WP13:g3b.WP13 + 0x14]),
            "position": [19.0, -33.0, -40.0]}


# --- plans: parse, images, variants -----------------------------------------------------------------------------

def parse_plan(text):
    m = {"head": [], "mods": [], "gameplay": [], "txs": [], "files": []}
    for ln in text.splitlines():
        if not ln:
            continue
        k = ln.split(" ", 1)[0]
        if k in ("R3HD_MOD_PLAN",) or k.startswith("#"):
            m["head"].append(ln)
        elif k == "mod":
            m["mods"].append(ln)
        elif k == "gameplay":
            m["gameplay"].append(ln)
        elif k == "level-tx":
            m["txs"].append(ln)
        elif k == "file":
            _, size, path = ln.split(" ", 2)
            m["files"].append({"size": int(size), "path": path, "tx": [], "grow": [], "range": []})
        elif k in ("tx-file", "grow", "range"):
            _, idx, rest = ln.split(" ", 2)
            m["files"][int(idx)][k if k != "tx-file" else "tx"].append(rest)
        elif k == "end":
            pass
        else:
            raise ValueError(ln)
    return m


def emit(m, tx_first=True, tx_after_grow=False):
    lines = list(m["head"]) + list(m["mods"]) + list(m["gameplay"])
    if tx_first:
        lines += m["txs"]
    body = []
    for i, f in enumerate(m["files"]):
        lines.append(f"file {f['size']} {f['path']}")
        tx = [f"tx-file {i} {t}" for t in f["tx"]]
        grow = [f"grow {i} {g}" for g in f["grow"]]
        lines += (grow + tx) if tx_after_grow else (tx + grow)
        body += [f"range {i} {r}" for r in f["range"]]
    if not tx_first:
        lines += m["txs"]
    lines += body + [f"end {len(m['files'])} {len(body)}", ""]
    return "\n".join(lines)


def images(m):
    """{file name: guest image} = the original file with every range laid over it (grown to its grow size)."""
    out = {}
    for f in m["files"]:
        data = bytearray(Path(f["path"]).read_bytes())
        for g in f["grow"]:
            data += bytes(int(g) - len(data))
        for r in f["range"]:
            off, length, _, _, _, blob = r.split(" ", 5)
            data[int(off):int(off) + int(length)] = Path(blob).read_bytes()
        out[Path(f["path"]).name] = bytes(data)
    return out


def compile_plan(name, mods):
    """mods: [(id, overrides)] in priority order -> (resolve report, plan text or None, paths)."""
    paths = fresh(name)
    with dev_env():
        for mid, ov in mods:
            install(paths, mid, ov)
        res = rm.resolve_all(paths, write_plan=paths["cache"])
    plan = paths["cache"] / rm.PLAN_NAME
    return res, (plan.read_text(encoding="utf-8") if plan.is_file() else None), paths


# --- offline check ------------------------------------------------------------------------------------------------

def refused(fn, code):
    try:
        fn()
    except rm.Refusal as x:
        return x.code == code or f"{x.code}: {x.detail}"
    return False


def check():
    data, ptr = g3a.files()
    res, det = {}, {}
    # P1: the compiler's output for the G3b parameters equals the G3b construction byte for byte
    for v in g3b.GROWN:
        r, text, paths = compile_plan(f"eq_{v}", [(f"g5p1.{v}", [igm(v)])])
        m = parse_plan(text or "")
        im = images(m) if text else {}
        nl, np_, tail, nslots = g3b.construct(data, ptr, v)
        L, P = im.get("intro_10.lvl", b""), im.get("intro_10.ptr", b"")
        n0, n1 = u32(ptr, 0), u32(P, 0) if len(P) >= 4 else 0
        new_entries = [struct.unpack_from(">iI", P, 4 + 8 * i) for i in range(n0, n1)] if n1 > n0 else []
        oracle_entries = [struct.unpack_from(">iI", np_, 4 + 8 * i) for i in range(n0, u32(np_, 0))]
        diff = sorted({i & ~3 for i in range(len(data)) if L[i:i + 1] != data[i:i + 1]}) if L else None
        odiff = sorted({i & ~3 for i in range(len(data)) if nl[i] != data[i]})
        B1 = 0x40F5509C

        def walk(lvl, p):
            area, _, dup = g3a.relocate(lvl, p, B1)
            rd = lambda a: u32(area, a - B1)   # noqa: E731
            nodes, prob, hdr = g3b.walk_null(rd, B1 + g3b.GRAPH - 4)
            al = rd(B1 + g3b.NODE13 - 4 + 0x18)
            arcs = {"count": rd(al + 8), "target": rd(rd(al) + 0xC)}
            wp = struct.unpack_from(">3f", area, g3b.FW - 4)
            return nodes, prob, hdr, sorted(dup), arcs, wp
        wc, wo = (walk(L, P) if L else None), walk(nl, np_)
        eq = {
            "lvl_size": len(L) == len(nl) == g3b.SIZE + g3b.N,
            "ptr_size": len(P) == len(np_) == g3b.PSIZE + 8 * g3b.K,
            "original_byte_edits": diff == odiff and len(odiff) == 4,
            "appended_structures": L[g3b.SIZE:] == tail,
            "relocation_entries": new_entries == oracle_entries and len(new_entries) == 9,
            "cross_file_table": P[4 + 8 * n1:] == np_[4 + 8 * u32(np_, 0):] == ptr[4 + 8 * n0:],
            "graph_count": u32(L, g3b.COUNT_AT) == 144 if L else False,
            "forward_backward_walk": bool(wc) and wc[0] == wo[0] and not wc[1] and len(wc[0]) == 144
                                     and not wc[3],
            "arc_connectivity": bool(wc) and wc[4] == wo[4] == {"count": 1, "target": B1 + g3b.FN - 4},
            "waypoint_placement": bool(wc) and wc[5] == wo[5] == g3b.WPOS[v],
            "lvl_bytes_identical": L == nl,
            "ptr_bytes_identical": P == np_,
        }
        if v == "neutral":
            eq["g3b_served_hashes"] = f"{fnv(L):016x}" == NEUTRAL_LVL_FNV and f"{fnv(P):016x}" == PTR_FNV_G3B
        for k, x in eq.items():
            res[f"P1_{v}_{k}"] = bool(x)
        recs = {"level-tx": len(m["txs"]), "tx-file": sum(len(f["tx"]) for f in m["files"]),
                "grow": sum(len(f["grow"]) for f in m["files"]), "ranges": [len(f["range"]) for f in m["files"]],
                "gameplay": m["gameplay"]}
        res[f"plan_{v}_records"] = (recs == {"level-tx": 1, "tx-file": 2, "grow": 2, "ranges": [5, 1],
                                             "gameplay": [f"gameplay g5p1.{v}"]}
                                    and r["structural_active"] == {f"g5p1.{v}": LEVEL})
        det[v] = {"plan_records": recs, "lvl_fnv": f"{fnv(L):016x}", "ptr_fnv": f"{fnv(P):016x}",
                  "lvl_sha256": hashlib.sha256(L).hexdigest(), "ptr_sha256": hashlib.sha256(P).hexdigest(),
                  "tx": m["txs"], "tx_files": [f["tx"] for f in m["files"]]}
    # determinism: compiling twice gives the same plan apart from the timestamp comment and cache paths
    r2, text2, _ = compile_plan("eq_neutral_again", [("g5p1.neutral", [igm("neutral")])])
    t1 = (WORK / "roots" / "eq_neutral" / "cache" / rm.PLAN_NAME).read_text(encoding="utf-8")
    strip = lambda t: [re.sub(r"roots\\[^\\]+\\", "", ln) for ln in t.splitlines() if not ln.startswith("#")]  # noqa
    res["deterministic"] = strip(t1) == strip(text2)

    # manifest / compiler refusals
    paths = {"game": GAME}
    cases = [("not enabled (no development opt-in)", lambda: rm.parse_insert_graph_node(igm(), "o"),
              "UNSUPPORTED", None)]
    cases += [(label, fn, code, LEVEL) for label, fn, code in [
            ("unknown key", lambda: rm.parse_insert_graph_node(igm(extra=1), "o"), "BAD_MANIFEST"),
            ("missing key", lambda: rm.parse_insert_graph_node({k: v for k, v in igm().items() if k != "after_node"},
                                                               "o"), "BAD_MANIFEST"),
            ("NaN position", lambda: rm.parse_insert_graph_node(igm(position=[float("nan"), 0, 0]), "o"),
             "BAD_MANIFEST"),
            ("boolean index", lambda: rm.parse_insert_graph_node(igm(after_node=True), "o"), "BAD_MANIFEST"),
            ("raw offset key (no addresses accepted)", lambda: rm.parse_insert_graph_node(igm(offset=7661836), "o"),
             "BAD_MANIFEST"),
            ("unsupported level", lambda: rm.parse_insert_graph_node(igm(level="intro_15"), "o"), "UNSUPPORTED"),
            ("two structural operations in one mod", lambda: rm.parse_manifest({"mod.json": json.dumps(
                manifest("x.two", [igm(), igm("offset")])).encode()}), "BAD_MANIFEST"),
            ("wrong .lvl hash", lambda: rm.compile_insert_graph_node(igm(lvl_sha256="0" * 64), paths),
             "TARGET_CHANGED"),
            ("wrong .ptr hash", lambda: rm.compile_insert_graph_node(igm(ptr_sha256="1" * 64), paths),
             "TARGET_CHANGED"),
            ("unsupported graph identity (other variable)", lambda: rm.compile_insert_graph_node(igm(variable=1),
                                                                                                 paths),
             "TARGET_MISSING"),
            ("unsupported graph identity (other model)", lambda: rm.compile_insert_graph_node(
                igm(model=rm.FLY10.replace("FlyInit", "FlyIdle")), paths), "TARGET_MISSING"),
            ("insertion segment not allow-listed (after 12)", lambda: rm.compile_insert_graph_node(
                igm(after_node=12), paths), "UNSUPPORTED"),
            ("last node (no following node)", lambda: rm.compile_insert_graph_node(igm(after_node=142), paths),
             "UNSUPPORTED"),
            ("position too far from the segment", lambda: rm.compile_insert_graph_node(
                igm(position=[g3b.M[0] + 20, g3b.M[1], g3b.M[2]]), paths), "UNSUPPORTED"),
        ]]
    cases.append(("enabled for another level only", lambda: rm.compile_insert_graph_node(igm(), paths),
                  "UNSUPPORTED", "intro_15"))
    for label, fn, code, env in cases:
        with dev_env(env):
            got = refused(fn, code)
        res[f"refuse_{label}"] = got is True
        if got is not True:
            det.setdefault("refusals", {})[label] = got

    # structural simulator: mutated inputs and corrupted outputs are refused (STRUCTURE_CHECK)
    ix = rm.read_script_index(GAME, LEVEL)
    entry = ix["graphs"][(rm.FLY10, 0, 0)]
    pos = g3b.WPOS["neutral"]

    def b(lvl=data, p=ptr):
        return lambda: rm.build_insert_node(lvl, p, 1, entry, 13, pos, "t")

    def put(buf, off, val):
        x = bytearray(buf)
        struct.pack_into(">I", x, off, val)
        return bytes(x)
    n0 = u32(ptr, 0)
    dup_ptr = put(ptr, 4 + 8 * (n0 - 1) + 4, struct.unpack_from(">iI", ptr, 4)[1])   # last entry = first's slot
    # the graph's other relocated words for "broken arc": node 13's arc target -> node 12
    scases = [
        ("duplicate slot in the original table", b(p=struct.pack(">I", n0) + dup_ptr[4:]), "STRUCTURE_CHECK"),
        ("pointer-table layout (cross-file count)", b(lvl=put(data, 0, u32(data, 0) + 1)), "STRUCTURE_CHECK"),
        ("incorrect graph count", b(lvl=put(data, g3b.COUNT_AT, 142)), "STRUCTURE_CHECK"),
        ("broken sibling link (node 13 next)", b(lvl=put(data, g3b.NODE13, g3b.NODE12 - 4)), "STRUCTURE_CHECK"),
        ("broken backward link (node 14 previous)", b(lvl=put(data, g3b.NODE14 + 4, g3b.NODE12 - 4)),
         "STRUCTURE_CHECK"),
        ("broken arc target", b(lvl=put(data, g3b.ARC13 + 0xC, g3b.NODE12 - 4)), "STRUCTURE_CHECK"),
        ("junction (arc list count 2)", b(lvl=put(data, rm._u32(data, g3b.NODE13 + 0x18) + 4 + 8, 2)),
         "STRUCTURE_CHECK"),
    ]
    good_l, good_p, edits, _ = rm.build_insert_node(data, ptr, 1, entry, 13, pos, "t")
    nodes = [nd for nd, _ in entry["nodes"]]
    place = {"node": g3b.FN, "waypoint": g3b.FW, "list": g3b.FL, "arc": g3b.FA}

    def v(lvl=good_l, p=good_p, slots=None):
        return lambda: rm.verify_insert(data, ptr, lvl, p, 1, g3b.GRAPH, nodes, 13, place,
                                        slots or [g3b.FN + k for k in (0, 4, 8, 0xC, 0x18)]
                                        + [g3b.FL, g3b.FL + 4, g3b.FA + 8, g3b.FA + 0xC], edits, "t")
    n1 = u32(good_p, 0)
    dup_new = bytearray(good_p)
    struct.pack_into(">iI", dup_new, 4 + 8 * (n1 - 1), 1, g3b.FN - 4)    # last new entry = the first new slot
    scases += [
        ("simulator accepts the valid output", None, None),
        ("simulator: duplicate relocation slot", v(p=bytes(dup_new)), "STRUCTURE_CHECK"),
        ("simulator: invalid relocation target", v(lvl=put(good_l, g3b.FA + 0xC, 0x00100000)), "STRUCTURE_CHECK"),
        ("simulator: target outside the file", v(lvl=put(good_l, g3b.FN + 0xC, len(good_l) + 64)),
         "STRUCTURE_CHECK"),
        ("simulator: incorrect graph count", v(lvl=put(good_l, g3b.COUNT_AT, 143)), "STRUCTURE_CHECK"),
        ("simulator: broken sibling link", v(lvl=put(good_l, g3b.FN, g3b.NODE12 - 4)), "STRUCTURE_CHECK"),
        ("simulator: broken arc linkage", v(lvl=put(good_l, g3b.FL, g3b.FL - 4)), "STRUCTURE_CHECK"),
        ("simulator: an unplanned word changed", v(lvl=put(good_l, 0x100, u32(good_l, 0x100) ^ 1)),
         "STRUCTURE_CHECK"),
        ("simulator: cross-file table changed", v(p=good_p[:-4] + bytes([good_p[-4] ^ 1]) + good_p[-3:]),
         "STRUCTURE_CHECK"),
    ]
    for label, fn, code in scases:
        if fn is None:
            try:
                v()()
                res[f"structure_{label}"] = True
            except rm.Refusal as x:
                res[f"structure_{label}"] = False
                det.setdefault("structure", {})[label] = x.detail
            continue
        got = refused(fn, code)
        res[f"structure_{label}"] = got is True
        if got is not True:
            det.setdefault("structure", {})[label] = got

    # composition and priority (resolve_all over private mods roots)
    comp = {}
    r, text, _ = compile_plan("two_structural", [("s.a", [igm("neutral")]), ("s.b", [igm("offset")])])
    codes = {x["id"]: x.get("code") for x in r["mods"]}
    res["comp_two_structural_both_refused"] = (codes == {"s.a": "STRUCTURAL_CONFLICT", "s.b": "STRUCTURAL_CONFLICT"}
                                               and not r["active"] and text is None)
    comp["two_structural"] = {x["id"]: (x["state"], x.get("code"), x.get("detail")) for x in r["mods"]}
    r, text, _ = compile_plan("with_waypoint", [("s.a", [igm("neutral")]), ("w.13", [waypoint13()])])
    res["comp_disjoint_waypoint_composes"] = (r["active"] == ["s.a", "w.13"] and text is not None
                                              and r["gameplay_active"] == ["s.a", "w.13"])
    r, text, _ = compile_plan("with_waypoint_rev", [("w.13", [waypoint13()]), ("s.a", [igm("neutral")])])
    res["comp_disjoint_waypoint_composes_reversed"] = r["active"] == ["w.13", "s.a"] and text is not None
    # fixed-size overlap: no existing override type can address the four edited words or the pointer table, so a
    # synthetic fixed-size range over the graph's count word stands in for one (resolve_all's policy is what is tested)
    real_compile = rm.compile_mod

    def fake_compile(m, files, paths, manifests=None):
        if m["id"].startswith("f."):
            m["_linked"] = m["id"].startswith("f.linked")
            return [(g3a.LVL, g3b.COUNT_AT, struct.pack(">I", 7), "synthetic.count")]
        return real_compile(m, files, paths, manifests)
    rm.compile_mod = fake_compile
    try:
        for label, order, want_active, want_code in (
                ("structural_over_fixed", [("s.a", [igm()]), ("f.fixed", [waypoint13()])], ["s.a"],
                 {"f.fixed": "STRUCTURAL_CONFLICT"}),
                ("fixed_over_structural", [("f.fixed", [waypoint13()]), ("s.a", [igm()])], ["f.fixed"],
                 {"s.a": "STRUCTURAL_CONFLICT"}),
                ("structural_over_linked", [("s.a", [igm()]), ("f.linked", [waypoint13()])], ["s.a"],
                 {"f.linked": "STRUCTURAL_CONFLICT"}),
                ("linked_over_structural", [("f.linked", [waypoint13()]), ("s.a", [igm()])], ["f.linked"],
                 {"s.a": "STRUCTURAL_CONFLICT"})):
            r, text, _ = compile_plan(label, order)
            got = {x["id"]: x.get("code") for x in r["mods"] if x["state"] != "active"}
            ok = r["active"] == want_active and got == want_code
            if r["active"] == ["s.a"]:
                ok = ok and text is not None and "level-tx" in text and "synthetic" not in text
            else:
                ok = ok and (text is None or "level-tx" not in text)
            # nothing is ever shadowed in part
            ok = ok and not any(x["shadowed"] for x in r["mods"])
            res[f"comp_{label}"] = ok
            comp[label] = {x["id"]: (x["state"], x.get("code"), x.get("detail")) for x in r["mods"]}
        # existing behaviour: two non-structural, non-linked overlapping mods still shadow per range
        def fake2(m, files, paths, manifests=None):
            m["_linked"] = False
            return [(g3a.LVL, g3b.COUNT_AT, struct.pack(">I", 7 if m["id"] == "f.one" else 8), "synthetic.count")]
        rm.compile_mod = fake2
        r, text, _ = compile_plan("fixed_fixed", [("f.one", [waypoint13()]), ("f.two", [waypoint13()])])
        res["comp_fixed_fixed_unchanged_shadowing"] = (r["active"] == ["f.one", "f.two"]
                                                       and r["mods"][1]["shadowed"] == ["synthetic.count (by f.one)"])
    finally:
        rm.compile_mod = real_compile
    # a mod that requires a refused structural mod is dropped (MISSING_DEPENDENCY)
    paths = fresh("requires")
    with dev_env():
        install(paths, "s.a", [igm("neutral")])
        install(paths, "s.b", [igm("offset")])
        install(paths, "w.dep", [waypoint13()], requires=["s.a"])
        r = rm.resolve_all(paths, write_plan=paths["cache"])
    res["comp_requires_refused_structural"] = {x["id"]: x.get("code") for x in r["mods"]}.get("w.dep") \
        == "MISSING_DEPENDENCY"
    # without the development opt-in the compiler refuses such a mod (import refused; an installed one is invalid)
    paths = fresh("production_compiler")
    with dev_env():
        install(paths, "s.a", [igm("neutral")])
    with dev_env(None):
        r = rm.resolve_all(paths, write_plan=paths["cache"])
        res["production_compiler_refuses"] = (not r["active"] and r["mods"][0]["code"] == "UNSUPPORTED"
                                              and not (paths["cache"] / rm.PLAN_NAME).exists())
        src = paths["_dir"] / "src" / "s.a"
        res["production_import_refuses"] = refused(lambda: rm.cmd_import(paths, src, replace=True),
                                                   "UNSUPPORTED") is True
    det["composition"] = comp
    res["game_files_unchanged"] = g3a.files() == (data, ptr)
    out = {"checks": res, "pass": all(res.values()), "details": det}
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "offline.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"failed": [k for k, x in res.items() if not x], "passed": sum(res.values()),
                      "total": len(res), "pass": out["pass"]}, indent=1))
    return 0 if out["pass"] else 1


# --- deterministic runtime test -----------------------------------------------------------------------------------

VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"


def build_test(kind):
    d = WORK / "negtest" / f"hdr_{kind}"
    d.mkdir(parents=True, exist_ok=True)
    if kind == "dev":
        subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "render", str(d / "m33_mod_overlay.h")],
                       check=True, capture_output=True)
    else:
        shutil.copyfile(TOOLS / "m33_mod_overlay.h", d / "m33_mod_overlay.h")
    exe = WORK / "negtest" / f"g5p1_tx_test_{kind}.exe"
    bat = WORK / "negtest" / f"build_{kind}.bat"
    bat.write_text(f'@echo off\ncall "{VCVARS}" >nul 2>&1\ncl /nologo /std:c++20 /EHsc /O2 /W3 /D_CRT_SECURE_NO_WARNINGS /I"{d}" '
                   f'"{HERE / "g5p1_tx_test.cpp"}" /Fe:"{exe}" /Fo:"{WORK / "negtest"}\\\\" >"{exe}.build.log" 2>&1\n'
                   f'exit /b %errorlevel%\n', encoding="ascii")
    r = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True)
    if r.returncode or not exe.is_file():
        raise SystemExit(f"build {kind} failed: {(exe.parent / (exe.name + '.build.log')).read_text(errors='replace')}")
    return exe


def negtest():
    data, ptr = g3a.files()
    nd = WORK / "negtest"
    if nd.exists():
        shutil.rmtree(nd)
    nd.mkdir(parents=True)
    _, text, _ = compile_plan("neg_valid", [("g5p1.neutral", [igm("neutral")])])
    _, comp_text, _ = compile_plan("neg_comp", [("g5p1.neutral", [igm("neutral")]), ("w.13", [waypoint13()])])
    _, fixed_text, _ = compile_plan("neg_fixed", [("w.13", [waypoint13()])])
    base = parse_plan(text)
    im = images(base)
    nl, np_ = g3b.construct(data, ptr, "neutral")[:2]
    assert im["intro_10.lvl"] == nl and im["intro_10.ptr"] == np_
    (nd / "valid_lvl.bin").write_bytes(nl)
    (nd / "valid_ptr.bin").write_bytes(np_)
    ci = images(parse_plan(comp_text))
    (nd / "comp_lvl.bin").write_bytes(ci["intro_10.lvl"])
    (nd / "comp_ptr.bin").write_bytes(ci["intro_10.ptr"])
    fi = images(parse_plan(fixed_text))
    (nd / "fixed_lvl.bin").write_bytes(fi["intro_10.lvl"])
    li = next(i for i, f in enumerate(base["files"]) if f["path"].endswith("intro_10.lvl"))
    pi = 1 - li

    def variant(name, fn=None, **emit_kw):
        m = json.loads(json.dumps(base))
        if fn:
            fn(m)
        p = nd / f"plan_{name}.txt"
        p.write_text(emit(m, **emit_kw), encoding="utf-8")
        return p

    def retx(m, i, k, v):   # replace token k (0 role, 1 orig, 2 guest, 3 result) of file i's tx-file
        t = m["files"][i]["tx"][0].split(" ")
        t[k] = v
        m["files"][i]["tx"][0] = " ".join(t)

    def tamper(m, i, ri, refnv):
        off, length, gb, nb, mid, blob = m["files"][i]["range"][ri].split(" ", 5)
        b = bytearray(Path(blob).read_bytes())
        b[len(b) // 2] ^= 0x5A
        q = nd / f"tampered_{i}_{ri}_{int(refnv)}.bin"
        q.write_bytes(bytes(b))
        m["files"][i]["range"][ri] = " ".join([off, length, gb, f"{fnv(bytes(b)):016x}" if refnv else nb, mid, str(q)])

    def split_ptr(m):
        off, length, gb, nb, mid, blob = m["files"][pi]["range"][0].split(" ", 5)
        b = Path(blob).read_bytes()
        h = len(b) // 2
        own = Path(m["files"][pi]["path"]).read_bytes()
        rows = []
        for k, (lo, hi) in enumerate(((0, h), (h, len(b)))):
            q = nd / f"split_{k}.bin"
            q.write_bytes(b[lo:hi])
            rows.append(f"{lo} {hi - lo} {fnv(own[lo:min(hi, len(own))]):016x} {fnv(b[lo:hi]):016x} {mid} {q}")
        m["files"][pi]["range"] = rows

    def drop_lvl_words(m):
        m["files"][li]["range"] = [r for r in m["files"][li]["range"] if int(r.split(" ")[0]) >= g3b.SIZE]

    def bad_bound(m):
        g = g3b.SIZE + 8192
        retx(m, li, 2, str(g))
        m["files"][li]["grow"] = [str(g)]
    lvl_p, ptr_p = str(g3a.LVL), str(g3a.PTR)
    V = nd / "valid_lvl.bin", nd / "valid_ptr.bin"
    plans = {
        "valid": variant("valid"),
        "wrong_lvl_sha": variant("wrong_lvl_sha", lambda m: retx(m, li, 1, "0" * 64)),
        "wrong_ptr_sha": variant("wrong_ptr_sha", lambda m: retx(m, pi, 1, "f" * 64)),
        "wrong_size": variant("wrong_size", lambda m: m["files"][li].update(size=g3b.SIZE + 4)),
        "tx_guest_mismatch": variant("tx_guest_mismatch", lambda m: retx(m, li, 2, str(g3b.SIZE + g3b.N + 4))),
        "missing_lvl": variant("missing_lvl", lambda m: m["files"].pop(li)),
        "missing_ptr": variant("missing_ptr", lambda m: m["files"].pop(pi)),
        "lvl_tx_file_dropped": variant("lvl_tx_file_dropped", lambda m: m["files"][li].update(tx=[])),
        "tampered_ptr": variant("tampered_ptr", lambda m: tamper(m, pi, 0, False)),
        "tampered_ptr_rehashed": variant("tampered_ptr_rehashed", lambda m: tamper(m, pi, 0, True)),
        "tampered_tail_rehashed": variant("tampered_tail_rehashed", lambda m: tamper(m, li, 4, True)),
        "corrupt_tx_id": variant("corrupt_tx_id", lambda m: m.update(
            txs=[m["txs"][0][:-16] + ("0" if m["txs"][0][-16] != "0" else "1") + m["txs"][0][-15:]])),
        # G6-P1 (D-251, E-484) expectation correction, before any G6-P1 game run: version 2 became the actor
        # transaction (lvl + ptr + transit), so the unsupported-version case now claims version 3 (still `tx_version`),
        # and a version-1 plan relabelled as version 2 is its own case: refused whole, missing the transit member
        # (`tx_incomplete`). The original G5-P1 result for "2" (`tx_version`, E-476) is kept in its logs.
        "tx_version_2": variant("tx_version_2", lambda m: m.update(txs=[m["txs"][0].replace("level-tx 1 ",
                                                                                         "level-tx 3 ", 1)])),
        "tx_relabelled_2": variant("tx_relabelled_2", lambda m: m.update(txs=[m["txs"][0].replace("level-tx 1 ",
                                                                                               "level-tx 2 ", 1)])),
        "grow_without_tx": variant("grow_without_tx", lambda m: (m.update(txs=[]), [f.update(tx=[])
                                                                                   for f in m["files"]])),
        "two_tx": variant("two_tx", lambda m: m.update(txs=m["txs"] * 2)),
        "tx_file_before_level_tx": variant("tx_file_before_level_tx", tx_first=False),
        "tx_file_after_grow": variant("tx_file_after_grow", tx_after_grow=True),
        "ptr_split": variant("ptr_split", split_ptr),
        "partial_lvl_words_dropped": variant("partial_lvl_words_dropped", drop_lvl_words),
        "bound_exceeded": variant("bound_exceeded", bad_bound),
        "duplicate_tx_file": variant("duplicate_tx_file", lambda m: m["files"][li]["tx"].append(
            m["files"][li]["tx"][0])),
        "unknown_role": variant("unknown_role", lambda m: retx(m, li, 0, "map")),
        "unknown_tx_mod": variant("unknown_tx_mod", lambda m: m.update(txs=[m["txs"][0].replace(
            " g5p1.neutral ", " other.mod ", 1)])),
    }
    (nd / "plan_comp.txt").write_text(comp_text, encoding="utf-8")
    (nd / "plan_fixed.txt").write_text(fixed_text, encoding="utf-8")
    plans["comp"], plans["fixed"] = nd / "plan_comp.txt", nd / "plan_fixed.txt"
    O = ("-", "-")
    dev_cases = [
        ("valid, .lvl opened first", "valid", LEVEL, "active", "lvl,ptr", V),
        ("valid, .ptr opened first (reversed)", "valid", LEVEL, "active", "ptr,lvl", V),
        ("not enabled at run time (.lvl first)", "valid", "-", "level_tx_not_enabled", "lvl,ptr", O),
        ("not enabled at run time (.ptr first)", "valid", "-", "level_tx_not_enabled", "ptr,lvl", O),
        ("enabled for another level", "valid", "intro_15", "tx_level", "lvl,ptr", O),
        ("wrong original .lvl hash", "wrong_lvl_sha", LEVEL, "tx_identity", "lvl,ptr", O),
        ("wrong original .ptr hash (.ptr first)", "wrong_ptr_sha", LEVEL, "tx_identity", "ptr,lvl", O),
        ("wrong resource size", "wrong_size", LEVEL, "file_size", "lvl,ptr", O),
        ("tx-file size differs from grow", "tx_guest_mismatch", LEVEL, "tx_bounds", "lvl,ptr", O),
        ("missing .lvl member", "missing_lvl", LEVEL, "tx_incomplete", "ptr,lvl", O),
        ("missing .ptr member", "missing_ptr", LEVEL, "tx_incomplete", "lvl,ptr", O),
        ("growth of a member without its tx-file", "lvl_tx_file_dropped", LEVEL, "grow_not_allowed", "lvl,ptr", O),
        ("tampered .ptr replacement", "tampered_ptr", LEVEL, "blob_hash", "ptr,lvl", O),
        ("tampered .ptr replacement, range hash rewritten", "tampered_ptr_rehashed", LEVEL, "tx_result_hash",
         "ptr,lvl", O),
        ("tampered appended .lvl bytes, range hash rewritten", "tampered_tail_rehashed", LEVEL, "tx_result_hash",
         "lvl,ptr", O),
        ("corrupted transaction identifier", "corrupt_tx_id", LEVEL, "tx_id", "lvl,ptr", O),
        ("unsupported transaction version", "tx_version_2", LEVEL, "tx_version", "lvl,ptr", O),
        ("version-1 plan relabelled as version 2 (G6-P1)", "tx_relabelled_2", LEVEL, "tx_incomplete", "lvl,ptr", O),
        ("growth without a transaction", "grow_without_tx", LEVEL, "grow_not_allowed", "lvl,ptr", O),
        ("two transactions", "two_tx", LEVEL, "tx_count", "lvl,ptr", O),
        ("tx-file before level-tx", "tx_file_before_level_tx", LEVEL, "tx_order", "lvl,ptr", O),
        ("tx-file after grow (the grow comes first)", "tx_file_after_grow", LEVEL, "grow_not_allowed", "lvl,ptr", O),
        ("pointer table split into two ranges", "ptr_split", LEVEL, "tx_ptr_cover", "ptr,lvl", O),
        ("partial activation (edited words dropped)", "partial_lvl_words_dropped", LEVEL, "tx_result_hash",
         "lvl,ptr", O),
        ("growth bound exceeded", "bound_exceeded", LEVEL, "tx_bounds", "lvl,ptr", O),
        ("duplicate tx-file", "duplicate_tx_file", LEVEL, "tx_duplicate", "lvl,ptr", O),
        ("unknown member role", "unknown_role", LEVEL, "tx_role", "lvl,ptr", O),
        ("transaction names a mod not in the plan", "unknown_tx_mod", LEVEL, "tx_mod", "lvl,ptr", O),
        ("structural + disjoint waypoint-position", "comp", LEVEL, "active", "ptr,lvl",
         (nd / "comp_lvl.bin", nd / "comp_ptr.bin")),
        ("fixed-size only, development runtime enabled", "fixed", LEVEL, "active", "lvl,ptr",
         (nd / "fixed_lvl.bin", "-")),
        ("fixed-size only, development runtime not enabled", "fixed", "-", "active", "lvl,ptr",
         (nd / "fixed_lvl.bin", "-")),
    ]
    prod_cases = [
        ("production runtime: valid transaction plan (.lvl first)", "valid", LEVEL, "unknown_record", "lvl,ptr", O),
        ("production runtime: valid transaction plan (.ptr first)", "valid", LEVEL, "unknown_record", "ptr,lvl", O),
        ("production runtime: growth without a transaction", "grow_without_tx", LEVEL, "grow_not_allowed",
         "lvl,ptr", O),
        ("production runtime: composition plan", "comp", LEVEL, "unknown_record", "lvl,ptr", O),
        ("production runtime: fixed-size only", "fixed", "-", "active", "lvl,ptr", (nd / "fixed_lvl.bin", "-")),
    ]
    out = {}
    for kind, cases in (("dev", dev_cases), ("prod", prod_cases)):
        exe = build_test(kind)
        cf = nd / f"cases_{kind}.tsv"
        cf.write_text("".join("\t".join([name, str(plans[p]), env, want, order, lvl_p, ptr_p, str(e[0]), str(e[1])])
                              + "\n" for name, p, env, want, order, e in cases), encoding="utf-8")
        r = subprocess.run([str(exe), str(cf)], capture_output=True, text=True, timeout=600)
        (nd / f"result_{kind}.txt").write_text(r.stdout + r.stderr)
        print(r.stdout)
        out[kind] = {"exit": r.returncode, "summary": r.stdout.strip().splitlines()[-1] if r.stdout else ""}
    (nd / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
    ok = all(v["exit"] == 0 for v in out.values())
    print(json.dumps(out), "NEGTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --- hidden runs and judgement (G3b's runner and judge, E-469) -----------------------------------------------------

def compiler_plan(work, data, ptr, variant):
    """The plan for a run: written by the mod compiler from an installed typed mod (replaces g3b.write_plan)."""
    res, text, paths = compile_plan(f"run_{work.parent.name}_{work.name}", [(f"g5p1.{variant}", [igm(variant)])])
    if text is None or res["active"] != [f"g5p1.{variant}"]:
        raise SystemExit(f"compiler refused the run's mod: {res['mods']}")
    plan = paths["cache"] / rm.PLAN_NAME
    shutil.copyfile(plan, work / "plan_copy.txt")
    return plan


def bind_g3b():
    g3b.PREFIX = PREFIX
    g3b.write_plan = compiler_plan
    g3b.GATE_ENV = (ENV, LEVEL)
    os.environ.pop("R3HD_G3A_TEST_GROW", None)
    os.environ.pop(ENV, None)


def run(tag, cases):
    bind_g3b()
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied (g5p1_dev_gate.py status)")
    for case in cases:
        print(json.dumps(g3b.run_case(tag, case)), flush=True)
    return 0


def judge(tag):
    bind_g3b()
    src = inspect.getsource(g3b.judge)
    old = 'row["refused"] = "grow_not_allowed" in log'
    if src.count(old) != 1:
        raise SystemExit("G3b judge changed")
    src = src.replace(old, 'row["refused"] = "state=refused reason=level_tx_not_enabled" in log')
    ns = dict(vars(g3b))
    exec(compile(src, "g3b_ab.judge (E-476: D's refusal reason)", "exec"), ns)
    rc = ns["judge"](tag)
    base = WORK / tag
    j = json.loads((base / "judgement.json").read_text())
    p2 = {}
    for case in g3b.CASES:
        run_dir = g3a.RUNS / f"{PREFIX}_{tag}_{case}"
        log = "\n".join(q.read_text(errors="replace") for q in sorted(run_dir.glob("runtime*.log")))
        tx = re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)
        pc = base / case / "plan_copy.txt"
        want = None
        if pc.is_file():
            t = parse_plan(pc.read_text(encoding="utf-8"))["txs"]
            want = [(t[0].split(" ")[2], t[0].split(" ")[3], t[0].split(" ")[4])] if t else None
        if case in g3b.GROWN:
            ok = "M33 mods state=active" in log and tx == want and want[0][1] == f"g5p1.{case}"
        elif case == "nogate":
            ok = ("state=refused reason=level_tx_not_enabled" in log and not tx and "M36 grow" not in log
                  and "M33 mods served" not in log)
        else:
            ok = "M33 mods=off" in log and not tx
        p2[case] = {"ok": bool(ok), "tx_lines": tx, "plan_tx": want}
    off = json.loads((WORK / "offline.json").read_text())
    neg = json.loads((WORK / "negtest" / "summary.json").read_text())
    neg_ok = all(v["exit"] == 0 for v in neg.values())
    n = j["checks"]
    P = {"P1_compiler_equivalence": all(v for k, v in off["checks"].items() if k.startswith("P1_")) and off["pass"],
         "P2_transaction_integrity": neg_ok and all(v["ok"] for v in p2.values()),
         "P3_runtime_growth": n["N1_resource"],
         "P4_relocation_registration": n["N2_relocation"] and n["N3_registration"] and n["N4_arcs"],
         "P5_consumption": n["N5_consumption"],
         "P6_functional_effect": n["N6_neutral"] and n["N7_effect"],
         "P7_rejection": off["pass"] and neg_ok and p2["nogate"]["ok"],
         "P8_safety": n["N8_safety"]}
    out = {"invalid": j["invalid"], "P": P, "pass": not j["invalid"] and all(P.values()), "p2_runtime": p2,
           "negtest": neg, "offline_pass": off["pass"], "g3b_checks": n, "g3b_judge_rc": rc}
    (base / "p_judgement.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("invalid", "P", "pass")}, indent=1))
    return 0 if out["pass"] else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return check()
    if len(sys.argv) > 1 and sys.argv[1] == "negtest":
        return negtest()
    if len(sys.argv) > 2 and sys.argv[1] == "judge":
        return judge(sys.argv[2])
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--cases", default=",".join(g3b.CASES))
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", a.tag):
        ap.error("bad tag")
    return run(a.tag, a.cases.split(","))


if __name__ == "__main__":
    sys.exit(main())

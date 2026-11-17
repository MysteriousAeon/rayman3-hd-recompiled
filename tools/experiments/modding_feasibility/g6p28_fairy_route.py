#!/usr/bin/env python3
"""E-517 (D-284) G6-P28: offline acceptance of the level-patch-v1 `route` component (graph C waypoints, intro_20).

    g6p28_fairy_route.py check   O1-O5: source compatibility, reference equivalence, authoring variation, integrity
                                 and refusal, regression against the HEAD-before-G6-P28 compiler and production isolation
Outputs: private/work/e517/ (numbers only). No game process, build or gate change.
"""
import copy
import importlib.util
import json
import math
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402
import g6p24_authoring_ux as g24  # noqa: E402

g22, g3, p1 = g24.g22, g24.g3, g24.p1
ROOT, GAME, LEVEL, EX = g24.ROOT, g24.GAME, g24.LEVEL, g24.EX
WORK = ROOT / "private" / "work" / "e517"
ROUTE = EX / "g6p28_fairy_route.json"
BASIN = EX / "g6p25_west_basin_fairy.json"
BASIN_TX = "9083786df631a5a3"            # G6-P25 / G6-P27 (run m1 observed these guest images)
SO, BLOCK, GRAPH_C = 0x3358A0, 0xA4C, 0x336050
EXISTING = ["g6p20_reference.json", "graph_b.json", "g6p22_reference_patch.json", "g6p22_west_dip_fairy.json",
            "g6p25_west_basin_fairy.json"]


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def doc(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def walk_graph_c(lvl):
    """Independent decode (no compiler code): graph {first, last, count}; node {next, prev, graph, waypoint, ...};
    relocated words hold file offset - 4. [(node, waypoint)] in list order."""
    t = lambda o: u32(lvl, o) + 4   # noqa: E731
    first, last, count = t(GRAPH_C), t(GRAPH_C + 4), u32(lvl, GRAPH_C + 8)
    out, n = [], first
    for _ in range(count):
        out.append((n, t(n + 0xC)))
        if t(n + 8) != GRAPH_C:
            return None
        n = t(n) if n != last else None
    return out if out and out[-1][0] == last else None


def route_bytes(lvl, route_doc):
    """{waypoint offset: 12 new bytes} computed independently (float32 original + offset, big-endian)."""
    wps = walk_graph_c(lvl)
    out = {}
    for m in route_doc["waypoints"]:
        w = wps[m["node"]][1]
        old = struct.unpack_from(">3f", lvl, w)
        out[w] = struct.pack(">3f", *(a + b for a, b in zip(old, m["offset"])))
    return out


def tx_rederived(m, mid):
    """G6-P20's transaction-line re-derivation (member results = rebuilt images; id = sha256 of the canonical lines)."""
    img = p1.images(m)
    lines, ok = [], len(m["txs"]) == 1 and m["txs"][0].split(" ")[1:4] == ["2", LEVEL, mid]
    for f in m["files"]:
        if len(f["tx"]) != 1:
            return False
        role, orig, guest, result = f["tx"][0].split(" ")
        im = img[Path(f["path"]).name]
        ok &= orig == rm.sha256_bytes(Path(f["path"]).read_bytes()) and int(guest) == len(im) \
            and result == rm.sha256_bytes(im)
        lines.append((role, Path(f["path"]).name.lower(), f["size"], orig, int(guest), result))
    canon = f"level-tx 2 {LEVEL} {mid}\n" + "".join(f"tx-file {r} {n} {s} {o} {g} {x}\n" for r, n, s, o, g, x in
                                                    sorted(lines))
    import hashlib
    return ok and len(lines) == 3 and m["txs"][0].split(" ")[4] == hashlib.sha256(canon.encode("ascii")).hexdigest()[:16]


def walk(tag, lp):
    """CLI compile -> import -> plan in private folders; (exit codes, plan text)."""
    w = WORK / tag
    if w.exists():
        shutil.rmtree(w)
    priv = ("--mods-root", str(w / "mods"), "--cache", str(w / "cache"))
    rc1, r1, _ = g24.cli(["level-patch", str(lp), "--out", str(w / "mod")], extra=("--json",))
    rc2, _, _ = g24.cli(["import", str(w / "mod"), "--enable"], extra=("--json", *priv))
    rc3, _, _ = g24.cli(["plan"], extra=("--json", *priv))
    text = (w / "cache" / rm.PLAN_NAME).read_text(encoding="utf-8") if rc3 == 0 else ""
    return (rc1, rc2, rc3), r1, text


def sig(ranges, tx):
    return ([(Path(p).name, o, rm.sha256_bytes(d), w) for p, o, d, w in ranges],
            {k: rm.sha256_bytes(v) for k, v in tx["images"].items()})


def check():
    WORK.mkdir(parents=True, exist_ok=True)
    O, det = {}, {}
    P = {"game": GAME}
    lvl, ptr, tl = g3.files()
    R = doc(ROUTE)
    route_c = next(c for c in R["components"] if c["type"] == "route")

    # O1 source compatibility: exact target, graph C ownership, constructor assumptions
    o1 = {}
    o1["level files = the pinned originals"] = [rm.sha256_bytes(x) for x in (lvl, ptr, tl)] == [
        rm.STRUCT_ALLOW[LEVEL]["lvl"][1], rm.STRUCT_ALLOW[LEVEL]["ptr"][1], rm.FAIRY_ALLOW[LEVEL]["transit"][1]]
    wps = walk_graph_c(lvl)
    ix = rm.read_script_index(GAME, LEVEL)
    e = ix["graphs"].get((rm.FAIRY20, 2, 2))
    o1["independent walk: graph C has 6 nodes = the compiler's graph of FairyLight instance 2 variable 2"] = (
        wps is not None and len(wps) == 6 and e is not None and e["graph"] == GRAPH_C
        and [w for _, w in wps] == [w for _, w in e["nodes"]] and not e["safe"] and not e["wsafe"])
    gl, gh = SO + 0x7B0, SO + 0x9E4
    o1["graph C, its nodes and waypoints lie in the source block's graph region"] = wps is not None and all(
        gl <= x and x + 0x14 <= gh for n, w in wps for x in (n, w)) and gl <= GRAPH_C < gh
    n = u32(ptr, 0)
    slots = {struct.unpack_from(">iI", ptr, 4 + 8 * i)[1] + 4: struct.unpack_from(">iI", ptr, 4 + 8 * i)[0]
             for i in range(n)}
    me = rm.script_level_files(GAME, LEVEL)[2]
    objs = [(GRAPH_C, 0xC)] + [(x, 0x1C) for x, _ in wps] + [(w, 0x14) for _, w in wps]
    refs = {s for s, f in slots.items() if f == me and s + 4 <= len(lvl)
            and any(a <= u32(lvl, s) + 4 < a + ln for a, ln in objs)}
    o1["every relocated reference to graph C / nodes / waypoints comes from the owner's block"] = bool(refs) and all(
        SO <= s < SO + BLOCK for s in refs)
    o1["no relocated word inside a waypoint"] = not any(w <= s < w + 0x14 for s in slots for _, w in wps)
    cl, cp, ct, lay = g3.construct(lvl, ptr, tl, "a")
    o1["independent FairyLight constructor leaves every waypoint original"] = all(
        cl[w:w + 0x14] == lvl[w:w + 0x14] for _, w in wps)
    det["O1"] = {"waypoints": [hex(w) for _, w in wps], "references": len(refs)}
    O["O1"] = o1

    # O2 reference equivalence
    o2 = {}
    with p1.dev_env(LEVEL):
        cb, rb, tb = rm.compile_level_patch(doc(BASIN), P)
        nr = copy.deepcopy(R)
        nr["components"] = [c for c in nr["components"] if c["type"] != "route"]
        nr["id"], nr["description"] = doc(BASIN)["id"], doc(BASIN)["description"]
        cn, rn, tn = rm.compile_level_patch(nr, P)
        cr, rr, tr = rm.compile_level_patch(R, P)
    ts_b = rm.transaction_summary(cb["id"], tb)
    o2["west-basin compiles to tx 9083786df631a5a3, the images G6-P27 run m1 served"] = (
        ts_b["id"] == BASIN_TX and tuple(rm.sha256_bytes(tb["images"][k]) for k in ("lvl", "ptr", "transit"))
        in [r["images"] for r in rm.LEVEL_PATCH_RUNTIME])
    o2["the route example without its route = west-basin (canonical form, ranges, images)"] = (
        cn == cb and sig(rn, tn) == sig(rb, tb))
    ind = route_bytes(lvl, route_c)
    rte = [(o, d) for p, o, d, w in rr if ".route." in w]
    o2["route ranges = the independently computed waypoint bytes"] = sorted(rte) == sorted(ind.items())
    wo = [{"type": "waypoint-position", "level": LEVEL, "model": rm.FAIRY20, "instance": 2, "variable": 2,
           "node": m["node"], "waypoint_sha256": rm.sha256_bytes(lvl[wps[m["node"]][1]:wps[m["node"]][1] + 0x14]),
           "position": list(struct.unpack(">3f", ind[wps[m["node"]][1]]))} for m in route_c["waypoints"]]
    for o in wo:
        rm.parse_waypoint_position(o, "o2")
    o2["= a standalone D-231 waypoint-position mod of the same positions"] = sorted(
        (o, d) for _, o, d, _ in rm.compile_waypoint_positions(wo, P)) == sorted(ind.items())
    O["O2"] = o2

    # O3 real authoring variation (CLI walk + an in-process second variant)
    o3 = {}
    rcs_b, _, text_b = walk("basin", BASIN)
    rcs_r, cli_r, text_r = walk("route", ROUTE)
    det["walk"] = {"basin": rcs_b, "route": rcs_r}
    mb, mr = (p1.parse_plan(t) if t else None for t in (text_b, text_r))
    with p1.dev_env(LEVEL):
        tc = rm.parse_terrain_patch(next(c for c in doc(BASIN)["components"] if c["type"] == "terrain")["patch"], "b")
        fc = g22.combined_check(text_b, "a", doc(BASIN)["id"], {k: v for k, v in tc.items() if k != "description"}) \
            if text_b else {"ok": False}
    o3["west-basin plan passes the independent combined checker (G6-P22 / G6-P20)"] = fc.get("ok") is True
    o3["compile / import / plan of the route example: exit 0, one level-tx, transaction lines re-derived"] = (
        rcs_r == (0, 0, 0) and mr is not None and tx_rederived(mr, R["id"]))
    ib, ir = (p1.images(m) if m else {} for m in (mb, mr))
    L_b, L_r = ib.get(f"{LEVEL}.lvl"), ir.get(f"{LEVEL}.lvl")
    diff = [i for i in range(len(L_b)) if L_b[i] != L_r[i]] if L_b and L_r and len(L_b) == len(L_r) else None
    allowed = {i for w in ind for i in range(w, w + 12)}
    o3["route image = verified west-basin image except inside the moved waypoints; ptr / transit identical"] = (
        diff is not None and set(diff) <= allowed and all(L_r[w:w + 12] == d for w, d in ind.items())
        and ib.get(f"{LEVEL}.ptr") == ir.get(f"{LEVEL}.ptr") and ib.get("transit.lvl") == ir.get("transit.lvl"))
    restored = bytearray(L_r or b"")
    for w in ind:
        restored[w:w + 12] = lvl[w:w + 12]
    o3["restoring the 3 original waypoints gives the west-basin image byte for byte"] = bool(L_r) and \
        bytes(restored) == L_b
    o3["a distinct transaction (id, lvl result), same growth +2892 / +408 / 0"] = (
        cli_r.get("transaction", {}).get("id") not in (None, BASIN_TX)
        and cli_r.get("growth") == {"lvl": 2892, "ptr": 408, "transit": 0} and cli_r.get("range_count") == 58
        and cli_r.get("route_ranges") == 3 and cli_r.get("terrain_ranges") == 42 and cli_r.get("fairylight_ranges") == 13)
    pvr = cli_r.get("preview", {}).get("route", {})
    o3["preview lists each move's new position = the independent bytes, runtime UNTESTED"] = (
        [m["node"] for m in pvr.get("moves", [])] == [0, 3, 5]
        and all([round(v, 4) for v in struct.unpack(">3f", ind[wps[m["node"]][1]])] == m["new"]
                for m in pvr.get("moves", []))
        and cli_r.get("preview", {}).get("evidence", {}).get("runtime", "").startswith("UNTESTED"))
    v2 = copy.deepcopy(doc(EX / "g6p20_reference.json"))
    v2["id"] = "g6p28.full-loop-b"
    v2["components"] = [{"type": "terrain", "preset": "start-two-step-v1"}, {"type": "fairylight", "follow_graph_of": 1},
                        {"type": "route", "waypoints": [{"node": k, "offset": off} for k, off in enumerate(
                            ([6.0, 0, 0], [0, -6.0, 0], [0, 0, 6.0], [-2.5, 2.5, 1.0], [3, -4, 0], [0.5, 0.5, -5]))]}]
    v2b = dict(v2, components=v2["components"][:2])
    with p1.dev_env(LEVEL):
        c2, r2, t2 = rm.compile_level_patch(v2, P)
        _, r2b, t2b = rm.compile_level_patch(v2b, P)
    i2 = route_bytes(lvl, v2["components"][2])
    a2, b2 = t2["images"]["lvl"], t2b["images"]["lvl"]
    o3["second variant (preset terrain, graph B, all 6 waypoints, three at exactly 6 units): only those 72 bytes "
       "differ from its no-route twin, each = the independent bytes"] = (
        len(a2) == len(b2) and {i for i in range(len(a2)) if a2[i] != b2[i]} <= {i for w in i2 for i in range(w, w + 12)}
        and all(a2[w:w + 12] == d for w, d in i2.items()) and len(i2) == 6
        and t2["images"]["ptr"] == t2b["images"]["ptr"] and len(r2) == len(r2b) + 6
        and rm.transaction_summary(c2["id"], t2)["id"] != rm.transaction_summary(c2["id"], t2b)["id"])
    det["O3"] = {"route_tx": cli_r.get("transaction", {}).get("id"), "changed_bytes": len(diff or []),
                 "moves": pvr.get("moves")}
    O["O3"] = o3

    # O4 integrity, determinism and refusal
    o4 = {}
    if mr:
        Pr = ir.get(f"{LEVEL}.ptr")
        k = u32(Pr, 0)
        sl = [struct.unpack_from(">iI", Pr, 4 + 8 * i)[1] + 4 for i in range(k)]
        o4["pointer slots unique; none inside a route waypoint; route below the original end"] = (
            len(sl) == len(set(sl)) and not any(q in allowed for s in sl for q in range(s, s + 4))
            and max(allowed) < len(lvl))
    other = [(o, o + len(d)) for _, o, d, w in rr if ".route." not in w]
    o4["route ranges disjoint from every FairyLight / terrain range"] = not any(
        a < w + 12 and w < b for a, b in other for w in ind)
    with p1.dev_env(LEVEL):
        again = rm.compile_level_patch(R, P)
        shuffled = copy.deepcopy(R)
        shuffled["components"] = shuffled["components"][::-1]
        next(c for c in shuffled["components"] if c["type"] == "route")["waypoints"].reverse()
        sh = rm.compile_level_patch(shuffled, P)
    o4["deterministic; component and move order do not change identity, ranges or images"] = (
        sig(again[1], again[2]) == sig(rr, tr) and sig(sh[1], sh[2]) == sig(rr, tr)
        and rm.level_patch_identity(sh[0]) == rm.level_patch_identity(cr))

    def bad(mut):
        d = copy.deepcopy(R)
        mut(next(c for c in d["components"] if c["type"] == "route"), d)
        return d
    cases = {
        "node 6 (UNSUPPORTED)": ("UNSUPPORTED", bad(lambda c, d: c["waypoints"].__setitem__(0, {"node": 6, "offset": [1, 0, 0]}))),
        "move 6.001 units (UNSUPPORTED)": ("UNSUPPORTED", bad(lambda c, d: c["waypoints"][0].update(offset=[6.001, 0, 0]))),
        "zero offset": ("BAD_MANIFEST", bad(lambda c, d: c["waypoints"][0].update(offset=[0, 0, 0]))),
        "node moved twice": ("BAD_MANIFEST", bad(lambda c, d: c["waypoints"].append({"node": 3, "offset": [1, 0, 0]}))),
        "seven moves": ("BAD_MANIFEST", bad(lambda c, d: c.update(waypoints=[{"node": i % 6, "offset": [1, 0, 0]}
                                                                             for i in range(7)]))),
        "absolute position key": ("BAD_MANIFEST", bad(lambda c, d: c["waypoints"][0].update(position=[0, 0, 0]))),
        "graph key": ("BAD_MANIFEST", bad(lambda c, d: c.update(graph=0x336050))),
        "second route": ("BAD_MANIFEST", bad(lambda c, d: d["components"].append(copy.deepcopy(c)))),
        "route without terrain": ("BAD_MANIFEST", bad(lambda c, d: d.update(components=[x for x in d["components"]
                                                                                        if x["type"] != "terrain"]))),
    }
    w = WORK / "refusals"
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    neg = {}
    for i, (name, (code, d)) in enumerate(cases.items()):
        f = g24.write(w / f"bad_{i}.json", d)
        rc, r, _ = g24.cli(["level-patch", str(f), "--out", str(w / f"out_{i}")], extra=("--json",))
        neg[name] = rc == 2 and r.get("code") == code and not (w / f"out_{i}").exists()
    rc, r, _ = g24.cli(["level-patch", str(ROUTE), "--out", str(w / "out_gate")], gate=None, extra=("--json",))
    neg["gate off (UNSUPPORTED)"] = rc == 2 and r.get("code") == "UNSUPPORTED" and not (w / "out_gate").exists()
    o4["refusals: exit 2, the expected code, nothing written"] = all(neg.values())
    det["O4_refusals"] = neg
    # a second mod moving the same waypoint conflicts with the transaction (refused whole, no partial shadowing)
    m0 = route_c["waypoints"][0]
    wp0 = wps[m0["node"]][1]
    clash = {"type": "waypoint-position", "level": LEVEL, "model": rm.FAIRY20, "instance": 2, "variable": 2,
             "node": m0["node"], "waypoint_sha256": rm.sha256_bytes(lvl[wp0:wp0 + 0x14]), "position": [0.0, 0.0, 0.0]}
    res, text_c, _ = g3.compile_plan("clash", [(R["id"], [{"type": "level-patch", "patch": R}]),
                                               ("t.clash", [clash])])
    rep = {x["id"]: x for x in res.get("mods", [])}
    det["O4_clash"] = {k: (v.get("state"), v.get("code")) for k, v in rep.items()}
    patch_on = rep.get(R["id"], {}).get("state") == "active"
    o4["a second mod moving a route waypoint: STRUCTURAL_CONFLICT, no partial shadowing (one side refused whole)"] = (
        sum(v.get("state") == "active" for v in rep.values()) == 1
        and any(v.get("code") == "STRUCTURAL_CONFLICT" for v in rep.values())
        and (len(p1.parse_plan(text_c)["txs"]) if text_c else 0) == (1 if patch_on else 0))
    O["O4"] = o4

    # O5 regression (HEAD-before-G6-P28 compiler) and production isolation
    o5 = {}
    old_dir = WORK / "old_tools"
    old_dir.mkdir(parents=True, exist_ok=True)
    src = subprocess.run(["git", "show", "43f1840:tools/r3hd_mods.py"], cwd=ROOT, capture_output=True).stdout
    (old_dir / "r3hd_mods.py").write_bytes(src)
    spec = importlib.util.spec_from_file_location("r3hd_mods_g6p27", old_dir / "r3hd_mods.py")
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    same, cli_same = {}, {}
    for name in EXISTING:
        with p1.dev_env(LEVEL):
            a = old.compile_level_patch(doc(EX / name), P)
            b = rm.compile_level_patch(doc(EX / name), P)
        same[name] = a[0] == b[0] and sig(a[1], a[2]) == sig(b[1], b[2])
        outs = []
        for tool in (old_dir / "r3hd_mods.py", ROOT / "tools" / "r3hd_mods.py"):
            env = {k: v for k, v in __import__("os").environ.items() if k != rm.STRUCT_ENV}
            env[rm.STRUCT_ENV] = LEVEL
            outs.append(subprocess.run([sys.executable, "-I", str(tool), "level-patch", str(EX / name), "--check",
                                        "--game-dir", str(GAME)], cwd=ROOT, capture_output=True, text=True,
                                       env=env).stdout)
        cli_same[name] = outs[0] == outs[1] and "VALID" in outs[0]
    o5["existing declarations: canonical form, ranges and images identical to the HEAD compiler"] = all(same.values())
    o5["existing declarations: --check text report identical to the HEAD compiler"] = all(cli_same.values())
    det["O5_same"], det["O5_cli_same"] = same, cli_same
    st = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "r3hd_mods.py"), "selftest"], cwd=ROOT,
                        capture_output=True, text=True).stdout.strip().splitlines()
    det["selftest"] = st[-1] if st else ""
    o5["selftest PASS"] = bool(st) and st[-1].startswith("R3HD_MODS_SELFTEST PASS")
    gate = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()
    o5["development gate production; binaries = the G6-P27 production identity"] = gate == "production" and {
        n_: rm.sha256_bytes((g24.BIN / n_).read_bytes()) for n_ in g24.PROD} == g24.PROD
    O["O5"] = o5

    res = {"pass": all(all(v.values()) for v in O.values()), "checks": O, "details": det}
    (WORK / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"pass": res["pass"], "checks": O}, indent=1))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        sys.exit(check())
    raise SystemExit(__doc__)

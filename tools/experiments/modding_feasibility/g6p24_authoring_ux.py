#!/usr/bin/env python3
"""E-513 (D-280) G6-P24: practical level-patch authoring UX -- offline acceptance O1-O5 of `level-patch --check`.

    g6p24_authoring_ux.py check     O1-O5 through the real CLI (subprocesses of tools/r3hd_mods.py) plus in-process
                                    comparisons with the independent G6-P22 geometry model / combined checker
Outputs: private/work/e513/ (numbers only, plus the walkthrough's private mod / mods / cache folders).

O1 preview / compiler parity: for valid and invalid declarations `--check` succeeds iff `--out` succeeds, with the same
   transaction, ranges, growth and geometry summary, and writes nothing (no out folder; mods / cache / game files and
   the git worktree unchanged).
O2 predictions: the preview's standing height equals the independent geometry model's (g6p22 geometry on the compiled
   final image) for the runtime-verified west-dip, the G6-P19 / G6-P20 preset and an offline-only 2-group graph-B
   patch; the measured runtime value is never used; probe models that do not apply are reported unavailable.
O3 refusals: representative author mistakes -> exit 2, stable code, actionable detail, `written` false, no output.
O4 walkthrough: copy an example, --check, change one value, --check, --out, import, plan (private folders), inspect the
   plan's level-tx and run the independent combined checker on it; no Python edited.
O5 compatibility / safety: G6-P21 / G6-P22 fixed declarations unchanged (tx ids, results), generic mixed mods and
   production refused (selftest), gate off refused, dev gate status production, binaries unchanged.
"""
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402
import g6p22_intro20_terrain as g22  # noqa: E402

g20, g3, p1, g19 = g22.g20, g22.g3, g22.p1, g22.g19
ROOT, GAME, LEVEL = g22.ROOT, g22.GAME, g22.LEVEL
WORK = ROOT / "private" / "work" / "e513"
EX = g22.EX
WEST = EX / "g6p22_west_dip_fairy.json"
BIN = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
# production identity history: 6635d232... / 784f7b72... (G6-P30 production build with the D-286 level-transaction
# policy, E-519, 2026-11-17); before: 2506d0a7... / bad7a072... (G6-P27 restore), e1c6df2b... / b47316a8... (G6-P23).
# G6-P39 (D-295): the live rows compare with the CURRENT validated identity, config/release/production_identity.json
# (G6-P36 relink, D-292); the history stays in that record and with its own runtime evidence.
CURRENT = json.loads((ROOT / "config" / "release" / "production_identity.json").read_text(
    encoding="utf-8"))["current"]["binaries"]
PROD = {n: CURRENT[n] for n in ("r3hd.exe", "rexruntime.dll")}
KNOWN = {"g6p22_west_dip_fairy.json": "3e74d122bdb042e3", "g6p22_reference_patch.json": "1b1f404eaf81a240",
         "g6p20_reference.json": "1b1f404eaf81a240", "graph_b.json": "3cdb5be5ebafc590"}


def cli(args, gate=LEVEL, extra=()):
    env = {k: v for k, v in __import__("os").environ.items() if k != rm.STRUCT_ENV}
    if gate:
        env[rm.STRUCT_ENV] = gate
    r = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "r3hd_mods.py"), *args, "--game-dir", str(GAME),
                        *extra], cwd=ROOT, capture_output=True, text=True, env=env)
    try:
        out = json.loads(r.stdout) if "--json" in extra else r.stdout
    except ValueError:
        out = {"raw": r.stdout[-400:], "err": r.stderr[-400:]}
    return r.returncode, out, r.stderr


def snapshot():
    """What a non-writing command must leave unchanged: mods / cache trees, the game's intro_20 files, git status."""
    s = {}
    for d in (ROOT / "private" / "play" / "mods", ROOT / "private" / "play" / "cache" / "mods"):
        s[str(d)] = sorted((str(p.relative_to(d)), p.stat().st_size, p.stat().st_mtime_ns)
                           for p in d.rglob("*")) if d.is_dir() else None
    lvl_p, ptr_p, _ = rm.script_level_files(GAME, LEVEL)
    tl = g3.files()[2]
    s["game"] = [rm.sha256_bytes(lvl_p.read_bytes()), rm.sha256_bytes(ptr_p.read_bytes()), rm.sha256_bytes(tl)]
    s["git"] = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    return s


def write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return path


def summary(r):
    """The fields a preview and a compile must agree on."""
    pv = r["preview"]
    return {"tx": r["transaction"], "growth": r["growth"], "ranges": [r["range_count"], r["terrain_ranges"],
            r["fairylight_ranges"]], "identity": r["patch"]["identity_sha256"],
            "geometry": {k: pv["terrain"][k] for k in ("collision_triangles", "visual_vertices", "visual_triangles",
                                                        "lowest_ground_normal_z", "ranges", "bytes")},
            "standing": pv["standing"], "evidence": pv["evidence"]}


def decls(tmp):
    """Valid declarations: the four examples + the offline-only 2-group graph-B patch."""
    base = json.loads(WEST.read_text(encoding="utf-8"))
    two = copy.deepcopy(base)
    two["id"] = "g6p24.two-group-b"
    two["description"] = "G6-P24 offline-only: two groups, graph B"
    two["components"][0]["follow_graph_of"] = 1
    two["components"][1]["patch"]["name"] = "corner-and-west"
    two["components"][1]["patch"]["groups"] = [{"name": "corner", "vertices": [0], "delta_z": -0.2},
                                               {"name": "west", "vertices": [4, 2], "delta_z": -0.05}]
    return [EX / n for n in KNOWN] + [write(tmp / "two_group_b.json", two)]


def negatives(tmp):
    base = json.loads(WEST.read_text(encoding="utf-8"))
    G = lambda d: d["components"][1]["patch"]["groups"]   # noqa: E731
    cases = {   # name: (mutation, code, detail substring)
        "vertex": (lambda d: G(d)[1].update(vertices=[7]), "UNSUPPORTED", "allowed: 0, 2, 4"),
        "raise": (lambda d: G(d)[1].update(delta_z=0.1), "UNSUPPORTED", "raising is not supported"),
        "too-deep": (lambda d: G(d)[1].update(delta_z=-0.5), "UNSUPPORTED", "outside -0.30..-0.05"),
        "duplicate": (lambda d: G(d)[1].update(vertices=[0]), "BAD_MANIFEST", "already in group 'spawn-corner'"),
        "source-hash": (lambda d: d.update(ptr_sha256="0" * 64), "UNSUPPORTED", "intro_20.ptr"),
        "missing-terrain": (lambda d: d["components"].pop(1), "BAD_MANIFEST", "missing component(s) ['terrain']"),
        "graph": (lambda d: d["components"][0].update(follow_graph_of=2), "UNSUPPORTED", "0 = graph A, 1 = graph B"),
        "unknown-key": (lambda d: d.update(colour="red"), "BAD_MANIFEST", "unknown: ['colour']"),
    }
    out = {}
    for n, (f, code, sub) in cases.items():
        d = copy.deepcopy(base)
        f(d)
        out[n] = (write(tmp / f"neg_{n}.json", d), code, sub)
    bad_json = tmp / "neg_not-json.json"
    bad_json.write_text(WEST.read_text(encoding="utf-8")[:-10], encoding="utf-8")
    out["not-json"] = (bad_json, "BAD_MANIFEST", "not JSON")
    return out


def check():
    if WORK.exists():
        shutil.rmtree(WORK)
    tmp = WORK / "inputs"
    tmp.mkdir(parents=True)
    O, det = {}, {}
    before = snapshot()
    gate0 = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)

    # O1 parity on valid declarations
    o1, par = {}, {}
    for f in decls(tmp):
        rc_c, c, _ = cli(["level-patch", str(f), "--check"], extra=("--json",))
        out = WORK / "o1_out" / f.stem
        rc_o, o, _ = cli(["level-patch", str(f), "--out", str(out)], extra=("--json",))
        same = rc_c == rc_o == 0 and summary(c) == summary(o)
        par[f.name] = {"check_exit": rc_c, "out_exit": rc_o, "tx": c.get("transaction", {}).get("id"),
                       "ranges": c.get("range_count"), "growth": c.get("growth"), "runtime_observed":
                       c.get("preview", {}).get("runtime_observed"), "predicted_z":
                       c.get("preview", {}).get("standing", {}).get("predicted_settled_z")}
        o1[f"{f.name}: --check and --out exit 0 with equal tx / ranges / growth / geometry / prediction"] = same
        o1[f"{f.name}: --out wrote exactly mod.json"] = sorted(p.name for p in out.iterdir()) == ["mod.json"]
        if f.name in KNOWN:
            o1[f"{f.name}: tx {KNOWN[f.name]} (G6-P20 / G6-P21 / G6-P22 identity unchanged)"] = (
                c["transaction"]["id"] == KNOWN[f.name])
    o1["only the G6-P23 / G6-P20 images report runtime OBSERVED; graph B and the new patch UNTESTED"] = (
        [n for n, v in par.items() if v["runtime_observed"]]
        == ["g6p22_west_dip_fairy.json", "g6p22_reference_patch.json", "g6p20_reference.json"])
    det["o1"] = par
    # O1 parity on invalid declarations (check refuses iff compile refuses, same code and detail, nothing written)
    neg = negatives(tmp)
    o3, nd = {}, {}
    for n, (f, code, sub) in neg.items():
        out = WORK / "o3_out" / n
        rc_c, c, _ = cli(["level-patch", str(f), "--check"], extra=("--json",))
        rc_o, o, _ = cli(["level-patch", str(f), "--out", str(out)], extra=("--json",))
        rc_t, t, _ = cli(["level-patch", str(f), "--check"])
        nd[n] = {"code": c.get("code"), "detail": c.get("detail")}
        o1[f"invalid {n}: --check refuses iff --out refuses (same code / detail)"] = (
            rc_c == rc_o == 2 and (c.get("code"), c.get("detail")) == (o.get("code"), o.get("detail")))
        o3[f"{n}: exit 2, {code}, detail names '{sub}', written false, no output folder, text says nothing written"] = (
            rc_c == 2 and c.get("code") == code and sub in c.get("detail", "") and c.get("written") is False
            and not out.exists() and rc_t == 2 and "Nothing was written." in t and "Traceback" not in t)
    det["o3"] = nd
    # gate off / gate naming another level / --check with --out
    for name, gate, args, code, sub in (
            ("gate off", None, ["--check"], "UNSUPPORTED", f"{rm.STRUCT_ENV}=intro_20"),
            ("gate names intro_15", "intro_15", ["--check"], "UNSUPPORTED", f"{rm.STRUCT_ENV}=intro_20"),
            ("--check with --out", LEVEL, ["--check", "--out", str(WORK / "o3_out" / "both")], "USAGE", "--check")):
        rc, r, _ = cli(["level-patch", str(WEST), *args], gate=gate, extra=("--json",))
        o3[f"{name}: exit 2, {code}, names '{sub}', nothing written"] = (
            rc == 2 and r.get("code") == code and sub in r.get("detail", "") and r.get("written") is False
            and not (WORK / "o3_out" / "both").exists())
    after = snapshot()
    o1["--check / refusals left mods, cache, game files and the git worktree unchanged"] = before == after
    O["O1"], O["O3"] = o1, o3

    # O2 predictions against the independent geometry model on the compiled final image
    o2, pd = {}, {}
    lvl, ptr = g19.files()
    with p1.dev_env(LEVEL):
        for f in decls(tmp):
            d = json.loads(f.read_text(encoding="utf-8"))
            canon, ranges, tx = rm.compile_level_patch(d, {"game": GAME})
            t = canon["components"][0]
            spec = rm.terrain_spec(t["patch"]) if "patch" in t else rm.COLLISION_ALLOW[LEVEL]["presets"][t["preset"]]
            moved = {v: g["dz"] for g in spec["groups"] for v in g["vertices"]}
            # independent model: g6p22 geometry on the fairy-only constructor image vs the compiled final image
            cl = g3.construct(*g3.files(), "a" if t and canon["components"][1]["follow_graph_of"] == 0 else "b")[0]
            ok, facts, _, z_ind = g22.geometry(cl[:len(lvl)], tx["images"]["lvl"][:len(lvl)], moved)
            pv = rm.level_patch_preview(canon, ranges, tx, {"game": GAME})
            z = pv["standing"].get("predicted_settled_z")
            pd[f.name] = {"preview": z, "independent": z_ind, "independent_ok": ok,
                          "ring_normal_z_min": facts.get("ring_normal_z_min"),
                          "preview_lowest_normal_z": pv["terrain"]["lowest_ground_normal_z"]}
            o2[f"{f.name}: preview z {z} = independent model z {z_ind}; independent geometry ok"] = (
                ok and z is not None and z == z_ind)
    o2["west-dip prediction -25.1408 (G6-P22 prospective value; measured -25.1415 not used)"] = (
        pd[WEST.name]["preview"] == -25.1408)
    o2["start-two-step-v1 prediction -25.2668 (G6-P19 / G6-P20 expected value)"] = (
        pd["g6p20_reference.json"]["preview"] == -25.2668)
    # unavailable cases: probe off the mesh, probe below its surface (model gap), a level without a probe
    saved = rm.LEVEL_PATCH_PROBE[LEVEL]
    with p1.dev_env(LEVEL):
        canon, ranges, tx = rm.compile_level_patch(json.loads(WEST.read_text(encoding="utf-8")), {"game": GAME})
    edits = [(o, d_) for p_, o, d_, w in ranges if ".terrain." in w and Path(p_).name.lower() == f"{LEVEL}.lvl"]
    un = {}
    try:
        x, y, z0 = saved["xyz"]
        for name, xyz in (("off the mesh", (x + 1e5, y + 1e5, z0)), ("probe below its surface", (x, y, z0 - 0.5))):
            rm.LEVEL_PATCH_PROBE[LEVEL] = dict(saved, xyz=xyz)
            un[name] = rm.standing_prediction(LEVEL, lvl, ptr, edits)
            pv = rm.level_patch_preview(canon, ranges, tx, {"game": GAME})
            un[name + " (report)"] = {"available": pv["standing"]["available"],
                                      "evidence": pv["evidence"]["standing_height"]}
    finally:
        rm.LEVEL_PATCH_PROBE[LEVEL] = saved
    un["no probe recorded (intro_15)"] = rm.standing_prediction("intro_15", b"", b"", [])
    o2["unavailable with a reason (no number) when the probe is off the mesh, below its surface, or not recorded"] = (
        all(v["available"] is False and v.get("reason") and "predicted_settled_z" not in v
            for k, v in un.items() if "report" not in k)
        and all(v["available"] is False and v["evidence"].startswith("UNAVAILABLE:")
                for k, v in un.items() if "report" in k))
    det["o2"], det["o2_unavailable"] = pd, un
    O["O2"] = o2

    # O4 walkthrough through the CLI only
    o4, wd = {}, {}
    w = WORK / "walkthrough"
    mine = w / "my_patch.json"
    mine.parent.mkdir(parents=True)
    shutil.copyfile(WEST, mine)
    rc1, t1, _ = cli(["level-patch", str(mine), "--check"])
    o4["1 copy + --check: VALID, nothing written, runtime OBSERVED (unchanged copy)"] = (
        rc1 == 0 and "VALID (nothing written)" in t1 and "OBSERVED for these exact guest images" in t1)
    d = json.loads(mine.read_text(encoding="utf-8"))
    d["id"] = "g6p24.my-west-dip"
    grp = {g["name"]: g for g in d["components"][1]["patch"]["groups"]}
    grp["west-a"]["delta_z"] = -0.15   # vertex 2: not on the probe triangle (1/11 = vertices 0 9 10)
    mine.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    rc2a, r2a, _ = cli(["level-patch", str(mine), "--check"], extra=("--json",))
    st2a = r2a.get("preview", {}).get("standing", {})
    o4["2a west-a (vertex 2) -> -0.15, --check: VALID, new tx, prediction unchanged -25.1408, only vertex 0 sets it"] = (
        rc2a == 0 and r2a["transaction"]["id"] != KNOWN[WEST.name] and st2a.get("predicted_settled_z") == -25.1408
        and st2a.get("moved_vertices_on_probe_triangle") == [0])
    grp["spawn-corner"]["delta_z"] = -0.2   # vertex 0: on the probe triangle
    mine.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    rc2, r2, _ = cli(["level-patch", str(mine), "--check"], extra=("--json",))
    rc2t, t2, _ = cli(["level-patch", str(mine), "--check"])
    st2 = r2.get("preview", {}).get("standing", {})
    o4["2b spawn-corner (vertex 0) -> -0.20, --check: VALID, lower prediction, runtime UNTESTED"] = (
        rc2 == rc2t == 0 and st2.get("available") and st2.get("predicted_settled_z") < -25.1408
        and r2["preview"]["evidence"]["runtime"].startswith("UNTESTED") and "UNTESTED" in t2)
    wd["step_2a_z"] = st2a.get("predicted_settled_z")
    mod = w / "mod"
    rc3, r3, _ = cli(["level-patch", str(mine), "--out", str(mod)], extra=("--json",))
    o4["3 --out: mod.json only, same tx as the preview"] = (
        rc3 == 0 and sorted(p.name for p in mod.iterdir()) == ["mod.json"]
        and r3["transaction"]["id"] == r2["transaction"]["id"])
    priv = ("--mods-root", str(w / "mods"), "--cache", str(w / "cache"))
    rc4, r4, _ = cli(["import", str(mod), "--enable"], extra=("--json", *priv))
    o4["4 import --enable into private mods: ok"] = rc4 == 0 and r4.get("id") == "g6p24.my-west-dip"
    rc5, r5, _ = cli(["plan"], extra=("--json", *priv))
    plan = w / "cache" / rm.PLAN_NAME
    text = plan.read_text(encoding="utf-8") if plan.is_file() else ""
    m = p1.parse_plan(text) if text else {"txs": []}
    mods = {x["id"]: x.get("state") for x in r5.get("mods", [])} if isinstance(r5, dict) else {}
    want = f"level-tx 2 {LEVEL} g6p24.my-west-dip {r2['transaction']['id']}"
    o4["5 plan: the mod is active; one level-tx line = the preview's transaction"] = (
        rc5 == 0 and mods.get("g6p24.my-west-dip") == "active" and m["txs"] == [want])
    tcanon = rm.parse_terrain_patch(d["components"][1]["patch"], "w") if rc5 == 0 else None
    with p1.dev_env(LEVEL):
        fc = g22.combined_check(text, "a", "g6p24.my-west-dip", tcanon) if text else {}
    o4["6 inspect: independent combined checker passes on the plan; its z = the preview's"] = (
        bool(fc.get("ok")) and fc.get("expected_settled_z") == st2.get("predicted_settled_z"))
    wd.update({"preview_tx": r2.get("transaction", {}).get("id"), "predicted_z": st2.get("predicted_settled_z"),
               "plan_tx": m["txs"], "mod_state": mods, "combined_ok": fc.get("ok"),
               "combined_z": fc.get("expected_settled_z"), "text_preview": t2})
    det["o4"] = wd
    O["O4"] = o4

    # O5 compatibility and production safety
    o5 = {}
    st = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "r3hd_mods.py"), "selftest"], capture_output=True,
                        text=True, cwd=ROOT)
    last = st.stdout.strip().splitlines()[-1] if st.stdout.strip() else ""
    o5["selftest PASS (incl. G6-P21 / G6-P22 mixed-mod and gate-off refusals, G6-P24 diagnostics)"] = (
        st.returncode == 0 and last.startswith("R3HD_MODS_SELFTEST PASS"))
    det["selftest"] = last
    gate1 = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    o5["development gate status production before and after"] = gate0.stdout.strip() == gate1.stdout.strip() == "production"
    hs = {n: rm.sha256_bytes((BIN / n).read_bytes()) for n in PROD}
    o5["production binaries unchanged (r3hd.exe e1c6df2b..., rexruntime.dll b47316a8...)"] = hs == PROD
    o5["no development gate string in the production binaries"] = all(
        rm.STRUCT_ENV.encode() not in (BIN / n).read_bytes() for n in PROD)
    det["binaries"] = hs
    O["O5"] = o5

    res = {"pass": all(all(v.values()) for v in O.values()), "checks": O, "details": det}
    (WORK / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"pass": res["pass"], "checks": O}, indent=1))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    if sys.argv[1:] != ["check"]:
        raise SystemExit(__doc__)
    sys.exit(check())

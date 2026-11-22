#!/usr/bin/env python3
"""G6-P63: level editor / 3D viewer round trip - export, install, disable / re-enable, replace safety and reopen.

    python tools/g6p63_editor_roundtrip_check.py --selftest   -> G6P63_SELFTEST PASS n/n      (no game data needed)
    python tools/g6p63_editor_roundtrip_check.py check        -> G6P63_ROUNDTRIP_CHECK PASS n/n

--selftest: synthetic manifests and packages only. The import-safety cases stub the mod manager's compiler
(r3hd_mods.compile_mod) so that only the editor's import decision is under test; nothing reads game files.

check: the person's own extracted game data (read only; hashed before and after), the editor's own code paths
(EditorApp with a withdrawn Tk root, and the 3D window attached with show=False: no window maps, no dialog, no
input), and private mod folders under private/work/g6p63 - never the person's mods folder, which is hashed before and
after. One supported edit per remix level and the intro_20 level patch preset are exported twice (determinism),
validated by the mod manager, reopened and re-exported (identity), installed, disabled and re-enabled (plan), and the
same-id replacement is refused until confirmed. No game process: in-game behaviour is NOT verified here.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402

WORK = ROOT / "private" / "work" / "g6p63"
LEVELS = ("intro_10", "intro_15", "intro_20")
FAKE = "ab" * 32


def tree_hashes(d: Path) -> dict:
    """{relative path: sha256} of a folder (no links followed); {} when it does not exist."""
    out = {}
    if not d.is_dir():
        return out
    for dp, dn, fn in os.walk(d, followlinks=False):
        dn[:] = [x for x in dn if not os.path.islink(os.path.join(dp, x))]
        for f in fn:
            p = Path(dp) / f
            if not p.is_symlink():
                out[p.relative_to(d).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def refused(fn, code):
    try:
        fn()
    except core.EditorError as x:
        return x.code == code
    return False


def report(results, tag):
    ok = sum(1 for _, v in results if v)
    for k, v in results:
        print(f"{'PASS' if v else 'FAIL'} {k}")
    verdict = "PASS" if ok == len(results) else "FAIL"
    print(f"{tag} {verdict} {ok}/{len(results)}")
    return 0 if verdict == "PASS" else 1


# ------------------------------------------------------------------------------------------------ selftest
def synthetic_remix(level="intro_10", dx=0.0, desc=""):
    p = core.new_remix(level)
    p["meta"]["description"] = desc
    p["actors"] = [{"model": "synthetic\\Model_A", "instance": 0, "matrix_sha256": FAKE,
                    "position": [1.0 + dx, 2.0, 3.0]}]
    p["waypoints"] = [{"model": "synthetic\\Model_B", "instance": 1, "variable": 0, "node": 2,
                       "waypoint_sha256": FAKE, "position": [4.0, 5.0, 6.5]}]
    return core.check_remix(p)


def write_pkg(d: Path, manifest, extra=None):
    d.mkdir(parents=True)
    (d / "mod.json").write_bytes(manifest if isinstance(manifest, bytes) else core.manifest_bytes(manifest))
    for k, v in (extra or {}).items():
        (d / k).write_bytes(v)
    return d


def selftest() -> int:
    R = []
    td = Path(tempfile.mkdtemp(prefix="g6p63-self-"))
    try:
        mp = core.mod_paths()
        p = synthetic_remix()
        m = core.remix_manifest(p, mp)
        d1 = write_pkg(td / "remix", m)
        kind, q, src = core.open_file(d1 / "mod.json")
        R.append(("S1 a remix export reopens as the same project (generated description dropped)",
                  (kind, src) == ("v2", "mod") and q == p and q["meta"]["description"] == ""))
        R.append(("S2 re-exporting the reopened project gives the same mod.json bytes",
                  core.manifest_bytes(core.remix_manifest(q, mp)) == (d1 / "mod.json").read_bytes()))
        R.append(("S3 the folder itself opens like its mod.json", core.open_file(d1)[:2] == ("v2", p)))
        pd = synthetic_remix(desc="My own words")
        d2 = write_pkg(td / "described", core.remix_manifest(pd, mp))
        R.append(("S4 a written description and name survive the reopen",
                  core.project_from_mod(d2)[1]["meta"] == pd["meta"]))
        bad = dict(m, authors=["someone"])
        R.append(("S5 a hand-added manifest key is refused (it would be dropped on export)",
                  refused(lambda: core.project_from_mod(write_pkg(td / "authors", bad)), "NOT_EDITOR_MOD")))
        bad = json.loads(json.dumps(m))
        bad["overrides"].reverse()
        R.append(("S6 a reordered override list is refused (not the editor's canonical export)",
                  refused(lambda: core.project_from_mod(write_pkg(td / "order", bad)), "NOT_EDITOR_MOD")))
        R.append(("S7 extra package files are refused",
                  refused(lambda: core.project_from_mod(write_pkg(td / "extra", m, {"readme.txt": b"x"})),
                          "NOT_EDITOR_MOD")))
        rec = json.dumps({"schema": 1, "id": m["id"], "files": {}}).encode()
        R.append(("S8 a mod manager's installed copy (installed.json of the same id) reopens",
                  core.project_from_mod(write_pkg(td / "inst", m, {"installed.json": rec}))[1] == p))
        rec2 = json.dumps({"schema": 1, "id": "other.mod", "files": {}}).encode()
        R.append(("S9 an installed.json of another id is refused",
                  refused(lambda: core.project_from_mod(write_pkg(td / "inst2", m, {"installed.json": rec2})),
                          "NOT_EDITOR_MOD")))
        mixed = json.loads(json.dumps(m))
        mixed["overrides"][1]["level"] = "intro_15"
        R.append(("S10 a mod over two levels is refused",
                  refused(lambda: core.project_from_mod(write_pkg(td / "mixed", mixed)), "NOT_EDITOR_MOD")))
        tex = dict(m, overrides=[{"type": "texture", "entry": "menu\\x.dds", "image": "x.png"}])
        R.append(("S11 a texture mod is refused",
                  refused(lambda: core.project_from_mod(write_pkg(td / "tex", tex, {"x.png": b"\x89PNG"})),
                          "NOT_EDITOR_MOD")))
        R.append(("S12 malformed JSON is refused by the mod manager's own parser",
                  refused(lambda: core.project_from_mod(write_pkg(td / "broken", b"{")), "BAD_MANIFEST")))
        R.append(("S13 a non-mod.json file name is refused",
                  refused(lambda: core.project_from_mod(d1 / "other.json"), "NOT_EDITOR_MOD")))
        R.append(("S14 the project loader names an exported mod instead of a format error",
                  refused(lambda: core.load_any(d1 / "mod.json"), "UNSUPPORTED")))
        # level patch (v1): the manifest r3hd_mods.cmd_level_patch writes, rebuilt here from the editor declaration
        v1 = core.new_project()
        v1["terrain"] = {"2": -0.15, "4": -0.15, "6": -0.2}
        v1["meta"]["description"] = "basin"
        v1 = core.check_project(v1)
        decl = core.declaration(v1)
        lp = {"format": rm.FORMAT, "id": decl["id"], "name": f"Level patch {decl['id']}", "version": "1.0.0",
              "description": decl["description"],
              "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids(mp), "min_port_version": "0.0.1"},
              "overrides": [{"type": "level-patch", "patch": decl}]}
        k1, q1 = core.project_from_mod(write_pkg(td / "lp", lp))
        R.append(("S15 a level-patch export reopens as the same terrain / route / FairyLight project",
                  k1 == "v1" and {x: q1[x] for x in q1 if x != "meta"} == {x: v1[x] for x in v1 if x != "meta"}
                  and q1["meta"]["id"] == v1["meta"]["id"] and q1["meta"]["description"] == "basin"))
        g = json.loads(json.dumps(lp))
        g["overrides"][0]["patch"]["components"][0]["patch"]["groups"][0]["name"] = "west"
        R.append(("S16 a level patch with non-editor terrain groups is refused",
                  refused(lambda: core.project_from_mod(write_pkg(td / "lpg", g)), "NOT_EDITOR_MOD")))
        h = json.loads(json.dumps(lp))
        h["overrides"][0]["patch"]["lvl_sha256"] = FAKE
        R.append(("S17 a level patch for other level files is refused (the mod manager's parser: UNSUPPORTED)",
                  refused(lambda: core.project_from_mod(write_pkg(td / "lph", h)), "UNSUPPORTED")))
        # import safety: the editor's decision with a stubbed compiler (no game data)
        real = rm.compile_mod
        rm.compile_mod = lambda *a, **k: []
        try:
            paths = {"home": mp["home"], "game": td / "nogame", "mods": td / "mods", "cache": td / "cache"}
            other = write_pkg(td / "other", core.remix_manifest(synthetic_remix(dx=1.0), mp))
            r0 = core.import_mod(other, paths)
            rm.cmd_set(paths, m["id"], False)                     # the person disabled their mod
            before = tree_hashes(paths["mods"])
            r1 = core.import_mod(d1, paths)
            R.append(("S18 a different package with an installed id is refused EXISTS; mods folder unchanged",
                      r0["ok"] and not r1["ok"] and r1["code"] == "EXISTS" and tree_hashes(paths["mods"]) == before
                      and r1["existing"].get("enabled") is False and "Nothing was changed" in r1["detail"]))
            r2 = core.import_mod(other, paths)
            R.append(("S19 re-importing the identical package is not a replacement (ok, unchanged, enabled)",
                      r2["ok"] and r2["result"].get("unchanged") and rm.load_state(paths)["mods"][0]["enabled"]))
            third = write_pkg(td / "first", dict(core.remix_manifest(synthetic_remix(), mp), id="g6p63.first"))
            core.import_mod(third, paths)
            rm.cmd_move(paths, "g6p63.first", "top")
            r3 = core.import_mod(d1, paths, replace=True)
            st = rm.load_state(paths)["mods"]
            inst = (paths["mods"] / "installed" / m["id"] / "mod.json").read_bytes()
            R.append(("S20 an explicit replace installs the new package and keeps its priority",
                      r3["ok"] and r3["result"]["replaced"] and [e["id"] for e in st] == ["g6p63.first", m["id"]]
                      and inst == (d1 / "mod.json").read_bytes()))
            before = tree_hashes(paths["mods"])
            r4 = core.import_mod(write_pkg(td / "badjson", b"{"), paths)
            R.append(("S21 other refusals pass through unchanged (malformed package: BAD_MANIFEST, nothing changed)",
                      not r4["ok"] and r4["code"] == "BAD_MANIFEST" and tree_hashes(paths["mods"]) == before))
        finally:
            rm.compile_mod = real
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return report(R, "G6P63_SELFTEST")


# ------------------------------------------------------------------------------------------------ check
def check() -> int:
    import tkinter as tk
    import r3hd_level_editor as ed
    R, det = [], {}
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    game = Path(core.mod_paths()["game"])
    person_mods = Path(core.mod_paths()["mods"])
    level_files = {}
    for lv in LEVELS:
        lp, pp, _ = rm.script_level_files(game, lv)
        for f in (lp, pp, lp.with_name("transit.lvl")):
            level_files[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    fix = game / "GAMEDATAbin" / "fix.lvl"
    level_files[str(fix)] = hashlib.sha256(fix.read_bytes()).hexdigest()
    mods_before = tree_hashes(person_mods)

    def paths(tag):
        return {"home": core.mod_paths()["home"], "game": game, "mods": WORK / tag / "mods",
                "cache": WORK / tag / "cache"}

    root = tk.Tk()
    root.withdraw()
    try:
        a = ed.EditorApp(root, game)
        a.canvas_w, a.canvas_h = 1000, 760
        exported = {}
        for lv in LEVELS:
            a.set_mode("remix", lv)
            akey = sorted(k for k, v in a.rmodel.actors.items() if v["status"] not in ("locked",
                                                                                         "script_overridden"))[0]
            pos = a.rmodel.actors[akey]["position"]
            a.set_remix_position(("actor", akey), [pos[0] + 3.0, pos[1], pos[2]])
            gkey = next(k for k, g in sorted(a.rmodel.graphs.items()) if g["status"] != "locked"
                        and any(n and not n["why"] for n in g["nodes"]))
            nd = next(n for n in a.rmodel.graphs[gkey]["nodes"] if n and not n["why"])
            a.set_remix_position(("rwp", gkey + (nd["node"],)), [nd["position"][0] + 2.0, nd["position"][1],
                                                                 nd["position"][2]])
            proj = json.loads(json.dumps(a.remix))
            e1 = a.export_mod(WORK / f"{lv}_a")
            e2 = a.export_mod(WORK / f"{lv}_b")
            b1, b2 = (WORK / f"{lv}_a" / "mod.json").read_bytes(), (WORK / f"{lv}_b" / "mod.json").read_bytes()
            det[lv] = {"actor": [akey[0].split("\\")[-1], akey[1]], "waypoint_node": nd["node"],
                       "ranges": e1.get("ranges"), "mod_json_sha256": hashlib.sha256(b1).hexdigest()}
            v = rm.cmd_validate(paths("validate"), WORK / f"{lv}_a")
            R.append((f"E1 {lv}: one actor + one waypoint edit export twice to identical bytes; the mod manager "
                      f"validates it ({e1.get('ranges')} ranges)",
                      e1["ok"] and e2["ok"] and b1 == b2 and v["ranges"] == e1["ranges"] and v["overrides"] == 2))
            again = WORK / f"{lv}_a" / "mod.json"
            opened = a.open_project(again)
            R.append((f"E2 {lv}: the exported mod reopens as the same project, with no path (Save cannot write "
                      "over the mod)", opened and a.mode == "remix" and a.remix == proj and a.path is None))
            e3 = a.export_mod(WORK / f"{lv}_c")
            R.append((f"E3 {lv}: re-exporting the reopened project gives the same bytes",
                      e3["ok"] and (WORK / f"{lv}_c" / "mod.json").read_bytes() == b1))
            a.set_remix_position(("actor", akey), [pos[0] + 4.0, pos[1], pos[2]])
            e4 = a.export_mod(WORK / f"{lv}_d")
            R.append((f"E4 {lv}: further editing of the reopened project exports a changed, valid mod",
                      e4["ok"] and (WORK / f"{lv}_d" / "mod.json").read_bytes() != b1))
            exported[lv] = (WORK / f"{lv}_a", proj)

        # install, disable, re-enable in an isolated mods folder
        p = paths("install")
        imp = {lv: a.import_mod(exported[lv][0], p) for lv in LEVELS}
        res = rm.resolve_all(p)
        installed = tree_hashes(p["mods"] / "installed")
        R.append(("E5 the three remix mods import + enable; the plan applies all three as gameplay mods",
                  all(r["ok"] for r in imp.values()) and len(res["active"]) == 3
                  and set(res["gameplay_active"]) == set(res["active"])))
        mid = imp["intro_10"]["result"]["id"]
        rm.cmd_set(p, mid, False)
        res2 = rm.resolve_all(p)
        R.append(("E6 disabling one leaves it installed (files unchanged) and out of the plan",
                  mid not in res2["active"] and len(res2["active"]) == 2
                  and tree_hashes(p["mods"] / "installed") == installed))
        rm.cmd_set(p, mid, True)
        res3 = rm.resolve_all(p)
        R.append(("E7 re-enabling restores the same plan (active mods and range count)",
                  sorted(res3["active"]) == sorted(res["active"]) and res3["ranges"] == res["ranges"]
                  and tree_hashes(p["mods"] / "installed") == installed))
        det["plan"] = {"active": res["active"], "ranges": res["ranges"]}

        # a second, different intro_10 project with the default id (the ordinary collision)
        a.set_mode("remix", "intro_10")
        akey = sorted(k for k, v in a.rmodel.actors.items() if v["status"] not in ("locked", "script_overridden"))[1]
        pos = a.rmodel.actors[akey]["position"]
        a.set_remix_position(("actor", akey), [pos[0], pos[1] + 2.0, pos[2]])
        a.set_meta("id", mid)
        other = WORK / "intro_10_other"
        a.export_mod(other)
        state_before, tree_before = (p["mods"] / "state.json").read_bytes(), tree_hashes(p["mods"])
        r = a.import_mod_asking(other, root, p)                  # withdrawn root: no dialog may open
        R.append(("E8 importing a different mod with an installed id is refused (EXISTS) without a dialog; the "
                  "installed mod, its files and the mod list are unchanged",
                  not r["ok"] and r["code"] == "EXISTS" and tree_hashes(p["mods"]) == tree_before
                  and (p["mods"] / "state.json").read_bytes() == state_before
                  and "NOT IMPORTED (EXISTS)" in a.status_var.get()))
        r = a.import_mod(exported["intro_10"][0], p)
        R.append(("E9 re-importing the identical package is not a replacement",
                  r["ok"] and r["result"].get("unchanged") and tree_hashes(p["mods"] / "installed")
                  .get(f"{mid}/mod.json") == installed.get(f"{mid}/mod.json")))
        order = [e["id"] for e in rm.load_state(p)["mods"]]
        r = a.import_mod(other, p, replace=True)
        R.append(("E10 the confirmed replacement installs the new package and keeps its priority and enabled state",
                  r["ok"] and r["result"]["replaced"] and [e["id"] for e in rm.load_state(p)["mods"]] == order
                  and (p["mods"] / "installed" / mid / "mod.json").read_bytes() == (other / "mod.json").read_bytes()
                  and next(e for e in rm.load_state(p)["mods"] if e["id"] == mid)["enabled"]))

        # level patch (intro_20 terrain + FairyLight, production preset)
        a.set_mode("patch")
        a.set_project(core.patch_preset())
        v1 = json.loads(json.dumps(a.project))
        l1, l2 = a.export_mod(WORK / "patch_a"), a.export_mod(WORK / "patch_b")
        lb = (WORK / "patch_a" / "mod.json").read_bytes()
        a.set_mode("remix", "intro_15")
        ok_open = a.open_project(WORK / "patch_a")
        reopened = json.loads(json.dumps(a.project)) if ok_open else None
        l3 = a.export_mod(WORK / "patch_c") if ok_open else {"ok": False}
        R.append(("E11 the intro_20 level patch exports deterministically, reopens (terrain, route, FairyLight) and "
                  "re-exports to the same bytes",
                  l1["ok"] and l2["ok"] and (WORK / "patch_b" / "mod.json").read_bytes() == lb and ok_open
                  and a.mode == "patch" and a.path is None
                  and {k: reopened[k] for k in reopened if k != "meta"} == {k: v1[k] for k in v1 if k != "meta"}
                  and l3["ok"] and (WORK / "patch_c" / "mod.json").read_bytes() == lb))
        det["patch_mod_json_sha256"] = hashlib.sha256(lb).hexdigest()
        rp = a.import_mod(WORK / "patch_a", p)
        res4 = rm.resolve_all(p)
        R.append(("E12 the level patch installs beside the remix mods and resolves active (production content)",
                  rp["ok"] and rp["result"]["id"] in res4["active"]))

        # refusals: unsupported edits never export, malformed mods never open
        a.set_mode("remix", "intro_10")
        lk = next((k for k, v in sorted(a.rmodel.actors.items()) if v["status"] == "locked"), None)
        bad = json.loads(json.dumps(a.remix))
        x = a.rmodel.actors[lk]
        bad["actors"] = [{"model": lk[0], "instance": lk[1], "matrix_sha256": x["matrix_sha256"] or FAKE,
                          "position": [x["position"][0] + 1, x["position"][1], x["position"][2]]}]
        rl = core.validate_remix(bad, game, WORK / "locked", model=a.rmodel)
        R.append(("E13 an edit of a locked actor is refused and nothing is written",
                  not rl["ok"] and not (WORK / "locked").exists()))
        far = json.loads(json.dumps(exported["intro_10"][1]))
        far["actors"][0]["position"][0] += 40.0
        rf = core.validate_remix(far, game, WORK / "far", model=a.rmodel)
        R.append(("E14 a move beyond the evidence bound is refused and nothing is written",
                  not rf["ok"] and not (WORK / "far").exists()))
        hand = WORK / "hand"
        shutil.copytree(exported["intro_10"][0], hand)
        mj = json.loads((hand / "mod.json").read_text(encoding="utf-8"))
        mj["version"] = "1.0.1"
        (hand / "mod.json").write_text(json.dumps(mj, indent=1) + "\n", encoding="utf-8")
        cur = json.loads(json.dumps(a.remix))
        R.append(("E15 a hand-edited exported mod is refused on open and the open project is untouched",
                  not a.open_project(hand / "mod.json") and a.remix == cur))

        # the 3D viewer: its toolbar has Open... and its import confirmation never opens a dialog unseen
        import r3hd_scene_view as sv
        root3 = tk.Tk()
        root3.withdraw()
        try:
            app3, view = sv.open_editor(root3, game, level="intro_10", show=False)
            labels = [w.cget("text") for w in view.top.winfo_children()[0].winfo_children()
                      if isinstance(w, tk.ttk.Button)]
            tree3 = tree_hashes(p["mods"])
            r = app3.import_mod_asking(exported["intro_10"][0], view.top, p)   # differs from the replaced mod
            ok3 = app3.open_project(WORK / "intro_15_a")
            R.append(("E16 3D viewer: Open... is offered; an exported mod opens there; a same-id import from the "
                      "withdrawn 3D window refuses without a dialog and changes nothing",
                      "Open..." in labels and ok3 and app3.remix == exported["intro_15"][1] and app3.path is None
                      and r["code"] == "EXISTS" and tree_hashes(p["mods"]) == tree3))
            det["toolbar"] = labels
            view.close(ask=False)
        finally:
            try:
                root3.destroy()
            except tk.TclError:
                pass
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass

    after = {k: hashlib.sha256(Path(k).read_bytes()).hexdigest() for k in level_files}
    R.append(("E17 the person's level files and fix.lvl are byte-identical before and after", after == level_files))
    R.append(("E18 the person's own mods folder is untouched", tree_hashes(person_mods) == mods_before))
    (WORK / "details.json").write_text(json.dumps(det, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(det, indent=1, default=str))
    return report(R, "G6P63_ROUNDTRIP_CHECK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", nargs="?", choices=["check"])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.mode == "check":
        return check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

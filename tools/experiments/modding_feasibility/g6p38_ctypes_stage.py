#!/usr/bin/env python3
"""E-527 (D-294) G6-P38: can the packaged Python runtime start the 3D editor? An isolated, private feasibility stage.

    g6p38_ctypes_stage.py check [--python-dir D]

Copies app/python, app/tools and app/config of the G6-P36 stage (private/work/e525/stage/payload, read only) to a NEW folder
private/work/g6p38/ctypes_stage, verifies the copied runtime equals the payload pins, then builds two variants:
  as_released   unchanged: the 3D editor must refuse cleanly (no ctypes) while the 2D editor module still imports;
  with_ctypes   plus DLLs _ctypes.pyd and libffi-8.dll of the same official CPython 3.11.4 build (exact SHA-256 below;
                Authenticode Python Software Foundation, checked by the report) and the stdlib `ctypes` package added to
                python311.zip; both variants carry the three G6-P37/38 modules in app/tools.
Each variant runs its STAGED python.exe (-I, no local Python on PATH): import checks, then for with_ctypes a hidden
offscreen render (one readback) and the 3D editor with withdrawn windows (select, preview, apply, validate, undo).
Nothing here changes config/release, the release stage, the candidate or any package; the payload keeps its documented
"no _ctypes" property until a person decides otherwise (D-294).

Superseded (G6-P39, D-295): the maintainer chose the narrow OpenGL bridge (option b), so the 3D modules no longer use
ctypes and this option-(a) experiment no longer renders; it is kept as the record of E-527. The packaged route is
checked by g6p39_bridge_check.py and g6p39_release_acceptance.py.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[1]
ROOT = TOOLS.parent
SRC = ROOT / "private" / "work" / "e525" / "stage" / "payload" / "app"
OUT = ROOT / "private" / "work" / "g6p38" / "ctypes_stage"
PAYLOAD = ROOT / "config" / "release" / "payload.json"
TKPIN = ROOT / "config" / "release" / "python_tk.json"
CTYPES_FILES = {"_ctypes.pyd": "ee543453ac1a2b9b52e80dc66207d3767012ca24ce2b44206804767f37443902",
                "libffi-8.dll": "eff52743773eb550fcc6ce3efc37c85724502233b6b002a35496d828bd7b280a"}
MODULES = ("r3hd_level_scene.py", "r3hd_scene_gl.py", "r3hd_scene_view.py")

PROBE = r'''
import json, os, sys, tempfile, time
sys.path.insert(0, sys.argv[1])
out = {"python": sys.version.split()[0], "prefix": sys.prefix, "executable": sys.executable}
try:
    import ctypes
    out["ctypes"] = ctypes.__file__
except ImportError as x:
    out["ctypes"] = "ImportError: " + str(x)
import tkinter as tk
import r3hd_level_editor as ed
out["editor_2d_import"] = True
try:
    import r3hd_scene_view as sv
    out["scene_view_import"] = True
except ImportError as x:
    out["scene_view_import"] = "ImportError: " + str(x)
if out["scene_view_import"] is True and len(sys.argv) > 3:
    import r3hd_scene_gl as sg
    from pathlib import Path
    r = sg.render_test(sys.argv[2], "intro_20", Path(sys.argv[3]) / "staged_intro20.png", frames=10)
    out["render"] = {k: r[k] for k in ("first_frame_ms", "interactive_ms_median", "upload_seconds", "gl_error",
                                        "window_visible", "readbacks", "covered_share_sampled")}
    root = tk.Tk(); root.withdraw()
    t0 = time.perf_counter()
    app, v = sv.open_editor(root, sys.argv[2], show=False)
    v.vp.configure(width=800, height=480); root.update_idletasks()
    out["gl"] = v.ensure_gl()
    out["load_seconds"] = round(time.perf_counter() - t0, 3)
    ident = next(i for i, a in app.rmodel.actors.items() if a["name"] == "NIK_mChameleon")
    v.select(("actor", ident))
    p = list(app.rmodel.actors[ident]["position"]); p[0] += 2.0
    v.preview = {"sel": ("actor", ident), "pos": tuple(p)}
    v.apply()
    out["applied"] = len(app.remix["actors"]) == 1
    vr = app.validate_now()
    out["valid"] = vr["ok"]
    out["validate_detail"] = None if vr["ok"] else [vr.get("code"), str(vr.get("detail"))[:300]]
    v.undo()
    out["undone"] = not app.remix["actors"]
    out["viewable"] = bool(v.top.winfo_viewable() or root.winfo_viewable())
    v.close(ask=False)
print(json.dumps(out))
'''


def sha(p):
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(py: Path, game: Path, work: Path, render: bool):
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PYTHONPATH", "PYTHONHOME")}
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if "python" not in p.lower())
    probe = work / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    args = [str(py), "-I", "-B", str(probe), str(py.parents[1] / "tools"), str(game)] + ([str(work)] if render else [])
    r = subprocess.run(args, capture_output=True, text=True, env=env, cwd=str(work), timeout=600)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"error": r.returncode, "stderr": r.stderr[-800:]}


def check(python_dir: Path):
    sys.path.insert(0, str(TOOLS))
    import r3hd_level_editor_core as core
    game = core.default_game_dir()
    pins = json.loads(PAYLOAD.read_text(encoding="utf-8"))["python"]
    tkpins = json.loads(TKPIN.read_text(encoding="utf-8"))["files"]
    if OUT.exists():
        shutil.rmtree(OUT)                       # this experiment's own folder only
    res = {"source_stage": str(SRC.relative_to(ROOT)), "checks": {}}
    C = res["checks"]
    for variant in ("as_released", "with_ctypes"):
        app = OUT / variant / "app"
        shutil.copytree(SRC / "python", app / "python")
        shutil.copytree(SRC / "tools", app / "tools")
        shutil.copytree(SRC / "config", app / "config")      # the staged layout the compiler reads
        shutil.copy2(SRC.parent / "payload.json", app.parent / "payload.json")   # port version of a staged payload
        pyd = app / "python"
        C[f"{variant}: copied runtime equals the payload pins"] = all(
            sha(pyd / n) == h for n, h in pins["files"].items() if (pyd / n).is_file()) and sha(
            pyd / "_tkinter.pyd") == tkpins["app/python/_tkinter.pyd"]["sha256"] and sha(
            pyd / "python311.zip") == pins["stdlib_zip_sha256"]
        if variant == "with_ctypes":
            for n, h in CTYPES_FILES.items():
                src = python_dir / "DLLs" / n
                C[f"with_ctypes: {n} is the pinned official file"] = sha(src) == h
                shutil.copy2(src, pyd / n)
            buf = io.BytesIO(pyd.joinpath("python311.zip").read_bytes())
            zout = io.BytesIO()
            with zipfile.ZipFile(buf) as zin, zipfile.ZipFile(zout, "w", zipfile.ZIP_DEFLATED) as zw:
                for i in zin.infolist():
                    zw.writestr(i, zin.read(i.filename))
                added = 0
                for f in sorted((python_dir / "Lib" / "ctypes").rglob("*.py")):
                    rel = f.relative_to(python_dir / "Lib").as_posix()
                    if "/test/" in rel:
                        continue
                    zi = zipfile.ZipInfo(rel, (2023, 6, 6, 0, 0, 0))   # fixed date: a reproducible digest
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zw.writestr(zi, f.read_bytes())
                    added += 1
            pyd.joinpath("python311.zip").write_bytes(zout.getvalue())
            res["stdlib_zip_with_ctypes"] = {"sha256": sha(pyd / "python311.zip"), "ctypes_files": added}
            res["added_bytes"] = sum((pyd / n).stat().st_size for n in CTYPES_FILES)
        for m in MODULES:                         # both variants carry the 3D modules
            shutil.copy2(TOOLS / m, app / "tools" / m)
        work = OUT / variant / "work"
        work.mkdir(parents=True)
        res[variant] = run(pyd / "python.exe", game, work, render=(variant == "with_ctypes"))
    a, b = res["as_released"], res["with_ctypes"]
    C["as_released: staged python, no ctypes, 2D editor imports, 3D editor refuses cleanly"] = (
        a.get("prefix", "").lower().startswith(str(OUT).lower()) and str(a.get("ctypes", "")).startswith("ImportError")
        and a.get("editor_2d_import") is True and str(a.get("scene_view_import", "")).startswith("ImportError"))
    C["with_ctypes: staged python (no system Python) imports ctypes from the stage"] = (
        b.get("prefix", "").lower().startswith(str(OUT).lower()) and str(OUT).lower() in str(b.get("ctypes", "")).lower())
    C["with_ctypes: hidden render, one readback, no GL error, window never visible"] = (
        b.get("render", {}).get("gl_error") == 0 and b["render"].get("readbacks") == 1
        and b["render"].get("window_visible") is False)
    C["with_ctypes: 3D editor select / apply / validate / undo, nothing viewable"] = (
        b.get("gl") is True and b.get("applied") and b.get("valid") and b.get("undone") and b.get("viewable") is False)
    ok = all(C.values())
    (OUT / "g6p38_ctypes_stage.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    for k, v in C.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(json.dumps({k: res[k] for k in ("stdlib_zip_with_ctypes", "added_bytes", "as_released", "with_ctypes")},
                     indent=1))
    print(f"G6-P38 CTYPES_STAGE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    args = sys.argv[1:]
    if not args or args[0] != "check":
        print(__doc__)
        return 2
    py = Path(args[args.index("--python-dir") + 1]) if "--python-dir" in args else Path(sys.base_prefix)
    return check(py)


if __name__ == "__main__":
    sys.exit(main())

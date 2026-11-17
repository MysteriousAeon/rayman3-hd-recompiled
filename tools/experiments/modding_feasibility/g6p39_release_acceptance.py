#!/usr/bin/env python3
"""E-528 (D-295) G6-P39: the 3D Level Remix Editor in the REAL installer and portable package.

    g6p39_release_acceptance.py installer STAGE SOURCE OUT
    g6p39_release_acceptance.py portable STAGE SOURCE OUT CRT

Runs every G6-P36 row (g6p36_release_acceptance: G6-P31 package rows, the remix rows, and for the installer the
uninstall lifecycle) on a G6-P39 stage, with two changes:
  * after the remix rows, the 3D rows below run on the package's own Python;
  * the editor that is open while uninstall is attempted is the 3D Level Remix Editor (withdrawn root, real OpenGL
    context on its withdrawn viewport, this installation's lock), so uninstall must refuse while it is open and work
    after it closed normally.
3D rows: the bridge and the three 3D modules are in the package (pinned bytes) and no _ctypes / libffi is; the
launcher's --level-editor-3d dry run names the package's pythonw.exe, r3hd_scene_view.py and home; on the package's
python.exe the 3D editor opens from HOME/data/content (the owner's data copied by the package), draws, switches
levels, edits through the editor's methods (select, preview, apply, validate, save / reopen, export, import into
HOME/mods, undo), closes and reopens with everything freed; the classic editor opens in the same process; the
installed app tree equals the stage payload (no stray file).
G6-P42 adds a production PlayStation prompt-plan check using each package's isolated Python and game-data path.
SOURCE (the owner's extracted game tree) is read only. OUT must be new and under private/work. Tk roots are withdrawn
and windows never shown; launcher actions are dry runs; the game never starts; no input is sent.
Prints rows and G6P39_<MODE> PASS|FAIL; OUT/result.json.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g6p36_release_acceptance as g36  # noqa: E402

g31 = g36.g31
ROOT = g31.ROOT
row = g31.row
rows = g31.rows
D3_MODULES = ("r3hd_scene_view.py", "r3hd_scene_gl.py", "r3hd_level_scene.py")

D3_PROBE = r'''
import json, os, sys, time
from pathlib import Path
tools, home, work = sys.argv[1], sys.argv[2], Path(sys.argv[3])
sys.path.insert(0, tools)
os.environ["R3HD_HOME"] = home                       # what r3hd_scene_view.main does with --home
out = {"prefix": sys.prefix}
try:
    import ctypes
    out["ctypes"] = ctypes.__file__
except ImportError:
    out["ctypes"] = "ImportError"
import tkinter as tk
import r3hd_level_editor as ed
import r3hd_level_editor_core as core
import r3hd_scene_view as sv
import _r3hd_scene_gl
out["bridge_file"] = _r3hd_scene_gl.__file__
cycles = []
for cycle in range(2):
    root = tk.Tk(); root.withdraw()
    t0 = time.perf_counter()
    app, v = sv.open_editor(root, show=False)
    v.vp.configure(width=800, height=480); root.update_idletasks()
    c = {"gl": v.ensure_gl(), "game_dir": str(app.game_dir)}
    v.ensure_scene()
    for k in range(4):
        v.cam.orbit(12.0, 1.5); v._draw()
    c["open_seconds"] = round(time.perf_counter() - t0, 3)
    c["frames"], c["last_ms"] = v.timing["frames"], v.timing["last_ms"]
    c["textures"], c["bridge_textures"] = v.r.stats["textures"], v.ctx.n.info()["textures"]
    c["texture_errors"] = len(v.r.stats["texture_errors"])
    if cycle == 0:
        label = next(ch[2] for ch in ed.CHOICES if ch[:2] == ("remix", "intro_15"))
        v.choose_level(label); v._draw()
        c["switch"] = {"level": app.remix["level"], "textures": v.r.stats["textures"],
                       "bridge": v.ctx.n.info()["textures"]}
        ident = next(i for i, a in app.rmodel.actors.items() if a["status"] not in ed.REFUSED)
        v.select(("actor", ident))
        p = list(app.rmodel.actors[ident]["position"]); p[0] += 1.5
        v.preview = {"sel": ("actor", ident), "pos": tuple(p)}
        v._draw()
        v.apply()
        c["applied"] = len(app.remix["actors"]) == 1
        c["valid"] = app.validate_now()["ok"]
        app.set_meta("id", "g6p39.package-3d")
        proj = work / "g6p39_3d.r3hdmap.json"
        app.save_project(proj)
        c["reopen_same"] = core.load_any(proj) == ("v2", app.remix)
        e = app.export_mod(work / "g6p39_3d_mod")
        c["export"] = bool(e["ok"])
        i = app.import_mod(work / "g6p39_3d_mod") if e["ok"] else {"ok": False}
        c["import"], c["import_mods"] = bool(i["ok"]), str(i.get("mods"))
        c["mod_id"] = e["manifest"]["id"] if e["ok"] else None
        v.undo()
        c["undone"] = not app.remix["actors"]
        app.dirty = False
    c["viewable"] = bool(v.top.winfo_viewable() or root.winfo_viewable())
    n = v.ctx.n
    v.close(ask=False)
    c["closed"] = n.info().get("closed") is True
    cycles.append(c)
out["cycles"] = cycles
root = tk.Tk(); root.withdraw()
a = ed.EditorApp(root)
a.set_mode("remix", "intro_20")
k = next(k for k, x in a.rmodel.actors.items() if x["status"] not in ed.REFUSED)   # an edit to validate
a.set_remix_position(("actor", k), [x + 1.0 for x in a.rmodel.actors[k]["position"]])
out["classic"] = {"loaded": a.rmodel is not None, "valid": a.validate_now()["ok"], "viewable": bool(root.winfo_viewable())}
a.dirty = False
root.destroy()
print("D3 " + json.dumps(out))
'''

# The 3D Level Remix Editor of this installation, on the installed pythonw.exe with a withdrawn root and a real OpenGL
# context on its withdrawn viewport: it holds the installation lock exactly as r3hd_scene_view.main does with --home.
HOLDER_3D = r'''
import json, os, sys
from pathlib import Path
tools, home, ready, stop = sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
sys.path.insert(0, tools)
os.environ["R3HD_HOME"] = home
import tkinter as tk
import r3hd_level_editor as ed
import r3hd_scene_view as sv
lock = ed.hold_home_lock(home)
root = tk.Tk()
root.withdraw()
app, v = sv.open_editor(root, show=False)
v.vp.configure(width=640, height=400); root.update_idletasks()
gl = v.ensure_gl()
v.ensure_scene(); v._draw()
info = {"lock": bool(lock), "gl": gl, "frames": v.timing["frames"], "textures": v.r.stats["textures"] if v.r else 0}
ready.with_name("holder3d.json").write_text(json.dumps(info), encoding="utf-8")
ready.write_text("held" if lock and gl and v.timing["frames"] >= 1 else "none", encoding="utf-8")
def poll():
    if stop.exists():
        v.close(ask=False)
    else:
        root.after(200, poll)
root.after(200, poll)
root.mainloop()
ed.release_home_lock(lock)
'''


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def prompt_check(label, home: Path, python: Path, out: Path, env):
    # Invoke the same script and isolated interpreter as Play. Importing it from
    # the host Python would hide missing sibling-module discovery in a package.
    code, text = g31.run([python, home / "app/tools/r3hd_button_prompts.py", "--game-dir", home / "data/content",
                         "--cache", out / "prompt_cache"], env, cwd=home)
    try:
        result = json.loads(text)
        plan = Path(result["plan"]).read_text(encoding="utf-8") if result.get("plan") else ""
    except (OSError, ValueError):
        result, plan = {}, ""
    targets = {Path(line.split(" ", 2)[2]).name.lower() for line in plan.splitlines() if line.startswith("file ")}
    row(f"{label}: packaged PlayStation prompt planner produces a fix.btf plan",
        code == 0 and result.get("result") == "ok" and result.get("ranges", 0) > 0 and targets == {"fix.btf"},
        (result.get("reason"), sorted(targets)) if result else text[-500:])


def d3_checks(label, home: Path, python: Path, out: Path, env):
    defn = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
    sg = defn["scene_gl"]
    pyd = home / "app" / "python" / "_r3hd_scene_gl.pyd"
    row(f"{label}: 3D: the OpenGL bridge is the pinned build and the three 3D modules are present",
        pyd.is_file() and sha(pyd) == sg["sha256"]
        and all((home / "app" / "tools" / m).is_file() for m in D3_MODULES), sha(pyd)[:16] if pyd.is_file() else None)
    natives = sorted(p.name for p in (home / "app" / "python").iterdir() if p.suffix.lower() in (".pyd", ".dll"))
    want = ["_r3hd_scene_gl.pyd", "_tkinter.pyd", "python3.dll", "python311.dll", "tcl86t.dll", "tk86t.dll"]
    crt_ok = True
    if label == "portable":
        # the portable package's own app-local CRT beside Python (r3hd_portable_zip.py), pinned in portable_crt.json
        crt = json.loads((ROOT / "config" / "release" / "portable_crt.json").read_text(encoding="utf-8"))["files"]
        want.append("vcruntime140.dll")
        v = home / "app" / "python" / "vcruntime140.dll"
        crt_ok = v.is_file() and sha(v) == crt["vcruntime140.dll"]
    row(f"{label}: 3D: no _ctypes / libffi in the package runtime (native files: Python, Tk, the bridge"
        + (", the pinned app-local CRT)" if label == "portable" else ")"), natives == sorted(want) and crt_ok, natives)
    code, text = g31.run([home / "app" / "r3hd_launcher.exe", "--level-editor-3d", "--dry-run", "--no-ui"], env,
                         cwd=home)
    row(f"{label}: 3D: launcher --level-editor-3d (dry run) names the package's pythonw.exe, r3hd_scene_view.py and "
        "home", code == 0 and "R3HD_LAUNCHER LEVEL_EDITOR_3D DRY_RUN" in text
        and str(home / "app" / "python" / "pythonw.exe").lower() in text.lower() and "r3hd_scene_view.py" in text
        and "--home" in text, text[-400:])
    work = out / "work3d"
    work.mkdir(exist_ok=True)
    (out / "d3_probe.py").write_text(D3_PROBE, encoding="utf-8")
    code, text = g31.run([python, "-B", out / "d3_probe.py", home / "app" / "tools", home, work], env, cwd=out,
                         timeout=1800)
    pr = {}
    for ln in text.splitlines():
        if ln.startswith("D3 "):
            pr = json.loads(ln[3:])
    (out / f"d3_{label}.json").write_text(json.dumps(pr, indent=1) + "\n", encoding="utf-8")
    cy = pr.get("cycles", [])
    c0 = cy[0] if cy else {}
    row(f"{label}: 3D: ran on the package's own Python without ctypes; bridge loaded from the package", code == 0
        and pr.get("prefix", "").lower() == str(home / "app" / "python").lower() and pr.get("ctypes") == "ImportError"
        and str(pr.get("bridge_file", "")).lower().startswith(str(home / "app" / "python").lower()), text[-800:])
    row(f"{label}: 3D: the editor opens on HOME/data/content, draws textured frames (twice opened, never viewable)",
        len(cy) == 2 and all(c["gl"] and c["frames"] >= 4 and c["textures"] > 0 and c["texture_errors"] == 0
                             and c["textures"] == c["bridge_textures"] and c["viewable"] is False
                             and c["game_dir"].lower() == str(home / "data" / "content").lower() for c in cy),
        [{k: c.get(k) for k in ("gl", "frames", "textures", "open_seconds", "last_ms")} for c in cy])
    row(f"{label}: 3D: level switch to intro_15 frees intro_20's textures (bridge = renderer)",
        c0.get("switch", {}).get("level") == "intro_15" and c0["switch"]["textures"] == c0["switch"]["bridge"],
        c0.get("switch"))
    row(f"{label}: 3D: select / preview / apply / validate / save-reopen / export / import into HOME/mods / undo",
        c0.get("applied") and c0.get("valid") and c0.get("reopen_same") and c0.get("export") and c0.get("import")
        and c0.get("undone") and c0.get("import_mods", "").lower() == str(home / "mods").lower(),
        {k: c0.get(k) for k in ("applied", "valid", "reopen_same", "export", "import", "undone", "import_mods")})
    row(f"{label}: 3D: closing frees the context; the classic editor opens in the same process",
        all(c["closed"] for c in cy) and pr.get("classic", {}).get("loaded") and pr["classic"]["valid"]
        and pr["classic"]["viewable"] is False, pr.get("classic"))
    stage_files = json.loads((STAGE / "payload" / "payload.json").read_text(encoding="utf-8"))["files"]
    want = sorted(k for k in stage_files if k.startswith("app/"))
    if label == "portable":                # the ZIP's own app members (compare-stage proves their payload bytes)
        with g31.zipfile.ZipFile(out / "g6p36-portable.zip") as zf:
            pre = g31.TOP + "/"
            want = sorted(n[len(pre):] for n in zf.namelist() if n.startswith(pre + "app/") and not n.endswith("/"))
    have = sorted(str(p.relative_to(home)).replace("\\", "/") for p in (home / "app").rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts)
    row(f"{label}: 3D: the installed app tree is exactly the package's app files (no stray file)",
        have == want, sorted(set(have) ^ set(want))[:10])


STAGE = None


def main(argv):
    global STAGE
    mode = argv[0] if argv else ""
    if mode == "installer" and len(argv) == 4:
        stage, source, out = (Path(s).resolve() for s in argv[1:])
    elif mode == "portable" and len(argv) == 5:
        stage, source, out, crt = (Path(s).resolve() for s in argv[1:])
    else:
        raise SystemExit(__doc__)
    if out.exists():
        raise SystemExit(f"{out} exists")
    if not out.is_relative_to((ROOT / "private" / "work").resolve()):
        raise SystemExit("OUT must be under private/work")
    STAGE = stage
    orig = g36.remix_checks

    def remix_then_3d(label, home, python, o, env):
        pr = orig(label, home, python, o, env)
        prompt_check(label, home, python, o, env)
        d3_checks(label, home, python, o, env)
        return pr
    g36.remix_checks = remix_then_3d
    g36.HOLDER = HOLDER_3D
    if mode == "installer":
        g36.installer(stage, source, out)
        h = out / "holder3d.json"
        info = json.loads(h.read_text(encoding="utf-8")) if h.is_file() else {}
        row("installer: the editor held open during uninstall was the 3D Level Remix Editor (lock, OpenGL context, "
            "a drawn textured frame)", info.get("lock") and info.get("gl") and info.get("frames", 0) >= 1
            and info.get("textures", 0) > 0, info)
    else:
        g36.portable(stage, source, out, crt)
    ok = bool(rows) and all(r["ok"] for r in rows)
    (out / "result.json").write_text(json.dumps({"mode": mode, "pass": ok, "rows": rows}, indent=1) + "\n",
                                     encoding="utf-8")
    print(f"G6P39_{mode.upper()} {'PASS' if ok else 'FAIL'} {sum(r['ok'] for r in rows)}/{len(rows)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""E-525 (D-292) G6-P36: release-candidate acceptance of the Level Remix Editor in the REAL installer and portable.

    g6p36_release_acceptance.py installer STAGE SOURCE OUT       G6-P31 installer rows (compile, silent test-mode install,
                                                                 shortcuts, verify, intro_20 patch workflow, mod manager,
                                                                 Play dry run), then the remix rows below, then: user
                                                                 data planted, uninstall while a hidden editor of this
                                                                 installation runs (refused, nothing removed, editor
                                                                 untouched), editor closed, uninstall (app\\ and
                                                                 shortcuts gone, user data kept)
    g6p36_release_acceptance.py portable STAGE SOURCE OUT CRT    G6-P31 portable rows plus the remix rows

Remix rows, on the package's own Python / Tk: intro_10 / intro_15 / intro_20 load in remix mode; a LOCKED item is
refused; the presets of each level apply (or one EXPERIMENTAL actor moves where a level has none); one snap-to-ground
proposal applies; the project saves and reopens identically; export and import + enable go through the mod manager;
the mod list marks every remix mod as changing game logic and the launch plan names each in a `gameplay` record (the
record that withholds new achievements in the runtime, D-224 / E-458).

SOURCE (the owner's extracted game tree) is read only. OUT must be new and under private/work. Tk roots are withdrawn
before the editor is built (never shown); launcher actions are dry runs; the game never starts; no input is sent.
Prints rows and G6P36_<MODE> PASS|FAIL; OUT/result.json.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g6p31_package_acceptance as g31  # noqa: E402

ROOT = g31.ROOT
rows = g31.rows
row = g31.row
LEVELS = ("intro_10", "intro_15", "intro_20")

REMIX_PROBE = r'''
import json, math, os, sys
from pathlib import Path
tools, home, work = sys.argv[1], sys.argv[2], Path(sys.argv[3])
sys.path.insert(0, tools)
os.environ["R3HD_HOME"] = home
import tkinter as tk
import r3hd_level_editor as ed
import r3hd_level_editor_core as core
out = {"prefix": sys.prefix, "levels": {}}
root = tk.Tk()
root.withdraw()
a = ed.EditorApp(root)
a.canvas_w, a.canvas_h = 1000, 760
for lv in ("intro_10", "intro_15", "intro_20"):
    r = {}
    a.dirty = False
    a.set_mode("remix", lv)
    m = a.rmodel
    r["loaded"] = m is not None
    if m is None:
        out["levels"][lv] = r
        continue
    st = {}
    for x in m.actors.values():
        st[x["status"]] = st.get(x["status"], 0) + 1
    r["actor_status"] = st
    r["graphs"] = len(m.graphs)
    r["triangles"] = len(getattr(m, "tris", []) or []) if hasattr(m, "tris") else None
    locked = next((k for k, x in m.actors.items() if x["status"] in ed.REFUSED), None)
    if locked is not None:
        p = m.actors[locked]["position"]
        r["locked_refused"] = a.set_remix_position(("actor", locked), [p[0] + 1.0, p[1], p[2]]) is False \
            and ("actor", locked) not in a.remix_edits()
    pres = [ps["id"] for ps in core.PRESETS if ps["level"] == lv]
    for pid in pres:
        a.cmd_preset(pid, confirm=False)
    r["presets"] = pres
    gi = m.ground_index()
    snapped = None
    for ident, x in sorted(m.actors.items()):
        if x["status"] in ed.REFUSED or ("actor", ident) in a.remix_edits():
            continue
        pos = [core.f32(x["position"][0] + 3.0), x["position"][1], x["position"][2]]
        if core.snap_proposal(gi, pos, x["position"], core.MAX_ACTOR_MOVE)["ok"]:
            a.sel = ("actor", ident)
            a.set_remix_position(a.sel, pos, clamp=False)
            snapped = bool(a.snap_preview()["ok"] and a.snap_apply())
            r["snapped_status"] = x["status"]
            break
    r["snapped"] = snapped
    if not a.remix["actors"] and not a.remix["waypoints"]:
        k = next(k for k, v in m.actors.items() if v["status"] not in ed.REFUSED)
        a.set_remix_position(("actor", k), [v + 2 for v in m.actors[k]["position"]])
    r["edits"] = {"actors": len(a.remix["actors"]), "waypoints": len(a.remix["waypoints"])}
    r["warnings"] = len(core.remix_warnings(a.remix, m))
    a.set_meta("id", f"g6p36.{lv.replace('_', '')}-remix")
    proj = work / f"remix_{lv}.r3hdmap.json"
    a.save_project(proj)
    r["reopened_same"] = core.load_any(proj) == ("v2", a.remix)
    e = a.export_mod(work / f"remix_mod_{lv}")
    r["export"] = bool(e["ok"])
    r["mod_id"] = e["manifest"]["id"] if e["ok"] else e.get("code")
    r["ranges"] = e.get("ranges")
    i = a.import_mod(work / f"remix_mod_{lv}") if e["ok"] else {"ok": False}
    r["import"] = bool(i["ok"])
    r["import_mods"] = str(i.get("mods"))
    out["levels"][lv] = r
    a.dirty = False
out["scope_levels"] = all(lv in ed.SCOPE_TEXT for lv in ("intro_10", "intro_15", "intro_20")) \
    and "Level Remix Editor" in ed.SCOPE_TEXT and "EXPERIMENTAL" in ed.SCOPE_TEXT and "achievements" in ed.SCOPE_TEXT
root.destroy()
print("REMIX " + json.dumps(out))
'''

# The real editor of this installation, on the installed pythonw.exe, built with its root withdrawn: it holds the
# G6-P36 lock exactly as r3hd_level_editor.main does with --home, until OUT/stop appears.
HOLDER = r'''
import os, sys
from pathlib import Path
tools, home, ready, stop = sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
sys.path.insert(0, tools)
os.environ["R3HD_HOME"] = home
import tkinter as tk
import r3hd_level_editor as ed
lock = ed.hold_home_lock(home)
root = tk.Tk()
root.withdraw()
ed.EditorApp(root)
ready.write_text("held" if lock else "none", encoding="utf-8")
def poll():
    if stop.exists():
        root.destroy()
    else:
        root.after(200, poll)
root.after(200, poll)
root.mainloop()
ed.release_home_lock(lock)
'''


def wait(cond, seconds):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.5)
    return cond()


def remix_checks(label, home: Path, python: Path, out: Path, env):
    work = out / "work"
    work.mkdir(exist_ok=True)
    (out / "remix_probe.py").write_text(REMIX_PROBE, encoding="utf-8")
    code, text = g31.run([python, "-B", out / "remix_probe.py", home / "app" / "tools", home, work], env, cwd=out)
    pr = {}
    for ln in text.splitlines():
        if ln.startswith("REMIX "):
            pr = json.loads(ln[6:])
    row(f"{label}: remix probe ran on the package's own Python", code == 0
        and pr.get("prefix", "").lower() == str(home / "app" / "python").lower(), text[-800:])
    lv = pr.get("levels", {})
    for level in LEVELS:
        r = lv.get(level, {})
        row(f"{label}: {level} loads in remix mode (actors, graphs, collision)", r.get("loaded")
            and sum(r.get("actor_status", {}).values()) > 0, r.get("actor_status"))
        if "locked_refused" in r:
            row(f"{label}: {level} a LOCKED / script-overridden actor is refused", r["locked_refused"], r)
        row(f"{label}: {level} edits applied (presets {r.get('presets')}; snap to ground {r.get('snapped')})",
            (r.get("edits", {}).get("actors", 0) + r.get("edits", {}).get("waypoints", 0)) > 0
            and r.get("snapped") is not False, r)
        row(f"{label}: {level} remix project save / reopen identical", r.get("reopened_same"), r)
        row(f"{label}: {level} remix export + import/enable into HOME/mods", r.get("export") and r.get("import")
            and r.get("import_mods", "").lower() == str(home / "mods").lower(), r)
    row(f"{label}: Help names the Level Remix Editor, its three levels, EXPERIMENTAL items and the achievement rule",
        pr.get("scope_levels"))
    ids = {lv.get(level, {}).get("mod_id") for level in LEVELS} - {None}
    mods = home / "app" / "tools" / "r3hd_mods.py"
    code, text = g31.run([python, "-B", mods, "list", "--json", "--home", home], env, cwd=home)
    try:
        lst = json.loads(text[text.index("{"):])
    except ValueError:
        lst = {}
    got = {m["id"]: m for m in lst.get("mods", []) if m.get("id") in ids}
    row(f"{label}: every remix mod is listed enabled, active and marked as changing game logic",
        len(ids) == 3 and len(got) == 3 and all(m.get("enabled") and m.get("state") == "active" and m.get("gameplay")
                                                 for m in got.values()), {k: (v.get("state"), v.get("gameplay"))
                                                                          for k, v in got.items()})
    code, text = g31.run([python, "-B", mods, "plan", "--json", "--home", home], env, cwd=home)
    try:
        pl = json.loads(text[text.index("{"):])
        plan = Path(pl["plan"]).read_text(encoding="utf-8") if pl.get("plan") else ""
    except (ValueError, KeyError, OSError):
        pl, plan = {}, ""
    grec = {ln.split()[1] for ln in plan.splitlines() if ln.startswith("gameplay ")}
    row(f"{label}: launch plan names each remix mod in a gameplay record (no new achievements while active)",
        code == 0 and pl.get("result") == "ok" and ids <= grec, (sorted(grec), text[-300:]))
    code, text = g31.run([home / "app" / "r3hd_launcher.exe", "--play", "--dry-run", "--no-ui"], env, cwd=home,
                         timeout=600)
    row(f"{label}: Play (dry run) with the patch and the three remix mods active: preflight passes",
        code == 0 and "R3HD_LAUNCHER PLAY" in text and all(i in text for i in ids), text[-600:])
    return pr


def uninstall_lifecycle(home: Path, menu: Path, out: Path, env):
    # user data the uninstaller must keep (existing policy): settings, a profile save, history, a project, mods
    plant = {home / "profiles" / "g6p36" / "user" / "g6p36_test.sav": b"synthetic save\n",
             home / "save_history" / "g6p36" / "g6p36_test.sav": b"synthetic history\n",
             home / "g6p36_project.r3hdmap.json": b"{}\n"}
    for p, b in plant.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    settings_before = (home / "settings.json").read_bytes() if (home / "settings.json").is_file() else None
    unins = sorted(home.glob("unins*.exe"))
    pyw = home / "app" / "python" / "pythonw.exe"
    (out / "holder.py").write_text(HOLDER, encoding="utf-8")
    ready, stop = out / "holder.ready", out / "holder.stop"
    holder = subprocess.Popen([str(pyw), "-B", str(out / "holder.py"), str(home / "app" / "tools"), str(home),
                               str(ready), str(stop)], env=env, cwd=str(home),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    held = wait(lambda: ready.exists(), 300) and ready.read_text(encoding="utf-8") == "held"
    row("installer: the installed editor (pythonw.exe, root withdrawn) holds this installation's lock", held
        and holder.poll() is None and (home / "level_editor.lock").is_file())
    code, text = g31.run([unins[0], "/VERYSILENT", "/SUPPRESSMSGBOXES"], env, timeout=1800) if unins else (1, "none")
    time.sleep(30)  # the uninstaller copies itself to TEMP and returns at once; give a removal time to happen
    lnks = sorted(p.name for p in menu.rglob("*.lnk"))
    row("installer: uninstall while the editor runs is refused: app\\, shortcuts and data untouched; the editor keeps "
        "running", (home / "app" / "r3hd_launcher.exe").is_file() and pyw.is_file() and len(lnks) == 4
        and holder.poll() is None and all(p.read_bytes() == b for p, b in plant.items()), (lnks, text[-300:]))
    stop.write_text("stop", encoding="utf-8")
    try:
        holder.wait(timeout=120)
    except subprocess.TimeoutExpired:
        pass
    row("installer: the editor closes normally and releases its lock (the test never kills it)",
        holder.returncode == 0 and not (home / "level_editor.lock").exists(), holder.returncode)
    code, text = g31.run([unins[0], "/VERYSILENT", "/SUPPRESSMSGBOXES"], env, timeout=1800)
    wait(lambda: not (home / "app").exists(), 120)
    left = sorted(p.name for p in menu.rglob("*.lnk"))
    row("installer: clean uninstall after the editor closed removes app\\ and every shortcut",
        not (home / "app").exists() and not left, (left, text[-300:]))
    row("installer: user data kept (mods, profile save, save history, project, settings)",
        (home / "mods").is_dir() and any((home / "mods").iterdir()) and all(p.read_bytes() == b for p, b in plant.items())
        and (settings_before is None or (home / "settings.json").read_bytes() == settings_before))
    row("installer: nothing left in TEMP / APPDATA / LOCALAPPDATA except Inno Setup's own temp",
        not [p for p in g31.leftovers(out) if not p.startswith("temp")], g31.leftovers(out)[:20])


def installer(stage: Path, source: Path, out: Path):
    out.mkdir(parents=True)
    env = g31.sentinel_env(out)
    dist = out / "dist"
    code, text = g31.run([g31.ISCC, "/Q", f"/DPayloadDir={stage / 'payload'}", f"/DOutputDir={dist}", g31.ISS],
                         env, cwd=ROOT, timeout=3600)
    setups = list(dist.glob("*-setup.exe"))
    row("installer: setup compiled from the audited stage (ISCC, release compression)", code == 0 and len(setups) == 1,
        text[-500:])
    if not setups:
        return
    home, menu, desk = out / "home", out / "menu", out / "desktop"
    menu.mkdir()
    desk.mkdir()
    log = out / "setup.log"
    code, text = g31.run([setups[0], "/VERYSILENT", "/SUPPRESSMSGBOXES", "/R3HDTEST=1", f"/DIR={home}",
                          f"/PACKAGE={source}", f"/STARTMENUDIR={menu}", f"/DESKTOPDIR={desk}", f"/LOG={log}",
                          "/PRESET=vanilla"], env, timeout=3600)
    row("installer: silent test-mode install into a synthetic folder", code == 0
        and (home / "app" / "r3hd_launcher.exe").is_file(),
        (log.read_text(encoding="utf-8", errors="replace")[-600:] if log.exists() else text[-600:]))
    lnks = sorted(p.name for p in menu.rglob("*.lnk"))
    row("installer: Start menu has Play, Settings, Level Editor, Uninstall", g31.LNK in lnks and len(lnks) == 4, lnks)
    py = home / "app" / "python" / "python.exe"
    code, text = g31.run([py, "-B", home / "app" / "tools" / "r3hd_installer.py", "verify", "--home", home], env,
                         cwd=home)
    row("installer: engine verify of the installation (Tk runtime included)", code == 0, text[-400:])
    g31.common_checks("installer", home, home / "app" / "r3hd_launcher.exe", py, out, env)
    remix_checks("installer", home, py, out, env)
    uninstall_lifecycle(home, menu, out, env)


def portable(stage: Path, source: Path, out: Path, crt: Path):
    out.mkdir(parents=True)
    env = g31.sentinel_env(out)
    z = out / "g6p36-portable.zip"
    code, text = g31.run([sys.executable, g31.TOOLS / "r3hd_stage.py", "portable", stage, "--portable-out", z,
                          "--development-id", "g6p36", "--crt-dir", crt], dict(g31.os.environ), cwd=ROOT,
                         timeout=3600)
    row("portable: ZIP built and checked from the audited stage", code == 0 and z.is_file(), text[-500:])
    if not z.is_file():
        return
    code, text = g31.run([sys.executable, g31.TOOLS / "r3hd_portable_zip.py", "compare-stage", stage, z],
                         dict(g31.os.environ), cwd=g31.TOOLS)
    row("portable: ZIP shares every payload byte with the installer stage", code == 0 and '"PASS"' in text,
        text[-300:])
    with g31.zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
        cmd = zf.read(f"{g31.TOP}/Level Editor.cmd").decode() if f"{g31.TOP}/Level Editor.cmd" in names else ""
        zf.extractall(out / "x")
    row("portable: Level Editor.cmd runs the portable entry (r3hd_portable.py level-editor)",
        "r3hd_portable.py\" level-editor" in cmd, cmd)
    home = out / "x" / g31.TOP
    py = home / "app" / "python" / "python.exe"
    code, text = g31.run([py, "-B", home / "app" / "tools" / "r3hd_portable.py", "prepare", "--source", source,
                          "--no-input"], env, cwd=home, timeout=3600)
    row("portable: prepared from the owner's data with the ZIP's own Python",
        code == 0 and "R3HD_PORTABLE READY" in text, text[-500:])
    g31.common_checks("portable", home, home / "app" / "r3hd_launcher.exe", py, out, env)
    remix_checks("portable", home, py, out, env)
    row("portable: nothing written to TEMP / APPDATA / LOCALAPPDATA (only the extracted folder)",
        not g31.leftovers(out), g31.leftovers(out)[:20])
    g31.safe_rmtree(home)
    row("portable: removal = deleting the folder; nothing else remains", not home.exists() and not g31.leftovers(out))


def main(argv):
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
    installer(stage, source, out) if mode == "installer" else portable(stage, source, out, crt)
    ok = bool(rows) and all(r["ok"] for r in rows)
    (out / "result.json").write_text(json.dumps({"mode": mode, "pass": ok, "rows": rows}, indent=1) + "\n",
                                     encoding="utf-8")
    print(f"G6P36_{mode.upper()} {'PASS' if ok else 'FAIL'} {sum(r['ok'] for r in rows)}/{len(rows)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

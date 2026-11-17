#!/usr/bin/env python3
"""E-520 (D-287) G6-P31: packaged level-editor acceptance on the REAL release stage (installer and portable).

    g6p31_package_acceptance.py installer STAGE SOURCE OUT   compile the setup from STAGE (ISCC), install it silently in
                                                             test mode (/R3HDTEST=1: no registry entry, shortcuts only
                                                             in OUT), check the Level Editor shortcut, the launcher
                                                             entry (dry run), the editor workflow on the INSTALLED
                                                             runtime, the mod manager and a Play dry run, then
                                                             uninstall (test mode) and check what remains
    g6p31_package_acceptance.py portable STAGE SOURCE OUT CRT
                                                             build + check the portable ZIP from STAGE, extract it,
                                                             prepare it from SOURCE, then the same checks with the
                                                             ZIP's own runtime, writes outside the folder, removal

SOURCE (the owner's extracted game tree) is read only. OUT must not exist and stays private (copied game data). The
editor runs with its Tk root withdrawn (never shown); launcher actions are --dry-run --no-ui; nothing starts the game,
no window is shown, no input is sent. TEMP / TMP / APPDATA / LOCALAPPDATA of every child process point to OUT/sentinel
so that a write outside the package is visible. Prints rows and G6P31_<MODE> PASS|FAIL; OUT/result.json.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
ISCC = ROOT / "external" / "innosetup" / "ISCC.exe"
ISS = TOOLS / "installer" / "r3hd_setup.iss"
TX = "9083786df631a5a3"           # the G6-P30 production transaction of this project (run e519_m1_M)
TOP = "Rayman3HDRecompiled-Portable"
LNK = "Rayman 3 HD Recompiled - Level Editor.lnk"
rows = []

PROBE = r'''
import json, os, sys
from pathlib import Path
tools, home, work = sys.argv[1], sys.argv[2], Path(sys.argv[3])
sys.path.insert(0, tools)
os.environ["R3HD_HOME"] = home                       # exactly what r3hd_level_editor.main does with --home
import tkinter as tk
import r3hd_level_editor as ed
import r3hd_level_editor_core as core
out = {"python": sys.version.split()[0], "prefix": sys.prefix, "executable": sys.executable, "tk": tk.TkVersion,
       "tcl": None, "tkinter_from": tk.__file__, "editor_from": ed.__file__}
root = tk.Tk()
root.withdraw()
out["tcl"] = root.tk.eval("info patchlevel")
out["tcl_library"] = root.tk.eval("info library")
out["tk_library"] = root.tk.eval("set tk_library")
a = ed.EditorApp(root)
out["game_dir"] = str(a.game_dir)
a.canvas_w, a.canvas_h = 1000, 760
a.fit("supported"); a.redraw()
out["model_loaded"] = a.model is not None
out["items"] = len(a.canvas.find_all())
for v, dz in ((6, -0.2), (2, -0.15), (4, -0.15)):
    a.set_vertex_dz(v, dz)
a.set_meta("id", "g6p25.west-basin-fairy")
r = a.validate_now()
out["production"] = a.prod_var.get()
out["valid"] = bool(r and r["ok"])
out["tx"] = r["report"]["transaction"]["id"] if r and r["ok"] else (r or {}).get("code")
proj = work / "basin.r3hdmap.json"
core.save_project(a.project, proj)
out["reopened_same"] = core.load_project(proj) == a.project
e = a.export_mod(work / "mod")
out["export"] = e["ok"]
i = a.import_mod(work / "mod")
out["import"] = i["ok"]
out["import_mods"] = str(i.get("mods"))
# development-only content stays refused without the development variable (graph B)
dev = core.check_project(dict(core.load_project(proj), fairylight={"follow_graph_of": 1}))
dv = core.validate(dev, a.game_dir)
out["graph_b_status"] = list(core.production_status(dev))
out["graph_b_valid"] = dv["ok"]
out["graph_b_code"] = dv.get("code")
out["scope_text"] = "intro_20" in ed.SCOPE_TEXT and "Development-only" in ed.SCOPE_TEXT
root.destroy()
print("PROBE " + json.dumps(out))
'''


def row(name, ok, detail=""):
    rows.append({"check": name, "ok": bool(ok), "detail": str(detail)[:600]})
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "  (" + str(detail)[:600] + ")"), flush=True)


def safe_rmtree(path: Path):
    """Remove a tree without ever following a junction / symlink (a link is unlinked, not entered)."""
    if not path.exists():
        return
    for dirpath, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        keep = []
        for d in dirnames:
            p = Path(dirpath) / d
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                os.rmdir(p) if not stat.S_ISLNK(st.st_mode) else os.unlink(p)
            else:
                keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            p = Path(dirpath) / f
            os.chmod(p, stat.S_IWRITE)
    shutil.rmtree(path)


def sentinel_env(out: Path, extra=None):
    s = out / "sentinel"
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("R3HD_") and k.upper() not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")}
    for k, sub in (("TEMP", "temp"), ("TMP", "temp"), ("APPDATA", "appdata"), ("LOCALAPPDATA", "localappdata")):
        (s / sub).mkdir(parents=True, exist_ok=True)
        env[k] = str(s / sub)
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    env["PATH"] = os.pathsep.join([sysroot + r"\System32", sysroot, sysroot + r"\System32\WindowsPowerShell\v1.0"])
    env.update(extra or {})
    return env


def run(cmd, env, cwd=None, timeout=1800):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env, cwd=cwd, timeout=timeout,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def leftovers(out: Path):
    s = out / "sentinel"
    return sorted(str(p.relative_to(s)) for p in s.rglob("*") if p.is_file()) if s.exists() else []


def common_checks(label, home: Path, launcher: Path, python: Path, out: Path, env):
    """The editor workflow on the package's own runtime, the mod manager, launcher dry runs."""
    work = out / "work"
    work.mkdir(exist_ok=True)
    code, text = run([launcher, "--level-editor", "--dry-run", "--no-ui"], env, cwd=home)
    pyw = str(home / "app" / "python" / "pythonw.exe")
    row(f"{label}: launcher --level-editor (dry run) runs the package's pythonw.exe on the package's editor and home",
        code == 0 and "R3HD_LAUNCHER LEVEL_EDITOR DRY_RUN" in text and pyw.lower() in text.lower()
        and str(home / "app" / "tools" / "r3hd_level_editor.py").lower() in text.lower(), text[-400:])
    for n in ("pythonw.exe", "_tkinter.pyd", "tcl86t.dll", "tk86t.dll", "tcl/tcl8.6/init.tcl", "tcl/tk8.6/tk.tcl"):
        row(f"{label}: runtime file app/python/{n} present", (home / "app" / "python" / n).is_file())
    row(f"{label}: editor and compiler modules present", all((home / "app" / "tools" / n).is_file() for n in (
        "r3hd_level_editor.py", "r3hd_level_editor_core.py", "r3hd_mods.py")))
    (out / "probe.py").write_text(PROBE, encoding="utf-8")
    code, text = run([python, "-B", out / "probe.py", home / "app" / "tools", home, work], env, cwd=out)
    pr = {}
    for ln in text.splitlines():
        if ln.startswith("PROBE "):
            pr = json.loads(ln[6:])
    row(f"{label}: editor ran on the package's own Python / Tk (no system Python)",
        code == 0 and pr.get("prefix", "").lower() == str(home / "app" / "python").lower()
        and pr.get("tkinter_from", "").lower().startswith(str(home / "app" / "python").lower())
        and pr.get("editor_from", "").lower().startswith(str(home / "app" / "tools").lower()), text[-800:])
    tcl_root = str(home / "app" / "python" / "tcl").replace("\\", "/").lower()
    row(f"{label}: Tcl/Tk {pr.get('tcl')} loaded from the bundled tcl/ tree", str(pr.get("tcl", "")).startswith("8.6")
        and str(pr.get("tcl_library", "")).replace("\\", "/").lower().startswith(tcl_root)
        and str(pr.get("tk_library", "")).replace("\\", "/").lower().startswith(tcl_root),
        (pr.get("tcl_library"), pr.get("tk_library")))
    row(f"{label}: intro_20 loaded from the package home's data/content", pr.get("model_loaded")
        and pr.get("game_dir", "").lower() == str(home / "data" / "content").lower() and pr.get("items", 0) > 1000, pr)
    row(f"{label}: production edit validates without any variable (tx {TX}, PRODUCTION-SUPPORTED)",
        pr.get("valid") and pr.get("tx") == TX and "PRODUCTION-SUPPORTED" in pr.get("production", ""), pr)
    row(f"{label}: project save / reopen", pr.get("reopened_same"))
    row(f"{label}: export + import/enable through the mod manager into HOME/mods",
        pr.get("export") and pr.get("import") and pr.get("import_mods", "").lower() == str(home / "mods").lower(), pr)
    row(f"{label}: graph B stays DEVELOPMENT-ONLY and is refused", not pr.get("graph_b_valid")
        and (pr.get("graph_b_status") or [True])[0] is False, pr)
    row(f"{label}: editor states its scope (Help text)", pr.get("scope_text"))
    mods = home / "app" / "tools" / "r3hd_mods.py"
    code, text = run([python, "-B", mods, "list", "--json", "--home", home], env, cwd=home)
    try:
        lst = json.loads(text[text.index("{"):])
    except ValueError:
        lst = {}
    m = [x for x in lst.get("mods", []) if x.get("id") == "g6p25.west-basin-fairy"]
    row(f"{label}: mod manager lists the editor mod enabled and active", code == 0 and m and m[0].get("enabled")
        and m[0].get("state") == "active", text[-500:])
    code, text = run([python, "-B", mods, "plan", "--json", "--home", home], env, cwd=home)
    try:
        pl = json.loads(text[text.index("{"):])
        plan = Path(pl["plan"]).read_text(encoding="utf-8") if pl.get("plan") else ""
    except (ValueError, KeyError, OSError):
        pl, plan = {}, ""
    row(f"{label}: launch plan carries the production level transaction (level-tx 2 intro_20 ... {TX})",
        code == 0 and pl.get("result") == "ok" and any(ln.startswith("level-tx 2 intro_20") and TX in ln
                                                       for ln in plan.splitlines()), text[-500:])
    code, text = run([launcher, "--play", "--dry-run", "--no-ui"], env, cwd=home, timeout=600)
    row(f"{label}: Play (dry run) through the launcher: preflight passes and the mod is active",
        code == 0 and "R3HD_LAUNCHER PLAY" in text and "g6p25.west-basin-fairy" in text, text[-600:])
    return pr


def installer(stage: Path, source: Path, out: Path):
    out.mkdir(parents=True)
    env = sentinel_env(out)
    dist = out / "dist"
    code, text = run([ISCC, "/Q", f"/DPayloadDir={stage / 'payload'}", f"/DOutputDir={dist}", "/DFastCompression", ISS],
                     env, cwd=ROOT, timeout=3600)
    setups = list(dist.glob("*-setup.exe"))
    row("installer: setup compiled from the audited stage (ISCC)", code == 0 and len(setups) == 1, text[-500:])
    if not setups:
        return
    home, menu, desk = out / "home", out / "menu", out / "desktop"
    menu.mkdir()
    desk.mkdir()
    log = out / "setup.log"
    code, text = run([setups[0], "/VERYSILENT", "/SUPPRESSMSGBOXES", "/R3HDTEST=1", f"/DIR={home}", f"/PACKAGE={source}",
                      f"/STARTMENUDIR={menu}", f"/DESKTOPDIR={desk}", f"/LOG={log}", "/PRESET=vanilla"], env,
                     timeout=3600)
    row("installer: silent test-mode install into a synthetic folder", code == 0 and (home / "app" / "r3hd_launcher.exe")
        .is_file(), (log.read_text(encoding="utf-8", errors="replace")[-600:] if log.exists() else text[-600:]))
    lnks = sorted(p.name for p in menu.rglob("*.lnk"))
    row("installer: Start menu has Play, Settings, Level Editor, Uninstall", LNK in lnks and len(lnks) == 4, lnks)
    if LNK in lnks:
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');$s.TargetPath+'|'+$s.Arguments+'|'+"
              "$s.WorkingDirectory" % str(next(menu.rglob(LNK))).replace("'", "''"))
        code, text = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env)
        tgt, args, wd = (text.strip().split("|") + ["", "", ""])[:3]
        row("installer: Level Editor shortcut = app\\r3hd_launcher.exe --level-editor in the installation",
            tgt.lower() == str(home / "app" / "r3hd_launcher.exe").lower() and args == "--level-editor"
            and wd.lower() == str(home).lower(), text)
    py = home / "app" / "python" / "python.exe"
    code, text = run([py, "-B", home / "app" / "tools" / "r3hd_installer.py", "verify", "--home", home], env, cwd=home)
    row("installer: engine verify of the installation (Tk runtime included)", code == 0, text[-400:])
    common_checks("installer", home, home / "app" / "r3hd_launcher.exe", py, out, env)
    unins = sorted(home.glob("unins*.exe"))
    code, text = run([unins[0], "/VERYSILENT", "/SUPPRESSMSGBOXES"], env, timeout=1800) if unins else (1, "no uninstaller")
    # the uninstaller copies itself to TEMP and returns at once; wait for the removal to finish
    for _ in range(240):
        if not (home / "app").exists():
            break
        subprocess.run(["powershell", "-NoProfile", "-Command", "Start-Sleep -Milliseconds 500"], env=env)
    left = sorted(p.name for p in menu.rglob("*.lnk"))
    row("installer: uninstall removes app\\ and every shortcut, keeps the person's mods (existing policy)",
        not (home / "app").exists() and not left and (home / "mods").is_dir(), (left, text[-300:]))
    row("installer: nothing left in TEMP / APPDATA / LOCALAPPDATA after setup, editor and uninstall",
        not [p for p in leftovers(out) if not p.startswith("temp")], leftovers(out)[:20])


def portable(stage: Path, source: Path, out: Path, crt: Path):
    out.mkdir(parents=True)
    env = sentinel_env(out)
    z = out / "g6p31-portable.zip"
    code, text = run([sys.executable, TOOLS / "r3hd_stage.py", "portable", stage, "--portable-out", z,
                      "--development-id", "g6p31", "--crt-dir", crt], dict(os.environ), cwd=ROOT, timeout=3600)
    row("portable: ZIP built and checked from the audited stage", code == 0 and z.is_file(), text[-500:])
    if not z.is_file():
        return
    code, text = run([sys.executable, TOOLS / "r3hd_portable_zip.py", "compare-stage", stage, z], dict(os.environ),
                     cwd=TOOLS)
    row("portable: ZIP shares every payload byte with the installer stage", code == 0 and '"PASS"' in text, text[-300:])
    with zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
        cmd = zf.read(f"{TOP}/Level Editor.cmd").decode() if f"{TOP}/Level Editor.cmd" in names else ""
        zf.extractall(out / "x")
    row("portable: Level Editor.cmd runs the portable entry (r3hd_portable.py level-editor)",
        "r3hd_portable.py\" level-editor" in cmd, cmd)
    home = out / "x" / TOP
    py = home / "app" / "python" / "python.exe"
    code, text = run([py, "-B", home / "app" / "tools" / "r3hd_portable.py", "prepare", "--source", source,
                      "--no-input"], env, cwd=home, timeout=3600)
    row("portable: prepared from the owner's data with the ZIP's own Python", code == 0 and "R3HD_PORTABLE READY" in text,
        text[-500:])
    common_checks("portable", home, home / "app" / "r3hd_launcher.exe", py, out, env)
    row("portable: nothing written to TEMP / APPDATA / LOCALAPPDATA (only the extracted folder)", not leftovers(out),
        leftovers(out)[:20])
    safe_rmtree(home)
    row("portable: removal = deleting the folder; nothing else remains", not home.exists() and not leftovers(out))


def payload_negative(stage: Path, out: Path):
    """The payload audit on the real stage, then on copies with one defect each (Tk runtime pins)."""
    sys.path.insert(0, str(TOOLS))
    import r3hd_release_audit as audit
    allow, binaries, pins = audit.load_payload_rules(audit.DEFAULT_PAYLOAD_ALLOWLIST, audit.DEFAULT_PAYLOAD_DEF)
    hashes = audit.GameHashes([audit.DEFAULT_MANIFEST], audit.DEFAULT_RELEASES)

    def codes(d):
        res = audit.audit_payload(str(d), allow, binaries, pins, hashes)
        return res["verdict"], {(r["path"], x["code"]) for r in res["results"] for x in r["reasons"]}

    v, c = codes(stage / "payload")
    row("payload audit: the real stage passes (Tk runtime pinned file by file)", v == "PASS" and not c, sorted(c)[:5])
    row("payload audit: every python_tk.json member is pinned", all(
        k in pins for k in json.loads((ROOT / "config/release/python_tk.json").read_text(encoding="utf-8"))["files"]))
    out.mkdir(parents=True)
    cases = {
        "tcl_tampered": lambda p: (p / "app/python/tcl/tk8.6/tk.tcl").write_bytes(
            (p / "app/python/tcl/tk8.6/tk.tcl").read_bytes() + b"\n# x\n"),
        "tcl_extra": lambda p: (p / "app/python/tcl/tk8.6/extra.tcl").write_bytes(b"# not pinned\n"),
        "pyd_replaced": lambda p: (p / "app/python/_tkinter.pyd").write_bytes(
            (p / "app/python/python3.dll").read_bytes()),
        "dll_extra": lambda p: (p / "app/python/tcl/dde14.dll").write_bytes(b"MZ" + bytes(200)),
    }
    expect = {"tcl_tampered": ("app/python/tcl/tk8.6/tk.tcl", "PIN_MISMATCH"),
              "tcl_extra": ("app/python/tcl/tk8.6/extra.tcl", "UNPINNED_RUNTIME_FILE"),
              "pyd_replaced": ("app/python/_tkinter.pyd", "PIN_MISMATCH"),
              "dll_extra": ("app/python/tcl/dde14.dll", "BINARY_MAGIC_PE")}
    for name, mutate in cases.items():
        d = out / name
        shutil.copytree(stage / "payload", d)
        mutate(d)
        v, c = codes(d)
        row(f"payload audit refuses {name}", v == "FAIL" and expect[name] in c, sorted(c)[:6])
        safe_rmtree(d)


def main(argv):
    mode = argv[0] if argv else ""
    if mode == "payload-neg" and len(argv) == 3:
        stage, out = Path(argv[1]).resolve(), Path(argv[2]).resolve()
        if out.exists():
            raise SystemExit(f"{out} exists")
        payload_negative(stage, out)
        ok = rows and all(r["ok"] for r in rows)
        (out / "result.json").write_text(json.dumps({"mode": mode, "pass": bool(ok), "rows": rows}, indent=1) + "\n",
                                         encoding="utf-8")
        print(f"G6P31_PAYLOAD_NEG {'PASS' if ok else 'FAIL'} {sum(r['ok'] for r in rows)}/{len(rows)}")
        return 0 if ok else 1
    if mode == "installer" and len(argv) == 4:
        stage, source, out = map(lambda s: Path(s).resolve(), argv[1:])
    elif mode == "portable" and len(argv) == 5:
        stage, source, out, crt = map(lambda s: Path(s).resolve(), argv[1:])
    else:
        raise SystemExit(__doc__)
    if out.exists():
        raise SystemExit(f"{out} exists")
    if not out.is_relative_to((ROOT / "private" / "work").resolve()):
        raise SystemExit("OUT must be under private/work")
    if mode == "installer":
        installer(stage, source, out)
    else:
        portable(stage, source, out, crt)
    ok = rows and all(r["ok"] for r in rows)
    (out / "result.json").write_text(json.dumps({"mode": mode, "pass": bool(ok), "rows": rows}, indent=1) + "\n",
                                     encoding="utf-8")
    print(f"G6P31_{mode.upper()} {'PASS' if ok else 'FAIL'} {sum(r['ok'] for r in rows)}/{len(rows)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

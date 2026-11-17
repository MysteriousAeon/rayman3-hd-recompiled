#!/usr/bin/env python3
"""E-519 (D-286) G6-P30: reproducible Tk staging proof for the packaged (embeddable-layout) CPython 3.11.4.

    g6p30_tk_stage.py check   stage private/work/e519/tkstage/app exactly as tools/r3hd_stage.py stages app/python
                              (pinned files of config/release/payload.json, the stdlib zip built from the same local
                              official CPython 3.11.4) PLUS the Tk runtime of that same official build: tkinter kept in
                              the stdlib zip, DLLs/_tkinter.pyd, tcl86t.dll, tk86t.dll (Authenticode: Python Software
                              Foundation) and tcl/tcl8.6, tcl/tk8.6, tcl/tcl8; copy the editor and the mod tool to
                              app/tools; then run, with the STAGED python.exe only (no local Python on the path), the
                              editor with its root withdrawn (never shown): load intro_20, edit, validate (production
                              policy, no development variable), export, SVG; prints sizes / hashes and TK_STAGE PASS.
Nothing here changes the release stage or any package; it is the evidence for the packaging plan.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_stage as stage  # noqa: E402
import r3hd_mods as rm  # noqa: E402

ROOT = rm.ROOT
OUT = ROOT / "private" / "work" / "e519" / "tkstage"
PAYLOAD = ROOT / "config" / "release" / "payload.json"
TK_FILES = ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll")
TCL_DIRS = ("tcl8.6", "tk8.6", "tcl8")

PROBE = r'''
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
os.environ.pop("R3HD_DEV_STRUCTURAL_TX", None)
import tkinter as tk
import r3hd_level_editor as ed
import r3hd_level_editor_core as core
out = {"python": sys.version.split()[0], "prefix": sys.prefix, "tk": tk.TkVersion,
       "tkinter_from": tk.__file__}
root = tk.Tk()
root.withdraw()
a = ed.EditorApp(root, sys.argv[2])
a.canvas_w, a.canvas_h = 1000, 760
a.fit("supported"); a.redraw()
a.set_vertex_dz(6, -0.2); a.set_vertex_dz(2, -0.15); a.set_vertex_dz(4, -0.15)
a.set_meta("id", "g6p25.west-basin-fairy")
r = a.validate_now()
d = Path(sys.argv[3])
e = a.export_mod(d / "mod")
a.export_svg(d / "view.svg")
out.update({"model_loaded": a.model is not None, "picks": len(a.picks), "items": len(a.canvas.find_all()),
            "production": a.prod_var.get(), "valid": r["ok"],
            "tx": r["report"]["transaction"]["id"] if r["ok"] else r.get("detail"),
            "export": e["ok"], "mod_json": (d / "mod" / "mod.json").is_file()})
root.destroy()
print(json.dumps(out))
'''


def check():
    if OUT.exists():
        shutil.rmtree(OUT)
    py_src = Path(sys.base_prefix)
    defn = json.loads(PAYLOAD.read_text(encoding="utf-8"))["python"]
    app = OUT / "app"
    pyd = app / "python"
    pyd.mkdir(parents=True)
    res = {"source": str(py_src)}
    for name, pin in defn["files"].items():   # the release stage's pinned files, verified the same way
        data = (py_src / name).read_bytes()
        if name != "LICENSE.txt" and rm.sha256_bytes(data) != pin:
            raise SystemExit(f"{name} is not the pinned CPython {defn['version']} file")
        (pyd / name).write_bytes(data)
    base = stage.stdlib_zip(py_src, defn["stdlib_exclude"])
    res["stdlib_zip_matches_release_pin"] = rm.sha256_bytes(base) == defn["stdlib_zip_sha256"]
    z = stage.stdlib_zip(py_src, [x for x in defn["stdlib_exclude"] if x != "tkinter"])
    (pyd / "python311.zip").write_bytes(z)
    (pyd / "python311._pth").write_bytes(b"python311.zip\n.\n")
    res["stdlib_zip_with_tkinter"] = {"bytes": len(z), "sha256": rm.sha256_bytes(z), "added_bytes": len(z) - len(base)}
    files = {}
    for n in TK_FILES:
        shutil.copyfile(py_src / "DLLs" / n, pyd / n)
        files[n] = {"bytes": (pyd / n).stat().st_size, "sha256": rm.sha256_bytes((pyd / n).read_bytes())}
    tsize = 0
    for d in TCL_DIRS:
        shutil.copytree(py_src / "tcl" / d, pyd / "tcl" / d)
        tsize += sum(p.stat().st_size for p in (pyd / "tcl" / d).rglob("*") if p.is_file())
    res["tk_files"], res["tcl_tree_bytes"] = files, tsize
    sig = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-AuthenticodeSignature " + ",".join(f"'{pyd / n}'" for n in TK_FILES)
                          + " | ForEach-Object { $_.Status.ToString() + ' ' + $_.SignerCertificate.Subject }"],
                         capture_output=True, text=True).stdout.split("\n")
    res["signatures"] = [s.strip() for s in sig if s.strip()]
    tools = app / "tools"
    tools.mkdir()
    for n in ("r3hd_mods.py", "r3hd_level_editor.py", "r3hd_level_editor_core.py"):
        shutil.copyfile(ROOT / "tools" / n, tools / n)
    (app / "config" / "intake").mkdir(parents=True)   # as payload.json stages it (app/config/intake)
    shutil.copyfile(ROOT / "config" / "intake" / "known_releases.json", app / "config" / "intake" / "known_releases.json")
    (OUT / "probe.py").write_text(PROBE, encoding="utf-8")
    run = OUT / "run"
    run.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", rm.STRUCT_ENV)}
    env["PATH"] = os.pathsep.join([str(pyd), os.environ.get("SystemRoot", r"C:\Windows") + r"\System32"])
    p = subprocess.run([str(pyd / "python.exe"), "-B", str(OUT / "probe.py"), str(tools),
                        str(ROOT / "private" / "extracted" / rm.TITLE_ID), str(run)],
                       capture_output=True, text=True, env=env, cwd=str(OUT), timeout=600)
    try:
        res["probe"] = json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        res["probe"] = {"error": p.stderr[-1500:]}
    pr = res["probe"]
    res["pass"] = bool(pr.get("prefix", "").lower().startswith(str(pyd).lower()) and pr.get("model_loaded")
                       and pr.get("valid") and pr.get("tx") == "9083786df631a5a3" and pr.get("export")
                       and pr.get("mod_json") and "PRODUCTION-SUPPORTED" in pr.get("production", "")
                       and all(s.startswith("Valid") and "Python Software Foundation" in s for s in res["signatures"])
                       and len(res["signatures"]) == 3)
    (OUT / "result.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))
    print("TK_STAGE", "PASS" if res["pass"] else "FAIL")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        sys.exit(check())
    raise SystemExit(__doc__)

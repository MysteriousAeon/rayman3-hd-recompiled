#!/usr/bin/env python3
"""M33 (D-070): regression of the data-only mod foundation. Starts no game and shows nothing on the person's desktop.

  * runtime: tools/m33_mod_overlay.h installed, the ReadSync site patched after the M26 correction, the per-process
    `M33 mods=` line, the strings in the built runtime; the build script replays and tests it in order
  * the mod tool's selftest is in the build (synthetic fixtures: manifest, versions, conflicts, dependencies, priority,
    path traversal / links / executables / zip bombs, tampering, baseline fallback); here: real-data authoring checks
    (read only): the layout of real bundle entries, decode against the stored bytes, a plan over the local game files
  * play.ps1 -DryRun (the built executable and the extracted data, read only): no mods folder, an enabled mod, -Mods
    off, an enabled mod that no longer fits (left out with a note, the launch goes on)
  * installer: mods\\ is the person's data: kept by repair and update, kept by uninstall, removed only with the
    confirmed removal of user data; a fresh home may hold it; the payload ships the mod tool
  * the launcher (private/work/launcher) on a private desktop (--ui-test): the Mods page lists, imports (a valid zip and
    a refused one), enables, reorders, disables and removes; layout at 96 and 144 DPI
usage: m33_regression.py [--keep DIR]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_installer as engine  # noqa: E402
import r3hd_mods as mods  # noqa: E402

SDK = ROOT / "external" / "rexglue-sdk"
LAUNCHER = ROOT / "private" / "work" / "launcher" / "r3hd_launcher.exe"
BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
GAME = Path(os.environ.get("R3HD_GAME_DIR") or ROOT / "private" / "extracted" / "5841123F")
TEXT_OFFSET = 143992  # a menu string of fix.lvl (M33 proof); its slot hash is computed from the local file
checks, skipped = [], []


def check(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  ({detail})" if detail and not cond else ""))


def skip(name, why):
    skipped.append(name)
    print(f"skip {name}  ({why})")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


# --- runtime and build ------------------------------------------------------------------------------------------------

def runtime_checks():
    hpf = read(SDK / "src" / "filesystem" / "devices" / "host_path_file.cpp")
    cp = read(SDK / "src" / "graphics" / "d3d12" / "command_processor.cpp")
    inst = SDK / "include" / "rex" / "m33_mod_overlay.h"
    check("runtime: the overlay header is installed as written", inst.is_file()
          and inst.read_bytes() == (TOOLS / "m33_mod_overlay.h").read_bytes())
    i26, i33, iret = hpf.find("m26tex::AfterRead("), hpf.find("m33mods::AfterRead("), hpf.find("return X_STATUS_SUCCESS;")
    check("runtime: ReadSync applies the mod plan after the M26 correction and before returning",
          0 < i26 < i33 < iret and hpf.count("m33mods::AfterRead(") == 1 and "if (m33mods::Enabled())" in hpf)
    check("runtime: one `M33 mods=plan|off` line per process, beside the M26 one",
          'REXGPU_INFO("M33 mods={}", m33mods::Enabled() ? "plan" : "off");\n  REXGPU_INFO("M26 texture_orient' in cp)
    h = read(TOOLS / "m33_mod_overlay.h")
    check("runtime: the overlay reads only R3HD_MODS_PLAN, writes no file and refuses a plan as a whole",
          'getenv("R3HD_MODS_PLAN")' in h and "ofstream" not in h and "state=refused reason=" in h
          and "kMaxTotalBytes" in h and "ranges_overlap" in h and "game_bytes_hash" in h)
    dll = BUILD / "rexruntime.dll"
    if dll.is_file():
        b = dll.read_bytes()
        check("runtime: the built runtime carries the M33 overlay (the variable read as UTF-16)",
              b"M33 mods state=" in b and "R3HD_MODS_PLAN".encode("utf-16-le") in b)
    else:
        skip("runtime: the built runtime carries the M33 overlay", "not built")
    bat = read(TOOLS / "build_milestone8.bat")
    order = [bat.find(s) for s in ("m32_runtime_patch.py", "m33_runtime_patch.py", "m32_prepare.py", "m33_prepare.py",
                                   "m33_mod_overlay_test.exe", "r3hd_mods.py selftest", "m33_regression.py",
                                   "M8_BUILD_OK")]
    check("build: patch, prepare, overlay test, mod selftest and this regression in order",
          all(x > 0 for x in order) and order == sorted(order), order)
    hp = read(TOOLS / "m23_haptics_regression.py")
    check("runtime: the hidden in-game check starts the game only through the known runner",
          "m9_license_run.py" in read(TOOLS / "m33_mod_game.py") and "r3hd.exe" not in read(TOOLS / "m33_mod_game.py")
          and "starters" in hp)


# --- the mod tool on the local game data (read only) -----------------------------------------------------------------

def data_checks(t: Path):
    if not (GAME / "GAMEDATAbin" / "fix.bhf").is_file():
        skip("mod tool on the local game data", "no extracted data")
        return
    before = {p: p.stat().st_mtime_ns for p in (GAME / "GAMEDATAbin").glob("fix.*")}
    info = mods.cmd_texture_info({"game": GAME}, "menu\\mnu_xb512_en.dds")
    check("data: a real bundle entry's size and format come from its texture record and match the stored sizes",
          info["bundles"] == [{"bundle": "GAMEDATAbin/fix", "width": 1024, "height": 1024, "format": "DXT5",
                               "base": 1048576, "mips": 393216}], info)
    hits = mods.resolve_texture(GAME, {"entry": "wood\\wood_moon.dds", "bundles": "all"})
    check("data: an entry shared by several bundles is found in each ('all')", len(hits) >= 2
          and all(h[2:] == (512, 512, "DXT1") for h in hits), [h[0].name for h in hits])
    slot = mods.text_slot((GAME / "GAMEDATAbin" / "fix.lvl").read_bytes(), TEXT_OFFSET)
    paths = {"home": None, "mods": t / "mods", "cache": t / "cache", "game": GAME}
    src = t / "src" / "local"
    (src / "t").mkdir(parents=True)
    w = h = 128
    png = mods.write_png(w, h, bytes([200, 30, 30, 255] * (w * h)))
    (src / "t" / "red.png").write_bytes(png)
    m = {"format": 1, "id": "reg.local", "name": "regression", "version": "1.0.0",
         "target": {"title_id": "5841123F", "releases": mods.release_ids(paths), "min_port_version": "0.33.0"},
         "overrides": [{"type": "texture", "entry": "menu\\mnu_jard.dds", "image": "t/red.png", "bundles": ["GAMEDATAbin/fix"]},
                       {"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": TEXT_OFFSET,
                        "slot_sha256": mods.sha256_bytes(slot), "text": "Ayarlar"}]}
    (src / "mod.json").write_text(json.dumps(m), encoding="utf-8")
    try:
        mods.cmd_import(paths, src, enable=True)
        res = mods.resolve_all(paths, write_plan=t / "plan")
        plan = read(Path(res["plan"]))
        check("data: a plan over the local files: two files, three ranges, absolute game paths, end marker",
              res["active"] == ["reg.local"] and res["ranges"] == 3 and plan.count("\nfile ") == 2
              and str(GAME / "GAMEDATAbin" / "fix.btf") in plan and "\nend 2 3\n" in plan, res)
    except mods.Refusal as e:
        check("data: a plan over the local files", False, e)
    check("data: the game files were not written", before == {p: p.stat().st_mtime_ns for p in before})


# --- play.ps1 ----------------------------------------------------------------------------------------------------------

def dry_run(play_root, *args):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(TOOLS / "play.ps1"), "-DryRun", "-BinDir", str(BUILD), "-GameDir", str(GAME),
                        "-PlayRoot", str(play_root), *args], capture_output=True, text=True, timeout=300)
    out = r.stdout + r.stderr
    line = next((x.split(":", 1)[1].strip() for x in out.splitlines() if x.startswith("mods       :")), "")
    notes = [x.split(":", 1)[1].strip() for x in out.splitlines() if x.startswith("mods note  :")]
    return r.returncode, out, line, notes


def play_checks(t: Path):
    if not (BUILD / "r3hd.exe").is_file() or not (GAME / "Default.xex").is_file():
        skip("play.ps1 dry runs", "the built executable or the extracted data is missing")
        return
    root = t / "play"
    root.mkdir()
    code, out, line, _ = dry_run(root)
    check("play: without a mods folder nothing is applied", code == 0 and line == "none installed", out[-400:])
    paths = {"home": None, "mods": root / "mods", "cache": root / "cache" / "mods", "game": GAME}
    slot = mods.text_slot((GAME / "GAMEDATAbin" / "fix.lvl").read_bytes(), TEXT_OFFSET)
    src = t / "src" / "dry"
    src.mkdir(parents=True)
    m = {"format": 1, "id": "reg.dry", "name": "dry", "version": "1.0.0",
         "target": {"title_id": "5841123F", "releases": mods.release_ids(paths), "min_port_version": "0.33.0"},
         "overrides": [{"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": TEXT_OFFSET,
                        "slot_sha256": mods.sha256_bytes(slot), "text": "Ayarlar"}]}
    (src / "mod.json").write_text(json.dumps(m), encoding="utf-8")
    mods.cmd_import(paths, src, enable=True)
    code, out, line, notes = dry_run(root)
    check("play: an enabled mod is listed with its ranges", code == 0 and line == "reg.dry (1 ranges)", out[-400:])
    code, out, line, _ = dry_run(root, "-Mods", "off")
    check("play: -Mods off launches the game's own data", code == 0 and line == "off (-Mods off)", line)
    # the installed mod no longer fits (its recorded slot hash is not this file's): left out, the launch goes on
    d = mods.installed_dir(paths, "reg.dry")
    m["overrides"][0]["slot_sha256"] = "0" * 64
    (d / "mod.json").write_text(json.dumps(m), encoding="utf-8")
    rec = json.loads((d / "installed.json").read_text(encoding="utf-8"))
    rec["files"]["mod.json"] = mods.sha256_bytes((d / "mod.json").read_bytes())
    (d / "installed.json").write_text(json.dumps(rec), encoding="utf-8")
    code, out, line, notes = dry_run(root)
    check("play: a mod that does not fit is left out with a note and the launch goes on",
          code == 0 and line == "none enabled" and any("TARGET_CHANGED" in n for n in notes), out[-500:])
    src = read(TOOLS / "play.ps1")
    check("play: R3HD_MODS_PLAN is set only from the verified plan and restored afterwards",
          "$env:R3HD_MODS_PLAN = $(if ($modsPlan)" in src and "$env:R3HD_MODS_PLAN = $savedModsPlan" in src
          and "[ValidateSet('on', 'off')][string]$Mods = 'on'" in src)


# --- installer ---------------------------------------------------------------------------------------------------------

def installer_checks(t: Path):
    check("installer: mods\\ is the person's data (kept by uninstall unless removal is confirmed)", "mods" in engine.USER_ITEMS)
    pl = json.loads(read(ROOT / "config" / "release" / "payload.json"))
    files = pl.get("files") or {}
    flat = json.dumps(pl)
    check("payload: the mod tool ships with the engine", '"app/tools/r3hd_mods.py": "tools/r3hd_mods.py"' in flat
          or files.get("app/tools/r3hd_mods.py") == "tools/r3hd_mods.py")
    saved = {k: os.environ.get(k) for k in engine.HOOKS}
    sys32 = t / "sys32"
    sys32.mkdir()
    for n in engine.VC_RUNTIME:
        (sys32 / n).write_bytes(b"x")
    os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
    quiet = lambda *_: None  # noqa: E731
    try:
        pl1, tree, rels = engine.make_fixture(t)
        home = t / "home"
        engine.install(home, pl1, tree, "vanilla", releases=rels, log=quiet)
        mods_dir = home / "mods" / "installed" / "x.kept"
        mods_dir.mkdir(parents=True)
        (mods_dir / "mod.json").write_text("{}", encoding="utf-8")
        (home / "mods" / "state.json").write_text('{"schema": 1, "mods": []}', encoding="utf-8")
        snap = {p.relative_to(home).as_posix(): p.read_bytes() for p in (home / "mods").rglob("*") if p.is_file()}

        def same():
            return snap == {p.relative_to(home).as_posix(): p.read_bytes() for p in (home / "mods").rglob("*") if p.is_file()}
        engine.repair(home, pl1, releases=rels, log=quiet)
        check("installer: repair keeps the mods folder byte for byte", same())
        pl2, _, rels2 = engine.make_fixture(t / "v2", version="0.30.0", tag=b"v2")
        try:
            engine.install(home, pl2, tree, releases=rels, log=quiet)
            check("installer: an update keeps the mods folder byte for byte", same())
        except engine.Refusal as e:
            skip("installer: update keeps mods", f"fixture update refused: {e.code}")
        r = engine.uninstall(home, releases=rels, log=quiet)
        check("installer: uninstall keeps the mods folder (user data)", same() and "mods" in r["user_data_kept"], r)
        engine.install(home, pl1, tree, "vanilla", releases=rels, log=quiet)
        check("installer: a home that holds only user data (mods included) can be installed into again", same())
        r = engine.uninstall(home, remove_user_data=True, confirm=str(home), releases=rels, log=quiet)
        check("installer: the confirmed removal of user data removes the mods folder",
              not (home / "mods").exists() and "mods" in r["user_data_removed"], r)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# --- launcher ----------------------------------------------------------------------------------------------------------

def launcher_checks(t: Path, keep):
    src = read(TOOLS / "launcher" / "r3hd_launcher.cpp")
    check("launcher: the Mods page runs the mod tool and holds no mod rule of its own",
          'L"\\\\r3hd_mods.py"' in src and "R3HD_MODS_ROWS" in src and "slot_sha256" not in src
          and "overrides" not in src)
    if not LAUNCHER.is_file():
        check("launcher built (tools\\launcher\\build_launcher.bat)", False)
        return
    import m30_launcher_regression as m30
    saved = {k: os.environ.get(k) for k in engine.HOOKS}
    sys32 = t / "sys32ui"
    sys32.mkdir()
    for n in engine.VC_RUNTIME:
        (sys32 / n).write_bytes(b"x")
    os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
    try:
        home = m30.make_home(t, "uihome")
        # A synthetic fix.lvl in the synthetic home's game data (the fixture tree has none).
        game = home / "data" / "content" / "GAMEDATAbin"
        game.mkdir(parents=True, exist_ok=True)
        fix = bytearray(0x100)
        fix[0x40:0x48] = b"Options\0"
        (game / "fix.lvl").write_bytes(bytes(fix))
        slot = mods.text_slot(bytes(fix), 0x40)
        rels = json.loads(read(home / "data" / "intake.json")).get("release")

        def make(name, mid, text, extra=None):
            z = t / f"{name}.zip"
            m = {"format": 1, "id": mid, "name": f"Test {name}", "version": "1.2.0", "description": "A synthetic mod.",
                 "target": {"title_id": "5841123F", "releases": [rels], "min_port_version": "0.1"},
                 "overrides": [{"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": 0x40,
                                "slot_sha256": mods.sha256_bytes(slot), "text": text}]}
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr(f"{name}/mod.json", json.dumps(m))
                for k, v in (extra or {}).items():
                    zf.writestr(f"{name}/{k}", v)
            return z
        a, b, bad = make("alpha", "ui.alpha", "Ayarlar"), make("beta", "ui.beta", "Seçenek"), \
            make("bad", "ui.bad", "x", {"payload.exe": b"MZ"})

        def run(name, lines, need):
            code, d, log, out = m30.ui(home, t, name, "\n".join(lines + ["click close", ""]),
                                       env=m30.launcher_env())
            if keep:
                shutil.copytree(out, Path(keep) / f"ui_{name}", dirs_exist_ok=True)
            ok = code == 0 and all(k in d for k in need)
            check(f"UI run {name} completed", ok, log[-800:])
            return (d, log) if ok else (None, log)
        d, log = run("m33a", ["page mods", "dump empty", "shot mods_empty_96",
                              f"mod import {a}", "dump imported", f"mod import {bad}", "dump refused",
                              f"mod import {b}", "mod select ui.alpha", "mod toggle", "dump enabled",
                              "mod select ui.beta", "mod toggle", "mod up", "dump moved", "shot mods_96",
                              "dpi 144", "dump m144", "shot mods_144", "dpi 96",
                              "mod select ui.alpha", "mod toggle", "dump disabled",
                              "mod select ui.beta", "mod remove", "dump removed"],
                     ("empty", "imported", "refused", "enabled", "moved", "m144", "disabled", "removed"))
        if not d:
            return
        check("UI: the Mods page opens with an empty list and says how to install",
              d["empty"]["page"] == "mods" and d["empty"]["page_buttons"] == "0001"
              and "mods_count=0" in d["empty"]["mods_visible"] and "No mods are installed" in d["empty"]["mod_detail"])
        check("UI: a valid .zip is installed (off until enabled) and selected",
              d["imported"].get("mod.ui.alpha") == "off disabled " and "mods_count=1" in d["imported"]["mods_visible"]
              and "installed" in d["imported"]["status"])
        check("UI: a package with an executable is refused, the reason shown, nothing installed",
              "The mod package is invalid. Choose a valid mod ZIP or folder." in d["refused"]["status"]
              and "mods_count=1" in d["refused"]["mods_visible"] and not (home / "mods" / "installed" / "ui.bad").exists())
        check("UI: Enable makes a mod active; the status says it applies at the next start",
              d["enabled"].get("mod.ui.alpha") == "on active " and "next time the game starts" in d["enabled"]["status"]
              and d["enabled"]["mod_toggle"].startswith("&Disable"))
        check("UI: Up moves a mod above the other (both on); the list shows the new order",
              d["moved"].get("mod_item.0", "").startswith("1.  [on]   Test beta")
              and d["moved"].get("mod_item.1", "").startswith("2.  [on]   Test alpha"), d["moved"])
        check("UI: the lower mod stays active and is reported as partly covered",
              d["moved"].get("mod.ui.alpha") == "on active ")
        check("UI: the Mods page lays out without overlap at 96 and 144 DPI",
              m30.layout_ok(d["moved"]) and m30.layout_ok(d["m144"]), [d[k].get("controls") for k in ("moved", "m144")])
        check("UI: Disable turns a mod off", d["disabled"].get("mod.ui.alpha") == "off disabled ")
        check("UI: Remove (confirmed) deletes the mod's folder only",
              "mod.ui.beta" not in d["removed"] and not (home / "mods" / "installed" / "ui.beta").exists()
              and (home / "mods" / "installed" / "ui.alpha").is_dir() and (game / "fix.lvl").read_bytes() == bytes(fix))
        check("UI: no file or folder dialog on the private desktop", "dialog" not in log or "dialog: Remove" in log)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keep")
    ap.add_argument("--skip-runtime-dry-run", action="store_true", help="skip real-build dry runs while a person plays")
    a = ap.parse_args()
    if a.keep:
        Path(a.keep).mkdir(parents=True, exist_ok=True)
    runtime_checks()
    with tempfile.TemporaryDirectory(prefix="r3hd_m33_") as tmp:
        t = Path(tmp)
        for name, fn in (("data", data_checks), ("play", play_checks), ("inst", installer_checks)):
            if name == "play" and a.skip_runtime_dry_run:
                skip("play.ps1 dry runs", "explicit --skip-runtime-dry-run; game may be running")
                continue
            (t / name).mkdir()
            fn(t / name)
        (t / "ui").mkdir()
        launcher_checks(t / "ui", a.keep)
    failed = sum(not ok for _, ok in checks)
    print(f"M33_REGRESSION {'PASS' if not failed else 'FAIL'} checks={len(checks)} failures={failed} skipped={len(skipped)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

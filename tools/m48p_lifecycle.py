#!/usr/bin/env python3
"""M48-P (D-087): silent lifecycle of the private playtest setup (test mode only: /VERYSILENT /SUPPRESSMSGBOXES
/R3HDTEST=1, synthetic folders under OUT, no registry entry, no game process; launches are play.ps1 -DryRun).

    python tools/m48p_lifecycle.py SETUP.exe PREVIOUS_SETUP.exe M48_SETUP.exe PACKAGE OLD_TR_MOD OTHER_MOD OUT
                                   [--expect-bin BUILD_DIR]

PREVIOUS_SETUP = the M42-era setup the person's installation came from, M48_SETUP = the frozen M48 candidate setup,
OLD_TR_MOD = tr.full.dev 0.1.0-dev, OTHER_MOD = an unrelated private test mod folder (another ID, no text overlap).
  A  fresh, Turkish UI: healthy, frozen binaries, DLLs, notices, Turkish enabled (one copy, record), gameplay subtitles
     on as Custom on the chosen preset, dry runs (plan, gameplay sub all, -Mods off, disable = English, enable again)
  B  fresh, English UI, Turkish and subtitles declined: no mod, fixed preset, plain dry run
  C  update of an M42-era installation: other mod first, Turkish 0.1.0 disabled second, Custom HD+ settings, user
     stand-ins -> Turkish 0.2.0 in place, still disabled, order kept, other mod / settings / user data byte-identical
  D  update of the M48 candidate installation with 0.2.0 enabled: unchanged, settings byte-identical
  E  a newer Turkish version (0.3.0-dev test copy) is kept; F a removed one is not brought back, /TURKISH=2 restores it
  G  an explicit subtitles-off choice survives a silent update; a launcher-style Custom save keeps subtitles on
  H  repair (/VERIFYDATA=1); I cancel during extraction leaves nothing, a clean retry installs
  J  uninstall keeps saves, settings and mods; reinstall reuses them; uninstall /REMOVEUSERDATA=1 removes them
Rows: OUT/lifecycle.json; prints M48P_LIFECYCLE PASS n/n.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m48_replay_check as rc  # noqa: E402  (setup / dry-run / mod helpers of the M48 check)

check, checks = rc.check, rc.checks
FROZEN = ("r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll", "ffmpeg.dll", "mspack.dll")
NOTICES = ("THIRD_PARTY_NOTICES.txt", "licenses/LGPL-SOURCE.txt", "licenses/DirectXShaderCompiler-LICENSE.txt",
           "licenses/FFmpeg-COPYING.LGPLv2.1.txt", "licenses/libmspack-COPYING.LIB.txt")
TR = "tr.full.dev"


def settings(home):
    p = home / "settings.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def mod_rows(home):
    code, j, _ = rc.mods(home, "list")
    return [(m["id"], m.get("version"), m["enabled"]) for m in j.get("mods", [])] if code == 0 else None


def record(home):
    p = home / "mods" / "bundled.json"
    return json.loads(p.read_text(encoding="utf-8"))["mods"].get(TR) if p.is_file() else None


def stand_ins(home):
    for rel, data in (("profiles/default/user/B13EBABEBABEBABE/5841123F/m48p_save.bin", b"M48-P save stand-in\n"),
                      ("profiles/default/user/achievements/5841123F.toml", b"# M48-P achievements stand-in\n"),
                      ("save_history/m48p/001/m48p_save.bin", b"M48-P history stand-in\n"),
                      ("sessions/m48p/runtime.log", b"M48-P session stand-in\n")):
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def user_hashes(home, names=("settings.json", "profiles", "save_history", "sessions")):
    return {n: rc.tree_hash(home / n) for n in names if (home / n).exists()}


def newer_copy(src: Path, dst: Path, version: str):
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zo:
        for item in zi.infolist():
            data = zi.read(item.filename)
            if item.filename == "mod.json":
                m = json.loads(data.decode("utf-8"))
                m["version"] = version
                data = json.dumps(m, ensure_ascii=False, indent=1).encode("utf-8")
            zo.writestr(item.filename, data)


def main() -> int:
    ap = argparse.ArgumentParser()
    for n in ("setup", "previous", "m48setup", "package", "old_mod", "other_mod", "out"):
        ap.add_argument(n, type=Path)
    ap.add_argument("--expect-bin", type=Path)
    a = ap.parse_args()
    out = a.out.resolve()
    if out.exists():
        raise SystemExit(f"{out} exists; give a new folder")
    out.mkdir(parents=True)
    menu, desk = out / "menu", out / "desktop"
    menu.mkdir()
    desk.mkdir()
    sc = [f"/STARTMENUDIR={menu}", f"/DESKTOPDIR={desk}"]
    S, pkg = a.setup.resolve(), str(a.package.resolve())
    want_bin = {n: rc.sha(a.expect_bin / n) for n in FROZEN} if a.expect_bin else None

    # A fresh, Turkish
    hA = out / "A_home"
    code, secs, log = rc.setup(S, out, "A_fresh_tr", "/LANG=tr", f"/DIR={hA}", f"/PACKAGE={pkg}", "/PRESET=vanilla", *sc)
    vr, _, vt = rc.run_json(hA, "r3hd_installer.py", "verify", "--json")
    check(f"A fresh Turkish install ({secs} s), healthy", code == 0 and vr == 0, log[-300:] + vt[-300:])
    bins = {n: rc.sha(hA / "bin" / n) for n in FROZEN if (hA / "bin" / n).is_file()}
    check("A five runtime binaries (ffmpeg.dll, mspack.dll included)" + (" equal the frozen build" if want_bin else ""),
          len(bins) == 5 and (want_bin is None or bins == want_bin), {k: v[:12] for k, v in bins.items()})
    check("A notices: third-party, LGPL source offer, DXC (NCSA), FFmpeg LGPL, libmspack LGPL",
          all((hA / "app" / n).is_file() for n in NOTICES), [n for n in NOTICES if not (hA / "app" / n).is_file()])
    rows, rec, s = mod_rows(hA), record(hA), settings(hA)
    check("A Turkish 0.2.0-dev installed and enabled, one copy, setup record", rows == [(TR, "0.2.0-dev", True)]
          and rec and rec["action"] == "install_enable" and len(list((hA / "mods" / "installed").iterdir())) == 1, (rows, rec))
    check("A gameplay subtitles on: Custom on Vanilla, experimental allowed, nothing else overridden",
          s and s["preset"] == "custom" and s["base"] == "vanilla" and s["overrides"] == {"gameplay_subtitles": "all"}
          and s.get("allow_experimental") is True, s)
    check("A setup log: playtest steps (Turkish install_enable, gameplay subtitles all)",
          "playtest steps: Turkish install_enable, gameplay subtitles all" in log, log[-400:])
    code, f, t = rc.play_dry(hA)
    check("A Play (dry run): gameplay sub all, Turkish named, default profile", code == 0 and f.get("gameplay sub") == "all"
          and TR in f.get("mods", "") and Path(f.get("profile", "")) == hA / "profiles" / "default" / "user", t[-700:])
    code, f, t = rc.play_dry(hA, "-Mods", "off")
    check("A -Mods off: English (no mod named)", code == 0 and TR not in f.get("mods", TR), t[-400:])
    r1, _, _ = rc.mods(hA, "disable", TR)
    r2, p_off, _ = rc.mods(hA, "plan")
    code, f, t = rc.play_dry(hA)
    r3, _, _ = rc.mods(hA, "enable", TR)
    r4, p_on, _ = rc.mods(hA, "plan")
    check(f"A disabled = English fallback (empty plan, no mod in Play); enabled again: {p_on.get('ranges')} ranges",
          r1 == r2 == r3 == r4 == 0 and not p_off.get("active") and TR not in f.get("mods", TR)
          and p_on.get("active") == [TR] and p_on.get("ranges", 0) > 1000, (p_off, p_on.get("active"), f.get("mods")))
    check("A no game data, key or save in the installed app\\ (payload names only)",
          not any(p.suffix.lower() in (".xex", ".bin", ".bhf", ".btf", ".lvl") for p in (hA / "app").rglob("*")))

    # B fresh, English, declined
    hB = out / "B_home"
    code, secs, log = rc.setup(S, out, "B_fresh_en", "/LANG=en", f"/DIR={hB}", f"/PACKAGE={pkg}", "/PRESET=hdplus",
                               "/TURKISH=0", "/GAMEPLAYSUBS=original", *sc)
    rows, s = mod_rows(hB), settings(hB)
    code2, f, t = rc.play_dry(hB)
    check(f"B fresh English install, Turkish and subtitles declined ({secs} s): no mod, HD+ fixed, plain Play",
          code == 0 and rows == [] and record(hB) is None and s and s["preset"] == "hdplus" and "overrides" not in s
          and code2 == 0 and f.get("gameplay sub") == "original", (rows, s, log[-300:]))

    # C update of an M42-era installation
    hC = out / "C_home"
    code, secs, log = rc.setup(a.previous.resolve(), out, "C_previous", f"/DIR={hC}", f"/PACKAGE={pkg}", "/PRESET=vanilla", *sc)
    r0, _, t0 = rc.run_json(hC, "r3hd_installer.py", "set-preset", "--preset", "custom", "--base", "hdplus", "--set",
                            "layer_coords=separate", "display=windowed", "window_size=1920x1080")
    r1, _, t1 = rc.mods(hC, "import", str(a.other_mod.resolve()), "--enable")
    r2, _, t2 = rc.mods(hC, "import", str(a.old_mod.resolve()))
    stand_ins(hC)
    rows0 = mod_rows(hC)
    check("C M42-era installation: other mod enabled first, Turkish 0.1.0-dev disabled second, Custom HD+",
          code == 0 and r0 == r1 == r2 == 0 and [(i, e) for i, _, e in rows0] == [(rows0[0][0], True), (TR, False)]
          and rows0[1][1] == "0.1.0-dev", (log[-200:], t0[-200:], t1[-200:], t2[-200:], rows0))
    other_id = rows0[0][0]
    other_hash = rc.tree_hash(hC / "mods" / "installed" / other_id)
    kept = user_hashes(hC)
    code, secs, log = rc.setup(S, out, "C_update", "/LANG=tr", f"/DIR={hC}", *sc)
    vr, _, vt = rc.run_json(hC, "r3hd_installer.py", "verify", "--json")
    rows = mod_rows(hC)
    check(f"C playtest update ({secs} s), healthy", code == 0 and vr == 0, log[-300:] + vt[-300:])
    check("C Turkish replaced in place by 0.2.0-dev, still disabled, order kept, other mod byte-identical",
          rows == [(other_id, rows0[0][1], True), (TR, "0.2.0-dev", False)]
          and rc.tree_hash(hC / "mods" / "installed" / other_id) == other_hash
          and record(hC)["action"] == "upgrade", rows)
    check("C settings (gameplay subtitles not imposed), profiles, save history, sessions byte-identical",
          user_hashes(hC) == kept, [n for n, v in user_hashes(hC).items() if kept.get(n) != v])

    # D update of the M48 candidate installation
    hD = out / "D_home"
    code, _, log = rc.setup(a.m48setup.resolve(), out, "D_m48", f"/DIR={hD}", f"/PACKAGE={pkg}", "/PRESET=vanilla", *sc)
    r1, _, _ = rc.mods(hD, "import", str((Path(__file__).resolve().parents[1] / "private" / "tr" / "rayman3hd-turkish" /
                                          "build" / "preview" / "tr_full_dev-0_2_0.zip")), "--enable")
    stand_ins(hD)
    keptD = user_hashes(hD, ("settings.json", "profiles", "save_history", "sessions"))
    installedD = rc.tree_hash(hD / "mods" / "installed")
    code2, secs, log2 = rc.setup(S, out, "D_update", "/LANG=en", f"/DIR={hD}", *sc)
    after = user_hashes(hD, ("settings.json", "profiles", "save_history", "sessions"))
    check(f"D update of the M48 candidate ({secs} s): Turkish unchanged and enabled, settings and user data identical",
          code == 0 and r1 == 0 and code2 == 0 and mod_rows(hD) == [(TR, "0.2.0-dev", True)]
          and record(hD)["action"] == "unchanged" and all(after[n] == keptD[n] for n in after)
          and rc.tree_hash(hD / "mods" / "installed") == installedD, (log2[-300:], mod_rows(hD)))

    # E newer version kept
    newer = out / "tr_full_dev-0_3_0-test.zip"
    newer_copy(Path(__file__).resolve().parents[1] / "private" / "tr" / "rayman3hd-turkish" / "build" / "preview" /
               "tr_full_dev-0_2_0.zip", newer, "0.3.0-dev")
    r1, _, t1 = rc.mods(hA, "import", str(newer), "--replace")
    newer_hash = rc.tree_hash(hA / "mods" / "installed" / TR)
    code, secs, log = rc.setup(S, out, "E_update", f"/DIR={hA}", *sc)
    check(f"E a newer Turkish version (0.3.0-dev) is kept by the update ({secs} s)",
          r1 == 0 and code == 0 and mod_rows(hA) == [(TR, "0.3.0-dev", True)]
          and rc.tree_hash(hA / "mods" / "installed" / TR) == newer_hash and "Turkish keep_newer" in log, (t1[-200:], log[-300:]))

    # F removed not brought back; /TURKISH=2 restores
    r1, _, _ = rc.mods(hA, "remove", TR)
    code, _, log = rc.setup(S, out, "F_update", f"/DIR={hA}", *sc)
    first = mod_rows(hA)
    code2, _, log2 = rc.setup(S, out, "F_restore", f"/DIR={hA}", "/TURKISH=2", *sc)
    check("F a removed Turkish preview is not brought back; /TURKISH=2 installs it again, enabled",
          r1 == 0 and code == 0 and first == [] and "Turkish skip_removed" in log and code2 == 0
          and mod_rows(hA) == [(TR, "0.2.0-dev", True)], (first, mod_rows(hA)))

    # G explicit subtitle choices
    r1, _, _ = rc.run_json(hA, "r3hd_installer.py", "set-option", "--set", "gameplay_subtitles=original")
    before = (hA / "settings.json").read_bytes()
    code, _, log = rc.setup(S, out, "G_update", f"/DIR={hA}", *sc)
    off_kept = (hA / "settings.json").read_bytes() == before
    r2, _, _ = rc.run_json(hA, "r3hd_installer.py", "set-option", "--set", "gameplay_subtitles=all")
    r3, _, _ = rc.run_json(hA, "r3hd_installer.py", "set-preset", "--preset", "custom", "--base", "vanilla", "--set",
                           "layer_coords=separate")
    s = settings(hA)
    check("G an explicit Off survives a silent update byte for byte; a launcher-style Custom save keeps On",
          r1 == r2 == r3 == code == 0 and off_kept and s["overrides"] == {"layer_coords": "separate", "gameplay_subtitles": "all"},
          (off_kept, s))

    # H repair
    victim = hA / "bin" / "mspack.dll"
    victim.write_bytes(b"damaged")
    code, secs, log = rc.setup(S, out, "H_repair", f"/DIR={hA}", "/VERIFYDATA=1", *sc)
    vr, _, vt = rc.run_json(hA, "r3hd_installer.py", "verify", "--data", "--json")
    check(f"H repair with /VERIFYDATA=1 ({secs} s) restores a damaged DLL; healthy with data",
          code == 0 and vr == 0 and rc.sha(victim) == bins.get("mspack.dll"), log[-300:] + vt[-300:])

    # I cancel during extraction, clean retry
    hI = out / "I_home"
    code, secs, log = rc.setup(S, out, "I_cancel", f"/DIR={hI}", f"/PACKAGE={pkg}", "/PRESET=vanilla", "/CANCELAT=300", *sc)
    left = sorted(p.name for p in hI.iterdir()) if hI.exists() else []
    none_installed = not (hI / "installer.json").exists()
    code2, secs2, log2 = rc.setup(S, out, "I_retry", f"/DIR={hI}", f"/PACKAGE={pkg}", "/PRESET=vanilla", *sc)
    check(f"I cancel at 30 % ({secs} s) leaves no installation; the retry installs with Turkish ({secs2} s)",
          code != 0 and "cancel requested:" in log and none_installed and left == []
          and code2 == 0 and mod_rows(hI) == [(TR, "0.2.0-dev", True)], (code, left, log[-300:], log2[-200:]))

    # J uninstall keeps / removes user data
    stand_ins(hI)
    kept = user_hashes(hI, ("settings.json", "profiles", "save_history", "mods"))
    un = hI / "unins000.exe"
    r = subprocess.run([str(un), "/VERYSILENT", "/SUPPRESSMSGBOXES"], timeout=600)
    for _ in range(60):  # the uninstaller copies itself and returns before its work ends
        if not (hI / "app").exists():
            break
        time.sleep(1)
    gone = not (hI / "bin").exists() and not (hI / "app").exists() and not (hI / "data").exists()
    kept_ok = user_hashes(hI, ("settings.json", "profiles", "save_history", "mods")) == kept
    code, secs, log = rc.setup(S, out, "J_reinstall", f"/DIR={hI}", f"/PACKAGE={pkg}", *sc)
    reuse = code == 0 and mod_rows(hI) == [(TR, "0.2.0-dev", True)] and (hI / "settings.json").is_file() \
        and user_hashes(hI, ("profiles", "save_history")) == {k: kept[k] for k in ("profiles", "save_history")}
    r2 = subprocess.run([str(un), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/REMOVEUSERDATA=1"], timeout=600)
    for _ in range(60):
        if not hI.exists() or not any(hI.iterdir()):
            break
        time.sleep(1)
    check("J uninstall removes the program and keeps saves, settings and mods; reinstall reuses them; "
          "/REMOVEUSERDATA=1 removes everything", r.returncode == 0 and gone and kept_ok and reuse and r2.returncode == 0
          and (not hI.exists() or not any(hI.iterdir())), (gone, kept_ok, reuse, sorted(p.name for p in hI.iterdir()) if hI.exists() else []))

    shutil.rmtree(out / "menu", ignore_errors=True)
    (out / "lifecycle.json").write_text(json.dumps({"checks": checks}, indent=1) + "\n", encoding="utf-8")
    n_ok = sum(c["ok"] for c in checks)
    print(f"M48P_LIFECYCLE {'PASS' if n_ok == len(checks) else 'FAIL'} {n_ok}/{len(checks)}")
    return 0 if n_ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

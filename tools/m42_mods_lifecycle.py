#!/usr/bin/env python3
"""M42: the compiled setup's lifecycle with imported data mods and the person's other data. Silent, test mode only
(/VERYSILENT /SUPPRESSMSGBOXES /R3HDTEST=1: no uninstall entry, no launch, shortcuts only into the named test folders),
into synthetic folders under OUT; the package and the mod sources are only read. No game process is started: Play is
the launcher's dry run (r3hd_launcher.exe --play --dry-run --no-ui).

    python tools/m42_mods_lifecycle.py SETUP.exe PACKAGE MOD_A MOD_B OUT

MOD_A / MOD_B are two valid mod folders for the installed release (private test mods; never game-derived files in
the repository). Every mod command runs through the installation's own Python and r3hd_mods.py.

  1  fresh install (Vanilla), healthy
  2  import A enabled and B disabled; list order A, B; move B to the top; enable / disable keep the order
  3  the launch plan holds A only; direct Play (dry run) names A
  4  stand-ins for the person's data (a save, save history, a session log) and the mods tree are hashed
  5  repair through the setup: mods, states, order, settings and the stand-ins byte-identical; Play still names A
  6  a deleted runtime DLL is restored by a repair; mods unchanged
  7  cancel at 50 % of a repair with data verification: installation healthy, mods unchanged
  8  disabling A: the plan is empty and Play names no mod (the game's own data)
  9  uninstall without removing user data: app / bin / data gone; mods, settings and the stand-ins kept
 10  install again into the same folder: the kept mods are listed with their states and order; Play as before
 11  uninstall with /REMOVEUSERDATA=1 (the explicit choice): the folder holds none of the person's items
Rows: OUT/lifecycle.json; prints M42_MODS_LIFECYCLE PASS n/n (14 checks).
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

checks = []


def check(name, cond, detail=""):
    checks.append({"name": name, "ok": bool(cond), "detail": "" if cond else str(detail)[:400]})
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  ({str(detail)[:300]})" if detail and not cond else ""), flush=True)


def setup(exe, out, tag, *args):
    log = out / f"{tag}.log"
    t = time.monotonic()
    r = subprocess.run([str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/R3HDTEST=1", f"/LOG={log}", *args], timeout=900)
    return r.returncode, round(time.monotonic() - t, 1), log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""


def run_json(home, tool, *args):
    py = home / "app" / "python" / "python.exe"
    r = subprocess.run([str(py), "-B", str(home / "app" / "tools" / tool), *args, "--home", str(home)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    txt = r.stdout + r.stderr
    try:
        return r.returncode, json.loads(txt[txt.index("{"):txt.rindex("}") + 1]), txt
    except ValueError:
        return r.returncode, {}, txt


def mods(home, *args):
    return run_json(home, "r3hd_mods.py", *args, "--json")


def engine(home, *args):
    return run_json(home, "r3hd_installer.py", *args)


def play_dry(home):
    env = {k: v for k, v in os.environ.items() if k not in ("R3HD_GAME_DIR", "R3HD_BIN_DIR", "R3HD_PLAY_ROOT", "R3HD_HOME",
                                                           "R3HD_MODS_PLAN")}
    r = subprocess.run([str(home / "app" / "r3hd_launcher.exe"), "--play", "--dry-run", "--no-ui"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=300, env=env)
    line = next((ln.strip() for ln in (r.stdout + r.stderr).splitlines() if ln.strip().startswith("mods ")), "")
    return r.returncode, line, r.stdout + r.stderr


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    if root.is_file():
        return hashlib.sha256(root.read_bytes()).hexdigest()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def order(home):
    rc, j, _ = mods(home, "list")
    return [(m["id"], m["enabled"]) for m in j.get("mods", [])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("setup", type=Path)
    ap.add_argument("package", type=Path)
    ap.add_argument("mod_a", type=Path)
    ap.add_argument("mod_b", type=Path)
    ap.add_argument("out", type=Path)
    a = ap.parse_args()
    out = a.out.resolve()
    if out.exists():
        raise SystemExit(f"{out} exists; give a new folder")
    out.mkdir(parents=True)
    menu, desk = out / "menu", out / "desktop"
    menu.mkdir()
    desk.mkdir()
    home = out / "home"
    sc = [f"/STARTMENUDIR={menu}", f"/DESKTOPDIR={desk}"]
    pkg = str(a.package.resolve())

    # 1 fresh install
    code, secs, log = setup(a.setup, out, "fresh", f"/DIR={home}", f"/PACKAGE={pkg}", "/PRESET=vanilla", *sc)
    rc, _, txt = engine(home, "verify")
    check(f"1 fresh install: exit 0 and healthy ({secs} s)", code == 0 and rc == 0, log[-400:] + txt[-300:])
    if code != 0:
        print("M42_MODS_LIFECYCLE FAIL (no installation to continue with)")
        return 1

    # 2 import, order, enable / disable
    rc1, ja, ta = mods(home, "import", str(a.mod_a.resolve()), "--enable")
    rc2, jb, tb = mods(home, "import", str(a.mod_b.resolve()))
    ida, idb = ja.get("id"), jb.get("id")
    check("2 import: A enabled, B disabled, list order A, B", rc1 == 0 and rc2 == 0
          and order(home) == [(ida, True), (idb, False)], (ta[-300:], tb[-300:], order(home)))
    rc3, _, t3 = mods(home, "move", idb, "top")
    rc4, _, _ = mods(home, "enable", idb)
    o1 = order(home)
    rc5, _, _ = mods(home, "disable", idb)
    check("2 move B to the top; enable / disable keep the order", rc3 == 0 and rc4 == 0 and rc5 == 0
          and o1 == [(idb, True), (ida, True)] and order(home) == [(idb, False), (ida, True)], (t3[-200:], o1, order(home)))

    # 3 plan and direct Play
    rc, jp, tp = mods(home, "plan")
    check("3 the plan holds A only", rc == 0 and jp.get("active") == [ida] and jp.get("ranges", 0) > 0, tp[-300:])
    prc, pline, ptxt = play_dry(home)
    check("3 direct Play (dry run) names A", prc == 0 and ida in pline and idb not in pline, ptxt[-500:])

    # 4 stand-ins for the person's data
    for rel, data in (("profiles/E000000000000001/5841123F/m42_save.bin", b"M42 save stand-in\n"),
                      ("save_history/m42/001/m42_save.bin", b"M42 history stand-in\n"),
                      ("sessions/m42/runtime.log", b"M42 diagnostics stand-in\n")):
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    items = ("mods", "settings.json", "profiles", "save_history", "sessions")
    snap = {i: tree_hash(home / i) for i in items}
    mods_order = order(home)
    check("4 every snapshotted item exists; the mod list is not empty",
          all((home / i).exists() for i in items) and mods_order == [(idb, False), (ida, True)], mods_order)

    def same(tag):
        now = {i: tree_hash(home / i) if (home / i).exists() else None for i in items}
        diff = [i for i in items if now[i] != snap[i]]
        return not diff, diff

    # 5 repair through the setup
    code, secs, log = setup(a.setup, out, "repair", f"/DIR={home}", *sc)
    ok, diff = same("repair")
    prc, pline, ptxt = play_dry(home)
    check(f"5 repair: exit 0; mods, order, settings and stand-ins byte-identical; Play names A ({secs} s)",
          code == 0 and ok and order(home) == mods_order and prc == 0 and ida in pline, (diff, log[-300:], pline))

    # 6 a lost runtime DLL
    (home / "bin" / "rexruntime.dll").unlink()
    rc, _, txt = engine(home, "verify")
    code, secs, log = setup(a.setup, out, "repair_dll", f"/DIR={home}", *sc)
    rc2, _, txt2 = engine(home, "verify")
    ok, diff = same("dll")
    check("6 a deleted runtime DLL: verify reports it, a repair restores it, mods unchanged",
          rc != 0 and code == 0 and rc2 == 0 and (home / "bin" / "rexruntime.dll").is_file() and ok,
          (txt[-200:], txt2[-200:], diff))

    # 7 cancel during a repair with data verification
    code, secs, log = setup(a.setup, out, "cancel", f"/DIR={home}", f"/PACKAGE={pkg}", "/VERIFYDATA=1", "/CANCELAT=50", *sc)
    rc, _, txt = engine(home, "verify")
    ok, diff = same("cancel")
    check(f"7 cancel at 50 % of a verifying repair: setup reports the cancel, installation healthy, mods unchanged "
          f"(exit {code}, {secs} s)", code == 7 and "cancel" in log.lower() and rc == 0 and ok and order(home) == mods_order,
          (code, txt[-200:], diff))

    # 8 disabling A: the game's own data
    rc, _, _ = mods(home, "disable", ida)
    rcp, jp, tp = mods(home, "plan")
    prc, pline, ptxt = play_dry(home)
    check("8 A disabled: empty plan, Play names no mod", rc == 0 and rcp == 0 and jp.get("active") == []
          and prc == 0 and "none enabled" in pline, (tp[-200:], pline))
    rc, _, _ = mods(home, "enable", ida)
    snap["mods"] = tree_hash(home / "mods")
    mods_order = order(home)
    check("8 A enabled again: order B (disabled), A (enabled)", rc == 0 and mods_order == [(idb, False), (ida, True)], mods_order)

    # 9 uninstall without removing user data
    code, secs, log = setup(home / "unins000.exe", out, "uninstall")
    time.sleep(3)  # the uninstaller's copy deletes itself after the exit
    gone = [d for d in ("app", "bin", "data") if (home / d).exists()]
    ok, diff = same("uninstall")
    check("9 uninstall: app / bin / data removed; mods, settings and stand-ins kept",
          code == 0 and not gone and ok, (gone, diff, log[-300:]))

    # 10 install again into the same folder
    code, secs, log = setup(a.setup, out, "reinstall", f"/DIR={home}", f"/PACKAGE={pkg}", *sc)
    prc, pline, ptxt = play_dry(home)
    ok, diff = same("reinstall")
    check(f"10 install again: exit 0; kept mods listed with states and order; Play names A ({secs} s)",
          code == 0 and order(home) == mods_order and ok and prc == 0 and ida in pline, (log[-300:], order(home), diff, pline))

    # 11 uninstall with the explicit user-data choice
    code, secs, log = setup(home / "unins000.exe", out, "uninstall_all", "/REMOVEUSERDATA=1")
    time.sleep(3)
    left = [i for i in items + ("app", "bin", "data") if (home / i).exists()]
    check("11 uninstall with /REMOVEUSERDATA=1 removes the person's items too", code == 0 and not left, (left, log[-300:]))

    passed = sum(c["ok"] for c in checks)
    (out / "lifecycle.json").write_text(json.dumps({"checks": checks}, indent=1), encoding="utf-8")
    print(f"M42_MODS_LIFECYCLE {'PASS' if passed == len(checks) else 'FAIL'} {passed}/{len(checks)}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

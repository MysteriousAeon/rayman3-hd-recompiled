#!/usr/bin/env python3
"""M48: replay readiness of one candidate setup over an installation like the person's (silent, test mode only:
/VERYSILENT /SUPPRESSMSGBOXES /R3HDTEST=1, synthetic folders under OUT, no registry entry, no game process; Play is
play.ps1 -DryRun). The setups, the game package and the mod packages are only read.
    python tools/m48_replay_check.py PREVIOUS_SETUP.exe SETUP.exe PACKAGE OLD_MOD NEW_MOD OUT [--expect-bin BUILD_DIR]
  1  the previous setup installs; Custom = Vanilla + layer_coords separate + texture_orient corrected, fullscreen
  2  the old Turkish mod is imported enabled; stand-ins for the person's profile, save history and sessions
  3  the candidate setup updates it: healthy; binaries equal BUILD_DIR's; ffmpeg.dll / mspack.dll and LGPL texts present
  4  settings file, profile, save history, sessions and the mods tree byte-identical across the update
  5  the new mod replaces the old one under the same ID: one installed copy, enabled, the new version
  6  the launch plan compiles with the new mod only
  7  replay launch (dry run): its own profile folder, gameplay subtitles on, the saved preset and mod kept, full licence
  8  fallbacks (dry run): the plain launch keeps gameplay subtitles off and the default profile; -Mods off names no mod;
     a disabled mod leaves an empty plan, enabling it again restores it
  9  the dry runs created no replay profile folder; the default profile still byte-identical
Rows: OUT/replay_check.json; prints M48_REPLAY_CHECK PASS n/n. OUT/plan.txt names the compiled plan for hidden runs.
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
REPLAY_PROFILE = "m48replay"


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


def play_dry(home, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("R3HD_GAME_DIR", "R3HD_BIN_DIR", "R3HD_PLAY_ROOT", "R3HD_HOME",
                                                           "R3HD_MODS_PLAN")}
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(home / "app" / "tools" / "play.ps1"), "-UserHome", str(home), "-DryRun", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, env=env)
    fields = {}
    for ln in r.stdout.splitlines():
        if ":" in ln and not ln.startswith("argument"):
            k, v = ln.split(":", 1)
            fields.setdefault(k.strip(), v.strip())
    fields["_arguments"] = [ln.split(":", 1)[1].strip() for ln in r.stdout.splitlines() if ln.startswith("argument")]
    return r.returncode, fields, r.stdout + r.stderr


def tree_hash(root: Path) -> str:
    if root.is_file():
        return hashlib.sha256(root.read_bytes()).hexdigest()
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("previous", type=Path)
    ap.add_argument("setup", type=Path)
    ap.add_argument("package", type=Path)
    ap.add_argument("old_mod", type=Path)
    ap.add_argument("new_mod", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--expect-bin", type=Path)
    a = ap.parse_args()
    out = a.out.resolve()
    if out.exists():
        raise SystemExit(f"{out} exists; give a new folder")
    out.mkdir(parents=True)
    menu, desk, home = out / "menu", out / "desktop", out / "home"
    menu.mkdir()
    desk.mkdir()
    sc = [f"/STARTMENUDIR={menu}", f"/DESKTOPDIR={desk}"]
    pkg = str(a.package.resolve())

    # 1 previous installation configured like the person's
    code, secs, log = setup(a.previous.resolve(), out, "previous", f"/DIR={home}", f"/PACKAGE={pkg}", "/PRESET=vanilla", *sc)
    rc, _, txt = run_json(home, "r3hd_installer.py", "set-preset", "--preset", "custom", "--base", "vanilla", "--set",
                          "layer_coords=separate", "texture_orient=corrected", "display=fullscreen",
                          "window_size=1920x1080")
    check(f"1 previous setup installs ({secs} s); Custom preset saved", code == 0 and rc == 0, log[-300:] + txt[-300:])
    if code != 0:
        print("M48_REPLAY_CHECK FAIL (no previous installation)")
        return 1

    # 2 old mod and stand-ins
    rc, jo, to = mods(home, "import", str(a.old_mod.resolve()), "--enable")
    old_version = jo.get("version")
    for rel, data in (("profiles/default/user/B13EBABEBABEBABE/5841123F/m48_save.bin", b"M48 save stand-in\n"),
                      ("profiles/default/user/achievements/5841123F.toml", b"# M48 achievements stand-in\n"),
                      ("save_history/m48/001/m48_save.bin", b"M48 history stand-in\n"),
                      ("sessions/m48/runtime.log", b"M48 session stand-in\n")):
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    rc2, jl, _ = mods(home, "list")
    check("2 old mod imported enabled", rc == 0 and rc2 == 0 and [(m["id"], m["enabled"]) for m in jl.get("mods", [])]
          == [(jo.get("id"), True)], to[-300:])
    kept = {n: tree_hash(home / n) for n in ("settings.json", "profiles", "save_history", "sessions", "mods")}

    # 3 update
    code, secs, log = setup(a.setup.resolve(), out, "update", f"/DIR={home}", *sc)
    rc, jv, txt = run_json(home, "r3hd_installer.py", "verify", "--json")
    check(f"3 candidate setup updates the installation ({secs} s), healthy", code == 0 and rc == 0, log[-300:] + txt[-300:])
    state = json.loads((home / "installer.json").read_text(encoding="utf-8"))
    print(f"   payload_id {state.get('payload_id')} version {state.get('version')}")
    names = ("r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll", "ffmpeg.dll", "mspack.dll")
    bins = {n: sha(home / "bin" / n) for n in names if (home / "bin" / n).is_file()}
    if a.expect_bin:
        want = {n: sha(a.expect_bin / n) for n in names}
        check("3 installed binaries equal the candidate build", bins == want, {n: bins.get(n, "-")[:12] for n in names})
    else:
        check("3 all five binaries installed", len(bins) == 5, sorted(bins))
    lic = home / "app" / "licenses"
    check("3 LGPL texts and source notice installed", (lic / "FFmpeg-COPYING.LGPLv2.1.txt").is_file()
          and (lic / "libmspack-COPYING.LIB.txt").is_file() and (lic / "LGPL-SOURCE.txt").is_file(),
          sorted(p.name for p in lic.iterdir()) if lic.is_dir() else "no licenses")

    # 4 user data across the update
    after = {n: tree_hash(home / n) for n in kept}
    check("4 settings, profile, save history, sessions and mods byte-identical across the update", after == kept,
          [n for n in kept if kept[n] != after[n]])

    # 5 new mod replaces the old one
    rc, jn, tn = mods(home, "import", str(a.new_mod.resolve()), "--replace", "--enable")
    rc2, jl, _ = mods(home, "list")
    listed = [(m["id"], m.get("version"), m["enabled"]) for m in jl.get("mods", [])]
    copies = [p for p in (home / "mods" / "installed").iterdir()] if (home / "mods" / "installed").is_dir() else []
    versions = [json.loads((p / "mod.json").read_text(encoding="utf-8")).get("version") for p in copies
                if (p / "mod.json").is_file()]
    check(f"5 new mod replaces {old_version} under the same ID: one copy, enabled, {jn.get('version')}",
          rc == 0 and rc2 == 0 and listed == [(jn.get("id"), jn.get("version"), True)] and versions == [jn.get("version")]
          and jn.get("version") != old_version, (tn[-300:], listed, versions))

    # 6 plan
    rc, jp, tp = mods(home, "plan")
    check(f"6 launch plan with the new mod only ({jp.get('ranges')} ranges)", rc == 0 and jp.get("active") == [jn.get("id")]
          and jp.get("ranges", 0) > 0, tp[-300:])
    (out / "plan.txt").write_text(str(jp.get("plan", "")) + "\n", encoding="utf-8")

    # 7 replay launch
    rc, f, t = play_dry(home, "-Profile", REPLAY_PROFILE, "-GameplaySubtitles", "all")
    prof = Path(f.get("profile", ""))
    want_prof = home / "profiles" / REPLAY_PROFILE / "user"
    check("7 replay dry run: own profile, gameplay subtitles all, Custom kept, mod named, full licence",
          rc == 0 and prof == want_prof and f.get("gameplay sub") == "all" and f.get("layer coord") == "separate"
          and f.get("texture ori") == "corrected" and f.get("display") == "fullscreen" and jn.get("id", "?") in
          f.get("mods", "") and f.get("licence", "").lower().startswith("full")
          and f.get("bin dir") and Path(f["bin dir"]) == home / "bin", t[-900:])
    check("7 replay arguments carry the gameplay-subtitle option to the runtime only through its own switch",
          not any("license_mask" in x for x in f["_arguments"]), f["_arguments"])
    (out / "dry_replay.txt").write_text(t, encoding="utf-8")

    # 8 fallbacks
    rc, f, t = play_dry(home)
    check("8 plain launch: gameplay subtitles original, default profile, mod named",
          rc == 0 and f.get("gameplay sub") == "original" and Path(f.get("profile", "")) == home / "profiles" / "default" / "user"
          and jn.get("id", "?") in f.get("mods", ""), t[-600:])
    rc, f, t = play_dry(home, "-Profile", REPLAY_PROFILE, "-GameplaySubtitles", "all", "-Mods", "off")
    check("8 -Mods off: no mod named", rc == 0 and jn.get("id", "?") not in f.get("mods", "x" + jn.get("id", "?")), t[-600:])
    rc1, _, _ = mods(home, "disable", jn.get("id", ""))
    rc2, jp2, _ = mods(home, "plan")
    rc3, _, _ = mods(home, "enable", jn.get("id", ""))
    rc4, jp3, _ = mods(home, "plan")
    check("8 disabled: empty plan; enabled again: the same plan", rc1 == rc2 == rc3 == rc4 == 0 and not jp2.get("active")
          and jp3.get("active") == [jn.get("id")] and jp3.get("ranges") == jp.get("ranges"), (jp2, jp3.get("active")))

    # 9 isolation
    check("9 dry runs created no replay profile folder", not (home / "profiles" / REPLAY_PROFILE).exists())
    check("9 default profile, save history and sessions still byte-identical",
          all(tree_hash(home / n) == kept[n] for n in ("profiles", "save_history")) and
          (home / "sessions" / "m48" / "runtime.log").read_bytes() == b"M48 session stand-in\n")

    (out / "replay_check.json").write_text(json.dumps({"checks": checks, "bins": bins, "payload_id": state.get("payload_id"),
                                                      "plan": jp.get("plan")}, indent=1) + "\n", encoding="utf-8")
    n_ok = sum(c["ok"] for c in checks)
    print(f"M48_REPLAY_CHECK {'PASS' if n_ok == len(checks) else 'FAIL'} {n_ok}/{len(checks)}")
    return 0 if n_ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Focused Game Language persistence/UI/normal launch preparation. Starts no game.

Uses the existing synthetic installer fixture, native private-desktop UI driver,
and production Play dry-run. Run only after hidden game tests end.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

import m30_launcher_regression as m30
import r3hd_installer as engine
import r3hd_settings as settings
import r3hd_ui_locale as locale

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = {"en": 1, "fr": 4, "es": 5, "it": 6, "de": 3}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path, help="new directory under private/")
    a = ap.parse_args()
    out = a.out.resolve()
    if out.exists() or not out.is_relative_to((ROOT / "private").resolve()):
        ap.error("use a NEW private directory")
    out.mkdir(parents=True)
    results = []

    def check(name, ok):
        results.append({"name": name, "pass": bool(ok)})
        print(("PASS " if ok else "FAIL ") + name, flush=True)

    reg = settings.load_registry()
    spec = reg["settings"]["game_language"]
    check("only runtime-verified target languages offered", set(spec["values"]) == set(CONSOLE))
    for p in ("vanilla", "hdplus", "custom"):
        check(f"{p}: default English", settings.resolve(reg, p)["values"]["game_language"] == "en")
    for schema in (1, 2, 3, 4):
        check(f"legacy schema {schema}: English", settings.resolve(reg, settings={"schema": schema, "preset": "vanilla"})[
            "values"]["game_language"] == "en")
    catalog = locale.load()
    needed = [spec["label"], spec["help"], *spec["value_labels"].values()]
    check("all new selector labels/help translated", all(k in catalog and catalog[k]["tr"] for k in needed))
    check("translation-mod English requirement visible", "Turkish/PT-BR mods need English" in spec["help"])
    sys32 = out / "sys32"
    sys32.mkdir()
    for n in engine.VC_RUNTIME:
        (sys32 / n).write_bytes(b"x")
    os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
    home = m30.make_home(out, "home")
    # Real mod-registry shape, synthetic IDs: choices/order must survive byte for byte.
    sentinel = home / "mods" / "state.json"
    sentinel.parent.mkdir(exist_ok=True)
    sentinel.write_bytes(b'{"schema":1,"mods":[{"id":"test.turkish","enabled":true},'
                         b'{"id":"test.ptbr","enabled":false}]}\n')
    before = sentinel.read_bytes()
    for lang in spec["values"]:
        # Exercise real Win32 controls, save, reload, preset transitions, and a second process.
        script = (f"profile vanilla\npage advanced\nset game_language {lang}\nclick save\nreload\npage advanced\ndump selected\n"
                  "profile hdplus\nclick save\nreload\npage advanced\ndump hdplus\nprofile custom\nclick save\nreload\n"
                  f"page advanced\ndump custom\nshot language_{lang}\npage mods\nshot mods_{lang}\nclick close\n")
        code, dumps, log, _ = m30.ui(home, out, lang, script)
        check(f"{lang}: native UI save/reload + Vanilla/HD+/Custom retention",
              code == 0 and all(dumps.get(k, {}).get("setting.game_language") == f"{lang} enabled=1"
                                for k in ("selected", "hdplus", "custom")))
        check(f"{lang}: native UI layout fits", bool(dumps) and all(m30.layout_ok(d) for d in dumps.values()))
        code, dumps, log, _ = m30.ui(home, out, lang + "_restart", "page advanced\ndump reopened\nclick close\n")
        check(f"{lang}: persisted across Settings processes",
              code == 0 and dumps.get("reopened", {}).get("setting.game_language") == f"{lang} enabled=1")
        code, text = m30.run_launcher(home, out, "--play", "--dry-run", "--no-ui",
                                     env=dict(m30.launcher_env(), R3HD_BIN_DIR=str(m30.BUILD), R3HD_GAME_DIR=str(m30.GAME)))
        (out / f"play_{lang}.log").write_bytes(text.encode("utf-8"))
        check(f"{lang}: normal Settings -> Play -> saved resolver -> console cvar",
              code == 0 and f"--user_language={CONSOLE[lang]}" in text)
        check(f"{lang}: mod state untouched", sentinel.read_bytes() == before)
    # Explicit launcher choice wins, without changing the saved choice.
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools/play.ps1"),
           "-UserHome", str(home), "-GameLanguage", "fr", "-DryRun"]
    env = dict(m30.launcher_env(), R3HD_BIN_DIR=str(m30.BUILD), R3HD_GAME_DIR=str(m30.GAME))
    before_settings = (home / "settings.json").read_bytes()
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    (out / "explicit_play.log").write_bytes((r.stdout + r.stderr).encode())
    check("explicit French wins; saved language untouched", r.returncode == 0 and "--user_language=4" in r.stdout
          and (home / "settings.json").read_bytes() == before_settings)
    (out / "results.json").write_bytes((json.dumps(results, indent=2) + "\n").encode())
    passed = sum(r["pass"] for r in results)
    print(f"ISSUE2_LANGUAGE_REGRESSION {'PASS' if passed == len(results) else 'FAIL'} {passed}/{len(results)}")
    return int(passed != len(results))


if __name__ == "__main__":
    raise SystemExit(main())

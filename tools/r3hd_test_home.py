#!/usr/bin/env python3
"""D-116: an isolated home for a human acceptance check, built from the development build without copying game data.

    python tools/r3hd_test_home.py make HOME [--bin DIR] [--data DIR] [--preset hdplus]
    python tools/r3hd_test_home.py check HOME

E-273's B8 home was made with r3hd_paths.py (init-home + install), which never writes the installer engine's state
record: launcher-model then reports INSTALL not_installed, so Settings shows "This installation needs repair" and
disables Play. That validation is correct for an installation and stays as it is; this tool makes a test home that
satisfies it honestly:
  * r3hd_paths.py init-home + install --from the build (bin\\ files and their hashes);
  * data\\content: an NTFS junction to the extracted data (nothing copied; the tool never deletes anything), checked
    against the known release's manifest (every file and size; --verify: SHA-256 too), recorded in data\\intake.json;
  * installer.json: the engine's own new_state record for these bin\\ files, marked test_home, whose owned list leaves
    out data (an uninstall of this home never walks into the junction).
Then launcher-model must report INSTALL ok, FILES ok and DATA ok (`check`). HOME must be under private/work, new or
empty. Nothing outside HOME is written; the extracted data is only read.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_installer as engine  # noqa: E402
import r3hd_intake as intake  # noqa: E402
import r3hd_paths as paths  # noqa: E402

BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
DATA = ROOT / "private" / "extracted" / "5841123F"


def model_rows(home: Path) -> dict:
    out = engine.launcher_model(home)
    return {line.split("\t", 1)[0]: line.split("\t")[1:] for line in out.splitlines() if "\t" in line}


def make(home: Path, bin_dir: Path, data: Path, preset: str, verify: bool) -> int:
    home = home.resolve()
    if not engine.is_within(home, ROOT / "private" / "work"):
        raise SystemExit(f"refused: {home} is not under private/work")
    if home.exists() and any(home.iterdir()):
        raise SystemExit(f"refused: {home} exists and is not empty (this tool never overwrites or deletes)")
    releases = engine.load_releases()
    release = next(r for r in releases if r["id"] == "x360-xbla-5841123F-v1")
    manifest = intake.load_manifest(release)
    try:
        checked = (intake.verify_tree(data, release, manifest) if verify else None)
    except intake.Refused as e:
        raise SystemExit(f"refused: {data} is not the known release's data ({e.code}: {e.detail})")
    missing = [r for r, (size, _) in manifest.items() if not data.joinpath(*r.split("/")).is_file()
               or data.joinpath(*r.split("/")).stat().st_size != size]
    if missing:
        raise SystemExit(f"refused: {data} lacks or differs in {len(missing)} manifest files (first {missing[0]})")
    home.mkdir(parents=True, exist_ok=True)
    paths.init_home(home, preset)
    paths.install(home, bin_dir)
    (home / "data").mkdir()
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(home / "data" / "content"), str(data)], capture_output=True,
                       text=True)
    if r.returncode != 0:
        raise SystemExit(f"junction failed: {r.stdout}{r.stderr}")
    record = {"tool": "r3hd_test_home.py", "tool_version": engine.SCHEMA, "release": release["id"],
              "source": {"kind": "junction", "path": str(data)},
              "content": {"directory": "content", "files": len(manifest),
                          "manifest_sha256": release["content"]["manifest_sha256"],
                          "executable_sha256": release["executable"]["sha256"],
                          "checked": "sha256" if checked else "sizes"},
              "note": "TEST HOME (D-116): content is a junction to the developer's extracted data. Never delete "
                      "through it; remove the junction itself (rmdir) first."}
    engine.write_json(home / "data" / "intake.json", record)
    bins = json.loads((home / "bin" / "install.json").read_text(encoding="utf-8"))["files"]
    payload = {"version": json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))["version"]
               + "-test", "payload_id": "test-home-" + engine.hashlib.sha256(json.dumps(bins, sort_keys=True).encode()).hexdigest(),
               "files": {f"bin/{n}": {"sha256": h} for n, h in bins.items()}}
    state = engine.new_state(payload, record, engine.presets.load_settings_file(home / "settings.json"), None)
    state["owned"] = ["bin", "cache", engine.STATE, engine.HOME_MARK]  # never data: the junction stays the person's
    state["test_home"] = True
    state["note"] = "TEST HOME (D-116) for a human acceptance check; not an installation made by setup."
    engine.write_json(home / engine.STATE, state)
    return check(home)


def check(home: Path) -> int:
    rows = model_rows(home)
    ok = rows.get("INSTALL", [""])[0] == "ok" and rows.get("FILES", [""])[0] == "ok" and rows.get("DATA", [""])[0] == "ok"
    print(f"R3HD_TEST_HOME {'OK' if ok else 'NOT_OK'} INSTALL={rows.get('INSTALL')} FILES={rows.get('FILES')} "
          f"DATA={rows.get('DATA')} SETTINGS={rows.get('SETTINGS', [''])[:2]} PADSTATE={rows.get('PADSTATE', [''])[:1]}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("home", type=Path)
    m.add_argument("--bin", type=Path, default=BUILD)
    m.add_argument("--data", type=Path, default=DATA)
    m.add_argument("--preset", default="hdplus")
    m.add_argument("--verify", action="store_true", help="SHA-256 of every data file (slower)")
    c = sub.add_parser("check")
    c.add_argument("home", type=Path)
    a = ap.parse_args()
    if a.cmd == "make":
        return make(a.home, a.bin.resolve(), a.data.resolve(), a.preset, a.verify)
    return check(a.home.resolve())


if __name__ == "__main__":
    raise SystemExit(main())

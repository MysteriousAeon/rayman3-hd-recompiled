#!/usr/bin/env python3
"""M48-P: a mod that a setup carries (the private playtest setup's Turkish preview), applied to an installation by one
deterministic policy. The work is r3hd_mods.py's own controlled import; this tool only decides whether to call it.

    r3hd_bundled_mods.py apply --home H --mod ZIP [--want 0|1] [--result-file F] [--json]
    r3hd_bundled_mods.py status --home H --mod ZIP                 the decision apply would take, nothing written
    r3hd_bundled_mods.py selftest                                  the decision table and the record, no game data

Policy (one copy per mod ID, by r3hd_mods.py's state; never a second folder):
  not installed, never installed by a setup     want=1: import and enable (a fresh playtest installation)
                                                want=0: nothing (the person declined it in the wizard)
  not installed, a setup installed it before    nothing: the person removed it; a setup never brings it back
                                                (want=2: the person ticked the box again: import and enable)
  installed, want=0                             nothing
  installed, newer version                      nothing (a newer preview the person imported is kept)
  installed, same version, same files           nothing
  installed, same version, other files          nothing (a local build of that version is kept)
  installed, older version                      replace in place: the enabled / disabled choice and the priority stay
M49 (D-088): want=3 = an existing installation (whatever the wizard's language): a copy that is installed is treated
as with want=1 (an older one is updated in place, its on / off choice and priority kept; a newer one is kept); a mod
that is not installed stays not installed (skip_absent), so a setup never adds or brings back a mod to an existing
installation unless the person asks (want=2). A fresh installation gets want=1 from a Turkish wizard and want=0 from
an English one.
The record HOME\\mods\\bundled.json says what a setup did (mod, version, package SHA-256, action, time); it is the only
file this tool writes besides r3hd_mods.py's own. Versions compare by their numbers (r3hd_mods.version_key); a
suffix such as -dev does not order. Exit 0 ok (also for "nothing"), 2 refused (reason code), 1 internal error.
"""
import argparse
import datetime
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_mods as mods  # noqa: E402  (the one mod engine, M33)

RECORD = "bundled.json"
RECORD_SCHEMA = 1
ACTIONS = {
    "install_enable": "installed and enabled",
    "skip_declined": "not installed (declined)",
    "skip_removed": "not installed: it was removed after an earlier setup installed it",
    "untouched": "left as it is (not selected in setup)",
    "keep_newer": "kept: a newer version is installed",
    "unchanged": "already installed (same version and files)",
    "keep_different": "kept: the installed copy of this version has other files",
    "upgrade": "updated in place (enabled state and order kept)",
    "skip_absent": "not installed (this installation did not have it)",
}


def decide(bundled: dict, installed, record, want) -> str:
    """bundled {version, files}; installed None or {version, files, enabled}; record None or the setup's entry;
    want 0 / 1, or 2 = 1 and also after a removal (the person asked again), or 3 = an existing installation: only an
    installed copy is looked at (M49)."""
    if installed is None:
        if want == 3:
            return "skip_absent"
        if record is not None and want != 2:
            return "skip_removed"
        return "install_enable" if want else "skip_declined"
    if not want:
        return "untouched"
    b, i = mods.version_key(bundled["version"]), mods.version_key(installed["version"])
    if i > b:
        return "keep_newer"
    if i == b:
        return "unchanged" if installed["files"] == bundled["files"] else "keep_different"
    return "upgrade"


def paths_for(home: Path) -> dict:
    return mods.resolve_paths(SimpleNamespace(home=str(home), mods_root=None, cache=None, game_dir=None))


def read_record(paths) -> dict:
    p = paths["mods"] / RECORD
    if not p.is_file():
        return {"schema": RECORD_SCHEMA, "mods": {}}
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(r, dict) and r.get("schema") == RECORD_SCHEMA and isinstance(r.get("mods"), dict)
        return r
    except (OSError, ValueError, AssertionError):
        raise mods.Refusal("STATE_DAMAGED", str(p))


def write_record(paths, rec: dict):
    paths["mods"].mkdir(parents=True, exist_ok=True)
    p = paths["mods"] / RECORD
    tmp = p.with_name(f"{RECORD}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def bundled_info(zip_path: Path) -> dict:
    files = mods.read_package(zip_path)
    m = mods.parse_manifest(files)
    return {"id": m["id"], "version": m["version"], "name": m.get("name", m["id"]),
            "files": {r: mods.sha256_bytes(b) for r, b in sorted(files.items())},
            "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest()}


def installed_info(paths, mod_id: str):
    state = mods.load_state(paths)
    e = next((x for x in state["mods"] if x["id"] == mod_id), None)
    d = mods.installed_dir(paths, mod_id)
    if e is None and not d.exists():
        return None
    try:
        rec = json.loads((d / "installed.json").read_text(encoding="utf-8"))
        return {"version": str(rec["version"]), "files": dict(rec["files"]), "enabled": bool(e and e["enabled"])}
    except (OSError, ValueError, KeyError, TypeError):
        raise mods.Refusal("STATE_DAMAGED", f"{d}: installed.json unreadable; nothing was changed")


def evaluate(home: Path, zip_path: Path, want: bool):
    paths = paths_for(home)
    mods.recover(paths)
    b = bundled_info(zip_path)
    inst = installed_info(paths, b["id"])
    rec = read_record(paths)
    return paths, b, inst, rec, decide(b, inst, rec["mods"].get(b["id"]), want)


def apply(home: Path, zip_path: Path, want: bool, importer=None) -> dict:
    importer = importer or mods.cmd_import
    paths, b, before, rec, action = evaluate(home, zip_path, want)
    if action == "install_enable":
        importer(paths, zip_path, replace=False, enable=True)
    elif action == "upgrade":
        importer(paths, zip_path, replace=True, enable=False)  # r3hd_mods keeps enabled state and priority
    after = installed_info(paths, b["id"])
    state = mods.load_state(paths)
    copies = sum(1 for e in state["mods"] if e["id"] == b["id"])
    if after is not None and copies != 1:
        raise mods.Refusal("STATE_DAMAGED", f"{b['id']}: {copies} entries in state.json")
    if action in ("install_enable", "upgrade", "unchanged"):
        rec["mods"][b["id"]] = {"version": b["version"], "sha256": b["sha256"], "action": action,
                                "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        write_record(paths, rec)
    return {"action": action, "id": b["id"], "version": b["version"], "package_sha256": b["sha256"],
            "before": before and {"version": before["version"], "enabled": before["enabled"]},
            "installed_version": after and after["version"], "enabled": int(bool(after and after["enabled"])),
            "order": [e["id"] for e in state["mods"]], "message": ACTIONS[action]}


def selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(("ok   " if cond else "FAIL ") + name)

    B = {"version": "0.2.0-dev", "files": {"mod.json": "b"}}
    inst = lambda v, f="b", en=True: {"version": v, "files": {"mod.json": f}, "enabled": en}  # noqa: E731
    table = [
        (None, None, True, "install_enable"), (None, None, False, "skip_declined"),
        (None, {"version": "0.1.0-dev"}, True, "skip_removed"), (None, {"version": "0.1.0-dev"}, 2, "install_enable"),
        (inst("0.1.0-dev"), None, False, "untouched"),
        (inst("0.3.0-dev"), None, True, "keep_newer"), (inst("0.2.0-dev"), None, True, "unchanged"),
        (inst("0.2.0-dev", "x"), None, True, "keep_different"), (inst("0.1.0-dev", "x", False), None, True, "upgrade"),
        (inst("0.2.0"), None, True, "unchanged"), (inst("0.10.0-dev", "x"), None, True, "keep_newer"),
        # M49: an existing installation (want 3) never gains the mod; an installed copy follows the want=1 rules
        (None, None, 3, "skip_absent"), (None, {"version": "0.1.0-dev"}, 3, "skip_absent"),
        (inst("0.1.0-dev", "x", False), None, 3, "upgrade"), (inst("0.3.0-dev"), None, 3, "keep_newer"),
        (inst("0.2.0-dev"), None, 3, "unchanged"), (inst("0.2.0-dev", "x"), None, 3, "keep_different"),
    ]
    for installed, record, want, expect in table:
        got = decide(B, installed, record, want)
        check(f"decide installed={installed and installed['version']} record={bool(record)} want={int(want)} -> {expect}",
              got == expect)
    # The record and the one-copy rule, with a stand-in importer (r3hd_mods' import needs game data).
    with tempfile.TemporaryDirectory() as t:
        home = Path(t) / "home"
        (home / "mods").mkdir(parents=True)
        z = Path(t) / "m.zip"
        import zipfile
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("mod.json", json.dumps({"format": 1, "id": "tr.test", "name": "T", "version": "0.2.0-dev",
                                                "target": {"title_id": "5841123F", "releases": ["x360-xbla-5841123F-v1"],
                                                           "min_port_version": "0.36.0"},
                                                "overrides": [{"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": 64,
                                                               "slot_sha256": "0" * 64, "text": "Test"}]}))
        try:
            bundled_info(z)
            have_manifest = True
        except mods.Refusal:
            have_manifest = False
        if have_manifest:
            calls = []

            def fake_import(paths, src, replace=False, enable=False):
                calls.append((replace, enable))
                files = mods.read_package(src)
                m = mods.parse_manifest(files)
                d = mods.installed_dir(paths, m["id"])
                d.mkdir(parents=True, exist_ok=True)
                (d / "installed.json").write_text(json.dumps({"version": m["version"], "files": {
                    r: mods.sha256_bytes(x) for r, x in files.items()}}), encoding="utf-8")
                s = mods.load_state(paths)
                e = next((x for x in s["mods"] if x["id"] == m["id"]), None)
                if e is None:
                    s["mods"].append({"id": m["id"], "enabled": enable, "installed_at": "t"})
                elif enable:
                    e["enabled"] = True
                mods.save_state(paths, s)

            mods.save_state(paths_for(home), {"schema": 1, "mods": [{"id": "other.a", "enabled": True, "installed_at": "t"}]})
            (home / "mods" / "installed" / "other.a").mkdir(parents=True)
            (home / "mods" / "installed" / "other.a" / "installed.json").write_text('{"version": "1", "files": {}}')
            r = apply(home, z, True, fake_import)
            check("fresh: imported and enabled after the unrelated mod; record written",
                  r["action"] == "install_enable" and r["enabled"] == 1 and r["order"] == ["other.a", "tr.test"]
                  and read_record(paths_for(home))["mods"]["tr.test"]["version"] == "0.2.0-dev" and calls == [(False, True)])
            r = apply(home, z, True, fake_import)
            check("second run: unchanged, no import", r["action"] == "unchanged" and len(calls) == 1)
            mods.cmd_set(paths_for(home), "tr.test", False)
            r = apply(home, z, True, fake_import)
            check("a disabled copy stays disabled", r["action"] == "unchanged" and r["enabled"] == 0)
            r = apply(home, z, 3, fake_import)
            check("M49: an existing installation keeps a disabled copy disabled", r["action"] == "unchanged"
                  and r["enabled"] == 0 and len(calls) == 1)
            mods.cmd_remove(paths_for(home), "tr.test")
            r = apply(home, z, 3, fake_import)
            check("M49: removed, then an existing-installation setup: not brought back", r["action"] == "skip_absent"
                  and r["installed_version"] is None and len(calls) == 1)
            r = apply(home, z, True, fake_import)
            check("removed after a setup installed it: not brought back", r["action"] == "skip_removed"
                  and r["installed_version"] is None and len(calls) == 1)
        else:
            check("synthetic manifest accepted by r3hd_mods", False)
    failed = sum(not ok for _, ok in checks)
    print(f"R3HD_BUNDLED_MODS_SELFTEST {'PASS' if not failed else 'FAIL'} checks={len(checks)}")
    return 0 if not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["apply", "status", "selftest"])
    ap.add_argument("--home")
    ap.add_argument("--mod")
    ap.add_argument("--want", choices=["0", "1", "2", "3"], default="1")
    ap.add_argument("--result-file")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    try:
        if not a.home or not a.mod:
            raise mods.Refusal("USAGE", f"{a.cmd} needs --home and --mod")
        home, z = Path(os.path.abspath(a.home)), Path(os.path.abspath(a.mod))
        if a.cmd == "status":
            _, b, inst, _, action = evaluate(home, z, int(a.want))
            r = {"action": action, "id": b["id"], "version": b["version"], "message": ACTIONS[action],
                 "installed_version": inst and inst["version"], "enabled": int(bool(inst and inst["enabled"]))}
        else:
            r = apply(home, z, int(a.want))
        r = {"result": "ok", **r}
        code = 0
    except mods.Refusal as x:
        r = {"result": "refused", "code": x.code, "detail": x.detail, "message": f"{x.code}: {x.detail}"}
        code = 2
    except (OSError, ValueError) as x:
        r = {"result": "refused", "code": "UNREADABLE", "detail": f"{type(x).__name__}: {x}",
             "message": f"UNREADABLE: {type(x).__name__}: {x}"}
        code = 2
    if a.result_file:
        lines = [f"{k.upper()}={' '.join(str(r[k]).split())}" for k in
                 ("result", "code", "message", "action", "id", "version", "installed_version", "enabled") if k in r]
        Path(a.result_file).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print(json.dumps(r, indent=1, default=str, ensure_ascii=not a.json))
    return code


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Save inspection and explicit recovery from the launcher's save history (M20, D-049; history: D-045).

    python tools/m20_save_recover.py list     [--profile NAME]
    python tools/m20_save_recover.py validate PATH
    python tools/m20_save_recover.py restore  SESSION/NNN SLOT [--profile NAME] [--apply]

`list` and `validate` only read. `restore` prints its plan and changes nothing unless `--apply` is given; with
it, the whole active profile is first copied to private/play/recovery_backups/<time>/user and verified, then the
one slot (its save file and its header file) is replaced by the snapshot's copy, each file through a temporary
file and an atomic rename. Other slots, the achievements file and everything else in the profile are not
touched. Nothing is ever restored automatically, and no byte of a save is edited: a restore copies a file the
title itself wrote.

What "valid" means here: the file has the size, the header word and a level name of the shape every save of
this title has shown (RE_NOTES "M12", "M16"). The record carries no check value (RE_NOTES "M19"), so a save
with a damaged body can pass; only the title can tell whether a save loads.

`--play-root DIR` points the tool at another tree of the same shape (tests use a synthetic one). The default
is private/play, where the human profile lives: agents run `list` / `validate` there and nothing else.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLE = "5841123F"
SAVE_SIZE, HEADER_SIZE = 510, 328
GAME_IMAGE = "r3hd.exe"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)).replace("\\", "/"): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def inspect_save(path: Path) -> dict:
    """Structural facts of one save file. `problems` empty = structurally valid (not proof of integrity)."""
    out: dict = {"file": path.name, "problems": []}
    if not path.is_file():
        out["problems"].append("save file missing")
        return out
    data = path.read_bytes()
    out.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    if len(data) != SAVE_SIZE:
        out["problems"].append(f"size {len(data)}, expected {SAVE_SIZE}")
    if data[:4] != b"AAAA":
        out["problems"].append("header word is not AAAA")
    if len(data) >= 184:
        raw = data[152:184].split(b"\0", 1)[0]
        level = raw.decode("latin-1")
        out["level"] = level
        if not level or not all(c.isalnum() or c == "_" for c in level):
            out["problems"].append("level name field is empty or not a name")
        word = lambda offset: struct.unpack_from(">I", data, offset)[0]  # noqa: E731
        out.update(end_of_game=word(104), highest_world=word(108), revisit=word(132))
        if word(104) == 0 and level.lower() == "endgame":
            out["note"] = "resumes in the end-of-game hub with the campaign unfinished (D-047)"
    return out


def slots_of(user: Path) -> dict:
    """Slot name -> (save file, header file) for every slot directory or header in a profile's user root."""
    out: dict = {}
    for content in sorted(user.glob(f"*/{TITLE}/00000001")):
        for slot in sorted(p for p in content.iterdir() if p.is_dir()):
            out[slot.name] = (slot / slot.name, content.parent / "Headers" / "00000001" / f"{slot.name}.header")
    return out


def describe(user: Path) -> list:
    rows = []
    for name, (save, header) in slots_of(user).items():
        row = {"slot": name, **inspect_save(save)}
        if not header.is_file():
            row["problems"].append("header file missing")
        elif header.stat().st_size != HEADER_SIZE:
            row["problems"].append(f"header size {header.stat().st_size}, expected {HEADER_SIZE}")
        rows.append(row)
    return rows


def leftovers(user: Path) -> list:
    return sorted(str(p.relative_to(user)).replace("\\", "/") for p in user.glob(f"*/{TITLE}/.staging/*"))


def session_profile(play: Path, session: str) -> str | None:
    """The profile a history session belongs to, from the launcher's own record of that session."""
    launch = play / "sessions" / session / "launch.json"
    try:
        return json.loads(launch.read_text(encoding="utf-8-sig")).get("profile")
    except (OSError, ValueError):
        return None


def snapshots(play: Path) -> list:
    out = []
    history = play / "save_history"
    for session in sorted(p for p in history.iterdir() if p.is_dir()) if history.is_dir() else []:
        for snap in sorted(p for p in session.iterdir() if p.is_dir()):
            meta = snap / "snapshot.json"
            out.append({"id": f"{session.name}/{snap.name}", "path": snap, "profile": session_profile(play, session.name),
                        "complete": meta.is_file() and (snap / "user").is_dir(),
                        "meta": json.loads(meta.read_text(encoding="utf-8-sig")) if meta.is_file() else {}})
    return out


def print_rows(rows: list, active: dict | None = None) -> None:
    for row in rows:
        state = "ok (structure only)" if not row["problems"] else "INVALID: " + "; ".join(row["problems"])
        same = ""
        if active is not None and row.get("sha256"):
            same = "  = active" if active.get(row["slot"]) == row["sha256"] else ""
        print(f"    {row['slot']:10s} level={row.get('level', '?'):12s} highest_world={row.get('highest_world', '?')} "
              f"revisit={row.get('revisit', '?')} end={row.get('end_of_game', '?')} sha256={row.get('sha256', '-')[:16]} {state}{same}"
              + (f"  [{row['note']}]" if row.get("note") else ""))


def cmd_list(a) -> int:
    play = Path(a.play_root)
    user = play / "profiles" / a.profile / "user"
    print(f"active profile: {user}")
    active_rows = describe(user) if user.is_dir() else []
    print_rows(active_rows)
    if not active_rows:
        print("    (no save slots)")
    for item in leftovers(user) if user.is_dir() else []:
        print(f"    leftover staging directory (removed by the game at its next start): {item}")
    active = {row["slot"]: row.get("sha256") for row in active_rows}
    print("snapshots (private/play/save_history; a snapshot holds the whole profile as it was):")
    found = snapshots(play)
    for snap in found:
        meta = snap["meta"]
        print(f"  {snap['id']}  profile={snap['profile'] or '?'}  {meta.get('time', '?')}  reason={meta.get('reason', '?')}"
              + ("" if snap["complete"] else "  INCOMPLETE COPY (no snapshot.json): not restorable"))
        if snap["complete"]:
            print_rows(describe(snap["path"] / "user"), active)
    if not found:
        print("  (none)")
    print("Nothing was changed. Structure checks cannot prove a save loads: the record has no check value.")
    return 0


def cmd_validate(a) -> int:
    path = Path(a.path)
    rows = [{"slot": path.name, **inspect_save(path)}] if path.is_file() else describe(path)
    if not rows:
        print("no save found")
        return 1
    print_rows(rows)
    return 0 if all(not row["problems"] for row in rows) else 1


def game_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_IMAGE}", "/NH"], capture_output=True, text=True,
                             check=False).stdout
    except OSError:
        return True  # cannot tell: refuse
    return GAME_IMAGE.lower() in out.lower()


def replace_file(source: Path, target: Path) -> None:
    """Copy through a temporary file beside the target, flushed, then an atomic rename."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".m20restore.tmp")
    with open(temp, "wb") as f:
        f.write(source.read_bytes())
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, target)


def cmd_restore(a) -> int:
    play = Path(a.play_root)
    if not a.profile or any(c in a.profile for c in "/\\:") or a.profile in (".", ".."):
        print(f"not a profile name: {a.profile}")
        return 2
    user = play / "profiles" / a.profile / "user"
    snap = play / "save_history" / a.snapshot
    if ".." in Path(a.snapshot).parts or not (snap / "snapshot.json").is_file() or not (snap / "user").is_dir():
        print(f"not a complete snapshot: {a.snapshot}")
        return 2
    owner = session_profile(play, Path(a.snapshot).parts[0])
    if owner != a.profile:
        print(f"refused: snapshot {a.snapshot} belongs to profile '{owner or 'unknown'}', not '{a.profile}'")
        return 2
    source = slots_of(snap / "user").get(a.slot)
    if source is None:
        print(f"snapshot {a.snapshot} has no slot {a.slot}")
        return 2
    row = {"slot": a.slot, **inspect_save(source[0])}
    if not source[1].is_file() or source[1].stat().st_size != HEADER_SIZE:
        row["problems"].append("header file missing or of the wrong size")
    if row["problems"]:
        print(f"refused: the snapshot's slot is not structurally valid: {'; '.join(row['problems'])}")
        return 2
    if not user.is_dir():
        print(f"no active profile at {user}")
        return 2
    accounts = [p for p in user.iterdir() if p.is_dir() and (p / TITLE).is_dir()]
    relative = source[0].relative_to(snap / "user")
    if len(accounts) != 1 or relative.parts[0] != accounts[0].name:
        print("refused: the snapshot and the active profile do not belong to the same account directory")
        return 2
    targets = [(source[0], user / relative), (source[1], user / source[1].relative_to(snap / "user"))]
    current = {row["slot"]: row for row in describe(user)}.get(a.slot)
    print(f"restore slot {a.slot} of profile '{a.profile}' from snapshot {a.snapshot}")
    print("  snapshot:")
    print_rows([row])
    print("  active now:")
    print_rows([current]) if current else print("    (slot not present)")
    for src, dst in targets:
        print(f"  {'replace' if dst.exists() else 'create '} {dst.relative_to(user)}")
    if all(dst.is_file() and sha(dst) == sha(src) for src, dst in targets):
        print("the active slot is already identical to the snapshot; nothing to do")
        return 0
    if not a.apply:
        print("DRY RUN: nothing was changed. Repeat with --apply to restore (the active profile is backed up first).")
        return 0
    if game_running():
        print("refused: the game is running (or its state cannot be determined). Close it first.")
        return 2
    backup = play / "recovery_backups" / time.strftime("%Y%m%d-%H%M%S")
    if backup.exists():
        print(f"refused: backup directory exists: {backup}")
        return 2
    before = tree(user)
    shutil.copytree(user, backup / "user")
    if tree(backup / "user") != before:
        print(f"refused: the backup at {backup} does not match the profile; nothing was changed")
        return 2
    print(f"  backup of the whole profile: {backup / 'user'} ({len(before)} files, verified)")
    try:
        for src, dst in targets:
            replace_file(src, dst)
    except OSError as exc:
        print(f"ERROR: {exc}. The slot may be partly restored; the profile as it was is at {backup / 'user'}.")
        return 1
    after = tree(user)
    expected = {str(dst.relative_to(user)).replace("\\", "/"): sha(src) for src, dst in targets}
    wrong = [k for k, v in expected.items() if after.get(k) != v]
    others = [k for k in set(before) | set(after) if k not in expected and before.get(k) != after.get(k)]
    if wrong or others:
        print(f"ERROR: verification failed (wrong: {wrong}; other files changed: {others}). The backup is at {backup}.")
        return 1
    (backup / "restore.json").write_text(json.dumps({"profile": a.profile, "snapshot": a.snapshot, "slot": a.slot,
                                                     "files": expected, "time": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2) + "\n",
                                         encoding="utf-8")
    print(f"restored: {len(expected)} files replaced, {len(after) - len(expected)} other files untouched.")
    print(f"to undo, restore the files of slot {a.slot} from {backup / 'user'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--play-root", default=str(ROOT / "private" / "play"))
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list")
    p.add_argument("--profile", default="default")
    p.set_defaults(run=cmd_list)
    p = sub.add_parser("validate")
    p.add_argument("path")
    p.set_defaults(run=cmd_validate)
    p = sub.add_parser("restore")
    p.add_argument("snapshot")
    p.add_argument("slot")
    p.add_argument("--profile", default="default")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(run=cmd_restore)
    a = ap.parse_args()
    return a.run(a)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""M20 tooling regression (no game run): shape and isolation of the staged save replacement (D-049) and the
recovery tool on a synthetic profile tree.

    python tools/m20_regression.py        -> M20_REGRESSION PASS checks=N failures=0

The commit itself is tested by m20_save_commit_test.exe (in the build). The hidden checks that need the game:
    python tools/m20_save_check.py TAG        (reports/milestone20/REPORT.md)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
TOOLS = ROOT / "tools"
checks = failures = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


# --- the patch is in place and narrow -----------------------------------------------------------------------------
header = read(TOOLS / "m20_save_commit.h")
installed = SDK / "include/rex/m20_save_commit.h"
check(installed.is_file() and installed.read_bytes() == (TOOLS / "m20_save_commit.h").read_bytes(), "installed header is tools/m20_save_commit.h")
manager = read(SDK / "src/system/xam/content_manager.cpp")
xam = read(SDK / "src/kernel/xam/xam_content.cpp")
host_file = read(SDK / "src/filesystem/devices/host_path_file.cpp")
check("ContentManager::CreateContentStaged" in manager and "m20save::Commit(" in manager, "content manager stages and commits")
check(manager.count("m20save::Commit(") == 1 and "X_RESULT ContentManager::CloseContent" in manager, "one commit site (CloseContent)")
check("m20save::Abort(" in manager.split("ContentPackage::~ContentPackage()")[1].split("\n}\n")[0], "an unmount without a close drops the stage")
check(xam.count("CreateContentStaged(") == 1, "one staged create site")
branch = xam.split("case 2:  // CREATE_ALWAYS")[1].split("case 3:")[0]
check("CreateContentStaged(" in branch and "M20StagedCommitEnabled()" in branch, "the staged create is the CREATE_ALWAYS branch only")
check("content_manager->DeleteContent(xuid, content_data);" in branch, "the pinned sequence is kept for R3HD_SAVE_COMMIT=legacy")
check(branch.index("M20StagedCommitEnabled()") < branch.index("DeleteContent("), "nothing is deleted before the staged create")
check(host_file.count("NoteWriteFailure(") == 4 and "Fault::kWrite" in host_file, "host write and set-length failures reach the stage")
check("X_STATUS_END_OF_FILE" in host_file and host_file.count("return X_STATUS_SUCCESS;") == 3, "host write statuses unchanged")
for needle in ("virtual_membase", "ctx.", "PPCContext", "TranslateVirtual", "REX_KERNEL_MEMORY"):
    check(needle not in header, f"commit module does not touch guest state ({needle})")
check("MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH" in header and "FlushFileBuffers" in header, "flush, then write-through rename")
check(header.index("FlushFile(stage.content / rel)") < header.index("ReplaceFile_(stage.content / rel"), "flush precedes the rename")
check(header.index("ReplaceFile_(stage.content / rel") < header.index("CREATE_ALWAYS semantics"), "old extras are removed only after the renames")
check('kStagingDirName = L".staging"' in header, "staging directory name")
check(header.index("kEmptyRefused, \"nothing was written") < header.index("FaultExit(Fault::kExitBeforeCommit)"), "an empty stage is refused before anything is renamed")
check(header.index("ReplaceFile_(stage.content / rel") < header.index("ReplaceFile_(stage.base / L\"header\""), "data is renamed before the header")

# --- switches stay in the hidden tools ------------------------------------------------------------------------------
play = read(TOOLS / "play.ps1")
test_only = play.split("$testOnly =")[1].split("$saved = @{}")[0]
check("'R3HD_SAVE_FAULT'" in test_only and "'R3HD_SAVE_COMMIT'" in test_only, "play.ps1 clears R3HD_SAVE_FAULT and R3HD_SAVE_COMMIT")
allowed = {"m20_save_check.py", "m20_regression.py", "m20_runtime_patch.py", "m20_save_commit.h", "m20_save_commit_test.cpp", "play.ps1"}
for path in sorted(TOOLS.glob("*")):
    if path.is_file() and path.suffix in (".py", ".ps1", ".bat", ".sh", ".h", ".cpp") and path.name not in allowed:
        text = read(path)
        check("R3HD_SAVE_FAULT" not in text and "R3HD_SAVE_COMMIT" not in text, f"{path.name} does not use the save switches")
launcher_tools = read(TOOLS / "play_savekeeper.ps1")
check("m20_save_recover" not in play and "m20_save_recover" not in launcher_tools, "the launcher never restores a save")

# --- build order ----------------------------------------------------------------------------------------------------
build = read(TOOLS / "build_milestone8.bat")
order = ["m17_runtime_patch.py", "m20_runtime_patch.py", "cmake --build external", "m18_prepare.py", "m20_prepare.py",
         "m20_save_commit_test.exe ||", "m20_regression.py"]
positions = [build.find(item) for item in order]
check(all(p >= 0 for p in positions) and positions == sorted(positions), "build replays the M20 patch, test and regression in order")

# --- hidden check never writes the human profile or an entry -------------------------------------------------------
save_check = read(TOOLS / "m20_save_check.py")
check(re.findall(r"\bHUMAN\b[^\n]*", save_check).__len__() == 3 and "tree_hashes(HUMAN)" in save_check, "hidden check only hashes the human profile")
check("copytree(m12.SAVES / ENTRY / \"profile\", profile)" in save_check, "hidden check runs on working copies of the entry")
check("write_bytes" not in save_check and "unlink" not in save_check, "hidden check edits no save file")

# --- recovery tool on a synthetic tree ------------------------------------------------------------------------------
RECOVER = TOOLS / "m20_save_recover.py"
ACCOUNT, TITLE = "B13EBABEBABEBABE", "5841123F"


def synthetic_save(level: str, fill: int, size: int = 510, magic: bytes = b"AAAA") -> bytes:
    data = bytearray([fill]) * size
    data[0:4] = magic
    data[104:112] = (0).to_bytes(4, "big") + (2).to_bytes(4, "big")
    data[132:136] = (0).to_bytes(4, "big")
    data[152:184] = level.encode("ascii").ljust(32, b"\0")
    return bytes(data[:size])


def make_user(user: Path, slots: dict) -> None:
    for name, data in slots.items():
        save = user / ACCOUNT / TITLE / "00000001" / name / name
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_bytes(data)
        head = user / ACCOUNT / TITLE / "Headers" / "00000001" / f"{name}.header"
        head.parent.mkdir(parents=True, exist_ok=True)
        head.write_bytes(bytes([len(name)]) * 328)
    (user / "achievements").mkdir(parents=True, exist_ok=True)
    (user / "achievements" / f"{TITLE}.toml").write_text("synthetic = true\n", encoding="utf-8")


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)).replace("\\", "/"): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def recover(play: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(RECOVER), "--play-root", str(play), *args], capture_output=True, text=True, check=False)
    return r.returncode, r.stdout + r.stderr


with tempfile.TemporaryDirectory(prefix="r3hd_m20_reg_") as tmp:
    play = Path(tmp) / "play"
    user = play / "profiles" / "testprofile" / "user"
    good_old, other = synthetic_save("wood_11", 1), synthetic_save("intro_15", 2)
    make_user(user, {"RAY1": synthetic_save("wood_11", 3, size=100), "RAY": other})  # RAY1 damaged: short file
    snap_good = play / "save_history" / "20260101-000000" / "000"
    make_user(snap_good / "user", {"RAY1": good_old, "RAY": synthetic_save("intro_10", 9)})
    (snap_good / "snapshot.json").write_text(json.dumps({"index": 0, "reason": "start", "time": "t", "slots": []}), encoding="utf-8")
    snap_bad = play / "save_history" / "20260101-000000" / "001"
    make_user(snap_bad / "user", {"RAY1": synthetic_save("wood_11", 4, magic=b"BBBB")})
    (snap_bad / "snapshot.json").write_text(json.dumps({"index": 1, "reason": "change", "time": "t", "slots": []}), encoding="utf-8")
    snap_partial = play / "save_history" / "20260101-000000" / "002"
    make_user(snap_partial / "user", {"RAY1": good_old})  # no snapshot.json: an incomplete copy
    snap_other = play / "save_history" / "20260102-000000" / "000"  # a session of another profile
    make_user(snap_other / "user", {"RAY1": good_old})
    (snap_other / "snapshot.json").write_text(json.dumps({"index": 0, "reason": "start", "time": "t", "slots": []}), encoding="utf-8")
    for session, profile in (("20260101-000000", "testprofile"), ("20260102-000000", "someone_else")):
        (play / "sessions" / session).mkdir(parents=True)
        (play / "sessions" / session / "launch.json").write_text(json.dumps({"session": session, "profile": profile}), encoding="utf-8")
    (user / ACCOUNT / TITLE / ".staging" / "4294967292.1" / "content").mkdir(parents=True)
    before, history_before = tree(user), tree(play / "save_history")

    code, out = recover(play, "list", "--profile", "testprofile")
    check(code == 0 and "INVALID: size 100" in out and "20260101-000000/000" in out and "INCOMPLETE COPY" in out
          and "header word is not AAAA" in out and "leftover staging directory" in out, "list reports slots, snapshots, damage and leftovers")
    check(tree(user) == before and tree(play / "save_history") == history_before, "list changes nothing")
    code, out = recover(play, "validate", str(user))
    check(code == 1 and tree(user) == before, "validate fails on the damaged profile and changes nothing")
    code, out = recover(play, "validate", str(snap_good / "user" / ACCOUNT / TITLE / "00000001" / "RAY1" / "RAY1"))
    check(code == 0 and "ok (structure only)" in out, "validate accepts a structurally valid save and says what that means")

    code, out = recover(play, "restore", "20260101-000000/000", "RAY1", "--profile", "testprofile")
    check(code == 0 and "DRY RUN" in out and tree(user) == before and not (play / "recovery_backups").exists(), "restore without --apply is a dry run")
    for bad in (("20260101-000000/001", "RAY1"), ("20260101-000000/002", "RAY1"), ("20260101-000000/000", "NOPE"),
                ("../profiles/testprofile", "RAY1"), ("20260101-000000/999", "RAY1"), ("20260102-000000/000", "RAY1")):
        code, out = recover(play, "restore", *bad, "--profile", "testprofile", "--apply")
        check(code == 2 and tree(user) == before and not (play / "recovery_backups").exists(), f"restore refuses {bad[0]} {bad[1]}")
    code, out = recover(play, "restore", "20260101-000000/000", "RAY1", "--profile", "../testprofile", "--apply")
    check(code == 2 and tree(user) == before, "restore refuses a profile that is not a plain name")
    code, out = recover(play, "restore", "20260101-000000/000", "RAY1", "--profile", "missing", "--apply")
    check(code == 2 and tree(user) == before, "restore refuses a missing profile")

    game_absent = "r3hd.exe" not in subprocess.run(["tasklist", "/FI", "IMAGENAME eq r3hd.exe", "/NH"], capture_output=True,
                                                   text=True, check=False).stdout.lower()
    code, out = recover(play, "restore", "20260101-000000/000", "RAY1", "--profile", "testprofile", "--apply")
    if game_absent:
        after = tree(user)
        slot_file = f"{ACCOUNT}/{TITLE}/00000001/RAY1/RAY1"
        slot_head = f"{ACCOUNT}/{TITLE}/Headers/00000001/RAY1.header"
        check(code == 0 and after[slot_file] == good_old, "restore --apply puts the snapshot's save in place")
        check({k for k in after if after[k] != before.get(k)} <= {slot_file, slot_head} and set(after) == set(before),
              "restore touches only the slot's two files (other slot, achievements, leftovers untouched)")
        backups = sorted((play / "recovery_backups").iterdir()) if (play / "recovery_backups").is_dir() else []
        check(len(backups) == 1 and tree(backups[0] / "user") == before and (backups[0] / "restore.json").is_file(),
              "the whole profile as it was is in the backup")
        check(not list(user.rglob("*.m20restore.tmp")), "no temporary file left by the restore")
        check(tree(play / "save_history") == history_before, "the history is never modified")
        code, out = recover(play, "restore", "20260101-000000/000", "RAY1", "--profile", "testprofile", "--apply")
        check(code == 0 and "already identical" in out and len(list((play / "recovery_backups").iterdir())) == 1, "a second restore is a no-op")
    else:
        check(code == 2 and tree(user) == before, "restore refuses while the game is running")

recover_text = read(RECOVER)
check('default=str(ROOT / "private" / "play")' in recover_text and '"--apply", action="store_true"' in recover_text, "restore needs an explicit --apply")
check(recover_text.count("replace_file(src, dst)") == 1 and "os.replace(temp, target)" in recover_text, "restore writes through a temporary file and a rename")
for name in ("m12_save_entry.py", "m18_revisit_check.py", "m19_campaign_check.py", "m20_save_check.py"):
    check("m20_save_recover" not in read(TOOLS / name), f"{name} never calls the recovery tool")

print(f"M20_REGRESSION {'PASS' if failures == 0 else 'FAIL'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)

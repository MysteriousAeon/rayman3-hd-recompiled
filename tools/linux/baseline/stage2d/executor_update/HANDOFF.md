# Stage2D exact systemd-executor correction — preserve every stopped attempt

Keep the original ZIP/runner, `r3hd-stage2d-guard-01`, its guard-preflight.json and
terminal STOP evidence, all native prepared data/workspace/build artifacts untouched.
This creates `r3hd-stage2d-guard-02`, not an edit in place. Do not repeat game/data
preparation or delete anything. No SDK/game rebuild, package install, host policy/
permissions/services change or automatic launch. Only one additional exact service
image path is supported; all canonical path/inode/UID/start/permission/race checks
remain unchanged. Process names/PIDs/PPIDs are not exemptions.

Copy `r3hd-stage2d-executor-update.zip` and sidecar to Downloads. First verify the
report's pinned SHA256, then execute the preparation and **read-only check** block:

```bash
set -euo pipefail
cd "$HOME/Downloads"
sha256sum -c r3hd-stage2d-executor-update.zip.sha256
UPDATE="$HOME/Downloads/r3hd-stage2d-executor-update-01"
test ! -e "$UPDATE" && test ! -L "$UPDATE"
python3 -B - "$UPDATE" <<'PY'
import pathlib,sys,zipfile
p=pathlib.Path(sys.argv[1])
with zipfile.ZipFile('r3hd-stage2d-executor-update.zip') as z:
    names=z.namelist()
    assert len(names)==len(set(names)) and all('/' not in n and '\\' not in n and n not in ('.','..') for n in names)
    assert z.testzip() is None
    p.mkdir()
    for n in names:
        with (p/n).open('xb') as f:f.write(z.read(n))
PY
cd "$UPDATE"
sha256sum -c SHA256SUMS
RUNNER="$HOME/Downloads/r3hd-stage2d-guard-02"
python3 -B "$UPDATE/apply_executor.py" --source "$HOME/Downloads/r3hd-stage2d-guard-01" --output "$RUNNER"
cd "$RUNNER"
sha256sum -c SHA256SUMS
python3 -B "$RUNNER/resume.py" check --allow-protected-inspection
```

Expected update marker: `R3HD_EXECUTOR_UPDATE PASS`. The read-only native check
must independently produce `R3HD_STAGE2D_GUARD SNAPSHOT PASS` before proceeding.
Neither native outcome is claimed in advance. It uses the same explicit optional
sudo observer as before; may request a password in your terminal. Only metadata
inspection is privileged; **never run the game or whole runner with sudo**.
Declining/unavailable sudo, any unresolved image/identity race, missing/changed
source file, existing output or unexpected game-launch state means STOP. Preserve
new/old receipts and return the exact output; no fallback or edits to pass a gate.
The observed PID2088/PPID2083 is not reused as a trusted identifier: every process
is checked afresh. A successful executor snapshot cannot prevent a later exec.

**STOP before game execution.** Only after the new check succeeds and you are
personally ready for visible/audible/physical-input effects, execute:

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-guard-02"
python3 -B "$RUNNER/resume.py" human a --human-present --allow-protected-inspection
```

Type **AUTHORIZE STAGE2D A**. All original gameplay instructions, independent A–F
gates,30minute safety ceiling, logging bounds and optional save/load prerequisites
are unchanged. Use the same already-prepared isolated workspace/HOME; no import,
level shortcut, visible fallback or automatic retry. Do not start another game.

Only if later PhaseB is eligible and personally authorized, substitute this new
runner in the original optional commands; these are not a batch to run blindly:

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-guard-02"
python3 -B "$RUNNER/resume.py" human save --human-present --allow-protected-inspection
```

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-guard-02"
python3 -B "$RUNNER/resume.py" human load --human-present --allow-protected-inspection
```

After the final performed phase, unchanged privacy-limited collection:

```bash
set -euo pipefail
RUNNER="$HOME/Downloads/r3hd-stage2d-guard-02"
python3 -B "$RUNNER/resume.py" collect
cd "$HOME/Projects/R3HD-baseline-noble-2d-01"
sha256sum -c stage2d-private-evidence.zip.sha256
```

Return that pair privately plus new guard-02 guard-preflight.json and any phase
guard JSONs separately. Preserve guard-01's failed receipt separately; do not label
it PASS or overwrite it. No saves/data/rawlogs/credentials are added to collection.

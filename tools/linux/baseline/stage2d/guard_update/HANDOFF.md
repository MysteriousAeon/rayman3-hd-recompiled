# Stage2D protected-process guard update — no automatic launch

Keep the original sealed ZIP, original runner `~/Downloads/r3hd-stage2d-01`, existing
`~/Projects/R3HD-baseline-noble-2d-01` and all evidence unchanged. No SDK/game rebuild,
host installs, permissions/sysctl/service changes or desktop changes. No data recopy.
The reported guard stopped before a/ creation and before any game execution; the
resume check verifies that boundary. Unexpected state means STOP, never delete it.

The secure fallback requires an **optional, explicitly enabled read-only administrator
observer** because the kernel denies unprivileged executable identity access. Names,
cmdline and a separate `ps` inventory cannot authenticate those executables. If you
do not want this administrator read, STOP; do not whitelist names or skip errors.
It uses existing sudo/system Python only, may prompt in the terminal, runs no game
as root, reads no process memory and attaches/signals nothing. The observer itself
makes no system writes (Python bytecode writes disabled); normal sudo authentication/
audit bookkeeping may occur under the existing policy.
It only accepts executable inode identity at these root-owned, non-writable paths:
`/usr/lib/systemd/systemd`, `/usr/bin/kwin_wayland`,
`/usr/lib/polkit-kde-authentication-agent-1`. Any mismatch/deleted or unknown image,
unreadable metadata or race stays STOP. No sudoers/capability/dumpability changes.
No cached authorization or proof file is trusted instead of a fresh check.

Copy `r3hd-stage2d-guard-update.zip` and sidecar to Downloads. First check the pinned
hash in the new report, then execute the following **preparation-only** block:

```bash
set -euo pipefail
cd "$HOME/Downloads"
sha256sum -c r3hd-stage2d-guard-update.zip.sha256
UPDATE="$HOME/Downloads/r3hd-stage2d-guard-update-01"
test ! -e "$UPDATE" && test ! -L "$UPDATE"
python3 -B - "$UPDATE" <<'PY'
import pathlib,sys,zipfile
p=pathlib.Path(sys.argv[1])
with zipfile.ZipFile('r3hd-stage2d-guard-update.zip') as z:
    names=z.namelist()
    assert len(names)==len(set(names)) and all('/' not in n and '\\' not in n and n not in ('.','..') for n in names)
    assert z.testzip() is None
    p.mkdir()
    for n in names:
        with (p/n).open('xb') as f:f.write(z.read(n))
PY
cd "$UPDATE"
sha256sum -c SHA256SUMS
RUNNER="$HOME/Downloads/r3hd-stage2d-guard-01"
python3 -B "$UPDATE/apply_update.py" --original "$HOME/Downloads/r3hd-stage2d-01" --output "$RUNNER"
cd "$RUNNER"
sha256sum -c SHA256SUMS
command -v sudo
test -x /usr/bin/python3
python3 -B "$RUNNER/resume.py" check --allow-protected-inspection
```

The last command is a fresh read-only concurrency check, **not a game launch**.
It may request your password via sudo in this terminal. Inspect `protected_read.py`
first if desired. Do not execute the game/whole runner with sudo. Expected:
`R3HD_STAGE2D_GUARD_UPDATE PASS`, then `R3HD_STAGE2D_GUARD SNAPSHOT PASS`.
No claim of native PASS exists until those actually succeed. Guard result/proofs
are recorded exclusively in the new runner's guard-preflight.json; no PID is an
allowlist and identities are checked again during launch. Rootless operation remains
available without the flag but stops on unresolved denied executables.

On any STOP: preserve old/new runner and workspace, return the exact terminal output
and new guard JSON if present. No fallback, broad cleanup, repeating a partial game
attempt, package install, password automation or permission workaround. A metadata
race may require a separately reviewed new check; do not edit/delete receipts.

**STOP here before game execution.** Only if the check passed and personally ready
to attend visible/audible/physical-input effects, run:

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-guard-01"
python3 -B "$RUNNER/resume.py" human a --human-present --allow-protected-inspection
```

Type **AUTHORIZE STAGE2D A**. All original PhaseA instructions/independent gates,
audio/Wayland routing,30min safety ceiling, log budget, integrity checks and same
isolated workspace apply unchanged. The guard may again request sudo authentication;
only its fixed metadata observer is privileged. No automatic retry or foreground
fallback. A successful snapshot cannot prevent a different process starting later:
do not start other game instances concurrently.

For later optional PhaseB only after the original A gate permits it, replace only
the old human commands with the following; do not run both automatically:

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-guard-01"
python3 -B "$RUNNER/resume.py" human save --human-present --allow-protected-inspection
```

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-guard-01"
python3 -B "$RUNNER/resume.py" human load --human-present --allow-protected-inspection
```

Original genuine-save prerequisites/phase-specific typed phrases remain mandatory.
No new intro_15/save deadline or progression shortcut. Original HANDOFF.md is copied
unchanged for the gameplay instructions; use these new resume commands instead of
its direct gameplay.py human commands. Preparation must **not** be repeated.

After the final attempted phase, original privacy-limited collection stays:

```bash
set -euo pipefail
RUNNER="$HOME/Downloads/r3hd-stage2d-guard-01"
python3 -B "$RUNNER/resume.py" collect
cd "$HOME/Projects/R3HD-baseline-noble-2d-01"
sha256sum -c stage2d-private-evidence.zip.sha256
```

Return that pair privately, plus new runner guard-preflight.json and any guard-a.json /
guard-save.json / guard-load.json separately. These contain technical PID/UID/service
metadata only; no passwords, command lines, process memory, saves or game content.
All original failed terminal evidence remains authoritative and must be kept.

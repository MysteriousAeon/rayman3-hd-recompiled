# Stage2D scoped concurrency controller — no sudo, no service allowlist

Keep guard-01/02, every stopped receipt, original runner/ZIPs, prepared workspace,
data, saves, binaries and caches unchanged. No repeat of game/data preparation,
SDK/game rebuild, host packages, permissions, services or desktop changes.
Use only the new scoped entrypoint below; retire all previous human commands.

Purpose: serialize these revised Stage2D launches and block identified/relevant
ambiguous external games. It is **not proof that every desktop process is non-game**.
Ordinary readable game images are checked independently of comm names. Unreadable
game indicators or live recorded task children STOP. Other unreadable processes
are recorded UNKNOWN, not trusted exemptions. Root/setuid/capable helpers are
outside the ordinary unprivileged target model; no service names are allowlisted.
Without global privileged inspection, deliberately hidden/renamed unknown external
games, another user/root game, other PID namespaces or a later external launch
cannot all be excluded. The person must confirm no other game instance is running.
No password, sudo, memory read, process attach, signal or external-game termination
is used by this concurrency controller.

Copy `r3hd-stage2d-scoped-update.zip` and sidecar to Downloads, verify the report's
pinned hash first, then execute this **non-launch preparation/preflight** block:

```bash
set -euo pipefail
cd "$HOME/Downloads"
sha256sum -c r3hd-stage2d-scoped-update.zip.sha256
UPDATE="$HOME/Downloads/r3hd-stage2d-scoped-update-01"
test ! -e "$UPDATE" && test ! -L "$UPDATE"
python3 -B - "$UPDATE" <<'PY'
import pathlib,sys,zipfile
p=pathlib.Path(sys.argv[1])
with zipfile.ZipFile('r3hd-stage2d-scoped-update.zip') as z:
    names=z.namelist()
    assert len(names)==len(set(names)) and all('/' not in n and '\\' not in n and n not in ('.','..') for n in names)
    assert z.testzip() is None
    p.mkdir()
    for n in names:
        with (p/n).open('xb') as f:f.write(z.read(n))
PY
cd "$UPDATE"
sha256sum -c SHA256SUMS
RUNNER="$HOME/Downloads/r3hd-stage2d-scoped-01"
python3 -B "$UPDATE/apply_scoped.py" --source "$HOME/Downloads/r3hd-stage2d-guard-02" --output "$RUNNER"
cd "$RUNNER"
sha256sum -c SHA256SUMS
python3 -B "$RUNNER/scoped_resume.py" check
```

Expected installer marker `R3HD_SCOPED_UPDATE PASS`. Preflight creates only new
task-control metadata under `~/Projects/R3HD-baseline-noble-2d-control-01` and a
summary in the new runner. It verifies absence of prior launch state and authenticates
the prepared executable. It may report unresolved external identities. Expected
`R3HD_SCOPED_PREFLIGHT READY WITH LIMITS; NO GAME EXECUTION` is **not a global
game-absence PASS**. No native success is claimed before actual execution.
Known conflicts, relevant ambiguity, corrupted registry or lock contention STOP.
Do not suppress an error or add a helper name to pass.

The persistent task.lock is an advisory kernel flock, shared by every revised
Stage2D phase/runner using this same host HOME. The parent holds it through checks,
launch, exit and observations. The actual authorized child inherits the same FD;
the parent only closes its reference, never LOCK_UN. Child PID/boot/start/proc-inode
records provide additional identity checks. A recycled PID is not killed or assumed
to be the old child. Interrupted or stale lock files are never deleted: the kernel
releases ownership when holders exit. A live/orphaned recorded child or unresolved
registration blocks another launch; return metadata for review, do not kill by PID/name.
Child inheritance/retention for the real executable still requires native evidence.
The controller does not defend against a malicious same-user process bypassing it
or altering HOME/control files; old wrappers and unrelated launchers do not obey it.

**STOP before visible launch.** Personally ensure no other r3hd is running; if an
existing game must keep running, do not start this smoke. Remain present for all
window/audio/physical-input effects. No automatic input or focus manipulation.

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-scoped-01"
python3 -B "$RUNNER/scoped_resume.py" human a --human-present
```

First type **I CLOSED OTHER R3HD INSTANCES** to acknowledge the external uncertainty,
then the unchanged **AUTHORIZE STAGE2D A** phrase. A fresh scoped check occurs under
the held lock and immediately before actual spawn. A lock alone cannot prevent
an unrelated launcher racing afterward: do not start anything concurrently.

All original A–F gameplay criteria, private HOME/profile, exact Wayland/Pulse audio
route, integrity/loader checks,30minute ceiling and log/disk budgets still apply.
The original supervisor alone handles its owned group on timeout/Ctrl+C/failure;
the concurrency controller never stops external processes. No new pacing marker,
level shortcut, source change, save import or automatic retry. Invalid answers or
any STOP: preserve evidence and return it. Do not repeat preparation/delete state.

Only when original PhaseB prerequisites permit, personally perform the relevant
optional session (not a batch to run automatically):

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-scoped-01"
python3 -B "$RUNNER/scoped_resume.py" human save --human-present
```

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-scoped-01"
python3 -B "$RUNNER/scoped_resume.py" human load --human-present
```

Each requires both the external-game attestation and original phase-specific phrase.
No intro_15/save-point deadline. Same isolated test profile is retained.

After the final performed phase, unchanged privacy-limited collection:

```bash
set -euo pipefail
RUNNER="$HOME/Downloads/r3hd-stage2d-scoped-01"
python3 -B "$RUNNER/scoped_resume.py" collect
cd "$HOME/Projects/R3HD-baseline-noble-2d-01"
sha256sum -c stage2d-private-evidence.zip.sha256
```

Return that pair privately, new runner scoped-preflight.json/scoped-a.json etc,
and any control-01 child-*.json separately. These contain counts/identity metadata,
not saves, profile contents, command lines or executable contents. Do not send
task.lock/data/HOME/cache directories. Keep every earlier failed proof distinct.

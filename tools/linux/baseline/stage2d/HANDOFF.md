# Stage2D bounded human gameplay — terminal-only CachyOS handoff

Preparation starts no game. Keep all earlier installations, profiles, saves, data,
build workspaces, packages, evidence and caches. No host installs, service/settings
changes, Podman/image creation, source changes or recompilation. This is private
validation, not publication. Do not run via Codex or as an unattended job.

Copy `r3hd-stage2d.zip` and its sidecar to Downloads. First verify the exact pinned
hash in the Stage2D report (not just the accompanying sidecar). Then:

```bash
set -euo pipefail
cd "$HOME/Downloads"
sha256sum -c r3hd-stage2d.zip.sha256
RUNNER="$HOME/Downloads/r3hd-stage2d-01"
test ! -e "$RUNNER" && test ! -L "$RUNNER"
python3 -B - "$RUNNER" <<'PY'
import pathlib,sys,zipfile
p=pathlib.Path(sys.argv[1])
with zipfile.ZipFile('r3hd-stage2d.zip') as z:
    names=z.namelist()
    assert len(names)==len(set(names)) and all('/' not in n and '\\' not in n and n not in ('.','..') for n in names)
    assert z.testzip() is None
    p.mkdir()
    for n in names:
        with (p/n).open('xb') as f:f.write(z.read(n))
PY
cd "$RUNNER"
sha256sum -c SHA256SUMS
df -B1 --output=avail,target "$HOME/Projects"
test "$(df -B1 --output=avail "$HOME/Projects" | tail -n 1 | tr -d ' ')" -ge 12000000000
python3 -B "$RUNNER/gameplay.py" prepare --data-source "$HOME/Projects/R3HD-baseline-noble-2c-pulse-01/installation/data"
```

Expected `R3HD_STAGE2D_PREPARED; NO GAME EXECUTION`. New workspace:
`~/Projects/R3HD-baseline-noble-2d-01`.12GB minimum on the existing filesystem;
no alternative disk or relocation. CoW clone of the **explicitly selected original
test data only**, no hardlinks/copy fallback. Fresh authenticated programs from the
original private binary archive; no imported profiles/Mods/settings/cache/HOME.
Preparation authenticates all Stage2C receipt pairs, original package/LGPL/ABI
inputs, all917 data hashes and packaged915-file manifest. Pulse socket/library
checks are metadata-only until the human launch. Missing/changed input, no CoW,
no owned desktop socket or any STOP: preserve everything, do not install/fallback.

**STOP here unless personally ready to see a window, hear audio and use physical
input.** Disconnect controllers if unwanted. Remain present throughout. Use only
the test window; no scripts injecting input, no focus manipulation, no captures.

## Phase A — one normal New Game, bounded observations

Personally execute this in your native Wayland terminal:

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-01"
python3 -B "$RUNNER/gameplay.py" human a --human-present
```

Type **AUTHORIZE STAGE2D A** at the prompt. The program requires a realTTY; no
background execution. Close any other game instance yourself first; the runner
checks same-user executable metadata and refuses concurrent r3hd, never kills it.
Only explicit Wayland/xenos and verified Pulse-compatible
desktop route are used, with LSFG disabled per process; no backend fallback.

1. Confirm recognizable title/menu. Start **New Game** using normal game menus.
2. Follow normal progression into gameplay. Observe intro_10 and intro_15 **if
   naturally reached**. Level names may be unknown; do not guess. Never use
   `-level:NAME`, a save import, injected state or a progression shortcut.
3. Personally try movement, camera and jumping; note which actually work. Listen
   for audible game sound and obvious distortion. Record graphics anomalies,
   stalls, crashes and unexpected behavior; don't change renderer/system settings.
4. If a genuine save indicator/action occurs naturally, remember the saved progress
   and let saving finish. A settings write, main menu or level name is not a save.
5. Exit using the game's normal Exit option if available; otherwise close only its
   window via X. The questionnaire records which path. Do not kill processes by name.
6. Answer each yes/no/unknown question literally. Questions about save/load may be
   unknown/not applicable on this first launch. Do not answer yes based solely on a
   window, file existence, menu, log marker or an action you did not actually try.

No minimum intro_15/save-point deadline. **30minutes per invocation is a safety
ceiling**, not a progression target; stop earlier if enough has been observed.
Natural blockage means record the furthest point and exit cleanly. If frozen,
disturbing the desktop, abnormal audio/output, crash or serious anomaly: stop at
once (close test window; if unresponsive, Ctrl+C in its terminal). Only the owned
process group can be terminated. Timeout, interrupt, log-budget/low-disk stop,
nonzero/signal exit, unknown/error or anomaly blocks PhaseB; no automatic retry.

Logging is info,4MiB rotation/8 old files, with sampled cumulative48MiB log-write
budget (small sampling overshoot possible), core0; free space below2GB stops the
owned group. No video/screenshots/shader dumps or detailed per-frame traces.
The wrapper records independent A–F gates, **no overall gameplay PASS marker**.
GPU debug-present count may be zero at info level. Vblank is not host pacing;
D3D12 M11 host-present summaries are not required. Raw bounded logs stay native.

## Phase B — optional genuine save/load, only after all Phase A prerequisites pass

Review the independent result first (no execution):

```bash
python3 -m json.tool "$HOME/Projects/R3HD-baseline-noble-2d-01/a/result.json"
```

Continue only with `phase_A_eligible:true`: startup/menu, natural gameplay, all
three basic actions, clear audible audio, integrity/clean runtime and normal exit
established, no observed anomaly. Otherwise STOP and collect. No compulsory save
or intro_15 requirement was added to PhaseA.

If `F_save_write` is already PASS, skip the following save invocation. Otherwise,
**only if continuing normally toward an accessible genuine save is useful**, run
one separately attended session using the same isolated HOME/profile/cache:

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-01"
python3 -B "$RUNNER/gameplay.py" human save --human-present
```

Type **AUTHORIZE STAGE2D SAVE**. Use New Game/Continue as appropriate in the game
UI, never a level override. Identify a real save-triggering action, observe its
completion, remember the location/progress, exit normally and answer honestly.
If no save is accessible naturally, stop cleanly and leave F NOT ESTABLISHED.
Do not grind, import saves or force a checkpoint. Same30minute safety ceiling.

Only after a clean session has **human save observation plus changed nonempty
files under the SDK's title-specific saved-game content type**:

```bash
RUNNER="$HOME/Downloads/r3hd-stage2d-01"
python3 -B "$RUNNER/gameplay.py" human load --human-present
```

Type **AUTHORIZE STAGE2D LOAD**. Choose the actual in-game saved slot/Continue;
verify that the remembered progression returns and is controllable, then exit
normally. Menu alone is not a successful load. The runner refuses absent genuine
save evidence or changed saved-game bytes since the preceding run. It does not
read/modify save contents to manufacture progression. No repeat of an existing
phase; each has a collision-protected directory. A failed/partial save attempt
blocks load. Never edit a result receipt to pass a gate.

## Collect once after the final performed phase (also on failure)

Do not collect between phases if you intend to continue. Once collected the ZIP
is never overwritten. If an early STOP happened before workspace creation, return
only the terminal STOP text; there is no new archive to collect.

```bash
set -euo pipefail
RUNNER="$HOME/Downloads/r3hd-stage2d-01"
python3 -B "$RUNNER/gameplay.py" collect
cd "$HOME/Projects/R3HD-baseline-noble-2d-01"
sha256sum -c stage2d-private-evidence.zip.sha256
```

Return only the new ZIP+sidecar privately, with any human clarification in your
message. The archive contains allowlisted **derived technical JSON/fixed-choice
observations and checksum ledger**, not game data, raw logs, profile/XUID/slot
names, save bytes/hashes, HOME, cache, screenshots, input traces or credentials.
All original raw logs, save metadata and actual saves remain untouched in the
native test workspace for a later focused review if justified. No deletion/cleanup.
This privacy-limited archive attests checked-runner summaries, not independent
replay of full raw logs. Never send the test-user or installation/data directory.

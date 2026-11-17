# One attended menu/gameplay CPU comparison — same accepted Noble home

Preparation only now. No SDK/game build, setup, data copy, installation, settings
change or gameplay automation. Keep all old runners/evidence. This reuses
`~/Projects/R3HD-noble-portable-01/portable` and its private HOME, actual Play.sh,
normal HD+/mod/feature settings, existing desktop Pulse-compatible audio route.
No D3D12 marker, DEBUG/frame trace, profiler, /proc memory, signals to unrelated
processes, global guard, focus or input injection. Device outputs are personally
authorized only at the launch step. Existing E-409 verified helper is required;
do not modify that sealed runner or rerun its integration controller.

## A — check only; no visible window

Copy r3hd-menu-cpu.zip and its .sha256 to Downloads. Verify the independent outer
hash in the checkpoint report first, then run:

```bash
(
  set -euo pipefail
  cd "$HOME/Downloads"
  sha256sum -c r3hd-menu-cpu.zip.sha256
  python3 -B - <<'PY'
from pathlib import Path
import zipfile
p=Path.home()/'Downloads/r3hd-menu-cpu-01'
assert not p.exists() and not p.is_symlink(), 'existing runner: preserve and STOP'
with zipfile.ZipFile(Path.home()/'Downloads/r3hd-menu-cpu.zip') as z:
    names={'cpu.py','timing.py','HANDOFF.md','SHA256SUMS'}
    assert len(z.namelist())==4 and set(z.namelist())==names and z.testzip() is None
    assert all(i.file_size<=60000 and (i.external_attr>>16)&0o170000==0o100000 for i in z.infolist())
    p.mkdir(mode=0o700)
    for n in sorted(names):
        with (p/n).open('xb') as f:f.write(z.read(n))
PY
  cd "$HOME/Downloads/r3hd-menu-cpu-01"
  sha256sum -c SHA256SUMS
  python3 -B cpu.py check
)
```

Expected `R3HD_MENU_CPU PREFLIGHT; NO GAME EXECUTION`. STOP here until personally
ready for one visible launch, sound and configured physical-device outputs.
No program/host changes are made by check. It requires the exact accepted settings,
mod state, previous log and E-410/E-412 evidence, one old session and no prior
R3HD-menu-cpu-01 output. A mismatch is a STOP for review, never a repair request.
The normal launcher still verifies all existing game data. If it unexpectedly
opens setup/repair, do not complete it: Ctrl+C, preserve evidence and STOP.

## B — person alone invokes the one visible launch

Close other Rayman instances/Settings yourself. Keep usual controller connection;
do not plug/unplug devices or change settings/presets/mods during the comparison.
The existing private test profile is backed up locally and verified before launch
(<=512 files/64MB). No save contents leave CachyOS; no automatic restore. Normal
play may write saves/cache in this same test home. No old installation is used.

```bash
python3 -B "$HOME/Downloads/r3hd-menu-cpu-01/cpu.py" human --human-present
```

Real terminal required. Type the exact prompts:

1. `AUTHORIZE ONE MENU CPU COMPARISON`
2. `I CLOSED OTHER R3HD INSTANCES`
3. At the stable actual main menu, physically return to terminal, type
   `MENU READY`, then return to the game within8 seconds. Keep it focused and
   idle for at least75 seconds using your own watch. No script changes focus or
   sends input/sound cues. It samples45 one-second intervals after8 seconds grace.
4. Naturally enter ordinary human-controlled gameplay through the game's menus,
   without `-level`, debug shortcuts or save manipulation. When actually ready,
   type `GAMEPLAY READY`, physically return within8 seconds and play normally
   with the game focused for at least75 seconds. Do not count an intro movie as
   controlled gameplay. No specific level/save point required.
5. Type `BOTH WINDOWS KEPT GAME FOCUSED` only if true. If not, Ctrl+C; preserve
   partial evidence and STOP. Terminal switching can affect pacing: inaccurate
   scene/focus labels cannot be repaired into good measurements later.
6. Exit normally through the game; answer `menu_slowdown_seen` and
   `gameplay_speed_looked_normal` with `yes`, `no` or `unknown`.

There is a15-minute overall safety ceiling, not a progression deadline. If gameplay
cannot be reached naturally, or display/audio/desktop behavior becomes unsafe,
Ctrl+C from the terminal. Only the live, identity-checked owned launcher group may
be terminated. No name-based/global kills or automatic retry. Abrupt terminal/
controller loss may leave the game: close only its own window manually, preserve
everything. Never delete an attempt directory/lock or re-run to clear a failure.

Sampling: process and per-thread CPU tick deltas via /proc at1Hz; correct actual
monotonic intervals and SC_CLK_TCK, percent of one logical CPU. TID/start identities,
exited/new/unreadable threads and partial windows are explicit. No thread names,
instruction sampling, guest memory, GPU load or compositor probing. M16 lateness
and scene hints from retained INFO logs are corroboration; no actual displayed
FPS or M11 Vulkan guest-swap intervals are available. No GPU-wait fix is tested.

## C — one evidence verification, including after STOP

The controller exports filtered evidence once on normal completion or handled
failure. It retains private local profile/configuration backups/console; neither enters the ZIP.
Expected `R3HD_MENU_CPU EVIDENCE READY; measurement only, no causal/compatibility PASS`.
Exit0 means measurement protocol completed; exit2 means preserve partial evidence.

```bash
(
  set -euo pipefail
  cd "$HOME/Projects/R3HD-menu-cpu-01"
  sha256sum -c cpu-private-evidence.zip.sha256
)
```

Return only cpu-private-evidence.zip and .zip.sha256 from that output folder.
If no ZIP exists after interruption/STOP, report terminal error; preserve the
directory and original home. Do not rerun launcher/collector automatically.
Caps:3GB free before,2GB safety floor,64MB retained-log ceiling,256 threads,
8MB export ceiling; normal Standard logging/rotation unchanged. Historical single
session remains byte-checked; one new timestamp session only, far below the normal
ten-session pruning threshold. No previous logs or receipt are rewritten.

No performance, gameplay, controller-output or release PASS is inferred by this
tool. A busy thread would justify attribution, not a timed-wait patch by itself.

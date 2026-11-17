# One attended pause-navigation measurement — preparation and launch are separate

Same canonical Noble `~/Projects/R3HD-noble-portable-01/portable`, its private HOME,
normal Play.sh/settings/Mods/data/Pulse route. No setup, installation, copy of game
data, rebuild, codec/backend fallback or production change. Preserve every old
runner/session/home/backup. Do not rerun old integration or CPU controllers.

Requires original sealed E-409 helper in `~/Downloads/r3hd-normal-portable-01`,
two authenticated existing normal-home sessions, original E-413 CPU evidence at
`~/Projects/R3HD-menu-cpu-01/`, native GSR6.1.0-1.1 and existing `/usr/bin/ffprobe`.
Missing/version/option/hash mismatch is STOP, not permission to install/repair.

## A — verify and check only

Copy only r3hd-pause-measure.zip and .zip.sha256 to Downloads. First verify the
independent outer hash given in the committed report, then run this block:

```bash
(
  set -euo pipefail
  cd "$HOME/Downloads"
  sha256sum -c r3hd-pause-measure.zip.sha256
  python3 -B - <<'PY'
from pathlib import Path
import zipfile
p=Path.home()/'Downloads/r3hd-pause-measure-01'
assert not p.exists() and not p.is_symlink(), 'existing runner: preserve and STOP'
assert p.parent.resolve()==p.parent, 'linked Downloads: STOP'
with zipfile.ZipFile(Path.home()/'Downloads/r3hd-pause-measure.zip') as z:
    names={'pause.py','cpu.py','review.py','timing.py','HANDOFF.md','SHA256SUMS'}
    assert len(z.namelist())==6 and set(z.namelist())==names and z.testzip() is None
    assert all(i.file_size<=100000 and (i.external_attr>>16)&0o170000==0o100000 for i in z.infolist())
    p.mkdir(mode=0o700)
    for n in sorted(names):
        with (p/n).open('xb') as f:f.write(z.read(n))
PY
  cd "$HOME/Downloads/r3hd-pause-measure-01"
  sha256sum -c SHA256SUMS
  python3 -B pause.py check
)
```

Expected `R3HD_PAUSE PREFLIGHT; NO GAME OR RECORDER EXECUTION`. It queries only
package metadata/reads installed documentation and files; no hardware probing.
Needs3GB free/2GB running floor on the existing filesystem. No relocation/deletion.
No output workspace created by check. **STOP until personally ready.**

## B — one personally attended launch and capture

Read the complete timeline below **before** launching. Close other Rayman/Settings
and recording/replay/streaming yourself. Background replay must remain off. Keep
usual controller connection, normal game settings and resolution/mods unchanged.
The game may play sound and use configured physical device outputs. No screen,
game, sound, focus or physical input operation is performed without this personal
command and explicit phrases. Do not leave the session unattended.

```bash
(
  set +e
  python3 -B "$HOME/Downloads/r3hd-pause-measure-01/pause.py" human --human-present
  result=$?
  printf 'Pause controller exit=%s\n' "$result"
  exit "$result"
)
```

Confirm these phrases at the real terminal:

1. `AUTHORIZE ONE ATTENDED PAUSE MEASUREMENT`
2. `I CLOSED OTHER GAMES AND RECORDERS`

Actual normal Play.sh launches once. Existing private profile/config files are
backed up locally/verified before normal game save/cache writes; no automatic
restore or exported saves. Existing game data are verified by the normal launcher;
if setup/repair unexpectedly appears, Ctrl+C and STOP, do not complete it.

First **recorder OFF**: naturally reach active gameplay; physically Escape into
the guest pause, idle briefly, navigate safe adjacent options using separate taps
with full release (~1s apart), idle, resume. Do not use F4/PC Settings, Load,
Restart, destructive confirmations, developer level entry or a movie as gameplay.
Return to terminal, type `OFF CONTROL DONE`, answer `off_before_slowdown` honestly
yes/no/unknown. This is the actual symptom, not idle title-menu speed.

At `AUTHORIZE WINDOW ONLY CAPTURE`, the one recorder starts and a native portal
chooser may appear. **Select ONLY the running game window**. Never select a
monitor/entire desktop. If window selection is missing, wrong or cancelled,
Ctrl+C and STOP; no alternate capture source or retry. Window-only selection is
a human assertion; the runner does not pretend that a filename proves the source.

After the chooser closes, immediately return to terminal (within8s of first
recorded frame) and type `WINDOW ONLY READY`. Then return focus physically to the
game within5s. Do not alt-tab again during the following55s; use your own watch:

| Elapsed after the 5s refocus grace | Human action |
|---|---|
| 0–10s | Ordinary active gameplay |
| 10–20s | Press Escape, guest pause idle; release controls |
| 20–35s | Navigate adjacent safe pause options with separate taps/full release, ~1s apart |
| 35–45s | Remain paused idle, release controls |
| 45–55s | Resume normally, ordinary gameplay |

No beeps, overlay, generated keypresses, cursor/focus manipulation or automation.
These are **planned** boundaries; actual actions are human/visual evidence, not
machine-confirmed phase transitions. If uncertain, answer unknown. The55s sequence
plus refocus/selection-confirmation padding produces approximately60–68s video.
This leaves safety margin under75s; it is not a progression deadline.

Recording ends automatically after the sequence via targeted SIGINT (save), or
the safety bound. CPU sampling continues. Wait about65s after typing READY before
returning to the terminal. A late READY/time bound is partial STOP, no retry.

The recorder is now **OFF**. Reproduce the same Escape/pause-navigation/resume
once more, return and type `OFF AFTER DONE`. Answer the independent yes/no/unknown
observations: slowdown off-after/on, all five phases performed, sustained game
focus, slow animation, felt delayed input, whether recording changed the symptom,
and whether resumed gameplay looked normal. Then exit normally through the game.
Do not extend this into gameplay/save-load/full integration or performance tuning.

Expected `R3HD_PAUSE EVIDENCE READY; private video/metadata only; no causal/performance PASS`.
Exit0 means protocol and structural media/integrity checks completed, not that the
slowdown exists/vanished or any hypothesis passed. Exit2: preserve and return
partial evidence. No fallback, automatic second launch/capture, cleanup or repair.

## Recording, CPU and safety boundaries

Native GSR only: portal, nominal maximum60fps, VFR, MKV, H264 GPU encoding,
CPU fallback explicitly off,12Mb/s CBR bitrate (VFR is independent of bitrate),
no audio source/mic/webcam/plugin/overlay/replay/stream. No VSync/VRR/HDR, compositor,
driver, power, game resolution or feature changes. Original video/PTS unchanged.
Recorder HOME/config/cache/token are confined to new measurement output, keeping
existing recorder settings intact. This different recorder state and capture
load are confounders; no NVIDIA profile is copied/installed as a performance fix.

The first-frame timestamp bounds the clip: save requested at sequence end or70s;
SIGTERM/KILL escalation only if owned recorder fails to exit, by approximately75s.
Such escalation makes the attempt incomplete.75s duration is also checked in the
result file;250MiB per-file limit,4MB recorder log,16MB CPU metadata,64MB game-log
budget,15-minute overall attended limit. Severe OS stalls cannot give a hard
real-time guarantee: stay present; stop if unsafe. Only identity-checked processes
started by this runner may be signalled; no process-name/global desktop inspection.

Continuous1Hz CPU uses owned game PID/executable/start and TID/start counters,
actual elapsed time and one-logical-core percentages; missing/churn explicit.
The first encoded frame supplies monotonic/wall timing anchors; buffering/encoder
latency still matters. No guest-memory reading, new wait hook or DEBUG flood.
Existing M16 summaries are worker timing, not displayed FPS. No D3D12 markers.

After normal game exit, existing ffprobe reads original clip metadata/decoded
frame timestamps only: MKV/H264,one video stream,no audio,positive duration<=75s,
finite increasing PTS. It does not display/transcode/interpolate or save images.
If unsupported or unusable, retain partial original video, not a synthesized fix.
Nominal60fps/encoded-frame count is not60 unique game images or panel scanout.
Physical key latency remains UNKNOWN without independently timed physical input.
Visible animation duration and captured image cadence require later clip review.
Recorder-off/on/off observations screen for perturbation, not zero-overhead proof.

STOP on wrong source/menu, encoder/portal failure, changed hashes/settings, unexpected
setup, unavailable natural gameplay, stall/crash/budget breach or recording visibly
changing the symptom. Ctrl+C stops only owned processes, with partial evidence.
If cleanup is uncertain, manually close only test windows and preserve everything;
never signal a stale PID, rerun, delete or change settings to force a result.

## C — one private evidence collection

Output: `~/Projects/R3HD-pause-measure-01/`. The runner creates one ZIP with original
private MKV only when window selection and recorder exit are confirmed, CPU/receipt/media metadata,
bounded recorder diagnostics and internal hashes. Recorder diagnostics may include
local paths: keep them private. Raw game console/runtime logs, token/state, config
backups and saves stay local. Partial evidence may omit video/media metadata; preserve all originals.
Unexpected audio detected during validation puts the clip on a local privacy hold;
it is omitted from the returned ZIP. No re-encoding/removal of tracks as a fallback.
Do not put the ZIP or video in Git or upload/publish them.

```bash
(
  set -euo pipefail
  cd "$HOME/Projects/R3HD-pause-measure-01"
  sha256sum -c pause-private-evidence.zip.sha256
)
```

Return only `pause-private-evidence.zip` and `.zip.sha256` privately to the Windows
repository evidence area for review. No other directory or private profile files.
If no ZIP exists after abrupt failure, report the error and preserve the folder;
do not relaunch or rerun the attempt. Continue the current coding-agent session.

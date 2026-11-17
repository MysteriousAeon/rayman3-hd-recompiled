# Normal portable integration — existing Noble package, human only

This is not a new game build. All existing homes, data, saves, caches, packages and
receipts remain unchanged. No SDK/game compile, Podman, sudo, packages or downloads.
Do not edit the package or old runners. Do not run a shell command to invoke r3hd.
Only the human command below starts the **actual packaged Settings.sh/Play.sh**.

## A. Preparation only — no GUI/game

Copy `r3hd-normal-portable.zip` and `.zip.sha256` to Downloads. Check the ZIP against
the independently recorded checkpoint SHA first, then run:

```bash
(
  set -euo pipefail
  cd "$HOME/Downloads"
  sha256sum -c r3hd-normal-portable.zip.sha256
  RUNNER="$HOME/Downloads/r3hd-normal-portable-01"
  test ! -e "$RUNNER" && test ! -L "$RUNNER"
  python3 -B - <<'PY'
from pathlib import Path
import zipfile
p=Path.home()/'Downloads/r3hd-normal-portable-01'
names={'integration.py','checks.py','EVIDENCE_LOCK.json','ABI_HASHES.json','settings_core.py','registry.json','content_manifest.tsv','HANDOFF.md','SHA256SUMS'}
with zipfile.ZipFile(Path.home()/'Downloads/r3hd-normal-portable.zip') as z:
    assert len(z.namelist())==len(names) and set(z.namelist())==names and z.testzip() is None
    assert all(i.file_size<=250000 and (i.external_attr>>16)&0o170000==0o100000 for i in z.infolist())
    p.mkdir(mode=0o700)
    for n in z.namelist():
        with (p/n).open('xb') as f:f.write(z.read(n))
PY
  cd "$RUNNER"
  sha256sum -c SHA256SUMS
  python3 -B integration.py check
  python3 -B integration.py prepare
)
```

Expected `R3HD_PORTABLE_PREPARED; NO UI OR GAME EXECUTION`. **STOP here** until
personally ready for all attended stages. Preparation authenticates existing Noble
archive and provenance evidence, hashes existing915-file game content, extracts
program files to new `~/Projects/R3HD-noble-portable-01/portable`, creates a private
HOME/XDG under `os-home`, and checks all five host ELF loader closures. It does not
copy game data or initialize portable settings. The actual setup will copy the
verified existing content normally, once, when you choose its Folder.

Prerequisites checked later on CachyOS, not claimed from Windows: existing python3,
tkinter, KDE Wayland/XWayland DISPLAY/authentication, owned Wayland and Pulse sockets;
native nonroot x86-64,12,000,000,000 free bytes for preparation,4GB before attended
sequence,2GB stop floor. No alternative disk or relocation. Missing prerequisite:
STOP and return reason; do not install/change host configuration in this task.

Only these existing inputs are read:

- Noble package under `~/Projects/R3HD-baseline-noble-2b-egl-01/work/private/work/linux_build/noble_2b01/`.
- `~/Projects/R3HD-linux-provenance-01/provenance-private-evidence.zip` (pinned SHA).
- Content source `~/Projects/R3HD-baseline-noble-2d-01/installation/data/content`.

Source content is never modified. No old profiles/settings/Mods/cache are imported.
Do not supply a known-good installed home as the test destination.

## B. Personally authorized user experience — real windows, sound and physical input

Close every other r3hd/Settings window yourself. Disconnect controllers you do not
want the game to open. Remain at the desktop. This sequence may capture the game
cursor/focus normally and may write controller LEDs/triggers/speaker when enabled.
No automation, focus manipulation, global input injection or hidden fallback.

Run once:

```bash
python3 -B "$HOME/Downloads/r3hd-normal-portable-01/integration.py" human --human-present
```

Type `AUTHORIZE NORMAL PORTABLE INTEGRATION`, then `I CLOSED OTHER R3HD INSTANCES`.
For each stage type the printed START phrase; each prior script/window must exit.

1. **START SETUP:** actual Settings.sh shows setup because this home has no data or
   settings. Choose **Folder** and the exact verified content source above. Choose
   **HD+**. Uncheck application-menu registration (any accidental registration goes
   to isolated XDG, not your normal menu). On Finish click **Finish only**, neither
   Play nor Settings. Confirm setup GUI and no game launch. Unexpected launch: STOP.
2. **START SETTINGS:** actual Settings.sh now opens Settings. Confirm HD+, Combo
   Meter Animation On, Gameplay subtitles On, desired normal DualSense options.
   Change and Save one recognizable preference (e.g. mouse sensitivity); note it.
   Confirm Mods tab. If you have an authorized mod ZIP/folder, personally import it
   here only, enable it and Save as appropriate. No automatic existing-mod import.
   If unavailable, leave mod-state/application observations **not-exercised**.
   Controller speaker is normally Off: enable it in this GUI only if you want its
   separate physical-output check. This is opt-in, never silently forced Off/On.
   Do not click Play/menu-entry buttons. Close Settings normally.
3. **START REOPEN:** Settings.sh again. Verify the preference and chosen mod state
   survived closing/reopening. Do not edit; close. Answer not-exercised for mod
   persistence if no actual mod selection was tested (an empty tab is not proof).
4. **START PLAY:** first type `AUTHORIZE PLAY AND CONFIGURED DEVICE OUTPUTS`.
   Actual Play.sh uses this home/settings/mod plan, without test R3HD_* overrides.
   In the game's own Options enable **Subtitles**: the launcher gameplay-subtitle
   preference alone does not enable the title's option. Start/play normally; no
   `-level:` shortcut. Observe menu/basic human gameplay and clear game audio.
   F3 must not open the SDK overlay; F4 must open PC Settings. Change/Apply one
   preference there, remember it. Observe voice subtitles during gameplay outside
   cutscenes and a scoring combo
   final-second exit if naturally reached; no specific level/progression deadline.
   Observe physical DualSense input, **light**, **R2 resistance**, **speaker**
   separately. Speaker needs a naturally occurring supported effect (power-up
   jingle/pickup/warning/expiry); endpoint detection is not audible speaker proof.
   Unreached scene/effect/device stays not-exercised. Do not force progression.
   Exit normally using guest menu or window X. Menu slowdown is reported separately
   and remains an OPEN issue; no tuning or driver/power changes.
5. **START VERIFY:** Settings.sh after game exit. Verify the F4 preference appears
   here after restart, without editing it. Close. No save/reload campaign.

Every observation is `yes/no/not-exercised`; machine logs and human answers are
separate. Questions never constitute a result before the person actually observes.
Subtitles/Combo and each device output have independent results. Missing optional
scene/mod/device does not falsify setup/basic-launch evidence; it leaves that
specific acceptance unestablished. No aggregate all-features/gameplay PASS.
Standard logging retains only two rotated5MB files plus the active file. Startup/
API markers can disappear normally. They corroborate observations, not gate them.
Feature/device PASS means human observation with its actual selected configuration;
it is not an API/driver certification. runtime_clean covers script exits and flags
in retained logs only, not a complete-history absence-of-errors proof.

Stop conditions: script nonzero exit, game crash/hang, refusal, integrity problem,
unexpected pre-Play game, loss of main display/audio or unsafe device behavior.
An unavailable optional device/effect is not-exercised; uncertainty never becomes yes.
Close only test windows or Ctrl+C this controller. It supervises only its own
process group (TERM then KILL on limit/interrupt), never processes by name.30min per
window/script is a safety ceiling, not a gameplay progression requirement. Sampled
cumulative log-growth budget96MB and2GB disk floor; core dumps disabled. Normal
logging/preset behavior stays intact, no DEBUG-only or D3D12 marker requirement.

Shared task file lock serializes this one controller; no broad /proc service
allowlist or sudo observer. The normal packaged process checks also remain intact.
Human attestation is still required: unrelated/hidden/later external launches cannot
be excluded by this lock. Any prior steps/task.lock means preserve/STOP; no retry.
An abruptly interrupted controller may leave a child: close the test yourself and
return receipts; no automatic stale-PID killing or cleanup.

Environment: private HOME/XDG files; existing Wayland/X11/Xauthority, desktop DBus
and explicitly verified Pulse socket only. No daemon autospawn; SDL audio uses the
previously verified desktop Pulse-compatible route. No project feature flags are
disabled and no direct executable arguments replace the launcher. Normal video
backend selection remains visible in logs; actual backend is recorded, not assumed.
The existing launcher session.json is read after play to verify home/profile/cache
roots, SDK-overlay suppression and selected feature-to-environment mapping; raw
paths/bindings/mod IDs are not exported. No diagnostic launch plan replaces it.
Controller-speaker endpoint availability on this explicit Pulse route remains a
native question: record an unavailable/unheard endpoint separately, with no audio
backend fallback, host rerouting or service changes.

## C. One evidence collection, also after failure

After all test windows have closed, run once and type `TEST WINDOWS ARE CLOSED`:

```bash
python3 -B "$HOME/Downloads/r3hd-normal-portable-01/integration.py" collect
(
  set -euo pipefail
  cd "$HOME/Projects/R3HD-noble-portable-01"
  sha256sum -c portable-private-evidence.zip.sha256
)
```

Return privately only `portable-private-evidence.zip` and its `.zip.sha256` from
that new workspace. Evidence contains technical receipts, enum settings, mod counts/
state hash and derived markers/human observations; no raw runtime/session logs,
Xauthority/bus addresses, game content, mod assets, screenshots, profiles or saves.
Raw bounded logs remain in the new home for later narrow diagnosis if needed.
Do not delete or overwrite a failed attempt/evidence file. Save/load, full-game,
SteamOS/Deck and menu-performance resolution are explicitly outside this milestone.

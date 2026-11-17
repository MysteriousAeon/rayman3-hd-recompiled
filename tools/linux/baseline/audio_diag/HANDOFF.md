# Stage2C one attended audio-route diagnostic

Historical preparation: native diagnostic has returned. Do not repeat this handoff.
Title/menu observed, child exit0; original wrapperFAIL from D3D12-only pacing gate
preserved. [Authenticated result and current boundary](../../../../reports/LINUX_BASELINE_STAGE2C_PULSE_RESULT_2026-11.md).

This is a new experiment, not an automatic retry or a proven game fix. Keep the
failed `R3HD-baseline-noble-2c-visible-01` workspace/evidence and every earlier
installation, image, source, save and cache unchanged. No host installs, service
changes, new images, SDK/game builds or production changes. No debugger/core dump.

Copy the report's checked ZIP+sidecar to Downloads. Verify its pinned SHA256 from
the report first, then use exact terminal commands on native CachyOS:

```bash
set -euo pipefail
cd "$HOME/Downloads"
sha256sum -c r3hd-stage2c-pulse-diag.zip.sha256
RUNNER="$HOME/Downloads/r3hd-stage2c-pulse-diag-01"
test ! -e "$RUNNER" && test ! -L "$RUNNER"
python3 -B - "$RUNNER" <<'PY'
import pathlib,sys,zipfile
p=pathlib.Path(sys.argv[1])
with zipfile.ZipFile('r3hd-stage2c-pulse-diag.zip') as z:
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
python3 -B "$RUNNER/forensic.py" "$HOME/Projects/R3HD-baseline-noble-2c-visible-01/visible-private-evidence.zip"
```

Expected all checksums OK and `AUTHENTICATED FAILURE`, exit-5/SIGTRAP. The latter
authenticates the previous failure, not a new launch. Retain12GB available on the
same existing filesystem; no relocation. New binaries about105MB; CoW content
about2.08GB logical size but initially shared extents.12GB conservatively budgets
private logs/cache/writes. No source archive or large download required.

Explicitly choose the **failed isolated test's verified data tree only**; no known-good
home, profiles, settings, Mods, translations or source package import:

```bash
set -euo pipefail
RUNNER="$HOME/Downloads/r3hd-stage2c-pulse-diag-01"
python3 -B "$RUNNER/audio_diag.py" prepare --data-source "$HOME/Projects/R3HD-baseline-noble-2c-visible-01/installation/data"
```

This starts no game/SDL/audio stream. It authenticates previous receipts/current
binary package/LGPL source/ABI; checks all917 source data files against the authenticated prior inventory; reads owned host audio-socket metadata and existing libpulse version;
creates `~/Projects/R3HD-baseline-noble-2c-pulse-01`; extracts original programs and
CoW-clones only the verified915 content files plus intake receipt/icon (`cp --reflink=always`, no hardlinks/copy fallback).
It rehashes source and clone and runs packaged full content verification. Original
content is only read. No saves or old runtime state are copied. Expected:
`R3HD_PULSE_PREPARED; NO GAME EXECUTION`.

Missing owned `XDG_RUNTIME_DIR/pulse/native` socket, libpulse, wrong runtime owner/
mode0700, linked path, insufficient space, CoW failure, modified content/receipts or
existing workspace means STOP. Do not install/start a service, change permissions,
select ALSA/dummy or relax a gate. Preserve partial artifacts; collect available logs
and return evidence. The host metadata check is not proof the server can open a stream.

**STOP before launch.** Only a person remaining present may separately authorize
window/focus/cursor/sound/physical input/controller effects. Disconnect controllers
if unwanted. No unattended execution, automated answers/input or visible fallback.
This command requires realTTY and the personally typed exact phrase
`AUTHORIZE VISIBLE AUDIO INPUT STARTUP`:

```bash
RUNNER="$HOME/Downloads/r3hd-stage2c-pulse-diag-01"
python3 -B "$RUNNER/audio_diag.py" human --human-present
```

The new child retains private HOME/all XDG directories and old bounded runner guards.
Only explicit owned Wayland and PulseAudio-compatible sockets are accessible through
environment routing. `SDL_AUDIO_DRIVER=pulseaudio` forces that single compiled backend,
`PULSE_SERVER=unix:<owned host runtime>/pulse/native` selects the existing server;
private client configuration disables autospawn and automatic localhost/X11 discovery.
No host cookie/config is imported or changed. Existing DBus addresses stay private/
nonexistent. LSFG remains disabled per-child. No other driver/backend/ABI/render setting
or binary changes. `audio-route.json` records exact socket/library/config identities.
If cookie/authentication/socket/stream connection fails, STOP; do not copy credentials
or retry with another driver. Desktop routing may be PipeWire's PulseAudio service;
neither service type nor working endpoint is claimed in advance.

Observe recognizable intro/title/menu content, idle at least15s for600-present sample,
then close **only this test window** normally before120s. No campaign/settings/save/
controller tests. If no content within30s, a crash/error or desktop disturbance occurs,
Ctrl+C this terminal and STOP. Hard bound120s then owned-groupTERM/3s/KILL; forced stop,
crash/SIGTRAP/remaining group remains FAIL. No processes are killed by name.

Answer the visible-content question honestly. Diagnostic PASS requires the original
XEX/runtime/launch/host-present ladder, natural0, visible content, unchanged binaries/
all915 files, plus logged successful audio endpoint open and no recurrentR6025/bugcheck.
Only the exact known benign `ResolvePath(\D:\Gamedata)` optional probe is classified
separately; every other error remains a failure. No criteria bypass for signal exit,
audio error, wrong pixels or no content. A stream-open record is not audio correctness.

Interpretation: endpoint opens and old fatal disappears -> supports audio availability
as the trigger; if endpoint opens but fatal recurs -> hypothesis weakened; route fails
before open -> cannot decide guest cause, return logs; a different error -> review new
failure. Even PASS is bounded startup evidence only, not gameplay/save/audio/input/
other-distro/Deck acceptance. No repeat in an existing attempt.

Collect after preparation failure or the one launch (use a new terminal if needed):

```bash
set -euo pipefail
RUNNER="$HOME/Downloads/r3hd-stage2c-pulse-diag-01"
python3 -B "$RUNNER/audio_diag.py" collect
cd "$HOME/Projects/R3HD-baseline-noble-2c-pulse-01"
sha256sum -c pulse-private-evidence.zip.sha256
```

Current and default20 rotated runtime logs are retained/analyzed in chronological order.
Return only this ZIP+sidecar privately. Allowlisted technical metadata/logs only;
no content, saves, profiles, HOME, caches, recordings, screenshots or credentials.
If preparation stopped before workspace creation there is nothing new to collect;
return the terminal STOP text. Preserve everything; no cleanup in this procedure.

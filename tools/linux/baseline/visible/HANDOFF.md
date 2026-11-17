# Stage2C bounded human-attended owned-data startup

No agent/unattended target execution. Preparation starts no game. This is a new
installation, not a continuation/retry in an old workspace. Keep all earlier inputs,
evidence, images, caches, working homes and saves. No package installation, privileges,
new image, SDK/game compilation or system configuration changes are needed.

Copy the checked ZIP and sidecar from the report's final private folder into Downloads.
Verify the report's full SHA256 first, then run this terminal-only block on CachyOS:

```bash
set -euo pipefail
cd "$HOME/Downloads"
sha256sum -c r3hd-stage2c-visible-startup.zip.sha256
RUNNER="$HOME/Downloads/r3hd-stage2c-visible-startup-01"
test ! -e "$RUNNER" && test ! -L "$RUNNER"
python3 -B - "$RUNNER" <<'PY'
import pathlib,sys,zipfile
p=pathlib.Path(sys.argv[1])
with zipfile.ZipFile('r3hd-stage2c-visible-startup.zip') as z:
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
```

Expected every checksum OK and at least12,000,000,000 bytes available. Same filesystem,
no relocation. Roughly2.2GB extracted content/programs plus transient staging/cache/logs;
12GB is a conservative startup budget, not a full-game cache estimate. Source original
package must already be accessible on Linux; script does not discover/download it.
Do not use a known-good installed content folder. Do not copy saves/settings/mods.
If original package is unavailable, STOP; no alternative automatic import.

Explicitly enter the **original legally owned Xbox360 package file** when prompted:

```bash
set -euo pipefail
RUNNER="$HOME/Downloads/r3hd-stage2c-visible-startup-01"
read -r -p 'Absolute path to your original legally owned Xbox360 package file: ' SOURCE
test -f "$SOURCE"
python3 -B "$RUNNER/visible.py" prepare --source "$SOURCE"
```

The source must match2,095,038,464 bytes/SHA256
`18bccaff1ca8298147b21f21142c756c3da328face135a519327180c96d07517`.
It is read only; before/after hashes checked. This deliberately supports only the
authenticated original package, not a different release/content tree.
Packaged portable engine verifies all content through its existing integrity rules,
extracting into `~/Projects/R3HD-baseline-noble-2c-visible-01/installation` with private
preparation HOME/XDG, no session display/bus. Expected marker:
`R3HD_STAGE2C_VISIBLE_PREPARED; NO GAME EXECUTION`.

**STOP here.** Only proceed if you personally authorize possible window/focus/cursor,
sound and physical input/controller effects and can stay present for the whole test.
The next command asks for exact `AUTHORIZE VISIBLE AUDIO INPUT STARTUP`; type it
yourself, never pipe answers. Disconnect physical controllers first if you do not
want possible device outputs. This is not a hidden or unattended-safe runner.

```bash
RUNNER="$HOME/Downloads/r3hd-stage2c-visible-startup-01"
python3 -B "$RUNNER/visible.py" human --human-present
```

The native guard refuses WSL/root/non-amd64. One attempt only. Fresh package/source/
previous receipts and all program binaries are authenticated; data inventory must be
unchanged. All915 content files are also reverified against the authenticated shipped
manifest before/after entry (not only a mutable local inventory). Five ELF closures are checked immediately before entry. Independent launch
HOME/XDG, new test-user/test-cache, only the owned current Wayland socket shared;
no inherited R3HD/loader injection variables. X11 fallback is not provided.
LSFG's native-log-advertised `DISABLE_LSFG=1` applies to this child only. Host graphics
driver/ICD remains in use; no driver files/settings are changed. Prior observed LSFG
configuration under the old private HOME remains preserved. Discord/optional DualSense
light/trigger/speaker options are off, but this is **not** a guarantee of no physical
input/audio/device effects once Runtime is constructed.

Remain present. Observe recognizable intro/title/menu content and leave it idle for at least15 seconds
(to permit the600-present pacing sample), then close **only this test window** normally
within120 seconds. No gameplay/campaign, save import, mod or
settings exercise. No automated/global input. If no window/content appears within30s,
or a crash/error/desktop disturbance occurs, interrupt this terminal with Ctrl+C and
STOP; do not start another copy. Wrapper timeout120s sends TERM to its own group,
waits3s then KILL; timeout/interruption/leftover group is FAIL even if milestones exist.
No debugger/core capture; child core limit zero only. Never kill by executable name.

After exit answer yes/no honestly to the visible-content question. No visible frame
is inferred from a swapchain. Natural exit0, positive observation, Wayland/plugin/
swapchain, exact XEX/runtime/launch markers and M11 host_present pacing in order, unchanged files,
and no logged error/LSFG-active/hidden-window marker are required for bounded PASS.
Natural exit1 is no longer expected. PASS still proves neither a completed normal
startup campaign nor gameplay/audio/input/save correctness or other distributions.
Any unmet criterion: preserve all artifacts and return evidence; no visible/driver/
toolchain fallback, silent retry or SDK rebuild.

Collect after PASS or failure (in a fresh terminal if set-e ended the old block):

```bash
set -euo pipefail
RUNNER="$HOME/Downloads/r3hd-stage2c-visible-startup-01"
python3 -B "$RUNNER/visible.py" collect
cd "$HOME/Projects/R3HD-baseline-noble-2c-visible-01"
sha256sum -c visible-private-evidence.zip.sha256
```

Privately return only `visible-private-evidence.zip` and its sidecar. Collector uses
an explicit technical-file allowlist; no game files, saves, profiles, shader caches,
private homes, screenshots or input/audio recordings. No overwrite: existing runner,
workspace, attempt or collected ZIP means STOP and preserve it. A partial preparation
is not resumable automatically; collect logs and request review in the current session.
No cleanup is part of this handoff.

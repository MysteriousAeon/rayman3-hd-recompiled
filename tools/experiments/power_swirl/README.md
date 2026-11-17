# Integrated HD+ swirl visual comparison (E-445 / D-218)

Acceptance update (2026-11-12; E-446): maintainer human visual PASS for the blue
LockJaw swirl in enabled Windows A/B case B, matching intended original-PC visuals.
The bounded Windows swirl milestone is closed. Acquisition/expiration were not
separately reported; other colors/scenes, Fist/Vortex coverage, full GPU-state and
production replay qualification remain limited/open. No repeat test needed for
closure. The preparation instructions below are historical procedure, not a new
acceptance request. [Current scope](../../../reports/post_release/POWERUP_SWIRL_HDPLUS_BRIDGE.md).

Current private candidate: native3014 geometry/materials restored in HD+; Vanilla
keeps original HD behavior. Human visual acceptance and full production replay
qualification remain pending. [Evidence and limitations](../../../reports/post_release/POWERUP_SWIRL_HDPLUS_BRIDGE.md).

Prepare isolated save copies (no game starts):

```powershell
python tools/experiments/power_swirl/prepare_visual_ab.py
```

Open the printed private folder. A.cmd: swirl off; B.cmd: swirl on, other HD+
settings identical. Each asks you to type PLAY before starting human gameplay.
Continue RAY1 at Knaar_20; follow the normal route to the first blue LockJaw can.
Watch pickup, move away, watch expiration, then exit normally before the other
case. Check shape/placement, blue color, animation/fade and unrelated effects.
Separate copied profiles are used; registered save and user settings are preserved.
The launcher refuses a changed executable hash. Mods are off only in this isolated
comparison. No claim of final visual acceptance until the maintainer confirms it.

Existing workspace for this checkpoint:
private/work/power_swirl/acceptance/20261112_041954_cd931de1.
Both modes were validated with visual_ab.ps1 without -Manual (dry run only).

Focused hidden_check.py/judge.py reuse the approved hidden runner and native
read-only metadata/scoped-input infrastructure. All raw outputs stay private.
Do not repeat failed Fist/Vortex routes or original-PC tests without a new hypothesis.

Historical PC observer instructions follow; that human experiment is complete.

# One human-controlled PC pickup observation

E-441 update: first human test completed successfully; yellow swirl reported at both
pickup and expiry, without sampled91/169/subanimations. See the [result](../../../reports/post_release/POWERUP_SWIRL_NATIVE_TRACE.md).
Do not repeat this experiment without a new discriminating hypothesis. Instructions
below retain the tested procedure as historical reference.

Ready for the first controlled live validation (D-213 / E-440). This attaches to
an existing original-PC session; it never starts or controls gameplay.

## Human instructions

1. Start `D:\Games\Rayman 3\Rayman3.exe` normally, without administrator mode.
   Enter gameplay and stand near one power-up can. Prefer no active power-up, so
   the pickup changes the power code. Do not punch/charge during this test.
2. From the repository root, run this in PowerShell:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\experiments\power_swirl\attach_pc_pickup.ps1
   ```

3. Wait for `PC_SWIRL_OBSERVER READY` and its output filename. If it says
   `REFUSED`, stop and report that message; do not perform the pickup test yet.
4. Return to the game yourself and collect **one** power-up within45 seconds.
   Watch whether a colored spiral appears around Rayman's body. Avoid attacks.
5. The observer stops automatically. Report the power-up/color, whether the swirl
   appeared (yes/no/uncertain), and any attack or unusual event during the interval.
   The pickup's power-code change is timestamped automatically; an approximate
   delay after READY is helpful if no power change was recorded.
6. Keep the displayed JSONL file. It is created exclusively under
   `<repo>\private\work\power_swirl\pc_pickup\pickup_<timestamp>_<unique>.jsonl`.
   Return its filename with your observation. No screenshot is required.

The command uses the first installed `python` application (tested Python3.11 x64).
The execution-policy option applies only to that PowerShell invocation; it changes
no persisted policy. No elevation or debug privilege is requested. If there are
multiple Rayman3 processes, pass `-GameProcessId <existing-ID>`; the Python side
still verifies the exact executable path, hash, architecture and loaded image.

Disk-only preflight, which never attaches or creates a log:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\experiments\power_swirl\attach_pc_pickup.ps1 -CheckOnly
```

## What this can establish

The observer reads the player's power mirror, main animation index and active
subanimation list. It marks power changes with elapsed seconds, logs changes plus
half-second heartbeats, and flags animation91/169 as the known helix-animation
path. Their charged-fist use was already established; it is not re-investigated.

**Limitations before the test:** it does not observe rendered objects, draws,
colors, native effect factories or actual frame-specific mesh visibility. The
subanimation `frame_parameter` is not a verified current-frame counter. An active
91/169 therefore identifies a candidate animation path, not a visible helix draw.
No direct per-object activity claim is made. Same-power reacquisition can leave
the mirror unchanged; do not infer no pickup from no power-change marker.

Live player traversal is **UNTESTED** until READY succeeds in this session. Reads
are asynchronous, nominally at most20Hz; short activity can be missed. Guarded
samples detect some concurrent changes, not a fully atomic snapshot. The footer
records maximum valid-sample gap and unstable-sample count. A refusal, incomplete
log, large sampling gap or absent visible swirl cannot prove the effect is missing.
Do not combine this observation with memory/performance measurements.

## Attachment, bounds and safety

- Expected game: supplied2,916,704-byte x86 PE32 executable, pinned SHA256
  `64deefd3a7b14a32124aa9b31ebba84e1a7c9a4a54ee40d9b65b4043ff1be15c`.
  Fixed image base00400000, no dynamic-base flag. Requires64-bit Python and
  x64 Windows with IsWow64Process2; the game must report x86 WOW64. Normal same-user
  access is intended; process ACL/integrity can still refuse it. No elevation fallback.
- Attachment is OpenProcess with only QUERY_LIMITED_INFORMATION|VM_READ (1010hex).
  Other kernel calls are QueryFullProcessImageNameW, IsWow64Process2,
  ReadProcessMemory and CloseHandle. No process write, injection, debugger, thread
  suspension or input/control API. The wrapper only enumerates named existing processes.
- The executable is opened only for reading/hash verification. No executable,
  installation configuration, save, profile or control file is opened for writing.
  The sole output is a new exclusive-create JSONL in the dedicated private folder;
  existing evidence is never overwritten, and resolved paths outside it are refused.
- Wrapper duration45s, at most900 sample attempts. Direct CLI maximum60s/1200 attempts.
  Log limit1MiB including reserved footer; player-read budget8MiB (plus70 bytes of
  loaded-image header validation). Discovery max512 objects, subanimation max24 nodes,
  individual player reads max256 bytes. Stop on invalid layout, unavailable memory,
  exhausted budget or manual Ctrl+C; close the handle, leave the game running.
- Schema2 footer status is complete/aborted. No footer means incomplete evidence.
  This is a human-visible observation, not an unattended or hidden game test.

## Validation and later analysis

Actual checks:18 focused tests PASS, including synthetic sampling/power timing,
output containment/no overwrite, byte budget, abort footer, race/out-of-bank
refusal, rights/architecture gates and end-to-end synthetic metadata output.
Real Windows API read/query/architecture bindings passed on this test process's
own synthetic buffer, under a non-elevated account. No game was attached.
Wrapper disk-only preflight PASS against the supplied installation; help PASS.
Initial wrapper checks exposed script-policy refusal and multiple Python results;
the command above and first-application selection resolve those preparation issues.
No game/installation/private input changed and no game-runtime build was needed.
Documentation links/IDs/index and whitespace checks pass; the full documentation
checker retains four pre-existing historical-text failures. Starting bodies of all
eight updated state/evidence books were verified preserved.

After the person returns: validate footer/coverage and power-change timing first;
compare visible-swirl timing with main/subanimation91/169 and any attack. If the
swirl is present without that animation activity in well-sampled data, prioritize
the separate native effect/render path. If correlated, trace the creation cause
before proposing a restoration. Neither outcome alone proves causation or missing
HD behavior. No HD+ implementation or beam recoloring is authorized by this test.

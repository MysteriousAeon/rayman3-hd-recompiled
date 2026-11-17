# Supplemental Stage 2B finalization and Stage 2C first probe

Run on CachyOS only. This does not rebuild, install host packages, run r3hd, open a
window or access audio/input/GPU devices. No Codex is needed on Linux. Keep every
previous attempt. Use this handoff, not any earlier full build/retry command.

Copy `r3hd-baseline-final-and-probe.zip` and its `.sha256` sidecar to Downloads.
Compare the ZIP SHA256 with the committed closure report before extraction.

```bash
set -euo pipefail
cd "$HOME/Downloads"
sha256sum -c r3hd-baseline-final-and-probe.zip.sha256
RUNNER="$HOME/Downloads/r3hd-baseline-final-and-probe-01"
test ! -e "$RUNNER" && test ! -L "$RUNNER"
mkdir "$RUNNER"
python3 -B -m zipfile -e r3hd-baseline-final-and-probe.zip "$RUNNER"
(cd "$RUNNER" && sha256sum -c SHA256SUMS)
TASK="$HOME/Projects/R3HD-baseline-noble-2b-egl-01"
OLD_RUNNER="$HOME/Downloads/r3hd-stage2b-egl-manifest-01"
FINAL="$HOME/Projects/R3HD-baseline-noble-2b-final-01"
PROBE="$HOME/Projects/R3HD-baseline-noble-2c-01"
test ! -e "$FINAL" && test ! -L "$FINAL"
test ! -e "$PROBE" && test ! -L "$PROBE"
df -B1 --output=avail,target "$HOME/Projects"
```

Every checksum must say OK. Native scripts require >=1,000,000,000 available bytes
on the existing workspace filesystem before each phase (about 105 MB unpacked
program files plus small logs; no new image, source copy or SDK build). Do not sum
filesystem space or relocate storage. Existing Python3, glibc loader, readelf and
Git must be available; a missing command is a stop, not a host installation request.
Original corrected toolkit, stopped workspace and all build/package artifacts must
still exist. No Podman creation/build/pull is required. The original evidence ZIP,
corrected check/acceptance, preserved prefixed record, source manifest, all source
pins/patches and selected receipts must authenticate against the locked evidence.

The expected original prefixed record is
`$TASK/evidence/package-check-original-prefixed.txt`. Missing/different evidence
stops; do not copy/reformat/repair records to satisfy the script.

```bash
if python3 -B "$RUNNER/native.py" finish --task "$TASK" --runner "$OLD_RUNNER" --dest "$FINAL"; then
  FINAL_EXIT=0
else FINAL_EXIT=$?; fi
printf 'Supplemental finalization exit=%s\n' "$FINAL_EXIT"
if test -f "$FINAL/OWNER.txt"; then
  python3 -B "$RUNNER/native.py" collect --dest "$FINAL"
fi
test "$FINAL_EXIT" -eq 0
(cd "$FINAL" && sha256sum -c SHA256SUMS && sha256sum -c DELIVERABLES.sha256 && sha256sum -c supplemental-private-evidence.zip.sha256)
```

Expected marker: `R3HD_STAGE2B_SUPPLEMENTAL_FINALIZATION PASS; original orchestration exit=2 retained`.
`finalization.json` must say supplemental PASS, original exit2, uninterrupted false,
game_executed false, publishable false. DELIVERABLES.sha256 binds the exact existing
binary package and LGPL source archive using their absolute paths. It is a **new
supplemental ledger**, not a retroactive original-run artifact. Old workspace and
toolkit are read only to the procedure. No old acceptance/exit/log/check file is rewritten.

Only after that block passes, run the isolated minimal probe:

```bash
if python3 -B "$RUNNER/native.py" probe --final "$FINAL" --dest "$PROBE"; then
  PROBE_EXIT=0
else PROBE_EXIT=$?; fi
printf 'Stage 2C loader/portable probe exit=%s\n' "$PROBE_EXIT"
if test -f "$PROBE/OWNER.txt"; then
  python3 -B "$RUNNER/native.py" collect --dest "$PROBE"
fi
test "$PROBE_EXIT" -eq 0
(cd "$PROBE" && sha256sum -c SHA256SUMS && sha256sum -c supplemental-private-evidence.zip.sha256)
```

Expected: five native host-loader closures exit0, all packaged component hashes
unchanged; packaged Python `prepare --no-input` exits2 with PACKAGE_REQUIRED (the
expected stop at absent game data). The wrapper then exits0 and emits
`R3HD_STAGE2C_LOADER_PORTABLE PASS; r3hd entrypoint NOT EXECUTED; runtime acceptance PARTIAL`.
`probe.json` must explicitly keep game_entrypoint_executed false, gameplay UNKNOWN,
graphics/audio/input NOT TESTED. No game content/saves/settings are copied or linked;
the fresh installation and HOME/XDG directories live only inside the new PROBE folder.
Desktop/session/injection/test variables are absent from the child environment.

The loader uses `--list` on each authenticated ELF, never its entrypoint. This checks
actual CachyOS DT_NEEDED/provider-version resolution, not runtime-loaded Vulkan/ICD,
SDL device initialization or gameplay. `r3hd --help` is deliberately excluded: the
pinned cvar parser catches the CLI help exception and can continue into SDL video.
No safe game-launch fallback is authorized here. A real startup needs an approved
Linux nonintrusive runner or a separately authorized human launch, after review.

Any collision, changed/missing file, source or package failure, nonzero loader exit,
unexpected portable result, timeout or new user state: STOP and retain everything.
Do not retry into existing folders, remove artifacts, change pins or install tools.
Completed phases may be checked repeatedly with their sha256sum blocks; rerunning
creation deliberately refuses existing destinations. A partial phase requires review.
If failure precedes output-folder creation, retain terminal output. Otherwise the
collector packages only top-level technical receipts/logs, never installation files.

Return each new folder's `supplemental-private-evidence.zip` and its `.sha256`, named
with the originating folder so the two ZIPs are not confused. Do not overwrite the
original Stage2B evidence ZIP. Keep the binary package/LGPL source pair local and
private. Stop after these bounded checks; no game launch, compatibility campaign,
publication, desktop integration, profile migration or known-good home changes.

# One read-only Linux metadata collection — no launch or rebuild

Copy only `r3hd-linux-provenance.zip` and its `.sha256` sidecar to CachyOS Downloads.
Verify the outer SHA against the independently supplied report/checkpoint first.
This is one collector, not a product build. No Codex, sudo, Podman, installs or new
images are needed. Use existing python3 and sha256sum. Do not run Play/Settings,
even their dry-run modes, for this collection.

Personally close the game and Settings before collecting; do not change any home
until collection ends. The collector neither enumerates nor terminates processes.
It only reads fixed program/manifest/config paths, never game content, saves,
profiles, sessions, logs, mod assets or caches. Selected settings are enum-filtered;
comments, arbitrary configuration strings, user/profile/mod IDs are not exported.
Normal filesystem read-atime updates, if enabled by the host, are not suppressed.

Known locations checked, with no recursive disk search:

- LX2F and LX2RED: their portable home under `~/Games/R3HD-LX2F/` and
  `~/Games/R3HD-LX2RED/`, respectively. Exactly one direct/nested portable.json
  must exist per home; ambiguous/missing locations produce a gap receipt.
- Noble: existing `~/Projects/R3HD-baseline-noble-2d-01/installation` and pinned
  `~/Projects/R3HD-baseline-noble-2b-egl-01/work/private/work/linux_build/noble_2b01/r3hd-linux-noble-2b01.tar.gz`.
- Optional LX2F/LX2RED/LX2D package archives at
  `~/Projects/RaymanLM1/private/work/linux_build/native_lma/` with their normal
  `r3hd-linux-lx2f.tar.gz`, `r3hd-linux-lx2red.tar.gz`, `r3hd-linux-lx2d.tar.gz` names.
  Missing optional archives are recorded; never move or regenerate them.

Only new outputs: `~/Downloads/r3hd-linux-provenance-01` (four toolkit files) and
`~/Projects/R3HD-linux-provenance-01` (one evidence ZIP and checksum). Existing
paths cause refusal; do not delete/overwrite/retry. Input read budget: 180 seconds,
200 MB per file, 500 MB expanded per archive; 16,000,000 free output bytes required.
Typical reads are a few hundred MB, writes below 1 MB. No binaries are copied.

Run this single block **after checking the report's exact outer SHA**:

```bash
(
  set -euo pipefail
  cd "$HOME/Downloads"
  sha256sum -c r3hd-linux-provenance.zip.sha256
  RUNNER="$HOME/Downloads/r3hd-linux-provenance-01"
  test ! -e "$RUNNER" && test ! -L "$RUNNER"
  python3 -B - <<'PY'
from pathlib import Path
import zipfile
p=Path.home()/'Downloads/r3hd-linux-provenance-01'
with zipfile.ZipFile(Path.home()/'Downloads/r3hd-linux-provenance.zip') as z:
    assert len(z.namelist())==4 and set(z.namelist())=={'collect.py','LOCK.json','HANDOFF.md','SHA256SUMS'}
    assert z.testzip() is None
    assert all(i.file_size<=100000 and (i.external_attr>>16)&0o170000==0o100000 for i in z.infolist())
    p.mkdir(mode=0o700)
    for n in z.namelist():
        with (p/n).open('xb') as f:f.write(z.read(n))
PY
  cd "$RUNNER"
  sha256sum -c SHA256SUMS
  python3 -B collect.py check
  if python3 -B collect.py collect; then RESULT=0; else RESULT=$?; fi
  printf 'Metadata collector exit=%s\n' "$RESULT"
  EVIDENCE="$HOME/Projects/R3HD-linux-provenance-01"
  if test -f "$EVIDENCE/provenance-private-evidence.zip.sha256"; then
    cd "$EVIDENCE"
    sha256sum -c provenance-private-evidence.zip.sha256
  fi
  test "$RESULT" -eq 0
)
```

Expected toolkit marker: `R3HD_PROVENANCE_TOOLKIT PASS; NO NATIVE CHECKS OR GAME EXECUTION`.
Expected complete collection marker: `R3HD_PROVENANCE COMPLETE_METADATA_ONLY`.
This authenticates bytes/metadata only, never gameplay, portable setup or feature use.
LX self-consistent manifests without independently pinned package identity remain
`LOCAL_MANIFEST_ONLY`; that is not a release provenance certification.

On exit2 / STOP_WITH_GAPS: retain and return the evidence pair if produced. Do not
repair an installation, change a manifest, copy a package, rerun setup or retry.
Missing/changed/unreadable/linked/oversized/ambiguous inputs need Windows review.
Permission errors are not silently treated as absent. Interruption may leave a
partial output folder; preserve it and report the console message, with no cleanup.

Return privately only these two files:

```text
~/Projects/R3HD-linux-provenance-01/provenance-private-evidence.zip
~/Projects/R3HD-linux-provenance-01/provenance-private-evidence.zip.sha256
```

The bundle contains derived program hashes, filtered selection metadata and its
internal checksum ledger. No raw portable/settings/installer/mod-state JSON, code,
archives or private content are transferred. After return, authenticate/reconcile
on Windows and update the authoritative inventory. **Stop: no gameplay commands.**

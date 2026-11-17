# Existing Noble retained timing evidence — no launch

Do not run Play.sh/Settings.sh for this collection. Close any test game normally
yourself before starting. No setup, new game-data copy, host installation, Podman,
sudo, process control, settings changes or repeat integration. Keep every existing
home, log and archive. This collector reads only the accepted normal home and
writes one new evidence directory. It cannot measure historical CPU use.

Copy r3hd-menu-retained.zip and its .sha256 to Downloads. Verify the independent
outer hash in the checkpoint report first. Run this entire block once:

```bash
(
  set -euo pipefail
  cd "$HOME/Downloads"
  sha256sum -c r3hd-menu-retained.zip.sha256
  python3 -B - <<'PY'
from pathlib import Path
import zipfile
p=Path.home()/'Downloads/r3hd-menu-retained-01'
assert not p.exists() and not p.is_symlink(), 'preserve existing runner; STOP'
with zipfile.ZipFile(Path.home()/'Downloads/r3hd-menu-retained.zip') as z:
    names={'timing.py','HANDOFF.md','SHA256SUMS'}
    assert len(z.namelist())==3 and set(z.namelist())==names and z.testzip() is None
    assert all(i.file_size<=50000 and (i.external_attr>>16)&0o170000==0o100000 for i in z.infolist())
    p.mkdir(mode=0o700)
    for n in sorted(names):
        with (p/n).open('xb') as f:f.write(z.read(n))
PY
  cd "$HOME/Downloads/r3hd-menu-retained-01"
  sha256sum -c SHA256SUMS
  python3 -B timing.py
  cd "$HOME/Projects/R3HD-menu-evidence-01"
  sha256sum -c menu-private-evidence.zip.sha256
)
```

Expected: all checksums OK, then
`R3HD_MENU_RETAINED READY; NO GAME EXECUTION; CPU UNKNOWN` and final ZIP OK.
Return privately only:

- `~/Projects/R3HD-menu-evidence-01/menu-private-evidence.zip`
- `~/Projects/R3HD-menu-evidence-01/menu-private-evidence.zip.sha256`

Read budget: <=8 runtime logs, <=32MB each, <=96MB total, twice for stability;
program verification reads the existing program payload twice, no game data.
Output <=4MB JSON plus compressed ZIP; no raw lines, guest/shader bytes, game data,
saves, settings text, mod IDs, usernames, arbitrary filenames or screenshots.
Existing source files are not rewritten. Warning categories/fingerprints and
whitelisted timing fields only; no PASS/FAIL for slowdown or benign-warning claim.

STOP on any error, missing/different accepted evidence, manifest/program/settings
hash mismatch, missing/multiple session directories, linked/changed/oversized log,
or existing runner/output. Do not repair inputs, remove locks/directories, rerun
setup, retry game, alter log settings or delete anything. Preserve terminal error
and all directories for review. An interrupted export may leave an incomplete new
directory; keep it. There is no automatic retry or visible fallback.

The manifest is pinned to native E-408; accepted receipt ZIP to E-410. Runtime
logs were not previously transferred, so their hashes establish a new retained
snapshot, not a retroactive proof they equal the original run at collection time.
If another launch/session was made meanwhile, STOP for provenance review.

After Windows review, decide whether a new measurement is necessary. This handoff
does NOT authorize or launch a new game. Missing CPU or M11 Vulkan statistics
remain UNKNOWN; do not infer zero CPU/frames or enable DEBUG/frame traces. Any
future CPU sampling must be bounded, read-only, per-thread identity-aware, and use
the existing normal launcher/settings with a separate personal launch action.

# Portable ZIP packaging workflow

The public portable edition is available starting with v1.0.3. Player instructions
are in `tools/installer/PORTABLE.txt`; approved release notes are in
`docs/releases/V1_0_3_RELEASE_NOTES.md`. The workflow below remains private by
default. Explicit `--public-release` packaging accepts a separately approved public
payload and checks its contents; that flag does not grant distribution rights.
The historical review boundaries below describe development preparation.

The installed edition is unchanged. This optional package uses its `app/`, `bin/`
and home layout, with independent user files beside the application. It neither
installs into AppData nor discovers/migrates another edition's profile.
The complete player contract is `tools/installer/PORTABLE.txt`, shipped at the ZIP
root. This workflow produces private development artifacts only. It does not
select a future release number, update v1.0.2, or authorize publication.

## Build and package

E-298 / D-127 scopes technical distribution validation to the sensitive-content
delta against the installer. Private matched development packaging is verified;
no new sensitive component was found. The inherited R-01 question remains
unresolved and does not independently block the ZIP's technical verdict. The
earlier E-297 literal no-key/no-new-ZIP boundary belongs to that historical task.
Nothing here authorizes public distribution. Clean Windows execution is still
NOT TESTED; see reports/post_release/PORTABLE_FINAL_DISTRIBUTION_VALIDATION.md.

Run the authoritative `tools\build_milestone8.bat` first. A host-only native probe
and `r3hd_portable_regression.py` are included. The runtime manifest declares UTF-8
for the process because the SDK converts Windows command-line arguments to UTF-8
but constructs host filesystem paths from narrow strings. Windows 10 version 1903
or newer is required for portable use; no global Windows code-page change is made.
No generated PPC translations are edited.

Stage normally into a new private output folder:

```powershell
python tools/r3hd_stage.py build private/work/portable/STAGE
python tools/r3hd_stage.py portable private/work/portable/STAGE --portable-out private/work/portable/portable-dev.zip --development-id portable-dev --crt-dir "<VC redist retail x64 Microsoft.VC145.CRT directory>"
python tools/r3hd_portable_zip.py check private/work/portable/portable-dev.zip
```

The CRT source directory is explicit, not a developer-machine default. Exact file
names/hashes/version are pinned in `config/release/portable_crt.json`; a mismatch
refuses packaging. Changing those pins requires dependency/release review.
The ZIP builder reuses the staged payload, its audit and R-01 boundary. It omits
the two installer console command files and recomputes the portable payload ID;
the base payload ID is retained in `portable.json`. The native launcher and DLLs
are otherwise copied byte for byte from the stage. It adds the preparation tool,
two top-level command files, instructions, CRT DLLs/notices, and the matching LGPL
source archive. Existing stages and output archives are never overwritten.

Actual members, hashes, Python/CRT pins, exact release-definition paths, known
game-file hashes and developer paths in binaries are checked from the written
ZIP. Fixed timestamps, sorted names, fixed metadata and compression make repeated
packaging deterministic with the pinned Python/zlib environment. Outputs include
`.zip.sha256` and `.zip.manifest.json`; every inner file except the manifest itself
is hashed in `portable.json`. Checksums establish integrity, not authenticity.

## Matched installer and ZIP workflow

Use the existing M50 builder after a verified runtime build, with a new private
output directory and an explicit pinned retail CRT source:

```powershell
python tools/m50_build.py private/NEW_PAIR --record-runtime private/runtime-hashes.json
python tools/m50_build.py private/NEW_PAIR --expect-runtime private/runtime-hashes.json --portable-id distribution-dev --crt-dir "<retail x64 Microsoft.VC145.CRT directory>"
python tools/r3hd_portable_zip.py compare-stage private/NEW_PAIR/stage private/NEW_PAIR/dist/Rayman3HDRecompiled-distribution-dev-portable.zip
python tools/r3hd_matched_package_regression.py
```

Both formats use the same stage, application version, runtime, Settings executable,
notices and corresponding source. The final comparison reads actual ZIP and stage
bytes; only the two installed console entry points are omitted. The installer
retains its existing setup/shortcut/mod policy. The ZIP retains portable entry,
app-local CRT and independent home policy. MANIFEST.json records all shared hashes,
base payload ID and source digest; SHA256SUMS.txt covers the installer, ZIP, source,
manifest and ZIP sidecars. A pair requires a new directory under private/, refuses
test-variant/reused-stage combinations, and remains publishable=false.

The ZIP is byte-reproducible for fixed inputs and the pinned compression environment.
This does not promise byte-identical Inno installers or time-stamped outer manifests;
shared payload/source identities are the reproducible installer/ZIP correspondence.
Current version metadata is preserved; development IDs do not choose a public version.

## Extraction and updates

The one top-level directory is `Rayman3HDRecompiled-Portable/`:

```text
Play.cmd                    Settings.cmd              PORTABLE.txt
portable.json               payload.json
app/                        bin/
r3hd-lgpl-source-<application-version>.zip
```

`Play.cmd` and `Settings.cmd` locate the bundled Python relative to themselves.
Preparation validates program files (with the two LGPL exceptions below) and game data, then uses the existing engine's
lock, intake, staging, commit journal and recovery. First preparation asks for the
owner's package/extracted tree and creates Vanilla settings with the existing
fresh-home preferences. Invalid existing settings are preserved and refused.
Damaged game data is reacquired without resetting user state. Missing components
require fresh extraction. No registry entry, shortcut, elevation or download is
performed. The unchanged native launcher starts only after preparation succeeds.

All settings, profiles, saves, history, mods, game data, cache and session logs
live in this home. No root or individual `R3HD_*` environment override is inherited
through these entry points. Linked user/program directories are refused to avoid
accidental sharing. A restricted home fails without falling back to another
location. Moving/renaming the complete home preserves relative paths.

For updates, extract into a **new** folder. With game and Settings closed, back up
both homes and explicitly copy settings.json, profiles/, save_history/, mods/,
sessions/, data/ and any dev_overlay_config/. Do not copy program files, manifests,
installer.json, home markers or transaction files. New preparation verifies copied
data and preserves settings byte for byte. Overlay updates are unsupported and a
state/payload mismatch refuses startup. No merge, downgrade migration, in-place
ZIP updater or broad profile manager is introduced. Keep the old home until the
new one and saves have been checked.

Installed/portable switching uses the same explicit backup/copy policy. Both keep
independent files and the existing single-game/Settings guards remain. Deleting
the portable home deletes its user files too: back them up first. Never share a
used home or this private prototype. The Windows setup/repair/uninstaller is for
installed homes; do not point it at a portable home.

## Verification and release limits

Current distribution verdict and user-reported human PASS7/7:
`reports/post_release/PORTABLE_LGPL_REPLACEMENT_AND_R01.md` (E-297). Clean Windows
runtime remains NOT TESTED. Portable startup permits different sizes/hashes only
at `bin/ffmpeg.dll` and `bin/mspack.dll`, after checking that each has a Windows
x64 DLL header. This permits a replacement attempt; Windows loading and actual
runtime use determine compatibility. All other manifest hashes, game identities,
reparse-point refusals and unlisted app/bin file checks remain strict. Original
ZIP audits always verify both LGPL hashes too. Keep originals outside app/bin;
see `tools/installer/LGPL-SOURCE.txt` for ABI and loader/dependency limits. No
search-path change, extra DLL location or automatic library restore is introduced.
Relocation retains replacements; fresh-folder updates need deliberate reapplication
after auditing the new ZIP. Installed startup/explicit repair are unchanged.
Prepared portable homes check app-local CRT in Play preflight;
installed homes keep the system-runtime check. The actual PowerShell preflight
can be checked without a game using `python tools/r3hd_portable_preflight_regression.py`.
The report records the matched future installer/ZIP workflow over a single stage;
no future version or public candidate has been selected.

```powershell
python tools/r3hd_portable_regression.py --archive PRIVATE.zip
python tools/r3hd_portable_lgpl_regression.py
python tools/r3hd_portable_lgpl_regression.py --original-bin ORIGINAL_BIN --replacement-bin MODIFIED_BIN
python tools/r3hd_portable_acceptance.py PRIVATE.zip private/extracted/5841123F private/work/portable/ACCEPTANCE --mod PRIVATE_TRANSLATION.zip
```

The acceptance command uses real private data copies and actual extracted tools,
native `--no-ui`/Play dry-run/private-desktop Settings tests, relocation, real ACL
write denial, mod import and PE dependency inventory. It starts no game. The
established M6 runner separately verifies the extracted runtime under hidden,
muted, controller-suppressed conditions. No visible window or global input is used.
These automated checks are distinct from human Play/gameplay acceptance and a
clean non-developer Windows machine test.

The installer-specific notice that Microsoft CRT DLLs are absent is supplemented
by `app/licenses/PORTABLE-CRT.txt`: this ZIP adds pinned retail app-local DLLs.
Microsoft's redistribution list and licensed-Build-Tools terms still apply.
Corresponding LGPL source is inside the ZIP; proprietary game data and translation
mods are not. Inherited translated runtime machine code and its acknowledged R-01
retail-key carrier remain private release-review concerns. A technical PASS is
not legal clearance or a claim that this artifact satisfies a no-key publication
requirement. A future version, release review, human acceptance and explicit
publication authorization remain separate. See the focused report for results.

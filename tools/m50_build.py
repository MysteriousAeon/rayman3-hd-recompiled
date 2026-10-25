#!/usr/bin/env python3
"""M50 (D-089): build the 1.0.1 release candidate with the M49 builder (tools/m49_build.py, same arguments, same
refusals) plus the release checks of M50. Nothing is uploaded; OUT/dist is never replaced.

    python tools/m50_build.py OUT --expect-runtime HASHES.json [--test-variant NAME --dpi-proxy PT] [--fast]
    python tools/m50_build.py OUT --record-runtime HASHES.json

Added checks on the staged payload (refusal = exit 2, nothing written to OUT/dist):
  * R-01 keys (tools/m50_r01_audit.py keys): the only key constant in any staged file is the XEX2 retail key, once,
    in bin/rexruntime.dll; the kernel key 0x19 is gone (tools/m50_runtime_patch.py).
  * licence files: the corresponding-source archive carries the licence of the project's M46 build files
    (tools/installer/LGPL-BUILD-FILES-LICENSE.txt) and the payload the third-party notices.
The manifest records both results.
"""
import json
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m49_build as b  # noqa: E402
from m48p_build import ROOT, Refused  # noqa: E402

b.VERSION = "1.0.1"
b.SETUP_NAME = f"Rayman3HDRecompiled-{b.VERSION}-setup.exe"
b.TAG = "M50_BUILD"
# D-108: the final Turkish translation (D-106 / D-107: the person's 65 LQA proposals verbatim, the U+2026 glyph, the
# achievement text). It needs the mod tools of fe24b37 or later, which the payload stages from this tree.
# D-110: the same package with its final authors / license fields (tools/release_turkish_metadata.py; every override and
# the achievement file byte-identical to 16c754e3...).
b.MOD = ROOT / "private" / "release_1.0.1" / "turkish_final" / "rayman3hd-turkish-1.0.1.zip"
b.MOD_SHA256 = "348b1ea7584fd2f0cc6cd9cb1cdcfaa7e4ab5378b5c6a7f3c97cc278f7789f97"
b.MOD_VERSION = "1.0.1"
b.MOD_SOURCE = ("final LQA candidate private/work/lqa_ellipsis_20261025/mod_candidate (E-258): 1.0.0 + 65 approved "
                "texts + the U+2026 glyph + achievements/achievements.json; authors / license set (D-110, "
                "tools/release_turkish_metadata.py)")
b.CLASSIFICATION = ("RELEASE CANDIDATE - private, not published. R-01 (redistribution of the translated code and the "
                    "XEX key) is an acknowledged open question, not cleared: docs/licensing/R-01.md")


def r01_keys(payload: Path) -> dict:
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "m50_r01_audit.py"), "keys", str(payload),
                        "--base", str(payload)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    if d["unresolved"]:
        raise Refused(f"R-01 key audit could not resolve {d['unresolved']}")
    hits = {row["file"].replace("\\", "/"): row["hits"] for row in d["files"] if row["hits"]}
    if hits != {"bin/rexruntime.dll": {"xe_xex2_retail_key": 1}}:
        raise Refused(f"R-01 key audit: unexpected key constants {hits}")
    return {"r01_keys": {"carriers": hits, "placeholders": [k["name"] for k in d["keys"] if k["placeholder"]],
                         "removed": [k["name"] for k in d["keys"] if k["removed_from_source"]]}}


def licence_files(payload: Path) -> dict:
    stage = payload.parent
    zips = sorted(stage.glob("r3hd-lgpl-source-*.zip"))
    if len(zips) != 1 or zips[0].name != f"r3hd-lgpl-source-{b.VERSION}.zip":
        raise Refused(f"expected r3hd-lgpl-source-{b.VERSION}.zip in {stage}, found {[z.name for z in zips]}")
    with zipfile.ZipFile(zips[0]) as z:
        names = set(z.namelist())
        man = json.loads(z.read("r3hd-lgpl-source/MANIFEST.json").decode("utf-8"))
    need = {"r3hd-lgpl-source/LGPL-BUILD-FILES-LICENSE.txt", "r3hd-lgpl-source/ReXGlue-SDK-LICENSE.txt",
            "r3hd-lgpl-source/FFmpeg/COPYING.LGPLv2.1", "r3hd-lgpl-source/libmspack/libmspack/mspack/lzxd.c"}
    if not need <= names or man.get("program_version") != b.VERSION:
        raise Refused(f"LGPL archive: missing {sorted(need - names)} or version {man.get('program_version')}")
    notices = payload / "app" / "THIRD_PARTY_NOTICES.txt"
    lic = payload / "app" / "licenses"
    for f in ("disruptorplus-LICENSE.txt", "DirectXShaderCompiler-LICENSE.txt", "FFmpeg-COPYING.LGPLv2.1.txt",
              "libmspack-COPYING.LIB.txt", "LGPL-SOURCE.txt", "rexglue-LICENSE.txt",
              "Rayman3HDRecompiled-LICENSE.txt"):
        if not (lic / f).is_file():
            raise Refused(f"payload: app/licenses/{f} missing")
    if not notices.is_file():
        raise Refused("payload: THIRD_PARTY_NOTICES.txt missing")
    return {"lgpl_archive_files": len(names)}


b.EXTRA_CHECKS[:] = [r01_keys, licence_files]

if __name__ == "__main__":
    sys.exit(b.main())

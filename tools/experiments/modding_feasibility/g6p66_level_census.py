#!/usr/bin/env python3
"""G6-P66 (E-552): read-only census of every level file with the editor's own readers (numbers and hashes only).

    python tools/experiments/modding_feasibility/g6p66_level_census.py [LEVEL ...]   -> private/work/g6p66_census

Per level: lvl / ptr / transit SHA-256; static scene (r3hd_level_scene.Scene: objects, triangles, draw modes, skipped
links, textures and how many decode); the remix model (r3hd_level_editor_core.RemixModel with the level's own hashes
pinned in memory for this census only: actors by status, graphs, waypoints, collision). Game files are only read.
"""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
import r3hd_mods as rm  # noqa: E402
import r3hd_level_scene as sc  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402

OUT = REPO / "private" / "work" / "g6p66_census"


def census(game, lv):
    r = {}
    t0 = time.time()
    lp, pp, _ = rm.script_level_files(game, lv)
    tp = lp.with_name("transit.lvl")
    r["hash"] = {"lvl": rm.sha256_bytes(lp.read_bytes()), "ptr": rm.sha256_bytes(pp.read_bytes()),
                 "transit": rm.sha256_bytes(tp.read_bytes()) if tp.is_file() else None}
    try:
        s = sc.Scene(game, lv)
        sm = s.summary()
        r["scene"] = {k: sm[k] for k in ("objects", "objects_non_identity", "elements", "triangles",
                                         "textured_triangles", "skipped", "modes")}
        r["scene"]["textures"] = len(sm["textures"])
        ok = bad = 0
        for key in s.textures:
            try:
                s.decode_texture(key, max_side=16)
                ok += 1
            except Exception:
                bad += 1
        r["tex_decode"] = {"ok": ok, "bad": bad, "total": len(s.textures)}
    except Exception as x:
        r["scene_err"] = f"{type(x).__name__}: {x}"
    pinned = lv in core.REMIX_LEVELS
    try:
        if not pinned:
            core.REMIX_LEVELS[lv] = dict(r["hash"], note="census")
        m = core.RemixModel(game, lv)
        r["remix"] = m.counts()
        r["remix"]["models"] = len({a["name"] for a in m.actors.values()})
        r["remix"]["experimental_models"] = sorted({a["name"] for a in m.actors.values()
                                                    if a["status"] == "experimental"})
    except Exception as x:
        r["remix_err"] = f"{type(x).__name__}: {x}"
    finally:
        if not pinned:
            core.REMIX_LEVELS.pop(lv, None)
    r["secs"] = round(time.time() - t0, 1)
    return r


def main():
    game = Path(core.mod_paths()["game"])
    levels = sys.argv[1:] or sorted(p.name for p in (game / "GAMEDATAbin").iterdir()
                                    if p.is_dir() and (p / f"{p.name}.lvl").is_file())
    out = {}
    for lv in levels:
        out[lv] = census(game, lv)
        print(lv, json.dumps({k: v for k, v in out[lv].items() if k != "hash"}, default=str)[:400], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    name = "census.json" if not sys.argv[1:] else "census_" + "_".join(levels)[:80] + ".json"
    (OUT / name).write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Offline D-199 audit against the owner's data. Writes optional private previews only.

Checks plan confinement, unmodified source/metrics, untouched base compression blocks,
native verifier readiness and conservative mod collision. Not in-game visual proof.
"""
import argparse
import hashlib
import json
from pathlib import Path

import r3hd_button_prompts as p
import r3hd_mods as m
import r3hd_loc as loc


def audit(game, work):
    work.mkdir(parents=True, exist_ok=True)
    paths = [game / f"GAMEDATAbin/fix.{ext}" for ext in ("lvl", "bhf", "btf")]
    before = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in paths}
    out = p.prepare(game, work / "plan")
    assert out["plan"], out
    plan = Path(out["plan"])
    ranges = []
    files = []
    for line in plan.read_text().splitlines():
        if line.startswith("file "):
            files.append(Path(line.split(" ", 2)[2]))
        if line.startswith("range "):
            fields = line.split(" ", 7)
            ranges.append((files[int(fields[1])], int(fields[2]), Path(fields[7]).read_bytes(), fields[6]))
    assert len(files) == 1 and files[0].resolve() == paths[-1].resolve()
    patched = bytearray(paths[-1].read_bytes())
    end = 0
    for _, off, data, _ in ranges:
        assert off >= end and off + len(data) <= len(patched)
        patched[off:off + len(data)] = data
        end = off + len(data)
    fix = paths[0].read_bytes()
    records = m.font_records(fix, m.FONT["others"][0])
    checks = 0
    stats = {}
    for name in (m.FONT["atlas"], "menu\\mnu_xb512_en.dds"):
        tex = p.texture(game, name)
        _, e, w, h, lay, blobs, _ = tex
        rects = p.MENU_RECTS
        if name == m.FONT["atlas"]:
            rects = [(records[c][0], records[c][1], records[c][0] + records[c][3],
                      records[c][1] + records[c][2]) for c in p.BUTTONS]
        allowed = {(x // 4, y // 4) for x0, y0, x1, y1 in rects
                   for x in range(x0, x1) for y in range(y0, y1)}
        modified = 0
        for by in range(h // 4):
            for bx in range(w // 4):
                off = (h // 4 - 1 - by) * lay[0][2] + bx * 16
                same = blobs[0][off:off + 16] == patched[e[2] + off:e[2] + off + 16]
                assert same or (bx, by) in allowed, (name, bx, by)
                checks += 1
                modified += not same
        new_blobs = (patched[e[2]:e[2] + e[1]], patched[e[4]:e[4] + e[3]])
        preview = m.decode_level(w, h, m.level_rows(new_blobs, lay[0], "DXT5"), "DXT5")
        # Dark compositing is only for inspection; plan pixels retain their alpha.
        image = bytearray(preview)
        for at in range(0, len(image), 4):
            alpha = image[at + 3]
            image[at:at + 4] = bytes([(preview[at + c] * alpha + 35 * (255 - alpha)) // 255
                                     for c in range(3)] + [255])
        (work / ("font.png" if name == m.FONT["atlas"] else "menu.png")).write_bytes(m.write_png(w, h, image))
        stats[name] = {"base_blocks_checked": w * h // 16, "base_blocks_changed": modified}
    # Deliberately overlapping mod must retain priority; no new prompt plan is served.
    assert p.overlaps_mod(plan, ranges)
    assert not p.overlaps_mod(None, ranges)
    assert before == {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in paths}
    # Reproducible, explicitly synthetic tutorial specimen; no registered save or
    # guest state is edited. Only this private read plan changes the displayed text.
    off, slot = loc.string_at(fix, loc.tables(fix), "en.471")
    context = {"game": game, "cache": work / "specimen_cache"}
    specimen = m.compile_texts([{"offset": off, "slot_sha256": m.sha256_bytes(slot),
        "text": "Prompt test: \\f1:c a b d 1 2 3 4\\f0:"}], context, frozenset(), m.font_defined(context))[0]
    specimen_plan = m.write_plan_files(context, work / "specimen",
        [(path, offset, data, "r3hd.prompt-specimen") for path, offset, data, _ in specimen],
        [("r3hd.prompt-specimen", "1")])
    result = {"status": "PASS", "base_blocks_checked": checks, "ranges": len(ranges), "textures": stats,
              "source_files_unchanged": 3, "metrics_unchanged": True, "specimen_plan": specimen_plan,
              "visual_acceptance": "not established"}
    (work / "audit.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-dir", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    a = ap.parse_args()
    print(json.dumps(audit(a.game_dir.resolve(), a.work.resolve())))

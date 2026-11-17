"""D-202: private complete font correction vs accepted shoulder/menu plan; no game."""
import argparse
import json
from pathlib import Path

import r3hd_button_prompts as p
import r3hd_mods as m
from ps3_prompt_regression import apply_plan


def audit(source, game, baseline, corrected, work):
    native = p.read_glyphs(source)
    assert len(native) == 9 and not hasattr(p, "face_pixel") and not hasattr(p, "paint_cell")
    fix = (game / "GAMEDATAbin/fix.lvl").read_bytes()
    assert m.read_font(fix) is not None
    records = m.font_records(fix, m.FONT["others"][0])
    placements = {}
    checks = 0
    for code, name in p.BUTTONS.items():
        rec = records[code]
        placement = p.shoulder_placement if code in p.SHOULDERS else p.glyph_placement
        left, top, w, h = placement(rec, native[name])
        assert 0 <= left and 0 <= top and left + w <= rec[3] and top + h <= rec[2]
        original = bytes([20, 30, 40, 50]) * 512 * 512
        image = bytearray(original)
        p.paint_shoulder(image, 512, rec, native[name], placement)
        x, y, ch, cw = rec[:4]
        for row in range(512):
            a, b = (row * 512 + x) * 4, (row * 512 + x + cw) * 4
            if y <= row < y + ch:
                assert image[row * 2048:a] == original[row * 2048:a]
                assert image[b:(row + 1) * 2048] == original[b:(row + 1) * 2048]
            else:
                assert image[row * 2048:(row + 1) * 2048] == original[row * 2048:(row + 1) * 2048]
            checks += 1
        if name in p.NATIVE_FACES or name in ("L1", "R1", "start"):
            assert (w, h) == native[name][:2]
            copied = b"".join(image[((y + top + j) * 512 + x + left) * 4:
                                   ((y + top + j) * 512 + x + left + w) * 4] for j in range(h))
            assert copied == native[name][3]
        placements[name] = [left, top, w, h]
    target = game / "GAMEDATAbin/fix.btf"
    original = target.read_bytes()
    before = apply_plan(baseline, original, target)
    after = apply_plan(corrected, original, target)
    entries = {e[0]: e for e in m.bhf_entries(target.with_suffix(".bhf"))}
    menu = entries["menu\\mnu_xb512_en.dds"]
    for off, size in ((menu[2], menu[1]), (menu[4], menu[3])):
        assert before[off:off + size] == after[off:off + size]
    font = entries[m.FONT["atlas"]]
    pitch = m.layout(512, 512, "DXT5")[2][0][2]
    allowed = {(x // 4, y // 4) for c in p.FACES | {0x54: "start"}
               for xx, yy, h, w in [records[c][:4]]
               for x in range(xx, xx + w) for y in range(yy, yy + h)}
    changed = 0
    for by in range(128):
        for bx in range(128):
            off = font[2] + (127 - by) * pitch + bx * 16
            same = before[off:off + 16] == after[off:off + 16]
            assert same or (bx, by) in allowed
            changed += not same
            checks += 1
    assert changed > 0
    assert m.sha256_bytes(target.read_bytes()) == m.sha256_bytes(original)
    assert (game / "GAMEDATAbin/fix.lvl").read_bytes() == fix
    result = {"status": "PASS", "checks": checks, "placements": placements,
              "face_start_base_blocks_changed": changed, "menu_all_mips_unchanged": True,
              "shoulder_base_unchanged": True, "guest_metrics_unchanged": True,
              "human_new_face_start_acceptance": "PENDING"}
    work.mkdir(parents=True, exist_ok=True)
    (work / "complete-regression.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "game", "baseline", "corrected", "work"):
        ap.add_argument("--" + name, type=Path, required=True)
    a = ap.parse_args()
    print(json.dumps(audit(a.source, a.game, a.baseline, a.corrected, a.work)))

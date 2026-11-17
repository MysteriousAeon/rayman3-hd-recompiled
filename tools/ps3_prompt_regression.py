"""Focused native shoulder/accepted-art regression against private, owner-supplied assets.

No game or device starts; no PS3 pixels are embedded here. Requires an existing
corrected plan and the preserved D-199 baseline plan, both in private directories.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

import r3hd_button_prompts as p
import r3hd_mods as m


def apply_plan(plan, original, target):
    data = bytearray(original)
    files = []
    for line in plan.read_text(encoding="utf-8").splitlines():
        if line.startswith("file "):
            files.append(Path(line.split(" ", 2)[2]).resolve())
        if line.startswith("range "):
            fields = line.split(" ", 7)
            if files[int(fields[1])] != target.resolve():
                raise ValueError("unexpected plan target")
            off, size = int(fields[2]), int(fields[3])
            value = Path(fields[7]).read_bytes()
            if len(value) != size or off < 0 or off + size > len(data):
                raise ValueError("invalid range")
            data[off:off + size] = value
    return data


def audit(source, game, baseline, corrected, work):
    checks = []
    def check(ok, label):
        checks.append((label, bool(ok)))
        if not ok:
            raise AssertionError(label)
    native = p.read_shoulders(source)
    check(set(native) == {"L1", "R1", "L2", "R2"}, "four verified native images")
    old_env = os.environ.pop("R3HD_PS3_PROMPT_SOURCE", None)
    try:
        try:
            p.read_shoulders()
        except (OSError, ValueError):
            check(True, "missing native source refuses, without placeholder fallback")
        else:
            check(False, "missing native source refuses, without placeholder fallback")
    finally:
        if old_env is not None:
            os.environ["R3HD_PS3_PROMPT_SOURCE"] = old_env
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as temporary:
        copy = Path(temporary)
        shutil.copyfile(source, copy / "shoulders.json")
        for name in native:
            shutil.copyfile(source.parent / f"{name}.png", copy / f"{name}.png")
        (copy / "L1.png").write_bytes(m.write_png(70, 35, bytes(70 * 35 * 4)))
        try:
            p.read_shoulders(copy / "shoulders.json")
        except ValueError:
            check(True, "modified pixels refuse before overlay")
        else:
            check(False, "modified pixels refuse before overlay")
    fix = (game / "GAMEDATAbin/fix.lvl").read_bytes()
    records = m.font_records(fix, m.FONT["others"][0])
    placements = {}
    for code, name in p.SHOULDERS.items():
        rec, original = records[code], bytes([12, 34, 56, 78]) * 512 * 512
        image = bytearray(original)
        x, y, h, w = rec[:4]
        left, top, tw, th = p.shoulder_placement(rec, native[name])
        placements[name] = {"left": left, "top": top, "width": tw, "height": th}
        check(tw <= native[name][0] and th <= native[name][1] and 0 <= left and 0 <= top
              and left + tw <= w and top + th <= h, f"{name}: bounded, no upscaling")
        check(abs(tw / th - native[name][0] / native[name][1]) < .04, f"{name}: native aspect ratio")
        p.paint_shoulder(image, 512, rec, native[name])
        for row in range(512):
            a, b = (row * 512 + x) * 4, (row * 512 + x + w) * 4
            if not y <= row < y + h:
                check(image[row * 2048:(row + 1) * 2048] == original[row * 2048:(row + 1) * 2048], f"{name}: outside row {row}")
            else:
                check(image[row * 2048:a] == original[row * 2048:a] and image[b:(row + 1) * 2048] == original[b:(row + 1) * 2048], f"{name}: outside columns {row}")
        if name in ("L1", "R1"):
            copied = b"".join(image[((y + top + j) * 512 + x + left) * 4:
                                       ((y + top + j) * 512 + x + left + tw) * 4] for j in range(th))
            check(copied == native[name][3], f"{name}: native pixels copied without resampling")
    check(p.resize_native(2, 1, bytes([255, 0, 0, 255, 0, 0, 255, 0]), 1, 1) == bytes([255, 0, 0, 128]),
          "premultiplied reduction excludes transparent color fringe")
    target = game / "GAMEDATAbin/fix.btf"
    original = target.read_bytes()
    before = apply_plan(baseline, original, target)
    after = apply_plan(corrected, original, target)
    entries = {e[0]: e for e in m.bhf_entries(target.with_suffix(".bhf"))}
    for name in ("menu\\mnu_xb512_en.dds",):
        e = entries[name]
        for off, size in ((e[2], e[1]), (e[4], e[3])):
            check(before[off:off + size] == after[off:off + size], "accepted menu bytes unchanged, including mips")
    e = entries[m.FONT["atlas"]]
    _, _, lay = m.layout(512, 512, "DXT5")
    allowed = {(xx // 4, yy // 4) for c in p.SHOULDERS for x, y, h, w in [records[c][:4]]
               for xx in range(x, x + w) for yy in range(y, y + h)}
    changed = 0
    for by in range(128):
        for bx in range(128):
            off = e[2] + (127 - by) * lay[0][2] + bx * 16
            same = before[off:off + 16] == after[off:off + 16]
            check(same or (bx, by) in allowed, "only shoulder base blocks differ from accepted baseline")
            changed += not same
    check(changed > 0, "correction changes shoulder artwork")
    check(m.sha256_bytes(target.read_bytes()) == m.sha256_bytes(original), "Xbox source never modified")
    result = {"status": "PASS", "checks": len(checks), "placements": placements,
              "shoulder_base_blocks_changed": changed, "menu_and_face_base_unchanged": True,
              "guest_metrics_unchanged": True, "human_acceptance": "pending"}
    (work / "regression.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "game", "baseline", "corrected", "work"):
        ap.add_argument(f"--{name}", type=Path, required=True)
    a = ap.parse_args()
    print(json.dumps(audit(a.source, a.game, a.baseline, a.corrected, a.work)))

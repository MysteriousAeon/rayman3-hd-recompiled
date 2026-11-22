"""G6-P54: synthetic end-to-end regression of the D-298 mod / PlayStation prompt precedence.

The existing D-298 unit test calls `preserve_bundled_translation` with hand-built overlap
tuples. This test drives the real `prepare` tail instead: a mods plan written by
`r3hd_mods.write_plan_files`, parsed by `overlapping_mod_ranges`, filtered by the bundled
Turkish preservation, coalesced and written as the prompt plan. Texture decoding, glyph
painting and block encoding are replaced by fixed synthetic ranges, so no game data, glyph
source, GPU, controller or window is used. It proves plan-level precedence only, never
in-game visual correctness.
"""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import r3hd_button_prompts as prompts
import r3hd_mods as m

TR = ("tr.full.dev", "1.0.1")
BLOCK = 16
# Synthetic font atlas: base level [0, 32), mip level [32, 64); original bytes are zero.
ORIGINAL = (bytes(32), bytes(32))
# Whole-region translation output; only the second block of each level differs from the original.
LOCALIZED = (bytes(16) + b"t" * 16, bytes(16) + b"u" * 16)
PINS = tuple(hashlib.sha256(d).hexdigest() for d in LOCALIZED)


def tree_digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def plan_rows(plan, game):
    """Range rows of a prompt plan, with paths relative to the game directory (layout-independent)."""
    files, rows = [], []
    for line in Path(plan).read_text(encoding="utf-8").splitlines():
        if line.startswith("file "):
            files.append(Path(line.split(" ", 2)[2]).resolve().relative_to(game.resolve()).as_posix())
        elif line.startswith("range "):
            _, fi, off, size, _, _, mod, _ = line.split(" ", 7)
            rows.append((files[int(fi)], int(off), int(size), mod))
    return rows


def stable_text(plan):
    return [ln for ln in Path(plan).read_text(encoding="utf-8").splitlines() if not ln.startswith("# written")]


class Layout:
    """One synthetic home: game data, user-owned mod packages, a mods cache and a prompt cache."""

    def __init__(self, base):
        self.home = base
        self.game = base / "data/content"
        (self.game / "GAMEDATAbin").mkdir(parents=True)
        (self.game / "GAMEDATAbin/fix.lvl").write_bytes(b"synthetic level")
        # As in the title, the font atlas and the menu art resolve from the one `GAMEDATAbin/fix` bundle:
        # one fix.btf, absolute offsets. Atlas [0, 64), menu art [64, 96).
        self.atlas = self.menu = self.game / "GAMEDATAbin/fix.btf"
        self.atlas.write_bytes(b"".join(ORIGINAL) + bytes(32))
        self.other = self.game / "GAMEDATAbin/other.btf"
        self.other.write_bytes(bytes(32))
        self.packages = base / "mods"
        self.packages.mkdir()
        (self.packages / "tr-full-1.0.1.zip").write_bytes(b"user-owned translation package")
        (self.packages / "community.zip").write_bytes(b"user-owned community package")
        self.mods_cache = base / "cache/mods"
        self.prompt_cache = base / "cache/button_prompts"

    def mods_plan(self, turkish=False, community=None):
        ranges, mods = [], []
        if turkish:
            ranges += [(self.atlas, 0, LOCALIZED[0], TR[0]), (self.atlas, 32, LOCALIZED[1], TR[0])]
            mods.append(TR)
        if community:
            path, off = {"menu": (self.menu, 64), "atlas": (self.atlas, 16), "other": (self.other, 0)}[community]
            ranges.append((path, off, b"c" * BLOCK, "community.texture"))
            mods.append(("community.texture", "1"))
        return m.write_plan_files({"cache": self.mods_cache}, self.mods_cache, ranges, mods) or None

    def prepare(self, mods_plan):
        font = (self.atlas, (0, 32, 0, 32, 32), 512, 512, (), ORIGINAL, b"")
        menu = (self.menu, (0, 32, 64, 0, 96), 1024, 1024, (), (bytes(32), b""), b"")
        gen = (self.game / "GAMEDATAbin/gen.btf", (0, 0, 0, 0, 0), 1024, 1024, (), (b"", b""), b"")
        textures = {m.FONT["atlas"]: font, "menu\\mnu_xb512_en.dds": menu, "menu\\mnu_gen.dds": gen}
        # The prompt's own changed blocks: every atlas block, and two adjacent menu blocks.
        sparse = {id(font): [(self.atlas, off, b"p" * BLOCK, "r3hd.button-prompts") for off in (0, 16, 32, 48)],
                  id(menu): [(self.menu, off, b"q" * BLOCK, "r3hd.button-prompts") for off in (64, 80)]}
        with patch.object(prompts, "read_glyphs", return_value={k: None for k in prompts.NATIVE_GLYPHS}), \
                patch.object(m, "read_font", return_value=object()), \
                patch.object(m, "font_records", return_value={c: (0, 0, 0, 0) for c in prompts.BUTTONS}), \
                patch.object(prompts, "texture", side_effect=lambda game, name: textures[name]), \
                patch.object(prompts, "paint_shoulder"), \
                patch.object(prompts, "sparse_ranges", side_effect=lambda tex, img, rects: list(sparse[id(tex)])), \
                patch.object(prompts, "BUNDLED_TR_FONT", PINS):
            return prompts.prepare(self.game, self.prompt_cache, mods_plan)


# Adjacent prompt blocks coalesce: the whole atlas plus the menu art is one range.
FULL = [("GAMEDATAbin/fix.btf", 0, 96, "r3hd.button-prompts")]
# The translation changed the atlas blocks at 16 and 48: those stay the translation's, the rest are prompts,
# including both menu-art blocks (64, 80) outside the translation's atlas.
WITH_TR = [("GAMEDATAbin/fix.btf", off, size, "r3hd.button-prompts") for off, size in ((0, 16), (32, 16), (64, 32))]


class TurkishPlayStationPrecedence(unittest.TestCase):
    def cycle(self, root):
        """Disable / enable / mix cycle on one layout; returns the Turkish-only prompt plan rows."""
        lay = Layout(root)
        packages = tree_digest(lay.packages)
        game = tree_digest(lay.game)

        result = lay.prepare(None)                          # no mods: the whole prompt plan
        self.assertEqual((result["reason"], plan_rows(result["plan"], lay.game)), ("launch-time", FULL))
        vanilla_text = stable_text(result["plan"])

        tr_plan = lay.mods_plan(turkish=True)              # Turkish enabled: its changed blocks retained
        mods_before = tree_digest(lay.mods_cache)
        result = lay.prepare(tr_plan)
        self.assertEqual(result["reason"], "launch-time; bundled Turkish atlas edits retained")
        rows = plan_rows(result["plan"], lay.game)
        self.assertEqual(rows, WITH_TR)
        tr_text = stable_text(result["plan"])
        self.assertEqual(tree_digest(lay.mods_cache), mods_before, "prompt planning must not touch the mods plan")

        # A non-overlapping community mod keeps the Turkish result; an overlapping one keeps whole-mod priority.
        self.assertEqual(plan_rows(lay.prepare(lay.mods_plan(turkish=True, community="other"))["plan"], lay.game),
                         WITH_TR)
        for where in ("menu", "atlas"):
            result = lay.prepare(lay.mods_plan(turkish=True, community=where))
            self.assertEqual((result["plan"], result["reason"]), ("", "mod overlap; existing mod retained"), where)

        # A Turkish font that is not the exact pinned output is an ordinary overlapping mod.
        odd = m.write_plan_files({"cache": lay.mods_cache}, lay.mods_cache,
                                 [(lay.atlas, 0, LOCALIZED[0], TR[0]), (lay.atlas, 32, bytes(16) + b"x" * 16, TR[0])],
                                 [TR])
        self.assertEqual(lay.prepare(odd)["plan"], "")

        # Disable Turkish: back to the full plan, byte for byte; re-enable: the identical Turkish plan.
        self.assertIsNone(lay.mods_plan())
        result = lay.prepare(None)
        self.assertEqual(stable_text(result["plan"]), vanilla_text)
        result = lay.prepare(lay.mods_plan(turkish=True))
        self.assertEqual(stable_text(result["plan"]), tr_text)

        self.assertEqual(tree_digest(lay.packages), packages, "user-owned mod packages changed")
        self.assertEqual(tree_digest(lay.game), game, "game data changed")
        return rows

    def test_installed_and_portable_layouts_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            installed = self.cycle(tmp / "Program Files/Rayman 3 HD Recompiled")
            portable = self.cycle(tmp / "R3HD Portable")
            self.assertEqual(installed, portable)

    @unittest.skipUnless(os.name == "nt", "case-insensitive paths are a Windows property")
    def test_mods_plan_path_case_does_not_hide_the_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            lay = Layout(Path(tmp) / "Home")
            upper = Path(str(lay.atlas).upper())
            plan = m.write_plan_files({"cache": lay.mods_cache}, lay.mods_cache,
                                      [(upper, 0, LOCALIZED[0], TR[0]), (upper, 32, LOCALIZED[1], TR[0])], [TR])
            self.assertEqual(plan_rows(lay.prepare(plan)["plan"], lay.game), WITH_TR)


if __name__ == "__main__":
    unittest.main()

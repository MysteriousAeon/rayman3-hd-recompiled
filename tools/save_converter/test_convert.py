"""Tests for convert.py. Synthetic records only; private samples are used when present and skipped otherwise.

    python -I tools/save_converter/test_convert.py
"""
import hashlib
import io
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import convert  # noqa: E402

SAMPLES = ROOT / 'private' / 'pcsave_samples' / 'raysaves'
SAVES = ROOT / 'private' / 'saves'
SAMPLE_SHA = {
    'L1P1.sav': '968d20cf45622a4226dff179642343af7de33d6850a6a06804aca2f84f9b32e7',
    'L4P1.sav': '57d3e33638366e8f6c8024fb1b6d26770c36fff1e4b9cd4eb4f2d09abf642d5b',
    'L9P5.sav': '0406cdab0783dc495ee7495a0a842e8df27a5d4ba22f7c180096a6984e746458',
}


def pc_record(level=b'Knaar_10', cages=(28, 0, 10, 9, 9, 0, 0, 0, 0, 0), scores=None, max_world=4,
              revisit=(0, 0, 0, 0, 0), after=b'', max_life=80, cur_life=52, cage_bits=28, elements=None):
    """Decoded little-endian PC SAV2 record with a consistent mid-campaign state (made up, not a real save)."""
    scores = scores or [0, 23198, 54643, 40000, 49368, 0, 0, 0, 0, 0]
    scores = [sum(scores[1:])] + list(scores[1:])
    env = [v for pair in zip(cages, scores) for v in pair]
    d = bytearray(0x10C)
    struct.pack_into('<20I', d, 0, *env)
    struct.pack_into('<4I', d, 0x50, 1, 2, 3, 4)
    struct.pack_into('<II', d, 0x60, 0, max_world)
    d[0x71] = 1  # a menu bool; PC key/pad tables left zero
    struct.pack_into('<5I', d, 0xAC, *revisit)
    d[0xC0:0xC0 + len(level)] = level
    d[0xD4:0xD4 + len(after)] = after
    struct.pack_into('<9I', d, 0xE8, 0, 0, 0, 0, 88, 127, 88, 88, 88)
    bits = (1 << cage_bits) - 1
    words = [bits & 0xFFFFFFFF, bits >> 32] + [0x10 + i for i in range(43)]
    for name, tb, cnt, vals in elements or [(b'save max life', 0x33, 1, [max_life]),
                                            (b'save current life', 0x33, 1, [cur_life]),
                                            (b'global save', 0x33, 45, words)]:
        n = name + b'\0'
        d += bytes([len(n)]) + n + bytes([tb, cnt]) + struct.pack('<%dI' % cnt, *vals)
    d += b'\0'
    return bytes(d)


def encode_pc(d, key=0x12345678):
    """Inverse of convert.decode_pc: RLE (zero runs, reversed literal runs) then the rotating XOR."""
    tokens, i = [], 0
    while i < len(d):
        j = i
        if d[i] == 0:
            while j < len(d) and d[j] == 0 and j - i < 127:
                j += 1
            tokens.append(bytes([j - i]))
        else:
            while j < len(d) and d[j] != 0 and j - i < 127:
                j += 1
            tokens.append(bytes([0x80 | (j - i)]) + d[i:j][::-1])
        i = j
    plain, out, k = b''.join(tokens), bytearray(struct.pack('<I', key ^ convert.PC_XOR)), key
    for b in plain:
        k = ((k >> 3) | (k << 29)) & 0xFFFFFFFF
        out.append(b ^ (k & 0xFF))
    return bytes(out)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = convert.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Codec(unittest.TestCase):
    def test_decode_inverts_encoder(self):
        rec = pc_record()
        self.assertEqual(convert.decode_pc(encode_pc(rec)), rec)
        self.assertEqual(len(rec), 510)  # the fixed SAV2 size seen in every PC and HD save

    def test_convert_maps_every_shared_field(self):
        f = convert.fields_from_pc(convert.decode_pc(encode_pc(pc_record())))
        self.assertEqual(convert.validate(f), [])
        hd = convert.build_hd(f)
        self.assertEqual(hd[:4], b'AAAA')
        self.assertEqual(struct.unpack_from('>I', hd, 4)[0], len(hd) - 8)
        self.assertEqual(len(hd), 510)
        g = convert.parse_hd(hd)
        for k in ('env', 'key_algo', 'end_of_game', 'max_world', 'warned_autosave', 'revisit', 'level',
                  'level_after_revisit', 'elements'):
            self.assertEqual(g[k], f[k], k)
        self.assertEqual(g['level'], 'Knaar_10')
        # worlds 2-4 complete; worlds 1 and 6 have no cages, so their bits are always set (E-342)
        self.assertEqual(g['award_words'], [0, 0, 0b1011110, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(g['hd_menu'], convert.HD_DEFAULT_MENU)
        self.assertEqual(g['hd_options'], convert.HD_DEFAULT_OPTIONS)
        # big-endian placement at the HD offsets (REPORT.md section 3)
        self.assertEqual(struct.unpack_from('>I', hd, 8)[0], 28)
        self.assertEqual(hd[152:160], b'Knaar_10')

    def test_donor_supplies_only_settings_bytes(self):
        f = convert.fields_from_pc(pc_record())
        menu = bytes(range(16))
        options = struct.pack('>9I', *range(9))
        donor = convert.build_hd(dict(f, level='Wood_10', env=[0] * 20), menu, options, [7] * 10)
        g = convert.parse_hd(donor)
        hd = convert.parse_hd(convert.build_hd(f, g['hd_menu'], g['hd_options']))
        self.assertEqual((hd['hd_menu'], hd['hd_options']), (menu, options))
        self.assertEqual(hd['level'], 'Knaar_10')
        self.assertEqual(hd['award_words'][0], 0)  # donor award progress is not carried over


class Rejections(unittest.TestCase):
    def refuse(self, rec, needle):
        with self.assertRaises(convert.SaveError) as cm:
            convert.validate(convert.fields_from_pc(rec))
        self.assertIn(needle, str(cm.exception))

    def test_unknown_level(self):
        self.refuse(pc_record(level=b'Nowhere_99'), 'not an HD level')

    def test_cage_total_mismatch(self):
        self.refuse(pc_record(cages=(27, 0, 10, 9, 9, 0, 0, 0, 0, 0)), 'total cages')

    def test_cage_over_world_maximum(self):
        self.refuse(pc_record(cages=(39, 0, 11, 9, 9, 10, 0, 0, 0, 0), cage_bits=39), 'maximum')

    def test_cage_bitmask_mismatch(self):
        self.refuse(pc_record(cage_bits=27), 'cage bitmask')

    def test_wrong_element_set(self):
        self.refuse(pc_record(elements=[(b'save max life', 0x33, 1, [80])]), 'element set')

    def test_bad_revisit(self):
        self.refuse(pc_record(revisit=(1, 0, 0, 0, 0)), 'revisit')

    def test_truncated_and_garbage(self):
        enc = encode_pc(pc_record())
        for bad in (enc[:-40], enc[:3]):
            with self.assertRaises(convert.SaveError):
                convert.fields_from_pc(convert.decode_pc(bad))

    def test_hd_file_is_not_a_pc_input(self):
        with self.assertRaises(convert.SaveError):
            convert.decode_pc(convert.build_hd(convert.fields_from_pc(pc_record())))

    def test_warns_on_unusual_life(self):
        w = convert.validate(convert.fields_from_pc(pc_record(max_life=200)))
        self.assertTrue(any('max life' in x for x in w))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.pc = self.dir / 'game.sav'
        self.pc.write_bytes(encode_pc(pc_record()))
        self.pc_sha = hashlib.sha256(self.pc.read_bytes()).hexdigest()

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.pc.read_bytes()).hexdigest(), self.pc_sha)  # input never modified
        self.tmp.cleanup()

    def test_convert_then_refuse_overwrite_then_force_with_backup(self):
        out = self.dir / 'RAY'
        self.assertEqual(run('--input', str(self.pc), '--output', str(out))[0], 0)
        first = out.read_bytes()
        out.write_bytes(b'existing')
        code, _, err = run('--input', str(self.pc), '--output', str(out))
        self.assertEqual(code, 1)
        self.assertIn('already exists', err)
        self.assertEqual(out.read_bytes(), b'existing')
        self.assertEqual(run('--input', str(self.pc), '--output', str(out), '--force')[0], 0)
        self.assertEqual(out.read_bytes(), first)
        backups = list(self.dir.glob('RAY.bak-*'))
        self.assertEqual([b.read_bytes() for b in backups], [b'existing'])
        code, text, _ = run('--input', str(out), '--dry-run')
        self.assertEqual(code, 0)
        self.assertIn('HD save is structurally valid', text)

    def test_in_place_donor_flow(self):
        # README step 5: --donor and --output name the same existing HD slot
        slot = self.dir / 'RAY'
        menu, options = bytes(range(16)), struct.pack('>9I', *range(9))
        fresh = convert.build_hd(dict(convert.fields_from_pc(pc_record(level=b'Intro_10', cages=(0,) * 10,
                                 cage_bits=0, max_world=1)), env=[0] * 20), menu, options)
        slot.write_bytes(fresh)
        self.assertEqual(run('--input', str(self.pc), '--donor', str(slot), '--output', str(slot), '--force')[0], 0)
        g = convert.parse_hd(slot.read_bytes())
        self.assertEqual((g['level'], g['hd_menu'], g['hd_options']), ('Knaar_10', menu, options))
        self.assertEqual([b.read_bytes() for b in self.dir.glob('RAY.bak-*')], [fresh])
        self.assertEqual(list(self.dir.glob('*.tmp-convert')), [])

    def test_non_hd_donor_refused(self):
        code, _, err = run('--input', str(self.pc), '--donor', str(self.pc), '--output', str(self.dir / 'RAY'))
        self.assertEqual(code, 1)
        self.assertIn('not an HD save', err)
        self.assertFalse((self.dir / 'RAY').exists())

    def test_revisit_save_converts_with_warning(self):
        rev = self.dir / 'rev.sav'
        rev.write_bytes(encode_pc(pc_record(level=b'Intro_15', revisit=(1, 0, 0, 1, 4), after=b'Knaar_10')))
        code, text, _ = run('--input', str(rev), '--output', str(self.dir / 'RAY'))
        self.assertEqual(code, 0)
        self.assertIn('revisit mode', text)
        self.assertEqual(convert.parse_hd((self.dir / 'RAY').read_bytes())['revisit'], [1, 0, 0, 1, 4])

    def test_dry_run_writes_nothing(self):
        code, text, _ = run('--input', str(self.pc), '--dry-run')
        self.assertEqual(code, 0)
        self.assertIn('Knaar_10', text)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ['game.sav'])

    def test_rejected_input_writes_nothing(self):
        bad = self.dir / 'bad.sav'
        bad.write_bytes(encode_pc(pc_record(level=b'Nowhere_99')))
        code, _, err = run('--input', str(bad), '--output', str(self.dir / 'RAY'))
        self.assertEqual(code, 1)
        self.assertIn('refusing', err)
        self.assertFalse((self.dir / 'RAY').exists())


def hd_slot_tree(home, name='RAY', data=None):
    """A synthetic home with one HD slot laid out as the runtime stores it; returns the slot file path."""
    slot = home / 'profiles' / 'default' / 'user' / 'B13EBABEBABEBABE' / '5841123F' / '00000001' / name / name
    slot.parent.mkdir(parents=True)
    header = home / 'profiles' / 'default' / 'user' / 'B13EBABEBABEBABE' / '5841123F' / 'Headers' / '00000001'
    header.mkdir(parents=True)
    (header / (name + '.header')).write_bytes(b'H' * 328)
    slot.write_bytes(data if data is not None else convert.build_hd(dict(convert.fields_from_pc(
        pc_record(level=b'Intro_10', cages=(0,) * 10, cage_bits=0, max_world=1)), env=[0] * 20)))
    return slot


class SlotSafety(unittest.TestCase):
    """Defect fixed in this milestone: a --force backup inside the slot directory is deleted by the game's next
    save (D-049 staged commit removes files the new content lacks), so slot backups go outside the slot."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.pc = self.dir / 'game.sav'
        self.pc.write_bytes(encode_pc(pc_record()))

    def tearDown(self):
        self.tmp.cleanup()

    def test_in_place_slot_backup_is_outside_the_slot_directory(self):
        home = self.dir / 'home'
        slot = hd_slot_tree(home)
        fresh = slot.read_bytes()
        header = next((home / 'profiles').glob('*/user/*/5841123F/Headers/00000001/RAY.header'))
        code, text, err = run('--input', str(self.pc), '--donor', str(slot), '--output', str(slot), '--force')
        self.assertEqual(code, 0, err)
        self.assertEqual([p.name for p in slot.parent.iterdir()], ['RAY'])  # nothing the game would delete
        backups = list((home / convert.BACKUP_DIR_NAME).glob('RAY.bak-*'))
        self.assertEqual([b.read_bytes() for b in backups], [fresh])
        self.assertIn(str(backups[0]), text)
        self.assertEqual(header.read_bytes(), b'H' * 328)  # the title's header is never touched
        self.assertEqual(convert.parse_hd(slot.read_bytes())['level'], 'Knaar_10')

    def test_slot_outside_a_profiles_folder_needs_backup_dir(self):
        slot = self.dir / 'x' / '00000001' / 'RAY' / 'RAY'
        slot.parent.mkdir(parents=True)
        slot.write_bytes(b'old')
        code, _, err = run('--input', str(self.pc), '--output', str(slot), '--force')
        self.assertEqual(code, 1)
        self.assertIn('--backup-dir', err)
        self.assertEqual(slot.read_bytes(), b'old')
        bdir = self.dir / 'backups'
        self.assertEqual(run('--input', str(self.pc), '--output', str(slot), '--force', '--backup-dir', str(bdir))[0], 0)
        self.assertEqual([b.read_bytes() for b in bdir.glob('RAY.bak-*')], [b'old'])
        self.assertEqual([p.name for p in slot.parent.iterdir()], ['RAY'])

    def test_backup_dir_inside_the_slot_is_refused(self):
        slot = hd_slot_tree(self.dir / 'home')
        before = slot.read_bytes()
        for bdir in (slot.parent, slot.parent / 'sub'):
            code, _, err = run('--input', str(self.pc), '--output', str(slot), '--force', '--backup-dir', str(bdir))
            self.assertEqual(code, 1)
            self.assertIn('inside the slot directory', err)
        self.assertEqual(slot.read_bytes(), before)
        self.assertEqual([p.name for p in slot.parent.iterdir()], ['RAY'])

    def test_relative_slot_path_from_inside_the_slot_folder(self):
        import os
        slot = hd_slot_tree(self.dir / 'home')
        cwd = os.getcwd()
        os.chdir(slot.parent)
        try:
            code, _, err = run('--input', str(self.pc), '--output', 'RAY', '--force')
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0, err)
        self.assertEqual([p.name for p in slot.parent.iterdir()], ['RAY'])
        self.assertEqual(len(list((self.dir / 'home' / convert.BACKUP_DIR_NAME).glob('RAY.bak-*'))), 1)

    def test_oversized_input_and_donor_are_refused_unread(self):
        big = self.dir / 'video.sav'
        big.write_bytes(b'\x01' * (convert.INPUT_LIMIT + 1))
        code, _, err = run('--input', str(big), '--dry-run')
        self.assertEqual(code, 1)
        self.assertIn('not one', err)
        code, _, err = run('--input', str(self.pc), '--donor', str(big), '--output', str(self.dir / 'RAY'))
        self.assertEqual(code, 1)
        self.assertFalse((self.dir / 'RAY').exists())

    def test_missing_donor_is_an_error_not_a_crash(self):
        code, _, err = run('--input', str(self.pc), '--donor', str(self.dir / 'nope'), '--output', str(self.dir / 'RAY'))
        self.assertEqual(code, 1)
        self.assertIn('donor', err)
        self.assertFalse((self.dir / 'RAY').exists())


try:
    import convert_gui  # noqa: E402  (tkinter is only imported, no window is created)
except ImportError:  # Python without tkinter
    convert_gui = None


@unittest.skipIf(convert_gui is None, 'tkinter not available')
class GuiSlotSearch(unittest.TestCase):
    """Defect fixed in this milestone: the slot search walked '**' below the exe's parent folder (a whole user
    profile when the exe sits in Downloads). It now looks at fixed depths only."""

    def test_fixed_depth_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            direct = hd_slot_tree(root / 'portable')  # <root>/portable/profiles/...: one level down
            nested = hd_slot_tree(root / 'a' / 'b' / 'deep')  # three levels down: not searched
            (direct.parent / 'RAY.bak-x').write_bytes(b'x')  # not a slot file
            self.assertEqual(convert_gui.find_slots([root]), [direct.resolve()])
            self.assertEqual(convert_gui.find_slots([root / 'portable']), [direct.resolve()])
            self.assertNotIn(nested.resolve(), convert_gui.find_slots([root, root / 'a']))


def pc_from_hd_fields(g):
    """A decoded little-endian PC record carrying exactly the shared fields of an HD save (PC key tables zero)."""
    d = bytearray(0x10C)
    struct.pack_into('<20I', d, 0, *g['env'])
    struct.pack_into('<4I', d, 0x50, *g['key_algo'])
    struct.pack_into('<II', d, 0x60, g['end_of_game'], g['max_world'])
    struct.pack_into('<I', d, 0xA8, g['warned_autosave'])
    struct.pack_into('<5I', d, 0xAC, *g['revisit'])
    d[0xC0:0xC0 + len(g['level'])] = g['level'].encode()
    d[0xD4:0xD4 + len(g['level_after_revisit'])] = g['level_after_revisit'].encode()
    for name, tb, cnt, vals in g['elements']:
        n = name + b'\0'
        d += bytes([len(n)]) + n + bytes([tb, cnt]) + struct.pack('<%dI' % cnt, *vals)
    return bytes(d + b'\0')


@unittest.skipUnless(SAMPLES.is_dir() and SAVES.is_dir(), 'private PC samples / HD saves not present')
class PrivateSamples(unittest.TestCase):
    def hd_slot(self, entry):
        slots = [p for p in (SAVES / entry / 'profile').glob('*/5841123F/00000001/*/*') if p.name == p.parent.name]
        self.assertEqual(len(slots), 1)
        return slots[0].read_bytes()

    def test_samples_convert_to_the_files_that_loaded_in_game(self):
        # E-342: these converted files loaded through the title's Load path (three hidden smokes).
        for name, sha in SAMPLE_SHA.items():
            raw = (SAMPLES / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)
            f = convert.fields_from_pc(convert.decode_pc(raw))
            convert.validate(f)
            self.assertEqual(convert.build_hd(f), self.hd_slot('pcconv_' + name[:-4].lower()), name)

    def test_genuine_hd_saves_round_trip_and_validate(self):
        entries = sorted(p.parent.name for p in SAVES.glob('*/entry.json') if not p.parent.name.startswith('pcconv'))
        self.assertTrue(entries)
        for entry in entries:
            data = self.hd_slot(entry)
            g = convert.parse_hd(data)
            self.assertEqual(convert.validate(g), [], entry)
            self.assertEqual(convert.build_hd(g, g['hd_menu'], g['hd_options'], g['award_words']), data, entry)
            self.assertEqual(g['award_words'][2], convert.award_word2(g['env']), entry)  # word-2 rule (E-342)
            # PC encoding round trip of the same state (no HD-only bytes in a PC record)
            self.assertEqual(convert.parse_hd(convert.build_hd(g))['elements'], g['elements'])

    def test_real_unedited_pc_save_raypc(self):
        # E-423: the maintainer's real, unedited PC save (early campaign, Swamp_60). Its progress equals the
        # genuine HD save at the same level except scores, current life and one global-save bit (word 4).
        raw_path = ROOT / 'private' / 'pcsave_samples' / 'maintainer' / 'RAYPC.sav'
        if not raw_path.is_file():
            self.skipTest('maintainer PC save not present')
        raw = raw_path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'ccd60b8189e8d08b614149dcfd3d100f3a734b65a4de55b38e45df0a72685af0')
        f = convert.fields_from_pc(convert.decode_pc(raw))
        self.assertEqual(convert.validate(f), [])
        g = convert.parse_hd(convert.build_hd(f))
        self.assertEqual((g['level'], g['max_world'], g['revisit'][0], g['env'][0], g['env'][1]),
                         ('Swamp_60', 2, 0, 10, 49097))
        self.assertEqual(g['award_words'][2], 0x46)
        hd = convert.parse_hd(self.hd_slot('swamp_60_human'))
        for k in ('end_of_game', 'max_world', 'revisit', 'level', 'level_after_revisit'):
            self.assertEqual(g[k], hd[k], k)
        self.assertEqual(g['env'][0::2], hd['env'][0::2])  # cages per world
        pw, hw = g['elements'][2][3], hd['elements'][2][3]
        self.assertEqual([i for i in range(45) if pw[i] != hw[i]], [4])
        self.assertEqual(hw[4] ^ pw[4], 0x02000000)

    def test_genuine_mid_campaign_states_through_the_pc_path(self):
        # Genuine HD campaign states (non-revisit, non-zero scores, worlds 1-5) re-expressed as encoded PC files
        # convert back to the same progress and award word 2. Synthetic PC encoding: not a real PC save (V6).
        entries = sorted(p.parent.name for p in SAVES.glob('*/entry.json') if not p.parent.name.startswith('pcconv'))
        for entry in entries:
            g = convert.parse_hd(self.hd_slot(entry))
            f = convert.fields_from_pc(convert.decode_pc(encode_pc(pc_from_hd_fields(g))))
            self.assertEqual(convert.validate(f), [], entry)
            h = convert.parse_hd(convert.build_hd(f, g['hd_menu'], g['hd_options']))
            for k in ('env', 'key_algo', 'end_of_game', 'max_world', 'warned_autosave', 'revisit', 'level',
                      'level_after_revisit', 'elements'):
                self.assertEqual(h[k], g[k], (entry, k))
            self.assertEqual(h['award_words'][2], g['award_words'][2], entry)


if __name__ == '__main__':
    unittest.main(verbosity=2)

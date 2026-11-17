#!/usr/bin/env python3
"""Convert a Rayman 3 PC (2003) save to a Rayman 3 HD Recompiled save slot file.

Standalone, Python 3.8+, standard library only. The input is only read; an existing output
is never replaced unless --force is given, and then it is first copied to a timestamped .bak.

    python convert.py --input original.sav --output RAY          convert
    python convert.py --input original.sav --dry-run             decode, validate, print, write nothing
    python convert.py --input <HD slot file> --dry-run           print an HD save (e.g. after reloading)

Format evidence: reports/pc_save_compat/REPORT.md (E-341, E-342). Both games store the same CPA
"SAV2" record. PC: XOR/RLE encoded, little-endian, with key/pad tables. HD: 'AAAA' + length,
big-endian, no key tables, plus ten HD-only award-progress words. Neither has a checksum, so the
title cannot detect a bad conversion: this tool validates instead and refuses what it does not know.
"""
import argparse
import datetime
import hashlib
import os
import shutil
import struct
import sys
from pathlib import Path

PC_XOR = 0xA55AA55A
LOADER_LIMIT = 0x1000  # HD loader buffer (8210C368)
HD_MAGIC = b'AAAA'
HD_HEADER = 0xE0  # header length in the HD file, after 'AAAA' + u32 length
HD_OPTIONS = 0x24  # game options block length (both)
PC_ELEMENTS = 0x10C  # first element in the decoded PC record
INPUT_LIMIT = 0x10000  # saves are a few hundred bytes; anything larger is refused before it is read
BACKUP_DIR_NAME = 'save_converter_backups'

# Per-world cage maxima: Total + 9 worlds. HD image table 82837460, equal to the PC samples.
CAGE_MAX = [60, 0, 10, 9, 9, 12, 0, 3, 7, 10]

# The three elements both games write (name, type byte, count). Type 0x33: low nibble 3 = u32.
ELEMENTS = [(b'save max life', 0x33, 1), (b'save current life', 0x33, 1), (b'global save', 0x33, 45)]

# HD level directories that contain <name>.lvl (61 names; GamedataBIN of title 5841123F).
HD_LEVELS = frozenset('''
ballmap bonustxt commando crush endgame fact_22 fact_34 fact_40 fact_50 fact_55 flash_10 flash_20
flash_30 intro_10 intro_15 intro_17 intro_20 knaar_10 knaar_20 knaar_30 knaar_45 knaar_60 knaar_69
knaar_70 lept_15 menu_00 menu_10 menu_20 menu_30 menumap moor_00 moor_19 moor_30 moor_60 mount_4x
mount_50 raz_map sea_10 sentinel ship_map sk8_00 sk8_10 sk8_20 snipe_00 staff swamp_50 swamp_51
swamp_60 swamp_81 swamp_82 swamp_83 ten_map toudi_00 tower_10 tower_20 tower_30 tower_40 wood_10
wood_11 wood_19 wood_50'''.split())

# HD-only bytes a new HD game writes (genuine save intro_10_fresh): header +0x68..+0x77 (two
# centering floats, four settings bytes whose meanings are UNKNOWN) and the 36-byte options block
# (details, screen size, PAL60, screen-size load, five volumes 63). Settings, not progress; the PC
# volume scale (88/127) differs and is not converted. --donor takes them from an HD save instead.
HD_DEFAULT_MENU = bytes.fromhex('00000000000000000001000000000000')
HD_DEFAULT_OPTIONS = struct.pack('>9I', 0, 0, 0, 0, 63, 63, 63, 63, 63)


class SaveError(Exception):
    pass


def decode_pc(raw):
    """PC .sav bytes -> decoded record. Key = first u32 ^ 0xA55AA55A; before each byte the key
    rotates right by 3 and the byte is XORed with its low byte. Then RLE: bit 7 clear = that many
    zero bytes; bit 7 set = n literal bytes follow, stored in reverse order."""
    if len(raw) < 5:
        raise SaveError('file too short to be a PC save (%d bytes)' % len(raw))
    if raw[:4] == HD_MAGIC:
        raise SaveError("file starts with 'AAAA': this is already an HD save, not a PC save")
    key = struct.unpack_from('<I', raw, 0)[0] ^ PC_XOR
    pos, out = 4, bytearray()
    while pos < len(raw):
        key = ((key >> 3) | (key << 29)) & 0xFFFFFFFF
        c = raw[pos] ^ (key & 0xFF)
        pos += 1
        if not c & 0x80:
            out += bytes(c)
        else:
            n = c & 0x7F
            if pos + n > len(raw):
                raise SaveError('corrupt PC save: literal run past the end of the file')
            chunk = bytearray(n)
            for i in range(n - 1, -1, -1):
                key = ((key >> 3) | (key << 29)) & 0xFFFFFFFF
                chunk[i] = raw[pos] ^ (key & 0xFF)
                pos += 1
            out += chunk
        if len(out) > LOADER_LIMIT:
            raise SaveError('corrupt PC save: decodes to more than %d bytes' % LOADER_LIMIT)
    return bytes(out)


def parse_elements(d, p, endian):
    """Elements until a zero length byte. Returns (elements, offset after the terminator)."""
    els = []
    while True:
        if p >= len(d):
            raise SaveError('element list has no terminator')
        n = d[p]
        p += 1
        if n == 0:
            return els, p
        if p + n + 2 > len(d):
            raise SaveError('element header past the end of the record')
        name = d[p:p + n]
        p += n
        tb, cnt = d[p], d[p + 1]
        p += 2
        if tb & 0xF != 3:
            raise SaveError('element %r has unsupported type byte %#x' % (name, tb))
        if p + 4 * cnt > len(d):
            raise SaveError('element %r values past the end of the record' % name)
        vals = list(struct.unpack_from('%s%dI' % (endian, cnt), d, p))
        p += 4 * cnt
        els.append((name.rstrip(b'\0'), tb, cnt, vals))


def level_name(field, what, notes):
    raw = field.split(b'\0')[0]
    if field[len(raw):].strip(b'\0'):
        notes.append('%s: bytes after the terminator are not zero; written as zero padding' % what)
    try:
        return raw.decode('ascii')
    except UnicodeDecodeError:
        raise SaveError('%s is not an ASCII level name: %r' % (what, raw))


def fields_from_pc(d):
    notes = []
    if len(d) < PC_ELEMENTS + 1:
        raise SaveError('decoded PC record too short (%d bytes)' % len(d))
    u = lambda o: struct.unpack_from('<I', d, o)[0]
    f = {
        'env': list(struct.unpack_from('<20I', d, 0)),
        'key_algo': list(struct.unpack_from('<4I', d, 0x50)),
        'end_of_game': u(0x60), 'max_world': u(0x64), 'warned_autosave': u(0xA8),
        'revisit': list(struct.unpack_from('<5I', d, 0xAC)),
        'level': level_name(d[0xC0:0xD4], 'resume level', notes),
        'level_after_revisit': level_name(d[0xD4:0xE8], 'after-revisit level', notes),
        'pc_options': list(struct.unpack_from('<9I', d, 0xE8)),
    }
    f['elements'], end = parse_elements(d, PC_ELEMENTS, '<')
    if d[end:].strip(b'\0'):
        raise SaveError('unexpected non-zero data after the element terminator')
    if len(d) != end:
        notes.append('%d zero bytes after the record ignored' % (len(d) - end))
    f['notes'] = notes
    return f


def parse_hd(data):
    """HD slot file -> fields (big-endian). Also returns the HD-only blocks."""
    if data[:4] != HD_MAGIC:
        raise SaveError("not an HD save (first word is not 'AAAA')")
    if len(data) < 8 or struct.unpack_from('>I', data, 4)[0] != len(data) - 8:
        raise SaveError('HD save length word does not match the file size')
    if len(data) > LOADER_LIMIT:
        raise SaveError('HD save larger than the loader buffer')
    h = data[8:8 + HD_HEADER]
    if len(h) != HD_HEADER:
        raise SaveError('HD save too short')
    u = lambda o: struct.unpack_from('>I', h, o)[0]
    notes = []
    f = {
        'env': list(struct.unpack_from('>20I', h, 0)),
        'key_algo': list(struct.unpack_from('>4I', h, 0x50)),
        'end_of_game': u(0x60), 'max_world': u(0x64), 'warned_autosave': u(0x78),
        'revisit': list(struct.unpack_from('>5I', h, 0x7C)),
        'level': level_name(h[0x90:0xA4], 'resume level', notes),
        'level_after_revisit': level_name(h[0xA4:0xB8], 'after-revisit level', notes),
        'award_words': list(struct.unpack_from('>10I', h, 0xB8)),
        'hd_menu': h[0x68:0x78],
        'hd_options': data[8 + HD_HEADER:8 + HD_HEADER + HD_OPTIONS],
    }
    f['elements'], end = parse_elements(data, 8 + HD_HEADER + HD_OPTIONS, '>')
    if end != len(data):
        raise SaveError('HD save has data after the element terminator')
    f['notes'] = notes
    return f


def validate(f):
    """Raise SaveError for anything this tool does not understand; return a list of warnings."""
    errors, warnings = [], []
    env = f['env']
    cages, scores = env[0::2], env[1::2]
    if cages[0] != sum(cages[1:]):
        errors.append('total cages %d != sum of world cages %d' % (cages[0], sum(cages[1:])))
    if scores[0] != sum(scores[1:]):
        errors.append('total score %d != sum of world scores %d' % (scores[0], sum(scores[1:])))
    for i, (c, m) in enumerate(zip(cages, CAGE_MAX)):
        if c > m:
            errors.append('world %d has %d cages, maximum is %d' % (i, c, m))
    got = [(n, t, c) for n, t, c, _ in f['elements']]
    if got != ELEMENTS:
        errors.append('unexpected element set %r (expected %r)' % (got, ELEMENTS))
    if f['end_of_game'] not in (0, 1):
        errors.append('end-of-game flag %d is not 0 or 1' % f['end_of_game'])
    if not 1 <= f['max_world'] <= 9:
        errors.append('highest world %d outside 1..9' % f['max_world'])
    if f['level'].lower() not in HD_LEVELS:
        errors.append('resume level %r is not an HD level' % f['level'])
    lar = f['level_after_revisit']
    if lar and lar.lower() not in HD_LEVELS:
        errors.append('after-revisit level %r is not an HD level' % lar)
    mode, _, _, world, origin = f['revisit']
    if mode not in (0, 1):
        errors.append('revisit mode %d is not 0 or 1' % mode)
    if mode and not (1 <= world <= 9 and 1 <= origin <= 9 and lar):
        errors.append('revisit mode on, but revisit world/origin/after-level are invalid')
    if not errors:
        els = {n: v for n, _, _, v in f['elements']}
        g = els[b'global save']
        if bin(g[0]).count('1') + bin(g[1]).count('1') != cages[0]:
            errors.append('cage bitmask (global save words 0-1) has %d bits, total cages is %d'
                          % (bin(g[0]).count('1') + bin(g[1]).count('1'), cages[0]))
        max_life = els[b'save max life'][0]
        if max_life != 40 + 10 * (cages[0] // 6):
            warnings.append('max life %d differs from the rule 40 + 10 * (cages // 6) = %d seen in all '
                            'genuine HD saves; kept as is' % (max_life, 40 + 10 * (cages[0] // 6)))
        if mode:
            warnings.append('save resumes in revisit mode (world %d, back to %r); revisit return to '
                            'the campaign is not verified with converted saves' % (world, lar))
        if f['end_of_game'] and not mode:
            warnings.append('end-of-game flag set')
    if errors:
        raise SaveError('refusing to convert:\n  - ' + '\n  - '.join(errors))
    return warnings


def award_word2(env):
    """HD award word 2: bit i set when world i (0 = Total) has all its cages (writer 82104AA8)."""
    return sum(1 << i for i in range(10) if env[2 * i] == CAGE_MAX[i])


def build_hd(f, menu=HD_DEFAULT_MENU, options=HD_DEFAULT_OPTIONS, award_words=None):
    if award_words is None:
        award_words = [0] * 10
        award_words[2] = award_word2(f['env'])
    h = bytearray(HD_HEADER)
    struct.pack_into('>20I', h, 0, *f['env'])
    struct.pack_into('>4I', h, 0x50, *f['key_algo'])
    struct.pack_into('>II', h, 0x60, f['end_of_game'], f['max_world'])
    h[0x68:0x78] = menu
    struct.pack_into('>I', h, 0x78, f['warned_autosave'])
    struct.pack_into('>5I', h, 0x7C, *f['revisit'])
    for off, name in ((0x90, f['level']), (0xA4, f['level_after_revisit'])):
        b = name.encode('ascii')
        if len(b) > 19:
            raise SaveError('level name %r longer than 19 characters' % name)
        h[off:off + len(b)] = b
    struct.pack_into('>10I', h, 0xB8, *award_words)
    body = bytearray(h) + options
    for name, tb, cnt, vals in f['elements']:
        n = name + b'\0'
        body += bytes([len(n)]) + n + bytes([tb, cnt]) + struct.pack('>%dI' % cnt, *vals)
    body += b'\0'
    out = HD_MAGIC + struct.pack('>I', len(body)) + bytes(body)
    if len(out) > LOADER_LIMIT:
        raise SaveError('converted save larger than the HD loader buffer')
    return out


def describe(f):
    env = f['env']
    els = {n.decode(): v for n, _, _, v in f['elements']}
    g = els.get('global save', [])
    lines = [
        'resume level        : %s' % f['level'],
        'highest world       : %d   end of game: %d' % (f['max_world'], f['end_of_game']),
        'revisit             : mode %d, world %d, origin %d, after-revisit level %r'
        % (f['revisit'][0], f['revisit'][3], f['revisit'][4], f['level_after_revisit']),
        'cages total / world : %d / %s' % (env[0], env[2::2]),
        'score total / world : %d / %s' % (env[1], env[3::2]),
        'life max / current  : %s / %s' % (els.get('save max life'), els.get('save current life')),
        'global save words   : %d (cage bitmask %08x %08x)' % (len(g), g[0] if g else 0, g[1] if g else 0),
    ]
    if 'award_words' in f:
        lines.append('HD award words      : %s' % ' '.join('%x' % w for w in f['award_words']))
    return '\n'.join(lines)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def is_slot_file(path):
    """True for an HD content slot file .../00000001/<NAME>/<NAME> (relative paths resolved first)."""
    path = Path(path).resolve()
    return path.parent.name.lower() == path.name.lower() and path.parent.parent.name == '00000001'


def backup_dir_for(path, backup_dir=None):
    """Where the --force backup of an existing output goes. Not inside an HD slot directory: when the title
    next saves, the runtime's staged commit (D-049, tools/m20_save_commit.h) deletes every file in the slot
    directory that the new save lacks, so a backup there would be lost at the first level change. For a slot
    file the default is <home>/save_converter_backups, the home being the folder that holds 'profiles'."""
    if backup_dir:
        return Path(backup_dir)
    if not is_slot_file(path):
        return path.parent
    for anc in path.resolve().parents:
        if anc.name.lower() == 'profiles':
            return anc.parent / BACKUP_DIR_NAME
    raise SaveError('output %s is an HD slot outside a profiles folder; give --backup-dir (a folder outside '
                    'the slot) for the backup of the existing slot' % path)


def write_output(path, data, force, backup_dir=None):
    path = Path(path)
    if path.is_dir():
        raise SaveError('output %s is a directory; give the slot file path' % path)
    backup = None
    if path.exists():
        if not force:
            raise SaveError('output %s already exists; refusing to overwrite (use --force, which '
                            'first copies it to a .bak file)' % path)
        bdir = backup_dir_for(path, backup_dir)
        if is_slot_file(path) and path.parent.resolve() in (bdir.resolve(), *bdir.resolve().parents):
            raise SaveError('backup folder %s is inside the slot directory, where the game deletes it at its '
                            'next save; choose a folder outside the slot' % bdir)
        bdir.mkdir(parents=True, exist_ok=True)
        backup = bdir / (path.name + '.bak-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
        if backup.exists():
            raise SaveError('backup %s already exists' % backup)
        shutil.copy2(path, backup)
        if sha256(backup) != sha256(path):
            raise SaveError('backup verification failed; output not written')
    if backup is None:
        with open(path, 'xb') as out:  # exclusive create: never replaces a file that appeared meanwhile
            out.write(data)
    else:
        tmp = path.with_name(path.name + '.tmp-convert')
        if tmp.exists():
            raise SaveError('stale temporary file %s exists; remove it first' % tmp)
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()
    if path.read_bytes() != data:
        raise SaveError('output verification failed')
    return backup


def read_small(path, what):
    if not path.is_file():
        raise SaveError('%s %s not found' % (what, path))
    if path.stat().st_size > INPUT_LIMIT:
        raise SaveError('%s %s is %d bytes; a save is a few hundred bytes, so this is not one'
                        % (what, path, path.stat().st_size))
    return path.read_bytes()


def main(argv=None):
    ap = argparse.ArgumentParser(description='Convert a Rayman 3 PC (2003) .sav to a Rayman 3 HD Recompiled '
                                             'save slot file. The input is never modified.')
    ap.add_argument('--input', required=True, help='PC .sav file (or an HD slot file with --dry-run)')
    ap.add_argument('--output', help='HD slot file to write (refused if it exists, unless --force)')
    ap.add_argument('--donor', help='optional HD slot file whose HD-only settings bytes (menu block, '
                                    'options/volumes) are kept; no progress is taken from it')
    ap.add_argument('--force', action='store_true', help='replace an existing output after copying it to .bak')
    ap.add_argument('--backup-dir', help='folder for the --force backup (default: beside a plain output file; '
                                         'for an HD slot <home>/%s, never inside the slot)' % BACKUP_DIR_NAME)
    ap.add_argument('--dry-run', action='store_true', help='decode, validate and print; write nothing')
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # paths with characters the console code page lacks
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='replace')
    if not a.dry_run and not a.output:
        ap.error('--output is required unless --dry-run is given')
    try:
        inp = Path(a.input)
        raw = read_small(inp, 'input')
        in_hash = hashlib.sha256(raw).hexdigest()
        print('input  %s  %d bytes  sha256 %s' % (inp, len(raw), in_hash))
        if raw[:4] == HD_MAGIC:
            if not a.dry_run:
                raise SaveError("input is already an HD save ('AAAA'); nothing to convert")
            f = parse_hd(raw)
            print('format HD (Xbox 360 / HD Recompiled)')
            print(describe(f))
            for w in f['notes'] + validate(f):
                print('WARNING', w)
            print('HD save is structurally valid')
            return 0
        f = fields_from_pc(decode_pc(raw))
        print('format PC (2003), decoded record OK')
        warnings = f['notes'] + validate(f)
        print(describe(f))
        menu, options = HD_DEFAULT_MENU, HD_DEFAULT_OPTIONS
        if a.donor:
            donor = parse_hd(read_small(Path(a.donor), 'donor'))
            menu, options = donor['hd_menu'], donor['hd_options']
            print('HD settings bytes from donor %s' % a.donor)
        else:
            print('HD settings bytes: new-game defaults (volumes 63)')
        out = build_hd(f, menu, options)
        check = parse_hd(out)  # re-read what will be written
        for k in ('env', 'key_algo', 'end_of_game', 'max_world', 'warned_autosave', 'revisit', 'level',
                  'level_after_revisit', 'elements'):
            if check[k] != f[k]:
                raise SaveError('internal round-trip mismatch in %s' % k)
        print('HD award words: word 2 = %#x (complete-cage worlds); others 0 (per-area award progress '
              'restarts)' % check['award_words'][2])
        for w in warnings:
            print('WARNING', w)
        if a.dry_run:
            print('dry run: %d-byte HD save not written' % len(out))
            return 0
        if Path(a.output).resolve() == inp.resolve():
            raise SaveError('output must not be the input file')
        if hashlib.sha256(inp.read_bytes()).hexdigest() != in_hash:
            raise SaveError('input changed while it was being read; nothing written')
        backup = write_output(a.output, out, a.force, a.backup_dir)
        if backup:
            print('existing output backed up to %s' % backup)
        if hashlib.sha256(inp.read_bytes()).hexdigest() != in_hash:
            raise SaveError('input changed during conversion')
        print('wrote  %s  %d bytes  sha256 %s' % (a.output, len(out), hashlib.sha256(out).hexdigest()))
        print('input unchanged')
        return 0
    except (SaveError, OSError) as e:
        print('ERROR', e, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

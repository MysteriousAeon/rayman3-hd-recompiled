#!/usr/bin/env python3
"""M38 regression (no game run): the compacting text packer (D-075).

  * r3hd_mods.py selftest (the M33-M36 checks and the M38 packer checks on synthetic tables)
  * real data (skipped without it): synthetic mods built in a temporary folder from the game's own menu, system and
    storage strings (handles 169-407 that are plain ASCII and reached by a table pointer; every third shortened, every
    third longer than its slot, the rest unchanged):
      - slightly longer texts: the M34 packer packs them and auto gives byte-identical ranges (no compaction);
      - longer texts that fragment the free space: the M34 packer refuses, auto compacts, and every handle of the five
        language tables reads the expected string (shared strings in every language), no other pointer changes, the
        same ranges twice;
      - far too long: refused by both, the compacting refusal names a string, the largest free space and the overage
  * the tool option and the variable: --text-packer m34 keeps the M34 refusal
  * game data unchanged (fix.lvl, fix.ptr); build order: this regression after M37
Writes only into a temporary folder; the synthetic mods hold game text and are deleted.

usage: m38_regression.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import m38_pack_game as pg  # noqa: E402
import r3hd_loc as loc  # noqa: E402
import r3hd_mods as rm  # noqa: E402

results = []


def check(ok, label):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)


def synthetic(paths, folder: Path, grow: int) -> Path:
    fix = (paths["game"] / "GAMEDATAbin" / "fix.lvl").read_bytes()
    tabs, refs = loc.tables(fix), rm.text_refs(paths["game"])
    ovs = []
    for h in range(169, 408):
        try:
            off, slot = loc.string_at(fix, tabs, f"en.{h}")
        except loc.Problem:
            continue
        s = slot[:slot.index(b"\0")]
        if not refs.get(off) or any(c >= 0x80 or c == 0x5C for c in s):
            continue
        t = s.decode("ascii")
        k = len(ovs) % 3
        t = t[:max(1, len(t) // 2)] if k == 0 else t + "a" * (len(slot) - len(s) + grow) if k == 1 else t
        ovs.append({"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": off, "slot_sha256": rm.sha256_bytes(slot),
                    "text": t})
    d = folder / f"grow{grow}"
    d.mkdir()
    (d / "mod.json").write_text(json.dumps({
        "format": 1, "id": f"x.frag{grow}", "name": "frag", "version": "1.0.0",
        "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids(paths), "min_port_version": "0.0.1"},
        "overrides": ovs}), encoding="utf-8")
    return d


def compiled(mod: Path, paths, packer):
    files = rm.read_package(mod)
    m = rm.parse_manifest(files)
    try:
        if packer:
            os.environ[rm.TEXT_PACKER_ENV] = packer
        return rm.compile_mod(m, files, paths), m.get("_text_packer")
    finally:
        os.environ.pop(rm.TEXT_PACKER_ENV, None)


def refusal(fn):
    try:
        fn()
    except rm.Refusal as x:
        return x
    return None


def main() -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    r = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "selftest"], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]
    n = int(last.rsplit("/", 1)[-1]) if "/" in last else 0
    check(r.returncode == 0 and "R3HD_MODS_SELFTEST PASS" in last and n >= 128,
          f"r3hd_mods.py selftest ({last}; at least 113 earlier + 15 M38)")
    bat = (TOOLS / "build_milestone8.bat").read_text(encoding="utf-8")
    check("python tools\\m38_regression.py || exit /b 1" in bat
          and bat.index("m37_regression.py") < bat.index("m38_regression.py"), "build order: this regression after M37")
    tmp = tempfile.TemporaryDirectory()
    paths = pg.paths_for(cache=Path(tmp.name) / "cache")
    game = paths["game"]
    if not (game / "GAMEDATAbin" / "fix.ptr").is_file():
        print("SKIP real-data checks: no game data", flush=True)
        return finish()
    watched = [game / "GAMEDATAbin" / n for n in ("fix.lvl", "fix.ptr")]
    before = [rm.sha256_bytes(p.read_bytes()) for p in watched]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        easy = synthetic(paths, td, 1)
        r34, p34 = compiled(easy, paths, "m34")
        rau, pau = compiled(easy, paths, None)
        check(p34 == pau == "m34" and r34 == rau,
              f"slightly longer texts: the M34 packer packs them; auto gives the same {len(rau)} ranges ({pau})")
        frag = synthetic(paths, td, 6)
        x = refusal(lambda: compiled(frag, paths, "m34"))
        check(x is not None and x.code == "TEXT_TOO_LONG" and "largest free space" in x.detail,
              f"fragmented: the M34 packer refuses ({x.detail if x else 'packed'})")
        r1, p1 = compiled(frag, paths, None)
        r2, _ = compiled(frag, paths, None)
        check(p1 == "compact" and r1 == r2, f"fragmented: auto compacts ({p1}, {len(r1)} ranges), the same ranges twice")
        e = pg.expectation(frag, cache=paths["cache"])
        bad = [k for k in e["want"] if e["after"].get(k, (None, None))[1] != e["want"][k]]
        check(not bad and not e["wrong_ptrs"] and e["moved"] and e["shared"],
              f"fragmented: all {len(e['want'])} handles of the five tables read the expected string ({len(bad)} "
              f"wrong), {len(e['moved'])} strings moved, {len(e['changed_ptrs'])} pointers redirected (shared: "
              f"{len(e['shared'])} handles of other languages), no other pointer changed ({len(e['wrong_ptrs'])})")
        tool = [sys.executable, str(TOOLS / "r3hd_mods.py"), "validate", str(frag), "--json", "--cache", str(paths["cache"])]
        out = json.loads(subprocess.run(tool + ["--text-packer", "m34"], cwd=ROOT, capture_output=True, text=True).stdout)
        out2 = json.loads(subprocess.run(tool, cwd=ROOT, capture_output=True, text=True).stdout)
        check(out.get("code") == "TEXT_TOO_LONG" and out2.get("text_packer") == "compact",
              f"tool: --text-packer m34 refuses, the default validates with the compacting packer "
              f"({out.get('code')}, {out2.get('text_packer')})")
        long_ = synthetic(paths, td, 20)
        x34 = refusal(lambda: compiled(long_, paths, "m34"))
        xc = refusal(lambda: compiled(long_, paths, None))
        check(x34 is not None and xc is not None and "the string at" in xc.detail and "largest free space" in xc.detail
              and "by at least" in xc.detail, f"far too long: refused by both ({xc.detail if xc else 'packed'})")
    check(before == [rm.sha256_bytes(p.read_bytes()) for p in watched], "game data unchanged (fix.lvl, fix.ptr)")
    tmp.cleanup()
    return finish()


def finish() -> int:
    n = results.count(False)
    print(f"M38_REGRESSION {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())

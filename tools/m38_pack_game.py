#!/usr/bin/env python3
"""M38 (D-075): the compacting text packer, checked against every language table, offline and in the running game.

  m38_pack_game.py check --mod DIR [--packer auto|m34|compact]
      offline: compiles the mod (tools/r3hd_mods.py), applies its fix.lvl ranges to a copy of the game's fix.lvl in
      memory and resolves every handle of the five language tables. Each must read the override's text where its
      original string is overridden (in every language that shares it) and its original string everywhere else; a
      fix.ptr pointer may change only if it pointed at an overridden string. `M38_PACK_CHECK PASS`.
  m38_pack_game.py suite TAG --mod DIR
      four hidden, muted runs without a physical controller (tools/m9_license_run.py, config/m34/menu_quit.txt): the
      main menu and the quit dialog in English and in Spanish (--user_language=5), each without and with the mod's
      plan. At the main menu a read-only probe reads the five language tables from guest memory (text block 82BCE1A0,
      RE_NOTES "M14") and compares every handle with the expectation above (no plan: the original tables).
  m38_pack_game.py judge TAG
  m38_pack_game.py intro-text TR_RUN FREE_RUN...
      read-only, existing frames: a text-only judgement of the intro_10 tutorial line (the M34 suite's intro check
      also requires the whole scene above the box to match one baseline, which fails between runs without any mod,
      E-176 / E-196). Passes when the tutorial line of TR_RUN differs from every mod-free run by at least 8 and by
      at least 5 times the largest difference between two mod-free runs. The scene is reported, never judged here;
      this does not change or replace the M34 suite's result. `M38_INTRO_TEXT PASS`.
Runs, plans, probe results and frames are game-derived: private/work/m38 and private/work/m6_runs only. No guest
memory is written.
"""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import r3hd_loc as loc  # noqa: E402
import r3hd_mods as rm  # noqa: E402

ROOT = m12.ROOT
TOOLS = ROOT / "tools"
WORK = ROOT / "private" / "work" / "m38"
MENU = ROOT / "config" / "m34" / "menu_quit.txt"
SPANISH = "--user_language=5"
CASES = {"en_off": (False, False), "en_tr": (True, False), "es_off": (False, True), "es_tr": (True, True)}
TEXT_BLOCK, ENGINE_BLOCK = 0x82BCE1A0, 0x82C06220   # RE_NOTES "M14": block[3] = the language list; byte +0x1B38
LANG_INDEX = {lang: i for i, lang in enumerate(loc.LANGS)}
SHARED_PROBE = range(402, 408)   # en.402-407: one copy for all five languages (RE_NOTES "M37")
# Menu words and the quit sentence (frame regions of tools/m34_loc_game.py, 1280x720)
MENU_COLUMN = (380, 186, 660, 474)   # below New, whose highlight pulses
QUIT_TEXT = (330, 250, 950, 400)


def paths_for(game_dir=None, cache=None):
    """The game data; the glyph / texture cache in this tool's own folder (never the person's play cache)."""
    return rm.resolve_paths(argparse.Namespace(home=None, mods_root=None, cache=str(cache or WORK / "cache"),
                                               game_dir=game_dir))


def resolve(d: bytes, tabs: dict) -> dict:
    """{(language, handle): (file offset, string bytes)} for every handle with a string."""
    out = {}
    for lang, (base, n) in tabs.items():
        for h in range(n):
            v = struct.unpack_from(">I", d, base + 4 * h)[0]
            if v:
                off = v + rm.REF_BIAS
                out[(lang, h)] = (off, bytes(d[off:d.index(b"\0", off)]))
    return out


def expectation(mod_dir: Path, game_dir=None, packer=None, cache=None) -> dict:
    """The mod's compiled fix.lvl and every table string it must give, from an independent rule (see the docstring)."""
    paths = paths_for(game_dir, cache)
    saved = os.environ.get(rm.TEXT_PACKER_ENV)
    if packer:
        os.environ[rm.TEXT_PACKER_ENV] = packer
    try:
        files = rm.read_package(mod_dir)
        m = rm.parse_manifest(files)
        ranges = rm.compile_mod(m, files, paths)
    finally:
        os.environ.pop(rm.TEXT_PACKER_ENV, None)
        if saved is not None:
            os.environ[rm.TEXT_PACKER_ENV] = saved
    fixp = paths["game"] / "GAMEDATAbin" / "fix.lvl"
    orig = fixp.read_bytes()
    new = bytearray(orig)
    for path, off, data, _ in ranges:
        if Path(path).resolve() == fixp.resolve():
            new[off:off + len(data)] = data
    tabs = loc.tables(orig)
    glyphs = rm.glyph_chars(m)
    defined = rm.font_defined(paths)
    over = {o["offset"]: rm.encode_text(o["text"], glyphs, defined) for o in m["overrides"] if o["type"] == "text"}
    before, after = resolve(orig, tabs), resolve(bytes(new), tabs)
    want = {k: over.get(off, s) for k, (off, s) in before.items()}
    refs = rm.text_refs(paths["game"])
    locs = sorted(loc_ for v in refs.values() for loc_ in v)
    changed_ptrs = [loc_ for loc_ in locs if new[loc_:loc_ + 4] != orig[loc_:loc_ + 4]]
    wrong_ptrs = [loc_ for loc_ in changed_ptrs if struct.unpack_from(">I", orig, loc_)[0] + rm.REF_BIAS not in over]
    moved = sorted(off for off in over
                   if any(struct.unpack_from(">I", new, loc_)[0] + rm.REF_BIAS != off for loc_ in refs.get(off, [])))
    shared = sorted(f"{lang}.{h}" for (lang, h), (off, _) in before.items() if lang != "en" and off in over)
    return {"mod": m["id"], "packer": m.get("_text_packer"), "ranges": len(ranges), "overrides": len(over),
            "before": before, "after": after, "want": want, "changed_ptrs": changed_ptrs, "wrong_ptrs": wrong_ptrs,
            "moved": moved, "shared": shared, "tabs": tabs}


def cmd_check(mod_dir: Path, packer=None) -> int:
    e = expectation(mod_dir, packer=packer)
    bad = sorted(f"{k[0]}.{k[1]}" for k in e["want"] if e["after"].get(k, (None, None))[1] != e["want"][k])
    turkish = sorted(f"{k[0]}.{k[1]}" for k in e["want"] if e["want"][k] != e["before"][k][1])
    probe = {f"{lang}.{h}": e["after"].get((lang, h), (0, b""))[1] == e["want"].get((lang, h))
             for lang in loc.LANGS for h in SHARED_PROBE}
    ok = not bad and not e["wrong_ptrs"] and all(probe.values())
    print(f"mod {e['mod']}: packer {e['packer']}, {e['ranges']} ranges, {e['overrides']} text overrides, "
          f"{len(e['moved'])} strings moved, {len(e['changed_ptrs'])} pointers redirected", flush=True)
    print(f"  handles: {len(e['want'])} with a string in five tables; {len(turkish)} read new text "
          f"({len(e['shared'])} of them in another language's table: shared strings); {len(bad)} wrong {bad[:8]}")
    print(f"  pointers changed that did not point at an overridden string: {len(e['wrong_ptrs'])}")
    print(f"  en.402-407 in every language read the new text: {all(probe.values())}")
    print(f"M38_PACK_CHECK {'PASS' if ok else 'FAIL'}", flush=True)
    return 0 if ok else 1


# ---------------------------------------------------------------------------------------------------------------
# In the game (hidden)

def no_game_running() -> bool:
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq r3hd.exe"], capture_output=True, text=True)
    return "r3hd.exe" not in r.stdout


def read_tables(pid: int, base: int) -> dict:
    """Read-only: the five tables as the guest has them: {(language, handle): (guest address, bytes)}, language byte."""
    from m5_live import Process
    p = Process(pid, base)
    block = p.words(TEXT_BLOCK, 5)
    lang_byte = p.read(ENGINE_BLOCK + 0x1B38, 1)
    out = {}
    for lang, i in LANG_INDEX.items():
        tbl, sizes = p.words(block[3] + 8 * i, 2)
        if sizes != (loc.CAPACITY << 16) | loc.HANDLES:
            raise RuntimeError(f"language {lang}: entry sizes {sizes:#x}")
        entries = p.words(tbl, loc.HANDLES)
        for h, a in enumerate(entries):
            if a:
                raw = p.read(a, 2048) or b""
                out[(lang, h)] = (a, raw.split(b"\0", 1)[0])
    return {"tables": out, "language": lang_byte[0] if lang_byte else None}


def table_run(tag, case, plan) -> dict:
    with_plan, spanish = CASES[case]
    run = f"m38_{tag}_{case}"
    run_dir = m12.RUNS / run
    if run_dir.exists() or (m12.PROFILES / run).exists():
        raise SystemExit(f"run or profile already exists for {run}")
    for _ in range(60):
        if no_game_running():
            break
        time.sleep(2)
    else:
        raise SystemExit("an r3hd.exe is still running: not starting another game")
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_M22_DRAW_TRACE", rm.TEXT_PACKER_ENV):
        env.pop(k, None)
    if with_plan:
        env["R3HD_MODS_PLAN"] = str(Path(plan).resolve())
    cmd = [sys.executable, str(TOOLS / "m9_license_run.py"), run, str(MENU), "--license-mask", "1", "--seconds", "140",
           "--user-root", run] + ([f"--extra={SPANISH}"] if spanish else [])
    log = WORK / tag / f"{case}.driver.log"
    res = {"run": run, "case": case}
    with log.open("w", encoding="utf-8") as out:
        game = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
        base, menu_at, end = None, None, time.monotonic() + 150
        while time.monotonic() < end and game.poll() is None and menu_at is None:
            time.sleep(1)
            rl = run_dir / "runtime.log"
            if rl.is_file():
                text = rl.read_text(errors="replace")
                m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                base = m.group(1) if m else base
                if "menumap.lvl result=00000000" in text.lower() and base:
                    menu_at = time.monotonic()
        if menu_at is None:
            res["error"] = "the main menu was not reached"
        else:
            time.sleep(12)   # the menu frame of menu_quit.txt is at +22 s; the tables are loaded long before
            try:
                pid = json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"]
                got = read_tables(pid, int(base, 16))
                res["language"] = got["language"]
                res["tables"] = {f"{k[0]}.{k[1]}": [f"{a:08X}", s.hex()] for k, (a, s) in got["tables"].items()}
            except (OSError, RuntimeError, TypeError, ValueError, KeyError) as x:
                res["error"] = f"probe: {type(x).__name__}: {x}"
        try:
            res["exit"] = game.wait(timeout=300)
        except subprocess.TimeoutExpired:
            game.kill()
            res["exit"] = None
    (WORK / tag / f"{case}.probe.json").write_text(json.dumps(res) + "\n", encoding="utf-8")
    print(f"run {case}: exit {res.get('exit')} {res.get('error', '')}", flush=True)
    return res


def suite_run(tag, mod_dir: Path) -> int:
    home = WORK / tag
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    margs = ["--mods-root", str(home / "mods"), "--cache", str(home / "cache"), "--json"]

    def mods(*a):
        r = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), *a, *margs], cwd=ROOT, capture_output=True,
                           text=True)
        out = json.loads(r.stdout)
        if out.get("result") != "ok":
            raise SystemExit(f"r3hd_mods.py {' '.join(a)} refused: {out}")
        return out
    mid = json.loads((mod_dir / "mod.json").read_text(encoding="utf-8"))["id"]
    mods("import", str(mod_dir), "--enable")
    listed = mods("list")
    plan = mods("plan", "--out", str(home / "plan"))["plan"]
    (home / "ids.json").write_text(json.dumps({"mod": str(mod_dir), "id": mid, "plan": plan,
                                               "text_packer": next(m.get("text_packer") for m in listed["mods"])}))
    for case in CASES:
        table_run(tag, case, plan)
    return suite_judge(tag)


def suite_judge(tag) -> int:
    from m34_loc_game import frames, region_diff
    ids = json.loads((WORK / tag / "ids.json").read_text())
    results = []

    def check(ok, label):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)
    check(ids["text_packer"] == "compact", f"the mod's text is placed by the compacting packer ({ids['text_packer']})")
    e = expectation(Path(ids["mod"]))
    expect = {False: {f"{k[0]}.{k[1]}": v[1] for k, v in e["before"].items()},
              True: {f"{k[0]}.{k[1]}": v for k, v in e["want"].items()}}
    file_off = {False: {f"{k[0]}.{k[1]}": v[0] for k, v in e["before"].items()},
                True: {f"{k[0]}.{k[1]}": v[0] for k, v in e["after"].items()}}
    probes = {c: json.loads((WORK / tag / f"{c}.probe.json").read_text()) for c in CASES}
    for case, (with_plan, spanish) in CASES.items():
        pr = probes[case]
        tables = pr.get("tables")
        if not tables:
            check(False, f"{case}: probe ({pr.get('error')})")
            continue
        got = {k: bytes.fromhex(v[1]) for k, v in tables.items()}
        wrong = sorted(k for k in expect[with_plan] if got.get(k) != expect[with_plan][k])
        extra = sorted(set(got) - set(expect[with_plan]))
        delta = {int(v[0], 16) - file_off[with_plan][k] for k, v in tables.items() if k in file_off[with_plan]}
        check(not wrong and not extra and len(delta) == 1,
              f"{case}: the guest's five tables ({len(got)} handles) read exactly the "
              f"{'plan' if with_plan else 'original'} strings, every pointer at its expected place (one load offset: "
              f"{len(delta)}); wrong {wrong[:6]}")
        lang = LANG_INDEX["es" if spanish else "en"]
        check(pr.get("language") == lang, f"{case}: the title's language index is {pr.get('language')} "
              f"({'es' if spanish else 'en'} = {lang})")
        if with_plan:
            shared = [f"{lg}.{h}" for lg in loc.LANGS for h in SHARED_PROBE]
            check(all(got.get(k) == expect[True][k] != expect[False][k] for k in shared),
                  f"{case}: en.402-407 read the Turkish text in all five tables (one copy; its guest addresses: "
                  f"{sorted(set(tables[k][0] for k in shared if k.startswith('en.')))[:6]})")
    log = {c: (m12.RUNS / probes[c]["run"] / "runtime.log").read_text(errors="replace")
           if (m12.RUNS / probes[c]["run"] / "runtime.log").is_file() else "" for c in CASES}
    for case, (with_plan, _) in CASES.items():
        m = re.search(r"M33 mods state=active .*?ranges=(\d+)", log[case])
        served = log[case].count("M33 mods served ")
        check(bool(m) and served == int(m.group(1)) if with_plan
              else "M33 mods=off" in log[case] and "M33 mods state=active" not in log[case],
              f"{case}: plan {'active, every range served' if with_plan else 'off'} "
              f"({m.group(0)[:80] if m else 'no active line'}; served {served})")
        check(probes[case].get("exit") == 0, f"{case}: the title ended by its own Exit Game (exit code 0)")
    fr = {c: frames(probes[c]["run"]) for c in CASES}
    if all(len(v) == 2 for v in fr.values()):
        en_menu = region_diff(fr["en_off"][0], fr["en_tr"][0], MENU_COLUMN)
        en_quit = region_diff(fr["en_off"][1], fr["en_tr"][1], QUIT_TEXT)
        es_menu = region_diff(fr["es_off"][0], fr["es_tr"][0], MENU_COLUMN)
        es_quit = region_diff(fr["es_off"][1], fr["es_tr"][1], QUIT_TEXT)
        lang_menu = region_diff(fr["en_off"][0], fr["es_off"][0], MENU_COLUMN)
        check(en_menu >= 8 and en_quit >= 8, f"English: menu words ({en_menu}) and the quit sentence ({en_quit}) change")
        check(es_menu <= 3 and es_quit <= 3 and lang_menu >= 8,
              f"Spanish: menu ({es_menu}) and quit dialog ({es_quit}) equal with and without the plan; the Spanish "
              f"menu differs from the English one ({lang_menu})")
        (WORK / f"{tag}_judge.json").write_text(json.dumps({"en_menu": en_menu, "en_quit": en_quit, "es_menu": es_menu,
                                                            "es_quit": es_quit, "lang_menu": lang_menu}) + "\n")
    else:
        check(False, f"two frames per run ({ {c: len(v) for c, v in fr.items()} })")
    runs = [probes[c]["run"] for c in CASES]
    for judge_tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / judge_tool), "--run", *runs], cwd=ROOT, capture_output=True,
                           text=True)
        check(r.returncode == 0, f"{judge_tool} --run (all {len(runs)} runs)")
    n = results.count(False)
    print(f"M38_PACK_GAME {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


def intro_text(tr_run: str, free_runs: list) -> int:
    """See the module doc: the tutorial line only, against the spread of runs without a mod."""
    import itertools
    import m34_loc_game as m34

    def first(run):
        f = sorted((m12.RUNS / run).glob("m3_frame_*.bmp"), key=lambda p: int(re.findall(r"\d+", p.stem)[-1]))
        if not f:
            raise SystemExit(f"{run}: no frames")
        return f[0]
    if len(free_runs) < 2 or tr_run in free_runs:
        raise SystemExit("intro-text TR_RUN FREE_RUN FREE_RUN...: at least two runs without a mod")
    fr = {r: first(r) for r in [tr_run, *free_runs]}
    noise_text = {f"{a}|{b}": m34.region_diff(fr[a], fr[b], m34.TUTORIAL_TEXT)
                  for a, b in itertools.combinations(free_runs, 2)}
    noise_scene = {f"{a}|{b}": m34.region_diff(fr[a], fr[b], m34.INTRO_SCENE)
                   for a, b in itertools.combinations(free_runs, 2)}
    tr = {r: {"text": m34.region_diff(fr[r], fr[tr_run], m34.TUTORIAL_TEXT),
              "scene": m34.region_diff(fr[r], fr[tr_run], m34.INTRO_SCENE)} for r in free_runs}
    noise = max(noise_text.values())
    low = min(v["text"] for v in tr.values())
    ok = low >= max(8.0, 5 * noise)
    res = {"tr_run": tr_run, "text_between_free_runs": noise_text, "scene_between_free_runs": noise_scene,
           "tr_against_free_runs": tr, "verdict": "PASS" if ok else "FAIL",
           "note": "text-only; the scene is reported, not judged; the M34 suite result is unchanged"}
    out = WORK / f"intro_text_{tr_run}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    sc = list(noise_scene.values())
    print(f"tutorial line: {tr_run} against {len(free_runs)} runs without a mod {low} .. "
          f"{max(v['text'] for v in tr.values())}; between those runs at most {noise}")
    print(f"scene (reported only): between runs without a mod {min(sc)} .. {max(sc)} "
          f"({sum(x > 3 for x in sc)} of {len(sc)} pairs above 3); {tr_run} against them "
          f"{min(v['scene'] for v in tr.values())} .. {max(v['scene'] for v in tr.values())}")
    print(f"M38_INTRO_TEXT {res['verdict']} ({out})", flush=True)
    return 0 if ok else 1


def main() -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    if len(sys.argv) > 1 and sys.argv[1] == "intro-text":
        if len(sys.argv) < 5:
            raise SystemExit("intro-text TR_RUN FREE_RUN FREE_RUN...")
        return intro_text(sys.argv[2], sys.argv[3:])
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("check", "suite", "judge"))
    ap.add_argument("tag", nargs="?")
    ap.add_argument("--mod", type=Path)
    ap.add_argument("--packer", choices=rm.TEXT_PACKERS)
    a = ap.parse_args()
    if a.cmd == "check":
        if not a.mod:
            ap.error("check --mod DIR")
        return cmd_check(a.mod, a.packer)
    if not a.tag or not m12.NAME_RE.fullmatch(a.tag):
        ap.error("a TAG of letters, digits, _ and -")
    if a.cmd == "suite":
        if not a.mod:
            ap.error("suite TAG --mod DIR")
        return suite_run(a.tag, a.mod)
    return suite_judge(a.tag)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""M35 regression (no game run): movie subtitle overrides (VS.sub), the translation workflow and the PC converter's
real-package cases on the person's own game data, plus the workflow selftest; and that no tracked file carries the
game's text. Game data is never written; everything this writes stays in a temporary folder. Skips the real-data part
(with a SKIP line) when the game data is absent.

usage: m35_regression.py
"""
import argparse
import hashlib
import io
import json
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402
import r3hd_loc as rl  # noqa: E402
import r3hd_locflow as lf  # noqa: E402
import r3hd_pcmod as pc  # noqa: E402

results = []


def check(ok, label):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def tracked_text_files():
    r = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
    for name in r.stdout.decode("utf-8", "replace").split("\0"):
        p = ROOT / name
        if name and p.suffix.lower() in (".py", ".json", ".md", ".txt", ".toml", ".ps1", ".bat", ".iss", ".h", ".cpp",
                                         ".csv", ".tsv", ".jsonl") and p.is_file():
            yield name, p.read_bytes().decode("utf-8", "replace")


def main() -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    for tool, marker in (("r3hd_locflow.py", "R3HD_LOCFLOW_SELFTEST PASS"), ("r3hd_loc.py", "R3HD_LOC_SELFTEST PASS"),
                         ("r3hd_pcmod.py", "R3HD_PCMOD_SELFTEST PASS")):
        r = run(str(TOOLS / tool), "selftest")
        check(r.returncode == 0 and marker in r.stdout,
              f"{tool} selftest ({r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]})")
    pay = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
    check(pay["version"].startswith(("0.35.0", "0.36.0", "0.49.0", "0.50.0", "1.0.0", "1.0.1", "1.0.2")), f"payload: version {pay['version']} (subtitle overrides need 0.35.0)")
    g = lf.load_glossary(ROOT / "config" / "localization" / "tr" / "glossary.example.json")
    check(g and all(t["tr"] == [t["en"]] for t in g), "glossary example: loads; it only keeps names (no guessed translation)")
    for f in ("WORKFLOW.md", "prompts/draft.md", "prompts/review.md"):
        check((ROOT / "config" / "localization" / f).is_file(), f"config/localization/{f} present")
    game = rm.ROOT / "private" / "extracted" / rm.TITLE_ID
    if not (game / "GAMEDATAbin" / "VS.sub").is_file():
        print("SKIP real-data checks: no game data", flush=True)
        return finish()
    watched = [game / "GAMEDATAbin" / n for n in ("fix.lvl", "fix.ptr", "VS.sub")]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    data = (game / "GAMEDATAbin" / "VS.sub").read_bytes()
    sub = rm.parse_vs_sub(data)
    en = [s for s in sub["ids"] if s.startswith("vs.en.")]
    check(len(sub["cues"]) == 327 and len(en) == 69 and sum(s.startswith("vs.en.42.") for s in en) == 8
          and sub["end"] == len(data),
          "VS.sub: 327 cues, 69 English, eight in movie 42 (menu10.bik); the file ends at its last string (no slack)")
    paths = {"game": game}

    def ov(sid, text):
        return {"type": "subtitle", "id": sid, "source_sha256": rm.sub_hash(sub, sub["ids"][sid]), "text": text}
    i0 = sub["ids"]["vs.en.42.0"]
    same = rm.compile_subtitles([ov("vs.en.42.0", sub["strings"][i0].decode("cp1252"))], paths, frozenset(), None)[0]
    check(data[:same[1]] + same[2] == data, "VS.sub: rebuilding with the game's own text gives the original bytes")
    i2 = sub["ids"]["vs.en.42.2"]
    short = rm.compile_subtitles([ov("vs.en.42.2", "Bir test satırı.")], paths, frozenset("ğĞşŞıİ"), None)[0]
    got = data[:short[1]] + short[2]
    back = rm.parse_vs_sub(got)
    check(len(got) == len(data) and [c[5] for c in back["cues"]] == [c[5] for c in sub["cues"]]
          and all(back["strings"][k] == sub["strings"][k] for k in range(len(sub["strings"])) if k != i2)
          and back["strings"][i2] == "Bir test satırı.".encode("cp1254"),
          "VS.sub: one cue replaced; size, every cue (timing, order, language, index) and every other string unchanged")
    over = "x" * (len(sub["strings"][i0]) + 1)
    # M36 (D-073): one byte over now grows the table by one byte (port 0.36.0 and newer); an older port refuses it.
    g = rm.compile_subtitles([ov("vs.en.42.0", over)], paths, frozenset(), None)[0]
    check(g[1] + len(g[2]) == len(data) + 1 and rm.parse_vs_sub(data[:g[1]] + g[2])["end"] == len(data) + 1,
          "VS.sub (M36): one byte over the file's size grows it by one byte")
    with tempfile.TemporaryDirectory() as hd:
        (Path(hd) / "installer.json").write_text(json.dumps({"version": "0.35.0"}))
        try:
            rm.compile_subtitles([ov("vs.en.42.0", over)], dict(paths, home=Path(hd)), frozenset(), None)
            check(False, "VS.sub: one byte over the file's size is refused on a 0.35 port")
        except rm.Refusal as x:
            check(x.code == "INCOMPATIBLE" and "1 bytes longer" in x.detail,
                  f"VS.sub: one byte over is refused on a 0.35 port ({x.detail})")
    ns = argparse.Namespace(cache=None, game_dir=None)
    lpaths = rl.game_paths(ns)
    rows = rl.catalog_rows(lpaths, "en")
    cat = lf.catalog_index(rows)
    check(len([r for r in rows if r["kind"] == "text"]) == 1188 and len([r for r in rows if r["kind"] == "subtitle"]) == 69
          and sum(r.get("category") == "voiced line" for r in rows) == 520 and cat["vs.en.42.0"]["movie_file"] == "menu10.bik",
          "catalog: 1188 table strings, 69 subtitle cues, 520 voiced lines (sound banks), movie 42 named")
    # no tracked file carries the game's text (every language's table strings and every subtitle of 24+ characters)
    texts = set()
    fix = (game / "GAMEDATAbin" / "fix.lvl").read_bytes()
    t = rl.tables(fix)
    for lang in rl.LANGS:
        for h in range(t[lang][1]):
            try:
                _, slot = rl.string_at(fix, t, f"{lang}.{h}")
            except rl.Problem:
                continue
            s = slot[:slot.index(b"\0")].decode("cp1252", "replace")
            if len(s) >= 24 and not s.startswith("\\hm"):
                texts.add(s)
    texts |= {s.decode("cp1252", "replace") for s in sub["strings"] if len(s) >= 24}
    leaks = [(n, s[:30]) for n, body in tracked_text_files() for s in texts if s in body]
    check(not leaks and len(texts) > 1000, f"tracked files: none holds a game string ({len(texts)} checked; {leaks[:3]})")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        proj = td / "p" / "tr.json"
        lf.cmd_init(proj, "tr.reg", "Reg")
        src = lf.load_project(proj)
        glyphs = lf.project_glyphs(src, proj.parent)
        lf.cmd_export(src, proj.parent, rows, td / "d.jsonl", "draft", "", "", 0, glyphs, "vs.en.42.")
        exp = lf.read_table(td / "d.jsonl")
        check(len(exp) == 8 and all(r["english"] == cat[r["id"]]["text"] for _, r in exp),
              "workflow: a draft export of movie 42 has its eight cues with their English")
        draft = [(1, dict(exp[2][1], turkish="Bir test satırı."))]
        rep = lf.cmd_import(src, proj.parent, rows, draft, "draft", "reg", False, glyphs)
        lf.write_project(proj, src)
        check(rep["changed"] == ["vs.en.42.2"], f"workflow: the draft imports ({rep['rejected']})")
        try:
            rl.cmd_build(lpaths, proj, td / "approved", False)
            check(False, "workflow: a build with nothing approved is refused")
        except rl.Problem as x:
            check("no string to build" in str(x), "workflow: a build with nothing approved is refused")
        dev = rl.cmd_build(lpaths, proj, td / "dev", False, allow_unapproved=True)
        m = json.loads((td / "dev" / "mod.json").read_text(encoding="utf-8"))
        check(dev["id"] == "tr.reg.dev" and "DEV" in m["name"] and m["version"].endswith("-dev")
              and [o["type"] for o in m["overrides"]].count("subtitle") == 1,
              "workflow: the private development build is a separate, marked mod with the subtitle")
        val = lf.cmd_validate(src, proj.parent, rows, glyphs, [], lpaths, proj)
        check(not val["errors"] and val.get("build_check", {}).get("errors") == [], f"workflow: validate on real data ({val['errors'][:2]})")
        # PC converter: the same GF in two archives -> one override; a different one -> reported, the first kept
        z = td / "pc.zip"
        pc.cmd_make_sample(z, "charact/rayman", 64)
        with zipfile.ZipFile(z) as zf:
            members = {n: zf.read(n) for n in zf.namelist()}
        gf = next(n for n in members if n.endswith(".gf"))
        gf888 = bytearray(members[gf])
        gf888[0:4] = struct.pack("<I", 888)
        for label, second, want in (("same", bytes(gf888), "same_as"), ("differs", members[gf][:-1] + bytes([members[gf][-1] ^ 1]), "skipped")):
            z2 = td / f"pc_{label}.zip"
            with zipfile.ZipFile(z2, "w") as zf:
                for n, b in members.items():
                    zf.writestr(n, bytes(gf888) if n == gf else b)
                zf.writestr(gf.replace("tex32_1.cnt", "tex32_2.cnt"), second)
            conv = pc.cmd_convert(lpaths, z2, td / f"out_{label}")
            mm = json.loads((td / f"out_{label}" / "mod.json").read_text(encoding="utf-8"))
            check(len(mm["overrides"]) == 1 and any(want in r for r in conv["textures"]) and conv["textures"][0].get("to"),
                  f"pc: format 888; a {label} copy in tex32_2 gives one override and a '{want}' note")
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    check(before == after, "game data never written")
    return finish()


def finish() -> int:
    n = results.count(False)
    print(f"M35_REGRESSION {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())

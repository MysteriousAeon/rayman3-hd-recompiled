#!/usr/bin/env python3
"""M36: localization stress tests, offline (D-073). Two parts:

  m36_loc_stress.py synthetic   no game data: a generated catalog (3,000 table strings, 400 subtitle cues of this tool's
                                own made-up words, never game text) through the translation workflow (r3hd_locflow.py):
                                drafts with planted invalid rows (unknown, duplicated and shifted ids, an edited English,
                                dropped codes, control characters, characters outside the code page, missing glyphs,
                                oversized subtitles), repeated imports, reviews over approved text, human sheets imported
                                twice, deterministic exports, then a generated VS.sub of 4,000 cues through the subtitle
                                compiler (growth inside and over the limit, repeated rebuilds, the plan's grow record).
                                Ends with M36_LOC_STRESS PASS n/n; peak Python memory is measured and bounded.
  m36_loc_stress.py real        the person's game data (read only; nothing is written beside it): the font atlas's room
                                for further glyph pictures, the real VS.sub's growth headroom, conflicting subtitle mods
                                and a tampered grown plan through r3hd_mods.py (private test home under private/work/m36).
                                Statistics only (M36_LOC_REAL PASS n/n).

These are parser and compiler tests: they say nothing about what the game shows (tools/m36_sub_game.py does).
"""
import json
import random
import shutil
import struct
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_locflow as lf  # noqa: E402
import r3hd_mods as rm  # noqa: E402

ROOT = rm.ROOT
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ' :: ' + str(detail)[:400]}", flush=True)


WORDS = ("amber", "lantern", "meadow", "pebble", "thistle", "copper", "harbour", "willow", "ember", "quarry", "saddle",
         "cobalt", "orchard", "beacon", "furrow", "garnet")
TR_WORDS = ("kehribar", "fener", "çayır", "çakıl", "devedikeni", "bakır", "liman", "söğüt", "kor", "taş ocağı", "eyer",
            "kobalt", "meyve bahçesi", "işaret", "karık", "lal", "ışık", "İzmir", "ağaç", "şimşek")
GLYPHS = frozenset("ğĞşŞıİ")


def sha(s):
    return rm.sha256_bytes(s.encode())


def make_catalog(rnd, n_text=3000, n_sub=400):
    cat = []
    for i in range(n_text):
        words = " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(1, 8))).capitalize()
        code = rnd.random()
        text = ("\\jc" + words) if code < 0.1 else (words + " \\f1:3\\f0:") if code < 0.15 else \
            (words + "\\l" + rnd.choice(WORDS)) if code < 0.25 else words + rnd.choice(".!?")
        cat.append({"id": f"en.{i}", "kind": "text", "text": text, "capacity": len(text) + rnd.randint(0, 6),
                    "source_sha256": sha(f"t{i}:{text}"), "category": "voiced line" if i % 7 == 0 else ""})
    for k in range(n_sub):
        movie, n = 1 + k // 50, k % 50
        text = " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(3, 14))).capitalize() + "."
        cat.append({"id": f"vs.en.{movie}.{n}", "kind": "subtitle", "text": text, "source_sha256": sha(f"s{k}:{text}"),
                    "category": "movie subtitle", "movie": movie, "movie_file": ""})
    return cat


def turkish(rnd, english, room):
    """A synthetic Turkish line keeping the English codes and breaks, at most `room` bytes when room is given."""
    lead = "\\jc" if english.startswith("\\jc") else ""
    tail = " \\f1:3\\f0:" if english.endswith("\\f1:3\\f0:") else ""
    parts = english.replace("\\jc", "").replace(" \\f1:3\\f0:", "").split("\\l")
    out = []
    for _ in parts:
        w = " ".join(rnd.choice(TR_WORDS) for _ in range(rnd.randint(1, 4)))
        out.append(w[:1].upper() + w[1:])   # not str.capitalize(): it turns İ into i + U+0307
    t = lead + "\\l".join(out) + tail
    end = english.rstrip()[-1:]
    if end in "?!." and not tail:
        t += end
    while room and len(rm.encode_text(t, GLYPHS)) > room and len(t) > len(lead + tail) + 2:
        t = lead + t[len(lead):len(t) - len(tail) - 2].rstrip() + tail + (end if end in "?!." and not tail else "")
    return t


def synthetic() -> int:
    rnd = random.Random(36)
    tracemalloc.start()
    t0 = time.time()
    cat = make_catalog(rnd)
    by_id = {c["id"]: c for c in cat}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        proj = td / "proj" / "tr.json"
        lf.cmd_init(proj, "tr.stress", "Stres")
        src = lf.load_project(proj)
        exp = lf.cmd_export(src, proj.parent, cat, td / "draft.jsonl", "draft", "", "", 0, GLYPHS)
        exp2 = lf.cmd_export(src, proj.parent, cat, td / "draft2.jsonl", "draft", "", "", 0, GLYPHS)
        check("export: 3,400 rows, byte-identical twice", exp["rows"] == len(cat)
              and (td / "draft.jsonl").read_bytes() == (td / "draft2.jsonl").read_bytes(), exp["rows"])
        rows = lf.read_table(td / "draft.jsonl")
        out, planted = [], {}
        for n, r in rows:
            c = by_id[r["id"]]
            room = c.get("capacity", rm.SUB_MAX_TEXT) if c["kind"] == "text" else rm.SUB_MAX_TEXT
            r = dict(r, turkish=turkish(rnd, c["text"], room if rnd.random() < 0.7 else 0))
            k = int(r["id"].split(".")[-1])
            if r["id"].startswith("en.") and k % 97 == 5:
                r["turkish"] = ""                               # untranslated: skipped
            out.append((n, r))
        # planted invalid rows, in place of the rows they damage (each must be rejected, nothing else). A duplicated
        # id rejects every copy: the shifted id takes out[2]'s copy with it, the repeated row its original.
        empty = sum(1 for _, r in out if not r["turkish"])
        sub_at = next(i for i, (_, r) in enumerate(out) if r["id"].startswith("vs.") and r["turkish"])
        code_at = next(i for i, (_, r) in enumerate(out) if "\\jc" in r["english"] and r["turkish"] and i > 20)
        planted = {
            1: ("shifted id", dict(out[1][1], id=out[2][1]["id"])),
            3: ("edited English", dict(out[3][1], english=out[3][1]["english"] + " x")),
            4: ("control character", dict(out[4][1], turkish="Bir\nİki")),
            6: ("outside the code page", dict(out[6][1], turkish="Fener €")),
            sub_at: ("oversized subtitle", dict(out[sub_at][1], turkish="ş" * 401)),
            code_at: ("dropped code", dict(out[code_at][1], turkish=out[code_at][1]["turkish"].replace("\\jc", ""))),
        }
        assert not any(not out[i][1]["turkish"] for i in planted) and not out[2][1]["turkish"] == "" \
            and out[10][1]["turkish"]
        table = [(n, planted[i][1] if i in planted else r) for i, (n, r) in enumerate(out)]
        table += [(90000, dict(out[0][1], id="en.99999")), (90001, dict(out[10][1]))]
        rep = lf.cmd_import(src, proj.parent, cat, table, "draft", "stress", False, GLYPHS)
        got = sorted((x["id"], x["reason"].split(" (")[0]) for x in rep["rejected"])
        want_ids = sorted([out[2][1]["id"]] * 2 + [out[10][1]["id"]] * 2 + ["en.99999"]
                          + [out[i][1]["id"] for i in (3, 4, 6, sub_at, code_at)])
        check("draft import: every planted invalid row is rejected with a reason; a duplicated id rejects every copy",
              sorted(x[0] for x in got) == want_ids and all(x[1] for x in got), got)
        accepted = len(rep["changed"])
        check("draft import: the rest is taken; empty Turkish skipped",
              accepted == len(out) - empty - (len(planted) + 2)   # out[2] and out[10]: duplicated
              and sum(1 for s in rep["skipped"] if "no Turkish" in s["reason"]) == empty,
              (accepted, empty, len(out), len(rep["skipped"])))
        lf.write_project(proj, src)
        first = proj.read_bytes()
        rep2 = lf.cmd_import(src, proj.parent, cat, table, "draft", "stress", False, GLYPHS)
        lf.write_project(proj, src)
        check("draft import twice: idempotent (no change, the same rows rejected, the project byte-identical)",
              not rep2["changed"] and len(rep2["rejected"]) == len(rep["rejected"]) and proj.read_bytes() == first)
        # glyphs missing: the same draft with no Turkish glyphs refuses every row with ğ ş ı İ, and only those
        src_ng = lf.load_project(proj)
        for e in src_ng["strings"].values():
            e["status"] = "draft"
        ng = lf.cmd_import(src_ng, proj.parent, cat, out, "draft", "ng", True, frozenset())
        need = sum(1 for _, r in out if r["turkish"] and set(r["turkish"]) & set("ğĞşŞıİ"))
        check("missing glyphs: every row with a Turkish-only letter is rejected when the glyphs are absent",
              len(ng["rejected"]) == need and all("glyph" in x["reason"] for x in ng["rejected"]),
              (len(ng["rejected"]), need))
        # approve everything, then a review over approved text changes no text
        for e in src["strings"].values():
            e["status"] = "approved"
        snap = {k: v["text"] for k, v in src["strings"].items()}
        review = [(i, {"id": sid, "check": lf.check_of(by_id[sid]["source_sha256"]), "verdict": "change",
                       "turkish": e["text"], "suggestion": e["text"] + " (öneri)", "review_note": "stress"})
                  for i, (sid, e) in enumerate(sorted(src["strings"].items())[:1500])]
        rr = lf.cmd_import(src, proj.parent, cat, review, "review", "model-b", False, GLYPHS)
        check("review over 1,500 approved strings: suggestions stored, no approved text changed",
              {k: v["text"] for k, v in src["strings"].items()} == snap and not rr["rejected"]
              and sum(1 for v in src["strings"].values() if v.get("review")) == 1500, (len(rr["rejected"]),))
        # human sheet: accept 500 suggestions, reject 500; imported twice
        human = lf.cmd_export(src, proj.parent, cat, td / "human.csv", "human", "pending", "", 0, GLYPHS)
        hrows = lf.read_table(td / "human.csv")
        for i, (_, r) in enumerate(hrows):
            r["decision"] = "accept" if i < 500 else "reject" if i < 1000 else ""
        h1 = lf.cmd_import(src, proj.parent, cat, hrows, "human", "", False, GLYPHS)
        lf.write_project(proj, src)
        after = proj.read_bytes()
        h2 = lf.cmd_import(src, proj.parent, cat, hrows, "human", "", False, GLYPHS)
        lf.write_project(proj, src)
        check("human sheet: 1,000 decisions applied; the same sheet again is a no-op",
              human["rows"] == 1500 and len(h1["changed"]) == 1000 and not h1["rejected"] and not h2["changed"]
              and not h2["rejected"] and proj.read_bytes() == after, (human["rows"], len(h1["changed"]),
                                                                     len(h2["rejected"])))
        v = lf.cmd_validate(src, proj.parent, cat, GLYPHS, [], report=td / "findings.csv")
        check("validate: every finding classified (stage known), report written",
              all(f["stage"] != "other" for f in v["findings"]) and (td / "findings.csv").is_file(),
              [f for f in v["findings"] if f["stage"] == "other"][:3])
        st = lf.cmd_status(src, cat, None, GLYPHS)
        check("status: subtitle balance reported with the growth limit",
              st["subtitle_bytes_vs_english"]["limit"] == rm.SUB_MAX_GROW, st["subtitle_bytes_vs_english"])
        # subtitles at scale: a generated VS.sub of 4,000 cues
        game = td / "game"
        (game / "GAMEDATAbin").mkdir(parents=True)
        cues, strings = [], []
        for i in range(4000):
            cues.append((1 + i % 5, 1 + i // 400, 1000 + i, 2000 + i))
            strings.append(" ".join(rnd.choice(WORDS) for _ in range(rnd.randint(2, 9))).encode())
        data = struct.pack("<H", len(cues)) + b"".join(struct.pack("<B3x4I", *c, i) for i, c in enumerate(cues)) \
            + struct.pack("<H", len(strings)) + b"".join(struct.pack("<H", len(s)) + s for s in strings)
        (game / "GAMEDATAbin" / "VS.sub").write_bytes(data)
        sub = rm.parse_vs_sub(data)
        paths = {"game": game}

        def ovs(n_, text_):
            return [{"type": "subtitle", "id": sid, "source_sha256": rm.sub_hash(sub, i), "text": text_}
                    for sid, i in list(sub["ids"].items())[:n_]]
        ok = ovs(4000, "Uzun ama geçerli bir alt yazı satırı, bütün ipuçlarında aynı: " + "ş" * 100)
        r1 = rm.compile_subtitles(ok, paths, GLYPHS, None)
        r2 = rm.compile_subtitles(ok, paths, GLYPHS, None)
        grown = data[:r1[0][1]] + r1[0][2]
        back = rm.parse_vs_sub(grown)
        check("4,000 cues: growth inside the limit, deterministic, cues unchanged, every string the new one",
              r1 == r2 and len(grown) - len(data) <= rm.SUB_MAX_GROW and len(grown) > len(data)
              and [c[5] for c in back["cues"]] == [c[5] for c in sub["cues"]]
              and set(back["strings"]) == {rm.encode_text(ok[0]["text"], GLYPHS)}, (len(grown), len(data)))
        over = ovs(4000, "ş" * 320)
        try:
            rm.compile_subtitles(over, paths, GLYPHS, None)
            check("4,000 cues of 320 bytes: growth over the limit is refused with the overage", False)
        except rm.Refusal as x:
            check("4,000 cues of 320 bytes: growth over the limit is refused with the overage",
                  x.code == "TEXT_TOO_LONG" and "by at most" in x.detail and "shorten" in x.detail, x.detail)
        plan_dir = td / "cache"
        plan = Path(rm.write_plan_files({"cache": plan_dir}, plan_dir, [(r1[0][0], r1[0][1], r1[0][2], "tr.stress")],
                                        [("tr.stress", "1")])).read_text(encoding="utf-8").splitlines()
        check("plan: one file, one grow record to the rebuilt size, one range",
              sum(ln.startswith("grow ") for ln in plan) == 1 and f"grow 0 {len(grown)}" in plan
              and plan[-1] == "end 1 1", plan[:6])
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    check(f"bounded: peak Python memory {peak >> 20} MiB (limit 512), {time.time() - t0:.1f} s", peak < (512 << 20))
    n = results.count(False)
    print(f"M36_LOC_STRESS {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


def real() -> int:
    """The person's game data, read only."""
    game = ROOT / "private" / "extracted" / "5841123F"
    if not (game / rm.SUB_FILE).is_file():
        print("M36_LOC_REAL SKIP no game data")
        return 0
    paths = {"game": game}
    data = (game / rm.SUB_FILE).read_bytes()
    sub = rm.parse_vs_sub(data)
    per_lang = {}
    for i, c in enumerate(sub["cues"]):
        per_lang[c[0]] = per_lang.get(c[0], 0) + 2 + len(sub["strings"][i])
    longest = max(len(s) for s in sub["strings"])
    print(f"  VS.sub: {len(data)} bytes, {len(sub['cues'])} cues, bytes per language {per_lang}, longest string "
          f"{longest}; growth limit {rm.SUB_MAX_GROW}, per subtitle {rm.SUB_MAX_TEXT}")
    # every English cue at the per-cue maximum still fits the growth limit
    worst = sum(rm.SUB_MAX_TEXT + 2 for c in sub["cues"] if c[0] == "en") - per_lang["en"]
    check("VS.sub: every English cue at 400 bytes stays inside the growth limit",
          0 < worst <= rm.SUB_MAX_GROW, worst)
    # the font atlas: how many further glyph pictures of the Turkish size would fit (statistics only)
    fix = (game / "GAMEDATAbin" / "fix.lvl").read_bytes()
    font = rm.read_font(fix)
    hits = rm.resolve_texture(game, {"entry": rm.FONT["atlas"], "bundles": [rm.FONT["bundle"]]})
    bhf, e, w, h, fmt = hits[0]
    with open(bhf.with_suffix(".btf"), "rb") as f:
        f.seek(e[2])
        b0 = f.read(e[1])
        f.seek(e[4])
        b1 = f.read(e[3])
    _, _, lay = rm.layout(w, h, fmt)
    atlas = rm.decode_level(w, h, rm.level_rows((b0, b1), lay[0], fmt), fmt)
    fits = 0
    for n_ in (6, 12, 24, 48, 96):
        try:
            rm.place_glyphs(font, atlas, w, [(f"g{i}", 12, 24) for i in range(n_)])
            fits = n_
        except rm.Refusal:
            break
    print(f"  font atlas {w}x{h} {fmt}: at least {fits} pictures of 12x24 fit (codes for new letters: the six Turkish "
          f"ones only, {''.join(sorted(rm.TURKISH))})")
    check("atlas: room for the six Turkish glyphs with a margin (statistics)", fits >= 12, fits)
    # conflicting subtitle mods and a tampered grown plan, through the mod manager (private test home)
    home = ROOT / "private" / "work" / "m36" / "stress_real"
    if home.exists():
        shutil.rmtree(home)
    margs = {"mods": home / "mods", "cache": home / "cache", "game": game, "home": None}

    def mk(mid, text):
        d = home / "src" / mid
        d.mkdir(parents=True)
        ovs = [{"type": "subtitle", "id": sid, "source_sha256": rm.sub_hash(sub, i), "text": text}
               for sid, i in sub["ids"].items() if sid.startswith("vs.en.42.")]
        (d / "mod.json").write_text(json.dumps({"format": 1, "id": mid, "name": mid, "version": "1.0.0",
                                                "target": {"title_id": rm.TITLE_ID, "releases": ["x360-xbla-5841123F-v1"],
                                                           "min_port_version": "0.36.0"}, "overrides": ovs}),
                                    encoding="utf-8")
        return d
    a = rm.cmd_import(margs, mk("t.grow.a", "Uzun bir deneme: ölçü, süre ve düzen\\lçok daha uzun bir metinle."),
                      enable=True)
    b = rm.cmd_import(margs, mk("t.grow.b", "Öteki deneme: üç ipucu ve uzun\\lsöz öbekleri de var."),
                      enable=True)
    res = rm.resolve_all(margs, home / "plan")
    st = {r["id"]: (r["state"], r.get("code")) for r in res["mods"]}
    check("conflict: two subtitle mods on the same cues: the first in priority applies, the other is refused whole",
          st.get("t.grow.a") == ("active", None) and st.get("t.grow.b") == ("invalid", "CONFLICT"), st)
    plan = Path(res["plan"])
    text = plan.read_text(encoding="utf-8")
    check("plan: the grown VS.sub carries its grow record", "\ngrow 0 " in text)
    before = rm.sha256_bytes(data)
    check("game data unchanged", rm.sha256_bytes((game / rm.SUB_FILE).read_bytes()) == before)
    n = results.count(False)
    print(f"M36_LOC_REAL {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("synthetic", "real"):
        print(__doc__)
        sys.exit(2)
    sys.exit(synthetic() if sys.argv[1] == "synthetic" else real())

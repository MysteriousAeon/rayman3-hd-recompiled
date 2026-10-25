#!/usr/bin/env python3
"""M36 (D-073): a subtitle mod that grows `VS.sub`, in the running game, hidden. Same entry, steps and runner as M35
(`m35_sub_game.py`: knaar_20_human, pause -> Bonus -> Cinematic -> the Otto movie (gallery title en.213), movie 42 =
`menu10.bik`, six frames, all through tools/m9_license_run.py: hidden, muted, no physical controller).

usage:
  m36_sub_game.py make TAG --base MOD     write the private test mods under private/work/m36/TAG/: `grow` (longer
                                          Turkish lines for the English cues of movie 42, filler for every other
                                          English cue and Turkish lines for the Spanish cues of movie 42, which then
                                          lie past the original end of the file) with the glyph overrides of MOD
                                          (the M35 test mod); MOD itself is the same-size case
  m36_sub_game.py suite TAG --base MOD    make, then seven runs: off (no plan), same (MOD, same size), grow, es_off
                                          (Spanish console language, no plan), es_grow (Spanish, grow), bad (the
                                          grow plan with its tail tampered: refused), back (disabled again)
  m36_sub_game.py judge TAG               judge a suite's runs again (M36_SUB_GAME)

The test strings are this tool's own Turkish sentences (no game text); cue hashes come from the person's own
VS.sub. The console language of the Spanish runs is the runtime's `--user_language=5` (XC_LANGUAGE_SPANISH) through
R3HD_HIDDEN_EXTRA. Mods, plans, frames and logs are game-derived: private/ only.
"""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import m35_sub_game as m35  # noqa: E402
import r3hd_mods as rm  # noqa: E402

ROOT = m12.ROOT
TOOLS = ROOT / "tools"
WORK = ROOT / "private" / "work" / "m36"
GAME = ROOT / "private" / "extracted" / "5841123F"
CASES = ("off", "same", "grow", "es_off", "es_grow", "bad", "back")
SPANISH = "--user_language=5"

# Synthetic Turkish test lines (this tool's own sentences), two lines each with the in-band break.
EN42 = [
    "Bu deneme satırı dosyanın eski boyutuna\\lartık sığmak zorunda değil, uzun olabilir.",
    "İkinci satır: uzun Türkçe cümleler\\lartık kısaltılmadan gösterilebiliyor.",
    "Üçüncü satır: ağır ağır ilerleyen gölge\\lsessizce köşeyi dönüp gözden kayboldu.",
    "Dördüncü satır: şimdi çok daha uzun\\lbir alt yazı ekranda görünmeli.",
    "Beşinci satır: iki satırlık bu yazı\\leski dosyadan daha fazla yer kaplıyor.",
    "Altıncı satır: zamanlama ve sıra\\lözgün altyazılarla aynı kalmalı.",
    "Yedinci satır: her ipucu kendi süresince\\lgörünür ve sonra kaybolur.",
    "Sekizinci satır: büyütülmüş dosyanın\\lson baytları da okunabiliyor.",
]
ES42 = [
    "İspanyolca dizi, ilk ipucu: bu yazı\\ldosyanın eski sonunun ötesinde duruyor.",
    "İspanyolca dizi, ikinci ipucu: oyun\\lbüyütülmüş dosyayı sonuna dek okudu.",
    "İspanyolca dizi, üçüncü ipucu: şu an\\lgördüğün baytlar eklenen kısımdan.",
    "İspanyolca dizi, dördüncü ipucu: süre\\lve sıra özgün dosyadaki gibi.",
    "İspanyolca dizi, beşinci ipucu: uzun\\lsatırlar da düzgün görünmeli.",
    "İspanyolca dizi, altıncı ipucu: bölüm\\lsonuna kadar okunmaya devam ediyor.",
    "İspanyolca dizi, yedinci ipucu: ışık\\lyavaşça sönüyor, perde iniyor.",
    "İspanyolca dizi, sekizinci ipucu: göz\\lucuyla bakınca her şey yerinde.",
    "İspanyolca dizi, dokuzuncu ipucu: son\\liki ipucu da eklenen kısımda.",
    "İspanyolca dizi, onuncu ipucu: bitti,\\lbu da dosyanın son satırı değil.",
]
FILLER = ("Dolgu satırı: bu ipucu yalnızca dosyayı büyütmek için uzatıldı\\lve bu testte ekranda görünmesi beklenmiyor.")


def vs_sub():
    return rm.parse_vs_sub((GAME / rm.SUB_FILE).read_bytes())


def make(tag: str, base: Path) -> dict:
    """The grow test mod (and its tampered plan later); MOD is the same-size case as it is."""
    sub = vs_sub()
    bm = json.loads((base / "mod.json").read_text(encoding="utf-8"))
    glyphs = [o for o in bm["overrides"] if o["type"] == "glyph"]
    subs = []

    def ov(sid, text):
        subs.append({"type": "subtitle", "id": sid, "source_sha256": rm.sub_hash(sub, sub["ids"][sid]), "text": text})
    for sid, i in sub["ids"].items():
        lang, movie, n = sid.split(".")[1], int(sid.split(".")[2]), int(sid.split(".")[3])
        if lang == "en" and movie == 42:
            ov(sid, EN42[n])
        elif lang == "en":
            ov(sid, FILLER)
        elif lang == "es" and movie == 42:
            ov(sid, ES42[n])
    home = WORK / tag
    mod = home / "mod_grow"
    if mod.exists():
        shutil.rmtree(mod)
    mod.mkdir(parents=True)
    m = dict(bm, id="tr.m36grow", name="M36 grow test", version="0.1.0",
             description="Private test: a VS.sub longer than the original.", overrides=glyphs + subs)
    m["target"] = dict(bm["target"], min_port_version="0.36.0")
    (mod / "mod.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    # Where the Spanish cues of movie 42 end up: past the original end?
    first_es = sub["ids"]["vs.es.42.0"]
    new = list(sub["strings"])
    for o in subs:
        new[sub["ids"][o["id"]]] = rm.encode_text(o["text"], frozenset("ğĞşŞıİ"))
    lo = sub["offsets"][0]
    es_at = lo + sum(2 + len(s) for s in new[:first_es])
    total = lo + sum(2 + len(s) for s in new)
    info = {"original": len((GAME / rm.SUB_FILE).read_bytes()), "grown": total, "es42_offset": es_at,
            "es42_past_original_end": es_at >= sub["end"], "cues": len(subs)}
    (home / "make.json").write_text(json.dumps(info, indent=1))
    print("M36 make", json.dumps(info), flush=True)
    return info


def mods(margs, *extra):
    return m35.mods(margs, *extra)


def run(case: str, run_name: str, plan, spanish=False) -> int:
    saved = os.environ.get("R3HD_HIDDEN_EXTRA")
    try:
        if spanish:
            os.environ["R3HD_HIDDEN_EXTRA"] = SPANISH
        else:
            os.environ.pop("R3HD_HIDDEN_EXTRA", None)
        return m35.one_run(run_name, m35.OTTO, m35.ENTRY, plan, load=True)
    finally:
        if saved is None:
            os.environ.pop("R3HD_HIDDEN_EXTRA", None)
        else:
            os.environ["R3HD_HIDDEN_EXTRA"] = saved


def suite(tag: str, base: Path) -> int:
    home = WORK / tag
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    info = make(tag, base)
    if not info["es42_past_original_end"]:
        raise SystemExit("the Spanish cues of movie 42 would not lie past the original end: no test of the tail")
    margs = ["--mods-root", str(home / "mods"), "--cache", str(home / "cache")]
    mods(margs, "import", str(base))
    mods(margs, "import", str(home / "mod_grow"))
    ids = [m["id"] for m in mods(margs, "list")["mods"]]
    same_id, grow_id = ids[0], ids[1]
    (home / "ids.json").write_text(json.dumps({"same": same_id, "grow": grow_id, **info}))
    runs = {c: f"m36_{tag}_{c}" for c in CASES}
    if mods(margs, "plan", "--out", str(home / "plan_off")).get("plan"):
        raise SystemExit("disabled mods still produced a plan")
    run("off", runs["off"], None)
    mods(margs, "enable", same_id)
    same_plan = Path(mods(margs, "plan", "--out", str(home / "plan_same"))["plan"])
    if "\ngrow " in same_plan.read_text(encoding="utf-8"):
        raise SystemExit("the same-size mod produced a grow record")
    run("same", runs["same"], same_plan)
    mods(margs, "disable", same_id)
    mods(margs, "enable", grow_id)
    grow_plan = Path(mods(margs, "plan", "--out", str(home / "plan_grow_çğ"))["plan"])
    run("grow", runs["grow"], grow_plan)
    run("es_off", runs["es_off"], None, spanish=True)
    run("es_grow", runs["es_grow"], grow_plan, spanish=True)
    # bad: the grown tail's replacement hash altered (the range that reaches past the end): refused as a whole.
    lines = grow_plan.read_text(encoding="utf-8").splitlines()
    files = [ln for ln in lines if ln.startswith("file ")]
    vs = next(i for i, ln in enumerate(files) if ln.lower().endswith("vs.sub"))
    bad = []
    for ln in lines:
        f = ln.split(" ")
        if f[0] == "range" and int(f[1]) == vs:
            f[5] = f"{int(f[5], 16) ^ 1:016x}"
        bad.append(" ".join(f))
    (grow_plan.parent / "bad_plan.txt").write_text("\n".join(bad) + "\n", encoding="utf-8")
    run("bad", runs["bad"], grow_plan.parent / "bad_plan.txt")
    mods(margs, "disable", grow_id)
    if mods(margs, "plan", "--out", str(home / "plan_back")).get("plan"):
        raise SystemExit("disabled mods still produced a plan")
    run("back", runs["back"], None)
    return judge(tag)


def judge(tag: str) -> int:
    ids = json.loads((WORK / tag / "ids.json").read_text())
    runs = {c: f"m36_{tag}_{c}" for c in CASES}
    results = []

    def check(ok, label):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)
    logs = {c: "\n".join(p.read_text(errors="replace") for p in sorted((m12.RUNS / r).glob("runtime*.log")))
            for c, r in runs.items()}
    for c in ("off", "es_off", "back"):
        check("M33 mods=off" in logs[c] and "M33 mods state=" not in logs[c] and "M36 grow" not in logs[c],
              f"{c}: no plan, nothing loaded, nothing grown")
    check(re.search(r"M33 mods state=active", logs["same"]) and "M36 grow" not in logs["same"]
          and f"M33 mods served mod={ids['same']} file=VS.sub" in logs["same"],
          "same: the same-size mod is served without growing the file")
    grown, orig = ids["grown"], ids["original"]
    for c in ("grow", "es_grow"):
        reads = [tuple(int(x) for x in m[:4]) + (m[4],) for m in re.findall(
            r"M36 grow read file=VS\.sub offset=(\d+) length=(\d+) host=(\d+) served=(\d+) kind=(\w+)", logs[c])]
        size_line = f"M36 grow size file=VS.sub host_size={orig} guest_size={grown}"
        check(f"M36 grow file=VS.sub host_size={orig} guest_size={grown}" in logs[c] and size_line in logs[c],
              f"{c}: the plan grows VS.sub from {orig} to {grown} bytes and the guest is told {grown}")
        # The reads the guest made: contiguous from 0, each within its buffer, ending exactly at the grown size.
        pos, ok, tail = 0, bool(reads), 0
        for off, length, host, served, kind in reads:
            ok &= off == pos and served <= length and kind != "short"
            if kind == "tail":
                tail += served - host
            if kind == "end":
                ok &= served == 0 and off == grown
                break
            pos += served
        check(ok and pos == grown and tail == grown - orig,
              f"{c}: the guest read VS.sub sequentially to its grown end, {tail} bytes past the original end served "
              f"({len(reads)} reads: {[(r[0], r[1], r[3], r[4]) for r in reads][:8]})")
        check(f"M33 mods served mod={ids['grow']} file=VS.sub" in logs[c], f"{c}: VS.sub served by {ids['grow']}")
    check(re.search(r"M33 mods state=refused reason=blob_hash", logs["bad"]) and "M33 mods served" not in logs["bad"]
          and "M36 grow" not in logs["bad"], "bad: the tampered grow plan is refused as a whole; nothing grown or served")
    check(all("menu10.bik" in logs[c] for c in CASES), "every run played VIDEOS\\menu10.bik")
    fr = {c: m35.frames(r) for c, r in runs.items()}
    if not all(len(v) == 6 for v in fr.values()):
        check(False, f"six frames per run ({ {c: len(v) for c, v in fr.items()} })")
    else:
        for k in m35.CUE_FRAMES:
            d = {c: m35.region(fr["off"][k], fr[c][k], m35.BANNER) for c in ("same", "grow", "bad", "back")}
            d["es"] = m35.region(fr["es_off"][k], fr["es_grow"][k], m35.BANNER)
            d["es_en"] = m35.region(fr["off"][k], fr["es_off"][k], m35.BANNER)
            scene = {c: m35.region(fr["off"][k], fr[c][k], m35.SCENE) for c in ("grow", "es_grow")}
            ink = {c: m35.banner_ink(fr[c][k]) for c in CASES}
            print(f"  frame {k}: banner {d}; scene {scene}; ink {ink}", flush=True)
            en_runs = [c for c in CASES if not c.startswith("es_")]
            check(all(m35.has_subtitle(ink[c]) for c in en_runs),
                  f"frame {k}: a subtitle banner with text in every English-language run")
            ref = max(d["back"], d["bad"])   # English against English: frame drift between runs
            check(d["grow"] >= max(4.0, 2 * ref) and d["same"] >= max(4.0, 2 * ref),
                  f"frame {k}: the grown and the same-size Turkish differ from the English ({d['grow']}, {d['same']} "
                  f"against {ref})")
            # The Spanish cues have their own times: a frame may fall between two of them. Then both Spanish runs
            # show no banner (the timing kept); otherwise the grown file's cue differs from the Spanish one.
            es_on = (m35.has_subtitle(ink["es_off"]), m35.has_subtitle(ink["es_grow"]))
            check(es_on == (False, False) or (es_on == (True, True) and d["es"] >= 4.0 and d["es_en"] >= 4.0),
                  f"frame {k}: Spanish: banners {es_on}; the grown file's Turkish cue (past the original end) "
                  f"against the Spanish one {d['es']}, Spanish against English {d['es_en']}")
            check(d["bad"] <= 4.0 and d["back"] <= 4.0,
                  f"frame {k}: refused and disabled-again show the English subtitle ({d['bad']}, {d['back']})")
            check(ink["grow"][0] > ink["same"][0] or ink["grow"][1] > ink["same"][1],
                  f"frame {k}: the grown Turkish (two longer lines) takes more banner than the same-size one")
        g = {c: m35.banner_ink(fr[c][m35.GAP_FRAME]) for c in CASES}
        check(not any(m35.has_subtitle(v) for v in g.values()),
              f"frame {m35.GAP_FRAME}: no subtitle between cues in any run (timing kept)")
    for c, r in runs.items():
        for j in ("m21_regression.py", "m23_haptics_regression.py"):
            rr = subprocess.run([sys.executable, str(TOOLS / j), "--run", r], cwd=ROOT, capture_output=True, text=True)
            check(rr.returncode == 0, f"{c}: {j} ({(rr.stdout.strip().splitlines() or [''])[-1]})")
    n = results.count(False)
    print(f"M36_SUB_GAME {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("make", "suite", "judge"))
    ap.add_argument("tag")
    ap.add_argument("--base", type=Path)
    a = ap.parse_args()
    if not m12.NAME_RE.fullmatch(a.tag):
        ap.error("invalid TAG")
    if a.mode != "judge" and not (a.base and (a.base / "mod.json").is_file()):
        ap.error("--base MOD (a mod folder with mod.json: the M35 same-size test mod)")
    if a.mode == "make":
        make(a.tag, a.base)
        return 0
    if a.mode == "suite":
        return suite(a.tag, a.base)
    return judge(a.tag)


if __name__ == "__main__":
    sys.exit(main())

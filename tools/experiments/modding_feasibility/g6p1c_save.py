#!/usr/bin/env python3
"""E-486 (D-253) G6-P1c: genuine saves with G6-P1's compiled lum (version-2 transaction intro_10.lvl + .ptr +
transit.lvl) and their loads with the transaction active, removed and re-enabled. Development-only; private,
hidden, disposable profiles; nothing here is committed except this script.

  g6p1c_save.py check              offline O1-O5 (no game process); writes private/work/e486/check.json
  g6p1c_save.py run TAG CASE       one hidden run, CASE in A B C D E F (development build; G5-P3's runner
                                   g5p3_reentry.run_case with default-preserving hooks EXTRA_MODS / TICK)
  g6p1c_save.py judge TAG          S1-S8 from the recorded runs
Outputs: private/work/e486/ (vault = immutable masters, issue = per-run copies of a master, TAG/ = run records).

SAVE FACTS USED (repository records; Phase A of the report)
  The title writes one 510-byte file `rayman3:\\<SLOT>` (XamContentCreateEx caller 822FCF04 flags 0x12, two
  NtWriteFile, XamContentClose; RE_NOTES M20) at name confirmation and at a level change, never during a level or on
  load (load: flags 0x13, no write; M12). The host stages the new file and renames it over the slot at the close
  (D-049; `M20 save stage` / `M20 save commit` log lines). Layout (E-341/E-342): `AAAA`, u32 502, header 0xE0 (cages
  and scores of 10 worlds, +0x50 four words that differ in every save, +0x60 end of game, +0x64 highest world,
  +0x7C..+0x8C revisit, +0x90 level to resume, +0xA4 after-revisit level, +0xB8 ten award words), options 0x24,
  elements `save max life` (1 word), `save current life` (1 word), `global save` (45 words), zero byte. No actor
  count, actor index, per-instance state, resource identity, version or checksum field exists (M19, M20, E-341).
  Genuine saves: `intro_10_fresh` life 12 -> `intro_15_start` (flight pilot, 6 lums) 30 -> SUPPORTED: +3 per lum.
  In a --test-level run the title selects no storage device and writes no save (E-484 h1 exit: no content call);
  the Load route from the title does (E-59 m9_full_progress2: save rewritten, then intro_15).

ROUTE (G5-P3's title steps up to the Load of the slot, unchanged; guest-scoped input; no frames)
  save cases A, B: entry `intro_10_fresh` copy -> title -> Load -> intro_10 -> automatic flight; the ordinary mod
    e478.lums-6 (generator variable 5 = 6, as E-485 k1) makes the junction end the flight -> the title's level-change
    save -> intro_15 -> 30 s -> the runner's end (210 s). A: e478.lums-6 only. B: g6p1.lum + e478.lums-6 (tx
    ccb07d2f770147cb). Right after the runner ended, the slot and its header are copied into the vault
    (vault/TAG_A, vault/TAG_B; m12 entry format, read-only files, SHA-256 in entry.json).
  load cases (each a NEW writable copy of a vault master, issue/TAG<case>/..., verified against entry.json first):
    C master B, g6p1.lum + e478.lums-6 (identical transaction);  D master B, e478.lums-6 only (structural removed);
    E master B, g6p1.lum + e478.lums-6 again, run after D (re-enabled);  F master A, g6p1.lum + e478.lums-6 (the
    control save under the structural mod). Title -> Load -> intro_15 -> 40 s -> the runner's end (120 s).
  Order A, B, (vault), C, D, E, F. A run's own read hook (TICK) records every change of the slot / header file
  (size, mtime, SHA-256; 0.25 s), the profile's file tree (2 s), and outside intro_10 every 5 s the engine lists
  (dynamic / inactive world walks, SO-record list, personal count; g6p1b_lifecycle.read_lists).

PROSPECTIVE CRITERIA (committed before the first save-generating run)
  S1 genuine save (A and B): exactly one `M6 content api=XamContentCreateEx caller=822FCF04 ... arg6=00000012` and one
     `M20 save stage result=ok` + `M20 save commit result=ok`, between the intro_10 open and the intro_15 open; the slot
     then parses (AAAA, 502, 510 bytes to the zero byte, three elements) and names intro_15. B in addition: the copy
     was collected before that save: in the intro_10 entry variable 5 rises 6 -> 7 once with the generator within
     3.0 units of the copy's anchor within 2 s, before the slot's change time (same clock); the plan carries
     `level-tx 2 intro_10 g6p1.lum ccb07d2f770147cb` and the log `G6P1 level-tx version=2 members=lvl,ptr,transit`.
  S2 integrity: every slot state the hook observed after the first change is a complete parseable 510-byte save
     (no partial state seen); the slot changed exactly once in the run (no rewrite before or during the clean exit:
     the post-exit read equals the first post-commit read); vault master = that file; master files read-only and
     equal to entry.json before every issue and after the last run.
  S3 same-mod load (C): plan active {g6p1.lum, e478.lums-6} with the same level-tx line as B; no `state=refused`; load
     bursts begin menumap, intro_15 and intro_10 is never opened; no `G5P3 tx pass` (no member read); engine lists in
     intro_15 consistent (walk length = count, previous links, record walk = header count) and equal in counts to D;
     fault codes = D's and within m12.ROUTINE_FAULTS; no fatal / trap / invalid-target line.
  S4 persisted behaviour (pre-registered from the facts above): (a) A vs B masters differ, outside header
     +0x50..+0x5F, only in `save current life`, and life(B) - life(A) = 3 x (variable-5 increments in B's intro_10
     entry - those in A's), expected 3 (one lum); (b) the extra actor is not re-created by any load: C, D, E and F
     resume at intro_15 (the save's level) and never open intro_10. FAIL: any other field differs or the life
     difference is not 3 x the increment difference. UNKNOWN: A or B has no save (S1 failed).
  S5 structural removed (D): plan active {e478.lums-6} with no level-tx; no `G5P1 level-tx active`, `G6P1` or
     `G5P3 tx` line; the master-B copy loads as in S3 (intro_15 first, no intro_10, lists consistent, faults
     routine). A refusal before intro_15 with no fault would also be safe (recorded as such); a fault is FAIL.
  S6 no unintended save change (C, D, E, F): no CreateEx with flags 0x12 in the log; the copy's slot and header equal
     the master at the end; no file in the profile at the end other than the slot and its header unless the same path
     also exists at the end of A and B; every vault master unchanged after every run.
  S7 re-enable (E after D): equal to C in active mods, level-tx line, refusals, bursts, intro_15 list counts, fault
     codes and S6 facts.
  S8 safety (every run): runner exit 0; game_foreground_events = game_foreground_samples = 0; haptics policy line;
     M21 / M22 / M23 0; D-250 ownership check (no r3hd.exe naming the run left); no engine error line; fault codes
     within m12.ROUTINE_FAULTS and equal between A and B and among C-F; p4b.protected() (save entries, play
     profiles, intro_10 files) unchanged around every run; `check` passed before the first run.
  Invalid (new tag, record kept): a route needle not observed, or the intro_10 / intro_15 area not seen.
  Stop: a guest fault, engine error or desktop-safety violation in any run.
  Revision 1 (after run s1A, before any other run; A's record kept): m12.load_bursts lists movies as well as levels
  (A: ubi, menumap, intro_10, intro_15), so "load bursts begin menumap, intro_15" in S3 / S4 / S5 is read on the
  level bursts only (bursts whose name was opened as a .lvl); nothing else changes.
  Judge correction (after the first judgement of s1, no new run; judgement_s1_original.json kept): S3 / S7 / S8 say
  fault codes; the first judge compared per-code counts and failed S3 / S7 / S8 only on E0473458 x 1 versus x 2
  (A 1, B 2, C 1, D 2, E 2, F 2: independent of the configuration). The judge now compares the code sets as written.
  S1-S8 PASS = G6-P1c VERIFIED — STRUCTURAL SAVE COMPATIBILITY CHARACTERIZED. S1-S2 with S3 / S5 not decided =
  PARTIAL — SAVE CREATED, LOAD UNCERTAIN. S1 not reached = BLOCKED — NO GENUINE SAVE ROUTE.
"""
import json
import hashlib
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
import r3hd_mods as rm  # noqa: E402
import block8_probe as bp  # noqa: E402
import m12_save_entry as m12  # noqa: E402
import g5p1_pilot as p1  # noqa: E402
import g5p2b_lifecycle as p2b  # noqa: E402
import g5p3_reentry as r3  # noqa: E402
import g5p4b_recovery as p4b  # noqa: E402
import g6p1_pilot as g6  # noqa: E402
import g6p1b_lifecycle as g6b  # noqa: E402

PREFIX = "e486"
WORK = ROOT / "private" / "work" / PREFIX
VAULT, ISSUE = WORK / "vault", WORK / "issue"
SAVES0 = m12.SAVES
TX_LINE = f"level-tx 2 intro_10 {g6.MOD} {g6b.TX_G6}"
LUM = (g6.MOD, lambda: [g6.lum("on")])
LUMS6 = ("e478.lums-6", lambda: [p2b.lums6()])
CASES = {"A": ("save", None, [LUMS6]), "B": ("save", None, [LUM, LUMS6]), "C": ("load", "B", [LUM, LUMS6]),
         "D": ("load", "B", [LUMS6]), "E": ("load", "B", [LUM, LUMS6]), "F": ("load", "A", [LUM, LUMS6])}
SECONDS = {"save": 210, "load": 120}
N10 = "log intro_10\\intro_10.lvl result=00000000 60"
MASK = range(0x50, 0x60)
LIFE_PER_LUM = 3


def sha(b):
    return hashlib.sha256(b).hexdigest()


# --- save file -----------------------------------------------------------------------------------------------------

def parse(b):
    """The repository's layout; raises on anything else."""
    if b[:4] != b"AAAA" or struct.unpack(">I", b[4:8])[0] != len(b) - 8:
        raise ValueError("magic / length")
    h, opt, i, el = b[8:8 + 0xE0], b[8 + 0xE0:8 + 0x104], 8 + 0x104, []
    while True:
        n = b[i]
        i += 1
        if n == 0:
            break
        name = b[i:i + n - 1].decode("ascii")
        i += n
        c = b[i + 1]
        el.append((name, list(struct.unpack(f">{c}I", b[i + 2:i + 2 + 4 * c]))))
        i += 2 + 4 * c
    if i != len(b) or len(b) != 510 or [e[0] for e in el] != ["save max life", "save current life", "global save"]:
        raise ValueError("elements / size")
    return {"h": h, "opt": opt, "el": dict(el), "level": h[0x90:0xA4].split(b"\0")[0].decode("ascii")}


def compare(a, b):
    """Field-level differences of two parsed saves, header +0x50..+0x5F excluded."""
    out = {"header": [f"{o:#x}" for o in range(0xE0) if o not in MASK and a["h"][o] != b["h"][o]],
           "options": [o for o in range(0x24) if a["opt"][o] != b["opt"][o]], "elements": {}}
    for k in a["el"]:
        d = [i for i, (x, y) in enumerate(zip(a["el"][k], b["el"][k])) if x != y]
        if d:
            out["elements"][k] = {str(i): [a["el"][k][i], b["el"][k][i]] for i in d}
    return out


def slot_files(profile):
    return [p for p in sorted(profile.glob("*/5841123F/00000001/*/*")) + sorted(profile.glob("*/5841123F/Headers/00000001/*"))
            if p.is_file()]


# --- vault and issue copies ----------------------------------------------------------------------------------------

def make_master(profile, name, provenance, vault=None):
    vault = vault or VAULT
    saves = m12.find_saves(profile)
    if len(saves) != 1:
        raise SystemExit(f"expected one slot in {profile}, found {len(saves)}")
    target = vault / name
    if target.exists():
        raise SystemExit(f"master exists: {target}")
    for f in slot_files(profile):
        d = target / "profile" / f.relative_to(profile)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, d)
    files = m12.profile_files(target / "profile")
    valid, level = m12.read_save_meta(saves[0])
    entry = {"name": name, "slot": saves[0].name, "level": level, "level_key": (level or "").lower(), "files": files,
             "source": provenance, "executable_sha256": m12.exe_sha()}
    (target / "entry.json").write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    for f in [target / "entry.json"] + [target / "profile" / x["path"] for x in files]:
        os.chmod(f, stat.S_IREAD)
    return entry


def verify_master(name, vault=None):
    vault = vault or VAULT
    e = json.loads((vault / name / "entry.json").read_text(encoding="utf-8"))
    fs = [vault / name / "profile" / x["path"] for x in e["files"]] + [vault / name / "entry.json"]
    ro = all(not (os.stat(f).st_mode & stat.S_IWRITE) for f in fs)
    return m12.profile_files(vault / name / "profile") == e["files"] and ro, e


def issue(name, dest, vault=None):
    ok, _ = verify_master(name, vault)
    if not ok:
        raise SystemExit(f"master {name} changed or writable")
    if dest.exists():
        raise SystemExit(f"exists: {dest}")
    shutil.copytree(vault or VAULT, dest, ignore=lambda d, n: [x for x in n if Path(d) == (vault or VAULT) and x != name])
    for f in (dest / name).rglob("*"):
        if f.is_file():
            os.chmod(f, stat.S_IREAD | stat.S_IWRITE)
    return dest


def vault_state():
    return {p.name: verify_master(p.name)[0] for p in sorted(VAULT.iterdir())} if VAULT.is_dir() else {}


# --- run hook --------------------------------------------------------------------------------------------------------

def brief_lists(L):
    if "error" in L:
        return {"error": L["error"]}
    return {"dw": [L["dw"]["count"], len(L["dw"]["walk"]), L["dw"]["prev_ok"]],
            "inactive": [L["inactive"]["count"], len(L["inactive"]["walk"]), L["inactive"]["prev_ok"]],
            "rec": [L["rec"]["count"], L["rec"]["n"]], "personal": L["personal"]["count"], "bak": len(L["bak_targets"])}


class Tick:
    def __init__(self):
        self.events, self.trees, self.level, self.last = [], [], [], {}
        self.next_stat = self.next_tree = self.next_lv = 0.0

    def __call__(self, p, profile, t):
        if p is None or t >= self.next_stat:
            self.next_stat = t + 0.25
            for f in slot_files(profile):
                rel = f.relative_to(profile).as_posix()
                try:
                    st = f.stat()
                    key = [st.st_size, st.st_mtime_ns]
                    if self.last.get(rel) == key and p is not None:
                        continue
                    b = f.read_bytes()
                except OSError as x:
                    self.events.append({"t": t, "file": rel, "error": repr(x)})
                    continue
                if self.last.get(rel) != key or p is None:
                    try:
                        lv, ok = parse(b)["level"], True
                    except Exception:
                        lv, ok = None, "/Headers/" in rel
                    self.events.append({"t": t, "file": rel, "size": len(b), "sha256": sha(b), "level": lv,
                                        "complete": ok, "final": p is None})
                    self.last[rel] = key
        if p is None or t >= self.next_tree:
            self.next_tree = t + 2.0
            tree = sorted(x.relative_to(profile).as_posix() for x in profile.rglob("*") if x.is_file())
            if not self.trees or self.trees[-1]["tree"] != tree or p is None:
                self.trees.append({"t": t, "tree": tree, "final": p is None})
        if p is not None and t >= self.next_lv:
            self.next_lv = t + 5.0
            a1 = (bp.areas(p) or {}).get(1)
            if a1 and a1["end"] - a1["base"] not in r3.AREA10:
                self.level.append({"t": t, "length": a1["end"] - a1["base"], "lists": brief_lists(g6b.read_lists(p))})


def steps(kind):
    pre = r3.STEPS[:r3.STEPS.index(N10)]
    if kind == "save":
        return pre + [N10, "log intro_15\\intro_15.lvl result=00000000 150", "wait 30"]
    return pre + ["log intro_15\\intro_15.lvl result=00000000 60", "wait 40"]


def bind():
    g6b.setup()
    r3.PREFIX, r3.WORK, p1.WORK = PREFIX, WORK, WORK
    p4b.PREFIX, p4b.WORK = PREFIX, WORK


# --- offline ---------------------------------------------------------------------------------------------------------

def check():
    WORK.mkdir(parents=True, exist_ok=True)
    bind()
    res, det = {}, {}
    # O1 parser and comparator on every registered genuine save
    genuine = [e for e in (json.loads(p.read_text(encoding="utf-8")) for p in sorted(SAVES0.glob("*/entry.json")))
               if not e["name"].startswith("pcconv")]
    parsed = {}
    for e in genuine:
        f = next(SAVES0 / e["name"] / "profile" / x["path"] for x in e["files"]
                 if x["path"].endswith("/" + e["slot"]) and "/Headers/" not in x["path"])
        parsed[e["name"]] = parse(f.read_bytes())
    d = compare(parsed["intro_10_fresh"], parsed["intro_15_start"])
    det["O1"] = {"genuine": len(parsed), "fresh_vs_start": d,
                 "life": [parsed[k]["el"]["save current life"][0] for k in ("intro_10_fresh", "intro_15_start")]}
    res["O1_parser"] = (len(parsed) >= 15 and list(d["elements"]) == ["save current life", "global save"]
                        and det["O1"]["life"] == [12, 30] and not d["options"]
                        and all(o in ("0x90", "0x97", "0xbb") for o in d["header"]))
    # O2 vault / issue on a scratch copy of intro_10_fresh
    sc = WORK / "check_vault"
    if sc.exists():
        for f in sc.rglob("*"):
            if f.is_file():
                os.chmod(f, stat.S_IREAD | stat.S_IWRITE)
        shutil.rmtree(sc)
    e = make_master(SAVES0 / "intro_10_fresh" / "profile", "t", "check", vault=sc / "vault")
    ok1, _ = verify_master("t", sc / "vault")
    dst = issue("t", sc / "issue", vault=sc / "vault")
    f = next(x for x in (dst / "t" / "profile").rglob("*") if x.is_file() and x.parent.name == x.name)
    f.write_bytes(f.read_bytes()[:100])          # damage the issued copy only
    ok2, _ = verify_master("t", sc / "vault")
    v = next(x for x in (sc / "vault" / "t" / "profile").rglob("*") if x.is_file() and x.parent.name == x.name)
    os.chmod(v, stat.S_IREAD | stat.S_IWRITE)
    v.write_bytes(v.read_bytes()[:-1] + b"\x01")  # a changed master must refuse to issue
    try:
        issue("t", sc / "issue2", vault=sc / "vault")
        refused = False
    except SystemExit:
        refused = True
    res["O2_vault"] = ok1 and ok2 and refused and e["files"] == m12.load_entry("intro_10_fresh")["files"]
    det["O2"] = {"verify_fresh": ok1, "verify_after_issue_damaged": ok2, "changed_master_refused": refused}
    # O3 plans: A / D (ordinary only) and B / C / E / F (identical transaction)
    plans = {}
    for k, mods in (("ordinary", [LUMS6]), ("structural", [LUM, LUMS6])):
        paths = p1.fresh(f"check_{k}")
        with p1.dev_env():
            for mid, ov in mods:
                p1.install(paths, mid, ov())
            r = rm.resolve_all(paths, write_plan=paths["cache"])
        t = (paths["cache"] / rm.PLAN_NAME).read_text(encoding="utf-8")
        plans[k] = {"active": sorted(r["active"]), "tx": re.findall(r"^level-tx .*$", t, re.M),
                    "files": re.findall(r"^file \d+ .*\\(\S+)$", t, re.M)}
    det["O3"] = plans
    res["O3_plans"] = (plans["ordinary"] == {"active": ["e478.lums-6"], "tx": [], "files": ["intro_10.lvl"]}
                       and plans["structural"]["active"] == sorted([g6.MOD, "e478.lums-6"])
                       and plans["structural"]["tx"] == [TX_LINE]
                       and plans["structural"]["files"] == ["intro_10.lvl", "intro_10.ptr", "transit.lvl"])
    # O4 host-side refusals that decide what a load sees (wrong identity, stale image, missing mod, marker)
    g6.WORK = WORK / "g6p1"
    g6.WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = g6.WORK
    rc_neg = g6.negtest()
    neg = json.loads((g6.WORK / "negtest" / "summary.json").read_text())
    bind()
    rc_pre = p4b.preflight()
    pre = json.loads((WORK / "preflight.json").read_text())
    res["O4_refusals"] = (rc_neg == 0 and neg["dev"]["exit"] == 0 and neg["prod"]["exit"] == 0
                          and rc_pre in (0, None) and pre["pass"] and len(pre["res"]) == 14)
    det["O4"] = {"g6p1_negtest": rc_neg, "negtest": {k: neg.get(k) for k in ("dev", "prod")},
                 "g5p4b_preflight_with_lum": pre["res"]}
    # O5 route and gate facts: the save steps extend G5-P3's title steps; no save gate exists in the overlay
    hdr = (TOOLS / "m33_mod_overlay.h").read_text(encoding="utf-8", errors="replace")
    det["O5"] = {"save_steps": steps("save")[-3:], "load_steps": steps("load")[-2:],
                 "overlay_mentions_content_api": bool(re.search(r"XamContent|rayman3:", hdr))}
    res["O5_route"] = N10 in r3.STEPS and not det["O5"]["overlay_mentions_content_api"]
    out = {"pass": all(res.values()), "results": res, "details": det}
    (WORK / "check.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1))
    return 0 if out["pass"] else 1


# --- runs ------------------------------------------------------------------------------------------------------------

def run(tag, case):
    if subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True,
                      text=True).stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    if not json.loads((WORK / "check.json").read_text())["pass"]:
        raise SystemExit("check did not pass")
    bind()
    kind, src, mods = CASES[case]
    if src is None:
        m12.SAVES, r3.ENTRY = SAVES0, "intro_10_fresh"
    else:
        name = f"{tag}_{src}"
        m12.SAVES, r3.ENTRY = issue(name, ISSUE / f"{tag}{case}"), name
    r3.PLAN_MOD = LUM if LUM in mods else None
    r3.EXTRA_MODS = [m for m in mods if m is not LUM]
    r3.STEPS, r3.SECONDS = steps(kind), SECONDS[kind]
    tick = r3.TICK = Tick()
    before, vb = p4b.protected(), vault_state()
    row = r3.run_case(f"{tag}{case}", "ra")
    work = WORK / f"{tag}{case}" / "ra"
    rec = {"protected": {"before": before, "after": p4b.protected()}, "vault": {"before": vb, "after": vault_state()},
           "events": tick.events, "trees": tick.trees, "level": tick.level}
    if kind == "save":
        prof = m12.PROFILES / f"{PREFIX}_{tag}{case}_ra"
        try:
            rec["master"] = make_master(prof, f"{tag}_{case}", f"G6-P1c case {case}: run {PREFIX}_{tag}{case}_ra, "
                                        "title level-change save after intro_10")
        except SystemExit as x:
            rec["master_error"] = str(x)
        rec["vault"]["after_master"] = vault_state()
    (work / "g6p1c.json").write_text(json.dumps(rec, indent=1, default=str) + "\n")
    print(json.dumps({k: row.get(k) for k in ("runner_exit", "process_left", "bursts", "error")}, default=str))
    return 0


# --- judgement -------------------------------------------------------------------------------------------------------

def facts(tag, case):
    run_ = f"{PREFIX}_{tag}{case}_ra"
    work = WORK / f"{tag}{case}" / "ra"
    row = json.loads((work / "row.json").read_text())
    rec = json.loads((work / "g6p1c.json").read_text())
    entries = json.loads((work / "entries.json").read_text())
    log = "\n".join(q.read_text(errors="replace") for q in sorted((r3.RUNS / run_).glob("runtime*.log")))
    pc = work / "plan_copy.txt"
    plan = pc.read_text(encoding="utf-8") if pc.is_file() else ""
    rj = r3.RUNS / run_ / "run.json"
    rjd = json.loads(rj.read_text(encoding="utf-8-sig")) if rj.is_file() else {}
    judges = {}
    for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        q = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run_], cwd=ROOT, capture_output=True, text=True)
        judges[tool] = q.returncode
        (work / f"{tool}.log").write_text(q.stdout + q.stderr)
    lines = log.splitlines()
    i10 = next((i for i, ln in enumerate(lines) if "intro_10\\intro_10.lvl result=00000000" in ln), None)
    i15 = next((i for i, ln in enumerate(lines) if "intro_15\\intro_15.lvl result=00000000" in ln), None)
    creates = [(i, m.group(1)) for i, ln in enumerate(lines)
               for m in [re.search(r"M6 content api=XamContentCreateEx caller=822FCF04 .*arg6=(\w+) result=00000000", ln)] if m]
    return {
        "run": run_, "row": row, "rec": rec, "entries": entries, "plan_mods": sorted(re.findall(r"^mod (\S+)", plan, re.M)),
        "plan_tx": re.findall(r"^level-tx .*$", plan, re.M), "i10": i10, "i15": i15, "creates": creates,
        "m20": [(i, m.group(1), m.group(2)) for i, ln in enumerate(lines)
                for m in [re.search(r"M20 save (stage|commit) result=(\w+)", ln)] if m],
        "refused": re.findall(r"state=refused reason=([A-Za-z_]+)", log),
        "g5p1": re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log),
        "g6p1": re.findall(r"G6P1 level-tx version=(\d+) members=(\S+)", log),
        "g5p3_tx": len(re.findall(r"G5P3 tx", log)), "g5p3_pass": len(re.findall(r"G5P3 tx pass", log)),
        "served": sorted(set(re.findall(r"M33 mods served mod=(\S+) file=(\S+)", log))),
        "error": re.findall(r"(?:engine error|unhandled exception|guest fault|crash)[^\n]{0,120}", log, re.I)[:5]
        + [ln[:160] for ln in lines if any(n in ln for n in m12.FATAL_NEEDLES) or m12.TRAP.search(ln)
           or m12.INVALID_TARGET.search(ln)][:5],
        "haptics": "M23 haptics policy=suppressed physical_pad_drivers=none" in log,
        # judge correction (after the first judgement, same runs): the protocol compares fault CODES; the first
        # judge compared per-code counts (E0473458 occurs once or twice per run in every configuration)
        "faults": sorted(g6b.fault_counts(run_)), "fault_counts": g6b.fault_counts(run_), "judges": judges,
        "fg": (rjd.get("game_foreground_events"), rjd.get("game_foreground_samples")),
        "bursts": [b for b in row.get("bursts", [])   # revision 1: level bursts only
                   if re.search(rf"\\{re.escape(b)}\.lvl result=00000000", log, re.I)],
        "all_bursts": row.get("bursts", []),
    }


def lists_ok(level):
    ls = [x["lists"] for x in level if "error" not in x["lists"]]
    good = bool(ls) and all(x["dw"][0] == x["dw"][1] and x["dw"][2] and x["inactive"][2] and x["rec"][0] == x["rec"][1]
                            for x in ls)
    return good, (ls[-1] if ls else None)


def judge(tag):
    bind()
    F = {c: facts(tag, c) for c in "ABCDEF" if (WORK / f"{tag}{c}" / "ra" / "row.json").is_file()}
    S, det = {}, {}
    pos = g6.anchor("on")

    def save_of(c):
        m = F[c]["rec"].get("master")
        if not m:
            return None
        f = next(VAULT / m["name"] / "profile" / x["path"] for x in m["files"] if "/Headers/" not in x["path"])
        return parse(f.read_bytes())

    def incs(c):
        e = F[c]["entries"]
        s = e[0]["samples"] if e else []
        return [(s[i]["t"], s[i - 1]["v5"], s[i]["v5"]) for i in range(1, len(s)) if s[i]["v5"] != s[i - 1]["v5"]]

    def slot_events(c):
        return [x for x in F[c]["rec"]["events"] if "/Headers/" not in x.get("file", "") and "sha256" in x]

    # S1
    s1 = {}
    for c in "AB":
        if c not in F:
            s1[c] = False
            continue
        f = F[c]
        x12 = [i for i, a in f["creates"] if a == "00000012"]
        st = [m for m in f["m20"] if m[1] == "stage"]
        cm = [m for m in f["m20"] if m[1] == "commit"]
        sv = save_of(c)
        ok = (len(x12) == 1 and len(st) == 1 and len(cm) == 1 and st[0][2] == cm[0][2] == "ok"
              and f["i10"] is not None and f["i15"] is not None and f["i10"] < x12[0] < f["i15"]
              and f["i10"] < st[0][0] < f["i15"] and sv is not None and sv["level"] == "intro_15")
        det.setdefault("S1", {})[c] = {"create_0x12": len(x12), "m20": [m[1:] for m in f["m20"]],
                                       "level": sv and sv["level"], "increments": incs(c)}
        if c == "B":
            ch = incs("B")
            e = F["B"]["entries"]
            coll = g6b.collection(e[0]["samples"], e[0]["ab"], pos, e[0]["t"]) if e else {}
            ev = slot_events("B")
            t_save = ev[1]["t"] if len(ev) > 1 else None
            det["S1"]["B"].update(near=coll.get("near"), t_rel=coll.get("t_rel"), t_save=t_save)
            ok = ok and bool(ch) and ch[0][1:] == (6, 7) and coll.get("near") is not None and coll["near"] <= 3.0 \
                and t_save is not None and ch[0][0] < t_save and f["plan_tx"] == [TX_LINE] \
                and f["g6p1"] == [("2", "lvl,ptr,transit")]
        s1[c] = ok
    S["S1_genuine_save"] = all(s1.get(c) for c in "AB")
    # S2
    s2 = {}
    for c in "AB":
        if c not in F or not F[c]["rec"].get("master"):
            s2[c] = False
            continue
        ev = slot_events(c)
        changes = [x for x in ev if not x["final"]]
        final = [x for x in ev if x["final"]]
        msha = next(x["sha256"] for x in F[c]["rec"]["master"]["files"] if "/Headers/" not in x["path"])
        s2[c] = (len(changes) == 2 and all(x["complete"] and x["size"] == 510 for x in changes[1:])
                 and final and final[-1]["sha256"] == changes[-1]["sha256"] == msha
                 and F[c]["rec"]["vault"]["after_master"].get(f"{tag}_{c}") is True)
        det.setdefault("S2", {})[c] = {"slot_states": [(x["t"], x["size"], x["sha256"][:12], x["level"]) for x in ev],
                                       "master_sha": msha[:12]}
    S["S2_integrity"] = all(s2.get(c) for c in "AB") and all(v for v in vault_state().values())
    det["vault_now"] = vault_state()

    # load cases
    def load_ok(c, struct_):
        if c not in F:
            return False, {}
        f = F[c]
        good, last = lists_ok(f["rec"]["level"])
        b = f["bursts"]
        d = {"active": f["plan_mods"], "tx": f["plan_tx"], "refused": f["refused"], "bursts": b, "lists": last,
             "g5p3_pass": f["g5p3_pass"], "g6p1": f["g6p1"], "g5p1": f["g5p1"], "faults": f["faults"]}
        ok = (b[:2] == ["menumap", "intro_15"] and "intro_10" not in b and good and f["g5p3_pass"] == 0
              and set(f["faults"]) <= set(m12.ROUTINE_FAULTS) and not f["error"])
        if struct_:
            ok = ok and f["plan_mods"] == sorted([g6.MOD, "e478.lums-6"]) and f["plan_tx"] == [TX_LINE] \
                and not f["refused"]
        else:
            ok = ok and f["plan_mods"] == ["e478.lums-6"] and not f["plan_tx"] and not f["g5p1"] \
                and not f["g6p1"] and f["g5p3_tx"] == 0
        return ok, d
    okC, det["C"] = load_ok("C", True)
    okD, det["D"] = load_ok("D", False)
    okE, det["E"] = load_ok("E", True)
    okF, det["F"] = load_ok("F", True)
    cnt = lambda d: d.get("lists") and {k: v for k, v in d["lists"].items() if k != "bak"} or None  # noqa: E731
    S["S3_same_mod_load"] = okC and cnt(det["C"]) == cnt(det["D"]) and det["C"].get("faults") == det["D"].get("faults")
    # S4
    sa, sb = (save_of("A") if "A" in F else None), (save_of("B") if "B" in F else None)
    if sa and sb:
        d = compare(sa, sb)
        la, lb = sa["el"]["save current life"][0], sb["el"]["save current life"][0]
        ia, ib = len(incs("A")), len(incs("B"))
        det["S4"] = {"diff": d, "life": [la, lb], "increments": [ia, ib], "life_A_minus_fresh": la - 12}
        s4a = (not d["header"] and not d["options"] and list(d["elements"]) in ([], ["save current life"])
               and lb - la == LIFE_PER_LUM * (ib - ia) and ib - ia == 1)
    else:
        s4a = None
    s4b = all(c in F and F[c]["bursts"][:2] == ["menumap", "intro_15"] and "intro_10" not in F[c]["bursts"]
              for c in "CDEF")
    S["S4_persisted"] = (s4a and s4b) if s4a is not None else None
    det["S4b_resume_intro_15"] = s4b
    S["S5_mod_removed_load"] = okD and cnt(det["D"]) == cnt(det["C"])
    # S6
    s6 = {}
    ab_trees = set()
    for c in "AB":
        if c in F and F[c]["rec"]["trees"]:
            ab_trees |= set(F[c]["rec"]["trees"][-1]["tree"])
    for c in "CDEF":
        if c not in F:
            s6[c] = False
            continue
        f = F[c]
        src = "A" if c == "F" else "B"
        m = json.loads((VAULT / f"{tag}_{src}" / "entry.json").read_text(encoding="utf-8"))
        want = {x["path"]: x["sha256"] for x in m["files"]}
        fin = {x["file"]: x["sha256"] for x in f["rec"]["events"] if x.get("final") and "sha256" in x}
        tree = set(f["rec"]["trees"][-1]["tree"]) if f["rec"]["trees"] else set()
        extra = sorted(tree - set(want) - ab_trees)
        s6[c] = (not [a for _, a in f["creates"] if a == "00000012"] and fin == want and not extra
                 and all(v for v in f["rec"]["vault"]["after"].values()))
        det.setdefault("S6", {})[c] = {"creates": [a for _, a in f["creates"]], "final_equal_master": fin == want,
                                       "extra_files": extra}
    S["S6_no_save_change"] = all(s6.get(c) for c in "CDEF") and all(vault_state().values())
    # S7
    keys = ("active", "tx", "refused", "bursts", "faults")
    S["S7_reenable"] = okE and all(det["E"].get(k) == det["C"].get(k) for k in keys) and cnt(det["E"]) == cnt(det["C"]) \
        and s6.get("E") and det.get("S6", {}).get("E", {}).get("creates") == det.get("S6", {}).get("C", {}).get("creates")
    # S8
    s8 = {}
    for c, f in F.items():
        pr = f["rec"]["protected"]
        s8[c] = (f["row"].get("runner_exit") == 0 and f["fg"] == (0, 0) and f["haptics"]
                 and not any(f["judges"].values()) and f["row"].get("process_left") is False and not f["error"]
                 and set(f["faults"]) <= set(m12.ROUTINE_FAULTS) and pr["before"] == pr["after"])
    same = (F.get("A", {}).get("faults") == F.get("B", {}).get("faults")
            and len({json.dumps(F[c]["faults"], sort_keys=True) for c in "CDEF" if c in F}) == 1)
    S["S8_safety"] = len(F) == 6 and all(s8.values()) and same and \
        json.loads((WORK / "check.json").read_text())["pass"]
    det["S8"] = {c: {"exit": f["row"].get("runner_exit"), "fg": f["fg"], "left": f["row"].get("process_left"),
                     "faults": f["faults"], "fault_counts": f["fault_counts"], "judges": f["judges"], "error": f["error"]} for c, f in F.items()}
    det["load_ok"] = {"C": okC, "D": okD, "E": okE, "F": okF}
    out = {"tag": tag, "criteria": S, "details": det}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(S, indent=1))
    return 0


def main():
    a = sys.argv[1:]
    if a == ["check"]:
        return check()
    if len(a) == 3 and a[0] == "run" and a[2] in CASES:
        return run(a[1], a[2])
    if len(a) == 2 and a[0] == "judge":
        return judge(a[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

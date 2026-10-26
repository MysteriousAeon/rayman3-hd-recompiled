#!/usr/bin/env python3
"""Decode the actors and scripts of levels from live isolated test-only runs (M14, D-040, D-021).

    python tools/m14_script_scan.py TAG LEVEL [LEVEL ...] | --all [--settle 12]

One hidden run per level (m14_<TAG>_<level>, title option "-level:<level>" through run_milestone6.ps1
-TestLevel). After the level has been open for --settle seconds the existing read-only probes run
(tools/m5_memory_probe.py actor discovery, tools/m5_script_probe.py script decode) and this tool records, per
actor, the model, position, current behaviours and every designer variable of type Text resolved to its
string through the title's own text tables. The run is then cancelled. No guest memory is written and no input
is sent.

Output is game-derived and stays private: private/work/m14/scan_v2/<level>/ (decoded scripts, actors.json).
Since D-113 the script probe writes format 2 (numeric node and designer-variable types, no Raymap names, with the
labels of D-113 step 2 that the title's interpreter establishes); a text handle is a designer variable of type 21
(E-270). The format-1 scans in private/work/m14/scan/ are kept as recorded evidence and are never overwritten;
tools/m14_transition_graph.py and tools/r3hd_lqa.py read either (--scan / --scans).
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m5_live import Actor, Process  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "m14"
GAMEDATA = ROOT / "private" / "extracted" / "5841123F" / "GAMEDATAbin"
# Text handles (RE_NOTES "M14"): the resolver 82133348 reads handles below 0x4E20 from the language table and
# the others from a second table, both reached through the block at 82BCE1A0.
TEXT_BLOCK, ENGINE_BLOCK, TEXT_SPLIT = 0x82BCE1A0, 0x82C06220, 0x4E20
# Designer-variable type number of a text handle in the probe's format 2 (reader 822680D0, tag 0x24; E-270).
TEXT_DSGVAR_TYPE = 21


def level_names() -> list:
    return sorted(p.name.lower() for p in GAMEDATA.iterdir() if p.is_dir() and (p / f"{p.name}.lvl").is_file())


def text_of(process: Process, handle: int):
    if handle == 0xFFFFFFFF:
        return None
    block = process.words(TEXT_BLOCK, 5)
    if not block:
        return None
    if handle < TEXT_SPLIT:
        language = process.read(ENGINE_BLOCK + 0x1B38, 1)
        table = process.words(block[3] + language[0] * 8, 1) if language and block[3] else None
        entry = process.words(table[0] + handle * 4, 1) if table and table[0] else None
    else:
        table = process.words(block[4], 1) if block[4] else None
        entry = process.words(table[0] + (handle - TEXT_SPLIT) * 4, 1) if table and table[0] else None
    if not entry or not entry[0]:
        return None
    raw = process.read(entry[0], 0x80)
    if not raw:
        return None
    raw = raw.split(b"\0", 1)[0]
    return raw.decode("latin-1") if raw and all(c >= 32 for c in raw) else None


def misc_texts(process: Process) -> dict:
    """The second text table (handles from 0x4E20): level names and other non-localised strings."""
    out = {}
    for index in range(0x400):
        text = text_of(process, TEXT_SPLIT + index)
        if text is not None:
            out[f"{TEXT_SPLIT + index:08X}"] = text
    return out


def scan(tag: str, level: str, settle: int) -> dict:
    run_name = f"m14_{tag}_{level}"
    run_dir = RUNS / run_name
    out = WORK / "scan_v2" / level
    if run_dir.exists():
        raise SystemExit(f"run directory exists: {run_name}")
    out.mkdir(parents=True, exist_ok=True)
    seconds = settle + 150
    steps = WORK / f"steps_{run_name}.txt"
    steps.write_text(f"wait {seconds - 8}\n", encoding="ascii")
    row: dict = {"run": run_name, "level": level, "entry": "isolated test-only (-level:)"}
    with (WORK / f"{run_name}.driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(ROOT / "tools" / "m9_license_run.py"), run_name, str(steps),
                                 "--license-mask", "1", "--seconds", str(seconds), "--play", "--test-level", level],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            needle = re.compile(rf"[\\/]{re.escape(level)}\.lvl result=00000000", re.IGNORECASE)
            opened, base, end = None, None, time.monotonic() + 60
            while time.monotonic() < end and game.poll() is None and opened is None:
                time.sleep(1)
                log_path = run_dir / "runtime.log"
                if log_path.is_file():
                    text = log_path.read_text(errors="replace")
                    if needle.search(text):
                        opened = time.monotonic()
                    m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                    base = m.group(1) if m else base
            if opened is None or base is None:
                row["error"] = "level did not open"
                return row
            time.sleep(settle)
            pid = json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            discovery = out / "discovery.json"
            probe = subprocess.run([sys.executable, str(ROOT / "tools" / "m5_memory_probe.py"), str(pid), base,
                                    str(discovery), "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
            if probe.returncode != 0:
                row["error"] = "actor discovery failed: " + probe.stderr.strip()[-200:]
                return row
            scripts = out / "scripts"
            decode = subprocess.run([sys.executable, str(ROOT / "tools" / "m5_script_probe.py"), str(pid), base,
                                     str(discovery), str(scripts)], cwd=ROOT, capture_output=True, text=True, timeout=600)
            if decode.returncode != 0:
                row["error"] = "script decode failed: " + decode.stderr.strip()[-200:]
                return row
            process = Process(pid, int(base, 16))
            texts = {}
            for path in scripts.glob("*.txt"):
                for m in re.finditer(rf"^dsgvar (\d+) t{TEXT_DSGVAR_TYPE} ([0-9a-f]{{8}})", path.read_text(errors="replace"), re.M):
                    handle = int(m.group(2), 16)
                    texts.setdefault(path.stem.rsplit("_", 1)[-1], {})[m.group(1)] = {
                        "handle": f"{handle:08X}", "text": text_of(process, handle)}
            (out / "misc_texts.json").write_text(json.dumps(misc_texts(process), indent=1) + "\n", encoding="utf-8")
            actors = []
            for record in json.loads(discovery.read_text(encoding="utf-8"))["actors"]:
                try:
                    actor = Actor(process, int(record["so"], 16))
                    if not actor.alive():
                        continue
                    actors.append({"so": record["so"], "perso": f"{actor.perso:08X}", "model": actor.model,
                                   "position": [round(v, 2) for v in actor.position()],
                                   "comport": actor.comport() if actor.mind else None,
                                   "reflex": actor.comport(reflex=True) if actor.mind else None,
                                   "bits": f"{actor.custom_bits():08X}",
                                   "texts": texts.get(f"{actor.perso:08X}", {})})
                except (TypeError, ValueError, IndexError, OSError, AttributeError):
                    continue
            (out / "actors.json").write_text(json.dumps({"level": level, "run": run_name, "actors": actors}, indent=1) + "\n",
                                             encoding="utf-8")
            row.update(actors=len(actors), with_text=sum(1 for a in actors if a["texts"]),
                       scripts=len(list(scripts.glob("*.txt"))))
        finally:
            if game.poll() is None:
                (run_dir / "cancel.request").write_text("script scan finished\n", encoding="ascii")
            try:
                game.wait(timeout=seconds + 120)
            except subprocess.TimeoutExpired:
                row["error"] = "runner did not stop"
            meta_path = run_dir / "run.json"
            if meta_path.is_file():
                meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
                row.update(exit_code=meta.get("exit_code"), game_foreground_events=meta.get("game_foreground_events"),
                           executable_sha256=meta.get("executable_sha256"))
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("levels", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--settle", type=int, default=12)
    a = ap.parse_args()
    known = level_names()
    levels = known if a.all else [name.lower() for name in a.levels]
    if not re.fullmatch(r"[A-Za-z0-9]+", a.tag) or not 5 <= a.settle <= 300 or not levels:
        ap.error("invalid TAG, --settle (5..300) or no level")
    unknown = [name for name in levels if name not in known]
    if unknown:
        ap.error(f"not a level directory: {unknown}")
    result = WORK / f"scan_{a.tag}.json"
    WORK.mkdir(parents=True, exist_ok=True)
    rows = json.loads(result.read_text()) if result.is_file() else []
    for level in levels:
        row = scan(a.tag, level, a.settle)
        rows.append(row)
        result.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
        print(f"M14_SCAN {level} actors={row.get('actors')} with_text={row.get('with_text')} scripts={row.get('scripts')} "
              f"exit={row.get('exit_code')} focus={row.get('game_foreground_events')} error={row.get('error')}", flush=True)
        time.sleep(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

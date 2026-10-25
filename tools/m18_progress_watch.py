#!/usr/bin/env python3
"""Read-only watcher for the title's progression and revisit state in a live hidden run (M18, D-021).

    python tools/m18_progress_watch.py RUN_DIR OUTPUT.jsonl [--seconds 300] [--interval 0.05] [--wait 120]

Waits for RUN_DIR/process.json and the guest base in the runtime log, then polls the globals listed in WORDS
and NAMES (RE_NOTES "M16" / "M18") and writes one JSON line whenever any of them changes: the revisit flag and
its one-shot word, the world numbers, the menu page / cursor, the engine's current and next level name, the
save's resume and backup names. Nothing is interpreted here; `m18_progress_watch.py summary OUTPUT.jsonl`
prints the changes as a compact table.

Opens the process with QUERY_INFORMATION | VM_READ only. OUTPUT must be under private/.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m5_live import Process  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORDS = {
    "revisit": 0x82876108,       # revisit flag
    "oneshot": 0x82875F28,       # exempts the first request after entering revisit mode
    "exit_armed": 0x828760F8,    # "return to the interrupted game" chosen on the world page
    "rev_world": 0x8287611C,     # revisited world number + 1
    "int_world": 0x82876120,     # world index of the interrupted game
    "world": 0x82836F60,         # current world
    "max_world": 0x82836F64,     # highest world reached
    "score_world": 0x82836F68,
    "end_of_game": 0x82876130,
    "staff_mode": 0x828760F4,
    "page": 0x828760EC,          # menu page
    "cursor": 0x82876100,
    "pages": 0x8287606C,
    "menu_mode": 0x82875F48,
    "menu_state": 0x828760FC,
    "loaded": 0x82875F34,
}
NAMES = {
    "current": 0x82C06220 + 0x01,
    "next": 0x82C06220 + 0x1F,
    "resume": 0x82BF7480,
    "backup": 0x82BF7440,
}
ENGINE_MODE = 0x82C06220


def attach(run: Path, wait: float) -> Process:
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        info = run / "process.json"
        if info.is_file():
            try:
                pid = int(json.loads(info.read_text(encoding="utf-8-sig"))["pid"])
            except (ValueError, KeyError):
                pid = None
            for path in sorted(run.glob("runtime*.log")) if pid else []:
                m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", path.read_text(errors="replace"))
                if m:
                    return Process(pid, int(m.group(1), 16))
        time.sleep(0.5)
    raise SystemExit("run did not start (process.json / guest base not found)")


def sample(process: Process):
    out = {}
    for key, address in WORDS.items():
        value = process.words(address, 1)
        if value is None:
            return None
        out[key] = value[0]
    mode = process.read(ENGINE_MODE, 1)
    out["engine_mode"] = mode[0] if mode else None
    for key, address in NAMES.items():
        raw = process.read(address, 0x1E)
        raw = raw.split(b"\0", 1)[0] if raw else b""
        out[key] = raw.decode("latin-1") if all(32 <= c < 127 for c in raw) else raw.hex()
    return out


def watch(a) -> int:
    output = a.output.resolve()
    if (ROOT / "private").resolve() not in output.parents:
        raise SystemExit("OUTPUT must be under private/")
    process = attach(a.run, a.wait)
    previous, start = None, time.monotonic()
    with output.open("w", encoding="utf-8") as stream:
        while time.monotonic() - start < a.seconds and process.running():
            now = sample(process)
            if now is not None and now != previous:
                changed = now if previous is None else {k: v for k, v in now.items() if previous.get(k) != v}
                stream.write(json.dumps({"t": round(time.monotonic() - start, 2), "wall": time.time(), **changed}) + "\n")
                stream.flush()
                previous = now
            time.sleep(a.interval)
    return 0


def summary(a) -> int:
    for line in a.output.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        t = record.pop("t")
        record.pop("wall", None)
        print(f"{t:8.2f}  " + "  ".join(f"{k}={v}" for k, v in record.items()))
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        ap = argparse.ArgumentParser()
        ap.add_argument("command")
        ap.add_argument("output", type=Path)
        return summary(ap.parse_args())
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--seconds", type=float, default=300.0)
    ap.add_argument("--interval", type=float, default=0.05)
    ap.add_argument("--wait", type=float, default=120.0)
    return watch(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())

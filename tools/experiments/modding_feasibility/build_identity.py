"""G6-P64 (D-313): which binaries the editor / modding checks' identity rows compare with.

The live rows of G6-P24 / G6-P29 / G6-P33 / G6-P35 / G6-P38 ("the build folder holds the production identity") guard
against a stale, incremental or development-gated build. They read `config/release/production_identity.json`:

  --identity development   (default) the record's `development` entry: the binaries of the last authoritative full
                           replay, named with its source commit and build log. The build folder must hold exactly
                           those bytes, the log must end `M8_BUILD_OK` (or wrapped `BUILD_SCRIPT_ENDED rc=0`) with
                           every binary written inside the log's lifetime, and the source commit must be an ancestor
                           of HEAD.
  --identity release       the record's `current` entry (the latest published Windows release binaries).
  --identity D-299 / ...   a `history` entry by decision.

A historical identity checks the retained artifact folder its record names, never the live build in its place; with
no retained folder it is UNAVAILABLE, which fails. `--bin DIR` checks another folder against the chosen identity
(only the hashes; the build-log tie applies to the recorded build folder). No mode substitutes another binary.

    build_identity.py show [--identity X] [--bin DIR]    prints the verdict; exit 0 only when it holds
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RECORD = ROOT / "config" / "release" / "production_identity.json"
NAMES = ("r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll")


def parse(argv):
    """Split `--identity X` / `--bin DIR` off argv; returns (rest, identity, bin or None). Raises ValueError."""
    rest, ident, bdir, i = [], "development", None, 0
    while i < len(argv):
        if argv[i] in ("--identity", "--bin"):
            if i + 1 >= len(argv):
                raise ValueError(f"{argv[i]} needs a value")
            if argv[i] == "--identity":
                ident = argv[i + 1]
            else:
                bdir = Path(argv[i + 1])
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    return rest, ident, bdir


def forward(ident, bdir=None):
    """Arguments that pass the same choice to a nested check."""
    return ["--identity", ident] + (["--bin", str(bdir)] if bdir else [])


def entry(ident, record=None):
    rec = record if record is not None else json.loads(RECORD.read_text(encoding="utf-8"))
    if ident == "development":
        return rec["development"]
    if ident == "release":
        return rec["current"]
    for h in rec.get("history", []):
        if h.get("decision") == ident:
            return h
    raise ValueError(f"unknown identity {ident!r} (development, release or a history decision)")


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _birth(st):
    return getattr(st, "st_birthtime", st.st_ctime if os.name == "nt" else None)


def _log_ok(tail):
    """Accept a direct build_milestone8.bat log ending with M8_BUILD_OK, or a wrapped log ending BUILD_SCRIPT_ENDED rc=0."""
    lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
    if not lines or "M8_BUILD_OK" not in lines:
        return False
    if any(ln.startswith("BUILD_SCRIPT_ENDED") for ln in lines):
        return lines[-1].startswith("BUILD_SCRIPT_ENDED rc=0")
    return lines[-1] == "M8_BUILD_OK"


def verify(ident, names=NAMES, bdir=None, record=None, root=ROOT):
    """(ok, label, detail): the named binaries in the identity's folder equal the identity's hashes."""
    try:
        e = entry(ident, record)
    except (ValueError, KeyError) as x:
        return False, f"{ident}: no such identity", {"error": str(x)}
    want = {n: e["binaries"].get(n) for n in names}
    label = f"{ident} ({e.get('decision', '?')}; r3hd.exe {str(want.get('r3hd.exe', ''))[:8]})"
    det = {"identity": ident, "decision": e.get("decision")}
    if any(v is None for v in want.values()):
        return False, label, dict(det, error=f"record lacks {[n for n, v in want.items() if v is None]}")
    if bdir is None:
        key = "build_dir" if ident == "development" else "artifact"
        if key not in e:
            return False, label + " UNAVAILABLE", dict(det, error=f"the record names no retained {key}")
        bdir = root / e[key]
    bdir = Path(bdir)
    det["folder"] = str(bdir)
    missing = [n for n in names if not (bdir / n).is_file()]
    if missing:
        return False, label + " UNAVAILABLE", dict(det, error=f"missing {missing}")
    got = {n: _sha(bdir / n) for n in names}
    det["sha256"] = {n: h[:16] for n, h in got.items()}
    ok = got == want
    if not ok:
        det["mismatch"] = [n for n in names if got[n] != want[n]]
    if ident == "development" and ok and bdir.resolve() == (root / e["build_dir"]).resolve():
        log = root / e["build_log"]
        if not log.is_file():
            return False, label, dict(det, error=f"build log {e['build_log']} unavailable")
        tail = log.read_bytes()[-4096:].decode("utf-8", "replace")
        ls = os.stat(log)
        start, end = _birth(ls), ls.st_mtime
        inside = start is not None and all(start <= os.stat(bdir / n).st_mtime <= end for n in names)
        anc = subprocess.run(["git", "merge-base", "--is-ancestor", e["source_commit"], "HEAD"], cwd=root,
                             capture_output=True).returncode == 0
        det.update(log_ok=_log_ok(tail), written_in_replay=inside,
                   source_commit=e["source_commit"][:12], commit_in_history=anc)
        ok = det["log_ok"] and inside and anc
    return ok, label, det


def main(argv):
    try:
        rest, ident, bdir = parse(argv)
    except ValueError as x:
        print(x)
        return 2
    if rest != ["show"]:
        print(__doc__)
        return 2
    ok, label, det = verify(ident, bdir=bdir)
    print(json.dumps(det, indent=1, default=str))
    print(f"IDENTITY {'OK' if ok else 'FAIL'} {label}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

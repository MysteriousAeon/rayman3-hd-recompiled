"""LX-1 (E-374) regression: the Exit Game hang mechanism and the PosixCondition<Thread> teardown fix.

Builds tools/linux/thread_teardown_test.cpp with each available compiler (natively on Linux, through WSL on
Windows) and requires:
  * original: blocks in delete (pthread_cond_destroy with a parked waiter) -> killed at the timeout;
  * fixed:    exits 0 with ran=0 (the abandoned thread never runs its routine);
  * resumed:  exits 0 with ran=1 (a resumed thread is unaffected).
Also checks that tools/r3hd_thread_teardown_patch.py carries the same protocol as the test (the predicate, the
abandon flag and the join), so the two cannot drift apart silently.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = HERE / "thread_teardown_test.cpp"
PATCH = ROOT / "tools/r3hd_thread_teardown_patch.py"
EXPECT = {"original": ("timeout", None), "fixed": (0, "ran=0"), "resumed": (0, "ran=1")}


def wsl_path(p: Path) -> str:
    s = str(p.resolve()).replace("\\", "/")
    return f"/mnt/{s[0].lower()}{s[2:]}"


def runner():
    if os.name == "nt":
        if not shutil.which("wsl"):
            return None
        return lambda cmd: ["wsl", "-e", "bash", "-lc", cmd], wsl_path
    return lambda cmd: ["bash", "-lc", cmd], lambda p: str(p)


def static_check() -> list:
    text = PATCH.read_text(encoding="utf-8")
    need = ["thread->handle_.suspend_count_ == 0 || thread->handle_.start_abandoned_",
            "thread->handle_.start_waiting_ = true;", "start_abandoned_ = true;",
            "pthread_join(thread_, nullptr);", "REL = 'src/core/threading_posix.cpp'"]
    return [n for n in need if n not in text]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cxx", action="append", help="compiler(s); default: g++ and clang++ when present")
    a = ap.parse_args()
    failures = [f"patch lacks: {m}" for m in static_check()]
    r = runner()
    if r is None:
        print("THREAD_TEARDOWN_TEST SKIP (no WSL)" if not failures else f"THREAD_TEARDOWN_TEST FAIL {failures}")
        return 1 if failures else 0
    sh, conv = r
    compilers = a.cxx or ["g++", "clang++"]
    built = 0
    with tempfile.TemporaryDirectory(dir=ROOT / "private" if (ROOT / "private").is_dir() else None) as tmp:
        for cxx in compilers:
            if subprocess.run(sh(f"command -v {cxx}"), capture_output=True).returncode:
                print(f"{cxx}: not installed, skipped")
                continue
            exe = Path(tmp) / f"tt_{cxx.replace('+', 'x')}"
            c = subprocess.run(sh(f"{cxx} -std=c++20 -O2 -pthread -o '{conv(exe)}' '{conv(SRC)}'"),
                               capture_output=True, text=True)
            if c.returncode:
                failures.append(f"{cxx} compile: {c.stderr[-300:]}")
                continue
            built += 1
            for mode, (code, token) in EXPECT.items():
                p = subprocess.run(sh(f"timeout -s KILL 5 '{conv(exe)}' {mode}; echo EXIT=$?"),
                                   capture_output=True, text=True)
                out = p.stdout
                got = out.rsplit("EXIT=", 1)[-1].strip()
                if code == "timeout":
                    ok = got in ("124", "137") and "destroying" in out and "PASS" not in out
                else:
                    ok = got == "0" and f"PASS {token}" in out
                print(f"{cxx} {mode}: exit={got} {'ok' if ok else 'FAIL'}")
                if not ok:
                    failures.append(f"{cxx} {mode}: {out.strip()[-200:]}")
    status = "PASS" if not failures and built else "FAIL"
    print(f"THREAD_TEARDOWN_TEST {status} compilers={built} failures={failures}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

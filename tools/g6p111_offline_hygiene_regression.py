#!/usr/bin/env python3
"""G6-P111 offline regression for docs_check.py, Windows cp1254 subprocess encoding,
and DualSense Settings private-desktop diagnostics.

No builds, game launches, visible windows, network access, or physical hardware.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
G6P35 = TOOLS / "experiments" / "modding_feasibility" / "g6p35_playable_check.py"
LAUNCHER_CPP = TOOLS / "launcher" / "r3hd_launcher.cpp"
sys.path.insert(0, str(TOOLS))
import docs_check  # noqa: E402
import release_dualsense_settings_test as ds_test  # noqa: E402

checks = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" ({detail})" if detail and not ok else ""))


def main() -> int:
    # --- 1. docs_check.py positive and negative controls ------------------------------------------------------
    r = subprocess.run([sys.executable, "-X", "utf8", str(TOOLS / "docs_check.py")],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    data = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    check("docs_check default passes (rc 0, 0 errors, 0 broken refs, 0 missing IDs)",
          r.returncode == 0 and data.get("errors") == [] and data.get("broken_references") == []
          and data.get("missing_ids") == [], r.stdout[-300:] + r.stderr[-300:])
    check("docs_check reports historical_baseline_byte_drift transparently",
          sorted(data.get("historical_baseline_byte_drift", [])) == sorted(docs_check.BOOKS),
          str(data.get("historical_baseline_byte_drift")))

    r_strict = subprocess.run([sys.executable, "-X", "utf8", str(TOOLS / "docs_check.py"), "--strict-baseline-bytes"],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    strict_data = json.loads(r_strict.stdout) if r_strict.stdout.strip().startswith("{") else {}
    check("docs_check --strict-baseline-bytes still exits 1 on living-book byte drift",
          r_strict.returncode == 1 and len(strict_data.get("errors", [])) == 4,
          str(strict_data.get("errors")))

    # Negative control: broken relative link is detected by docs_check.links
    _, broken = docs_check.links(["README.md"], {"README.md": "[missing](nonexistent_g6p111_target.md)\n"})
    check("docs_check negative control: broken relative link detected",
          len(broken) == 1 and "nonexistent_g6p111_target.md" in broken[0], str(broken))

    # Negative control: dropped baseline heading is detected
    ref = json.loads(docs_check.BASE.read_text(encoding="utf-8"))["head"]
    old_headings = [t for _, t, _ in docs_check.headings(docs_check.git_text(ref, "DECISIONS.md"))]
    cur_headings = {t for _, t, _ in docs_check.headings((ROOT / "DECISIONS.md").read_text(encoding="utf-8"))}
    check("docs_check baseline headings all present in DECISIONS.md",
          len(old_headings) >= 168 and all(t in cur_headings for t in old_headings))
    dropped = [t for t in old_headings if t not in (cur_headings - {old_headings[0]})]
    check("docs_check negative control: dropping a baseline heading is detected",
          dropped == [old_headings[0]], str(dropped))

    # --- 2. Windows cp1254 / -I UTF-8 subprocess contract -----------------------------------------------------
    # Positive control: python -I -X utf8 emitting U+0130 ('İ') decodes cleanly as UTF-8
    ok_child = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", "print('PASS text: (\\\\xdd for \\u0130) is refused')"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    check("isolated child (-I -X utf8) preserves U+0130 ('İ') cleanly under UTF-8 capture",
          ok_child.returncode == 0 and "\u0130" in ok_child.stdout, repr(ok_child.stdout))

    # Negative control: invalid UTF-8 byte 0xDD from child is NOT silently ignored
    raw_bad = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", "import sys; sys.stdout.buffer.write(b'bad:\\xdd\\n')"],
        cwd=ROOT, capture_output=True, timeout=60,
    )
    decoded_bad_failed = False
    try:
        raw_bad.stdout.decode("utf-8")
    except UnicodeDecodeError:
        decoded_bad_failed = True
    check("negative control: raw 0xDD byte is rejected by strict UTF-8 decode (never silently ignored)",
          raw_bad.returncode == 0 and decoded_bad_failed)

    # Source contract in g6p35_playable_check.py
    g6p35_src = G6P35.read_text(encoding="utf-8")
    check("g6p35_playable_check.py passes -X utf8 and encoding='utf-8' for r3hd_mods.py selftest",
          '[sys.executable, "-I", "-X", "utf8", str(TOOLS / "r3hd_mods.py"), "selftest"]' in g6p35_src
          and 'encoding="utf-8"' in g6p35_src)
    check("g6p35_playable_check.py never uses errors='ignore' or errors='replace'",
          'errors="ignore"' not in g6p35_src and "errors='ignore'" not in g6p35_src
          and 'errors="replace"' not in g6p35_src and "errors='replace'" not in g6p35_src)

    # --- 3. DualSense Settings private-desktop contract -------------------------------------------------------
    cpp = LAUNCHER_CPP.read_text(encoding="utf-8")
    check("r3hd_launcher.cpp exits 3 when CreateDesktopW/SetThreadDesktop fails (no visible fallback)",
          "if (!desk || !SetThreadDesktop(desk)) return 3;" in cpp)
    detail3 = ds_test.ui_detail(3, "")
    check("release_dualsense_settings_test ui_detail explains exit code 3 clearly",
          "private desktop unavailable" in detail3[0] and "exit 3" in detail3[0], str(detail3))

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    print(f"G6P111_OFFLINE_HYGIENE_REGRESSION {'PASS' if passed == total else 'FAIL'} {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

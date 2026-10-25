#!/usr/bin/env python3
"""M18 tooling regression (no game run): shape and isolation of the revisit compatibility correction (D-047).

    python tools/m18_regression.py        -> M18_REGRESSION PASS checks=N failures=0

The decision table itself is tested by m18_revisit_test.exe (in the build). The hidden checks that need the game:
    python tools/m18_revisit_check.py TAG        (reports/milestone18/REPORT.md)
"""
import re
import struct
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "private" / "work" / "rex"
checks = failures = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


# --- hook configuration --------------------------------------------------------------------------------------------
compat = tomllib.loads(read(ROOT / "config/rexglue/r3hd_compat.toml"))["midasm_hook"]
by_name = {hook["name"]: hook for hook in compat}
check(sorted(by_name) == ["M18RevisitRedirect", "M18TestWorldEnd"], "the compatibility file holds exactly the two M18 hooks")
redirect, trigger = by_name.get("M18RevisitRedirect", {}), by_name.get("M18TestWorldEnd", {})
check(redirect.get("address") == 0x82102E3C and redirect.get("registers") == ["r1"]
      and redirect.get("jump_address_on_true") == 0x82102E58, "redirect hook: site 82102E3C, continues at 82102E58 when true")
check(set(redirect) == {"address", "name", "registers", "jump_address_on_true"}, "redirect hook has no other flag")
check(trigger.get("address") == 0x82102CC4 and trigger.get("registers") == ["r3"]
      and set(trigger) == {"address", "name", "registers"}, "test trigger: 82102CC4, r3 only, no return / jump flag")
wait = tomllib.loads(read(ROOT / "config/rexglue/r3hd_wait.toml"))["midasm_hook"]
check(len(wait) == 1 and set(wait[0]) == {"address", "name", "registers"},
      "r3hd_wait.toml still holds one scheduling hook without return / jump flags")
manifest = W / "r3hd_manifest.toml"
if manifest.is_file():
    check(read(manifest).count("r3hd_compat.toml") == 1, "the codegen manifest includes r3hd_compat.toml once")

# --- the title image at the two sites (private; skipped when absent) -------------------------------------------------
image = ROOT / "private" / "work" / "default_image.bin"
if image.is_file():
    data = image.read_bytes()
    word = lambda va: struct.unpack_from(">I", data, va - 0x82000000)[0]  # noqa: E731
    check(word(0x82102E3C) >> 26 == 15, "82102E3C starts the endgame substitution block with an address load")
    check(word(0x82102E38) >> 26 == 16 and word(0x82102E58) >> 26 == 18, "the block is entered by fall-through and left at 82102E58")
    check(word(0x82102CC4) >> 26 == 31 and (word(0x82102CC4) >> 21) & 31 == 3,
          "82102CC4 is a register move out of r3, the first use of the requested name")

# --- generated code (skipped before the first codegen) -------------------------------------------------------------
generated = W / "generated" / "default"
sources = sorted(generated.glob("r3hd_recomp.*.cpp")) if generated.is_dir() else []
if sources:
    calls = {"M18RevisitRedirect(": [], "M18TestWorldEnd(": []}
    for path in sources:
        text = read(path)
        for needle in calls:
            for m in re.finditer(r"^\t(?:if \()?" + re.escape(needle), text, re.M):
                calls[needle].append((path, text, m.start()))
    check(len(calls["M18RevisitRedirect("]) == 1 and len(calls["M18TestWorldEnd("]) == 1, "each hook is called from exactly one place")
    if len(calls["M18RevisitRedirect("]) == 1:
        _, text, at = calls["M18RevisitRedirect("][0]
        before, after = text[max(0, at - 200):at], text[at:at + 200]
        tail = [line.strip() for line in before.rstrip().splitlines()[-2:]]
        check(tail[0] == "loc_82102E3C:" and tail[1].startswith("//"), "the redirect hook is the first thing at loc_82102E3C")
        check(re.match(r"\tif \(M18RevisitRedirect\(ctx\.r1\)\) \{\s+goto loc_82102E58;\s+\}", after) is not None,
              "the redirect hook continues at loc_82102E58 when it returns true")
    if len(calls["M18TestWorldEnd("]) == 1:
        _, text, at = calls["M18TestWorldEnd("][0]
        check(text[at:at + 120].startswith("\tM18TestWorldEnd(ctx.r3);") and "ctx.r30.u64 = ctx.r3.u64;" in text[at:at + 120],
              "the test trigger runs before the name in r3 is first used")

# --- host code -----------------------------------------------------------------------------------------------------
header = read(ROOT / "tools/m18_revisit.h")
host = read(ROOT / "tools/m2_host/m2_trace.cpp")
installed = W / "src" / "m18_revisit.h"
if installed.is_file():
    check(read(installed) == header, "installed m18_revisit.h equals tools/m18_revisit.h")
check(all(word not in header for word in ("windows.h", "PPC", "REX", "getenv")), "the decision header is pure (no guest or host access)")
section = host[host.index("// M18 (D-047)"):]
redirect_body = section[section.index("bool M18RevisitRedirect("):section.index("void M18TestWorldEnd(")]
trigger_body = section[section.index("void M18TestWorldEnd("):]
check(host[:host.index("// M18 (D-047)")].count("M18") == 0, "nothing before the M18 section refers to it")
check("M18Store(" not in trigger_body and "memcpy(M18Base()" not in trigger_body, "the test trigger writes no guest memory")
check('std::getenv("R3HD_TEST_WORLD_END")' in trigger_body and '!std::strcmp(v, "1")' in trigger_body,
      "the test trigger is off unless R3HD_TEST_WORLD_END=1")
check('m18::OriginalSelected(std::getenv("R3HD_REVISIT"))' in section and "if (!M18Original() && name_ok)" in redirect_body,
      "R3HD_REVISIT=original keeps the title's behaviour")
check(redirect_body.index("if (action == m18::Action::kOriginal) return false;") < redirect_body.index("M18Store("),
      "no guest write before the decision; none when the title's behaviour is kept")
check(redirect_body.index("if (action == m18::Action::kPass) return true;") < redirect_body.index("M18Store("),
      "a passing request writes no guest memory")
stores = re.findall(r"M18Store\((\w+)", redirect_body)
check(stores == ["kM18Flag", "kM18ScoreWorld", "kM18RevWorld", "0x8287610C", "0x82876110", "0x82876128"],
      "the return transition writes the words of the title's own branch 82108518, in its order")
check(redirect_body.index("M18Store(kM18Flag, 0);") < redirect_body.index("sub_82104BE0(*ctx, M18Base());")
      < redirect_body.index("M18Store(kM18ScoreWorld"), "flag cleared, then the title's score routine, then the restores")
check("const PPCContext saved = *ctx;" in redirect_body and "*ctx = saved;" in redirect_body, "guest registers are restored after the call")
check(all(word not in section for word in ("0x82836F64", "0x82875F4C", "M18Store(kM18EndOfGame")),
      "highest world, end-of-game flag and the world mask are never written")
check("achievement" not in section.lower(), "achievements are not touched")

# --- launcher and tools --------------------------------------------------------------------------------------------
play = read(ROOT / "tools/play.ps1")
check("[ValidateSet('fixed', 'original')][string]$Revisit = 'fixed'" in play and "$env:R3HD_REVISIT = $Revisit" in play
      and "$env:R3HD_REVISIT = $savedRevisit" in play, "launcher: -Revisit fixed is the default, original is explicit, the variable is restored")
check("'R3HD_TEST_WORLD_END'" in play and play.count("R3HD_TEST_WORLD_END") == 1,
      "launcher clears the test trigger variable and never sets it")
allowed = {"m18_regression.py", "m18_revisit_check.py", "play.ps1"}
users = {p.name for p in (ROOT / "tools").iterdir() if p.is_file() and p.suffix in (".py", ".ps1", ".bat", ".sh")
         and "R3HD_TEST_WORLD_END" in p.read_text(encoding="utf-8", errors="replace")}
# M19's runner names the variable once, in the list of switches it removes from the environment of its runs
# (found failing in the M20 build: M19 ran no build after adding that list).
m19 = read(ROOT / "tools/m19_campaign_check.py")
strips_only = m19.count("R3HD_TEST_WORLD_END") == 1 and 'SWITCHES = ("R3HD_TEST_WORLD_END", "R3HD_REVISIT")' in m19 \
    and "if k not in SWITCHES" in m19
check(strips_only, "the M19 runner only removes the test trigger from its environment")
users -= {"m19_campaign_check.py"} if strips_only else set()
check(users <= allowed, f"only the hidden M18 check uses the test trigger (found {sorted(users - allowed)})")
watch = read(ROOT / "tools/m18_progress_watch.py")
check("WriteProcessMemory" not in watch and "from m5_live import Process" in watch, "the progression watcher is read-only")
for steps in sorted((ROOT / "config" / "m18").glob("*.txt")):
    verbs = {line.split()[0] for line in read(steps).splitlines() if line.strip() and not line.lstrip().startswith("#")}
    check(verbs <= {"log", "wait", "press", "axis"}, f"{steps.name}: only log / wait / press / axis steps")
build = read(ROOT / "tools/build_milestone8.bat")
check(build.index("m11_prepare.py") < build.index("m16_prepare.py") < build.index("m18_prepare.py") < build.index("codegen --ignore-stamp"),
      "m18_prepare.py runs after the M11 / M16 preparation and before codegen")
check("m18_revisit_test.exe || exit /b 1" in build and "m18_regression.py || exit /b 1" in build, "the build runs both M18 regressions")

print(f"M18_REGRESSION {'FAIL' if failures else 'PASS'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)

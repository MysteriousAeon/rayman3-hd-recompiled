"""G6-P82 / G6-P83 (D-331, D-332): source and policy pins for the state-change-aware XamShowSigninUI notification,
the development default since G6-P83, and its legacy switch back.

Checks, without building or running the game:
  * the policy: by default XN_SYS_SIGNINCHANGED only when the signed-in owner changed during the call, independent of
    the hidden-test gate; R3HD_SIGNIN_NOTIFY exactly "legacy" -> always notify (the inherited stub); any other value
    keeps the default; the retired G6-P82 test flag is gone from the tooling (no second implementation);
  * the patch: the owner is read before the handoff block and after it; only the 0x0A broadcast of XamShowSigninUI is
    conditional; XN_SYS_UI = 0 follows unconditionally, after it, with the same data; the return value is unchanged;
    the trace line is logging only, under the hidden gate; no new guest memory access;
  * every other SIGNINCHANGED source (the G6-P80 rollback in xam_input.cpp) is untouched by the flag;
  * the replayed M6 unit test covers the decision; the build installs the header and runs this regression;
  * the runner sets the switch back only on -SigninNotifyLegacy, clears an inherited value otherwise and restores it;
    m9 passes it only on its option; nothing in the product launcher or release tooling names it;
  * if the SDK tree has been replayed, the patched xam_user.cpp and the installed header are current.
--selftest also proves that each rule rejects a targeted mutation.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
FLAG = "R3HD_SIGNIN_NOTIFY"  # G6-P83 switch back (exactly "legacy")
OLD_FLAG = "R3HD_TEST_SIGNIN_NOTIFY_ON_CHANGE"  # G6-P82 test-only enable flag, retired by G6-P83
# Files allowed to name the switch back (its implementation, tests and records); anything else tracked naming it fails.
ALLOWED = {"tools/g6p82_signin_notify.h", "tools/g6p82_signin_notify_regression.py", "tools/run_milestone6.ps1",
           "tools/g6p82_signin_notify_check.py", "tools/g6p79_profile_handoff_patch.py", "tools/m6_input_test.cpp"}


def load_patch(text=None):
    sys.path.insert(0, str(ROOT / "tools"))
    if text is not None:
        ns = {"__name__": "g6p82_mutant"}
        exec(compile(text, "mutant", "exec"), ns)
        return type("M", (), ns)
    spec = importlib.util.spec_from_file_location("g6p79_patch", ROOT / "tools" / "g6p79_profile_handoff_patch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sources():
    t = {name: (ROOT / "tools" / name).read_text(encoding="utf-8") for name in (
        "g6p82_signin_notify.h", "g6p79_profile_handoff_patch.py", "m6_input_test.cpp", "build_milestone8.bat",
        "run_milestone6.ps1", "m9_license_run.py", "play.ps1")}
    for key, flag in (("_flag_files", FLAG), ("_old_flag_files", OLD_FLAG)):
        try:
            tracked = subprocess.check_output(["git", "-C", str(ROOT), "grep", "-l", "--untracked", flag],
                                              text=True).split()
        except subprocess.CalledProcessError:
            tracked = []
        t[key] = "\n".join(sorted(tracked))
    return t


def signin_block(edits):
    """The after-text of the XamShowSigninUI edit (the one that calls OnSigninRequest)."""
    for before, after in edits:
        if "g6p79::OnSigninRequest(" in after:
            return before, after
    return "", ""


def check(t, module):
    out = []

    def rule(label, ok):
        out.append((label, bool(ok)))

    h = t["g6p82_signin_notify.h"]
    rule("switch back: exactly \"legacy\" in R3HD_SIGNIN_NOTIFY; anything else keeps the default",
         'inline bool ParseLegacy(const char* value) { return value != nullptr && std::strcmp(value, "legacy") == 0; }'
         in h and f'static const bool legacy = ParseLegacy(std::getenv("{FLAG}"));' in h and
         h.count("std::getenv(") == 2)
    rule("default: the state-change-aware policy is active unless the switch back is selected",
         "inline bool Enabled() { return !Legacy(); }" in h)
    rule("default: independent of the hidden-test gate (only the trace line reads R3HD_NONINTRUSIVE)",
         h.count("R3HD_NONINTRUSIVE") == 1 and "ParseEnable" not in h and OLD_FLAG not in h)
    rule("decision: legacy always notifies; the default only on an owner change",
         "return !enabled || owner_before != owner_after;" in h and
         "return Decide(Enabled(), owner_before, owner_after);" in h)
    rule("trace: logging only under the hidden gate",
         'static const bool trace = std::getenv("R3HD_NONINTRUSIVE") != nullptr;' in h)
    rule("note: one legacy log line per process, only when the switch back is selected",
         "static std::atomic<bool> noted{false};\n  return Legacy() && !noted.exchange(true);" in h)
    rule("header: no guest memory, kernel or notification access",
         all(s not in h for s in ("TranslateVirtual", "BroadcastNotification", "store_and_swap", "0x82")))

    before, after = signin_block(module.XAM_USER) if module is not None else ("", "")
    rule("patch: the XamShowSigninUI edit is present", bool(after))
    i_snap = after.find("const unsigned g6p82_owner_before = g6p79::Owner();")
    i_hand = after.find("  if (g6p79::Enabled()) {\n    bool connected")
    i_dec = after.find("const bool g6p82_notify = g6p82::ShouldNotify(g6p82_owner_before, g6p79::Owner());")
    i_if = after.find("  if (g6p82_notify)\n    REX_KERNEL_STATE()->BroadcastNotification(0x0000000A, 1u << g6p79::Owner());")
    rule("patch: owner read before the handoff block; the decision after it; the 0x0A send depends on it",
         0 <= i_snap < i_hand < i_dec < i_if and after.count("BroadcastNotification(0x0000000A,") == 1)
    rule("patch: no unconditional 0x0A send remains in XamShowSigninUI",
         "\n  REX_KERNEL_STATE()->BroadcastNotification(0x0000000A" not in after)
    rule("patch: the trace line is behind Trace() and reports both owners and the decision",
         "  if (g6p82::Trace())\n    REXKRNL_INFO(\"G6P82 signin_ui owner_before={} owner_after={} signinchanged={} "
         "ui_off=1 notify_on_change={}\"," in after)
    i_trace = after.find("  if (g6p82::Trace())")
    i_note = after.find("  else if (g6p82::NoteLegacyOnce())\n    REXKRNL_INFO(\"XamShowSigninUI: legacy sign-in "
                        "notification selected (R3HD_SIGNIN_NOTIFY=legacy)\");")
    rule("patch: outside hidden runs only the one-time legacy note is logged, before the 0x0A send",
         0 <= i_trace < i_note < i_if and after.count("REXKRNL_INFO(") == 3)
    rule("pin: XN_SYS_UI = 0 and the success return follow the 0x0A in the pinned stub (kept outside the edit)",
         "REX_KERNEL_STATE()->BroadcastNotification(0x0000000A, 1);" in before and
         "BroadcastNotification(0x00000009" not in after)
    pin = t.get("xam_user_pin", "")
    if pin:
        tail = pin[pin.find("REX_KERNEL_STATE()->BroadcastNotification(0x0000000A, 1);"):]
        rule("pin: XN_SYS_UI (off) and X_ERROR_SUCCESS follow unconditionally",
             tail.find("  REX_KERNEL_STATE()->BroadcastNotification(0x00000009, 0);\n  return X_ERROR_SUCCESS;") > 0)
    raw = t["g6p79_profile_handoff_patch.py"]
    rule("patch: still one guest read and no guest store (G6-P82 adds none)",
         raw.count("TranslateVirtual") == 1 and "store_and_swap" not in raw)
    other = "\n".join(a for _, a in list(module.XAM_INPUT) + list(module.XAM_UI)) if module is not None else "g6p82"
    rule("patch: the G6-P80 rollback SIGNINCHANGED and every UI path are untouched by the flag",
         "g6p82" not in other and
         "REX_KERNEL_STATE()->BroadcastNotification(0x0000000A, 1u << g6p79::Owner());  // XN_SYS_SIGNINCHANGED" in other)
    rule("patch: xam_user includes the header; the patch installs it",
         any("#include <rex/g6p82_signin_notify.h>" in a for _, a in module.XAM_USER) and
         "    install('g6p82_signin_notify.h')" in raw if module is not None else False)

    test = t["m6_input_test.cpp"]
    rule("tests: the replayed M6 unit test covers the switch-back parse, every owner pair and both process modes",
         '#include "g6p82_signin_notify.h"' in test and "assert(g6p82::Decide(false, b, a));" in test and
         "assert(g6p82::Decide(true, b, a) == (b != a));" in test and 'assert(g6p82::ParseLegacy("legacy"));' in test and
         '!g6p82::ParseLegacy("Legacy")' in test and '!g6p82::ParseLegacy("legacy ")' in test and
         '!g6p82::ParseLegacy("1")' in test and
         "assert(!g6p82::ShouldNotify(0, 0) && g6p82::ShouldNotify(0, 1));" in test and
         "assert(g6p82::ShouldNotify(0, 0) && g6p82::ShouldNotify(0, 1));" in test and
         "assert(!g6p82::Legacy() && g6p82::Enabled() && !g6p82::NoteLegacyOnce() && !g6p82::NoteLegacyOnce());"
         in test)

    bat = t["build_milestone8.bat"]
    line = "python tools\\g6p82_signin_notify_regression.py || exit /b 1"
    rule("build: this regression runs after the handoff regression, before M8_BUILD_OK",
         bat.count(line) == 1 and
         0 < bat.find("python tools\\g6p79_handoff_regression.py || exit /b 1") < bat.find(line) <
         bat.find("echo M8_BUILD_OK"))
    ps = t["run_milestone6.ps1"]
    rule("runner: legacy only on -SigninNotifyLegacy, an inherited value cleared otherwise, restored and recorded",
         f"if ($SigninNotifyLegacy) {{ $env:{FLAG} = 'legacy' }} else {{ [Environment]::SetEnvironmentVariable('{FLAG}', $null) }}"
         in ps and f"'R3HD_TEST_USER_EVENTS', '{FLAG}')" in ps and
         "signin_notify_on_change = -not [bool]$SigninNotifyLegacy" in ps and
         "signin_notify = $(if ($SigninNotifyLegacy) { 'legacy' } else { 'on_change' })" in ps and
         ps.count(f"$env:{FLAG} =") == 1 and "SigninNotifyOnChange" not in ps)
    m9 = t["m9_license_run.py"]
    rule("runner: m9 passes -SigninNotifyLegacy only on --signin-notify-legacy",
         'if args.signin_notify_legacy:\n        command.append("-SigninNotifyLegacy")' in m9 and
         m9.count('"-SigninNotifyLegacy"') == 1 and "signin-notify-on-change" not in m9)
    rule("product: the launcher never names the switch back or the runner switch",
         FLAG not in t["play.ps1"] and "SigninNotifyLegacy" not in t["play.ps1"])
    files = [f for f in t["_flag_files"].split("\n") if f and not f.endswith(".md")]  # records may name it
    rule(f"product: no tracked file outside the implementation and tests names {FLAG} ({sorted(set(files) - ALLOWED)})",
         set(files) <= ALLOWED)
    old = [f for f in t["_old_flag_files"].split("\n") if f and not f.endswith(".md")]
    rule(f"retired: only this regression still names {OLD_FLAG} ({old})",
         set(old) <= {"tools/g6p82_signin_notify_regression.py"})

    replayed = SDK / "src" / "kernel" / "xam" / "xam_user.cpp"
    if module is not None and replayed.exists() and "G6-P82" in replayed.read_text(errors="replace"):
        live = replayed.read_text(errors="replace")
        rule("replayed tree: xam_user.cpp carries the G6-P82 XamShowSigninUI edit once", live.count(after) == 1)
        installed = SDK / "include" / "rex" / "g6p82_signin_notify.h"
        rule("replayed tree: the installed g6p82_signin_notify.h is current",
             installed.exists() and installed.read_bytes() == (ROOT / "tools" / "g6p82_signin_notify.h").read_bytes())
    return out


MUTATIONS = [
    ("g6p82_signin_notify.h", 'std::strcmp(value, "legacy") == 0', 'std::strncmp(value, "legacy", 6) == 0'),
    ("g6p82_signin_notify.h", 'return value != nullptr && std::strcmp', 'return value == nullptr || std::strcmp'),
    ("g6p82_signin_notify.h", "inline bool Enabled() { return !Legacy(); }", "inline bool Enabled() { return Legacy(); }"),
    ("g6p82_signin_notify.h", 'static const bool legacy = ParseLegacy(std::getenv("R3HD_SIGNIN_NOTIFY"));',
     'static const bool legacy = !std::getenv("R3HD_NONINTRUSIVE") || ParseLegacy(std::getenv("R3HD_SIGNIN_NOTIFY"));'),
    ("g6p82_signin_notify.h", "return Legacy() && !noted.exchange(true);", "return !noted.exchange(true);"),
    ("g6p82_signin_notify.h", "return !enabled || owner_before != owner_after;", "return owner_before != owner_after;"),
    ("g6p82_signin_notify.h", "return !enabled || owner_before != owner_after;", "return !enabled;"),
    ("g6p82_signin_notify.h", 'static const bool trace = std::getenv("R3HD_NONINTRUSIVE") != nullptr;',
     "static const bool trace = true;"),
    ("g6p79_profile_handoff_patch.py",
     "     '  const unsigned g6p82_owner_before = g6p79::Owner();  // G6-P82: the signed-in owner before this request\\n'\n",
     ""),
    ("g6p79_profile_handoff_patch.py", "'  if (g6p82_notify)\\n'", "'  if (true)\\n'"),
    ("g6p79_profile_handoff_patch.py", "g6p82::ShouldNotify(g6p82_owner_before, g6p79::Owner())",
     "g6p82::ShouldNotify(g6p79::Owner(), g6p79::Owner())"),
    ("g6p79_profile_handoff_patch.py", "'  if (g6p82::Trace())\\n'", "''"),
    ("g6p79_profile_handoff_patch.py", "'  else if (g6p82::NoteLegacyOnce())\\n'", "'  if (true)\\n'"),
    ("g6p79_profile_handoff_patch.py", "    install('g6p82_signin_notify.h')", "    pass"),
    ("g6p79_profile_handoff_patch.py",
     "if (n.kind == m6input::UeNote::kConnect && n.value == 0 && g6p79::OnDisconnect(n.user)) {\\n'",
     "if (n.kind == m6input::UeNote::kConnect && n.value == 0 && g6p79::OnDisconnect(n.user) && g6p82::Enabled()) {\\n'"),
    ("m6_input_test.cpp", "assert(g6p82::Decide(true, b, a) == (b != a));", "assert(true);"),
    ("m6_input_test.cpp", "assert(!g6p82::ShouldNotify(0, 0) && g6p82::ShouldNotify(0, 1));",
     "assert(g6p82::ShouldNotify(0, 1));"),
    ("m6_input_test.cpp", '!g6p82::ParseLegacy("legacy ")', 'true'),
    ("build_milestone8.bat", "python tools\\g6p82_signin_notify_regression.py || exit /b 1\r\n", ""),
    ("build_milestone8.bat", "python tools\\g6p82_signin_notify_regression.py || exit /b 1\n", ""),
    ("run_milestone6.ps1", f"if ($SigninNotifyLegacy) {{ $env:{FLAG} = 'legacy' }}",
     f"if ($true) {{ $env:{FLAG} = 'legacy' }}"),
    ("run_milestone6.ps1", f"else {{ [Environment]::SetEnvironmentVariable('{FLAG}', $null) }}", "else { }"),
    ("run_milestone6.ps1", f"'R3HD_TEST_USER_EVENTS', '{FLAG}')", "'R3HD_TEST_USER_EVENTS')"),
    ("m9_license_run.py", 'if args.signin_notify_legacy:\n        command.append("-SigninNotifyLegacy")',
     'if True:\n        command.append("-SigninNotifyLegacy")'),
    ("play.ps1", "$ErrorActionPreference", f"$env:{FLAG} = 'legacy'\n$ErrorActionPreference"),
    ("_flag_files", "tools/g6p82_signin_notify.h", "tools/g6p82_signin_notify.h\ntools/play.ps1"),
    ("_old_flag_files", "tools/g6p82_signin_notify_regression.py",
     "tools/g6p82_signin_notify_regression.py\ntools/run_milestone6.ps1"),
]


def run(selftest):
    t = sources()
    try:
        t["xam_user_pin"] = subprocess.check_output(
            ["git", "-C", str(SDK), "show", "HEAD:src/kernel/xam/xam_user.cpp"]).decode()
    except (OSError, subprocess.CalledProcessError):
        t["xam_user_pin"] = ""
    module = load_patch()
    results = check(t, module)
    failed = [label for label, ok in results if not ok]
    for label, ok in results:
        print(("PASS " if ok else "FAIL ") + label)
    if not selftest:
        print(f"G6P82 signin notify regression {'PASS' if not failed else 'FAIL'} {len(results) - len(failed)}/{len(results)}")
        return 0 if not failed else 1
    rejected = applied = 0
    for name, before, after in MUTATIONS:
        if before not in t[name]:
            continue  # line-ending variant not present
        applied += 1
        mutated = dict(t)
        mutated[name] = t[name].replace(before, after, 1)
        mod = load_patch(mutated[name]) if name == "g6p79_profile_handoff_patch.py" else module
        bad = [label for label, ok in check(mutated, mod) if not ok and label not in failed]
        print(("REJECTED " if bad else "MISSED   ") + f"{name}: {before[:50]!r} -> {bad[:1]}")
        rejected += bool(bad)
    ok = not failed and rejected == applied and applied >= 25
    print(f"G6P82 signin notify regression selftest {'PASS' if ok else 'FAIL'} {len(results) - len(failed)}/"
          f"{len(results)} rules, {rejected}/{applied} mutations rejected")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run("--selftest" in sys.argv[1:]))

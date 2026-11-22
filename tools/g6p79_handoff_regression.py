"""G6-P79 / G6-P80 (D-328 / D-329): source and policy pins for the TEST-ONLY profile handoff prototype.

Checks, without building or running the game:
  * the gate: R3HD_NONINTRUSIVE plus R3HD_TEST_PROFILE_HANDOFF exactly "1"; Owner() is 0 when disabled;
  * exclusivity: one owner variable, every user-indexed profile API in xam_user.cpp asks IsOwner, no user-0 literal
    is left (the patch is applied to the pinned xam_user.cpp in memory);
  * the only move point is XamShowSigninUI; a lock (commit witness) and a connected, recent START are required;
  * the disabled XamShowSigninUI broadcast is unchanged (1u << Owner() = 1);
  * content, licence and Live paths are not touched; no guest memory access; START is noted only in the M6 path;
  * the build replays the patch last and runs this regression; the runner sets the flag only on -ProfileHandoff;
    the product launcher never names it;
  * if the SDK tree has been replayed, the patched files carry the same edits.
G6-P80 adds: the candidate is the title's save-gate word, read once and read-only inside XamShowSigninUI (the only
guest access; no store); a pending owner's unplug rolls back to user 0 with XN_SYS_SIGNINCHANGED, never after the
lock; the user-scoped schedule and the scripted message-box answers exist only behind R3HD_TEST_USER_EVENTS exactly
"1" (runner -UserEvents), drop events for an unplugged user instead of redirecting them, and are bounded.
--selftest also proves that each rule rejects a targeted mutation.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"


def load_patch():
    spec = importlib.util.spec_from_file_location("g6p79_patch", ROOT / "tools" / "g6p79_profile_handoff_patch.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "tools"))
    spec.loader.exec_module(module)
    return module


def apply(text, edits):
    for before, after in edits:
        if text.count(before) != 1:
            return None
        text = text.replace(before, after)
    return text


def sources():
    t = {name: (ROOT / "tools" / name).read_text(encoding="utf-8") for name in (
        "g6p79_profile_handoff.h", "g6p79_profile_handoff_patch.py", "m6_test_input.h", "m6_input_test.cpp",
        "g6p80_test_dialog.h",
        "build_milestone8.bat", "run_milestone6.ps1", "m9_license_run.py", "play.ps1")}
    try:
        t["xam_user_pin"] = subprocess.check_output(
            ["git", "-C", str(SDK), "show", "HEAD:src/kernel/xam/xam_user.cpp"]).decode()
    except (OSError, subprocess.CalledProcessError):
        t["xam_user_pin"] = ""
    return t


def check(t, patch_module=None):
    out = []

    def rule(label, ok):
        out.append((label, bool(ok)))

    h = t["g6p79_profile_handoff.h"]
    rule("gate: exact flag inside the hidden-test gate",
         'return nonintrusive != nullptr && flag != nullptr && std::strcmp(flag, "1") == 0;' in h and
         'ParseEnable(std::getenv("R3HD_NONINTRUSIVE"), std::getenv("R3HD_TEST_PROFILE_HANDOFF"))' in h)
    rule("gate: owner is 0 when disabled",
         "inline unsigned Owner() { return Enabled() ? State().owner.load(std::memory_order_acquire) : 0u; }" in h)
    rule("gate: nothing recorded when disabled",
         "inline void NoteStart(uint32_t user, uint64_t now_ms) {\n  if (!Enabled()) return;" in h and
         "inline bool NoteCommitWitness(uint32_t user) {\n  if (!Enabled()) return false;" in h)
    body = h[h.find("Decision OnSigninRequest(const bool (&connected)[kUsers], uint64_t now_ms, uint32_t title_user) {"):]
    order = [body.find(s) for s in ("if (locked_)", "if (candidate == kUsers)", "if (candidate == owner_)",
                                    "if (start_seq_[candidate] == 0)",
                                    "if (start_seq_[candidate] <= used_seq_[candidate])",
                                    "used_seq_[candidate] = start_seq_[candidate];", "if (!connected[candidate])",
                                    "owner_ = candidate;")]
    rule("policy (G6-P80): lock, title user, same owner, an unused START (then used) and connection are checked "
         "before the single owner assignment; no wall-clock window",
         all(i > 0 for i in order) and order == sorted(order) and h.count("owner_ = candidate;") == 1 and
         h.count("owner_ = kHome;") == 1 and h.count("owner_ =") - h.count("owner_ ==") == 3 and
         "kStartWindowMs" not in h and "start_ms_[candidate]" not in body and
         h.count("used_seq_[candidate] = start_seq_[candidate];") == 1)
    rule("policy (G6-P80): the candidate is the title's selected user, not the most recent START",
         "const unsigned candidate = title_user < kUsers ? unsigned(title_user) : kUsers;" in h and
         0 < body.find("start_candidate = u;") < body.find("const unsigned candidate"))
    rule("policy (G6-P80): rollback only for a pending, non-home owner, and only to kHome",
         "if (user >= kUsers) return false;\n    used_seq_[user] = start_seq_[user];" in h and
         "if (locked_ || user != owner_ || owner_ == kHome) return false;\n    owner_ = kHome;" in h and
         "constexpr unsigned kHome = 0;" in h and
         "inline bool OnDisconnect(uint32_t user) {\n  if (!Enabled()) return false;" in h)
    rule("policy: a commit witness must come from the owner and latches",
         "if (locked_ || user != owner_) return false;\n    locked_ = true;" in h and h.count("locked_ = false") == 1)
    rule("policy: invalid users are ignored", "if (user >= kUsers) return;" in h)

    raw = t["g6p79_profile_handoff_patch.py"]
    edits = (list(patch_module.XAM_USER) + list(patch_module.XAM_INPUT) + list(patch_module.XAM_UI)
             if patch_module is not None else [])
    p = "\n".join(before + "\n" + after for before, after in edits)  # the C++ the patch writes
    rule("patch: never touches content, licence, Live or generated code",
         all(s not in raw for s in ("xam_content.cpp", "content_manager", "LicenseMask", "generated/", "xam_net",
                                  "achievement")))
    rule("patch: no guest store, and one guest read: the title's save-gate word (G6-P80; was: no guest access)",
         raw.count("TranslateVirtual") == 1 and raw.count("TranslateVirtual(g6p79::kTitleSaveGateUser)") == 1 and
         all(s not in raw for s in ("store_and_swap", "base +", "0x8287", "TranslateVirtual<")) and
         h.count("0x828750A0") == 1 and "constexpr uint32_t kTitleSaveGateUser = 0x828750A0;" in h)
    i_gate = p.find("  if (g6p79::Enabled()) {\n    bool connected")
    rule("patch (G6-P80): the save-gate read happens only inside the enabled sign-in request, before the decision",
         0 < i_gate < p.find("TranslateVirtual(g6p79::kTitleSaveGateUser)") <
         p.find("g6p79::OnSigninRequest(connected, g6p79::NowMs(), title_user)"))
    rule("patch: the disabled broadcast is unchanged (data 1 << Owner())",
         "BroadcastNotification(0x0000000A, 1u << g6p79::Owner());" in p and
         "BroadcastNotification(0x0000000A, 1);" in p)
    rule("patch: the handoff runs only in XamShowSigninUI, behind Enabled()",
         p.count("g6p79::OnSigninRequest(") == 1 and "  if (g6p79::Enabled()) {\n    bool connected" in p)
    rule("patch: commit witnesses are the owner's settings read and device selection",
         p.count("g6p79::NoteCommitWitness(user_index)") == 2 and "witness=profile_settings" in p and
         "witness=device_selector" in p)
    rule("patch (G6-P80): a rollback comes only from the user-event hook on an unplug, then SIGNINCHANGED",
         p.count("g6p79::OnDisconnect(") == 1 and
         "if (n.kind == m6input::UeNote::kConnect && n.value == 0 && g6p79::OnDisconnect(n.user)) {" in p and
         0 < p.find("g6p79::OnDisconnect(") <
         p.find("BroadcastNotification(0x0000000A, 1u << g6p79::Owner());  // XN_SYS_SIGNINCHANGED"))
    rule("patch (G6-P80): the input path pumps before routing and samples per user; dialogs only behind the flag",
         "    m6input::Pump();  // G6-P80: no-op unless R3HD_TEST_USER_EVENTS\n"
         "    for (int b; (b = m6input::TakeDialogAnswer()) >= 0;) g6p80dlg::Answer(uint32_t(b));\n"
         "    const auto m6_route = m6input::RouteFor(actual_user_index);\n" in p and
         "m6input::SampleFor(actual_user_index, bool(input_state))" in p and
         "  if (m6input::UserEventsEnabled() &&  // G6-P80" in p and p.count("g6p80dlg::Open(") == 1 and
         "      if (!m6input::UserEventsEnabled()) return false;\n" in p)
    rule("patch: START is noted only inside the hidden schedule path, behind Enabled()",
         "    if (g6p79::Enabled() && input_state && actual_user_index < g6p79::kUsers) {" in p and
         p.count("g6p79::NoteStart(") == 1)
    pin = t["xam_user_pin"]
    rule("xam_user: the pinned source is available (rules below are not skipped)", bool(pin) and patch_module is not None)
    if pin and patch_module is not None:
        patched = apply(pin, patch_module.XAM_USER)
        rule("xam_user: every pinned edit anchors exactly once", patched is not None)
        patched = patched or ""
        rule("xam_user: no user-0 literal remains",
             all(s not in patched for s in ("if (user_index) {", "user_index == 0", "&& user_index) {")))
        rule("xam_user: twelve owner checks (every user-indexed profile API)",
             patched.count("g6p79::IsOwner(user_index)") == 12)
        w = patched.find("witness=profile_settings")
        rule("xam_user: the settings witness follows the size query and the setting validation",
             0 < patched.find("return X_ERROR_INSUFFICIENT_BUFFER;") < w and
             0 < patched.find("if (any_missing) {") < w)
        rule("xam_user: content and Live answers otherwise unchanged",
             "return 6 /* 6 appears to be Gold */;" in patched and "*out_value = 0;" in patched)

    m6 = t["m6_test_input.h"]
    rule("routes: without codes the dynamic routing equals the G6-P77 routing",
         "static Routing r = [] { Routing x; x.schedule_user = TestUser(); return x; }();" in m6 and
         "if (r.schedule_user < 0 || user > 3) return kNotConnected;" in m6)
    rule("user events (G6-P80): exact flag inside the hidden gate; every entry point is a no-op without it",
         'ParseUserEvents(std::getenv("R3HD_NONINTRUSIVE"), std::getenv("R3HD_TEST_USER_EVENTS"))' in m6 and
         "return nonintrusive != nullptr && flag != nullptr && flag[0] == '1' && flag[1] == '\\0';" in m6 and
         "inline void Pump() {\n  if (!UserEventsEnabled()) return;" in m6 and
         "  if (!UserEventsEnabled()) return Sample(consume);" in m6 and
         "  if (UserEventsEnabled()) return UeRouteFor(user);" in m6 and
         "inline int TakeDialogAnswer() {\n  if (!UserEventsEnabled()) return -1;" in m6)
    rule("user events (G6-P80): an unplugged target's press is dropped and reported, never redirected",
         "    if (!Present(target_)) {\n      if (value == 1 && button) notes.push_back({UeNote::kDrop" in m6 and
         0 < m6.find("    if (!Present(target_)) {") < m6.find("      pending_[target_] |= button;"))
    rule("user events (G6-P80): bounded lines, ledger, answers and per-call work",
         "constexpr unsigned kUeUsers = 4, kUeMaxLines = 1024, kUeLedger = 128, kUeAnswers = 8;" in m6 and
         "if (lines_ >= kUeMaxLines) {" in m6 and "for (unsigned guard = 0; guard < 64; ++guard)" in m6)
    dlg = t["g6p80_test_dialog.h"]
    rule("dialog (G6-P80): one pending box, answered only by a scheduled code, via the SDK's deferred completion",
         "if (Current().open) return false;" in dlg and "if (!box.open || button >= box.buttons) {" in dlg and
         "REX_KERNEL_STATE()->CompleteOverlappedDeferred(" in dlg and dlg.count("BroadcastNotification(0x9,") == 2 and
         "0x82" not in dlg)
    rule("routes: only codes 310-313 / 320-323 are consumed",
         "if ((scan_ >= 310 && scan_ <= 313) || (scan_ >= 320 && scan_ <= 323)) { if (route_) route_(scan_, down_); continue; }"
         in m6)
    test = t["m6_input_test.cpp"]
    rule("tests: policy and route cases in the replayed M6 unit test",
         '#include "g6p79_profile_handoff.h"' in test and "Outcome::kLocked" in test and
         "Outcome::kNotConnected" in test and "Outcome::kUsedStart" in test and "ApplyRouteCode(r, 321, 1)" in test and
         "assert(!g6p79::Enabled() && g6p79::Owner() == 0" in test)
    rule("tests (G6-P80): title-selected candidate, rollback and user-scoped events in the replayed M6 unit test",
         "Outcome::kNoTitleUser" in test and "p.OnDisconnect(1) && p.Owner() == 0" in test and
         "m6input::UserEvents e(" in test and "N::kDrop" in test and "N::kDeliver" in test and
         "m6input::kUeMaxLines" in test)
    rule("tests (G6-P80): one-use START: delayed request accepted, used / voided / changed-selection STARTs refused",
         "d = p.OnSigninRequest(all, 2000 + 600000, 1); assert(d.outcome == Outcome::kMoved" in test and
         "d = p.OnSigninRequest(all, 50, 1); assert(d.outcome == Outcome::kUsedStart" in test and
         "d = p.OnSigninRequest(all, 20, 2); assert(d.outcome == Outcome::kUsedStart" in test and
         "d = p.OnSigninRequest(all, 1200, 1); assert(d.outcome == Outcome::kUsedStart" in test)

    bat = t["build_milestone8.bat"]
    main = "python tools\\g6p79_profile_handoff_patch.py || exit /b 1"
    i_main, i_prev = bat.find(main), bat.find("python tools\\r3hd_pad_motors_patch.py || exit /b 1")
    rule("build: the patch is replayed last, before the SDK build",
         bat.count(main) == 1 and 0 < i_prev < i_main < bat.find("cmake -S external"))
    rule("build: this regression runs before M8_BUILD_OK",
         0 < bat.find("python tools\\g6p79_handoff_regression.py || exit /b 1") < bat.find("echo M8_BUILD_OK") and
         bat.find("m6_input_test.exe || exit /b 1") > 0)
    ps = t["run_milestone6.ps1"]
    rule("runner: the flag is set only by -ProfileHandoff and restored afterwards",
         "if ($ProfileHandoff) { $env:R3HD_TEST_PROFILE_HANDOFF = '1' } else { [Environment]::SetEnvironmentVariable('R3HD_TEST_PROFILE_HANDOFF', $null) }"
         in ps and "'R3HD_PROFILE_TRACE', 'R3HD_TEST_PROFILE_HANDOFF', 'R3HD_TEST_USER_EVENTS'" in ps and  # G6-P82 appends one
         "profile_handoff = [bool]$ProfileHandoff" in ps)
    rule("runner (G6-P80): user events only by -UserEvents and restored afterwards; m9 passes it only on --user-events",
         "if ($UserEvents) { $env:R3HD_TEST_USER_EVENTS = '1' } else { [Environment]::SetEnvironmentVariable('R3HD_TEST_USER_EVENTS', $null) }"
         in ps and "user_events = [bool]$UserEvents" in ps and
         'if args.user_events:\n        command.append("-UserEvents")' in t["m9_license_run.py"])
    rule("runner: m9 driver passes -ProfileHandoff only on --profile-handoff",
         'if args.profile_handoff:\n        command.append("-ProfileHandoff")' in t["m9_license_run.py"])
    rule("product: the launcher never names the flags",
         "R3HD_TEST_PROFILE_HANDOFF" not in t["play.ps1"] and "R3HD_TEST_USER_EVENTS" not in t["play.ps1"])

    replayed = SDK / "src" / "kernel" / "xam" / "xam_user.cpp"
    if patch_module is not None and replayed.exists() and "G6-P79" in replayed.read_text(errors="replace"):
        live = {rel: (SDK / rel).read_text(errors="replace") for rel in (
            "src/kernel/xam/xam_user.cpp", "src/kernel/xam/xam_input.cpp", "src/kernel/xam/xam_ui.cpp")}
        for rel, edits in (("src/kernel/xam/xam_user.cpp", patch_module.XAM_USER),
                           ("src/kernel/xam/xam_input.cpp", patch_module.XAM_INPUT),
                           ("src/kernel/xam/xam_ui.cpp", patch_module.XAM_UI)):
            rule(f"replayed tree: {rel} carries every edit once",
                 all(live[rel].count(after) == 1 for _, after in edits))
        for name in ("g6p79_profile_handoff.h", "g6p80_test_dialog.h", "m6_test_input.h"):
            installed = SDK / "include" / "rex" / name
            rule(f"replayed tree: the installed {name} is current",
                 installed.exists() and installed.read_bytes() == (ROOT / "tools" / name).read_bytes())
    return out


MUTATIONS = [
    ("g6p79_profile_handoff.h", 'std::strcmp(flag, "1") == 0', 'flag[0] == \'1\''),
    ("g6p79_profile_handoff.h", "? State().owner.load(std::memory_order_acquire) : 0u", "? State().owner.load() : 1u"),
    ("g6p79_profile_handoff.h", "  if (!Enabled()) return;", "  "),
    ("g6p79_profile_handoff.h", "    if (locked_) return {Outcome::kLocked, from, owner_, candidate};\n", ""),
    ("g6p79_profile_handoff.h", "    if (!connected[candidate]) return {Outcome::kNotConnected, from, owner_, candidate};\n", ""),
    ("g6p79_profile_handoff.h", "if (locked_ || user != owner_) return false;", "if (locked_) return false;"),
    ("g6p79_profile_handoff.h", "if (user >= kUsers) return;", ""),
    ("g6p79_profile_handoff_patch.py", "BroadcastNotification(0x0000000A, 1u << g6p79::Owner());",
     "BroadcastNotification(0x0000000A, 0xF);"),
    ("g6p79_profile_handoff_patch.py", "    ('#include <rex/system/xtypes.h>\\n',", "    ('#include <rex/system/xtypes.h>\\n', # xam_content.cpp\n"),
    ("g6p79_profile_handoff_patch.py", "OWNER = 'g6p79::IsOwner(user_index)'", "OWNER = 'user_index == 0'"),
    ("g6p79_profile_handoff_patch.py", "     f'  if (!{OWNER}) {{  // {TAG}'),", "     '  if (user_index) {'),"),
    ("g6p79_profile_handoff_patch.py", "  if (!xuids && g6p79::NoteCommitWitness(user_index))", "  if (false)"),
    ("g6p79_profile_handoff_patch.py", "    if (g6p79::Enabled() && input_state && actual_user_index < g6p79::kUsers) {",
     "    if (input_state && actual_user_index < g6p79::kUsers) {"),
    ("m6_test_input.h", "{ if (route_) route_(scan_, down_); continue; }", "{ continue; }"),
    ("m6_input_test.cpp", '#include "g6p79_profile_handoff.h"', ""),
    ("build_milestone8.bat", "python tools\\g6p79_handoff_regression.py || exit /b 1\r\n", ""),
    ("build_milestone8.bat", "python tools\\g6p79_handoff_regression.py || exit /b 1\n", ""),
    ("run_milestone6.ps1", "if ($ProfileHandoff) { $env:R3HD_TEST_PROFILE_HANDOFF = '1' }",
     "if ($true) { $env:R3HD_TEST_PROFILE_HANDOFF = '1' }"),
    ("play.ps1", "$ErrorActionPreference", "$env:R3HD_TEST_PROFILE_HANDOFF = '1'\n$ErrorActionPreference"),
    # G6-P80
    ("g6p79_profile_handoff.h", "const unsigned candidate = title_user < kUsers ? unsigned(title_user) : kUsers;",
     "const unsigned candidate = start_candidate;"),
    ("g6p79_profile_handoff.h", "if (locked_ || user != owner_ || owner_ == kHome) return false;",
     "if (user != owner_ || owner_ == kHome) return false;"),
    # G6-P80 continuation: the one-use START authorization replaces the 3 s window
    ("g6p79_profile_handoff.h", "    used_seq_[candidate] = start_seq_[candidate];  // this START", "    // this START"),
    ("g6p79_profile_handoff.h", "    used_seq_[user] = start_seq_[user];  // a START made before", "    // a START made before"),
    ("g6p79_profile_handoff.h", "    if (start_seq_[candidate] <= used_seq_[candidate])\n",
     "    if (now_ms - start_ms_[candidate] > 3000)\n"),
    ("m6_input_test.cpp", "d = p.OnSigninRequest(all, 50, 1); assert(d.outcome == Outcome::kUsedStart",
     "d = p.OnSigninRequest(all, 50, 1); assert(d.outcome == Outcome::kMoved"),
    ("g6p79_profile_handoff.h",
     "    if (start_seq_[candidate] == 0) return {Outcome::kNoCandidate, from, owner_, candidate, start_candidate};\n", ""),
    ("g6p79_profile_handoff.h", "    owner_ = kHome;  // rollback", "    owner_ = (user + 1) % kUsers;  // rollback"),
    ("g6p79_profile_handoff_patch.py", "        REX_KERNEL_MEMORY()->TranslateVirtual(g6p79::kTitleSaveGateUser));\\n'",
     "        REX_KERNEL_MEMORY()->TranslateVirtual(g6p79::kTitleSaveGateUser));\\n'\n"
     "     '    rex::memory::store_and_swap<uint32_t>(nullptr, 0);\\n'"),
    ("g6p79_profile_handoff_patch.py", "'    m6input::Pump();  // G6-P80: no-op unless R3HD_TEST_USER_EVENTS\\n'", "''"),
    ("g6p79_profile_handoff_patch.py", "'  if (m6input::UserEventsEnabled() &&  // G6-P80", "'  if (true &&  // G6-P80"),
    ("g6p79_profile_handoff_patch.py", "&& n.value == 0 && g6p79::OnDisconnect(n.user)", "&& g6p79::OnDisconnect(n.user)"),
    ("m6_test_input.h", "inline void Pump() {\n  if (!UserEventsEnabled()) return;", "inline void Pump() {\n"),
    ("m6_test_input.h", "  if (UserEventsEnabled()) return UeRouteFor(user);", "  if (true) return UeRouteFor(user);"),
    ("m6_test_input.h", "flag[0] == '1' && flag[1] == '\\0'", "flag[0] == '1'"),
    ("m6_test_input.h", "    if (!Present(target_)) {\n      if (value == 1 && button) notes.push_back({UeNote::kDrop",
     "    if (false) {\n      if (value == 1 && button) notes.push_back({UeNote::kDrop"),
    ("m6_test_input.h", "for (unsigned guard = 0; guard < 64; ++guard)", "for (;;)"),
    ("g6p80_test_dialog.h", "if (Current().open) return false;", ""),
    ("m6_input_test.cpp", "p.OnDisconnect(1) && p.Owner() == 0", "p.Owner() == 1"),
    ("run_milestone6.ps1", "if ($UserEvents) { $env:R3HD_TEST_USER_EVENTS = '1' }",
     "if ($true) { $env:R3HD_TEST_USER_EVENTS = '1' }"),
    ("play.ps1", "$ErrorActionPreference", "$env:R3HD_TEST_USER_EVENTS = '1'\n$ErrorActionPreference"),
]


def run(selftest):
    t = sources()
    module = load_patch()
    results = check(t, module)
    failed = [label for label, ok in results if not ok]
    for label, ok in results:
        print(("PASS " if ok else "FAIL ") + label)
    if not selftest:
        print(f"G6P79 handoff regression {'PASS' if not failed else 'FAIL'} {len(results) - len(failed)}/{len(results)}")
        return 0 if not failed else 1
    rejected = 0
    applied = 0
    for name, before, after in MUTATIONS:
        if before not in t[name]:
            continue  # line-ending variant not present
        applied += 1
        mutated = dict(t)
        mutated[name] = t[name].replace(before, after, 1)
        mod = module
        if name == "g6p79_profile_handoff_patch.py":
            ns = {"__name__": "g6p79_mutant"}
            sys.path.insert(0, str(ROOT / "tools"))
            exec(compile(mutated[name], "mutant", "exec"), ns)
            mod = type("M", (), ns)
        bad = [label for label, ok in check(mutated, mod) if not ok and label not in failed]
        print(("REJECTED " if bad else "MISSED   ") + f"{name}: {before[:50]!r} -> {bad[:1]}")
        rejected += bool(bad)
    ok = not failed and rejected == applied and applied >= 30
    print(f"G6P79 handoff regression selftest {'PASS' if ok else 'FAIL'} {len(results) - len(failed)}/{len(results)} "
          f"rules, {rejected}/{applied} mutations rejected")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run("--selftest" in sys.argv[1:]))

"""Regression tests for the LM-1 Linux build driver (run anywhere; nothing is built).

Native history covered here:
  * attempt 1: SDK built, `cmake --install` failed on libSDL3_test.a (SDL3_test not built), then the driver crashed
    with KeyError: 'sdk' instead of reporting the CMake error;
  * retry 1: SDK built with a single-config generator, install failed on libTracyClient.so (TracyClient is a Release
    target dependency only under the SDK's multi-config preset); the SDK's CMake refused GCC (Clang requirement).
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_linux_build as B  # noqa: E402

SDL_INSTALL_FAILURE = """CMake Error at external/rexglue-sdk/out/build/linux-clang/thirdparty/sdl3/cmake_install.cmake:54 (file):
  file INSTALL cannot find
  "/home/user/RaymanLM1/external/rexglue-sdk/out/linux-amd64/libSDL3_test.a":
  No such file or directory.
"""
TRACY_INSTALL_FAILURE = """-- Installing: /w/external/rexglue-sdk/out/install/linux-clang/include/tracy/tracy/TracyC.h
CMake Error at external/rexglue-sdk/out/build/linux-clang/cmake_install.cmake:61 (file):
  file INSTALL cannot find
  "/w/external/rexglue-sdk/out/linux-amd64/libTracyClient.so": No such file or
  directory.
"""
CLANG_REQUIREMENT = """CMake Error at CMakeLists.txt:84 (message):
  ReXGlue requires the Clang compiler (LLVM Clang or AppleClang).  Please set
  CMAKE_CXX_COMPILER to clang++
"""


class FakeShell:
    """Stands in for sh(). Configure/build succeed unless told otherwise."""

    def __init__(self, install_text=None, gcc_host_text=None):
        self.install_text = install_text      # failing install output, or None
        self.gcc_host_text = gcc_host_text    # failing GCC host configure output, or None
        self.calls = []

    def __call__(self, argv, log, cwd=None, check=True, env=None):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        rc, text = 0, ""
        if argv[:2] == ["cmake", "--install"] and self.install_text:
            rc, text = 1, self.install_text
        if argv[:2] == ["cmake", "-S"] and "-DCMAKE_CXX_COMPILER=g++" in argv and self.gcc_host_text:
            rc, text = 1, self.gcc_host_text
        if rc and check:
            raise B.Fail("command failed")
        return rc, text


def run_driver(out, shell, sample=None, host=None):
    args = argparse.Namespace(out=out, compilers=["clang", "gcc"], jobs=2, private_headers=Path("h"),
                              lge_private=Path("lge"))
    stdout = io.StringIO()
    patches = [mock.patch.object(B, "doctor", return_value={"ok": True}),
               mock.patch.object(B, "apply_patches", return_value={"steps": []}),
               mock.patch.object(B, "sh", shell),
               mock.patch.object(B, "compile_generated_sample", sample or (lambda *a: {"exit": 0})),
               mock.patch.object(B, "host_tests", lambda *a: {"m16-O0": 0, "m20-O0": 0})]
    if host:
        patches.append(mock.patch.object(B, "compile_host", host))
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(contextlib.redirect_stdout(stdout))
        rc = B.run(args)
    return rc, json.loads((out / "results.json").read_text()), stdout.getvalue(), shell


class SdkContractTests(unittest.TestCase):
    def test_targets_follow_the_windows_chain_including_sdl3_test(self):
        self.assertEqual(B.sdk_targets(), ["rexglue", "rexgpu-xenos", "SDL3_test"])

    def test_sdk_uses_its_own_clang_preset_and_release_config(self):
        shell = FakeShell()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(B, "sh", shell):
            result = B.build_sdk(Path(d), 2)
        configure, build, install = shell.calls
        self.assertEqual(configure[:3], ["cmake", "--preset", "linux-amd64"])
        self.assertFalse(any("COMPILER" in a for a in configure))  # The preset's Clang, never overridden.
        self.assertEqual(build[build.index("--config") + 1], "Release")
        self.assertIn("SDL3_test", build)
        self.assertEqual(install[:2] + install[-2:], ["cmake", "--install", "--config", "Release"])
        self.assertEqual((result["compiler"], result["install_exit"]), ("clang", 0))
        self.assertIn("installed", result)

    def test_gcc_never_builds_the_sdk(self):
        with tempfile.TemporaryDirectory() as d:
            _, result, _, shell = run_driver(Path(d), FakeShell())
        sdk_configures = [c for c in shell.calls if c[:2] == ["cmake", "--preset"]]
        self.assertEqual(len(sdk_configures), 1)
        self.assertEqual(result["sdk"]["compiler"], "clang")


class FailureReportingTests(unittest.TestCase):
    def test_retry1_tracy_install_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            rc, result, text, _ = run_driver(Path(d), FakeShell(install_text=TRACY_INSTALL_FAILURE))
        self.assertEqual((rc, result["status"]), (1, "FAIL"))
        self.assertNotIn("traceback", result)
        sdk = result["sdk"]
        self.assertEqual((sdk["build_exit"], sdk["install_exit"]), (0, 1))
        self.assertTrue(any("libTracyClient.so" in e for e in sdk["install_errors"]))
        for key in ("clang", "gcc"):
            self.assertNotIn("host", result["configurations"][key])  # Nothing compiled against a missing install.
            self.assertTrue(result["configurations"][key]["host_tests"])  # Independent tests still run.
        self.assertIn('"install_exit": 1', text)

    def test_attempt1_sdl_install_error_extraction(self):
        errors = B.install_errors(SDL_INSTALL_FAILURE)
        self.assertEqual(len(errors), 1)
        self.assertIn("libSDL3_test.a", errors[0])

    def test_gcc_host_refused_by_the_sdk_is_unsupported_not_failed(self):
        with tempfile.TemporaryDirectory() as d:
            rc, result, _, _ = run_driver(Path(d), FakeShell(gcc_host_text=CLANG_REQUIREMENT))
        self.assertEqual(result["configurations"]["gcc"]["host"]["status"], "sdk-unsupported")
        self.assertEqual(result["configurations"]["clang"]["host"]["status"], "pass")
        self.assertEqual((rc, result["status"]), (0, "PASS"))

    def test_other_gcc_host_configure_errors_fail(self):
        with tempfile.TemporaryDirectory() as d:
            rc, result, _, _ = run_driver(Path(d), FakeShell(gcc_host_text="CMake Error at x:1 (find_package):\n  boom\n"))
        self.assertEqual(result["configurations"]["gcc"]["host"]["status"], "fail")
        self.assertEqual((rc, result["status"]), (1, "FAIL"))

    def test_unexpected_driver_error_is_recorded(self):
        def broken(*args):
            raise KeyError("sdk")
        with tempfile.TemporaryDirectory() as d:
            rc, result, text, _ = run_driver(Path(d), FakeShell(), host=broken)
        self.assertEqual((rc, result["status"]), (1, "FAIL"))
        self.assertIn("driver error KeyError", result["error"])
        self.assertIn("KeyError", result["traceback"])
        self.assertIn("R3HD_LINUX_BUILD FAIL", text)

    def test_summary_never_raises_on_partial_results(self):
        self.assertEqual(B.summarize({})["sdk"]["install_exit"], None)
        rows = B.summarize({"sdk": {"build_exit": 0}, "configurations": {"clang": {}, "gcc": {"host": None}}})
        self.assertEqual((rows["clang"]["host"], rows["gcc"]["host"]), (None, None))

    def test_passing_run(self):
        with tempfile.TemporaryDirectory() as d:
            rc, result, text, _ = run_driver(Path(d), FakeShell())
        self.assertEqual((rc, result["status"]), (0, "PASS"))
        self.assertTrue(text.startswith("R3HD_LINUX_BUILD PASS "))

    def test_a_failing_stage_fails_the_run(self):
        with tempfile.TemporaryDirectory() as d:
            rc, result, _, _ = run_driver(Path(d), FakeShell(), sample=lambda *a: {"exit": 1})
        self.assertEqual((rc, result["status"]), (1, "FAIL"))


class GccGeneratedSampleTests(unittest.TestCase):
    """LM-1 retry 2: GCC rejected the prelude's __builtin_assume in every generated function."""

    PRELUDE = ("#include <cstddef>\n#include <cstdint>\n"
               "#define REX_FUNC_PROLOGUE() __builtin_assume(((size_t)base & 0x1F) == 0)\n"
               "int f(uint8_t* base) { REX_FUNC_PROLOGUE(); return base[0]; }\n")

    def sample_argv(self, key):
        shell = FakeShell()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(B, "sh", shell):
            B.compile_generated_sample(Path(d), key, Path("lge"))
        return shell.calls[0]

    def test_compat_include_is_gcc_only(self):
        header = str(B.ROOT / "tools/linux/compat_gcc/rex_gcc_builtin_assume.h")
        self.assertIn(header, self.sample_argv("gcc"))
        self.assertNotIn(header, self.sample_argv("clang"))
        self.assertTrue(Path(header).exists())

    def test_real_gcc_reproduces_and_resolves_the_retry2_error(self):
        import shutil
        import subprocess
        gxx = shutil.which("g++")
        if not gxx or "clang" in subprocess.run([gxx, "--version"], capture_output=True, text=True).stdout:
            self.skipTest("GNU g++ not available")
        header = B.ROOT / "tools/linux/compat_gcc/rex_gcc_builtin_assume.h"
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "prelude.cpp"
            src.write_text(self.PRELUDE)
            bare = subprocess.run([gxx, "-std=c++23", "-fsyntax-only", str(src)], capture_output=True, text=True)
            self.assertNotEqual(bare.returncode, 0)
            self.assertIn("__builtin_assume", bare.stderr)
            fixed = subprocess.run([gxx, "-std=c++23", "-O2", "-fsyntax-only", "-include", str(header), str(src)],
                                   capture_output=True, text=True)
            self.assertEqual(fixed.returncode, 0, fixed.stderr)


def diag_tree(root, tamper=False):
    import hashlib
    gen, src = root / "generated/default", root / "src"
    gen.mkdir(parents=True)
    src.mkdir()
    (root / "DIAGNOSTIC_SEH_DISABLED.txt").write_text("diagnostic\n")
    (gen / "r3hd_recomp.0.cpp").write_text("// generated\n")
    (src / "main.cpp").write_text("int main(){}\n")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {"format": "R3HD_DIAG_TREE_V1", "manifest_change": [B.__name__, "generate_exception_handlers = false"],
                "codegen_files": 1, "codegen_digest": "d", "audit": {}, "seh_emission": {"__try": 0, "M4Init": 0},
                "generated_sha256": {"r3hd_recomp.0.cpp": sha(gen / "r3hd_recomp.0.cpp")},
                "src_sha256": {"main.cpp": sha(src / "main.cpp")}}
    (root / "diag_manifest.json").write_text(json.dumps(manifest))
    if tamper:
        (gen / "r3hd_recomp.0.cpp").write_text("// edited\n")
    return root


class GameTests(unittest.TestCase):
    """LM-2: the Linux r3hd from the diagnostic tree (no run)."""

    def test_tree_identity_is_verified(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(B.verify_tree(diag_tree(Path(d)))["codegen_digest"], "d")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(B.Fail):
            B.verify_tree(diag_tree(Path(d), tamper=True))
        with tempfile.TemporaryDirectory() as d, self.assertRaises(B.Fail):
            B.verify_tree(Path(d))  # Unmarked: never a production tree.

    def test_configure_is_clang_and_the_diag_tree_and_failures_are_recorded(self):
        shell = FakeShell()
        def fake(argv, log, cwd=None, check=True, env=None):
            argv = [str(a) for a in argv]
            shell.calls.append(argv)
            return (1, "src/main.cpp:3:4: error: boom\n") if argv[:2] == ["cmake", "--build"] else (0, "")
        with tempfile.TemporaryDirectory() as d:
            tree = diag_tree(Path(d) / "tree")
            prefix = B.SDK / f"out/install/{B.SDK_PRESET}/lib/cmake/rexglue"
            with mock.patch.object(B, "sh", fake), mock.patch.object(Path, "is_dir", lambda p: True if p == prefix else
                                                                       Path.exists(p) and not Path.is_file(p)):
                result = B.build_game(Path(d) / "out", tree, 2)
        configure = shell.calls[0]
        self.assertIn("-DCMAKE_CXX_COMPILER=clang++", configure)
        self.assertIn(f"-DR3HD_TREE={tree}", configure)
        build = shell.calls[1]
        self.assertEqual(build[build.index("--target") + 1], "r3hd")
        self.assertEqual((result["build_exit"], result["error_count"]), (1, 1))
        self.assertNotIn("elf", result)
        self.assertFalse(B.game_passed(result))

    def test_symbol_gates(self):
        good = "\n".join(f"0000 T {s}" for s in B.GAME_REQUIRED_SYMBOLS) + "\n0000 T __imp__sub_820E7440\n"
        sym = B.symbol_checks(good)
        self.assertEqual((sym["missing"], sym["forbidden"], sym["imp_functions"]), ([], [], 1))
        self.assertEqual(B.symbol_checks(good + "0000 T _Z6M4InitR7M4Frame\n")["forbidden"], ["_Z6M4InitR7M4Frame"])
        elf = {"diagnostic_banner": True, "symbols": sym}
        self.assertTrue(B.game_passed({"configure_exit": 0, "build_exit": 0, "elf": elf}))
        self.assertFalse(B.game_passed({"configure_exit": 0, "build_exit": 0, "elf": dict(elf, diagnostic_banner=False)}))


def pinned_vulkan_cp():
    import subprocess
    return subprocess.check_output(["git", "-C", str(B.SDK), "show", f"{B.SDK_PIN}:{B.VULKAN_CP}"])


class VulkanVbFixTests(unittest.TestCase):
    """D-020 on Vulkan (E-369): the one-file edit, the A/B conditions and the run judge."""

    def sdk_with(self, d, data):
        path = Path(d) / B.VULKAN_CP
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        sys.path.insert(0, str(B.ROOT / "tools"))
        import m3_runtime_patch
        return path, [mock.patch.object(B, "SDK", Path(d)), mock.patch.object(m3_runtime_patch, "SDK", Path(d))]

    def test_pinned_file_gets_exactly_the_replayed_chain_state_and_is_idempotent(self):
        pinned = pinned_vulkan_cp()
        self.assertEqual(B.hashlib.sha256(pinned).hexdigest(), B.VULKAN_CP_PINNED)
        with tempfile.TemporaryDirectory() as d:
            path, patches = self.sdk_with(d, pinned)
            with contextlib.ExitStack() as stack, contextlib.redirect_stdout(io.StringIO()):
                for p in patches:
                    stack.enter_context(p)
                first = B.apply_vulkan_vb_fix()
                second = B.apply_vulkan_vb_fix()
            self.assertEqual((first["after"], first["applied"]), (B.VULKAN_CP_FIXED, True))
            self.assertEqual((second["after"], second["applied"]), (B.VULKAN_CP_FIXED, False))
            self.assertIn(b"M5 vb_residency backend=vulkan mode=", path.read_bytes())

    def test_an_unexpected_vulkan_file_is_refused_untouched(self):
        tampered = pinned_vulkan_cp().replace(b"vertex_buffers_in_sync_", b"vertex_buffers_insync_", 1)
        with tempfile.TemporaryDirectory() as d:
            path, patches = self.sdk_with(d, tampered)
            with contextlib.ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                with self.assertRaises(B.Fail):
                    B.apply_vulkan_vb_fix()
            self.assertEqual(path.read_bytes(), tampered)

    def test_modes_differ_only_in_the_switch(self):
        base = {"PATH": "/usr/bin", "R3HD_TRIAL": "1", "REX_FULLSCREEN": "1", "R3HD_M5_VB_RESIDENCY_CACHE": "1"}
        fixed, pinned = B.menu_env("fixed", base, "/sdk/lib"), B.menu_env("pinned", base, "/sdk/lib")
        self.assertNotIn("R3HD_M5_VB_RESIDENCY_CACHE", fixed)
        self.assertEqual(pinned.pop("R3HD_M5_VB_RESIDENCY_CACHE"), "1")
        self.assertEqual(fixed, pinned)
        self.assertEqual(fixed, {"PATH": "/usr/bin", "DISABLE_LSFG": "1", "LD_LIBRARY_PATH": "/sdk/lib"})
        argv = B.menu_argv(Path("/b/r3hd"), Path("/g"), Path("/o/menu_fixed"))
        for flag in ("--mnk_mode=true", "--fullscreen=false", "--gpu_plugin=xenos", "--game_data_root=/g"):
            self.assertIn(flag.replace("/", B.os.sep) if flag.startswith("--game") else flag, argv)

    def test_run_judge(self):
        consumed = "M5 consumed function=822331D8 samples={} controller=82C68B80 buttons={} a=0 lx=0 ly={} rx=0"
        log = "\n".join(["M32 keyboard test_instance=false mnk_mode=true", "M5 vb_residency backend=vulkan mode=pinned_cache",
                         consumed.format(1, "0010", 0), consumed.format(2, "1000", 0), consumed.format(3, "0000", -32768),
                         "XELOG_GPU PRESENT: a", "XELOG_GPU PRESENT: b"])
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            (run / "runtime.log").write_text(log)
            (run / "stderr.log").write_text("R3HD DIAGNOSTIC BUILD: guest SEH disabled\n")
            j = B.judge_menu_run("pinned", run)
            self.assertTrue(j["mode_ok"] and j["banner"] and j["keyboard_mnk"])
            self.assertEqual((j["guest_buttons"], j["guest_stick_samples"], j["presents"], j["m4_aborts"]),
                             (["0000", "0010", "1000"], 1, 2, 0))
            self.assertFalse(B.judge_menu_run("fixed", run)["mode_ok"])
            (run / "stderr.log").write_text("M4 portable: unsupported guest RtlRaiseException (0x1, 0x2)\n")
            self.assertEqual(B.judge_menu_run("pinned", run)["m4_aborts"], 1)
            (run / "stderr.log").write_text("M4 portable: FAIL-FAST unhandled guest exception (0xC0000017, 0x0)\n")
            self.assertEqual(B.judge_menu_run("pinned", run)["m4_aborts"], 1)  # LM-A portable backend record

    def test_vbfix_acceptance_needs_the_marker_and_the_unchanged_elf(self):
        ok = {"source": {"after": B.VULKAN_CP_FIXED}, "build_exit": 0, "install_exit": 0, "plugin": {"marker": True},
              "elf_unchanged": True}
        self.assertTrue(B.vbfix_passed(ok))
        self.assertFalse(B.vbfix_passed(dict(ok, plugin={"marker": False})))
        self.assertFalse(B.vbfix_passed(dict(ok, elf_unchanged=False)))
        self.assertFalse(B.vbfix_passed(dict(ok, source={"after": B.VULKAN_CP_PINNED})))

    def test_evidence_leaves_out_user_cache_build_and_the_plugin_backup(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            for rel in ("results-vbfix.json", "vbfix.log", "menu_fixed/run.json", "menu_fixed/runtime.log",
                        "menu_fixed/observations.txt", "menu_fixed/user/profile.json", "menu_fixed/cache/x.log",
                        "build/game/CMakeFiles/a.log", "plugin_before/notes.txt"):
                (out / rel).parent.mkdir(parents=True, exist_ok=True)
                (out / rel).write_text("x")
            with contextlib.redirect_stdout(io.StringIO()):
                B.evidence(argparse.Namespace(out=out, zip=out / "e.zip"))
            import zipfile
            names = sorted(zipfile.ZipFile(out / "e.zip").namelist())
        self.assertEqual(names, ["PRIVATE.txt", "menu_fixed/observations.txt", "menu_fixed/run.json",
                                 "menu_fixed/runtime.log", "results-vbfix.json", "vbfix.log"])


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeProcess:
    """Exits at `exit_at` (or on the first signal in `honours`); writes the guest-exit line at `guest_exit_at`."""

    def __init__(self, clock, log, exit_at=None, guest_exit_at=None, honours=()):
        self.clock, self.log, self.exit_at, self.guest_exit_at, self.honours = clock, log, exit_at, guest_exit_at, honours
        self.sent, self.code, self.pid = [], None, 4242

    def poll(self):
        if self.guest_exit_at is not None and self.clock() >= self.guest_exit_at and not self.log.exists():
            self.log.write_text("... M2 guest_thread_exit\n... Execution complete\n")
        if self.code is None and self.exit_at is not None and self.clock() >= self.exit_at:
            self.code = 0
        return self.code

    def send_signal(self, sig):
        self.sent.append(int(sig))
        if int(sig) in self.honours:
            self.code = -int(sig)

    def kill(self):
        self.sent.append(9)
        self.code = -9

    def wait(self):
        return self.code


class ExitWatchTests(unittest.TestCase):
    """E-371: a shutdown hang after the guest's own exit is detected and its stacks requested; nothing is left
    running."""

    def run_case(self, **kw):
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "runtime.log"
            p = FakeProcess(clock, log, **kw)
            rec = B.supervise(p, 120, 15, log, clock=clock, sleep=clock.sleep)
        return rec, p.sent

    def test_a_normal_exit_sends_nothing(self):
        rec, sent = self.run_case(exit_at=30)
        self.assertEqual((rec["exit"], rec["timed_out"], rec["exit_hang"], sent), (0, False, False, []))

    def test_guest_exit_then_hang_requests_stacks(self):
        rec, sent = self.run_case(guest_exit_at=20, honours=(3,))
        self.assertTrue(rec["exit_hang"] and not rec["timed_out"])
        self.assertEqual((sent, rec["stack_signal"], rec["exit"]), ([3], "SIGQUIT", -3))
        self.assertLess(rec["elapsed_s"], 40)
        self.assertEqual(rec["guest_exit_after_s"], 20.0)

    def test_guest_exit_followed_by_a_prompt_exit_is_not_a_hang(self):
        rec, sent = self.run_case(guest_exit_at=20, exit_at=22)
        self.assertEqual((rec["exit_hang"], sent), (False, []))

    def test_time_limit_honoured_sigterm(self):
        import signal
        rec, sent = self.run_case(honours=(int(signal.SIGTERM),))
        self.assertTrue(rec["timed_out"])
        self.assertEqual(sent, [int(signal.SIGTERM)])
        self.assertNotIn("stack_signal", rec)

    def test_ignored_sigterm_then_unanswered_sigquit_ends_with_sigkill(self):
        import signal
        rec, sent = self.run_case()
        self.assertEqual(sent, [int(signal.SIGTERM), 3, 9])
        self.assertEqual((rec["exit"], rec["signals"]), (-9, ["SIGTERM", "SIGQUIT", "SIGKILL"]))


class LiveCaptureTests(unittest.TestCase):
    """E-371 follow-up: live stacks first (no core file), the core dump only as a fallback, kill only after capture."""

    def run_case(self, capture_ok, core_fallback=True):
        clock = FakeClock()
        seen = []
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "runtime.log"
            p = FakeProcess(clock, log, guest_exit_at=20, honours=(3,))

            def capture(pid):
                seen.append(p.poll() is None)  # still alive while captured
                return {"ok": capture_ok}
            rec = B.supervise(p, 120, 15, log, clock=clock, sleep=clock.sleep, capture=capture,
                              core_fallback=core_fallback)
        return rec, p.sent, seen

    def test_successful_live_capture_needs_no_core_and_kills_after(self):
        rec, sent, seen = self.run_case(True)
        self.assertEqual((seen, sent, rec["signals"]), ([True], [9], ["SIGKILL"]))
        self.assertNotIn("stack_signal", rec)
        self.assertTrue(rec["capture"]["ok"] and rec["exit_hang"])

    def test_failed_live_capture_falls_back_to_a_core_dump(self):
        rec, sent, seen = self.run_case(False)
        self.assertEqual((seen, sent, rec["stack_signal"]), ([True], [3], "SIGQUIT"))

    def test_core_fallback_can_be_disabled(self):
        rec, sent, _ = self.run_case(False, core_fallback=False)
        self.assertEqual((sent, rec["signals"]), ([9], ["SIGKILL"]))

    def test_gdb_output_parsing(self):
        good = "Thread 2 (Thread 0x7f LWP 12 \"XThread\"):\n#0  0x1 in futex_wait ()\nThread 1 (Thread 0x7e LWP 11):\n#0  0x2 in main ()\n"
        self.assertEqual(B.gdb_thread_count(good), 2)
        self.assertEqual(B.gdb_thread_count("ptrace: Operation not permitted.\n"), 0)

    @unittest.skipUnless(sys.platform.startswith("linux"), "needs Linux")
    def test_allow_ptrace_survives_exec_for_a_non_ancestor(self):
        """A sibling process (like gdb -p) may attach only when the game process opted in before exec."""
        import subprocess
        attacher = ("import ctypes,os,sys\nlibc=ctypes.CDLL(None,use_errno=True)\npid=int(sys.argv[1])\n"
                    "r=libc.ptrace(16,pid,None,None)\nif r==0:\n os.waitpid(pid,0)\n libc.ptrace(17,pid,None,None)\n"
                    "print('OK' if r==0 else 'EPERM')\n")
        results = {}
        for label, pre in (("allowed", B.allow_ptrace), ("control", None)):
            target = subprocess.Popen(["sleep", "30"], preexec_fn=pre)
            try:
                results[label] = subprocess.run([sys.executable, "-c", attacher, str(target.pid)], capture_output=True,
                                                text=True).stdout.strip()
                self.assertIsNone(target.poll())
            finally:
                target.kill()
                target.wait()
        self.assertEqual(results["allowed"], "OK")
        scope = Path("/proc/sys/kernel/yama/ptrace_scope")
        if scope.is_file() and scope.read_text().strip() == "1":
            self.assertEqual(results["control"], "EPERM")

    @unittest.skipUnless(sys.platform.startswith("linux") and B.shutil.which("gdb"), "needs Linux and gdb")
    def test_real_live_capture_of_a_sleeping_child(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.Popen(["sleep", "60"], preexec_fn=B.allow_ptrace)
            try:
                rec = B.live_capture(p.pid, Path(d), timeout=60)
                rows = (Path(d) / "proc_threads.txt").read_text().splitlines()
                self.assertEqual(rows[0].split("\t"), ["tid", "comm", "state", "wchan"])
                self.assertEqual(rows[1].split("\t")[1], "sleep")
                self.assertTrue(rec["ok"], rec)
                self.assertIsNone(p.poll())  # gdb detached; the process is still alive
            finally:
                p.kill()
                p.wait()


def lma_tree(root, tamper=False):
    gen = root / "generated/default"
    (root / "src").mkdir(parents=True)
    gen.mkdir(parents=True)
    (gen / "r3hd_recomp.0.cpp").write_text("M4_FRAME(1)\n")
    (root / "src/main.cpp").write_text("int main();\n")
    (root / "m4_generated_test.cpp").write_text("// extracted\n")
    (root / "LMA_PORTABLE_M4.txt").write_text("LM-A\n")
    h = lambda p: B.hashlib.sha256(p.read_bytes()).hexdigest()
    m = {"format": "R3HD_LMA_TREE_V1", "codegen": {"files": 247, "digest": "0c2d"},
         "generated_sha256": {"r3hd_recomp.0.cpp": h(gen / "r3hd_recomp.0.cpp")},
         "src_sha256": {"main.cpp": h(root / "src/main.cpp")},
         "m4_generated_test_sha256": h(root / "m4_generated_test.cpp")}
    (root / "lma_manifest.json").write_text(json.dumps(m))
    if tamper:
        (gen / "r3hd_recomp.0.cpp").write_text("M4_FRAME(2)\n")


class LmaTreeTests(unittest.TestCase):
    """LM-A: the production tree on the portable backend is a second marked kind with its own gates."""

    def test_kinds_and_verification(self):
        with tempfile.TemporaryDirectory() as d:
            lma_tree(Path(d))
            self.assertEqual(B.tree_kind(Path(d))[0], "lma")
            self.assertEqual(B.verify_tree(Path(d))["kind"], "lma")
        with tempfile.TemporaryDirectory() as d:
            lma_tree(Path(d), tamper=True)
            with self.assertRaises(B.Fail):
                B.verify_tree(Path(d))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(B.Fail):  # unmarked
                B.tree_kind(Path(d))

    def test_lma_symbol_gates_and_portable_backend(self):
        nm = "\n".join(f"0000 T {s}" for s in B.LMA_REQUIRED_SYMBOLS)
        sym = B.symbol_checks(nm, "lma")
        self.assertEqual((sym["missing"], sym["forbidden"]), ([], []))
        self.assertEqual(B.symbol_checks(nm + "\n0000 T _Z11M4SehFilterP19_EXCEPTION_POINTERS", "lma")["forbidden"],
                         ["_Z11M4SehFilterP19_EXCEPTION_POINTERS"])
        self.assertIn("r3hd_diagnostic_build", B.symbol_checks(nm, "diag")["missing"])
        elf = {"diagnostic_banner": True, "symbols": sym, "portable_m4": True}
        ok = {"configure_exit": 0, "build_exit": 0, "tree": {"kind": "lma"}, "elf": elf}
        self.assertTrue(B.game_passed(ok))
        self.assertFalse(B.game_passed(dict(ok, elf=dict(elf, portable_m4=False))))


class SdkUpdateTests(unittest.TestCase):
    """LM-A: the SDK copy moves from the old to the new chain only through expected states."""

    def setup(self, d, current):
        sdk, delta = Path(d) / "sdk", Path(d) / "delta"
        (sdk / "include/rex").mkdir(parents=True)
        (delta / "files/include/rex").mkdir(parents=True)
        old, new = b"old header\n", b"new header\n"
        if current is not None:
            (sdk / "include/rex/m4_seh.h").write_bytes(current)
        (delta / "files/include/rex/m4_seh.h").write_bytes(new)
        h = lambda b: B.hashlib.sha256(b).hexdigest()
        (delta / "delta.json").write_text(json.dumps({"files": {"include/rex/m4_seh.h": {"old": h(old), "new": h(new)}},
                                                      "chain_old": [1, "aaa"], "chain_new": [2, "bbb"]}))
        (sdk / "out/build/linux-amd64").mkdir(parents=True)
        (sdk / "out/build/linux-amd64/CMakeCache.txt").write_text("")
        return sdk, delta, new

    def run_update(self, sdk, delta, out, digests):
        shell = FakeShell()
        with contextlib.ExitStack() as s, contextlib.redirect_stdout(io.StringIO()):
            s.enter_context(mock.patch.object(B, "SDK", sdk))
            s.enter_context(mock.patch.object(B, "ROOT", sdk.parent))
            s.enter_context(mock.patch.object(B, "git", lambda *a, **k: B.SDK_PIN))
            s.enter_context(mock.patch.object(B.platform, "system", lambda: "Linux"))
            s.enter_context(mock.patch.object(B.platform, "machine", lambda: "x86_64"))
            s.enter_context(mock.patch.object(B, "chain_digest", mock.Mock(side_effect=digests)))
            s.enter_context(mock.patch.object(B, "sh", shell))
            s.enter_context(mock.patch.object(B, "sdk_targets", lambda: ["rexglue"]))
            rc = B.sdkupdate(argparse.Namespace(out=out, delta=delta, jobs=2))
        return rc, json.loads((out / "results-sdkupdate.json").read_text())

    def test_old_state_is_updated_and_verified(self):
        with tempfile.TemporaryDirectory() as d:
            sdk, delta, new = self.setup(d, b"old header\n")
            rc, r = self.run_update(sdk, delta, Path(d) / "out", [(1, "aaa"), (2, "bbb")])
            self.assertEqual((rc, r["status"]), (0, "PASS"))
            self.assertEqual((sdk / "include/rex/m4_seh.h").read_bytes(), new)
            self.assertTrue(r["files"]["include/rex/m4_seh.h"]["written"])

    def test_unexpected_content_is_refused_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            sdk, delta, _ = self.setup(d, b"hand edited\n")
            rc, r = self.run_update(sdk, delta, Path(d) / "out", [(1, "aaa"), (2, "bbb")])
            self.assertEqual(r["status"], "FAIL")
            self.assertEqual((sdk / "include/rex/m4_seh.h").read_bytes(), b"hand edited\n")

    def test_unknown_chain_state_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            sdk, delta, _ = self.setup(d, b"old header\n")
            rc, r = self.run_update(sdk, delta, Path(d) / "out", [(9, "zzz")])
            self.assertEqual(r["status"], "FAIL")
            self.assertEqual((sdk / "include/rex/m4_seh.h").read_bytes(), b"old header\n")


class PatchChainTests(unittest.TestCase):
    def test_patch_chain_order(self):
        steps = B.patch_chain()
        self.assertEqual((len(steps), steps[0], steps[-1]), (38, "m2_runtime_patch.py", "r3hd_xex_case_patch.py"))  # LX-6 (E-377) last


if __name__ == "__main__":
    unittest.main()

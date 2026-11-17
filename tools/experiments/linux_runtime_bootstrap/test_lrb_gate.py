"""Synthetic-record tests for the LRB gate validators (any platform).

These exercise the wire contract and rejection logic only. They are not
evidence of native signal delivery, which needs the CachyOS gate run.
"""
import copy
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

import lrb_gate as g

# Fake child for runner tests: behaviour chosen by FAKE_BEHAVIOR. It never
# touches /dev/shm; it only writes (or omits) the ownership record.
FAKE_CHILD = textwrap.dedent('''
    import json, os, sys
    behavior = os.environ["FAKE_BEHAVIOR"]
    path = os.environ["LRB_OWNERSHIP_FILE"]
    def record(**changes):
        own = {"format": "LRB_OWNERSHIP_V1", "stage": "started", "mode": sys.argv[1], "pid": os.getpid(),
               "policy": "sdk-contract", "shm_name": "/xenia_memory_987654321", "device": 1, "inode": 2,
               "apparent_size": 0x120001000, "allocated_bytes": 4096, "unlinked_early": False,
               "virtual_membase": 1 << 32, "vm_size_kib_before": 1000, "vm_size_kib_after": 4720000,
               "vm_rss_kib_before": 3000, "vm_rss_kib_after": 3100}
        own.update(changes)
        with open(path, "w") as f:
            json.dump(own, f)
    if behavior == "early-fail":   # like a require() failure inside Bootstrap::start
        sys.stderr.write("LRB FAIL: guest view range [2^32, 2^32+0x120000000) unmapped before Initialize\\n")
        sys.exit(2)
    if behavior == "garbage":
        open(path, "w").write("{not json")
        sys.exit(2)
    if behavior == "wrong-pid":
        record(pid=1)
        sys.exit(0)
    if behavior == "initialized-then-fail":
        record(stage="initialized")
        sys.stderr.write("LRB FAIL: views placed at the first probed base 2^32\\n")
        sys.exit(2)
    if behavior == "echo-log":
        sys.stderr.write("LOG=" + os.environ.get("LRB_SDK_LOG_CONSOLE", "unset") + "\\n")
        sys.exit(3)
    if behavior == "pass":
        record()
        sys.stdout.buffer.write(b"LRB_MEMORY vm_size_kib_before=1000 vm_size_kib_after=4720000 "
                                b"vm_rss_kib_before=3000 vm_rss_kib_after=3100 shm_apparent=4831842304 "
                                b"shm_allocated=4096\\nLRB PASS checks=207 mode=normal native=1\\n")
        sys.exit(0)
    raise SystemExit("unknown behaviour")
''')

TOKEN = "0123456789abcdef0123456789abcdef"
PID = 4242
ADDR = 0x1A4002000


def line(mode, phase, counters, address=ADDR, token=TOKEN):
    f, c, i, r = counters
    return (f"LRB_GATE_V1 token={token} mode={mode} phase={phase} faults={f} consumed={c} "
            f"invalidations={i} records={r} address=0x{address:x}\n")


def ownership(mode, fatal=True):
    return {"format": "LRB_OWNERSHIP_V1", "stage": "started", "mode": mode, "pid": PID,
            "policy": "unlink-after-map" if fatal else "sdk-contract",
            "shm_name": "/xenia_memory_123456789", "device": 64769, "inode": 77,
            "apparent_size": 0x120001000, "allocated_bytes": 8192, "unlinked_early": fatal,
            "virtual_membase": 1 << 32, "vm_size_kib_before": 1000, "vm_size_kib_after": 4720000,
            "vm_rss_kib_before": 3000, "vm_rss_kib_after": 3100}


def traced(mode):
    phases = g.PHASES[mode]
    full = "".join(line(mode, p, c) for p, c in phases)
    signals = []
    for rows in g.ACCERR_ROWS[mode]:
        signals.append({"signal": 11, "code": 2, "errno": 0, "address": ADDR, "sender_pid": 0,
                        "trace": "".join(line(mode, p, c) for p, c in phases[:rows]), "phases": rows})
    signals.append({"signal": 11, "code": -6, "errno": 0, "address": 0, "sender_pid": PID,
                    "trace": full, "phases": len(phases)})
    return {"mode": mode, "token": TOKEN, "pid": PID, "status": "PASS", "returncode": -11,
            "stdout": "", "stderr": full, "signals": signals, "ownership": ownership(mode),
            "residue": {"present": False, "after": False}}


def normal(checks=300):
    return {"mode": "normal", "pid": PID, "returncode": 0, "stderr": "",
            "stdout": ("LRB_MEMORY vm_size_kib_before=1000 vm_size_kib_after=4720000 vm_rss_kib_before=3000 "
                       "vm_rss_kib_after=3200 shm_apparent=4831842304 shm_allocated=8192\n"
                       f"LRB PASS checks={checks} mode=normal native=1\n"),
            "ownership": ownership("normal", fatal=False), "residue": {"present": False, "after": False}}


def leak():
    return {"mode": "leak-probe", "pid": PID, "returncode": -9, "stdout": "", "stderr": "",
            "ownership": ownership("leak-probe", fatal=False),
            "residue": {"present": True, "inode_match": True, "removed": True, "allocated_bytes": 4096,
                        "after": False}}


class TracedContract(unittest.TestCase):
    def test_all_modes_accept_exact_records(self):
        for mode in g.FATAL:
            g.validate_traced(traced(mode))

    def rejects(self, run):
        with self.assertRaises(g.GateError):
            g.validate_traced(run)

    def test_ordinary_exit_139_is_not_signal_death(self):
        run = traced("callback-failure"); run["returncode"] = 139
        self.rejects(run)

    def test_wrong_token_or_mode(self):
        run = traced("repair-failure")
        run["stderr"] = run["stderr"].replace(TOKEN, "f" * 32)
        run["signals"][-1]["trace"] = run["stderr"]
        self.rejects(run)

    def test_wrong_counters(self):
        run = traced("repair-failure")
        run["stderr"] = run["stderr"].replace("faults=2 consumed=1", "faults=3 consumed=1")
        run["signals"][-1]["trace"] = run["stderr"]
        self.rejects(run)

    def test_missing_phase(self):
        run = traced("declined-unhandled")
        run["stderr"] = "".join(run["stderr"].splitlines(True)[:2])
        run["signals"][-1]["trace"] = run["stderr"]
        self.rejects(run)

    def test_extra_fault_stop(self):
        run = traced("callback-failure")
        run["signals"].insert(1, copy.deepcopy(run["signals"][0]))
        self.rejects(run)

    def test_premature_fault_after_witness(self):
        # A checked fault observed after ordinary witnesses already ran.
        run = traced("callback-failure")
        run["signals"][0]["trace"] = line("callback-failure", "injected", (1, 0, 1, 0))
        run["signals"][0]["phases"] = 1
        self.rejects(run)

    def test_wrong_sender_or_code(self):
        run = traced("unadmitted"); run["signals"][-1]["sender_pid"] = PID + 1
        self.rejects(run)
        run = traced("unadmitted"); run["signals"][-1]["code"] = 0  # SI_USER
        self.rejects(run)

    def test_unrelated_fault_address(self):
        run = traced("repair-failure"); run["signals"][1]["address"] = ADDR + 4
        self.rejects(run)

    def test_output_after_terminal(self):
        run = traced("callback-failure"); run["stderr"] += "late\n"
        self.rejects(run)
        run = traced("callback-failure"); run["stdout"] = "x"
        self.rejects(run)

    def test_unadmitted_must_not_reach_ordinary_terminal(self):
        run = traced("unadmitted")
        extra = line("unadmitted", "terminal", (0, 0, 0, 0))
        run["stderr"] += extra; run["signals"][-1]["trace"] = run["stderr"]
        self.rejects(run)

    def test_residue_left(self):
        run = traced("callback-failure")
        run["residue"] = {"present": True, "inode_match": True, "removed": True, "after": False}
        self.rejects(run)

    def test_policy_mismatch(self):
        run = traced("callback-failure"); run["ownership"]["unlinked_early"] = False
        self.rejects(run)

    def test_ownership_pid_mismatch(self):
        run = traced("callback-failure"); run["ownership"]["pid"] = PID + 1
        self.rejects(run)


class OtherRuns(unittest.TestCase):
    def test_normal_contract(self):
        self.assertEqual(g.validate_normal(normal())["checks"], 300)
        for mutate in (lambda r: r.update(returncode=1), lambda r: r.update(stderr="x"),
                       lambda r: r.update(stdout=r["stdout"] + "x\n"),
                       lambda r: r["residue"].update(present=True)):
            run = normal(); mutate(run)
            with self.assertRaises(g.GateError):
                g.validate_normal(run)

    def test_virtual_reservation_must_be_reported(self):
        run = normal(); run["stdout"] = run["stdout"].replace("vm_size_kib_after=4720000", "vm_size_kib_after=2000")
        with self.assertRaises(g.GateError):
            g.validate_normal(run)

    def test_leak_requires_exact_owned_removal(self):
        g.validate_leak(leak())
        for key, value in (("inode_match", False), ("removed", False), ("after", True)):
            run = leak(); run["residue"][key] = value
            with self.assertRaises(g.GateError):
                g.validate_leak(run)
        run = leak(); run["returncode"] = -11
        with self.assertRaises(g.GateError):
            g.validate_leak(run)

    def test_results_inventory(self):
        result = {"status": "PASS", "repeats": 2, "fatal_repeats": 1, "shm_snapshot": {"foreign_new": []},
                  "configurations": []}
        for cxx, _, opt in g.CONFIGS:
            result["configurations"].append({
                "key": f"{cxx}_O{opt}", "status": "PASS", "normal": [normal(), normal()],
                "traced": [traced(m) for m in g.FATAL], "leak": [leak()]})
        self.assertEqual(g.validate_results(result), 300)
        bad = copy.deepcopy(result); bad["configurations"][2]["normal"][1] = normal(299)
        with self.assertRaises(g.GateError):
            g.validate_results(bad)
        bad = copy.deepcopy(result); bad["configurations"][0]["traced"].pop()
        with self.assertRaises(g.GateError):
            g.validate_results(bad)
        bad = copy.deepcopy(result); bad["shm_snapshot"]["foreign_new"] = ["/xenia_memory_9"]
        with self.assertRaises(g.GateError):
            g.validate_results(bad)


SDK_DIR = Path(__file__).resolve().parents[3] / "external/rexglue-sdk"


@unittest.skipUnless((SDK_DIR / ".git").exists(), "pinned SDK checkout not present")
class PinnedSdkThreadContract(unittest.TestCase):
    """The native thread policy allows exactly one pre-main SDK thread. Tie that
    constant to the pinned source so a pin change cannot silently invalidate it."""

    def pinned(self, name):
        import subprocess
        return subprocess.run(["git", "-C", str(SDK_DIR), "show", f"{g.SDK_PIN}:{name}"],
                              capture_output=True, check=True, timeout=60).stdout.decode()

    def test_timer_queue_global_starts_one_thread_at_load(self):
        source = self.pinned("src/core/timer_queue.cpp")
        self.assertEqual(source.count("\nrex::thread::TimerQueue timer_queue_;"), 1)
        self.assertEqual(source.count("std::jthread([this]"), 1)
        self.assertIn("timer_queue.cpp", self.pinned("src/core/CMakeLists.txt"))
        header = (Path(__file__).resolve().parent / "lrb_bootstrap.h").read_text(encoding="utf-8")
        self.assertIn("inline constexpr size_t kSdkPreMainThreads = 1;", header)

    def test_logging_starts_no_thread_by_default(self):
        logging = self.pinned("src/core/logging.cpp")
        self.assertIn('REXCVAR_DEFINE_INT32(log_flush_interval, 0,', logging)
        self.assertEqual(logging.count("flush_every"), 1)
        self.assertIn("if (flush_interval > 0)", logging)


class RunnerFailurePreservation(unittest.TestCase):
    """Regression for the first CachyOS run: a child that ends before writing
    its ownership record must yield a structured FAIL, never a traceback."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.script = self.out / "fake_child.py"
        self.script.write_text(FAKE_CHILD, encoding="utf-8")
        self.command = [sys.executable, str(self.script)]

    def tearDown(self):
        self.tmp.cleanup()

    def run_fake(self, behavior, tag="t"):
        return g.run_plain(self.command, "normal", self.out, tag, extra_env={"FAKE_BEHAVIOR": behavior})

    def test_missing_record_preserves_child_failure(self):
        run = self.run_fake("early-fail")  # Must not raise (was FileNotFoundError).
        self.assertEqual(run["returncode"], 2)
        self.assertIn("LRB FAIL: guest view range", run["stderr"])
        self.assertIsNone(run["ownership"])
        self.assertIn("missing ownership record", run["ownership_error"])
        self.assertEqual(run["residue"], {"unknown": True})
        self.assertEqual(run["argv"][-1], "normal")
        self.assertEqual(run["env"]["LRB_OWNERSHIP_FILE"], run["ownership_file"])
        with self.assertRaises(g.GateError) as ctx:
            g.checked(run, g.validate_normal)
        message = str(ctx.exception)
        self.assertIn("returncode=2", message)
        self.assertIn("LRB FAIL: guest view range", message)
        self.assertIn("missing ownership record", message)

    def test_missing_record_cannot_pass_ownership_even_with_clean_exit(self):
        run = self.run_fake("early-fail")
        run.update(returncode=0, stderr="", stdout=normal()["stdout"])  # Forge a clean exit.
        with self.assertRaises(g.GateError):
            g.validate_normal(run)

    def test_unreadable_and_foreign_records_fail_without_removal(self):
        for behavior in ("garbage", "wrong-pid"):
            run = self.run_fake(behavior, tag=behavior)
            self.assertTrue(run["ownership_error"], behavior)
            self.assertEqual(run["residue"], {"unknown": True}, behavior)
            with self.assertRaises(g.GateError):
                g.checked(run, g.validate_normal)

    def test_partial_start_record_fails_with_cause(self):
        run = self.run_fake("initialized-then-fail")
        self.assertEqual(run["ownership"]["stage"], "initialized")
        self.assertNotIn("ownership_error", run)
        with self.assertRaises(g.GateError) as ctx:
            g.checked(run, g.validate_normal)
        self.assertIn("views placed at the first probed base", str(ctx.exception))

    def test_complete_record_and_contract_pass(self):
        run = self.run_fake("pass")
        self.assertEqual(g.checked(run, g.validate_normal)["checks"], 207)

    def test_failed_run_fails_whole_result(self):
        failed = self.run_fake("early-fail")
        result = {"status": "PASS", "repeats": 1, "fatal_repeats": 1, "shm_snapshot": {"foreign_new": []},
                  "configurations": [{"key": f"{c}_O{o}", "status": "PASS", "normal": [failed],
                                      "traced": [traced(m) for m in g.FATAL], "leak": [leak()]}
                                     for c, _, o in g.CONFIGS]}
        with self.assertRaises(g.GateError) as ctx:
            g.validate_results(result)
        self.assertIn("returncode=2", str(ctx.exception))

    def test_diagnostic_rerun_enables_sdk_console_log(self):
        os.environ["FAKE_BEHAVIOR"] = "echo-log"
        try:
            run = g.diagnose(self.command, self.out, "cfg")
        finally:
            del os.environ["FAKE_BEHAVIOR"]
        self.assertEqual(run["stderr"].strip(), "LOG=1")
        self.assertEqual(run["returncode"], 3)
        plain = self.run_fake("echo-log", tag="plain")
        self.assertEqual(plain["stderr"].strip(), "LOG=unset")  # Never inherited by normal runs.

    def test_describe_reports_signal_death(self):
        self.assertIn("signal=11", g.describe({"mode": "normal", "pid": 1, "returncode": -11}))

    def test_timeout_is_a_failure(self):
        run = normal(); run["timeout"] = True
        with self.assertRaises(g.GateError):
            g.validate_normal(run)


if __name__ == "__main__":
    unittest.main()

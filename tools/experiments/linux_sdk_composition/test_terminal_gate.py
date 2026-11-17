"""Portable adversarial protocol tests; synthetic records, never Linux execution."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("terminal_gate", Path(__file__).with_name("terminal_gate.py"))
gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
TOKEN = "0123456789abcdef0123456789abcdef"


def trace(mode):
    phases = {"callback-failure": ("injected", "caught", "terminal"),
              "repair-failure": ("claimed", "retry_fault", "terminal"),
              "unhandled": ("filter_search", "caught", "terminal")}[mode]
    lines = []
    for i, phase in enumerate(phases):
        attempts = 2 if mode == "repair-failure" and i else 1
        inv = int(mode == "callback-failure"); filters = int(mode == "unhandled")
        caught = int(mode != "repair-failure" and i > 0)
        lines.append(f"LSC_GATE_V1 token={TOKEN} mode={mode} phase={phase} attempts={attempts} "
            f"faults={attempts} callbacks=1 invalidations={inv} filters={filters} caught={caught} address=0x1000\n")
    return lines


def model(mode):
    lines = trace(mode)
    first = {"signal": 11, "code": 2, "address": 0x1000, "sender_pid": 0, "trace": "", "phases": 0}
    events = [first]
    if mode == "repair-failure": events.append({**first, "trace": lines[0], "phases": 1})
    events.append({"signal": 11, "code": -6, "address": 0, "sender_pid": 123,
                   "trace": "".join(lines), "phases": 3})
    return {"status": "PASS", "mode": mode, "pid": 123, "token": TOKEN, "signals": events,
            "returncode": -11, "stdout": "", "stderr": "".join(lines)}


def matrix_model():
    result = {"status": "PASS", "platform": "Linux-model-only", "machine": "x86_64", "configurations": []}
    counter = 0
    for cxx, cc in (("clang++", "clang"), ("g++", "gcc")):
        for opt in ("O0", "O2"):
            lines = [f"[1/3] /usr/bin/{cc if n != 'sdk_composition.cpp' else cxx} "
                     f"-DLSC_TERMINAL_DIAGNOSTICS -{opt} -Wall -Wextra -Werror -c /src/{n}"
                     for n in ("transport.c", "access.S", "sdk_composition.cpp")]
            row = {"key": cxx + "_" + opt, "status": "PASS", "runs": [],
                   "cxx_version": "clang" if cxx == "clang++" else "GCC",
                   "cc_version": "clang" if cc == "clang" else "GCC",
                   "commands": [{"argv": ["cmake", "--build", "model"], "returncode": 0,
                                 "stderr": "", "stdout": "\n".join(lines)}]}
            row["commands"] = [{"argv": ["/usr/bin/" + cxx, "--version"], "returncode": 0,
                                "stderr": "", "stdout": row["cxx_version"]},
                               {"argv": ["/usr/bin/" + cc, "--version"], "returncode": 0,
                                "stderr": "", "stdout": row["cc_version"]}] + row["commands"]
            for mode in gate.MODES:
                counter += 1; token = f"{counter:032x}"; run = model(mode)
                run["token"] = token; run["stderr"] = run["stderr"].replace(TOKEN, token)
                for event in run["signals"]: event["trace"] = event["trace"].replace(TOKEN, token)
                row["runs"].append(run)
            result["configurations"].append(row)
    return result


class ProtocolTests(unittest.TestCase):
    def rejects(self, record):
        with self.assertRaises(ValueError): gate.validate_run(record)

    def test_three_complete_kernel_sequences(self):
        for mode in gate.MODES: gate.validate_run(model(mode))

    def test_ordinary_exit_139_never_counts(self):
        for mode in gate.MODES:
            r = model(mode); r["returncode"] = 139; self.rejects(r)

    def test_early_or_missing_branch_marker(self):
        for mode in gate.MODES:
            r = model(mode); r["signals"][-1]["trace"] = r["stderr"] = ""; self.rejects(r)

    def test_unexpected_fault_after_terminal_marker(self):
        for mode in gate.MODES:
            r = model(mode); extra = copy.deepcopy(r["signals"][-1])
            extra.update(code=2, address=0x1000, sender_pid=0)
            r["signals"].insert(-1, extra); self.rejects(r)

    def test_wrong_terminal_origin(self):
        for mode in gate.MODES:
            for change in ({"code": 2, "address": 0x1000}, {"code": 0}, {"sender_pid": 124}):
                r = model(mode); r["signals"][-1].update(change); self.rejects(r)

    def test_fault_address_must_match_ordinary_metadata(self):
        r = model("callback-failure"); r["signals"][0]["address"] = 0x2000; self.rejects(r)
        r = model("repair-failure"); r["signals"][1]["address"] = 0x2000; self.rejects(r)

    def test_retry_count_and_phase_order(self):
        r = model("repair-failure")
        text = r["stderr"].replace("attempts=2 faults=2", "attempts=3 faults=3")
        r["stderr"] = r["signals"][-1]["trace"] = text; self.rejects(r)
        r = model("unhandled"); text = r["stderr"].replace("filter_search", "caught")
        r["stderr"] = r["signals"][-1]["trace"] = text; self.rejects(r)

    def test_nonce_extra_output_and_partial_lines(self):
        for mode in gate.MODES:
            r = model(mode); r["token"] = "f" * 32; self.rejects(r)
            r = model(mode); r["stdout"] = "unexpected"; self.rejects(r)
            r = model(mode); r["stderr"] += "extra\n"; self.rejects(r)
            r = model(mode); r["stderr"] = r["stderr"][:-1]; r["signals"][-1]["trace"] = r["stderr"]; self.rejects(r)

    def test_exact_four_by_three_inventory(self):
        gate.validate_results(matrix_model())
        r = matrix_model(); r["configurations"][0]["runs"].pop()
        with self.assertRaises(ValueError): gate.validate_results(r)
        r = matrix_model(); r["configurations"][1]["key"] = r["configurations"][0]["key"]
        with self.assertRaises(ValueError): gate.validate_results(r)

    def test_build_flags_and_scope_cannot_be_weakened(self):
        for before, after in (("-Werror", ""), ("-DLSC_TERMINAL_DIAGNOSTICS", ""), ("-O0", "-O2")):
            r = matrix_model()
            cmd = r["configurations"][0]["commands"][-1]
            cmd["stdout"] = cmd["stdout"].replace(before, after)
            with self.assertRaises(ValueError): gate.validate_results(r)
        r = matrix_model(); r["platform"] = "Windows"
        with self.assertRaises(ValueError): gate.validate_results(r)
        r = matrix_model(); cmd = r["configurations"][0]["commands"][-1]
        cmd["stdout"] = cmd["stdout"].replace("/usr/bin/clang ", "/usr/bin/gcc ")
        with self.assertRaises(ValueError): gate.validate_results(r)


if __name__ == "__main__": unittest.main()

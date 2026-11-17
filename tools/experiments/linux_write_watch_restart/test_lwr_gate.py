"""Validator tests for lwr_gate.py (synthetic records only; no build, no game, no generated code)."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lwr_gate as W  # noqa: E402

G, L = W.G, W.L
W.register_fatal()
TOKEN = "0123456789abcdef0123456789abcdef"
PID = 4242
OWNERSHIP = {"format": "LRB_OWNERSHIP_V1", "stage": "started", "pid": PID, "shm_name": "/xenia_memory_123",
             "virtual_membase": 1 << 32, "apparent_size": 0x120001000, "allocated_bytes": 4096}
RESIDUE = {"present": False, "after": False}


def ownership(fatal):
    return {**OWNERSHIP, "unlinked_early": fatal, "policy": "unlink-after-map" if fatal else "sdk-contract"}


def case_line(case_id):
    fields = {"id": case_id, "fn": "sub_820E7440", "guest": "820e7440", "seed": "1", "input": "a" * 64,
              "before": "r0=0", "after": "r0=1", "nonint": "unchanged", "writable": "20001400-20001404",
              "changed": "4", "delta": "400:0a0a0a0a", "trace": "__imp__sub_820E7440", "model": "pass"}
    body = "LWR_CASE_V1|" + "|".join(f"{k}={fields[k]}" for k in G.CASE_FIELDS[:-1])
    return body + "|digest=" + hashlib.sha256(body.encode()).hexdigest()


def make_reference():
    text = "".join(case_line(W.restart_id(line)) + "\n" for line in W.EXPECTED_RESTART)
    cases = W.parse_cases(text.encode())
    return {"format": "LWR_REFERENCE_V1", "case_count": 8, "cases_text": text, "cases_sha256": W.sha(text.encode()),
            "aggregate": W.aggregate(cases), "checks": 100}


REF = make_reference()
RESTART_TEXT = "".join(f"{line}|digest={W.sha(line.encode())}\n" for line in W.EXPECTED_RESTART)


def claim_line(cid, n, page, fn="__imp__sub_820E7440", width=4, length=3, within=0, effective_offset=0x10, error=7):
    effective = page * 4096 + effective_offset
    return (f"LWR_CLAIM_V1|id={cid}|n={n}|page={page}|fn={fn}|offset=0x1c|width={width}|length={length}|"
            f"address=0x{effective + within:x}|effective=0x{effective:x}|error={error}|before={'00' * width}")


def claims_text(**over):
    lines = []
    for cid, pages in W.EXPECTED_PAGES.items():
        for n, page in enumerate(pages):
            lines.append(claim_line(cid, n, page, **over))
    return "\n".join(lines) + "\n"


CLAIMS = claims_text()


def normal_run(**over):
    run = {"mode": "normal", "pid": PID, "returncode": 0, "stderr": "",
           "stdout": f"LWR PASS cases=8 claims=9 checks=77 aggregate={REF['aggregate']} native=1\n",
           "results_sha256": REF["cases_sha256"], "watched_sha256": REF["cases_sha256"],
           "restart_text": RESTART_TEXT, "claims_text": CLAIMS, "ownership": ownership(False), "residue": dict(RESIDUE)}
    run.update(over)
    return run


class Constants(unittest.TestCase):
    def test_expected_restart_matches_case_claim_counts(self):
        self.assertEqual(W.CASE_CLAIMS, [1, 1, 2, 1, 0, 1, 1, 2])
        self.assertEqual([len(W.restart_pages(line)) for line in W.EXPECTED_RESTART], W.CASE_CLAIMS)
        self.assertEqual(sum(W.CASE_CLAIMS), W.TOTAL_CLAIMS)
        self.assertEqual(len(W.EXPECTED_RESTART), W.CASE_COUNT)

    def test_closure_shape(self):
        for key in W.CONFIG_KEYS:
            self.assertEqual(W.CLOSURE["lrb"][key]["lrb_owner.o"], W.CLOSURE["lge"][key]["lrb_owner.o"])
            for kind in ("lge", "lrb"):
                self.assertTrue(all(len(v) == 64 for v in W.CLOSURE[kind][key].values()))

    def test_fatal_registration_is_idempotent(self):
        W.register_fatal()
        for mode in W.FATAL_LWR:
            self.assertEqual(L.FATAL.count(mode), 1)
        self.assertIn("unadmitted", L.FATAL)

    def test_reference_self_consistent(self):
        self.assertEqual(len(W.check_reference(REF)), 8)
        bad = {**REF, "aggregate": "0" * 64}
        with self.assertRaisesRegex(W.GateError, "aggregate"):
            W.check_reference(bad)
        with self.assertRaisesRegex(W.GateError, "format"):
            W.check_reference({**REF, "format": "X"})


class Packaging(unittest.TestCase):
    def test_source_inventory(self):
        files = W.source_files()
        self.assertEqual(files, sorted(set(files)))
        for name in W.OWN_FILES:
            self.assertIn(W.REL + name, files)
        self.assertIn(G.REL + "lge_tests.cpp", files)
        self.assertIn(G.LRB_REL + "lrb_owner.c", files)
        self.assertFalse([f for f in files if "private" in f or f.endswith(".zip") or "generated.cpp" in f])

    def test_package_entries_lf_and_manifest(self):
        blobs = {"a.txt": b"x\r\ny\r\n", "b.txt": b"z\n"}
        entries = W.package_entries("c" * 40, sorted(blobs), blobs.__getitem__,
                                    lambda n: blobs[n].replace(b"\r\n", b"\n"))
        manifest = json.loads(entries["SOURCE_MANIFEST.json"])
        self.assertEqual(manifest, {"a.txt": W.sha(b"x\ny\n"), "b.txt": W.sha(b"z\n")})
        self.assertEqual(json.loads(entries["IMPLEMENTATION_ID.json"])["commit"], "c" * 40)
        self.assertEqual(entries["a.txt"], b"x\ny\n")

    def test_package_refuses_generated_code_and_dirty_tree(self):
        blobs = {"a.txt": b"x\nDEFINE_REX_FUNC(sub_1) {\n}\n"}
        with self.assertRaisesRegex(W.GateError, "generated code"):
            W.package_entries("c" * 40, ["a.txt"], blobs.__getitem__, blobs.__getitem__)
        with self.assertRaisesRegex(W.GateError, "differs from HEAD"):
            W.package_entries("c" * 40, ["a.txt"], lambda n: b"x\n", lambda n: b"y\n")

    def test_source_manifest_check(self):
        names = W.source_files()
        manifest = {n: "h" for n in names}
        identity = {"commit": "a" * 40}
        W.check_source_manifest(manifest, identity, lambda p: "h")
        with self.assertRaisesRegex(W.GateError, "hash mismatch"):
            W.check_source_manifest(manifest, identity, lambda p: "g")
        with self.assertRaisesRegex(W.GateError, "inventory"):
            W.check_source_manifest({**manifest, "extra": "h"}, identity, lambda p: "h")
        with self.assertRaisesRegex(W.GateError, "commit"):
            W.check_source_manifest(manifest, {"commit": "abc"}, lambda p: "h")

    def test_private_zip_inventory_and_refusal(self):
        entries = W.private_zip_entries(b'{"x": 1}\n')
        self.assertEqual(sorted(entries), ["PRIVATE_MANIFEST.json", "lwr_reference/lwr_windows_reference.json"])
        manifest = json.loads(entries["PRIVATE_MANIFEST.json"])
        self.assertEqual(manifest, {"lwr_reference/lwr_windows_reference.json": W.sha(b'{"x": 1}\n')})
        with self.assertRaisesRegex(W.GateError, "generated code"):
            W.private_zip_entries(b"a\nDEFINE_REX_FUNC(sub_1) {\n")


class RestartAndClaims(unittest.TestCase):
    def test_restart_exact(self):
        W.validate_restart(RESTART_TEXT)
        for bad in (RESTART_TEXT.replace("claimed=4|", "claimed=5|", 1), RESTART_TEXT.replace("|digest=", "|x=", 1),
                    RESTART_TEXT.split("\n", 1)[1], RESTART_TEXT[:-1], RESTART_TEXT.replace("closed", "open", 1)):
            with self.assertRaisesRegex(W.GateError, "restart file"):
                W.validate_restart(bad)

    def test_claims_accepted(self):
        self.assertEqual(len(W.validate_claims(CLAIMS)), 9)

    def test_claims_rejections(self):
        lines = CLAIMS.split("\n")
        cases = {
            "page set": CLAIMS.replace("page=5|", "page=6|", 1).replace("effective=0x5", "effective=0x6", 1)
                              .replace("address=0x5", "address=0x6", 1),
            "line count": "\n".join(lines[:-2]) + "\n",
            "framing": CLAIMS.rstrip("\n"),
            "function": CLAIMS.replace("__imp__sub_820E7440", "__imp__sub_82000000", 1),
            "inside its page": CLAIMS.replace("effective=0x4010", "effective=0x4ffe", 1).replace("address=0x4010", "address=0x4ffe", 1),
            "outside the store": CLAIMS.replace("address=0x4010", "address=0x4014", 1),
            "format": CLAIMS.replace("error=7", "error=5", 1),
        }
        for why, text in cases.items():
            with self.assertRaisesRegex(W.GateError, why if why != "page set" else "claimed page set|one claim"):
                W.validate_claims(text)

    def test_duplicate_page_rejected(self):
        # two-pages case claims 4 and 5; make both claim page 4.
        dup = CLAIMS.replace(claim_line("restart/memset-two-pages", 1, 5), claim_line("restart/memset-two-pages", 1, 4))
        with self.assertRaisesRegex(W.GateError, "one claim per page"):
            W.validate_claims(dup)

    def test_crossing_effective_rejected(self):
        text = claims_text(effective_offset=0xffe)
        with self.assertRaisesRegex(W.GateError, "inside its page"):
            W.validate_claims(text)


class NormalContract(unittest.TestCase):
    def test_accepts_exact_run(self):
        out = W.validate_normal(normal_run(), REF)
        self.assertEqual(out["checks"], 77)

    def test_rejections(self):
        agg = REF["aggregate"]
        for over, why in (
                (dict(stdout=f"LWR PASS cases=8 claims=9 checks=77 aggregate={agg} native=0\n"), "stdout"),
                (dict(stdout=f"LWR PASS cases=8 claims=0 checks=77 aggregate={agg} native=1\n"), "stdout"),
                (dict(stdout=f"LWR PASS cases=8 claims=9 checks=77 aggregate={'1' * 64} native=1\n"), "aggregate"),
                (dict(stderr="x"), "exit/stderr"), (dict(returncode=-11), "exit/stderr"), (dict(timeout=True), "exit/stderr"),
                (dict(results_sha256="0" * 64), "Windows reference"),
                (dict(watched_sha256="0" * 64), "watched"),
                (dict(restart_text=RESTART_TEXT.replace("claimed=4|", "claimed=5|", 1)), "restart"),
                (dict(restart_text=RESTART_TEXT.replace("|digest=", "|digest-", 1)), "restart"),
                (dict(restart_text=RESTART_TEXT.split("\n", 1)[1]), "restart"),
                (dict(claims_text=CLAIMS.replace("__imp__sub_820E7440", "__imp__sub_82000000", 1)), "generated set"),
                (dict(residue={"present": True}), "residue")):
            with self.assertRaisesRegex(W.GateError, why):
                W.validate_normal(normal_run(**over), REF)

    def test_divergence_named(self):
        with self.assertRaisesRegex(W.GateError, "field delta differs"):
            W.validate_normal(normal_run(results_sha256="0" * 64, divergence="case x: field delta differs from the Windows reference"), REF)


def witness(mode, phase, claims, inv, address, token=TOKEN):
    return f"LWR_GATE_V1 token={token} mode={mode} phase={phase} claims={claims} invalidations={inv} address=0x{address:x}\n"


def accerr(address, trace):
    return {"signal": 11, "code": 2, "address": address, "sender_pid": 0, "trace": trace}


def tkill(trace, pid=PID):
    return {"signal": 11, "code": -6, "address": 0, "sender_pid": pid, "trace": trace}


def positive_run():
    witnesses, stops, text = [], [], ""
    index = 0
    for k in W.CASE_CLAIMS:
        for _ in range(k):
            stops.append(accerr(0x7f0000004000 + 0x100 * index, text))
            index += 1
        # all claims of the case are witnessed after the call returns
        for j in range(k):
            text += witness(W.TRACED_POSITIVE, "claim", k, 0, 0x7f0000004000 + 0x100 * (index - k + j))
    return {"mode": W.TRACED_POSITIVE, "token": TOKEN, "pid": PID, "status": "PASS", "returncode": 0, "signals": stops,
            "stdout": f"LWR PASS cases=8 claims=9 checks=77 aggregate={REF['aggregate']} native=1\n",
            "stderr": text, "ownership": ownership(False), "residue": dict(RESIDUE)}


class TracedPositive(unittest.TestCase):
    def test_accepts_exact_interleaving(self):
        self.assertEqual(W.validate_traced_positive(positive_run(), REF), 9)

    def mutate(self, fn):
        run = positive_run()
        fn(run)
        return run

    def test_rejections(self):
        def addr(r): r["signals"][3]["address"] += 8
        def late(r): r["signals"][0]["trace"] = r["stderr"].split("\n", 1)[0] + "\n"  # stop after its own witness
        def extra(r): r["signals"].append(accerr(1, r["stderr"]))
        def code(r): r["signals"][0]["code"] = 1
        def claims(r): r["stderr"] = r["stderr"].replace("claims=2", "claims=1", 1)
        def inv(r): r["stderr"] = r["stderr"].replace("invalidations=0", "invalidations=1", 1)
        def rows(r): r["stderr"] = r["stderr"].split("\n", 1)[1]
        def partial(r): r["signals"][8]["trace"] = r["stderr"][:-5]
        def out(r): r["stdout"] = r["stdout"].replace("native=1", "native=0")
        def rc(r): r["returncode"] = -11
        for fn, why in ((addr, "address mismatch"), (late, "witness lines already written"), (extra, "stop count"),
                        (code, "SEGV_ACCERR"), (claims, "claims differ|trace|witness"), (inv, "witness rows"),
                        (rows, "witness rows|trace"), (partial, "prefix"), (out, "stdout"), (rc, "exit status")):
            with self.assertRaisesRegex(W.GateError, why, msg=fn.__name__):
                W.validate_traced_positive(self.mutate(fn), REF)

    def test_stop_before_earlier_witness_is_rejected(self):
        run = positive_run()
        run["signals"][2]["trace"] = ""  # claim 2 (case 2) faulted with fewer lines than the cases before it wrote
        with self.assertRaisesRegex(W.GateError, "witness lines already written"):
            W.validate_traced_positive(run, REF)


def fatal_run(mode, **over):
    a = 0x7f0000004040
    if mode == "lwr-signal-origin":
        trace = witness(mode, "begin", 0, 0, 0)
        stops, stderr = [tkill(trace), tkill(trace)], trace
    elif mode == "lwr-consumed":
        t1 = witness(mode, "begin", 0, 0, a)
        t3 = t1 + witness(mode, "claimed", 1, 0, a) + witness(mode, "rewatched", 1, 1, a)
        stops, stderr = [accerr(a, t1), accerr(a, t3), tkill(t3)], t3
    else:
        trace = witness(mode, "begin", 0, 0, a)
        stops, stderr = [accerr(a, trace), tkill(trace)], trace
    run = {"mode": mode, "token": TOKEN, "pid": PID, "status": "PASS", "returncode": -11, "stdout": "",
           "stderr": stderr, "signals": stops, "ownership": ownership(True), "residue": dict(RESIDUE)}
    run.update(over)
    return run


class TracedFatal(unittest.TestCase):
    def test_all_modes_accepted(self):
        for mode in W.FATAL_LWR:
            self.assertGreaterEqual(W.validate_traced_fatal(fatal_run(mode)), 2, mode)

    def test_missing_terminal_tkill(self):
        for mode in W.FATAL_LWR:
            run = fatal_run(mode)
            run["signals"] = run["signals"][:-1]
            with self.assertRaisesRegex(W.GateError, "sequence length", msg=mode):
                W.validate_traced_fatal(run)

    def test_foreign_sender_pid(self):
        for mode in W.FATAL_LWR:
            run = fatal_run(mode)
            run["signals"][-1]["sender_pid"] = PID + 1
            with self.assertRaisesRegex(W.GateError, "SI_TKILL", msg=mode):
                W.validate_traced_fatal(run)

    def test_extra_accerr(self):
        for mode in ("lwr-unregistered", "lwr-consumed", "lwr-signal-origin"):
            run = fatal_run(mode)
            run["signals"].insert(0, accerr(0x7f0000004040, run["signals"][0]["trace"]))
            with self.assertRaises(W.GateError, msg=mode):
                W.validate_traced_fatal(run)

    def test_wrong_fault_address(self):
        run = fatal_run("lwr-read")
        run["signals"][0]["address"] += 4
        with self.assertRaisesRegex(W.GateError, "address mismatch"):
            W.validate_traced_fatal(run)

    def test_consumed_witness_order_and_counters(self):
        a = 0x7f0000004040
        base = fatal_run("lwr-consumed")
        swapped = base["stderr"].replace("phase=claimed", "phase=TMP").replace("phase=rewatched", "phase=claimed") \
            .replace("phase=TMP", "phase=rewatched")
        for text, why in ((swapped, "witness phase"),
                          (base["stderr"].replace("claims=1 invalidations=1", "claims=1 invalidations=0"), "witness phase"),
                          (base["stderr"].replace("claims=1 invalidations=0", "claims=0 invalidations=0", 1), "witness phase")):
            run = fatal_run("lwr-consumed", stderr=text)
            run["signals"] = [accerr(a, text.split("phase=claimed")[0].rsplit("LWR_GATE_V1", 1)[0] if False else
                                     witness("lwr-consumed", "begin", 0, 0, a)), accerr(a, text), tkill(text)]
            with self.assertRaisesRegex(W.GateError, why):
                W.validate_traced_fatal(run)

    def test_default_mode_rejects_extra_rows_and_zero_address(self):
        a = 0x7f0000004040
        text = witness("lwr-wide", "begin", 0, 0, a) + witness("lwr-wide", "begin", 0, 0, a)
        run = fatal_run("lwr-wide", stderr=text, signals=[accerr(a, text), tkill(text)])
        with self.assertRaisesRegex(W.GateError, "witness phase"):
            W.validate_traced_fatal(run)
        zero = witness("lwr-wide", "begin", 0, 0, 0)
        with self.assertRaisesRegex(W.GateError, "witness address"):
            W.validate_traced_fatal(fatal_run("lwr-wide", stderr=zero, signals=[accerr(0, zero), tkill(zero)]))

    def test_signal_origin_zero_address_and_two_tkills(self):
        run = fatal_run("lwr-signal-origin")
        self.assertEqual([s["code"] for s in run["signals"]], [-6, -6])
        run["signals"][0] = accerr(0, run["signals"][0]["trace"])
        with self.assertRaisesRegex(W.GateError, "SI_TKILL"):
            W.validate_traced_fatal(run)

    def test_ownership_policy_enforced(self):
        run = fatal_run("lwr-after-release", ownership=ownership(False))
        with self.assertRaisesRegex(W.GateError, "shm policy"):
            W.validate_traced_fatal(run)

    def test_stdout_status_and_token(self):
        with self.assertRaisesRegex(W.GateError, "SIGSEGV death"):
            W.validate_traced_fatal(fatal_run("lwr-read", stdout="x"))
        with self.assertRaisesRegex(W.GateError, "token"):
            W.validate_traced_fatal(fatal_run("lwr-read", token="f" * 32))
        with self.assertRaisesRegex(W.GateError, "failed traced"):
            W.validate_traced_fatal(fatal_run("lwr-read", status="FAIL"))


def probe_run(mode, **over):
    a = 0x7ffff7ff0020
    begin = f"LWR_PROBE begin mode={mode} address=0x{a:x}\n"
    if mode == "signal-origin":
        stops = [tkill(begin), tkill(begin)]
    elif mode == "consumed":
        stops = [accerr(a, ""), accerr(a, begin), tkill(begin)]
    else:
        stops = [accerr(a, begin), tkill(begin)]
    run = {"mode": mode, "pid": PID, "status": "PASS", "returncode": -11, "stdout": "", "stderr": begin, "signals": stops}
    run.update(over)
    return run


class ProbeContract(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(W.validate_probe_positive({"returncode": 0, "stderr": "", "stdout": "LWR_PROBE PASS claims=2 checks=31\n"}), 31)
        for bad in ({"returncode": 1, "stderr": "", "stdout": "LWR_PROBE PASS claims=2 checks=31\n"},
                    {"returncode": 0, "stderr": "x", "stdout": "LWR_PROBE PASS claims=2 checks=31\n"},
                    {"returncode": 0, "stderr": "", "stdout": "LWR_PROBE PASS claims=3 checks=31\n"}):
            with self.assertRaises(W.GateError):
                W.validate_probe_positive(bad)

    def test_negative_modes_accepted(self):
        for mode in W.PROBE_NEGATIVE:
            W.validate_probe_negative(probe_run(mode))

    def test_negative_rejections(self):
        with self.assertRaisesRegex(W.GateError, "SIGSEGV"):
            W.validate_probe_negative(probe_run("read", returncode=3))
        with self.assertRaisesRegex(W.GateError, "begin line"):
            W.validate_probe_negative(probe_run("read", stderr="LWR_PROBE begin mode=wide address=0x10\n"))
        run = probe_run("read")
        run["signals"][0]["address"] += 1
        with self.assertRaisesRegex(W.GateError, "address mismatch"):
            W.validate_probe_negative(run)
        run = probe_run("read")
        run["signals"][0]["trace"] = ""  # begin line not yet written at the first stop
        with self.assertRaisesRegex(W.GateError, "begin line position"):
            W.validate_probe_negative(run)
        run = probe_run("wide")
        run["signals"][1]["sender_pid"] = 1
        with self.assertRaisesRegex(W.GateError, "SI_TKILL"):
            W.validate_probe_negative(run)
        run = probe_run("host-store")
        run["signals"].append(tkill(run["stderr"]))
        with self.assertRaisesRegex(W.GateError, "sequence length"):
            W.validate_probe_negative(run)


def wide(address, label, insns):
    out = [f"{address:016x} <{label}>:"]
    for i, (raw, text, reloc) in enumerate(insns):
        line = f"  {address + 4 * i:x}:\t{raw:<22}\t{text}"
        if reloc:
            line += f"\t{address + 4 * i + 1:x}: {reloc[0]}\t{reloc[1]}"
        out.append(line)
    return "\n".join(out) + "\n"


ADMIT_OK = [("55", "push   %rbp", None), ("64 48 8b 04 25 00 00 00 00", "mov    %fs:0x0,%rax", ("R_X86_64_TPOFF32", "s-0x4")),
            ("48 8b 05 00 00 00 00", "mov    0x0(%rip),%rax        # 14 <x+0x14>", ("R_X86_64_GOTTPOFF", "s-0x4")),
            ("75 02", "jne    20 <lwr_restart_admit+0x20>", None), ("0f 05", "syscall", None), ("c3", "ret", None)]


def restart_dump(admit=ADMIT_OK, extra=""):
    return ("\nDisassembly of section .text:\n\n" + wide(0, "lwr_restart_admit", admit) +
            wide(0x100, "lwr_open", [("55", "push   %rbp", None), ("c3", "ret", None)]) + extra)


class ObjectChecks(unittest.TestCase):
    def test_accepts_clean_function(self):
        facts = W.check_restart_object(restart_dump())
        self.assertEqual(facts["syscalls"], 1)
        self.assertEqual({r[0] for r in facts["relocations"]}, {"R_X86_64_TPOFF32", "R_X86_64_GOTTPOFF"})

    def test_rejections(self):
        base = ADMIT_OK[:]
        cases = [
            ("call outside", base + [("e8 00 00 00 00", "call   9 <lwr_restart_admit+0x9>", ("R_X86_64_PLT32", "sigaction-0x4"))], "outside itself|relocation"),
            ("call external", base + [("e8 00 00 00 00", "call   200 <lwr_open>", None)], "outside itself"),
            ("indirect jump", base + [("ff e0", "jmp    *%rax", None)], "outside itself"),
            ("xmm", base + [("0f 28 c1", "movaps %xmm1,%xmm0", None)], "vector or x87"),
            ("x87", base + [("d9 c0", "fld    %st(0)", None)], "vector or x87"),
            ("plt32 reloc", base + [("48 8d 05 00 00 00 00", "lea    0x0(%rip),%rax", ("R_X86_64_PLT32", "foo-0x4"))], "R_X86_64_PLT32"),
            ("pc32 reloc", base + [("48 8d 05 00 00 00 00", "lea    0x0(%rip),%rax", ("R_X86_64_PC32", ".rodata-0x4"))], "PC32"),
            ("second syscall", base + [("0f 05", "syscall", None)], "exactly one syscall"),
            ("no syscall", base[:4] + base[5:], "exactly one syscall"),
        ]
        for name, insns, why in cases:
            with self.assertRaisesRegex(W.GateError, why, msg=name):
                W.check_restart_object(restart_dump(insns))

    def test_stack_protector_and_tls_resolver_anywhere_in_object(self):
        for symbol in ("__stack_chk_fail", "__tls_get_addr"):
            other = wide(0x200, "lwr_other", [("e8 00 00 00 00", "call   205 <lwr_other+0x5>", ("R_X86_64_PLT32", symbol + "-0x4"))])
            with self.assertRaisesRegex(W.GateError, "references " + symbol, msg=symbol):
                W.check_restart_object(restart_dump(extra=other))
        W.check_restart_object(restart_dump(extra=wide(0x200, "lwr_memset_free", [("c3", "ret", None)])))

    def test_memory_primitive_in_admit_still_rejected(self):
        bad = ADMIT_OK + [("e8 00 00 00 00", "call   9 <lwr_restart_admit+0x9>", ("R_X86_64_PLT32", "memcpy-0x4"))]
        with self.assertRaisesRegex(W.GateError, "outside itself|relocation"):
            W.check_restart_object(restart_dump(bad))


FIXTURES = Path(__file__).resolve().parent / "fixtures"
# Exact native failure 1 evidence (lwr-native-failure.zip c533325a…6d97, implementation a4b60e7):
# EVIDENCE_MANIFEST digests of native/clang++_O2/{restart,owner}.objdump.txt.
FAILURE1 = {"restart": ("native_failure1_clang_O2_restart.objdump.txt",
                        "131dab2a42d9b1fa395bfba9309bcf64896325b338123038b4bee3dd0ccafff0"),
            "owner": ("native_failure1_clang_O2_owner.objdump.txt",
                      "a548f95cd2cd6373b8fdb67e1029727d0d936ec4a1bedf954c652d2387817175")}
# G6-P36 (D-292): the public source export carries these fixtures as declared redacted copies
# (config/release/public_redactions.json): line 2's account segment of /home/<account>/ is "<user>", nothing else.
# Only that exact copy is accepted besides the evidence bytes above.
FAILURE1_PUBLIC = {"restart": "176e81a7910b071d3af581ed7a7a32e96717bc77357831997a9bfe34d223718c",
                   "owner": "3be880a6f6f7a6102df71c338bd4e219de3feb8cae940d7d00ff0328f1f97766"}


def failure1(kind):
    name, digest = FAILURE1[kind]
    data = (FIXTURES / name).read_bytes().replace(b"\r\n", b"\n")
    got = hashlib.sha256(data).hexdigest()
    assert got == digest or (got == FAILURE1_PUBLIC[kind] and data.split(b"\n")[1].startswith(b"/home/<user>/")), \
        name + " differs from the native evidence"
    return data.decode()


class NativeFailure1(unittest.TestCase):
    """Clang 22 -O2 lowered lwr_authorize's ordinary-code range copy loop to `call memcpy`."""

    def test_old_object_wide_rule_is_what_failed(self):
        text = failure1("restart")
        self.assertIsNotNone(re.search(r"call\s+\S+ <lwr_authorize\+0x[0-9a-f]+>\s+[0-9a-f]+: R_X86_64_PLT32\s+memcpy-0x4",
                                       text))
        self.assertEqual(re.findall(r"R_X86_64_\w+\s+(mem\w+)", text), ["memcpy"])

    def test_admit_function_contract_holds(self):
        facts = W.check_restart_object(failure1("restart"))
        self.assertEqual(facts["syscalls"], 1)
        self.assertTrue(all(kind in W.TLS_RELOCS for kind, _ in facts["relocations"]))

    def test_signal_closure_separates_memcpy(self):
        facts = W.check_signal_closure(failure1("owner"), failure1("restart"))
        self.assertEqual(facts["reachable"], ["handler", "lwr_restart_admit"])
        self.assertEqual(facts["externals"], ["_Exit", "__stack_chk_fail", "raise", "sigaction", "sigprocmask"])
        self.assertEqual(facts["unreachable_memory_calls"], [["lwr_authorize", "memcpy"]])

    def test_closure_rejects_memcpy_if_reachable(self):
        owner = failure1("owner")
        # Re-target one audited handler call (raise) at lwr_authorize: its memcpy becomes reachable.
        mutated = re.sub(r"R_X86_64_PLT32\s+raise-0x4", "R_X86_64_PLT32\tlwr_authorize-0x4", owner, count=1)
        self.assertNotEqual(mutated, owner)
        with self.assertRaisesRegex(W.GateError, r"outside the audited set: memcpy"):
            W.check_signal_closure(mutated, failure1("restart"))

    def test_closure_rejects_call_in_admit_and_unaudited_external(self):
        restart, owner = failure1("restart"), failure1("owner")
        first_ret = re.search(r"^(\s*)([0-9a-f]+):\t(c3)\s*\tret\s*$", restart.split("<lwr_open>:")[0], re.M)
        self.assertIsNotNone(first_ret)
        injected = restart.replace(first_ret.group(0), first_ret.group(1) + first_ret.group(2) +
                                   ":\te8 00 00 00 00       \tcall   0 <lwr_restart_admit>\t0: R_X86_64_PLT32\tmemset-0x4", 1)
        with self.assertRaisesRegex(W.GateError, r"lwr_restart_admit calls \['memset'\]"):
            W.check_signal_closure(owner, injected)
        extra = re.sub(r"R_X86_64_PLT32\s+raise-0x4", "R_X86_64_PLT32\tprintf-0x4", owner, count=1)
        with self.assertRaisesRegex(W.GateError, "printf"):
            W.check_signal_closure(extra, restart)

    def test_closure_requires_handler_and_admit(self):
        with self.assertRaisesRegex(W.GateError, "handler not found"):
            W.check_signal_closure(failure1("owner").replace("<handler>:", "<other_handler>:"), failure1("restart"))
        unhooked = re.sub(r"R_X86_64_PLT32\s+lwr_restart_admit-0x4", "R_X86_64_PLT32\traise-0x4", failure1("owner"))
        with self.assertRaisesRegex(W.GateError, "not reachable from the signal handler"):
            W.check_signal_closure(unhooked, failure1("restart"))


ADMIT_CLEAN = [("0f 05", "syscall", None), ("c3", "ret", None)]


def owner_dump(handler, extra=""):
    return wide(0, "handler", handler) + extra


CALL_ADMIT = ("e8 00 00 00 00", "call   5 <handler+0x5>", ("R_X86_64_PLT32", "lwr_restart_admit-0x4"))


class SignalClosureShapes(unittest.TestCase):
    """Control-transfer forms the closure must follow (review of the failure-1 correction)."""

    def check(self, handler, extra="", restart_extra=""):
        return W.check_signal_closure(owner_dump(handler, extra), wide(0x400, "lwr_restart_admit", ADMIT_CLEAN) + restart_extra)

    def test_minimal_ok(self):
        facts = self.check([CALL_ADMIT, ("c3", "ret", None)])
        self.assertEqual(facts["reachable"], ["handler", "lwr_restart_admit"])

    def test_indirect_call_rejected(self):
        for text in ("call   *%rax", "callq  *0x8(%rax)", "jmp    *%rax", "jmpq   *%rdx"):
            with self.assertRaisesRegex(W.GateError, "indirect", msg=text):
                self.check([CALL_ADMIT, ("ff d0", text, None)])

    def test_jmpq_tail_call_external_rejected(self):
        with self.assertRaisesRegex(W.GateError, "outside the audited set: memcpy"):
            self.check([CALL_ADMIT, ("e9 00 00 00 00", "jmpq   a <handler+0xa>", ("R_X86_64_PLT32", "memcpy-0x4"))])

    def test_conditional_jump_into_cold_block_followed(self):
        cold = wide(0x800, "handler.cold", [("e8 00 00 00 00", "call   805 <handler.cold+0x5>", ("R_X86_64_PLT32", "memcpy-0x4"))])
        with self.assertRaisesRegex(W.GateError, "outside the audited set: memcpy"):
            self.check([CALL_ADMIT, ("0f 85 00 00 00 00", "jne    800 <handler.cold>", None)], cold)

    def test_cold_sibling_reachable_without_parsed_branch(self):
        cold = wide(0x800, "handler.cold", [("e8 00 00 00 00", "call   805 <handler.cold+0x5>", ("R_X86_64_PLT32", "printf-0x4"))])
        with self.assertRaisesRegex(W.GateError, "outside the audited set: printf"):
            self.check([CALL_ADMIT, ("c3", "ret", None)], cold)

    def test_cross_section_branch_fails_closed(self):
        with self.assertRaisesRegex(W.GateError, r"outside the audited set: \.text\.unlikely"):
            self.check([CALL_ADMIT, ("0f 85 00 00 00 00", "jne    0 <handler>", ("R_X86_64_PC32", ".text.unlikely-0x4"))])

    def test_static_callee_followed_and_unreachable_memcpy_allowed(self):
        term = wide(0x200, "terminate_signal", [("e8 00 00 00 00", "call   205 <terminate_signal+0x5>",
                                                  ("R_X86_64_PLT32", "sigaction-0x4"))])
        ordinary = wide(0x300, "lwr_authorize", [("e8 00 00 00 00", "call   305 <lwr_authorize+0x5>",
                                                   ("R_X86_64_PLT32", "memcpy-0x4"))])
        facts = self.check([CALL_ADMIT, ("e8 00 00 00 00", "call   200 <terminate_signal>", None)], term, ordinary)
        self.assertEqual(facts["reachable"], ["handler", "lwr_restart_admit", "terminate_signal"])
        self.assertEqual(facts["unreachable_memory_calls"], [["lwr_authorize", "memcpy"]])

    def test_duplicate_function_across_objects_rejected(self):
        with self.assertRaisesRegex(W.GateError, "defined twice"):
            self.check([CALL_ADMIT], wide(0x900, "lwr_restart_admit", ADMIT_CLEAN))

    def test_missing_function(self):
        with self.assertRaisesRegex(W.GateError, "not found"):
            W.check_restart_object(wide(0, "lwr_open", [("c3", "ret", None)]))

    def test_non_wide_relocation_lines(self):
        text = ("0000000000000000 <lwr_restart_admit>:\n   0:\t0f 05                \tsyscall\n"
                "   2:\te8 00 00 00 00       \tcall   7 <lwr_restart_admit+0x7>\n\t\t\t3: R_X86_64_PLT32\tfoo-0x4\n")
        with self.assertRaisesRegex(W.GateError, "outside itself"):
            W.check_restart_object(text)

    def test_owner_references_admit(self):
        text = wide(0, "terminate_signal", [("e8 00 00 00 00", "call   5 <x+0x5>", ("R_X86_64_PLT32", "lwr_restart_admit-0x4"))])
        self.assertTrue(W.check_owner_calls_admit(text))
        with self.assertRaisesRegex(W.GateError, "no relocation"):
            W.check_owner_calls_admit(text.replace("lwr_restart_admit", "other_function"))

    def test_final_elf_admit_has_no_calls(self):
        self.assertEqual(W.check_final_admit(wide(0x1000, "lwr_restart_admit", ADMIT_OK)), len(ADMIT_OK))
        bad = ADMIT_OK + [("e8 00 00 00 00", "call   1100 <foo>", None)]
        with self.assertRaisesRegex(W.GateError, "call instructions"):
            W.check_final_admit(wide(0x1000, "lwr_restart_admit", bad))
        with self.assertRaisesRegex(W.GateError, "not found"):
            W.check_final_admit(wide(0x1000, "other", ADMIT_OK))

    def test_bind_now(self):
        self.assertTrue(W.check_bind_now(" 0x000000000000001e (FLAGS)  BIND_NOW\n"))
        self.assertTrue(W.check_bind_now(" 0x000000006ffffffb (FLAGS_1)  Flags: NOW PIE\n"))
        with self.assertRaisesRegex(W.GateError, "BIND_NOW"):
            W.check_bind_now(" 0x000000006ffffffb (FLAGS_1)  Flags: PIE\n")

    def test_closure_drift_rejected(self):
        good = W.CLOSURE["lge"]["g++_O2"]["lge_generated.o"]
        W.check_closure("lge", "g++_O2", "lge_generated.o", good, "g++ 15.1\nmore")
        with self.assertRaisesRegex(W.GateError, "lge_generated.o.*expected " + good + " actual " + "0" * 64 + ".*g\\+\\+ 15.1"):
            W.check_closure("lge", "g++_O2", "lge_generated.o", "0" * 64, "g++ 15.1\nmore")
        with self.assertRaisesRegex(W.GateError, "lrb_tests.elf"):
            W.check_closure("lrb", "clang++_O0", "lrb_tests.elf", "1" * 64, None)


SYMBOLS = {"__imp__sub_820E7440": (0x1000, "T")}
INDEX_SRC = "  101c:\t89 14 0f             \tmov    %edx,(%rdi,%rcx,1)\n"


def claim(**over):
    base = {"id": "restart/single-store", "n": 0, "page": 4, "fn": "__imp__sub_820E7440", "offset": 0x1c, "width": 4,
            "length": 3, "address": 0x4010, "effective": 0x4010, "error": 7, "before": "00" * 4}
    base.update(over)
    return base


class ClaimSites(unittest.TestCase):
    def sites(self, text, **over):
        return W.check_claim_sites([claim(**over)], SYMBOLS, W.instruction_index(text))

    def test_accepts_matching_store(self):
        site = self.sites(INDEX_SRC)[0]
        self.assertEqual((site["address"], site["bytes"], site["text"]), (0x101c, "89 14 0f", "mov    %edx,(%rdi,%rcx,1)"))
        self.sites("  101c:\t66 89 07             \tmov    %ax,(%rdi)\n", width=2)
        self.sites("  101c:\t88 07                \tmov    %al,(%rdi)\n", width=1, length=2)
        self.sites("  101c:\t48 89 07             \tmov    %rax,(%rdi)\n", width=8)
        self.sites("  101c:\t40 88 37             \tmov    %sil,(%rdi)\n", width=1)
        self.sites("  101c:\tc7 07 00 00 00 00    \tmovl   $0x0,(%rdi)\n", length=6)

    def test_rejections(self):
        for text, over, why in (
                (INDEX_SRC, dict(width=8), "width"),
                (INDEX_SRC, dict(width=2), "width"),
                (INDEX_SRC, dict(length=4), "length"),
                ("  101c:\t8b 07                \tmov    (%rdi),%eax\n", dict(length=2), "destination is not memory"),
                ("  101c:\t01 07                \tadd    %eax,(%rdi)\n", dict(length=2), "not a mov"),
                ("  101c:\t0f 11 07             \tmovups %xmm0,(%rdi)\n", dict(), "not a mov"),
                ("  1020:\t89 14 0f             \tmov    %edx,(%rdi,%rcx,1)\n", dict(), "no instruction"),
                (INDEX_SRC, dict(fn="__imp__sub_820EB350"), "symbol")):
            with self.assertRaisesRegex(W.GateError, why):
                self.sites(text, **over)

    def test_operand_split_respects_parentheses(self):
        self.assertEqual(W.split_operands("%edx,(%rdi,%rcx,1)"), ["%edx", "(%rdi,%rcx,1)"])


class ResultsShape(unittest.TestCase):
    def test_incomplete_status_rejected(self):
        with self.assertRaisesRegex(W.GateError, "result status"):
            W.validate_results({"status": "INCOMPLETE"}, REF)

    def test_configuration_inventory_rejected(self):
        with self.assertRaisesRegex(W.GateError, "configurations"):
            W.validate_results({"status": "PASS", "configurations": []}, REF)

    def test_regression_drift_names_artifact(self):
        key = "clang++_O0"
        row = {"key": key, "cxx_version": "clang 21.1\n", "executable_sha256": "0" * 64,
               "owner_sha256": W.CLOSURE["lrb"][key]["lrb_owner.o"], "normal": []}
        reg = {"lrb": [copy.deepcopy(row)] + [{**row, "key": k} for k in W.CONFIG_KEYS[1:]], "lge": []}
        reg["lge"] = [{"key": k} for k in W.CONFIG_KEYS]
        with self.assertRaisesRegex(W.GateError, "lrb clang\\+\\+_O0 lrb_tests.elf.*clang 21.1"):
            W.validate_regression(reg, {"aggregate": "a", "cases_sha256": "b"})


if __name__ == "__main__":
    unittest.main()

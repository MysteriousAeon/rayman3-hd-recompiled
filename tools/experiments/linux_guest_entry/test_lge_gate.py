"""Validator tests for lge_gate.py (synthetic records only; no build, no generated code)."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lge_gate as G  # noqa: E402

L = G.L
NAMES = {f["name"] for f in G.selection()["functions"]}


def case_line(case_id="memset/a0/n4", fn="sub_820E7440", delta="400:0a0a0a0a", trace="__imp__sub_820E7440"):
    fields = {"id": case_id, "fn": fn, "guest": "820e7440", "seed": "1", "input": "a" * 64,
              "before": "r0=0", "after": "r0=1", "nonint": "unchanged", "writable": "20001400-20001404",
              "changed": "4", "delta": delta, "trace": trace, "model": "pass"}
    body = "LGE_CASE_V1|" + "|".join(f"{k}={fields[k]}" for k in G.CASE_FIELDS[:-1])
    return body + "|digest=" + hashlib.sha256(body.encode()).hexdigest()


def cases_text(*lines):
    return ("\n".join(lines) + "\n").encode()


class CaseRecords(unittest.TestCase):
    def test_parse_and_compare_exact(self):
        ref = G.parse_cases(cases_text(case_line(), case_line("strstr/x", "sub_820E6D08", "", "__imp__sub_820E6D08")))
        self.assertEqual(G.compare_cases(ref, ref, NAMES), {"sub_820E7440", "sub_820E6D08"})
        self.assertEqual(G.aggregate(ref), G.aggregate(G.parse_cases(cases_text(case_line(), case_line(
            "strstr/x", "sub_820E6D08", "", "__imp__sub_820E6D08")))))

    def test_tampered_field_breaks_digest(self):
        line = case_line().replace("delta=400:0a0a0a0a", "delta=400:0a0a0a0b")
        with self.assertRaisesRegex(G.GateError, "digest recomputes"):
            G.parse_case(line)

    def test_differing_field_is_named(self):
        ref = G.parse_cases(cases_text(case_line()))
        got = G.parse_cases(cases_text(case_line(delta="400:0a0a0a0b")))
        with self.assertRaisesRegex(G.GateError, "field delta differs"):
            G.compare_cases(ref, got, NAMES)

    def test_count_and_framing(self):
        ref = G.parse_cases(cases_text(case_line()))
        with self.assertRaisesRegex(G.GateError, "case count"):
            G.compare_cases(ref, [], NAMES)
        with self.assertRaisesRegex(G.GateError, "framing"):
            G.parse_cases(case_line().encode() + b"\r\n")
        with self.assertRaisesRegex(G.GateError, "unique case ids"):
            G.parse_cases(cases_text(case_line(), case_line()))

    def test_foreign_function_in_trace_rejected(self):
        ref = G.parse_cases(cases_text(case_line(trace="__imp__sub_820E7440,__imp__sub_82000000")))
        with self.assertRaisesRegex(G.GateError, "outside the selection"):
            G.compare_cases(ref, ref, NAMES)

    def test_self_check_failures_rejected(self):
        line = case_line()
        body = line[:line.rindex("|digest=")].replace("model=pass", "model=fail")
        with self.assertRaisesRegex(G.GateError, "self-checks"):
            G.parse_case(body + "|digest=" + hashlib.sha256(body.encode()).hexdigest())


OBJDUMP = """
0000000000000000 <__imp__sub_820E78A0>:
   0:\t55                   \tpush   %rbp
\t\t\t5: R_X86_64_PLT32\t_Z7M2EnterPKcR10PPCContext-0x4
\t\t\t9: R_X86_64_32S\t.rodata.str1.1+0x14
\t\t\te: R_X86_64_PLT32\t_ZN3rex3ppc10CRRegister7compareIiEEvT_S3_RKNS0_11XERRegisterE-0x4
\t\t\t20: R_X86_64_PLT32\tsub_820EB350-0x4
0000000000000000 <_ZN3rex3ppc10CRRegister7compareIiEEvT_S3_RKNS0_11XERRegisterE>:
   0:\t55                   \tpush   %rbp
0000000000000100 <sub_helper_inline>:
\t\t\t105: R_X86_64_PLT32\tmemcpy-0x4
"""
DEFINED = NAMES | {"__imp__" + n for n in NAMES} | set(G.INLINE_HELPERS)
ROTL = "_ZSt4rotlITkSt18__unsigned_integermET_S0_i"
ROTL_ALIAS = "_ZSt4rotlImET_S0_i"
ROTL_IMPL = "_ZSt6__rotlImET_S0_i"


def objdump(extra=""):
    blocks = [f"0000000000000{i:03x} <__imp__{n}>:\n\t\t\t5: R_X86_64_PLT32\t_Z7M2EnterPKcR10PPCContext-0x4\n"
              for i, n in enumerate(sorted(NAMES - {"sub_820E78A0"}))]
    return OBJDUMP + "".join(blocks) + extra


class BodyReferences(unittest.TestCase):
    def test_admitted_targets_pass_and_header_code_is_ignored(self):
        refs = G.check_body_references(G.body_references(objdump(), NAMES), NAMES, DEFINED)
        self.assertIn("sub_820EB350", refs["sub_820E78A0"])
        self.assertNotIn("memcpy", {t for v in refs.values() for t in v})

    def test_unselected_callee_rejected(self):
        bad = objdump("0000000000000900 <__imp__sub_820E7440>:\n\t\t\t5: R_X86_64_PLT32\tsub_82000000-0x4\n")
        with self.assertRaisesRegex(G.GateError, "outside the selected set"):
            G.check_body_references(G.body_references(bad, NAMES), NAMES, DEFINED)

    def test_library_call_from_body_rejected(self):
        bad = objdump("0000000000000900 <__imp__sub_820E7328>:\n\t\t\t5: R_X86_64_PLT32\tmemcpy-0x4\n")
        with self.assertRaisesRegex(G.GateError, "references memcpy"):
            G.check_body_references(G.body_references(bad, NAMES), NAMES, DEFINED)

    def test_weak_alias_header_maps_to_body(self):
        text = objdump().replace("<__imp__sub_820E7440>:", "<sub_820E7440>:")
        refs = G.check_body_references(G.body_references(text, NAMES), NAMES, DEFINED)
        self.assertIn("_Z7M2EnterPKcR10PPCContext", refs["sub_820E7440"])

    def test_body_without_prologue_rejected(self):
        text = objdump().replace("<__imp__sub_820E7440>:\n\t\t\t5: R_X86_64_PLT32\t_Z7M2EnterPKcR10PPCContext-0x4\n",
                                 "<__imp__sub_820E7440>:\n")
        with self.assertRaisesRegex(G.GateError, "no M2Enter prologue"):
            G.check_body_references(G.body_references(text, NAMES), NAMES, DEFINED)

    def test_missing_body_rejected(self):
        with self.assertRaisesRegex(G.GateError, "every selected function body"):
            G.check_body_references(G.body_references(OBJDUMP, NAMES), NAMES, DEFINED)

    def test_generated_name_pattern(self):
        for s in ("sub_820E7440", "__imp__sub_82000000", "__savegprlr_29", "__imp____restgprlr_14"):
            self.assertTrue(G.GENERATED_NAME.match(s), s)
        for s in ("M2Enter", "_Z7M2EnterPKcR10PPCContext", "subtract"):
            self.assertFalse(G.GENERATED_NAME.match(s), s)


def wide_block(address, label, relocations):
    """One function in the exact GNU objdump -drw layout the native gate records:
    each relocation is appended to its instruction line after a tab."""
    out = [f"{address:016x} <{label}>:", f"    {address:x}:\t55                   \tpush   %rbp"]
    for i, target in enumerate(relocations):
        pc = address + 0x10 + 8 * i
        out.append(f"    {pc:x}:\te8 00 00 00 00       \tcall   {pc + 5:x} <{label}+0x{pc + 5 - address:x}>"
                   f"\t{pc + 1:x}: R_X86_64_PLT32\t{target}-0x4")
    out.append(f"    {address + 0x80:x}:\tc3                   \tret")
    return "\n".join(out) + "\n"


def wide_objdump(overrides=None):
    blocks = ["\nDisassembly of section .text:\n\n"]
    for i, name in enumerate(sorted(NAMES)):
        targets = (overrides or {}).get(name, ["_Z7M2EnterPKcR10PPCContext"])
        blocks.append(wide_block(0x100 * (i + 1), "__imp__" + name, targets))
    return "".join(blocks)


class WideObjdumpFormat(unittest.TestCase):
    """Regression for native attempt 1: the wide format was parsed as having no relocations,
    so every body looked empty (first reported: __restgprlr_29, which sorts first)."""

    def test_inline_relocations_are_parsed_for_every_body(self):
        refs = G.check_body_references(G.body_references(wide_objdump({
            "sub_820F7978": ["_Z7M2EnterPKcR10PPCContext", "__savegprlr_29", "sub_820E78A0", "__restgprlr_29"]}),
            NAMES), NAMES, DEFINED)
        self.assertEqual(refs["__restgprlr_29"], ["_Z7M2EnterPKcR10PPCContext"])
        self.assertEqual(refs["sub_820F7978"], sorted(["_Z7M2EnterPKcR10PPCContext", "__savegprlr_29",
                                                       "sub_820E78A0", "__restgprlr_29"]))
        self.assertTrue(all("_Z7M2EnterPKcR10PPCContext" in v for v in refs.values()))

    def test_inline_foreign_call_rejected(self):
        bad = wide_objdump({"__restgprlr_29": ["_Z7M2EnterPKcR10PPCContext", "sub_82000000"]})
        with self.assertRaisesRegex(G.GateError, "__restgprlr_29 references sub_82000000"):
            G.check_body_references(G.body_references(bad, NAMES), NAMES, DEFINED)

    def test_inline_missing_prologue_still_rejected(self):
        bad = wide_objdump({"__restgprlr_29": []})
        with self.assertRaisesRegex(G.GateError, "__restgprlr_29 body has no M2Enter prologue"):
            G.check_body_references(G.body_references(bad, NAMES), NAMES, DEFINED)

    def test_comment_and_symbolic_operands_are_not_relocations(self):
        line = ("    1e:\t48 8d 35 00 00 00 00 \tlea    0x0(%rip),%rsi        # 25 <x+0x15>\t21: R_X86_64_PC32\t.rodata-0x4")
        self.assertEqual([m.group(1) for m in G.RELOC.finditer(line)], [".rodata"])
        self.assertEqual(list(G.RELOC.finditer("    29:\te8 00 00 00 00       \tcall   2e <sub_82000000+0x1e>")), [])

    @unittest.skipUnless((G.ROOT / "tools/experiments/linux_runtime_bootstrap/lrb-native-evidence.zip").is_file(),
                         "returned LRB evidence absent")
    def test_real_cachyos_objdump_text(self):
        """The same CachyOS binutils output (LRB owner object, no game code)."""
        import zipfile
        with zipfile.ZipFile(G.ROOT / "tools/experiments/linux_runtime_bootstrap/lrb-native-evidence.zip") as z:
            for key in ("clang++_O0", "g++_O2"):
                text = z.read(f"native/{key}/owner.objdump.txt").decode()
                refs = G.body_references(text, {"terminate_signal"})
                self.assertIn("sigaction", refs["terminate_signal"], key)
                self.assertIn("raise", refs["terminate_signal"], key)


def nm_text(skip=(), weak=True, shift=()):
    lines = []
    for i, name in enumerate(sorted(NAMES)):
        address = 0x100 * (i + 1)
        lines.append(f"{address:016x} T __imp__{name}")
        if name not in skip:
            lines.append(f"{address + (0x10 if name in shift else 0):016x} {'W' if weak else 'T'} {name}")
    lines.append("0000000000000000 W _ZNSt6vectorIiSaIiEE9push_backEOi")  # header inline code
    return "\n".join(lines) + "\n"


EVIDENCE2 = G.PRIVATE / "evidence/lge-native-failure.zip"
EVIDENCE3 = G.PRIVATE / "evidence/lge-native-failure-retry2.zip"
LLVM_BIN = Path(r"C:\Program Files\LLVM\bin")


def rotl_objdump(memset_targets=None, helpers=None):
    """GCC O0 shape (native retry 2): memset calls std::rotl<uint64_t>, which calls
    std::__rotl<uint64_t>; both are emitted out of line in the generated object."""
    text = wide_objdump({"sub_820E7440": memset_targets or ["_Z7M2EnterPKcR10PPCContext", ROTL]})
    for i, (label, targets) in enumerate((helpers if helpers is not None else
                                          [(ROTL, [ROTL_IMPL]), (ROTL_IMPL, [])])):
        text += wide_block(0x10000 + 0x100 * i, label, targets)
    return text


class InlineHelperContract(unittest.TestCase):
    """Regression for native retry 2: GCC O0 out-of-line std::rotl (pinned SDK polyfill
    for __builtin_rotateleft64) was rejected as an unknown call target."""

    def test_exact_native_rejection_without_the_helper_contract(self):
        saved = dict(G.INLINE_HELPERS)
        try:
            for name in (ROTL, ROTL_ALIAS, ROTL_IMPL):
                del G.INLINE_HELPERS[name]
            with self.assertRaises(G.GateError) as caught:
                G.check_body_references(G.body_references(rotl_objdump(), NAMES), NAMES, DEFINED)
            self.assertEqual(str(caught.exception), f"sub_820E7440 references {ROTL}, outside the selected set "
                                                    "and admitted helpers")
        finally:
            G.INLINE_HELPERS.clear(); G.INLINE_HELPERS.update(saved)

    def test_locally_defined_closed_helper_chain_accepted(self):
        refs = G.check_body_references(G.body_references(rotl_objdump(), NAMES), NAMES, DEFINED)
        self.assertEqual(refs[ROTL], [ROTL_IMPL])
        self.assertEqual(refs[ROTL_IMPL], [])

    def test_alias_labelled_block_accepted(self):
        text = rotl_objdump(helpers=[(ROTL_ALIAS, [ROTL_IMPL]), (ROTL_IMPL, [])])
        refs = G.check_body_references(G.body_references(text, NAMES), NAMES, DEFINED)
        self.assertEqual(refs[ROTL], [ROTL_IMPL])

    def test_imported_helper_rejected(self):
        with self.assertRaisesRegex(G.GateError, "is not defined in the generated object"):
            G.check_body_references(G.body_references(rotl_objdump(), NAMES), NAMES, DEFINED - {ROTL})

    def test_helper_without_body_rejected(self):
        with self.assertRaisesRegex(G.GateError, "has no disassembled body"):
            G.check_body_references(G.body_references(rotl_objdump(helpers=[(ROTL, [ROTL_IMPL])]), NAMES),
                                    NAMES, DEFINED)

    def test_helper_calling_outside_rejected(self):
        for bad in ("memcpy", "sub_82000000", "_Z7M2EnterPKcR10PPCContext", "__imp__sub_820E7440"):
            text = rotl_objdump(helpers=[(ROTL, [ROTL_IMPL]), (ROTL_IMPL, [bad])])
            with self.assertRaisesRegex(G.GateError, f"inline helper {ROTL_IMPL} references"):
                G.check_body_references(G.body_references(text, NAMES), NAMES, DEFINED)

    def test_unlisted_rotate_width_rejected(self):
        with self.assertRaisesRegex(G.GateError, "outside the selected set"):
            G.check_body_references(G.body_references(rotl_objdump(
                memset_targets=["_Z7M2EnterPKcR10PPCContext", "_ZSt4rotlIjET_S0_i"]), NAMES), NAMES, DEFINED)

    def test_helper_alias_identity_in_final_elf(self):
        used = {ROTL: [ROTL_IMPL]}
        self.assertTrue(G.check_helper_aliases({ROTL: (0xb292, "W"), ROTL_ALIAS: (0xb292, "W")}, used))
        with self.assertRaisesRegex(G.GateError, "share one final-ELF address"):
            G.check_helper_aliases({ROTL: (0xb292, "W"), ROTL_ALIAS: (0xb2a0, "W")}, used)
        with self.assertRaisesRegex(G.GateError, "defined in the final ELF"):
            G.check_helper_aliases({ROTL: (0xb292, "W")}, used)
        self.assertTrue(G.check_helper_aliases({}, {"sub_820E7440": []}))

    def test_readelf_symbol_parse(self):
        text = ("   812: 000000000000b292    34 FUNC    WEAK   DEFAULT   15 _ZSt4rotlImET_S0_i\n"
                "    12: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND sigaction@GLIBC_2.2.5\n")
        self.assertEqual(G.readelf_symbols(text), {ROTL_ALIAS: (0xb292, "W")})

    def test_rotate_shift_precondition(self):
        ok = "a = __builtin_rotateleft64(ctx.r4.u32 | (ctx.r4.u64 << 32), 8) & 0xFF00; b = __builtin_rotateleft64(x, 0);"
        self.assertEqual(G.rotate_shifts(ok), [8, 0])
        for bad, why in (("__builtin_rotateleft32(x, 3)", "64-bit"), ("__builtin_rotateleft64(x, n)", "literal"),
                         ("__builtin_rotateleft64(x, 64)", "literal")):
            with self.assertRaisesRegex(G.GateError, why):
                G.rotate_shifts(bad)

    @unittest.skipUnless(EVIDENCE3.is_file() and (LLVM_BIN / "llvm-objdump.exe").is_file(),
                         "private retry-2 evidence or LLVM tools absent")
    def test_real_gcc_o0_object(self):
        """The returned g++ O0 generated object (private) under the new contract."""
        import subprocess, zipfile
        with zipfile.ZipFile(EVIDENCE3) as z, tempfile.TemporaryDirectory() as d:
            obj, elf = Path(d) / "gen.o", Path(d) / "lge_tests.elf"
            obj.write_bytes(z.read("native/g++_O0/lge_generated.o"))
            elf.write_bytes(z.read("native/g++_O0/lge_tests.elf"))
            run = lambda *a: subprocess.run([str(x) for x in a], capture_output=True, text=True, check=True).stdout
            dump = run(LLVM_BIN / "llvm-objdump.exe", "-dr", obj)
            nm = run(LLVM_BIN / "llvm-nm.exe", "--defined-only", obj)
            elf_nm = G.nm_symbols(run(LLVM_BIN / "llvm-nm.exe", "--defined-only", elf))
        G.check_aliases(nm, NAMES)
        refs = G.check_body_references(G.body_references(dump, NAMES), NAMES, set(G.nm_symbols(nm)))
        self.assertIn(ROTL, refs["sub_820E7440"])
        self.assertEqual(refs[ROTL_IMPL], [])
        G.check_helper_aliases(elf_nm, refs)


class DefineRexFunc(unittest.TestCase):
    """Regression for native retry 1 (attempt 2): GCC 16 rejected the pinned macro's
    attribute placement; an ignored attribute would silently drop the weak alias."""

    def test_alias_contract_accepts_weak_alias_at_same_address(self):
        self.assertTrue(G.check_aliases(nm_text(), NAMES))

    def test_dropped_alias_rejected(self):
        with self.assertRaisesRegex(G.GateError, "sub_820E7440 is a weak definition"):
            G.check_aliases(nm_text(skip={"sub_820E7440"}), NAMES)

    def test_non_weak_or_displaced_alias_rejected(self):
        with self.assertRaisesRegex(G.GateError, "weak definition"):
            G.check_aliases(nm_text(weak=False), NAMES)
        with self.assertRaisesRegex(G.GateError, "same address"):
            G.check_aliases(nm_text(shift={"__restgprlr_29"}), NAMES)

    def test_replacement_macro_is_the_pinned_declaration_with_gcc_placement(self):
        text = (HERE / "lge_define_rex_func.h").read_text(encoding="utf-8")
        macro = text[text.index("#define DEFINE_REX_FUNC(name)"):]
        self.assertIn('extern "C" __attribute__((alias("__imp__" #name), weak, noinline)) REX_FUNC(name);', macro)
        self.assertIn("REX_EXTERN(__imp__##name)", macro)
        self.assertLess(macro.index('extern "C"'), macro.index("__attribute__"))
        self.assertIn(G.REL + "lge_define_rex_func.h", G.source_files())

    @unittest.skipUnless((G.ROOT / "external/rexglue-sdk/.git").exists(), "pinned SDK checkout absent")
    def test_pinned_template_has_the_extension_point_and_same_attributes(self):
        import subprocess
        tpl = subprocess.run(["git", "-C", str(G.ROOT / "external/rexglue-sdk"), "show",
                              L.SDK_PIN + ":resources/templates/codegen/pch_h.inja"],
                             capture_output=True, check=True).stdout.decode()
        self.assertIn("#ifndef DEFINE_REX_FUNC", tpl)
        self.assertIn('__attribute__((alias("__imp__" #name)))', tpl)
        self.assertIn('__attribute__((weak, noinline)) extern "C" REX_FUNC(name);', tpl)

    def test_first_diagnostic_named_on_build_failure(self):
        log = []
        line = "r3hd_pch.h:75:3: error: attributes are not permitted in this position [-Werror=attributes]"
        argv = [sys.executable, "-c", f"print('[5/6] g++ ...'); print({line!r}); raise SystemExit(1)"]
        with self.assertRaisesRegex(G.GateError, "first diagnostic: .*attributes are not permitted"):
            G.build_step(argv, log)
        self.assertEqual(log[-1]["returncode"], 1)

    @unittest.skipUnless(EVIDENCE2.is_file(), "private retry-1 failure evidence absent")
    def test_real_retry1_failure_log(self):
        import zipfile
        with zipfile.ZipFile(EVIDENCE2) as z:
            result = json.loads(z.read("results.json"))
        row = next(r for r in result["configurations"] if r["key"] == "g++_O0")
        failed = row["commands"][-1]
        self.assertEqual(failed["argv"][:2], ["cmake", "--build"])
        self.assertIn("attributes are not permitted in this position", G.first_diagnostic(failed["stdout"]))


def witness(token, mode, address):
    return (f"LRB_GATE_V1 token={token} mode={mode} phase=begin faults=0 consumed=0 invalidations=0 "
            f"records=0 address=0x{address:x}\n")


class FatalContract(unittest.TestCase):
    def setUp(self):
        G.configure_lrb_fatal_contract()
        self.token = "0123456789abcdef0123456789abcdef"

    def test_lrb_modes_unchanged_and_lge_registered(self):
        self.assertEqual(L.PHASES["unadmitted"], [("begin", (0, 0, 0, 0))])
        for mode in G.FATAL:
            self.assertIn(mode, L.FATAL)
            self.assertEqual(L.ACCERR_ROWS[mode], [1])
        self.assertEqual(len(L.FATAL), len(set(L.FATAL)))

    def test_guard_fault_then_tkill_accepted(self):
        for mode in G.FATAL:
            trace = witness(self.token, mode, 0x120011000)
            events = [{"signal": 11, "code": 2, "address": 0x120011000}]
            self.assertEqual(L.check_stop(mode, self.token, events, trace, 42), 1)
            events.append({"signal": 11, "code": -6, "address": 0, "sender_pid": 42})
            self.assertEqual(L.check_stop(mode, self.token, events, trace, 42), 1)

    def test_wrong_address_extra_stop_and_foreign_sender_rejected(self):
        mode, trace = "lge-write-guard", witness(self.token, "lge-write-guard", 0x120011000)
        with self.assertRaises(G.GateError):
            L.check_stop(mode, self.token, [{"signal": 11, "code": 2, "address": 0x120010ffc}], trace, 42)
        with self.assertRaises(G.GateError):
            L.check_stop(mode, self.token, [{"signal": 11, "code": 2, "address": 0x120011000}] * 2, trace, 42)
        with self.assertRaises(G.GateError):
            L.check_stop(mode, self.token, [{"signal": 11, "code": 2, "address": 0x120011000},
                                            {"signal": 11, "code": -6, "address": 0, "sender_pid": 7}], trace, 42)
        with self.assertRaises(G.GateError):  # Fault before the witness was written.
            L.check_stop(mode, self.token, [{"signal": 11, "code": 2, "address": 0x120011000}], "", 42)


def normal_run(**over):
    text = case_line() + "\n"
    run = {"mode": "normal", "pid": 9, "returncode": 0, "stderr": "",
           "stdout": "LGE PASS cases=1 checks=10 aggregate=" + "b" * 64 + " native=1\n",
           "cases_sha256": hashlib.sha256(text.encode()).hexdigest(), "reference_aggregate": "b" * 64,
           "ownership": {"format": "LRB_OWNERSHIP_V1", "stage": "started", "pid": 9,
                         "shm_name": "/xenia_memory_123", "virtual_membase": 1 << 32, "apparent_size": 0x120001000,
                         "allocated_bytes": 4096, "unlinked_early": False, "policy": "sdk-contract"},
           "residue": {"present": False, "after": False}}
    run.update(over)
    return run, text


class NormalContract(unittest.TestCase):
    def test_accepts_exact_run(self):
        run, text = normal_run()
        self.assertEqual(G.validate_normal(run, text), {"cases": 1, "checks": 10})

    def test_rejections(self):
        _, text = normal_run()
        for over, why in ((dict(stdout="LGE PASS cases=1 checks=10 aggregate=" + "b" * 64 + " native=0\n"), "stdout"),
                          (dict(cases_sha256="0" * 64), "Windows reference"),
                          (dict(reference_aggregate="c" * 64), "aggregate"),
                          (dict(stderr="x"), "exit/stderr"), (dict(returncode=-11), "exit/stderr"),
                          (dict(residue={"present": True}), "residue")):
            run, _ = normal_run(**over)
            with self.assertRaisesRegex(G.GateError, why):
                G.validate_normal(run, text)


class Inventories(unittest.TestCase):
    def test_source_inventory_has_no_private_material(self):
        files = G.source_files()
        self.assertIn(G.REL + "lge_tests.cpp", files)
        self.assertIn(G.LRB_REL + "lrb_owner.c", files)
        self.assertFalse([f for f in files if "private" in f or f.endswith(".zip") or "generated.cpp" in f])
        self.assertFalse([f for f in files if f.endswith(("r3hd_pch.h", "windows_reference.json"))])

    def test_selection_is_call_closed(self):
        sel = G.selection()
        self.assertEqual(len(sel["functions"]), 10)
        self.assertEqual(sum(f["entry"] for f in sel["functions"]), 8)

    def test_selection_rejects_open_closure(self):
        data = json.loads(G.SELECTION.read_text(encoding="utf-8"))
        data["functions"][0]["calls"] = ["sub_82000000"]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sel.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            old, G.SELECTION = G.SELECTION, path
            try:
                with self.assertRaisesRegex(G.GateError, "call-closed"):
                    G.selection()
            finally:
                G.SELECTION = old

    def test_private_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "lge_generated.cpp").write_bytes(b"x")
            (d / "r3hd_pch.h").write_bytes(b"y")
            manifest = {"format": "LGE_GENERATED_V1", "selection_sha256_lf": L.sha(L.lf(G.SELECTION)),
                        "files": {"lge_generated.cpp": L.sha(b"x"), "r3hd_pch.h": L.sha(b"y")},
                        "functions": [{"name": f["name"]} for f in G.selection()["functions"]]}
            (d / "GENERATED_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
            G.private_identity(d, need_reference=False)
            (d / "r3hd_recomp.7.cpp").write_bytes(b"z")
            with self.assertRaisesRegex(G.GateError, "inventory"):
                G.private_identity(d, need_reference=False)
            (d / "r3hd_recomp.7.cpp").unlink()
            (d / "r3hd_pch.h").write_bytes(b"changed")
            with self.assertRaisesRegex(G.GateError, "digest"):
                G.private_identity(d, need_reference=False)


@unittest.skipUnless((G.PRIVATE / "private_generated/windows_reference.json").is_file(), "private reference absent")
class PrivateReference(unittest.TestCase):
    def test_reference_self_consistent(self):
        _, reference = G.private_identity(G.PRIVATE / "private_generated")
        cases = G.parse_cases(reference["cases_text"].encode())
        self.assertEqual(G.compare_cases(cases, cases, NAMES), set(reference["functions_exercised"]))
        self.assertEqual(len(reference["functions_exercised"]), 8)


if __name__ == "__main__":
    unittest.main(verbosity=1)

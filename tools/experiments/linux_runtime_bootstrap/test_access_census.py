import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import access_census as ac  # noqa: E402

SENTINEL_FUNC = "sub_8ABCDEF0"
SENTINEL_CONST = "0x5A5A1234"

SYNTH_CPP = f"""#include "x.h"

DEFINE_REX_FUNC({SENTINEL_FUNC}) {{
\tREX_FUNC_PROLOGUE();
\t// lwz r3,0(r4)
\tctx.r3.u64 = REX_LOAD_U32(ctx.r4.u32 + 0);
\t// stw r3,4(r4)
\tREX_STORE_U32(ctx.r4.u32 + 4, ctx.r3.u32);
\t// lbz r5,0(r4)
\tctx.r5.u64 = REX_LOAD_U8(ctx.r4.u32 + {SENTINEL_CONST});
\tREX_STORE_U64(ctx.r4.u32 + ctx.r6.u32, ctx.r3.u64);
\t// lvx128 v63,r0,r4
\tea = (ctx.r4.u32) & ~0xF;
\tsimde_mm_store_si128((simde__m128i*)ctx.v63.u8, simde_mm_shuffle_epi8(simde_mm_load_si128((simde__m128i*)REX_RAW_ADDR(ea)), simde_mm_load_si128((simde__m128i*)VectorMaskL)));
\t// stvx128 v63,r0,r4
\tsimde_mm_store_si128((simde__m128i*)REX_RAW_ADDR(ea), simde_mm_shuffle_epi8(simde_mm_load_si128((simde__m128i*)ctx.v63.u8), simde_mm_load_si128((simde__m128i*)VectorMaskL)));
\t// lwarx r11,r0,r3
\tctx.reserved.u32 = *(uint32_t*)REX_RAW_ADDR(ea);
\t// stwcx. r4,r0,r3
\tctx.cr0.eq = __sync_bool_compare_and_swap(reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)), ctx.reserved.s32, __builtin_bswap32(ctx.r4.s32));
\t// dcbz r0,r3
\tmemset((void*)REX_RAW_ADDR(ea), 0, 128);
\t// lvlx v1,r0,r3
\tREX_MM_STORE_U32(ctx.r10.u32, ctx.r11.u32);
\tctx.r3.u64 = REX_MM_LOAD_U32(ctx.r10.u32);
\tREX_ENTER_GLOBAL_LOCK();
\tREX_LEAVE_GLOBAL_LOCK();
\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);
\tmemcpy(dst, src, 4);
\tsimde_mm_storeu_si128(p, v);
\t// lswi r5,r4,8
\t// ldfoo r1,r2
\tfoo = REX_RAW_ADDR(ea);
}}

DEFINE_REX_FUNC(sub_8ABCDEF1) {{
\tREX_FUNC_PROLOGUE();
\tctx.r3.u64 = REX_LOAD_U32(ctx.r4.u32 + 8);
}}
"""

SDK_PCH = """#define REX_PHYS_HOST_OFFSET(addr) 0u
#define REX_RAW_ADDR(x) (base + (u32)(x) + REX_PHYS_HOST_OFFSET(x))
#define REX_LOAD_U32(x) __builtin_bswap32(*(volatile u32*)(base + (u32)(x)))
#define REX_STORE_U32(x, y) (*(volatile u32*)(base + (u32)(x)) = __builtin_bswap32(y))
"""


def run(gen, sdk, out):
    return subprocess.run(
        [sys.executable, str(HERE / "access_census.py"), "--generated", str(gen),
         "--sdk", str(sdk), "--out", str(out)],
        capture_output=True, text=True)


class AccessCensusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.gen, self.sdk, self.out = t / "gen", t / "sdk", t / "out"
        self.gen.mkdir()
        (self.gen / "a.0.cpp").write_text(SYNTH_CPP, encoding="utf-8")
        (self.gen / "a.0.h").write_text("DECLARE_REX_FUNC(sub_8ABCDEF0);\n", encoding="utf-8")
        d = self.sdk / "resources" / "templates" / "codegen"
        d.mkdir(parents=True)
        (d / "pch_h.inja").write_text(SDK_PCH, encoding="utf-8")
        (d / "_indirect_call.inja").write_text("#define REX_LOOKUP_FUNC(x, y) 0\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def census(self):
        p = run(self.gen, self.sdk, self.out)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn("ACCESS_CENSUS PASS", p.stdout)
        return json.loads((self.out / "census.json").read_text(encoding="utf-8"))

    def test_classification(self):
        r = self.census()
        self.assertEqual(r["inputs"]["function_definitions"], 2)
        s = r["scalar_by_width"]
        self.assertEqual(s["load_u32"]["occurrences"], 2)
        self.assertEqual(s["load_u32"]["functions_exact"], 2)
        self.assertEqual(s["store_u32"]["occurrences"], 1)
        self.assertEqual(s["load_u8"]["occurrences"], 1)
        self.assertEqual(s["store_u64"]["functions_exact"], 1)
        v = r["vector_aligned_raw_addr"]
        self.assertEqual(v["load_si128"]["occurrences"], 1)
        self.assertEqual(v["store_si128"]["occurrences"], 1)
        self.assertEqual(r["effective_address_alignment_masks"]["0xf"], 1)
        self.assertEqual(r["reservations"]["load_reserved"]["occurrences"], 1)
        self.assertEqual(r["reservations"]["store_conditional_cas"]["occurrences"], 1)
        self.assertEqual(r["reservations"]["global_lock_enter"]["occurrences"], 1)
        self.assertEqual(r["bulk_memory"]["memset_raw_addr"]["occurrences"], 1)
        self.assertEqual(r["bulk_memory"]["memcpy_tokens"]["occurrences"], 1)
        self.assertEqual(r["mmio"]["all"]["occurrences"], 2)
        self.assertEqual(r["indirect_calls_and_code_addresses"]["call_indirect_func"]["occurrences"], 1)
        self.assertEqual(r["explicit_unaligned_forms"]["unaligned_intrinsics_loadu_storeu_etc"]["occurrences"], 1)
        mg = r["guest_mnemonic_groups"]
        self.assertEqual(mg["reservation"]["occurrences"], 2)
        self.assertEqual(mg["multiword_string"]["occurrences"], 1)
        self.assertEqual(r["unclassified_memory_like_mnemonics"], {"ldfoo": 1})
        self.assertEqual(r["other_unclassified"]["raw_addr_lines_not_matching_known_forms"]["occurrences"], 1)
        self.assertEqual(r["scalar_address_argument_form"]["reg_plus_reg"], 1)
        self.assertEqual(r["sdk_macro_forms"]["REX_LOAD_U32"].startswith("#define REX_LOAD_U32"), True)

    def test_no_code_bytes_in_output(self):
        self.census()
        for name in ("census.json", "census.md"):
            text = (self.out / name).read_text(encoding="utf-8")
            self.assertNotIn(SENTINEL_FUNC, text)
            self.assertNotIn("sub_8ABCDEF1", text)
            self.assertNotIn(SENTINEL_CONST, text)
            self.assertNotIn("ctx.r4.u32", text)
        r = json.loads((self.out / "census.json").read_text(encoding="utf-8"))
        for cat, ex in r["examples_normalised_max3"].items():
            self.assertLessEqual(len(ex), ac.MAX_EXAMPLES)
            for line in ex:
                self.assertLessEqual(len(line), ac.EXAMPLE_WIDTH)

    def test_deterministic_and_digest(self):
        a = self.census()
        first = (self.out / "census.json").read_bytes()
        self.census()
        self.assertEqual(first, (self.out / "census.json").read_bytes())
        (self.gen / "a.0.h").write_text("DECLARE_REX_FUNC(sub_8ABCDEF9);\n", encoding="utf-8")
        b = self.census()
        self.assertNotEqual(a["inputs"]["generated_aggregate_sha256"], b["inputs"]["generated_aggregate_sha256"])

    def test_missing_generated_dir_refuses(self):
        p = run(self.gen / "nope", self.sdk, self.out)
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("PASS", p.stdout)

    def test_missing_sdk_macros_refuses(self):
        (self.sdk / "resources" / "templates" / "codegen" / "pch_h.inja").write_text("", encoding="utf-8")
        p = run(self.gen, self.sdk, self.out)
        self.assertNotEqual(p.returncode, 0)

    def test_generated_inputs_not_modified(self):
        before = ac.sha256_file(self.gen / "a.0.cpp")
        self.census()
        self.assertEqual(before, ac.sha256_file(self.gen / "a.0.cpp"))


if __name__ == "__main__":
    unittest.main()

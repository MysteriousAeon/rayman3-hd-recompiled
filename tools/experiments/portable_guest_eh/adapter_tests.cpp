// Focused tests of the real SDK context and host FP environment.
#include "ppc_adapter.h"

#include <array>
#include <cfenv>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

using pgeh::Adapter;
static constexpr std::array<PPCRegister PPCContext::*, 32> gpr = {
    &PPCContext::r0, &PPCContext::r1, &PPCContext::r2, &PPCContext::r3,
    &PPCContext::r4, &PPCContext::r5, &PPCContext::r6, &PPCContext::r7,
    &PPCContext::r8, &PPCContext::r9, &PPCContext::r10, &PPCContext::r11,
    &PPCContext::r12, &PPCContext::r13, &PPCContext::r14, &PPCContext::r15,
    &PPCContext::r16, &PPCContext::r17, &PPCContext::r18, &PPCContext::r19,
    &PPCContext::r20, &PPCContext::r21, &PPCContext::r22, &PPCContext::r23,
    &PPCContext::r24, &PPCContext::r25, &PPCContext::r26, &PPCContext::r27,
    &PPCContext::r28, &PPCContext::r29, &PPCContext::r30, &PPCContext::r31};
static constexpr std::array<PPCRegister PPCContext::*, 32> fpr = {
    &PPCContext::f0, &PPCContext::f1, &PPCContext::f2, &PPCContext::f3,
    &PPCContext::f4, &PPCContext::f5, &PPCContext::f6, &PPCContext::f7,
    &PPCContext::f8, &PPCContext::f9, &PPCContext::f10, &PPCContext::f11,
    &PPCContext::f12, &PPCContext::f13, &PPCContext::f14, &PPCContext::f15,
    &PPCContext::f16, &PPCContext::f17, &PPCContext::f18, &PPCContext::f19,
    &PPCContext::f20, &PPCContext::f21, &PPCContext::f22, &PPCContext::f23,
    &PPCContext::f24, &PPCContext::f25, &PPCContext::f26, &PPCContext::f27,
    &PPCContext::f28, &PPCContext::f29, &PPCContext::f30, &PPCContext::f31};
static constexpr std::array<PPCVRegister PPCContext::*, 128> vector_regs = {
    &PPCContext::v0, &PPCContext::v1, &PPCContext::v2, &PPCContext::v3,
    &PPCContext::v4, &PPCContext::v5, &PPCContext::v6, &PPCContext::v7,
    &PPCContext::v8, &PPCContext::v9, &PPCContext::v10, &PPCContext::v11,
    &PPCContext::v12, &PPCContext::v13, &PPCContext::v14, &PPCContext::v15,
    &PPCContext::v16, &PPCContext::v17, &PPCContext::v18, &PPCContext::v19,
    &PPCContext::v20, &PPCContext::v21, &PPCContext::v22, &PPCContext::v23,
    &PPCContext::v24, &PPCContext::v25, &PPCContext::v26, &PPCContext::v27,
    &PPCContext::v28, &PPCContext::v29, &PPCContext::v30, &PPCContext::v31,
    &PPCContext::v32, &PPCContext::v33, &PPCContext::v34, &PPCContext::v35,
    &PPCContext::v36, &PPCContext::v37, &PPCContext::v38, &PPCContext::v39,
    &PPCContext::v40, &PPCContext::v41, &PPCContext::v42, &PPCContext::v43,
    &PPCContext::v44, &PPCContext::v45, &PPCContext::v46, &PPCContext::v47,
    &PPCContext::v48, &PPCContext::v49, &PPCContext::v50, &PPCContext::v51,
    &PPCContext::v52, &PPCContext::v53, &PPCContext::v54, &PPCContext::v55,
    &PPCContext::v56, &PPCContext::v57, &PPCContext::v58, &PPCContext::v59,
    &PPCContext::v60, &PPCContext::v61, &PPCContext::v62, &PPCContext::v63,
    &PPCContext::v64, &PPCContext::v65, &PPCContext::v66, &PPCContext::v67,
    &PPCContext::v68, &PPCContext::v69, &PPCContext::v70, &PPCContext::v71,
    &PPCContext::v72, &PPCContext::v73, &PPCContext::v74, &PPCContext::v75,
    &PPCContext::v76, &PPCContext::v77, &PPCContext::v78, &PPCContext::v79,
    &PPCContext::v80, &PPCContext::v81, &PPCContext::v82, &PPCContext::v83,
    &PPCContext::v84, &PPCContext::v85, &PPCContext::v86, &PPCContext::v87,
    &PPCContext::v88, &PPCContext::v89, &PPCContext::v90, &PPCContext::v91,
    &PPCContext::v92, &PPCContext::v93, &PPCContext::v94, &PPCContext::v95,
    &PPCContext::v96, &PPCContext::v97, &PPCContext::v98, &PPCContext::v99,
    &PPCContext::v100, &PPCContext::v101, &PPCContext::v102, &PPCContext::v103,
    &PPCContext::v104, &PPCContext::v105, &PPCContext::v106, &PPCContext::v107,
    &PPCContext::v108, &PPCContext::v109, &PPCContext::v110, &PPCContext::v111,
    &PPCContext::v112, &PPCContext::v113, &PPCContext::v114, &PPCContext::v115,
    &PPCContext::v116, &PPCContext::v117, &PPCContext::v118, &PPCContext::v119,
    &PPCContext::v120, &PPCContext::v121, &PPCContext::v122, &PPCContext::v123,
    &PPCContext::v124, &PPCContext::v125, &PPCContext::v126, &PPCContext::v127};
static constexpr std::array<PPCCRRegister PPCContext::*, 8> cr = {
    &PPCContext::cr0, &PPCContext::cr1, &PPCContext::cr2, &PPCContext::cr3,
    &PPCContext::cr4, &PPCContext::cr5, &PPCContext::cr6, &PPCContext::cr7};
static int checks = 0;
static void check(bool condition, const char* what) {
  ++checks;
  if (!condition) throw std::runtime_error(std::string(what) + " check=" + std::to_string(checks));
}

static void fill(PPCContext& c, uint64_t seed) {
  for (size_t i = 0; i < gpr.size(); ++i) (c.*gpr[i]).u64 = seed + i;
  for (size_t i = 0; i < fpr.size(); ++i) (c.*fpr[i]).u64 = seed + 100 + i;
  for (size_t i = 0; i < vector_regs.size(); ++i) {
    (c.*vector_regs[i]).u64[0] = seed + 200 + i;
    (c.*vector_regs[i]).u64[1] = seed + 400 + i;
  }
  for (size_t i = 0; i < cr.size(); ++i) (c.*cr[i]).set_raw(uint32_t(((seed >> 16) + i) & 15));
  c.lr = seed + 600;
  c.ctr.u64 = seed + 601;
  c.xer = {uint8_t((seed >> 16) & 1), uint8_t((seed >> 17) & 1), uint8_t((seed >> 18) & 1)};
  c.reserved.u64 = seed + 602;
  c.msr = uint32_t(seed + 603);
  c.vscr_sat = uint8_t((seed >> 16) & 1);
  c.last_indirect_target = uint32_t(seed + 604);
  c.fpscr.csr = PPCFPSCRRegister::Platform::getcsr();
}

static void check_full(const PPCContext& a, const PPCContext& b) {
  for (size_t i = 0; i < gpr.size(); ++i) check((a.*gpr[i]).u64 == (b.*gpr[i]).u64, "gpr");
  for (size_t i = 0; i < fpr.size(); ++i) check((a.*fpr[i]).u64 == (b.*fpr[i]).u64, "fpr");
  for (size_t i = 0; i < vector_regs.size(); ++i) {
    check((a.*vector_regs[i]).u64[0] == (b.*vector_regs[i]).u64[0], "vector low");
    check((a.*vector_regs[i]).u64[1] == (b.*vector_regs[i]).u64[1], "vector high");
  }
  for (size_t i = 0; i < cr.size(); ++i) check((a.*cr[i]).raw() == (b.*cr[i]).raw(), "cr");
  check(a.lr == b.lr && a.ctr.u64 == b.ctr.u64, "lr ctr");
  check(a.xer.so == b.xer.so && a.xer.ov == b.xer.ov && a.xer.ca == b.xer.ca, "xer");
  check(a.reserved.u64 == b.reserved.u64 && a.msr == b.msr, "reserved msr");
  check(a.vscr_sat == b.vscr_sat && a.last_indirect_target == b.last_indirect_target, "vscr indirect");
  check(a.fpscr.csr == b.fpscr.csr, "fpscr context");
}

int main() {
  std::fenv_t original_env;
  if (std::fegetenv(&original_env) != 0) return 2;
  const uint32_t original_csr = PPCFPSCRRegister::Platform::getcsr();
  try {
    std::fenv_t held_env;
    check(std::feholdexcept(&held_env) == 0, "mask host FP traps");
    PPCContext owner{};
    fill(owner, 0x10000);
    // Keep traps masked while exercising both guest and non-guest CSR bits.
    constexpr uint32_t guest_mask = PPCFPSCRRegister::GuestMask;
    uint32_t controlled = original_csr | uint32_t(rex::platform::FPSCRPlatform::ExceptionMask);
    controlled &= ~guest_mask;
    controlled |= uint32_t(PPCFPSCRRegister::Platform::GuestToHost[1]);
    PPCFPSCRRegister::Platform::setcsr(controlled);
    owner.fpscr.csr = controlled;
    const auto saved = Adapter::capture_owner(owner);
    PPCContext changed{};
    fill(changed, 0x20000);
    // Alter guest bits; keep host exception masks safe and set a non-guest status flag.
    uint32_t before_restore = (controlled & ~guest_mask) |
        uint32_t(PPCFPSCRRegister::Platform::GuestToHost[2]) |
        uint32_t(PPCFPSCRRegister::FlushMask);
#if defined(__x86_64__) || defined(_M_X64)
    before_restore |= 1u; // MXCSR invalid-operation sticky flag, with mask still set.
#endif
    PPCFPSCRRegister::Platform::setcsr(before_restore);
    Adapter::restore_owner(changed, saved);
    const uint32_t after_restore = PPCFPSCRRegister::Platform::getcsr();
    check((after_restore & guest_mask) == (controlled & guest_mask), "guest CSR bits restored");
    check((after_restore & ~guest_mask) == (before_restore & ~guest_mask), "host CSR policy preserved");
    check(changed.fpscr.csr == after_restore, "context CSR matches restored host CSR");
    for (size_t i = 0; i < gpr.size(); ++i) {
      const bool saved_reg = i == 1 || i == 2 || i == 13 || i >= 14;
      check((changed.*gpr[i]).u64 == (saved_reg ? (owner.*gpr[i]).u64 : uint64_t(0x20000 + i)), "owner gpr");
    }
    for (size_t i = 0; i < fpr.size(); ++i)
      check((changed.*fpr[i]).u64 == (i >= 14 ? (owner.*fpr[i]).u64 : uint64_t(0x20000 + 100 + i)), "owner fpr");
    for (size_t i = 0; i < vector_regs.size(); ++i) {
      const bool saved_reg = (i >= 14 && i < 32) || i >= 64;
      check((changed.*vector_regs[i]).u64[0] == (saved_reg ? (owner.*vector_regs[i]).u64[0] : uint64_t(0x20000 + 200 + i)), "owner vector low");
      check((changed.*vector_regs[i]).u64[1] == (saved_reg ? (owner.*vector_regs[i]).u64[1] : uint64_t(0x20000 + 400 + i)), "owner vector high");
    }
    for (size_t i = 0; i < cr.size(); ++i)
      check((changed.*cr[i]).raw() == ((i >= 2 && i <= 4) ? (owner.*cr[i]).raw() : uint32_t((2 + i) & 15)), "owner cr");
    check(changed.lr == 0x20000 + 600 && changed.ctr.u64 == 0x20000 + 601, "volatile special registers");
    check(changed.xer.so == 0 && changed.xer.ov == 1 && changed.xer.ca == 0, "volatile xer");

    // Capture actual fenv plus host CSR: restore after a synthetic funclet mutates both.
    std::feclearexcept(FE_ALL_EXCEPT);
    check(std::fesetround(FE_DOWNWARD) == 0, "set initial rounding");
    check(std::feraiseexcept(FE_INVALID) == 0, "raise initial exception flag");
    PPCContext live{};
    fill(live, 0x30000);
    live.fpscr.csr = PPCFPSCRRegister::Platform::getcsr();
    const PPCContext live_expected = live;
    const int saved_round = std::fegetround();
    const int saved_flags = std::fetestexcept(FE_ALL_EXCEPT);
    const uint32_t saved_csr = PPCFPSCRRegister::Platform::getcsr();
    const auto full = Adapter::capture_full(live);
    fill(live, 0x40000);
    std::feclearexcept(FE_ALL_EXCEPT);
    check(std::feraiseexcept(FE_DIVBYZERO) == 0, "change host sticky flags");
    check(std::fesetround(FE_UPWARD) == 0, "change funclet rounding");
    uint32_t mutated = PPCFPSCRRegister::Platform::getcsr() ^ uint32_t(PPCFPSCRRegister::FlushMask);
    PPCFPSCRRegister::Platform::setcsr(mutated);
    Adapter::restore_full(live, full);
    check_full(live, live_expected);
    check(std::fegetround() == saved_round, "host rounding restored");
    check(std::fetestexcept(FE_ALL_EXCEPT) == saved_flags, "host flags restored");
    check(PPCFPSCRRegister::Platform::getcsr() == saved_csr, "full host CSR restored");
    Adapter::set_stack(live, 0xfff0);
    Adapter::set_args(live, 11, 22, 33);
    check(Adapter::stack(live) == 0xfff0 && live.r3.u64 == 11 && live.r4.u64 == 22 && live.r12.u64 == 33, "ABI registers");
    Adapter::set_return(live, 44);
    check(live.r3.u64 == 44, "return register");

    std::fesetenv(&original_env);
    PPCFPSCRRegister::Platform::setcsr(original_csr);
    std::cout << "PPC_ADAPTER PASS checks=" << checks << "\n";
    return 0;
  } catch (const std::exception& e) {
    std::fesetenv(&original_env);
    PPCFPSCRRegister::Platform::setcsr(original_csr);
    std::cerr << e.what() << "\n";
    return 1;
  }
}

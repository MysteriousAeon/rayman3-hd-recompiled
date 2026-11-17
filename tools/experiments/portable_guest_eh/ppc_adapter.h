// Experiment only: uses the real pinned SDK definitions; never included by production.
#pragma once

#include <array>
#include <cfenv>
#include <cstdint>
#include <stdexcept>

#include <rex/ppc/context.h>

#if !defined(__x86_64__) && !defined(_M_X64)
#error This experimental adapter is validated for x86-64 only; ARM FP state needs a separate milestone.
#endif

namespace pgeh {
struct Adapter {
  using State = PPCContext;
  static_assert(State::kNonVolatileSaveSize == 1616);

  struct OwnerSnapshot {
    std::array<uint8_t, State::kNonVolatileSaveSize> regs{};
    PPCRegister r1{}, r2{}, r13{};
  };

  // This experiment saves the complete host environment for funclet rollback.
  // M4 itself restores the guest-owned CSR bits while keeping host policy.
  struct FullSnapshot {
    State state;
    std::fenv_t host_env{};
    uint32_t host_csr{};
  };

  static OwnerSnapshot capture_owner(const State& state) {
    OwnerSnapshot out;
    state.SaveNonVolatiles(out.regs.data());
    out.r1 = state.r1; out.r2 = state.r2; out.r13 = state.r13;
    return out;
  }

  static void restore_owner(State& state, const OwnerSnapshot& saved) {
    state.RestoreNonVolatiles(saved.regs.data());
    state.r1 = saved.r1; state.r2 = saved.r2; state.r13 = saved.r13;
  }

  static FullSnapshot capture_full(const State& state) {
    FullSnapshot out{state};
    if (std::fegetenv(&out.host_env) != 0) throw std::runtime_error("fegetenv failed");
    out.host_csr = PPCFPSCRRegister::Platform::getcsr();
    return out;
  }

  static void restore_full(State& state, const FullSnapshot& saved) {
    if (std::fesetenv(&saved.host_env) != 0) throw std::runtime_error("fesetenv failed");
    PPCFPSCRRegister::Platform::setcsr(saved.host_csr);
    state = saved.state;
  }

  static uint32_t stack(const State& state) { return state.r1.u32; }
  static void set_stack(State& state, uint32_t value) { state.r1.u64 = value; }
  static void set_args(State& state, uint32_t r3, uint32_t r4, uint32_t r12) {
    state.r3.u64 = r3; state.r4.u64 = r4; state.r12.u64 = r12;
  }
  static void set_return(State& state, uint32_t value) { state.r3.u64 = value; }
};
}  // namespace pgeh

#include "record_bridge.h"

#include <array>
#include <atomic>
#include <barrier>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <functional>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
constexpr uint32_t kPc = 0x82001234u;
constexpr uint32_t kLabel = 0x82001300u;
constexpr uint32_t kOwnerSp = 0x33000u;
constexpr uint32_t kLiveSp = 0x30000u;
constexpr uint32_t kEa = 0x5000u;
std::atomic<unsigned> checks{0};
std::atomic<unsigned> failures{0};

void expect(bool value, const char* what) {
  ++checks;
  if (value) return;
  ++failures;
  std::fprintf(stderr, "BRIDGE_TESTS FAIL: %s\n", what);
}

struct Fixture {
  std::vector<uint8_t> bytes = std::vector<uint8_t>(0x40000, 0xa5);
  lgi::GuestArena arena{std::span<uint8_t>(bytes), 0x28000, 0x34000,
                       true, 4096, 0x12345678u};
};

PPCContext new_context(uint32_t sp = kOwnerSp) {
  PPCContext state{};
  state.r1.u64 = sp;
  state.r14.u64 = 0x14141414u;
  state.r3.u64 = 0x33333333u;
  state.fpscr.csr = 0x1234u;
  return state;
}

void put_be32(std::array<uint8_t, 80>& bytes, size_t offset, uint32_t value) {
  bytes[offset] = uint8_t(value >> 24);
  bytes[offset + 1] = uint8_t(value >> 16);
  bytes[offset + 2] = uint8_t(value >> 8);
  bytes[offset + 3] = uint8_t(value);
}

lgi::AccessRequest request(uint32_t ea = kEa, uint32_t pc = kPc) {
  return {ea, pc, 4, lgi::Operation::read};
}

lgi::Backend success_backend(uint32_t guest_value, unsigned* calls = nullptr) {
  const uint32_t raw = lgi::host_to_guest_be32(guest_value);
  return [raw, calls](const void*) {
    if (calls) ++*calls;
    return lgi::BackendResult::Success(raw);
  };
}

void test_record_layout_and_restore() {
  Fixture fixture;
  PPCContext state = new_context();
  unsigned finally_calls = 0;
  bool filter_seen = false;
  const uint32_t original_host_csr = PPCFPSCRRegister::Platform::getcsr();
  const lgf::Record source = [] {
    lgf::Record record{};
    record.code = lgi::kGuestAccessViolation;
    record.pc = kPc;
    record.count = 2;
    record.info[0] = 0;
    record.info[1] = kEa;
    for (uint32_t i = 2; i < record.info.size(); ++i)
      record.info[i] = 0xa1000000u + i;
    return record;
  }();
  std::vector<pgeh::Scope> scopes;
  scopes.push_back({kPc - 4, kPc + 4, 0, {}, [&](auto&, uint32_t) {
                      ++finally_calls;
                    }});
  scopes.push_back({kPc - 4, kPc + 4, kLabel,
      lgi::wrap_filter([&](PPCContext& visible, const pgeh::GuestRecord& record,
                           uint32_t establisher) {
        filter_seen = true;
        const uint32_t scratch = lgi::scratch_sp(kLiveSp);
        expect(record.code == source.code && record.flags == source.flags &&
                   record.address == source.pc,
               "filter gets guest code, flags and PC");
        expect(visible.r1.u32 == scratch && visible.r3.u32 == scratch + 0x70 &&
                   visible.r4.u32 == kOwnerSp && visible.r12.u32 == kOwnerSp &&
                   establisher == kOwnerSp,
               "filter arguments use live scratch and owner establisher");
        expect(visible.r14.u64 == 0x14141414u,
               "filter sees owner nonvolatile snapshot");
        const std::array<lgi::Consumer, 0> no_consumers{};
        unsigned nested_backend_calls = 0;
        uint32_t nested_out = 0xabcdef01u;
        const auto nested_status = lgi::checked_load32(
            fixture.arena, request(), kLiveSp, no_consumers,
            [&](const void*) {
              ++nested_backend_calls;
              return lgi::BackendResult::Success(0);
            }, nested_out);
        bool nested_delivery_rejected = false;
        try {
          lgi::deliver(fixture.arena, kLiveSp, source);
        } catch (const pgeh::Unsupported&) {
          nested_delivery_rejected = lgi::current_delivery != nullptr;
        }
        expect(nested_status == lgi::AccessStatus::unsupported &&
                   !nested_backend_calls && nested_out == 0xabcdef01u &&
                   nested_delivery_rejected,
               "filter cannot recursively dispatch access or serialize a record");

        std::array<uint8_t, 80> expected{};
        put_be32(expected, 0, source.code);
        put_be32(expected, 4, source.flags);
        put_be32(expected, 8, source.chain);
        put_be32(expected, 12, source.pc);
        put_be32(expected, 16, source.count);
        for (uint32_t i = 0; i < source.info.size(); ++i)
          put_be32(expected, 20 + 4 * i, source.info[i]);
        const size_t record_offset = scratch + 0x80;
        expect(std::memcmp(fixture.bytes.data() + record_offset, expected.data(),
                           expected.size()) == 0,
               "all 80 record bytes match the big-endian M4 layout");
        expect(fixture.bytes[scratch + 0x70] == uint8_t((scratch + 0x80) >> 24) &&
                   fixture.bytes[scratch + 0x71] == uint8_t((scratch + 0x80) >> 16) &&
                   fixture.bytes[scratch + 0x72] == uint8_t((scratch + 0x80) >> 8) &&
                   fixture.bytes[scratch + 0x73] == uint8_t(scratch + 0x80) &&
                   fixture.bytes[scratch + 0x74] == 0 &&
                   fixture.bytes[scratch + 0x75] == 0 &&
                   fixture.bytes[scratch + 0x76] == 0 &&
                   fixture.bytes[scratch + 0x77] == 0,
               "exception pointers contain record pointer and zero ContextRecord");
        expect(std::all_of(fixture.bytes.begin() + scratch + 0x78,
                           fixture.bytes.begin() + scratch + 0x80,
                           [](uint8_t b) { return b == 0xa5; }) &&
                   std::all_of(fixture.bytes.begin() + scratch + 0xd0,
                               fixture.bytes.begin() + scratch + 0xe0,
                               [](uint8_t b) { return b == 0xa5; }),
               "serialization preserves both adjacent canary regions");
        bool exact_extent = true;
        for (size_t i = 0; i < fixture.bytes.size(); ++i) {
          const bool pointer_byte = i >= scratch + 0x70 && i < scratch + 0x78;
          const bool record_byte = i >= scratch + 0x80 && i < scratch + 0xd0;
          if (!pointer_byte && !record_byte && fixture.bytes[i] != 0xa5)
            exact_extent = false;
        }
        expect(exact_extent, "all bytes outside the 88-byte write extent remain canaries");

        visible.r3.u64 = 0xdeadbeefu;
        visible.r14.u64 = 0xeeeeeeeeu;
        visible.fpscr.csr ^= 0xffffffffu;
        PPCFPSCRRegister::Platform::setcsr(original_host_csr ^ 0x6000u);
        fixture.bytes[kEa + 8] = 0x77;  // Guest-memory effects survive rollback.
        bool every_other_byte_preserved = true;
        for (size_t i = 0; i < fixture.bytes.size(); ++i) {
          const bool pointer_byte = i >= scratch + 0x70 && i < scratch + 0x78;
          const bool record_byte = i >= scratch + 0x80 && i < scratch + 0xd0;
          const bool guest_effect = i == kEa + 8;
          if (!pointer_byte && !record_byte && !guest_effect &&
              fixture.bytes[i] != 0xa5)
            every_other_byte_preserved = false;
        }
        expect(every_other_byte_preserved,
               "no other guest bytes change during record serialization");
        return -1;
      }), {}});
  pgeh::Owner owner(state, std::move(scopes));
  owner.declare_label(kLabel);
  const uint32_t selected = pgeh::region(owner, [&] {
    owner.set_pc(kPc);
    owner.before_call();
    state.r1.u64 = kLiveSp;
    state.r14.u64 = 0x22222222u;
    const uint32_t before_r3 = state.r3.u32;
    const uint32_t before_fpscr = state.fpscr.csr;
    lgi::deliver(fixture.arena, kLiveSp, source);
    expect(state.r1.u32 == kLiveSp && state.r3.u32 == before_r3 &&
               state.r14.u64 == 0x22222222u && state.fpscr.csr == before_fpscr,
           "filter register and FPSCR mutations roll back to the live state");
    expect(PPCFPSCRRegister::Platform::getcsr() == original_host_csr,
           "filter host MXCSR rounding mutation rolls back");
    expect(fixture.bytes[kEa + 8] == 0x77,
           "guest-memory side effects are not rolled back");
  });
  expect(filter_seen && selected == 0 && finally_calls == 0,
         "negative continuation returns in place without cleanup");
}

void test_preflight_rejections_are_write_free() {
  auto unchanged = [&](const Fixture& fixture, const char* reason) {
    expect(std::all_of(fixture.bytes.begin(), fixture.bytes.end(),
                       [](uint8_t b) { return b == 0xa5; }), reason);
  };
  auto valid_record = [] {
    lgf::Record record{};
    record.code = lgi::kGuestAccessViolation;
    record.pc = kPc;
    record.count = 2;
    record.info[1] = kEa;
    return record;
  };
  auto rejected = [&](Fixture& fixture, uint32_t live_sp, lgf::Record record,
                      const char* reason, uint32_t context_sp = kOwnerSp,
                      bool set_context_to_live = true) {
    PPCContext state = new_context(context_sp);
    std::vector<pgeh::Scope> scopes;
    pgeh::Owner owner(state, std::move(scopes));
    if (set_context_to_live) state.r1.u64 = live_sp;
    bool threw = false;
    try {
      lgi::deliver(fixture.arena, live_sp, record);
    } catch (const pgeh::Unsupported&) {
      threw = true;
    }
    expect(threw, reason);
    unchanged(fixture, "rejected delivery writes no scratch bytes");
  };

  {
    Fixture fixture;
    auto record = valid_record();
    record.count = 16;
    rejected(fixture, kLiveSp, record, "oversized information count rejected");
  }
  {
    Fixture fixture;
    auto record = valid_record();
    record.chain = 0x3000;
    rejected(fixture, kLiveSp, record, "unsupported chained record rejected");
  }
  {
    Fixture fixture;
    fixture.arena.stable_writable_backing = false;
    rejected(fixture, kLiveSp, valid_record(), "untrusted scratch backing rejected");
  }
  {
    Fixture fixture;
    fixture.arena.stack_low = 0x2fd00;
    rejected(fixture, kLiveSp, valid_record(), "scratch below stack bound rejected");
  }
  {
    Fixture fixture;
    rejected(fixture, 0x100, valid_record(), "underflowing live stack rejected");
  }
  {
    Fixture fixture;
    rejected(fixture, kLiveSp + 0x10000, valid_record(),
             "scratch above backing bounds rejected");
  }
  {
    Fixture fixture;
    auto record = valid_record();
    record.pc = 0;
    rejected(fixture, kLiveSp, record, "malformed guest PC rejected");
  }
  {
    Fixture fixture;
    auto record = valid_record();
    record.info[1] = 0x3ffff;
    rejected(fixture, kLiveSp, record, "effective address without full width rejected");
  }
  {
    Fixture fixture;
    rejected(fixture, kLiveSp, valid_record(),
             "live stack pointer mismatch rejected", kOwnerSp + 0x100, false);
  }
  {
    Fixture fixture;
    PPCContext state = new_context();
    std::vector<pgeh::Scope> scopes;
    pgeh::Owner owner(state, std::move(scopes));
    owner.set_pc(kPc);
    owner.before_call();
    state.r1.u64 = kLiveSp;
    pgeh::FuncletGuard funclet;
    unsigned consumer_calls = 0, backend_calls = 0;
    const std::array<lgi::Consumer, 1> consumers{{
        [&](const auto&, uintptr_t) {
          ++consumer_calls;
          return lgi::ConsumerResult::Pass();
        }}};
    uint32_t out = 0xabcdef01u;
    const auto status = lgi::checked_load32(
        fixture.arena, request(), kLiveSp, consumers,
        [&](const void*) {
          ++backend_calls;
          return lgi::BackendResult::Success(0);
        }, out);
    expect(status == lgi::AccessStatus::unsupported && !consumer_calls &&
               !backend_calls && out == 0xabcdef01u,
           "funclet reentrant dispatch rejects before consumers and backend");
  }
}

void test_checked_access_and_consumers() {
  Fixture fixture;
  unsigned mmio_calls = 0, watch_calls = 0, backend_calls = 0;
  const std::array<lgi::Consumer, 2> consumers{{
      [&](const auto& access, uintptr_t host) {
        ++mmio_calls;
        expect(access.effective_address == kEa &&
                   host == reinterpret_cast<uintptr_t>(fixture.bytes.data() + kEa),
               "consumer receives translated host address and guest EA");
        return lgi::ConsumerResult::Mmio(0x12345678u);
      },
      [&](const auto&, uintptr_t) {
        ++watch_calls;
        return lgi::ConsumerResult::WatchRepair();
      }}};
  uint32_t out = 0xaaaaaaaa;
  auto status = lgi::checked_load32(fixture.arena, request(), kLiveSp,
                                     consumers,
                                     success_backend(0, &backend_calls), out);
  expect(status == lgi::AccessStatus::mmio_consumed && out == 0x12345678u &&
             mmio_calls == 1 && watch_calls == 0 && backend_calls == 0,
         "first MMIO consumer wins and prevents later consumers or load");

  const std::array<lgi::Consumer, 1> watch{{
      [&](const auto&, uintptr_t) {
        ++watch_calls;
        return lgi::ConsumerResult::WatchRepair();
      }}};
  out = 0xbbbbbbbb;
  status = lgi::checked_load32(fixture.arena, request(), kLiveSp, watch,
                               success_backend(0x87654321, &backend_calls), out);
  expect(status == lgi::AccessStatus::watch_repair_required &&
             out == 0xbbbbbbbb && watch_calls == 1 && backend_calls == 0,
         "watch repair is consume-first and leaves retry to a fresh call");

  unsigned retry_consumer_calls = 0;
  const std::array<lgi::Consumer, 1> repaired{{
      [&](const auto&, uintptr_t) {
        ++retry_consumer_calls;
        return lgi::ConsumerResult::Pass();
      }}};
  status = lgi::checked_load32(fixture.arena, request(), kLiveSp, repaired,
                               success_backend(0x87654321, &backend_calls), out);
  expect(status == lgi::AccessStatus::success && out == 0x87654321 &&
             retry_consumer_calls == 1 && backend_calls == 1,
         "fresh helper call after repair executes once and converts big endian");

  unsigned recursive_calls = 0, recursive_backend_calls = 0;
  lgi::AccessStatus nested_status = lgi::AccessStatus::success;
  std::array<lgi::Consumer, 0> no_consumers{};
  const std::array<lgi::Consumer, 1> recursive{{
      [&](const auto&, uintptr_t) {
        ++recursive_calls;
        uint32_t nested_out = 0x01020304u;
        nested_status = lgi::checked_load32(
            fixture.arena, request(), kLiveSp, no_consumers,
            [&](const void*) {
              ++recursive_backend_calls;
              return lgi::BackendResult::Success(0);
            }, nested_out);
        expect(nested_out == 0x01020304u,
               "rejected nested access preserves its output value");
        return lgi::ConsumerResult::Pass();
      }}};
  status = lgi::checked_load32(fixture.arena, request(), kLiveSp, recursive,
                               success_backend(0x10203040u, &backend_calls), out);
  expect(status == lgi::AccessStatus::success && out == 0x10203040u &&
             recursive_calls == 1 && nested_status == lgi::AccessStatus::unsupported &&
             recursive_backend_calls == 0,
         "recursive consumer dispatch is rejected without duplicate access");

  unsigned invalid_pc_consumers = 0, invalid_pc_backend = 0;
  const std::array<lgi::Consumer, 1> invalid_pc_consumer{{
      [&](const auto&, uintptr_t) {
        ++invalid_pc_consumers;
        return lgi::ConsumerResult::Pass();
      }}};
  auto malformed_pc = request(); malformed_pc.pc = 0;
  out = 0x55667788u;
  status = lgi::checked_load32(
      fixture.arena, malformed_pc, kLiveSp, invalid_pc_consumer,
      [&](const void*) {
        ++invalid_pc_backend;
        return lgi::BackendResult::Success(0);
      }, out);
  expect(status == lgi::AccessStatus::unsupported && !invalid_pc_consumers &&
             !invalid_pc_backend && out == 0x55667788u,
         "malformed guest PC is rejected before consumer and backend effects");

  const std::array<lgi::Consumer, 1> rejecting{{
      [](const auto&, uintptr_t) { return lgi::ConsumerResult::Reject(); }}};
  out = 0xcccccccc;
  status = lgi::checked_load32(fixture.arena, request(), kLiveSp, rejecting,
                               success_backend(1, &backend_calls), out);
  expect(status == lgi::AccessStatus::rejected && out == 0xcccccccc &&
             backend_calls == 2,
         "consumer rejection has no memory access side effect");

  for (unsigned bad = 0; bad != 3; ++bad) {
    auto rejected_backend = [&](const void* address) {
      return lgi::BackendResult::Fault(
          reinterpret_cast<uintptr_t>(address) + (bad == 0 ? 4u : 0u),
          fixture.arena.admitted_read_site + (bad == 1 ? 1u : 0u), bad != 2);
    };
    out = 0xdddddddd;
    status = lgi::checked_load32(fixture.arena, request(), kLiveSp,
                                 no_consumers, rejected_backend, out);
    expect(status == lgi::AccessStatus::rejected && out == 0xdddddddd,
           "wrong address/site/admission fault metadata is rejected");
  }
  unsigned forbidden_effects = 0;
  const lgi::Backend forbidden_backend = [&](const void*) {
    ++forbidden_effects;
    return lgi::BackendResult::Success(0);
  };
  for (auto operation : {lgi::Operation::write, lgi::Operation::atomic,
                         lgi::Operation::execute}) {
    auto access = request(); access.operation = operation;
    out = 0xdddddddd;
    expect(lgi::checked_load32(fixture.arena, access, kLiveSp, no_consumers,
                              forbidden_backend, out) == lgi::AccessStatus::unsupported &&
           out == 0xdddddddd, "all unsupported operation classes preserve output");
  }
  for (uint32_t width : {0u, 1u, 2u, 8u, 16u}) {
    auto access = request(); access.width = width;
    expect(lgi::checked_load32(fixture.arena, access, kLiveSp, no_consumers,
                              forbidden_backend, out) == lgi::AccessStatus::unsupported,
           "unsupported access width rejected");
  }
  auto malformed_arena = fixture.arena;
  malformed_arena.page_size = 6;
  expect(lgi::checked_load32(malformed_arena, request(), kLiveSp, no_consumers,
                            forbidden_backend, out) == lgi::AccessStatus::unsupported,
         "non-power-of-two page declaration rejected");
  malformed_arena = fixture.arena;
  malformed_arena.bytes = std::span<uint8_t>(fixture.bytes).subspan(1);
  expect(lgi::checked_load32(malformed_arena, request(), kLiveSp, no_consumers,
                            forbidden_backend, out) == lgi::AccessStatus::unsupported,
         "host-unaligned translation rejected");
  expect(forbidden_effects == 0, "invalid operation/translation executes no backend");
}

void test_fault_negative_fresh_call_and_invalid_accesses() {
  Fixture fixture;
  PPCContext state = new_context();
  unsigned filters = 0, cleanups = 0, backend_calls = 0;
  bool repaired = false;
  std::vector<pgeh::Scope> scopes;
  scopes.push_back({kPc - 4, kPc + 4, 0, {}, [&](auto&, uint32_t) {
                      ++cleanups;
                    }});
  scopes.push_back({kPc - 4, kPc + 4, kLabel,
      lgi::wrap_filter([&](PPCContext& visible, const auto& record, uint32_t) {
        ++filters;
        expect(record.code == lgi::kGuestAccessViolation &&
                   record.address == kPc && visible.r3.u32 ==
                       lgi::scratch_sp(kLiveSp) + 0x70,
               "fault filter receives M4 guest exception metadata");
        repaired = true;
        return -1;
      }), {}});
  pgeh::Owner owner(state, std::move(scopes));
  owner.declare_label(kLabel);
  const std::array<lgi::Consumer, 0> consumers{};
  const uintptr_t host = reinterpret_cast<uintptr_t>(fixture.bytes.data() + kEa);
  auto backend = [&](const void*) {
    ++backend_calls;
    if (backend_calls == 1)
      return lgi::BackendResult::Fault(host, fixture.arena.admitted_read_site, true);
    return lgi::BackendResult::Success(lgi::host_to_guest_be32(0xcafebabeu));
  };
  const uint32_t label = pgeh::region(owner, [&] {
    owner.set_pc(kPc);
    owner.before_call();
    state.r1.u64 = kLiveSp;
    uint32_t out = 0xfeedfaceu;
    const auto status = lgi::checked_load32(fixture.arena, request(), kLiveSp,
                                             consumers, backend, out);
    expect(status == lgi::AccessStatus::guest_fault && out == 0xfeedfaceu &&
               repaired && filters == 1 && cleanups == 0,
           "negative continuation keeps output and owner live without cleanup");
    const auto retry = lgi::checked_load32(fixture.arena, request(), kLiveSp,
                                           consumers, backend, out);
    expect(retry == lgi::AccessStatus::success && out == 0xcafebabeu &&
               backend_calls == 2,
           "repair retry is a distinct checked call with one backend attempt");

    auto operation = request(0x3fffcu);
    expect(lgi::checked_load32(fixture.arena, operation, kLiveSp, consumers,
                               backend, out) == lgi::AccessStatus::success &&
               out == 0xcafebabeu,
           "last fully contained four-byte read is accepted");

    out = 0x13572468u;
    operation = request();
    operation.operation = lgi::Operation::write;
    expect(lgi::checked_load32(fixture.arena, operation, kLiveSp, consumers,
                               backend, out) == lgi::AccessStatus::unsupported &&
               out == 0x13572468u,
           "writes are rejected without side effects");
    operation = request(); operation.width = 8;
    expect(lgi::checked_load32(fixture.arena, operation, kLiveSp, consumers,
                               backend, out) == lgi::AccessStatus::unsupported,
           "non-four-byte widths are rejected");
    operation = request(); operation.effective_address++;
    expect(lgi::checked_load32(fixture.arena, operation, kLiveSp, consumers,
                               backend, out) == lgi::AccessStatus::unsupported,
           "unaligned reads are rejected");
    operation = request(); operation.operation = lgi::Operation::atomic;
    expect(lgi::checked_load32(fixture.arena, operation, kLiveSp, consumers,
                               backend, out) == lgi::AccessStatus::unsupported,
           "atomic operations are rejected");
    operation = request(0x40000u);
    expect(lgi::checked_load32(fixture.arena, operation, kLiveSp, consumers,
                               backend, out) == lgi::AccessStatus::rejected,
      "access beginning at arena end is rejected");
    operation = request(4094);
    expect(lgi::checked_load32(fixture.arena, operation, kLiveSp, consumers,
                               backend, out) == lgi::AccessStatus::unsupported,
           "unaligned cross-page four-byte access is unsupported");
  });
  expect(label == 0 && filters == 1 && cleanups == 0,
         "negative path returns in the same owner invocation");
}

void test_accepted_cross_owner_transfer() {
  Fixture fixture;
  PPCContext state = new_context();
  std::vector<std::string> order;
  std::vector<pgeh::Scope> outer_scopes;
  outer_scopes.push_back({kPc - 4, kPc + 4, 0, {}, [&](auto&, uint32_t) {
                            order.emplace_back("outer-finally");
                          }});
  outer_scopes.push_back({kPc - 4, kPc + 4, kLabel,
      lgi::wrap_filter([&](PPCContext& visible, const auto& record,
                           uint32_t establisher) {
        expect(record.address == kPc && visible.r4.u32 == kOwnerSp &&
                   visible.r12.u32 == kOwnerSp && establisher == kOwnerSp,
               "outer filter receives owner establisher");
        return 1;
      }), {}});
  const std::array<lgi::Consumer, 0> consumers{};
  const uintptr_t fault_address =
      reinterpret_cast<uintptr_t>(fixture.bytes.data() + kEa);
  auto backend = [&](const void*) {
    return lgi::BackendResult::Fault(fault_address,
                                     fixture.arena.admitted_read_site, true);
  };
  {
    pgeh::Owner outer(state, std::move(outer_scopes));
    outer.declare_label(kLabel);
    const uint32_t selected = pgeh::region(outer, [&] {
      outer.set_pc(kPc);
      outer.before_call();
      state.r1.u64 = 0x32000u;
      std::vector<pgeh::Scope> inner_scopes;
      inner_scopes.push_back({kPc - 4, kPc + 4, 0, {}, [&](auto&, uint32_t) {
                                order.emplace_back("inner-finally");
                              }});
      pgeh::Owner inner(state, std::move(inner_scopes));
      (void)pgeh::region(inner, [&] {
        inner.set_pc(kPc);
        inner.before_call();
        state.r1.u64 = kLiveSp;
        struct HostCleanup {
          std::vector<std::string>& order;
          ~HostCleanup() { order.emplace_back("host-destructor"); }
        } host_cleanup{order};
        uint32_t out = 0xfeedfaceu;
        const auto status = lgi::checked_load32(fixture.arena, request(), kLiveSp,
                                                 consumers, backend, out);
        expect(status == lgi::AccessStatus::guest_fault && out == 0xfeedfaceu,
               "accepted transfer starts from admitted guest fault");
      });
    });
    expect(selected == kLabel,
           "accepted transfer returns same outer invocation label");
    expect(order == std::vector<std::string>{"host-destructor", "inner-finally",
                                             "outer-finally"},
           "host destruction precedes ordered cross-owner guest cleanup");
    expect(lgi::current_delivery == nullptr && !lgi::access_dispatch_active,
           "transfer clears delivery and dispatch state");
  }
  expect(pgeh::Owner::top() == nullptr, "transfer unregisters every owner");
}

void test_host_exception_and_thread_local_owners() {
  {
    Fixture fixture;
    PPCContext state = new_context();
    unsigned cleanups = 0;
    std::vector<pgeh::Scope> scopes;
    scopes.push_back({kPc - 4, kPc + 4, 0, {}, [&](auto&, uint32_t) {
                        ++cleanups;
                      }});
    scopes.push_back({kPc - 4, kPc + 4, kLabel,
        lgi::wrap_filter([](PPCContext&, const auto&, uint32_t) -> int {
          throw std::runtime_error("synthetic host exception");
        }), {}});
    pgeh::Owner owner(state, std::move(scopes));
    owner.declare_label(kLabel);
    bool caught = false;
    try {
      (void)pgeh::region(owner, [&] {
        owner.set_pc(kPc);
        owner.before_call();
        state.r1.u64 = kLiveSp;
        lgi::deliver(fixture.arena, kLiveSp, [] {
          lgf::Record record{};
          record.code = lgi::kGuestAccessViolation;
          record.pc = kPc;
          record.count = 2;
          record.info[1] = kEa;
          return record;
        }());
      });
    } catch (const std::runtime_error&) {
      caught = true;
    }
    expect(caught && cleanups == 1 && lgi::current_delivery == nullptr,
           "host C++ exception runs cleanup and clears delivery");
  }
  expect(pgeh::Owner::top() == nullptr,
         "host exception leaves no registered owner");

  std::atomic<unsigned> thread_passes{0};
  std::barrier rendezvous(2);
  auto thread_body = [&](uint32_t ea) {
    Fixture fixture;
    PPCContext state = new_context();
    std::vector<pgeh::Scope> scopes;
    scopes.push_back({kPc - 4, kPc + 4, kLabel,
        lgi::wrap_filter([&](PPCContext& visible, const auto&, uint32_t) {
          rendezvous.arrive_and_wait();
          const uint32_t scratch = lgi::scratch_sp(kLiveSp);
          if (visible.r3.u32 == scratch + 0x70 &&
              lgi::current_delivery &&
              lgi::current_delivery->record.info[1] == ea)
            ++thread_passes;
          return -1;
        }), {}});
    pgeh::Owner owner(state, std::move(scopes));
    owner.declare_label(kLabel);
    (void)pgeh::region(owner, [&] {
      owner.set_pc(kPc);
      owner.before_call();
      state.r1.u64 = kLiveSp;
      lgf::Record record{};
      record.code = lgi::kGuestAccessViolation;
      record.pc = kPc;
      record.count = 2;
      record.info[1] = ea;
      lgi::deliver(fixture.arena, kLiveSp, record);
    });
  };
  std::thread first(thread_body, 0x5000u);
  std::thread second(thread_body, 0x6000u);
  first.join();
  second.join();
  expect(thread_passes == 2,
         "two threads retain separate owner and delivery state");
}

}  // namespace

int main() {
  test_record_layout_and_restore();
  test_preflight_rejections_are_write_free();
  test_checked_access_and_consumers();
  test_fault_negative_fresh_call_and_invalid_accesses();
  test_accepted_cross_owner_transfer();
  test_host_exception_and_thread_local_owners();
  if (failures.load()) return 2;
  std::printf("BRIDGE_TESTS PASS checks=%u\n", checks.load());
  return 0;
}

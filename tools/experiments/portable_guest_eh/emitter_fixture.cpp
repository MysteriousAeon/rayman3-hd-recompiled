// Synthetic emitter fixture over the pinned SDK PPCContext. Never used by production.
#include "bridge.h"
#include "exception_core.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cfenv>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <new>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
using pgeh::Adapter;
using pgeh::Finally;
using pgeh::Filter;
using pgeh::GuestRecord;
using pgeh::Owner;
using pgeh::Scope;
using State = Adapter::State;

constexpr uint32_t kM4Owners = 103;
constexpr uint32_t kM4Scopes = 114;
constexpr uint32_t kM4InlineBodies = 37;
constexpr std::array<uint32_t, 4> kM4Destinations{
    0x822FDC00u, 0x826BA700u, 0x826C2A40u, 0x826C5948u};
static_assert(kM4Owners == 103 && kM4Scopes == 114 && kM4InlineBodies == 37);

int checks = 0;
void check(bool condition, const char* message) {
  ++checks;
  if (!condition) throw std::runtime_error(std::string("check ") + std::to_string(checks) + ": " + message);
}
void expect_unsupported(const std::function<void()>& action) {
  bool rejected = false;
  try { action(); } catch (const pgeh::Unsupported&) { rejected = true; }
  check(rejected, "unsupported continuation must fail explicitly");
}

std::array<PPCRegister*, 32> gprs(State& s) {
  return {&s.r0, &s.r1, &s.r2, &s.r3, &s.r4, &s.r5, &s.r6, &s.r7, &s.r8, &s.r9, &s.r10, &s.r11, &s.r12, &s.r13, &s.r14, &s.r15, &s.r16, &s.r17, &s.r18, &s.r19, &s.r20, &s.r21, &s.r22, &s.r23, &s.r24, &s.r25, &s.r26, &s.r27, &s.r28, &s.r29, &s.r30, &s.r31};
}
std::array<PPCRegister*, 32> fprs(State& s) {
  return {&s.f0, &s.f1, &s.f2, &s.f3, &s.f4, &s.f5, &s.f6, &s.f7, &s.f8, &s.f9, &s.f10, &s.f11, &s.f12, &s.f13, &s.f14, &s.f15, &s.f16, &s.f17, &s.f18, &s.f19, &s.f20, &s.f21, &s.f22, &s.f23, &s.f24, &s.f25, &s.f26, &s.f27, &s.f28, &s.f29, &s.f30, &s.f31};
}
std::array<PPCCRRegister*, 8> crs(State& s) {
  return {&s.cr0, &s.cr1, &s.cr2, &s.cr3, &s.cr4, &s.cr5, &s.cr6, &s.cr7};
}
std::array<PPCVRegister*, 128> vectors(State& s) {
  return {&s.v0, &s.v1, &s.v2, &s.v3, &s.v4, &s.v5, &s.v6, &s.v7, &s.v8, &s.v9, &s.v10, &s.v11, &s.v12, &s.v13, &s.v14, &s.v15, &s.v16, &s.v17, &s.v18, &s.v19, &s.v20, &s.v21, &s.v22, &s.v23, &s.v24, &s.v25, &s.v26, &s.v27, &s.v28, &s.v29, &s.v30, &s.v31, &s.v32, &s.v33, &s.v34, &s.v35, &s.v36, &s.v37, &s.v38, &s.v39, &s.v40, &s.v41, &s.v42, &s.v43, &s.v44, &s.v45, &s.v46, &s.v47, &s.v48, &s.v49, &s.v50, &s.v51, &s.v52, &s.v53, &s.v54, &s.v55, &s.v56, &s.v57, &s.v58, &s.v59, &s.v60, &s.v61, &s.v62, &s.v63, &s.v64, &s.v65, &s.v66, &s.v67, &s.v68, &s.v69, &s.v70, &s.v71, &s.v72, &s.v73, &s.v74, &s.v75, &s.v76, &s.v77, &s.v78, &s.v79, &s.v80, &s.v81, &s.v82, &s.v83, &s.v84, &s.v85, &s.v86, &s.v87, &s.v88, &s.v89, &s.v90, &s.v91, &s.v92, &s.v93, &s.v94, &s.v95, &s.v96, &s.v97, &s.v98, &s.v99, &s.v100, &s.v101, &s.v102, &s.v103, &s.v104, &s.v105, &s.v106, &s.v107, &s.v108, &s.v109, &s.v110, &s.v111, &s.v112, &s.v113, &s.v114, &s.v115, &s.v116, &s.v117, &s.v118, &s.v119, &s.v120, &s.v121, &s.v122, &s.v123, &s.v124, &s.v125, &s.v126, &s.v127};
}

State seeded() {
  State s{};
  auto gi = gprs(s); auto fi = fprs(s); auto ci = crs(s); auto vi = vectors(s);
  for (size_t i = 0; i < gi.size(); ++i) gi[i]->u64 = 0x1000u + i;
  for (size_t i = 0; i < fi.size(); ++i) fi[i]->u64 = 0x2000u + i;
  for (size_t i = 0; i < ci.size(); ++i) ci[i]->set_raw(uint32_t(i * 3));
  for (size_t i = 0; i < vi.size(); ++i) {
    vi[i]->u64[0] = 0x3000u + i;
    vi[i]->u64[1] = 0x4000u + i;
  }
  s.lr = 0x55667788u; s.ctr.u64 = 0x12345678u;
  s.xer = {1, 0, 1}; s.reserved.u64 = 0xabcdefu;
  s.msr = 0x200a000u; s.vscr_sat = 1; s.last_indirect_target = 0x87654321u;
  s.r1.u64 = 0x10000u;
  s.fpscr.InitHost();
  return s;
}

void mutate(State& s) {
  auto gi = gprs(s); auto fi = fprs(s); auto ci = crs(s); auto vi = vectors(s);
  for (auto* r : gi) r->u64 ^= 0x11111111u;
  for (auto* r : fi) r->u64 ^= 0x22222222u;
  for (auto* r : ci) r->set_raw(r->raw() ^ 0xfu);
  for (auto* r : vi) { r->u64[0] ^= 0x33333333u; r->u64[1] ^= 0x44444444u; }
  s.lr ^= 0x13579bdfu; s.ctr.u64 ^= 0x2468ace0u;
  s.xer.so ^= 1; s.xer.ov ^= 1; s.xer.ca ^= 1;
  s.reserved.u64 ^= 0x55aa55aau; s.msr ^= 0x80000000u;
  s.vscr_sat ^= 1; s.last_indirect_target ^= 0xdeadbeefu;
  s.fpscr.csr ^= 0x1234u;
}

bool same_context(const State& a, const State& b) {
  auto ag = gprs(const_cast<State&>(a)); auto bg = gprs(const_cast<State&>(b));
  auto af = fprs(const_cast<State&>(a)); auto bf = fprs(const_cast<State&>(b));
  auto ac = crs(const_cast<State&>(a)); auto bc = crs(const_cast<State&>(b));
  auto av = vectors(const_cast<State&>(a)); auto bv = vectors(const_cast<State&>(b));
  for (size_t i = 0; i < ag.size(); ++i) if (ag[i]->u64 != bg[i]->u64) return false;
  for (size_t i = 0; i < af.size(); ++i) if (af[i]->u64 != bf[i]->u64) return false;
  for (size_t i = 0; i < ac.size(); ++i) if (ac[i]->raw() != bc[i]->raw()) return false;
  for (size_t i = 0; i < av.size(); ++i)
    if (av[i]->u64[0] != bv[i]->u64[0] || av[i]->u64[1] != bv[i]->u64[1]) return false;
  return a.lr == b.lr && a.ctr.u64 == b.ctr.u64 && a.xer.so == b.xer.so &&
      a.xer.ov == b.xer.ov && a.xer.ca == b.xer.ca && a.reserved.u64 == b.reserved.u64 &&
      a.msr == b.msr && a.vscr_sat == b.vscr_sat &&
      a.last_indirect_target == b.last_indirect_target && a.fpscr.csr == b.fpscr.csr;
}

void test_real_adapter() {
  State s = seeded();
  const auto owner = Adapter::capture_owner(s);
  const uint32_t saved_host_csr = PPCFPSCRRegister::Platform::getcsr();
  const uint32_t guest_mask = PPCFPSCRRegister::GuestMask;
  s.fpscr.storeFromGuest(rex::ppc::kRoundUp);
  const uint32_t changed_host_csr = PPCFPSCRRegister::Platform::getcsr();
  mutate(s);
  Adapter::restore_owner(s, owner);
  const auto restored = Adapter::capture_owner(s);
  check(std::equal(owner.regs.begin(), owner.regs.end() - sizeof(uint32_t), restored.regs.begin()),
        "real SDK nonvolatile image (GPR/FPR/VMX/CR)");
  check(s.r1.u64 == owner.r1.u64 && s.r2.u64 == owner.r2.u64 && s.r13.u64 == owner.r13.u64,
        "M4 supplemental r1/r2/r13");
  const uint32_t csr = PPCFPSCRRegister::Platform::getcsr();
  check((csr & guest_mask) == (saved_host_csr & guest_mask), "guest-owned FPSCR bits restored");
  check((csr & ~guest_mask) == (changed_host_csr & ~guest_mask),
        "host FPSCR policy retained by owner restore");

  const auto full = Adapter::capture_full(s);
  const int host_round = std::fegetround();
  mutate(s);
  (void)std::fesetround(host_round == FE_DOWNWARD ? FE_UPWARD : FE_DOWNWARD);
  PPCFPSCRRegister::Platform::setcsr(PPCFPSCRRegister::Platform::getcsr() ^ guest_mask);
  Adapter::restore_full(s, full);
  check(same_context(s, full.state), "full real PPCContext rollback");
  check(std::fegetround() == host_round, "host fenv rounding restored independently");
  check(PPCFPSCRRegister::Platform::getcsr() == full.host_csr, "host CSR restored independently");
}

void test_filter_rollback_and_live_negative() {
  State s = seeded();
  const State before = s;
  std::vector<int> events;
  int guest_memory_effect = 0, destroyed = 0;
  Owner owner(s, {
    {10, 20, 30, [&](State& ctx, const GuestRecord& rec, uint32_t establisher) {
      events.push_back(1);
      ++guest_memory_effect; // Memory effects survive register rollback.
      check(rec.code == 0x1234 && rec.address == 15, "guest record routed to filter");
      check(ctx.r31.u64 == before.r31.u64, "filter sees owner nonvolatile state");
      check(ctx.r4.u32 == establisher && ctx.r12.u32 == establisher, "establisher in r4/r12");
      check(ctx.r1.u32 < 0xf000, "filter scratch below live faulting stack");
      mutate(ctx);
      (void)std::fesetround(FE_DOWNWARD);
      return -1;
    }, {}}
  });
  owner.declare_label(30); owner.set_pc(15); owner.before_call();
  s.r1.u64 = 0xf000; s.r31.u64 = 0xbadf00d;
  const State live = s;
  const int round = std::fegetround();
  const int destination = pgeh::region(owner, [&] {
    struct CalleeLifetime { int& count; ~CalleeLifetime() { ++count; } } sentinel{destroyed};
    pgeh::raise({0x1234, 0, 15});
    check(destroyed == 0, "negative continuation keeps faulting callee alive");
    check(same_context(s, live), "negative filter continues at the raise callsite");
  });
  check(destination == 0, "negative disposition does not enter handler");
  check(same_context(s, live), "filter edits fully rolled back");
  check(std::fegetround() == round, "filter host rounding rolled back");
  check(events == std::vector<int>{1}, "filter called once");
  check(destroyed == 1 && guest_memory_effect == 1, "normal callee destruction and retained memory effect");
}

void test_scope_order_cleanup_stack_and_unsupported_funclets() {
  State s = seeded();
  std::vector<int> events;
  {
    Owner owner(s, {
      {12, 16, 0, {}, [&](State& ctx, uint32_t) {
        check(ctx.r1.u32 == 0xfb00, "cleanup scratch uses restored prologue stack");
        events.push_back(3);
      }},
      {12, 16, 30, [&](State&, const GuestRecord&, uint32_t) { events.push_back(1); return 0; }, {}},
      {10, 20, 40, [&](State&, const GuestRecord&, uint32_t) { events.push_back(2); return 1; }, {}},
      {10, 20, 0, {}, [&](State&, uint32_t) { events.push_back(99); }}
    });
    owner.declare_label(30); owner.declare_label(40); owner.set_pc(12);
    s.r1.u64 = 0xff00; owner.before_call(); s.r1.u64 = 0xf000;
    check(pgeh::region(owner, [] { pgeh::raise({1, 0, 12}); }) == 40, "scope beginning included");
    check(events == std::vector<int>({1, 2, 3}), "same-owner innermost-first search and cleanup index limit");
    check(s.r1.u32 == 0xff00, "owner stack restored at accepted label");
  }
  {
    int normal_cleanups = 0;
    Owner owner(s, {{10, 20, 0, {}, [&](State&, uint32_t) { ++normal_cleanups; }}});
    owner.set_pc(12);
    check(pgeh::region(owner, [&] { ++normal_cleanups; }) == 0 && normal_cleanups == 1,
          "compiled normal cleanup is not duplicated");
  }
  for (bool cleanup_case : {false, true}) {
    State live = seeded();
    auto nested_raise = [&](State& ctx) { mutate(ctx); pgeh::raise({2, 0, 12}); };
    // Keep table construction explicit: GCC may diagnose conditional vector
    // initializer-list temporaries as dangling even though Owner owns the table.
    std::vector<Scope> scopes;
    if (cleanup_case) {
      scopes.push_back({10, 20, 0, {}, [&](State& ctx, uint32_t) { nested_raise(ctx); }});
    } else {
      scopes.push_back({10, 20, 30, [&](State& ctx, const GuestRecord&, uint32_t) { nested_raise(ctx); return 1; }, {}});
    }
    Owner owner(live, std::move(scopes));
    owner.declare_label(30); owner.set_pc(12);
    const State before = live;
    expect_unsupported([&] { pgeh::region(owner, [] { pgeh::raise({1, 0, 12}); }); });
    check(same_context(live, before) && !pgeh::in_funclet, "unsupported nested funclet raise restores state and guard");
  }
}

void test_nested_search_and_inline_handler() {
  State s = seeded();
  std::vector<int> events;
  constexpr uint32_t kInline = 0x826BA700u;
  Owner outer(s, {
    {10, 20, 0, {}, [&](State& ctx, uint32_t) {
      check(ctx.r3.u32 == 1, "AbnormalTermination passed as true");
      events.push_back(3);
    }},
    {10, 20, kInline, [&](State& ctx, const GuestRecord&, uint32_t) {
      events.push_back(2); check(ctx.r31.u64 == 0x1000u + 31, "outer owner restored for filter");
      return 1;
    }, {}}
  });
  outer.declare_label(kInline); outer.set_pc(15); outer.before_call();
  const uint32_t destination = pgeh::region(outer, [&] {
    Owner inner(s, {
      {10, 20, 0, {}, [&](State& ctx, uint32_t) {
        check(ctx.r3.u32 == 1, "inner abnormal cleanup");
        events.push_back(4);
      }},
      {10, 20, 0x99u, [&](State&, const GuestRecord&, uint32_t) {
        events.push_back(1); return 0;
      }, {}}
    });
    inner.declare_label(0x99u); inner.set_pc(15); inner.before_call();
    mutate(s); s.r1.u64 = 0xe000;
    const uint32_t inner_destination = pgeh::region(inner, [&] { pgeh::raise({0x55, 0, 15}); });
    check(inner_destination == 0, "outer acceptance propagates through inner owner");
    check(false, "raise should transfer to outer owner");
  });

  // Synthetic emitted switch: the body remains an inline label of this owner.
  switch (destination) {
    case kInline:
      events.push_back(5); outer.set_pc(kInline);
      break;
    default:
      check(false, "owner-local continuation label selected");
  }
  check(events == std::vector<int>({1, 2, 4, 3, 5}), "search precedes ordered finally and inline body");
  check(s.r31.u64 == 0x1000u + 31 && s.r1.u64 == 0x10000u, "owner nonvolatiles and stack restored");
}

void test_scope_boundary_and_host_exception() {
  State s = seeded();
  int cleanup = 0, filters = 0;
  {
    Owner owner(s, {
      {10, 12, 0, {}, [&](State&, uint32_t) { ++cleanup; }},
      {10, 12, 50, [&](State&, const GuestRecord&, uint32_t) { ++filters; return 1; }, {}}
    });
    owner.declare_label(50); owner.set_pc(12);
    bool unhandled = false;
    try { pgeh::region(owner, [&] { pgeh::raise({1, 0, 12}); }); }
    catch (const pgeh::Unhandled&) { unhandled = true; }
    check(unhandled && filters == 0 && cleanup == 0, "scope end is excluded");
  }
  {
    Owner owner(s, {
      {10, 20, 0, {}, [&](State& ctx, uint32_t) {
        ++cleanup; mutate(ctx); (void)std::fesetround(FE_DOWNWARD);
      }},
      {10, 20, 30, [&](State&, const GuestRecord&, uint32_t) { ++filters; return 1; }, {}}
    });
    owner.declare_label(30); owner.set_pc(12);
    const State prior = s;
    const int prior_round = std::fegetround();
    bool host = false;
    try {
      pgeh::region(owner, [] { throw std::runtime_error("host failure"); });
    } catch (const std::runtime_error&) { host = true; }
    check(host && filters == 0 && cleanup == 1, "host exception is never reclassified as guest");
    check(same_context(s, prior) && std::fegetround() == prior_round,
          "cleanup funclet rolls back real PPC state and host environment");
  }
}

void test_noncontinuable_and_four_destinations() {
  State s = seeded();
  Owner outer(s, {{10, 20, 70, [](State&, const GuestRecord&, uint32_t) { return 1; }, {}}});
  outer.declare_label(70); outer.set_pc(15);
  const auto dest = pgeh::region(outer, [&] {
    Owner inner(s, {
      {10, 20, 80, [](State&, const GuestRecord&, uint32_t) { return -1; }, {}},
      {10, 20, 90, [](State&, const GuestRecord&, uint32_t) { check(false, "later inner filter skipped"); return 1; }, {}}
    });
    inner.declare_label(80); inner.declare_label(90); inner.set_pc(15);
    pgeh::region(inner, [&] { pgeh::raise({1, pgeh::kNoncontinuable, 15}); });
    check(false, "noncontinuable search continues to outer owner");
  });
  check(dest == 70, "outer owner accepts noncontinuable exception");

  check(kM4Owners == 103 && kM4Scopes == 114 && kM4InlineBodies == 37 &&
        kM4Destinations.size() == 4, "M4 census carried into fixture");
  for (uint32_t target : kM4Destinations) {
    Owner owner(s, {});
    for (uint32_t label : kM4Destinations) owner.declare_label(label);
    const uint32_t result = pgeh::region(owner, [&] { pgeh::request_unwind(owner.id(), target, 0xfeed); });
    check(result == target && s.r3.u32 == 0xfeed, "recorded same-frame destination");
  }
}

void test_explicit_unwind_retained_scopes_and_forgery() {
  State s = seeded();
  std::vector<int> events;
  Owner owner(s, {
    {100, 200, 0, {}, [&](State&, uint32_t) { events.push_back(1); }},
    {0, 0xffffffffu, 0, {}, [&](State&, uint32_t) { events.push_back(2); }},
    {100, 200, 60, [&](State&, const GuestRecord&, uint32_t) { check(false, "unwind skips filters"); return 1; }, {}}
  });
  owner.declare_label(0x822fdc00u); owner.set_pc(150); owner.before_call();
  const uint32_t result = pgeh::region(owner, [&] { pgeh::request_unwind(owner.id(), 0x822fdc00u, 0x77); });
  check(result == 0x822fdc00u && s.r3.u32 == 0x77, "unwind label and return value");
  check(events == std::vector<int>{1}, "destination-containing scope retained, exited scope cleaned");

  events.clear();
  Owner forged(s, {{1, 50, 0, {}, [&](State&, uint32_t) { events.push_back(9); }},
    {1, 50, 30, [](State&, const GuestRecord&, uint32_t) { return 1; }, {}}});
  forged.declare_label(30); forged.set_pc(10);
  expect_unsupported([&] {
    pgeh::region(forged, [&] {
      throw pgeh::Transfer{pgeh::Transfer::Kind::handler, forged.id(), 30, 0, 0, nullptr};
    });
  });
  check(events.empty(), "forged scope limit rejected before cleanup");
  expect_unsupported([&] { pgeh::request_unwind(forged.id(), 999, 0); });
}

void test_checkpoint_semantics_and_stale_owner() {
  State s = seeded();
  std::vector<int> events;
  constexpr uint32_t kResume = 0x826C2A40u;
  std::optional<pgeh::Checkpoint> stale;
  {
    Owner owner(s, {
      {100, 200, 0, {}, [&](State&, uint32_t) { events.push_back(2); }},
      {0, 0xffffffffu, 0, {}, [&](State&, uint32_t) { events.push_back(9); }}
    });
    owner.declare_label(kResume); owner.set_pc(150); owner.before_call();
    const auto checkpoint = pgeh::save_checkpoint(owner, kResume);
    stale = checkpoint;
    const State saved = s;
    const uint32_t destination = pgeh::region(owner, [&] {
      Owner inner(s, {{100, 200, 0, {}, [&](State&, uint32_t) { events.push_back(1); }}});
      inner.set_pc(150); inner.before_call();
      pgeh::region(inner, [&] { mutate(s); pgeh::resume_checkpoint(checkpoint, 0); });
      check(false, "checkpoint transfer");
    });
    check(destination == kResume, "checkpoint returns to saved owner label");
    owner.set_pc(kResume);
    State expected = saved; expected.r3.u64 = 1; // setjmp/longjmp zero result is one.
    check(same_context(s, expected), "checkpoint restores guest state and normalizes zero");
    check(events == std::vector<int>({1, 2}), "intervening cleanup once; retained owner scope");
    const uint32_t second = pgeh::region(owner, [&] { pgeh::resume_checkpoint(checkpoint, 5); });
    check(second == kResume && s.r3.u32 == 5, "live checkpoint can resume again with new value");
    check(events == std::vector<int>({1, 2}), "no duplicated cleanup on same destination");
  }
  expect_unsupported([&] { pgeh::resume_checkpoint(*stale, 1); });

  alignas(Owner) std::byte storage[sizeof(Owner)];
  Owner* first = std::construct_at(reinterpret_cast<Owner*>(storage), s, std::vector<Scope>{});
  first->declare_label(40);
  const auto old_id = first->id();
  const auto old_checkpoint = pgeh::save_checkpoint(*first, 40);
  std::destroy_at(first);
  Owner* second = std::construct_at(reinterpret_cast<Owner*>(storage), s, std::vector<Scope>{});
  second->declare_label(40);
  check(second->id() != old_id, "invocation generation prevents stack-address ABA");
  expect_unsupported([&] { pgeh::request_unwind(old_id, 40, 0); });
  expect_unsupported([&] { pgeh::resume_checkpoint(old_checkpoint, 1); });
  std::destroy_at(second);
  {
    Owner outer(s, {}); outer.declare_label(40);
    expect_unsupported([&] { outer.declare_label(0); });
    State other = seeded();
    expect_unsupported([&] { Owner invalid_context(other, {}); });
    Owner inner(s, {});
    expect_unsupported([&] { (void)pgeh::save_checkpoint(outer, 40); });
  }
}

void test_thread_isolation_and_bridge() {
  State s = seeded();
  Owner main_owner(s, {{10, 20, 30, [](State&, const GuestRecord&, uint32_t) { return 1; }, {}}});
  main_owner.declare_label(30); main_owner.set_pc(15);
  const auto checkpoint = pgeh::save_checkpoint(main_owner, 30);
  std::atomic<bool> isolated{false};
  std::thread worker([&] {
    isolated = Owner::find(main_owner.id()) == nullptr;
    try { pgeh::request_unwind(main_owner.id(), 30, 0); }
    catch (const pgeh::Unsupported&) { isolated = isolated && Owner::top() == nullptr; }
    bool checkpoint_rejected = false;
    try { pgeh::resume_checkpoint(checkpoint, 1); }
    catch (const pgeh::Unsupported&) { checkpoint_rejected = true; }
    State thread_state = seeded(); Owner thread_owner(thread_state, {});
    isolated = isolated && checkpoint_rejected && Owner::find(thread_owner.id()) == &thread_owner;
  });
  worker.join();
  check(isolated.load(), "owner IDs are thread-local");

  const unsigned before = pgeh_bridge_unwind_count();
  bool rethrown = false;
  const uint32_t destination = pgeh::region(main_owner, [&] {
    try { pgeh_bridge([](void*) { pgeh::raise({0xface, 0, 15}); }, nullptr); }
    catch (...) { rethrown = true; throw; }
  });
  check(destination == 30, "typed owner transfer crosses a shared-library boundary");
  check(rethrown && pgeh_bridge_unwind_count() == before + 1, "DSO frame destruction and catch/rethrow boundary");
}

void test_aligned_checkpoint_payload_lifetime() {
  State state = seeded();
  Owner owner(state, {}); owner.declare_label(40); owner.set_pc(12);
  std::optional<pgeh::Checkpoint> source = pgeh::save_checkpoint(owner, 40);
  const State expected_state = state;
  const auto expected_fp = Adapter::capture_full(state);
  std::weak_ptr<const pgeh::Checkpoint> payload;
  bool source_destroyed = false;
  const auto unwinds = pgeh_bridge_unwind_count();
  const auto destination = pgeh::region(owner, [&] {
    Owner inner(state, {}); inner.set_pc(12);
    pgeh::region(inner, [&] {
      try {
        pgeh_bridge([](void* opaque) {
          auto& original = *static_cast<std::optional<pgeh::Checkpoint>*>(opaque);
          pgeh::Checkpoint local = *original;
          original.reset();
          pgeh::resume_checkpoint(local, 17); // local dies during library unwind.
        }, &source);
      } catch (const pgeh::Transfer& token) {
        check(!source && token.checkpoint, "payload survives destruction of original checkpoint");
        source_destroyed = true;
        payload = token.checkpoint;
        check(reinterpret_cast<uintptr_t>(token.checkpoint.get()) % alignof(pgeh::Checkpoint) == 0,
              "heap checkpoint satisfies real PPCContext alignment");
        check(reinterpret_cast<uintptr_t>(&token) % alignof(pgeh::Transfer) == 0,
              "thrown token alignment");
        const auto owners_before_copy = token.checkpoint.use_count();
        {
          const auto copy = token;
          check(copy.checkpoint == token.checkpoint && token.checkpoint.use_count() == owners_before_copy + 1,
                "token copy shares immutable owned payload");
        }
        check(token.checkpoint.use_count() == owners_before_copy, "token copy releases payload ownership");
        mutate(state); std::fesetround(FE_DOWNWARD);
        throw;
      }
    });
  });
  State expected = expected_state; expected.r3.u64 = 17;
  check(destination == 40 && source_destroyed && same_context(state, expected),
        "checkpoint crosses nested owners and DSO with full guest restore");
  check(PPCFPSCRRegister::Platform::getcsr() == expected_fp.host_csr,
        "owned checkpoint restores host CSR after rethrow");
  check(pgeh_bridge_unwind_count() == unwinds + 1 && payload.expired(),
        "DSO unwinds and payload is released after final handler");
}

void noexcept_callback(void*) { pgeh::raise({0xdead, 0, 0}); }
[[gnu::noinline]] void noexcept_barrier() noexcept {
  pgeh_bridge(noexcept_callback, nullptr);
}
}  // namespace

int main(int argc, char** argv) {
  if (argc == 2 && std::string(argv[1]) == "--noexcept-barrier") {
    std::set_terminate([] { std::_Exit(86); });
    State state = seeded();
    Owner owner(state, {{10, 20, 30, [](State&, const GuestRecord&, uint32_t) { return 1; }, {}}});
    owner.declare_label(30); owner.set_pc(15);
    noexcept_barrier();
    return 0;
  }
  if (argc == 2 && std::string(argv[1]) == "--swallow-barrier") {
    State state = seeded();
    Owner owner(state, {{10, 20, 30, [](State&, const GuestRecord&, uint32_t) { return 1; }, {}}});
    owner.declare_label(30); owner.set_pc(15);
    bool swallowed = false;
    const auto target = pgeh::region(owner, [&] {
      try { pgeh::raise({1, 0, 15}); } catch (...) { swallowed = true; }
    });
    // Focused negative reproducer: this foreign barrier violates the protocol.
    return swallowed && target == 0 ? 87 : 1;
  }
  try {
    test_real_adapter();
    test_filter_rollback_and_live_negative();
    test_scope_order_cleanup_stack_and_unsupported_funclets();
    test_nested_search_and_inline_handler();
    test_scope_boundary_and_host_exception();
    test_noncontinuable_and_four_destinations();
    test_explicit_unwind_retained_scopes_and_forgery();
    test_checkpoint_semantics_and_stale_owner();
    test_thread_isolation_and_bridge();
    test_aligned_checkpoint_payload_lifetime();
    check(Owner::top() == nullptr && !pgeh::in_funclet, "all owners and funclet guards unregistered");
    std::printf("EMITTER_FIXTURE PASS checks=%d\n", checks);
    std::printf("TRANSPORT_LAYOUT token_alignment=%zu token_size=%zu checkpoint_alignment=%zu\n",
                alignof(pgeh::Transfer), sizeof(pgeh::Transfer), alignof(pgeh::Checkpoint));
    return 0;
  } catch (const std::exception& e) {
    std::fprintf(stderr, "EMITTER_FIXTURE FAIL checks=%d error=%s\n", checks, e.what());
  } catch (...) {
    std::fprintf(stderr, "EMITTER_FIXTURE FAIL checks=%d error=unknown\n", checks);
  }
  return 1;
}

// Synthetic architecture probe only. No SDK, game data, signals or production hooks.
#include <array>
#include <cfenv>
#include <cstdint>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace probe {
struct State {
  std::array<uint64_t, 32> gpr{};
  std::array<uint64_t, 32> fpr{};
  std::array<std::array<uint64_t, 2>, 128> vr{};
  uint32_t cr{}, fpscr{};
  bool operator==(const State&) const = default;
};
struct Record { uint32_t code{}, flags{}; };
struct Frame;
struct Transfer { Frame* owner; uint32_t pc, value; size_t limit; bool explicit_unwind; };
struct Unhandled {};
struct Unsupported {};
using Funclet = std::function<int(State&)>;
struct Scope { uint32_t begin, end, target; Funclet call; };
thread_local Frame* top = nullptr;
thread_local bool in_funclet = false;
struct Frame {
  Frame* parent = top;
  State& state;
  State snapshot;
  std::vector<Scope> scopes;
  uint32_t establisher, pc = 0;
  bool in_call = false;
  std::vector<uint32_t> labels{30, 40, 60, 80, 90}; // synthetic emitted-label whitelist
  Frame(State& s, std::vector<Scope> table)
      : state(s), snapshot(s), scopes(std::move(table)), establisher(uint32_t(s.gpr[1])) { top = this; }
  ~Frame() { top = parent; }
  Frame(const Frame&) = delete;
  void before_call() { snapshot = state; in_call = true; }
  void restore_owner() {
    if (!in_call) return;
    for (int i = 14; i < 32; ++i) { state.gpr[i] = snapshot.gpr[i]; state.fpr[i] = snapshot.fpr[i]; }
    for (int i = 14; i < 128; ++i)
      if (i < 32 || i >= 64) state.vr[i] = snapshot.vr[i];
    // Synthetic cr2..cr4 packed in the same bit positions as PPC CR fields.
    state.cr = (state.cr & ~0x00fff000u) | (snapshot.cr & 0x00fff000u);
    state.fpscr = snapshot.fpscr;
    for (int i : {1, 2, 13}) state.gpr[i] = snapshot.gpr[i];
    in_call = false;
  }
};
bool active(const Scope& s, uint32_t pc) { return pc >= s.begin && pc < s.end; }
int side_call(Frame& f, const Scope& scope, bool filter) {
  State saved = f.state;
  bool was_call = f.in_call;
  int rounding = std::fegetround();
  f.restore_owner();
  // Filters use scratch below the LIVE callee stack; cleanup uses owner stack.
  if (filter) f.state.gpr[1] = saved.gpr[1];
  f.state.gpr[1] = (f.state.gpr[1] - 0x400) & ~uint64_t(15);
  f.state.gpr[3] = filter ? f.state.gpr[1] + 0x70 : 1;
  f.state.gpr[4] = f.state.gpr[12] = f.establisher;
  in_funclet = true;
  try {
    int result = scope.call(f.state);
    f.state = saved; f.in_call = was_call; in_funclet = false;
    std::fesetround(rounding);
    return result;
  } catch (...) {
    f.state = saved; f.in_call = was_call; in_funclet = false;
    std::fesetround(rounding);
    throw;
  }
}
void raise(Record record) {
  if (in_funclet) throw Unsupported{}; // M4 does not promise arbitrary nested funclet EH.
  for (Frame* f = top; f; f = f->parent) {
    for (size_t i = 0; i < f->scopes.size(); ++i) {
      const Scope& s = f->scopes[i];
      if (!s.target || !active(s, f->pc)) continue;
      int disposition = side_call(*f, s, true);
      if (disposition < 0) {
        if (record.flags & 1) break; // M4 searches the next OWNER, not the next scope.
        return; // No C++ unwind: the original raising call can return.
      }
      if (disposition > 0) throw Transfer{f, s.target, 0, i, false};
    }
  }
  throw Unhandled{};
}
void unwind(Frame* owner, uint32_t pc, uint32_t value) {
  if (in_funclet) throw Unsupported{};
  for (Frame* f = top; f; f = f->parent)
    if (f == owner) {
      for (uint32_t label : f->labels)
        if (label == pc) throw Transfer{f, pc, value, f->scopes.size(), true};
      throw Unsupported{};
    }
  throw Unsupported{};
}
void cleanup(Frame& f, const Transfer* t) {
  size_t limit = t && t->owner == &f ? t->limit : f.scopes.size();
  for (size_t i = 0; i < limit; ++i) {
    const Scope& s = f.scopes[i];
    if (s.target || !active(s, f.pc)) continue;
    if (t && t->owner == &f && t->explicit_unwind && active(s, t->pc)) continue;
    side_call(f, s, false);
  }
}
// This returns a token to the SAME invocation's label switch, never calls a body.
template<class Body> uint32_t region(Frame& f, Body body) {
  try { body(); f.in_call = false; return 0; }
  catch (const Transfer& t) {
    cleanup(f, &t);
    if (t.owner != &f) throw;
    f.restore_owner();
    if (t.explicit_unwind) f.state.gpr[3] = t.value;
    return t.pc;
  } catch (...) { cleanup(f, nullptr); throw; }
}
// Metadata admission ONLY; no claim that a host fault was captured or resumable.
bool guest_fault(uint32_t code, uintptr_t address, uintptr_t base, bool guest_site) {
  return guest_site && (code == 0xc0000005 || code == 0xc0000006) &&
         address >= base && address - base <= UINT32_MAX;
}
} // namespace probe

using namespace probe;
int checks = 0;
void check(bool value) { ++checks; if (!value) throw std::runtime_error("check " + std::to_string(checks)); }
State initial() {
  State s;
  for (size_t i = 0; i < 32; ++i) { s.gpr[i] = i + 100; s.fpr[i] = i + 200; }
  for (size_t i = 0; i < 128; ++i) s.vr[i] = {i + 300, i + 400};
  s.gpr[1] = 0x10000; s.cr = 0x12345678; s.fpscr = 42;
  return s;
}
int main() {
  try {
    std::vector<int> events;
    auto fin = [&](int id) { return [&, id](State& s) { check(s.gpr[3] == 1); events.push_back(id); return 0; }; };
    {
      State s = initial(); Frame f(s, {{10, 20, 30, [&](State& x) {
        check(x.gpr[1] == 0xec00); check(x.gpr[4] == 0x10000 && x.gpr[12] == 0x10000);
        check(x.gpr[31] == 131); x = {}; std::fesetround(FE_DOWNWARD); return -1;
      }}});
      f.pc = 12; f.before_call(); s.gpr[1] = 0xf000; s.gpr[31] = 999;
      State live = s; int rounding = std::fegetround();
      check(region(f, [&] { raise({1, 0}); check(s == live); }) == 0);
      check(std::fegetround() == rounding); check(events.empty());
      check(f.in_call == false);
    }
    check(top == nullptr);
    {
      // Boundary and table-order test: outside and outer cleanup must not run.
      State s = initial(); Frame f(s, {{0, 12, 0, fin(99)}, {12, 20, 0, fin(5)},
        {12, 20, 30, [](State&) { return 1; }}, {12, 20, 0, fin(99)}});
      f.pc = 12;
      check(region(f, [] { raise({1, 0}); }) == 30);
      check(events == std::vector<int>({5})); events.clear();
    }
    {
      State s = initial();
      Frame outer(s, {{10, 20, 0, fin(3)}, {10, 20, 90, [&](State&) { events.push_back(1); return 1; }}});
      outer.pc = 12; outer.before_call();
      uint32_t dest = region(outer, [&] {
        s.gpr[1] -= 128; s.gpr[31] = 999;
        s.gpr[2] = s.gpr[13] = 999;
        for (int i = 14; i < 32; ++i) s.fpr[i] = 999;
        for (int i = 14; i < 128; ++i)
          if (i < 32 || i >= 64) s.vr[i] = {999, 999};
        s.cr ^= 0x00fff000u; s.fpscr = 999;
        Frame inner(s, {{10, 20, 0, fin(2)}, {10, 20, 80, [&](State&) { events.push_back(0); return 0; }}});
        inner.pc = 12;
        region(inner, [&] { raise({1, 0}); check(false); });
        check(false);
      });
      check(dest == 90); check(events == std::vector<int>({0, 1, 2, 3}));
      check(s.gpr[31] == 131 && s.gpr[1] == 0x10000 && s.gpr[2] == 102 && s.gpr[13] == 113);
      check(s.fpr == initial().fpr && s.vr == initial().vr && s.cr == initial().cr && s.fpscr == 42);
      // Synthetic owner-label dispatch in this invocation.
      switch (dest) { case 90: events.push_back(4); break; default: check(false); }
      check(events.back() == 4);
    }
    events.clear();
    {
      // A noncontinuable negative skips the rest of that owner's table.
      State s = initial(); Frame outer(s, {{10, 20, 90, [](State&) { return 1; }}}); outer.pc = 12;
      check(region(outer, [&] {
        Frame inner(s, {{10, 20, 80, [](State&) { return -1; }},
          {10, 20, 30, [](State&) { check(false); return 1; }}}); inner.pc = 12;
        region(inner, [] { raise({1, 1}); });
      }) == 90);
    }
    {
      State s = initial(); Frame f(s, {{10, 20, 0, fin(1)}, {10, 20, 30, [](State&) { return -1; }}});
      f.pc = 12; bool rejected = false;
      try { region(f, [&] { raise({1, 1}); }); } catch (const Unhandled&) { rejected = true; }
      check(rejected); check(events == std::vector<int>({1}));
    }
    events.clear();
    {
      State s = initial(); Frame f(s, {{10, 20, 0, fin(1)}, {10, 50, 0, fin(2)},
        {10, 20, 60, [&](State&) { check(false); return 1; }}});
      f.pc = 12; f.before_call(); s.gpr[31] = 999;
      check(region(f, [&] { unwind(&f, 30, 7); }) == 30);
      check(events == std::vector<int>({1})); check(s.gpr[3] == 7 && s.gpr[31] == 131);
      // Re-entry clears selection: second transfer leaves the formerly retained scope.
      f.pc = 30;
      check(region(f, [&] { unwind(&f, 60, 8); }) == 60);
      check(events == std::vector<int>({1, 2})); check(s.gpr[3] == 8);
    }
    events.clear();
    {
      State s = initial(); Frame f(s, {{10, 20, 0, fin(1)}}); f.pc = 12;
      check(region(f, [&] { s.gpr[3] = 1; fin(9)(s); }) == 0);
      check(events == std::vector<int>({9})); // normal cleanup not duplicated
      events.clear(); bool escaped = false;
      try { region(f, [] { throw std::logic_error("host"); }); }
      catch (const std::logic_error&) { escaped = true; }
      check(escaped && events == std::vector<int>({1}));
    }
    {
      State s = initial(); Frame f(s, {{10, 20, 30, [](State&) { raise({2, 0}); return 1; }}}); f.pc = 12;
      State prior = s; bool rejected = false;
      try { region(f, [] { raise({1, 0}); }); } catch (const Unsupported&) { rejected = true; }
      check(rejected && s == prior && !in_funclet);
      rejected = false;
      try { unwind(nullptr, 30, 0); } catch (const Unsupported&) { rejected = true; }
      check(rejected);
      rejected = false;
      try { unwind(&f, 999, 0); } catch (const Unsupported&) { rejected = true; }
      check(rejected);
    }
    {
      // Portable checkpoint model; deliberately NOT a test of host setjmp/longjmp.
      State s = initial(), checkpoint = s; Frame f(s, {}); f.pc = 12;
      int cleaned = 0, destructed = 0;
      check(region(f, [&] {
        struct Guard { int& count; ~Guard() { ++count; } } guard{destructed};
        Frame child(s, {{10, 20, 0, [&](State&) { ++cleaned; return 0; }}}); child.pc = 12;
        region(child, [&] { s = {}; unwind(&f, 40, 7); });
      }) == 40);
      uint32_t result = uint32_t(s.gpr[3]); s = checkpoint; f.in_call = false; f.pc = 12;
      check(result == 7 && s == initial() && top == &f);
      check(cleaned == 1 && destructed == 1);
    }
    check(guest_fault(0xc0000005, 0x100000010ULL, 0x100000000ULL, true));
    check(guest_fault(0xc0000006, 0x1ffffffffULL, 0x100000000ULL, true));
    check(!guest_fault(0xc0000005, 0, 0x100000000ULL, true));
    check(!guest_fault(0xc0000005, 0x200000000ULL, 0x100000000ULL, true));
    check(!guest_fault(0xc0000005, 0x100000010ULL, 0x100000000ULL, false));
    check(!guest_fault(0xe06d7363, 0x100000010ULL, 0x100000000ULL, true));
    bool thread_ok = false;
    std::thread t([&] { State s = initial(); Frame f(s, {}); thread_ok = top == &f; }); t.join();
    check(thread_ok && top == nullptr);
    std::cout << "PORTABLE_GUEST_EH PASS checks=" << checks << "\n";
    return 0;
  } catch (const std::exception& e) { std::cerr << e.what() << "\n"; }
    catch (...) { std::cerr << "unexpected transport\n"; }
  return 1;
}

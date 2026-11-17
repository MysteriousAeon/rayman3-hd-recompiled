// Linux Guest Entry (LGE) acceptance executable.
//
// Executes a small, call-closed set of REAL generated Rayman 3 HD functions
// (private, verbatim, linked from the build-time private translation unit) on
// synthetic inputs inside the real pinned ReXGlue memory system brought up by
// the audited LRB bootstrap module. No game data, image, kernel, imports,
// threads, GPU, audio or input. Every case records its exact input identity,
// all integer guest registers, every changed guest-memory byte and the entered
// guest functions, checks them against declared bounds and an independent host
// model, and emits a canonical observation plus its SHA-256 for a bit-exact
// Windows/Linux comparison.
#include "lrb_bootstrap.h"

#include <algorithm>
#include <array>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

#include <rex/memory/utils.h>
#include <rex/ppc/context.h>

#if LRB_NATIVE
#include <signal.h>
#include <sys/resource.h>
#include "lrb_owner.h"
#endif

// ---- the selected generated functions (defined verbatim in lge_generated.cpp)
extern "C" {
void sub_820E7440(PPCContext& __restrict ctx, uint8_t* base);  // memset
void sub_820EB7D8(PPCContext& __restrict ctx, uint8_t* base);  // forward copy
void sub_820E78A0(PPCContext& __restrict ctx, uint8_t* base);  // memmove
void sub_820EB350(PPCContext& __restrict ctx, uint8_t* base);  // memcpy (doubleword)
void sub_820E7328(PPCContext& __restrict ctx, uint8_t* base);  // strncpy
void sub_820E6D08(PPCContext& __restrict ctx, uint8_t* base);  // strstr
void sub_820F0A28(PPCContext& __restrict ctx, uint8_t* base);  // format-spec predicate
void sub_820F7978(PPCContext& __restrict ctx, uint8_t* base);  // vector erase(pos)
}

namespace {
using lrb::require;
using GuestFn = void (*)(PPCContext& __restrict, uint8_t*);
static_assert(std::is_trivially_copyable_v<PPCContext>, "PPCContext snapshot by bytes");

// ---------------------------------------------------------------- SHA-256
class Sha256 {
 public:
  Sha256() { reset(); }
  void reset() {
    static constexpr uint32_t init[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                                         0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
    std::memcpy(h_, init, sizeof(h_));
    length_ = 0;
    used_ = 0;
  }
  void update(const void* data, size_t size) {
    const auto* p = static_cast<const uint8_t*>(data);
    length_ += size;
    while (size) {
      const size_t n = std::min(size, sizeof(block_) - used_);
      std::memcpy(block_ + used_, p, n);
      used_ += n;
      p += n;
      size -= n;
      if (used_ == sizeof(block_)) {
        compress();
        used_ = 0;
      }
    }
  }
  void update(std::string_view s) { update(s.data(), s.size()); }
  std::string hex() {
    const uint64_t bits = length_ * 8;
    const uint8_t pad = 0x80;
    update(&pad, 1);
    const uint8_t zero = 0;
    while (used_ != 56) update(&zero, 1);
    uint8_t len[8];
    for (int i = 0; i < 8; ++i) len[i] = static_cast<uint8_t>(bits >> (56 - 8 * i));
    update(len, 8);
    std::string out;
    char buf[9];
    for (uint32_t v : h_) {
      std::snprintf(buf, sizeof(buf), "%08x", v);
      out += buf;
    }
    reset();
    return out;
  }

 private:
  static uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
  void compress() {
    static constexpr uint32_t k[64] = {
        0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u, 0x923f82a4u,
        0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu,
        0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu,
        0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau, 0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
        0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu,
        0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
        0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u, 0x19a4c116u,
        0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
        0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u, 0x90befffau, 0xa4506cebu, 0xbef9a3f7u,
        0xc67178f2u};
    uint32_t w[64];
    for (int i = 0; i < 16; ++i)
      w[i] = (uint32_t(block_[4 * i]) << 24) | (uint32_t(block_[4 * i + 1]) << 16) |
             (uint32_t(block_[4 * i + 2]) << 8) | uint32_t(block_[4 * i + 3]);
    for (int i = 16; i < 64; ++i) {
      const uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      const uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h_[0], b = h_[1], c = h_[2], d = h_[3], e = h_[4], f = h_[5], g = h_[6], h = h_[7];
    for (int i = 0; i < 64; ++i) {
      const uint32_t t1 = h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + k[i] + w[i];
      const uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
      h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h_[0] += a; h_[1] += b; h_[2] += c; h_[3] += d; h_[4] += e; h_[5] += f; h_[6] += g; h_[7] += h;
  }
  uint32_t h_[8];
  uint8_t block_[64];
  uint64_t length_;
  size_t used_;
};

std::string sha256(std::string_view s) {
  Sha256 h;
  h.update(s);
  return h.hex();
}

// ---------------------------------------------------------------- PRNG
struct SplitMix {
  uint64_t state;
  uint64_t next() {
    uint64_t z = (state += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
  }
  uint32_t below(uint32_t n) { return static_cast<uint32_t>(next() % n); }
};

// ---------------------------------------------------------------- call trace
// M2Enter is the production prologue hook (see m2_trace.h). Recording only.
constexpr size_t kTraceMax = 32;
const char* g_trace[kTraceMax];
size_t g_trace_count = 0;
bool g_trace_overflow = false;
}  // namespace

void M2Enter(const char* name, PPCContext&) {
  if (g_trace_count < kTraceMax)
    g_trace[g_trace_count++] = name;
  else
    g_trace_overflow = true;
}

namespace {
// ---------------------------------------------------------------- guest arena
// One real 4 KiB-page allocation in the v00000000 guest heap at a fixed
// address: [guard][16 RW pages][guard]. Guards are no-access; any stray guest
// access beyond the arena faults (native: unadmitted -> terminal).
constexpr uint32_t kPage = 0x1000u;
constexpr uint32_t kRegion = 0x20000000u;
constexpr uint32_t kArena = kRegion + kPage;
constexpr uint32_t kArenaSize = 16 * kPage;
constexpr uint32_t kGuardHigh = kArena + kArenaSize;
constexpr uint32_t kRegionSize = kArenaSize + 2 * kPage;
constexpr uint32_t kStackTop = kArena + kArenaSize - 0x100u;  // Initial r1 (16-aligned).
constexpr uint32_t kDataEnd = kArena + 0xC000u;                // Data below, stack above.
constexpr uint64_t kReturnLr = 0x82FFF000ull;                  // Synthetic caller LR.

struct Range {
  uint32_t begin, end;  // Guest [begin, end).
};

struct Env {
  lrb::Bootstrap* bs = nullptr;
  uint8_t* base = nullptr;   // Guest virtual membase (the generated code's `base`).
  uint8_t* arena = nullptr;  // Host address of kArena.
  std::vector<std::string> lines;
  unsigned cases = 0;
};

uint8_t* host(Env& env, uint32_t guest) {
  require(guest >= kArena && guest < kGuardHigh, "host() inside the arena");
  return env.arena + (guest - kArena);
}
void put_be32(Env& env, uint32_t guest, uint32_t value) {
  uint8_t* p = host(env, guest);
  p[0] = uint8_t(value >> 24); p[1] = uint8_t(value >> 16); p[2] = uint8_t(value >> 8); p[3] = uint8_t(value);
}
uint32_t get_be32(const uint8_t* p) {
  return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | uint32_t(p[3]);
}

// Byte ranges of the integer guest state inside PPCContext. Everything else
// (FPRs, VMX, FPSCR, VSCR, reserve, indirect target, padding) must stay
// byte-identical across every call.
std::vector<std::pair<size_t, size_t>> integer_fields(const PPCContext& c) {
  const auto* b = reinterpret_cast<const uint8_t*>(&c);
  std::vector<std::pair<size_t, size_t>> out;
  auto add = [&](const void* p, size_t n) { out.emplace_back(static_cast<const uint8_t*>(p) - b, n); };
  const PPCRegister* gprs[32] = {&c.r0, &c.r1, &c.r2, &c.r3, &c.r4, &c.r5, &c.r6, &c.r7,
                                 &c.r8, &c.r9, &c.r10, &c.r11, &c.r12, &c.r13, &c.r14, &c.r15,
                                 &c.r16, &c.r17, &c.r18, &c.r19, &c.r20, &c.r21, &c.r22, &c.r23,
                                 &c.r24, &c.r25, &c.r26, &c.r27, &c.r28, &c.r29, &c.r30, &c.r31};
  for (auto* r : gprs) add(r, sizeof(*r));
  add(&c.lr, sizeof(c.lr));
  add(&c.ctr, sizeof(c.ctr));
  add(&c.xer, sizeof(c.xer));
  const PPCCRRegister* crs[8] = {&c.cr0, &c.cr1, &c.cr2, &c.cr3, &c.cr4, &c.cr5, &c.cr6, &c.cr7};
  for (auto* r : crs) add(r, sizeof(*r));
  return out;
}

const PPCRegister& gpr(const PPCContext& c, int i) {
  const PPCRegister* gprs[32] = {&c.r0, &c.r1, &c.r2, &c.r3, &c.r4, &c.r5, &c.r6, &c.r7,
                                 &c.r8, &c.r9, &c.r10, &c.r11, &c.r12, &c.r13, &c.r14, &c.r15,
                                 &c.r16, &c.r17, &c.r18, &c.r19, &c.r20, &c.r21, &c.r22, &c.r23,
                                 &c.r24, &c.r25, &c.r26, &c.r27, &c.r28, &c.r29, &c.r30, &c.r31};
  return *gprs[i];
}

// Canonical, ABI-independent text of the integer guest state.
std::string integer_state(const PPCContext& c) {
  std::string s;
  char buf[64];
  for (int i = 0; i < 32; ++i) {
    std::snprintf(buf, sizeof(buf), "r%d=%016" PRIx64 " ", i, gpr(c, i).u64);
    s += buf;
  }
  std::snprintf(buf, sizeof(buf), "lr=%016" PRIx64 " ctr=%016" PRIx64 " ", c.lr, c.ctr.u64);
  s += buf;
  std::snprintf(buf, sizeof(buf), "xer=%02x%02x%02x cr=", c.xer.so, c.xer.ov, c.xer.ca);
  s += buf;
  const PPCCRRegister* crs[8] = {&c.cr0, &c.cr1, &c.cr2, &c.cr3, &c.cr4, &c.cr5, &c.cr6, &c.cr7};
  for (auto* r : crs) {
    std::snprintf(buf, sizeof(buf), "%02x%02x%02x%02x", r->lt, r->gt, r->eq, r->so);
    s += buf;
  }
  return s;
}

std::string hex_bytes(const uint8_t* p, size_t n) {
  static const char digits[] = "0123456789abcdef";
  std::string s;
  s.reserve(2 * n);
  for (size_t i = 0; i < n; ++i) {
    s += digits[p[i] >> 4];
    s += digits[p[i] & 15];
  }
  return s;
}

// Everything a case needs: arguments, declared writable guest ranges, the
// expected entered-function trace and an independent host model.
struct Spec {
  std::string id;
  const char* function;
  uint32_t guest;
  GuestFn fn;
  uint64_t seed;
};
struct Setup {
  Env& env;
  PPCContext& ctx;
  std::vector<Range> writable;
  std::vector<std::string> trace;
  std::function<bool(const PPCContext& before, const PPCContext& after, const uint8_t* arena_before,
                     const uint8_t* arena_after)> model;
};

void init_context(PPCContext& ctx, SplitMix& rng) {
  auto* raw = reinterpret_cast<uint8_t*>(&ctx);
  for (size_t i = 0; i < sizeof(PPCContext); ++i) raw[i] = static_cast<uint8_t>(rng.next());
  for (int i = 0; i < 32; ++i) const_cast<PPCRegister&>(gpr(ctx, i)).u64 = rng.next();
  ctx.r1.u64 = kStackTop;
  ctx.lr = kReturnLr;
  ctx.ctr.u64 = rng.next();
  ctx.xer.so = uint8_t(rng.next() & 1);
  ctx.xer.ov = uint8_t(rng.next() & 1);
  ctx.xer.ca = uint8_t(rng.next() & 1);
  PPCCRRegister* crs[8] = {&ctx.cr0, &ctx.cr1, &ctx.cr2, &ctx.cr3, &ctx.cr4, &ctx.cr5, &ctx.cr6, &ctx.cr7};
  for (auto* r : crs) r->set_raw(uint32_t(rng.next() & 15));
  ctx.fpscr.csr = 0;  // Untouched by the selected integer code; must stay 0.
}

void run_case(Env& env, const Spec& spec, const std::function<void(Setup&)>& prepare) {
  SplitMix rng{spec.seed};
  // Deterministic synthetic memory: the whole arena from the case seed.
  for (uint32_t i = 0; i < kArenaSize; i += 8) {
    const uint64_t v = rng.next();
    std::memcpy(env.arena + i, &v, 8);
  }
  alignas(64) PPCContext ctx;
  init_context(ctx, rng);
  Setup setup{env, ctx, {}, {}, {}};
  prepare(setup);
  for (const Range& r : setup.writable)
    require(r.begin <= r.end && r.begin >= kArena && r.end <= kGuardHigh &&
                (r.end <= kDataEnd || r.begin >= kDataEnd),
            "declared range inside the arena, data or stack part");

  std::vector<uint8_t> before(env.arena, env.arena + kArenaSize);
  alignas(64) PPCContext ctx_before;
  std::memcpy(static_cast<void*>(&ctx_before), &ctx, sizeof(ctx));
  std::string input = "arena=" + std::to_string(kArena) + ":";
  {
    Sha256 h;
    h.update(before.data(), before.size());
    input += h.hex();
  }
  input += " " + integer_state(ctx_before);
  const std::string input_digest = sha256(input);

  g_trace_count = 0;
  g_trace_overflow = false;
  spec.fn(ctx, env.base);  // The generated code runs here.
  require(!g_trace_overflow, "call trace bounded");

  // Non-integer guest/host state must be untouched.
  const auto fields = integer_fields(ctx);
  std::vector<bool> integer_byte(sizeof(PPCContext), false);
  for (auto [offset, size] : fields)
    for (size_t i = 0; i < size; ++i) integer_byte[offset + i] = true;
  const auto* rb = reinterpret_cast<const uint8_t*>(&ctx_before);
  const auto* ra = reinterpret_cast<const uint8_t*>(&ctx);
  bool nonint_same = true;
  for (size_t i = 0; i < sizeof(PPCContext); ++i)
    if (!integer_byte[i] && rb[i] != ra[i]) nonint_same = false;
  require(nonint_same, (spec.id + ": non-integer context state unchanged").c_str());

  // Memory delta: every changed byte, as runs, and its containment.
  std::string delta;
  unsigned changed = 0;
  bool contained = true;
  for (uint32_t i = 0; i < kArenaSize;) {
    if (env.arena[i] == before[i]) {
      ++i;
      continue;
    }
    uint32_t j = i;
    while (j < kArenaSize && env.arena[j] != before[j]) ++j;
    for (uint32_t k = i; k < j; ++k) {
      const uint32_t g = kArena + k;
      bool declared = false;
      for (const Range& r : setup.writable) declared = declared || (g >= r.begin && g < r.end);
      contained = contained && declared;
    }
    char head[32];
    std::snprintf(head, sizeof(head), "%s%x:", delta.empty() ? "" : ",", i);
    delta += head;
    delta += hex_bytes(env.arena + i, j - i);
    changed += j - i;
    i = j;
  }
  require(contained, (spec.id + ": every changed byte lies in a declared region").c_str());
  std::string trace;
  for (size_t i = 0; i < g_trace_count; ++i) trace += (i ? "," : "") + std::string(g_trace[i]);
  std::string expected_trace;
  for (size_t i = 0; i < setup.trace.size(); ++i)
    expected_trace += (i ? "," : "") + std::string("__imp__") + setup.trace[i];
  require(trace == expected_trace, (spec.id + ": entered-function trace").c_str());
  require(setup.model(ctx_before, ctx, before.data(), env.arena), (spec.id + ": host model").c_str());

  std::string writable;
  for (const Range& r : setup.writable) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%s%08x-%08x", writable.empty() ? "" : ",", r.begin, r.end);
    writable += buf;
  }
  char guest[16];
  std::snprintf(guest, sizeof(guest), "%08x", spec.guest);
  std::string canonical = "LGE_CASE_V1|id=" + spec.id + "|fn=" + spec.function + "|guest=" + guest +
                          "|seed=" + std::to_string(spec.seed) + "|input=" + input_digest +
                          "|before=" + integer_state(ctx_before) + "|after=" + integer_state(ctx) +
                          "|nonint=unchanged|writable=" + writable + "|changed=" + std::to_string(changed) +
                          "|delta=" + delta + "|trace=" + trace + "|model=pass";
  env.lines.push_back(canonical);
  ++env.cases;
}

// ---------------------------------------------------------------- host models
bool bytes_equal(const uint8_t* a, const uint8_t* b, size_t n) { return n == 0 || std::memcmp(a, b, n) == 0; }

struct Cases {
  Env& env;
  uint64_t next_seed = 0x4C47450000000001ull;  // "LGE"
  uint64_t seed() { return next_seed++; }

  // memset(dst, c, n)
  void memset_case(const std::string& id, uint32_t dst_off, uint32_t n, uint32_t c) {
    const Spec spec{id, "sub_820E7440", 0x820E7440u, sub_820E7440, seed()};
    run_case(env, spec, [&](Setup& s) {
      const uint32_t dst = kArena + dst_off;
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = c; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      s.trace = {"sub_820E7440"};
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t*, const uint8_t* after) {
        const uint8_t* p = after + (dst - kArena);
        for (uint32_t i = 0; i < n; ++i)
          if (p[i] != uint8_t(c)) return false;
        return a.r3.u64 == dst;
      };
    });
  }

  // copy(dst, src, n) for the two forward copies (non-overlapping).
  void copy_case(const std::string& id, const char* name, uint32_t guest, GuestFn fn, uint32_t dst_off,
                 uint32_t src_off, uint32_t n, bool via_stack) {
    const Spec spec{id, name, guest, fn, seed()};
    run_case(env, spec, [&](Setup& s) {
      const uint32_t dst = kArena + dst_off, src = kArena + src_off;
      require(dst + n <= src || src + n + 16 <= dst, "copy case regions disjoint");
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = src; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      if (via_stack) s.writable.push_back({kStackTop - 8, kStackTop});  // std r3,-8(r1)
      s.trace = {name};
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t* before, const uint8_t* after) {
        return bytes_equal(after + (dst - kArena), before + (src - kArena), n) && a.r3.u64 == dst &&
               a.r1.u64 == kStackTop;
      };
    });
  }

  // memmove(dst, src, n), any overlap.
  void memmove_case(const std::string& id, uint32_t dst_off, uint32_t src_off, uint32_t n) {
    const Spec spec{id, "sub_820E78A0", 0x820E78A0u, sub_820E78A0, seed()};
    run_case(env, spec, [&](Setup& s) {
      const uint32_t dst = kArena + dst_off, src = kArena + src_off;
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = src; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      if (dst == src) {
        s.trace = {"sub_820E78A0"};
      } else if (int32_t(dst) < int32_t(src)) {
        s.trace = {"sub_820E78A0", "sub_820EB350"};
        s.writable.push_back({kStackTop - 8, kStackTop});
      } else {
        s.trace = {"sub_820E78A0"};
      }
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t* before, const uint8_t* after) {
        std::vector<uint8_t> expect(before, before + kArenaSize);
        std::memmove(expect.data() + (dst - kArena), before + (src - kArena), n);
        return bytes_equal(after + (dst - kArena), expect.data() + (dst - kArena), n) &&
               a.r1.u64 == kStackTop;
      };
    });
  }

  // strncpy(dst, src, n). `text` is written at src with its NUL (if any).
  void strncpy_case(const std::string& id, uint32_t dst_off, uint32_t src_off, std::string_view text,
                    bool terminate, uint32_t n) {
    const Spec spec{id, "sub_820E7328", 0x820E7328u, sub_820E7328, seed()};
    run_case(env, spec, [&](Setup& s) {
      const uint32_t dst = kArena + dst_off, src = kArena + src_off;
      uint8_t* p = host(env, src);
      for (size_t i = 0; i < text.size(); ++i) p[i] = uint8_t(text[i] ? text[i] : 'x');
      if (terminate) p[text.size()] = 0;
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = src; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      s.trace = {"sub_820E7328"};
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t* before, const uint8_t* after) {
        const uint8_t* in = before + (src - kArena);
        const uint8_t* out = after + (dst - kArena);
        uint32_t i = 0;
        for (; i < n && in[i]; ++i)
          if (out[i] != in[i]) return false;
        for (; i < n; ++i)
          if (out[i] != 0) return false;
        return a.r3.u64 == dst;
      };
    });
  }

  // strstr(haystack, needle); both strings NUL-terminated in the arena.
  void strstr_case(const std::string& id, std::string_view hay, std::string_view needle) {
    const Spec spec{id, "sub_820E6D08", 0x820E6D08u, sub_820E6D08, seed()};
    run_case(env, spec, [&](Setup& s) {
      const uint32_t h = kArena + 0x2000u, nd = kArena + 0x3000u;
      std::memcpy(host(env, h), hay.data(), hay.size());
      host(env, h)[hay.size()] = 0;
      std::memcpy(host(env, nd), needle.data(), needle.size());
      host(env, nd)[needle.size()] = 0;
      s.ctx.r3.u64 = h; s.ctx.r4.u64 = nd;
      s.trace = {"sub_820E6D08"};
      const size_t pos = std::string_view(hay).find(needle);
      const uint64_t expect = needle.empty() ? h : (pos == std::string_view::npos ? 0 : h + pos);
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t*, const uint8_t*) {
        return a.r3.u64 == expect;
      };
    });
  }

  // Format-spec predicate: r3 -> {+0 word, +8 conversion char, +12 flags}.
  void format_case(const std::string& id, char object_conv, char conv, uint32_t value, uint32_t flags,
                   uint32_t object_flags, bool value_matches) {
    const Spec spec{id, "sub_820F0A28", 0x820F0A28u, sub_820F0A28, seed()};
    run_case(env, spec, [&](Setup& s) {
      const uint32_t obj = kArena + 0x1000u;
      const uint32_t word = value_matches ? value : value ^ 0x10u;
      put_be32(env, obj, word);
      host(env, obj + 8)[0] = uint8_t(object_conv);
      put_be32(env, obj + 12, object_flags);
      s.ctx.r3.u64 = obj; s.ctx.r4.u64 = value;
      s.ctx.r5.u64 = (s.ctx.r5.u64 & ~0xFFull) | uint8_t(conv);
      s.ctx.r6.u64 = flags;
      s.trace = {"sub_820F0A28"};
      s.model = [](const PPCContext&, const PPCContext& a, const uint8_t*, const uint8_t*) {
        return a.r3.u64 == 0 || a.r3.u64 == 1;
      };
    });
  }

  // erase(position) on {begin, end} of 4-byte elements; result through r3.
  void erase_case(const std::string& id, uint32_t count, uint32_t index) {
    const Spec spec{id, "sub_820F7978", 0x820F7978u, sub_820F7978, seed()};
    run_case(env, spec, [&](Setup& s) {
      require(index < count, "erase index inside the vector");
      const uint32_t ret = kArena + 0x0080u, vec = kArena + 0x0100u, elems = kArena + 0x4000u;
      put_be32(env, vec, elems);
      put_be32(env, vec + 4, elems + 4 * count);
      const uint32_t pos = elems + 4 * index;
      s.ctx.r3.u64 = ret; s.ctx.r4.u64 = vec; s.ctx.r5.u64 = pos;
      s.writable = {{ret, ret + 4}, {vec + 4, vec + 8}, {pos, elems + 4 * count},
                    {kStackTop - 128, kStackTop}};
      s.trace = {"sub_820F7978", "__savegprlr_29", "sub_820E78A0", "sub_820EB350", "__restgprlr_29"};
      s.model = [=](const PPCContext& b, const PPCContext& a, const uint8_t* before, const uint8_t* after) {
        const uint8_t* eb = before + (elems - kArena);
        const uint8_t* ea = after + (elems - kArena);
        for (uint32_t i = 0; i + 1 < count; ++i) {
          const uint8_t* expect = eb + 4 * (i < index ? i : i + 1);
          if (!bytes_equal(ea + 4 * i, expect, 4)) return false;
        }
        return get_be32(after + (vec + 4 - kArena)) == elems + 4 * (count - 1) &&
               get_be32(after + (vec - kArena)) == elems && get_be32(after + (ret - kArena)) == pos &&
               a.r3.u64 == ret && a.r1.u64 == kStackTop && a.lr == kReturnLr &&
               a.r29.u64 == b.r29.u64 && a.r30.u64 == b.r30.u64 && a.r31.u64 == b.r31.u64;
      };
    });
  }

  void all() {
    // memset: sizes across every loop/tail path, all four alignments, n = 0.
    const uint32_t ms[] = {0, 1, 3, 4, 15, 16, 17, 63, 64, 1000, 4096, 5003};
    for (uint32_t a = 0; a < 4; ++a)
      for (uint32_t i = 0; i < 12; i += 1 + a)
        memset_case("memset/a" + std::to_string(a) + "/n" + std::to_string(ms[i]), 0x0400u + a, ms[i],
                    0x00000A00u | ((a * 37 + i * 11) & 0xFF));
    memset_case("memset/c-upper-bits", 0x0401u, 37, 0x7FFFFF80u);
    // Forward copies: every dst/src alignment pair, sizes across paths, page-crossing.
    const uint32_t cs[] = {0, 1, 2, 5, 8, 31, 100, 1027};
    for (uint32_t d = 0; d < 4; ++d)
      for (uint32_t s = 0; s < 4; ++s) {
        const uint32_t n = cs[(d * 4 + s) % 8];
        copy_case("copy/d" + std::to_string(d) + "s" + std::to_string(s) + "/n" + std::to_string(n),
                  "sub_820EB7D8", 0x820EB7D8u, sub_820EB7D8, 0x0800u + d, 0x6000u + s, n, false);
      }
    copy_case("copy/page-cross", "sub_820EB7D8", 0x820EB7D8u, sub_820EB7D8, 0x0FF3u, 0x7FF9u, 4100, false);
    const uint32_t ls[] = {0, 1, 7, 8, 9, 31, 32, 33, 127, 128, 129, 255, 256, 4096, 8191};
    for (uint32_t i = 0; i < 15; ++i) {
      const uint32_t d = (i * 3) % 8, s = (i * 5) % 8;
      copy_case("memcpy/d" + std::to_string(d) + "s" + std::to_string(s) + "/n" + std::to_string(ls[i]),
                "sub_820EB350", 0x820EB350u, sub_820EB350, 0x0800u + d, 0x6000u + s, ls[i], true);
    }
    // memmove: identity, both overlap directions, disjoint both orders, n = 0.
    memmove_case("memmove/same", 0x2000u, 0x2000u, 64);
    memmove_case("memmove/fwd-overlap-3", 0x2000u, 0x2003u, 200);
    memmove_case("memmove/fwd-overlap-64", 0x2001u, 0x2041u, 777);
    memmove_case("memmove/back-overlap-5", 0x2005u, 0x2000u, 200);
    memmove_case("memmove/back-overlap-1", 0x2001u, 0x2000u, 4097);
    memmove_case("memmove/back-aligned", 0x2400u, 0x2000u, 3000);
    memmove_case("memmove/back-misaligned-src", 0x2404u, 0x2001u, 1203);
    memmove_case("memmove/disjoint-up", 0x6000u, 0x2000u, 513);
    memmove_case("memmove/disjoint-down", 0x2000u, 0x6000u, 513);
    memmove_case("memmove/zero-back", 0x2010u, 0x2000u, 0);
    memmove_case("memmove/zero-fwd", 0x2000u, 0x2010u, 0);
    // strncpy: short (pad), exact, long (no NUL written), n = 0/1, empty source.
    strncpy_case("strncpy/pad", 0x0800u, 0x3000u, "rayman", true, 32);
    strncpy_case("strncpy/exact", 0x0801u, 0x3000u, "globox!", true, 7);
    strncpy_case("strncpy/truncate", 0x0802u, 0x3000u, "teensies-and-murfy", true, 9);
    strncpy_case("strncpy/no-nul-long", 0x0803u, 0x3000u, std::string(300, 'h'), false, 256);
    strncpy_case("strncpy/n0", 0x0800u, 0x3000u, "abc", true, 0);
    strncpy_case("strncpy/n1", 0x0800u, 0x3000u, "abc", true, 1);
    strncpy_case("strncpy/empty", 0x0800u, 0x3000u, "", true, 12);
    strncpy_case("strncpy/high-bytes", 0x0800u, 0x3000u, "\xC3\xA9t\xE9\xFF", true, 10);
    // strstr: positions, absence, empty needle/haystack, partial-match restarts, high bytes.
    strstr_case("strstr/start", "hoodlum-army", "hood");
    strstr_case("strstr/middle", "the-glade-of-dreams", "glade");
    strstr_case("strstr/end", "fairy-council", "council");
    strstr_case("strstr/absent", "land-of-the-livid-dead", "lums");
    strstr_case("strstr/empty-needle", "anything", "");
    strstr_case("strstr/empty-haystack", "", "x");
    strstr_case("strstr/needle-longer", "abc", "abcd");
    strstr_case("strstr/restart", "aaaaaab", "aaab");
    strstr_case("strstr/overlap-prefix", "abababac", "ababac");
    strstr_case("strstr/high-bytes", "x\xE9\xFF\x80y\xE9\xFF\x81", "\xE9\xFF\x81");
    strstr_case("strstr/single", "z", "z");
    // Format predicate: conversion classes x flags x value match.
    const char conv[] = {'p', 's', 'S', 'd', 'i', 'o', 'u', 'x', 'X', 'c'};
    SplitMix pick{0x464D5400u};
    for (int i = 0; i < 24; ++i) {
      const char oc = conv[pick.below(10)], c = conv[pick.below(10)];
      const uint32_t flags = uint32_t(pick.next()) & 0x00030830u;
      const uint32_t oflags = (i % 3 == 0) ? flags : uint32_t(pick.next()) & 0x00030830u;
      format_case("format/" + std::to_string(i) + "/" + oc + c, oc, c, uint32_t(pick.next()), flags, oflags,
                  i % 2 == 0);
    }
    format_case("format/same-p", 'p', 'p', 0x1234u, 0, 0, true);
    format_case("format/same-s", 's', 's', 0x1234u, 0x800u, 0x800u, true);
    format_case("format/s-vs-S", 's', 'S', 0x1234u, 0x10u, 0x810u, true);
    format_case("format/d-vs-x", 'd', 'x', 0x1u, 0x20000u, 0x20u, false);
    // erase(position): first, middle, last element, single element, larger vector.
    erase_case("erase/k1-i0", 1, 0);
    erase_case("erase/k2-i0", 2, 0);
    erase_case("erase/k2-i1", 2, 1);
    erase_case("erase/k5-i2", 5, 2);
    erase_case("erase/k5-i4", 5, 4);
    erase_case("erase/k64-i0", 64, 0);
    erase_case("erase/k64-i37", 64, 37);
    erase_case("erase/k1000-i1", 1000, 1);
  }
};

// ---------------------------------------------------------------- arena lifecycle
rex::memory::BaseHeap* g_heap = nullptr;

void allocate_arena(Env& env) {
  auto& m = env.bs->memory();
  g_heap = m.LookupHeap(kRegion);
  require(g_heap != nullptr && g_heap == m.LookupHeapByType(false, 4096), "arena heap is the 4 KiB virtual heap");
  require(g_heap->AllocFixed(kRegion, kRegionSize, kPage,
                             rex::memory::kMemoryAllocationReserve | rex::memory::kMemoryAllocationCommit,
                             rex::memory::kMemoryProtectRead | rex::memory::kMemoryProtectWrite),
          "real fixed arena allocation");
  require(g_heap->Protect(kRegion, kPage, rex::memory::kMemoryProtectNoAccess) &&
              g_heap->Protect(kGuardHigh, kPage, rex::memory::kMemoryProtectNoAccess),
          "guard pages no-access");
  env.base = m.virtual_membase();
  require((reinterpret_cast<uintptr_t>(env.base) & 0x1F) == 0, "generated-code base is 32-byte aligned");
  require(m.TranslateVirtual(kArena) == env.base + kArena, "arena translation is base + guest (no host offset)");
  env.arena = m.TranslateVirtual(kArena);
}

void verify_arena_protection(Env& env) {
  auto& m = env.bs->memory();
  using rex::memory::PageAccess;
  require(lrb::host_access(m.TranslateVirtual(kRegion)) == PageAccess::kNoAccess &&
              lrb::host_access(m.TranslateVirtual(kGuardHigh)) == PageAccess::kNoAccess,
          "guards are host no-access");
  for (uint32_t p = kArena; p < kGuardHigh; p += kPage)
    require(lrb::host_access(m.TranslateVirtual(p)) == PageAccess::kReadWrite, "arena pages host read-write");
}

void release_arena() {
  uint32_t released = 0;
  require(g_heap->Release(kRegion, &released) && released == kRegionSize, "arena released exactly");
}

#if LRB_NATIVE
class Witness final : public lrb::Observer {
 public:
  Witness(const char* mode, const char* token) : mode_(mode) {
    valid_ = token && std::strlen(token) == 32;
    for (unsigned i = 0; valid_ && i < 32; ++i)
      valid_ = (token[i] >= '0' && token[i] <= '9') || (token[i] >= 'a' && token[i] <= 'f');
    if (valid_) std::memcpy(token_, token, 33);
  }
  bool valid() const { return valid_; }
  void emit(lrb::Bootstrap& bs, const char* phase, uintptr_t address) {
    std::array<char, 256> line{};
    const int n = std::snprintf(line.data(), line.size(),
        "LRB_GATE_V1 token=%s mode=%s phase=%s faults=%u consumed=%u invalidations=0 "
        "records=0 address=0x%llx\n",
        token_, mode_, phase, bs.admitted_faults(), bs.consumed_dispatches(),
        static_cast<unsigned long long>(address));
    if (n > 0 && static_cast<size_t>(n) < line.size()) {
      (void)std::fwrite(line.data(), 1, static_cast<size_t>(n), stderr);
      (void)std::fflush(stderr);
    }
  }

 private:
  const char* mode_;
  char token_[33] = {};
  bool valid_ = false;
};

// Unsupported access by real generated code: a guard-page store (memset) or
// load (strncpy). Nothing admits it; the owner must terminate in signal context.
[[noreturn]] void run_fatal(Env& env, Witness& witness, std::string_view mode) {
  alignas(64) PPCContext ctx;
  SplitMix rng{0x4641544100000001ull};
  init_context(ctx, rng);
  const uintptr_t guard = reinterpret_cast<uintptr_t>(env.bs->memory().TranslateVirtual(kGuardHigh));
  if (mode == "lge-write-guard") {
    ctx.r3.u64 = kGuardHigh - 8; ctx.r4.u64 = 0x5A; ctx.r5.u64 = 64;
    witness.emit(*env.bs, "begin", guard);
    sub_820E7440(ctx, env.base);
    require(false, "guard store returned");
  }
  if (mode == "lge-read-guard") {
    std::memset(host(env, kGuardHigh - 4), 'r', 4);
    ctx.r3.u64 = kArena; ctx.r4.u64 = kGuardHigh - 4; ctx.r5.u64 = 64;
    witness.emit(*env.bs, "begin", guard);
    sub_820E7328(ctx, env.base);
    require(false, "guard load returned");
  }
  require(false, "unknown fatal mode");
  std::abort();
}
#endif
}  // namespace

int main(int argc, char** argv) {
  const std::string_view mode = argc > 1 ? argv[1] : "normal";
  require(argc <= 2, "one optional mode");
#if LRB_NATIVE
  const bool fatal = mode == "lge-write-guard" || mode == "lge-read-guard";
  require(fatal || mode == "normal", "unsupported native mode");
  const rlimit no_core{0, 0};
  require(setrlimit(RLIMIT_CORE, &no_core) == 0, "disable core dumps for fatal modes");
  Witness witness(mode.data(), std::getenv("LRB_GATE_TOKEN"));
  if (fatal) require(witness.valid(), "fatal modes require a 32-hex LRB_GATE_TOKEN");
#else
  const bool fatal = false;
  require(mode == "normal", "ordinary build supports normal mode only");
#endif
  lrb::Bootstrap bs(fatal ? lrb::ShmPolicy::kUnlinkAfterMap : lrb::ShmPolicy::kSdkContract);
  bs.start(std::getenv("LRB_OWNERSHIP_FILE"), mode.data());
  Env env;
  env.bs = &bs;
  allocate_arena(env);
  verify_arena_protection(env);
#if LRB_NATIVE
  require(lrb_owns_sigsegv() == 1, "LRB owner exclusive before generated code");
  if (fatal) run_fatal(env, witness, mode);
#endif
  Cases cases{env};
  cases.all();
  verify_arena_protection(env);
#if LRB_NATIVE
  require(lrb_owns_sigsegv() == 1, "LRB owner still exclusive after generated code");
  require(bs.admitted_faults() == 0, "zero admitted faults on positive runs");
#endif
  require(bs.consumed_dispatches() == 0 && bs.declined_dispatches() == 0, "no SDK dispatch");
  release_arena();

  Sha256 aggregate;
  for (const std::string& line : env.lines) {
    aggregate.update(sha256(line));
    aggregate.update("\n");
  }
  const std::string total = aggregate.hex();
  if (const char* path = std::getenv("LGE_RESULTS_FILE")) {
    std::FILE* f = std::fopen(path, "wb");
    require(f != nullptr, "open LGE_RESULTS_FILE");
    for (const std::string& line : env.lines) {
      const std::string digest = sha256(line);
      require(std::fprintf(f, "%s|digest=%s\n", line.c_str(), digest.c_str()) > 0, "write case record");
    }
    require(std::fclose(f) == 0, "close LGE_RESULTS_FILE");
  }
  bs.stop();
  std::printf("LGE PASS cases=%u checks=%u aggregate=%s native=%d\n", env.cases, lrb::checks(), total.c_str(),
              LRB_NATIVE);
  return 0;
}

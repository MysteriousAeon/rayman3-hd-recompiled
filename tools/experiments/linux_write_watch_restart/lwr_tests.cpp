// Linux Write-Watch Restart (LWR) acceptance executable.
//
// Runs REAL generated Rayman 3 HD functions (the audited LGE private,
// verbatim translation unit) on synthetic data in a real vA physical-alias
// allocation of the pinned ReXGlue memory system (audited LRB bootstrap).
//
// Every scenario runs twice:
//  * ordinary: no watch; the record is the semantic reference (Windows too);
//  * watched (Linux native only): selected pages are SDK write-watched
//    (EnablePhysicalMemoryAccessCallbacks, so they are host read-only) and
//    registered with the LWR session. The generated store faults, the single
//    LRB owner admits it through lwr_restart_admit (page made writable, one
//    claim, no context edit), the same instruction re-executes, and ordinary
//    code then drains each claim into the real SDK invalidation path
//    (Memory::TriggerPhysicalMemoryCallbacks).
// The semantic record of the watched run must be byte-identical to the
// ordinary one and to the Windows reference; native fault/claim facts are
// recorded separately and never compared with Windows.
#include "lrb_bootstrap.h"

#include <algorithm>
#include <array>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <set>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

#include <rex/memory/utils.h>
#include <rex/ppc/context.h>
#include <rex/thread/mutex.h>

#include "lwr_decode.h"

#if LRB_NATIVE
#include <elf.h>
#include <pthread.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <unistd.h>
#include "lrb_owner.h"
#include "lwr_restart.h"
extern "C" {
void lwr_leaf_store32(void* p_minus_4, uint32_t v);
void lwr_leaf_store128(void* p);
extern const unsigned char lwr_leaf_store32_end[], lwr_leaf_store128_end[];
}
#endif

// ---- the selected generated functions (defined verbatim in lge_generated.cpp)
extern "C" {
void sub_820E7440(PPCContext& __restrict ctx, uint8_t* base);  // memset
void sub_820EB7D8(PPCContext& __restrict ctx, uint8_t* base);  // forward copy
void sub_820E78A0(PPCContext& __restrict ctx, uint8_t* base);  // memmove
void sub_820EB350(PPCContext& __restrict ctx, uint8_t* base);  // memcpy (doubleword)
void sub_820E7328(PPCContext& __restrict ctx, uint8_t* base);  // strncpy
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

struct SplitMix {
  uint64_t state;
  uint64_t next() {
    uint64_t z = (state += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
  }
};

// ---------------------------------------------------------------- call trace
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
// ---------------------------------------------------------------- guest region
// One real 64 KiB vA physical allocation = 16 host pages P0..P15. Watched
// pages (native watched runs only): P4, P5, P9, P12. Their neighbours P3, P6,
// P8, P10, P11, P13 stay ordinary. P15 holds the guest stack.
constexpr uint32_t kPage = 0x1000u;
constexpr uint32_t kAliasVa = 0xA4000000u;
constexpr uint32_t kAliasPhysical = 0x04000000u;
constexpr uint32_t kAliasSize = 0x10000u;
constexpr uint32_t kPages = kAliasSize / kPage;
constexpr uint32_t kStackTop = kAliasVa + 15 * kPage + 0xF00u;
constexpr uint64_t kReturnLr = 0x82FFF000ull;
constexpr std::array<uint32_t, 4> kWatched = {4, 5, 9, 12};
constexpr uint32_t P(uint32_t n) { return kAliasVa + n * kPage; }

struct Range {
  uint32_t begin, end;  // Guest [begin, end).
};

struct Env {
  lrb::Bootstrap* bs = nullptr;
  uint8_t* base = nullptr;   // Guest virtual membase (the generated code's `base`).
  uint8_t* alias = nullptr;  // Host address of kAliasVa (A view).
  rex::memory::BaseHeap* heap = nullptr;
  std::vector<std::string> ordinary, watched, restarts, claims;
  unsigned cases = 0, total_claims = 0;
};

uint8_t* host(Env& env, uint32_t guest) {
  require(guest >= kAliasVa && guest < kAliasVa + kAliasSize, "host() inside the alias region");
  return env.alias + (guest - kAliasVa);
}
void put_be32(Env& env, uint32_t guest, uint32_t value) {
  uint8_t* p = host(env, guest);
  p[0] = uint8_t(value >> 24); p[1] = uint8_t(value >> 16); p[2] = uint8_t(value >> 8); p[3] = uint8_t(value);
}
uint32_t get_be32(const uint8_t* p) {
  return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | uint32_t(p[3]);
}

const PPCRegister& gpr(const PPCContext& c, int i) {
  const PPCRegister* gprs[32] = {&c.r0, &c.r1, &c.r2, &c.r3, &c.r4, &c.r5, &c.r6, &c.r7,
                                 &c.r8, &c.r9, &c.r10, &c.r11, &c.r12, &c.r13, &c.r14, &c.r15,
                                 &c.r16, &c.r17, &c.r18, &c.r19, &c.r20, &c.r21, &c.r22, &c.r23,
                                 &c.r24, &c.r25, &c.r26, &c.r27, &c.r28, &c.r29, &c.r30, &c.r31};
  return *gprs[i];
}

std::vector<std::pair<size_t, size_t>> integer_fields(const PPCContext& c) {
  const auto* b = reinterpret_cast<const uint8_t*>(&c);
  std::vector<std::pair<size_t, size_t>> out;
  auto add = [&](const void* p, size_t n) { out.emplace_back(static_cast<const uint8_t*>(p) - b, n); };
  for (int i = 0; i < 32; ++i) add(&gpr(c, i), sizeof(PPCRegister));
  add(&c.lr, sizeof(c.lr));
  add(&c.ctr, sizeof(c.ctr));
  add(&c.xer, sizeof(c.xer));
  const PPCCRRegister* crs[8] = {&c.cr0, &c.cr1, &c.cr2, &c.cr3, &c.cr4, &c.cr5, &c.cr6, &c.cr7};
  for (auto* r : crs) add(r, sizeof(*r));
  return out;
}

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
  for (size_t i = 0; i < n; ++i) {
    s += digits[p[i] >> 4];
    s += digits[p[i] & 15];
  }
  return s;
}

#if LRB_NATIVE
std::string page_list(const std::vector<uint32_t>& pages) {
  std::string s;
  for (uint32_t p : pages) s += (s.empty() ? "" : ",") + std::to_string(p);
  return s.empty() ? "-" : s;
}
#endif
static_assert(kWatched.size() == 4 && kWatched[0] == 4 && kWatched[3] == 12, "watched page set");

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
  ctx.fpscr.csr = 0;
}

void fill_region(Env& env, SplitMix& rng) {
  for (uint32_t i = 0; i < kAliasSize; i += 8) {
    const uint64_t v = rng.next();
    std::memcpy(env.alias + i, &v, 8);
  }
}

// ---------------------------------------------------------------- invalidations
struct Invalidations {
  unsigned count = 0;
  uint32_t per_page[kPages] = {};
  bool bad_range = false, inexact_seen = false;
};
Invalidations g_inv;

std::pair<uint32_t, uint32_t> invalidated(void* opaque, uint32_t physical, uint32_t length, bool exact) {
  auto& s = *static_cast<Invalidations*>(opaque);
  ++s.count;
  if (physical < kAliasPhysical || length != kPage || (physical & (kPage - 1)) ||
      physical - kAliasPhysical >= kAliasSize)
    s.bad_range = true;
  else
    ++s.per_page[(physical - kAliasPhysical) / kPage];
  s.inexact_seen = s.inexact_seen || !exact;
  return {physical, length};  // Unwatch exactly the reported page.
}

// ---------------------------------------------------------------- code ranges
#if LRB_NATIVE
struct CodeRange {
  const char* name;
  uintptr_t begin = 0, end = 0;
};
// Generated symbols (the bodies' strong names) whose machine code may hold an
// admitted store. Filled from the executable's own ELF symbol table (native).
std::vector<CodeRange> g_ranges = {
    {"__imp__sub_820E7440"}, {"__imp__sub_820EB7D8"}, {"__imp__sub_820E78A0"}, {"__imp__sub_820EB350"},
    {"__imp__sub_820E7328"}, {"__imp__sub_820F7978"}, {"__imp____savegprlr_29"}, {"__imp____restgprlr_29"}};

const CodeRange& code_range(std::string_view name) {
  for (const CodeRange& r : g_ranges)
    if (name == r.name) return r;
  require(false, "known code range");
  return g_ranges[0];
}

// Ordinary code before any session: read st_value/st_size of each generated
// symbol from /proc/self/exe and relocate by the load bias derived from the
// weak alias address of sub_820E7440 (same address as its __imp__ body).
void load_code_ranges() {
  std::FILE* f = std::fopen("/proc/self/exe", "rb");
  require(f != nullptr, "open /proc/self/exe");
  std::vector<uint8_t> elf;
  uint8_t chunk[65536];
  for (size_t n; (n = std::fread(chunk, 1, sizeof(chunk), f)) > 0;) elf.insert(elf.end(), chunk, chunk + n);
  std::fclose(f);
  require(elf.size() > sizeof(Elf64_Ehdr) && std::memcmp(elf.data(), ELFMAG, SELFMAG) == 0, "own ELF image");
  Elf64_Ehdr eh;
  std::memcpy(&eh, elf.data(), sizeof(eh));
  require(eh.e_ident[EI_CLASS] == ELFCLASS64 && eh.e_shentsize == sizeof(Elf64_Shdr) &&
              eh.e_shoff + uint64_t(eh.e_shnum) * sizeof(Elf64_Shdr) <= elf.size(),
          "ELF64 section table");
  auto section = [&](unsigned i) {
    Elf64_Shdr sh;
    std::memcpy(&sh, elf.data() + eh.e_shoff + uint64_t(i) * sizeof(Elf64_Shdr), sizeof(sh));
    return sh;
  };
  std::vector<std::pair<std::string, Elf64_Sym>> symbols;
  for (unsigned i = 0; i < eh.e_shnum; ++i) {
    const Elf64_Shdr sh = section(i);
    if (sh.sh_type != SHT_SYMTAB) continue;
    require(sh.sh_link < eh.e_shnum && sh.sh_entsize == sizeof(Elf64_Sym) && sh.sh_offset + sh.sh_size <= elf.size(),
            "symbol table bounds");
    const Elf64_Shdr strtab = section(sh.sh_link);
    require(strtab.sh_offset + strtab.sh_size <= elf.size(), "string table bounds");
    for (uint64_t off = 0; off + sizeof(Elf64_Sym) <= sh.sh_size; off += sizeof(Elf64_Sym)) {
      Elf64_Sym sym;
      std::memcpy(&sym, elf.data() + sh.sh_offset + off, sizeof(sym));
      if (ELF64_ST_TYPE(sym.st_info) != STT_FUNC || sym.st_name >= strtab.sh_size || sym.st_shndx == SHN_UNDEF)
        continue;
      const char* name = reinterpret_cast<const char*>(elf.data() + strtab.sh_offset + sym.st_name);
      symbols.emplace_back(std::string(name, strnlen(name, strtab.sh_size - sym.st_name)), sym);
    }
  }
  auto find = [&](std::string_view name) {
    const Elf64_Sym* found = nullptr;
    for (const auto& [n, sym] : symbols)
      if (n == name) {
        require(found == nullptr, "unique generated symbol");
        found = &sym;
      }
    require(found != nullptr && found->st_size > 0, "generated symbol with size in the symbol table");
    return *found;
  };
  const uintptr_t bias = reinterpret_cast<uintptr_t>(&sub_820E7440) - find("__imp__sub_820E7440").st_value;
  for (CodeRange& r : g_ranges) {
    const Elf64_Sym sym = find(r.name);
    r.begin = bias + sym.st_value;
    r.end = r.begin + sym.st_size;
  }
  require(code_range("__imp__sub_820EB7D8").begin == reinterpret_cast<uintptr_t>(&sub_820EB7D8) &&
              code_range("__imp__sub_820E78A0").begin == reinterpret_cast<uintptr_t>(&sub_820E78A0) &&
              code_range("__imp__sub_820EB350").begin == reinterpret_cast<uintptr_t>(&sub_820EB350) &&
              code_range("__imp__sub_820E7328").begin == reinterpret_cast<uintptr_t>(&sub_820E7328) &&
              code_range("__imp__sub_820F7978").begin == reinterpret_cast<uintptr_t>(&sub_820F7978),
          "symbol ranges agree with the weak-alias entry points");
  for (size_t i = 0; i < g_ranges.size(); ++i)
    for (size_t j = i + 1; j < g_ranges.size(); ++j)
      require(g_ranges[i].end <= g_ranges[j].begin || g_ranges[j].end <= g_ranges[i].begin,
              "generated code ranges disjoint");
}

std::string range_name(uintptr_t pc, uintptr_t* offset) {
  for (const CodeRange& r : g_ranges)
    if (pc >= r.begin && pc < r.end) {
      *offset = pc - r.begin;
      return r.name;
    }
  *offset = 0;
  return "?";
}

void authorize(const std::vector<std::string>& names) {
  std::vector<lwr_range> ranges;
  for (const std::string& n : names) {
    const CodeRange& r = code_range(n);
    ranges.push_back({r.begin, r.end});
  }
  require(lwr_authorize(ranges.data(), unsigned(ranges.size())) == 0, "authorize generated code ranges");
}
#endif

// ---------------------------------------------------------------- watch helpers
uint8_t* page_host(Env& env, uint32_t n) { return host(env, P(n)); }

bool watched_bit(Env& env, uint32_t n) { return lrb::host_page_watched(env.heap, P(n)); }

void verify_plain(Env& env, const char* what) {
  for (uint32_t n = 0; n < kPages; ++n)
    require(lrb::host_access(page_host(env, n)) == rex::memory::PageAccess::kReadWrite && !watched_bit(env, n), what);
}

#if LRB_NATIVE
void watch(Env& env, uint32_t n) {
  env.bs->memory().EnablePhysicalMemoryAccessCallbacks(kAliasPhysical + n * kPage, kPage, true, false);
  require(lrb::host_access(page_host(env, n)) == rex::memory::PageAccess::kReadOnly && watched_bit(env, n),
          "real SDK watch: allocating alias page read-only and watched");
}

// Ordinary-code drain into the real SDK invalidation path (never the MMIO
// exception callback: it re-checks protection and skips an already
// unprotected page without invalidating).
bool trigger(Env& env, uint32_t n) {
  return env.bs->memory().TriggerPhysicalMemoryCallbacks(rex::thread::global_critical_region::AcquireDirect(),
                                                         P(n), 1, true, false, true);
}
#endif

// ---------------------------------------------------------------- cases
struct Spec {
  std::string id;
  const char* function;
  uint32_t guest;
  GuestFn fn;
  uint64_t seed;
  std::vector<std::string> closure;  // Generated symbols the call may execute.
  std::vector<uint32_t> expect;      // Watched pages the call must claim (sorted).
};
struct Setup {
  Env& env;
  PPCContext& ctx;
  std::vector<Range> writable;
  std::vector<std::string> trace;
  std::function<bool(const PPCContext&, const PPCContext&, const uint8_t*, const uint8_t*)> model;
};

std::string semantic_record(Env& env, const Spec& spec, const Setup& setup, const std::string& input_digest,
                            const PPCContext& before_ctx, const PPCContext& after_ctx,
                            const std::vector<uint8_t>& before) {
  const auto fields = integer_fields(after_ctx);
  std::vector<bool> integer_byte(sizeof(PPCContext), false);
  for (auto [offset, size] : fields)
    for (size_t i = 0; i < size; ++i) integer_byte[offset + i] = true;
  const auto* rb = reinterpret_cast<const uint8_t*>(&before_ctx);
  const auto* ra = reinterpret_cast<const uint8_t*>(&after_ctx);
  for (size_t i = 0; i < sizeof(PPCContext); ++i)
    require(integer_byte[i] || rb[i] == ra[i], (spec.id + ": non-integer context state unchanged").c_str());
  std::string delta;
  unsigned changed = 0;
  for (uint32_t i = 0; i < kAliasSize;) {
    if (env.alias[i] == before[i]) {
      ++i;
      continue;
    }
    uint32_t j = i;
    while (j < kAliasSize && env.alias[j] != before[j]) ++j;
    for (uint32_t k = i; k < j; ++k) {
      bool declared = false;
      for (const Range& r : setup.writable) declared = declared || (kAliasVa + k >= r.begin && kAliasVa + k < r.end);
      require(declared, (spec.id + ": every changed byte lies in a declared region").c_str());
    }
    char head[32];
    std::snprintf(head, sizeof(head), "%s%x:", delta.empty() ? "" : ",", i);
    delta += head;
    delta += hex_bytes(env.alias + i, j - i);
    changed += j - i;
    i = j;
  }
  std::string trace, expected_trace;
  for (size_t i = 0; i < g_trace_count; ++i) trace += (i ? "," : "") + std::string(g_trace[i]);
  for (size_t i = 0; i < setup.trace.size(); ++i)
    expected_trace += (i ? "," : "") + std::string("__imp__") + setup.trace[i];
  require(!g_trace_overflow && trace == expected_trace, (spec.id + ": entered-function trace").c_str());
  require(setup.model(before_ctx, after_ctx, before.data(), env.alias), (spec.id + ": host model").c_str());
  std::string writable;
  for (const Range& r : setup.writable) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%s%08x-%08x", writable.empty() ? "" : ",", r.begin, r.end);
    writable += buf;
  }
  char guest[16];
  std::snprintf(guest, sizeof(guest), "%08x", spec.guest);
  return "LWR_CASE_V1|id=" + spec.id + "|fn=" + spec.function + "|guest=" + guest + "|seed=" +
         std::to_string(spec.seed) + "|input=" + input_digest + "|before=" + integer_state(before_ctx) +
         "|after=" + integer_state(after_ctx) + "|nonint=unchanged|writable=" + writable +
         "|changed=" + std::to_string(changed) + "|delta=" + delta + "|trace=" + trace + "|model=pass";
}

constexpr unsigned kExpectedClaims = 9;  // Sum of Spec::expect sizes in Cases::all().

#if LRB_NATIVE
// Ordinary-code witness for the traced gate (stderr, exact bytes).
struct Witness {
  const char* mode;
  char token[33] = {};
  bool valid = false;
  Witness(const char* m, const char* t) : mode(m) {
    valid = t && std::strlen(t) == 32;
    for (unsigned i = 0; valid && i < 32; ++i) valid = (t[i] >= '0' && t[i] <= '9') || (t[i] >= 'a' && t[i] <= 'f');
    if (valid) std::memcpy(token, t, 33);
  }
  void emit(const char* phase, uintptr_t address) const {
    std::array<char, 256> line{};
    const int n = std::snprintf(line.data(), line.size(),
                                "LWR_GATE_V1 token=%s mode=%s phase=%s claims=%u invalidations=%u address=0x%llx\n",
                                token, mode, phase, lwr_claim_count(), g_inv.count,
                                static_cast<unsigned long long>(address));
    if (n > 0 && static_cast<size_t>(n) < line.size()) {
      (void)std::fwrite(line.data(), 1, static_cast<size_t>(n), stderr);
      (void)std::fflush(stderr);
    }
  }
};
Witness* g_witness = nullptr;
bool g_emit_claims = false;
#endif

// One execution of a case. `watched` only on native builds.
std::string execute(Env& env, const Spec& spec, const std::function<void(Setup&)>& prepare, bool watched) {
  SplitMix rng{spec.seed};
  fill_region(env, rng);
  alignas(64) PPCContext ctx;
  init_context(ctx, rng);
  Setup setup{env, ctx, {}, {}, {}};
  prepare(setup);
  for (const Range& r : setup.writable)
    require(r.begin <= r.end && r.begin >= kAliasVa && r.end <= kAliasVa + kAliasSize, "declared range in region");
  std::vector<uint8_t> before(env.alias, env.alias + kAliasSize);
  alignas(64) PPCContext ctx_before;
  std::memcpy(static_cast<void*>(&ctx_before), &ctx, sizeof(ctx));
  std::string input = "region=" + std::to_string(kAliasVa) + ":";
  {
    Sha256 h;
    h.update(before.data(), before.size());
    input += h.hex();
  }
  input += " " + integer_state(ctx_before);
  const std::string input_digest = sha256(input);
  verify_plain(env, "region plain before the case");
#if LRB_NATIVE
  if (watched) {
    for (uint32_t n : kWatched) watch(env, n);
    require(lwr_open() == 0, "open the LWR session");
    for (uint32_t n : kWatched) require(lwr_register_page(page_host(env, n)) == 0, "register watched page");
    g_inv = Invalidations{};
    authorize(spec.closure);
  }
#else
  require(!watched, "watched runs are native only");
#endif
  g_trace_count = 0;
  g_trace_overflow = false;
  const unsigned invalidations_before = g_inv.count;
  spec.fn(ctx, env.base);  // The generated code runs here.
  if (!watched) require(g_inv.count == invalidations_before, "ordinary run: no invalidation");
#if LRB_NATIVE
  if (watched) {
    require(lwr_revoke() == 0, "revoke after the generated call");
    // Claims: exactly the expected watched pages, once each, from an
    // authorized generated instruction, before the store committed.
    std::vector<uint32_t> claimed;
    std::string details;
    for (unsigned i = 0; i < lwr_claim_count(); ++i) {
      lwr_claim c{};
      require(lwr_get_claim(i, &c) == 0, "read claim");
      const uintptr_t first = reinterpret_cast<uintptr_t>(env.alias);
      require(c.page >= first && c.page < first + kAliasSize && (c.page - first) % kPage == 0, "claim page in region");
      const uint32_t n = uint32_t((c.page - first) / kPage);
      require(std::find(kWatched.begin(), kWatched.end(), n) != kWatched.end(), "claimed page is registered");
      require(std::find(claimed.begin(), claimed.end(), n) == claimed.end(), "one claim per page");
      claimed.push_back(n);
      require(c.address >= c.effective && c.address - c.effective < c.width && c.effective >= c.page &&
                  c.effective + c.width <= c.page + kPage,
              "kernel address inside the decoded single-page store");
      require((c.width == 1 || c.width == 2 || c.width == 4 || c.width == 8) && c.error == 7ul,
              "admitted width and write fault");
      uintptr_t offset = 0;
      const std::string fn = range_name(c.instruction, &offset);
      require(std::find(spec.closure.begin(), spec.closure.end(), fn) != spec.closure.end(),
              "fault site inside an authorized generated function");
      const uint32_t at = uint32_t(c.effective - first);
      require(std::memcmp(c.before, before.data() + at, c.width) == 0, "store had not committed at the fault");
      require(lwr_page_state(page_host(env, n)) == LWR_PAGE_CLAIMED, "claimed page state");
      char line[320];
      std::snprintf(line, sizeof(line),
                    "LWR_CLAIM_V1|id=%s|n=%u|page=%u|fn=%s|offset=0x%lx|width=%u|length=%u|address=0x%x|"
                    "effective=0x%x|error=%lu|before=%s",
                    spec.id.c_str(), i, n, fn.c_str(), static_cast<unsigned long>(offset), c.width, c.length,
                    unsigned(c.address - first), at, c.error, hex_bytes(c.before, c.width).c_str());
      env.claims.push_back(line);
      if (g_witness && g_emit_claims) g_witness->emit("claim", c.address);
    }
    std::vector<uint32_t> sorted = claimed;
    std::sort(sorted.begin(), sorted.end());
    require(sorted == spec.expect, (spec.id + ": claimed exactly the expected watched pages").c_str());
    // Restart completion: a claimed page is writable but still SDK-watched
    // (the handler touched no SDK state); an unclaimed one is untouched.
    for (uint32_t n : kWatched) {
      const bool c = std::find(claimed.begin(), claimed.end(), n) != claimed.end();
      require(watched_bit(env, n), "SDK watch bit still set before the drain");
      require(lrb::host_access(page_host(env, n)) ==
                  (c ? rex::memory::PageAccess::kReadWrite : rex::memory::PageAccess::kReadOnly),
              "page protection after restart");
      if (!c) require(lwr_page_state(page_host(env, n)) == LWR_PAGE_ARMED, "unclaimed page still armed");
    }
    require(g_inv.count == 0, "no invalidation before the ordinary-code drain");
    for (uint32_t n : claimed) require(trigger(env, n), "drain: real SDK invalidation for a claimed page");
    require(!g_inv.bad_range && (claimed.empty() || g_inv.inexact_seen) && g_inv.count == claimed.size(),
            "one invalidation per claim (SDK AccessViolation parameters: unwatch_exact_range=false)");
    for (uint32_t n : kWatched) {
      const bool c = std::find(claimed.begin(), claimed.end(), n) != claimed.end();
      require(g_inv.per_page[n] == (c ? 1u : 0u), "invalidation only for the claimed page");
      require(watched_bit(env, n) == !c, "drain unwatches exactly the claimed pages");
    }
    // Cleanup: unwatch unclaimed pages through the same SDK path (counted
    // separately), close the session, then every page is plain again.
    std::vector<uint32_t> cleanup;
    for (uint32_t n : kWatched)
      if (std::find(claimed.begin(), claimed.end(), n) == claimed.end()) {
        require(trigger(env, n), "cleanup: unwatch an unclaimed page");
        cleanup.push_back(n);
      }
    require(g_inv.count == claimed.size() + cleanup.size(), "cleanup invalidations");
    require(lwr_close() == 0 && lwr_claim_count() == 0, "close the LWR session");
    require(lrb_owns_sigsegv() == 1, "LRB owner still exclusive");
    std::string invalidations;
    for (uint32_t n : sorted)
      invalidations += (invalidations.empty() ? "" : ",") + std::to_string(n) + ":" + std::to_string(g_inv.per_page[n]);
    env.restarts.push_back("LWR_RESTART_V1|id=" + spec.id + "|watched=4,5,9,12|claimed=" + page_list(sorted) +
                           "|invalidations=" + (invalidations.empty() ? "-" : invalidations) +
                           "|cleanup=" + page_list(cleanup) + "|restart=complete|session=closed");
    env.total_claims += unsigned(claimed.size());
  }
#endif
  verify_plain(env, "region plain after the case (protection and watch restored)");
  return semantic_record(env, spec, setup, input_digest, ctx_before, ctx, before);
}

bool bytes_equal(const uint8_t* a, const uint8_t* b, size_t n) { return n == 0 || std::memcmp(a, b, n) == 0; }

struct Cases {
  Env& env;
  bool native_watched;
  uint64_t next_seed = 0x4C57520000000001ull;  // "LWR"

  void run(const Spec& spec, const std::function<void(Setup&)>& prepare) {
    const std::string ordinary = execute(env, spec, prepare, false);
    env.ordinary.push_back(ordinary);
    if (native_watched) env.watched.push_back(execute(env, spec, prepare, true));
    ++env.cases;
  }

  void memset_case(const std::string& id, uint32_t dst, uint32_t n, uint32_t c, std::vector<uint32_t> expect) {
    run({id, "sub_820E7440", 0x820E7440u, sub_820E7440, next_seed++, {"__imp__sub_820E7440"}, expect},
        [&](Setup& s) {
          s.ctx.r3.u64 = dst; s.ctx.r4.u64 = c; s.ctx.r5.u64 = n;
          s.writable = {{dst, dst + n}};
          s.trace = {"sub_820E7440"};
          s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t*, const uint8_t* after) {
            const uint8_t* p = after + (dst - kAliasVa);
            for (uint32_t i = 0; i < n; ++i)
              if (p[i] != uint8_t(c)) return false;
            return a.r3.u64 == dst;
          };
        });
  }

  void copy_case(const std::string& id, const char* name, uint32_t guest, GuestFn fn, uint32_t dst, uint32_t src,
                 uint32_t n, bool via_stack, std::vector<uint32_t> expect) {
    run({id, name, guest, fn, next_seed++, {std::string("__imp__") + name}, expect}, [&](Setup& s) {
      require(dst + n <= src || src + n + 16 <= dst, "copy regions disjoint");
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = src; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      if (via_stack) s.writable.push_back({kStackTop - 8, kStackTop});  // std r3,-8(r1)
      s.trace = {name};
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t* b, const uint8_t* after) {
        return bytes_equal(after + (dst - kAliasVa), b + (src - kAliasVa), n) && a.r3.u64 == dst &&
               a.r1.u64 == kStackTop;
      };
    });
  }

  void erase_case(const std::string& id, uint32_t vec, uint32_t elems, uint32_t ret, uint32_t count, uint32_t index,
                  std::vector<uint32_t> expect) {
    run({id, "sub_820F7978", 0x820F7978u, sub_820F7978, next_seed++,
         {"__imp__sub_820F7978", "__imp____savegprlr_29", "__imp__sub_820E78A0", "__imp__sub_820EB350",
          "__imp____restgprlr_29"},
         expect},
        [&](Setup& s) {
          put_be32(env, vec, elems);
          put_be32(env, vec + 4, elems + 4 * count);
          const uint32_t pos = elems + 4 * index;
          s.ctx.r3.u64 = ret; s.ctx.r4.u64 = vec; s.ctx.r5.u64 = pos;
          s.writable = {{ret, ret + 4}, {vec + 4, vec + 8}, {pos, elems + 4 * count}, {kStackTop - 128, kStackTop}};
          s.trace = {"sub_820F7978", "__savegprlr_29", "sub_820E78A0", "sub_820EB350", "__restgprlr_29"};
          s.model = [=](const PPCContext& b, const PPCContext& a, const uint8_t* before, const uint8_t* after) {
            const uint8_t* eb = before + (elems - kAliasVa);
            const uint8_t* ea = after + (elems - kAliasVa);
            for (uint32_t i = 0; i + 1 < count; ++i)
              if (!bytes_equal(ea + 4 * i, eb + 4 * (i < index ? i : i + 1), 4)) return false;
            return get_be32(after + (vec + 4 - kAliasVa)) == elems + 4 * (count - 1) &&
                   get_be32(after + (vec - kAliasVa)) == elems && get_be32(after + (ret - kAliasVa)) == pos &&
                   a.r3.u64 == ret && a.r1.u64 == kStackTop && a.lr == kReturnLr && a.r29.u64 == b.r29.u64 &&
                   a.r30.u64 == b.r30.u64 && a.r31.u64 == b.r31.u64;
          };
        });
  }

  void all() {
    memset_case("restart/single-store", P(4) + 0x101u, 1, 0xA5u, {4});
    memset_case("restart/memset-page", P(4), kPage, 0x3Cu, {4});
    memset_case("restart/memset-two-pages", P(4) + 0xF00u, 0x300u, 0x7Eu, {4, 5});
    memset_case("restart/memset-edges", P(9) + 1u, kPage - 1, 0xC3u, {9});
    memset_case("restart/neighbour-only", P(3), kPage, 0x11u, {});
    copy_case("restart/memcpy", "sub_820EB350", 0x820EB350u, sub_820EB350, P(12) + 0x18u, P(1) + 0x5u, 1000, true,
              {12});
    copy_case("restart/forward-copy", "sub_820EB7D8", 0x820EB7D8u, sub_820EB7D8, P(9) + 0xC01u, P(2) + 0x3u, 0x700u,
              false, {9});
    erase_case("restart/erase", P(5) + 0x100u, P(12) + 0x200u, P(14) + 0x40u, 64, 5, {5, 12});
  }
};

// ---------------------------------------------------------------- decoder self-test
// Hand-written generic x86-64 encodings (no generated bytes). Runs on every
// platform, so Windows exercises the exact decoder the signal path uses.
void decoder_selftest() {
  uint64_t regs[16];
  for (unsigned i = 0; i < 16; ++i) regs[i] = 0x1000u * (i + 1);
  struct Vector {
    std::array<uint8_t, 8> bytes;
    size_t size;
    int ok;
    unsigned width, length;
    uint64_t ea;
  };
  const Vector vectors[] = {
      {{0x89, 0x07}, 2, 1, 4, 2, 0x8000},                          // mov %eax,(%rdi)
      {{0x88, 0x14, 0x08}, 3, 1, 1, 3, 0x1000 + 0x2000},           // mov %dl,(%rax,%rcx,1)
      {{0x48, 0x89, 0x14, 0x08}, 4, 1, 8, 4, 0x3000},              // mov %rdx,(%rax,%rcx,1)
      {{0x42, 0x89, 0x3c, 0x30}, 4, 1, 4, 4, 0x1000 + 0xF000},     // mov %edi,(%rax,%r14,1)
      {{0x4f, 0x89, 0x14, 0x0b}, 4, 1, 8, 4, 0xC000 + 0xA000},     // mov %r10,(%r11,%r9,1)
      {{0x40, 0x88, 0x34, 0x10}, 4, 1, 1, 4, 0x1000 + 0x3000},     // mov %sil,(%rax,%rdx,1)
      {{0x89, 0x44, 0x15, 0xfc}, 4, 1, 4, 4, 0x6000 + 0x3000 - 4}, // mov %eax,-0x4(%rbp,%rdx,1)
      {{0x89, 0x54, 0x8d, 0x10}, 4, 1, 4, 4, 0x6000 + 0x2000 * 4 + 0x10},  // mov %edx,0x10(%rbp,%rcx,4)
      {{0x66, 0x89, 0x07}, 3, 1, 2, 3, 0x8000},                    // mov %ax,(%rdi)
      {{0x89, 0x87, 0x00, 0x01, 0x00, 0x00}, 6, 1, 4, 6, 0x8100},  // mov %eax,0x100(%rdi)
      {{0x89, 0x04, 0x24}, 3, 1, 4, 3, 0x5000},                    // mov %eax,(%rsp)
      {{0x41, 0x89, 0x04, 0x24}, 4, 1, 4, 4, 0xD000},              // mov %eax,(%r12)
      {{0x89, 0xc7}, 2, 0, 0, 0, 0},                               // mov %eax,%edi (register)
      {{0x89, 0x05, 0, 0, 0, 0}, 6, 0, 0, 0, 0},                   // RIP-relative
      {{0x89, 0x04, 0x25, 0, 0x10, 0, 0}, 7, 0, 0, 0, 0},          // no base (disp32)
      {{0x8b, 0x07}, 2, 0, 0, 0, 0},                               // load
      {{0xc7, 0x07, 1, 0, 0, 0}, 6, 0, 0, 0, 0},                   // immediate store
      {{0x0f, 0x11, 0x07}, 3, 0, 0, 0, 0},                         // movups store
      {{0xf0, 0x89, 0x07}, 3, 0, 0, 0, 0},                         // lock prefix
      {{0x64, 0x89, 0x07}, 3, 0, 0, 0, 0},                         // fs segment
      {{0x67, 0x89, 0x07}, 3, 0, 0, 0, 0},                         // address size
      {{0x66, 0x48, 0x89, 0x07}, 4, 0, 0, 0, 0},                   // 66 + REX.W
      {{0x66, 0x88, 0x07}, 3, 0, 0, 0, 0},                         // 66 + 88
      {{0x48, 0x88, 0x07}, 3, 0, 0, 0, 0},                         // REX.W + 88
      {{0x48, 0x66, 0x89, 0x07}, 4, 0, 0, 0, 0},                   // REX before 66
      {{0x89, 0x47}, 2, 0, 0, 0, 0},                               // truncated disp8
      {{0x89, 0x04}, 2, 0, 0, 0, 0},                               // truncated SIB
  };
  for (const Vector& v : vectors) {
    lwr_store s{};
    const int ok = lwr_decode_store(v.bytes.data(), v.size, regs, &s);
    require(ok == v.ok, "decoder admission");
    if (ok) require(s.width == v.width && s.length == v.length && s.effective == v.ea, "decoder width/length/address");
  }
  lwr_store s{};
  require(lwr_decode_store(vectors[0].bytes.data(), 1, regs, &s) == 0, "decoder never reads past avail");
}

// ---------------------------------------------------------------- region lifecycle
void allocate_region(Env& env) {
  auto& m = env.bs->memory();
  require(rex::memory::page_size() == kPage, "4 KiB host pages");
  env.heap = m.LookupHeap(kAliasVa);
  require(env.heap && env.heap->heap_type() == rex::memory::HeapType::kGuestPhysical,
          "region heap is the vA physical alias heap");
  require(env.heap->AllocFixed(kAliasVa, kAliasSize, kAliasSize,
                               rex::memory::kMemoryAllocationReserve | rex::memory::kMemoryAllocationCommit,
                               rex::memory::kMemoryProtectRead | rex::memory::kMemoryProtectWrite),
          "real fixed vA physical allocation");
  require(m.GetPhysicalAddress(kAliasVa) == kAliasPhysical, "region physical address");
  env.base = m.virtual_membase();
  require(m.TranslateVirtual(kAliasVa) == env.base + kAliasVa, "region translation is base + guest");
  env.alias = m.TranslateVirtual(kAliasVa);
  verify_plain(env, "region pages plain after allocation");
}

void release_region(Env& env) {
  uint32_t released = 0;
  require(env.heap->Release(kAliasVa, &released) && released == kAliasSize, "region released exactly");
}

#if LRB_NATIVE
// ---------------------------------------------------------------- traced modes
constexpr std::array<std::string_view, 11> kFatal = {
    "lwr-unregistered", "lwr-unauthorized", "lwr-consumed", "lwr-wrong-function", "lwr-host-store", "lwr-read",
    "lwr-cross-page",   "lwr-wide",         "lwr-signal-origin", "lwr-foreign-thread", "lwr-after-release"};

struct Foreign {
  Env* env;
  pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
  pthread_cond_t cond = PTHREAD_COND_INITIALIZER;
  bool ready = false;
};
void* foreign_session(void* raw) {
  auto* f = static_cast<Foreign*>(raw);
  require(lwr_open() == 0 && lwr_register_page(page_host(*f->env, 4)) == 0, "foreign thread session and page");
  authorize({"__imp__sub_820E7440"});
  pthread_mutex_lock(&f->lock);
  f->ready = true;
  pthread_cond_signal(&f->cond);
  pthread_mutex_unlock(&f->lock);
  for (;;) pause();
  return nullptr;
}

// Each mode prepares one unsupported fault and emits "begin" with the exact
// host address the kernel must report (0 for a non-kernel signal). Nothing
// admits it: the LRB owner must terminate in signal context.
[[noreturn]] void run_fatal(Env& env, const Witness& w, std::string_view mode) {
  alignas(64) PPCContext ctx;
  SplitMix rng{0x4C57524600000001ull};
  fill_region(env, rng);
  init_context(ctx, rng);
  const uintptr_t p4 = reinterpret_cast<uintptr_t>(page_host(env, 4));
  auto memset_p4 = [&]() {
    ctx.r3.u64 = P(4); ctx.r4.u64 = 0x5A; ctx.r5.u64 = 64;
    sub_820E7440(ctx, env.base);
  };
  if (mode == "lwr-foreign-thread") {
    watch(env, 4);
    static Foreign f;
    f.env = &env;
    pthread_t t;
    require(pthread_create(&t, nullptr, foreign_session, &f) == 0, "start the foreign session thread");
    pthread_mutex_lock(&f.lock);
    while (!f.ready) pthread_cond_wait(&f.cond, &f.lock);
    pthread_mutex_unlock(&f.lock);
    require(lwr_open() == EBUSY, "the session belongs to the other thread");
    w.emit("begin", p4);
    memset_p4();
    require(false, "foreign-thread store returned");
  }
  watch(env, 4);
  if (mode == "lwr-wide" || mode == "lwr-cross-page") watch(env, 9);
  require(lwr_open() == 0, "open the LWR session");
  if (mode == "lwr-unregistered") {
    authorize({"__imp__sub_820E7440"});
    w.emit("begin", p4);
    memset_p4();
    require(false, "unregistered store returned");
  }
  require(lwr_register_page(page_host(env, 4)) == 0, "register P4");
  if (mode == "lwr-unauthorized") {
    w.emit("begin", p4);
    memset_p4();
    require(false, "unauthorized store returned");
  }
  if (mode == "lwr-after-release") {
    authorize({"__imp__sub_820E7440"});
    require(lwr_revoke() == 0 && lwr_close() == 0, "session released");
    w.emit("begin", p4);
    memset_p4();
    require(false, "post-release store returned");
  }
  if (mode == "lwr-consumed") {
    g_inv = Invalidations{};
    authorize({"__imp__sub_820E7440"});
    w.emit("begin", p4);
    memset_p4();
    require(lwr_revoke() == 0 && lwr_claim_count() == 1 && lwr_page_state(page_host(env, 4)) == LWR_PAGE_CLAIMED,
            "first fault admitted once");
    w.emit("claimed", p4);
    require(trigger(env, 4) && g_inv.count == 1 && !watched_bit(env, 4), "drained through the real SDK path");
    watch(env, 4);  // The SDK re-watches the page; the LWR slot stays consumed.
    authorize({"__imp__sub_820E7440"});
    w.emit("rewatched", p4);
    memset_p4();
    require(false, "consumed-slot store returned");
  }
  if (mode == "lwr-wrong-function") {
    authorize({"__imp__sub_820EB350"});
    w.emit("begin", p4);
    memset_p4();
    require(false, "wrong-function store returned");
  }
  if (mode == "lwr-host-store") {
    authorize({"__imp__sub_820E7440"});
    w.emit("begin", p4 + 0x10);
    *reinterpret_cast<volatile uint8_t*>(p4 + 0x10) = 1;  // Host code, not a generated site.
    require(false, "host store returned");
  }
  if (mode == "lwr-read") {
    // Test-only: make the registered page no-access so a generated LOAD faults there.
    require(mprotect(page_host(env, 4), kPage, PROT_NONE) == 0, "test-only no-access registered page");
    authorize({"__imp__sub_820E7328"});
    ctx.r3.u64 = P(2); ctx.r4.u64 = P(4); ctx.r5.u64 = 16;  // strncpy reads P4 first.
    w.emit("begin", p4);
    sub_820E7328(ctx, env.base);
    require(false, "read fault returned");
  }
  if (mode == "lwr-cross-page" || mode == "lwr-wide") {
    require(lwr_register_page(page_host(env, 9)) == 0, "register P9");
    const bool wide = mode == "lwr-wide";
    // Explicitly synthetic code range (lwr_test_leaf.S), never generated code.
    const lwr_range leaf = wide ? lwr_range{reinterpret_cast<uintptr_t>(&lwr_leaf_store128),
                                            reinterpret_cast<uintptr_t>(lwr_leaf_store128_end)}
                                : lwr_range{reinterpret_cast<uintptr_t>(&lwr_leaf_store32),
                                            reinterpret_cast<uintptr_t>(lwr_leaf_store32_end)};
    require(lwr_authorize(&leaf, 1) == 0, "authorize the synthetic leaf");
    uint8_t* target = wide ? page_host(env, 9) + 0x100 : page_host(env, 10) - 2;  // P9 watched, P10 plain.
    w.emit("begin", reinterpret_cast<uintptr_t>(target));
    if (wide) lwr_leaf_store128(target); else lwr_leaf_store32(target - 4, 0x01020304u);
    require(false, "synthetic store returned");
  }
  if (mode == "lwr-signal-origin") {
    authorize({"__imp__sub_820E7440"});
    w.emit("begin", 0);
    raise(SIGSEGV);
    require(false, "user SIGSEGV returned");
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
  const bool fatal = std::find(kFatal.begin(), kFatal.end(), mode) != kFatal.end();
  const bool traced_positive = mode == "lwr-traced-positive";
  require(fatal || traced_positive || mode == "normal", "unsupported native mode");
  const rlimit no_core{0, 0};
  require(setrlimit(RLIMIT_CORE, &no_core) == 0, "disable core dumps for fatal modes");
  Witness witness(mode.data(), std::getenv("LRB_GATE_TOKEN"));
  if (fatal || traced_positive) {
    require(witness.valid, "traced modes require a 32-hex LRB_GATE_TOKEN");
    g_witness = &witness;
  }
  load_code_ranges();
#else
  const bool fatal = false;
  require(mode == "normal", "ordinary build supports normal mode only");
#endif
  decoder_selftest();
  lrb::Bootstrap bs(fatal ? lrb::ShmPolicy::kUnlinkAfterMap : lrb::ShmPolicy::kSdkContract);
  bs.start(std::getenv("LRB_OWNERSHIP_FILE"), mode.data());
  Env env;
  env.bs = &bs;
  allocate_region(env);
  void* handle = bs.memory().RegisterPhysicalMemoryInvalidationCallback(invalidated, &g_inv);
  require(handle != nullptr, "register the invalidation callback");
#if LRB_NATIVE
  require(lrb_owns_sigsegv() == 1, "LRB owner exclusive before generated code");
  if (fatal) run_fatal(env, witness, mode);
  // lwr-traced-positive is the normal matrix under ptrace: each kernel
  // SEGV_ACCERR stop must match the claim witnessed after its call.
  g_emit_claims = traced_positive;
#endif
  Cases cases{env, LRB_NATIVE != 0};
  cases.all();
  require(env.total_claims == (LRB_NATIVE ? kExpectedClaims : 0u), "claim total across the watched matrix");
#if LRB_NATIVE
  require(lrb_owns_sigsegv() == 1, "LRB owner still exclusive after generated code");
  require(bs.admitted_faults() == 0, "no LRB checked-access fault");
#endif
  require(bs.consumed_dispatches() == 0 && bs.declined_dispatches() == 0, "no MMIO-path SDK dispatch");
  bs.memory().UnregisterPhysicalMemoryInvalidationCallback(handle);
  release_region(env);

  Sha256 aggregate;
  for (const std::string& line : env.ordinary) {
    aggregate.update(sha256(line));
    aggregate.update("\n");
  }
  const std::string total = aggregate.hex();
  auto write = [](const char* variable, const std::vector<std::string>& lines, bool digest) {
    const char* path = std::getenv(variable);
    if (!path) return;
    std::FILE* f = std::fopen(path, "wb");
    require(f != nullptr, "open a results file");
    for (const std::string& line : lines) {
      const std::string text = digest ? line + "|digest=" + sha256(line) : line;
      require(std::fprintf(f, "%s\n", text.c_str()) > 0, "write a record");
    }
    require(std::fclose(f) == 0, "close a results file");
  };
  write("LWR_RESULTS_FILE", env.ordinary, true);
  write("LWR_WATCHED_FILE", env.watched, true);
  write("LWR_RESTART_FILE", env.restarts, true);
  write("LWR_CLAIMS_FILE", env.claims, false);
  // After the files exist (the gate keeps them on failure).
  if (LRB_NATIVE) require(env.watched == env.ordinary, "watched semantic records equal the ordinary ones");
  bs.stop();
  std::printf("LWR PASS cases=%u claims=%u checks=%u aggregate=%s native=%d\n", env.cases, env.total_claims,
              lrb::checks(), total.c_str(), LRB_NATIVE);
  return 0;
}

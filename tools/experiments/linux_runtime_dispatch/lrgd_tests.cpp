// Linux Runtime Generated Dispatch (LRGD) acceptance executable.
//
// Executes the ten audited LGE generated Rayman 3 HD functions (private,
// verbatim translation unit, codegen c7e96852...) through the REAL pinned
// ReXGlue runtime path:
//
//   rex::Runtime::Setup(PPCImageInfo, tool mode)
//     -> FunctionDispatcher::InitializeFunctionTable (real guest table at
//        IMAGE_BASE + IMAGE_SIZE in runtime-owned Memory)
//     -> FunctionDispatcher::SetFunction for each func_mappings row
//   rex::runtime::ThreadState (constructed directly; no XThread, no new thread)
//   FunctionDispatcher::Execute(thread_state, guest, args, n)
//     -> ThreadState::Bind, r1 -= 176, lr = 0xBCBCBCBC, fn(ctx, membase)
//
// The image info carries the PRODUCTION layout constants (r3hd_pch.h) and
// exactly the ten production PPCFuncMappings rows for the selected functions,
// with the same host symbols production uses. No image bytes are loaded: the
// selected bodies never read code memory.
//
// Every case is the unchanged LGE (124) or LWR (8) case: same seeds, same
// synthetic memory, same context fill. The dispatcher legitimately changes
// these observable things, each checked exactly here and re-derived by the gate:
//   T1 entry: the callee sees the LGE "before" state with lr = 0xBCBCBCBC
//      (whole PPCContext byte-compared at the first prologue hook);
//   T2 exit:  Execute restores r1 (+176) and the caller's lr; the callee's
//      final lr is not observable after Execute;
//   T2b r12:  a function that saves LR (erase: mflr r12, then __restgprlr_29
//      reloads r12) exits with r12 = the observed LR, i.e. the sentinel;
//   T3 memory: the same function stores that LR at its entry r1 - 8
//      (__savegprlr_29). Exactly that one declared 4-byte slot is normalized.
// Only cases declared `saves_lr` (the erase cases) receive T2b and T3.
// The reconstructed LGE_CASE_V1 / LWR_CASE_V1 lines must equal the audited
// Windows references byte for byte.
//
// Variants (one per subprocess, never mixed):
//   default-dispatch  unchanged SDK initialization; ordinary dispatch only;
//                     no project signal owner (nothing faults).
//   latch*            EXPERIMENTAL LRSO D1(a), test executable only: the SDK's
//                     own g_seh_initialized is set before Setup, the audited
//                     LRB handoff installs the single owner, ordinary dispatch
//                     plus LWR watched-page restarts through Execute.
// Windows builds (LRB_ORDINARY_ONLY) run default-dispatch only.
#include "lrb_bootstrap.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

#include <rex/image_info.h>
#include <rex/logging/api.h>
#include <rex/logging/types.h>
#include <rex/memory/utils.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/runtime.h>
#include <rex/system/function_dispatcher.h>
#include <rex/system/kernel_state.h>
#include <rex/system/mmio_handler.h>
#include <rex/system/thread_state.h>
#include <rex/system/xmemory.h>
#include <rex/thread/mutex.h>

#if LRB_NATIVE
#include <dlfcn.h>
#include <elf.h>
#include <pthread.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

#include <atomic>

#include <rex/exception_handler.h>

#include "lrb_owner.h"
#include "lwr_restart.h"
#endif

// ---- the selected generated functions (defined verbatim in lge_generated.cpp).
// Weak aliases of the __imp__ bodies: exactly the host symbols the production
// PPCFuncMappings rows name (r3hd_init.cpp).
extern "C" {
void sub_820E7440(PPCContext& __restrict ctx, uint8_t* base);  // memset
void sub_820EB7D8(PPCContext& __restrict ctx, uint8_t* base);  // forward copy
void sub_820E78A0(PPCContext& __restrict ctx, uint8_t* base);  // memmove
void sub_820EB350(PPCContext& __restrict ctx, uint8_t* base);  // memcpy (doubleword)
void sub_820E7328(PPCContext& __restrict ctx, uint8_t* base);  // strncpy
void sub_820E6D08(PPCContext& __restrict ctx, uint8_t* base);  // strstr
void sub_820F0A28(PPCContext& __restrict ctx, uint8_t* base);  // format-spec predicate
void sub_820F7978(PPCContext& __restrict ctx, uint8_t* base);  // vector erase(pos)
void __savegprlr_29(PPCContext& __restrict ctx, uint8_t* base);
void __restgprlr_29(PPCContext& __restrict ctx, uint8_t* base);
}

namespace {
using lrb::require;
using rex::X_STATUS;  // X_STATUS_SUCCESS expands to an unqualified cast.
using rex::memory::Memory;
using rex::memory::PageAccess;
using rex::runtime::FunctionDispatcher;
using rex::runtime::ThreadState;
static_assert(std::is_trivially_copyable_v<PPCContext>, "PPCContext snapshot by bytes");

// ------------------------------------------------------------------ image layout
// Production constants (private r3hd_pch.h; the gate checks them there).
constexpr uint32_t kImageBase = 0x82000000u;
constexpr uint32_t kImageSize = 0x00CE0000u;
constexpr uint32_t kCodeBase = 0x820E0000u;
constexpr uint32_t kCodeSize = 0x007425E4u;
constexpr uint32_t kThunkReserve = FunctionDispatcher::kThunkReserveSize;
static_assert(kThunkReserve == 0x10000u, "pinned thunk reserve");
constexpr uint32_t kTableBase = kImageBase + kImageSize;
constexpr uint32_t kTableSize = (kCodeSize + kThunkReserve) * 2;
constexpr uint32_t kUnregistered = kCodeBase;            // In range, never registered.
constexpr uint32_t kOutOfRange = kImageBase;             // Below code_base.
constexpr uint64_t kSentinelLr = 0xBCBCBCBCull;          // FunctionDispatcher::Execute.
constexpr uint64_t kPad = 64 + 112;                      // FunctionDispatcher::Execute.
constexpr uint64_t kNotFound = 0xDEADBABEull;            // FunctionDispatcher::Execute.
constexpr uint32_t kThreadId = 0x4C524744u;              // "LRGD"; not UINT_MAX (no system id).
constexpr uint64_t kReturnLr = 0x82FFF000ull;            // LGE/LWR synthetic caller LR.

struct Mapping {
  uint32_t guest;
  PPCFunc* host;
  const char* symbol;
};
// The ten production rows, in production (ascending) order.
const Mapping kMappings[] = {
    {0x820E6D08u, sub_820E6D08, "sub_820E6D08"},     {0x820E7328u, sub_820E7328, "sub_820E7328"},
    {0x820E73CCu, __savegprlr_29, "__savegprlr_29"}, {0x820E741Cu, __restgprlr_29, "__restgprlr_29"},
    {0x820E7440u, sub_820E7440, "sub_820E7440"},     {0x820E78A0u, sub_820E78A0, "sub_820E78A0"},
    {0x820EB350u, sub_820EB350, "sub_820EB350"},     {0x820EB7D8u, sub_820EB7D8, "sub_820EB7D8"},
    {0x820F0A28u, sub_820F0A28, "sub_820F0A28"},     {0x820F7978u, sub_820F7978, "sub_820F7978"}};
constexpr size_t kMappingCount = sizeof(kMappings) / sizeof(kMappings[0]);
PPCFuncMapping g_func_mappings[kMappingCount + 1];

rex::PPCImageInfo image_info() {
  for (size_t i = 0; i < kMappingCount; ++i) g_func_mappings[i] = {kMappings[i].guest, kMappings[i].host};
  g_func_mappings[kMappingCount] = {0, nullptr};
  rex::PPCImageInfo info{};
  info.code_base = kCodeBase;
  info.code_size = kCodeSize;
  info.image_base = kImageBase;
  info.image_size = kImageSize;
  info.func_mappings = g_func_mappings;
  info.rexcrt_heap = false;          // Production REXCRT_HEAP 0.
  info.register_modules = nullptr;   // Production: single binary.
  info.codegen_flags = {};           // Production: all eight flags false.
  return info;
}

// ------------------------------------------------------------------ SHA-256
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
  uint32_t below(uint32_t n) { return static_cast<uint32_t>(next() % n); }
};

std::string hex(uint64_t v) {
  char buf[24];
  std::snprintf(buf, sizeof(buf), "0x%" PRIx64, v);
  return buf;
}

// ------------------------------------------------------------------ records
std::string g_mode;
std::FILE* g_records = nullptr;

void record(const std::string& line) {
  if (!g_records) return;
  require(std::fprintf(g_records, "%s\n", line.c_str()) > 0 && std::fflush(g_records) == 0, "write an LRGD record");
}

// ------------------------------------------------------------------ call trace + dispatch witness
// M2Enter is the production prologue hook (m2_trace.h shim, recording only).
// At the FIRST entry of each Execute it snapshots the callee-observed context
// and the bound ThreadState; every entry must see the same context object.
constexpr size_t kTraceMax = 32;
const char* g_trace[kTraceMax];
size_t g_trace_count = 0;
bool g_trace_overflow = false;
alignas(64) PPCContext g_entry;
const PPCContext* g_entry_ctx = nullptr;
const ThreadState* g_entry_bound = nullptr;
const PPCContext* g_expected_ctx = nullptr;
bool g_ctx_mismatch = false;
}  // namespace

void M2Enter(const char* name, PPCContext& ctx) {
  if (g_trace_count == 0) {
    std::memcpy(static_cast<void*>(&g_entry), &ctx, sizeof(PPCContext));
    g_entry_ctx = &ctx;
    g_entry_bound = ThreadState::Get();
  }
  if (g_expected_ctx && &ctx != g_expected_ctx) g_ctx_mismatch = true;
  if (g_trace_count < kTraceMax)
    g_trace[g_trace_count++] = name;
  else
    g_trace_overflow = true;
}

namespace {
// ------------------------------------------------------------------ PPCContext helpers
PPCRegister& gpr(PPCContext& c, int i) {
  PPCRegister* gprs[32] = {&c.r0, &c.r1, &c.r2, &c.r3, &c.r4, &c.r5, &c.r6, &c.r7,
                           &c.r8, &c.r9, &c.r10, &c.r11, &c.r12, &c.r13, &c.r14, &c.r15,
                           &c.r16, &c.r17, &c.r18, &c.r19, &c.r20, &c.r21, &c.r22, &c.r23,
                           &c.r24, &c.r25, &c.r26, &c.r27, &c.r28, &c.r29, &c.r30, &c.r31};
  return *gprs[i];
}
const PPCRegister& gpr(const PPCContext& c, int i) { return gpr(const_cast<PPCContext&>(c), i); }

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

bool nonint_equal(const PPCContext& a, const PPCContext& b) {
  std::vector<bool> integer_byte(sizeof(PPCContext), false);
  for (auto [offset, size] : integer_fields(a))
    for (size_t i = 0; i < size; ++i) integer_byte[offset + i] = true;
  const auto* pa = reinterpret_cast<const uint8_t*>(&a);
  const auto* pb = reinterpret_cast<const uint8_t*>(&b);
  for (size_t i = 0; i < sizeof(PPCContext); ++i)
    if (!integer_byte[i] && pa[i] != pb[i]) return false;
  return true;
}

bool bytes_same(const PPCContext& a, const PPCContext& b) { return std::memcmp(&a, &b, sizeof(PPCContext)) == 0; }

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

uint32_t get_be32(const uint8_t* p) {
  return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | uint32_t(p[3]);
}
void set_be32(uint8_t* p, uint32_t value) {
  p[0] = uint8_t(value >> 24); p[1] = uint8_t(value >> 16); p[2] = uint8_t(value >> 8); p[3] = uint8_t(value);
}
bool bytes_equal(const uint8_t* a, const uint8_t* b, size_t n) { return n == 0 || std::memcmp(a, b, n) == 0; }

// ------------------------------------------------------------------ guest regions
// Two suites, each exactly its audited source layout, now inside RUNTIME-owned
// Memory:
//   lge: [guard][16 RW pages][guard] at 0x20000000 in the 4 KiB v00000000 heap;
//   lwr: 64 KiB vA physical alias allocation at 0xA4000000 (physical 0x04000000).
constexpr uint32_t kPage = 0x1000u;
constexpr uint32_t kLgeRegion = 0x20000000u;
constexpr uint32_t kLgeArena = kLgeRegion + kPage;
constexpr uint32_t kLgeArenaSize = 16 * kPage;
constexpr uint32_t kLgeGuardHigh = kLgeArena + kLgeArenaSize;
constexpr uint32_t kLgeRegionSize = kLgeArenaSize + 2 * kPage;
constexpr uint32_t kLgeStackTop = kLgeArena + kLgeArenaSize - 0x100u;
constexpr uint32_t kLgeDataEnd = kLgeArena + 0xC000u;
constexpr uint32_t kLwrVa = 0xA4000000u;
constexpr uint32_t kLwrPhysical = 0x04000000u;
constexpr uint32_t kLwrSize = 0x10000u;
constexpr uint32_t kLwrPages = kLwrSize / kPage;
constexpr uint32_t kLwrStackTop = kLwrVa + 15 * kPage + 0xF00u;
constexpr std::array<uint32_t, 4> kWatched = {4, 5, 9, 12};
static_assert(kWatched.size() == 4 && kWatched[0] == 4 && kWatched[3] == 12, "watched page set (LWR)");
constexpr uint32_t P(uint32_t n) { return kLwrVa + n * kPage; }

struct Range {
  uint32_t begin, end;  // Guest [begin, end).
};

enum class Suite { kLge, kLwr };

struct Region {
  Suite suite;
  const char* name;      // "lge" / "lwr".
  const char* prefix;    // Canonical record prefix.
  const char* label;     // Input-digest label ("arena" / "region").
  uint32_t guest;        // Data base (LGE arena / LWR region).
  uint32_t size;
  uint32_t stack_top;
  uint8_t* host = nullptr;
};

Region g_lge{Suite::kLge, "lge", "LGE_CASE_V1", "arena", kLgeArena, kLgeArenaSize, kLgeStackTop};
Region g_lwr{Suite::kLwr, "lwr", "LWR_CASE_V1", "region", kLwrVa, kLwrSize, kLwrStackTop};

uint8_t* host(Region& r, uint32_t guest) {
  require(guest >= r.guest && guest < r.guest + r.size, "host() inside the region");
  return r.host + (guest - r.guest);
}
void put_be32(Region& r, uint32_t guest, uint32_t value) { set_be32(host(r, guest), value); }

// ------------------------------------------------------------------ the runtime under test
struct Rt {
  rex::Runtime* runtime = nullptr;
  Memory* memory = nullptr;
  FunctionDispatcher* dispatcher = nullptr;
  ThreadState* thread = nullptr;
  uint8_t* base = nullptr;
  rex::memory::BaseHeap* lge_heap = nullptr;
  rex::memory::BaseHeap* lwr_heap = nullptr;
  unsigned dispatches = 0;
};
Rt g_rt;

// ------------------------------------------------------------------ invalidations (LWR)
struct Invalidations {
  unsigned count = 0;
  uint32_t per_page[kLwrPages] = {};
  bool bad_range = false, inexact_seen = false;
};
Invalidations g_inv;

std::pair<uint32_t, uint32_t> invalidated(void* opaque, uint32_t physical, uint32_t length, bool exact) {
  auto& s = *static_cast<Invalidations*>(opaque);
  ++s.count;
  if (physical < kLwrPhysical || length != kPage || (physical & (kPage - 1)) || physical - kLwrPhysical >= kLwrSize)
    s.bad_range = true;
  else
    ++s.per_page[(physical - kLwrPhysical) / kPage];
  s.inexact_seen = s.inexact_seen || !exact;
  return {physical, length};
}

bool watched_bit(uint32_t n) { return lrb::host_page_watched(g_rt.lwr_heap, P(n)); }
uint8_t* lwr_page(uint32_t n) { return host(g_lwr, P(n)); }

void verify_lwr_plain(const char* what) {
  for (uint32_t n = 0; n < kLwrPages; ++n)
    require(lrb::host_access(lwr_page(n)) == PageAccess::kReadWrite && !watched_bit(n), what);
}

#if LRB_NATIVE
void watch(uint32_t n) {
  g_rt.memory->EnablePhysicalMemoryAccessCallbacks(kLwrPhysical + n * kPage, kPage, true, false);
  require(lrb::host_access(lwr_page(n)) == PageAccess::kReadOnly && watched_bit(n),
          "real SDK watch: runtime alias page read-only and watched");
}
// Ordinary-code drain into the real SDK invalidation path (never the MMIO
// exception callback: it skips an already-writable page).
bool trigger(uint32_t n) {
  return g_rt.memory->TriggerPhysicalMemoryCallbacks(rex::thread::global_critical_region::AcquireDirect(), P(n), 1,
                                                     true, false, true);
}

// ------------------------------------------------------------------ code ranges (LWR admission)
struct CodeRange {
  const char* name;
  uintptr_t begin = 0, end = 0;
};
std::vector<CodeRange> g_ranges = {
    {"__imp__sub_820E7440"}, {"__imp__sub_820EB7D8"}, {"__imp__sub_820E78A0"}, {"__imp__sub_820EB350"},
    {"__imp__sub_820E7328"}, {"__imp__sub_820F7978"}, {"__imp____savegprlr_29"}, {"__imp____restgprlr_29"}};

const CodeRange& code_range(std::string_view name) {
  for (const CodeRange& r : g_ranges)
    if (name == r.name) return r;
  require(false, "known code range");
  return g_ranges[0];
}

// Unchanged LWR method: st_value/st_size of each generated body from the
// executable's own symbol table, relocated by the load bias of sub_820E7440.
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
              code_range("__imp__sub_820F7978").begin == reinterpret_cast<uintptr_t>(&sub_820F7978) &&
              code_range("__imp____savegprlr_29").begin == reinterpret_cast<uintptr_t>(&__savegprlr_29) &&
              code_range("__imp____restgprlr_29").begin == reinterpret_cast<uintptr_t>(&__restgprlr_29),
          "symbol ranges agree with the registered weak-alias entry points");
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

std::string page_list(const std::vector<uint32_t>& pages) {
  std::string s;
  for (uint32_t p : pages) s += (s.empty() ? "" : ",") + std::to_string(p);
  return s.empty() ? "-" : s;
}

// Ordinary-code witness for the traced gate (stderr, exact bytes).
struct Witness {
  char token[33] = {};
  bool valid = false;
  explicit Witness(const char* t) {
    valid = t && std::strlen(t) == 32;
    for (unsigned i = 0; valid && i < 32; ++i) valid = (t[i] >= '0' && t[i] <= '9') || (t[i] >= 'a' && t[i] <= 'f');
    if (valid) std::memcpy(token, t, 33);
  }
};
Witness* g_witness = nullptr;
bool g_emit_claims = false;

void emit(const char* phase, uintptr_t address) {
  if (!g_witness) return;
  std::array<char, 256> line{};
  const int n = std::snprintf(line.data(), line.size(),
                              "LRGD_GATE_V1 token=%s mode=%s phase=%s claims=%u invalidations=%u address=0x%llx\n",
                              g_witness->token, g_mode.c_str(), phase, lwr_claim_count(), g_inv.count,
                              static_cast<unsigned long long>(address));
  if (n > 0 && static_cast<size_t>(n) < line.size()) {
    (void)std::fwrite(line.data(), 1, static_cast<size_t>(n), stderr);
    (void)std::fflush(stderr);
  }
}
#endif

// ------------------------------------------------------------------ the dispatcher invocation
// One FunctionDispatcher::Execute of `guest` with LGE input `in`. The thread
// state's context is loaded with `in` except r1 (+176, the dispatcher's
// padding) and the argument registers (poisoned with ~value, so that only the
// dispatcher's args[] marshalling can produce the callee's arguments).
struct Invocation {
  alignas(64) PPCContext pre;    // ThreadState context immediately before Execute.
  alignas(64) PPCContext entry;  // Callee-observed, at the first prologue hook.
  alignas(64) PPCContext post;   // ThreadState context immediately after Execute.
  alignas(64) PPCContext lge_after;  // T2: post with r1 - 176.
  uint64_t ret = 0;
  unsigned nargs = 0;
};

void invoke(const std::string& id, uint32_t guest, unsigned nargs, const PPCContext& in, Invocation& out) {
  require(nargs >= 1 && nargs <= 8, "register arguments only (no stack-argument path)");
  PPCContext& tc = *g_rt.thread->context();
  std::memcpy(static_cast<void*>(&tc), &in, sizeof(PPCContext));
  tc.r1.u64 = in.r1.u64 + kPad;
  uint64_t args[8] = {};
  for (unsigned i = 0; i < nargs; ++i) {
    args[i] = gpr(in, 3 + int(i)).u64;
    gpr(tc, 3 + int(i)).u64 = ~args[i];
  }
  std::memcpy(static_cast<void*>(&out.pre), &tc, sizeof(PPCContext));
  out.nargs = nargs;
  require(ThreadState::Get() == nullptr, (id + ": no ThreadState bound before Execute").c_str());
  g_trace_count = 0;
  g_trace_overflow = false;
  g_entry_ctx = nullptr;
  g_entry_bound = nullptr;
  g_ctx_mismatch = false;
  g_expected_ctx = &tc;
  out.ret = g_rt.dispatcher->Execute(g_rt.thread, guest, args, nargs);  // The generated code runs here.
  g_expected_ctx = nullptr;
  ++g_rt.dispatches;
  require(ThreadState::Get() == nullptr, (id + ": Execute restored the previous binding").c_str());
  std::memcpy(static_cast<void*>(&out.post), &tc, sizeof(PPCContext));
  require(!g_trace_overflow && g_trace_count > 0, (id + ": the registered function was entered").c_str());
  require(g_entry_ctx == &tc && !g_ctx_mismatch, (id + ": every entry saw the ThreadState context").c_str());
  require(g_entry_bound == g_rt.thread, (id + ": Execute bound the ThreadState for the callee").c_str());
  // T1: the callee saw exactly `in`, except the dispatcher's LR sentinel.
  alignas(64) PPCContext expect_entry;
  std::memcpy(static_cast<void*>(&expect_entry), &in, sizeof(PPCContext));
  expect_entry.lr = kSentinelLr;
  require(bytes_same(g_entry, expect_entry), (id + ": callee entry = LGE input with lr=0xBCBCBCBC (whole context)").c_str());
  std::memcpy(static_cast<void*>(&out.entry), &g_entry, sizeof(PPCContext));
  // T2: Execute restores r1 and the caller's lr; returns r3.
  require(out.post.r1.u64 == out.pre.r1.u64 && out.post.lr == out.pre.lr && out.pre.lr == in.lr,
          (id + ": Execute restored r1 and lr").c_str());
  require(out.ret == out.post.r3.u64, (id + ": Execute returned r3").c_str());
  require(nonint_equal(out.pre, out.post), (id + ": non-integer context state unchanged").c_str());
  std::memcpy(static_cast<void*>(&out.lge_after), &out.post, sizeof(PPCContext));
  out.lge_after.r1.u64 = out.post.r1.u64 - kPad;
}

// ------------------------------------------------------------------ cases
struct Spec {
  std::string id;
  const char* function;
  uint32_t guest;
  unsigned nargs;
  uint64_t seed;
  std::vector<std::string> closure;  // Generated symbols (LWR watched runs).
  std::vector<uint32_t> expect;      // Watched pages the call must claim (LWR).
  bool saves_lr = false;             // T3: __savegprlr_29 stores LR at entry r1 - 8.
};
struct Setup {
  Region& region;
  PPCContext& ctx;
  std::vector<Range> writable;
  std::vector<std::string> trace;
  std::function<bool(const PPCContext& before, const PPCContext& after, const uint8_t* region_before,
                     const uint8_t* region_after)> model;
};

struct Results {
  std::vector<std::string> lge, lwr, lwr_watched, dispatch, restarts, claims;
  unsigned total_claims = 0;
};
Results g_results;
bool g_capture = true;  // Pass 1 records; later passes must reproduce pass 1.
size_t g_replay_lge = 0, g_replay_lwr = 0;

std::string delta_of(const uint8_t* after, const std::vector<uint8_t>& before, uint32_t size, unsigned* changed_out) {
  std::string delta;
  unsigned changed = 0;
  for (uint32_t i = 0; i < size;) {
    if (after[i] == before[i]) {
      ++i;
      continue;
    }
    uint32_t j = i;
    while (j < size && after[j] != before[j]) ++j;
    char head[32];
    std::snprintf(head, sizeof(head), "%s%x:", delta.empty() ? "" : ",", i);
    delta += head;
    delta += hex_bytes(after + i, j - i);
    changed += j - i;
    i = j;
  }
  *changed_out = changed;
  return delta;
}

// One dispatched execution of a case; returns the reconstructed canonical
// (LGE_CASE_V1 / LWR_CASE_V1) line. `watched` is native LWR only.
std::string execute(Region& region, const Spec& spec, const std::function<void(Setup&)>& prepare, bool watched,
                    unsigned pass) {
  SplitMix rng{spec.seed};
  for (uint32_t i = 0; i < region.size; i += 8) {
    const uint64_t v = rng.next();
    std::memcpy(region.host + i, &v, 8);
  }
  alignas(64) PPCContext ctx;
  {
    auto* raw = reinterpret_cast<uint8_t*>(&ctx);
    for (size_t i = 0; i < sizeof(PPCContext); ++i) raw[i] = static_cast<uint8_t>(rng.next());
    for (int i = 0; i < 32; ++i) gpr(ctx, i).u64 = rng.next();
    ctx.r1.u64 = region.stack_top;
    ctx.lr = kReturnLr;
    ctx.ctr.u64 = rng.next();
    ctx.xer.so = uint8_t(rng.next() & 1);
    ctx.xer.ov = uint8_t(rng.next() & 1);
    ctx.xer.ca = uint8_t(rng.next() & 1);
    PPCCRRegister* crs[8] = {&ctx.cr0, &ctx.cr1, &ctx.cr2, &ctx.cr3, &ctx.cr4, &ctx.cr5, &ctx.cr6, &ctx.cr7};
    for (auto* r : crs) r->set_raw(uint32_t(rng.next() & 15));
    ctx.fpscr.csr = 0;
  }
  Setup setup{region, ctx, {}, {}, {}};
  prepare(setup);
  for (const Range& r : setup.writable) {
    if (region.suite == Suite::kLge)
      require(r.begin <= r.end && r.begin >= kLgeArena && r.end <= kLgeGuardHigh &&
                  (r.end <= kLgeDataEnd || r.begin >= kLgeDataEnd),
              "declared range inside the arena, data or stack part");
    else
      require(r.begin <= r.end && r.begin >= kLwrVa && r.end <= kLwrVa + kLwrSize, "declared range in region");
  }
  const std::vector<uint8_t> before(region.host, region.host + region.size);
  std::string input = std::string(region.label) + "=" + std::to_string(region.guest) + ":";
  {
    Sha256 h;
    h.update(before.data(), before.size());
    input += h.hex();
  }
  input += " " + integer_state(ctx);
  const std::string input_digest = sha256(input);
  if (region.suite == Suite::kLwr) verify_lwr_plain("region plain before the case");
#if LRB_NATIVE
  if (watched) {
    for (uint32_t n : kWatched) watch(n);
    require(lwr_open() == 0, "open the LWR session");
    for (uint32_t n : kWatched) require(lwr_register_page(lwr_page(n)) == 0, "register watched page");
    g_inv = Invalidations{};
    authorize(spec.closure);
  }
#else
  require(!watched, "watched runs are native only");
#endif
  const unsigned invalidations_before = g_inv.count;
  Invocation inv;
  invoke(spec.id, spec.guest, spec.nargs, ctx, inv);
  if (spec.saves_lr) {
    // T2b: erase does `mflr r12` and __restgprlr_29 reloads r12 from the save
    // slot (lwz, zero-extended), so r12 carries the LR the callee observed.
    require(inv.lge_after.r12.u64 == kSentinelLr,
            (spec.id + ": r12 holds the callee-observed LR (the dispatcher sentinel)").c_str());
    inv.lge_after.r12.u64 = kReturnLr;
  }
  if (!watched) require(g_inv.count == invalidations_before, "ordinary run: no invalidation");
#if LRB_NATIVE
  if (watched) {
    require(lwr_revoke() == 0, "revoke after the dispatched call");
    std::vector<uint32_t> claimed;
    for (unsigned i = 0; i < lwr_claim_count(); ++i) {
      lwr_claim c{};
      require(lwr_get_claim(i, &c) == 0, "read claim");
      const uintptr_t first = reinterpret_cast<uintptr_t>(region.host);
      require(c.page >= first && c.page < first + kLwrSize && (c.page - first) % kPage == 0, "claim page in region");
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
      require(lwr_page_state(lwr_page(n)) == LWR_PAGE_CLAIMED, "claimed page state");
      char line[320];
      std::snprintf(line, sizeof(line),
                    "LRGD_CLAIM_V1|id=%s|n=%u|page=%u|fn=%s|offset=0x%lx|width=%u|length=%u|address=0x%x|"
                    "effective=0x%x|error=%lu|before=%s",
                    spec.id.c_str(), i, n, fn.c_str(), static_cast<unsigned long>(offset), c.width, c.length,
                    unsigned(c.address - first), at, c.error, hex_bytes(c.before, c.width).c_str());
      if (g_capture) g_results.claims.push_back(line);
      if (g_witness && g_emit_claims) emit("claim", c.address);
    }
    std::vector<uint32_t> sorted = claimed;
    std::sort(sorted.begin(), sorted.end());
    require(sorted == spec.expect, (spec.id + ": claimed exactly the expected watched pages").c_str());
    for (uint32_t n : kWatched) {
      const bool c = std::find(claimed.begin(), claimed.end(), n) != claimed.end();
      require(watched_bit(n), "SDK watch bit still set before the drain");
      require(lrb::host_access(lwr_page(n)) == (c ? PageAccess::kReadWrite : PageAccess::kReadOnly),
              "page protection after restart");
      if (!c) require(lwr_page_state(lwr_page(n)) == LWR_PAGE_ARMED, "unclaimed page still armed");
    }
    require(g_inv.count == 0, "no invalidation before the ordinary-code drain");
    for (uint32_t n : claimed) require(trigger(n), "drain: real SDK invalidation for a claimed page");
    require(!g_inv.bad_range && (claimed.empty() || g_inv.inexact_seen) && g_inv.count == claimed.size(),
            "one invalidation per claim");
    for (uint32_t n : kWatched) {
      const bool c = std::find(claimed.begin(), claimed.end(), n) != claimed.end();
      require(g_inv.per_page[n] == (c ? 1u : 0u), "invalidation only for the claimed page");
      require(watched_bit(n) == !c, "drain unwatches exactly the claimed pages");
    }
    std::vector<uint32_t> cleanup;
    for (uint32_t n : kWatched)
      if (std::find(claimed.begin(), claimed.end(), n) == claimed.end()) {
        require(trigger(n), "cleanup: unwatch an unclaimed page");
        cleanup.push_back(n);
      }
    require(g_inv.count == claimed.size() + cleanup.size(), "cleanup invalidations");
    require(lwr_close() == 0 && lwr_claim_count() == 0, "close the LWR session");
    require(lrb_owns_sigsegv() == 1, "LRB owner still exclusive");
    std::string invalidations;
    for (uint32_t n : sorted)
      invalidations += (invalidations.empty() ? "" : ",") + std::to_string(n) + ":" + std::to_string(g_inv.per_page[n]);
    if (g_capture)
      g_results.restarts.push_back("LRGD_RESTART_V1|id=" + spec.id + "|watched=4,5,9,12|claimed=" + page_list(sorted) +
                                   "|invalidations=" + (invalidations.empty() ? "-" : invalidations) +
                                   "|cleanup=" + page_list(cleanup) + "|restart=complete|session=closed");
    g_results.total_claims += unsigned(claimed.size());
  }
#endif
  if (region.suite == Suite::kLwr) verify_lwr_plain("region plain after the case (protection and watch restored)");

  // Raw memory delta, then T3 on a copy: only the declared LR slot.
  unsigned raw_changed = 0;
  const std::string raw_delta = delta_of(region.host, before, region.size, &raw_changed);
  std::vector<uint8_t> normalized(region.host, region.host + region.size);
  std::string slot = "-";
  if (spec.saves_lr) {
    const uint32_t at = region.stack_top - 8 - region.guest;
    require(get_be32(normalized.data() + at) == uint32_t(kSentinelLr),
            (spec.id + ": the LR save slot holds the dispatcher sentinel the callee observed").c_str());
    set_be32(normalized.data() + at, uint32_t(kReturnLr));
    char buf[16];
    std::snprintf(buf, sizeof(buf), "%x", at);
    slot = buf;
  }
  unsigned changed = 0;
  const std::string delta = delta_of(normalized.data(), before, region.size, &changed);
  if (!spec.saves_lr) require(delta == raw_delta, "no normalization without a declared LR slot");
  for (uint32_t i = 0; i < region.size; ++i) {
    if (normalized[i] == before[i]) continue;
    bool declared = false;
    for (const Range& r : setup.writable) declared = declared || (region.guest + i >= r.begin && region.guest + i < r.end);
    require(declared, (spec.id + ": every changed byte lies in a declared region").c_str());
  }
  std::string trace, expected_trace;
  for (size_t i = 0; i < g_trace_count; ++i) trace += (i ? "," : "") + std::string(g_trace[i]);
  for (size_t i = 0; i < setup.trace.size(); ++i) expected_trace += (i ? "," : "") + std::string("__imp__") + setup.trace[i];
  require(trace == expected_trace, (spec.id + ": entered-function trace").c_str());
  require(setup.model(ctx, inv.lge_after, before.data(), normalized.data()), (spec.id + ": host model").c_str());

  std::string writable;
  for (const Range& r : setup.writable) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%s%08x-%08x", writable.empty() ? "" : ",", r.begin, r.end);
    writable += buf;
  }
  char guest[16];
  std::snprintf(guest, sizeof(guest), "%08x", spec.guest);
  const std::string canonical = std::string(region.prefix) + "|id=" + spec.id + "|fn=" + spec.function +
                                "|guest=" + guest + "|seed=" + std::to_string(spec.seed) + "|input=" + input_digest +
                                "|before=" + integer_state(ctx) + "|after=" + integer_state(inv.lge_after) +
                                "|nonint=unchanged|writable=" + writable + "|changed=" + std::to_string(changed) +
                                "|delta=" + delta + "|trace=" + trace + "|model=pass";
  char ret[24];
  std::snprintf(ret, sizeof(ret), "%016" PRIx64, inv.ret);
  const std::string raw = "LRGD_CASE_V1|suite=" + std::string(region.name) + "|watched=" + (watched ? "1" : "0") +
                          "|pass=" + std::to_string(pass) + "|id=" + spec.id + "|guest=" + guest +
                          "|nargs=" + std::to_string(spec.nargs) + "|ret=" + ret + "|pre=" + integer_state(inv.pre) +
                          "|entry=" + integer_state(inv.entry) + "|post=" + integer_state(inv.post) +
                          "|bound=thread_state|ctx=thread_state|entry_ctx=input+lr_sentinel|lr_slot=" + slot +
                          "|raw_changed=" + std::to_string(raw_changed) + "|raw_delta=" + raw_delta +
                          "|trace=" + trace + "|canonical=" + sha256(canonical);
  if (g_capture) g_results.dispatch.push_back(raw);
  return canonical;
}

void emit_case(Region& region, const Spec& spec, const std::function<void(Setup&)>& prepare, bool native_watched,
               unsigned pass) {
  const std::string ordinary = execute(region, spec, prepare, false, pass);
  std::vector<std::string>& sink = region.suite == Suite::kLge ? g_results.lge : g_results.lwr;
  size_t& replay = region.suite == Suite::kLge ? g_replay_lge : g_replay_lwr;
  if (g_capture) {
    sink.push_back(ordinary);
  } else {
    require(replay < sink.size() && sink[replay] == ordinary, (spec.id + ": repeated dispatch reproduces pass 1").c_str());
    ++replay;
  }
  if (native_watched) {
    const std::string watched = execute(region, spec, prepare, true, pass);
    require(watched == ordinary, (spec.id + ": watched dispatch record equals the ordinary one").c_str());
    if (g_capture) g_results.lwr_watched.push_back(watched);
  }
}

// --- the 124 LGE cases (unchanged order, seeds and inputs).
struct LgeCases {  // Ordinary only: no LGE page is ever watched.
  unsigned pass = 1;
  uint64_t next_seed = 0x4C47450000000001ull;  // "LGE"
  uint64_t seed() { return next_seed++; }
  void run(const Spec& spec, const std::function<void(Setup&)>& prepare) { emit_case(g_lge, spec, prepare, false, pass); }

  void memset_case(const std::string& id, uint32_t dst_off, uint32_t n, uint32_t c) {
    run({id, "sub_820E7440", 0x820E7440u, 3, seed(), {}, {}}, [&](Setup& s) {
      const uint32_t dst = kLgeArena + dst_off;
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = c; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      s.trace = {"sub_820E7440"};
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t*, const uint8_t* after) {
        const uint8_t* p = after + (dst - kLgeArena);
        for (uint32_t i = 0; i < n; ++i)
          if (p[i] != uint8_t(c)) return false;
        return a.r3.u64 == dst;
      };
    });
  }
  void copy_case(const std::string& id, const char* name, uint32_t guest, uint32_t dst_off, uint32_t src_off,
                 uint32_t n, bool via_stack) {
    run({id, name, guest, 3, seed(), {}, {}}, [&](Setup& s) {
      const uint32_t dst = kLgeArena + dst_off, src = kLgeArena + src_off;
      require(dst + n <= src || src + n + 16 <= dst, "copy case regions disjoint");
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = src; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      if (via_stack) s.writable.push_back({kLgeStackTop - 8, kLgeStackTop});
      s.trace = {name};
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t* before, const uint8_t* after) {
        return bytes_equal(after + (dst - kLgeArena), before + (src - kLgeArena), n) && a.r3.u64 == dst &&
               a.r1.u64 == kLgeStackTop;
      };
    });
  }
  void memmove_case(const std::string& id, uint32_t dst_off, uint32_t src_off, uint32_t n) {
    run({id, "sub_820E78A0", 0x820E78A0u, 3, seed(), {}, {}}, [&](Setup& s) {
      const uint32_t dst = kLgeArena + dst_off, src = kLgeArena + src_off;
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = src; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      if (dst == src) {
        s.trace = {"sub_820E78A0"};
      } else if (int32_t(dst) < int32_t(src)) {
        s.trace = {"sub_820E78A0", "sub_820EB350"};
        s.writable.push_back({kLgeStackTop - 8, kLgeStackTop});
      } else {
        s.trace = {"sub_820E78A0"};
      }
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t* before, const uint8_t* after) {
        std::vector<uint8_t> expect(before, before + kLgeArenaSize);
        std::memmove(expect.data() + (dst - kLgeArena), before + (src - kLgeArena), n);
        return bytes_equal(after + (dst - kLgeArena), expect.data() + (dst - kLgeArena), n) &&
               a.r1.u64 == kLgeStackTop;
      };
    });
  }
  void strncpy_case(const std::string& id, uint32_t dst_off, uint32_t src_off, std::string_view text, bool terminate,
                    uint32_t n) {
    run({id, "sub_820E7328", 0x820E7328u, 3, seed(), {}, {}}, [&](Setup& s) {
      const uint32_t dst = kLgeArena + dst_off, src = kLgeArena + src_off;
      uint8_t* p = host(g_lge, src);
      for (size_t i = 0; i < text.size(); ++i) p[i] = uint8_t(text[i] ? text[i] : 'x');
      if (terminate) p[text.size()] = 0;
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = src; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      s.trace = {"sub_820E7328"};
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t* before, const uint8_t* after) {
        const uint8_t* in = before + (src - kLgeArena);
        const uint8_t* out = after + (dst - kLgeArena);
        uint32_t i = 0;
        for (; i < n && in[i]; ++i)
          if (out[i] != in[i]) return false;
        for (; i < n; ++i)
          if (out[i] != 0) return false;
        return a.r3.u64 == dst;
      };
    });
  }
  void strstr_case(const std::string& id, std::string_view hay, std::string_view needle) {
    run({id, "sub_820E6D08", 0x820E6D08u, 2, seed(), {}, {}}, [&](Setup& s) {
      const uint32_t h = kLgeArena + 0x2000u, nd = kLgeArena + 0x3000u;
      std::memcpy(host(g_lge, h), hay.data(), hay.size());
      host(g_lge, h)[hay.size()] = 0;
      std::memcpy(host(g_lge, nd), needle.data(), needle.size());
      host(g_lge, nd)[needle.size()] = 0;
      s.ctx.r3.u64 = h; s.ctx.r4.u64 = nd;
      s.trace = {"sub_820E6D08"};
      const size_t pos = std::string_view(hay).find(needle);
      const uint64_t expect = needle.empty() ? h : (pos == std::string_view::npos ? 0 : h + pos);
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t*, const uint8_t*) { return a.r3.u64 == expect; };
    });
  }
  void format_case(const std::string& id, char object_conv, char conv, uint32_t value, uint32_t flags,
                   uint32_t object_flags, bool value_matches) {
    run({id, "sub_820F0A28", 0x820F0A28u, 4, seed(), {}, {}}, [&](Setup& s) {
      const uint32_t obj = kLgeArena + 0x1000u;
      const uint32_t word = value_matches ? value : value ^ 0x10u;
      put_be32(g_lge, obj, word);
      host(g_lge, obj + 8)[0] = uint8_t(object_conv);
      put_be32(g_lge, obj + 12, object_flags);
      s.ctx.r3.u64 = obj; s.ctx.r4.u64 = value;
      s.ctx.r5.u64 = (s.ctx.r5.u64 & ~0xFFull) | uint8_t(conv);
      s.ctx.r6.u64 = flags;
      s.trace = {"sub_820F0A28"};
      s.model = [](const PPCContext&, const PPCContext& a, const uint8_t*, const uint8_t*) {
        return a.r3.u64 == 0 || a.r3.u64 == 1;
      };
    });
  }
  void erase_case(const std::string& id, uint32_t count, uint32_t index) {
    Spec spec{id, "sub_820F7978", 0x820F7978u, 3, seed(), {}, {}};
    spec.saves_lr = true;
    run(spec, [&](Setup& s) {
      require(index < count, "erase index inside the vector");
      const uint32_t ret = kLgeArena + 0x0080u, vec = kLgeArena + 0x0100u, elems = kLgeArena + 0x4000u;
      put_be32(g_lge, vec, elems);
      put_be32(g_lge, vec + 4, elems + 4 * count);
      const uint32_t pos = elems + 4 * index;
      s.ctx.r3.u64 = ret; s.ctx.r4.u64 = vec; s.ctx.r5.u64 = pos;
      s.writable = {{ret, ret + 4}, {vec + 4, vec + 8}, {pos, elems + 4 * count}, {kLgeStackTop - 128, kLgeStackTop}};
      s.trace = {"sub_820F7978", "__savegprlr_29", "sub_820E78A0", "sub_820EB350", "__restgprlr_29"};
      s.model = [=](const PPCContext& b, const PPCContext& a, const uint8_t* before, const uint8_t* after) {
        const uint8_t* eb = before + (elems - kLgeArena);
        const uint8_t* ea = after + (elems - kLgeArena);
        for (uint32_t i = 0; i + 1 < count; ++i) {
          const uint8_t* expect = eb + 4 * (i < index ? i : i + 1);
          if (!bytes_equal(ea + 4 * i, expect, 4)) return false;
        }
        // a.lr is the dispatcher-restored caller LR (T2), not the callee's.
        return get_be32(after + (vec + 4 - kLgeArena)) == elems + 4 * (count - 1) &&
               get_be32(after + (vec - kLgeArena)) == elems && get_be32(after + (ret - kLgeArena)) == pos &&
               a.r3.u64 == ret && a.r1.u64 == kLgeStackTop && a.lr == kReturnLr && a.r29.u64 == b.r29.u64 &&
               a.r30.u64 == b.r30.u64 && a.r31.u64 == b.r31.u64;
      };
    });
  }

  void all() {
    const uint32_t ms[] = {0, 1, 3, 4, 15, 16, 17, 63, 64, 1000, 4096, 5003};
    for (uint32_t a = 0; a < 4; ++a)
      for (uint32_t i = 0; i < 12; i += 1 + a)
        memset_case("memset/a" + std::to_string(a) + "/n" + std::to_string(ms[i]), 0x0400u + a, ms[i],
                    0x00000A00u | ((a * 37 + i * 11) & 0xFF));
    memset_case("memset/c-upper-bits", 0x0401u, 37, 0x7FFFFF80u);
    const uint32_t cs[] = {0, 1, 2, 5, 8, 31, 100, 1027};
    for (uint32_t d = 0; d < 4; ++d)
      for (uint32_t s = 0; s < 4; ++s) {
        const uint32_t n = cs[(d * 4 + s) % 8];
        copy_case("copy/d" + std::to_string(d) + "s" + std::to_string(s) + "/n" + std::to_string(n), "sub_820EB7D8",
                  0x820EB7D8u, 0x0800u + d, 0x6000u + s, n, false);
      }
    copy_case("copy/page-cross", "sub_820EB7D8", 0x820EB7D8u, 0x0FF3u, 0x7FF9u, 4100, false);
    const uint32_t ls[] = {0, 1, 7, 8, 9, 31, 32, 33, 127, 128, 129, 255, 256, 4096, 8191};
    for (uint32_t i = 0; i < 15; ++i) {
      const uint32_t d = (i * 3) % 8, s = (i * 5) % 8;
      copy_case("memcpy/d" + std::to_string(d) + "s" + std::to_string(s) + "/n" + std::to_string(ls[i]), "sub_820EB350",
                0x820EB350u, 0x0800u + d, 0x6000u + s, ls[i], true);
    }
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
    strncpy_case("strncpy/pad", 0x0800u, 0x3000u, "rayman", true, 32);
    strncpy_case("strncpy/exact", 0x0801u, 0x3000u, "globox!", true, 7);
    strncpy_case("strncpy/truncate", 0x0802u, 0x3000u, "teensies-and-murfy", true, 9);
    strncpy_case("strncpy/no-nul-long", 0x0803u, 0x3000u, std::string(300, 'h'), false, 256);
    strncpy_case("strncpy/n0", 0x0800u, 0x3000u, "abc", true, 0);
    strncpy_case("strncpy/n1", 0x0800u, 0x3000u, "abc", true, 1);
    strncpy_case("strncpy/empty", 0x0800u, 0x3000u, "", true, 12);
    strncpy_case("strncpy/high-bytes", 0x0800u, 0x3000u, "\xC3\xA9t\xE9\xFF", true, 10);
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
    const char conv[] = {'p', 's', 'S', 'd', 'i', 'o', 'u', 'x', 'X', 'c'};
    SplitMix pick{0x464D5400u};
    for (int i = 0; i < 24; ++i) {
      const char oc = conv[pick.below(10)], c = conv[pick.below(10)];
      const uint32_t flags = uint32_t(pick.next()) & 0x00030830u;
      const uint32_t oflags = (i % 3 == 0) ? flags : uint32_t(pick.next()) & 0x00030830u;
      format_case("format/" + std::to_string(i) + "/" + oc + c, oc, c, uint32_t(pick.next()), flags, oflags, i % 2 == 0);
    }
    format_case("format/same-p", 'p', 'p', 0x1234u, 0, 0, true);
    format_case("format/same-s", 's', 's', 0x1234u, 0x800u, 0x800u, true);
    format_case("format/s-vs-S", 's', 'S', 0x1234u, 0x10u, 0x810u, true);
    format_case("format/d-vs-x", 'd', 'x', 0x1u, 0x20000u, 0x20u, false);
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

// --- the 8 LWR cases (unchanged order, seeds and inputs).
constexpr unsigned kExpectedClaims = 9;

struct LwrCases {
  bool native_watched = false;
  unsigned pass = 1;
  uint64_t next_seed = 0x4C57520000000001ull;  // "LWR"
  void run(const Spec& spec, const std::function<void(Setup&)>& prepare) {
    emit_case(g_lwr, spec, prepare, native_watched, pass);
  }
  void memset_case(const std::string& id, uint32_t dst, uint32_t n, uint32_t c, std::vector<uint32_t> expect) {
    run({id, "sub_820E7440", 0x820E7440u, 3, next_seed++, {"__imp__sub_820E7440"}, expect}, [&](Setup& s) {
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = c; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      s.trace = {"sub_820E7440"};
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t*, const uint8_t* after) {
        const uint8_t* p = after + (dst - kLwrVa);
        for (uint32_t i = 0; i < n; ++i)
          if (p[i] != uint8_t(c)) return false;
        return a.r3.u64 == dst;
      };
    });
  }
  void copy_case(const std::string& id, const char* name, uint32_t guest, uint32_t dst, uint32_t src, uint32_t n,
                 bool via_stack, std::vector<uint32_t> expect) {
    run({id, name, guest, 3, next_seed++, {std::string("__imp__") + name}, expect}, [&](Setup& s) {
      require(dst + n <= src || src + n + 16 <= dst, "copy regions disjoint");
      s.ctx.r3.u64 = dst; s.ctx.r4.u64 = src; s.ctx.r5.u64 = n;
      s.writable = {{dst, dst + n}};
      if (via_stack) s.writable.push_back({kLwrStackTop - 8, kLwrStackTop});
      s.trace = {name};
      s.model = [=](const PPCContext&, const PPCContext& a, const uint8_t* b, const uint8_t* after) {
        return bytes_equal(after + (dst - kLwrVa), b + (src - kLwrVa), n) && a.r3.u64 == dst && a.r1.u64 == kLwrStackTop;
      };
    });
  }
  void erase_case(const std::string& id, uint32_t vec, uint32_t elems, uint32_t ret, uint32_t count, uint32_t index,
                  std::vector<uint32_t> expect) {
    Spec spec{id, "sub_820F7978", 0x820F7978u, 3, next_seed++,
              {"__imp__sub_820F7978", "__imp____savegprlr_29", "__imp__sub_820E78A0", "__imp__sub_820EB350",
               "__imp____restgprlr_29"},
              expect};
    spec.saves_lr = true;
    run(spec, [&](Setup& s) {
      put_be32(g_lwr, vec, elems);
      put_be32(g_lwr, vec + 4, elems + 4 * count);
      const uint32_t pos = elems + 4 * index;
      s.ctx.r3.u64 = ret; s.ctx.r4.u64 = vec; s.ctx.r5.u64 = pos;
      s.writable = {{ret, ret + 4}, {vec + 4, vec + 8}, {pos, elems + 4 * count}, {kLwrStackTop - 128, kLwrStackTop}};
      s.trace = {"sub_820F7978", "__savegprlr_29", "sub_820E78A0", "sub_820EB350", "__restgprlr_29"};
      s.model = [=](const PPCContext& b, const PPCContext& a, const uint8_t* before, const uint8_t* after) {
        const uint8_t* eb = before + (elems - kLwrVa);
        const uint8_t* ea = after + (elems - kLwrVa);
        for (uint32_t i = 0; i + 1 < count; ++i)
          if (!bytes_equal(ea + 4 * i, eb + 4 * (i < index ? i : i + 1), 4)) return false;
        return get_be32(after + (vec + 4 - kLwrVa)) == elems + 4 * (count - 1) &&
               get_be32(after + (vec - kLwrVa)) == elems && get_be32(after + (ret - kLwrVa)) == pos &&
               a.r3.u64 == ret && a.r1.u64 == kLwrStackTop && a.lr == kReturnLr && a.r29.u64 == b.r29.u64 &&
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
    copy_case("restart/memcpy", "sub_820EB350", 0x820EB350u, P(12) + 0x18u, P(1) + 0x5u, 1000, true, {12});
    copy_case("restart/forward-copy", "sub_820EB7D8", 0x820EB7D8u, P(9) + 0xC01u, P(2) + 0x3u, 0x700u, false, {9});
    erase_case("restart/erase", P(5) + 0x100u, P(12) + 0x200u, P(14) + 0x40u, 64, 5, {5, 12});
  }
};

// ------------------------------------------------------------------ registration and dispatcher negatives
std::string hex8(uint32_t v) {
  char buf[16];
  std::snprintf(buf, sizeof(buf), "%08x", v);
  return buf;
}

void verify_registration(unsigned cycle) {
  require(g_rt.dispatcher->HasAnyFunctionTable() && g_rt.memory->HasAnyFunctionTable(),
          "dispatcher and Memory hold the function table");
  require(g_rt.dispatcher->FindCallerModuleBase(kMappings[0].guest) == kCodeBase &&
              g_rt.dispatcher->FindCallerModuleBase(kCodeBase + kCodeSize + kThunkReserve - 4) == kCodeBase &&
              g_rt.dispatcher->FindCallerModuleBase(kCodeBase + kCodeSize + kThunkReserve) == 0 &&
              g_rt.dispatcher->FindCallerModuleBase(kOutOfRange) == 0,
          "module range is [code_base, code_base + code_size + thunk reserve)");
  auto* table = g_rt.memory->LookupHeap(kTableBase);
  require(table != nullptr && table == g_rt.memory->LookupHeap(kImageBase), "function table lives in the image heap");
  require(g_rt.memory->TranslateVirtual(kTableBase) == g_rt.base + kTableBase,
          "table translation is base + guest (the generated REX_LOOKUP_FUNC formula)");
  for (const Mapping& m : kMappings) {
    const bool dispatcher = g_rt.dispatcher->GetFunction(m.guest) == m.host;
    // Exactly the generated prelude's lookup: base + IMAGE_BASE + IMAGE_SIZE + (guest - CODE_BASE) * 2.
    PPCFunc* slot = nullptr;
    std::memcpy(&slot, g_rt.base + uint64_t(kImageBase) + kImageSize + uint64_t(m.guest - kCodeBase) * 2, sizeof(slot));
    const bool in_table = slot == m.host;
    const bool indirect = rex::runtime::ResolveIndirectFunction(m.guest) == m.host;
    require(dispatcher && in_table && indirect, "registered: dispatcher lookup, guest table slot and indirect resolve");
    record("LRGD_REG_V1|mode=" + g_mode + "|cycle=" + std::to_string(cycle) + "|guest=" + hex8(m.guest) +
           "|symbol=" + m.symbol + "|dispatcher=1|table_slot=1|indirect=1");
  }
  // Only the ten rows: neighbouring slots and an in-range address are empty.
  require(g_rt.dispatcher->GetFunction(kUnregistered) == nullptr && g_rt.dispatcher->GetFunction(kOutOfRange) == nullptr,
          "unregistered addresses have no host function");
  unsigned empty_slots = 0, populated = 0;
  for (uint32_t g = 0x820E6000u; g < 0x820F8000u; g += 4) {
    PPCFunc* slot = nullptr;
    std::memcpy(&slot, g_rt.base + uint64_t(kImageBase) + kImageSize + uint64_t(g - kCodeBase) * 2, sizeof(slot));
    if (slot) ++populated; else ++empty_slots;
  }
  require(populated == kMappingCount, "the guest table window holds exactly the ten registered rows");
  record("LRGD_IMAGE_V1|mode=" + g_mode + "|cycle=" + std::to_string(cycle) + "|code_base=" + hex8(kCodeBase) +
         "|code_size=" + hex8(kCodeSize) + "|image_base=" + hex8(kImageBase) + "|image_size=" + hex8(kImageSize) +
         "|table_base=" + hex8(kTableBase) + "|table_size=" + hex8(kTableSize) + "|thunk_reserve=" + hex8(kThunkReserve) +
         "|mappings=" + std::to_string(kMappingCount) + "|window_populated=" + std::to_string(populated) +
         "|window_empty=" + std::to_string(empty_slots) + "|codegen_flags=00000000|rexcrt_heap=0|register_modules=0");
}

// Execute on an in-range but unregistered address: the real "not in function
// table" path returns 0xDEADBABE, enters nothing, rebinds nothing and writes
// no guest memory. SetFunction outside every module range is refused.
void dispatcher_negatives(unsigned cycle) {
  PPCContext& tc = *g_rt.thread->context();
  SplitMix rng{0x4C52474400000001ull};
  auto* raw = reinterpret_cast<uint8_t*>(&tc);
  for (size_t i = 0; i < sizeof(PPCContext); ++i) raw[i] = static_cast<uint8_t>(rng.next());
  tc.r1.u64 = kLgeStackTop + kPad;
  tc.lr = kReturnLr;
  alignas(64) PPCContext before;
  std::memcpy(static_cast<void*>(&before), &tc, sizeof(PPCContext));
  const std::vector<uint8_t> arena(g_lge.host, g_lge.host + kLgeArenaSize);
  uint64_t args[3] = {kLgeArena, 0x5A, 64};
  g_trace_count = 0;
  const uint64_t ret = g_rt.dispatcher->Execute(g_rt.thread, kUnregistered, args, 3);
  ++g_rt.dispatches;
  require(ret == kNotFound && g_trace_count == 0 && ThreadState::Get() == nullptr,
          "unregistered Execute: 0xDEADBABE, nothing entered, binding unchanged");
  before.r3.u64 = args[0]; before.r4.u64 = args[1]; before.r5.u64 = args[2];
  require(bytes_same(before, tc), "unregistered Execute changed only the marshalled argument registers");
  require(std::memcmp(arena.data(), g_lge.host, kLgeArenaSize) == 0, "unregistered Execute wrote no guest memory");
  require(!g_rt.dispatcher->SetFunction(kOutOfRange, sub_820E7440) && g_rt.dispatcher->GetFunction(kOutOfRange) == nullptr,
          "SetFunction outside every module range is refused");
  record("LRGD_NEGATIVE_V1|mode=" + g_mode + "|cycle=" + std::to_string(cycle) + "|unregistered=" + hex8(kUnregistered) +
         "|ret=" + hex(ret) + "|entered=0|bound=unchanged|context=args-only|memory=unchanged|out_of_range_set=refused");
}

// ------------------------------------------------------------------ regions in runtime Memory
void allocate_regions() {
  Memory& m = *g_rt.memory;
  g_rt.lge_heap = m.LookupHeap(kLgeRegion);
  require(g_rt.lge_heap != nullptr && g_rt.lge_heap == m.LookupHeapByType(false, 4096),
          "LGE arena heap is the runtime's 4 KiB virtual heap");
  require(g_rt.lge_heap->AllocFixed(kLgeRegion, kLgeRegionSize, kPage,
                                    rex::memory::kMemoryAllocationReserve | rex::memory::kMemoryAllocationCommit,
                                    rex::memory::kMemoryProtectRead | rex::memory::kMemoryProtectWrite),
          "real fixed LGE arena allocation in runtime-owned Memory");
  require(g_rt.lge_heap->Protect(kLgeRegion, kPage, rex::memory::kMemoryProtectNoAccess) &&
              g_rt.lge_heap->Protect(kLgeGuardHigh, kPage, rex::memory::kMemoryProtectNoAccess),
          "LGE guard pages no-access");
  require(m.TranslateVirtual(kLgeArena) == g_rt.base + kLgeArena, "arena translation is base + guest");
  g_lge.host = m.TranslateVirtual(kLgeArena);
  g_rt.lwr_heap = m.LookupHeap(kLwrVa);
  require(g_rt.lwr_heap && g_rt.lwr_heap->heap_type() == rex::memory::HeapType::kGuestPhysical,
          "LWR region heap is the runtime's vA physical alias heap");
  require(g_rt.lwr_heap->AllocFixed(kLwrVa, kLwrSize, kLwrSize,
                                    rex::memory::kMemoryAllocationReserve | rex::memory::kMemoryAllocationCommit,
                                    rex::memory::kMemoryProtectRead | rex::memory::kMemoryProtectWrite),
          "real fixed vA physical allocation in runtime-owned Memory");
  require(m.GetPhysicalAddress(kLwrVa) == kLwrPhysical, "LWR region physical address");
  require(m.TranslateVirtual(kLwrVa) == g_rt.base + kLwrVa, "region translation is base + guest");
  g_lwr.host = m.TranslateVirtual(kLwrVa);
  verify_lwr_plain("LWR region plain after allocation");
}

void verify_lge_protection() {
  require(lrb::host_access(g_rt.memory->TranslateVirtual(kLgeRegion)) == PageAccess::kNoAccess &&
              lrb::host_access(g_rt.memory->TranslateVirtual(kLgeGuardHigh)) == PageAccess::kNoAccess,
          "LGE guards are host no-access");
  for (uint32_t p = kLgeArena; p < kLgeGuardHigh; p += kPage)
    require(lrb::host_access(g_rt.memory->TranslateVirtual(p)) == PageAccess::kReadWrite, "LGE arena pages read-write");
}

void release_regions() {
  uint32_t released = 0;
  require(g_rt.lwr_heap->Release(kLwrVa, &released) && released == kLwrSize, "LWR region released exactly");
  released = 0;
  require(g_rt.lge_heap->Release(kLgeRegion, &released) && released == kLgeRegionSize, "LGE arena released exactly");
}

#if LRB_NATIVE
// ------------------------------------------------------------------ signal snapshots (LRSO method)
constexpr uint64_t kGuestSpan = lrb::kGuestSpan;
constexpr uint64_t kBase = lrb::kPreferredBase;
constexpr unsigned long kLibcSaRestorer = 0x04000000ul;
constexpr const char* kLatchSymbol = "_ZN3rex8platform17g_seh_initializedE";

struct Action {
  bool valid = false;
  uintptr_t handler = 0;
  bool siginfo = false;
  unsigned long flags = 0;
  uint64_t mask = 0;
};
using Snapshot = std::array<Action, 65>;

bool skipped(int sig) { return sig == SIGKILL || sig == SIGSTOP; }

Snapshot snapshot() {
  static_assert(NSIG == 65, "glibc x86-64 signal numbering");
  Snapshot s{};
  for (int sig = 1; sig < NSIG; ++sig) {
    if (skipped(sig)) continue;
    struct sigaction a{};
    Action& out = s[sig];
    if (sigaction(sig, nullptr, &a) != 0) {
      require(errno == EINVAL, "signal query fails only for glibc-reserved signals");
      continue;
    }
    out.valid = true;
    out.siginfo = (a.sa_flags & SA_SIGINFO) != 0;
    out.handler = out.siginfo ? reinterpret_cast<uintptr_t>(a.sa_sigaction) : reinterpret_cast<uintptr_t>(a.sa_handler);
    out.flags = static_cast<unsigned long>(a.sa_flags) & ~kLibcSaRestorer;
    for (int m = 1; m < NSIG; ++m)
      if (!skipped(m) && sigismember(&a.sa_mask, m) == 1) out.mask |= 1ull << (m - 1);
  }
  return s;
}

bool same(const Action& a, const Action& b) {
  return a.valid == b.valid && a.handler == b.handler && a.siginfo == b.siginfo && a.flags == b.flags && a.mask == b.mask;
}
std::vector<int> changed(const Snapshot& a, const Snapshot& b) {
  std::vector<int> out;
  for (int sig = 1; sig < NSIG; ++sig)
    if (!skipped(sig) && !same(a[sig], b[sig])) out.push_back(sig);
  return out;
}
bool is_default(const Action& a) { return a.valid && !a.siginfo && a.handler == reinterpret_cast<uintptr_t>(SIG_DFL); }

struct Where {
  std::string object = "-";
  uintptr_t offset = 0;
};
Where where(uintptr_t handler) {
  Where w;
  if (handler == reinterpret_cast<uintptr_t>(SIG_DFL) || handler == reinterpret_cast<uintptr_t>(SIG_IGN)) return w;
  Dl_info info{};
  if (dladdr(reinterpret_cast<void*>(handler), &info) && info.dli_fname) {
    std::string name = info.dli_fname;
    const size_t slash = name.rfind('/');
    w.object = slash == std::string::npos ? name : name.substr(slash + 1);
    if (w.object.empty()) w.object = "main";
    w.offset = handler - reinterpret_cast<uintptr_t>(info.dli_fbase);
  } else {
    w.object = "?";
  }
  return w;
}
bool in_sdk_runtime(uintptr_t handler) { return where(handler).object.rfind("librexruntime.so", 0) == 0; }

void record_snapshot(unsigned cycle, const char* stage, const Snapshot& s) {
  for (int sig = 1; sig < NSIG; ++sig) {
    if (skipped(sig)) continue;
    const Action& a = s[sig];
    const char* state = !a.valid ? "invalid"
                        : (!a.siginfo && a.handler == reinterpret_cast<uintptr_t>(SIG_DFL)) ? "dfl"
                        : (!a.siginfo && a.handler == reinterpret_cast<uintptr_t>(SIG_IGN)) ? "ign"
                                                                                           : "fn";
    const Where w = (a.valid && std::strcmp(state, "fn") == 0) ? where(a.handler) : Where{};
    char buf[96];
    std::snprintf(buf, sizeof(buf), "0x%016" PRIx64, a.mask);
    record("LRGD_SIG_V1|mode=" + g_mode + "|cycle=" + std::to_string(cycle) + "|stage=" + stage +
           "|sig=" + std::to_string(sig) + "|state=" + state + "|siginfo=" + (a.siginfo ? "1" : "0") +
           "|flags=" + hex(a.flags) + "|mask=" + buf + "|object=" + w.object + "|offset=" + hex(w.offset));
  }
}

std::vector<long> g_baseline;
long g_main = 0;
void check_threads(unsigned cycle, const char* stage) {
  const std::vector<long> now = lrb::process_tasks();
  const char* violation = lrb::thread_set_violation(g_baseline, now, g_main, lrb::kSdkPreMainThreads);
  record("LRGD_THREADS_V1|mode=" + g_mode + "|cycle=" + std::to_string(cycle) + "|stage=" + stage +
         "|count=" + std::to_string(now.size()) + "|baseline=" + std::to_string(g_baseline.size()) +
         "|equal=" + (violation ? "0" : "1"));
  if (violation) require(false, (std::string(violation) + " at " + stage).c_str());
  require(static_cast<long>(gettid()) == g_main, "LRGD runs on the main thread");
}

std::atomic<bool>* g_latch = nullptr;
void locate_latch() {
  static_assert(std::atomic<bool>::is_always_lock_free && sizeof(std::atomic<bool>) == 1, "lock-free one-byte latch");
  void* symbol = dlsym(RTLD_DEFAULT, kLatchSymbol);
  require(symbol != nullptr, "SDK latch symbol resolvable in the global scope");
  Dl_info info{};
  require(dladdr(symbol, &info) && info.dli_fname &&
              std::string_view(info.dli_fname).find("librexruntime.so") != std::string_view::npos,
          "the resolved latch is the SDK library's own definition");
  g_latch = static_cast<std::atomic<bool>*>(symbol);
}
void record_latch(const char* stage) {
  record("LRGD_LATCH_V1|mode=" + g_mode + "|stage=" + stage + "|value=" + (g_latch->load() ? "1" : "0") +
         "|object=" + where(reinterpret_cast<uintptr_t>(g_latch)).object);
}

// ------------------------------------------------------------------ maps / shm (LRSO method)
struct MapEntry {
  uint64_t start = 0, end = 0, inode = 0;
  unsigned major = 0, minor = 0;
  char perms[5] = {};
};
std::vector<MapEntry> read_maps() {
  std::vector<MapEntry> entries;
  std::ifstream maps("/proc/self/maps");
  require(maps.is_open(), "open /proc/self/maps");
  std::string line;
  while (std::getline(maps, line)) {
    MapEntry e;
    unsigned long long start = 0, end = 0, offset = 0, inode = 0;
    if (std::sscanf(line.c_str(), "%llx-%llx %4s %llx %x:%x %llu", &start, &end, e.perms, &offset, &e.major, &e.minor,
                    &inode) < 7)
      continue;
    e.start = start;
    e.end = end;
    e.inode = inode;
    entries.push_back(e);
  }
  require(!entries.empty(), "parse /proc/self/maps");
  return entries;
}
bool range_unmapped(uint64_t begin, uint64_t end) {
  for (const auto& e : read_maps())
    if (e.start < end && e.end > begin) return false;
  return true;
}
struct Shm {
  std::string name;
  uint64_t device = 0, inode = 0, apparent = 0, allocated = 0;
  bool unlinked_early = false;
};
Shm identify(Memory& m) {
  Shm shm;
  const std::string name = m.file_name().string();
  require(!name.empty() && name.find('/') == std::string::npos && name.rfind("xenia_memory_", 0) == 0 &&
              name.size() > 13 && name.find_first_not_of("0123456789", 13) == std::string::npos,
          "runtime shm name is xenia_memory_<ticks>");
  shm.name = "/" + name;
  struct stat st{};
  require(stat(("/dev/shm" + shm.name).c_str(), &st) == 0 && S_ISREG(st.st_mode), "runtime shm object exists");
  require(st.st_uid == geteuid(), "runtime shm object owned by this user");
  shm.device = st.st_dev;
  shm.inode = st.st_ino;
  shm.apparent = uint64_t(st.st_size);
  shm.allocated = uint64_t(st.st_blocks) * 512u;
  return shm;
}
void verify_views(const Shm& shm) {
  uint64_t cursor = kBase;
  const uint64_t end = kBase + kGuestSpan;
  for (const auto& e : read_maps()) {
    if (e.end <= cursor || e.start >= end) continue;
    require(e.start <= cursor, "runtime views have no gap");
    require(e.perms[3] == 's' && e.inode == shm.inode && e.major == major(shm.device) && e.minor == minor(shm.device),
            "runtime view is a shared mapping of the identified shm inode");
    cursor = e.end < end ? e.end : end;
  }
  require(cursor == end, "runtime views cover the whole guest span");
  // LRSO bound (64 MiB) plus exactly the function table that
  // Setup(PPCImageInfo) commits by zeroing it (Memory::InitializeFunctionTable).
  require(shm.apparent == 0x120001000ull && shm.allocated < (64ull << 20) + kTableSize, "sparse runtime shm size");
}
void unlink_owned(Shm& shm) {
  const std::string path = "/dev/shm" + shm.name;
  struct stat st{};
  require(stat(path.c_str(), &st) == 0 && st.st_ino == shm.inode && st.st_dev == shm.device,
          "owned shm identity unchanged before early unlink");
  require(unlink(path.c_str()) == 0, "early unlink of the owned shm name");
  errno = 0;
  require(stat(path.c_str(), &st) != 0 && errno == ENOENT, "owned shm name gone");
  shm.unlinked_early = true;
}
void write_ownership(const Shm& shm, const char* stage, bool fatal, const lrb::ProcessMemory& before,
                     const lrb::ProcessMemory& after) {
  const char* path = std::getenv("LRB_OWNERSHIP_FILE");
  if (!path || !*path) return;
  const std::string temporary = std::string(path) + ".tmp";
  std::FILE* file = std::fopen(temporary.c_str(), "w");
  require(file != nullptr, "open ownership record");
  std::fprintf(file,
               "{\"format\":\"LRB_OWNERSHIP_V1\",\"stage\":\"%s\",\"mode\":\"%s\",\"policy\":\"%s\",\"pid\":%lld,"
               "\"shm_name\":\"%s\",\"device\":%" PRIu64 ",\"inode\":%" PRIu64 ",\"apparent_size\":%" PRIu64
               ",\"allocated_bytes\":%" PRIu64 ",\"unlinked_early\":%s,\"virtual_membase\":%" PRIu64
               ",\"vm_size_kib_before\":%" PRIu64 ",\"vm_size_kib_after\":%" PRIu64
               ",\"vm_rss_kib_before\":%" PRIu64 ",\"vm_rss_kib_after\":%" PRIu64 "}\n",
               stage, g_mode.c_str(), fatal ? "unlink-after-map" : "sdk-contract", static_cast<long long>(getpid()),
               shm.name.c_str(), shm.device, shm.inode, shm.apparent, shm.allocated,
               shm.unlinked_early ? "true" : "false", kBase, before.vm_size_kib, after.vm_size_kib, before.vm_rss_kib,
               after.vm_rss_kib);
  require(std::fflush(file) == 0 && std::fclose(file) == 0, "write ownership record");
  require(std::rename(temporary.c_str(), path) == 0, "publish ownership record atomically");
}
#endif

// ------------------------------------------------------------------ runtime lifecycle
struct Cycle {
  unsigned index = 0;
  bool latch = false, fatal = false;
  rex::Runtime* runtime = nullptr;
  rex::runtime::MMIOHandler* mmio = nullptr;
#if LRB_NATIVE
  Shm shm;
#endif
};

void setup(Cycle& c) {
  require(rex::Runtime::instance() == nullptr && rex::system::KernelState::shared() == nullptr,
          "no runtime or kernel singleton before Setup");
  require(rex::runtime::MMIOHandler::global_handler() == nullptr, "no SDK MMIOHandler before Setup");
  require(ThreadState::Get() == nullptr, "no ThreadState bound before Setup");
#if LRB_NATIVE
  require(range_unmapped(kBase, kBase + kGuestSpan), "guest view range unmapped before Runtime::Setup");
  require(rex::memory::page_size() == kPage, "4 KiB host pages (tested configuration)");
  const auto before = lrb::process_memory();
#endif
  rex::RuntimeConfig config;
  config.tool_mode = true;
  const rex::PPCImageInfo info = image_info();
  const X_STATUS status = c.runtime->Setup(info, std::move(config));  // The real Setup(PPCImageInfo).
  require(status == X_STATUS_SUCCESS, "real Runtime::Setup(PPCImageInfo) (tool mode) succeeded");
  g_rt.runtime = c.runtime;
  g_rt.memory = c.runtime->memory();
  g_rt.dispatcher = c.runtime->function_dispatcher();
  c.mmio = rex::runtime::MMIOHandler::global_handler();
  require(g_rt.memory != nullptr && g_rt.dispatcher != nullptr && c.mmio != nullptr,
          "runtime owns Memory, the FunctionDispatcher and the SDK MMIOHandler");
  require(rex::Runtime::instance() == c.runtime && c.runtime->is_tool_mode(), "runtime singleton in tool mode");
  require(rex::system::KernelState::shared() == c.runtime->kernel_state() && c.runtime->kernel_state() != nullptr,
          "kernel state singleton owned by the runtime");
  require(c.runtime->graphics_system() == nullptr && c.runtime->audio_system() == nullptr &&
              c.runtime->input_system() == nullptr,
          "no graphics, audio or input system");
  const auto& flags = c.runtime->codegen_flags();
  require(!flags.skip_lr && !flags.ctr_as_local && !flags.xer_as_local && !flags.reserved_as_local && !flags.skip_msr &&
              !flags.cr_as_local && !flags.non_argument_as_local && !flags.non_volatile_as_local,
          "runtime stored the production codegen flags (all false)");
  g_rt.base = g_rt.memory->virtual_membase();
  require((reinterpret_cast<uintptr_t>(g_rt.base) & 0x1F) == 0, "generated-code base is 32-byte aligned");
#if LRB_NATIVE
  const auto after = lrb::process_memory();
  check_threads(c.index, "after-setup");
  require(reinterpret_cast<uintptr_t>(g_rt.base) == kBase &&
              g_rt.memory->physical_membase() == g_rt.base + lrb::kPhysicalOffset,
          "runtime views at 2^32, physical at +4 GiB");
  c.shm = identify(*g_rt.memory);
  write_ownership(c.shm, "initialized", c.fatal, before, after);
  verify_views(c.shm);
  if (c.fatal) unlink_owned(c.shm);
  write_ownership(c.shm, "started", c.fatal, before, after);
  record("LRGD_RUNTIME_V1|mode=" + g_mode + "|cycle=" + std::to_string(c.index) + "|setup_status=" + hex(status) +
         "|instance=1|kernel_shared=1|mmio=1|dispatcher=1|membase=" + hex(kBase) + "|tool_mode=1|shm=" + c.shm.name +
         "|inode=" + std::to_string(c.shm.inode) + "|device=" + std::to_string(c.shm.device) +
         "|allocated=" + std::to_string(c.shm.allocated));
#else
  record("LRGD_RUNTIME_V1|mode=" + g_mode + "|cycle=" + std::to_string(c.index) + "|setup_status=" + hex(status) +
         "|instance=1|kernel_shared=1|mmio=1|dispatcher=1|tool_mode=1");
#endif
  verify_registration(c.index);
}

void make_thread_state(unsigned cycle) {
  // Constructed directly with the runtime's Memory: no XThread, no new host
  // thread, no kernel object. Its PPCContext is the one Execute uses.
  g_rt.thread = new ThreadState(kThreadId, kLgeStackTop + uint32_t(kPad), 0, g_rt.memory);
  require(g_rt.thread->thread_id() == kThreadId && g_rt.thread->memory() == g_rt.memory &&
              (reinterpret_cast<uintptr_t>(g_rt.thread->context()) & 63) == 0,
          "ThreadState: explicit id, runtime Memory, 64-byte aligned context");
  require(ThreadState::Get() == nullptr, "constructing a ThreadState binds nothing");
  record("LRGD_THREAD_STATE_V1|mode=" + g_mode + "|cycle=" + std::to_string(cycle) + "|thread_id=" + hex(kThreadId) +
         "|xthread=0|host_thread=main|bound_before=0");
}

void drop_thread_state() {
  delete g_rt.thread;
  g_rt.thread = nullptr;
  require(ThreadState::Get() == nullptr, "no ThreadState bound after release");
}

#if LRB_NATIVE
Action check_after_setup(const Cycle& c, const Snapshot& entry, const Snapshot& now) {
  const Action& segv = now[SIGSEGV];
  const Action& ill = now[SIGILL];
  require(segv.valid && segv.siginfo && in_sdk_runtime(segv.handler) && segv.flags == static_cast<unsigned long>(SA_SIGINFO) &&
              segv.mask == 0,
          "SIGSEGV is the SDK MMIO thunk (SA_SIGINFO, empty mask)");
  require(same(segv, ill), "SIGILL is the same SDK MMIO thunk");
  std::vector<int> expect = {SIGILL, SIGSEGV};
  Action seh{};
  if (c.latch) {
    require(is_default(now[SIGBUS]) && is_default(now[SIGFPE]), "latch: SIGBUS/SIGFPE untouched");
  } else {
    seh = now[SIGFPE];
    require(seh.valid && seh.siginfo && in_sdk_runtime(seh.handler) &&
                seh.flags == static_cast<unsigned long>(SA_SIGINFO | SA_NODEFER) && seh.mask == 0,
            "default: SIGFPE is the SDK SEH handler");
    require(same(now[SIGBUS], seh), "default: SIGBUS is the same SDK SEH handler");
    expect = {SIGILL, SIGBUS, SIGFPE, SIGSEGV};
  }
  std::sort(expect.begin(), expect.end());
  require(changed(entry, now) == expect, "Setup changed exactly the expected signal dispositions");
  return seh;
}

void handoff(Cycle& c, const Snapshot& entry) {
  rex::arch::ExceptionHandler::Uninstall(lrb::SdkAccess::exception_thunk(), c.mmio);
  require(rex::runtime::MMIOHandler::global_handler() == c.mmio, "MMIOHandler singleton survives the handoff");
  Snapshot now = snapshot();
  record_snapshot(c.index, "after-thunk-removal", now);
  require(changed(entry, now).empty(), "thunk removal restores SIG_DFL beneath");
  require(lrb_install() == 0, "install the exclusive LRB SIGSEGV owner");
  require(lrb_owns_sigsegv() == 1, "LRB owner is the only live SIGSEGV action");
  now = snapshot();
  record_snapshot(c.index, "after-owner", now);
  require(changed(entry, now) == std::vector<int>{SIGSEGV}, "the owner changed SIGSEGV only");
  require(lrb_attach() == 0, "attach guarded alternate signal stack");
  check_threads(c.index, "after-owner");
  record("LRGD_HANDOFF_V1|mode=" + g_mode + "|cycle=" + std::to_string(c.index) + "|result=installed|segv_beneath=sig_dfl");
}

void release_owner(Cycle& c, const Snapshot& entry) {
  require(lrb_detach() == 0, "detach after dispatch");
  require(lrb_uninstall() == 0 && lrb_installed() == 0, "remove the LRB owner before Shutdown");
  const Snapshot now = snapshot();
  record_snapshot(c.index, "after-owner-removal", now);
  require(changed(entry, now).empty(), "owner removal restores every entry disposition");
}
#endif

void teardown(Cycle& c
#if LRB_NATIVE
              , const Snapshot& expect_final
#endif
) {
  c.runtime->Shutdown();
  require(rex::Runtime::instance() == nullptr && rex::system::KernelState::shared() == nullptr &&
              c.runtime->memory() == nullptr && c.runtime->function_dispatcher() == nullptr,
          "Shutdown releases the runtime, kernel state, dispatcher and Memory");
  require(rex::runtime::MMIOHandler::global_handler() == nullptr, "SDK MMIOHandler removed with Memory");
  require(rex::runtime::ResolveIndirectFunction(kMappings[0].guest) != kMappings[0].host,
          "no dispatcher lookup survives Shutdown");
  require(ThreadState::Get() == nullptr, "no ThreadState bound after Shutdown");
#if LRB_NATIVE
  require(range_unmapped(kBase, kBase + kGuestSpan), "no runtime view remains mapped after Shutdown");
  stack_t stack{};
  require(sigaltstack(nullptr, &stack) == 0 && (stack.ss_flags & SS_DISABLE), "alternate stack removed");
  struct stat st{};
  errno = 0;
  require(stat(("/dev/shm" + c.shm.name).c_str(), &st) != 0 && errno == ENOENT, "no runtime /dev/shm residue");
  const Snapshot now = snapshot();
  record_snapshot(c.index, "after-shutdown", now);
  require(changed(expect_final, now).empty(), "dispositions after Shutdown are exactly the expected ones");
  check_threads(c.index, "after-shutdown");
#endif
  g_rt = Rt{};
  record("LRGD_TEARDOWN_V1|mode=" + g_mode + "|cycle=" + std::to_string(c.index) +
         "|instance=0|kernel_shared=0|mmio=0|dispatcher=0|views_unmapped=" + (LRB_NATIVE ? "1" : "-") +
         "|shm_removed=" + (LRB_NATIVE ? "1" : "-"));
}

// The dispatch matrix of one cycle. Pass 1 of cycle 1 records; every later
// pass (and cycle) must reproduce it exactly.
void dispatch_matrix(unsigned cycle, bool native_watched) {
  constexpr unsigned kPasses = 2;
  for (unsigned pass = 1; pass <= kPasses; ++pass) {
    g_capture = cycle == 1 && pass == 1;
    g_replay_lge = g_replay_lwr = 0;
    LgeCases lge;
    lge.pass = pass;
    lge.all();
    LwrCases lwr;
    lwr.pass = pass;
    lwr.native_watched = native_watched;
    lwr.all();
    require(g_results.lge.size() == 124 && g_results.lwr.size() == 8, "124 LGE and 8 LWR cases");
    if (!g_capture) require(g_replay_lge == 124 && g_replay_lwr == 8, "every case reproduced");
    record("LRGD_PASS_V1|mode=" + g_mode + "|cycle=" + std::to_string(cycle) + "|pass=" + std::to_string(pass) +
           "|lge=124|lwr=8|watched=" + (native_watched ? "8" : "0") + "|reproduced=" + (g_capture ? "-" : "1"));
  }
  g_capture = false;
}

#if LRB_NATIVE
// ------------------------------------------------------------------ fatal modes (latch, traced)
constexpr std::array<std::string_view, 4> kFatal = {"lrgd-write-guard", "lrgd-unregistered-page", "lrgd-unauthorized",
                                                     "lrgd-wrong-function"};

// One unsupported fault by REAL generated code entered through Execute. Nothing
// admits it: the LRB owner must terminate in signal context.
[[noreturn]] void run_fatal(std::string_view mode) {
  alignas(64) PPCContext ctx;
  SplitMix rng{0x4C52474600000001ull};
  auto* raw = reinterpret_cast<uint8_t*>(&ctx);
  for (size_t i = 0; i < sizeof(PPCContext); ++i) raw[i] = static_cast<uint8_t>(rng.next());
  ctx.lr = kReturnLr;
  Invocation inv;
  if (mode == "lrgd-write-guard") {
    ctx.r1.u64 = kLgeStackTop;
    ctx.r3.u64 = kLgeGuardHigh - 8; ctx.r4.u64 = 0x5A; ctx.r5.u64 = 64;
    emit("begin", reinterpret_cast<uintptr_t>(g_rt.memory->TranslateVirtual(kLgeGuardHigh)));
    invoke(std::string(mode), 0x820E7440u, 3, ctx, inv);
    require(false, "guard store returned");
  }
  ctx.r1.u64 = kLwrStackTop;
  ctx.r3.u64 = P(4); ctx.r4.u64 = 0x5A; ctx.r5.u64 = 64;
  const uintptr_t p4 = reinterpret_cast<uintptr_t>(lwr_page(4));
  watch(4);
  require(lwr_open() == 0, "open the LWR session");
  if (mode == "lrgd-unregistered-page") {
    authorize({"__imp__sub_820E7440"});
    emit("begin", p4);
    invoke(std::string(mode), 0x820E7440u, 3, ctx, inv);
    require(false, "unregistered-page store returned");
  }
  require(lwr_register_page(lwr_page(4)) == 0, "register P4");
  if (mode == "lrgd-unauthorized") {
    emit("begin", p4);
    invoke(std::string(mode), 0x820E7440u, 3, ctx, inv);
    require(false, "unauthorized store returned");
  }
  if (mode == "lrgd-wrong-function") {
    authorize({"__imp__sub_820EB350"});
    emit("begin", p4);
    invoke(std::string(mode), 0x820E7440u, 3, ctx, inv);
    require(false, "wrong-function store returned");
  }
  require(false, "unknown fatal mode");
  std::abort();
}
#endif

void write_lines(const char* variable, const std::vector<std::string>& lines, bool digest) {
  const char* path = std::getenv(variable);
  if (!path || !*path) return;
  std::FILE* f = std::fopen(path, "wb");
  require(f != nullptr, "open a results file");
  for (const std::string& line : lines) {
    const std::string text = digest ? line + "|digest=" + sha256(line) : line;
    require(std::fprintf(f, "%s\n", text.c_str()) > 0, "write a record");
  }
  require(std::fclose(f) == 0, "close a results file");
}

std::string aggregate(const std::vector<std::string>& lines) {
  Sha256 a;
  for (const std::string& line : lines) {
    a.update(sha256(line));
    a.update("\n");
  }
  return a.hex();
}

template <typename List>
bool contains(const List& list, std::string_view mode) {
  return std::find(list.begin(), list.end(), mode) != list.end();
}
}  // namespace

int main(int argc, char** argv) {
#if LRB_NATIVE
  const Snapshot entry = snapshot();
  g_main = static_cast<long>(getpid());
  require(static_cast<long>(gettid()) == g_main, "started on the main thread");
  g_baseline = lrb::process_tasks();
#endif
  require(argc == 2, "exactly one mode");
  g_mode = argv[1];
#if LRB_NATIVE
  const std::array<std::string_view, 3> positive = {"default-dispatch", "latch", "latch-cycles"};
  const bool fatal = contains(kFatal, g_mode);
  const bool traced_positive = g_mode == "latch-traced-positive";
  require(fatal || traced_positive || contains(positive, g_mode), "supported LRGD mode");
  const bool latch = g_mode != "default-dispatch";
  const rlimit no_core{0, 0};
  require(setrlimit(RLIMIT_CORE, &no_core) == 0, "disable core dumps");
  Witness witness(std::getenv("LRB_GATE_TOKEN"));
  if (fatal || traced_positive) {
    require(witness.valid, "traced modes require a 32-hex LRB_GATE_TOKEN");
    g_witness = &witness;
  }
  g_emit_claims = traced_positive;
  load_code_ranges();
#else
  require(g_mode == "default-dispatch", "ordinary (non-native) build supports default-dispatch only");
  const bool fatal = false, latch = false;
#endif
  const unsigned cycles = g_mode == "latch-cycles" ? 2u : 1u;
  if (const char* path = std::getenv("LRGD_RECORD_FILE"); path && *path) {
    g_records = std::fopen(path, "w");
    require(g_records != nullptr, "open the LRGD record file");
  }
#if LRB_NATIVE
  record_snapshot(0, "entry", entry);
  check_threads(0, "entry");
  locate_latch();
  record_latch("entry");
  require(g_latch->load() == false, "SDK SEH latch clear at entry");
#endif
  rex::LogConfig log{};
  log.log_to_console = std::getenv("LRB_SDK_LOG_CONSOLE") != nullptr;
  rex::InitLogging(log);
#if LRB_NATIVE
  {
    const Snapshot logged = snapshot();
    record_snapshot(0, "after-logging", logged);
    require(changed(entry, logged).empty(), "logging initialization changed no signal disposition");
    check_threads(0, "after-logging");
  }
  if (latch) {
    // EXPERIMENTAL D1(a), test executable only: suppress the SDK SEH handler.
    g_latch->store(true);
    record_latch("after-store");
  }
#endif

  for (unsigned i = 1; i <= cycles; ++i) {
    rex::Runtime runtime{std::filesystem::path{}};
    Cycle c;
    c.index = i;
    c.latch = latch;
    c.fatal = fatal;
    c.runtime = &runtime;
    setup(c);
#if LRB_NATIVE
    if (i == 1) record_latch("after-setup");
    require(g_latch->load(), "SDK SEH latch set after Setup in both variants");
    const Snapshot after_setup = snapshot();
    record_snapshot(i, "after-setup", after_setup);
    const Action seh = check_after_setup(c, entry, after_setup);
    Snapshot expect_final = entry;
    if (latch) {
      handoff(c, entry);
    } else {
      for (int sig : {SIGSEGV, SIGILL, SIGBUS, SIGFPE}) expect_final[sig] = seh;
      record("LRGD_HANDOFF_V1|mode=" + g_mode + "|cycle=" + std::to_string(i) +
             "|result=not-attempted|segv_beneath=sdk-seh");
    }
    const Snapshot before_dispatch = snapshot();
#endif
    allocate_regions();
    verify_lge_protection();
    void* handle = g_rt.memory->RegisterPhysicalMemoryInvalidationCallback(invalidated, &g_inv);
    require(handle != nullptr, "register the invalidation callback");
    make_thread_state(i);
#if LRB_NATIVE
    if (latch) require(lrb_owns_sigsegv() == 1, "LRB owner exclusive before dispatch");
    if (fatal) run_fatal(g_mode);
#endif
    dispatcher_negatives(i);
    const unsigned claims_before = g_results.total_claims;
    dispatch_matrix(i, latch);
    verify_lge_protection();
    require(g_results.total_claims - claims_before == (latch ? 2 * kExpectedClaims : 0u),
            "claim total across both watched passes");
#if LRB_NATIVE
    const Snapshot after_dispatch = snapshot();
    record_snapshot(i, "after-dispatch", after_dispatch);
    require(changed(before_dispatch, after_dispatch).empty(), "dispatch changed no signal disposition");
    check_threads(i, "after-dispatch");
    if (latch) require(lrb_owns_sigsegv() == 1, "LRB owner still exclusive after dispatch");
#endif
    record("LRGD_DISPATCH_V1|mode=" + g_mode + "|cycle=" + std::to_string(i) +
           "|dispatches=" + std::to_string(g_rt.dispatches) + "|claims=" + std::to_string(g_results.total_claims - claims_before));
    drop_thread_state();
    g_rt.memory->UnregisterPhysicalMemoryInvalidationCallback(handle);
    release_regions();
#if LRB_NATIVE
    if (latch) release_owner(c, entry);
    teardown(c, expect_final);
    if (i == cycles) record_latch("after-shutdown");
#else
    teardown(c);
#endif
  }
  if (g_records) require(std::fclose(g_records) == 0, "close the LRGD record file");
  write_lines("LRGD_LGE_FILE", g_results.lge, true);
  write_lines("LRGD_LWR_FILE", g_results.lwr, true);
  write_lines("LRGD_LWR_WATCHED_FILE", g_results.lwr_watched, true);
  write_lines("LRGD_DISPATCH_FILE", g_results.dispatch, false);
  write_lines("LRGD_RESTART_FILE", g_results.restarts, false);
  write_lines("LRGD_CLAIMS_FILE", g_results.claims, false);
  std::printf("LRGD PASS mode=%s variant=%s cycles=%u lge=%zu lwr=%zu watched=%zu claims=%u lge_aggregate=%s "
              "lwr_aggregate=%s checks=%u native=%d\n",
              g_mode.c_str(), latch ? "latch" : "default", cycles, g_results.lge.size(), g_results.lwr.size(),
              g_results.lwr_watched.size(), g_results.total_claims, aggregate(g_results.lge).c_str(),
              aggregate(g_results.lwr).c_str(), lrb::checks(), LRB_NATIVE);
  return 0;
}

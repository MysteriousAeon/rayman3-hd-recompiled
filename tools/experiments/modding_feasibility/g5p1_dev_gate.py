#!/usr/bin/env python3
"""G5-P1 (D-243, E-476) DEVELOPMENT-ONLY runtime gate: the `level-tx` transaction of tools/m33_mod_overlay.h.
NOT part of any build chain or release. The production overlay (tools/m33_mod_overlay.h) is never edited and has no
transaction code; production runtimes refuse `level-tx` / `tx-file` (unknown_record) and `.lvl` / `.ptr` growth
(grow_not_allowed).

`apply` edits only the SDK's installed copy (external/rexglue-sdk/include/rex/m33_mod_overlay.h, outside Git) for a
private incremental build (tools\\build_incremental.bat): it adds `#define R3HD_DEV_STRUCTURAL_TX 1` and the code
under `#if defined(R3HD_DEV_STRUCTURAL_TX)` listed in EDITS below. `revert` copies the production header back byte for
byte (then rebuild). `render OUT [--no-define]` writes the patched text elsewhere (for the deterministic test,
g5p1_tx_test.cpp); `status` prints production | patched | other.

What the patched runtime accepts (everything else is the production validation unchanged; any failure refuses the
whole plan before any byte is served, whichever file the guest opens first):
  - only while the environment variable R3HD_DEV_STRUCTURAL_TX names the level (unset by default:
    `level_tx_not_enabled`);
  - one `level-tx 1 <level> <mod> <id>` (version 1, an allow-listed level, a mod of the plan), then per member
    `tx-file <index> <lvl|ptr> <orig sha256> <guest size> <result sha256>` after its `file` and before its `grow` /
    ranges;
  - members: exactly intro_10.lvl 7,661,836 bytes and intro_10.ptr 209,068 bytes, or (G5-P4a, D-247) intro_20.lvl
    6,135,684 bytes and intro_20.ptr 273,540 bytes, with their SHA-256 (hashed here),
    growth <= 4,096 / 1,024 bytes; each grown by a `grow` of exactly the declared size;
  - the pointer table is one range of the transaction's mod over the whole guest size; the guest image (original +
    the transaction mod's ranges) has the declared SHA-256; the id is the first 16 hex digits of the SHA-256 of the
    canonical text (tools/r3hd_mods.py tx_id);
  - a grown file that is not VS.sub and not a member refuses the plan.

G5-P3 (D-246, E-479): the members are snapshotted once at plan load and every read and size query of a member is
served from the verified image (P3 below). `render ... --no-snapshot` writes the G5-P2b header (for the reproduction
only); `render ... --test-allow LVL_SIZE:LVL_SHA:PTR_SIZE:PTR_SHA` swaps the allow-list for synthetic fixtures (the
deterministic test only; `apply` never does either).

G6-P1 (D-251, E-484): transaction version 2 (lvl + ptr + transit.lvl, the transit member same-size), the P6 edits
below; version 1 is unchanged. `render ... --no-g6` writes the header without them (reproduction only).

G6-P3 (D-256, E-489): intro_20 version-2 transactions (its .lvl / .ptr rows also in version 2, and intro_20's own
transit.lvl 26,140 bytes as the same-size member), the P7 edits; `render ... --no-g6p3` omits them.

usage: g5p1_dev_gate.py apply | revert | status | render OUT [--no-define] [--no-snapshot] [--no-g6] [--no-g6p3]
       [--test-allow X]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROD = ROOT / "tools" / "m33_mod_overlay.h"
# G6-P30 (D-286): the production header now carries the production level-transaction policy; development builds are
# still rendered from the frozen pre-G6-P30 production header (byte for byte the base of every earlier dev build).
BASE = Path(__file__).resolve().parent / "m33_mod_overlay_pre_g6p30.h"
SDK = ROOT / "external" / "rexglue-sdk" / "include" / "rex" / "m33_mod_overlay.h"
MARK = "G5P1 level-tx"
DEFINE = "#define R3HD_DEV_STRUCTURAL_TX 1  // G5-P1 development build (g5p1_dev_gate.py); never in production\n"

EDITS = []


def rep(old, new):
    EDITS.append((old, new))


rep("#include <fstream>\n", "#include <fstream>\n#include <iterator>\n")

rep('''// refuses such a plan as a whole (unknown_record).
#pragma once
''', '''// refuses such a plan as a whole (unknown_record).
//
// G5-P1 (D-243, DEVELOPMENT BUILDS ONLY): with R3HD_DEV_STRUCTURAL_TX defined at compile time (never in a production
// build: tools/experiments/modding_feasibility/g5p1_dev_gate.py adds the define to the SDK's installed copy for a
// private build) and the environment variable R3HD_DEV_STRUCTURAL_TX naming the level, a plan may carry one level
// transaction that lets an allow-listed level file and its pointer table grow together:
//   level-tx <version 1> <level> <mod id> <transaction id>
//   tx-file <file index> <lvl|ptr> <original sha256> <guest size> <sha256 of the guest image>   (after its `file`)
// Before anything is served: the level, the two files' names, sizes and SHA-256 (hashed here from the files) are the
// allow-listed ones; both members are present, each grown by its own `grow` within its bound; the pointer table is
// covered by one range of the transaction's mod; the image the guest will read (original + that mod's ranges) has
// the declared SHA-256; the identifier is the SHA-256 of the canonical transaction text. Any failure refuses the whole
// plan, as every other check does (so no member is ever served alone, whichever file the guest opens first). Without
// the define these records are unknown (`unknown_record`), so a production runtime refuses such a plan as a whole,
// and `.lvl` / `.ptr` growth stays refused (`grow_not_allowed`).
#pragma once
''')
rep('''struct Range {''', '''#if defined(R3HD_DEV_STRUCTURAL_TX)
// G5-P1 (D-243): development-only level transactions (see the top of this file).
namespace devtx {
struct Member {
  const char* level;
  const char* role;
  const char* name;
  uint64_t size;
  const char* sha256;
  uint64_t max_grow;
};
constexpr Member kAllowed[] = {
    {"intro_10", "lvl", "intro_10.lvl", 7661836, "a37638bf1370357db21f33df5c4d37ae806b3c4b9f81b331503ba62d1b19e2ee",
     4096},
    {"intro_10", "ptr", "intro_10.ptr", 209068, "6c9dd70c488a1cac95efc0a55a6086255dae2d851bacd93f5abefdcc8200e940",
     1024},
    // G5-P4a (D-247, E-480): the second allow-listed level (one transaction per plan; the variable names the level)
    {"intro_20", "lvl", "intro_20.lvl", 6135684, "a21aa7691db4cedb3892e685e5395fd23b530b0bde4d64a09035dfb5f2d0b11f",
     4096},
    {"intro_20", "ptr", "intro_20.ptr", 273540, "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1",
     1024},
};
// The level the environment enables ("" = none): read at plan load.
inline std::string EnabledLevel() {
  const char* v = std::getenv("R3HD_DEV_STRUCTURAL_TX");
  return v ? std::string(v) : std::string();
}

class Sha256 {
 public:
  void Update(const uint8_t* p, size_t n) {
    total_ += n;
    while (n) {
      const size_t k = std::min(n, size_t(64) - used_);
      std::memcpy(buf_ + used_, p, k);
      used_ += k;
      p += k;
      n -= k;
      if (used_ == 64) {
        Block(buf_);
        used_ = 0;
      }
    }
  }
  std::string HexDigest() {
    const uint64_t bits = total_ * 8;
    const uint8_t one = 0x80, zero = 0;
    Update(&one, 1);
    while (used_ != 56) Update(&zero, 1);
    uint8_t len[8];
    for (int i = 0; i < 8; ++i) len[i] = uint8_t(bits >> (56 - 8 * i));
    Update(len, 8);
    static const char* hex = "0123456789abcdef";
    std::string out;
    for (uint32_t v : h_)
      for (int i = 28; i >= 0; i -= 4) out.push_back(hex[(v >> i) & 15]);
    return out;
  }

 private:
  static uint32_t Rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
  void Block(const uint8_t* b) {
    static const uint32_t k[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
    uint32_t w[64];
    for (int i = 0; i < 16; ++i)
      w[i] = uint32_t(b[4 * i]) << 24 | uint32_t(b[4 * i + 1]) << 16 | uint32_t(b[4 * i + 2]) << 8 | b[4 * i + 3];
    for (int i = 16; i < 64; ++i) {
      const uint32_t s0 = Rotr(w[i - 15], 7) ^ Rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      const uint32_t s1 = Rotr(w[i - 2], 17) ^ Rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h_[0], bb = h_[1], c = h_[2], d = h_[3], e = h_[4], f = h_[5], g = h_[6], h = h_[7];
    for (int i = 0; i < 64; ++i) {
      const uint32_t t1 = h + (Rotr(e, 6) ^ Rotr(e, 11) ^ Rotr(e, 25)) + ((e & f) ^ (~e & g)) + k[i] + w[i];
      const uint32_t t2 = (Rotr(a, 2) ^ Rotr(a, 13) ^ Rotr(a, 22)) + ((a & bb) ^ (a & c) ^ (bb & c));
      h = g;
      g = f;
      f = e;
      e = d + t1;
      d = c;
      c = bb;
      bb = a;
      a = t1 + t2;
    }
    h_[0] += a;
    h_[1] += bb;
    h_[2] += c;
    h_[3] += d;
    h_[4] += e;
    h_[5] += f;
    h_[6] += g;
    h_[7] += h;
  }
  uint32_t h_[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  uint8_t buf_[64] = {};
  size_t used_ = 0;
  uint64_t total_ = 0;
};
inline std::string Sha256Hex(const uint8_t* p, size_t n) {
  Sha256 s;
  s.Update(p, n);
  return s.HexDigest();
}
// The file name (ASCII letters without case) is exactly `name`.
inline bool NameIs(const std::filesystem::path& p, const char* name) {
  const auto x = p.filename().native();
  if (x.size() != std::strlen(name)) return false;
  for (size_t i = 0; i < x.size(); ++i) {
    auto c = x[i];
    if (c >= 'A' && c <= 'Z') c = c + 32;
    if (c != decltype(c)(name[i])) return false;
  }
  return true;
}
inline bool Hex64(const std::string& s) {
  if (s.size() != 64) return false;
  for (char c : s)
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
  return true;
}
}  // namespace devtx
#endif

struct Range {''')
rep('''  uint64_t grow_reads = 0;    // M36: reads of a grown file seen (for the log)
  bool size_logged = false;
};''', '''  uint64_t grow_reads = 0;    // M36: reads of a grown file seen (for the log)
  bool size_logged = false;
#if defined(R3HD_DEV_STRUCTURAL_TX)
  int tx_member = -1;         // G5-P1: index into devtx::kAllowed when a `tx-file` names this file
  uint64_t tx_guest = 0;
  std::string tx_orig, tx_result;
#endif
};''')
rep('''  bool grown = false;  // M36: some file has guest_size > size
};''', '''  bool grown = false;  // M36: some file has guest_size > size
#if defined(R3HD_DEV_STRUCTURAL_TX)
  bool tx = false;  // G5-P1: a `level-tx` record was read
  std::string tx_level, tx_mod, tx_id;
#endif
};''')
rep('''    } else if (kind == "grow") {
      std::string index_text, size_text, extra;
      ls >> index_text >> size_text >> extra;
      uint64_t index = 0, guest = 0;
      if (!ParseU64(index_text, index) || !ParseU64(size_text, guest) || !extra.empty()) return fail("bad_grow");
      if (index >= out.files.size()) return fail("grow_file");
      Target& t = out.files[size_t(index)];
      if (!GrowAllowed(t.path)) return fail("grow_not_allowed");
      if (t.guest_size != t.size || !t.ranges.empty()) return fail("grow_order");
      if (guest <= t.size || guest - t.size > kMaxGrowBytes) return fail("grow_bounds");''', '''#if defined(R3HD_DEV_STRUCTURAL_TX)
    } else if (kind == "level-tx") {  // G5-P1 (D-243): development builds only
      const std::string enabled = devtx::EnabledLevel();
      if (enabled.empty()) return fail("level_tx_not_enabled");
      std::string version, level, mod, id, extra;
      ls >> version >> level >> mod >> id >> extra;
      if (version != "1") return fail("tx_version");
      if (out.tx) return fail("tx_count");
      if (level.empty() || !extra.empty() || id.size() != 16 || !SafeToken(mod)) return fail("bad_tx");
      bool allowed = false;
      for (const auto& a : devtx::kAllowed) allowed |= level == a.level;
      if (!allowed || level != enabled) return fail("tx_level");
      bool known = false;
      for (const auto& m : out.mods) known |= m.substr(0, m.find(' ')) == mod;
      if (!known) return fail("tx_mod");
      out.tx = true;
      out.tx_level = level;
      out.tx_mod = mod;
      out.tx_id = id;
    } else if (kind == "tx-file") {
      std::string index_text, role, orig, guest_text, result, extra;
      ls >> index_text >> role >> orig >> guest_text >> result >> extra;
      uint64_t index = 0, guest = 0;
      if (!ParseU64(index_text, index) || !ParseU64(guest_text, guest) || !devtx::Hex64(orig) ||
          !devtx::Hex64(result) || !extra.empty())
        return fail("bad_tx_file");
      if (!out.tx) return fail("tx_order");
      if (index >= out.files.size()) return fail("tx_file");
      Target& t = out.files[size_t(index)];
      if (t.tx_member >= 0) return fail("tx_duplicate");
      if (t.guest_size != t.size || !t.ranges.empty()) return fail("tx_order");
      int member = -1;
      for (size_t i = 0; i < std::size(devtx::kAllowed); ++i)
        if (out.tx_level == devtx::kAllowed[i].level && role == devtx::kAllowed[i].role) member = int(i);
      if (member < 0) return fail("tx_role");
      for (const auto& other : out.files)
        if (other.tx_member == member) return fail("tx_duplicate");
      const devtx::Member& a = devtx::kAllowed[size_t(member)];
      if (!devtx::NameIs(t.path, a.name) || t.size != a.size || orig != a.sha256)
        return fail("tx_identity");
      if (guest <= t.size || guest - t.size > a.max_grow) return fail("tx_bounds");
      std::vector<uint8_t> all;
      if (!ReadAt(t.path, 0, t.size, all) || devtx::Sha256Hex(all.data(), all.size()) != orig)
        return fail("tx_identity");
      t.tx_member = member;
      t.tx_guest = guest;
      t.tx_orig = orig;
      t.tx_result = result;
#endif
    } else if (kind == "grow") {
      std::string index_text, size_text, extra;
      ls >> index_text >> size_text >> extra;
      uint64_t index = 0, guest = 0;
      if (!ParseU64(index_text, index) || !ParseU64(size_text, guest) || !extra.empty()) return fail("bad_grow");
      if (index >= out.files.size()) return fail("grow_file");
      Target& t = out.files[size_t(index)];
#if defined(R3HD_DEV_STRUCTURAL_TX)
      // G5-P1: a level transaction's member grows only to the size its `tx-file` declares (bounded there)
      const bool tx_grow = t.tx_member >= 0;
      if (tx_grow && guest != t.tx_guest) return fail("tx_bounds");
#else
      const bool tx_grow = false;
#endif
      if (!GrowAllowed(t.path) && !tx_grow) return fail("grow_not_allowed");
      if (t.guest_size != t.size || !t.ranges.empty()) return fail("grow_order");
      if (guest <= t.size || (!tx_grow && guest - t.size > kMaxGrowBytes)) return fail("grow_bounds");''')
rep('''      if (covered != t.guest_size) return "grow_uncovered";
    }
  }
  return {};
}''', '''      if (covered != t.guest_size) return "grow_uncovered";
    }
  }
#if defined(R3HD_DEV_STRUCTURAL_TX)
  // G5-P1 (D-243): the transaction is complete and its image is the one declared, or the whole plan is refused.
  if (out.tx) {
    std::string canonical = "level-tx 1 " + out.tx_level + " " + out.tx_mod + "\\n";
    for (size_t i = 0; i < std::size(devtx::kAllowed); ++i) {
      const devtx::Member& a = devtx::kAllowed[i];
      if (out.tx_level != a.level) continue;
      Target* t = nullptr;
      for (auto& f : out.files)
        if (f.tx_member == int(i)) t = &f;
      if (!t) return "tx_incomplete";
      if (t->guest_size != t->tx_guest) return "tx_incomplete";
      std::vector<uint8_t> image;
      if (!ReadAt(t->path, 0, t->size, image)) return "tx_identity";
      image.resize(size_t(t->guest_size), 0);
      size_t own = 0;
      for (const auto& r : t->ranges) {
        if (r.mod != out.tx_mod) continue;
        std::memcpy(image.data() + r.offset, r.data.data(), r.data.size());
        ++own;
      }
      if (!own) return "tx_incomplete";
      if (std::string(a.role) == "ptr" &&
          (t->ranges.size() != 1 || t->ranges[0].offset != 0 || t->ranges[0].length != t->guest_size))
        return "tx_ptr_cover";  // the rebuilt pointer table is one range of the transaction's mod
      if (devtx::Sha256Hex(image.data(), image.size()) != t->tx_result) return "tx_result_hash";
      canonical += std::string("tx-file ") + a.role + " " + a.name + " " + std::to_string(t->size) + " " +
                   t->tx_orig + " " + std::to_string(t->guest_size) + " " + t->tx_result + "\\n";
    }
    for (const auto& f : out.files)
      if (f.tx_member < 0 && f.guest_size > f.size && !GrowAllowed(f.path)) return "tx_incomplete";
    const std::string id = devtx::Sha256Hex(reinterpret_cast<const uint8_t*>(canonical.data()), canonical.size());
    if (id.substr(0, 16) != out.tx_id) return "tx_id";
  }
#endif
  return {};
}''')
rep('''  for (const auto& id : s.plan.gameplay) Log(s, "M33 mods gameplay mod=" + id + " achievements=not_awarded");
}''', '''  for (const auto& id : s.plan.gameplay) Log(s, "M33 mods gameplay mod=" + id + " achievements=not_awarded");
#if defined(R3HD_DEV_STRUCTURAL_TX)
  if (s.plan.tx)
    Log(s, "G5P1 level-tx active level=" + s.plan.tx_level + " mod=" + s.plan.tx_mod + " id=" + s.plan.tx_id +
               " (development build)");
#endif
}''')

# --- G5-P3 (D-246, E-479): immutable member snapshot ------------------------------------------------------------
# Before G5-P3 the guest's reads of a member came from disk (HostPathFile::ReadSync, a handle shared for writing) with
# only the plan's ranges laid over them, so a member changed on disk after the plan was verified reached the guest
# mixed with the transaction's edits. From G5-P3 each member is read from disk exactly once at plan load; its SHA-256,
# its ranges' own-byte hashes and the declared image are all checked on those bytes, and the resulting guest image
# (immutable, owned by the process-lifetime plan) is what every size query and every read of the member is served.
P3 = []


def rep3(old, new):
    P3.append((old, new))


rep3("#include <iterator>\n", "#include <iterator>\n#include <memory>\n")
rep3('''// and `.lvl` / `.ptr` growth stays refused (`grow_not_allowed`).
#pragma once
''', '''// and `.lvl` / `.ptr` growth stays refused (`grow_not_allowed`).
//
// G5-P3 (D-246, development builds only): each member is read from disk once, at plan load, into host memory; its
// SHA-256, its ranges' own-byte hashes and the declared image are checked on those bytes, and the guest image built
// from them (immutable, owned by the plan for the process's life) answers every size query and every read of the
// member: the host's own bytes are discarded, so a member changed, truncated, replaced or removed on disk after the
// plan was verified never reaches the guest, and the `.lvl` and `.ptr` the guest reads are always the verified pair.
// Snapshots and images together are bounded (kMaxSnapshotBytes, `tx_snapshot_budget`); the snapshots are released
// once the images are built.
#pragma once
''')
rep3('''inline bool Hex64(const std::string& s) {''', '''// G5-P3 (D-246): bound on the members' host copies during plan load (snapshots + images; afterwards images only).
#ifndef R3HD_DEVTX_SNAPSHOT_BUDGET
#define R3HD_DEVTX_SNAPSHOT_BUDGET (16ull << 20)
#endif
constexpr uint64_t kMaxSnapshotBytes = R3HD_DEVTX_SNAPSHOT_BUDGET;
// Whole-member reads from disk (for the deterministic test: one per member per plan load).
inline uint64_t& MemberDiskReads() {
  static uint64_t n = 0;
  return n;
}
inline bool Hex64(const std::string& s) {''')
rep3('''  std::string tx_orig, tx_result;
#endif''', '''  std::string tx_orig, tx_result;
  std::shared_ptr<const std::vector<uint8_t>> tx_snapshot;  // G5-P3: the original bytes, read once (load only)
  std::shared_ptr<const std::vector<uint8_t>> tx_image;     // G5-P3: the whole guest view, served for every read
  uint64_t tx_reads = 0, tx_passes = 0;  // G5-P3: reads served; reads at offset 0 (a guest pass from the start)
  bool tx_changed_logged = false;
#endif''')
rep3('''      std::vector<uint8_t> all;
      if (!ReadAt(t.path, 0, t.size, all) || devtx::Sha256Hex(all.data(), all.size()) != orig)
        return fail("tx_identity");''', '''      // G5-P3: one physical read of the whole member; every later check and every guest read uses these bytes
      uint64_t held = 0;
      for (const auto& other : out.files)
        if (other.tx_snapshot) held += other.tx_snapshot->size() + other.tx_guest;
      if (held + t.size + guest > devtx::kMaxSnapshotBytes) return fail("tx_snapshot_budget");
      auto all = std::make_shared<std::vector<uint8_t>>();
      ++devtx::MemberDiskReads();
      if (!ReadAt(t.path, 0, t.size, *all) || devtx::Sha256Hex(all->data(), all->size()) != orig)
        return fail("tx_identity");
      t.tx_snapshot = std::move(all);''')
rep3('''      if ((inside && !ReadAt(t.path, r.offset, inside, own)) || Fnv1a(own.data(), own.size()) != r.base)
        return fail("game_bytes_hash");''', '''#if defined(R3HD_DEV_STRUCTURAL_TX)
      if (t.tx_snapshot && inside)  // G5-P3: a member's own bytes come from its snapshot, never from disk again
        own.assign(t.tx_snapshot->begin() + size_t(r.offset), t.tx_snapshot->begin() + size_t(r.offset + inside));
      else
#endif
      if (inside && !ReadAt(t.path, r.offset, inside, own)) return fail("game_bytes_hash");
      if (Fnv1a(own.data(), own.size()) != r.base) return fail("game_bytes_hash");''')
rep3('''      std::vector<uint8_t> image;
      if (!ReadAt(t->path, 0, t->size, image)) return "tx_identity";
      image.resize(size_t(t->guest_size), 0);''', '''      if (!t->tx_snapshot || t->tx_snapshot->size() != t->size) return "tx_identity";
      std::vector<uint8_t> image;  // G5-P3: the snapshot, not a second read from disk (one allocation)
      image.reserve(size_t(t->guest_size));
      image.assign(t->tx_snapshot->begin(), t->tx_snapshot->end());
      image.resize(size_t(t->guest_size), 0);''')
rep3('''      if (devtx::Sha256Hex(image.data(), image.size()) != t->tx_result) return "tx_result_hash";''',
     '''      if (devtx::Sha256Hex(image.data(), image.size()) != t->tx_result) return "tx_result_hash";
      // G5-P3: the view the guest is served: the declared image plus any other mod's (disjoint, verified) ranges
      for (const auto& r : t->ranges)
        if (r.mod != out.tx_mod) std::memcpy(image.data() + r.offset, r.data.data(), r.data.size());
      t->tx_image = std::make_shared<const std::vector<uint8_t>>(std::move(image));''')
rep3('''    if (id.substr(0, 16) != out.tx_id) return "tx_id";''', '''    if (id.substr(0, 16) != out.tx_id) return "tx_id";
    for (auto& f : out.files) f.tx_snapshot.reset();  // G5-P3: the images hold every byte the guest can read''')
rep3('''               " (development build)");
#endif''', '''               " (development build)");
  for (const auto& t : s.plan.files)
    if (t.tx_image)
      Log(s, "G5P3 tx snapshot file=" + t.path.filename().string() + " host_size=" + std::to_string(t.size) +
                 " image_bytes=" + std::to_string(t.tx_image->size()) + " disk_reads=" +
                 std::to_string(devtx::MemberDiskReads()));
#endif''')
rep3('''  Target* found = nullptr;
  for (auto& t : s.plan.files) {
    std::error_code ec;''', '''  Target* found = nullptr;
#if defined(R3HD_DEV_STRUCTURAL_TX)
  // G5-P3: a member is matched by its path too, so a replaced or removed file still maps to its image
  for (auto& t : s.plan.files)
    if (!found && t.tx_image && t.path.lexically_normal() == host_path.lexically_normal()) found = &t;
#endif
  for (auto& t : s.plan.files) {
    if (found) break;
    std::error_code ec;''')
rep3('''  Target* t = Find(s, host_path);
  if (!t) return 0;
  size_t replaced = 0;''', '''  Target* t = Find(s, host_path);
  if (!t) return 0;
  size_t replaced = 0;
#if defined(R3HD_DEV_STRUCTURAL_TX)
  if (t->tx_image)  // G5-P3: the read is the image's bytes (laid again so no earlier overlay can alter a member)
    Overlay(buffer, offset, length, t->tx_image->data(), 0, t->tx_image->size());
#endif''')
rep3('''  Target* t = Find(s, host_path);
  if (!t || t->guest_size == t->size || uint64_t(size) != t->size) return size;''', '''  Target* t = Find(s, host_path);
#if defined(R3HD_DEV_STRUCTURAL_TX)
  if (t && t->tx_image) {  // G5-P3: a member's guest size is its image's, whatever the file on disk became
    if (uint64_t(size) != t->size && !t->tx_changed_logged) {
      t->tx_changed_logged = true;
      Log(s, "G5P3 tx host_changed file=" + t->path.filename().string() + " host_size=" + std::to_string(size) +
                 " verified_size=" + std::to_string(t->size) + " served=image");
    }
    if (!t->size_logged) {
      t->size_logged = true;
      Log(s, "M36 grow size file=" + t->path.filename().string() + " host_size=" + std::to_string(t->size) +
                 " guest_size=" + std::to_string(t->guest_size));
    }
    return size_t(t->tx_image->size());
  }
#endif
  if (!t || t->guest_size == t->size || uint64_t(size) != t->size) return size;''')
rep3('''  Target* t = Find(s, host_path);
  if (!t || t->guest_size == t->size) return host_ok;''', '''  Target* t = Find(s, host_path);
#if defined(R3HD_DEV_STRUCTURAL_TX)
  if (t && t->tx_image) {  // G5-P3: every byte of a member comes from its image; the host's bytes are discarded
    const auto& img = *t->tx_image;
    const size_t n = offset >= img.size() ? 0 : size_t(std::min<uint64_t>(length, img.size() - offset));
    if (n) std::memcpy(buffer, img.data() + size_t(offset), n);
    const uint64_t host = host_ok ? *bytes_read : 0;
    *bytes_read = n;
    ++t->tx_reads;
    if (offset == 0 && ++t->tx_passes <= kMaxGrowLogLines)
      Log(s, "G5P3 tx pass file=" + t->path.filename().string() + " pass=" + std::to_string(t->tx_passes) +
                 " reads_before=" + std::to_string(t->tx_reads - 1) + " image_bytes=" + std::to_string(img.size()));
    if (t->tx_reads <= kMaxGrowLogLines)
      Log(s, "G5P3 tx read file=" + t->path.filename().string() + " offset=" + std::to_string(offset) + " length=" +
                 std::to_string(length) + " host=" + std::to_string(host) + " served=" + std::to_string(n) +
                 " kind=" + (n ? "image" : "end"));
    return n > 0;
  }
#endif
  if (!t || t->guest_size == t->size) return host_ok;''')

# --- G6-P1 (D-251, E-484): transaction version 2 (an actor insertion: lvl + ptr + transit) ---------------------
# Version 1 (insert-graph-node) keeps exactly its members, rules, canonical text and log line. Version 2 adds the
# level's transit.lvl as a SAME-SIZE member (max_grow 0: its `tx-file` must declare the original size and no `grow`
# may name it); which members a transaction needs is a property of its version (Member::versions), so a version-2
# plan without its transit member is `tx_incomplete` and a version-1 plan cannot name a transit member (`tx_role`).
# Every member, the transit one included, is snapshotted, hashed and served from its verified image (G5-P3).
P6 = []


def rep6(old, new):
    P6.append((old, new))


rep6('''  const char* sha256;
  uint64_t max_grow;
};''', '''  const char* sha256;
  uint64_t max_grow;  // G6-P1: 0 = a same-size member (never grown)
  unsigned versions;  // G6-P1: bit (v - 1) set when a version-v transaction of the level needs this member
};''')
rep6('''     4096},
    {"intro_10", "ptr", "intro_10.ptr", 209068, "6c9dd70c488a1cac95efc0a55a6086255dae2d851bacd93f5abefdcc8200e940",
     1024},''', '''     4096, 3},
    {"intro_10", "ptr", "intro_10.ptr", 209068, "6c9dd70c488a1cac95efc0a55a6086255dae2d851bacd93f5abefdcc8200e940",
     1024, 3},''')
rep6('''     4096},
    {"intro_20", "ptr", "intro_20.ptr", 273540, "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1",
     1024},
};''', '''     4096, 1},
    {"intro_20", "ptr", "intro_20.ptr", 273540, "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1",
     1024, 1},
    // G6-P1 (D-251, E-484): intro_10's transit.lvl, a same-size member of version 2 only (insert-passive-lum)
    {"intro_10", "transit", "transit.lvl", 41508, "d300ba3a4a3c03cec6a73eb9da8a8d820fcc3a669591e976b357e804315bf275",
     0, 2},
};''')
rep6('''inline std::string EnabledLevel() {''', '''// G6-P1: the Member::versions bit of a transaction version (0 = unknown).
inline unsigned VersionBit(const std::string& v) { return v == "1" ? 1u : v == "2" ? 2u : 0u; }
inline std::string EnabledLevel() {''')
rep6('''  std::string tx_level, tx_mod, tx_id;''', '''  std::string tx_level, tx_mod, tx_id;
  std::string tx_version;  // G6-P1: "1" (lvl + ptr) or "2" (lvl + ptr + transit)''')
rep6('''      if (version != "1") return fail("tx_version");''',
     '''      if (!devtx::VersionBit(version)) return fail("tx_version");''')
rep6('''      for (const auto& a : devtx::kAllowed) allowed |= level == a.level;''',
     '''      for (const auto& a : devtx::kAllowed) allowed |= level == a.level && (a.versions & devtx::VersionBit(version));''')
rep6('''      out.tx_id = id;''', '''      out.tx_id = id;
      out.tx_version = version;''')
rep6('''        if (out.tx_level == devtx::kAllowed[i].level && role == devtx::kAllowed[i].role) member = int(i);''',
     '''        if (out.tx_level == devtx::kAllowed[i].level && role == devtx::kAllowed[i].role &&
            (devtx::kAllowed[i].versions & devtx::VersionBit(out.tx_version)))
          member = int(i);''')
rep6('''      if (guest <= t.size || guest - t.size > a.max_grow) return fail("tx_bounds");''',
     '''      if (a.max_grow == 0 ? guest != t.size : (guest <= t.size || guest - t.size > a.max_grow))
        return fail("tx_bounds");''')
rep6('''    std::string canonical = "level-tx 1 " + out.tx_level + " " + out.tx_mod + "\\n";''',
     '''    std::string canonical = "level-tx " + out.tx_version + " " + out.tx_level + " " + out.tx_mod + "\\n";''')
rep6('''      if (out.tx_level != a.level) continue;''',
     '''      if (out.tx_level != a.level || !(a.versions & devtx::VersionBit(out.tx_version))) continue;''')
rep6('''  if (s.plan.tx)
    Log(s, "G5P1 level-tx active level="''', '''  if (s.plan.tx && s.plan.tx_version != "1")
    Log(s, "G6P1 level-tx version=" + s.plan.tx_version + " members=lvl,ptr,transit (development build)");
  if (s.plan.tx)
    Log(s, "G5P1 level-tx active level="''')


# --- G6-P3 (D-256, E-489): intro_20 version-2 transactions (insert-fairy-on-graph) -----------------------------
# intro_20's .lvl / .ptr rows become members of versions 1 and 2, and intro_20's own transit.lvl (26,140 bytes) is
# its same-size version-2 member; no code changes. Applied after P6 (it edits P6's rows); `render ... --no-g6p3`
# writes the header without it (reproduction only).
P7 = []


def rep7(old, new):
    P7.append((old, new))


rep7('''     4096, 1},
    {"intro_20", "ptr", "intro_20.ptr", 273540, "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1",
     1024, 1},''', '''     4096, 3},
    {"intro_20", "ptr", "intro_20.ptr", 273540, "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1",
     1024, 3},''')
rep7('''     0, 2},
};''', '''     0, 2},
    // G6-P3 (D-256, E-489): intro_20's transit.lvl, a same-size member of version 2 only (insert-fairy-on-graph)
    {"intro_20", "transit", "transit.lvl", 26140, "51c0fbf1239acd6188316a6d64507761903d5a087df1ea717426d5cb810e6aa8",
     0, 2},
};''')


def patched(define=True, snapshot=True, test_allow=None, g6=True, g6p3=True):
    text = BASE.read_bytes().decode("utf-8")
    for old, new in EDITS + (P3 if snapshot else []) + (P6 if g6 else []) + (P7 if g6 and g6p3 else []):
        if text.count(old) != 1:
            raise SystemExit(f"anchor not unique: {old[:60]!r}")
        text = text.replace(old, new)
    if test_allow:   # render only (deterministic test on synthetic fixtures): replace the two allow-listed members
        ls, lh, ps, ph = test_allow.split(":")
        for name, size, sha in (("intro_10.lvl", ls, lh), ("intro_10.ptr", ps, ph)):
            old = [ln for ln in text.splitlines(True) if f'"{name}"' in ln]
            if len(old) != 1:
                raise SystemExit(f"allow-list line for {name}")
            head = old[0][:old[0].index(f'"{name}"')]
            text = text.replace(old[0], f'{head}"{name}", {int(size)}, "{sha}",\n', 1)
    if define:
        text = text.replace("#pragma once\n", "#pragma once\n" + DEFINE, 1)
    return text


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "status":
        b = SDK.read_bytes()
        print("patched" if MARK.encode() in b else ("production" if b == PROD.read_bytes() else "other"))
        return 0
    if cmd == "revert":
        SDK.write_bytes(PROD.read_bytes())
        print("reverted: SDK copy == tools/m33_mod_overlay.h")
        return 0
    if cmd == "render" and len(argv) >= 2:
        allow = argv[argv.index("--test-allow") + 1] if "--test-allow" in argv else None
        Path(argv[1]).write_bytes(patched("--no-define" not in argv, "--no-snapshot" not in argv,
                                          allow, "--no-g6" not in argv, "--no-g6p3" not in argv).encode("utf-8"))
        print(f"rendered {argv[1]}")
        return 0
    if cmd != "apply":
        raise SystemExit(__doc__)
    if SDK.read_bytes() != PROD.read_bytes():
        raise SystemExit("SDK copy differs from the production header; revert first")
    SDK.write_bytes(patched().encode("utf-8"))
    print("applied (development-only): SDK copy patched")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

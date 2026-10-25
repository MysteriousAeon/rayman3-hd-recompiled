// Optional display text for the host Achievements overlay and unlock toast (D-101). The achievement store, which
// the title's own XamUserCreateAchievementEnumerator reads, keeps the XDBF English; only what the host draws is
// replaced, and only when the translated entry names the exact English it was made from (SHA-256 of the XDBF
// string). R3HD_ACH_TEXT = a file written by tools/r3hd_mods.py plan from the enabled mods'
// achievements/achievements.json: one entry per line, "<id>\t<field>\t<sha256 hex of the English>\t<text>",
// field = label | description | unachieved; UTF-8. No variable, no file, an empty or stale entry: English.
// Installed into the SDK as <rex/r3hd_achtext.h> by tools/r3hd_achtext_patch.py.
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <utility>

namespace r3hd_achtext {

enum Field : int { kLabel = 0, kDescription = 1, kUnachieved = 2 };

// Small SHA-256 (FIPS 180-4) for the source check; the SDK's own copy is compiled into one kernel unit only.
inline std::string Sha256Hex(const std::string& s) {
  static const uint32_t k[64] = {
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98,
      0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
      0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8,
      0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
      0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
      0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
      0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
      0xc67178f2};
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  std::string m = s;
  const uint64_t bits = static_cast<uint64_t>(s.size()) * 8;
  m.push_back(static_cast<char>(0x80));
  while (m.size() % 64 != 56) m.push_back(0);
  for (int i = 7; i >= 0; --i) m.push_back(static_cast<char>((bits >> (i * 8)) & 0xFF));
  auto rotr = [](uint32_t x, int n) { return (x >> n) | (x << (32 - n)); };
  for (size_t off = 0; off < m.size(); off += 64) {
    uint32_t w[64];
    for (int i = 0; i < 16; ++i) {
      const auto* p = reinterpret_cast<const unsigned char*>(m.data() + off + i * 4);
      w[i] = (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3];
    }
    for (int i = 16; i < 64; ++i) {
      const uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      const uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; ++i) {
      const uint32_t t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + k[i] + w[i];
      const uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
      hh = g, g = f, f = e, e = d + t1, d = c, c = b, b = a, a = t1 + t2;
    }
    h[0] += a, h[1] += b, h[2] += c, h[3] += d, h[4] += e, h[5] += f, h[6] += g, h[7] += hh;
  }
  char out[65];
  for (int i = 0; i < 8; ++i) std::snprintf(out + i * 8, 9, "%08x", h[i]);
  return std::string(out, 64);
}

struct Entry {
  std::string source_sha256, text;
};

class Table {
 public:
  // Parses the file's text; bad lines are skipped (counted). Returns the number of entries kept.
  size_t Parse(const std::string& body) {
    entries_.clear();
    skipped_ = 0;
    size_t pos = 0;
    while (pos < body.size()) {
      size_t end = body.find('\n', pos);
      if (end == std::string::npos) end = body.size();
      std::string line = body.substr(pos, end - pos);
      pos = end + 1;
      if (!line.empty() && line.back() == '\r') line.pop_back();
      if (line.empty() || line[0] == '#') continue;
      size_t t1 = line.find('\t'), t2 = t1 == std::string::npos ? t1 : line.find('\t', t1 + 1),
             t3 = t2 == std::string::npos ? t2 : line.find('\t', t2 + 1);
      if (t3 == std::string::npos) { ++skipped_; continue; }
      const std::string id_text = line.substr(0, t1), field = line.substr(t1 + 1, t2 - t1 - 1),
                        hash = line.substr(t2 + 1, t3 - t2 - 1), text = line.substr(t3 + 1);
      char* stop = nullptr;
      const unsigned long id = std::strtoul(id_text.c_str(), &stop, 10);
      const int f = field == "label" ? kLabel : field == "description" ? kDescription
                  : field == "unachieved" ? kUnachieved : -1;
      bool control = false;
      for (unsigned char ch : text) control |= ch < 0x20 || ch == 0x7F;
      if (id_text.empty() || *stop || id == 0 || id > 0xFFFF || f < 0 || hash.size() != 64 || text.empty() ||
          text.size() > 640 || control) {
        ++skipped_;
        continue;
      }
      entries_[{static_cast<uint32_t>(id), f}] = Entry{hash, text};
    }
    return entries_.size();
  }

  // The text to draw: the translation when it was made from exactly this English, otherwise the English.
  // An untranslated "unachieved" text whose English equals the description takes the description's translation
  // (the title's table repeats the description there for every achievement, E-245).
  const std::string& Display(uint32_t id, Field field, const std::string& english,
                             const std::string& english_description) const {
    if (const Entry* e = Find(id, field, english)) return e->text;
    if (field == kUnachieved && english == english_description) {
      if (const Entry* e = Find(id, kDescription, english_description)) return e->text;
    }
    return english;
  }
  size_t size() const { return entries_.size(); }
  size_t skipped() const { return skipped_; }
  size_t stale() const {
    std::lock_guard<std::mutex> guard(mutex_);
    return stale_seen_.size();
  }

 private:
  const Entry* Find(uint32_t id, int field, const std::string& english) const {
    auto it = entries_.find({id, field});
    if (it == entries_.end()) return nullptr;
    if (Sha256Hex(english) == it->second.source_sha256) return &it->second;
    std::lock_guard<std::mutex> guard(mutex_);
    stale_seen_.insert({id, field});
    return nullptr;
  }
  std::map<std::pair<uint32_t, int>, Entry> entries_;
  mutable std::set<std::pair<uint32_t, int>> stale_seen_;
  size_t skipped_ = 0;
  mutable std::mutex mutex_;
};

// The process-wide table, loaded once from R3HD_ACH_TEXT. log(text) receives one summary line. Not a template: every
// caller (overlay, toast) must reach the same static table.
inline const Table& Get(void (*log)(const char*)) {
  static Table table;
  static std::once_flag once;
  std::call_once(once, [&] {
    const char* path = std::getenv("R3HD_ACH_TEXT");
    if (!path || !*path) {
      log("R3HD achievement_text=off");
      return;
    }
    std::string body;
    if (FILE* f = std::fopen(path, "rb")) {
      char buf[4096];
      size_t n;
      while ((n = std::fread(buf, 1, sizeof(buf), f)) > 0 && body.size() < (1u << 20)) body.append(buf, n);
      std::fclose(f);
    }
    const size_t kept = table.Parse(body);
    log(("R3HD achievement_text=file entries=" + std::to_string(kept) + " skipped=" +
         std::to_string(table.skipped())).c_str());
  });
  return table;
}

}  // namespace r3hd_achtext

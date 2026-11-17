// Host-only probe for plans produced by the shared Python engine. Never starts a game or writes source data.
#include "m33_mod_overlay.h"
#include <iostream>

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
  if (argc != 2) return 2;
  m33mods::Plan plan;
  const auto path = std::filesystem::path(argv[1]);
  const auto reason = m33mods::Load(path, plan);
  if (!reason.empty()) { std::cout << reason << '\n'; return 1; }
  size_t tested = 0;
  for (const auto& target : plan.files) {
    if (m33mods::GuestSize(target.path, size_t(target.size), nullptr, &path) != target.guest_size) return 1;
    for (const auto& range : target.ranges) {
      // Same sequence as HostPathFile::ReadSync, including M36 subtitle growth.
      const auto inside = range.offset < target.size
          ? std::min(range.length, target.size - range.offset) : 0;
      std::vector<uint8_t> bytes;
      if (!m33mods::ReadAt(target.path, range.offset, inside, bytes) && inside) return 1;
      bytes.resize(size_t(range.length));
      size_t count = size_t(inside);
      if (!m33mods::ExtendRead(target.path, range.offset, bytes.data(), bytes.size(), inside != 0, &count,
                              nullptr, &path)) return 1;
      m33mods::AfterRead(target.path, range.offset, bytes.data(), count, &path);
      if (bytes != range.data) return 1;
      ++tested;
    }
  }
  std::cout << "MOD_PLAN_PROBE PASS ranges=" << tested << '\n';
  return tested ? 0 : 1;
}

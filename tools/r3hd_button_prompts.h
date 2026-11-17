#pragma once
// D-199: one immutable artwork choice at initial texture load. The existing M33
// verifier is reused with a separate state, independent of community mod enablement.
#include <rex/m33_mod_overlay.h>
#include <rex/r3hd_button_prompt_policy.h>

namespace r3hd_prompts {
inline std::filesystem::path PlanPath() {
#ifdef _WIN32
  const wchar_t* p = _wgetenv(L"R3HD_BUTTON_PROMPTS_PLAN");
#else
  const char* p = std::getenv("R3HD_BUTTON_PROMPTS_PLAN");
#endif
  return p && *p ? std::filesystem::path(p) : std::filesystem::path();
}
inline size_t AfterRead(const std::filesystem::path& path, uint64_t offset, uint8_t* buffer,
                        size_t length, void (*log)(const char*)) {
  // This is the first texture bundle, not XEX/file metadata before SDL setup.
  if (!length || !m33mods::SameFileName(path, std::filesystem::path("fix.btf"))) return 0;
  static m33mods::State s;
  std::lock_guard<std::mutex> guard(s.mutex);
  if (!s.loaded) {
    s.log = log;
    const char* effective = std::getenv("R3HD_BUTTON_PROMPTS_EFFECTIVE");
    const Style style = effective && std::string_view(effective) == "playstation" ? Style::PlayStation : Style::Xbox;
    const auto plan = PlanPath();
    if (style == Style::PlayStation && !plan.empty()) {
      m33mods::EnsureLoaded(s, plan);
    } else {
      s.loaded = true;
    }
    if (log) log(s.active ? "R3HD prompts style=playstation policy=launch-time" :
                           "R3HD prompts style=xbox policy=launch-time");
  }
  if (!s.active) return 0;
  auto* t = m33mods::Find(s, path);
  if (!t) return 0;
  size_t replaced = 0;
  for (auto& r : t->ranges) {
    if (r.offset >= offset + length) break;
    if (r.offset + r.length <= offset) continue;
    replaced += m33mods::Overlay(buffer, offset, length, r.data.data(), r.offset, r.data.size());
  }
  return replaced;
}
}  // namespace r3hd_prompts

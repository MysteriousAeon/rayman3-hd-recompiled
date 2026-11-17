#pragma once
// Artwork only. No gameplay state, controller opening, mapping, polling or output.
#include <cstddef>
#include <string_view>

namespace r3hd_prompts {
enum class Style { Xbox, PlayStation };
enum class Family { Unknown, Xbox, PlayStation };
struct Controller { Family family; int player; };

inline Style Select(std::string_view preference, const Controller* pads, size_t count) {
  if (preference == "playstation") return Style::PlayStation;
  if (preference != "auto") return Style::Xbox;
  const Controller* chosen = nullptr;
  size_t primary = 0;
  for (size_t i = 0; i < count; ++i) {
    if (pads[i].player == 0) { chosen = &pads[i]; ++primary; }
  }
  if (primary != 1) chosen = count == 1 ? pads : nullptr;
  return chosen && chosen->family == Family::PlayStation ? Style::PlayStation : Style::Xbox;
}
}  // namespace r3hd_prompts

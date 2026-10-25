// M18 (D-047): guest-title compatibility correction for the end of revisit mode.
//
// This is NOT a runtime correctness fix. The translated title behaves exactly as its code says; the code has a
// progression defect (RE_NOTES "M18"). While the revisit flag is set, the level request function 82102CA8
// replaces every request for a world's first level by `endgame` (site 82102E3C). `endgame` is the hub of a
// finished campaign: its level script sets the world counter to 9, the pause menu's Resume is disabled and the
// last world page (the Tower of the Leptys) can only be entered once the end-of-game flag is set. Reached with
// the campaign unfinished, it leaves no way back to the interrupted game and no way into the Tower.
//
// The correction decides at that one site, from the title's own state:
//   - the request names the first level of the world being revisited (Revisit chosen again from inside revisit
//     mode, a reload of that level, a loaded revisit save): not the end of the world, the request passes;
//   - the request names the first level of the next world, the campaign is unfinished and an interrupted game
//     is on record: the title's own "return to the current game" transition (menu branch 82108518) is applied
//     and the interrupted level is requested;
//   - anything else (campaign finished, no interrupted game): the original substitution by `endgame`.
// R3HD_REVISIT=original keeps the title's original behaviour in every case.
//
// Decide() is pure and tested by tools/m18_revisit_test.cpp. The guest access lives in tools/m2_host/m2_trace.cpp.
#pragma once
#include <cstdint>
#include <cstring>

namespace m18 {

// First level of worlds 1..9 in the order of the title's table at 82837008 (lower case, as the title compares).
inline constexpr const char* kFirstLevels[9] = {"intro_10", "wood_11",  "swamp_60", "moor_00", "knaar_10",
                                                "flash_20", "sea_10",   "fact_40",  "tower_10"};
inline constexpr std::size_t kNameLimit = 0x1E;

enum class Action {
  kOriginal,          // let the title substitute `endgame`
  kPass,              // not the end of the revisited world: request the level that was asked for
  kReturnToCampaign,  // end of the revisited world in an unfinished campaign: request the interrupted level
};

struct Request {
  const char* name_lower;    // requested level, lower case (the title's own copy)
  uint32_t revisited_world;  // 8287611C: world being revisited, 1..9
  uint32_t end_of_game;      // 82876130
  const char* backup;        // 82BF7440: level of the interrupted game
};

inline bool EqualNoCase(const char* a, const char* b) {
  for (;; ++a, ++b) {
    char x = *a, y = *b;
    if (x >= 'A' && x <= 'Z') x = char(x - 'A' + 'a');
    if (y >= 'A' && y <= 'Z') y = char(y - 'A' + 'a');
    if (x != y) return false;
    if (!x) return true;
  }
}

// A usable interrupted-game level: a short printable name that is not the hub itself.
inline bool ValidBackup(const char* backup) {
  if (!backup || !*backup) return false;
  std::size_t n = 0;
  for (; backup[n]; ++n)
    if (n >= kNameLimit - 1 || backup[n] <= 32 || backup[n] >= 127) return false;
  return !EqualNoCase(backup, "endgame") && !EqualNoCase(backup, "menumap");
}

// Called only for a request the title is about to replace: revisit flag set, one-shot word clear, name equal to
// one of the eight world-entry levels.
inline Action Decide(const Request& q) {
  const uint32_t w = q.revisited_world;
  if (!q.name_lower || w < 1 || w > 9) return Action::kOriginal;
  if (!std::strcmp(q.name_lower, kFirstLevels[w - 1])) return Action::kPass;
  if (w <= 8 && !std::strcmp(q.name_lower, kFirstLevels[w]) && q.end_of_game == 0 && ValidBackup(q.backup))
    return Action::kReturnToCampaign;
  return Action::kOriginal;
}

inline const char* Name(Action a) {
  return a == Action::kPass ? "pass" : a == Action::kReturnToCampaign ? "return_to_campaign" : "original";
}

// R3HD_REVISIT: unset or anything but "original" selects the correction.
inline bool OriginalSelected(const char* value) { return value && !std::strcmp(value, "original"); }

}  // namespace m18

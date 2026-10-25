// M18 (D-047): decision table of the revisit correction. Host-only, no game material.
#include "m18_revisit.h"
#include <cstdio>

static int checks = 0, failures = 0;
static void Check(bool ok, const char* what) {
  ++checks;
  if (!ok) {
    ++failures;
    std::printf("FAIL %s\n", what);
  }
}

int main() {
  using namespace m18;
  // End of a revisited world, campaign unfinished, interrupted game on record: back to the campaign.
  Check(Decide({"wood_11", 1, 0, "wood_11"}) == Action::kReturnToCampaign, "world 1 ends, campaign in wood_11");
  Check(Decide({"tower_10", 8, 0, "tower_20"}) == Action::kReturnToCampaign, "world 8 ends, campaign in the Tower");
  Check(Decide({"tower_10", 8, 0, "Tower_10"}) == Action::kReturnToCampaign, "world 8 ends, campaign at the Tower entry");
  Check(Decide({"swamp_60", 2, 0, "Knaar_45"}) == Action::kReturnToCampaign, "world 2 ends, capitalised backup");
  for (uint32_t w = 1; w <= 8; ++w)
    Check(Decide({kFirstLevels[w], w, 0, "moor_30"}) == Action::kReturnToCampaign, "every world end");
  // Campaign finished: the title's hub is the right destination.
  for (uint32_t w = 1; w <= 8; ++w)
    Check(Decide({kFirstLevels[w], w, 1, "moor_30"}) == Action::kOriginal, "finished campaign keeps endgame");
  Check(Decide({"wood_11", 1, 1, "endgame"}) == Action::kOriginal, "finished campaign, revisit from the hub");
  // No interrupted game on record: nothing to return to.
  Check(Decide({"wood_11", 1, 0, ""}) == Action::kOriginal, "empty backup");
  Check(Decide({"wood_11", 1, 0, nullptr}) == Action::kOriginal, "null backup");
  Check(Decide({"wood_11", 1, 0, "endgame"}) == Action::kOriginal, "backup is the hub");
  Check(Decide({"wood_11", 1, 0, "EndGame"}) == Action::kOriginal, "backup is the hub, other case");
  Check(Decide({"wood_11", 1, 0, "menumap"}) == Action::kOriginal, "backup is the front end");
  Check(Decide({"wood_11", 1, 0, "bad name"}) == Action::kOriginal, "backup with a space");
  Check(Decide({"wood_11", 1, 0, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}) == Action::kOriginal, "backup too long");
  // The revisited world's own first level is never the end of that world.
  for (uint32_t w = 2; w <= 9; ++w) {
    Check(Decide({kFirstLevels[w - 1], w, 0, "moor_30"}) == Action::kPass, "own first level passes, unfinished");
    Check(Decide({kFirstLevels[w - 1], w, 1, "endgame"}) == Action::kPass, "own first level passes, finished");
    Check(Decide({kFirstLevels[w - 1], w, 0, ""}) == Action::kPass, "own first level passes, no backup");
  }
  // A world-entry level that is neither the revisited world's nor the next one's: not ours to interpret.
  Check(Decide({"moor_00", 1, 0, "wood_11"}) == Action::kOriginal, "unrelated world entry");
  Check(Decide({"wood_11", 5, 0, "sea_10"}) == Action::kOriginal, "earlier world entry");
  Check(Decide({"tower_10", 9, 0, "moor_30"}) == Action::kPass, "Tower revisited: its own entry");
  // Out-of-range state falls back to the title.
  Check(Decide({"wood_11", 0, 0, "wood_11"}) == Action::kOriginal, "world 0");
  Check(Decide({"wood_11", 10, 0, "wood_11"}) == Action::kOriginal, "world 10");
  Check(Decide({"wood_11", 0xFFFFFFFFu, 0, "wood_11"}) == Action::kOriginal, "world -1");
  Check(Decide({nullptr, 1, 0, "wood_11"}) == Action::kOriginal, "null name");
  Check(Decide({"Wood_11", 1, 0, "wood_11"}) == Action::kOriginal, "name must be the title's lower-case copy");
  // Helpers.
  Check(ValidBackup("wood_11") && ValidBackup("Lept_15") && !ValidBackup("") && !ValidBackup("ENDGAME"), "ValidBackup");
  Check(EqualNoCase("Tower_10", "tower_10") && !EqualNoCase("tower_1", "tower_10"), "EqualNoCase");
  Check(!OriginalSelected(nullptr) && !OriginalSelected("") && !OriginalSelected("fixed") && OriginalSelected("original"),
        "R3HD_REVISIT values");
  Check(!std::strcmp(Name(Action::kPass), "pass") && !std::strcmp(Name(Action::kOriginal), "original") &&
            !std::strcmp(Name(Action::kReturnToCampaign), "return_to_campaign"),
        "names");
  std::printf("M18_REVISIT_TEST %s checks=%d\n", failures ? "FAIL" : "PASS", checks);
  return failures ? 1 : 0;
}

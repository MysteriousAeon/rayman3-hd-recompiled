#pragma once
// G6-P82 / G6-P83 (D-331, D-332): state-change-aware XN_SYS_SIGNINCHANGED from XamShowSigninUI. Development default
// since G6-P83; the console contract for a sign-in UI that changed nothing remains UNKNOWN.
//
// The inherited XamShowSigninUI stub shows no UI. It broadcast XN_SYS_SIGNINCHANGED (0x0A) and then XN_SYS_UI = 0
// (0x09) on every call, whether or not any sign-in changed. In Rayman 3 HD that no-change 0x0A arms the title's 500 ms
// sign-in refresh; with the selected user still unsigned the refresh sets the signed-out latch 82836CC8 while the
// title's sign-in error box is open, and the box's later XN_SYS_UI = 0 close is then ignored (G6-P81, E-567; G6-P82,
// E-568: stuck box, ignored retry, stale deferred request).
//
// Default: XamShowSigninUI sends the 0x0A only when the signed-in owner (the single local profile's guest user,
// g6p79::Owner()) differs after the call from what it was before. Without the test-only handoff the owner never
// changes there, so the call sends XN_SYS_UI = 0 alone.
// Switch back (D-047): R3HD_SIGNIN_NOTIFY exactly "legacy" restores the inherited stub (0x0A on every call). Any
// other value, or none, keeps the default. No setting, UI or launcher option selects it.
// Either way the XN_SYS_UI = 0 completion, its order, the return value and every other notification source (startup,
// the G6-P80 rollback) are unchanged. Nothing reads or writes guest memory.
#include <atomic>
#include <cstdlib>
#include <cstring>

namespace g6p82 {

// Exact switch-back value: "legacy" and nothing else.
inline bool ParseLegacy(const char* value) { return value != nullptr && std::strcmp(value, "legacy") == 0; }

inline bool Legacy() {
  static const bool legacy = ParseLegacy(std::getenv("R3HD_SIGNIN_NOTIFY"));
  return legacy;
}

// State-change-aware policy active (the default).
inline bool Enabled() { return !Legacy(); }

// Hidden runs only: the per-call trace line (logging, no behaviour).
inline bool Trace() {
  static const bool trace = std::getenv("R3HD_NONINTRUSIVE") != nullptr;
  return trace;
}

// Outside hidden runs: true once, on the first call, when the switch back is selected (one log line, no behaviour).
inline bool NoteLegacyOnce() {
  static std::atomic<bool> noted{false};
  return Legacy() && !noted.exchange(true);
}

// Pure decision (unit-tested): legacy (not enabled) -> always notify; default -> notify only on an owner change.
inline bool Decide(bool enabled, unsigned owner_before, unsigned owner_after) {
  return !enabled || owner_before != owner_after;
}

inline bool ShouldNotify(unsigned owner_before, unsigned owner_after) {
  return Decide(Enabled(), owner_before, owner_after);
}

}  // namespace g6p82

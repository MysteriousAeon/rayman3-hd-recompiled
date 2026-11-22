#pragma once
// G6-P79 / G6-P80 (test only, hidden runs): profile handoff prototype. NOT a product policy (D-326 / D-327 / D-328 /
// D-329).
//
// The port has one local offline profile (XUID B13EBABEBABEBABE). Without this prototype it is signed in on guest
// user 0 for the whole process, and every user-indexed XAM profile API answers only for user 0.
//
// With R3HD_NONINTRUSIVE set and R3HD_TEST_PROFILE_HANDOFF exactly "1", the profile may move to another guest user,
// but only through the title's own sign-in request, as a transaction:
//   - pending: the title calls XamShowSigninUI (its single call site, 0x820F5268, runs after its START commit found
//     the save-gate user not signed in). G6-P80: the candidate is the title's OWN selection, its save-gate user
//     (word 828750A0, read once, read-only, at that call), not the host's "most recent START". The move needs that
//     user to be connected and to hold an unused START authorization: a START press edge made while connected and
//     not yet used by an earlier sign-in decision for that user (a cross-check: the title selects only by START).
//     Each START authorizes at most one decision; an unplug of that user voids it; the commit lock ends all moves.
//     There is no wall-clock window (G6-P80: the title's own error box can delay a legitimate request by seconds
//     or minutes; E-566 r1 refused one 3.6 s after its START). Otherwise nothing moves and the title's own error
//     path runs;
//   - committed: the owner's first commit witness (its profile-settings read or device selection, which the title
//     makes only after its START commit succeeded) locks the owner for the process lifetime;
//   - rolled back (G6-P80): if the pending owner's controller is unplugged before the commit, the profile returns to
//     guest user 0 (the boot state) and the caller broadcasts XN_SYS_SIGNINCHANGED, so the title re-reads its
//     sign-in records through its own refresh. No other controller is picked.
// The profile is always signed in on exactly one user (Owner()); every user-indexed XAM call answers for that user
// as user 0 does today and NO_SUCH_USER for the others. Content stays keyed by the XUID, so saves are shared.
//
// Without both variables Owner() is 0 and nothing else is recorded: the G6-P77 behaviour.
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <mutex>

namespace g6p79 {

constexpr unsigned kUsers = 4;

// Exact flag: "1" and nothing else, and only inside the hidden-test gate.
inline bool ParseEnable(const char* nonintrusive, const char* flag) {
  return nonintrusive != nullptr && flag != nullptr && std::strcmp(flag, "1") == 0;
}

constexpr unsigned kHome = 0;  // the boot owner, and the rollback target
constexpr uint32_t kTitleSaveGateUser = 0x828750A0;  // the title's selected (save-gate) user, read-only (RE_NOTES)

enum class Outcome { kMoved, kSameOwner, kLocked, kNoCandidate, kUsedStart, kNotConnected, kNoTitleUser };

inline const char* OutcomeName(Outcome o) {
  switch (o) {
    case Outcome::kMoved: return "moved";
    case Outcome::kSameOwner: return "same_owner";
    case Outcome::kLocked: return "refused_locked";
    case Outcome::kNoCandidate: return "refused_no_start";
    case Outcome::kUsedStart: return "refused_used_start";
    case Outcome::kNotConnected: return "refused_not_connected";
    case Outcome::kNoTitleUser: return "refused_no_title_user";
  }
  return "?";
}

struct Decision {
  Outcome outcome;
  unsigned from;
  unsigned to;  // the owner after the decision
  unsigned candidate;        // the title's selected user (kUsers if out of range)
  unsigned start_candidate;  // diagnostic only: the user with the most recent START edge (kUsers if none)
};

// The pure policy (unit-tested in m6_input_test.cpp). Times are milliseconds from any monotonic origin.
class Policy {
 public:
  unsigned Owner() const { return owner_; }
  bool Locked() const { return locked_; }
  bool IsOwner(uint32_t user) const { return user == owner_; }

  void NoteStart(uint32_t user, uint64_t now_ms) {
    if (user >= kUsers) return;
    start_seq_[user] = ++seq_;  // a new authorization; now_ms is kept for diagnostics only
    start_ms_[user] = now_ms;
  }

  // Returns true when this call locked the owner (first commit witness from the owner).
  bool NoteCommitWitness(uint32_t user) {
    if (locked_ || user != owner_) return false;
    locked_ = true;
    return true;
  }

  // The title asked for its sign-in UI. connected[u] says whether guest user u's controller is connected;
  // title_user is the title's own selected user (its save-gate word), or any value >= kUsers if unknown.
  // now_ms is not used by the decision (G6-P80: no recency window).
  Decision OnSigninRequest(const bool (&connected)[kUsers], uint64_t now_ms, uint32_t title_user) {
    (void)now_ms;
    unsigned start_candidate = kUsers;
    uint64_t best = 0;
    for (unsigned u = 0; u < kUsers; ++u)
      if (start_seq_[u] > best) best = start_seq_[u], start_candidate = u;
    const unsigned from = owner_;
    const unsigned candidate = title_user < kUsers ? unsigned(title_user) : kUsers;
    if (locked_) return {Outcome::kLocked, from, owner_, candidate, start_candidate};
    if (candidate == kUsers) return {Outcome::kNoTitleUser, from, owner_, candidate, start_candidate};
    if (candidate == owner_) return {Outcome::kSameOwner, from, owner_, candidate, start_candidate};  // no move
    if (start_seq_[candidate] == 0) return {Outcome::kNoCandidate, from, owner_, candidate, start_candidate};
    if (start_seq_[candidate] <= used_seq_[candidate])
      return {Outcome::kUsedStart, from, owner_, candidate, start_candidate};
    used_seq_[candidate] = start_seq_[candidate];  // this START is used by this decision, whatever it is
    if (!connected[candidate]) return {Outcome::kNotConnected, from, owner_, candidate, start_candidate};
    owner_ = candidate;  // the only move to a new user: the profile is never on two users
    return {Outcome::kMoved, from, owner_, candidate, start_candidate};
  }

  // A guest user's controller was unplugged. Returns true when this rolled a pending (not locked) handoff back to
  // kHome; the caller then broadcasts XN_SYS_SIGNINCHANGED. A locked owner, a non-owner or kHome never moves.
  // G6-P80: any user's unplug also voids that user's unused START authorization.
  bool OnDisconnect(uint32_t user) {
    if (user >= kUsers) return false;
    used_seq_[user] = start_seq_[user];  // a START made before an unplug never authorizes a later request
    if (locked_ || user != owner_ || owner_ == kHome) return false;
    owner_ = kHome;  // rollback to the boot state, never to another controller
    return true;
  }

 private:
  unsigned owner_ = 0;
  bool locked_ = false;
  uint64_t seq_ = 0;
  uint64_t start_seq_[kUsers] = {};
  uint64_t start_ms_[kUsers] = {};
  uint64_t used_seq_[kUsers] = {};  // the START sequence each user's last decision or unplug used up
};

// ---- Runtime wrappers (one process-wide policy) ----

inline uint64_t NowMs() {
  return uint64_t(std::chrono::duration_cast<std::chrono::milliseconds>(
                      std::chrono::steady_clock::now().time_since_epoch())
                      .count());
}

inline bool Enabled() {
  static const bool enabled =
      ParseEnable(std::getenv("R3HD_NONINTRUSIVE"), std::getenv("R3HD_TEST_PROFILE_HANDOFF"));
  return enabled;
}

struct Global {
  std::mutex lock;
  Policy policy;
  std::atomic<unsigned> owner{0};  // mirror of policy.Owner() for lock-free reads
};
inline Global& State() {
  static Global g;
  return g;
}

// The guest user that holds the profile. 0 whenever the prototype is disabled.
inline unsigned Owner() { return Enabled() ? State().owner.load(std::memory_order_acquire) : 0u; }
inline bool IsOwner(uint32_t user) { return user == Owner(); }

inline void NoteStart(uint32_t user, uint64_t now_ms) {
  if (!Enabled()) return;
  std::lock_guard<std::mutex> guard(State().lock);
  State().policy.NoteStart(user, now_ms);
}

inline bool NoteCommitWitness(uint32_t user) {
  if (!Enabled()) return false;
  std::lock_guard<std::mutex> guard(State().lock);
  return State().policy.NoteCommitWitness(user);
}

inline Decision OnSigninRequest(const bool (&connected)[kUsers], uint64_t now_ms, uint32_t title_user) {
  std::lock_guard<std::mutex> guard(State().lock);
  Decision d = State().policy.OnSigninRequest(connected, now_ms, title_user);
  State().owner.store(State().policy.Owner(), std::memory_order_release);
  return d;
}

// G6-P80: called when a guest user's controller is unplugged (test source). True when it rolled the profile back.
inline bool OnDisconnect(uint32_t user) {
  if (!Enabled()) return false;
  std::lock_guard<std::mutex> guard(State().lock);
  const bool rolled = State().policy.OnDisconnect(user);
  State().owner.store(State().policy.Owner(), std::memory_order_release);
  return rolled;
}

}  // namespace g6p79

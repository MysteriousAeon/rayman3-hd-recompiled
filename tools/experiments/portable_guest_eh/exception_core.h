// Synthetic exception emitter semantics. Experimental; not used by the runtime.
#pragma once

#include "ppc_adapter.h"

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <functional>
#include <memory>
#include <optional>
#include <limits>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>

namespace pgeh {

struct OwnerId {
  uint64_t thread = 0;
  uint64_t invocation = 0;
  friend bool operator==(OwnerId, OwnerId) = default;
};

struct GuestRecord {
  uint32_t code = 0;
  uint32_t flags = 0;
  uint32_t address = 0;
};
inline constexpr uint32_t kNoncontinuable = 1;

struct Unsupported final : std::exception {
  const char* what() const noexcept override { return "unsupported synthetic guest continuation"; }
};
struct Unhandled final : std::exception {
  const char* what() const noexcept override { return "unhandled synthetic guest exception"; }
};

class Owner;
struct Checkpoint {
  OwnerId owner;
  uint32_t continuation;
  Adapter::FullSnapshot state;
};

struct Transfer final {
  enum class Kind { handler, unwind, checkpoint } kind;
  OwnerId owner;
  uint32_t target;
  uint32_t value;
  size_t scope_limit;
  // PPCContext requires 64-byte alignment; exception storage need not provide it.
  // A shared immutable copy owns aligned state through token copies and rethrows.
  std::shared_ptr<const Checkpoint> checkpoint;
};
static_assert(alignof(Transfer) <= 16 && alignof(Transfer) <= alignof(std::max_align_t),
              "Thrown transport must not embed over-aligned guest state");
static_assert(std::is_nothrow_copy_constructible_v<Transfer> &&
              std::is_nothrow_destructible_v<Transfer>);

using Filter = std::function<int(Adapter::State&, const GuestRecord&, uint32_t establisher)>;
using Finally = std::function<void(Adapter::State&, uint32_t establisher)>;
struct Scope {
  uint32_t begin;
  uint32_t end;
  uint32_t target;  // zero = finally; otherwise an inline owner label.
  Filter filter;
  Finally cleanup;
};

inline thread_local bool in_funclet = false;
struct FuncletGuard {
  FuncletGuard() {
    if (in_funclet) throw Unsupported{};
    in_funclet = true;
  }
  ~FuncletGuard() { in_funclet = false; }
  FuncletGuard(const FuncletGuard&) = delete;
};

class Owner final {
 public:
  Owner(Adapter::State& state, std::vector<Scope> scopes)
      : state_(state), parent_(top_), scopes_(std::move(scopes)),
        establisher_(Adapter::stack(state)), id_{thread_id(), next_invocation()} {
    if (in_funclet) throw Unsupported{};
    if (parent_ && &parent_->state_ != &state_) throw Unsupported{};
    top_ = this;
  }
  ~Owner() {
    if (top_ != this) std::terminate();
    top_ = parent_;
  }  // Registration only. Guest cleanup is always explicit.
  Owner(const Owner&) = delete;
  Owner& operator=(const Owner&) = delete;

  OwnerId id() const { return id_; }
  uint32_t establisher() const { return establisher_; }
  uint32_t pc() const { return pc_; }
  void set_pc(uint32_t pc) { pc_ = pc; }
  bool in_call() const { return in_call_; }
  Owner* parent() const { return parent_; }
  void restore_call_state(bool value) { in_call_ = value; }
  void before_call() { owner_snapshot_ = Adapter::capture_owner(state_); in_call_ = true; }
  void after_call() { in_call_ = false; }

  void declare_label(uint32_t label) {
    if (label == 0) throw Unsupported{}; // zero is the normal-return sentinel.
    labels_.push_back(label);
  }
  bool has_label(uint32_t label) const {
    for (uint32_t candidate : labels_)
      if (candidate == label) return true;
    return false;
  }
  const std::vector<Scope>& scopes() const { return scopes_; }
  Adapter::State& state() { return state_; }

  void restore_owner() {
    if (!in_call_) return;
    Adapter::restore_owner(state_, owner_snapshot_);
    in_call_ = false;
  }

  static Owner* find(OwnerId id) {
    if (id.thread != thread_id()) return nullptr;
    for (Owner* p = top_; p; p = p->parent_)
      if (p->id_ == id) return p;
    return nullptr;
  }
  static Owner* top() { return top_; }

 private:
  static uint64_t thread_id() {
    thread_local const uint64_t id = next_thread_.fetch_add(1, std::memory_order_relaxed);
    return id;
  }
  static uint64_t next_invocation() {
    const uint64_t id = next_owner_.fetch_add(1, std::memory_order_relaxed);
    if (id == 0 || id == std::numeric_limits<uint64_t>::max()) std::terminate();
    return id;
  }
  inline static std::atomic<uint64_t> next_thread_{1};
  inline static std::atomic<uint64_t> next_owner_{1};
  inline static thread_local Owner* top_ = nullptr;

  Adapter::State& state_;
  Owner* parent_;
  std::vector<Scope> scopes_;
  uint32_t establisher_;
  uint32_t pc_ = 0;
  OwnerId id_;
  bool in_call_ = false;
  Adapter::OwnerSnapshot owner_snapshot_{};
  std::vector<uint32_t> labels_;
  friend void raise(const GuestRecord&);
  friend int call_filter(Owner&, const Scope&, const GuestRecord&);
  friend void run_cleanup(Owner&, const Transfer*);
  friend uint32_t region(Owner&, const std::function<void()>&);
  friend void request_unwind(OwnerId, uint32_t, uint32_t);
  friend Checkpoint save_checkpoint(Owner&, uint32_t);
  friend void resume_checkpoint(const Checkpoint&, uint32_t);
};

inline bool active(const Scope& scope, uint32_t pc) {
  return pc >= scope.begin && pc < scope.end;
}

inline int call_filter(Owner& owner, const Scope& scope, const GuestRecord& record) {
  auto& state = owner.state_;
  const auto live = Adapter::capture_full(state);
  const bool was_in_call = owner.in_call_;
  try {
    owner.restore_owner();
    const uint32_t live_sp = Adapter::stack(live.state);
    Adapter::set_stack(state, (live_sp - 0x400u) & ~0xFu);
    // The callback receives the synthetic record separately; r3 is a test-only
    // guest pointer token, never an address that can be dereferenced.
    Adapter::set_args(state, 0x70u, owner.establisher_, owner.establisher_);
    if (!scope.filter) throw Unsupported{};
    int disposition;
    {
      FuncletGuard guard;
      disposition = scope.filter(state, record, owner.establisher_);
    }
    Adapter::restore_full(state, live);
    owner.restore_call_state(was_in_call);
    return disposition;
  } catch (...) {
    Adapter::restore_full(state, live);
    owner.restore_call_state(was_in_call);
    throw;
  }
}

inline void raise(const GuestRecord& record) {
  if (in_funclet) throw Unsupported{};
  for (Owner* owner = Owner::top(); owner; owner = owner->parent()) {
    for (size_t i = 0; i < owner->scopes_.size(); ++i) {
      const Scope& scope = owner->scopes_[i];
      if (!scope.target || !active(scope, owner->pc())) continue;
      const int disposition = call_filter(*owner, scope, record);  // Live-frame search.
      if (disposition < 0) {
        if (record.flags & kNoncontinuable) break;
        return;  // Continue execution at the raising call site, without C++ unwind.
      }
      if (disposition == 0) continue;
      if (!owner->has_label(scope.target)) throw Unsupported{};
      throw Transfer{Transfer::Kind::handler, owner->id_, scope.target, 0, i, nullptr};
    }
  }
  throw Unhandled{};
}

inline void request_unwind(OwnerId destination_owner, uint32_t destination,
                           uint32_t return_value) {
  if (in_funclet) throw Unsupported{};
  Owner* owner = Owner::find(destination_owner);
  if (!owner || !owner->has_label(destination)) throw Unsupported{};
  throw Transfer{Transfer::Kind::unwind, destination_owner, destination, return_value,
                 owner->scopes_.size(), nullptr};
}

inline Checkpoint save_checkpoint(Owner& owner, uint32_t continuation) {
  if (in_funclet) throw Unsupported{};
  if (Owner::find(owner.id_) != &owner || Owner::top() != &owner ||
      !owner.has_label(continuation)) throw Unsupported{};
  return {owner.id_, continuation, Adapter::capture_full(owner.state_)};
}

inline void resume_checkpoint(const Checkpoint& checkpoint, uint32_t value) {
  if (in_funclet) throw Unsupported{};
  Owner* owner = Owner::find(checkpoint.owner);
  if (!owner || !owner->has_label(checkpoint.continuation)) throw Unsupported{};
  throw Transfer{Transfer::Kind::checkpoint, checkpoint.owner, checkpoint.continuation,
                 value ? value : 1u, owner->scopes_.size(),
                 std::make_shared<const Checkpoint>(checkpoint)};
}

inline void run_cleanup(Owner& owner, const Transfer* transfer) {
  size_t limit = owner.scopes_.size();
  const bool target_owner = transfer && transfer->owner == owner.id_;
  if (target_owner && transfer->kind == Transfer::Kind::handler)
    limit = transfer->scope_limit;
  for (size_t i = 0; i < limit; ++i) {
    const Scope& scope = owner.scopes_[i];
    if (scope.target || !active(scope, owner.pc_) || !scope.cleanup) continue;
    if (target_owner && transfer->kind != Transfer::Kind::handler &&
        active(scope, transfer->target))
      continue;  // Retain a scope containing the unwind/checkpoint destination.
    const auto live = Adapter::capture_full(owner.state_);
    const bool was_in_call = owner.in_call_;
    try {
      owner.restore_owner();
      const uint32_t owner_sp = Adapter::stack(owner.state_);
      Adapter::set_stack(owner.state_, (owner_sp - 0x400u) & ~0xFu);
      Adapter::set_args(owner.state_, 1u, owner.establisher_, owner.establisher_);
      {
        FuncletGuard guard;
        scope.cleanup(owner.state_, owner.establisher_);
      }
      Adapter::restore_full(owner.state_, live);
      owner.restore_call_state(was_in_call);
    } catch (...) {
      Adapter::restore_full(owner.state_, live);
      owner.restore_call_state(was_in_call);
      throw;
    }
  }
}

inline void validate_transfer(const Transfer& transfer) {
  Owner* target = Owner::find(transfer.owner);
  if (!target || !target->has_label(transfer.target)) throw Unsupported{};
  switch (transfer.kind) {
    case Transfer::Kind::handler:
      if (transfer.checkpoint || transfer.scope_limit >= target->scopes().size())
        throw Unsupported{};
      if (target->scopes()[transfer.scope_limit].target != transfer.target ||
          !active(target->scopes()[transfer.scope_limit], target->pc()))
        throw Unsupported{};
      break;
    case Transfer::Kind::unwind:
      if (transfer.checkpoint || transfer.scope_limit != target->scopes().size())
        throw Unsupported{};
      break;
    case Transfer::Kind::checkpoint:
      if (!transfer.checkpoint || transfer.scope_limit != target->scopes().size() ||
          transfer.checkpoint->owner != transfer.owner ||
          transfer.checkpoint->continuation != transfer.target)
        throw Unsupported{};
      break;
    default:
      throw Unsupported{};
  }
}

// The generated owner catches at each frame, runs guest cleanup explicitly,
// rethrows through intervening owners, and returns a label in its own switch.
inline uint32_t region(Owner& owner, const std::function<void()>& body) {
  if (Owner::find(owner.id()) != &owner || Owner::top() != &owner) throw Unsupported{};
  std::optional<Transfer> accepted;
  try {
    body();
    owner.after_call();
    return 0;
  } catch (const Transfer& transfer) {
    validate_transfer(transfer);  // Reject forged/stale tokens before any cleanup.
    run_cleanup(owner, &transfer);
    if (transfer.owner != owner.id_) throw;
    accepted = transfer;
  } catch (...) {
    run_cleanup(owner, nullptr);
    throw;
  }
  // Win64 catch exit may restore the throw site's FP control word. Apply the
  // destination state only after the host exception handler has finished.
  owner.restore_owner();
  if (accepted->kind == Transfer::Kind::checkpoint)
    Adapter::restore_full(owner.state_, accepted->checkpoint->state);
  if (accepted->kind != Transfer::Kind::handler) Adapter::set_return(owner.state_, accepted->value);
  return accepted->target;
}

}  // namespace pgeh

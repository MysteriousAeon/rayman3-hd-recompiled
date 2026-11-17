// Isolated checked-read / guest-record bridge. Not part of the runtime.
#pragma once

#include "../linux_guest_fault/record_contract.h"
#include "../portable_guest_eh/exception_core.h"

#include <algorithm>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>
#include <limits>
#include <span>
#include <utility>
#include <vector>

namespace lgi {

inline constexpr uint32_t kGuestAccessViolation = 0xc0000005u;

// The caller guarantees a stable mapping and a writable scratch reservation
// throughout delivery: the whole [scratch_sp, scratch_sp + 0x400) interval.
// Data pages outside that reservation may be protected for checked reads.
// Native callers supply the actual OS page granularity. Mapping/protection and
// callback storage must remain stable; callbacks must not unmap/protect scratch.
// Bounds alone do not prove host page permissions. Tests use synthetic backing;
// the native fixture supplies a writable stack interval in an mmap arena.
struct GuestArena {
  std::span<uint8_t> bytes;  // Guest addresses are zero-based offsets in bytes.
  uint32_t stack_low = 0;
  uint32_t stack_high = 0;
  bool stable_writable_backing = false;
  size_t page_size = 4096;
  uintptr_t admitted_read_site = 0;
};

enum class Operation { read, write, atomic, execute };
struct AccessRequest {
  uint32_t effective_address = 0;
  uint32_t pc = 0;
  uint32_t width = 4;
  Operation operation = Operation::read;
};

enum class ConsumerKind { pass, mmio, watch_repair, reject };
struct ConsumerResult {
  ConsumerKind kind = ConsumerKind::pass;
  uint32_t guest_value = 0;
  static ConsumerResult Pass() { return {}; }
  static ConsumerResult Mmio(uint32_t value) { return {ConsumerKind::mmio, value}; }
  static ConsumerResult WatchRepair() { return {ConsumerKind::watch_repair, 0}; }
  static ConsumerResult Reject() { return {ConsumerKind::reject, 0}; }
};
using Consumer = std::function<ConsumerResult(const AccessRequest&, uintptr_t host_address)>;

enum class BackendKind { success, fault, reject };
struct BackendResult {
  BackendKind kind = BackendKind::reject;
  uint32_t raw_host_value = 0;
  uintptr_t host_address = 0;
  uintptr_t instruction = 0;
  bool admitted_guest_site = false;
  static BackendResult Success(uint32_t raw) {
    return {BackendKind::success, raw, 0, 0, false};
  }
  static BackendResult Fault(uintptr_t address, uintptr_t site, bool admitted) {
    return {BackendKind::fault, 0, address, site, admitted};
  }
  static BackendResult Reject() { return {}; }
};
using Backend = std::function<BackendResult(const void* host_address)>;

enum class AccessStatus {
  success,
  mmio_consumed,
  watch_repair_required,
  guest_fault,
  rejected,
  unsupported,
};

struct Delivery {
  const GuestArena* arena;
  uint32_t live_sp;
  lgf::Record record;
};
inline thread_local const Delivery* current_delivery = nullptr;
inline thread_local bool access_dispatch_active = false;
inline thread_local bool consumer_callback_active = false;
inline thread_local bool backend_callback_active = false;

inline uint32_t scratch_sp(uint32_t live_sp) {
  return (live_sp - 0x400u) & ~0xfu;
}

// Match lgf::push's complete reservation check before establishing delivery.
// This makes rejected inputs fail before a filter or any record write occurs.
inline bool can_serialize(const GuestArena& arena, uint32_t live_sp,
                          const lgf::Record& record) {
  if (!arena.stable_writable_backing || record.code != kGuestAccessViolation ||
      record.flags != 0 || record.chain != 0 || record.count != 2 ||
      record.info[0] != 0 || record.count > record.info.size() ||
      record.pc == 0 || (record.pc & 3u) != 0 ||
      (record.info[1] & 3u) != 0 || arena.page_size < 4 ||
      !std::has_single_bit(arena.page_size) ||
      uint64_t(record.info[1]) > arena.bytes.size() ||
      arena.bytes.size() - uint64_t(record.info[1]) < 4 ||
      uint64_t(record.info[1]) % arena.page_size > arena.page_size - 4 ||
      arena.stack_low > arena.stack_high || live_sp < 0x400u ||
      live_sp > arena.stack_high || arena.bytes.size() > UINT32_MAX)
    return false;
  const uint32_t sp = scratch_sp(live_sp);
  if (sp < arena.stack_low || sp > arena.stack_high ||
      arena.stack_high - sp < 0x400u || sp > arena.bytes.size() ||
      arena.bytes.size() - sp < 0x400u)
    return false;
  const uint64_t record_pointer = uint64_t(sp) + 0x80u;
  const uint64_t pointers = uint64_t(sp) + 0x70u;
  return record_pointer + 80u <= uint64_t(arena.stack_high) + 1u &&
         pointers + 8u <= uint64_t(arena.stack_high) + 1u &&
         record_pointer + 80u <= arena.bytes.size() &&
         pointers + 8u <= arena.bytes.size();
}

inline bool same_core_record(const Delivery& delivery,
                             const pgeh::GuestRecord& raised) {
  return raised.code == delivery.record.code &&
         raised.flags == delivery.record.flags &&
         raised.address == delivery.record.pc;
}

inline pgeh::Filter wrap_filter(pgeh::Filter filter) {
  if (!filter) throw pgeh::Unsupported{};
  return [filter = std::move(filter)](pgeh::Adapter::State& state,
                                     const pgeh::GuestRecord& raised,
                                     uint32_t establisher) {
    const Delivery* delivery = current_delivery;
    if (!delivery || !delivery->arena ||
        !same_core_record(*delivery, raised) ||
        !can_serialize(*delivery->arena, delivery->live_sp,
                       delivery->record))
      throw pgeh::Unsupported{};

    const uint32_t expected_scratch = scratch_sp(delivery->live_sp);
    if (state.r1.u32 != expected_scratch) throw pgeh::Unsupported{};
    uint32_t scratch = 0, pointers = 0;
    if (!lgf::push(delivery->arena->bytes, delivery->live_sp,
                   delivery->arena->stack_low, delivery->arena->stack_high,
                   delivery->record, scratch, pointers))
      throw pgeh::Unsupported{};

    // The core has already selected scratch r1 and restored the owner snapshot.
    // r4/r12 retain the M4 owner establisher set by exception_core.h.
    if (scratch != expected_scratch) throw pgeh::Unsupported{};
    state.r3.u64 = pointers;
    return filter(state, raised, establisher);
  };
}

inline void deliver(GuestArena arena, uint32_t live_sp,
                    const lgf::Record& record) {
  // A nested serialization is rejected before changing the active delivery.
  pgeh::Owner* const owner = pgeh::Owner::top();
  if (pgeh::in_funclet || current_delivery || consumer_callback_active ||
      backend_callback_active || !owner ||
      owner->state().r1.u32 != live_sp ||
      !can_serialize(arena, live_sp, record))
    throw pgeh::Unsupported{};
  Delivery delivery{&arena, live_sp, record};
  struct DeliveryGuard {
    explicit DeliveryGuard(Delivery& value) { current_delivery = &value; }
    ~DeliveryGuard() { current_delivery = nullptr; }
    DeliveryGuard(const DeliveryGuard&) = delete;
  } guard(delivery);
  pgeh::raise({record.code, record.flags, record.pc});
}

inline uint32_t host_to_guest_be32(uint32_t raw) {
  if constexpr (std::endian::native == std::endian::little) {
    return ((raw & 0x000000ffu) << 24) | ((raw & 0x0000ff00u) << 8) |
           ((raw & 0x00ff0000u) >> 8) | ((raw & 0xff000000u) >> 24);
  }
  return raw;
}

// Ordinary-code metadata predicate, separate from signal capture and serialization.
inline bool admits_fault(const GuestArena& arena, uintptr_t expected_host,
                         const BackendResult& result) {
  return result.kind == BackendKind::fault && result.admitted_guest_site &&
         arena.admitted_read_site && result.host_address == expected_host &&
         result.instruction == arena.admitted_read_site;
}

inline AccessStatus checked_load32(GuestArena arena,
                                  const AccessRequest request,
                                  uint32_t live_sp,
                                  std::span<const Consumer> consumers,
                                  const Backend& backend,
                                  uint32_t& out_guest_value) {
  if (pgeh::in_funclet || access_dispatch_active || current_delivery)
    return AccessStatus::unsupported;
  if (request.operation != Operation::read || request.width != 4 ||
      (request.effective_address & 3u) != 0 || arena.page_size < 4 ||
      !std::has_single_bit(arena.page_size) ||
      request.pc == 0 || (request.pc & 3u) != 0 || !backend)
    return AccessStatus::unsupported;
  const uint64_t ea = request.effective_address;
  if (ea > arena.bytes.size() || arena.bytes.size() - ea < request.width ||
      ea % arena.page_size > arena.page_size - request.width)
    return AccessStatus::rejected;
  const uintptr_t host_address =
      reinterpret_cast<uintptr_t>(arena.bytes.data() + request.effective_address);
  if ((host_address & 3u) != 0 ||
      host_address % arena.page_size > arena.page_size - request.width)
    return AccessStatus::unsupported;
  struct AccessGuard {
    AccessGuard() { access_dispatch_active = true; }
    ~AccessGuard() { access_dispatch_active = false; }
    AccessGuard(const AccessGuard&) = delete;
  } guard;

  for (const Consumer& consumer : consumers) {
    if (!consumer) return AccessStatus::rejected;
    struct ConsumerGuard {
      ConsumerGuard() { consumer_callback_active = true; }
      ~ConsumerGuard() { consumer_callback_active = false; }
      ConsumerGuard(const ConsumerGuard&) = delete;
    } consumer_guard;
    const ConsumerResult consumed = consumer(request, host_address);
    switch (consumed.kind) {
      case ConsumerKind::pass:
        break;
      case ConsumerKind::mmio:
        out_guest_value = consumed.guest_value;
        return AccessStatus::mmio_consumed;
      case ConsumerKind::watch_repair:
        return AccessStatus::watch_repair_required;
      case ConsumerKind::reject:
      default:
        return AccessStatus::rejected;
    }
  }

  BackendResult result;
  {
    struct BackendGuard {
      BackendGuard() { backend_callback_active = true; }
      ~BackendGuard() { backend_callback_active = false; }
      BackendGuard(const BackendGuard&) = delete;
    } backend_guard;
    result = backend(
        static_cast<const void*>(arena.bytes.data() + request.effective_address));
  }
  if (result.kind == BackendKind::success) {
    out_guest_value = host_to_guest_be32(result.raw_host_value);
    return AccessStatus::success;
  }
  if (!admits_fault(arena, host_address, result))
    return AccessStatus::rejected;

  lgf::Record record{};
  record.code = kGuestAccessViolation;
  record.pc = request.pc;
  record.count = 2;
  record.info[0] = 0;  // M4 AccessViolationOperation::kRead.
  record.info[1] = request.effective_address;
  deliver(arena, live_sp, record);
  // A negative filter returns here. Retry is a new explicit helper call.
  return AccessStatus::guest_fault;
}

}  // namespace lgi

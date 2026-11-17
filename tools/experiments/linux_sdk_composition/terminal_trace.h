// Fixture-only ordinary-code witness. Never include/call this in transport.c.
#pragma once
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string_view>

namespace lsc_gate {
enum class Mode { callback, repair, unhandled };
struct InjectedInvalidation final {};
struct Facts {
  unsigned attempts{}, faults{}, callbacks{}, invalidations{}, filters{}, caught{};
  uintptr_t address{};
};
inline const char* name(Mode mode) {
  switch (mode) {
    case Mode::callback: return "callback-failure";
    case Mode::repair: return "repair-failure";
    case Mode::unhandled: return "unhandled";
  }
  return "invalid";
}
inline bool valid_token(const char* token) {
  if (!token || std::strlen(token) != 32) return false;
  for (unsigned i = 0; i < 32; ++i)
    if (!((token[i] >= '0' && token[i] <= '9') || (token[i] >= 'a' && token[i] <= 'f')))
      return false;
  return true;
}
inline bool expected(Mode mode, unsigned stage, std::string_view phase, const Facts& f) {
  if (stage > 2 || !f.address || (f.address & 3) || f.callbacks != 1) return false;
  const bool last = stage == 2;
  if (last && phase != "terminal") return false;
  switch (mode) {
    case Mode::callback:
      return f.attempts == 1 && f.faults == 1 && f.invalidations == 1 && f.filters == 0 &&
          f.caught == (stage == 0 ? 0u : 1u) &&
          (last || phase == (stage == 0 ? "injected" : "caught"));
    case Mode::repair:
      return f.attempts == (stage == 0 ? 1u : 2u) && f.faults == f.attempts &&
          f.invalidations == 0 && f.filters == 0 && f.caught == 0 &&
          (last || phase == (stage == 0 ? "claimed" : "retry_fault"));
    case Mode::unhandled:
      return f.attempts == 1 && f.faults == 1 && f.invalidations == 0 && f.filters == 1 &&
          f.caught == (stage == 0 ? 0u : 1u) &&
          (last || phase == (stage == 0 ? "filter_search" : "caught"));
  }
  return false;
}
class Witness final {
 public:
  Witness(Mode mode, const char* token, unsigned callback_base, unsigned invalidation_base)
      : mode_(mode), callback_base_(callback_base), invalidation_base_(invalidation_base) {
    if (valid_token(token)) std::memcpy(token_.data(), token, 33);
  }
  Facts facts{};
  bool consumers(unsigned callbacks, unsigned invalidations) {
    if (callbacks < callback_base_ || invalidations < invalidation_base_) return false;
    facts.callbacks = callbacks - callback_base_;
    facts.invalidations = invalidations - invalidation_base_;
    return true;
  }
  bool emit(std::string_view phase, std::FILE* stream = stderr) {
    if (!valid_token(token_.data()) || !expected(mode_, stage_, phase, facts) ||
        (address_ && address_ != facts.address)) return false;
    std::array<char, 320> line{};
    const int length = std::snprintf(line.data(), line.size(),
        "LSC_GATE_V1 token=%s mode=%s phase=%.*s attempts=%u faults=%u callbacks=%u "
        "invalidations=%u filters=%u caught=%u address=0x%llx\n",
        token_.data(), name(mode_), static_cast<int>(phase.size()), phase.data(), facts.attempts,
        facts.faults, facts.callbacks, facts.invalidations, facts.filters, facts.caught,
        static_cast<unsigned long long>(facts.address));
    if (length <= 0 || static_cast<size_t>(length) >= line.size() ||
        std::fwrite(line.data(), 1, static_cast<size_t>(length), stream) != static_cast<size_t>(length) ||
        std::fflush(stream) != 0) return false;
    address_ = facts.address;
    ++stage_;
    return true;
  }
 private:
  Mode mode_;
  unsigned callback_base_, invalidation_base_, stage_{};
  uintptr_t address_{};
  std::array<char, 33> token_{};
};
}  // namespace lsc_gate

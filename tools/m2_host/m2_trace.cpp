#include "m2_trace.h"
#include <rex/logging.h>
#include <rex/m24_event_trace.h>
#include <spdlog/sinks/base_sink.h>
#include <mutex>
#include <windows.h>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <cstdlib>
// M8: last-chance crash record. Optional so the M2..M6 build scripts keep working unchanged.
#if __has_include("m8_crash_report.h")
#include "m8_crash_report.h"
#define R3HD_M8_CRASH_REPORT 1
#endif
thread_local const char* m2_current_function = nullptr;
thread_local PPCContext* m2_current_context = nullptr;
static std::atomic<bool> entered{false};
static std::atomic<bool> bink_entered{false};
static thread_local bool object_trace = false;
static thread_local unsigned object_trace_count = 0;
// M11 (D-036): this runs at the entry of every translated function. The two stores keep the fault and crash
// records ("last entered function", guest lr / sp) and are all that a normal run needs. The M2 / M3 research
// probes below (string compares, strtoul and a probe table per call) took about three quarters of the title's
// main thread; they now run only with R3HD_M2_PROBES set, which m2_summarize.py / m3_summarize.py runs need.
static const bool m2_probes = std::getenv("R3HD_M2_PROBES") != nullptr;
void M2Enter(const char* name, PPCContext& ctx) {
  m2_current_function = name;
  m2_current_context = &ctx;
  if (!m2_probes) return;
  if (!std::strcmp(name, "__imp__sub_823E4AC8")) object_trace = true;
  if (object_trace && object_trace_count++ < 128)
    REXLOG_INFO("M2 object_call function={} sp={:08X} r31={:08X} lr={:08X}", name, ctx.r1.u32, ctx.r31.u32, unsigned(ctx.lr));
  if ((!std::strcmp(name, "__imp__xstart") || !std::strcmp(name, "xstart")) && !entered.exchange(true)) {
    REXLOG_INFO("M2 guest_entry_executed pc=820E13F8 lr={:08X} sp={:08X}", ctx.lr, ctx.r1.u32);
  }
  auto length = std::strlen(name);
  if (length >= 8) {
    auto address = std::strtoul(name + length - 8, nullptr, 16);
    if (address >= 0x8280C600 && address < 0x828225E4 && !bink_entered.exchange(true))
      REXLOG_INFO("M2 bink_code_entered function={:08X}", unsigned(address));
    // M3 shader-provenance / exception probes: entry counts only (first and power-of-two hits).
    static const uint32_t probes[] = {
        0x822019E0, 0x822065D8,              // reference *ShaderCache_xenon.bin names
        0x82204830,                          // references the .psh/.vsh/.hlsl source-name table
        0x822308E0, 0x822309F0,              // format "0x%016I64x.hlsl"
        0x82230A58, 0x82230C18,              // reference "ps_3_0" / "vs_3_0"
        0x82366910, 0x823681C0,              // D3DX compile front end (profiles, CompareBackEnds)
        0x823C2D08, 0x82550FF0,              // shader assembler profile check / ucode driver
        0x826B8650, 0x826B8A30,              // _CxxThrowException / C++ frame handler
        0x826BF880, 0x826CAB60,              // RtlUnwind wrappers (nonlocal/local unwind)
        0x8249E3C0};                         // XMACreateContext caller
    static std::atomic<unsigned long long> probe_counts[sizeof(probes) / sizeof(probes[0])];
    for (size_t i = 0; i < sizeof(probes) / sizeof(probes[0]); ++i) {
      if (address != probes[i]) continue;
      auto n = ++probe_counts[i];
      if ((n & (n - 1)) == 0)
        REXLOG_INFO("M3 probe function={:08X} count={} lr={:08X}", unsigned(address), n, unsigned(ctx.lr));
    }
  }
}
static LONG CALLBACK M2Fault(EXCEPTION_POINTERS* fault) {
  // An observational first-chance record, never consumes or changes an exception.
  auto* ctx = m2_current_context;
  char line[512];
  int n = std::snprintf(line, sizeof(line), "M2 exception code=%08lX host_pc=%p last_entered_function=%s lr=%08X indirect=%08X sp=%08X fault_address=%p\n",
    fault->ExceptionRecord->ExceptionCode, fault->ExceptionRecord->ExceptionAddress,
    m2_current_function ? m2_current_function : "host", ctx ? unsigned(ctx->lr) : 0,
    ctx ? ctx->last_indirect_target : 0, ctx ? ctx->r1.u32 : 0,
    fault->ExceptionRecord->NumberParameters >= 2 ? reinterpret_cast<void*>(fault->ExceptionRecord->ExceptionInformation[1]) : nullptr);
  FILE* file = std::fopen("m2_faults.log", "a");
  if (file) {
    std::fwrite(line, 1, n, file);
    HMODULE fault_module = nullptr;
    char fault_path[MAX_PATH] = {};
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                      reinterpret_cast<LPCSTR>(fault->ExceptionRecord->ExceptionAddress), &fault_module);
    if (fault_module) GetModuleFileNameA(fault_module, fault_path, MAX_PATH);
    std::fprintf(file, "M2 exception_location module=%s offset=%llX\n", fault_path,
      static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(fault->ExceptionRecord->ExceptionAddress) - reinterpret_cast<uintptr_t>(fault_module)));
    void* frames[32];
    auto count = CaptureStackBackTrace(0, 32, frames, nullptr);
    for (unsigned i = 0; i < count; ++i) {
      HMODULE module = nullptr;
      char path[MAX_PATH] = {};
      GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                        reinterpret_cast<LPCSTR>(frames[i]), &module);
      if (module) GetModuleFileNameA(module, path, MAX_PATH);
      std::fprintf(file, "M2 stack %u module=%s offset=%llX\n", i, path,
                   static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(frames[i]) - reinterpret_cast<uintptr_t>(module)));
    }
    std::fclose(file);
  }
  return EXCEPTION_CONTINUE_SEARCH;
}
class M2FatalSink : public spdlog::sinks::base_sink<std::mutex> {
  void sink_it_(const spdlog::details::log_msg& msg) override {
    if (msg.level != spdlog::level::critical) return;
    EXCEPTION_RECORD record{};
    record.ExceptionCode = 0xDEADC0DE; // Observer record for a fatal log, not a raised exception.
    EXCEPTION_POINTERS pointers{&record, nullptr};
    M2Fault(&pointers);
  }
  void flush_() override {}
};
#ifdef R3HD_M8_CRASH_REPORT
static int M8Describe(char* out, int size) {
  // Runs on the faulting thread, so the observer's thread-local guest context is the relevant one.
  auto* ctx = m2_current_context;
  return std::snprintf(out, size, "last_entered_function=%s lr=%08X indirect=%08X sp=%08X\n",
                       m2_current_function ? m2_current_function : "host", ctx ? unsigned(ctx->lr) : 0,
                       ctx ? ctx->last_indirect_target : 0, ctx ? ctx->r1.u32 : 0);
}
#endif
void M2InstallCrashHandler() {
  AddVectoredExceptionHandler(1, M2Fault);
  rex::AddSink(std::make_shared<M2FatalSink>());
#ifdef R3HD_M8_CRASH_REPORT
  m8crash::Install(M8Describe);
#endif
}
static void M2Object(const char* site, PPCRegister& object, PPCRegister& result, PPCRegister& stack) {
  REXLOG_INFO("M2 object_site={} object={:08X} r3={:08X} sp={:08X}", site, object.u32, result.u32, stack.u32);
}
void M2ObjectCallA(PPCRegister& r31, PPCRegister& r3, PPCRegister& r1) { M2Object("823E4BE8", r31, r3, r1); }
void M2ObjectCallB(PPCRegister& r31, PPCRegister& r3, PPCRegister& r1) { M2Object("823E4BF0", r31, r3, r1); }
void M2ObjectRead(PPCRegister& r31, PPCRegister& r3, PPCRegister& r1) { M2Object("823E4BFC", r31, r3, r1); }

// M11 (D-037): the title's D3D library waits for the GPU's command-buffer position in a spin loop built from
// SMT-priority hint no-ops (0x82316B40, called in a loop from 0x8232A0A8). On the console that parks a hardware
// thread; here it kept one host core fully busy for the whole session. This hook runs at the top of each spin
// step. A wait that ends within a few hundred steps is left alone; a longer one sleeps the host thread for a
// fraction of a millisecond per step on a high-resolution timer. The guest loop, its exit condition and its
// timeout are untouched. R3HD_GPU_WAIT=spin restores the unmodified behaviour for comparison.
void M11GpuWaitStep(PPCRegister&) {
  static const bool spin = [] { const char* v = std::getenv("R3HD_GPU_WAIT"); return v && !std::strcmp(v, "spin"); }();
  if (spin) return;
  static const long long gap = [] { LARGE_INTEGER f; QueryPerformanceFrequency(&f); return f.QuadPart / 5000; }();
  static std::atomic<unsigned long long> sleeps{0};
  thread_local long long last = 0;
  thread_local unsigned streak = 0;
  thread_local HANDLE timer = nullptr;
  LARGE_INTEGER now;
  QueryPerformanceCounter(&now);
  // M24: observation only, when R3HD_M24_EVENTS is set: one record per finished wait that slept.
  thread_local long long m24_start = 0, m24_longest = 0;
  thread_local unsigned m24_sleeps = 0;
  if (now.QuadPart - last > gap) {  // more than 200 us since the previous step: a new wait
    if (m24_sleeps && m24ev::Enabled()) {
      const long long per_us = gap / 200;  // counter ticks per microsecond
      const unsigned long long longest = static_cast<unsigned long long>(m24_longest / per_us);
      m24ev::EventAt(m24ev::kGpuWait, m24_start, uint32_t((last - m24_start) / per_us),
                     (m24_sleeps > 0xFFFF ? 0xFFFFu : m24_sleeps) << 16 | uint32_t(longest > 0xFFFF ? 0xFFFF : longest));
    }
    streak = 0;
    m24_start = now.QuadPart;
    m24_sleeps = 0;
    m24_longest = 0;
  }
  last = now.QuadPart;
  if (++streak <= 256) return;
  const long long m24_before = now.QuadPart;
  if (!timer) timer = CreateWaitableTimerExW(nullptr, nullptr, 0x00000002 /* high resolution */, TIMER_ALL_ACCESS);
  if (timer) {
    LARGE_INTEGER due;
    due.QuadPart = -1000;  // 100 us; the system rounds it up to its timer resolution
    SetWaitableTimer(timer, &due, 0, nullptr, nullptr, FALSE);
    WaitForSingleObject(timer, 2);
  } else {
    SwitchToThread();
  }
  QueryPerformanceCounter(&now);
  last = now.QuadPart;
  ++m24_sleeps;
  if (now.QuadPart - m24_before > m24_longest) m24_longest = now.QuadPart - m24_before;
  auto n = ++sleeps;
  if ((n & (n - 1)) == 0) REXLOG_INFO("M11 gpu_wait mode=timed sleeps={}", n);
}

// M18 (D-047): guest-title compatibility correction for the end of revisit mode. Rationale, the decision table
// and the switch are in tools/m18_revisit.h; the hook sites are in config/rexglue/r3hd_compat.toml. This is
// the only place where the host changes what the title does, and R3HD_REVISIT=original turns it off.
#if __has_include("m18_revisit.h")
#include "m18_revisit.h"
#include <rex/ppc/func.h>
#include <rex/system/kernel_state.h>
REX_EXTERN(sub_82104BE0);
namespace {
constexpr uint32_t kM18Flag = 0x82876108, kM18OneShot = 0x82875F28, kM18RevWorld = 0x8287611C,
                   kM18IntWorld = 0x82876120, kM18EndOfGame = 0x82876130, kM18Backup = 0x82BF7440,
                   kM18ScoreWorld = 0x82836F68, kM18ScoreTable = 0x82BF7A00, kM18NameTable = 0x82837004;
uint8_t* M18Base() { return REX_KERNEL_MEMORY()->virtual_membase(); }
uint32_t M18Load(uint32_t address) {
  uint32_t v;
  std::memcpy(&v, M18Base() + address, 4);
  return _byteswap_ulong(v);
}
void M18Store(uint32_t address, uint32_t value) {
  value = _byteswap_ulong(value);
  std::memcpy(M18Base() + address, &value, 4);
}
// Copies a guest string of at most kNameLimit - 1 characters; false when it is longer.
bool M18String(uint32_t address, char* out, bool lower) {
  const char* p = reinterpret_cast<const char*>(M18Base() + address);
  for (std::size_t i = 0; i < m18::kNameLimit; ++i) {
    char c = p[i];
    if (lower && c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    out[i] = c;
    if (!c) return true;
  }
  out[m18::kNameLimit - 1] = 0;
  return false;
}
bool M18Original() {
  static const bool original = m18::OriginalSelected(std::getenv("R3HD_REVISIT"));
  return original;
}
}  // namespace

// At 82102E3C: the title is about to replace the requested level (its lower-case copy is at r1 + 0x50, the name
// it will request at r1 + 0x80) by "endgame". Returns true when the request must go ahead unreplaced.
bool M18RevisitRedirect(PPCRegister& r1) {
  char name[m18::kNameLimit], backup[m18::kNameLimit];
  const bool name_ok = M18String(r1.u32 + 0x50, name, false);
  const bool backup_ok = M18String(kM18Backup, backup, false);
  const uint32_t world = M18Load(kM18RevWorld), end_of_game = M18Load(kM18EndOfGame);
  auto action = m18::Action::kOriginal;
  if (!M18Original() && name_ok)
    action = m18::Decide({name, world, end_of_game, backup_ok ? backup : nullptr});
  const uint32_t interrupted = M18Load(kM18IntWorld);
  PPCContext* ctx = m2_current_context;
  if (action == m18::Action::kReturnToCampaign && (interrupted > 9 || !ctx)) action = m18::Action::kOriginal;
  REXLOG_INFO("M18 revisit redirect name={} revisited_world={} end_of_game={} backup={} mode={} action={}", name, world,
              end_of_game, backup_ok ? backup : "?", M18Original() ? "original" : "fixed", m18::Name(action));
  if (action == m18::Action::kOriginal) return false;
  if (action == m18::Action::kPass) return true;
  // The title's own transition back to the interrupted game (menu branch 82108518 .. 82108578), in its order:
  // clear the flag, let the title settle its score bookkeeping, restore the interrupted world's index and
  // running score, request the interrupted level.
  M18Store(kM18Flag, 0);
  const PPCContext saved = *ctx;
  sub_82104BE0(*ctx, M18Base());
  *ctx = saved;
  M18Store(kM18ScoreWorld, interrupted);
  M18Store(kM18RevWorld, 0);
  const uint32_t score = M18Load(kM18ScoreTable + 4 + interrupted * 8);
  M18Store(0x8287610C, score);
  M18Store(0x82876110, score);
  M18Store(0x82876128, score);
  std::memcpy(M18Base() + r1.u32 + 0x80, backup, std::strlen(backup) + 1);
  return true;
}

// At 82102CC4, hidden test runs only (R3HD_TEST_WORLD_END=1): in revisit mode, turn a request for the revisited
// world's own first level into the request its last level makes, by pointing r3 at the next world's name in the
// title's table. Reads guest memory, writes none.
void M18TestWorldEnd(PPCRegister& r3) {
  static const bool enabled = [] { const char* v = std::getenv("R3HD_TEST_WORLD_END"); return v && !std::strcmp(v, "1"); }();
  if (!enabled || M18Load(kM18Flag) != 1 || M18Load(kM18OneShot) != 0) return;
  const uint32_t world = M18Load(kM18RevWorld);
  char name[m18::kNameLimit];
  if (world < 1 || world > 8 || !M18String(r3.u32, name, true) || std::strcmp(name, m18::kFirstLevels[world - 1])) return;
  const uint32_t next = M18Load(kM18NameTable + 4 + world * 4);
  REXLOG_INFO("M18 test world_end revisited_world={} asked={} substituted={:08X}", world, name, next);
  r3.u64 = next;
}

// E-304: a bounded experiment, deliberately not a player setting. At 8219E9D4
// f13 holds vector2.y; changing that operand lets the original routine set its
// duration/reciprocal and run its own timed close. No command vector, scoring
// field, timer, handle or generated translation is written by this hook.
void ComboTimedCloseTest(PPCRegister& object, PPCRegister& command,
                         PPCRegister& duration, PPCRegister& scalar) {
  static const int mode = [] {
    const char* v = std::getenv("R3HD_TEST_COMBO_CLOSE");
    if (!std::getenv("R3HD_NONINTRUSIVE") || !v) return 0;
    if (!std::strcmp(v, "timed")) return 2;
    if (!std::strcmp(v, "observe")) return 1;
    if (!std::strcmp(v, "countdown")) return 3;
    if (!std::strcmp(v, "delayed-countdown")) return 4;
    return 0;
  }();
  if (!mode) return;
  // Scope the prototype and command log to the already verified nonzero fixture.
  // No assumptions about designer-buffer relocation in any other level.
  if (std::memcmp(M18Base() + 0x82C06221, "knaar_69\0", 9)) return;
  if (object.u32 < 0x82800000 || object.u32 > 0x82900000 ||
      M18Load(object.u32) != 0x8200FE2C) return;
  const auto selector = M18Load(object.u32 + 0x58);
  if (selector > 1 || command.u32 < 0x40000000 || command.u32 > 0x83000000) return;
  const auto action = M18Load(command.u32);
  const auto old_duration = duration.f64;
  const bool selected = mode == 2 && selector == 1 && action == 0x40000000 &&
      old_duration == -1.0 && scalar.f64 == 0.0 &&
      M18Base()[0x40CDD6FE] == 1;
  if (selected) duration.f64 = 6.0;
  REXLOG_INFO("ComboTest command selector={} action_bits={:08X} duration={} selected={} object={:08X} scalar={} state={} score={} bonus_bits={:08X} pending={}",
      selector, action, old_duration, selected, object.u32, scalar.f64,
      M18Load(0x8288D618), M18Load(0x40CDD678), M18Load(0x40CDD644),
      unsigned(M18Base()[0x40CDD6FE]));
}

// E-305 / Model B: use the remaining *gameplay* timer to initialize the
// existing Combo closing state, then leave interpolation to 8219F2C0. The
// native update-disable gate is before this site. The ordinary expiry command
// remains immediate, and original scoring open(-1) cancels/restarts the close.
// No polling thread, allocation, synthetic command or gameplay timer write.
// Explicit playable developer session only. The shared fix actor is present at
// these same addresses in intro_10, knaar_69 and swamp_81 scans. Fail closed if
// its live reciprocal link or designer-buffer identity differs; never guess a
// relocated buffer. Existing hidden experiments retain their original gates.
static bool ComboProfileEnabled() {
  static const bool enabled = [] {
    const char* v = std::getenv("R3HD_COMBO_CLOSE");
    const bool selected = v && !std::strcmp(v, "delayed");
    REXLOG_INFO("ComboClose profile_mode={}", selected ? "delayed" : "original");
    return selected;
  }();
  return enabled;
}

static bool ComboPlayableTest() {
  static const bool selected = [] {
    const char* mode = std::getenv("R3HD_TEST_COMBO_CLOSE");
    const char* manual = std::getenv("R3HD_TEST_COMBO_PLAYTEST");
    return mode && !std::strcmp(mode, "delayed-countdown") && manual &&
        !std::strcmp(manual, "1");
  }();
  return ComboProfileEnabled() || selected;
}

static bool ComboPlayableLayout() {
  const auto valid = [](uint32_t p) { return p >= 0x40000000 && p <= 0x41FFF000 && !(p & 3); };
  if (M18Load(0x40CD65D8) != 2 || M18Load(0x40CD65DC) != 0x40CD6340) return false;
  const auto stdgame = M18Load(0x40CD6344), brain = M18Load(0x40CD634C);
  if (!valid(stdgame) || M18Load(stdgame + 12) != 0x40CD65D8 || !valid(brain)) return false;
  const auto mind = M18Load(brain);
  if (!valid(mind)) return false;
  const auto mem = M18Load(mind + 12);
  if (!valid(mem) || M18Load(mem + 8) != 0x40CDD5BC) return false;
  const auto model = M18Load(mem);
  if (!valid(model)) return false;
  const auto vars = M18Load(model);
  if (!valid(vars) || M18Load(vars + 8) != 325) return false;
  const auto infos = M18Load(vars + 4);
  return valid(infos) && M18Load(infos + 24 * 16) == 136 &&
      M18Load(infos + 25 * 16) == 140 && M18Load(infos + 26 * 16) == 144 &&
      M18Load(infos + 29 * 16) == 322 && M18Load(infos + 36 * 16) == 188;
}

// E-311: command10029 owns a handle, not a permanent heap address. Mirror
// 821ABC88's read-only handle lookup (16-byte records, payload+16). A real
// front-end -> intro_15 load recreates the Combo handle; the former fixed
// 828A3E98 address is reused before the human's first pickup.
static bool ComboPlayableObject(uint32_t object) {
  const uint32_t handle = M18Load(0x8288D658), count = M18Load(0x829A3E18);
  if (!handle || !count || count > 256) return false;
  for (uint32_t i = 0; i < count; ++i) {
    const uint32_t entry = 0x82890598 + i * 16;
    if (M18Load(entry) == handle) {
      const uint32_t payload = M18Load(entry + 8);
      return payload >= 0x82800000 && payload <= 0x828FFFA0 &&
          !(payload & 3) && object == payload + 16;
    }
  }
  return false;
}

static void ComboDiagnostic(uint32_t object, int enabled) {
  static const bool selected = [] {
    const char* v = std::getenv("R3HD_TEST_COMBO_CAPTURE");
    return v && !std::strcmp(v, "1");
  }();
  if (!selected || object < 0x82800000 || object > 0x828FFFA0 ||
      M18Load(object) != 0x8200FE2C || M18Load(object + 0x58) != 1) return;
  const auto now = M18Load(0x82C0628C), start = M18Load(0x40CDD64C);
  const auto window = M18Load(0x40CDD648), age = now - start;
  const auto state = M18Load(0x8288D618), pending = unsigned(M18Base()[0x40CDD6FE]);
  const bool binding = ComboPlayableObject(object), layout = ComboPlayableLayout();
  const unsigned rejected = (!enabled ? 1 : 0) | (!binding ? 2 : 0) | (!layout ? 4 : 0) |
      (pending != 1 ? 8 : 0) | (state != 2 ? 16 : 0) |
      (window < 2000 || window > 6000 ? 32 : 0) | (age >= window ? 64 : 0) |
      (age < window && window - age > 1000 ? 128 : 0);
  const uint32_t row[] = {object, start, window, state, pending, rejected, M18Load(0x40CDD678)};
  static uint32_t last[7] = {};
  if (!std::memcmp(last, row, sizeof(row))) return;
  std::memcpy(last, row, sizeof(row));
  REXLOG_INFO("ComboEligibility pc=8219F2D8 now={} object={:08X} handle={} start={} window={} age={} state={} pending={} rejected={} score={}",
      now, object, M18Load(0x8288D658), start, window, age, state, pending, rejected, row[6]);
}

void ComboCountdownTest(PPCRegister& object) {
  static const int enabled = [] {
    const char* v = std::getenv("R3HD_TEST_COMBO_CLOSE");
    if (!v) return ComboProfileEnabled() ? 2 : 0;
    if ((!std::getenv("R3HD_NONINTRUSIVE") && !ComboPlayableTest()) || !v) return 0;
    if (!std::strcmp(v, "countdown")) return 1;
    if (!std::strcmp(v, "delayed-countdown")) return 2;
    return 0;
  }();
  ComboDiagnostic(object.u32, enabled);
  if (!enabled) return;
  if (ComboPlayableTest() ? (!ComboPlayableObject(object.u32) || !ComboPlayableLayout()) :
      std::memcmp(M18Base() + 0x82C06221, "knaar_69\0", 9)) return;
  if (
      object.u32 < 0x82800000 || object.u32 > 0x82900000 ||
      M18Load(object.u32) != 0x8200FE2C || M18Load(object.u32 + 0x58) != 1 ||
      M18Base()[0x40CDD6FE] != 1 || M18Load(0x8288D618) != 2) return;
  const uint32_t window = M18Load(0x40CDD648), start = M18Load(0x40CDD64C);
  const uint32_t now = M18Load(0x82C0628C), age = now - start;
  // E-307: scoring after a long event preserves max(2000, remaining), then
  // refreshes start. Delayed mode must accept these game-owned intermediate
  // windows too. Keep the earlier full-window experiment's exact guard.
  if (age >= window || (enabled == 2 ? (window < 2000 || window > 6000)
                                    : (window != 2000 && window != 6000))) return;
  // E-306: leave the game-owned open state alone until the final second.
  // Scoring's original open/reset restores the row and refreshes start; the
  // same guard then waits for the refreshed deadline. No extra tracking state.
  if (enabled == 2 && window - age > 1000) return;
  const float duration = float(window - age) / 1000.0f, reciprocal = 1.0f / duration;
  uint32_t duration_bits, reciprocal_bits;
  std::memcpy(&duration_bits, &duration, sizeof(duration_bits));
  std::memcpy(&reciprocal_bits, &reciprocal, sizeof(reciprocal_bits));
  M18Store(0x8288D5AC, duration_bits);
  M18Store(0x8288D5B0, reciprocal_bits);
  M18Store(0x8288D614, 0);
  M18Store(0x8288D618, 3);
  REXLOG_INFO("{} begin now={} start={} window={} remaining={} duration={} object={:08X} score={} bonus_bits={:08X}",
      enabled == 2 ? "ComboDelayed" : "ComboCountdown",
      now, start, window, window - age, duration, object.u32,
      M18Load(0x40CDD678), M18Load(0x40CDD644));
}
#endif

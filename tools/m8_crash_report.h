#if defined(_WIN32)  // M8 last-chance crash record for human playtests. Self-contained Win32: no runtime or guest
// dependency, no guest state is read or changed. Writes r3hd_crash.txt and a small minidump
// (thread stacks plus bounded host memory near the faulting thread's registers, D-311) to the process working
// directory, which the launchers keep under private/.
#pragma once
#include <windows.h>
#include <dbghelp.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#pragma comment(lib, "dbghelp.lib")

namespace m8crash {
// Optional host-side context (last entered guest function, lr, sp): writes text lines into out.
using DescribeFn = int (*)(char* out, int size);
inline DescribeFn& Describe() { static DescribeFn fn = nullptr; return fn; }

// D-311 (E-546): a stacks-only dump could not show the host objects behind the v1.1.0 RC1 SDL audio-thread fault
// (a stale logical-device link). Add the host heap near the faulting thread's integer registers (level 1) and near
// the pointers found in those windows (level 2). Only committed, non-executable, readable MEM_PRIVATE memory: never
// an image (translated game code), the guest address space or any other file mapping (MEM_MAPPED). Fixed storage,
// no allocation: the heap may be the thing that is damaged.
namespace detail {
struct Range { ULONG64 base; ULONG size; };
constexpr int kMaxRanges = 160;
constexpr ULONG kMaxBytes = 64 * 1024;
constexpr ULONG64 kLevel1Before = 0x80, kLevel1After = 0x180, kLevel2Before = 0x40, kLevel2After = 0xC0;
struct Capture { Range ranges[kMaxRanges]; int count = 0, level1 = 0, next = 0; ULONG bytes = 0; };
inline Capture& Captured() { static Capture capture; return capture; }

inline bool HostPrivate(ULONG64 address, ULONG64& lo, ULONG64& hi) {
  MEMORY_BASIC_INFORMATION info;
  if (address < 0x10000 || !VirtualQuery(reinterpret_cast<const void*>(address), &info, sizeof(info))) return false;
  const DWORD protect = info.Protect;
  if (info.State != MEM_COMMIT || info.Type != MEM_PRIVATE || (protect & (PAGE_GUARD | PAGE_NOACCESS)) ||
      !(protect & (PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY)))
    return false;
  lo = reinterpret_cast<ULONG64>(info.BaseAddress);
  hi = lo + info.RegionSize;
  return true;
}

inline void Add(ULONG64 address, ULONG64 before, ULONG64 after) {
  Capture& c = Captured();
  ULONG64 lo, hi;
  if (c.count >= kMaxRanges || c.bytes >= kMaxBytes || !HostPrivate(address, lo, hi)) return;
  const ULONG64 base = address - lo > before ? address - before : lo;
  ULONG64 end = hi - address > after ? address + after : hi;
  for (int i = 0; i < c.count; ++i)  // inside an earlier window: nothing new
    if (base >= c.ranges[i].base && end <= c.ranges[i].base + c.ranges[i].size) return;
  if (end - base > kMaxBytes - c.bytes) end = base + (kMaxBytes - c.bytes);
  c.ranges[c.count++] = {base, static_cast<ULONG>(end - base)};
  c.bytes += static_cast<ULONG>(end - base);
}

inline void CollectNearRegisters(const CONTEXT* context) {
#if defined(_M_X64) || defined(__x86_64__)
  const DWORD64 registers[] = {context->Rax, context->Rcx, context->Rdx, context->Rbx, context->Rsp, context->Rbp,
                               context->Rsi, context->Rdi, context->R8,  context->R9,  context->R10, context->R11,
                               context->R12, context->R13, context->R14, context->R15};
  for (DWORD64 value : registers) Add(value, kLevel1Before, kLevel1After);
  Capture& c = Captured();
  c.level1 = c.count;
  static ULONG64 window[(kLevel1Before + kLevel1After) / 8];
  for (int i = 0; i < c.level1; ++i) {
    SIZE_T read = 0;  // ReadProcessMemory fails instead of faulting if another thread frees the page meanwhile
    if (!ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<const void*>(c.ranges[i].base), window,
                           c.ranges[i].size < sizeof(window) ? c.ranges[i].size : sizeof(window), &read))
      continue;
    for (SIZE_T k = 0; k < read / 8; ++k) Add(window[k], kLevel2Before, kLevel2After);
  }
#else
  (void)context;
#endif
}

inline BOOL CALLBACK DumpCallback(PVOID, const PMINIDUMP_CALLBACK_INPUT input, PMINIDUMP_CALLBACK_OUTPUT output) {
  if (input->CallbackType != MemoryCallback) return TRUE;
  Capture& c = Captured();
  if (c.next >= c.count) {
    output->MemorySize = 0;
    return FALSE;
  }
  output->MemoryBase = c.ranges[c.next].base;
  output->MemorySize = c.ranges[c.next].size;
  ++c.next;
  return TRUE;
}
}  // namespace detail

inline LONG WINAPI Unhandled(EXCEPTION_POINTERS* fault) {
  static std::atomic<bool> entered{false};
  if (entered.exchange(true)) return EXCEPTION_CONTINUE_SEARCH;  // a second faulting thread: first report wins
  const EXCEPTION_RECORD* record = fault->ExceptionRecord;
  HMODULE module = nullptr;
  char module_path[MAX_PATH] = {};
  GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                     reinterpret_cast<LPCSTR>(record->ExceptionAddress), &module);
  if (module) GetModuleFileNameA(module, module_path, MAX_PATH);

  bool dumped = false;
  detail::CollectNearRegisters(fault->ContextRecord);
  HANDLE dump = CreateFileA("r3hd_crash.dmp", GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (dump != INVALID_HANDLE_VALUE) {
    MINIDUMP_EXCEPTION_INFORMATION info{GetCurrentThreadId(), fault, FALSE};
    MINIDUMP_CALLBACK_INFORMATION callback{detail::DumpCallback, nullptr};
    dumped = MiniDumpWriteDump(GetCurrentProcess(), GetCurrentProcessId(), dump, MiniDumpNormal, &info, nullptr, &callback) != FALSE;
    CloseHandle(dump);
  }

  char context[1024] = {};
  if (Describe()) Describe()(context, int(sizeof(context)) - 1);
  SYSTEMTIME now;
  GetSystemTime(&now);
  if (FILE* file = std::fopen("r3hd_crash.txt", "w")) {
    std::fprintf(file, "r3hd crash report\ntime_utc=%04u-%02u-%02uT%02u:%02u:%02uZ\n", now.wYear, now.wMonth, now.wDay,
                 now.wHour, now.wMinute, now.wSecond);
    std::fprintf(file, "code=%08lX flags=%08lX thread=%lu\n", record->ExceptionCode, record->ExceptionFlags, GetCurrentThreadId());
    std::fprintf(file, "address=%p module=%s offset=%llX\n", record->ExceptionAddress, module_path,
                 static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(record->ExceptionAddress) -
                                                 reinterpret_cast<uintptr_t>(module)));
    if (record->ExceptionCode == EXCEPTION_ACCESS_VIOLATION && record->NumberParameters >= 2)
      std::fprintf(file, "access=%s target=%p\n",
                   record->ExceptionInformation[0] == 0 ? "read" : record->ExceptionInformation[0] == 1 ? "write" : "execute",
                   reinterpret_cast<void*>(record->ExceptionInformation[1]));
    std::fputs(context, file);
    std::fprintf(file, "minidump=r3hd_crash.dmp written=%d\n", dumped ? 1 : 0);
    std::fprintf(file, "register_memory ranges=%d level1=%d bytes=%lu\n", detail::Captured().count,
                 detail::Captured().level1, detail::Captured().bytes);
    std::fclose(file);
  }

  // Hidden automated runs never show or activate a dialog (D-023).
  if (!std::getenv("R3HD_NONINTRUSIVE")) {
    char directory[MAX_PATH] = {};
    GetCurrentDirectoryA(MAX_PATH, directory);
    char message[2 * MAX_PATH];
    std::snprintf(message, sizeof(message),
                  "r3hd stopped because of an unexpected error (code %08lX).\n\n"
                  "Diagnostics were written to:\n%s\n\nr3hd_crash.txt, r3hd_crash.dmp, m2_faults.log and runtime.log",
                  record->ExceptionCode, directory);
    MessageBoxA(nullptr, message, "r3hd", MB_OK | MB_ICONERROR | MB_SETFOREGROUND);
  }
  return EXCEPTION_EXECUTE_HANDLER;
}

inline void Install(DescribeFn describe) {
  Describe() = describe;
  SetUnhandledExceptionFilter(Unhandled);
}
}  // namespace m8crash
#else
#pragma once
// Linux (LM-1): the Win32 crash report (unhandled-exception filter, minidump) is unavailable; Install records the
// describe hook only and installs no signal handler (signal ownership is the SDK's).
namespace m8crash {
using DescribeFn = int (*)(char* out, int size);
inline DescribeFn& Describe() { static DescribeFn fn = nullptr; return fn; }
inline void Install(DescribeFn describe) { Describe() = describe; }
}  // namespace m8crash
#endif

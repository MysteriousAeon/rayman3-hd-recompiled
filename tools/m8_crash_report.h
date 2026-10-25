// M8 last-chance crash record for human playtests. Self-contained Win32: no runtime or guest
// dependency, no guest state is read or changed. Writes r3hd_crash.txt and a small minidump
// (thread stacks only) to the process working directory, which the launchers keep under private/.
#pragma once
#include <windows.h>
#include <dbghelp.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#pragma comment(lib, "dbghelp.lib")

namespace m8crash {
// Optional host-side context (last entered guest function, lr, sp): writes text lines into out.
using DescribeFn = int (*)(char* out, int size);
inline DescribeFn& Describe() { static DescribeFn fn = nullptr; return fn; }

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
  HANDLE dump = CreateFileA("r3hd_crash.dmp", GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (dump != INVALID_HANDLE_VALUE) {
    MINIDUMP_EXCEPTION_INFORMATION info{GetCurrentThreadId(), fault, FALSE};
    dumped = MiniDumpWriteDump(GetCurrentProcess(), GetCurrentProcessId(), dump, MiniDumpNormal, &info, nullptr, nullptr) != FALSE;
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

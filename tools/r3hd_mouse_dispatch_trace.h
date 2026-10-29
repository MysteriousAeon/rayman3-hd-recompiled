// Optional hidden-only observation at existing host function-entry probes.
// Research only: no guest writes or mouse delivery. Never enabled by play.ps1.
#pragma once
#include <rex/system/kernel_state.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <windows.h>

namespace r3hd_mouse_dispatch {
inline void Enter(const char* name, const PPCContext& ctx) {
  static const char* path = std::getenv("R3HD_MOUSE_DISPATCH_TRACE");
  static const bool enabled = path && *path && std::getenv("R3HD_NONINTRUSIVE");
  if (!enabled || std::strncmp(name, "__imp__sub_822", 14)) return;
  name += 7;
  uint32_t pc = 0;
  // Exact known function names; no parsing or memory work for other calls.
  if (!std::strcmp(name, "sub_82297ED0")) pc = 0x82297ED0;
  else if (!std::strcmp(name, "sub_82297638")) pc = 0x82297638;
  else if (!std::strcmp(name, "sub_82297C80")) pc = 0x82297C80;
  else if (!std::strcmp(name, "sub_82297C58")) pc = 0x82297C58;
  else if (!std::strcmp(name, "sub_82297CD0")) pc = 0x82297CD0;
  else if (!std::strcmp(name, "sub_82297CA8")) pc = 0x82297CA8;
  else if (!std::strcmp(name, "sub_8227CFD0")) pc = 0x8227CFD0;
  else return;
  const bool reader = pc >= 0x82297C58 && pc <= 0x82297CD0;
  if (reader && (ctx.lr < 0x8227D000 || ctx.lr > 0x8227D0B0)) return;
  static FILE* out = std::fopen(path, "wb");
  if (!out) return;
  const auto* base = REX_KERNEL_MEMORY()->virtual_membase();
  auto word = [&](uint32_t address) -> uint32_t {
    uint8_t data[4]{};
    SIZE_T got = 0;
    if (!ReadProcessMemory(GetCurrentProcess(), base + address, data, 4, &got) || got != 4) return UINT32_MAX;
    return (uint32_t(data[0]) << 24) | (uint32_t(data[1]) << 16) | (uint32_t(data[2]) << 8) | data[3];
  };
  static bool header = false;
  if (!header) {
    std::fputs("qpc,frame,pc,lr,r3,r4,r5,global_enable,count,list,counter,entry_enable,context0,context4,context8,tid,opcode,argument\n", out);
    header = true;
  }
  LARGE_INTEGER now{};
  QueryPerformanceCounter(&now);
  const uint32_t pointer = ctx.r3.u32;
  const uint32_t enabled_word = word(0x8283D6B8);
  std::fprintf(out, "%lld,%u,%08X,%08X,%08X,%08X,%08X,%u,%u,%08X,%u,%u,%08X,%08X,%08X,%lu,%u,%08X\n",
      now.QuadPart, word(0x82C06284), pc, unsigned(ctx.lr), pointer, ctx.r4.u32, ctx.r5.u32,
      enabled_word == UINT32_MAX ? UINT32_MAX : ((enabled_word >> 16) & 255),
      word(0x82C8DE5C), word(0x82C8DE60), reader ? word(pointer + 16) : UINT32_MAX,
      reader ? word(pointer + 24) >> 24 : UINT32_MAX, word(pointer), word(pointer + 4), word(pointer + 8),
      GetCurrentThreadId(), pc == 0x8227CFD0 ? word(ctx.r4.u32 - 8) : UINT32_MAX,
      pc == 0x8227CFD0 ? word(ctx.r4.u32) : UINT32_MAX);
  if (pc == 0x82297ED0) std::fflush(out);
}
}  // namespace r3hd_mouse_dispatch

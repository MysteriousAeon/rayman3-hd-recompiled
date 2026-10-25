// Synthetic guest register state only; no game bytes or translated functions.
#include "r3hd_pch.h"
#include <cstdio>
thread_local const char* m2_current_function = nullptr;
thread_local PPCContext* m2_current_context = nullptr;
void M2Enter(const char*, PPCContext&) {}
static void NestedJump(PPCContext& ctx) {
  ctx.r1.u32 = 0x1234;
  ctx.r31.u32 = 0;
  ppc_longjmp(0x1000, 1);
}
int main() {
  PPCContext ctx{};
  ctx.r1.u32 = 0x70001000;
  ctx.r31.u32 = 0x40001234;
  PPCContext env = ctx;
  PPCRegister temp{};
  temp.s64 = ppc_setjmp(0x1000);
  if (temp.s64 != 0) ctx = env;
  ctx.r3 = temp;
  if (ctx.r3.s32 == 0) NestedJump(ctx);
  bool passed = ctx.r3.s32 == 1 && ctx.r1.u32 == 0x70001000 && ctx.r31.u32 == 0x40001234;
  std::printf("nonlocal synthetic register restoration: %s\n", passed ? "PASS" : "FAIL");
  return passed ? 0 : 1;
}

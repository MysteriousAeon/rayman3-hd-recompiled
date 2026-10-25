#pragma once
#include <windows.h>
#include <rex/ppc/context.h>
#include <rex/platform/exceptions.h>
void M2InstallCrashHandler();
void M2Enter(const char* name, PPCContext& ctx);
extern thread_local const char* m2_current_function;
extern thread_local PPCContext* m2_current_context;

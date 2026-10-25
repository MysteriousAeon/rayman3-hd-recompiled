#define R3HD_DISCORD_TEST
#include "m2_host/r3hd_discord.h"
#include <iostream>

int wmain(int argc, wchar_t** argv) {
  if (argc != 3) return 2;
  SetEnvironmentVariableA("R3HD_NONINTRUSIVE", "1");
  // CRT getenv uses its own environment snapshot.
  _putenv_s("R3HD_NONINTRUSIVE", "1");
  if (r3hd::DiscordPresence::Enabled()) return 3;
  _putenv_s("R3HD_NONINTRUSIVE", "");
  _putenv_s("R3HD_DISCORD", "off");
  if (r3hd::DiscordPresence::Enabled()) return 4;
  _putenv_s("R3HD_DISCORD", "on");
  if (!r3hd::DiscordPresence::Enabled()) return 5;
  // Warm up the CRT thread machinery before comparing live handles.
  std::thread([] {}).join();
  DWORD before = 0, after = 0;
  GetProcessHandleCount(GetCurrentProcess(), &before);
  r3hd::DiscordPresence presence;
  presence.StartTest(argv[1]);
  presence.StartTest(argv[1]); // idempotent
  Sleep(static_cast<DWORD>(_wtoi(argv[2])));
  auto time = GetTickCount64();
  presence.Stop();
  presence.Stop();
  auto elapsed = GetTickCount64() - time;
  GetProcessHandleCount(GetCurrentProcess(), &after);
  std::cout << "{\"stop_ms\":" << elapsed << ",\"handles_before\":" << before
            << ",\"handles_after\":" << after << "}" << std::endl;
  return elapsed < 1000 && after == before ? 0 : 6;
}

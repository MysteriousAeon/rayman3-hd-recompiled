// Host-only proof for the same std::filesystem narrow-path boundary used by the runtime.
#include <windows.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) return 2;
  std::filesystem::path wide(argv[1]);
  std::filesystem::create_directories(wide);
  auto utf8 = wide.u8string();
  std::string narrow(reinterpret_cast<const char*>(utf8.data()), utf8.size());
  std::filesystem::path converted(narrow);
  bool same = converted == wide;
  if (same) {
    std::ofstream(converted / "probe.txt") << "retained";
    std::filesystem::rename(converted / "probe.txt", converted / "renamed.txt");
    std::ifstream f(wide / "renamed.txt");
    std::string text; f >> text;
    same = text == "retained";
  }
  std::cout << "UTF8_PATH acp=" << GetACP() << " same=" << same << "\n";
  return same ? 0 : 1;
}

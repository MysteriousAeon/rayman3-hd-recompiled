"""Replay last in the chain: the entrypoint check accepts Default.xex on a case-sensitive filesystem (LX-6, E-377).

`ReXApp` checks `<game_data_root>/default.xex` with `std::filesystem::is_regular_file` before loading the image
"game:\\default.xex". The guest VFS (`HostPathDevice::ResolvePath`) already resolves names case-insensitively, and the
person's verified data holds `Default.xex` (the package's own name, checked by the intake), so on Linux the host
pre-check refused a file the loader would find (LX2B: "Entrypoint XEX not found: .../data/content/default.xex").

The edit keeps the Windows build identical and every Windows line number unchanged:
  * src/ui/rex_app.cpp: the one `if` line gains `REX_XEX_CASE_FALLBACK(xex_host)` on the same line;
  * include/rex/rex_app.h, appended after its last line: on Windows the macro is empty; on POSIX it adds
    `&& !rex::detail::XexExistsIgnoringCase(path)`, which looks for that file name in its directory ignoring ASCII
    case, as the VFS does. The data is never renamed and no link is made.
Tests: tools/linux/xex_case_test.py (POSIX behaviour, WSL/Linux) and tools/r3hd_xex_case_regression.py (patched text,
Windows token/line neutrality).
"""
from m3_runtime_patch import SDK
from m8_runtime_patch import patch_once

CPP = 'src/ui/rex_app.cpp'
HDR = 'include/rex/rex_app.h'
LINE_BEFORE = '    if (!std::filesystem::is_regular_file(xex_host)) {\n'
LINE_AFTER = '    if (!std::filesystem::is_regular_file(xex_host) REX_XEX_CASE_FALLBACK(xex_host)) {\n'
HELPER = '''
// LX-6 (E-377): the entrypoint pre-check in rex_app.cpp agrees with the guest VFS, which resolves names
// case-insensitively (HostPathDevice::ResolvePath): on POSIX, Default.xex satisfies "default.xex". Windows: empty.
#if !defined(_WIN32)
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <system_error>
namespace rex::detail {
inline bool XexExistsIgnoringCase(const std::filesystem::path& path) {
  const std::string want = path.filename().string();
  std::error_code ec;
  std::filesystem::directory_iterator it(path.parent_path(), ec), end;
  for (; !ec && it != end; it.increment(ec)) {
    const std::string name = it->path().filename().string();
    if (name.size() == want.size() &&
        std::equal(name.begin(), name.end(), want.begin(), [](char a, char b) {
          return std::tolower(static_cast<unsigned char>(a)) == std::tolower(static_cast<unsigned char>(b));
        })) {
      std::error_code type_ec;
      if (it->is_regular_file(type_ec)) return true;
    }
  }
  return false;
}
}  // namespace rex::detail
#define REX_XEX_CASE_FALLBACK(path) && !::rex::detail::XexExistsIgnoringCase(path)
#else
#define REX_XEX_CASE_FALLBACK(path)
#endif
'''


if __name__ == '__main__':
    patch_once(CPP, [(LINE_BEFORE, LINE_AFTER)])
    text = (SDK / HDR).read_text()
    if 'REX_XEX_CASE_FALLBACK' not in text:
        (SDK / HDR).write_text(text + HELPER)
        print('patched', HDR)

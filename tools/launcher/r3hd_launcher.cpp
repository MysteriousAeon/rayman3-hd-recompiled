// M30 (D-067): the Settings launcher and the direct Play entry of an installation of Rayman 3 HD Recompiled.
//
// It holds no setting, default or rule of its own. What it shows comes from the installer engine
// (app\tools\r3hd_installer.py launcher-model: the preset registry, the resolver's view of settings.json and the
// installation state); what it saves goes through the engine's set-preset, where the resolver validates it and
// writes settings.json. Play runs app\tools\play.ps1 -UserHome HOME hidden (the same launcher, settings
// resolution and save keeper as every other entry) and this program exits as soon as the game has started, or
// reports why it could not. It never starts r3hd.exe itself, never writes a file of the installation and never
// touches saves.
// M31 (D-068): a setting may require another setting's value (model REQUIRES rows; shown disabled otherwise), the
// read-only Controls page lists the model's CONTROL rows (the runtime's key bindings), and the window icon is the
// project icon of the executable's resources.
//
// usage:  r3hd_launcher.exe                 the Settings window
//         r3hd_launcher.exe --play          start the game with the saved settings, without a window
// test only (tools/m30_launcher_regression.py; synthetic homes):
//         --home H --python P --tools T [--releases F]   paths instead of the installation's own
//         --play --dry-run --no-ui          play.ps1 -DryRun; the result on stdout, never a message box
//         --ui-test SCRIPT --out DIR        the Settings window on a private desktop that no one sees (never the
//                                           user's desktop); Play is a dry run there, Open folder does nothing
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <commctrl.h>
#include <commdlg.h>
#include <shlobj.h>
#include <shellapi.h>
#include <tlhelp32.h>

#include <algorithm>
#include <array>
#include <map>
#include <string>
#include <vector>

namespace {

const wchar_t kWindowClass[] = L"R3HDRecompSettings";
const wchar_t kAppMutex[] = L"Rayman3HDRecompLauncher";  // tools/installer/r3hd_setup.iss AppMutex
const wchar_t kPlayMutex[] = L"Local\\Rayman3HDRecompPlay";
const DWORD kEngineTimeoutMs = 60000;
const DWORD kModsTimeoutMs = 15 * 60000;  // M33: importing a large texture mod encodes it in pure Python
const DWORD kStartTimeoutMs = 120000;
const int kWidth = 840;  // client width in pixels at 96 DPI

// ---------------------------------------------------------------------------------------------------- text --

std::wstring Widen(const std::string& s, UINT cp = CP_UTF8) {
  if (s.empty()) return {};
  int n = MultiByteToWideChar(cp, 0, s.data(), (int)s.size(), nullptr, 0);
  std::wstring w(n, L'\0');
  MultiByteToWideChar(cp, 0, s.data(), (int)s.size(), &w[0], n);
  return w;
}

std::string Narrow(const std::wstring& w) {
  if (w.empty()) return {};
  int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), nullptr, 0, nullptr, nullptr);
  std::string s(n, '\0');
  WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), &s[0], n, nullptr, nullptr);
  return s;
}

std::vector<std::wstring> Split(const std::wstring& s, wchar_t sep) {
  std::vector<std::wstring> out;
  size_t start = 0;
  for (;;) {
    size_t p = s.find(sep, start);
    out.push_back(s.substr(start, p == std::wstring::npos ? std::wstring::npos : p - start));
    if (p == std::wstring::npos) return out;
    start = p + 1;
  }
}

std::wstring Trim(const std::wstring& s) {
  size_t a = s.find_first_not_of(L" \t\r\n");
  if (a == std::wstring::npos) return {};
  size_t b = s.find_last_not_of(L" \t\r\n");
  return s.substr(a, b - a + 1);
}

// One argument, quoted by the rules CommandLineToArgvW and the C runtime read.
std::wstring Quote(const std::wstring& a) {
  if (!a.empty() && a.find_first_of(L" \t\"") == std::wstring::npos) return a;
  std::wstring q = L"\"";
  size_t slashes = 0;
  for (wchar_t c : a) {
    if (c == L'\\') { ++slashes; continue; }
    if (c == L'"') q.append(slashes * 2 + 1, L'\\');
    else q.append(slashes, L'\\');
    slashes = 0;
    q.push_back(c);
  }
  q.append(slashes * 2, L'\\');
  return q + L"\"";
}

std::wstring Join(const std::vector<std::wstring>& args) {
  std::wstring s;
  for (const auto& a : args) { if (!s.empty()) s += L' '; s += Quote(a); }
  return s;
}

std::wstring Parent(const std::wstring& p) {
  size_t i = p.find_last_of(L"\\/");
  return i == std::wstring::npos ? p : p.substr(0, i);
}

std::wstring FullPath(const std::wstring& p) {
  wchar_t buf[MAX_PATH * 4];
  DWORD n = GetFullPathNameW(p.c_str(), (DWORD)std::size(buf), buf, nullptr);
  return n && n < std::size(buf) ? std::wstring(buf, n) : p;
}

std::string ReadFileBytes(const std::wstring& p) {
  std::string s;
  HANDLE f = CreateFileW(p.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                         OPEN_EXISTING, 0, nullptr);
  if (f == INVALID_HANDLE_VALUE) return s;
  char buf[4096];
  DWORD got = 0;
  while (ReadFile(f, buf, sizeof buf, &got, nullptr) && got) s.append(buf, got);
  CloseHandle(f);
  return s;
}

// ----------------------------------------------------------------------------------------------- processes --

struct Paths {
  std::wstring home, python, tools, releases;
};

void IdlePump();

// Runs a console program without any window and returns what it wrote (stdout and stderr) and its exit code.
// M33: `pump` keeps the (disabled) Settings window painting while a long mod action runs.
bool RunCapture(const std::wstring& exe, const std::vector<std::wstring>& args, std::string& out, DWORD& code,
                DWORD timeoutMs = kEngineTimeoutMs, bool pump = false) {
  SECURITY_ATTRIBUTES sa{sizeof sa, nullptr, TRUE};
  HANDLE rd = nullptr, wr = nullptr;
  if (!CreatePipe(&rd, &wr, &sa, 0)) return false;
  SetHandleInformation(rd, HANDLE_FLAG_INHERIT, 0);
  HANDLE nul = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, nullptr);
  STARTUPINFOW si{sizeof si};
  si.dwFlags = STARTF_USESTDHANDLES;
  si.hStdInput = nul;
  si.hStdOutput = wr;
  si.hStdError = wr;
  PROCESS_INFORMATION pi{};
  std::wstring cmd = Join({exe}) + L" " + Join(args);
  BOOL ok = CreateProcessW(exe.c_str(), &cmd[0], nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi);
  CloseHandle(wr);
  if (nul != INVALID_HANDLE_VALUE) CloseHandle(nul);
  if (!ok) { CloseHandle(rd); return false; }
  ULONGLONG deadline = GetTickCount64() + timeoutMs;
  char buf[8192];
  for (;;) {
    DWORD avail = 0;
    if (!PeekNamedPipe(rd, nullptr, 0, nullptr, &avail, nullptr)) break;  // writer gone and pipe drained
    if (avail) {
      DWORD got = 0;
      if (!ReadFile(rd, buf, std::min<DWORD>(avail, sizeof buf), &got, nullptr) || !got) break;
      out.append(buf, got);
      continue;
    }
    if (GetTickCount64() > deadline) { TerminateProcess(pi.hProcess, 1); break; }
    if (pump) IdlePump();
    WaitForSingleObject(pi.hProcess, 20);
  }
  WaitForSingleObject(pi.hProcess, 5000);
  GetExitCodeProcess(pi.hProcess, &code);
  CloseHandle(pi.hProcess);
  CloseHandle(pi.hThread);
  CloseHandle(rd);
  return true;
}

std::vector<std::wstring> EngineArgs(const Paths& p, const std::wstring& cmd) {
  std::vector<std::wstring> a{L"-B", p.tools + L"\\r3hd_installer.py", cmd, L"--home", p.home};
  if (!p.releases.empty()) { a.push_back(L"--releases"); a.push_back(p.releases); }
  return a;
}

// pid -> parent pid of every running r3hd.exe.
std::vector<std::pair<DWORD, DWORD>> GameProcesses() {
  std::vector<std::pair<DWORD, DWORD>> out;
  HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
  if (snap == INVALID_HANDLE_VALUE) return out;
  PROCESSENTRY32W e{sizeof e};
  for (BOOL ok = Process32FirstW(snap, &e); ok; ok = Process32NextW(snap, &e))
    if (_wcsicmp(e.szExeFile, L"r3hd.exe") == 0) out.push_back({e.th32ProcessID, e.th32ParentProcessID});
  CloseHandle(snap);
  return out;
}

// English source keys are stable, independent of setting IDs and control positions.
std::wstring uiLanguage = L"en";
std::map<std::wstring, std::wstring> uiStrings;
std::wstring T(const std::wstring& key) {
  auto it = uiStrings.find(key);
  return it == uiStrings.end() ? key : it->second;
}
std::wstring F(const std::wstring& key,
               std::initializer_list<std::pair<std::wstring, std::wstring>> fields) {
  std::wstring result = T(key);
  for (const auto& field : fields) {
    std::wstring token = L"{" + field.first + L"}";
    size_t at = 0;
    while ((at = result.find(token, at)) != std::wstring::npos) {
      result.replace(at, token.size(), field.second);
      at += field.second.size();
    }
  }
  return result;
}

// -------------------------------------------------------------------------------------------------- model --

struct Value { std::wstring value, label; };
struct Setting {
  std::wstring key, group, scope, category, label, help, note, vanilla, hdplus, current;
  std::wstring requiresKey, requiresValue;  // M31: shown disabled unless that setting has that value
  std::vector<Value> values;
  bool slider = false;  // D-108: model SLIDER row: a trackbar over the values (min ... max), its value beside it
  bool Toggle() const { return !slider && values.size() == 2 && (scope == L"preset" || group == L"corrections" ||
      (values[0].value == L"off" && values[1].value == L"on")); }
  const std::wstring& Column(const std::wstring& preset) const { return preset == L"hdplus" ? hdplus : vanilla; }
  HWND title = nullptr, control = nullptr, helpText = nullptr, valueText = nullptr;
};
struct Preset { std::wstring key, name, text; };
// M32 (D-069): the keyboard map, all from the model's KEY* rows (config/controls/keymap.json and the saved keys).
using Slots = std::array<std::wstring, 2>;
struct KeyName { std::wstring name, label, reserved; std::vector<std::wstring> scans; };
struct KeyInput {
  std::wstring id, group, pad, action;
  bool hidden = false, required = false;
  Slots saved;
  HWND text = nullptr, padText = nullptr, button[2] = {};
};
struct KeyLayout { std::wstring key, name, text; std::map<std::wstring, Slots> keys; };
struct Model {
  std::wstring home, product, version, install, files, filesFirst, data, dataDetail;
  std::wstring languageKey, language = L"en";
  std::wstring settingsState, preset, base, presetLabel, settingsDetail, lastStamp, lastExit;
  int filesMissing = 0;
  bool running = false, lastFailed = false;
  std::vector<Preset> presets;
  std::vector<std::pair<std::wstring, std::wstring>> groups;
  std::vector<Setting> settings;
  std::wstring keyboardState, keyboardLayout, keyboardWarning, keyNote;
  std::vector<KeyLayout> layouts;
  std::vector<std::pair<std::wstring, std::wstring>> keyGroups;
  std::vector<KeyInput> keyInputs;
  std::vector<KeyName> keyNames;
  std::vector<std::pair<std::wstring, std::wstring>> fallbacks;  // key -> input
};

bool LoadModel(const Paths& p, Model& m, std::wstring& error) {
  std::string out;
  DWORD code = 1;
  if (!RunCapture(p.python, EngineArgs(p, L"launcher-model"), out, code)) {
    error = L"the settings component could not be started (" + p.python + L")";
    return false;
  }
  std::wstring text = Widen(out);
  std::vector<std::wstring> lines = Split(text, L'\n');
  while (!lines.empty() && Trim(lines.back()).empty()) lines.pop_back();
  if (code != 0 || lines.empty() || lines.front() != L"R3HD_LAUNCHER_MODEL\t3" || lines.back() != L"END") {
    std::wstring tail = Trim(text);
    if (tail.size() > 600) tail = L"..." + tail.substr(tail.size() - 600);
    error = L"the installation could not be read (exit code " + std::to_wstring(code) + L"): " + tail;
    return false;
  }
  m = Model{};
  uiStrings.clear();
  for (const auto& line : lines) {
    auto f = Split(line, L'\t');
    auto at = [&](size_t i) { return i < f.size() ? f[i] : std::wstring(); };
    const std::wstring& k = f[0];
    if (k == L"LANG") { m.languageKey = at(1); m.language = at(2); }
    else if (k == L"UISTRING") uiStrings[at(1)] = at(2);
    else if (k == L"HOME") m.home = at(1);
    else if (k == L"PRODUCT") m.product = at(1);
    else if (k == L"VERSION") m.version = at(1);
    else if (k == L"INSTALL") m.install = at(1);
    else if (k == L"FILES") { m.files = at(1); m.filesMissing = _wtoi(at(2).c_str()); m.filesFirst = at(3); }
    else if (k == L"DATA") { m.data = at(1); m.dataDetail = at(2); }
    else if (k == L"RUNNING") m.running = at(1) == L"1";
    else if (k == L"LASTRUN") { m.lastStamp = at(1); m.lastExit = at(2); m.lastFailed = at(3) == L"1"; }
    else if (k == L"SETTINGS") {
      m.settingsState = at(1); m.preset = at(2); m.base = at(3); m.presetLabel = at(4); m.settingsDetail = at(5);
    } else if (k == L"PRESET") m.presets.push_back({at(1), at(2), at(3)});
    else if (k == L"GROUP") m.groups.push_back({at(1), at(2)});
    else if (k == L"SETTING") {
      Setting s;
      s.key = at(1); s.group = at(2); s.scope = at(3); s.category = at(4); s.label = at(5); s.help = at(6);
      s.note = at(7); s.vanilla = at(8); s.hdplus = at(9); s.current = at(10);
      m.settings.push_back(s);
    } else if (k == L"VALUE") {
      for (auto& s : m.settings)
        if (s.key == at(1)) s.values.push_back({at(2), at(3)});
    } else if (k == L"REQUIRES") {
      for (auto& s : m.settings)
        if (s.key == at(1)) { s.requiresKey = at(2); s.requiresValue = at(3); }
    } else if (k == L"SLIDER") {
      for (auto& s : m.settings)
        if (s.key == at(1)) s.slider = true;
    } else if (k == L"KEYBOARD") { m.keyboardState = at(1); m.keyboardLayout = at(2); m.keyboardWarning = at(3); }
    else if (k == L"KEYLAYOUT") m.layouts.push_back({at(1), at(2), at(3), {}});
    else if (k == L"KEYGROUP") m.keyGroups.push_back({at(1), at(2)});
    else if (k == L"KEYINPUT") {
      KeyInput i;
      i.id = at(1); i.group = at(2); i.hidden = at(3) == L"1"; i.required = at(4) == L"1"; i.pad = at(5); i.action = at(6);
      m.keyInputs.push_back(i);
    } else if (k == L"KEYDEFAULT") {
      for (auto& l : m.layouts)
        if (l.key == at(1)) l.keys[at(2)] = {at(3), at(4)};
    } else if (k == L"KEYBIND") {
      for (auto& i : m.keyInputs)
        if (i.id == at(1)) i.saved = {at(2), at(3)};
    } else if (k == L"KEYNAME") m.keyNames.push_back({at(1), at(2), at(4), Split(at(3), L',')});
    else if (k == L"KEYFALLBACK") m.fallbacks.push_back({at(1), at(2)});
    else if (k == L"KEYNOTE") m.keyNote = at(1);
  }
  uiLanguage = m.language;
  if (m.languageKey.empty() || uiStrings.empty()) {
    error = L"The Settings components do not match. Run setup to repair this installation.";
    return false;
  }
  if (m.presets.size() != 3 || m.settings.empty()) { error = L"the settings description is incomplete"; return false; }
  if (m.layouts.empty() || m.keyInputs.empty() || m.keyNames.empty()) { error = L"the keyboard description is incomplete"; return false; }
  return true;
}

// The engine's set-preset: the resolver validates the choice and writes settings.json.
bool SaveSettings(const Paths& p, const std::wstring& preset, const std::wstring& base,
                  const std::vector<std::wstring>& pairs, const std::vector<std::wstring>& keyboard,
                  std::wstring& message) {
  wchar_t dir[MAX_PATH], file[MAX_PATH];
  GetTempPathW(MAX_PATH, dir);
  GetTempFileNameW(dir, L"r3h", 0, file);
  std::vector<std::wstring> a = EngineArgs(p, L"set-preset");
  a.insert(a.end(), {L"--preset", preset});
  if (!base.empty()) a.insert(a.end(), {L"--base", base});
  if (!pairs.empty()) { a.push_back(L"--set"); a.insert(a.end(), pairs.begin(), pairs.end()); }
  a.insert(a.end(), keyboard.begin(), keyboard.end());  // M32: --keyboard LAYOUT [--key INPUT=KEYS ...]
  a.insert(a.end(), {L"--result-file", file});
  std::string out;
  DWORD code = 1;
  bool ran = RunCapture(p.python, a, out, code);
  std::wstring result = Widen(ReadFileBytes(file));
  DeleteFileW(file);
  if (!result.empty() && result[0] == 0xFEFF) result.erase(0, 1);
  message.clear();
  for (const auto& line : Split(result, L'\n'))
    if (line.rfind(L"MESSAGE=", 0) == 0) message = Trim(line.substr(8));
  if (code != 0) message = T(L"Settings could not be saved. Check folder access and try again.");
  if (!ran) message = T(L"The settings component could not be started.");
  return ran && code == 0;
}

// ------------------------------------------------------------------------------------------------- mods --
std::wstring ModError(const std::wstring& code) {
  if (code == L"BAD_MANIFEST" || code == L"NOT_A_MOD" || code == L"BAD_IMAGE" || code == L"UNSAFE_PACKAGE" ||
      code == L"TOO_LARGE" || code == L"UNSUPPORTED")
    return T(L"The mod package is invalid. Choose a valid mod ZIP or folder.");
  if (code == L"TARGET_CHANGED" || code == L"TARGET_MISSING" || code == L"INCOMPATIBLE")
    return T(L"This mod does not match your game files or port version.");
  if (code == L"MISSING_DEPENDENCY" || code == L"TEXT_GLYPH_MISSING")
    return T(L"This mod needs another mod. Check its requirements and load order.");
  if (code == L"CONFLICT") return T(L"This mod conflicts with another enabled mod.");
  if (code == L"DAMAGED" || code == L"STATE_DAMAGED")
    return T(L"The mod is damaged. Reinstall it from its original package.");
  if (code == L"UNREADABLE") return T(L"Mod data could not be read or written. Check folder access and try again.");
  if (code == L"NO_GAME_DATA") return T(L"Game data is unavailable. Run setup to repair it.");
  if (code == L"TEXT_TOO_LONG" || code == L"TEXT_OVERLAP")
    return T(L"The translation does not fit the game files. Use a compatible mod package.");
  return T(L"The mod action could not be completed. Check the package and folder access.");
}
// M33 (D-070): the Mods page shows app\tools\r3hd_mods.py list and runs its import / enable / disable / move /
// remove. The launcher validates nothing itself: the mod tool refuses unsafe or invalid packages and says why.

struct ModRow {
  std::wstring id, state, name, version, code, detail, description;
  bool enabled = false;
  int ranges = 0, shadowed = 0;
};

// Runs r3hd_mods.py CMD ARGS --home HOME --rows. `message` is the refusal's text (or the problem running it).
bool RunMods(const Paths& p, const std::vector<std::wstring>& args, std::vector<ModRow>* rows, std::wstring& message) {
  std::vector<std::wstring> a{L"-B", p.tools + L"\\r3hd_mods.py"};
  a.insert(a.end(), args.begin(), args.end());
  a.insert(a.end(), {L"--home", p.home, L"--rows"});
  std::string out;
  DWORD code = 1;
  message.clear();
  if (!RunCapture(p.python, a, out, code, kModsTimeoutMs, true)) {
    message = T(L"The mod component could not be started.");
    return false;
  }
  std::vector<std::wstring> lines = Split(Widen(out), L'\n');
  while (!lines.empty() && Trim(lines.back()).empty()) lines.pop_back();
  if (lines.empty() || Trim(lines.front()) != L"R3HD_MODS_ROWS\t1" || Trim(lines.back()) != L"END") {
    std::wstring tail = Trim(Widen(out));
    if (tail.size() > 400) tail = L"..." + tail.substr(tail.size() - 400);
    message = T(L"Mod data could not be read or written. Check folder access and try again.");
    return false;
  }
  bool ok = false;
  if (rows) rows->clear();
  for (auto& line : lines) {
    if (!line.empty() && line.back() == L'\r') line.pop_back();
    auto f = Split(line, L'\t');
    auto at = [&](size_t i) { return i < f.size() ? f[i] : std::wstring(); };
    if (f[0] == L"RESULT") {
      ok = at(1) == L"ok";
      if (!ok) { message = ModError(at(2)); }
    } else if (f[0] == L"MOD" && rows) {
      ModRow r;
      r.id = at(1); r.enabled = at(2) == L"1"; r.state = at(3); r.name = at(4); r.version = at(5); r.code = at(6);
      r.detail = at(7); r.description = at(8); r.ranges = _wtoi(at(9).c_str()); r.shadowed = _wtoi(at(10).c_str());
      rows->push_back(r);
    }
  }
  return ok && code == 0;
}

// ---------------------------------------------------------------------------------------------- launching --

// Slow: play.ps1 is still running but no game appeared within the timeout (never reported as a start; M30 review).
enum class Launch { Started, Ended, Failed, AlreadyRunning, Busy, Slow };

// While a start is awaited the Settings window is disabled but keeps painting (M30 review: no "Not responding").
void IdlePump() {
  MSG msg;
  while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
    if (msg.message == WM_QUIT) { PostQuitMessage((int)msg.wParam); return; }
    TranslateMessage(&msg);
    DispatchMessageW(&msg);
  }
}

// The message of a failed play.ps1 run, from its redirected output.
std::wstring PlayFailure(const std::string& raw) {
  std::vector<std::wstring> lines = Split(Widen(raw, CP_OEMCP), L'\n');
  std::wstring preflight, thrown;
  for (size_t i = 0; i < lines.size(); ++i) {
    std::wstring l = Trim(lines[i]);
    if (l.rfind(L"PREFLIGHT: ", 0) == 0) preflight += L"\n" + l.substr(11);
    if (thrown.empty() && l.rfind(L"At ", 0) == 0 && l.find(L"play.ps1:") != std::wstring::npos) {
      // The thrown text is the block of non-empty lines just above (PowerShell may wrap a long message).
      size_t j = i;
      while (j > 0 && Trim(lines[j - 1]).empty()) --j;
      size_t end = j;
      while (j > 0 && !Trim(lines[j - 1]).empty() && Trim(lines[j - 1]).rfind(L"PREFLIGHT: ", 0) != 0) --j;
      for (size_t k = j; k < end; ++k) thrown += (thrown.empty() ? L"" : L" ") + Trim(lines[k]);
    }
  }
  if (!preflight.empty()) return preflight.substr(1);
  if (!thrown.empty()) {
    size_t refused = thrown.find(L"Settings refused");
    if (refused != std::wstring::npos)  // the resolver's own stderr line may precede play.ps1's message
      thrown = thrown.substr(refused) + L"\n\nOpen Rayman 3 HD Settings and choose your settings again.";
    return thrown;
  }
  std::wstring tail = Trim(Widen(raw, CP_OEMCP));
  if (tail.size() > 800) tail = L"..." + tail.substr(tail.size() - 800);
  return tail.empty() ? L"The launcher stopped without a message." : tail;
}

// play.ps1 -UserHome HOME, hidden. Returns when the game has started, play.ps1 has ended, or after a timeout.
Launch StartGame(const Paths& p, bool dryRun, std::wstring& detail, void (*idle)() = nullptr) {
  HANDLE busy = CreateMutexW(nullptr, TRUE, kPlayMutex);
  if (busy && GetLastError() == ERROR_ALREADY_EXISTS) { CloseHandle(busy); return Launch::Busy; }
  struct Release { HANDLE h; ~Release() { if (h) { ReleaseMutex(h); CloseHandle(h); } } } release{busy};
  if (!dryRun && !GameProcesses().empty()) return Launch::AlreadyRunning;
  wchar_t sys[MAX_PATH];
  GetSystemDirectoryW(sys, MAX_PATH);
  std::wstring ps = std::wstring(sys) + L"\\WindowsPowerShell\\v1.0\\powershell.exe";
  std::wstring cacheDir = p.home + L"\\cache";
  CreateDirectoryW(cacheDir.c_str(), nullptr);
  std::wstring logPath = cacheDir + L"\\launcher_play.log";
  SECURITY_ATTRIBUTES sa{sizeof sa, nullptr, TRUE};
  HANDLE log = CreateFileW(logPath.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, &sa,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (log == INVALID_HANDLE_VALUE) { detail = T(L"The launch log could not be written. Check folder access."); return Launch::Failed; }
  HANDLE nul = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, nullptr);
  std::vector<std::wstring> args{L"-NoProfile", L"-NonInteractive", L"-ExecutionPolicy", L"Bypass", L"-File",
                                 p.tools + L"\\play.ps1", L"-UserHome", p.home};
  if (dryRun) args.push_back(L"-DryRun");
  std::wstring cmd = Quote(ps) + L" " + Join(args);
  STARTUPINFOW si{sizeof si};
  si.dwFlags = STARTF_USESTDHANDLES;
  si.hStdInput = nul;
  si.hStdOutput = log;
  si.hStdError = log;
  PROCESS_INFORMATION pi{};
  // The person started this launch: the game window may take the foreground when it opens.
  if (!dryRun) AllowSetForegroundWindow(ASFW_ANY);
  BOOL ok = CreateProcessW(ps.c_str(), &cmd[0], nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, p.home.c_str(),
                           &si, &pi);
  CloseHandle(log);
  if (nul != INVALID_HANDLE_VALUE) CloseHandle(nul);
  if (!ok) { detail = T(L"Windows PowerShell could not be started. Run setup to repair this installation."); return Launch::Failed; }
  Launch result = Launch::Started;
  ULONGLONG deadline = GetTickCount64() + kStartTimeoutMs;
  for (;;) {
    if (idle) idle();
    if (WaitForSingleObject(pi.hProcess, 200) == WAIT_OBJECT_0) {
      DWORD code = 1;
      GetExitCodeProcess(pi.hProcess, &code);
      std::string out = ReadFileBytes(logPath);
      if (code == 0) { result = Launch::Ended; detail = Widen(out, CP_OEMCP); }
      else { result = Launch::Failed; detail = PlayFailure(out); }
      break;
    }
    bool started = false;
    for (auto& g : GameProcesses()) started |= g.second == pi.dwProcessId;
    if (started) break;  // play.ps1 keeps running beside the game as its supervisor
    if (GetTickCount64() > deadline) {
      result = Launch::Slow;
      detail = T(L"The game is taking longer to start. Check cache/launcher_play.log.");
      break;
    }
  }
  CloseHandle(pi.hProcess);
  CloseHandle(pi.hThread);
  return result;
}

// ----------------------------------------------------------------------------------------------------- UI --

enum : int { kIdSave = 10, kIdPlay = 11, kIdFolder = 12, kIdControls = 13, kIdPageSettings = 14, kIdAdvanced = 15,
              kIdLayout = 16, kIdRestoreKeys = 17, kIdLanguage = 18, kIdMods = 19, kIdModList = 20, kIdModZip = 21,
              kIdModFolder = 22, kIdModToggle = 23, kIdModUp = 24, kIdModDown = 25, kIdModRemove = 26, kIdRadio = 100,
              kIdSetting = 200, kIdKey = 400 };
enum class Page { Settings, Controls, Advanced, Mods };

struct Ui {
  Paths paths;
  Model model;
  HWND hwnd = nullptr;
  int dpi = 96, forcedDpi = 0, scrollY = 0, contentHeight = 0;
  HFONT body = nullptr, bold = nullptr, title = nullptr;
  HBRUSH background = nullptr;
  HICON icon = nullptr;
  HWND titleText = nullptr, versionText = nullptr, homeText = nullptr, banner = nullptr, rule1 = nullptr,
       rule2 = nullptr, status = nullptr, saveButton = nullptr, playButton = nullptr, folderButton = nullptr,
       closeButton = nullptr, profileHint = nullptr;
  HWND radios[3] = {}, radioText[3] = {}, lastFocus = nullptr;
  // M32 (D-069): three pages in one window: settings, the keyboard (Controls) and Advanced (troubleshooting).
  HWND controlsButton = nullptr, settingsButton = nullptr, advancedButton = nullptr;
  HWND controlsTitle = nullptr, layoutTitle = nullptr, layoutBox = nullptr, restoreKeys = nullptr,
       controlsNote = nullptr, keyHead[4] = {}, controlsRule = nullptr;
  HWND advancedTitle = nullptr, advancedText = nullptr, languageTitle = nullptr, languageBox = nullptr;

  std::vector<HWND> settingsPage, controlsPage, advancedPage, modsPage;
  // M33 (D-070): the Mods page (rows of r3hd_mods.py list, read when the page is first shown).
  HWND modsButton = nullptr, modsTitle = nullptr, modsText = nullptr, modList = nullptr, modDetail = nullptr,
       modZip = nullptr, modFolder = nullptr, modToggle = nullptr, modUp = nullptr, modDown = nullptr, modRemove = nullptr,
       modsNote = nullptr;
  std::vector<ModRow> mods;
  bool modsLoaded = false;
  std::wstring modsError;
  std::map<std::wstring, HWND> keyGroupTitles;
  Page page = Page::Settings;
  // The keys the Controls page shows (input id -> slots) and the layout they start from.
  std::map<std::wstring, Slots> keys;
  std::wstring keyLayout;
  // M43 (D-080): the point the window keeps as its centre when a page of another height is shown: the work area's
  // centre at start, the window's own centre once a person has moved it, the system's rectangle after a DPI change.
  POINT anchor{};
  bool userPlaced = false;
  RECT placed{};      // where Fit last put the window: a move loop that ends there (a click on the title bar) is no move
  RECT forcedWork{};  // --ui-test `workarea`: a smaller screen's work area (empty: the monitor's)
  int captureInput = -1, captureSlot = 0;  // -1: no key capture
  std::map<std::wstring, HWND> groupTitle;
  std::vector<HWND> secondary;  // grey help text
  bool bannerError = false, statusError = false, dirty = false, testMode = false;
  int profile = 0;           // 0 vanilla, 1 hdplus, 2 custom
  int shownFixed = 0;        // the fixed preset the corrections showed before Custom was chosen
  bool haveCustom = false;   // custom choices exist (saved, or made in this session)
  std::wstring customBase = L"vanilla";
  std::map<std::wstring, std::wstring> chosen;  // what the controls show
  std::map<std::wstring, std::wstring> customValues;
  std::vector<std::wstring> log;  // --ui-test journal
};

Ui g;

int S(int v) { return MulDiv(v, g.dpi, 96); }

const wchar_t* PresetKey(int i) { return i == 0 ? L"vanilla" : i == 1 ? L"hdplus" : L"custom"; }

void Note(const std::wstring& s) { if (g.testMode) g.log.push_back(s); }

int Ask(const std::wstring& text, UINT flags, int testAnswer) {
  if (g.testMode) { Note(L"dialog: " + text); return testAnswer; }  // never a modal box on the private desktop
  return MessageBoxW(g.hwnd, text.c_str(), T(L"Rayman 3 HD Settings").c_str(), flags);
}

void CreateFonts() {
  for (HFONT* f : {&g.body, &g.bold, &g.title}) if (*f) { DeleteObject(*f); *f = nullptr; }
  NONCLIENTMETRICSW ncm{sizeof ncm};
  using Fn = BOOL(WINAPI*)(UINT, UINT, PVOID, UINT, UINT);
  auto forDpi = (Fn)GetProcAddress(GetModuleHandleW(L"user32.dll"), "SystemParametersInfoForDpi");
  if (!(forDpi && forDpi(SPI_GETNONCLIENTMETRICS, sizeof ncm, &ncm, 0, g.dpi))) {
    SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof ncm, &ncm, 0);
    HDC dc = GetDC(nullptr);
    ncm.lfMessageFont.lfHeight = MulDiv(ncm.lfMessageFont.lfHeight, g.dpi, GetDeviceCaps(dc, LOGPIXELSY));
    ReleaseDC(nullptr, dc);
  }
  LOGFONTW lf = ncm.lfMessageFont;
  g.body = CreateFontIndirectW(&lf);
  lf.lfWeight = FW_SEMIBOLD;
  g.bold = CreateFontIndirectW(&lf);
  lf.lfHeight = lf.lfHeight * 3 / 2;
  g.title = CreateFontIndirectW(&lf);
}

// Settings uses resource 2, matching its shortcuts (MIT Fluent gear).
HICON LoadAppIcon(HINSTANCE inst, int metric) {
  int size = GetSystemMetrics(metric);
  return (HICON)LoadImageW(inst, MAKEINTRESOURCEW(2), IMAGE_ICON, size, size, LR_DEFAULTCOLOR | LR_SHARED);
}

HWND Make(const wchar_t* cls, const std::wstring& text, DWORD style, int id = 0) {
  HWND h = CreateWindowExW(0, cls, T(text).c_str(), WS_CHILD | WS_VISIBLE | style, 0, 0, 10, 10, g.hwnd,
                           (HMENU)(INT_PTR)id, GetModuleHandleW(nullptr), nullptr);
  return h;
}

HWND Text(const std::wstring& text, bool grey = false) {
  HWND h = Make(L"STATIC", text, SS_LEFT | SS_NOPREFIX);
  if (grey) g.secondary.push_back(h);
  return h;
}

Setting* Find(int id) {
  int i = id - kIdSetting;
  return i >= 0 && i < (int)g.model.settings.size() ? &g.model.settings[i] : nullptr;
}

std::wstring SettingLabel(const Setting& s) {
  return s.note.empty() ? T(s.label) : T(s.label) + L" (" + T(s.note) + L")";
}

void BuildControls() {
  g.titleText = Make(L"STATIC", L"Rayman 3 HD Recompiled", SS_LEFT | SS_NOPREFIX);
  g.versionText = Make(L"STATIC", L"", SS_RIGHT | SS_NOPREFIX);
  g.secondary.push_back(g.versionText);
  g.homeText = Make(L"STATIC", L"", SS_LEFT | SS_NOPREFIX | SS_PATHELLIPSIS);
  g.secondary.push_back(g.homeText);
  g.banner = Text(L"");
  g.rule1 = Make(L"STATIC", L"", SS_ETCHEDHORZ);
  g.groupTitle[L"profile"] = Make(L"STATIC", T(L"Game profile"), SS_LEFT | SS_NOPREFIX);
  for (int i = 0; i < 3; ++i) {
    const Preset& p = g.model.presets[i];
    g.radios[i] = Make(L"BUTTON", p.name, BS_AUTORADIOBUTTON | WS_TABSTOP | (i == 0 ? WS_GROUP : 0), kIdRadio + i);
    g.radioText[i] = Text(p.text, true);
  }
  g.profileHint = Text(T(L"Saving Vanilla or HD+ drops Custom choices. Display settings and gameplay "
                       L"subtitles apply to every profile."), true);
  g.settingsPage.push_back(g.groupTitle[L"profile"]);
  for (int i = 0; i < 3; ++i) { g.settingsPage.push_back(g.radios[i]); g.settingsPage.push_back(g.radioText[i]); }
  g.settingsPage.push_back(g.profileHint);
  bool firstInGroup = true;
  for (const auto& gr : g.model.groups) {
    if (!g.groupTitle.count(gr.first)) g.groupTitle[gr.first] = Make(L"STATIC", gr.second, SS_LEFT | SS_NOPREFIX);
    // M32: the troubleshooting group lives on the Advanced page, out of the everyday settings.
    std::vector<HWND>& pageList = gr.first == L"advanced" ? g.advancedPage : g.settingsPage;
    pageList.push_back(g.groupTitle[gr.first]);
    for (size_t i = 0; i < g.model.settings.size(); ++i) {
      Setting& s = g.model.settings[i];
      if (s.group != gr.first) continue;
      int id = kIdSetting + (int)i;
      if (s.slider) {
        s.title = Make(L"STATIC", SettingLabel(s), SS_LEFT | SS_NOPREFIX);  // before the bar: its accessible name
        s.control = Make(TRACKBAR_CLASSW, L"", TBS_HORZ | TBS_NOTICKS | TBS_DOWNISLEFT | WS_TABSTOP | WS_GROUP, id);
        SendMessageW(s.control, TBM_SETRANGE, TRUE, MAKELPARAM(0, (int)s.values.size() - 1));
        SendMessageW(s.control, TBM_SETLINESIZE, 0, 1);
        SendMessageW(s.control, TBM_SETPAGESIZE, 0, 10);
        s.valueText = Make(L"STATIC", L"", SS_RIGHT | SS_NOPREFIX);
      } else if (s.Toggle()) {
        s.control = Make(L"BUTTON", SettingLabel(s), BS_AUTOCHECKBOX | WS_TABSTOP | (firstInGroup ? WS_GROUP : 0), id);
      } else {
        s.title = Make(L"STATIC", SettingLabel(s), SS_LEFT | SS_NOPREFIX);  // before its box: the box's accessible name
        s.control = Make(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP | WS_GROUP, id);
        for (const auto& v : s.values) SendMessageW(s.control, CB_ADDSTRING, 0, (LPARAM)T(v.label).c_str());
      }
      firstInGroup = false;
      // D-090: a correction check box that is a preference (gameplay subtitles) is clear from its label alone
      if (!s.help.empty() && !(s.Toggle() && s.scope == L"preference")) s.helpText = Text(s.help, true);
      for (HWND h : {s.title, s.control, s.valueText, s.helpText}) if (h) pageList.push_back(h);
    }
  }
  // M32 (D-069): the Controls page: a layout, then one row per pad input with two key buttons (the keyboard map of
  // the model's KEY* rows). M43 (D-080): inputs not yet characterised are not shown at all; their keys stay in the map
  // (saved, restored with a layout, part of the conflict check), so a later milestone can show them once named.
  g.controlsTitle = Make(L"STATIC", T(L"Keyboard"), SS_LEFT | SS_NOPREFIX);
  g.groupTitle[L"controls"] = g.controlsTitle;
  g.layoutTitle = Make(L"STATIC", T(L"Layout"), SS_LEFT | SS_NOPREFIX);
  g.layoutBox = Make(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP | WS_GROUP, kIdLayout);
  for (const auto& l : g.model.layouts) SendMessageW(g.layoutBox, CB_ADDSTRING, 0, (LPARAM)T(l.name).c_str());
  g.restoreKeys = Make(L"BUTTON", T(L"&Restore defaults"), BS_PUSHBUTTON | WS_TABSTOP | WS_GROUP, kIdRestoreKeys);
  const std::wstring heads[4] = {T(L"Action"), T(L"Controller"), T(L"Key"), T(L"Second key")};
  for (int c = 0; c < 4; ++c) {
    g.keyHead[c] = Make(L"STATIC", heads[c], SS_LEFT | SS_NOPREFIX);
    g.groupTitle[L"controls.head" + std::to_wstring(c)] = g.keyHead[c];  // bold, like a group title
  }
  g.controlsRule = Make(L"STATIC", L"", SS_ETCHEDHORZ);
  g.controlsPage = {g.controlsTitle, g.layoutTitle, g.layoutBox, g.restoreKeys, g.keyHead[0], g.keyHead[1],
                    g.keyHead[2], g.keyHead[3], g.controlsRule};
  for (const auto& kg : g.model.keyGroups) {
    HWND t = Make(L"STATIC", kg.second, SS_LEFT | SS_NOPREFIX);
    g.keyGroupTitles[kg.first] = t;
    g.groupTitle[L"keys." + kg.first] = t;
    g.controlsPage.push_back(t);
    for (size_t i = 0; i < g.model.keyInputs.size(); ++i) {
      KeyInput& in = g.model.keyInputs[i];
      if (in.group != kg.first) continue;
      in.text = Text(in.action);
      in.padText = Text(in.pad, true);
      for (int s = 0; s < 2; ++s)
        in.button[s] = Make(L"BUTTON", L"", BS_PUSHBUTTON | WS_TABSTOP | (i == 0 && s == 0 ? WS_GROUP : 0),
                            kIdKey + (int)i * 2 + s);
      for (HWND h : {in.text, in.padText, in.button[0], in.button[1]}) g.controlsPage.push_back(h);
    }
  }
  g.controlsNote = Text(T(L"Click a key to change it, then press the new key (Esc cancels). Right-click a key or press "
                        L"Delete to remove it. ") + T(g.model.keyNote), true);
  g.controlsPage.push_back(g.controlsNote);
  // M32: Advanced holds the troubleshooting settings (registry group "advanced") and the installation folder.
  g.advancedTitle = Make(L"STATIC", T(L"Advanced"), SS_LEFT | SS_NOPREFIX);
  g.groupTitle[L"advanced.page"] = g.advancedTitle;
  g.advancedText = Text(T(L"For troubleshooting. You do not need to change anything here to play."), true);
  g.folderButton = Make(L"BUTTON", T(L"Open the installation &folder"), BS_PUSHBUTTON | WS_TABSTOP | WS_GROUP, kIdFolder);
  g.languageTitle = Make(L"STATIC", T(L"Interface language"), SS_RIGHT | SS_NOPREFIX);
  g.languageBox = Make(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_TABSTOP, kIdLanguage);
  SendMessageW(g.languageBox, CB_ADDSTRING, 0, (LPARAM)L"English");
  SendMessageW(g.languageBox, CB_ADDSTRING, 0, (LPARAM)L"Türkçe");
  SendMessageW(g.languageBox, CB_SETCURSEL, uiLanguage == L"tr" ? 1 : 0, 0);
  g.advancedPage.insert(g.advancedPage.begin(), {g.advancedTitle, g.advancedText});
  g.advancedPage.push_back(g.folderButton);
  // M33 (D-070): Mods: the installed data mods, in priority order (the first wins where two change the same thing).
  g.modsTitle = Make(L"STATIC", T(L"Mods"), SS_LEFT | SS_NOPREFIX);
  g.groupTitle[L"mods.page"] = g.modsTitle;
  g.modsText = Text(T(L"Community mods that replace textures or text. They never change your game files or saves, and "
                    L"Vanilla, HD+ and Custom stay as they are. Only data mods are accepted: no programs or scripts."), true);
  g.modList = Make(WC_LISTBOXW, L"", LBS_NOTIFY | LBS_NOINTEGRALHEIGHT | WS_VSCROLL | WS_HSCROLL | WS_BORDER | WS_TABSTOP |
                   WS_GROUP, kIdModList);
  // M43 (D-080): the selected mod's details in a read-only box of a fixed height that scrolls, so a long description
  // (or a long name, or a long reason it is not applied) is never cut off and the page never changes height.
  g.modDetail = Make(L"EDIT", L"", ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL | WS_VSCROLL | WS_BORDER | WS_TABSTOP);
  g.modZip = Make(L"BUTTON", T(L"&Install .zip..."), BS_PUSHBUTTON | WS_TABSTOP | WS_GROUP, kIdModZip);
  g.modFolder = Make(L"BUTTON", T(L"Install &folder..."), BS_PUSHBUTTON | WS_TABSTOP, kIdModFolder);
  g.modToggle = Make(L"BUTTON", T(L"&Enable"), BS_PUSHBUTTON | WS_TABSTOP, kIdModToggle);
  g.modUp = Make(L"BUTTON", T(L"&Up"), BS_PUSHBUTTON | WS_TABSTOP, kIdModUp);
  g.modDown = Make(L"BUTTON", T(L"&Down"), BS_PUSHBUTTON | WS_TABSTOP, kIdModDown);
  g.modRemove = Make(L"BUTTON", T(L"&Remove"), BS_PUSHBUTTON | WS_TABSTOP, kIdModRemove);
  g.modsNote = Text(T(L"Changes apply the next time the game starts. A mod that does not fit this game version is not "
                    L"applied and the reason is shown here."), true);
  g.modsPage = {g.modsTitle, g.modsText, g.modList, g.modDetail, g.modZip, g.modFolder, g.modToggle, g.modUp, g.modDown,
                g.modRemove, g.modsNote};
  g.rule2 = Make(L"STATIC", L"", SS_ETCHEDHORZ);
  g.status = Text(L"");
  // The page selector: push-like radio buttons, the shown page's one pressed.
  g.settingsButton = Make(L"BUTTON", T(L"Se&ttings"), BS_AUTORADIOBUTTON | BS_PUSHLIKE | WS_TABSTOP | WS_GROUP, kIdPageSettings);
  g.controlsButton = Make(L"BUTTON", T(L"&Controls"), BS_AUTORADIOBUTTON | BS_PUSHLIKE, kIdControls);
  g.advancedButton = Make(L"BUTTON", T(L"&Advanced"), BS_AUTORADIOBUTTON | BS_PUSHLIKE, kIdAdvanced);
  g.modsButton = Make(L"BUTTON", T(L"&Mods"), BS_AUTORADIOBUTTON | BS_PUSHLIKE, kIdMods);
  g.saveButton = Make(L"BUTTON", T(L"&Save"), BS_PUSHBUTTON | WS_TABSTOP | WS_GROUP, kIdSave);
  g.playButton = Make(L"BUTTON", T(L"&Play"), BS_DEFPUSHBUTTON | WS_TABSTOP | WS_GROUP, kIdPlay);
  g.closeButton = Make(L"BUTTON", T(L"Close"), BS_PUSHBUTTON | WS_TABSTOP | WS_GROUP, IDCANCEL);
}

void ApplyFonts() {
  EnumChildWindows(g.hwnd, [](HWND h, LPARAM) -> BOOL { SendMessageW(h, WM_SETFONT, (WPARAM)g.body, TRUE); return TRUE; }, 0);
  SendMessageW(g.titleText, WM_SETFONT, (WPARAM)g.title, TRUE);
  for (auto& t : g.groupTitle) SendMessageW(t.second, WM_SETFONT, (WPARAM)g.bold, TRUE);
}

int Measure(HWND h, HFONT font, int width) {
  wchar_t buf[2048];
  GetWindowTextW(h, buf, (int)std::size(buf));
  HDC dc = GetDC(g.hwnd);
  HGDIOBJ old = SelectObject(dc, font);
  RECT r{0, 0, width, 0};
  DrawTextW(dc, buf[0] ? buf : L" ", -1, &r, DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX | DT_EDITCONTROL);
  SelectObject(dc, old);
  ReleaseDC(g.hwnd, dc);
  return r.bottom;
}

int LineHeight(HFONT font) {
  HDC dc = GetDC(g.hwnd);
  HGDIOBJ old = SelectObject(dc, font);
  TEXTMETRICW tm{};
  GetTextMetricsW(dc, &tm);
  SelectObject(dc, old);
  ReleaseDC(g.hwnd, dc);
  return tm.tmHeight;
}

// Places every control for the current DPI and scroll position; returns the content height (pixels).
int Layout() {
  const int margin = S(20), gap = S(28), width = S(kWidth);
  const int col = (width - 2 * margin - gap) / 2;
  const int line = LineHeight(g.body);
  const int rowH = std::max(line + S(6), S(24));
  HDWP dwp = BeginDeferWindowPos(64);
  auto put = [&](HWND h, int x, int y, int w, int hgt) {
    // SWP_NOCOPYBITS: a moved control repaints instead of carrying its old pixels (M31: the list's header left a copy).
    if (h) dwp = DeferWindowPos(dwp, h, nullptr, x, y - g.scrollY, w, hgt, SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOCOPYBITS);
  };
  int y = S(16);
  int th = Measure(g.titleText, g.title, width);
  put(g.titleText, margin, y, col + gap, th);
  put(g.versionText, margin + col + gap, y + th - line - S(2), col, line);
  y += th + S(2);
  // Persistent header: locale is explicitly an interface choice, separate from game settings.
  int languageX = width - margin - S(150);
  put(g.homeText, margin, y + (rowH - line) / 2, col, line);
  put(g.languageTitle, languageX - S(148), y + (rowH - line) / 2, S(140), line);
  put(g.languageBox, languageX, y, S(150), rowH + S(80));
  y += rowH + S(1);
  int bh = Measure(g.banner, g.body, width - 2 * margin);
  put(g.banner, margin, y, width - 2 * margin, bh);
  y += bh + S(12);
  put(g.rule1, margin, y, width - 2 * margin, S(2));
  const int top = y + S(14);
  int bottom = top;
  std::vector<HWND> hidden;  // controls of the shown page that stay hidden (inputs not shown)
  if (g.page == Page::Controls) {
    // M32: layout row, then a table: action, controller input, two key buttons; one group title per keymap group.
    int full = width - 2 * margin;
    int ch = Measure(g.controlsTitle, g.bold, full);
    put(g.controlsTitle, margin, top, full, ch);
    int ly2 = top + ch + S(8);
    const int lw = S(70), cbw = S(240), rbw = S(150);
    int lh = Measure(g.layoutTitle, g.body, lw);
    put(g.layoutTitle, margin, ly2 + std::max(0, (rowH - lh) / 2), lw, lh);
    put(g.layoutBox, margin + lw + S(8), ly2, cbw, rowH + S(120));
    put(g.restoreKeys, margin + lw + S(16) + cbw, ly2 - S(1), rbw, rowH + S(2));
    ly2 += rowH + S(12);
    const int cgap = S(10), kw = S(130);
    const int cw[4] = {full - S(150) - 2 * kw - 3 * cgap, S(150), kw, kw};
    const int cx[4] = {margin, margin + cw[0] + cgap, margin + cw[0] + cw[1] + 2 * cgap,
                       margin + cw[0] + cw[1] + cw[2] + 3 * cgap};
    int hh2 = 0;
    for (int c = 0; c < 4; ++c) hh2 = std::max(hh2, Measure(g.keyHead[c], g.bold, cw[c]));
    for (int c = 0; c < 4; ++c) put(g.keyHead[c], cx[c], ly2, cw[c], hh2);
    ly2 += hh2 + S(4);
    put(g.controlsRule, margin, ly2, full, S(2));
    ly2 += S(8);
    for (const auto& kg : g.model.keyGroups) {
      bool any = false;
      for (const auto& in : g.model.keyInputs) any |= in.group == kg.first && !in.hidden;
      HWND t = g.keyGroupTitles[kg.first];
      if (!any) {
        hidden.push_back(t);
        for (auto& in : g.model.keyInputs)
          if (in.group == kg.first) for (HWND h : {in.text, in.padText, in.button[0], in.button[1]}) hidden.push_back(h);
        continue;
      }
      int gh = Measure(t, g.bold, full);
      put(t, margin, ly2, full, gh);
      ly2 += gh + S(4);
      for (auto& in : g.model.keyInputs) {
        if (in.group != kg.first) continue;
        if (in.hidden) {
          for (HWND h : {in.text, in.padText, in.button[0], in.button[1]}) hidden.push_back(h);
          continue;
        }
        int th2 = std::max(Measure(in.text, g.body, cw[0]), Measure(in.padText, g.body, cw[1]));
        int rh = std::max(th2, rowH);
        put(in.text, cx[0], ly2 + std::max(0, (rh - Measure(in.text, g.body, cw[0])) / 2), cw[0], Measure(in.text, g.body, cw[0]));
        put(in.padText, cx[1], ly2 + std::max(0, (rh - Measure(in.padText, g.body, cw[1])) / 2), cw[1], Measure(in.padText, g.body, cw[1]));
        for (int s = 0; s < 2; ++s) put(in.button[s], cx[2 + s], ly2 + (rh - rowH) / 2, cw[2 + s], rowH);
        ly2 += rh + S(3);
      }
      ly2 += S(8);
    }
    int nh = Measure(g.controlsNote, g.body, full);
    put(g.controlsNote, margin, ly2, full, nh);
    bottom = ly2 + nh;
  } else if (g.page == Page::Advanced) {
    // M32: the troubleshooting settings and the folder, in one column.
    int full = width - 2 * margin, ay = top;
    int ah = Measure(g.advancedTitle, g.bold, full);
    put(g.advancedTitle, margin, ay, full, ah);
    ay += ah + S(4);
    int atx = Measure(g.advancedText, g.body, full);
    put(g.advancedText, margin, ay, full, atx);
    ay += atx + S(14);
    for (const auto& gr : g.model.groups) {
      if (gr.first != L"advanced") continue;
      HWND ht = g.groupTitle[gr.first];
      int gh = Measure(ht, g.bold, col);
      put(ht, margin, ay, col, gh);
      ay += gh + S(8);
      for (auto& s : g.model.settings) {
        if (s.group != gr.first) continue;
        if (s.Toggle()) {  // (none today: the troubleshooting group holds preferences only)
          int ch2 = std::max(Measure(s.control, g.body, col - S(22)), rowH - S(4));
          put(s.control, margin, ay, col, ch2);
          ay += ch2 + S(10);
          continue;
        }
        int lw2 = S(150), lh2 = Measure(s.title, g.body, lw2);
        put(s.title, margin, ay + std::max(0, (rowH - lh2) / 2), lw2, lh2);
        if (s.slider) {  // D-108: label, bar, value ("30%") in one row
          int vw = S(48), bw2 = col - lw2 - S(8) - vw - S(6);
          put(s.control, margin + lw2 + S(8), ay, bw2, rowH);
          int vh = Measure(s.valueText, g.body, vw);
          put(s.valueText, margin + lw2 + S(8) + bw2 + S(6), ay + std::max(0, (rowH - vh) / 2), vw, vh);
        } else {
          put(s.control, margin + lw2 + S(8), ay, col - lw2 - S(8), rowH + S(200));
        }
        ay += std::max(rowH, lh2) + S(4);
        if (s.helpText) { int hh3 = Measure(s.helpText, g.body, full); put(s.helpText, margin, ay, full, hh3); ay += hh3; }
        ay += S(10);
      }
    }
    put(g.folderButton, margin, ay + S(6), S(240), S(30));
    bottom = ay + S(36);
  } else if (g.page == Page::Mods) {
    // M33: title, text, the list with its buttons on the right, the selected mod's details, the note.
    int full = width - 2 * margin, my = top;
    int mh = Measure(g.modsTitle, g.bold, full);
    put(g.modsTitle, margin, my, full, mh);
    my += mh + S(4);
    int mt = Measure(g.modsText, g.body, full);
    put(g.modsText, margin, my, full, mt);
    my += mt + S(12);
    const int bw2 = S(150), listW = full - bw2 - S(12), listH = S(190);
    put(g.modList, margin, my, listW, listH);
    {  // M43: a list line longer than the list scrolls sideways instead of being cut off (widths at this DPI)
      int widest = 0, n = (int)SendMessageW(g.modList, LB_GETCOUNT, 0, 0);
      HDC dc = GetDC(g.hwnd);
      HGDIOBJ old = SelectObject(dc, g.body);
      for (int i = 0; i < n; ++i) {
        std::wstring item((size_t)std::max(0, (int)SendMessageW(g.modList, LB_GETTEXTLEN, i, 0)) + 1, L'\0');
        int len = (int)SendMessageW(g.modList, LB_GETTEXT, i, (LPARAM)item.data());
        SIZE sz{};
        if (len > 0 && GetTextExtentPoint32W(dc, item.c_str(), len, &sz)) widest = std::max(widest, (int)sz.cx);
      }
      SelectObject(dc, old);
      ReleaseDC(g.hwnd, dc);
      SendMessageW(g.modList, LB_SETHORIZONTALEXTENT, widest + S(8), 0);
    }
    int by = my;
    for (HWND b : {g.modZip, g.modFolder}) { put(b, margin + listW + S(12), by, bw2, S(30)); by += S(36); }
    by += S(8);
    for (HWND b : {g.modToggle, g.modUp, g.modDown, g.modRemove}) { put(b, margin + listW + S(12), by, bw2, S(28)); by += S(32); }
    my += std::max(listH, by - my) + S(10);
    const int dh = line * 6 + S(8);  // six lines; more scroll inside the box
    put(g.modDetail, margin, my, full, dh);
    my += dh + S(8);
    int nh2 = Measure(g.modsNote, g.body, full);
    put(g.modsNote, margin, my, full, nh2);
    bottom = my + nh2;
  } else {
    // Left column: profile and corrections.
    int x = margin, ly = top, hh = Measure(g.groupTitle[L"profile"], g.bold, col);
    put(g.groupTitle[L"profile"], x, ly, col, hh);
    ly += hh + S(8);
    for (int i = 0; i < 3; ++i) {
      put(g.radios[i], x, ly, col, rowH - S(4));
      ly += rowH - S(4);
      int dh = Measure(g.radioText[i], g.body, col - S(22));
      put(g.radioText[i], x + S(22), ly, col - S(22), dh);
      ly += dh + S(8);
    }
    int ph = Measure(g.profileHint, g.body, col);
    put(g.profileHint, x, ly, col, ph);
    ly += ph;
    // The corrections group continues the left column (it belongs to the profile); the other groups fill the right.
    int rx = margin + col + gap, ry = top;
    for (const auto& gr : g.model.groups) {
      if (gr.first == L"advanced") continue;  // M32: on the Advanced page
      bool left = gr.first == L"corrections";
      int& cy = left ? ly : ry;
      int cx = left ? x : rx;
      if (left) cy += S(12);  // D-090: room for the gameplay subtitles check box
      else if (cy != top) cy += S(18);
      HWND ht = g.groupTitle[gr.first];
      int gh = Measure(ht, g.bold, col);
      put(ht, cx, cy, col, gh);
      cy += gh + S(8);
      for (auto& s : g.model.settings) {
        if (s.group != gr.first) continue;
        if (s.Toggle()) {
          int ch = std::max(Measure(s.control, g.body, col - S(22)), rowH - S(4));
          put(s.control, cx, cy, col, ch);
          cy += ch;
          if (s.helpText) {
            int hh2 = Measure(s.helpText, g.body, col - S(22));
            put(s.helpText, cx + S(22), cy, col - S(22), hh2);
            cy += hh2;
          }
          cy += S(10);
        } else {
          int lw = S(150);
          int lh = Measure(s.title, g.body, lw);
          put(s.title, cx, cy + std::max(0, (rowH - lh) / 2), lw, lh);
          put(s.control, cx + lw + S(8), cy, col - lw - S(8), rowH + S(200));  // the height includes the list
          cy += std::max(rowH, lh) + S(4);
          if (s.helpText) {
            int hh2 = Measure(s.helpText, g.body, col);
            put(s.helpText, cx, cy, col, hh2);
            cy += hh2;
          }
          cy += S(10);
        }
      }
    }
    bottom = std::max(ly, ry);
  }
  y = bottom + S(8);
  put(g.rule2, margin, y, width - 2 * margin, S(2));
  y += S(12);
  int sh = Measure(g.status, g.body, width - 2 * margin);
  put(g.status, margin, y, width - 2 * margin, std::max(sh, line));
  y += std::max(sh, line) + S(10);
  const int bw = S(100), bhgt = S(30), bgap = S(8);
  put(g.settingsButton, margin, y, bw, bhgt);
  put(g.controlsButton, margin + bw + bgap, y, bw, bhgt);
  put(g.advancedButton, margin + 2 * (bw + bgap), y, bw, bhgt);
  put(g.modsButton, margin + 3 * (bw + bgap), y, bw, bhgt);
  put(g.closeButton, width - margin - bw, y, bw, bhgt);
  put(g.playButton, width - margin - 2 * bw - bgap, y, bw, bhgt);
  put(g.saveButton, width - margin - 3 * bw - 2 * bgap, y, bw, bhgt);
  y += bhgt + S(16);
  EndDeferWindowPos(dwp);
  auto show = [&](const std::vector<HWND>& list, bool on) {
    for (HWND h : list)
      ShowWindow(h, on && std::find(hidden.begin(), hidden.end(), h) == hidden.end() ? SW_SHOWNA : SW_HIDE);
  };
  show(g.settingsPage, g.page == Page::Settings);
  show(g.controlsPage, g.page == Page::Controls);
  show(g.advancedPage, g.page == Page::Advanced);
  show(g.modsPage, g.page == Page::Mods);
  SendMessageW(g.settingsButton, BM_SETCHECK, g.page == Page::Settings ? BST_CHECKED : BST_UNCHECKED, 0);
  SendMessageW(g.controlsButton, BM_SETCHECK, g.page == Page::Controls ? BST_CHECKED : BST_UNCHECKED, 0);
  SendMessageW(g.advancedButton, BM_SETCHECK, g.page == Page::Advanced ? BST_CHECKED : BST_UNCHECKED, 0);
  SendMessageW(g.modsButton, BM_SETCHECK, g.page == Page::Mods ? BST_CHECKED : BST_UNCHECKED, 0);
  return y;
}

void SetText(HWND h, const std::wstring& s) { SetWindowTextW(h, T(s).c_str()); }

// The work area the window must stay inside: the monitor's (taskbar excluded), or the UI test's smaller screen.
RECT WorkArea() {
  if (!IsRectEmpty(&g.forcedWork)) return g.forcedWork;
  MONITORINFO mi{sizeof mi};
  GetMonitorInfoW(MonitorFromWindow(g.hwnd, MONITOR_DEFAULTTONEAREST), &mi);
  return mi.rcWork;
}

void CentreAnchor() {
  RECT wa = WorkArea();
  g.anchor = {(wa.left + wa.right) / 2, (wa.top + wa.bottom) / 2};
}

// Sizes the window to the shown page. M43 (D-080): `recentre` (a page change, a DPI change, the first show) puts the
// window's centre on g.anchor, so pages of different heights share one centre and switching back returns the window
// to where it was; any other call (a status line, a key capture, a mod list update) keeps the top-left corner. Either
// way the window stays inside the work area; a page taller than the work area scrolls.
void Fit(bool recentre = false) {
  g.contentHeight = Layout();
  RECT want{0, 0, S(kWidth), g.contentHeight};
  DWORD style = (DWORD)GetWindowLongPtrW(g.hwnd, GWL_STYLE) & ~WS_VSCROLL;
  using Fn = BOOL(WINAPI*)(LPRECT, DWORD, BOOL, DWORD, UINT);
  auto adjust = (Fn)GetProcAddress(GetModuleHandleW(L"user32.dll"), "AdjustWindowRectExForDpi");
  RECT frame = want;
  if (adjust) adjust(&frame, style, FALSE, 0, g.dpi); else AdjustWindowRectEx(&frame, style, FALSE, 0);
  RECT wa = WorkArea();
  int maxH = wa.bottom - wa.top;
  int w = frame.right - frame.left, h = frame.bottom - frame.top;
  // A UI test takes the same path (M43 follow-up, D-082): the M33 exception that kept the whole page in test mode
  // left a page taller than a real 1032 px work area outside it; the dump checks the layout against the whole page.
  bool scroll = h > maxH;
  if (scroll) { w += GetSystemMetrics(SM_CXVSCROLL); h = maxH; }
  SetWindowLongPtrW(g.hwnd, GWL_STYLE, style | (scroll ? WS_VSCROLL : 0));
  RECT cur;
  GetWindowRect(g.hwnd, &cur);
  int x = recentre ? g.anchor.x - w / 2 : cur.left, y = recentre ? g.anchor.y - h / 2 : cur.top;
  x = std::max<int>(wa.left, std::min<int>(x, wa.right - w));  // left / top win when the window is wider / taller
  int y0 = std::max<int>(wa.top, std::min<int>(y, wa.bottom - h));
  // SWP_NOCOPYBITS: a recentred window repaints instead of carrying its old client pixels to the new place.
  SetWindowPos(g.hwnd, nullptr, x, y0, w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOCOPYBITS);
  GetWindowRect(g.hwnd, &g.placed);
  if (scroll) {
    RECT client;
    GetClientRect(g.hwnd, &client);
    SCROLLINFO si{sizeof si, SIF_RANGE | SIF_PAGE | SIF_POS, 0, g.contentHeight - 1, (UINT)client.bottom, g.scrollY};
    SetScrollInfo(g.hwnd, SB_VERT, &si, TRUE);
  } else if (g.scrollY) {
    g.scrollY = 0;
    Layout();
  }
}

// Shows g.chosen in the controls; corrections are editable only in Custom.
void Show() {
  for (int i = 0; i < 3; ++i) SendMessageW(g.radios[i], BM_SETCHECK, i == g.profile ? BST_CHECKED : BST_UNCHECKED, 0);
  for (auto& s : g.model.settings) {
    const std::wstring& v = g.chosen[s.key];
    if (s.slider) {
      bool applies = s.requiresKey.empty() || g.chosen[s.requiresKey] == s.requiresValue;
      EnableWindow(s.control, (s.scope == L"preference" || g.profile == 2) && applies);
      EnableWindow(s.valueText, IsWindowEnabled(s.control));
      int idx = 0;
      for (size_t j = 0; j < s.values.size(); ++j) if (s.values[j].value == v) idx = (int)j;
      if ((int)SendMessageW(s.control, TBM_GETPOS, 0, 0) != idx) SendMessageW(s.control, TBM_SETPOS, TRUE, idx);
      SetWindowTextW(s.valueText, F(L"{n}%", {{L"n", v}}).c_str());
    } else if (s.Toggle()) {
      SendMessageW(s.control, BM_SETCHECK, v == s.values[1].value ? BST_CHECKED : BST_UNCHECKED, 0);
      EnableWindow(s.control, g.profile == 2 || s.scope == L"preference");  // D-090: a preference in any profile
    } else {
      // A preset setting changes only in Custom; M31: a setting that requires another one's value (the window size
      // needs the window mode) is shown disabled otherwise and keeps its value.
      bool applies = s.requiresKey.empty() || g.chosen[s.requiresKey] == s.requiresValue;
      EnableWindow(s.control, (s.scope == L"preference" || g.profile == 2) && applies);
      int idx = 0;
      for (size_t j = 0; j < s.values.size(); ++j) if (s.values[j].value == v) idx = (int)j;
      SendMessageW(s.control, CB_SETCURSEL, idx, 0);
    }
  }
  EnableWindow(g.saveButton, g.dirty && g.model.install == L"ok");
}

void SetStatus(const std::wstring& s, bool error = false) {
  g.statusError = error;
  SetText(g.status, s);
  Note(L"status: " + s);
  Fit();
  InvalidateRect(g.status, nullptr, TRUE);
}

// ------------------------------------------------------------------------------------------------- keyboard --
// M32 (D-069). Everything here works on the model's rows: which keys exist (with their scan codes), which are
// reserved and why, which inputs need a key, and every layout's keys. The engine validates again when saving.

const KeyName* FindKeyName(const std::wstring& name) {
  for (const auto& k : g.model.keyNames) if (k.name == name) return &k;
  return nullptr;
}

// The key a WM_KEYDOWN means, by its physical position (the runtime reads scan codes too, so a key keeps its place on
// every keyboard layout). Empty when the game cannot read it.
const KeyName* KeyFromMessage(WPARAM vk, LPARAM lp) {
  if (vk == VK_PAUSE) return nullptr;  // Pause shares scan code 45 with Num Lock and is not in the keymap
  UINT scan = (UINT)(lp >> 16) & 0xFF;
  bool ext = ((lp >> 24) & 1) != 0;
  if (scan == 0) {  // a synthesized key without a scan code
    UINT sc = MapVirtualKeyW((UINT)vk, MAPVK_VK_TO_VSC_EX);
    scan = sc & 0xFF;
    ext = (sc & 0xFF00) == 0xE000;
  }
  wchar_t code[8];
  swprintf(code, 8, ext ? L"E0%02X" : L"%02X", scan);
  for (const auto& k : g.model.keyNames)
    for (const auto& s : k.scans) if (_wcsicmp(s.c_str(), code) == 0) return &k;
  return nullptr;
}

// What the key is called on this keyboard (Windows' own name for that position), else the model's label.
std::wstring KeyLabel(const std::wstring& name) {
  if (name.empty()) return L"-";
  const KeyName* k = FindKeyName(name);
  if (!k) return name;
  if (!k->scans.empty()) {
    const std::wstring& s = k->scans.front();
    bool ext = s.size() == 4;
    UINT scan = (UINT)wcstoul(s.substr(ext ? 2 : 0).c_str(), nullptr, 16);
    wchar_t buf[64] = {};
    LONG lp = (LONG)((scan << 16) | (ext ? (1u << 24) : 0));
    // Letters, digits and punctuation take the keyboard layout's name; the others keep the model's short label.
    if (k->name.size() == 1 || k->label.size() == 1) {
      if (GetKeyNameTextW(lp, buf, (int)std::size(buf)) > 0) return buf;
    }
  }
  return T(k->label);
}

std::wstring InputName(const KeyInput& in) {
  std::wstring a = T(in.action);
  size_t cut = a.find_first_of(L";.");
  if (cut != std::wstring::npos) a = a.substr(0, cut);
  return a + L" (" + T(in.pad) + L")";
}

const KeyLayout* LayoutByKey(const std::wstring& key) {
  for (const auto& l : g.model.layouts) if (l.key == key) return &l;
  return nullptr;
}

// Empties last, so the first button always holds a key when the input has one.
void Compact(Slots& s) { if (s[0].empty() && !s[1].empty()) { s[0] = s[1]; s[1].clear(); } }

void ShowKeys() {
  for (size_t i = 0; i < g.model.keyInputs.size(); ++i) {
    KeyInput& in = g.model.keyInputs[i];
    for (int s = 0; s < 2; ++s) {
      std::wstring t = (int)i == g.captureInput && s == g.captureSlot ? T(L"Press a key...") : KeyLabel(g.keys[in.id][s]);
      SetText(in.button[s], t);
    }
  }
  for (size_t i = 0; i < g.model.layouts.size(); ++i)
    if (g.model.layouts[i].key == g.keyLayout) {
      SendMessageW(g.layoutBox, CB_SETCURSEL, i, 0);
    }
}

void EndCapture() {
  if (g.captureInput < 0) return;
  g.captureInput = -1;
  ShowKeys();
}

void StartCapture(int input, int slot) {
  g.captureInput = input;
  g.captureSlot = slot;
  ShowKeys();
  SetFocus(g.model.keyInputs[input].button[slot]);
  SetStatus(F(L"Press a key for {action}. Esc cancels.", {{L"action", InputName(g.model.keyInputs[input])}}));
}

void KeysChanged(const std::wstring& message, bool error = false) {
  g.dirty = true;
  EnableWindow(g.saveButton, g.model.install == L"ok");
  ShowKeys();
  SetStatus(message + (error ? L"" : T(L" Unsaved changes.")), error);
}

// Puts a key on (input, slot). A key another input uses moves here and that input gets this slot's old key in its
// place (a swap: nothing is lost and every key stays on one input), unless that would leave an input that needs a
// key without one: then nothing changes and the person is told why.
void AssignKey(int input, int slot, const KeyName& key) {
  KeyInput& in = g.model.keyInputs[input];
  Slots& mine = g.keys[in.id];
  if (!key.reserved.empty()) {
    SetStatus(F(L"{key} cannot be used: {reason}. Press another key or Esc.", {{L"key", T(key.label)}, {L"reason", T(key.reserved)}}), true);
    return;  // capture continues
  }
  EndCapture();
  if (mine[slot] == key.name) { SetStatus(F(L"{key} is already assigned here.", {{L"key", T(key.label)}})); return; }
  if (mine[1 - slot] == key.name) {
    std::swap(mine[0], mine[1]);
    Compact(mine);
    KeysChanged(F(L"{key} assigned to {action}.", {{L"key", KeyLabel(key.name)}, {L"action", InputName(in)}}));
    return;
  }
  for (auto& other : g.model.keyInputs) {
    if (other.id == in.id) continue;
    Slots& theirs = g.keys[other.id];
    for (int s = 0; s < 2; ++s) {
      if (theirs[s] != key.name) continue;
      std::wstring old = mine[slot];
      Slots after = theirs;
      after[s] = old;
      Compact(after);
      if (other.required && after[0].empty()) {
        SetStatus(F(L"{action} needs a key. Assign another key before moving {key}.", {{L"action", InputName(other)}, {L"key", KeyLabel(key.name)}}), true);
        return;
      }
      theirs = after;
      mine[slot] = key.name;
      Compact(mine);
      KeysChanged(F(L"Keys swapped: {from} / {to}.", {{L"from", InputName(other)}, {L"to", InputName(in)}}));
      return;
    }
  }
  mine[slot] = key.name;
  Compact(mine);
  KeysChanged(F(L"{key} assigned to {action}.", {{L"key", KeyLabel(key.name)}, {L"action", InputName(in)}}));
}

void ClearKey(int input, int slot) {
  KeyInput& in = g.model.keyInputs[input];
  Slots& mine = g.keys[in.id];
  if (mine[slot].empty()) return;
  Slots after = mine;
  after[slot].clear();
  Compact(after);
  if (in.required && after[0].empty()) {
    SetStatus(F(L"{action} needs at least one key.", {{L"action", InputName(in)}}), true);
    return;
  }
  std::wstring old = mine[slot];
  mine = after;
  KeysChanged(F(L"{key} removed from {action}.", {{L"key", KeyLabel(old)}, {L"action", InputName(in)}}));
}

void UseLayout(const std::wstring& key, const std::wstring& message) {
  const KeyLayout* l = LayoutByKey(key);
  if (!l) return;
  EndCapture();
  g.keyLayout = key;
  for (const auto& in : g.model.keyInputs) g.keys[in.id] = l->keys.count(in.id) ? l->keys.at(in.id) : Slots{};
  KeysChanged(message);
}

bool KeysDifferFromLayout() {
  const KeyLayout* l = LayoutByKey(g.keyLayout);
  for (const auto& in : g.model.keyInputs)
    if (!l || !l->keys.count(in.id) || l->keys.at(in.id) != g.keys[in.id]) return true;
  return false;
}

// The key message of the capture: true when it was used (the dialog manager must not see it).
bool CaptureFilter(const MSG& msg) {
  if (!IsWindow(g.hwnd)) return false;
  bool ours = msg.hwnd == g.hwnd || IsChild(g.hwnd, msg.hwnd);
  // The release of the key that ended a capture (F10 or Alt would otherwise start menu mode).
  static WPARAM swallowUp = 0;
  if (swallowUp && ours && (msg.message == WM_KEYUP || msg.message == WM_SYSKEYUP) && msg.wParam == swallowUp) {
    swallowUp = 0;
    return true;
  }
  if (g.captureInput >= 0) {
    if (!ours) return false;
    if (msg.message == WM_KEYDOWN || msg.message == WM_SYSKEYDOWN) {
      swallowUp = msg.wParam;
      if (msg.wParam == VK_ESCAPE) { EndCapture(); SetStatus(T(L"Key not changed.")); return true; }
      if ((msg.lParam >> 30) & 1) return true;  // auto-repeat of a held key
      const KeyName* k = KeyFromMessage(msg.wParam, msg.lParam);
      if (!k) { SetStatus(T(L"The game cannot read that key. Press another key, or Esc to cancel."), true); return true; }
      AssignKey(g.captureInput, g.captureSlot, *k);
      return true;
    }
    if (msg.message == WM_KEYUP || msg.message == WM_SYSKEYUP || msg.message == WM_CHAR || msg.message == WM_SYSCHAR)
      return true;
    if (msg.message == WM_LBUTTONDOWN || msg.message == WM_RBUTTONDOWN || msg.message == WM_NCLBUTTONDOWN) {
      bool same = msg.hwnd == g.model.keyInputs[g.captureInput].button[g.captureSlot];
      EndCapture();
      if (same) { SetStatus(T(L"Key not changed.")); return true; }  // a click on the capturing button cancels it
      SetStatus(T(L"Key not changed."));
      return false;  // the click itself still goes where it was aimed (another key button starts its capture)
    }
    return false;
  }
  // Delete on a focused key button removes that key.
  if (ours && msg.message == WM_KEYDOWN && msg.wParam == VK_DELETE) {
    int id = GetDlgCtrlID(msg.hwnd);
    if (id >= kIdKey && id < kIdKey + 2 * (int)g.model.keyInputs.size()) { ClearKey((id - kIdKey) / 2, (id - kIdKey) % 2); return true; }
  }
  return false;
}

bool Playable(std::wstring* why) {
  const Model& m = g.model;
  std::wstring w;
  if (m.install != L"ok")
    w = T(L"This installation needs repair. Run setup again and choose this folder.");
  else if (m.files != L"ok")
    w = F(L"Program files are missing ({file}). Run setup again to repair them.", {{L"file", m.filesFirst}});
  else if (m.data != L"ok")
    w = T(L"Game data needs repair. Run setup again; your game package may be needed.");
  else if (m.running)
    w = T(L"Rayman 3 HD is running. Saved changes apply next time it starts.");
  if (why) *why = w;
  return w.empty();
}

void UpdateBanner() {
  const Model& m = g.model;
  SetText(g.versionText, F(L"Version {version}", {{L"version", m.version}}));
  SetText(g.homeText, F(L"Installed in {folder}", {{L"folder", m.home}}));
  std::wstring why;
  bool ok = Playable(&why);
  std::wstring banner = ok ? T(L"Ready to play. Settings apply the next time the game starts.") : why;
  if (m.settingsState == L"invalid")
    banner += L"\n" + T(L"Saved settings could not be read. Save replaces them and keeps a backup.");
  if (m.lastFailed)
    banner += L"\n" + F(L"The last session ended unexpectedly. Logs: sessions\\{session}", {{L"session", m.lastStamp}});
  if (m.keyboardState == L"invalid")
    banner += L"\n" + T(L"Saved keys could not be used. Save replaces them and keeps a backup.");
  g.bannerError = !ok || m.settingsState == L"invalid" || m.keyboardState == L"invalid" || m.lastFailed;
  SetText(g.banner, banner);
  EnableWindow(g.playButton, ok);
}

void Populate() {
  const Model& m = g.model;
  UpdateBanner();
  g.profile = m.preset == L"hdplus" ? 1 : m.preset == L"custom" ? 2 : 0;
  g.haveCustom = m.preset == L"custom";
  g.customBase = m.preset == L"custom" ? m.base : L"vanilla";
  g.shownFixed = m.base == L"hdplus" ? 1 : 0;
  g.chosen.clear();
  g.customValues.clear();
  for (const auto& s : m.settings) {
    g.chosen[s.key] = s.current;
    if (s.scope == L"preset" && g.haveCustom) g.customValues[s.key] = s.current;
  }
  // M32: the saved keyboard map (or the layout the resolver fell back to).
  g.keyLayout = m.keyboardLayout;
  for (const auto& in : m.keyInputs) g.keys[in.id] = in.saved;
  g.captureInput = -1;
  ShowKeys();
  g.dirty = m.settingsState == L"invalid" || m.keyboardState == L"invalid";  // Save can replace an unreadable file
  Show();
}

void Changed() {
  g.dirty = true;
  Show();
  SetStatus(T(L"Unsaved changes."));
}

void ChooseProfile(int i) {
  if (i == g.profile) return;
  if (g.profile == 2) { for (auto& s : g.model.settings) if (s.scope == L"preset") g.customValues[s.key] = g.chosen[s.key]; }
  else g.shownFixed = g.profile;
  g.profile = i;
  if (i == 2 && !g.haveCustom) {
    // Custom starts from what the previous profile showed: nothing changes until the person changes it.
    g.customBase = PresetKey(g.shownFixed);
    for (auto& s : g.model.settings) if (s.scope == L"preset") g.customValues[s.key] = s.Column(g.customBase);
    g.haveCustom = true;
  }
  for (auto& s : g.model.settings)
    if (s.scope == L"preset") g.chosen[s.key] = i == 2 ? g.customValues[s.key] : s.Column(PresetKey(i));
  Changed();
}

bool Save() {
  std::wstring preset = PresetKey(g.profile), base;
  std::vector<std::wstring> pairs;
  if (g.profile == 2) base = g.customBase;
  pairs.push_back(g.model.languageKey + L"=" + uiLanguage);
  for (const auto& s : g.model.settings) {
    const std::wstring& v = g.chosen[s.key];
    if (s.scope == L"preference") pairs.push_back(s.key + L"=" + v);  // stored only when not the default
    else if (g.profile == 2 && v != s.Column(g.customBase)) pairs.push_back(s.key + L"=" + v);
  }
  // M32: the keyboard map as shown: its layout and every input that differs from it.
  std::vector<std::wstring> keyboard{L"--keyboard", g.keyLayout};
  std::vector<std::wstring> changed;
  if (const KeyLayout* l = LayoutByKey(g.keyLayout))
    for (const auto& in : g.model.keyInputs) {
      const Slots& k = g.keys[in.id];
      if (!l->keys.count(in.id) || l->keys.at(in.id) != k)
        changed.push_back(in.id + L"=" + k[0] + (k[1].empty() ? L"" : L"," + k[1]));
    }
  if (!changed.empty()) { keyboard.push_back(L"--key"); keyboard.insert(keyboard.end(), changed.begin(), changed.end()); }
  std::wstring msg;
  if (!SaveSettings(g.paths, preset, base, pairs, keyboard, msg)) {
    SetStatus(T(L"Not saved: ") + msg, true);
    return false;
  }
  std::wstring error;
  Model fresh;
  if (LoadModel(g.paths, fresh, error)) {
    g.model.settingsState = fresh.settingsState;
    g.model.preset = fresh.preset;
    g.model.base = fresh.base;
    g.model.running = fresh.running;
    for (size_t i = 0; i < g.model.settings.size() && i < fresh.settings.size(); ++i)
      g.model.settings[i].current = fresh.settings[i].current;
    g.model.keyboardState = fresh.keyboardState;
    g.model.keyboardLayout = fresh.keyboardLayout;
    g.model.keyboardWarning = fresh.keyboardWarning;
    for (size_t i = 0; i < g.model.keyInputs.size() && i < fresh.keyInputs.size(); ++i)
      g.model.keyInputs[i].saved = fresh.keyInputs[i].saved;
    Populate();
  }
  SetStatus(T(L"Saved. The settings apply the next time the game starts."));
  return true;
}

void Play() {
  if (g.dirty && !Save()) return;
  bool dryRun = g.testMode;
  SetStatus(dryRun ? T(L"Checking the launch (test mode: dry run)...") : T(L"Starting Rayman 3 HD..."));
  EnableWindow(g.playButton, FALSE);
  EnableWindow(g.hwnd, FALSE);
  std::wstring detail;
  Launch r = StartGame(g.paths, dryRun, detail, IdlePump);
  EnableWindow(g.hwnd, TRUE);
  EnableWindow(g.playButton, TRUE);
  switch (r) {
    case Launch::Started: DestroyWindow(g.hwnd); return;  // the game is running; nothing of the launcher stays
    case Launch::Ended:
      SetStatus(dryRun ? T(L"Dry run passed: the game would start with these settings.") : T(L"The game has ended."));
      Note(L"play-output: " + Trim(detail));
      return;
    case Launch::AlreadyRunning: SetStatus(T(L"Rayman 3 HD is already running."), true); return;
    case Launch::Busy: SetStatus(T(L"The game is already being started."), true); return;
    case Launch::Failed: SetStatus(g.testMode ? T(L"The game could not be started: ") + detail : T(L"The game could not start. Check cache/launcher_play.log or run setup to repair it."), true); return;
    case Launch::Slow: SetStatus(detail, true); return;
  }
}

bool ConfirmClose() {
  if (!g.dirty) return true;
  int r = Ask(T(L"Save your changes before closing?"), MB_YESNOCANCEL | MB_ICONQUESTION, IDNO);
  if (r == IDCANCEL) return false;
  return r == IDNO || Save();
}

// ------------------------------------------------------------------------------------------- Mods page --

std::wstring ModState(const ModRow& m) {
  if (m.state == L"active")
    return m.shadowed ? T(L"Active (partly covered by a mod above it)") : T(L"Active");
  if (m.state == L"disabled") return T(L"Off");
  if (m.state == L"disabled_invalid") return T(L"Off; it cannot be applied: ") + ModError(m.code);
  return T(L"Not applied: ") + ModError(m.code);
}

int SelectedMod() {
  int i = (int)SendMessageW(g.modList, LB_GETCURSEL, 0, 0);
  return i >= 0 && i < (int)g.mods.size() ? i : -1;
}

void ShowModDetail() {
  int i = SelectedMod();
  bool any = i >= 0;
  std::wstring t;
  if (!g.modsError.empty()) t = T(L"The mod list cannot be read: ") + g.modsError;
  else if (g.mods.empty()) t = T(L"No mods are installed. Install a mod from a .zip file or a folder.");
  else if (!any) t = T(L"Select a mod to see its details.");
  else {
    const ModRow& m = g.mods[i];
    t = m.name + L"  " + m.version + L"   (" + m.id + L")\r\n" + T(L"State: ") + ModState(m);
    if (!m.description.empty()) {
      std::wstring d;  // the edit box breaks lines only at CR LF
      for (wchar_t c : m.description) { if (c == L'\n') d += L"\r\n"; else if (c != L'\r') d += c; }
      t += L"\r\n" + d;
    }
  }
  SetText(g.modDetail, t);
  SendMessageW(g.modDetail, EM_SETSEL, 0, 0);
  SendMessageW(g.modDetail, EM_SCROLLCARET, 0, 0);  // a new selection starts at its first line
  EnableWindow(g.modToggle, any);
  EnableWindow(g.modRemove, any);
  EnableWindow(g.modUp, any && i > 0);
  EnableWindow(g.modDown, any && i + 1 < (int)g.mods.size());
  SetText(g.modToggle, any && g.mods[i].enabled ? T(L"&Disable") : T(L"&Enable"));
}

// Reads the list again and selects `select` (an id) if it is still there.
void ShowMods(const std::wstring& select) {
  std::wstring message;
  g.modsError.clear();
  if (!RunMods(g.paths, {L"list"}, &g.mods, message)) { g.mods.clear(); g.modsError = message; }
  g.modsLoaded = true;
  SendMessageW(g.modList, LB_RESETCONTENT, 0, 0);
  int sel = -1;
  for (size_t i = 0; i < g.mods.size(); ++i) {
    const ModRow& m = g.mods[i];
    std::wstring item = std::to_wstring(i + 1) + L".  " + (m.enabled ? T(L"[on]   ") : T(L"[off]  ")) + m.name + L"  " + m.version +
                        L"  -  " + (m.state == L"active" ? T(L"active") : m.enabled ? T(L"not applied") : T(L"off"));
    SendMessageW(g.modList, LB_ADDSTRING, 0, (LPARAM)item.c_str());
    if (m.id == select) sel = (int)i;
  }
  SendMessageW(g.modList, LB_SETCURSEL, sel, 0);
  ShowModDetail();
  Note(L"mods: " + std::to_wstring(g.mods.size()) + L" listed" + (g.modsError.empty() ? L"" : L"; error " + g.modsError));
}

std::wstring RestartNote() {
  return g.model.running ? T(L" The game is running: restart it to apply the change.") : T(L" It applies the next time the game starts.");
}

void ModAction(const std::vector<std::wstring>& args, const std::wstring& select, const std::wstring& done) {
  std::wstring message;
  SetCursor(LoadCursorW(nullptr, IDC_WAIT));
  // M33 review: the window keeps painting during a long import but takes no input until the tool has finished.
  EnableWindow(g.hwnd, FALSE);
  bool ok = RunMods(g.paths, args, nullptr, message);
  EnableWindow(g.hwnd, TRUE);
  ShowMods(select);
  if (ok) SetStatus(done + RestartNote());
  else SetStatus(T(L"Not done: ") + message, true);
  Note(std::wstring(L"mod action ") + args[0] + (ok ? L": ok" : L": refused " + message));
}

void ImportMod(const std::wstring& source) {
  if (source.empty()) return;
  SetStatus(T(L"Checking the mod..."));
  UpdateWindow(g.hwnd);
  std::vector<ModRow> before = g.mods;
  ModAction({L"import", source}, L"", T(L"The mod was installed. Enable it to use it."));
  // Select the new or replaced mod (the one whose id was not listed before, else keep the selection).
  for (size_t i = 0; i < g.mods.size(); ++i) {
    bool known = false;
    for (const auto& b : before) known |= b.id == g.mods[i].id;
    if (!known) { SendMessageW(g.modList, LB_SETCURSEL, i, 0); ShowModDetail(); }
  }
}

std::wstring PickZip() {
  wchar_t file[MAX_PATH * 2] = L"";
  OPENFILENAMEW ofn{sizeof ofn};
  ofn.hwndOwner = g.hwnd;
  std::wstring filter = T(L"Mod archive (*.zip)") + std::wstring(L"\0*.zip\0", 7);
  ofn.lpstrFilter = filter.c_str();
  ofn.lpstrFile = file;
  ofn.nMaxFile = (DWORD)std::size(file);
  std::wstring dialogTitle = T(L"Install a mod");
  ofn.lpstrTitle = dialogTitle.c_str();
  // M49 (D-088): start in the installation's extras folder (the Turkish translation's .zip) when there is one.
  std::wstring extras = g.model.home + L"\\extras";
  DWORD attr = GetFileAttributesW(extras.c_str());
  if (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY)) ofn.lpstrInitialDir = extras.c_str();
  ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_DONTADDTORECENT;
  return GetOpenFileNameW(&ofn) ? std::wstring(file) : std::wstring();
}

std::wstring PickFolder() {
  // The new-style folder dialog needs COM on this thread (M33 review).
  HRESULT com = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
  struct Uninit { HRESULT hr; ~Uninit() { if (SUCCEEDED(hr)) CoUninitialize(); } } uninit{com};
  BROWSEINFOW bi{};
  bi.hwndOwner = g.hwnd;
  std::wstring dialogTitle = T(L"Choose the mod folder containing mod.json.");
  bi.lpszTitle = dialogTitle.c_str();
  bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE | BIF_NONEWFOLDERBUTTON;
  PIDLIST_ABSOLUTE pidl = SHBrowseForFolderW(&bi);
  if (!pidl) return {};
  wchar_t path[MAX_PATH * 2] = L"";
  bool ok = SHGetPathFromIDListEx(pidl, path, (DWORD)std::size(path), GPFIDL_DEFAULT) != FALSE;
  CoTaskMemFree(pidl);
  return ok ? std::wstring(path) : std::wstring();
}

void OnModsCommand(int id, int code) {
  int i = SelectedMod();
  std::wstring sel = i >= 0 ? g.mods[i].id : L"";
  switch (id) {
    case kIdModList: if (code == LBN_SELCHANGE) ShowModDetail(); break;
    case kIdModZip:
      if (g.testMode) { Note(L"mods: the file dialog is not opened in test mode"); break; }
      ImportMod(PickZip());
      break;
    case kIdModFolder:
      if (g.testMode) { Note(L"mods: the folder dialog is not opened in test mode"); break; }
      ImportMod(PickFolder());
      break;
    case kIdModToggle:
      if (i < 0) break;
      ModAction({g.mods[i].enabled ? L"disable" : L"enable", sel}, sel,
                F(g.mods[i].enabled ? T(L"{mod} is now off.") : T(L"{mod} is now on."), {{L"mod", g.mods[i].name}}));
      break;
    case kIdModUp:
    case kIdModDown:
      if (i < 0) break;
      ModAction({L"move", sel, id == kIdModUp ? L"up" : L"down"}, sel, T(L"The order was changed."));
      break;
    case kIdModRemove:
      if (i < 0) break;
      if (Ask(F(L"Remove {mod}? Game files and saves are kept.", {{L"mod", g.mods[i].name}}), MB_OKCANCEL | MB_ICONQUESTION, IDOK) != IDOK) break;
      ModAction({L"remove", sel}, L"", F(L"{mod} was removed.", {{L"mod", g.mods[i].name}}));
      break;
  }
}

bool ChangeLanguage(const std::wstring& language) {
  if (language == uiLanguage || (language != L"en" && language != L"tr")) return true;
  auto args = EngineArgs(g.paths, L"set-option");
  args.insert(args.end(), {L"--set", g.model.languageKey + L"=" + language});
  std::string output;
  DWORD code = 1;
  if (!RunCapture(g.paths.python, args, output, code) || code != 0) {
    SetStatus(T(L"Settings could not be saved. Check folder access and try again."), true);
    SendMessageW(g.languageBox, CB_SETCURSEL, uiLanguage == L"tr" ? 1 : 0, 0);
    return false;
  }
  Model fresh;
  std::wstring error;
  if (!LoadModel(g.paths, fresh, error)) {
    SetStatus(T(L"The settings component could not be started."), true);
    return false;
  }
  g.model.language = language;
  // Preserve the form state. Only child controls are rebuilt; no Populate(), save or mod operation.
  int selected = SelectedMod();
  std::wstring selectedId = selected >= 0 ? g.mods[selected].id : L"";
  EndCapture();
  while (HWND child = GetWindow(g.hwnd, GW_CHILD)) DestroyWindow(child);
  g.settingsPage.clear(); g.controlsPage.clear(); g.advancedPage.clear(); g.modsPage.clear();
  g.groupTitle.clear(); g.keyGroupTitles.clear(); g.secondary.clear();
  for (auto& setting : g.model.settings) setting.title = setting.control = setting.helpText = nullptr;
  BuildControls();
  ApplyFonts();
  SetWindowTextW(g.hwnd, T(L"Rayman 3 HD Settings").c_str());
  UpdateBanner();
  ShowKeys();
  Show();
  if (g.modsLoaded) ShowMods(selectedId);  // read only; never applies a mod action
  SetStatus(T(L"UI language changed. Unsaved edits are kept."));
  Fit(true);
  SetFocus(g.languageBox);
  InvalidateRect(g.hwnd, nullptr, TRUE);
  return true;
}

void OnCommand(int id, int code) {
  if (id >= kIdModList && id <= kIdModRemove) { OnModsCommand(id, code); return; }
  if (id >= kIdRadio && id < kIdRadio + 3 && code == BN_CLICKED) { ChooseProfile(id - kIdRadio); return; }
  if (Setting* s = Find(id)) {
    if (s->Toggle() && code == BN_CLICKED) {
      bool on = SendMessageW(s->control, BM_GETCHECK, 0, 0) == BST_CHECKED;
      g.chosen[s->key] = s->values[on ? 1 : 0].value;
      Changed();
    } else if (!s->Toggle() && code == CBN_SELCHANGE) {
      int idx = (int)SendMessageW(s->control, CB_GETCURSEL, 0, 0);
      if (idx >= 0 && idx < (int)s->values.size()) { g.chosen[s->key] = s->values[idx].value; Changed(); }
    }
    return;
  }
  if (id >= kIdKey && id < kIdKey + 2 * (int)g.model.keyInputs.size() && code == BN_CLICKED) {
    int input = (id - kIdKey) / 2, slot = (id - kIdKey) % 2;
    if (g.captureInput == input && g.captureSlot == slot) { EndCapture(); SetStatus(T(L"Key not changed.")); }
    else StartCapture(input, slot);
    return;
  }
  switch (id) {
    case kIdLanguage:
      if (code == CBN_SELCHANGE) ChangeLanguage(SendMessageW(g.languageBox, CB_GETCURSEL, 0, 0) == 1 ? L"tr" : L"en");
      break;
    case kIdSave: Save(); break;
    case kIdPlay: Play(); break;
    case kIdPageSettings:
    case kIdControls:
    case kIdAdvanced:
    case kIdMods: {
      if (code != BN_CLICKED) break;
      EndCapture();
      g.page = id == kIdControls ? Page::Controls : id == kIdAdvanced ? Page::Advanced : id == kIdMods ? Page::Mods
             : Page::Settings;
      if (g.page == Page::Mods && !g.modsLoaded) ShowMods(L"");
      g.scrollY = 0;
      Fit(true);  // M43: the new page's height around the same centre
      SetFocus(g.page == Page::Controls ? g.layoutBox : g.page == Page::Advanced ? g.folderButton
               : g.page == Page::Mods ? g.modList : g.radios[g.profile]);
      Note(std::wstring(L"page: ") + (g.page == Page::Controls ? L"controls" : g.page == Page::Advanced ? L"advanced"
                                      : g.page == Page::Mods ? L"mods" : L"settings"));
      InvalidateRect(g.hwnd, nullptr, TRUE);
      break;
    }
    case kIdLayout:
      if (code == CBN_SELCHANGE) {
        int idx = (int)SendMessageW(g.layoutBox, CB_GETCURSEL, 0, 0);
        if (idx < 0 || idx >= (int)g.model.layouts.size() || g.model.layouts[idx].key == g.keyLayout) break;
        const KeyLayout& l = g.model.layouts[idx];
        if (KeysDifferFromLayout() && Ask(F(L"Use {layout}? Your changed keys will be replaced.", {{L"layout", T(l.name)}}),
                                          MB_OKCANCEL | MB_ICONQUESTION, IDOK) != IDOK) { ShowKeys(); break; }
        UseLayout(l.key, F(L"{layout} keys are shown.", {{L"layout", T(l.name)}}));
      }
      break;
    case kIdRestoreKeys:
      if (const KeyLayout* l = LayoutByKey(g.keyLayout)) {
        if (!KeysDifferFromLayout()) { SetStatus(F(L"Already using {layout} defaults.", {{L"layout", T(l->name)}})); break; }
        if (Ask(F(L"Restore {layout} keys?", {{L"layout", T(l->name)}}), MB_OKCANCEL | MB_ICONQUESTION, IDOK) == IDOK)
          UseLayout(l->key, F(L"{layout} keys restored.", {{L"layout", T(l->name)}}));
      }
      break;
    case kIdFolder:
      if (g.testMode) Note(L"folder: not opened in test mode");
      else ShellExecuteW(g.hwnd, L"open", g.model.home.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
      break;
    case IDCANCEL: if (ConfirmClose()) DestroyWindow(g.hwnd); break;
  }
}

LRESULT CALLBACK WndProc(HWND h, UINT msg, WPARAM wp, LPARAM lp) {
  switch (msg) {
    case WM_COMMAND: OnCommand(LOWORD(wp), HIWORD(wp)); return 0;
    case WM_HSCROLL:  // D-108: a slider moved (keyboard, mouse or the UI test's set)
      if (lp) if (Setting* s = Find(GetDlgCtrlID((HWND)lp))) if (s->slider) {
        int idx = (int)SendMessageW(s->control, TBM_GETPOS, 0, 0);
        if (idx >= 0 && idx < (int)s->values.size() && g.chosen[s->key] != s->values[idx].value) {
          g.chosen[s->key] = s->values[idx].value;
          Changed();
        }
        return 0;
      }
      break;
    case DM_GETDEFID: return MAKELONG(kIdPlay, DC_HASDEFID);
    case WM_CTLCOLORSTATIC:
    case WM_CTLCOLORBTN: {
      HDC dc = (HDC)wp;
      HWND c = (HWND)lp;
      SetBkMode(dc, TRANSPARENT);
      COLORREF text = GetSysColor(COLOR_WINDOWTEXT);
      HIGHCONTRASTW hc{sizeof hc};
      bool contrast = SystemParametersInfoW(SPI_GETHIGHCONTRAST, sizeof hc, &hc, 0) && (hc.dwFlags & HCF_HIGHCONTRASTON);
      if (std::find(g.secondary.begin(), g.secondary.end(), c) != g.secondary.end()) text = GetSysColor(COLOR_GRAYTEXT);
      if (!contrast && ((c == g.banner && g.bannerError) || (c == g.status && g.statusError))) text = RGB(168, 0, 0);
      if (!IsWindowEnabled(c)) text = GetSysColor(COLOR_GRAYTEXT);
      SetTextColor(dc, text);
      if (c == g.modDetail) { SetBkMode(dc, OPAQUE); SetBkColor(dc, GetSysColor(COLOR_WINDOW)); }  // M43: it scrolls
      return (LRESULT)g.background;
    }
    case WM_DPICHANGED: {
      if (g.forcedDpi) return 0;
      g.dpi = HIWORD(wp);
      CreateFonts();
      ApplyFonts();
      const RECT* r = (const RECT*)lp;
      SetWindowPos(h, nullptr, r->left, r->top, r->right - r->left, r->bottom - r->top, SWP_NOZORDER | SWP_NOACTIVATE);
      g.anchor = {(r->left + r->right) / 2, (r->top + r->bottom) / 2};  // M43: the system's place for the new DPI
      Fit(true);
      RedrawWindow(h, nullptr, nullptr, RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN);  // M42: no stale strip
      return 0;
    }
    case WM_EXITSIZEMOVE: {  // M43: a person moved the window: page changes keep it centred where they put it
      RECT wr;
      GetWindowRect(h, &wr);
      if (EqualRect(&wr, &g.placed)) return 0;  // not moved: a clamped page must not shift the anchor
      g.placed = wr;
      g.anchor = {(wr.left + wr.right) / 2, (wr.top + wr.bottom) / 2};
      g.userPlaced = true;
      Note(L"moved: anchor " + std::to_wstring(g.anchor.x) + L"," + std::to_wstring(g.anchor.y));
      return 0;
    }
    case WM_VSCROLL:
    case WM_MOUSEWHEEL: {
      RECT client;
      GetClientRect(h, &client);
      int y = g.scrollY, page = client.bottom, maxY = std::max(0, g.contentHeight - page);
      if (msg == WM_MOUSEWHEEL) y -= GET_WHEEL_DELTA_WPARAM(wp) * S(40) / WHEEL_DELTA;
      else switch (LOWORD(wp)) {
        case SB_LINEUP: y -= S(30); break;
        case SB_LINEDOWN: y += S(30); break;
        case SB_PAGEUP: y -= page; break;
        case SB_PAGEDOWN: y += page; break;
        case SB_THUMBTRACK: case SB_THUMBPOSITION: y = HIWORD(wp); break;
      }
      y = std::max(0, std::min(y, maxY));
      if (y != g.scrollY && (GetWindowLongPtrW(h, GWL_STYLE) & WS_VSCROLL)) {
        g.scrollY = y;
        SetScrollPos(h, SB_VERT, y, TRUE);
        Layout();
        InvalidateRect(h, nullptr, TRUE);
      }
      return 0;
    }
    case WM_ACTIVATE:
      if (LOWORD(wp) == WA_INACTIVE) {
        HWND f = GetFocus();
        if (f && IsChild(h, f)) g.lastFocus = f;
        if (g.captureInput >= 0) { EndCapture(); SetStatus(T(L"Key not changed.")); }  // M32: no capture without focus
      }
      return 0;
    case WM_CONTEXTMENU: {  // M32: right-click on a key button removes that key
      int id = GetDlgCtrlID((HWND)wp);
      if (id >= kIdKey && id < kIdKey + 2 * (int)g.model.keyInputs.size()) { EndCapture(); ClearKey((id - kIdKey) / 2, (id - kIdKey) % 2); return 0; }
      break;
    }
    case WM_SETFOCUS: SetFocus(g.lastFocus && IsWindow(g.lastFocus) ? g.lastFocus : g.radios[g.profile]); return 0;
    case WM_CLOSE: if (ConfirmClose()) DestroyWindow(h); return 0;
    case WM_DESTROY: if (!g.testMode) PostQuitMessage(0); return 0;  // the UI test drives its own pump
  }
  return DefWindowProcW(h, msg, wp, lp);
}

bool CreateUi(HINSTANCE inst) {
  INITCOMMONCONTROLSEX icc{sizeof icc, ICC_STANDARD_CLASSES | ICC_WIN95_CLASSES};
  InitCommonControlsEx(&icc);
  g.background = GetSysColorBrush(COLOR_WINDOW);
  g.icon = LoadAppIcon(inst, SM_CXICON);
  WNDCLASSEXW wc{sizeof wc};
  wc.lpfnWndProc = WndProc;
  wc.hInstance = inst;
  wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
  wc.hbrBackground = g.background;
  wc.lpszClassName = kWindowClass;
  wc.hIcon = g.icon;
  wc.hIconSm = LoadAppIcon(inst, SM_CXSMICON);
  RegisterClassExW(&wc);
  g.hwnd = CreateWindowExW(WS_EX_CONTROLPARENT, kWindowClass, T(L"Rayman 3 HD Settings").c_str(),
                           WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_CLIPCHILDREN,
                           CW_USEDEFAULT, CW_USEDEFAULT, 800, 600, nullptr, nullptr, inst, nullptr);
  if (!g.hwnd) return false;
  using Fn = UINT(WINAPI*)(HWND);
  auto dpiFor = (Fn)GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDpiForWindow");
  g.dpi = g.forcedDpi ? g.forcedDpi : dpiFor ? dpiFor(g.hwnd) : 96;
  CreateFonts();
  BuildControls();
  ApplyFonts();
  Populate();
  // Centre on the work area of the monitor the window opened on (M43: the anchor every page change keeps).
  CentreAnchor();
  Fit(true);
  SetText(g.status, L"");
  return true;
}

int RunUi(HINSTANCE inst) {
  if (!CreateUi(inst)) return 1;
  ShowWindow(g.hwnd, SW_SHOWNORMAL);
  SetFocus(g.radios[g.profile]);
  MSG msg;
  while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
    if (CaptureFilter(msg)) continue;  // M32: the key capture sees keys before the dialog manager
    if (IsDialogMessageW(g.hwnd, &msg)) continue;
    TranslateMessage(&msg);
    DispatchMessageW(&msg);
  }
  return 0;
}

// ------------------------------------------------------------------------------------------------ UI test --

void Pump() {
  MSG msg;
  while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
    if (msg.message == WM_QUIT) continue;
    if (CaptureFilter(msg)) continue;
    if (!IsWindow(g.hwnd) || !IsDialogMessageW(g.hwnd, &msg)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
  }
}

bool SaveBmp(const std::wstring& path) {
  RECT c;
  GetClientRect(g.hwnd, &c);
  int w = c.right, h = c.bottom;
  HDC wdc = GetDC(g.hwnd);
  HDC dc = CreateCompatibleDC(wdc);
  BITMAPINFO bi{};
  bi.bmiHeader = {sizeof(BITMAPINFOHEADER), w, h, 1, 24, BI_RGB};
  void* bits = nullptr;
  HBITMAP bmp = CreateDIBSection(wdc, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
  HGDIOBJ old = SelectObject(dc, bmp);
  PrintWindow(g.hwnd, dc, PW_CLIENTONLY);
  GdiFlush();
  SelectObject(dc, old);
  DWORD stride = ((DWORD)w * 3 + 3) & ~3u, size = stride * h;
  BITMAPFILEHEADER fh{0x4D42, (DWORD)(sizeof fh + sizeof bi.bmiHeader + size), 0, 0, (DWORD)(sizeof fh + sizeof bi.bmiHeader)};
  HANDLE f = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, 0, nullptr);
  bool ok = f != INVALID_HANDLE_VALUE;
  if (ok) {
    DWORD n;
    ok = WriteFile(f, &fh, sizeof fh, &n, nullptr) && WriteFile(f, &bi.bmiHeader, sizeof bi.bmiHeader, &n, nullptr)
         && WriteFile(f, bits, size, &n, nullptr);
    CloseHandle(f);
  }
  DeleteObject(bmp);
  DeleteDC(dc);
  ReleaseDC(g.hwnd, wdc);
  return ok;
}

std::wstring StateDump() {
  std::wstring s = L"profile=" + std::wstring(PresetKey(g.profile)) + L"\n";
  s += L"ui_language=" + uiLanguage + L"\n";
  ModRow sample; sample.state = L"active";
  s += L"mod_state.active=" + ModState(sample) + L"\n";
  sample.shadowed = 1;
  s += L"mod_state.partial=" + ModState(sample) + L"\n";
  sample.state = L"disabled";
  s += L"mod_state.off=" + ModState(sample) + L"\n";
  sample.state = L"invalid"; sample.code = L"BAD_MANIFEST";
  s += L"mod_state.invalid=" + ModState(sample) + L"\n";

  wchar_t windowTitle[512]; GetWindowTextW(g.hwnd, windowTitle, 512);
  s += L"window_title=" + std::wstring(windowTitle) + L"\n";
  wchar_t languageLabel[128]; GetWindowTextW(g.languageTitle, languageLabel, 128);
  s += L"interface_language_label=" + std::wstring(languageLabel) + L"\n";
  s += L"interface_language_visible=" + std::to_wstring(IsWindowVisible(g.languageBox) != 0) + L"\n";
  s += L"version_visible=" + std::to_wstring(IsWindowVisible(g.versionText) != 0) + L"\n";
  s += L"interface_language_options=";
  int languageCount = (int)SendMessageW(g.languageBox, CB_GETCOUNT, 0, 0);
  for (int i = 0; i < languageCount; ++i) {
    wchar_t option[128] = {};
    SendMessageW(g.languageBox, CB_GETLBTEXT, i, (LPARAM)option);
    s += (i ? L"," : L"") + std::wstring(option);
  }
  s += L"\n";
  int headerClipped = 0;
  HDC headerDc = GetDC(g.hwnd);
  HGDIOBJ headerFont = SelectObject(headerDc, g.body);
  const wchar_t glyphs[] = L"ğĞşŞıİçÇöÖüÜ";
  WORD glyphIndices[12] = {};
  bool glyphsOk = GetGlyphIndicesW(headerDc, glyphs, 12, glyphIndices, GGI_MARK_NONEXISTING_GLYPHS) != GDI_ERROR;
  for (WORD glyph : glyphIndices) glyphsOk = glyphsOk && glyph != 0xFFFF;
  s += L"turkish_glyphs=" + std::to_wstring(glyphsOk) + L"\n";
  for (HWND label : {g.languageTitle, g.versionText}) {
    wchar_t text[512]; GetWindowTextW(label, text, 512);
    RECT area; GetClientRect(label, &area);
    SIZE measured; GetTextExtentPoint32W(headerDc, text, (int)wcslen(text), &measured);
    if (measured.cx > area.right || measured.cy > area.bottom) ++headerClipped;
  }
  SelectObject(headerDc, headerFont); ReleaseDC(g.hwnd, headerDc);
  s += L"header_clipped=" + std::to_wstring(headerClipped) + L"\n";
  EnumChildWindows(g.hwnd, [](HWND h, LPARAM value) -> BOOL {
    if (!IsWindowVisible(h)) return TRUE;
    wchar_t text[4096]; GetWindowTextW(h, text, 4096);
    auto* result = (std::wstring*)value;
    std::wstring caption(text);
    std::replace(caption.begin(), caption.end(), L'\n', L' ');
    std::replace(caption.begin(), caption.end(), L'\r', L' ');
    *result += L"visible." + std::to_wstring(GetDlgCtrlID(h)) + L"=" + caption + L"\n";
    return TRUE;
  }, (LPARAM)&s);

  s += L"custom_base=" + g.customBase + L"\n";
  s += L"dirty=" + std::to_wstring(g.dirty) + L"\n";
  s += L"save_enabled=" + std::to_wstring(IsWindowEnabled(g.saveButton) != 0) + L"\n";
  s += L"play_enabled=" + std::to_wstring(IsWindowEnabled(g.playButton) != 0) + L"\n";
  for (const auto& st : g.model.settings)
    s += L"setting." + st.key + L"=" + g.chosen[st.key] + L" enabled=" + std::to_wstring(IsWindowEnabled(st.control) != 0) + L"\n";
  wchar_t buf[4096];
  for (const auto& st : g.model.settings) {  // D-108: a slider as it shows: bar position, label and value text
    if (!st.slider) continue;
    wchar_t label[256] = {}, value[64] = {};
    GetWindowTextW(st.title, label, 256);
    GetWindowTextW(st.valueText, value, 64);
    s += L"slider." + st.key + L"=pos=" + std::to_wstring(SendMessageW(st.control, TBM_GETPOS, 0, 0)) + L" max=" +
         std::to_wstring(SendMessageW(st.control, TBM_GETRANGEMAX, 0, 0)) + L" visible=" +
         std::to_wstring(IsWindowVisible(st.control) != 0) + L" value=" + value + L" label=" + label + L"\n";
  }
  // M32: the Controls page as its controls show it (button captions read back from the window, not the model).
  s += std::wstring(L"page=") + (g.page == Page::Controls ? L"controls" : g.page == Page::Advanced ? L"advanced"
                                 : g.page == Page::Mods ? L"mods" : L"settings") + L"\n";
  // M33: the Mods page as its controls show it.
  s += L"mods_visible=" + std::to_wstring(IsWindowVisible(g.modList) != 0) + L" mods_count=" +
       std::to_wstring(SendMessageW(g.modList, LB_GETCOUNT, 0, 0)) + L" mods_selected=" +
       std::to_wstring(SendMessageW(g.modList, LB_GETCURSEL, 0, 0)) + L"\n";
  for (int i = 0; i < (int)SendMessageW(g.modList, LB_GETCOUNT, 0, 0); ++i) {
    SendMessageW(g.modList, LB_GETTEXT, i, (LPARAM)buf);
    s += L"mod_item." + std::to_wstring(i) + L"=" + buf + L"\n";
  }
  for (const auto& m : g.mods) s += L"mod." + m.id + L"=" + (m.enabled ? L"on " : L"off ") + m.state + L" " + m.code + L"\n";
  {
    std::wstring d((size_t)GetWindowTextLengthW(g.modDetail) + 1, L'\0');  // M43: a description may exceed buf
    d.resize((size_t)GetWindowTextW(g.modDetail, d.data(), (int)d.size()));
    d.erase(std::remove(d.begin(), d.end(), L'\r'), d.end());
    std::replace(d.begin(), d.end(), L'\n', L' ');
    s += L"mod_detail=" + d + L"\n";
    // M43: the box shows its text whole or scrolls to its end: its lines, the lines that fit, its scroll range
    RECT box;
    SendMessageW(g.modDetail, EM_GETRECT, 0, (LPARAM)&box);
    int lines = (int)SendMessageW(g.modDetail, EM_GETLINECOUNT, 0, 0);
    int fit = (box.bottom - box.top) / std::max(1, LineHeight(g.body));
    SCROLLINFO si{sizeof si, SIF_ALL};
    bool bar = GetScrollInfo(g.modDetail, SB_VERT, &si) != 0;
    s += L"mod_detail_box=lines=" + std::to_wstring(lines) + L" fit=" + std::to_wstring(fit) + L" scroll_max=" +
         std::to_wstring(bar ? si.nMax : -1) + L" scroll_page=" + std::to_wstring(bar ? (int)si.nPage : -1) + L"\n";
    GetWindowTextW(g.modToggle, buf, (int)std::size(buf));
    s += L"mod_toggle=" + std::wstring(buf) + L" enabled=" + std::to_wstring(IsWindowEnabled(g.modToggle) != 0) + L"\n";
  }
  s += L"key_layout=" + g.keyLayout + L"\n";
  s += L"key_capture=" + (g.captureInput >= 0 ? g.model.keyInputs[g.captureInput].id + L"." + std::to_wstring(g.captureSlot) : L"") + L"\n";
  s += L"key_rows=" + std::to_wstring(g.model.keyInputs.size()) + L"\n";
  int shownRows = 0;
  for (const auto& in : g.model.keyInputs) {
    std::wstring caps;
    for (int b = 0; b < 2; ++b) { GetWindowTextW(in.button[b], buf, (int)std::size(buf)); caps += (b ? L"|" : L"") + std::wstring(buf); }
    GetWindowTextW(in.text, buf, (int)std::size(buf));
    bool vis = IsWindowVisible(in.button[0]) != 0;
    shownRows += vis;
    s += L"key." + in.id + L"=" + g.keys[in.id][0] + L"," + g.keys[in.id][1] + L" caption=" + caps + L" visible=" +
         std::to_wstring(vis) + L" action=" + buf + L"\n";
  }
  s += L"key_rows_shown=" + std::to_wstring(shownRows) + L"\n";
  s += L"layout_text=\n";  // Fixed layout summaries are no longer shown; current bindings are in the table.
  GetWindowTextW(g.controlsNote, buf, (int)std::size(buf));
  s += L"controls_note=" + std::wstring(buf) + L"\n";
  s += L"advanced_visible=" + std::to_wstring(IsWindowVisible(g.folderButton) != 0) + L"\n";
  s += L"page_buttons=" + std::to_wstring(SendMessageW(g.settingsButton, BM_GETCHECK, 0, 0) == BST_CHECKED) +
       std::to_wstring(SendMessageW(g.controlsButton, BM_GETCHECK, 0, 0) == BST_CHECKED) +
       std::to_wstring(SendMessageW(g.advancedButton, BM_GETCHECK, 0, 0) == BST_CHECKED) +
       std::to_wstring(SendMessageW(g.modsButton, BM_GETCHECK, 0, 0) == BST_CHECKED) + L"\n";
  GetWindowTextW(g.banner, buf, (int)std::size(buf));
  std::wstring b = buf;
  std::replace(b.begin(), b.end(), L'\n', L' ');
  s += L"banner=" + b + L"\n";
  GetWindowTextW(g.status, buf, (int)std::size(buf));
  b = buf;
  std::replace(b.begin(), b.end(), L'\n', L' ');
  s += L"status=" + b + L"\n";
  RECT r;
  GetClientRect(g.hwnd, &r);
  s += L"client=" + std::to_wstring(r.right) + L"x" + std::to_wstring(r.bottom) + L" dpi=" + std::to_wstring(g.dpi) + L"\n";
  {  // M43 (D-080): the window against its work area (screen pixels)
    RECT wr, wa = WorkArea();
    GetWindowRect(g.hwnd, &wr);
    auto rc = [](const RECT& q) { return std::to_wstring(q.left) + L"," + std::to_wstring(q.top) + L"," +
                                         std::to_wstring(q.right) + L"," + std::to_wstring(q.bottom); };
    s += L"window=" + rc(wr) + L" work=" + rc(wa) + L" centre=" + std::to_wstring((wr.left + wr.right) / 2) + L"," +
         std::to_wstring((wr.top + wr.bottom) / 2) + L" anchor=" + std::to_wstring(g.anchor.x) + L"," +
         std::to_wstring(g.anchor.y) + L" user_placed=" + std::to_wstring(g.userPlaced) + L" scroll=" +
         std::to_wstring((GetWindowLongPtrW(g.hwnd, GWL_STYLE) & WS_VSCROLL) != 0) + L"\n";
  }
  // Every visible control inside the page and not overlapping a sibling of the same column.
  std::vector<RECT> rects;
  EnumChildWindows(g.hwnd, [](HWND c, LPARAM p) -> BOOL {
    auto* v = (std::vector<RECT>*)p;
    if (GetParent(c) != g.hwnd) return TRUE;  // a control's own parts (the list's header) are inside it
    RECT rc;
    GetWindowRect(c, &rc);
    MapWindowPoints(nullptr, g.hwnd, (POINT*)&rc, 2);
    wchar_t cls[32];
    GetClassNameW(c, cls, 32);
    if (_wcsicmp(cls, WC_COMBOBOXW) == 0) { COMBOBOXINFO ci{sizeof ci}; GetComboBoxInfo(c, &ci); rc.bottom = rc.top + (ci.rcItem.bottom + 3); }
    if (IsWindowVisible(c)) v->push_back(rc);
    return TRUE;
  }, (LPARAM)&rects);
  int overlaps = 0, out = 0;
  for (size_t i = 0; i < rects.size(); ++i) {
    // Inside the page (the client width, the content height at the scroll position): a page that scrolls is
    // checked whole, on a 1080p screen as on a 1440p one (M33; D-082).
    if (rects[i].right > r.right || rects[i].bottom > std::max<LONG>(r.bottom, g.contentHeight - g.scrollY) ||
        rects[i].left < 0 || rects[i].top < -g.scrollY) ++out;
    for (size_t j = i + 1; j < rects.size(); ++j) {
      RECT x;
      if (IntersectRect(&x, &rects[i], &rects[j]) && (x.bottom - x.top) > 1 && (x.right - x.left) > 1) ++overlaps;
    }
  }
  s += L"controls=" + std::to_wstring(rects.size()) + L" overlaps=" + std::to_wstring(overlaps) + L" outside=" + std::to_wstring(out) + L"\n";
  return s;
}

void WriteText(const std::wstring& path, const std::wstring& text) {
  HANDLE f = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, 0, nullptr);
  if (f == INVALID_HANDLE_VALUE) return;
  std::string u = Narrow(text);
  DWORD n;
  WriteFile(f, u.data(), (DWORD)u.size(), &n, nullptr);
  CloseHandle(f);
}

int RunUiTest(HINSTANCE inst, const std::wstring& script, const std::wstring& outDir) {
  // A desktop of its own in this window station: nothing here is visible on, or can take focus from, the
  // person's desktop. The thread must switch before it owns any window.
  std::wstring name = L"r3hd_ui_test_" + std::to_wstring(GetCurrentProcessId());
  HDESK desk = CreateDesktopW(name.c_str(), nullptr, nullptr, 0, GENERIC_ALL, nullptr);
  if (!desk || !SetThreadDesktop(desk)) return 3;
  g.testMode = true;
  if (!CreateUi(inst)) return 1;
  ShowWindow(g.hwnd, SW_SHOWNOACTIVATE);
  UpdateWindow(g.hwnd);
  Pump();
  int failures = 0;
  std::string scriptText = ReadFileBytes(script);
  if (scriptText.find_first_not_of(" \t\r\n") == std::string::npos) { g.log.push_back(L"empty or unreadable script"); ++failures; }
  for (const auto& raw : Split(Widen(scriptText), L'\n')) {
    std::wstring line = Trim(raw);
    if (line.empty() || line[0] == L'#') continue;
    if (!IsWindow(g.hwnd)) { g.log.push_back(L"window closed; stop"); break; }
    auto f = Split(line, L' ');
    const std::wstring& cmd = f[0];
    std::wstring a1 = f.size() > 1 ? f[1] : L"", a2 = f.size() > 2 ? f[2] : L"";
    g.log.push_back(L"> " + line);
    if (cmd == L"language") {
      if (!ChangeLanguage(a1)) ++failures;
    } else if (cmd == L"profile") {
      for (int i = 0; i < 3; ++i) if (a1 == PresetKey(i)) SendMessageW(g.radios[i], BM_CLICK, 0, 0);
    } else if (cmd == L"set") {
      bool found = false;
      for (size_t i = 0; i < g.model.settings.size(); ++i) {
        Setting& s = g.model.settings[i];
        if (s.key != a1) continue;
        found = true;
        if (!IsWindowEnabled(s.control)) { g.log.push_back(L"control disabled: " + a1); break; }
        if (s.slider) {
          for (size_t j = 0; j < s.values.size(); ++j)
            if (s.values[j].value == a2) {
              SendMessageW(s.control, TBM_SETPOS, TRUE, (LPARAM)j);
              SendMessageW(g.hwnd, WM_HSCROLL, MAKEWPARAM(TB_ENDTRACK, 0), (LPARAM)s.control);
            }
        } else if (s.Toggle()) {
          if (g.chosen[s.key] != a2) SendMessageW(s.control, BM_CLICK, 0, 0);
        } else {
          for (size_t j = 0; j < s.values.size(); ++j)
            if (s.values[j].value == a2) {
              SendMessageW(s.control, CB_SETCURSEL, j, 0);
              SendMessageW(g.hwnd, WM_COMMAND, MAKEWPARAM(kIdSetting + i, CBN_SELCHANGE), (LPARAM)s.control);
            }
        }
      }
      if (!found) { g.log.push_back(L"no setting " + a1); ++failures; }
    } else if (cmd == L"click") {
      HWND b = a1 == L"save" ? g.saveButton : a1 == L"play" ? g.playButton : a1 == L"folder" ? g.folderButton
             : a1 == L"close" ? g.closeButton : a1 == L"controls" ? g.controlsButton : a1 == L"restore" ? g.restoreKeys
             : a1 == L"advanced" ? g.advancedButton : a1 == L"settings" ? g.settingsButton : a1 == L"mods" ? g.modsButton
             : a1 == L"modzip" ? g.modZip : a1 == L"modfolder" ? g.modFolder : nullptr;
      if (!b) { g.log.push_back(L"no button " + a1); ++failures; }
      else if (!IsWindowEnabled(b)) g.log.push_back(L"button disabled: " + a1);
      else SendMessageW(b, BM_CLICK, 0, 0);
    } else if (cmd == L"page") {  // M31 / M32: settings | controls | advanced; M33: mods
      HWND b = a1 == L"controls" ? g.controlsButton : a1 == L"advanced" ? g.advancedButton : a1 == L"mods" ? g.modsButton
             : g.settingsButton;
      SendMessageW(b, BM_CLICK, 0, 0);
    } else if (cmd == L"layout") {  // M32: choose a keyboard layout in the box
      bool found = false;
      for (size_t i = 0; i < g.model.layouts.size(); ++i)
        if (g.model.layouts[i].key == a1) {
          found = true;
          SendMessageW(g.layoutBox, CB_SETCURSEL, i, 0);
          SendMessageW(g.hwnd, WM_COMMAND, MAKEWPARAM(kIdLayout, CBN_SELCHANGE), (LPARAM)g.layoutBox);
        }
      if (!found) { g.log.push_back(L"no layout " + a1); ++failures; }
    } else if (cmd == L"key" || cmd == L"rclick") {  // M32: click (or right-click) a key button: INPUT SLOT(0|1)
      int found = -1;
      for (size_t i = 0; i < g.model.keyInputs.size(); ++i) if (g.model.keyInputs[i].id == a1) found = (int)i;
      int slot = _wtoi(a2.c_str());
      if (found < 0 || slot < 0 || slot > 1) { g.log.push_back(L"no key button " + a1 + L" " + a2); ++failures; }
      else if (!IsWindowVisible(g.model.keyInputs[found].button[slot])) g.log.push_back(L"key button hidden: " + a1);
      else if (cmd == L"key") SendMessageW(g.model.keyInputs[found].button[slot], BM_CLICK, 0, 0);
      else SendMessageW(g.hwnd, WM_CONTEXTMENU, (WPARAM)g.model.keyInputs[found].button[slot], 0);
    } else if (cmd == L"press") {  // M32: a key-down with this scan code (hex, E0xx = extended) to the focused control
      std::wstring code = a1;
      bool ext = code.size() == 4;
      UINT scan = (UINT)wcstoul(code.substr(ext ? 2 : 0).c_str(), nullptr, 16);
      UINT vk = MapVirtualKeyW(ext ? (0xE000 | scan) : scan, MAPVK_VSC_TO_VK_EX);
      if (a1 == L"01") vk = VK_ESCAPE;
      HWND target = GetFocus();
      if (!target || !IsChild(g.hwnd, target)) target = g.hwnd;
      LPARAM lp = (LPARAM)(1 | (scan << 16) | (ext ? (1u << 24) : 0));
      PostMessageW(target, vk == VK_MENU || vk == VK_F10 ? WM_SYSKEYDOWN : WM_KEYDOWN, vk, lp);
      Pump();
      PostMessageW(target, vk == VK_MENU || vk == VK_F10 ? WM_SYSKEYUP : WM_KEYUP, vk, lp | (LPARAM)(3u << 30));
    } else if (cmd == L"mod") {  // M33: mod select ID | toggle | up | down | remove | import PATH (no dialog)
      if (a1 == L"select") {
        int found = -1;
        for (size_t i = 0; i < g.mods.size(); ++i) if (g.mods[i].id == a2) found = (int)i;
        if (found < 0) { g.log.push_back(L"no mod " + a2); ++failures; }
        else {
          SendMessageW(g.modList, LB_SETCURSEL, found, 0);
          SendMessageW(g.hwnd, WM_COMMAND, MAKEWPARAM(kIdModList, LBN_SELCHANGE), (LPARAM)g.modList);
        }
      } else if (a1 == L"import") {
        ImportMod(FullPath(Trim(line.substr(line.find(L"import") + 6))));
      } else {
        HWND b = a1 == L"toggle" ? g.modToggle : a1 == L"up" ? g.modUp : a1 == L"down" ? g.modDown
               : a1 == L"remove" ? g.modRemove : nullptr;
        if (!b) { g.log.push_back(L"no mod command " + a1); ++failures; }
        else if (!IsWindowEnabled(b)) g.log.push_back(L"button disabled: mod " + a1);
        else SendMessageW(b, BM_CLICK, 0, 0);
      }
    } else if (cmd == L"dpi") {  // as WM_DPICHANGED: the window keeps its centre (M43)
      g.forcedDpi = g.dpi = _wtoi(a1.c_str());
      CreateFonts();
      ApplyFonts();
      RECT wr;
      GetWindowRect(g.hwnd, &wr);
      g.anchor = {(wr.left + wr.right) / 2, (wr.top + wr.bottom) / 2};
      Fit(true);
      RedrawWindow(g.hwnd, nullptr, nullptr, RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN);
    } else if (cmd == L"move") {  // M43: X Y (the window's top-left), then the end of a move as a person's drag ends
      SetWindowPos(g.hwnd, nullptr, _wtoi(a1.c_str()), _wtoi(a2.c_str()), 0, 0, SWP_NOZORDER | SWP_NOSIZE | SWP_NOACTIVATE);
      SendMessageW(g.hwnd, WM_EXITSIZEMOVE, 0, 0);
    } else if (cmd == L"endmove") {  // M43: a move loop that ends where it began (a click on the title bar)
      SendMessageW(g.hwnd, WM_EXITSIZEMOVE, 0, 0);
    } else if (cmd == L"workarea") {  // M43: L T R B: a smaller screen's work area; the window reopens centred on it
      RECT wa{_wtoi(a1.c_str()), _wtoi(a2.c_str()), f.size() > 4 ? _wtoi(f[3].c_str()) : 0, f.size() > 4 ? _wtoi(f[4].c_str()) : 0};
      if (wa.right - wa.left < 320 || wa.bottom - wa.top < 240) { g.log.push_back(L"workarea needs L T R B"); ++failures; continue; }
      g.forcedWork = wa;
      CentreAnchor();
      g.userPlaced = false;
      g.scrollY = 0;
      Fit(true);
    } else if (cmd == L"reload") {
      // As if the window were closed and opened again: a new model from the engine, new controls.
      if (IsWindow(g.hwnd)) DestroyWindow(g.hwnd);
      Pump();
      Paths paths = g.paths;
      int forced = g.forcedDpi;
      std::vector<std::wstring> journal = std::move(g.log);
      for (HFONT f : {g.body, g.bold, g.title}) if (f) DeleteObject(f);
      g = Ui{};
      g.paths = paths;
      g.forcedDpi = forced;
      g.testMode = true;
      g.log = std::move(journal);
      std::wstring error;
      if (!LoadModel(g.paths, g.model, error) || !CreateUi(inst)) { g.log.push_back(L"reload failed: " + error); ++failures; break; }
      ShowWindow(g.hwnd, SW_SHOWNOACTIVATE);
    } else if (cmd == L"shot") {
      Pump();
      RedrawWindow(g.hwnd, nullptr, nullptr, RDW_INVALIDATE | RDW_ALLCHILDREN | RDW_UPDATENOW | RDW_ERASE);
      if (!SaveBmp(outDir + L"\\" + a1 + L".bmp")) { g.log.push_back(L"shot failed"); ++failures; }
    } else if (cmd == L"dump") {
      Pump();
      WriteText(outDir + L"\\" + a1 + L".txt", StateDump());
    } else if (cmd == L"wait") {  // keeps the launcher open, e.g. while a lifecycle test runs the installer
      ULONGLONG until = GetTickCount64() + (ULONGLONG)std::max(0, std::min(_wtoi(a1.c_str()), 600000));
      while (GetTickCount64() < until) { Pump(); Sleep(50); }
    } else {
      g.log.push_back(L"unknown command"); ++failures;
    }
    Pump();
  }
  if (IsWindow(g.hwnd)) DestroyWindow(g.hwnd);
  Pump();
  std::wstring journal;
  for (const auto& l : g.log) journal += l + L"\n";
  WriteText(outDir + L"\\ui_test.log", journal);
  CloseDesktop(desk);
  return failures ? 2 : 0;
}

// -------------------------------------------------------------------------------------------------- entry --

void Report(const std::wstring& s) {
  HANDLE out = GetStdHandle(STD_OUTPUT_HANDLE);
  if (out && out != INVALID_HANDLE_VALUE) {
    std::string u = Narrow(s + L"\n");
    DWORD n;
    WriteFile(out, u.data(), (DWORD)u.size(), &n, nullptr);
  }
}

}  // namespace

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE, PWSTR, int) {
  using Fn = BOOL(WINAPI*)(HANDLE);
  if (auto ctx = (Fn)GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetProcessDpiAwarenessContext"))
    ctx((HANDLE)-4);  // per-monitor v2 (also in the manifest)
  int argc = 0;
  wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
  wchar_t self[MAX_PATH * 2];
  GetModuleFileNameW(nullptr, self, (DWORD)std::size(self));
  std::wstring appDir = Parent(self);
  Paths& p = g.paths;
  p.home = Parent(appDir);
  p.python = appDir + L"\\python\\python.exe";
  p.tools = appDir + L"\\tools";
  bool play = false, dryRun = false, noUi = false;
  std::wstring uiScript, outDir;
  for (int i = 1; i < argc; ++i)  // the test modes never show a message box, whatever else is wrong
    noUi |= wcscmp(argv[i], L"--no-ui") == 0 || wcscmp(argv[i], L"--ui-test") == 0;
  bool quiet = noUi;
  for (int i = 1; i < argc; ++i) {
    std::wstring a = argv[i];
    auto next = [&]() { return i + 1 < argc ? FullPath(argv[++i]) : std::wstring(); };
    if (a == L"--play") play = true;
    else if (a == L"--dry-run") dryRun = true;
    else if (a == L"--no-ui") noUi = true;
    else if (a == L"--home") p.home = next();
    else if (a == L"--python") p.python = next();
    else if (a == L"--tools") p.tools = next();
    else if (a == L"--releases") p.releases = next();
    else if (a == L"--ui-test") { uiScript = next(); noUi = false; }
    else if (a == L"--out") outDir = next();
    else {
      Report(L"R3HD_LAUNCHER USAGE unknown argument " + a);
      if (!quiet) {
        Model initial; std::wstring error; LoadModel(p, initial, error);
        MessageBoxW(nullptr, F(L"Unknown argument: {argument}", {{L"argument", a}}).c_str(), L"Rayman 3 HD", MB_ICONERROR);
      }
      return 1;
    }
  }
  LocalFree(argv);
  SetCurrentProcessExplicitAppUserModelID(play ? L"Rayman3HDRecompiled.Game" : L"Rayman3HDRecompiled.Settings");
  // Inno Setup's AppMutex: setup and uninstall ask the person to close this program first.
  HANDLE appMutex = CreateMutexW(nullptr, FALSE, kAppMutex);

  if (play) {
    if (!quiet) { Model initial; std::wstring error; LoadModel(p, initial, error); }
    std::wstring detail;
    Launch r = StartGame(p, dryRun, detail);
    const wchar_t* name = r == Launch::Started ? L"STARTED" : r == Launch::Ended ? L"ENDED" : r == Launch::Failed ? L"FAILED"
                        : r == Launch::AlreadyRunning ? L"ALREADY_RUNNING" : r == Launch::Slow ? L"SLOW" : L"BUSY";
    Report(std::wstring(L"R3HD_LAUNCHER PLAY ") + name);
    if (!detail.empty()) Report(Trim(detail));
    int code = r == Launch::Started || r == Launch::Ended ? 0 : 2;
    if (code && !quiet) {
      std::wstring text = r == Launch::AlreadyRunning ? T(L"Rayman 3 HD is already running.")
                        : r == Launch::Busy ? T(L"Rayman 3 HD is already being started.")
                        : r == Launch::Slow ? detail
                        : T(L"The game could not start. Check cache/launcher_play.log. Open Settings now?");
      UINT flags = r == Launch::Failed ? MB_YESNO | MB_ICONERROR : MB_OK | MB_ICONINFORMATION;
      if (MessageBoxW(nullptr, text.c_str(), L"Rayman 3 HD", flags) == IDYES) play = false;  // continue to Settings
    }
    if (play) { if (appMutex) CloseHandle(appMutex); return code; }
  }

  if (uiScript.empty() && !noUi) {
    // One Settings window: a second start brings the first one forward.
    if (HWND other = FindWindowW(kWindowClass, nullptr)) {
      ShowWindow(other, SW_RESTORE);
      SetForegroundWindow(other);
      return 0;
    }
  }
  std::wstring error;
  if (!LoadModel(p, g.model, error)) {
    Report(L"R3HD_LAUNCHER MODEL_FAILED " + error);
    if (!quiet)
      MessageBoxW(nullptr, (L"Rayman 3 HD Settings cannot read this installation: " + error +
                            L"\n\nRun the installer again and choose this folder to repair it.").c_str(),
                  T(L"Rayman 3 HD Settings").c_str(), MB_ICONERROR);
    return 2;
  }
  int code;
  if (!uiScript.empty()) code = RunUiTest(inst, uiScript, outDir.empty() ? Parent(uiScript) : outDir);
  else if (noUi) { Report(L"R3HD_LAUNCHER MODEL_OK " + g.model.preset); code = 0; }
  else code = RunUi(inst);
  if (appMutex) CloseHandle(appMutex);
  return code;
}

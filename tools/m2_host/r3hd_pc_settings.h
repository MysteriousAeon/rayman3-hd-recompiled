// D-139: the in-game PC Settings panel (F4). Host-only: no guest memory, no generated code, no device output.
//
// One model, one writer: the panel shows the Settings app's own model (engine `launcher-model`: settings, values,
// labels and the EN / TR strings of config/settings/ui_strings.json) and saves through the engine's
// `set-preferences --expect-revision`, which accepts only shown preferences and refuses STALE when the Settings
// app (or anything else) replaced settings.json since the panel read it. The engine runs as a short-lived hidden
// process (CREATE_NO_WINDOW) only when the panel opens or saves; nothing runs while it is closed.
// Live in this session: Display mode (the SDK's own fullscreen cvar -> Window::SetFullscreen, borderless; kept only
// after the person confirms it, otherwise reverted after kConfirmSeconds), Mouse Camera / Mouse Sensitivity /
// Mouse Buttons (the D-138 cvars the driver reads at every poll). Every other preference applies at the next start
// and says so; preset settings (Vanilla / HD+ / Custom corrections), keyboard and controller maps stay in Settings.
// While the panel is open the app sets SetHostUiInputBlocked: every input driver gives the guest neutral input and
// withholds what is still held when it closes (tools/r3hd_hostui_gate.h). The game keeps running underneath, as
// with Alt+Tab; the panel never pauses or resumes the title.
// LX-4 (E-375): one panel on both platforms. Only the engine process, its result file, the environment and the
// UTF-8/UTF-16 conversion differ; the POSIX branches (posix_spawn, a poll()ed pipe, mkstemp) sit beside the Windows
// code, which is unchanged token for token. The `#line` directives keep every Windows line number (and so every
// REXLOG source location in the Windows binary) exactly as before; tools/linux/test_pcset_windows_identity.py checks.
#pragma once
#if defined(_WIN32)
#line 16
#include <windows.h>
#else
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>
#include <cerrno>
#include <chrono>
#include <cstdint>
extern char** environ;
#endif
#line 17
#include <imgui.h>
#include <imgui_internal.h>  // BeginTooltipEx retains SetTooltip's replace-previous semantics
#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ui/imgui_dialog.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace r3hd_pcset {
#if !defined(_WIN32)
using DWORD = uint32_t;
#endif

#line 35
constexpr double kConfirmSeconds = 15.0;
constexpr float kFontSize = 18.0f;  // logical pixels; the drawer scales logical to physical (DPI)
constexpr DWORD kEngineTimeoutMs = 60000;

// ------------------------------------------------------------------------------------------------ model --
struct Value {
  std::string value, label;
};
struct Setting {
  std::string key, group, scope, category, label, help, note, current;
  std::vector<Value> values;
  std::vector<std::pair<std::string, std::string>> needs;
  bool slider = false;
  int min = 0, max = 0;
};
struct Model {
  bool ok = false;
  std::string settings_state, preset_label, revision = "none", language = "en";
  std::vector<std::pair<std::string, std::string>> groups;
  std::vector<Setting> settings;
  std::map<std::string, std::string> strings;
};

inline std::vector<std::string> Split(const std::string& s, char sep) {
  std::vector<std::string> out;
  size_t a = 0;
  for (;;) {
    size_t b = s.find(sep, a);
    out.push_back(s.substr(a, b == std::string::npos ? std::string::npos : b - a));
    if (b == std::string::npos) return out;
    a = b + 1;
  }
}

// The engine's tab-separated rows (r3hd_installer.py launcher_model); unknown rows are ignored like the launcher does.
inline Model ParseModel(const std::string& text) {
  Model m;
  bool header = false, end = false;
  for (std::string line : Split(text, '\n')) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    auto f = Split(line, '\t');
    auto at = [&](size_t i) { return i < f.size() ? f[i] : std::string(); };
    const std::string& k = f[0];
    if (k == "R3HD_LAUNCHER_MODEL") header = true;
    else if (k == "END") end = true;
    else if (k == "SETTINGS") { m.settings_state = at(1); m.preset_label = at(4); }
    else if (k == "REVISION") m.revision = at(1);
    else if (k == "LANG") m.language = at(2);
    else if (k == "UISTRING") m.strings[at(1)] = at(2);
    else if (k == "GROUP") m.groups.push_back({at(1), at(2)});
    else if (k == "SETTING") {
      Setting s;
      s.key = at(1); s.group = at(2); s.scope = at(3); s.category = at(4); s.label = at(5); s.help = at(6);
      s.note = at(7); s.current = at(10);
      m.settings.push_back(s);
    } else if (k == "VALUE" || k == "REQUIRES" || k == "SLIDER") {
      for (auto& s : m.settings) {
        if (s.key != at(1)) continue;
        if (k == "VALUE") s.values.push_back({at(2), at(3)});
        else if (k == "REQUIRES") s.needs.push_back({at(2), at(3)});
        else { s.slider = true; s.min = std::atoi(at(2).c_str()); s.max = std::atoi(at(3).c_str()); }
      }
    }
  }
  m.ok = header && end && !m.settings.empty();
  return m;
}

// "k=v;k=v" (play.ps1's resolved values of this launch).
inline std::map<std::string, std::string> ParsePairs(const std::string& text) {
  std::map<std::string, std::string> out;
  for (const auto& item : Split(text, ';')) {
    size_t eq = item.find('=');
    if (eq != std::string::npos && eq) out[item.substr(0, eq)] = item.substr(eq + 1);
  }
  return out;
}

// The live settings of this session and the runtime setting each one is.
inline bool IsLive(const std::string& key) {
  return key == "display" || key == "mouse_camera" || key == "mouse_sensitivity" || key == "mouse_buttons";
}
// D-138: percent -> the runtime's mouse sensitivity (play.ps1: 2 ** ((percent - 50) / 25)).
inline double SensitivityScale(int percent) { return std::pow(2.0, (percent - 50) / 25.0); }
inline int SensitivityPercent(double scale) {
  if (!(scale > 0.0)) return 50;
  return std::clamp(int(std::lround(50.0 + 25.0 * std::log2(scale))), 1, 100);
}

// ------------------------------------------------------------------------------------------------ engine --
#if !defined(_WIN32)
// POSIX: wchar_t holds one code point (UTF-32); the engine's text is UTF-8. Invalid input becomes U+FFFD.
inline std::wstring Widen(const std::string& s) {
  std::wstring w;
  for (size_t i = 0; i < s.size();) {
    const unsigned char c = static_cast<unsigned char>(s[i]);
    const int extra = c < 0x80 ? 0 : (c >> 5) == 0x6 ? 1 : (c >> 4) == 0xE ? 2 : (c >> 3) == 0x1E ? 3 : -1;
    uint32_t cp = extra == 0 ? c : extra == 1 ? (c & 0x1F) : extra == 2 ? (c & 0x0F) : (c & 0x07);
    bool ok = extra >= 0;
    for (int k = 1; ok && k <= extra; ++k) {
      if (i + k >= s.size() || (static_cast<unsigned char>(s[i + k]) & 0xC0) != 0x80) ok = false;
      else cp = (cp << 6) | (static_cast<unsigned char>(s[i + k]) & 0x3F);
    }
    if (!ok) { w.push_back(wchar_t(0xFFFD)); ++i; continue; }
    w.push_back(wchar_t(cp));
    i += size_t(extra) + 1;
  }
  return w;
}
inline std::string Narrow(const std::wstring& w) {
  std::string s;
  for (wchar_t wc : w) {
    uint32_t cp = uint32_t(wc);
    if (cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) cp = 0xFFFD;
    if (cp < 0x80) s.push_back(char(cp));
    else if (cp < 0x800) { s.push_back(char(0xC0 | (cp >> 6))); s.push_back(char(0x80 | (cp & 0x3F))); }
    else if (cp < 0x10000) {
      s.push_back(char(0xE0 | (cp >> 12))); s.push_back(char(0x80 | ((cp >> 6) & 0x3F)));
      s.push_back(char(0x80 | (cp & 0x3F)));
    } else {
      s.push_back(char(0xF0 | (cp >> 18))); s.push_back(char(0x80 | ((cp >> 12) & 0x3F)));
      s.push_back(char(0x80 | ((cp >> 6) & 0x3F))); s.push_back(char(0x80 | (cp & 0x3F)));
    }
  }
  return s;
}
inline std::wstring Env(const wchar_t* name) {
  const char* v = std::getenv(Narrow(name).c_str());
  return v ? Widen(v) : L"";
}
#else
#line 125
inline std::wstring Widen(const std::string& s) {
  if (s.empty()) return {};
  int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), int(s.size()), nullptr, 0);
  std::wstring w(size_t(n), L'\0');
  MultiByteToWideChar(CP_UTF8, 0, s.data(), int(s.size()), w.data(), n);
  return w;
}
inline std::string Narrow(const std::wstring& w) {
  if (w.empty()) return {};
  int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), int(w.size()), nullptr, 0, nullptr, nullptr);
  std::string s(size_t(n), '\0');
  WideCharToMultiByte(CP_UTF8, 0, w.data(), int(w.size()), s.data(), n, nullptr, nullptr);
  return s;
}
inline std::wstring Env(const wchar_t* name) {
  const wchar_t* v = _wgetenv(name);
  return v ? v : L"";
}
inline std::wstring Quote(const std::wstring& a) {
  std::wstring q = L"\"";
  size_t slashes = 0;
  for (wchar_t c : a) {
    if (c == L'\\') { ++slashes; q += c; continue; }
    if (c == L'"') q.append(slashes + 1, L'\\');
    slashes = 0;
    q += c;
  }
  q.append(slashes, L'\\');
  return q + L"\"";
}
#endif

// Where the engine is. Empty home: this launch did not start from an installation's settings (no persistence).
#line 157
struct Engine {
  std::wstring home, python, tools, settings_app;
  bool usable() const { return !home.empty() && !python.empty() && !tools.empty(); }
  static Engine FromEnvironment() {
    Engine e;
    if (std::getenv("R3HD_NONINTRUSIVE")) return e;  // a hidden test run never starts a process
    e.home = Env(L"R3HD_PCSET_HOME");
    e.python = Env(L"R3HD_PCSET_PYTHON");
    e.tools = Env(L"R3HD_PCSET_TOOLS");
    e.settings_app = Env(L"R3HD_PCSET_SETTINGS_APP");
    return e;
  }
};

// Runs python -B tools\r3hd_installer.py ARGS --home HOME without a window; stdout+stderr and the exit code.
#if !defined(_WIN32)
// POSIX: the same contract. stdin is /dev/null, stdout and stderr share one pipe that is poll()ed (never a blocking
// read), and a hung engine is killed at the deadline. No shell: the arguments go to posix_spawn as they are.
inline bool RunEngine(const Engine& e, const std::vector<std::wstring>& args, std::string& out, DWORD& code) {
  std::vector<std::string> items{Narrow(e.python), "-B", Narrow(e.tools) + "/r3hd_installer.py"};
  for (const auto& a : args) items.push_back(Narrow(a));
  items.push_back("--home");
  items.push_back(Narrow(e.home));
  std::vector<char*> argv;
  for (auto& item : items) argv.push_back(item.data());
  argv.push_back(nullptr);
  int fds[2];
  if (pipe(fds) != 0) return false;
  fcntl(fds[0], F_SETFD, FD_CLOEXEC);
  fcntl(fds[1], F_SETFD, FD_CLOEXEC);  // dup2 below gives the child its own inheritable copies
  posix_spawn_file_actions_t actions;
  posix_spawn_file_actions_init(&actions);
  posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0);
  posix_spawn_file_actions_adddup2(&actions, fds[1], 1);
  posix_spawn_file_actions_adddup2(&actions, fds[1], 2);
  pid_t pid = -1;
  const int spawned = posix_spawn(&pid, argv[0], &actions, nullptr, argv.data(), environ);
  posix_spawn_file_actions_destroy(&actions);
  close(fds[1]);
  if (spawned != 0) {
    close(fds[0]);
    return false;
  }
  using Clock = std::chrono::steady_clock;
  const auto deadline = Clock::now() + std::chrono::milliseconds(kEngineTimeoutMs);
  char buf[8192];
  for (;;) {
    const auto left = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count();
    if (left <= 0) break;
    pollfd p{fds[0], POLLIN, 0};
    const int ready = poll(&p, 1, int(std::min<long long>(left, 20)));
    if (ready < 0 && errno != EINTR) break;
    if (ready <= 0) continue;
    const ssize_t got = read(fds[0], buf, sizeof buf);
    if (got > 0) {
      out.append(buf, size_t(got));
      continue;
    }
    if (got < 0 && errno == EINTR) continue;
    break;  // end of file: the engine closed its output
  }
  close(fds[0]);
  int status = 0;
  bool finished = false;
  for (;;) {
    const pid_t r = waitpid(pid, &status, WNOHANG);
    if (r == pid) { finished = true; break; }
    if (r < 0 && errno != EINTR) break;
    if (Clock::now() >= deadline) break;
    usleep(20000);
  }
  if (!finished) {
    kill(pid, SIGKILL);
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
  }
  code = finished && WIFEXITED(status) ? DWORD(WEXITSTATUS(status)) : 1;
  return finished;
}
#else
#line 172
inline bool RunEngine(const Engine& e, const std::vector<std::wstring>& args, std::string& out, DWORD& code) {
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
  std::wstring cmd = Quote(e.python) + L" -B " + Quote(e.tools + L"\\r3hd_installer.py");
  for (const auto& a : args) cmd += L" " + Quote(a);
  cmd += L" --home " + Quote(e.home);
  BOOL ok = CreateProcessW(e.python.c_str(), cmd.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, nullptr,
                           &si, &pi);
  CloseHandle(wr);
  if (nul != INVALID_HANDLE_VALUE) CloseHandle(nul);
  if (!ok) {
    CloseHandle(rd);
    return false;
  }
  char buf[8192];
  const ULONGLONG deadline = GetTickCount64() + kEngineTimeoutMs;
  // Never block on the pipe: a hung engine is ended at the deadline instead of holding this worker for good.
  while (GetTickCount64() < deadline) {
    DWORD avail = 0;
    if (!PeekNamedPipe(rd, nullptr, 0, nullptr, &avail, nullptr)) break;  // writer gone and pipe drained
    if (avail) {
      DWORD got = 0;
      if (!ReadFile(rd, buf, std::min<DWORD>(avail, sizeof buf), &got, nullptr) || !got) break;
      out.append(buf, got);
      continue;
    }
    if (WaitForSingleObject(pi.hProcess, 20) == WAIT_OBJECT_0) {
      while (PeekNamedPipe(rd, nullptr, 0, nullptr, &avail, nullptr) && avail) {  // what it wrote last
        DWORD got = 0;
        if (!ReadFile(rd, buf, std::min<DWORD>(avail, sizeof buf), &got, nullptr) || !got) break;
        out.append(buf, got);
      }
      break;
    }
  }
  CloseHandle(rd);
  const ULONGLONG now = GetTickCount64();
  bool finished = WaitForSingleObject(pi.hProcess, now < deadline ? DWORD(deadline - now) : 0) == WAIT_OBJECT_0;
  if (!finished) TerminateProcess(pi.hProcess, 1);
  GetExitCodeProcess(pi.hProcess, &code);
  CloseHandle(pi.hProcess);
  CloseHandle(pi.hThread);
  return finished;
}
#endif

// One engine request on a worker thread; the panel polls it from the UI thread.
#line 227
struct Job {
  std::mutex mutex;
  bool done = false, ran = false;
  DWORD code = 1;
  std::string out, result;
};
inline std::shared_ptr<Job> Start(const Engine& e, std::vector<std::wstring> args, bool result_file) {
  auto job = std::make_shared<Job>();
  std::thread([job, e, args = std::move(args), result_file]() mutable {
    std::wstring file;
    if (result_file) {
#if !defined(_WIN32)
      const char* tmp = std::getenv("TMPDIR");
      std::string name = std::string(tmp && *tmp ? tmp : "/tmp") + "/r3pXXXXXX";
      const int fd = mkstemp(name.data());
      if (fd >= 0) {
        close(fd);
        file = Widen(name);
        args.push_back(L"--result-file");
        args.push_back(file);
      }
#else
#line 238
      wchar_t dir[MAX_PATH], name[MAX_PATH];
      GetTempPathW(MAX_PATH, dir);
      if (GetTempFileNameW(dir, L"r3p", 0, name)) {
        file = name;
        args.push_back(L"--result-file");
        args.push_back(file);
      }
#endif
#line 245
    }
    std::string out, result;
    DWORD code = 1;
    bool ran = RunEngine(e, args, out, code);
    if (!file.empty()) {
#if !defined(_WIN32)
      FILE* f = std::fopen(Narrow(file).c_str(), "rb");
      if (f) {
        char buf[4096];
        size_t n;
        while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) result.append(buf, n);
        std::fclose(f);
      }
      unlink(Narrow(file).c_str());
#else
#line 250
      FILE* f = nullptr;
      if (_wfopen_s(&f, file.c_str(), L"rb") == 0 && f) {
        char buf[4096];
        size_t n;
        while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) result.append(buf, n);
        std::fclose(f);
      }
      DeleteFileW(file.c_str());
#endif
#line 258
      if (result.rfind("\xEF\xBB\xBF", 0) == 0) result.erase(0, 3);
    }
    std::lock_guard lock(job->mutex);
    job->ran = ran;
    job->code = code;
    job->out = std::move(out);
    job->result = std::move(result);
    job->done = true;
  }).detach();
  return job;
}

inline std::string ResultField(const std::string& result, const char* name) {
  const std::string prefix = std::string(name) + "=";
  for (std::string line : Split(result, '\n')) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.rfind(prefix, 0) == 0) return line.substr(prefix.size());
  }
  return {};
}

// ------------------------------------------------------------------------------------------------ layout --
// B10 (E-319): a fixed label column let long labels (Turkish and English preset rows) run under the controls. A
// setting is now one row of a two-column table: the label column is as wide as the widest label, at most
// kLabelShare of the row and never leaving the control less than kMinControlWidth; a longer label wraps inside it.
// The control and its note share the second column and the row is as tall as its taller cell. Sizes are logical
// pixels (the drawer scales logical to physical for DPI), so the layout is the same at every display scale.
constexpr float kLabelShare = 0.45f;
constexpr float kMinControlWidth = 120.0f;
// Latin-1, Latin Extended-A (Turkish) and the typographic punctuation of the catalog.
constexpr ImWchar kFontRanges[] = {0x0020, 0x00FF, 0x0100, 0x017F, 0x2013, 0x2014, 0x2018, 0x201E, 0x2026, 0x2026, 0};

struct Box {
  ImVec2 min, max;
};
struct RowBoxes {
  Box label, control, note;
};

inline ImVec2 PanelSize(const ImVec2& view) {
  return ImVec2(std::min(760.0f, std::max(320.0f, view.x - 32.0f)), std::min(680.0f, std::max(240.0f, view.y - 32.0f)));
}
inline float LabelColumnWidth(float avail, float widest_label) {
  const float cap = std::floor(std::min(avail * kLabelShare, avail - kMinControlWidth));
  return std::max(1.0f, std::min(std::ceil(widest_label), cap));
}
inline Box LastItemBox() { return {ImGui::GetItemRectMin(), ImGui::GetItemRectMax()}; }

inline bool BeginSettingRows(const char* id, float label_column) {
  const ImGuiStyle& style = ImGui::GetStyle();
  // Half the item spacing above and below each row: the same row pitch as the untabled layout.
  ImGui::PushStyleVar(ImGuiStyleVar_CellPadding, ImVec2(style.ItemSpacing.x * 0.5f, style.ItemSpacing.y * 0.5f));
  if (!ImGui::BeginTable(id, 2, ImGuiTableFlags_None)) {
    ImGui::PopStyleVar();
    return false;
  }
  ImGui::TableSetupColumn("label", ImGuiTableColumnFlags_WidthFixed, label_column);
  ImGui::TableSetupColumn("value", ImGuiTableColumnFlags_WidthStretch);
  return true;
}
inline void EndSettingRows() {
  ImGui::EndTable();
  ImGui::PopStyleVar();
}

inline void HelpTooltip(const std::string& help) {
  const ImGuiViewport* viewport = ImGui::GetMainViewport();
  const ImGuiStyle& style = ImGui::GetStyle();
  const ImVec2 margin(std::max(4.0f, style.DisplaySafeAreaPadding.x),
                      std::max(4.0f, style.DisplaySafeAreaPadding.y));
  const ImVec2 available(viewport->WorkSize.x - 2 * margin.x, viewport->WorkSize.y - 2 * margin.y);
  const float max_text_width = std::max(1.0f, available.x - 2 * style.WindowPadding.x);
  float wrap = std::min(35.0f * ImGui::GetFontSize(), max_text_width);
  ImVec2 text = ImGui::CalcTextSize(help.c_str(), nullptr, false, wrap);
  // Use more horizontal space if a narrow wrap would make a description too tall.
  if (text.y + 2 * style.WindowPadding.y > available.y) {
    wrap = max_text_width;
    text = ImGui::CalcTextSize(help.c_str(), nullptr, false, wrap);
  }
  const ImVec2 size(std::ceil(text.x) + 2 * style.WindowPadding.x,
                    std::ceil(text.y) + 2 * style.WindowPadding.y);
  ImGui::SetNextWindowSize(size);
  if (ImGui::BeginTooltipEx(ImGuiTooltipFlags_OverridePrevious, ImGuiWindowFlags_None)) {
    // Keep ImGui's mouse/controller anchor and preferred side. Its tooltip fallback
    // may leave the viewport when no side avoids the anchor: clamp that fallback.
    const ImVec2 pos = ImGui::GetWindowPos();
    ImGui::SetWindowPos(ImVec2(
        std::clamp(pos.x, viewport->WorkPos.x + margin.x,
                   viewport->WorkPos.x + std::max(margin.x, viewport->WorkSize.x - margin.x - size.x)),
        std::clamp(pos.y, viewport->WorkPos.y + margin.y,
                   viewport->WorkPos.y + std::max(margin.y, viewport->WorkSize.y - margin.y - size.y))));
    ImGui::PushTextWrapPos(ImGui::GetCursorPosX() + wrap);
    ImGui::TextUnformatted(help.c_str());
    ImGui::PopTextWrapPos();
    ImGui::EndTooltip();
  }
}

// One setting: `control` submits a single frame-high widget (its width is set to the column). The help text is the
// tooltip of the label and the note.
template <class Control>
RowBoxes DrawSettingRow(const std::string& label, const std::string& note, const std::string& help, Control&& control) {
  RowBoxes r;
  ImGui::TableNextRow();
  ImGui::TableSetColumnIndex(0);
  ImGui::AlignTextToFramePadding();
  ImGui::PushTextWrapPos(0.0f);
  ImGui::TextUnformatted(label.c_str());
  ImGui::PopTextWrapPos();
  r.label = LastItemBox();
  bool hovered = ImGui::IsItemHovered();
  ImGui::TableSetColumnIndex(1);
  const ImVec2 at = ImGui::GetCursorScreenPos();
  r.control = {at, ImVec2(at.x + ImGui::GetContentRegionAvail().x, at.y + ImGui::GetFrameHeight())};
  ImGui::SetNextItemWidth(-FLT_MIN);
  control();
  hovered |= ImGui::IsItemFocused();  // keyboard/controller users can read the same help as mouse users
  ImGui::PushTextWrapPos(0.0f);
  ImGui::TextDisabled("%s", note.c_str());
  ImGui::PopTextWrapPos();
  r.note = LastItemBox();
  hovered |= ImGui::IsItemHovered();
  if (!help.empty() && hovered) HelpTooltip(help);
  return r;
}

// A row of buttons that continues on the next line when the next button does not fit (Turkish, narrow windows).
struct ButtonFlow {
  float avail, x = 0.0f;
  int lines = 0;
  bool draw = true;
  void Next(const std::string& label) {
    const ImGuiStyle& style = ImGui::GetStyle();
    const float w = ImGui::CalcTextSize(label.c_str(), nullptr, true).x + style.FramePadding.x * 2.0f;
    if (lines && x + style.ItemSpacing.x + w <= avail) {
      if (draw) ImGui::SameLine();
      x += style.ItemSpacing.x + w;
    } else {
      ++lines;
      x = w;
    }
  }
};
// The height under the settings: separator, the wrapped status line and the button lines.
inline float FooterHeight(const std::string& status, const std::vector<std::string>& buttons, float avail) {
  const ImGuiStyle& style = ImGui::GetStyle();
  ButtonFlow flow{avail};
  flow.draw = false;
  for (const auto& b : buttons) flow.Next(b);
  const float text = ImGui::CalcTextSize(status.c_str(), nullptr, false, avail).y;
  return (1.0f + style.ItemSpacing.y) + (text + style.ItemSpacing.y) + flow.lines * ImGui::GetFrameHeightWithSpacing() +
         style.ItemSpacing.y;
}

// ------------------------------------------------------------------------------------------------- panel --
struct Host {
  std::function<void()> closed;  // the app clears its pointer and gives the input back
  ImFont* font = nullptr;
};

class Panel final : public rex::ui::ImGuiDialog {
 public:
  Panel(rex::ui::ImGuiDrawer* drawer, Host host, Engine engine, std::map<std::string, std::string> session)
      : ImGuiDialog(drawer), host_(std::move(host)), engine_(std::move(engine)), session_(std::move(session)) {
    ReadLive();
    if (engine_.usable()) {
      Load();
    } else {
      model_ = LocalModel();
      Reset();
    }
    REXLOG_INFO("R3HD pcset open persistence={}", engine_.usable() ? "home" : "none");
  }
  void RequestClose() { close_requested_ = true; }
  // Raw pad input has no keyboard/mouse window event to wake the drawer. Keep this
  // open panel responsive even when loading stalls guest paints; closed panels do no work.
  bool NeedsContinuousRepaint() const override { return true; }

 protected:
  void OnClose() override {
    if (confirm_) RevertDisplay("close");
    REXLOG_INFO("R3HD pcset close");
    if (host_.closed) host_.closed();
  }

  void OnDraw(ImGuiIO& io) override {
    Poll();
    if (close_requested_) {
      if (confirm_) RevertDisplay("close");
      Close();
      return;
    }
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
    if (host_.font) ImGui::PushFont(host_.font, kFontSize);
    const ImVec2 view = io.DisplaySize;
    ImGui::SetNextWindowPos(ImVec2(view.x * 0.5f, view.y * 0.5f), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowSize(PanelSize(view), ImGuiCond_Always);
    ImGui::SetNextWindowBgAlpha(0.96f);
    const ImGuiWindowFlags flags = ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoResize | ImGuiWindowFlags_NoMove |
                                   ImGuiWindowFlags_NoSavedSettings;
    std::string title = T("PC Settings") + "###r3hd_pcset";
    if (!opened_) ImGui::SetNextWindowFocus();
    if (ImGui::Begin(title.c_str(), nullptr, flags)) {
      opened_ = true;
      DrawBody();
    }
    ImGui::End();
    if (confirm_) DrawConfirm(view);
    // Cancel belongs to the previously active control/popup first. ImGui may already
    // have dismissed it in NewFrame; do not let that same press also close Settings.
    back_at_root_ = !ImGui::IsAnyItemActive() && !ImGui::IsPopupOpen(nullptr, ImGuiPopupFlags_AnyPopupId);
    if (host_.font) ImGui::PopFont();
  }

 private:
  // English source text -> the Settings language (the model's UISTRING rows; English before / without a model).
  std::string T(const std::string& key) const {
    auto it = model_.strings.find(key);
    return it != model_.strings.end() && !it->second.empty() ? it->second : key;
  }
  static std::string Fill(std::string text, const char* name, const std::string& value) {
    const std::string token = std::string("{") + name + "}";
    size_t at = text.find(token);
    if (at != std::string::npos) text.replace(at, token.size(), value);
    return text;
  }

  // The live settings as the runtime has them now.
  void ReadLive() {
    live_["display"] = rex::cvar::GetFlagByName("fullscreen") == "true" ? "fullscreen" : "windowed";
    live_["mouse_camera"] = rex::cvar::GetFlagByName("mnk_mouse") == "true" ? "on" : "off";
    live_["mouse_buttons"] = rex::cvar::GetFlagByName("mnk_mouse_buttons") == "true" ? "on" : "off";
    live_["mouse_sensitivity"] =
        std::to_string(SensitivityPercent(std::atof(rex::cvar::GetFlagByName("mnk_sensitivity").c_str())));
    for (const auto& [k, v] : live_) session_[k] = v;
  }

  // Without an installation: the live settings only, labelled from the catalog's English source text.
  Model LocalModel() const {
    Model m;
    m.ok = true;
    m.groups = {{"display", "Display"}, {"mouse", "Mouse"}};
    Setting d{"display", "display", "preference", "platform", "Display mode", "", "", live_.at("display")};
    d.values = {{"windowed", "Window"}, {"fullscreen", "Fullscreen"}};
    Setting c{"mouse_camera", "mouse", "preference", "enhancement", "Mouse Camera", "", "", live_.at("mouse_camera")};
    c.values = {{"off", "Off"}, {"on", "On"}};
    Setting s{"mouse_sensitivity", "mouse", "preference", "enhancement", "Mouse Sensitivity", "", "",
              live_.at("mouse_sensitivity")};
    s.slider = true;
    s.min = 1;
    s.max = 100;
    s.needs = {{"mouse_camera", "on"}};
    Setting b{"mouse_buttons", "mouse", "preference", "enhancement", "Mouse Buttons", "", "", live_.at("mouse_buttons")};
    b.values = {{"off", "Off"}, {"on", "On"}};
    m.settings = {d, c, s, b};
    return m;
  }

  void Load() {
    loading_ = true;
    load_ = Start(engine_, {L"launcher-model"}, false);
  }
  void Reset() {
    pending_.clear();
    for (const auto& s : model_.settings) {
      // A live setting starts from what this session runs; a saved one from settings.json.
      pending_[s.key] = IsLive(s.key) ? live_[s.key] : s.current;
    }
    initial_ = pending_;
  }
  const Setting* Find(const std::string& key) const {
    for (const auto& s : model_.settings)
      if (s.key == key) return &s;
    return nullptr;
  }
  std::string ValueLabel(const Setting& s, const std::string& v) const {
    for (const auto& x : s.values)
      if (x.value == v) return T(x.label);
    return v;
  }
  bool Editable(const Setting& s) const {
    if (s.scope != "preference") return false;
    return engine_.usable() || IsLive(s.key);
  }
  bool Satisfied(const Setting& s) const {
    for (const auto& [other, value] : s.needs) {
      auto it = pending_.find(other);
      if (it != pending_.end() && it->second != value) return false;
    }
    return true;
  }
  // Only what the person changed in this panel counts: a live value that differs from the saved one (a launch
  // parameter) is never saved behind their back.
  bool Changed(const std::string& key) const {
    auto a = pending_.find(key), b = initial_.find(key);
    return a != pending_.end() && b != initial_.end() && a->second != b->second;
  }
  bool Dirty() const {
    for (const auto& s : model_.settings)
      if (Editable(s) && Changed(s.key)) return true;
    return false;
  }

  void Poll() {
    if (load_) {
      std::lock_guard lock(load_->mutex);
      if (load_->done) {
        Model m = load_->ran && load_->code == 0 ? ParseModel(load_->out) : Model{};
        if (m.ok) {
          model_ = std::move(m);
          status_ = stale_ ? T("The settings were changed in the Settings app while this panel was open. They were reloaded: check them and apply again.") : status_;
          error_ = stale_;
        } else {
          REXLOG_WARN("R3HD pcset model=unavailable code={}", load_->code);
          model_ = LocalModel();
          engine_ = Engine{};  // no persistence for the rest of this panel; the live options still work
          status_ = T("The saved settings could not be read. Only the options of this session are shown.");
          error_ = true;
        }
        stale_ = false;
        Reset();
        loading_ = false;
        load_.reset();
      }
    }
    if (save_) {
      std::lock_guard lock(save_->mutex);
      if (save_->done) {
        const std::string code = ResultField(save_->result, "CODE");
        if (save_->ran && save_->code == 0) {
          status_ = T("Saved.");
          error_ = false;
          REXLOG_INFO("R3HD pcset saved");
        } else if (code == "STALE") {
          stale_ = true;
          REXLOG_INFO("R3HD pcset saved=stale");
        } else {
          status_ = T("Settings could not be saved. Check folder access and try again.");
          error_ = true;
          REXLOG_WARN("R3HD pcset saved=failed code={} exit={}", code, save_->code);
        }
        saving_ = false;
        save_.reset();
        Load();  // the model again: its current values, revision and (after STALE) the newer file
      }
    }
    if (confirm_ && ImGui::GetTime() >= confirm_deadline_) RevertDisplay("timeout");
  }

  // ------------------------------------------------------------------------------------------- apply --
  void SetLive(const std::string& key, const std::string& value) {
    if (key == "display") rex::cvar::SetFlagByName("fullscreen", value == "fullscreen" ? "true" : "false");
    else if (key == "mouse_camera") rex::cvar::SetFlagByName("mnk_mouse", value == "on" ? "true" : "false");
    else if (key == "mouse_buttons") rex::cvar::SetFlagByName("mnk_mouse_buttons", value == "on" ? "true" : "false");
    else if (key == "mouse_sensitivity") {
      char text[32];
      std::snprintf(text, sizeof text, "%.6f", SensitivityScale(std::atoi(value.c_str())));
      rex::cvar::SetFlagByName("mnk_sensitivity", text);
    }
    live_[key] = value;
    session_[key] = value;
  }
  void Apply() {
    if (loading_ || saving_ || confirm_) return;
    for (const char* key : {"mouse_camera", "mouse_sensitivity", "mouse_buttons"}) {
      if (pending_.count(key) && pending_[key] != live_[key]) SetLive(key, pending_[key]);
    }
    if (pending_.count("display") && pending_["display"] != live_["display"]) {
      confirm_previous_ = live_["display"];
      SetLive("display", pending_["display"]);
      confirm_ = true;
      confirm_focus_ = true;
      confirm_deadline_ = ImGui::GetTime() + kConfirmSeconds;
      REXLOG_INFO("R3HD pcset display={} confirm=pending", live_["display"]);
      return;  // saved after Keep
    }
    Persist();
  }
  void KeepDisplay() {
    confirm_ = false;
    REXLOG_INFO("R3HD pcset display={} confirm=kept", live_["display"]);
    Persist();
  }
  void RevertDisplay(const char* why) {
    confirm_ = false;
    SetLive("display", confirm_previous_);
    pending_["display"] = confirm_previous_;
    REXLOG_INFO("R3HD pcset display={} confirm=reverted reason={}", confirm_previous_, why);
    status_ = T("The previous display mode was restored.");
    error_ = false;
    Persist();
  }
  void Persist() {
    if (!engine_.usable()) {
      status_ = T("Applied to this session only: this launch did not start from an installation's settings.");
      error_ = false;
      return;
    }
    std::vector<std::wstring> args{L"set-preferences", L"--expect-revision", Widen(model_.revision), L"--set"};
    size_t named = 0;
    for (const auto& s : model_.settings) {
      if (!Editable(s)) continue;
      auto it = pending_.find(s.key);
      if (it == pending_.end() || !Changed(s.key) || it->second == s.current) continue;
      args.push_back(Widen(s.key + "=" + it->second));
      ++named;
    }
    if (!named) {
      status_ = T("Applied.");
      error_ = false;
      return;
    }
    saving_ = true;
    status_ = T("Saving...");
    error_ = false;
    save_ = Start(engine_, std::move(args), true);
  }

  // -------------------------------------------------------------------------------------------- draw --
  void DrawBody() {
    const std::string footer_text =
        status_.empty() ? T("F4 or Esc closes this panel. Changes that are not applied are discarded.") : status_;
    const std::vector<std::string> buttons{T("Apply"), T("Discard changes"), T("Close")};
    const float footer = FooterHeight(footer_text, buttons, ImGui::GetContentRegionAvail().x);
    ImGui::BeginChild("##settings", ImVec2(0.0f, -footer), ImGuiChildFlags_NavFlattened);
    ImGui::PushTextWrapPos(0.0f);
    ImGui::TextDisabled("%s", T("The game keeps running while this panel is open. Pause first during gameplay.").c_str());
    if (!model_.preset_label.empty())
      ImGui::TextUnformatted(Fill(T("Profile: {profile}"), "profile", T(model_.preset_label)).c_str());
    ImGui::PopTextWrapPos();
    if (loading_) {
      ImGui::Spacing();
      ImGui::TextUnformatted(T("Loading settings...").c_str());
    } else {
      // One label column for every group, so the controls line up down the whole panel.
      float widest = 0.0f;
      for (const auto& s : model_.settings) widest = std::max(widest, ImGui::CalcTextSize(T(s.label).c_str()).x);
      const float label_column = LabelColumnWidth(ImGui::GetContentRegionAvail().x, widest);
      for (const auto& [group, name] : model_.groups) {
        bool any = false;
        for (const auto& s : model_.settings) any |= s.group == group;
        if (!any) continue;
        ImGui::Spacing();
        ImGui::SeparatorText(T(name).c_str());
        if (!BeginSettingRows(group.c_str(), label_column)) continue;
        for (const auto& s : model_.settings)
          if (s.group == group) DrawSetting(s);
        EndSettingRows();
      }
      ImGui::Spacing();
      ImGui::SeparatorText(T("Controls").c_str());
      ImGui::PushTextWrapPos(0.0f);
      ImGui::TextUnformatted(
          T("Keyboard and controller controls, and the profile's corrections, are changed in the Settings app.").c_str());
      ImGui::PopTextWrapPos();
      ImGui::BeginDisabled(loading_ || saving_ || confirm_);
      if (!engine_.settings_app.empty() && ImGui::Button(T("Open Settings app").c_str())) OpenSettingsApp();
      ImGui::EndDisabled();
    }
    ImGui::EndChild();

    ImGui::Separator();
    ImGui::PushTextWrapPos(0.0f);
    if (!status_.empty()) {
      if (error_) ImGui::TextColored(ImVec4(1.0f, 0.55f, 0.45f, 1.0f), "%s", status_.c_str());
      else ImGui::TextUnformatted(status_.c_str());
    } else {
      ImGui::TextDisabled("%s", footer_text.c_str());
    }
    ImGui::PopTextWrapPos();
    const bool busy = loading_ || saving_ || confirm_;
    ButtonFlow flow{ImGui::GetContentRegionAvail().x};
    ImGui::BeginDisabled(busy || !Dirty());
    flow.Next(buttons[0]);
    if (ImGui::Button(buttons[0].c_str())) Apply();
    flow.Next(buttons[1]);
    if (ImGui::Button(buttons[1].c_str())) {
      Reset();
      status_.clear();
    }
    ImGui::EndDisabled();
    flow.Next(buttons[2]);
    ImGui::BeginDisabled(confirm_);
    if (ImGui::Button(buttons[2].c_str())) close_requested_ = true;
    ImGui::EndDisabled();
    if (!confirm_ && back_at_root_ && !ImGui::IsAnyItemActive() &&
        !ImGui::IsPopupOpen(nullptr, ImGuiPopupFlags_AnyPopupId) &&
        (ImGui::IsKeyPressed(ImGuiKey_Escape, false) || ImGui::IsKeyPressed(ImGuiKey_GamepadFaceRight, false)))
      close_requested_ = true;
  }

  void DrawSetting(const Setting& s) {
    ImGui::PushID(s.key.c_str());
    const bool editable = Editable(s) && !loading_ && !saving_ && !confirm_;
    const bool allowed = Satisfied(s);
    std::string& value = pending_[s.key];
    // The truth about when it acts: live, next start, or Settings only; and what this session runs.
    std::string when;
    if (s.scope != "preference") when = T("Set by the profile; change it in the Settings app.");
    else if (!Editable(s)) when = T("Can be changed in the Settings app.");
    else if (IsLive(s.key)) when = T("Applies now.");
    else when = T("Applies the next time the game starts.");
    auto running = session_.find(s.key);
    if (s.scope == "preference" && !IsLive(s.key) && running != session_.end() && running->second != value)
      when += "  " + Fill(T("This session: {value}"), "value", s.slider ? running->second + " %" : ValueLabel(s, running->second));
    DrawSettingRow(T(s.label), when, s.help.empty() ? std::string() : T(s.help), [&] {
      ImGui::BeginDisabled(!editable || !allowed);
      if (s.slider) {
        int v = std::clamp(std::atoi(value.c_str()), s.min, s.max);
        if (ImGui::SliderInt("##v", &v, s.min, s.max, "%d %%", ImGuiSliderFlags_AlwaysClamp)) value = std::to_string(v);
      } else if (ImGui::BeginCombo("##v", ValueLabel(s, value).c_str())) {
        for (const auto& x : s.values) {
          if (ImGui::Selectable(T(x.label).c_str(), x.value == value)) value = x.value;
          if (x.value == value) ImGui::SetItemDefaultFocus();
        }
        ImGui::EndCombo();
      }
      ImGui::EndDisabled();
    });
    ImGui::PopID();
  }

  void DrawConfirm(const ImVec2& view) {
    ImGui::SetNextWindowPos(ImVec2(view.x * 0.5f, view.y * 0.5f), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowSize(ImVec2(std::min(520.0f, std::max(300.0f, view.x - 48.0f)), 0.0f), ImGuiCond_Always);
    ImGui::SetNextWindowFocus();
    const ImGuiWindowFlags flags = ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoResize | ImGuiWindowFlags_NoMove |
                                   ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_AlwaysAutoResize;
    std::string title = T("Keep this display mode?") + "###r3hd_pcset_confirm";
    if (ImGui::Begin(title.c_str(), nullptr, flags)) {
      const int left = std::max(0, int(std::ceil(confirm_deadline_ - ImGui::GetTime())));
      ImGui::PushTextWrapPos(0.0f);
      ImGui::TextUnformatted(
          Fill(T("The previous display mode returns in {seconds} seconds unless you keep this one."), "seconds",
               std::to_string(left)).c_str());
      ImGui::PopTextWrapPos();
      if (ImGui::Button(T("Keep").c_str())) KeepDisplay();
      ImGui::SameLine();
      if (confirm_focus_) { ImGui::SetKeyboardFocusHere(); confirm_focus_ = false; }
      if (ImGui::Button(T("Revert").c_str()) || ImGui::IsKeyPressed(ImGuiKey_Escape, false) ||
          ImGui::IsKeyPressed(ImGuiKey_GamepadFaceRight, false)) RevertDisplay("person");
    }
    ImGui::End();
  }

  void OpenSettingsApp() {
#if !defined(_WIN32)
    // POSIX: only when a launcher names a Settings application (the Linux launcher has none yet, so the button is
    // hidden). The child is reaped on its own thread; the game never waits for it.
    std::string app = Narrow(engine_.settings_app);
    char* argv[] = {app.data(), nullptr};
    pid_t pid = -1;
    if (posix_spawn(&pid, app.c_str(), nullptr, nullptr, argv, environ) == 0) {
      std::thread([pid] { int status = 0; while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {} }).detach();
      status_ = T("Settings is open. Its changes apply the next time the game starts.");
      error_ = false;
      REXLOG_INFO("R3HD pcset settings_app=started");
    } else {
      status_ = T("The Settings app could not be started.");
      error_ = true;
    }
    return;
#endif
#if defined(_WIN32)
#line 759
    STARTUPINFOW si{sizeof si};
    PROCESS_INFORMATION pi{};
    std::wstring cmd = Quote(engine_.settings_app);
    if (CreateProcessW(engine_.settings_app.c_str(), cmd.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi)) {
      CloseHandle(pi.hProcess);
      CloseHandle(pi.hThread);
      status_ = T("Settings is open. Its changes apply the next time the game starts.");
      error_ = false;
      REXLOG_INFO("R3HD pcset settings_app=started");
    } else {
      status_ = T("The Settings app could not be started.");
      error_ = true;
    }
#endif
#line 772
  }

  Host host_;
  Engine engine_;
  Model model_;
  std::map<std::string, std::string> session_, live_, pending_, initial_;
  std::shared_ptr<Job> load_, save_;
  bool loading_ = false, saving_ = false, stale_ = false, opened_ = false, close_requested_ = false, error_ = false;
  bool confirm_ = false;
  bool confirm_focus_ = false, back_at_root_ = true;
  double confirm_deadline_ = 0.0;
  std::string confirm_previous_, status_;
};

}  // namespace r3hd_pcset

// LX-4: the panel's font on POSIX. r3hd_app.h's OnConfigureFonts begins with R3HD_PCSET_POSIX_FONTS on its first line
// (so no Windows line moves); on Windows the macro is empty, so the Windows tokens and lines are unchanged. On Linux
// it loads the first common distribution font that has Latin Extended-A (Turkish), else the Windows search below it
// finds nothing and the panel keeps ImGui's default font.
#if !defined(_WIN32)
#include <filesystem>
namespace r3hd_pcset {
inline bool PosixFont(ImFontAtlas* atlas, ImFont*& font) {
  for (const char* path : {"/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                           "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                           "/usr/share/fonts/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
                           "/usr/share/fonts/google-noto/NotoSans-Regular.ttf",
                           "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
                           "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"}) {
    std::error_code error;
    if (!std::filesystem::is_regular_file(path, error)) continue;
    ImFontConfig config;
    config.OversampleH = 2;
    config.OversampleV = 1;
    font = atlas->AddFontFromFileTTF(path, kFontSize, &config, kFontRanges);
    if (!font) continue;
    REXLOG_INFO("R3HD pcset font={}", path);
    return true;
  }
  return false;
}
}  // namespace r3hd_pcset
#define R3HD_PCSET_POSIX_FONTS(atlas, font) if (r3hd_pcset::PosixFont(atlas, font)) return;
#else
#define R3HD_PCSET_POSIX_FONTS(atlas, font)
#endif

// M20 (D-049): staged replacement of saved-game content.
//
// The pinned content manager serves XamContentCreate(CREATE_ALWAYS) by deleting the existing content directory
// and its header file, and the title then writes the new file into the emptied directory. A process that dies
// in between has lost the previous save. Here the new content is written into a private staging directory on
// the same volume instead; the live content is replaced file by file with an atomic rename when the guest
// closes the content, after the staged data has been flushed. Until that rename the previous save is untouched.
//
// Host-only and free of SDK types so that tools/m20_save_commit_test.cpp can exercise it alone.
//
// Layout below <content root>/<xuid>/<title id>/ (the staging directory is a sibling of the content-type
// directories and of Headers, so no content enumeration ever lists it):
//   .staging/<pid>.<seq>/content/   mounted as the guest's content root while the content is open
//   .staging/<pid>.<seq>/header     the new header file, when it differs from the live one
//
// Guarantees: see reports/milestone20/REPORT.md. Safety against the end of the process is tested. Against power
// loss nothing is claimed: the staged data is flushed (FlushFileBuffers) before the rename, the rename itself
// is a metadata operation whose durability is the file system's business, and none of it was tested.
#pragma once

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cwctype>
#include <filesystem>
#include <mutex>
#include <set>
#include <string>
#include <system_error>
#include <vector>

namespace m20save {

// Test-only fault points (R3HD_SAVE_FAULT=<name>[:<n>] fires once, at the n-th time the point is passed,
// default the first). Never set by tools/play.ps1.
enum class Fault : int {
  kNone = 0,
  kStageCreate,       // the staging directory cannot be created
  kWrite,             // a guest write into staged content is cut short by the host
  kFlush,             // flushing a staged file fails
  kBeforeReplace,     // the commit is abandoned just before the first rename
  kReplace,           // the rename onto the live file fails
  kHeaderReplace,     // the rename of the header file fails (after the data is committed)
  kCleanup,           // the staging directory cannot be removed after a successful commit
  kExitAfterCreate,   // the process ends right after the content was created (old or new write path)
  kExitBeforeCommit,  // the process ends at close, after the flush and before the first rename
};

enum class Result : int {
  kOk = 0,
  kStageFailed,    // nothing staged; live content untouched
  kWriteFailed,    // a host write into the stage failed earlier; live content untouched
  kFlushFailed,    // live content untouched
  kAbandoned,      // test fault before the first rename; live content untouched
  kEmptyRefused,   // nothing was staged over content that has files; live content untouched
  kReplaceFailed,  // a data rename failed; with one staged file the live content and header are untouched
};

inline const char* Name(Result r) {
  switch (r) {
    case Result::kOk: return "ok";
    case Result::kStageFailed: return "stage_failed";
    case Result::kWriteFailed: return "write_failed";
    case Result::kFlushFailed: return "flush_failed";
    case Result::kAbandoned: return "abandoned";
    case Result::kEmptyRefused: return "empty_refused";
    case Result::kReplaceFailed: return "replace_failed";
  }
  return "?";
}

struct Stage {
  std::filesystem::path base;     // .staging/<pid>.<seq>
  std::filesystem::path content;  // base / "content"
  std::filesystem::path live;     // the content directory that a commit replaces
  std::filesystem::path header;   // the live header file ("" = none)
  std::vector<uint8_t> header_bytes;
  bool valid() const { return !base.empty(); }
};

constexpr const wchar_t* kStagingDirName = L".staging";
constexpr int kExitCode = 0x4D20;  // "M20": a process ended by a kExit* fault

struct State {
  std::mutex mutex;
  std::set<std::filesystem::path> active;    // stage bases owned by this process
  std::set<std::filesystem::path> poisoned;  // stage bases that saw a failed host write
  Fault fault = Fault::kNone;
  int fault_countdown = 0;
  bool fault_read = false;
  void (*log)(const char*) = nullptr;
};

inline State& state() {
  static State s;
  return s;
}

inline void Log(const std::string& line) {
  if (auto fn = state().log) fn(line.c_str());
}

inline std::string Utf8(const std::filesystem::path& p) {
  auto u8 = p.generic_u8string();
  return std::string(u8.begin(), u8.end());
}

// R3HD_SAVE_COMMIT=legacy selects the pinned delete-then-write sequence (comparison only).
inline bool Enabled() {
  static const bool enabled = [] {
    const char* v = std::getenv("R3HD_SAVE_COMMIT");
    return !(v && std::strcmp(v, "legacy") == 0);
  }();
  return enabled;
}

inline Fault ParseFault(const std::string& name) {
  static const struct { const char* name; Fault fault; } table[] = {
      {"stage_create", Fault::kStageCreate},       {"write", Fault::kWrite},
      {"flush", Fault::kFlush},                    {"before_replace", Fault::kBeforeReplace},
      {"replace", Fault::kReplace},                {"cleanup", Fault::kCleanup},
      {"header_replace", Fault::kHeaderReplace},
      {"exit_after_create", Fault::kExitAfterCreate},
      {"exit_before_commit", Fault::kExitBeforeCommit},
  };
  for (const auto& row : table) {
    if (name == row.name) return row.fault;
  }
  return Fault::kNone;
}

// Arms one fault (tests). `nth` = fire at the n-th passage of the point.
inline void SetFault(Fault fault, int nth = 1) {
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  s.fault = fault;
  s.fault_countdown = nth < 1 ? 1 : nth;
  s.fault_read = true;
}

inline bool FaultArmed() {
  auto& s = state();
  if (!s.fault_read) {
    std::lock_guard<std::mutex> lock(s.mutex);
    if (!s.fault_read) {
      if (const char* v = std::getenv("R3HD_SAVE_FAULT")) {
        std::string text(v);
        auto colon = text.find(':');
        s.fault = ParseFault(text.substr(0, colon));
        s.fault_countdown = colon == std::string::npos ? 1 : std::max(1, std::atoi(text.c_str() + colon + 1));
      }
      s.fault_read = true;
    }
  }
  return s.fault != Fault::kNone;
}

// True exactly once, when the armed fault's point is passed for the n-th time.
inline bool Fire(Fault point) {
  if (!FaultArmed()) return false;
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (s.fault != point) return false;
  if (--s.fault_countdown > 0) return false;
  s.fault = Fault::kNone;
  return true;
}

// Ends the process at a kExit* point, without unwinding: what a crash or a kill at that point leaves on disk.
inline void FaultExit(Fault point) {
  if (!Fire(point)) return;
  Log(std::string("M20 save fault=exit point=") +
      (point == Fault::kExitAfterCreate ? "after_create" : "before_commit"));
  TerminateProcess(GetCurrentProcess(), UINT(kExitCode));
}

inline bool IsStageName(const std::wstring& name, uint32_t* pid_out) {
  auto dot = name.find(L'.');
  if (dot == std::wstring::npos || dot == 0 || dot + 1 >= name.size()) return false;
  for (size_t i = 0; i < name.size(); ++i) {
    if (i != dot && (name[i] < L'0' || name[i] > L'9')) return false;
  }
  if (dot > 10) return false;
  *pid_out = uint32_t(std::wcstoul(name.substr(0, dot).c_str(), nullptr, 10));
  return true;
}

inline bool ProcessAlive(uint32_t pid) {
  if (pid == GetCurrentProcessId()) return true;
  HANDLE h = OpenProcess(SYNCHRONIZE, FALSE, pid);
  if (!h) {
    // No such process -> dead. Anything else (access denied): assume alive and leave its files alone.
    return GetLastError() != ERROR_INVALID_PARAMETER;
  }
  bool alive = WaitForSingleObject(h, 0) == WAIT_TIMEOUT;
  CloseHandle(h);
  return alive;
}

// Removes stage directories left by a process that no longer exists (or by this process, when not in use).
// Touches only entries of `staging_root` named <digits>.<digits>; returns how many it removed.
inline size_t Sweep(const std::filesystem::path& staging_root) {
  std::error_code ec;
  if (!std::filesystem::is_directory(staging_root, ec)) return 0;
  std::vector<std::filesystem::path> stale;
  for (std::filesystem::directory_iterator it(staging_root, ec), end; !ec && it != end; it.increment(ec)) {
    uint32_t pid = 0;
    if (!it->is_directory(ec) || !IsStageName(it->path().filename().wstring(), &pid)) continue;
    if (pid == GetCurrentProcessId()) {
      auto& s = state();
      std::lock_guard<std::mutex> lock(s.mutex);
      if (s.active.count(it->path())) continue;
    } else if (ProcessAlive(pid)) {
      continue;
    }
    stale.push_back(it->path());
  }
  size_t removed = 0;
  for (const auto& path : stale) {
    std::error_code rec;
    std::filesystem::remove_all(path, rec);
    if (!rec && !std::filesystem::exists(path, rec)) {
      ++removed;
      Log("M20 save sweep removed=" + Utf8(path.filename()));
    } else {
      Log("M20 save sweep kept=" + Utf8(path.filename()) + " error=" + rec.message());
    }
  }
  std::filesystem::remove(staging_root, ec);  // only when empty
  return removed;
}

// Creates a fresh stage below `staging_root`. On failure nothing is left behind and `out` stays invalid.
inline bool Begin(const std::filesystem::path& staging_root, Stage* out) {
  *out = Stage{};
  if (Fire(Fault::kStageCreate)) {
    Log("M20 save fault=stage_create");
    return false;
  }
  static uint32_t sequence = 0;
  std::error_code ec;
  std::filesystem::create_directories(staging_root, ec);
  if (ec) return false;
  auto& s = state();
  for (int attempt = 0; attempt < 64; ++attempt) {
    std::filesystem::path base;
    {
      std::lock_guard<std::mutex> lock(s.mutex);
      base = staging_root / (std::to_wstring(GetCurrentProcessId()) + L"." + std::to_wstring(++sequence));
    }
    // Registered before it exists, so that a concurrent Sweep of this process never takes it for a leftover.
    {
      std::lock_guard<std::mutex> lock(s.mutex);
      s.active.insert(base);
    }
    auto drop = [&s, &base] {
      std::lock_guard<std::mutex> lock(s.mutex);
      s.active.erase(base);
    };
    // create_directory is false when the name exists (a leftover of an earlier process with this pid).
    if (!std::filesystem::create_directory(base, ec) || ec) {
      drop();
      std::filesystem::create_directories(staging_root, ec);  // another process may have removed the empty root
      continue;
    }
    if (!std::filesystem::create_directory(base / L"content", ec) || ec) {
      std::filesystem::remove_all(base, ec);
      drop();
      return false;
    }
    out->base = base;
    out->content = base / L"content";
    return true;
  }
  return false;
}

// Host write path: a write into `host_path` failed or was short. Marks the stage that holds the file.
inline void NoteWriteFailure(const std::filesystem::path& host_path) {
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  for (const auto& base : s.active) {
    auto rel = host_path.lexically_relative(base);
    if (!rel.empty() && *rel.begin() != L"..") {
      s.poisoned.insert(base);
      return;
    }
  }
}

inline bool InActiveStage(const std::filesystem::path& host_path) {
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  for (const auto& base : s.active) {
    auto rel = host_path.lexically_relative(base);
    if (!rel.empty() && *rel.begin() != L"..") return true;
  }
  return false;
}

inline void Release(const Stage& stage) {
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  s.active.erase(stage.base);
  s.poisoned.erase(stage.base);
}

// Drops a stage without touching the live content.
inline void Abort(Stage& stage) {
  if (!stage.valid()) return;
  std::error_code ec;
  std::filesystem::remove_all(stage.base, ec);
  Release(stage);
  std::filesystem::remove(stage.base.parent_path(), ec);  // only when empty
  stage = Stage{};
}

inline bool FlushFile(const std::filesystem::path& path) {
  HANDLE h = CreateFileW(path.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                         nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (h == INVALID_HANDLE_VALUE) return false;
  bool ok = FlushFileBuffers(h) != 0;
  CloseHandle(h);
  return ok;
}

// Atomic rename onto `to` (replacing it). A reader that holds the target without delete sharing (a copy in
// progress, a scanner) gets a few short retries; after that the rename fails and the target is what it was.
inline bool ReplaceFile_(const std::filesystem::path& from, const std::filesystem::path& to, DWORD* error) {
  for (int attempt = 0; attempt < 25; ++attempt) {
    if (MoveFileExW(from.c_str(), to.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
      *error = 0;
      return true;
    }
    *error = GetLastError();
    if (*error != ERROR_SHARING_VIOLATION && *error != ERROR_ACCESS_DENIED && *error != ERROR_LOCK_VIOLATION) {
      return false;
    }
    Sleep(10);
  }
  return false;
}

inline FILE* OpenFileW(const std::filesystem::path& path, const wchar_t* mode) {
  FILE* f = nullptr;
  return _wfopen_s(&f, path.c_str(), mode) == 0 ? f : nullptr;
}

inline bool SameBytes(const std::filesystem::path& path, const std::vector<uint8_t>& bytes) {
  std::error_code ec;
  if (!std::filesystem::is_regular_file(path, ec) || std::filesystem::file_size(path, ec) != bytes.size()) {
    return false;
  }
  FILE* f = OpenFileW(path, L"rb");
  if (!f) return false;
  std::vector<uint8_t> have(bytes.size());
  size_t n = have.empty() ? 0 : std::fread(have.data(), 1, have.size(), f);
  std::fclose(f);
  return n == bytes.size() && have == bytes;
}

inline bool WriteBytes(const std::filesystem::path& path, const std::vector<uint8_t>& bytes) {
  FILE* f = OpenFileW(path, L"wb");
  if (!f) return false;
  size_t n = bytes.empty() ? 0 : std::fwrite(bytes.data(), 1, bytes.size(), f);
  bool ok = std::fclose(f) == 0 && n == bytes.size();
  return ok && FlushFile(path);
}

inline std::wstring Folded(const std::filesystem::path& p) {
  std::wstring s = p.generic_wstring();
  for (auto& c : s) c = wchar_t(std::towlower(c));
  return s;
}

inline bool HasEntries(const std::filesystem::path& dir) {
  std::error_code ec;
  std::filesystem::directory_iterator it(dir, ec);
  return !ec && it != std::filesystem::directory_iterator();
}

// Replaces the live content by the staged one. The data files are renamed first, the header file last. Every
// failure before the first rename leaves the live content and its header byte-identical; with one staged file
// (this title) that covers every failure of the data. The stage is removed in every case (or left for Sweep
// when removal fails).
inline Result Commit(Stage& stage) {
  if (!stage.valid()) return Result::kStageFailed;
  std::error_code ec;
  bool live_created = false;
  auto fail = [&stage, &live_created](Result r, const std::string& detail) {
    Log(std::string("M20 save commit result=") + Name(r) + " " + detail);
    if (live_created) {
      std::error_code rec;
      std::filesystem::remove(stage.live, rec);  // a first save that failed leaves no empty slot; only if empty
    }
    Abort(stage);
    return r;
  };
  bool poisoned = false;
  {
    auto& s = state();
    std::lock_guard<std::mutex> lock(s.mutex);
    poisoned = s.poisoned.count(stage.base) != 0;
  }
  if (poisoned) return fail(Result::kWriteFailed, "a host write into the staged content failed");

  std::vector<std::filesystem::path> files, dirs;
  for (std::filesystem::recursive_directory_iterator it(stage.content, ec), end; !ec && it != end;
       it.increment(ec)) {
    auto rel = it->path().lexically_relative(stage.content);
    (it->is_directory(ec) ? dirs : files).push_back(rel);
  }
  if (ec) return fail(Result::kFlushFailed, "cannot enumerate the stage: " + ec.message());
  std::sort(files.begin(), files.end());

  // The guest closed content it wrote nothing into, over content that has files: the signature of a create or
  // write that failed on the way. The existing content is kept and the close reports the failure.
  if (files.empty() && HasEntries(stage.live)) {
    return fail(Result::kEmptyRefused, "nothing was written; the existing content is kept");
  }

  for (const auto& rel : files) {
    if (Fire(Fault::kFlush) || !FlushFile(stage.content / rel)) {
      return fail(Result::kFlushFailed, "file=" + Utf8(rel));
    }
  }
  const bool new_header = !stage.header.empty() && !SameBytes(stage.header, stage.header_bytes);
  if (new_header && !WriteBytes(stage.base / L"header", stage.header_bytes)) {
    return fail(Result::kFlushFailed, "header");
  }

  FaultExit(Fault::kExitBeforeCommit);
  if (Fire(Fault::kBeforeReplace)) return fail(Result::kAbandoned, "fault=before_replace");

  live_created = !std::filesystem::exists(stage.live, ec);
  std::filesystem::create_directories(stage.live, ec);
  if (ec) return fail(Result::kReplaceFailed, "cannot create the content directory: " + ec.message());
  DWORD error = 0;
  size_t replaced = 0;
  for (const auto& rel : files) {
    if (rel.has_parent_path()) {
      std::filesystem::create_directories((stage.live / rel).parent_path(), ec);
      if (ec) return fail(Result::kReplaceFailed, "cannot create the directory of " + Utf8(rel));
    }
    bool ok = !Fire(Fault::kReplace);
    if (!ok) error = ERROR_ACCESS_DENIED;
    if (!ok || !ReplaceFile_(stage.content / rel, stage.live / rel, &error)) {
      return fail(Result::kReplaceFailed, "file=" + Utf8(rel) + " error=" + std::to_string(error) +
                                              " replaced_before=" + std::to_string(replaced));
    }
    ++replaced;
    live_created = false;  // the content exists now
  }
  live_created = false;
  for (const auto& rel : dirs) {
    std::filesystem::create_directories(stage.live / rel, ec);  // directories the guest left empty
  }

  // The data is committed. The header (the content manager's own record: names and ids, no save data) follows;
  // a failure here is logged and does not undo the save. Enumeration works without a current header.
  const char* header_state = "same";
  if (new_header) {
    std::filesystem::create_directories(stage.header.parent_path(), ec);
    bool ok = !ec && !Fire(Fault::kHeaderReplace) && ReplaceFile_(stage.base / L"header", stage.header, &error);
    header_state = ok ? "written" : "FAILED";
  }

  // CREATE_ALWAYS semantics: what the new content does not contain is gone. Only after every rename.
  // Names are compared the way the file system compares them (a renamed directory keeps its old spelling).
  std::set<std::wstring> keep;
  for (const auto& rel : files) keep.insert(Folded(rel));
  for (const auto& rel : dirs) keep.insert(Folded(rel));
  for (const auto& rel : files) {
    for (auto parent = rel.parent_path(); !parent.empty(); parent = parent.parent_path()) keep.insert(Folded(parent));
  }
  std::vector<std::filesystem::path> extra;
  for (std::filesystem::recursive_directory_iterator it(stage.live, ec), end; !ec && it != end;
       it.increment(ec)) {
    if (!keep.count(Folded(it->path().lexically_relative(stage.live)))) {
      extra.push_back(it->path());
      if (it->is_directory(ec)) it.disable_recursion_pending();
    }
  }
  for (const auto& path : extra) {
    std::filesystem::remove_all(path, ec);
    Log("M20 save commit removed_old=" + Utf8(path.filename()) + (ec ? " error=" + ec.message() : ""));
  }

  size_t count = files.size();
  if (Fire(Fault::kCleanup)) {
    Log("M20 save fault=cleanup stage_left=" + Utf8(stage.base.filename()));
    Release(stage);
    stage = Stage{};
  } else {
    Abort(stage);
  }
  Log("M20 save commit result=ok files=" + std::to_string(count) + " header=" + header_state);
  return Result::kOk;
}

}  // namespace m20save

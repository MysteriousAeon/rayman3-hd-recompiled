// M20 (D-049): deterministic fault-injection tests of the staged save replacement. Host-only, no game material:
// every file is synthetic and lives in a private directory below the system temporary directory.
#if defined(_WIN32)
//   m20_save_commit_test.exe                 -> "m20_save_commit_test checks=N failures=0"
//   m20_save_commit_test.exe child DIR POINT    (internal: a process that ends itself at a fault point)
#include "m20_save_commit.h"

#include <chrono>
#include <cstdio>
#include <string>
#include <thread>

namespace fs = std::filesystem;
using Bytes = std::vector<uint8_t>;
using namespace m20save;

static int checks = 0, failures = 0;
static void Check(bool ok, const std::string& what) {
  ++checks;
  if (!ok) {
    ++failures;
    std::printf("FAIL %s\n", what.c_str());
  }
}

static Bytes Pattern(size_t size, uint8_t seed) {
  Bytes b(size);
  for (size_t i = 0; i < size; ++i) b[i] = uint8_t(seed + i * 7);
  return b;
}

static bool Put(const fs::path& path, const Bytes& bytes) {
  fs::create_directories(path.parent_path());
  FILE* f = OpenFileW(path, L"wb");
  if (!f) return false;
  size_t n = bytes.empty() ? 0 : std::fwrite(bytes.data(), 1, bytes.size(), f);
  return std::fclose(f) == 0 && n == bytes.size();
}

static bool Is(const fs::path& path, const Bytes& bytes) { return SameBytes(path, bytes); }

static size_t Entries(const fs::path& dir) {
  std::error_code ec;
  size_t n = 0;
  for (fs::directory_iterator it(dir, ec), end; !ec && it != end; it.increment(ec)) ++n;
  return n;
}

// One profile-shaped tree: <root>/00000001/SLOT/SLOT (510 bytes), <root>/Headers/00000001/SLOT.header (328).
struct Slot {
  fs::path root, live, file, header, staging;
  Bytes old_data = Pattern(510, 1), old_header = Pattern(328, 9);
  explicit Slot(const fs::path& base, bool existing = true, bool build = true) : root(base) {
    live = root / L"00000001" / L"SLOT";
    file = live / L"SLOT";
    header = root / L"Headers" / L"00000001" / L"SLOT.header";
    staging = root / kStagingDirName;
    if (!build) return;  // paths only: the tree belongs to another process
    std::error_code ec;
    fs::remove_all(root, ec);
    fs::create_directories(root);
    if (existing) {
      Put(file, old_data);
      Put(header, old_header);
    }
  }
  bool Open(Stage* stage, const Bytes& new_header) const {
    if (!Begin(staging, stage)) return false;
    stage->live = live;
    stage->header = header;
    stage->header_bytes = new_header;
    return true;
  }
  bool Untouched() const { return Is(file, old_data) && Is(header, old_header) && Entries(live) == 1; }
  bool NoStage() const { return !fs::exists(staging); }
};

static DWORD RunChild(const fs::path& dir, const wchar_t* point) {
  wchar_t self[MAX_PATH];
  GetModuleFileNameW(nullptr, self, MAX_PATH);
  std::wstring command = L"\"" + std::wstring(self) + L"\" child \"" + dir.wstring() + L"\" " + point;
  STARTUPINFOW si{};
  si.cb = sizeof(si);
  PROCESS_INFORMATION pi{};
  if (!CreateProcessW(nullptr, command.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &si,
                      &pi)) {
    return DWORD(-1);
  }
  WaitForSingleObject(pi.hProcess, 30000);
  DWORD code = DWORD(-1);
  GetExitCodeProcess(pi.hProcess, &code);
  CloseHandle(pi.hThread);
  CloseHandle(pi.hProcess);
  return code;
}

int wmain(int argc, wchar_t** argv) {
  if (argc == 4 && std::wstring(argv[1]) == L"child") {
    std::wstring point(argv[3]);
    Slot slot(fs::path(argv[2]), true, false);
    Stage stage;
    if (!slot.Open(&stage, Pattern(328, 9))) return 2;
    if (point == L"mid_write") {
      Put(stage.content / L"SLOT", Pattern(200, 77));
      TerminateProcess(GetCurrentProcess(), UINT(kExitCode));
    }
    Put(stage.content / L"SLOT", Pattern(510, 77));
    SetFault(ParseFault(std::string(point.begin(), point.end())));
    Commit(stage);
    return 3;
  }

  const fs::path base = fs::temp_directory_path() / (L"r3hd_m20_test_" + std::to_wstring(GetCurrentProcessId()));
  std::error_code ec;
  fs::remove_all(base, ec);
  const Bytes new_data = Pattern(510, 77), same_header = Pattern(328, 9), new_header = Pattern(328, 33);
  Stage stage;

  {  // 1. The model of the pinned sequence: delete, recreate, die before the write. The old save is gone.
    Slot slot(base / L"legacy_model");
    fs::remove_all(slot.live);
    fs::remove(slot.header);
    fs::create_directories(slot.live);
    Put(slot.header, slot.old_header);
    Check(!fs::exists(slot.file), "legacy model: a stop after the create has already lost the old file");
  }
  {  // 2. The same stop with staging: nothing of the live content has changed.
    Slot slot(base / L"staged_stop");
    Check(slot.Open(&stage, same_header), "staged stop: stage opened");
    Check(slot.Untouched(), "staged stop: old save intact after the create");
    Check(Entries(stage.content) == 0, "staged stop: the guest root is empty after the create");
    Put(stage.content / L"SLOT", Pattern(200, 77));  // a short write, then the process is gone
    Release(stage);                                  // what the death of the process amounts to here
    Check(slot.Untouched(), "staged stop: old save intact with a short staged file");
    Check(Sweep(slot.staging) == 1 && slot.NoStage(), "staged stop: the leftover stage is swept");
    Check(slot.Untouched(), "staged stop: old save intact after the sweep");
  }
  {  // 3. Normal replacement, header unchanged.
    Slot slot(base / L"replace");
    Check(slot.Open(&stage, same_header), "replace: stage opened");
    Put(stage.content / L"SLOT", new_data);
    Check(slot.Untouched(), "replace: old save intact until the commit");
    Check(Commit(stage) == Result::kOk, "replace: commit ok");
    Check(Is(slot.file, new_data) && Is(slot.header, same_header) && Entries(slot.live) == 1, "replace: new content live");
    Check(slot.NoStage(), "replace: no staging directory left");
    Check(!stage.valid(), "replace: stage released");
  }
  {  // 4. Replacement with a different header.
    Slot slot(base / L"replace_header");
    slot.Open(&stage, new_header);
    Put(stage.content / L"SLOT", new_data);
    Check(Commit(stage) == Result::kOk && Is(slot.file, new_data) && Is(slot.header, new_header),
          "replace with new header: both live");
    Check(Entries(slot.header.parent_path()) == 1, "replace with new header: no temporary beside the header");
  }
  {  // 5. First save: nothing existed.
    Slot slot(base / L"fresh", false);
    slot.Open(&stage, new_header);
    Check(!fs::exists(slot.live), "fresh: the content does not exist before the commit");
    Put(stage.content / L"SLOT", new_data);
    Check(Commit(stage) == Result::kOk && Is(slot.file, new_data) && Is(slot.header, new_header) && slot.NoStage(),
          "fresh: content and header created by the commit");
  }
  {  // 6. Every injected failure before the rename leaves the old save byte-identical.
    struct Case { Fault fault; Result expect; const char* name; };
    const Case cases[] = {{Fault::kFlush, Result::kFlushFailed, "flush"},
                          {Fault::kBeforeReplace, Result::kAbandoned, "before_replace"},
                          {Fault::kReplace, Result::kReplaceFailed, "replace"}};
    for (const auto& c : cases) {
      Slot slot(base / (std::wstring(L"fault_") + std::wstring(c.name, c.name + std::strlen(c.name))));
      slot.Open(&stage, new_header);
      Put(stage.content / L"SLOT", new_data);
      SetFault(c.fault);
      Result r = Commit(stage);
      Check(r == c.expect, std::string(c.name) + ": result " + Name(r));
      // The header follows the data, so a failure of the data leaves the old header as well.
      Check(slot.Untouched(), std::string(c.name) + ": old save file and header byte-identical");
      Check(slot.NoStage(), std::string(c.name) + ": no staging directory left");
      SetFault(Fault::kNone);
      // The same failure on a first save leaves no slot behind: no directory, no header.
      Slot fresh(base / (std::wstring(L"fresh_fault_") + std::wstring(c.name, c.name + std::strlen(c.name))), false);
      fresh.Open(&stage, new_header);
      Put(stage.content / L"SLOT", new_data);
      SetFault(c.fault);
      Check(Commit(stage) == c.expect, std::string(c.name) + " on a first save: result");
      Check(!fs::exists(fresh.live) && !fs::exists(fresh.header) && fresh.NoStage(),
            std::string(c.name) + " on a first save: no slot directory, no header, no stage");
      SetFault(Fault::kNone);
    }
    {  // The header rename fails after the data is committed: the save stands, the old header stays.
      Slot slot(base / L"fault_header_replace");
      slot.Open(&stage, new_header);
      Put(stage.content / L"SLOT", new_data);
      SetFault(Fault::kHeaderReplace);
      Check(Commit(stage) == Result::kOk && Is(slot.file, new_data) && Is(slot.header, slot.old_header) && slot.NoStage(),
            "header_replace: data committed, previous header kept, no stage");
      SetFault(Fault::kNone);
    }
    {  // Two staged files, the second rename fails: not atomic across files, and reported as a failure.
      Slot slot(base / L"fault_second_file");
      Put(slot.live / L"ZZZ", Pattern(30, 2));
      slot.Open(&stage, same_header);
      Put(stage.content / L"SLOT", new_data);
      Put(stage.content / L"ZZZ", Pattern(30, 8));
      SetFault(Fault::kReplace, 2);
      Check(Commit(stage) == Result::kReplaceFailed, "second file: commit reports the failure");
      Check(Is(slot.file, new_data) && Is(slot.live / L"ZZZ", Pattern(30, 2)) && slot.NoStage(),
            "second file: first file new, second old (documented limit), no stage");
      SetFault(Fault::kNone);
    }
    Slot slot(base / L"fault_stage_create");
    SetFault(Fault::kStageCreate);
    Check(!slot.Open(&stage, new_header) && !stage.valid(), "stage_create: no stage");
    Check(slot.Untouched() && slot.NoStage(), "stage_create: old save intact, nothing left");
    Check(Commit(stage) == Result::kStageFailed && slot.Untouched(), "stage_create: a commit without a stage does nothing");
    SetFault(Fault::kNone);
  }
  {  // 7. A failed host write into the stage blocks the commit.
    Slot slot(base / L"write_failed");
    slot.Open(&stage, new_header);
    Put(stage.content / L"SLOT", Pattern(255, 77));
    Check(InActiveStage(stage.content / L"SLOT") && !InActiveStage(slot.file), "write failure: stage membership");
    NoteWriteFailure(slot.file);  // a failure outside any stage marks nothing
    NoteWriteFailure(stage.content / L"SLOT");
    Check(Commit(stage) == Result::kWriteFailed, "write failure: commit refused");
    Check(slot.Untouched() && slot.NoStage(), "write failure: old save intact, stage removed");
    slot.Open(&stage, same_header);
    Put(stage.content / L"SLOT", new_data);
    Check(Commit(stage) == Result::kOk && Is(slot.file, new_data), "write failure: the next save goes through");
  }
  {  // 8. A real sharing conflict: another handle holds the live file without delete sharing.
    Slot slot(base / L"sharing");
    HANDLE reader = CreateFileW(slot.file.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
    Check(reader != INVALID_HANDLE_VALUE, "sharing: reader opened");
    slot.Open(&stage, same_header);
    Put(stage.content / L"SLOT", new_data);
    Check(Commit(stage) == Result::kReplaceFailed, "sharing: commit fails while the file is held");
    Check(slot.Untouched() && slot.NoStage(), "sharing: old save intact, stage removed");
    // A reader that lets go within the retry window does not fail the save.
    slot.Open(&stage, same_header);
    Put(stage.content / L"SLOT", new_data);
    std::thread release([reader] {
      std::this_thread::sleep_for(std::chrono::milliseconds(60));
      CloseHandle(reader);
    });
    Result r = Commit(stage);
    release.join();
    Check(r == Result::kOk && Is(slot.file, new_data), "sharing: commit succeeds once the reader lets go");
  }
  {  // 9. Failed cleanup: the save is committed, the leftover is swept later.
    Slot slot(base / L"cleanup");
    slot.Open(&stage, same_header);
    Put(stage.content / L"SLOT", new_data);
    SetFault(Fault::kCleanup);
    Check(Commit(stage) == Result::kOk && Is(slot.file, new_data), "cleanup: commit ok");
    Check(fs::exists(slot.staging) && Entries(slot.staging) == 1, "cleanup: stage directory left behind");
    Check(Entries(slot.live) == 1 && Entries(slot.live.parent_path()) == 1, "cleanup: nothing extra among the slots");
    Check(Sweep(slot.staging) == 1 && slot.NoStage(), "cleanup: swept at the next opportunity");
    Check(Is(slot.file, new_data), "cleanup: the committed save is untouched by the sweep");
    SetFault(Fault::kNone);
  }
  {  // 10. Sweep: only stages of dead processes go; everything else stays.
    Slot slot(base / L"sweep");
    const fs::path dead = slot.staging / L"4294967292.1", system_pid = slot.staging / L"4.7";
    const fs::path foreign = slot.staging / L"notes", stray = slot.staging / L"12.x";
    Put(dead / L"content" / L"SLOT", Pattern(100, 5));
    Put(system_pid / L"content" / L"SLOT", Pattern(100, 5));
    Put(foreign / L"readme", Pattern(10, 5));
    Put(stray / L"content" / L"SLOT", Pattern(10, 5));
    slot.Open(&stage, same_header);  // an active stage of this process
    const fs::path mine = stage.base;
    Check(Sweep(slot.staging) == 1, "sweep: exactly the dead process's stage is removed");
    Check(!fs::exists(dead), "sweep: dead stage gone");
    Check(fs::exists(system_pid), "sweep: a stage of a process that cannot be examined is kept");
    Check(fs::exists(foreign / L"readme") && fs::exists(stray), "sweep: entries that are not stages are kept");
    Check(fs::exists(mine / L"content"), "sweep: this process's active stage is kept");
    Check(slot.Untouched(), "sweep: live content untouched");
    Abort(stage);
    Check(!fs::exists(mine) && fs::exists(slot.staging), "abort: own stage removed, the non-empty root stays");
  }
  {  // 11. A leftover with this process's own id and an upcoming sequence number is never reused.
    Slot slot(base / L"collision");
    for (int i = 1; i <= 40; ++i) {
      Put(slot.staging / (std::to_wstring(GetCurrentProcessId()) + L"." + std::to_wstring(i)) / L"content" / L"junk",
          Pattern(4, 1));
    }
    Check(Begin(slot.staging, &stage) && Entries(stage.content) == 0, "collision: a fresh, empty stage");
    Abort(stage);
  }
  {  // 12. Repeated replacement.
    Slot slot(base / L"repeat");
    bool all = true;
    for (int i = 0; i < 100; ++i) {
      Bytes data = Pattern(510, uint8_t(i));
      all = all && slot.Open(&stage, same_header) && Put(stage.content / L"SLOT", data) &&
            Commit(stage) == Result::kOk && Is(slot.file, data) && slot.NoStage();
    }
    Check(all, "repeat: 100 replacements, each one live and clean");
  }
  {  // 13. CREATE_ALWAYS semantics: files the new content lacks are removed, after the renames.
    Slot slot(base / L"superset");
    Put(slot.live / L"OTHER", Pattern(10, 3));
    Put(slot.live / L"sub" / L"deep", Pattern(10, 3));
    slot.Open(&stage, same_header);
    Put(stage.content / L"SLOT", new_data);
    Put(stage.content / L"dir" / L"inner", Pattern(20, 4));
    Check(Commit(stage) == Result::kOk, "superset: commit ok");
    Check(Is(slot.file, new_data) && Is(slot.live / L"dir" / L"inner", Pattern(20, 4)), "superset: new files live");
    Check(!fs::exists(slot.live / L"OTHER") && !fs::exists(slot.live / L"sub"), "superset: old extras removed");
    // Names are matched the way the file system matches them: "Dir" on disk is the staged "dir".
    Put(slot.live / L"Keep" / L"old", Pattern(5, 1));
    slot.Open(&stage, same_header);
    Put(stage.content / L"SLOT", new_data);
    Put(stage.content / L"keep" / L"new", Pattern(6, 2));
    Check(Commit(stage) == Result::kOk && Is(slot.live / L"keep" / L"new", Pattern(6, 2)) &&
              !fs::exists(slot.live / L"Keep" / L"old") && !fs::exists(slot.live / L"dir"),
          "case: a directory spelled differently is kept, its old file removed");
  }
  {  // 13b. A close with nothing written never wipes content that has files.
    Slot slot(base / L"empty_close");
    slot.Open(&stage, new_header);
    Check(Commit(stage) == Result::kEmptyRefused, "empty close over a save: refused");
    Check(slot.Untouched() && slot.NoStage(), "empty close over a save: old save and header intact, no stage");
    slot.Open(&stage, new_header);
    fs::create_directories(stage.content / L"only_a_directory");
    Check(Commit(stage) == Result::kEmptyRefused && slot.Untouched(), "a close with only an empty directory: refused");
    Slot fresh(base / L"empty_close_fresh", false);
    fresh.Open(&stage, new_header);
    Check(Commit(stage) == Result::kOk && fs::is_directory(fresh.live) && Entries(fresh.live) == 0 &&
              Is(fresh.header, new_header),
          "empty close with no previous content: empty content created, as with the pinned sequence");
  }
  {  // 14. A process that really ends at the commit point, and one that ends in the middle of the write.
    for (const wchar_t* point : {L"exit_before_commit", L"mid_write"}) {
      Slot slot(base / (std::wstring(L"kill_") + point));
      DWORD code = RunChild(slot.root, point);
      std::string name(point, point + std::wcslen(point));
      Check(code == DWORD(kExitCode), name + ": the child ended at the fault point (code " + std::to_string(code) + ")");
      Check(slot.Untouched(), name + ": old save byte-identical after the child's death");
      Check(fs::exists(slot.staging) && Entries(slot.staging) == 1, name + ": the dead child's stage is on disk");
      Check(Entries(slot.live.parent_path()) == 1, name + ": no extra slot directory");
      Check(Sweep(slot.staging) == 1 && slot.NoStage() && slot.Untouched(), name + ": swept by the next process, save intact");
    }
  }
  {  // 15. Names.
    uint32_t pid = 0;
    Check(IsStageName(L"1234.5", &pid) && pid == 1234, "stage name parsed");
    Check(!IsStageName(L"1234", &pid) && !IsStageName(L".5", &pid) && !IsStageName(L"12.", &pid) &&
              !IsStageName(L"a.1", &pid) && !IsStageName(L"1.2.3", &pid) && !IsStageName(L"00000001", &pid),
          "other names are not stages");
    Check(ParseFault("replace") == Fault::kReplace && ParseFault("nonsense") == Fault::kNone, "fault names");
  }

  fs::remove_all(base, ec);
  std::printf("m20_save_commit_test checks=%d failures=%d\n", checks, failures);
  return failures ? 1 : 0;
}
#else  // POSIX (Linux, glibc): the same scenarios with narrow paths, fork-free posix_spawn of this binary and
       // rename(2)/fsync semantics. Differences from the Windows cases are marked "POSIX:".
//
//   m20_save_commit_test                     -> "m20_save_commit_test checks=N failures=0"
//   m20_save_commit_test child DIR POINT        (internal: a process that ends itself at a fault point)
#include "m20_save_commit.h"

#include <spawn.h>
#include <sys/wait.h>

#include <cstdio>
#include <string>

extern char** environ;

namespace fs = std::filesystem;
using Bytes = std::vector<uint8_t>;
using namespace m20save;

static int checks = 0, failures = 0;
static void Check(bool ok, const std::string& what) {
  ++checks;
  if (!ok) {
    ++failures;
    std::printf("FAIL %s\n", what.c_str());
  }
}

static Bytes Pattern(size_t size, uint8_t seed) {
  Bytes b(size);
  for (size_t i = 0; i < size; ++i) b[i] = uint8_t(seed + i * 7);
  return b;
}

static bool Put(const fs::path& path, const Bytes& bytes) {
  fs::create_directories(path.parent_path());
  FILE* f = OpenFileW(path, "wb");
  if (!f) return false;
  size_t n = bytes.empty() ? 0 : std::fwrite(bytes.data(), 1, bytes.size(), f);
  return std::fclose(f) == 0 && n == bytes.size();
}

static bool Is(const fs::path& path, const Bytes& bytes) { return SameBytes(path, bytes); }

static size_t Entries(const fs::path& dir) {
  std::error_code ec;
  size_t n = 0;
  for (fs::directory_iterator it(dir, ec), end; !ec && it != end; it.increment(ec)) ++n;
  return n;
}

// One profile-shaped tree: <root>/00000001/SLOT/SLOT (510 bytes), <root>/Headers/00000001/SLOT.header (328).
struct Slot {
  fs::path root, live, file, header, staging;
  Bytes old_data = Pattern(510, 1), old_header = Pattern(328, 9);
  explicit Slot(const fs::path& base, bool existing = true, bool build = true) : root(base) {
    live = root / "00000001" / "SLOT";
    file = live / "SLOT";
    header = root / "Headers" / "00000001" / "SLOT.header";
    staging = root / kStagingDirName;
    if (!build) return;  // paths only: the tree belongs to another process
    std::error_code ec;
    fs::remove_all(root, ec);
    fs::create_directories(root);
    if (existing) {
      Put(file, old_data);
      Put(header, old_header);
    }
  }
  bool Open(Stage* stage, const Bytes& new_header) const {
    if (!Begin(staging, stage)) return false;
    stage->live = live;
    stage->header = header;
    stage->header_bytes = new_header;
    return true;
  }
  bool Untouched() const { return Is(file, old_data) && Is(header, old_header) && Entries(live) == 1; }
  bool NoStage() const { return !fs::exists(staging); }
};

// Runs this binary as "child DIR POINT"; returns its exit status, or -1 (not started, or ended by a signal).
static int RunChild(const fs::path& dir, const char* point) {
  std::error_code ec;
  const std::string self = fs::read_symlink("/proc/self/exe", ec).string();
  if (ec) return -1;
  const std::string dir_text = dir.string();
  char* args[] = {const_cast<char*>(self.c_str()), const_cast<char*>("child"), const_cast<char*>(dir_text.c_str()),
                  const_cast<char*>(point), nullptr};
  pid_t pid = 0;
  if (posix_spawn(&pid, self.c_str(), nullptr, nullptr, args, environ) != 0) return -1;
  int status = 0;
  if (waitpid(pid, &status, 0) != pid || !WIFEXITED(status)) return -1;
  return WEXITSTATUS(status);
}

int main(int argc, char** argv) {
  if (argc == 4 && std::string(argv[1]) == "child") {
    std::string point(argv[3]);
    Slot slot(fs::path(argv[2]), true, false);
    Stage stage;
    if (!slot.Open(&stage, Pattern(328, 9))) return 2;
    if (point == "mid_write") {
      Put(stage.content / "SLOT", Pattern(200, 77));
      _exit(kExitCode & 0xFF);
    }
    Put(stage.content / "SLOT", Pattern(510, 77));
    SetFault(ParseFault(point));
    Commit(stage);
    return 3;
  }

  const fs::path base = fs::temp_directory_path() / ("r3hd_m20_test_" + std::to_string(unsigned(getpid())));
  std::error_code ec;
  fs::remove_all(base, ec);
  const Bytes new_data = Pattern(510, 77), same_header = Pattern(328, 9), new_header = Pattern(328, 33);
  Stage stage;

  {  // 1. The model of the pinned sequence: delete, recreate, die before the write. The old save is gone.
    Slot slot(base / "legacy_model");
    fs::remove_all(slot.live);
    fs::remove(slot.header);
    fs::create_directories(slot.live);
    Put(slot.header, slot.old_header);
    Check(!fs::exists(slot.file), "legacy model: a stop after the create has already lost the old file");
  }
  {  // 2. The same stop with staging: nothing of the live content has changed.
    Slot slot(base / "staged_stop");
    Check(slot.Open(&stage, same_header), "staged stop: stage opened");
    Check(slot.Untouched(), "staged stop: old save intact after the create");
    Check(Entries(stage.content) == 0, "staged stop: the guest root is empty after the create");
    Put(stage.content / "SLOT", Pattern(200, 77));  // a short write, then the process is gone
    Release(stage);                                 // what the death of the process amounts to here
    Check(slot.Untouched(), "staged stop: old save intact with a short staged file");
    Check(Sweep(slot.staging) == 1 && slot.NoStage(), "staged stop: the leftover stage is swept");
    Check(slot.Untouched(), "staged stop: old save intact after the sweep");
  }
  {  // 3. Normal replacement, header unchanged.
    Slot slot(base / "replace");
    Check(slot.Open(&stage, same_header), "replace: stage opened");
    Put(stage.content / "SLOT", new_data);
    Check(slot.Untouched(), "replace: old save intact until the commit");
    Check(Commit(stage) == Result::kOk, "replace: commit ok");
    Check(Is(slot.file, new_data) && Is(slot.header, same_header) && Entries(slot.live) == 1, "replace: new content live");
    Check(slot.NoStage(), "replace: no staging directory left");
    Check(!stage.valid(), "replace: stage released");
  }
  {  // 4. Replacement with a different header.
    Slot slot(base / "replace_header");
    slot.Open(&stage, new_header);
    Put(stage.content / "SLOT", new_data);
    Check(Commit(stage) == Result::kOk && Is(slot.file, new_data) && Is(slot.header, new_header),
          "replace with new header: both live");
    Check(Entries(slot.header.parent_path()) == 1, "replace with new header: no temporary beside the header");
  }
  {  // 5. First save: nothing existed.
    Slot slot(base / "fresh", false);
    slot.Open(&stage, new_header);
    Check(!fs::exists(slot.live), "fresh: the content does not exist before the commit");
    Put(stage.content / "SLOT", new_data);
    Check(Commit(stage) == Result::kOk && Is(slot.file, new_data) && Is(slot.header, new_header) && slot.NoStage(),
          "fresh: content and header created by the commit");
  }
  {  // 6. Every injected failure before the rename leaves the old save byte-identical.
    struct Case { Fault fault; Result expect; const char* name; };
    const Case cases[] = {{Fault::kFlush, Result::kFlushFailed, "flush"},
                          {Fault::kBeforeReplace, Result::kAbandoned, "before_replace"},
                          {Fault::kReplace, Result::kReplaceFailed, "replace"}};
    for (const auto& c : cases) {
      Slot slot(base / (std::string("fault_") + c.name));
      slot.Open(&stage, new_header);
      Put(stage.content / "SLOT", new_data);
      SetFault(c.fault);
      Result r = Commit(stage);
      Check(r == c.expect, std::string(c.name) + ": result " + Name(r));
      // The header follows the data, so a failure of the data leaves the old header as well.
      Check(slot.Untouched(), std::string(c.name) + ": old save file and header byte-identical");
      Check(slot.NoStage(), std::string(c.name) + ": no staging directory left");
      SetFault(Fault::kNone);
      // The same failure on a first save leaves no slot behind: no directory, no header.
      Slot fresh(base / (std::string("fresh_fault_") + c.name), false);
      fresh.Open(&stage, new_header);
      Put(stage.content / "SLOT", new_data);
      SetFault(c.fault);
      Check(Commit(stage) == c.expect, std::string(c.name) + " on a first save: result");
      Check(!fs::exists(fresh.live) && !fs::exists(fresh.header) && fresh.NoStage(),
            std::string(c.name) + " on a first save: no slot directory, no header, no stage");
      SetFault(Fault::kNone);
    }
    {  // The header rename fails after the data is committed: the save stands, the old header stays.
      Slot slot(base / "fault_header_replace");
      slot.Open(&stage, new_header);
      Put(stage.content / "SLOT", new_data);
      SetFault(Fault::kHeaderReplace);
      Check(Commit(stage) == Result::kOk && Is(slot.file, new_data) && Is(slot.header, slot.old_header) && slot.NoStage(),
            "header_replace: data committed, previous header kept, no stage");
      SetFault(Fault::kNone);
    }
    {  // Two staged files, the second rename fails: not atomic across files, and reported as a failure.
      Slot slot(base / "fault_second_file");
      Put(slot.live / "ZZZ", Pattern(30, 2));
      slot.Open(&stage, same_header);
      Put(stage.content / "SLOT", new_data);
      Put(stage.content / "ZZZ", Pattern(30, 8));
      SetFault(Fault::kReplace, 2);
      Check(Commit(stage) == Result::kReplaceFailed, "second file: commit reports the failure");
      Check(Is(slot.file, new_data) && Is(slot.live / "ZZZ", Pattern(30, 2)) && slot.NoStage(),
            "second file: first file new, second old (documented limit), no stage");
      SetFault(Fault::kNone);
    }
    Slot slot(base / "fault_stage_create");
    SetFault(Fault::kStageCreate);
    Check(!slot.Open(&stage, new_header) && !stage.valid(), "stage_create: no stage");
    Check(slot.Untouched() && slot.NoStage(), "stage_create: old save intact, nothing left");
    Check(Commit(stage) == Result::kStageFailed && slot.Untouched(), "stage_create: a commit without a stage does nothing");
    SetFault(Fault::kNone);
  }
  {  // 7. A failed host write into the stage blocks the commit.
    Slot slot(base / "write_failed");
    slot.Open(&stage, new_header);
    Put(stage.content / "SLOT", Pattern(255, 77));
    Check(InActiveStage(stage.content / "SLOT") && !InActiveStage(slot.file), "write failure: stage membership");
    NoteWriteFailure(slot.file);  // a failure outside any stage marks nothing
    NoteWriteFailure(stage.content / "SLOT");
    Check(Commit(stage) == Result::kWriteFailed, "write failure: commit refused");
    Check(slot.Untouched() && slot.NoStage(), "write failure: old save intact, stage removed");
    slot.Open(&stage, same_header);
    Put(stage.content / "SLOT", new_data);
    Check(Commit(stage) == Result::kOk && Is(slot.file, new_data), "write failure: the next save goes through");
  }
  {  // 8. POSIX: no sharing conflicts exist; a real rename(2) failure stands in for the held file. The live
     // "SLOT" is a non-empty directory, so rename(file, directory) fails with EISDIR and nothing is replaced.
    Slot slot(base / "rename_conflict", false);
    Put(slot.live / "SLOT" / "inner", Pattern(7, 1));
    slot.Open(&stage, same_header);
    Put(stage.content / "SLOT", new_data);
    Check(Commit(stage) == Result::kReplaceFailed, "rename conflict: commit fails");
    Check(Is(slot.live / "SLOT" / "inner", Pattern(7, 1)) && slot.NoStage(), "rename conflict: live tree intact, stage removed");
    // A directory fsync/rename path that works on a plain file still succeeds afterwards.
    Slot again(base / "rename_conflict_ok");
    again.Open(&stage, same_header);
    Put(stage.content / "SLOT", new_data);
    Check(Commit(stage) == Result::kOk && Is(again.file, new_data), "rename conflict: a normal commit still succeeds");
  }
  {  // 9. Failed cleanup: the save is committed, the leftover is swept later.
    Slot slot(base / "cleanup");
    slot.Open(&stage, same_header);
    Put(stage.content / "SLOT", new_data);
    SetFault(Fault::kCleanup);
    Check(Commit(stage) == Result::kOk && Is(slot.file, new_data), "cleanup: commit ok");
    Check(fs::exists(slot.staging) && Entries(slot.staging) == 1, "cleanup: stage directory left behind");
    Check(Entries(slot.live) == 1 && Entries(slot.live.parent_path()) == 1, "cleanup: nothing extra among the slots");
    Check(Sweep(slot.staging) == 1 && slot.NoStage(), "cleanup: swept at the next opportunity");
    Check(Is(slot.file, new_data), "cleanup: the committed save is untouched by the sweep");
    SetFault(Fault::kNone);
  }
  {  // 10. Sweep: only stages of dead processes go; everything else stays.
    Slot slot(base / "sweep");
    // POSIX: pid 1 always exists (kill() answers 0 or EPERM) and stands for a process that cannot be examined;
    // a pid above INT_MAX is never real and must not reach kill().
    const fs::path dead = slot.staging / "4294967292.1", system_pid = slot.staging / "1.7";
    const fs::path foreign = slot.staging / "notes", stray = slot.staging / "12.x";
    Put(dead / "content" / "SLOT", Pattern(100, 5));
    Put(system_pid / "content" / "SLOT", Pattern(100, 5));
    Put(foreign / "readme", Pattern(10, 5));
    Put(stray / "content" / "SLOT", Pattern(10, 5));
    slot.Open(&stage, same_header);  // an active stage of this process
    const fs::path mine = stage.base;
    Check(Sweep(slot.staging) == 1, "sweep: exactly the dead process's stage is removed");
    Check(!fs::exists(dead), "sweep: dead stage gone");
    Check(fs::exists(system_pid), "sweep: a stage of a process that cannot be examined is kept");
    Check(fs::exists(foreign / "readme") && fs::exists(stray), "sweep: entries that are not stages are kept");
    Check(fs::exists(mine / "content"), "sweep: this process's active stage is kept");
    Check(slot.Untouched(), "sweep: live content untouched");
    Abort(stage);
    Check(!fs::exists(mine) && fs::exists(slot.staging), "abort: own stage removed, the non-empty root stays");
  }
  {  // 11. A leftover with this process's own id and an upcoming sequence number is never reused.
    Slot slot(base / "collision");
    for (int i = 1; i <= 40; ++i) {
      Put(slot.staging / (std::to_string(unsigned(getpid())) + "." + std::to_string(i)) / "content" / "junk",
          Pattern(4, 1));
    }
    Check(Begin(slot.staging, &stage) && Entries(stage.content) == 0, "collision: a fresh, empty stage");
    Abort(stage);
  }
  {  // 12. Repeated replacement.
    Slot slot(base / "repeat");
    bool all = true;
    for (int i = 0; i < 100; ++i) {
      Bytes data = Pattern(510, uint8_t(i));
      all = all && slot.Open(&stage, same_header) && Put(stage.content / "SLOT", data) &&
            Commit(stage) == Result::kOk && Is(slot.file, data) && slot.NoStage();
    }
    Check(all, "repeat: 100 replacements, each one live and clean");
  }
  {  // 13. CREATE_ALWAYS semantics: files the new content lacks are removed, after the renames.
    Slot slot(base / "superset");
    Put(slot.live / "OTHER", Pattern(10, 3));
    Put(slot.live / "sub" / "deep", Pattern(10, 3));
    slot.Open(&stage, same_header);
    Put(stage.content / "SLOT", new_data);
    Put(stage.content / "dir" / "inner", Pattern(20, 4));
    Check(Commit(stage) == Result::kOk, "superset: commit ok");
    Check(Is(slot.file, new_data) && Is(slot.live / "dir" / "inner", Pattern(20, 4)), "superset: new files live");
    Check(!fs::exists(slot.live / "OTHER") && !fs::exists(slot.live / "sub"), "superset: old extras removed");
    // Names are matched the way the guest sees them (ASCII case-insensitively, as the SDK host path device does):
    // POSIX: the staged "keep/new" lands below the existing spelling "Keep", and no second "keep" appears (checked by entry count, so the check also holds on a
    // case-insensitive mount such as /mnt/c).
    Put(slot.live / "Keep" / "old", Pattern(5, 1));
    slot.Open(&stage, same_header);
    Put(stage.content / "SLOT", new_data);
    Put(stage.content / "keep" / "new", Pattern(6, 2));
    Check(Commit(stage) == Result::kOk && Is(slot.live / "Keep" / "new", Pattern(6, 2)) &&
              !fs::exists(slot.live / "Keep" / "old") && Entries(slot.live) == 2 && !fs::exists(slot.live / "dir"),
          "case: a directory spelled differently is kept under its old spelling, its old file removed");
    // The same for a file: the staged "slot" replaces the live "SLOT" and leaves no second spelling.
    slot.Open(&stage, same_header);
    Put(stage.content / "slot", Pattern(9, 6));
    Check(Commit(stage) == Result::kOk && Is(slot.live / "SLOT", Pattern(9, 6)) && Entries(slot.live) == 1,
          "case: a file spelled differently replaces the existing one");
  }
  {  // 13b. A close with nothing written never wipes content that has files.
    Slot slot(base / "empty_close");
    slot.Open(&stage, new_header);
    Check(Commit(stage) == Result::kEmptyRefused, "empty close over a save: refused");
    Check(slot.Untouched() && slot.NoStage(), "empty close over a save: old save and header intact, no stage");
    slot.Open(&stage, new_header);
    fs::create_directories(stage.content / "only_a_directory");
    Check(Commit(stage) == Result::kEmptyRefused && slot.Untouched(), "a close with only an empty directory: refused");
    Slot fresh(base / "empty_close_fresh", false);
    fresh.Open(&stage, new_header);
    Check(Commit(stage) == Result::kOk && fs::is_directory(fresh.live) && Entries(fresh.live) == 0 &&
              Is(fresh.header, new_header),
          "empty close with no previous content: empty content created, as with the pinned sequence");
  }
  {  // 14. A process that really ends at the commit point, and one that ends in the middle of the write.
    for (const char* point : {"exit_before_commit", "mid_write"}) {
      Slot slot(base / (std::string("kill_") + point));
      int code = RunChild(slot.root, point);
      std::string name(point);
      Check(code == (kExitCode & 0xFF), name + ": the child ended at the fault point (code " + std::to_string(code) + ")");
      Check(slot.Untouched(), name + ": old save byte-identical after the child's death");
      Check(fs::exists(slot.staging) && Entries(slot.staging) == 1, name + ": the dead child's stage is on disk");
      Check(Entries(slot.live.parent_path()) == 1, name + ": no extra slot directory");
      Check(Sweep(slot.staging) == 1 && slot.NoStage() && slot.Untouched(), name + ": swept by the next process, save intact");
    }
  }
  {  // 15. Names.
    uint32_t pid = 0;
    Check(IsStageName("1234.5", &pid) && pid == 1234, "stage name parsed");
    Check(!IsStageName("1234", &pid) && !IsStageName(".5", &pid) && !IsStageName("12.", &pid) &&
              !IsStageName("a.1", &pid) && !IsStageName("1.2.3", &pid) && !IsStageName("00000001", &pid),
          "other names are not stages");
    Check(ParseFault("replace") == Fault::kReplace && ParseFault("nonsense") == Fault::kNone, "fault names");
  }

  fs::remove_all(base, ec);
  std::printf("m20_save_commit_test checks=%d failures=%d\n", checks, failures);
  return failures ? 1 : 0;
}
#endif  // _WIN32

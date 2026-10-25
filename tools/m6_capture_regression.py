"""Small standalone regression for the M6 request-driven capture policy."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile


FIXTURE = r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <rex/m6_frame_capture.h>
#ifdef NDEBUG
#error "M6 capture regression requires active assertions"
#endif

static void WriteId(const char* path, unsigned id) {
  std::ofstream out(path, std::ios::trunc);
  out << id << "\n";
}
static void MakePollDue() {
  auto& state = m6frame::State();
  state.last_poll = std::chrono::steady_clock::now() - m6frame::kPollInterval - std::chrono::milliseconds(1);
}

int main(int argc, char** argv) {
  assert(argc == 2);
  const char* request_path = argv[1];
  _putenv_s("R3HD_FRAME_REQUEST", request_path);
  WriteId(request_path, 0);

  assert(!m6frame::CaptureAt(10)); // no request means no readback
  assert(!m6frame::CaptureAt(10)); // same-swap decision is cached
  assert(m6frame::ReadbackAttempts() == 0);

  WriteId(request_path, 1);
  auto& state = m6frame::State();
  state.last_poll = std::chrono::steady_clock::now() - (m6frame::kPollInterval - std::chrono::milliseconds(100));
  assert(!m6frame::CaptureAt(11)); // poll interval has not elapsed
  MakePollDue();
  assert(!m6frame::CaptureAt(11)); // even when due, same-swap result remains cached
  MakePollDue();
  assert(m6frame::CaptureAt(12));
  assert(m6frame::CaptureAt(12));
  assert(m6frame::RequestIdForSwap(12) == 1);

  rex::ui::RawImage first{2, 1, 12, {1, 2, 3, 4, 5, 6, 7, 8, 90, 91, 92, 93}};
  rex::ui::RawImage same_rgb{2, 1, 12, {1, 2, 3, 44, 5, 6, 7, 55, 10, 20, 30, 40}};
  rex::ui::RawImage changed_rgb{2, 1, 12, {9, 2, 3, 4, 5, 6, 7, 8, 90, 91, 92, 93}};
  rex::ui::RawImage different_dimensions{1, 2, 4, {1, 2, 3, 0, 5, 6, 7, 0}};
  rex::ui::RawImage invalid{1, 1, 4, {1, 2, 3}};
  int writes = 0;
  auto writer = [&writes](const char*, const rex::ui::RawImage&) { ++writes; return true; };
  assert(m6frame::SaveIfNew(first, "first.bmp", 12, writer));
  assert(!m6frame::SaveIfNew(same_rgb, "duplicate.bmp", 12, writer)); // X8 and row padding are ignored
  assert(writes == 1);

  WriteId(request_path, 1); // repeated IDs cannot be consumed twice
  MakePollDue();
  assert(!m6frame::CaptureAt(13));
  assert(m6frame::ReadbackAttempts() == 1);
  WriteId(request_path, 2);
  MakePollDue();
  assert(m6frame::CaptureAt(14));
  assert(m6frame::SaveIfNew(changed_rgb, "changed.bmp", 14, writer));
  WriteId(request_path, 3);
  MakePollDue();
  assert(m6frame::CaptureAt(15));
  assert(m6frame::SaveIfNew(different_dimensions, "different_dimensions.bmp", 15, writer));
  assert(writes == 3); // changed pixels and dimensions each produce a capture

  WriteId(request_path, 4);
  MakePollDue();
  assert(m6frame::CaptureAt(16));
  m6frame::ReadbackUnavailable(16); // selected requests count even if readback fails
  assert(m6frame::ReadbackAttempts() == 4);
  WriteId(request_path, 5);
  MakePollDue();
  assert(m6frame::CaptureAt(17));
  assert(!m6frame::SaveIfNew(invalid, "invalid.bmp", 17, writer));
  assert(writes == 3);
  assert(m6frame::ReadbackAttempts() == 5);

  for (unsigned id = 6; id <= 8; ++id) {
    WriteId(request_path, id);
    MakePollDue();
    assert(m6frame::CaptureAt(20 + id));
  }
  assert(m6frame::ReadbackAttempts() == 8);
  WriteId(request_path, 9);
  MakePollDue();
  assert(!m6frame::CaptureAt(99));
  assert(m6frame::ReadbackAttempts() == 8);
  return 0;
}
'''


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    private_work = (repo / "private" / "work").resolve()
    private_work.mkdir(parents=True, exist_ok=True)
    test_dir = Path(tempfile.mkdtemp(prefix="m6_capture_regression_", dir=private_work))
    try:
        include_root = test_dir / "include"
        rex_root = include_root / "rex"
        ui_root = rex_root / "ui"
        ui_root.mkdir(parents=True)
        (rex_root / "logging.h").write_text("#pragma once\n#define REXGPU_INFO(...) ((void)0)\n", encoding="ascii")
        (ui_root / "presenter.h").write_text(
            "#pragma once\n#include <cstddef>\n#include <cstdint>\n#include <vector>\n"
            "namespace rex::ui { struct RawImage { uint32_t width=0, height=0; "
            "size_t stride=0; std::vector<uint8_t> data; }; }\n",
            encoding="ascii",
        )
        (rex_root / "m6_frame_capture.h").write_bytes((repo / "tools" / "m6_frame_capture.h").read_bytes())
        source = test_dir / "fixture.cpp"
        source.write_text(FIXTURE, encoding="ascii")
        exe = test_dir / "fixture.exe"
        request_file = test_dir / "request.txt"
        request_file.write_text("0\n", encoding="ascii")

        build_cmd = test_dir / "compile.cmd"
        build_cmd.write_text(
            "@echo off\r\n"
            f'call "{repo / "tools" / "devenv.bat"}" clang++ -std=c++20 -I"{include_root}" "{source}" -o "{exe}"\r\n'
            "exit /b %ERRORLEVEL%\r\n",
            encoding="ascii",
        )
        subprocess.run(["cmd.exe", "/d", "/c", str(build_cmd)], cwd=repo, check=True)
        subprocess.run([str(exe), str(request_file)], cwd=repo, check=True)
        print("M6 capture policy regression: PASS")
    finally:
        resolved = test_dir.resolve(strict=True)
        try:
            resolved.relative_to(private_work)
        except ValueError as exc:
            raise RuntimeError(f"Refusing cleanup outside private/work: {resolved}") from exc
        shutil.rmtree(resolved)


if __name__ == "__main__":
    main()

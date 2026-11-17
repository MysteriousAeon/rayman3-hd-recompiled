#!/usr/bin/env python3
"""E-378 regression: a stale r3hd must never be packaged, and gamesync must rebuild it (runs anywhere).

LX2C (native): sdkupdate replaced the SDK's src/ui/rex_app.cpp (LX-6) and relinked librexruntime.so, but the game
target compiles the INSTALLED share/rexglue/rex_app.cpp itself, so r3hd kept the old case-sensitive check; the
package tool then packaged that stale ELF. This test drives tools/linux/r3hd_linux_build.py's game_rebuild /
host_input_problems on a synthetic game build with a fake Ninja that decides by timestamps only, as the real one does:

  1. baseline gamesync writes the stamp; the package check passes;
  2. the LX2C case: the installed rex_app.cpp changes content but keeps an OLDER modification time (a copy that
     preserves times); Ninja alone sees nothing to do, the package check still refuses (content stamp);
  3. gamesync touches the changed input, the fake Ninja recompiles and relinks, the check passes again;
  4. a hand-replaced bin/r3hd, a changed tree source, a stale staged GPU plugin and a missing stamp are refused;
  5. sdkupdate with --game-build runs the game rebuild.

  python3 tools/linux/test_r3hd_host_inputs.py
"""
import hashlib
import inspect
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import r3hd_linux_build as B  # noqa: E402

fails, oks = [], []


def check(name, ok, detail=""):
    (oks if ok else fails).append(name)
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f" ({detail})"))


class FakeNinja:
    """`cmake --build BUILD --target r3hd [-j N | -- -n]` by timestamps: r3hd depends on every host input."""

    def __init__(self, build, inputs):
        self.build, self.inputs = build, inputs
        self.builds = 0

    def stale(self):
        elf = self.build / "r3hd"
        return not elf.exists() or any(p.stat().st_mtime_ns > elf.stat().st_mtime_ns for p in self.inputs())

    def __call__(self, argv, log, cwd=None, check=True, env=None):
        argv = [str(a) for a in argv]
        assert argv[:3] == ["cmake", "--build", str(self.build)] and "r3hd" in argv, argv
        if argv[-2:] == ["--", "-n"]:
            return 0, ("[1/2] Building CXX object CMakeFiles/r3hd.dir/rex_app.cpp.o\n[2/2] Linking CXX executable r3hd\n"
                       if self.stale() else "ninja: no work to do.\n")
        if not self.stale():
            return 0, "ninja: no work to do.\n"
        self.builds += 1
        h = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(self.inputs())))
        elf = self.build / "r3hd"
        elf.write_bytes(b"\x7fELF" + h.digest())
        future = max(p.stat().st_mtime_ns for p in self.inputs()) + 10**9
        os.utime(elf, ns=(future, future))
        return 0, ("[1/3] Building CXX object CMakeFiles/r3hd.dir/share/rexglue/rex_app.cpp.o\n"
                   "[2/3] Building CXX object CMakeFiles/r3hd.dir/src/main.cpp.o\n[3/3] Linking CXX executable r3hd\n")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        prefix, tree, build = t / "sdk/out/install/linux-amd64", t / "rex_lma", t / "build/game-lma"
        files = {prefix / "share/rexglue/rex_app.cpp": b"if (!is_regular_file(xex_host)) {\n",
                 prefix / "include/rex/rex_app.h": b"#pragma once\n",
                 prefix / "lib/librexruntime.so": b"\x7fELF runtime",
                 prefix / "lib/librexgpu-xenos.so": b"\x7fELF plugin",
                 tree / "src/main.cpp": b"int main() {}\n"}
        for p, data in files.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        build.mkdir(parents=True)
        (build / "CMakeCache.txt").write_text(f"CMAKE_PREFIX_PATH:UNINITIALIZED={prefix.as_posix()}\n"
                                              f"R3HD_TREE:UNINITIALIZED={tree.as_posix()}\n")
        (build / B.PLUGIN).write_bytes(files[prefix / "lib/librexgpu-xenos.so"])
        ninja = FakeNinja(build, lambda: [p for p in files] + [build / B.PLUGIN][:0])
        B.sh = ninja
        log = t / "log"

        g = B.game_rebuild(build, 4, log)
        check("1 baseline gamesync builds, stamps and passes", B.gamesync_passed(g) and g["baseline"] and ninja.builds == 1, g)
        check("1 package check passes on the current build", B.host_input_problems(build, log) == [])

        old = (build / "r3hd").read_bytes()
        cpp = prefix / "share/rexglue/rex_app.cpp"
        before = cpp.stat().st_mtime_ns
        cpp.write_bytes(b"if (!is_regular_file(xex_host) REX_XEX_CASE_FALLBACK(xex_host)) {\n")
        os.utime(cpp, ns=(before - 10**10, before - 10**10))  # content changed, timestamp older (LX2C hazard)
        check("2 Ninja alone sees nothing to do (timestamps)", not ninja.stale())
        probs = B.host_input_problems(build, log)
        check("2 the stale ELF is refused by content", any("sdk:share/rexglue/rex_app.cpp" in p for p in probs), probs)

        g = B.game_rebuild(build, 4, log)
        check("3 gamesync names the changed input and rebuilds rex_app.cpp + main.cpp + link",
              g["changed_inputs"] == ["sdk:share/rexglue/rex_app.cpp"] and len(g["compiled"]) == 2 and g["linked"]
              and B.gamesync_passed(g) and (build / "r3hd").read_bytes() != old, g)
        check("3 package check passes after gamesync", B.host_input_problems(build, log) == [])
        g = B.game_rebuild(build, 4, log)
        check("3 a second gamesync is a no-op", not g["compiled"] and not g["changed_inputs"] and B.gamesync_passed(g), g)

        good = (build / "r3hd").read_bytes()
        (build / "r3hd").write_bytes(good + b"x")
        check("4 a hand-replaced r3hd is refused",
              any("not the ELF" in p for p in B.host_input_problems(build, log)))
        (build / "r3hd").write_bytes(good)
        (tree / "src/main.cpp").write_bytes(b"int main() { return 1; }\n")
        check("4 a changed tree source is refused",
              any("tree:main.cpp" in p for p in B.host_input_problems(build, log)))
        B.game_rebuild(build, 4, log)
        (build / B.PLUGIN).write_bytes(b"\x7fELF old plugin")
        check("4 a stale staged GPU plugin is refused",
              any(B.PLUGIN in p for p in B.host_input_problems(build, log)))
        (build / B.PLUGIN).write_bytes(files[prefix / "lib/librexgpu-xenos.so"])
        check("4 current again", B.host_input_problems(build, log) == [])
        (build / B.HOST_STAMP).unlink()
        probs = B.host_input_problems(build, log)
        check("4 a build without a stamp is refused with the gamesync hint", len(probs) == 1 and "gamesync" in probs[0], probs)

    src = inspect.getsource(B.sdkupdate)
    check("5 sdkupdate --game-build rebuilds the game target",
          "game_rebuild(args.game_build" in src and "gamesync_passed" in src)
    pkg = (HERE / "r3hd_linux_package.py").read_text(encoding="utf-8")
    check("5 the package tool refuses a game build that is not current", bool(re.search(r"host_input_problems\(", pkg)))
    print(f"R3HD_HOST_INPUTS_TEST {'PASS' if not fails else 'FAIL'} checks={len(oks) + len(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())

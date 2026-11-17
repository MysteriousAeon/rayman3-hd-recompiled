"""G6-P43 (D-299): the Auto prompt snapshot must query the SDL instance the input driver initialized.

rexruntime links SDL3-static and exports that link interface, so r3hd.exe carries a second, never-initialized
SDL copy. An inlined LaunchStyle() in the executable therefore saw zero gamepads and chose Xbox for a physical
DualSense. This test checks the source wiring and, with --bin, the built module boundary from the PE tables:
rexruntime.dll exports RuntimeLaunchStyle and r3hd.exe imports it from rexruntime.dll. It reads files only.
"""
import argparse
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "?RuntimeLaunchStyle@r3hd_prompts@@YA?AW4Style@1@XZ"
LOG = b"R3HD prompts auto_identity module=rexruntime"
rows = []


def check(name, ok, detail=""):
    rows.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")


class Pe:
    def __init__(self, path):
        self.data = path.read_bytes()
        d = self.data
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        assert d[pe:pe + 4] == b"PE\0\0"
        sections, optional = struct.unpack_from("<H12xH", d, pe + 6)
        opt = pe + 24
        assert struct.unpack_from("<H", d, opt)[0] == 0x20B, "PE32+ expected"
        self.dirs = [struct.unpack_from("<II", d, opt + 112 + 8 * i) for i in range(16)]
        self.sections = []
        for i in range(sections):
            s = opt + optional + 40 * i
            vsize, va, rsize, raw = struct.unpack_from("<IIII", d, s + 8)
            self.sections.append((va, max(vsize, rsize), raw))

    def off(self, rva):
        for va, size, raw in self.sections:
            if va <= rva < va + size:
                return raw + rva - va
        raise ValueError(hex(rva))

    def cstr(self, rva):
        o = self.off(rva)
        return self.data[o:self.data.index(b"\0", o)].decode("ascii", "replace")

    def exports(self):
        rva, size = self.dirs[0]
        if not rva:
            return set()
        o = self.off(rva)
        count, names = struct.unpack_from("<I", self.data, o + 24)[0], struct.unpack_from("<I", self.data, o + 32)[0]
        table = self.off(names)
        return {self.cstr(struct.unpack_from("<I", self.data, table + 4 * i)[0]) for i in range(count)}

    def imports(self):
        rva, _ = self.dirs[1]
        result = {}
        o = self.off(rva)
        while True:
            lookup, _, _, name, first = struct.unpack_from("<IIIII", self.data, o)
            if not name:
                return result
            entries, t = set(), self.off(lookup or first)
            while (thunk := struct.unpack_from("<Q", self.data, t)[0]):
                if not thunk >> 63:
                    entries.add(self.cstr((thunk & 0x7FFFFFFF) + 2))
                t += 8
            result[self.cstr(name).lower()] = entries
            o += 20


def source_checks():
    app = (ROOT / "tools/m2_host/r3hd_app.h").read_text(encoding="utf-8")
    windows = re.search(r"#ifdef _WIN32\s*\n(?:\s*//[^\n]*\n)*\s*const auto style = r3hd_prompts::(\w+)\(\);", app)
    check("host Windows launch snapshot calls RuntimeLaunchStyle", bool(windows) and windows.group(1) == "RuntimeLaunchStyle",
          windows.group(1) if windows else "not found")
    header = (ROOT / "tools/r3hd_button_prompts_sdl.h").read_text(encoding="utf-8")
    check("RuntimeLaunchStyle is declared out of line", re.search(r"^Style RuntimeLaunchStyle\(\);", header, re.M) is not None)
    patch = (ROOT / "tools/r3hd_button_prompts_patch.py").read_text(encoding="utf-8")
    check("patch defines RuntimeLaunchStyle in the SDL input driver",
          'patch_once("src/input/sdl/sdl_input_driver.cpp"' in patch and "r3hd_prompts::RuntimeLaunchStyle() {" in patch)
    driver = ROOT / "external/rexglue-sdk/src/input/sdl/sdl_input_driver.cpp"
    if driver.exists():
        text = driver.read_text(encoding="utf-8", errors="replace")
        if "RuntimeLaunchStyle" in text:
            check("patched input driver initializes SDL gamepads and defines the snapshot",
                  "SDL_InitSubSystem(SDL_INIT_GAMEPAD)" in text and "r3hd_prompts::RuntimeLaunchStyle() {" in text)


def binary_checks(bin_dir):
    exe, dll = Pe(bin_dir / "r3hd.exe"), Pe(bin_dir / "rexruntime.dll")
    check("rexruntime.dll exports RuntimeLaunchStyle", SYMBOL in dll.exports())
    imported = exe.imports().get("rexruntime.dll", set())
    check("r3hd.exe imports RuntimeLaunchStyle from rexruntime.dll", SYMBOL in imported)
    check("auto identity log is emitted by rexruntime.dll", LOG in dll.data and LOG not in exe.data)
    # Informational: the duplicate static SDL that caused the defect is still present in the executable.
    print(f"INFO r3hd.exe own SDL copy present={b'SDL_HIDAPI_DEVICE_DETECTION' in exe.data}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", type=Path, help="directory holding r3hd.exe and rexruntime.dll")
    parser.add_argument("--binaries-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.binaries_only:
        source_checks()
    if args.bin:
        binary_checks(args.bin)
    passed = sum(rows)
    print(f"BUTTON_PROMPT_MODULE {'PASS' if passed == len(rows) else 'FAIL'} {passed}/{len(rows)}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

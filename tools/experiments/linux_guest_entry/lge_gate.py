"""Linux Guest Entry (LGE): private extract, Windows reference, transfer, native gate, evidence, audit.

Subcommands:
  extract      (Windows, read-only on the generated tree) verify the selection against the
               pinned codegen and write the PRIVATE verbatim extract (lge_generated.cpp,
               r3hd_pch.h, GENERATED_MANIFEST.json) under private/work/linux_guest_entry/.
  windows      (Windows) build Clang O0/O2 ordinary harnesses against the existing Windows SDK
               install, run them repeatedly and write the PRIVATE windows_reference.json.
  private-zip  (Windows) package the private extract + reference into the private transfer ZIP.
  source       (any) write the source-only CachyOS ZIP from committed Git bytes (no generated code).
  run          (Linux x86-64 only) build Clang/GCC O0/O2, run the LGE matrix and the LRB regression.
  evidence     (Linux) package results, own ELF/object bytes and dumps (PRIVATE: compiled game code).
  audit        (Windows/any, read-only) validate a returned evidence ZIP against Git and the reference.

Never builds, patches or installs the SDK; never launches the game; never commits, publishes
or uploads generated code; removes only /dev/shm objects proven to belong to its own child.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REL = "tools/experiments/linux_guest_entry/"
LRB_REL = "tools/experiments/linux_runtime_bootstrap/"
sys.path.insert(0, str(HERE.parent / "linux_runtime_bootstrap"))
import lrb_gate as L  # noqa: E402  (audited LRB runner primitives, unchanged)

GateError, require, sha, lf, read_json = L.GateError, L.require, L.sha, L.lf, L.read_json
OWN_FILES = ["CMakeLists.txt", "README.md", "lge_gate.py", "lge_select.py", "lge_selection.json",
             "lge_define_rex_func.h", "lge_tests.cpp", "m2_trace.h",
             "test_lge_gate.py"]
SELECTION = HERE / "lge_selection.json"
PRIVATE = ROOT / "private/work/linux_guest_entry"
DEFAULT_GENERATED = ROOT / "private/work/rex/generated/Default"
DEFAULT_WIN_PREFIX = ROOT / "external/rexglue-sdk/out/install/win-amd64"
PRIVATE_FILES = ("lge_generated.cpp", "r3hd_pch.h", "GENERATED_MANIFEST.json", "windows_reference.json")
FATAL = ("lge-write-guard", "lge-read-guard")
PASS_LINE = re.compile(r"LGE PASS cases=(\d+) checks=(\d+) aggregate=([0-9a-f]{64}) native=([01])\n")
CASE_FIELDS = ("id", "fn", "guest", "seed", "input", "before", "after", "nonint", "writable", "changed",
               "delta", "trace", "model", "digest")
# Relocation targets a selected generated function body may reference: other
# selected functions, the M2 prologue hook (defined by lge_tests), toolchain stack
# protection and local labels/sections (__func__ strings, constant pools). The
# object as a whole also carries unrelated inline STL/CRT code from the SDK
# headers; that is not generated code and is not reachable from these bodies
# unless it appears here or among the inline helpers below.
BODY_TARGETS = re.compile(r"^(?:_Z7M2EnterPKcR10PPCContext|__stack_chk_fail|_GLOBAL_OFFSET_TABLE_|\..*)$")
# Header-inline helpers the verbatim bodies instantiate, by exact mangled name.
# A compiler may emit them out of line (O0). Each one a body reaches must be
# DEFINED in the generated object itself and its own disassembled body may reach
# only other listed helpers, local data or stack protection: no import, no
# generated or library function. Native retry 2: GCC O0 emitted the pinned SDK's
# GCC polyfill for __builtin_rotateleft64 (rex/platform.h: std::rotl on uint64_t).
INLINE_HELPERS = {
    "_ZN3rex3ppc10CRRegister7compareIiEEvT_S3_RKNS0_11XERRegisterE": "rex::ppc::CRRegister::compare<int32_t>",
    "_ZN3rex3ppc10CRRegister7compareIjEEvT_S3_RKNS0_11XERRegisterE": "rex::ppc::CRRegister::compare<uint32_t>",
    "_ZSt4rotlITkSt18__unsigned_integermET_S0_i": "std::rotl<uint64_t> (C++20 constrained mangling)",
    "_ZSt4rotlImET_S0_i": "std::rotl<uint64_t> (GCC ABI-compatibility alias of the same definition)",
    "_ZSt6__rotlImET_S0_i": "std::__rotl<uint64_t>, called by std::rotl",
}
# Names that must denote one definition (checked at equal final-ELF addresses).
HELPER_ALIASES = ({"_ZSt4rotlITkSt18__unsigned_integermET_S0_i", "_ZSt4rotlImET_S0_i"},)
HELPER_TARGETS = re.compile(r"^(?:__stack_chk_fail|_GLOBAL_OFFSET_TABLE_|\..*)$")
GENERATED_NAME = re.compile(r"^(?:__imp__)?(?:sub_[0-9A-F]{8}|__(?:save|rest)\w+_\d+)$")
FUNC_HEADER = re.compile(r"^[0-9a-f]+ <([^>]+)>:$")
# GNU objdump -drw (wide) appends each relocation to its instruction line after a
# tab ("...\tcall 2e <f+0x1e>\t2a: R_X86_64_PLT32\tsigaction-0x4"); without -w it
# prints it on its own indented line. Both forms are accepted.
RELOC = re.compile(r"(?:^|\t)\s*[0-9a-f]+:\s+R_X86_64_\w+\s+([^\s+-]+)")


def body_references(objdump_text, names):
    """Relocation targets per selected function from `objdump -drw` (no demangling)."""
    # Each body is the global __imp__X with a weak alias X at the same address;
    # objdump labels the block with either name, so both map to X.
    refs, current = {}, None
    for line in objdump_text.splitlines():
        header = FUNC_HEADER.match(line)
        if header:
            label = header.group(1)
            plain = label[7:] if label.startswith("__imp__") else label
            current = plain if plain in names else (label if label in INLINE_HELPERS else None)
            if current:
                refs.setdefault(current, set())
            continue
        if current:
            for match in RELOC.finditer(line):
                refs[current].add(match.group(1))
    return refs


def helper_block(refs, helper):
    for group in HELPER_ALIASES:
        if helper in group:
            return next((refs[n] for n in sorted(group) if n in refs), None)
    return refs.get(helper)


def check_body_references(refs, names, defined):
    """Closed-call contract over selected bodies and the inline helpers they reach.

    `defined` is the set of symbols defined in the generated object (nm)."""
    require({n for n in refs if n in names} == set(names), "every selected function body found in the generated object")
    reached, out = [], {}
    for name in sorted(names):
        targets = refs[name]
        # Every body enters through the production M2 prologue: an empty or
        # misparsed block can never pass vacuously.
        require("_Z7M2EnterPKcR10PPCContext" in targets, f"{name} body has no M2Enter prologue relocation")
        for target in targets:
            plain = target[7:] if target.startswith("__imp__") else target
            if target in INLINE_HELPERS:
                reached.append(target)
                continue
            require(plain in names or BODY_TARGETS.match(target),
                    f"{name} references {target}, outside the selected set and admitted helpers")
        out[name] = sorted(targets)
    while reached:
        helper = reached.pop()
        if helper in out:
            continue
        require(helper in defined, f"inline helper {helper} is not defined in the generated object")
        block = helper_block(refs, helper)
        require(block is not None, f"inline helper {helper} has no disassembled body in the generated object")
        for target in block:
            if target in INLINE_HELPERS:
                reached.append(target)
            else:
                require(HELPER_TARGETS.match(target), f"inline helper {helper} references {target}")
        out[helper] = sorted(block)
    return out


def check_helper_aliases(elf_symbols, used):
    """Aliased helper names must resolve to one local definition in the final ELF."""
    for group in HELPER_ALIASES:
        if group & set(used):
            entries = [elf_symbols.get(n) for n in sorted(group)]
            require(all(e is not None and e[1] in "TtWw" for e in entries), "helper alias defined in the final ELF")
            require(len({e[0] for e in entries}) == 1, "helper alias names share one final-ELF address")
    return True


READELF_SYM = re.compile(r"^\s*\d+:\s+([0-9a-f]+)\s+\d+\s+(\w+)\s+(\w+)\s+\w+\s+(\w+)\s+(\S+)$")


def readelf_symbols(text):
    """Defined .symtab entries from `readelf -Ws` as {name: (address, nm-style type)}."""
    out = {}
    for line in text.splitlines():
        m = READELF_SYM.match(line)
        if m and m.group(4) != "UND" and m.group(2) == "FUNC":
            out[m.group(5)] = (int(m.group(1), 16), {"WEAK": "W", "GLOBAL": "T", "LOCAL": "t"}.get(m.group(3), "?"))
    return out


def configure_lrb_fatal_contract():
    """Register the LGE fatal modes with the audited LRB traced-run validators.

    Each LGE mode emits one ordinary-code witness ("begin", no admitted fault)
    immediately before calling generated code; the kernel must then report one
    SEGV_ACCERR at exactly the witnessed guard-page address, followed by the
    owner's same-process SI_TKILL and a real SIGSEGV death (the LRB
    "unadmitted" profile). Shm policy for these modes is unlink-after-map.
    """
    for mode in FATAL:
        L.PHASES[mode] = [("begin", (0, 0, 0, 0))]
        L.ACCERR_ROWS[mode] = [1]
    L.FATAL = tuple(dict.fromkeys(L.FATAL + FATAL))


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True, timeout=120).stdout


def selection():
    data = read_json(lf(SELECTION))
    require(data.get("format") == "LGE_SELECTION_V1", "selection format")
    names = [f["name"] for f in data["functions"]]
    require(len(names) == len(set(names)) and 3 <= len(names) <= 10, "selection size")
    closed = set(names)
    for f in data["functions"]:
        require(set(f["closure"]) <= closed and set(f["calls"]) <= closed, "selection is call-closed: " + f["name"])
    return data


# ------------------------------------------------------------- canonical cases

def parse_case(line):
    """Split one canonical case record into its named fields (exact, ordered)."""
    require(line.startswith("LGE_CASE_V1|"), "case record prefix")
    parts = line[len("LGE_CASE_V1|"):].split("|")
    require(len(parts) == len(CASE_FIELDS), "case record field count")
    fields = {}
    for part, name in zip(parts, CASE_FIELDS):
        require(part.startswith(name + "="), "case record field order: " + name)
        fields[name] = part[len(name) + 1:]
    require(sha(line[:line.rindex("|digest=")].encode()) == fields["digest"], "case digest recomputes")
    require(fields["nonint"] == "unchanged" and fields["model"] == "pass", "case self-checks")
    return fields


def parse_cases(data):
    text = data.decode("ascii")
    require(text.endswith("\n") and "\r" not in text, "case file framing")
    cases = [parse_case(line) for line in text[:-1].split("\n")]
    ids = [c["id"] for c in cases]
    require(len(ids) == len(set(ids)), "unique case ids")
    return cases


def aggregate(cases):
    h = hashlib.sha256()
    for c in cases:
        h.update(c["digest"].encode() + b"\n")
    return h.hexdigest()


def compare_cases(reference, candidate, functions):
    """Field-by-field comparison; a matching total alone is never accepted."""
    require(len(reference) == len(candidate), "case count differs from reference")
    seen = set()
    for ref, got in zip(reference, candidate):
        for name in CASE_FIELDS:
            require(ref[name] == got[name], f"case {ref['id']}: field {name} differs from the Windows reference")
        require(got["fn"] in functions, "case function outside the selection")
        for entered in filter(None, got["trace"].split(",")):
            require(entered.startswith("__imp__") and entered[7:] in functions,
                    f"case {got['id']}: entered function outside the selection")
        seen.add(got["fn"])
    return seen


# ------------------------------------------------------------------ extract

def codegen_digest(generated):
    out = subprocess.run([sys.executable, str(ROOT / "tools/r3hd_build_step.py"), "digest", str(generated), "--json"],
                         capture_output=True, text=True, check=True, timeout=600, cwd=ROOT).stdout
    return json.loads(out)


def function_body(path, line, name):
    lines = path.read_bytes().decode("utf-8").split("\n")
    first = lines[line - 1].rstrip("\r")
    require(first == f"DEFINE_REX_FUNC({name}) {{", "definition line: " + name)
    body = []
    for raw in lines[line - 1:]:
        body.append(raw.rstrip("\r"))
        if body[-1] == "}":
            break
    require(body[-1] == "}", "definition end: " + name)
    return "\n".join(body) + "\n"


def extract(generated, out):
    sys.path.insert(0, str(HERE))
    import lge_select  # classification rules, shared with the census
    sel = selection()
    tree = sel["generated_tree"]
    digest = codegen_digest(generated)
    require(digest == {"files": tree["codegen_files"], "digest": tree["codegen_digest"]},
            "generated tree is not the pinned codegen output")
    pch = (generated / tree["pch"]).read_bytes()
    require(sha(pch) == tree["pch_sha256"], "r3hd_pch.h identity")
    require(b'#include "m2_trace.h"' in pch, "pch carries the M2 prologue block")
    declarations = (generated / tree["declarations"]).read_bytes()
    require(sha(declarations) == tree["declarations_sha256"], "r3hd_funcs.h identity")
    decl_lines = set(declarations.decode().replace("\r\n", "\n").split("\n"))
    parts = ["// LGE PRIVATE EXTRACT: game-derived generated code (Rayman 3 HD static recompilation).\n"
             "// Never commit, publish, upload or include in evidence. Bodies are verbatim.\n"
             f"// codegen digest {tree['codegen_digest']}\n"
             '#include "r3hd_pch.h"\n\n']
    functions = []
    for f in sel["functions"]:
        decl = f"DECLARE_REX_FUNC({f['name']});"
        require(decl in decl_lines, "declaration present in r3hd_funcs.h: " + f["name"])
        parts.append(decl + "\n")
    parts.append("\n")
    for f in sel["functions"]:
        source = generated / f["file"]
        body = function_body(source, f["line"], f["name"])
        require(sha(body.encode()) == f["body_sha256"], "body digest: " + f["name"])
        lines = body.rstrip("\n").split("\n")
        cls = lge_select.classify({"body": lines})
        require(cls["reasons"] == [] and sorted(cls["calls"]) == sorted(f["calls"]),
                "body uses only admitted forms: " + f["name"])
        parts.append(f"// {f['name']} guest {f['guest']} from {f['file']}:{f['line']}\n")
        parts.append(body + "\n")
        functions.append({"name": f["name"], "guest": f["guest"], "file": f["file"], "line": f["line"],
                          "body_sha256": f["body_sha256"], "source_file_sha256": sha(source.read_bytes())})
    cpp = "".join(parts).encode()
    require(cpp.count(b"\nDEFINE_REX_FUNC(") == len(sel["functions"]), "exactly the selected definitions")
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("m2_trace.h",):
        require(not (out / stale).exists(), "private dir must not shadow " + stale)
    (out / "lge_generated.cpp").write_bytes(cpp)
    (out / "r3hd_pch.h").write_bytes(pch)
    manifest = {"format": "LGE_GENERATED_V1", "codegen": digest, "selection_sha256_lf": sha(lf(SELECTION)),
                "files": {"lge_generated.cpp": sha(cpp), "r3hd_pch.h": sha(pch)},
                "r3hd_pch_sha256_lf": sha(pch.replace(b"\r\n", b"\n")), "functions": functions}
    (out / "GENERATED_MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"LGE_EXTRACT PASS functions={len(functions)} lge_generated.cpp={sha(cpp)} out={out}")


def rotate_shifts(cpp_text):
    """Every rotate primitive in the verbatim bodies, as literal shift amounts.

    Precondition for the GCC polyfill equivalence: Clang's __builtin_rotateleft64
    and the pinned GCC polyfill std::rotl<uint64_t>(x, int n) are both the 64-bit
    left rotation by n mod 64; for a literal 0 <= n < 64 they are identical
    functions of x. Any other rotate form (32-bit, non-literal or out-of-range
    amount) is refused rather than assumed equivalent."""
    shifts = []
    for match in re.finditer(r"__builtin_rotate\w*", cpp_text):
        require(match.group(0) == "__builtin_rotateleft64", "only the 64-bit rotate primitive is admitted")
        start = match.end()
        require(cpp_text[start] == "(", "rotate call syntax")
        depth, i, comma = 0, start, None
        while True:
            ch = cpp_text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            elif ch == "," and depth == 1:
                comma = i
            i += 1
        require(comma is not None, "rotate call has two arguments")
        amount = cpp_text[comma + 1:i].strip()
        require(re.fullmatch(r"\d+", amount) is not None and int(amount) < 64, "rotate amount is a literal in [0, 63]")
        shifts.append(int(amount))
    return shifts


def private_identity(private_dir, need_reference=True):
    manifest = read_json((private_dir / "GENERATED_MANIFEST.json").read_bytes())
    require(manifest.get("format") == "LGE_GENERATED_V1", "private manifest format")
    require(manifest["selection_sha256_lf"] == sha(lf(SELECTION)), "private extract matches the tracked selection")
    for name, digest in manifest["files"].items():
        require(sha((private_dir / name).read_bytes()) == digest, "private file digest: " + name)
    sel = selection()
    require([f["name"] for f in manifest["functions"]] == [f["name"] for f in sel["functions"]], "private functions")
    rotate_shifts((private_dir / "lge_generated.cpp").read_bytes().decode("utf-8"))
    present = sorted(p.name for p in private_dir.iterdir() if p.is_file())
    allowed = set(PRIVATE_FILES) if need_reference else set(PRIVATE_FILES) - {"windows_reference.json"}
    require(set(present) <= set(PRIVATE_FILES) and allowed <= set(present), "private directory inventory")
    reference = None
    if need_reference:
        reference = read_json((private_dir / "windows_reference.json").read_bytes())
        require(reference.get("format") == "LGE_REFERENCE_V1", "reference format")
        require(reference["generated_manifest_sha256"] == sha((private_dir / "GENERATED_MANIFEST.json").read_bytes()),
                "reference built from this private extract")
        cases = parse_cases(reference["cases_text"].encode("ascii"))
        require(sha(reference["cases_text"].encode("ascii")) == reference["cases_sha256"], "reference cases digest")
        require(aggregate(cases) == reference["aggregate"], "reference aggregate")
    return manifest, reference


# ------------------------------------------------------------------ Windows reference

def run_child(argv, env_extra, timeout=300):
    env = os.environ.copy()
    env.pop("LRB_GATE_TOKEN", None)
    env.pop("LRB_SDK_LOG_CONSOLE", None)
    env.update(env_extra)
    p = subprocess.run([str(a) for a in argv], capture_output=True, timeout=timeout, env=env)
    return {"argv": [str(a) for a in argv], "returncode": p.returncode, "stdout": p.stdout.decode(errors="replace"),
            "stderr": p.stderr.decode(errors="replace")}


def windows_reference(private_dir, prefix, repeats, work):
    require(platform.system() == "Windows", "the reference harness runs on the Windows development host")
    manifest, _ = private_identity(private_dir, need_reference=False)
    cxx, cc = shutil.which("clang++"), shutil.which("clang")
    require(cxx and cc and shutil.which("ninja") and shutil.which("cmake"), "run inside tools\\devenv.bat")
    work.mkdir(parents=True, exist_ok=True)
    configs, text = [], None
    for opt in ("0", "2"):
        build = work / f"clang_O{opt}"
        if build.exists():
            shutil.rmtree(build)
        log = []
        row = {"key": f"clang++_O{opt}", "commands": log, "runs": []}
        configs.append(row)
        row["cxx_version"] = L.command([cxx, "--version"], log)
        L.command(["cmake", "-S", HERE, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                   "-DCMAKE_PREFIX_PATH=" + str(prefix), "-DCMAKE_CXX_COMPILER=clang++", "-DCMAKE_C_COMPILER=clang",
                   "-DLGE_OPT=" + opt, "-DLRB_ORDINARY_ONLY=ON", "-DLGE_GENERATED_DIR=" + str(private_dir)], log)
        build_step(["cmake", "--build", build, "--verbose"], log)
        exe = build / "lge_tests.exe"
        row["executable_sha256"] = sha(exe.read_bytes())
        for i in range(repeats):
            cases_path = build / f"cases_{i}.txt"
            own = build / f"ownership_{i}.json"
            for p in (cases_path, own):
                if p.exists():
                    p.unlink()
            # rexruntime.dll lives in the existing install's bin directory (searched first).
            dll_path = str(prefix / "bin") + os.pathsep + os.environ.get("PATH", "")
            run = run_child([exe, "normal"], {"LGE_RESULTS_FILE": str(cases_path), "LRB_OWNERSHIP_FILE": str(own),
                                              "PATH": dll_path})
            row["runs"].append(run)
            require(run["returncode"] == 0 and run["stderr"] == "", f"Windows run failed: {L.describe({**run, 'mode': 'normal'})}")
            match = PASS_LINE.fullmatch(run["stdout"].replace("\r\n", "\n"))
            require(match is not None and match.group(4) == "0", "Windows stdout contract")
            data = cases_path.read_bytes()
            cases = parse_cases(data)
            require(aggregate(cases) == match.group(3) and len(cases) == int(match.group(1)), "Windows aggregate")
            run.update(cases=len(cases), checks=int(match.group(2)), aggregate=match.group(3), cases_sha256=sha(data))
            require(text is None or data.decode() == text, "Windows runs are not bit-identical across runs/O-levels")
            text = data.decode()
    checks = {r["checks"] for row in configs for r in row["runs"]}
    require(len(checks) == 1, "identical check count across Windows runs")
    cases = parse_cases(text.encode())
    reference = {"format": "LGE_REFERENCE_V1", "generated_manifest_sha256": sha((private_dir / "GENERATED_MANIFEST.json").read_bytes()),
                 "selection_sha256_lf": manifest["selection_sha256_lf"], "platform": platform.platform(),
                 "repeats": repeats, "configurations": configs, "checks": checks.pop(), "case_count": len(cases),
                 "aggregate": aggregate(cases), "cases_sha256": sha(text.encode()), "cases_text": text,
                 "functions_exercised": sorted({c["fn"] for c in cases})}
    (private_dir / "windows_reference.json").write_text(json.dumps(reference, indent=1) + "\n", encoding="utf-8",
                                                        newline="\n")
    print(f"LGE_WINDOWS PASS configurations=2 runs={2 * repeats} cases={len(cases)} checks={reference['checks']} "
          f"aggregate={reference['aggregate']}")


def private_zip(private_dir, path):
    manifest, reference = private_identity(private_dir)
    entries = {"private_generated/" + n: (private_dir / n).read_bytes() for n in PRIVATE_FILES}
    cpp = entries["private_generated/lge_generated.cpp"]
    require(cpp.count(b"\nDEFINE_REX_FUNC(") == len(manifest["functions"]), "inventory: only selected definitions")
    require(sorted(entries) == sorted("private_generated/" + n for n in PRIVATE_FILES), "private ZIP inventory")
    entries["PRIVATE_MANIFEST.json"] = (json.dumps({n: sha(b) for n, b in sorted(entries.items())}, indent=1)
                                        + "\n").encode()
    digest = L.write_zip(path, entries)
    (path.parent / (path.name + ".sha256")).write_text(f"{digest}  {path.name}\n", encoding="utf-8", newline="\n")
    print(f"LGE_PRIVATE PASS entries={len(entries)} size={path.stat().st_size} sha256={digest} path={path} "
          f"reference_aggregate={reference['aggregate']}")


# ------------------------------------------------------------------ source transfer

def source_files():
    return sorted([REL + f for f in OWN_FILES] + [LRB_REL + f for f in L.OWN_FILES])


def package_source(path):
    head = git("rev-parse", "HEAD").decode().strip()
    entries = {}
    for name in source_files():
        blob = git("show", f"HEAD:{name}").replace(b"\r\n", b"\n")
        require(lf(ROOT / name) == blob, "working file differs from HEAD: " + name)
        require(b"\nDEFINE_REX_FUNC(" not in blob, "generated code in the source package: " + name)
        entries[name] = blob
    manifest = {n: sha(b) for n, b in entries.items()}
    entries["SOURCE_MANIFEST.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    entries["IMPLEMENTATION_ID.json"] = (json.dumps({"commit": head, "sdk": L.SDK_PIN, "simde": L.SIMDE_PIN},
                                                    indent=2) + "\n").encode()
    digest = L.write_zip(path, entries)
    (path.parent / (path.name + ".sha256")).write_text(f"{digest}  {path.name}\n", encoding="utf-8", newline="\n")
    print(f"LGE_SOURCE PASS files={len(entries)} commit={head} size={path.stat().st_size} sha256={digest} path={path}")


def source_identity():
    manifest = read_json((ROOT / "SOURCE_MANIFEST.json").read_bytes())
    require(all(sha(lf(ROOT / p)) == h for p, h in manifest.items()), "source transfer hash mismatch")
    require(sorted(manifest) == source_files(), "LGE source inventory")
    identity = read_json((ROOT / "IMPLEMENTATION_ID.json").read_bytes())
    require(re.fullmatch(r"[0-9a-f]{40}", identity["commit"]) is not None, "commit identity")
    return manifest, identity


# ------------------------------------------------------------------ native gate

def validate_normal(run, reference_text):
    require(not run.get("timeout") and run["returncode"] == 0 and run["stderr"] == "", "normal run exit/stderr")
    match = PASS_LINE.fullmatch(run["stdout"])
    require(match is not None and match.group(4) == "1", "normal run stdout contract")
    require(run["cases_sha256"] == L.sha(reference_text.encode()), "case file differs from the Windows reference")
    require(match.group(3) == run["reference_aggregate"], "aggregate differs from the Windows reference")
    L.validate_ownership(run, expect_residue=False)
    return {"cases": int(match.group(1)), "checks": int(match.group(2))}


def run_plain(command, out, tag, reference_text, reference_aggregate, timeout=300):
    cases = out / "cases" / f"{tag}.txt"
    cases.parent.mkdir(parents=True, exist_ok=True)
    if cases.exists():
        cases.unlink()
    run = L.run_plain(command, "normal", out, tag, extra_env={"LGE_RESULTS_FILE": str(cases)}, timeout=timeout)
    data = cases.read_bytes() if cases.exists() else b""
    run.update(cases_file=str(cases), cases_sha256=sha(data), reference_aggregate=reference_aggregate)
    if data and sha(data) != sha(reference_text.encode()):
        # Keep the full divergent file and name the first differing field.
        try:
            compare_cases(parse_cases(reference_text.encode()), parse_cases(data),
                          {f["name"] for f in selection()["functions"]})
            run["divergence"] = "case file bytes differ although every parsed field matches"
        except GateError as error:
            run["divergence"] = str(error)
    return run


def binary_checks(build, key, log):
    """Readelf/objdump/nm facts the gate requires (the root audit re-derives them from the bytes)."""
    exe = build / "lge_tests"
    objects = sorted((build / "CMakeFiles/lge_generated.dir").rglob("*.o"))
    require(len(objects) == 1, "one generated object")
    gen = objects[0]
    dynamic = L.command(["readelf", "-Wd", exe], log)
    flags_now = (re.search(r"\(FLAGS_1\)\s+Flags:.*\bNOW\b", dynamic)
                 or re.search(r"\(FLAGS\).*\bBIND_NOW\b", dynamic))
    require(flags_now,
            "lge_tests linked with BIND_NOW")
    names = {f["name"] for f in selection()["functions"]}
    nm_text = L.command(["nm", "--defined-only", gen], log)
    (build / "generated.nm.txt").write_text(nm_text, encoding="utf-8")
    check_aliases(nm_text, names)
    defined = set(nm_symbols(nm_text))
    refs = check_body_references(body_references(L.command(["objdump", "-drw", gen], log), names), names, defined)
    check_helper_aliases(readelf_symbols(L.command(["readelf", "-Ws", exe], log)), refs)
    stray = {s for s in defined if GENERATED_NAME.match(s) and (s[7:] if s.startswith("__imp__") else s) not in names}
    require(not stray, "no unselected generated function in the object: " + ",".join(sorted(stray)))
    return gen, refs


NM_LINE = re.compile(r"^([0-9a-f]+) ([A-Za-z]) (\S+)$")


def nm_symbols(nm_text):
    symbols = {}
    for line in nm_text.splitlines():
        match = NM_LINE.match(line)
        if match:
            symbols[match.group(3)] = (int(match.group(1), 16), match.group(2))
    return symbols


def check_aliases(nm_text, names):
    """DEFINE_REX_FUNC contract: global __imp__X (text) and weak X at the same address."""
    symbols = nm_symbols(nm_text)
    for name in sorted(names):
        imp, alias = symbols.get("__imp__" + name), symbols.get(name)
        require(imp is not None and imp[1] == "T", f"__imp__{name} is a global text definition")
        require(alias is not None and alias[1] == "W", f"{name} is a weak definition")
        require(alias[0] == imp[0], f"{name} aliases __imp__{name} (same address)")
    return True


def build_step(argv, log):
    """Run a build command; on failure name the first compiler/linker diagnostic."""
    try:
        return L.command(argv, log)
    except GateError as error:
        text = (log[-1].get("stdout") or "") + "\n" + (log[-1].get("stderr") or "")
        raise GateError(f"{error}; first diagnostic: {first_diagnostic(text)} "
                        "(full log in results.json commands)") from None


def first_diagnostic(text):
    return next((line.strip()[:400] for line in text.splitlines()
                 if re.search(r"\b(?:error|undefined reference)\b", line, re.I)), "no diagnostic line captured")


def artifact_paths(build, key, gen):
    objects = build / "CMakeFiles/lge_tests.dir"
    owner = sorted(objects.rglob("lrb_owner.c.o"))
    access = sorted(objects.rglob("lrb_access.S.o"))
    require(len(owner) == 1 and len(access) == 1, "owner/access objects")
    return {f"native/{key}/{n}": p for n, p in {
        "lge_tests.elf": build / "lge_tests", "lge_generated.o": gen, "lrb_owner.o": owner[0],
        "lrb_access.o": access[0], "final.objdump.txt": build / "final.objdump.txt",
        "final.readelf.txt": build / "final.readelf.txt", "generated.objdump.txt": build / "generated.objdump.txt",
        "owner.objdump.txt": build / "owner.objdump.txt", "generated.nm.txt": build / "generated.nm.txt",
        "cases.txt": build / "cases.txt"}.items()}


def run_native(args):
    require(platform.system() == "Linux" and platform.machine() == "x86_64" and struct.calcsize("P") == 8,
            "native Linux x86-64 required; no Windows/WSL fallback")
    configure_lrb_fatal_contract()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    sdk, prefix, private_dir = args.sdk.resolve(), args.prefix.resolve(), args.private.resolve()
    result = {"status": "INCOMPLETE", "platform": platform.platform(), "machine": platform.machine(),
              "kernel": platform.release(), "python": sys.version, "repeats": args.repeats,
              "fatal_repeats": args.fatal_repeats, "lrb_repeats": args.lrb_repeats, "configurations": []}
    before_names = L.shm_names()
    result["shm_snapshot"] = {"before": before_names}
    try:
        manifest, identity = source_identity()
        result.update(identity=identity, source_manifest=manifest)
        gen_manifest, reference = private_identity(private_dir)
        result["private_identity"] = {"generated_manifest_sha256": sha((private_dir / "GENERATED_MANIFEST.json").read_bytes()),
                                      "files": gen_manifest["files"], "reference_aggregate": reference["aggregate"],
                                      "reference_cases_sha256": reference["cases_sha256"]}
        reference_text = reference["cases_text"]
        sdk_info = L.sdk_identity(sdk, prefix)
        result["sdk_identity"] = sdk_info
        for cxx_name, cc_name, opt in L.CONFIGS:
            cxx, cc = shutil.which(cxx_name), shutil.which(cc_name)
            require(cxx and cc, "missing compiler pair " + cxx_name)
            key = f"{cxx_name}_O{opt}"
            build = out / key
            row = {"key": key, "status": "INCOMPLETE", "commands": [], "normal": [], "traced": []}
            result["configurations"].append(row)
            log = row["commands"]
            row["cxx_version"] = L.command([cxx, "--version"], log)
            row["cc_version"] = L.command([cc, "--version"], log)
            if build.exists():
                shutil.rmtree(build)
            build_step(["cmake", "-S", HERE, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                        "-DCMAKE_PREFIX_PATH=" + str(prefix), "-DCMAKE_CXX_COMPILER=" + cxx,
                       "-DCMAKE_C_COMPILER=" + cc, "-DCMAKE_ASM_COMPILER=" + cc, "-DLGE_OPT=" + opt,
                       "-DLRB_ORDINARY_ONLY=OFF", "-DLGE_GENERATED_DIR=" + str(private_dir)], log)
            build_log = build_step(["cmake", "--build", build, "--verbose"], log)
            # GCC must use the GCC-placement DEFINE_REX_FUNC; Clang keeps the pinned macro.
            row["portable_define"] = "lge_define_rex_func.h" in build_log
            require(row["portable_define"] == (cxx_name == "g++"), "DEFINE_REX_FUNC variant for this compiler")
            executable = build / "lge_tests"
            digest = sha(executable.read_bytes())
            row["executable_sha256"] = digest
            for i in range(args.repeats):
                run = run_plain([executable], out, f"{key}_normal_{i}", reference_text, reference["aggregate"])
                row["normal"].append(run)
                row.setdefault("normal_summary", []).append(L.checked(run, lambda r: validate_normal(r, reference_text)))
                if i == 0:
                    shutil.copyfile(run["cases_file"], build / "cases.txt")
                    compare_cases(parse_cases(reference_text.encode()), parse_cases((build / "cases.txt").read_bytes()),
                                  {f["name"] for f in selection()["functions"]})
            for i in range(args.fatal_repeats):
                for mode in FATAL:
                    record = {"mode": mode, "status": "INCOMPLETE"}
                    row["traced"].append(record)
                    L.traced_run(executable, mode, out, f"{key}_{mode}_{i}", result=record)
            require(sha(executable.read_bytes()) == digest, "executable changed during runs")
            gen, row["body_references"] = binary_checks(build, key, log)
            objects = build / "CMakeFiles/lge_tests.dir"
            for tool, flags, path, target in (
                    ("objdump", ["-drwC"], build / "final.objdump.txt", executable),
                    ("readelf", ["-Wh", "-Wr", "-Ws", "-Wl", "-Wd"], build / "final.readelf.txt", executable),
                    ("objdump", ["-drw"], build / "generated.objdump.txt", gen),  # mangled: audit re-parses
                    ("objdump", ["-drwC"], build / "owner.objdump.txt", sorted(objects.rglob("lrb_owner.c.o"))[0])):
                path.write_text(L.command([tool, *flags, target], log), encoding="utf-8")
            row["artifacts"] = {n: sha(p.read_bytes()) for n, p in artifact_paths(build, key, gen).items()}
            require(row["artifacts"][f"native/{key}/lge_tests.elf"] == digest, "executable changed during inspection")
            row["status"] = "PASS"
        names = L.shm_names()
        ours = {r["ownership"]["shm_name"] for row in result["configurations"] for r in row["normal"] + row["traced"]
                if isinstance(r.get("ownership"), dict) and isinstance(r["ownership"].get("shm_name"), str)}
        result["shm_snapshot"].update(after_lge=names, foreign_new=sorted(set(names) - set(before_names) - ours),
                                      own_left=sorted(set(names) & ours))
        require(not result["shm_snapshot"]["own_left"], "own shm residue left")
        # LRB regression, unchanged sources, bounded counts (prior fixtures untouched by LGE).
        target = out / "lrb_regression"
        argv = [sys.executable, str(HERE.parent / "linux_runtime_bootstrap/lrb_gate.py"), "run", "--sdk", str(sdk),
                "--prefix", str(prefix), "--out", str(target), "--repeats", str(args.lrb_repeats),
                "--fatal-repeats", "1", "--skip-prior"]
        p = subprocess.run(argv, capture_output=True, text=True, timeout=7200, cwd=ROOT)
        result["lrb_regression"] = {"argv": argv, "returncode": p.returncode, "stdout": p.stdout[-8000:],
                                    "stderr": p.stderr[-8000:], "out": str(target)}
        require(p.returncode == 0 and "LRB_GATE PASS configurations=4" in p.stdout, "LRB regression failed")
        result["shm_snapshot"]["after_lrb"] = L.shm_names()
        require(L.sdk_identity(sdk, prefix) == sdk_info, "SDK changed during run")
        require(source_identity() == (manifest, identity), "sources changed during run")
        result["positive_checks"] = validate_results({**result, "status": "PASS"}, reference)
        result["status"] = "PASS"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"LGE_GATE PASS configurations=4 normal={4 * args.repeats} traced={4 * len(FATAL) * args.fatal_repeats} "
          f"cases={reference['case_count']} lrb_regression=PASS; independent audit still required")


def validate_results(result, reference):
    configure_lrb_fatal_contract()
    require(result.get("status") == "PASS", "result status")
    require([c["key"] for c in result["configurations"]] == [f"{a}_O{o}" for a, _, o in L.CONFIGS], "configurations")
    require(result["repeats"] >= 1 and result["fatal_repeats"] >= 1, "repetition counts")
    checks = set()
    for row in result["configurations"]:
        require(row["status"] == "PASS", "configuration status")
        require(len(row["normal"]) == result["repeats"], "normal repetitions")
        for run in row["normal"]:
            require(run["reference_aggregate"] == reference["aggregate"], "run bound to this reference")
            summary = L.checked(run, lambda r: validate_normal(r, reference["cases_text"]))
            require(summary["cases"] == reference["case_count"], "case count")
            checks.add(summary["checks"])
        require(sorted(r["mode"] for r in row["traced"]) == sorted(FATAL * result["fatal_repeats"]), "traced inventory")
        for run in row["traced"]:
            L.checked(run, L.validate_traced)
    require(len(checks) == 1, "identical positive check count across configurations")
    require(result["shm_snapshot"]["foreign_new"] == [], "unattributed new xenia_memory objects")
    lrb = result.get("lrb_regression") or {}
    require(lrb.get("returncode") == 0 and "LRB_GATE PASS configurations=4" in lrb.get("stdout", ""),
            "LRB regression recorded as PASS")
    return checks.pop()


# ------------------------------------------------------------------ evidence and audit

def package_evidence(out, path, failure):
    out = out.resolve()
    entries = {}
    results = out / "results.json"
    if results.exists():
        entries["results.json"] = results.read_bytes()
        data = read_json(entries["results.json"])
        for row in data.get("configurations", []):
            build = out / row["key"]
            objects = sorted((build / "CMakeFiles/lge_generated.dir").rglob("*.o")) if build.is_dir() else []
            gen = objects[0] if len(objects) == 1 else build / "missing-generated-object"
            try:
                paths = artifact_paths(build, row["key"], gen)
            except GateError:
                paths = {}
            for name, src in paths.items():
                if src.exists():
                    entries[name] = src.read_bytes()
            if failure:
                for run in row.get("normal", []):
                    cases = Path(run.get("cases_file", ""))
                    if run.get("divergence") and cases.is_file():
                        entries[f"divergent/{cases.name}"] = cases.read_bytes()
        lrb = out / "lrb_regression/results.json"
        if lrb.exists():
            entries["lrb_regression/results.json"] = lrb.read_bytes()
    for name in ("SOURCE_MANIFEST.json", "IMPLEMENTATION_ID.json"):
        if (ROOT / name).exists():
            entries[name] = (ROOT / name).read_bytes()
    console = out / "console.log"
    if console.exists():
        entries["console.log"] = console.read_bytes()
    if failure:
        own = out / "ownership"
        for p in sorted(own.glob("*.json")) if own.is_dir() else []:
            entries["ownership/" + p.name] = p.read_bytes()
        entries["FAILURE.txt"] = b"INCOMPLETE/FAILED native LGE evidence; not a PASS claim.\n"
    require(entries, "nothing to package")
    entries["EVIDENCE_MANIFEST.json"] = (json.dumps({n: sha(b) for n, b in sorted(entries.items())}, indent=2)
                                         + "\n").encode()
    digest = L.write_zip(path, entries)
    print(f"LGE_EVIDENCE {'FAILURE' if failure else 'PASS'} entries={len(entries)} sha256={digest} path={path} "
          "(PRIVATE: contains compiled game code; return only to private/work/linux_guest_entry/)")


def audit(archive, implementation, private_dir):
    configure_lrb_fatal_contract()
    _, reference = private_identity(private_dir)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) and z.testzip() is None, "archive integrity")
        data = {n: z.read(n) for n in names}
    require("FAILURE.txt" not in data, "failure bundle is not PASS evidence")
    require(not any(n.endswith((".cpp", ".h")) for n in data), "no source or generated code in evidence")
    manifest = read_json(data["EVIDENCE_MANIFEST.json"])
    require(set(manifest) == set(data) - {"EVIDENCE_MANIFEST.json"}, "evidence inventory")
    require(all(sha(data[n]) == h for n, h in manifest.items()), "evidence digest mismatch")
    identity = read_json(data["IMPLEMENTATION_ID.json"])
    require(identity["commit"] == implementation, "implementation commit mismatch")
    source = read_json(data["SOURCE_MANIFEST.json"])
    require(sorted(source) == source_files(), "transferred source inventory")
    for name, digest in source.items():
        blob = git("show", f"{implementation}:{name}").replace(b"\r\n", b"\n")
        require(sha(blob) == digest, "transferred source differs from Git: " + name)
    result = read_json(data["results.json"])
    require(result["identity"] == identity and result["source_manifest"] == source, "result source identity")
    require(result["sdk_identity"]["sdk"] == L.SDK_PIN and result["sdk_identity"]["simde"] == L.SIMDE_PIN, "SDK pins")
    for name, digest in result["sdk_identity"]["sources_sha256_lf"].items():
        blob = subprocess.run(["git", "-C", str(ROOT / "external/rexglue-sdk"), "show", f"{L.SDK_PIN}:{name}"],
                              capture_output=True, check=True).stdout.replace(b"\r\n", b"\n")
        require(sha(blob) == digest, "SDK source identity differs from pin: " + name)
    pid = result["private_identity"]
    require(pid["generated_manifest_sha256"] == sha((private_dir / "GENERATED_MANIFEST.json").read_bytes()),
            "native run used this private extract")
    require(pid["reference_aggregate"] == reference["aggregate"] and pid["reference_cases_sha256"] == reference["cases_sha256"],
            "native run compared against this Windows reference")
    checks = validate_results(result, reference)
    functions = {f["name"] for f in selection()["functions"]}
    for row in result["configurations"]:
        for name, digest in row["artifacts"].items():
            require(name in data and sha(data[name]) == digest, "artifact digest: " + name)
        require(row["executable_sha256"] == row["artifacts"][f"native/{row['key']}/lge_tests.elf"], "ELF identity")
        nm_text = data[f"native/{row['key']}/generated.nm.txt"].decode()
        check_aliases(nm_text, functions)
        refs = body_references(data[f"native/{row['key']}/generated.objdump.txt"].decode(), functions)
        derived = check_body_references(refs, functions, set(nm_symbols(nm_text)))
        require(derived == row["body_references"], "body references re-derived")
        check_helper_aliases(readelf_symbols(data[f"native/{row['key']}/final.readelf.txt"].decode()), derived)
        require(row["portable_define"] == row["key"].startswith("g++"), "DEFINE_REX_FUNC variant recorded")
        native_cases = parse_cases(data[f"native/{row['key']}/cases.txt"])
        exercised = compare_cases(parse_cases(reference["cases_text"].encode()), native_cases, functions)
        require(exercised == set(reference["functions_exercised"]), "every entry function exercised")
    require("lrb_regression/results.json" in data, "LRB regression results archived")
    lrb = read_json(data["lrb_regression/results.json"])
    require(lrb.get("status") == "PASS" and lrb["identity"] == identity, "LRB regression from the same package")
    print(f"LGE_AUDIT PASS cases={reference['case_count']} positive_checks={checks} configurations=4 "
          f"entries={len(data)}; manual final-ELF/handler/generated-object review still required")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("extract"); x.add_argument("--generated", type=Path, default=DEFAULT_GENERATED)
    x.add_argument("--out", type=Path, default=PRIVATE / "private_generated")
    w = sub.add_parser("windows"); w.add_argument("--private", type=Path, default=PRIVATE / "private_generated")
    w.add_argument("--prefix", type=Path, default=DEFAULT_WIN_PREFIX); w.add_argument("--repeats", type=int, default=5)
    w.add_argument("--work", type=Path, default=PRIVATE / "windows")
    p = sub.add_parser("private-zip"); p.add_argument("--private", type=Path, default=PRIVATE / "private_generated")
    p.add_argument("--zip", type=Path, default=PRIVATE / "lge-private-generated.zip")
    s = sub.add_parser("source"); s.add_argument("--zip", type=Path, default=PRIVATE / "lge-cachyos-source.zip")
    r = sub.add_parser("run")
    r.add_argument("--sdk", type=Path, required=True); r.add_argument("--prefix", type=Path, required=True)
    r.add_argument("--private", type=Path, required=True); r.add_argument("--out", type=Path, required=True)
    r.add_argument("--repeats", type=int, default=20); r.add_argument("--fatal-repeats", type=int, default=5)
    r.add_argument("--lrb-repeats", type=int, default=5)
    e = sub.add_parser("evidence"); e.add_argument("--out", type=Path, required=True)
    e.add_argument("--zip", type=Path, required=True); e.add_argument("--failure", action="store_true")
    a = sub.add_parser("audit"); a.add_argument("--archive", type=Path, required=True)
    a.add_argument("--implementation", required=True)
    a.add_argument("--private", type=Path, default=PRIVATE / "private_generated")
    args = ap.parse_args()
    if args.cmd == "extract":
        extract(args.generated.resolve(), args.out.resolve())
    elif args.cmd == "windows":
        require(args.repeats >= 1, "positive repetition count")
        windows_reference(args.private.resolve(), args.prefix.resolve(), args.repeats, args.work.resolve())
    elif args.cmd == "private-zip":
        private_zip(args.private.resolve(), args.zip.resolve())
    elif args.cmd == "source":
        package_source(args.zip.resolve())
    elif args.cmd == "run":
        require(args.repeats >= 1 and args.fatal_repeats >= 1 and args.lrb_repeats >= 1, "positive repetition counts")
        run_native(args)
    elif args.cmd == "evidence":
        package_evidence(args.out, args.zip, args.failure)
    else:
        audit(args.archive, args.implementation, args.private.resolve())


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print(f"LGE_GATE FAIL: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:  # Unexpected runner fault: keep the traceback, still a FAIL.
        traceback.print_exc()
        print(f"LGE_GATE FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)

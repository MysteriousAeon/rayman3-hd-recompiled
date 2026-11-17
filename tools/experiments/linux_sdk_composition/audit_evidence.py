"""Read-only audit of transferred 6f81aa7 records; never execute logged commands.

Checks archive integrity, committed source identity and exact recorded matrices.
Machine-code text still requires manual control-flow review. Original executables,
objects and SDK libraries are absent: recorded binary digests are not rehashed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[3]
CHECKPOINT = "6f81aa7"
SDK = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
SIMDE = "71fd833d9666141edcd1d3c109a80e228303d8d7"
PREFIX = "private/work/linux_sdk_composition/"
SUITES = {"lifecycle", "lifecycle_sanitizers", "native", "ordinary", "prior_native",
          "prior_fault", "prior_sanitizers", "prior_record_sanitizers", "prior_emitter"}
FOLDERS = ("portable_guest_eh", "linux_guest_fault", "linux_guest_integration", "linux_sdk_composition")
SDK_FILES = {"include/rex/" + p for p in (
    "system/xmemory.h", "system/mmio_handler.h", "exception_handler.h", "memory/utils.h",
    "thread/mutex.h", "ppc/context.h", "platform/fpscr.h", "ppc/func.h", "types.h", "platform.h", "assert.h")}
SDK_FILES.update("src/" + p for p in ("core/exception_handler_posix.cpp", "core/seh_posix.cpp",
    "system/mmio_handler.cpp", "system/xmemory.cpp", "core/memory_posix.cpp", "core/exception_handler_win.cpp", "core/memory_win.cpp"))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return data.replace(b"\r\n", b"\n")


def dump_header(text, executable):
    # Manual objdump used a relative path; the runner logged the absolute path.
    # Normalize only that one file-format header, never instruction/symbol text.
    lines = text.splitlines(keepends=True)
    require(len(lines) > 2 and lines[0] == "\n", "objdump header framing")
    name, rest = lines[1].split(":     file format ", 1)
    require(name.endswith(executable) and rest == "elf64-x86-64\n", "objdump header target/architecture")
    lines[1] = executable + ":     file format " + rest
    return "".join(lines)


def json_bytes(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def git(repo, *args, data=None):
    return subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
                          input=data, capture_output=True, timeout=60, check=True).stdout


def blob_hashes(repo, revision, names):
    """One cat-file process per repository, without filesystem/check-out writes."""
    names = sorted(set(names))
    requests = "".join(f"{revision}:{name}\n" for name in names).encode()
    raw = git(repo, "cat-file", "--batch", data=requests)
    offset, result = 0, {}
    for name in names:
        end = raw.index(b"\n", offset)
        header = raw[offset:end].split()
        require(len(header) == 3 and header[1] == b"blob", f"missing Git blob: {name}")
        size = int(header[2]); offset = end + 1
        result[name] = digest(canonical(raw[offset:offset + size]))
        offset += size
        require(raw[offset:offset + 1] == b"\n", "invalid cat-file framing")
        offset += 1
    require(offset == len(raw), "unexpected Git output")
    return result


def hashes(mapping, label):
    require(mapping and isinstance(mapping, dict), f"missing hashes: {label}")
    require(all(isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h)
                for h in mapping.values()), f"invalid digest: {label}")


def recorded_source_sets(suite, data):
    if suite in ("native", "ordinary"):
        return dict(data["sources_sha256_lf"])
    if suite.startswith("lifecycle"):
        return {"tools/experiments/linux_sdk_composition/" + p: h
                for p, h in data["sources_sha256"].items()}
    if suite == "prior_emitter":
        return {"tools/experiments/portable_guest_eh/" + p: h
                for p, h in data["source_sha256"].items()}
    if suite in ("prior_fault", "prior_record_sanitizers"):
        result = {"tools/experiments/linux_guest_fault/" + p: h for p, h in data["sources"].items()}
        result.update({"tools/experiments/portable_guest_eh/" + p: h
                       for p, h in data.get("emitter_sources", {}).items()})
        return result
    return dict(data["sources"])


def runtime_spec(suite):
    if suite == "lifecycle":
        success = {m: (0, f"LSC_LIFECYCLE PASS mode={m} checks={n}") for m, n in
                   (("ordinary", 5), ("normal", 35), ("conflicts", 6), ("replaced", 7))}
        return 20, {("lifecycle", m): v for m, v in success.items()} | {
            ("lifecycle", m): (-11, "") for m in
            ("host-null", "host-outside", "unarmed", "wrong-site", "reentrant", "terminal")}
    if suite == "lifecycle_sanitizers":
        return 2, {("lifecycle", "ordinary"): (0, "LSC_LIFECYCLE PASS mode=ordinary checks=5")}
    if suite in ("native", "ordinary"):
        result = {("sdk_composition", "normal"): (0, "SDK_COMPOSITION PASS checks=" +
                  ("293" if suite == "native" else "32") + " mode=normal")}
        if suite == "native":
            result.update({("sdk_composition", m): (-11, "")
                           for m in ("callback-failure", "unhandled", "repair-failure")})
        return 20, result
    if suite in ("prior_native", "prior_sanitizers"):
        result = {("bridge_tests", ""): (0, "BRIDGE_TESTS PASS checks=73")}
        if suite == "prior_native":
            result[("native_bridge", "")] = (0, "NATIVE_BRIDGE PASS checks=97")
        return (20 if suite == "prior_native" else 2), result
    result = {("record", ""): (0, "RECORD_CONTRACT PASS checks=16335")}
    if suite == "prior_fault":
        result.update({("fault_fixture", "normal"): (0, "LGF_FIXTURE PASS mode=normal classification=synthetic recovery=checked-leaf"),
                       ("fault_fixture", "prior-handler"): (0, "LGF_FIXTURE PASS mode=prior-handler result=refused"),
                       ("context_fixture", ""): (0, "LGF_CONTEXT PASS")})
        result.update({("fault_fixture", m): (-11, "") for m in
                       ("host-null", "host-outside", "wrong-site", "unarmed", "reentrant")})
        result[("fault_fixture", "unsupported-bus")] = (-7, "")
    return (20 if suite == "prior_fault" else 2), result


def flags(tokens, opt, sanitized):
    require(not any(t in ("-w", "-ffast-math", "-fno-exceptions") or
                    t.startswith(("-Wno-", "-fno-sanitize=", "-fsanitize-recover="))
                    for t in tokens), "suppression or unsupported compiler flags")
    require(all(t in tokens for t in ("-Wall", "-Wextra", "-Werror")), "missing strict warnings")
    opts = [t for t in tokens if re.fullmatch(r"-O[0123gs]", t)]
    require(opts and opts[-1] == "-" + opt, "effective optimization mismatch")
    if sanitized:
        require("-fsanitize=address,undefined" in tokens and "-fno-sanitize-recover=all" in tokens,
                "missing sanitizer/non-recovery flags")


def exact_source_names(suite, sources):
    def folder(name):
        return {n for n in sources if n.startswith("tools/experiments/" + name + "/")}
    if suite in ("native", "ordinary"):
        return {n for n in sources if n.startswith("tools/")}
    if suite.startswith("lifecycle"):
        return {"tools/experiments/linux_sdk_composition/" + n for n in
                ("transport.h", "transport.c", "access.S", "lifecycle.c", "run_lifecycle.py")}
    if suite == "prior_emitter":
        return {"tools/experiments/portable_guest_eh/" + n for n in
                ("ppc_adapter.h", "adapter_tests.cpp", "exception_core.h", "emitter_fixture.cpp", "bridge.cpp", "bridge.h")}
    if suite in ("prior_fault", "prior_record_sanitizers"):
        return folder("linux_guest_fault") | ({n for n in folder("portable_guest_eh")
            if PurePosixPath(n).suffix in (".cpp", ".h", ".py")} if suite == "prior_fault" else set())
    return {n for name in FOLDERS[:3] for n in folder(name) if PurePosixPath(n).name != "CMakeLists.txt"}


def emitter(data):
    expected = {(c, o) for c in ("clang++", "g++") for o in ("O0", "O2", "san")}
    seen, records = set(), 0
    for row in data["configurations"]:
        compiler = PurePosixPath(row["compiler"]).name; opt = row["configuration"]
        key = compiler, opt
        require(key in expected and key not in seen, "emitter configuration mismatch"); seen.add(key)
        require(("22.1.8" if compiler == "clang++" else "16.2.1") in row["version"], "emitter compiler version")
        require(len(row["commands"]) == 3, "emitter build inventory")
        for cmd in row["commands"]:
            flags(cmd, "O1" if opt == "san" else opt, opt == "san")
            require(cmd[0] == row["compiler"], "emitter compiler changed")
        counts = Counter()
        for run in row["runs"]:
            test = run["test"]; iteration = run["iteration"]
            require(iteration in (0, 1) and not run.get("stderr"), "emitter iteration/stderr")
            counts[test, iteration] += 1
            if test == "adapter_tests":
                require(run["stdout"] == "PPC_ADAPTER PASS checks=676", "adapter marker")
            elif test == "emitter_fixture":
                require(run["stdout"] == "EMITTER_FIXTURE PASS checks=70\nTRANSPORT_LAYOUT token_alignment=8 token_size=56 checkpoint_alignment=64", "emitter marker/layout")
            else:
                require(test in ("noexcept_barrier", "swallowed_transfer_reproducer") and
                        run["exit"] == (86 if test == "noexcept_barrier" else 87) and
                        not run.get("stdout"), "emitter expected barrier exit")
        require(counts == Counter({(t, i): 1 for t in ("adapter_tests", "emitter_fixture", "noexcept_barrier",
                "swallowed_transfer_reproducer") for i in (0, 1)}), "emitter run matrix")
        records += sum(counts.values())
    require(seen == expected, "missing emitter configuration")
    return {"configurations": 6, "recorded_runs": records, "repeats": 2}


def audit(archive, sdk):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) == 51, "ZIP inventory/duplicates")
        require(all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts
                    and ":" not in n and "\\" not in n for n in names), "unsafe ZIP path")
        require(z.testzip() is None, "ZIP CRC corruption")
        expected = {"SOURCE_MANIFEST.json", "EVIDENCE_SHA256.json"} | {PREFIX + s + "/results.json" for s in SUITES}
        expected.update(PREFIX + f"native/{c}_{o}/" + n for c in ("clang++", "g++") for o in ("O0", "O2")
                        for n in ("access.objdump.txt", "transport.objdump.txt", "final.objdump.txt", "final.readelf.txt", "final.sha256", "elf.txt"))
        expected.update(PREFIX + f"lifecycle/{c}_{o}/" + n for c in ("clang", "gcc") for o in ("O0", "O2")
                        for n in ("transport.objdump.txt", "transport.readelf.txt", "lifecycle.objdump.txt", "lifecycle.readelf.txt"))
        require(set(names) == expected, "unexpected/missing ZIP artifact")
        payload = {n: z.read(n) for n in names}
    manifest = json_bytes(payload["EVIDENCE_SHA256.json"])
    require(set(manifest) == set(names) - {"EVIDENCE_SHA256.json"}, "evidence manifest inventory")
    hashes(manifest, "evidence")
    require(all(digest(payload[n]) == h for n, h in manifest.items()), "evidence hash mismatch")
    sources = json_bytes(payload["SOURCE_MANIFEST.json"]); hashes(sources, "source manifest")
    require(len(sources) == 49, "source manifest count")
    require(all(n.startswith(("tools/experiments/", "reports/")) and "\n" not in n
                and ".." not in PurePosixPath(n).parts for n in sources), "invalid source path")
    committed = blob_hashes(ROOT, CHECKPOINT, sources)
    require(committed == sources, "source manifest differs from implementation checkpoint")
    tree = git(ROOT, "ls-tree", "-r", "--name-only", CHECKPOINT, "--", "tools/experiments").decode().splitlines()
    expected_sources = {p for p in tree if any(p.startswith("tools/experiments/" + f + "/") for f in FOLDERS)}
    expected_sources.update("reports/" + n for n in ("PORTABLE_GUEST_EXCEPTIONS_2026-11.md",
        "PORTABLE_GUEST_EMITTER_2026-11.md", "LINUX_GUEST_FAULT_2026-11.md", "LINUX_GUEST_INTEGRATION_2026-11.md", "LINUX_SDK_COMPOSITION_2026-11.md"))
    require(set(sources) == expected_sources, "source manifest exact inventory")
    results = {n.split("/")[-2]: json_bytes(data) for n, data in payload.items()
               if n.endswith("/results.json")}
    require(set(results) == SUITES, "result JSON inventory")
    current = results["native"]
    require(current["sdk_commit"] == SDK and current["simde_commit"] == SIMDE, "SDK/SIMDe pins")
    simde_names = {n for n in git(sdk / "thirdparty/simde", "ls-tree", "-r", "--name-only", SIMDE, "--", "simde").decode().splitlines() if n.endswith(".h")}
    require(set(current["sdk_sources_sha256_lf"]) == SDK_FILES and set(current["simde_headers_sha256_lf"]) == simde_names and len(simde_names) == 469,
            "SDK source/header inventory")
    sdk_hashes = blob_hashes(sdk, SDK, current["sdk_sources_sha256_lf"])
    simde_hashes = blob_hashes(sdk / "thirdparty/simde", SIMDE, current["simde_headers_sha256_lf"])
    require(sdk_hashes == current["sdk_sources_sha256_lf"] and
            simde_hashes == current["simde_headers_sha256_lf"], "SDK/SIMDe content mismatch")
    hashes(current["installed_libraries_sha256"], "installed libraries")
    require(len(current["installed_libraries_sha256"]) == 20, "installed library inventory")
    summary, total_commands = {}, 0
    runtime_names = {"lifecycle", "sdk_composition", "record", "fault_fixture", "context_fixture", "bridge_tests", "native_bridge"}
    for suite, data in sorted(results.items()):
        require(data["machine"].lower() == "x86_64" and data["platform"].startswith("Linux"), "non-Linux evidence")
        recorded = recorded_source_sets(suite, data); hashes(recorded, suite)
        require(set(recorded) == exact_source_names(suite, sources), f"{suite}: required source inventory")
        require(all(n in committed and committed[n] == h for n, h in recorded.items()), f"{suite}: source drift")
        for entry in data.get("commands", []):
            require(not entry["stderr"] and entry["returncode"] == entry["expected"] == 0,
                    f"{suite}: setup command failed")
            total_commands += 1
        if "sdk" in data:
            info = data["sdk"]
            require(info["commit"] == SDK and info["simde_commit"] == SIMDE, "prior SDK pins")
            expected_headers = {"include/rex/" + n for n in ("ppc/context.h", "platform/fpscr.h", "ppc/func.h", "types.h", "assert.h", "platform.h")}
            require(set(info["sdk_header_sha256"]) == expected_headers and all(sdk_hashes.get(n) == h
                    for n, h in info["sdk_header_sha256"].items()), "prior SDK header mismatch")
        if suite == "ordinary":
            for field in ("sdk_commit", "simde_commit", "sdk_sources_sha256_lf", "simde_headers_sha256_lf", "installed_libraries_sha256", "sources_sha256_lf"):
                require(data[field] == current[field], "ordinary/native installation/source mismatch")
        if suite == "prior_emitter":
            summary[suite] = emitter(data); continue
        require(data["status"] == "PASS", f"{suite}: matrix status")
        expected_scopes = {
            "lifecycle": ("scope", "native lifecycle and controlled exact read/write"),
            "lifecycle_sanitizers": ("scope", "ordinary rejection only; no signal ownership or fault recovery"),
            "native": ("scope", "native deferred components"), "ordinary": ("scope", "ordinary components"),
            "prior_native": ("scope", "bridge plus native leaf"), "prior_sanitizers": ("scope", "ordinary bridge"),
            "prior_fault": ("sanitizer_scope", "none"), "prior_record_sanitizers": ("sanitizer_scope", "record model only")}
        field, value = expected_scopes[suite]
        require(data[field] == value, "scope differs from tested fixture")
        if "sanitizers" in data:
            expected_san = ("address,undefined" if suite in ("lifecycle_sanitizers", "prior_sanitizers") else
                            "none; SDK Install signal ownership conflicts with ASan" if suite in ("native", "ordinary") else "none")
            require(data["sanitizers"] == expected_san, "sanitizer scope mismatch")
        if "portable_only" in data:
            require(data["portable_only"] == (suite == "prior_record_sanitizers"), "fault sanitizer/native scope")
        repeats, spec = runtime_spec(suite)
        compilers = ("clang", "gcc") if suite.startswith("lifecycle") else ("clang++", "g++")
        expected_keys = {(c, o) for c in compilers for o in ("O0", "O2")}; seen = set()
        totals = Counter()
        sanitized = suite in ("lifecycle_sanitizers", "prior_sanitizers", "prior_record_sanitizers")
        for row in data["configurations"]:
            compiler = PurePosixPath(row["compiler"]).name; opt = row["optimization"]
            require((compiler, opt) in expected_keys and (compiler, opt) not in seen, "duplicate/unexpected configuration")
            seen.add((compiler, opt)); require(row["status"] == "PASS", "configuration failure")
            require(("22.1.8" if compiler.startswith("clang") else "16.2.1") in row["version"], "compiler version mismatch")
            row_spec = dict(spec)
            if row.get("benchmarks"):
                require(suite in ("native", "lifecycle") and opt == "O2" and
                        len(row["benchmarks"]) == repeats, "benchmark scope/count")
                row_spec[("sdk_composition" if suite == "native" else "lifecycle", "benchmark")] = (0, None)
            counts = Counter(); builds = 0
            build_inputs = Counter()
            benchmark_outputs = []
            versions = [e for e in data.get("commands", []) + row["commands"]
                        if e["command"] == [row["compiler"], "--version"]]
            require(len(versions) == 1 and versions[0]["stdout"] == row["version"], "compiler identity/version record")
            for entry in row["commands"]:
                cmd = entry["command"]; exe = PurePosixPath(cmd[0]).name
                require(not entry["stderr"], f"{suite}: command stderr")
                expected_exit = 0
                if exe in runtime_names:
                    require(len(cmd) <= 2, "unexpected runtime arguments")
                    key = exe, (cmd[1] if len(cmd) == 2 else "")
                    require(key in row_spec, f"unexpected runtime mode: {key}")
                    expected_exit, marker = row_spec[key]
                    if marker is None:
                        pattern = (r"SDK_COMPONENT_BENCH ns_per_operation direct_mmio=([0-9]+\.[0-9]+) n=100000 "
                            r"watch_enable_dispatch_repair=([0-9]+\.[0-9]+) n=1000\nSDK_COMPOSITION PASS checks=205294 mode=benchmark") if suite == "native" else (
                            r"LSC_BENCH ns_per_operation lifecycle_pair=([0-9]+\.[0-9]+) n=1000 stack_pair=([0-9]+\.[0-9]+) n=100 "
                            r"normal_checked_read=([0-9]+\.[0-9]+) n=10000 capture_return=([0-9]+\.[0-9]+) n=1000\nLSC_LIFECYCLE PASS mode=benchmark checks=12116")
                        match = re.fullmatch(pattern, entry["stdout"].strip())
                        require(match and all(float(v) > 0 for v in match.groups()), "benchmark measurements/marker")
                        benchmark_outputs.append(entry["stdout"])
                    else:
                        require(entry.get("stdout", "").strip() == marker, f"{suite}: runtime marker")
                    counts[key] += 1
                elif exe in ("clang", "gcc", "clang++", "g++") and cmd[1:] != ["--version"]:
                    require(cmd[0] == row["compiler"], "unexpected compilation driver")
                    inputs = [PurePosixPath(t).name for t in cmd if str(t).endswith((".c", ".cpp", ".S"))]
                    require(len(inputs) <= 1, "unexpected build source count")
                    build_inputs[inputs[0] if inputs else ":link"] += 1
                    if suite.startswith("lifecycle"):
                        require("-DLSC_TEST" in cmd, "missing lifecycle test instrumentation")
                    if any(str(t).endswith((".c", ".cpp")) for t in cmd):
                        flags(cmd, opt, sanitized); builds += 1
                        if suite.startswith("lifecycle"):
                            require("-DLSC_TEST" in cmd and "-pthread" in cmd, "missing lifecycle test instrumentation")
                elif exe == "cmake" and cmd[1] == "--build":
                    lines = [line for line in entry["stdout"].splitlines() if " -c " in line]
                    require(len(lines) == (3 if suite == "native" else 1), "CMake compile inventory")
                    names = {line.split(" -c ")[-1].split("/")[-1] for line in lines}
                    require(names == ({"sdk_composition.cpp", "transport.c", "access.S"} if suite == "native" else {"sdk_composition.cpp"}), "CMake compilation inputs")
                    for line in lines:
                        flags(line.split(), opt, False)
                        driver = line.split()[1]
                        require(PurePosixPath(driver).name in (("clang", "clang++") if compiler.startswith("clang") else ("gcc", "g++")), "CMake compiler family")
                        require(("-DLSC_ORDINARY_ONLY" in line) == (suite == "ordinary"), "ordinary/native compile definition")
                    builds += len(lines)
                require(entry["returncode"] == expected_exit and entry.get("expected", expected_exit) == expected_exit,
                        f"{suite}: expected/actual exit mismatch")
                if "output_file" in entry:
                    name = entry["output_file"][entry["output_file"].index(PREFIX):]
                    require(name in payload and digest(payload[name]) == entry["output_sha256"], "dump hash association")
                total_commands += 1
            require(counts == Counter({key: repeats for key in row_spec}), f"{suite}: exact runtime matrix")
            require(benchmark_outputs == row.get("benchmarks", []), "benchmark record association")
            require(builds > 0, "missing recorded compilation")
            if suite not in ("native", "ordinary"):
                expected_builds = {"lifecycle": ("transport.c", "access.S", "lifecycle.c"),
                    "lifecycle_sanitizers": ("transport.c", "access.S", "lifecycle.c"),
                    "prior_native": ("bridge_tests.cpp", "transport.c", "access.S", "native_bridge.cpp"),
                    "prior_sanitizers": ("bridge_tests.cpp",), "prior_record_sanitizers": ("record_tests.cpp",),
                    "prior_fault": ("record_tests.cpp", "transport.c", "access.S", "fault_fixture.cpp", "context_fixture.c", "context_state.S", ":link")}
                require(build_inputs == Counter(expected_builds[suite]), "recorded build input inventory")
            totals.update({"runtime_runs": sum(counts.values()), "signal_terminations": sum(n for k, n in counts.items() if row_spec[k][0] < 0),
                           "benchmark_runs": len(benchmark_outputs)})
            if suite not in ("prior_fault", "prior_record_sanitizers"):
                require("executable_sha256" in row, "missing executable digest")
            if "executable_sha256" in row:
                value = row["executable_sha256"]
                hashes(value if isinstance(value, dict) else {"executable": value}, "executables")
            if suite.startswith("lifecycle"):
                require("transport_object_sha256" in row, "missing transport object digest")
                hashes({"transport": row["transport_object_sha256"]}, "transport object")
            if suite == "native":
                folder = PREFIX + f"native/{compiler}_{opt}/"
                require(payload[folder + "final.sha256"].decode().split()[0] == row["executable_sha256"], "standalone ELF digest mismatch")
                require(payload[folder + "elf.txt"] == payload[folder + "final.readelf.txt"], "ELF dump copies differ")
                for suffix in ("transport.objdump.txt", "access.objdump.txt", "final.objdump.txt", "final.readelf.txt"):
                    require(folder + suffix in payload, "missing native machine-code artifact")
                for tool, filename in (("objdump", "final.objdump.txt"), ("readelf", "elf.txt")):
                    logged = [e["stdout"] for e in row["commands"] if PurePosixPath(e["command"][0]).name == tool]
                    require(len(logged) == 1, "missing/extra logged final dump")
                    expected_text = payload[folder + filename].decode()
                    require((dump_header(logged[0], folder + "sdk_composition") == dump_header(expected_text, folder + "sdk_composition"))
                            if tool == "objdump" else logged[0] == expected_text, "logged/final dump mismatch")
        require(seen == expected_keys, "missing configuration")
        summary[suite] = {"configurations": 4, "repeats": repeats, **totals}
    return {"status": "PASS", "scope": "supplied records/source/integrity audit; manual machine-code review separate",
            "milestone_acceptance": "Not determined by this tool; SIGSEGV alone does not prove terminal branch intent",
            "implementation": git(ROOT, "rev-parse", CHECKPOINT).decode().strip(),
            "zip_sha256": digest(archive.read_bytes()), "zip_entries": 51, "evidence_hashes": 50,
            "source_manifest_files": 49, "sdk_files": 18, "simde_headers": 469,
            "installed_library_digests": 20, "recorded_commands": total_commands, "suites": summary,
            "limits": "Original ELF/object/library bytes absent; binary hashes not independently recomputed; text does not cryptographically bind to absent binaries; fatal-mode branch provenance requires separate acceptance review"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--sdk", type=Path, default=ROOT / "external/rexglue-sdk")
    args = parser.parse_args()
    print(json.dumps(audit(args.archive.resolve(), args.sdk.resolve()), indent=2))


if __name__ == "__main__":
    main()

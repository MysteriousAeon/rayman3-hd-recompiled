"""Read-only audit of supplied ac5dde9 evidence; never execute logged commands.

This checks records against Git objects, not against the current working tree.
Object text checks supplement (and do not replace) manual control-flow review.
It does not authenticate the originating machine or reconstruct linked binaries.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[3]
CHECKPOINT = "ac5dde99eff05566fe02a9e6e178f964d27f1d11"
SDK = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
SIMDE = "71fd833d9666141edcd1d3c109a80e228303d8d7"
HEADERS = {"include/rex/" + n for n in (
    "ppc/context.h", "platform/fpscr.h", "ppc/func.h", "types.h", "assert.h", "platform.h")}


def require(ok, detail):
    if not ok:
        raise ValueError(detail)


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", "-c", "core.fsmonitor=false", *args], cwd=cwd, timeout=30)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return data.replace(b"\r\n", b"\n")


def source_set(folder):
    prefix = "tools/experiments/" + folder + "/"
    names = git("ls-tree", "-r", "--name-only", CHECKPOINT, "--", prefix).decode().splitlines()
    return {n.removeprefix(prefix): sha(canonical(git("show", CHECKPOINT + ":" + n))) for n in names}


def flags(command, instrumented=False):
    require(not any(x in ("-w", "-fno-exceptions", "-ffast-math", "-fno-rounding-math") or
                    x.startswith(("-Wno-", "-flto", "-fno-sanitize=", "-fsanitize-recover="))
                    for x in command), "warning/sanitizer suppression or unexpected LTO")
    if instrumented:
        require("-fsanitize=address,undefined" in command and
                "-fno-sanitize-recover=all" in command, "missing strict sanitizer flags")


def matrix(data, instrumented):
    require(data["status"] == "PASS" and data["portable_only"] == instrumented and
            data["sanitizer_scope"] == ("record model only" if instrumented else "none"), "matrix scope/status")
    seen = set()
    totals = Counter()
    for config in data["configurations"]:
        key = (Path(config["compiler"]).name, config["optimization"])
        require(key not in seen and config["status"] == "PASS", "duplicate/failed configuration")
        seen.add(key)
        counts = Counter()
        builds = 0
        versions = 0
        for entry in config["commands"]:
            cmd = entry["command"]
            exe, args = Path(cmd[0]).name, cmd[1:]
            require(not entry["stderr"], "unexpected stderr")
            if exe in ("clang++", "g++"):
                require(cmd[0] == config["compiler"], "compiler changed within configuration")
                expected = 0
                flags(cmd)
                if args == ["--version"]:
                    versions += 1
                    require(entry["stdout"].strip() == config["version"].strip(), "version mismatch")
                else:
                    builds += 1
                    require("-o" in args and not entry["stdout"], "unexpected build record")
                    if any(str(x).endswith((".cpp", ".c")) for x in args):
                        require(all(x in args for x in ("-Wall", "-Wextra", "-Werror", "-" + key[1])), "compile flags")
                        flags(cmd, instrumented)
            else:
                mode = args[0] if args else ""
                expected = -7 if mode == "unsupported-bus" else -11 if mode in (
                    "host-null", "host-outside", "wrong-site", "unarmed", "reentrant") else 0
                markers = {("record", ""): "RECORD_CONTRACT PASS checks=16335",
                           ("context_fixture", ""): "LGF_CONTEXT PASS",
                           ("fault_fixture", "normal"): "LGF_FIXTURE PASS mode=normal classification=synthetic recovery=checked-leaf",
                           ("fault_fixture", "prior-handler"): "LGF_FIXTURE PASS mode=prior-handler result=refused"}
                require(len(args) <= 1, "unexpected runtime arguments")
                if expected:
                    require(exe == "fault_fixture" and not entry["stdout"], "unexpected crash output/target")
                else:
                    require(entry["stdout"].strip() == markers.get((exe, mode)), "success marker mismatch")
                counts[(exe, mode)] += 1
            require(entry["expected"] == expected and entry["returncode"] == expected, "incorrect expected/actual exit")
        expected_counts = Counter({("record", ""): 2 if instrumented else 20})
        if not instrumented:
            expected_counts.update({("context_fixture", ""): 20})
            expected_counts.update({("fault_fixture", m): 20 for m in (
                "normal", "prior-handler", "host-null", "host-outside", "wrong-site", "unarmed", "reentrant", "unsupported-bus")})
        require(counts == expected_counts and versions == 1 and builds == (1 if instrumented else 7), "missing/extra matrix rows")
        totals.update(counts)
    require(seen == {(c, o) for c in ("clang++", "g++") for o in ("O0", "O2")}, "matrix combinations")
    return sum(totals.values())


def emitter(data):
    seen = set()
    runs = 0
    for config in data["configurations"]:
        key = (Path(config["compiler"]).name, config["configuration"])
        require(key not in seen, "duplicate emitter configuration")
        seen.add(key)
        require(len(config["commands"]) == 3, "emitter build count")
        for cmd in config["commands"]:
            require(cmd[0] == config["compiler"] and all(f in cmd for f in (
                "-Wall", "-Wextra", "-Werror", "-fexceptions", "-fno-fast-math",
                "-frounding-math", "-O1" if key[1] == "san" else "-" + key[1])), "emitter flags")
            flags(cmd, key[1] == "san")
        rows = set()
        for row in config["runs"]:
            identity = (row["test"], row["iteration"])
            require(identity not in rows and not row.get("stderr", ""), "duplicate/emitter stderr")
            rows.add(identity)
            if row["test"] == "adapter_tests":
                require(row["stdout"] == "PPC_ADAPTER PASS checks=676", "adapter checks")
            elif row["test"] == "emitter_fixture":
                require(row["stdout"] == "EMITTER_FIXTURE PASS checks=70\nTRANSPORT_LAYOUT token_alignment=8 token_size=56 checkpoint_alignment=64", "emitter checks/layout")
            else:
                require(row["exit"] == {"noexcept_barrier": 86, "swallowed_transfer_reproducer": 87}.get(row["test"]), "barrier exit")
            runs += 1
        require(rows == {(t, i) for t in ("adapter_tests", "emitter_fixture", "noexcept_barrier", "swallowed_transfer_reproducer") for i in range(2)}, "emitter runs")
    require(seen == {(c, o) for c in ("clang++", "g++") for o in ("O0", "O2", "san")}, "emitter combinations")
    return runs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path)
    args = ap.parse_args()
    required = ("native-results.json", "reocrd-sanitizer-results.json", "emitter-sanitizer-results.json")
    docs = {name: json.loads((args.results / name).read_text(encoding="utf-8")) for name in required}
    native, record, existing = (docs[n] for n in required)
    versions = {}
    for data in docs.values():
        for config in data["configurations"]:
            compiler = Path(config["compiler"]).name
            version = config["version"].strip()
            require(version and versions.setdefault(compiler, version) == version,
                    "inconsistent compiler version across evidence")
    source = source_set("linux_guest_fault")
    portable = source_set("portable_guest_eh")
    require(native["sources"] == source == record["sources"], "fault source hashes")
    require(native["emitter_sources"] == {k: v for k, v in portable.items() if Path(k).suffix in (".cpp", ".h", ".py")}, "emitter closure hashes")
    used = {"ppc_adapter.h", "adapter_tests.cpp", "exception_core.h", "emitter_fixture.cpp", "bridge.cpp", "bridge.h"}
    require(existing["source_sha256"] == {k: portable[k] for k in used}, "emitter regression hashes")
    for data in docs.values():
        require(data["machine"] == "x86_64" and data["platform"] == "Linux-7.2.2-1-cachyos-x86_64-with-glibc2.44", "native platform")
        if "sdk" in data:
            sdk = data["sdk"]
            require(sdk["commit"] == SDK and sdk["simde_commit"] == SIMDE and set(sdk["sdk_header_sha256"]) == HEADERS, "SDK pins/closure")
            for name, value in sdk["sdk_header_sha256"].items():
                require(sha(canonical(git("show", SDK + ":" + name, cwd=ROOT / "external/rexglue-sdk"))) == value, "SDK header " + name)
    counts = {"native_executions": matrix(native, False), "record_sanitizer_executions": matrix(record, True), "emitter_executions": emitter(existing)}
    archive = args.results / "disassembly-review.zip"
    with zipfile.ZipFile(archive) as z:
        names = {c + "_" + o + "_" + t + ".txt" for c in ("clang++", "g++") for o in ("O0", "O2") for t in ("transport", "access")}
        require(set(z.namelist()) == names and len(z.namelist()) == 8 and z.testzip() is None, "object dump inventory/CRC")
        for name in sorted(names):
            text = z.read(name).decode("utf-8")
            require("__tls_get_addr" not in text, "dynamic TLS resolver")
            if name.endswith("access.txt"):
                code = b"".join(bytes.fromhex(m[1]) for m in re.finditer(r"^\s*[0-9a-f]+:\s+((?:[0-9a-f]{2}[ \t]+)+)", text, re.M))
                require(code.hex() == "8b07890631c0c3b801000000c38b07890631c0c3", "access leaf bytes")
            else:
                require("R_X86_64_TPOFF32" in text and "<fault_handler>:" in text, "TLS/handler evidence")
    artifacts = {p.name: sha(p.read_bytes()) for p in [*(args.results / n for n in required), archive]}
    print(json.dumps({"audit": "PASS", "checkpoint": CHECKPOINT, "configurations": 14, **counts,
                      "compiler_versions": {k: v.splitlines()[0] for k, v in versions.items()},
                      "artifact_sha256": artifacts, "object_control_flow": "manual review required; text inventory is not final-binary provenance"}, indent=2))


if __name__ == "__main__":
    main()

"""Linux Write-Watch Restart (LWR): Windows reference, transfer, native gate, evidence, audit.

Subcommands:
  windows      (Windows) build Clang O0/O2 ordinary harnesses against the existing Windows SDK
               install (generated code from the PRIVATE LGE extract), run them repeatedly and write
               the PRIVATE lwr_windows_reference.json.
  private-zip  (Windows) package the PRIVATE reference (no generated code) into the private ZIP.
  source       (any) write the source-only CachyOS ZIP from committed Git bytes (no generated code).
  run          (Linux x86-64 only) build Clang/GCC O0/O2, run the LWR matrix, then the LRB and LGE
               regressions rebuilt from the same package.
  evidence     (Linux) package results, own ELF/object bytes and dumps.  The ZIP is PRIVATE: it
               contains compiled game code and must only be returned to private/work/.
  audit        (Windows/any, read-only) validate a returned evidence ZIP against Git and the reference.

Never builds, patches or installs the SDK; never launches the game; never commits, publishes
or uploads generated code; removes only /dev/shm objects proven to belong to its own child.
Input to the guest never enters here: the children run synthetic fixtures and generated code only.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import selectors
import shutil
import signal
import struct
import subprocess
import sys
import time
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REL = "tools/experiments/linux_write_watch_restart/"
sys.path.insert(0, str(HERE.parent / "linux_guest_entry"))
import lge_gate as G  # noqa: E402  (audited LGE runner primitives, unchanged)

L = G.L
GateError, require, sha, lf, read_json = L.GateError, L.require, L.sha, L.lf, L.read_json
OWN_FILES = ["CMakeLists.txt", "README.md", "lwr_decode.h", "lwr_restart.h", "lwr_restart.c", "lwr_test_leaf.S",
             "lwr_probe.c", "lwr_tests.cpp", "lwr_gate.py", "test_lwr_gate.py",
             # Our own objects' disassembly from native failure 1 (no generated code).
             "fixtures/native_failure1_clang_O2_restart.objdump.txt",
             "fixtures/native_failure1_clang_O2_owner.objdump.txt"]
PRIVATE = ROOT / "private/work/linux_write_watch_restart"
LGE_PRIVATE = G.PRIVATE / "private_generated"
LGE_PRIVATE_ZIP = G.PRIVATE / "lge-private-generated.zip"
REFERENCE_NAME = "lwr_windows_reference.json"
CASE_COUNT = 8

EXPECTED_RESTART = [
    "LWR_RESTART_V1|id=restart/single-store|watched=4,5,9,12|claimed=4|invalidations=4:1|cleanup=5,9,12|restart=complete|session=closed",
    "LWR_RESTART_V1|id=restart/memset-page|watched=4,5,9,12|claimed=4|invalidations=4:1|cleanup=5,9,12|restart=complete|session=closed",
    "LWR_RESTART_V1|id=restart/memset-two-pages|watched=4,5,9,12|claimed=4,5|invalidations=4:1,5:1|cleanup=9,12|restart=complete|session=closed",
    "LWR_RESTART_V1|id=restart/memset-edges|watched=4,5,9,12|claimed=9|invalidations=9:1|cleanup=4,5,12|restart=complete|session=closed",
    "LWR_RESTART_V1|id=restart/neighbour-only|watched=4,5,9,12|claimed=-|invalidations=-|cleanup=4,5,9,12|restart=complete|session=closed",
    "LWR_RESTART_V1|id=restart/memcpy|watched=4,5,9,12|claimed=12|invalidations=12:1|cleanup=4,5,9|restart=complete|session=closed",
    "LWR_RESTART_V1|id=restart/forward-copy|watched=4,5,9,12|claimed=9|invalidations=9:1|cleanup=4,5,12|restart=complete|session=closed",
    "LWR_RESTART_V1|id=restart/erase|watched=4,5,9,12|claimed=5,12|invalidations=5:1,12:1|cleanup=4,9|restart=complete|session=closed"]
CASE_CLAIMS = [1, 1, 2, 1, 0, 1, 1, 2]
TOTAL_CLAIMS = 9
GENERATED_FUNCTIONS = {"__imp__sub_820E7440", "__imp__sub_820EB7D8", "__imp__sub_820E78A0", "__imp__sub_820EB350",
                       "__imp__sub_820E7328", "__imp__sub_820F7978", "__imp____savegprlr_29", "__imp____restgprlr_29"}
FATAL_LWR = ["lwr-unregistered", "lwr-unauthorized", "lwr-consumed", "lwr-wrong-function", "lwr-host-store", "lwr-read",
             "lwr-cross-page", "lwr-wide", "lwr-signal-origin", "lwr-foreign-thread", "lwr-after-release"]
TRACED_POSITIVE = "lwr-traced-positive"
PROBE_NEGATIVE = ["unregistered", "unauthorized", "after-close", "signal-origin", "consumed", "wrong-site",
                  "host-store", "read", "cross-page", "wide", "foreign-thread"]
PROBE_POSITIVE_RUNS = 3
REGRESSION_RUNS = 2
SEGV_ACCERR, SI_TKILL = 2, -6

# Audited LRB/LGE closures (SHA-256) that the rebuilt regressions and the LWR generated object must reproduce.
CLOSURE = {
    "lge": {
        "clang++_O0": {"lge_tests.elf": "2be4045c9813cb873495079dec8b1625c9d4186e232e060f8aced8def334a056",
                       "lge_generated.o": "49b361b866d91e9725b0df4b322664ea6064d12c84ba48235bd3f3ca12b6db86",
                       "lrb_owner.o": "df66c8ea115b680d230bedc426823ffa32158c685ae1cecb8c56999b1cf585be"},
        "clang++_O2": {"lge_tests.elf": "d7642a2aae29bca46133dda07c4d2ff51f383ee7b6bbe808cf3b531aaa2eb63f",
                       "lge_generated.o": "c0aa512d023e31982513ec9e8507df086754a36bf38e270dd8b01fae7c8a95cd",
                       "lrb_owner.o": "5125dbb0e6d3831e61c8277b74ff45e93296c6f47747485317785257e352cccb"},
        "g++_O0": {"lge_tests.elf": "e53c1e236a14530119a8d9b84742ab16941a6c257abc561f73d6b1ecbbe721d4",
                   "lge_generated.o": "188ebae46c4eb2af20d08cfee7f702b4f2dd4df0bdd5d285122fde565ee5828c",
                   "lrb_owner.o": "39c9e898eae40e63c9815662fa82391d05323aa5d13ef311951b99d3dc81043f"},
        "g++_O2": {"lge_tests.elf": "7f85ece13946a41b7bb33ab1c49eca2732775702a95078faa759df2225b6ed02",
                   "lge_generated.o": "aa2ad175e211fb4ccd38ca31bad7bf94d41fd1910a895bd16d683a6897650c1e",
                   "lrb_owner.o": "d1227548674d14e500890740d2f324af7e3579003db3b2bffc44c9f21e7cb409"},
    },
    "lrb": {
        "clang++_O0": {"lrb_tests.elf": "fde6fed7e1510f7a4ae9f0134ab7586372180f65d6642a815c224e2c4ecede96"},
        "clang++_O2": {"lrb_tests.elf": "44f8efa9652c7c44a164a6fc5da8598aed2df6d7cfdceffda2ca9dde720291e2"},
        "g++_O0": {"lrb_tests.elf": "4a27869b93b6f918f2438a681cc7afb79c9146c8c124deaa8f287b2ac82aba76"},
        "g++_O2": {"lrb_tests.elf": "4e9342d21b113f83e5c2664889cbc4ff191564324002b5ae619c1d60176f705c"},
    },
}
for _key, _row in CLOSURE["lrb"].items():
    _row["lrb_owner.o"] = CLOSURE["lge"][_key]["lrb_owner.o"]
CONFIG_KEYS = [f"{a}_O{o}" for a, _, o in L.CONFIGS]

NATIVE_NAMES = ["lwr_tests.elf", "lwr_probe.elf", "lge_generated.o", "lwr_restart.o", "lrb_owner.o", "lwr_test_leaf.o",
                "lrb_access.o", "final.objdump.txt", "restart.objdump.txt", "owner.objdump.txt",
                "generated.objdump.txt", "final.readelf.txt", "generated.nm.txt"]

NATIVE_PASS = re.compile(r"LWR PASS cases=(\d+) claims=(\d+) checks=(\d+) aggregate=([0-9a-f]{64}) native=([01])\n")
PROBE_PASS = re.compile(r"LWR_PROBE PASS claims=2 checks=(\d+)\n")
PROBE_BEGIN = re.compile(r"LWR_PROBE begin mode=([a-z-]+) address=0x([0-9a-f]+)\n")
WITNESS = re.compile(r"LWR_GATE_V1 token=([0-9a-f]{32}) mode=([a-z-]+) phase=([a-z]+) claims=(\d+) "
                     r"invalidations=(\d+) address=0x([0-9a-f]+)\n")
CLAIM_LINE = re.compile(r"LWR_CLAIM_V1\|id=([^|]+)\|n=(\d+)\|page=(\d+)\|fn=(\w+)\|offset=0x([0-9a-f]+)\|"
                        r"width=([1248])\|length=(\d+)\|address=0x([0-9a-f]+)\|effective=0x([0-9a-f]+)\|"
                        r"error=([67])\|before=([0-9a-f]+)")


def restart_pages(line):
    value = re.search(r"\|claimed=([0-9,-]+)\|", line).group(1)
    return [] if value == "-" else [int(p) for p in value.split(",")]


def restart_id(line):
    return re.match(r"LWR_RESTART_V1\|id=([^|]+)\|", line).group(1)


EXPECTED_PAGES = {restart_id(line): restart_pages(line) for line in EXPECTED_RESTART}


def register_fatal():
    """Register the LWR fatal modes with the audited LRB ownership validator (unlink-after-map policy)."""
    L.FATAL = tuple(dict.fromkeys(L.FATAL + tuple(FATAL_LWR)))


def source_files():
    return sorted({REL + f for f in OWN_FILES} | set(G.source_files()))


# ------------------------------------------------------------------ canonical records

def parse_case(line):
    require(line.startswith("LWR_CASE_V1|"), "case record prefix")
    parts = line[len("LWR_CASE_V1|"):].split("|")
    require(len(parts) == len(G.CASE_FIELDS), "case record field count")
    fields = {}
    for part, name in zip(parts, G.CASE_FIELDS):
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


aggregate = G.aggregate


def compare_cases(reference, candidate):
    """First differing field between two parsed case lists (a matching total alone is never accepted)."""
    require(len(reference) == len(candidate), "case count differs from reference")
    for ref, got in zip(reference, candidate):
        for name in G.CASE_FIELDS:
            require(ref[name] == got[name], f"case {ref['id']}: field {name} differs from the Windows reference")


def validate_restart(text):
    expected = "".join(f"{line}|digest={sha(line.encode())}\n" for line in EXPECTED_RESTART)
    require(text == expected, "restart file differs from the expected restart records")


def parse_claim(line):
    match = CLAIM_LINE.fullmatch(line)
    require(match is not None, "claim record format")
    cid, n, page, fn, offset, width, length, address, effective, error, before = match.groups()
    claim = {"id": cid, "n": int(n), "page": int(page), "fn": fn, "offset": int(offset, 16), "width": int(width),
             "length": int(length), "address": int(address, 16), "effective": int(effective, 16),
             "error": int(error), "before": before}
    require(fn in GENERATED_FUNCTIONS, "claim function outside the generated set: " + fn)
    require(0 <= claim["address"] - claim["effective"] < claim["width"], "claim kernel address outside the store")
    require(claim["effective"] >> 12 == claim["page"] and
            (claim["effective"] + claim["width"] - 1) >> 12 == claim["page"], "claim store not inside its page")
    require(len(before) == 2 * claim["width"], "claim before-bytes length")
    return claim


def validate_claims(text):
    require(text.endswith("\n") and "\r" not in text, "claims file framing")
    claims = [parse_claim(line) for line in text[:-1].split("\n")]
    require(len(claims) == TOTAL_CLAIMS, "claims file line count")
    by_id = {}
    for claim in claims:
        require(claim["id"] in EXPECTED_PAGES, "claim for an unknown case: " + claim["id"])
        by_id.setdefault(claim["id"], []).append(claim)
    require([i for i in EXPECTED_PAGES if EXPECTED_PAGES[i]] == list(by_id), "claim case order/inventory")
    for cid, rows in by_id.items():
        pages = [c["page"] for c in rows]
        require(len(pages) == len(set(pages)), "one claim per page: " + cid)
        require(sorted(pages) == sorted(EXPECTED_PAGES[cid]), "claimed page set: " + cid)
        require([c["n"] for c in rows] == list(range(len(rows))), "claim index order: " + cid)
    return claims


def check_reference(reference):
    require(reference.get("format") == "LWR_REFERENCE_V1", "reference format")
    require(reference.get("case_count") == CASE_COUNT, "reference case count")
    data = reference["cases_text"].encode("ascii")
    cases = parse_cases(data)
    require(len(cases) == CASE_COUNT, "reference case lines")
    require(sha(data) == reference["cases_sha256"], "reference cases digest")
    require(aggregate(cases) == reference["aggregate"], "reference aggregate")
    require(isinstance(reference.get("checks"), int) and reference["checks"] > 0, "reference check count")
    return cases


def load_reference(path, private_dir):
    reference = read_json(Path(path).read_bytes())
    check_reference(reference)
    require(reference["generated_manifest_sha256"] == sha((private_dir / "GENERATED_MANIFEST.json").read_bytes()),
            "LWR reference built from this private extract")
    require(reference["lge_reference_sha256"] == sha((private_dir / "windows_reference.json").read_bytes()),
            "LWR reference built from this LGE reference")
    return reference


# --------------------------------------------------------------- run validators

def validate_normal(run, reference):
    require(not run.get("timeout") and run["returncode"] == 0 and run["stderr"] == "", "normal run exit/stderr")
    match = NATIVE_PASS.fullmatch(run["stdout"])
    require(match is not None and (match.group(1), match.group(2), match.group(5)) == (str(CASE_COUNT), str(TOTAL_CLAIMS), "1"),
            "normal run stdout contract")
    require(run["results_sha256"] == sha(reference["cases_text"].encode()),
            "case file differs from the Windows reference" + (": " + run["divergence"] if run.get("divergence") else ""))
    require(run["watched_sha256"] == run["results_sha256"], "watched case file differs from the results file")
    require(match.group(4) == reference["aggregate"], "aggregate differs from the Windows reference")
    validate_restart(run["restart_text"])
    validate_claims(run["claims_text"])
    L.validate_ownership(run, expect_residue=False)
    return {"checks": int(match.group(3)), "claims_sha256": sha(run["claims_text"].encode())}


def parse_witness(text, token=None, mode=None):
    """Parse the exact stderr witness bytes; any junk or partial line fails."""
    rows, offset = [], 0
    while offset < len(text):
        match = WITNESS.match(text, offset)
        require(match is not None, "unexpected/partial trace bytes")
        tok, name, phase, claims, invalidations, address = match.groups()
        require(token is None or tok == token, "witness token")
        require(mode is None or name == mode, "witness mode")
        rows.append({"phase": phase, "claims": int(claims), "invalidations": int(invalidations),
                     "address": int(address, 16)})
        offset = match.end()
    return rows


def positive_expectations():
    out, before = [], 0
    for k in CASE_CLAIMS:
        out.extend([(k, before)] * k)
        before += k
    return out


def check_stop_kind(stop, kind, pid, address=None):
    require(stop["signal"] == 11, "stop is not SIGSEGV")
    if kind == "ACCERR":
        require(stop["code"] == SEGV_ACCERR, "stop is not SEGV_ACCERR")
        if address is not None:
            require(stop["address"] == address, "kernel/witness fault address mismatch")
    else:
        require(stop["code"] == SI_TKILL and stop["sender_pid"] == pid, "terminal signal was not same-process SI_TKILL")


def stop_rows(stop, run):
    require(run["stderr"].startswith(stop["trace"]) and (stop["trace"] == "" or stop["trace"].endswith("\n")),
            "stop-time stderr is not a complete-line prefix of the final stderr")
    return parse_witness(stop["trace"], run.get("token"), run["mode"])


def validate_traced_positive(run, reference):
    require(run["status"] == "PASS" and run["mode"] == TRACED_POSITIVE, "failed traced record")
    require(run["returncode"] == 0 and not run.get("timeout"), "traced positive exit status")
    match = NATIVE_PASS.fullmatch(run["stdout"])
    require(match is not None and (match.group(1), match.group(2), match.group(5)) == (str(CASE_COUNT), str(TOTAL_CLAIMS), "1")
            and match.group(4) == reference["aggregate"], "traced positive stdout contract")
    rows = parse_witness(run["stderr"], run["token"], TRACED_POSITIVE)
    require(len(rows) == TOTAL_CLAIMS and all(r["phase"] == "claim" and r["invalidations"] == 0 and r["address"]
                                              for r in rows), "traced positive witness rows")
    stops, expected = run["signals"], positive_expectations()
    require(len(stops) == TOTAL_CLAIMS, "traced positive stop count")
    for i, (stop, (case_claims, before)) in enumerate(zip(stops, expected)):
        check_stop_kind(stop, "ACCERR", run["pid"], rows[i]["address"])
        require(rows[i]["claims"] == case_claims, f"witness {i} claims differ from its case claim count")
        require(len(stop_rows(stop, run)) == before, f"stop {i}: witness lines already written at the fault")
    L.validate_ownership(run, expect_residue=False)
    return len(rows)


def fatal_contract(mode, rows):
    """(expected witness rows, expected stops) for a traced fatal mode; stops are (kind, rows_at_stop)."""
    require(rows, "fatal witness rows")
    address = rows[0]["address"]
    if mode == "lwr-signal-origin":
        require(address == 0, "signal-origin witness address")
        return [("begin", 0, 0, 0)], [("TKILL", 1), ("TKILL", 1)]
    require(address != 0, "fatal witness address")
    if mode == "lwr-consumed":
        return ([("begin", 0, 0, address), ("claimed", 1, 0, address), ("rewatched", 1, 1, address)],
                [("ACCERR", 1), ("ACCERR", 3), ("TKILL", 3)])
    return [("begin", 0, 0, address)], [("ACCERR", 1), ("TKILL", 1)]


def validate_traced_fatal(run):
    mode = run["mode"]
    require(run["status"] == "PASS" and mode in FATAL_LWR, "failed traced record")
    require(run["returncode"] == -11 and run["stdout"] == "" and not run.get("timeout"),
            "not real SIGSEGV death or extra stdout")
    rows = parse_witness(run["stderr"], run["token"], mode)
    want_rows, want_stops = fatal_contract(mode, rows)
    require([(r["phase"], r["claims"], r["invalidations"], r["address"]) for r in rows] == want_rows,
            "witness phase/counter/address sequence")
    stops = run["signals"]
    require(len(stops) == len(want_stops), "signal sequence length")
    for stop, (kind, at_stop) in zip(stops, want_stops):
        check_stop_kind(stop, kind, run["pid"], rows[0]["address"])
        require(len(stop_rows(stop, run)) == at_stop, f"witness lines already written at the {kind} stop")
    require(stops[-1]["trace"] == run["stderr"], "trace changed after terminal delivery stop")
    L.validate_ownership(run, expect_residue=False)
    return len(stops)


def validate_probe_positive(run):
    require(not run.get("timeout") and run["returncode"] == 0 and run["stderr"] == "", "probe positive exit/stderr")
    match = PROBE_PASS.fullmatch(run["stdout"])
    require(match is not None, "probe positive stdout contract")
    return int(match.group(1))


def validate_probe_negative(run):
    mode = run["mode"]
    require(run["status"] == "PASS" and mode in PROBE_NEGATIVE, "failed probe record")
    require(run["returncode"] == -11 and run["stdout"] == "" and not run.get("timeout"),
            "probe did not die by SIGSEGV or wrote stdout")
    match = PROBE_BEGIN.fullmatch(run["stderr"])
    require(match is not None and match.group(1) == mode, "probe begin line")
    address = int(match.group(2), 16)
    # lwr_probe.c "consumed" admits one store (first stop, nothing on stderr yet) before it prints begin.
    plan = {"signal-origin": [("TKILL", True), ("TKILL", True)],
            "consumed": [("ACCERR", False), ("ACCERR", True), ("TKILL", True)]}.get(mode, [("ACCERR", True), ("TKILL", True)])
    stops = run["signals"]
    require(len(stops) == len(plan), "probe signal sequence length")
    for stop, (kind, begun) in zip(stops, plan):
        check_stop_kind(stop, kind, run["pid"], None if mode == "signal-origin" else address)
        require(stop["trace"] == (run["stderr"] if begun else ""), "probe begin line position at the stop")
    return address


# -------------------------------------------------------------- binary checks

OBJ_HEADER = re.compile(r"^[0-9a-f]+ <([^>]+)>:$")
OBJ_INSN = re.compile(r"^\s*([0-9a-f]+):\t([0-9a-f]{2}(?: [0-9a-f]{2})*) *(?:\t(.*))?$")
OBJ_RELOC = re.compile(r"([0-9a-f]+):\s+(R_X86_64_\w+)\s+(\S+)")
PREFIXES = {"lock", "rep", "repz", "repnz", "repe", "repne", "notrack", "bnd", "data16", "addr32", "cs", "ds", "es",
            "ss", "fs", "gs"}
TLS_RELOCS = {"R_X86_64_GOTTPOFF", "R_X86_64_TPOFF32", "R_X86_64_TPOFF64"}
# Forbidden anywhere in lwr_restart.o (built -fno-stack-protector, initial-exec TLS).
FORBIDDEN_SYMBOLS = re.compile(r"(?<![\w.])(__stack_chk_fail|__tls_get_addr)(?![\w])")
# Out-of-line memory primitives: allowed only in functions the signal entry cannot reach
# (e.g. Clang -O2 turns lwr_authorize's ordinary-code range copy loop into memcpy; native
# failure 1, c533325a…6d97). Enforced by check_signal_closure, not by an object-wide ban.
MEMORY_PRIMITIVES = re.compile(r"^(?:memcpy|memset|memmove|memcmp|bcopy|bzero)$")
SIGNAL_ENTRY = "handler"  # The static LRB SIGSEGV handler in lrb_owner.o.
# Exact external callees the audited LRB handler may reach on its fail-closed path.
SIGNAL_EXTERNALS = {"sigaction", "sigprocmask", "raise", "_Exit", "__stack_chk_fail"}
VECTOR_X87 = re.compile(r"%(?:[xyz]mm\d+|st(?:\(\d\))?|mm\d)(?!\w)")
BRANCH = re.compile(r"^(?:call|jmp|j[a-z]+|loop[a-z]*)$")
ADMIT = "lwr_restart_admit"


def parse_objdump(text):
    """Blocks of `objdump -drw[C]` as {label: [instruction dict]} (relocations attached to their instruction)."""
    funcs, current = {}, None
    for line in text.splitlines():
        header = OBJ_HEADER.match(line)
        if header:
            current = header.group(1)
            funcs.setdefault(current, [])
            continue
        if current is None:
            continue
        match = OBJ_INSN.match(line)
        if match:
            rest = (match.group(3) or "").split("\t")
            body = rest[0].split(" # ")[0].strip()
            relocs = [m.groups()[1:] for m in OBJ_RELOC.finditer("\t".join(rest[1:]))]
            if not body and funcs[current]:  # byte continuation line
                funcs[current][-1]["bytes"] += " " + match.group(2)
                continue
            funcs[current].append({"address": int(match.group(1), 16), "bytes": match.group(2), "text": body,
                                   "relocs": [list(r) for r in relocs]})
            continue
        reloc = OBJ_RELOC.fullmatch(line.strip())
        if reloc and funcs[current]:
            funcs[current][-1]["relocs"].append([reloc.group(2), reloc.group(3)])
    return funcs


def split_mnemonic(text):
    tokens = text.split()
    while tokens and (tokens[0] in PREFIXES or tokens[0].startswith("rex")):
        tokens.pop(0)
    return (tokens[0] if tokens else ""), " ".join(tokens[1:])


def check_restart_object(text):
    """Machine-code contract of the signal-context admission function in lwr_restart.o."""
    blocks = parse_objdump(text)
    require(ADMIT in blocks and blocks[ADMIT], ADMIT + " not found in the object disassembly")
    syscalls, relocs, branches = 0, [], 0
    for insn in blocks[ADMIT]:
        mnemonic, operands = split_mnemonic(insn["text"])
        require(not VECTOR_X87.search(insn["text"]) and not re.fullmatch(r"f[a-z0-9]+", mnemonic),
                f"{ADMIT} uses vector or x87 state: {insn['text']}")
        if mnemonic == "syscall":
            syscalls += 1
        if BRANCH.fullmatch(mnemonic):
            target = re.search(r"<([^>+]+)(?:\+0x[0-9a-f]+)?>$", operands)
            require(target is not None and target.group(1) == ADMIT and not insn["relocs"],
                    f"{ADMIT} branches outside itself: {insn['text']}")
            branches += 1
        for kind, symbol in insn["relocs"]:
            require(kind in TLS_RELOCS, f"{ADMIT} relocation {kind} {symbol} is not a TLS relocation")
            relocs.append([kind, symbol])
    require(syscalls == 1, f"{ADMIT} must contain exactly one syscall instruction, found {syscalls}")
    forbidden = FORBIDDEN_SYMBOLS.search(text)
    require(forbidden is None, "lwr_restart.o references " + (forbidden.group(1) if forbidden else ""))
    return {"instructions": len(blocks[ADMIT]), "syscalls": syscalls, "branches": branches, "relocations": relocs}


def call_edges(blocks):
    """{function: [callee or '*indirect']} from call/jmp instructions of parsed objdump blocks."""
    edges = {}
    for name, insns in blocks.items():
        out = edges.setdefault(name, [])
        for insn in insns:
            mnemonic, operands = split_mnemonic(insn["text"])
            # Every control transfer: call/callq, jmp/jmpq, conditional jumps (incl. into a
            # GCC `.cold` split block), jrcxz and loop*. Intra-function targets are dropped below.
            if not (mnemonic.startswith(("call", "j", "loop"))):
                continue
            branch_relocs = [s for _, s in insn["relocs"]]
            if branch_relocs:
                target = re.split(r"[-+]0x[0-9a-f]+$", branch_relocs[0])[0]
            elif operands.lstrip().startswith("*"):
                target = "*indirect"
            else:
                match = re.search(r"<([^>+]+)(?:\+0x[0-9a-f]+)?>$", operands)
                target = match.group(1) if match else "*unknown"
            if target != name:
                out.append(target)
    return edges


def check_signal_closure(owner_text, restart_text):
    """Every function reachable by calls from the LRB SIGSEGV handler, across lrb_owner.o and
    lwr_restart.o: no indirect call, external callees exactly within SIGNAL_EXTERNALS, the LWR
    admission function reached and itself call-free. Memory primitives may appear only outside
    that closure; each such reference is reported with its function as proof of separation."""
    edges = {}
    for text in (owner_text, restart_text):
        for name, out in call_edges(parse_objdump(text)).items():
            require(name not in edges, f"function {name} defined twice across the two objects")
            edges.setdefault(name, []).extend(out)
    require(SIGNAL_ENTRY in edges, "LRB signal handler not found in lrb_owner.o")
    reachable, externals, stack = set(), set(), [SIGNAL_ENTRY]
    while stack:
        name = stack.pop()
        if name in reachable:
            continue
        reachable.add(name)
        # A compiler-split cold part runs as part of its parent, whether or not a branch to it parsed.
        for part in edges:
            if part.startswith(name + ".") and part not in reachable:
                stack.append(part)
        for callee in edges.get(name, []):
            require(not callee.startswith("*"), f"signal-reachable {name} has an indirect or unresolved call")
            if callee in edges:
                stack.append(callee)
            else:
                externals.add(callee)
    require(ADMIT in reachable, f"{ADMIT} is not reachable from the signal handler")
    require(not edges[ADMIT], f"{ADMIT} calls {edges[ADMIT]}")
    require(externals <= SIGNAL_EXTERNALS,
            "signal-reachable external calls outside the audited set: " + ", ".join(sorted(externals - SIGNAL_EXTERNALS)))
    # A reachable memory primitive is already rejected above (it is not in SIGNAL_EXTERNALS);
    # what remains is the documented separation of the ordinary-code ones.
    unreachable_memory = sorted({(name, callee) for name, out in edges.items() for callee in out
                                 if MEMORY_PRIMITIVES.fullmatch(callee)})
    return {"reachable": sorted(reachable), "externals": sorted(externals),
            "unreachable_memory_calls": [list(x) for x in unreachable_memory]}


def check_owner_calls_admit(text):
    require(re.search(r"R_X86_64_\w+\s+" + ADMIT + r"(?:[-+]0x[0-9a-f]+)?\s*$", text, re.M) is not None,
            "lrb_owner.o has no relocation/call to " + ADMIT)
    return True


def check_final_admit(text):
    blocks = parse_objdump(text)
    require(ADMIT in blocks and blocks[ADMIT], "linked " + ADMIT + " not found")
    calls = [i["text"] for i in blocks[ADMIT] if split_mnemonic(i["text"])[0].startswith("call")]
    require(not calls, f"linked {ADMIT} contains call instructions: {calls[0] if calls else ''}")
    return len(blocks[ADMIT])


def check_bind_now(readelf_text):
    require(re.search(r"\(FLAGS_1\)\s+Flags:.*\bNOW\b", readelf_text) or re.search(r"\(FLAGS\).*\bBIND_NOW\b", readelf_text),
            "lwr_tests linked with BIND_NOW")
    return True


REG64 = {"rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp"} | {f"r{i}" for i in range(8, 16)}
REG32 = {"eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp"} | {f"r{i}d" for i in range(8, 16)}
REG16 = {"ax", "bx", "cx", "dx", "si", "di", "bp", "sp"} | {f"r{i}w" for i in range(8, 16)}
REG8 = {"al", "bl", "cl", "dl", "ah", "bh", "ch", "dh", "sil", "dil", "bpl", "spl"} | {f"r{i}b" for i in range(8, 16)}
SEGMENTS = ("%fs:", "%gs:", "%es:", "%ds:", "%ss:", "%cs:")


def register_width(operand):
    if not operand.startswith("%"):
        return None
    name = operand[1:]
    for width, names in ((8, REG64), (4, REG32), (2, REG16), (1, REG8)):
        if name in names:
            return width
    return None


def split_operands(text):
    out, depth, current = [], 0, ""
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            out.append(current)
            current = ""
        else:
            current += ch
    return out + [current] if current else out


def instruction_index(text):
    index = {}
    for line in text.splitlines():
        match = OBJ_INSN.match(line)
        if match and match.group(3):
            body = match.group(3).split("\t")[0].split(" # ")[0].strip()
            if body:
                index[int(match.group(1), 16)] = (match.group(2), body)
    return index


def check_claim_sites(claims, symbols, index):
    """Each claim must land exactly on a scalar mov store of the claimed width and length."""
    sites = []
    for claim in claims:
        symbol = symbols.get(claim["fn"])
        require(symbol is not None, "claim function symbol not in the final ELF: " + claim["fn"])
        address = symbol[0] + claim["offset"]
        found = index.get(address)
        require(found is not None, f"no instruction at {claim['fn']}+0x{claim['offset']:x} (0x{address:x})")
        raw, text = found
        mnemonic, operands = split_mnemonic(text)
        match = re.fullmatch(r"mov([bwlq]?)", mnemonic)
        require(match is not None, f"claim site {claim['fn']}+0x{claim['offset']:x} is not a mov: {text}")
        ops = split_operands(operands)
        require(len(ops) == 2, f"claim site operands: {text}")
        dest, src = ops[1], ops[0]
        require("(" in dest or dest.startswith(SEGMENTS) or not dest.startswith(("%", "$")),
                f"claim site destination is not memory: {text}")
        width = register_width(src)
        if width is None and src.startswith("$"):
            width = {"b": 1, "w": 2, "l": 4, "q": 8}.get(match.group(1))
        require(width == claim["width"], f"claim site width {width} != claimed {claim['width']}: {text}")
        require(len(raw.split()) == claim["length"], f"claim site length {len(raw.split())} != claimed {claim['length']}: {text}")
        sites.append({"id": claim["id"], "fn": claim["fn"], "offset": claim["offset"], "address": address,
                      "bytes": raw, "text": text})
    return sites


def check_closure(kind, key, name, actual, version):
    expected = CLOSURE[kind][key][name]
    require(actual == expected, f"{kind} {key} {name} differs from the audited closure: expected {expected} actual "
                                f"{actual} (compiler: {(version or '').splitlines()[0] if version else 'unknown'}); "
                                "toolchain drift is a blocker, not a pass")


# ----------------------------------------------------------------- result validators

def validate_regression(regression, lge_ref):
    require([r["key"] for r in regression["lrb"]] == CONFIG_KEYS and [r["key"] for r in regression["lge"]] == CONFIG_KEYS,
            "regression configurations")
    for row in regression["lrb"]:
        check_closure("lrb", row["key"], "lrb_tests.elf", row["executable_sha256"], row["cxx_version"])
        check_closure("lrb", row["key"], "lrb_owner.o", row["owner_sha256"], row["cxx_version"])
        require(len(row["normal"]) == REGRESSION_RUNS, "LRB regression repetitions")
        for run in row["normal"]:
            L.checked(run, L.validate_normal)
    for row in regression["lge"]:
        check_closure("lge", row["key"], "lge_tests.elf", row["executable_sha256"], row["cxx_version"])
        check_closure("lge", row["key"], "lge_generated.o", row["generated_sha256"], row["cxx_version"])
        check_closure("lge", row["key"], "lrb_owner.o", row["owner_sha256"], row["cxx_version"])
        require(len(row["normal"]) == REGRESSION_RUNS, "LGE regression repetitions")
        for run in row["normal"]:
            L.checked(run, lambda r: validate_lge_normal(r, lge_ref))


def validate_lge_normal(run, lge_ref):
    require(not run.get("timeout") and run["returncode"] == 0 and run["stderr"] == "", "LGE regression exit/stderr")
    match = G.PASS_LINE.fullmatch(run["stdout"])
    require(match is not None and match.group(4) == "1", "LGE regression stdout contract")
    require(run["cases_sha256"] == lge_ref["cases_sha256"], "LGE case file differs from the LGE Windows reference")
    require(match.group(3) == lge_ref["aggregate"] == run["reference_aggregate"], "LGE aggregate differs from the reference")
    L.validate_ownership(run, expect_residue=False)


def validate_results(result, reference):
    register_fatal()
    require(result.get("status") == "PASS", "result status")
    require([c["key"] for c in result["configurations"]] == CONFIG_KEYS, "configurations")
    n, t = result["repeats"], result["traced_repeats"]
    require(n >= 1 and t >= 1, "repetition counts")
    checks = set()
    for row in result["configurations"]:
        require(row["status"] == "PASS", "configuration status")
        check_closure("lge", row["key"], "lge_generated.o", row["artifacts"]["lge_generated.o"], row.get("cxx_version"))
        require(len(row["probe_positive"]) == PROBE_POSITIVE_RUNS, "probe positive repetitions")
        for run in row["probe_positive"]:
            L.checked(run, validate_probe_positive)
        require(sorted(r["mode"] for r in row["probe_negative"]) == sorted(PROBE_NEGATIVE), "probe negative inventory")
        for run in row["probe_negative"]:
            L.checked(run, validate_probe_negative)
        require(len(row["normal"]) == n, "normal repetitions")
        claims_hashes = set()
        for run in row["normal"]:
            summary = L.checked(run, lambda r: validate_normal(r, reference))
            checks.add(summary["checks"])
            claims_hashes.add(summary["claims_sha256"])
        require(len(claims_hashes) == 1, "claims file differs across runs of a configuration")
        require(len(row["claim_sites"]) == TOTAL_CLAIMS, "claim site count")
        require(len(row["traced_positive"]) == t, "traced positive repetitions")
        for run in row["traced_positive"]:
            L.checked(run, lambda r: validate_traced_positive(r, reference))
        require(sorted(r["mode"] for r in row["traced_fatal"]) == sorted(FATAL_LWR * t), "traced fatal inventory")
        for run in row["traced_fatal"]:
            L.checked(run, validate_traced_fatal)
        checks_rec = row["object_checks"]
        require(checks_rec["bind_now"] is True and checks_rec["owner_calls_admit"] is True
                and checks_rec["restart_admit"]["syscalls"] == 1, "recorded object checks")
    require(len(checks) == 1, "identical positive check count across configurations")
    require(result["shm_snapshot"]["foreign_new"] == [], "unattributed new xenia_memory objects")
    validate_regression(result["regression"], result["private_identity"]["lge_reference"])
    return checks.pop()


# ------------------------------------------------------------------ source transfer

def package_entries(head, names, head_blob, work_blob):
    entries = {}
    for name in names:
        blob = head_blob(name).replace(b"\r\n", b"\n")
        require(work_blob(name) == blob, "working file differs from HEAD: " + name)
        require(b"\nDEFINE_REX_FUNC(" not in blob, "generated code in the source package: " + name)
        entries[name] = blob
    manifest = {n: sha(b) for n, b in entries.items()}
    entries["SOURCE_MANIFEST.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    entries["IMPLEMENTATION_ID.json"] = (json.dumps({"commit": head, "sdk": L.SDK_PIN, "simde": L.SIMDE_PIN},
                                                    indent=2) + "\n").encode()
    return entries


def write_sidecar(path, digest):
    (path.parent / (path.name + ".sha256")).write_text(f"{digest}  {path.name}\n", encoding="utf-8", newline="\n")


def package_source(path):
    head = G.git("rev-parse", "HEAD").decode().strip()
    entries = package_entries(head, source_files(), lambda n: G.git("show", f"HEAD:{n}"), lambda n: lf(ROOT / n))
    digest = L.write_zip(path, entries)
    write_sidecar(path, digest)
    print(f"LWR_SOURCE PASS files={len(entries)} commit={head} size={path.stat().st_size} sha256={digest} path={path}")


def check_source_manifest(manifest, identity, hasher):
    require(all(hasher(p) == h for p, h in manifest.items()), "source transfer hash mismatch")
    require(sorted(manifest) == source_files(), "LWR source inventory")
    require(re.fullmatch(r"[0-9a-f]{40}", identity["commit"]) is not None, "commit identity")


def source_identity():
    manifest = read_json((ROOT / "SOURCE_MANIFEST.json").read_bytes())
    identity = read_json((ROOT / "IMPLEMENTATION_ID.json").read_bytes())
    check_source_manifest(manifest, identity, lambda p: sha(lf(ROOT / p)))
    return manifest, identity


def private_zip_entries(reference_bytes):
    entries = {"lwr_reference/" + REFERENCE_NAME: reference_bytes}
    require(b"\nDEFINE_REX_FUNC(" not in reference_bytes, "generated code in the LWR private ZIP")
    entries["PRIVATE_MANIFEST.json"] = (json.dumps({n: sha(b) for n, b in sorted(entries.items())}, indent=1)
                                        + "\n").encode()
    return entries


def private_zip(path):
    reference_bytes = (PRIVATE / REFERENCE_NAME).read_bytes()
    check_reference(read_json(reference_bytes))
    require(LGE_PRIVATE_ZIP.is_file(), "the LGE private ZIP (generated code) must already exist; it is reused unchanged")
    entries = private_zip_entries(reference_bytes)
    digest = L.write_zip(path, entries)
    write_sidecar(path, digest)
    print(f"LWR_PRIVATE PASS entries={len(entries)} size={path.stat().st_size} sha256={digest} path={path} "
          f"lge_private_zip_sha256={sha(LGE_PRIVATE_ZIP.read_bytes())}")


# ------------------------------------------------------------------ Windows reference

def windows_reference(private_dir, prefix, repeats, work):
    require(platform.system() == "Windows", "the reference harness runs on the Windows development host")
    _, lge_reference = G.private_identity(private_dir)
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
                   "-DLWR_OPT=" + opt, "-DLRB_ORDINARY_ONLY=ON", "-DLGE_GENERATED_DIR=" + str(private_dir)], log)
        G.build_step(["cmake", "--build", build, "--verbose"], log)
        exe = build / "lwr_tests.exe"
        row["executable_sha256"] = sha(exe.read_bytes())
        for i in range(repeats):
            cases_path, own = build / f"cases_{i}.txt", build / f"ownership_{i}.json"
            for p in (cases_path, own):
                if p.exists():
                    p.unlink()
            dll_path = str(prefix / "bin") + os.pathsep + os.environ.get("PATH", "")
            run = G.run_child([exe, "normal"], {"LWR_RESULTS_FILE": str(cases_path), "LRB_OWNERSHIP_FILE": str(own),
                                                "PATH": dll_path})
            row["runs"].append(run)
            require(run["returncode"] == 0 and run["stderr"] == "", f"Windows run failed: {L.describe({**run, 'mode': 'normal'})}")
            match = NATIVE_PASS.fullmatch(run["stdout"].replace("\r\n", "\n"))
            require(match is not None and (match.group(1), match.group(2), match.group(5)) == (str(CASE_COUNT), "0", "0"),
                    "Windows stdout contract")
            data = cases_path.read_bytes()
            cases = parse_cases(data)
            require(len(cases) == CASE_COUNT and aggregate(cases) == match.group(4), "Windows aggregate")
            run.update(cases=len(cases), checks=int(match.group(3)), aggregate=match.group(4), cases_sha256=sha(data))
            require(text is None or data.decode() == text, "Windows runs are not bit-identical across runs/O-levels")
            text = data.decode()
    checks = {r["checks"] for row in configs for r in row["runs"]}
    require(len(checks) == 1, "identical check count across Windows runs")
    cases = parse_cases(text.encode())
    reference = {"format": "LWR_REFERENCE_V1",
                 "generated_manifest_sha256": sha((private_dir / "GENERATED_MANIFEST.json").read_bytes()),
                 "lge_reference_sha256": sha((private_dir / "windows_reference.json").read_bytes()),
                 "platform": platform.platform(), "repeats": repeats, "configurations": configs,
                 "checks": checks.pop(), "case_count": len(cases), "aggregate": aggregate(cases),
                 "cases_sha256": sha(text.encode()), "cases_text": text}
    check_reference(reference)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / REFERENCE_NAME).write_text(json.dumps(reference, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"LWR_WINDOWS PASS configurations=2 runs={2 * repeats} cases={len(cases)} aggregate={reference['aggregate']}")


# ------------------------------------------------------------------ tracer

def traced(argv, env, timeout=60, ownership=None, result=None):
    """PTRACE_TRACEME supervision recording every stop; contract validation happens afterwards.

    Any non-SIGSEGV stop or ptrace refusal fails; there is no untraced fallback and no
    security setting is changed.  `ownership` is the LRB ownership record path, if any."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.ptrace.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]
    libc.ptrace.restype = ctypes.c_long

    def ptrace(request, pid=0, addr=None, data=None):
        value = libc.ptrace(request, pid, addr, data)
        if value == -1:
            raise OSError(ctypes.get_errno(), "ptrace denied/failed; no security change or untraced fallback")
        return value

    def trace_me():
        try:
            ptrace(0)
        except OSError as error:
            os.write(2, f"LWR_PTRACE_BLOCKED errno={error.errno}\n".encode())
            os._exit(125)

    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    result = result if result is not None else {}
    result.update(argv=[str(a) for a in argv], signals=[], status="INCOMPLETE")
    if ownership is not None:
        result["shm_before"] = L.shm_names()
    process, selector, exited = None, None, False
    deadline = time.monotonic() + timeout

    def drain():
        for key in list(selector.get_map().values()):
            while True:
                try:
                    data = os.read(key.fileobj.fileno(), 4096)
                except BlockingIOError:
                    break
                if not data:
                    selector.unregister(key.fileobj)
                    break
                buffers[key.data].extend(data)
                require(len(buffers[key.data]) <= 16384, "unexpected output volume")

    def wait():
        while time.monotonic() < deadline:
            drain()
            pid, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
            if pid:
                return status
            selector.select(min(0.01, max(0, deadline - time.monotonic())))
        raise TimeoutError("traced LWR child timed out")

    try:
        process = subprocess.Popen([str(a) for a in argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   preexec_fn=trace_me, env=env)
        result["pid"] = process.pid
        selector = selectors.DefaultSelector()
        for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        status = wait(); drain()
        if os.WIFEXITED(status) or os.WIFSIGNALED(status):
            exited = True
            result["returncode"] = os.waitstatus_to_exitcode(status)
        require(os.WIFSTOPPED(status) and os.WSTOPSIG(status) == 5 and status >> 16 == 0,
                "missing initial exec SIGTRAP (tracing unsupported?)")
        ptrace(0x4200, process.pid, data=ctypes.c_void_p(0x100000))  # SETOPTIONS EXITKILL
        ptrace(7, process.pid)  # CONT
        while True:
            status = wait(); drain()
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                exited = True
                process.returncode = os.waitstatus_to_exitcode(status)
                drain()
                result.update(returncode=process.returncode, stdout=buffers["stdout"].decode(errors="replace"),
                              stderr=buffers["stderr"].decode(errors="replace"), status="PASS")
                if ownership is not None:
                    L.inspect_residue(ownership, result, remove=True)
                return result
            require(os.WIFSTOPPED(status) and status >> 16 == 0 and os.WSTOPSIG(status) == 11,
                    "unexpected ptrace stop/event")
            info = ctypes.create_string_buffer(128)
            ptrace(0x4202, process.pid, data=ctypes.cast(info, ctypes.c_void_p))  # GETSIGINFO
            sig, error, code = struct.unpack_from("<iii", info.raw)
            result["signals"].append({"signal": sig, "code": code, "errno": error,
                                      "address": struct.unpack_from("<Q", info.raw, 16)[0] if code in (1, 2) else 0,
                                      "sender_pid": struct.unpack_from("<i", info.raw, 16)[0] if code == SI_TKILL else 0,
                                      "trace": buffers["stderr"].decode(errors="replace")})
            ptrace(7, process.pid, data=ctypes.c_void_p(11))  # forward the exact SIGSEGV
    except BaseException as error:
        result.update(status="FAIL", error=str(error), stdout=buffers["stdout"].decode(errors="replace"),
                      stderr=buffers["stderr"].decode(errors="replace"))
        raise
    finally:
        if process is not None and not exited:
            try:
                os.kill(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            cleanup_deadline = time.monotonic() + 5
            while time.monotonic() < cleanup_deadline:
                try:
                    pid, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
                except ChildProcessError:
                    break
                if pid and (os.WIFEXITED(status) or os.WIFSIGNALED(status)):
                    result["cleanup_returncode"] = os.waitstatus_to_exitcode(status)
                    break
                if pid and os.WIFSTOPPED(status):
                    try:
                        ptrace(7, process.pid, data=ctypes.c_void_p(9))
                    except OSError:
                        pass
                time.sleep(0.01)
            else:
                result["cleanup_error"] = "child did not reap after SIGKILL"
            if ownership is not None and Path(ownership).exists() and "residue" not in result:
                try:
                    L.inspect_residue(ownership, result, remove=True)
                except Exception as error:  # Recorded, never masks the original failure.
                    result["residue_error"] = str(error)
        if selector is not None:
            selector.close()
        if process is not None:
            process.stdout.close(); process.stderr.close()


# ------------------------------------------------------------------ native gate

def lwr_files(out, tag):
    base = out / "cases"
    base.mkdir(parents=True, exist_ok=True)
    paths = {name: base / f"{tag}.{name}.txt" for name in ("results", "watched", "restart", "claims")}
    for p in paths.values():
        if p.exists():
            p.unlink()
    env = {"LWR_RESULTS_FILE": str(paths["results"]), "LWR_WATCHED_FILE": str(paths["watched"]),
           "LWR_RESTART_FILE": str(paths["restart"]), "LWR_CLAIMS_FILE": str(paths["claims"])}
    return paths, env


def read_lwr_files(paths):
    data = {n: (p.read_bytes() if p.exists() else b"") for n, p in paths.items()}
    return {"results_sha256": sha(data["results"]), "watched_sha256": sha(data["watched"]),
            "restart_text": data["restart"].decode("ascii", errors="replace"),
            "claims_text": data["claims"].decode("ascii", errors="replace"),
            "files": {n: str(p) for n, p in paths.items()}}, data


def run_normal(command, out, tag, reference):
    paths, env = lwr_files(out, tag)
    run = L.run_plain(command, "normal", out, tag, extra_env=env)
    facts, data = read_lwr_files(paths)
    run.update(facts)
    if data["results"] and data["results"] != reference["cases_text"].encode():
        try:
            compare_cases(parse_cases(reference["cases_text"].encode()), parse_cases(data["results"]))
            run["divergence"] = "case file bytes differ although every parsed field matches"
        except (GateError, UnicodeDecodeError) as error:
            run["divergence"] = str(error)
    return run


def run_simple(argv, timeout=60):
    p = subprocess.run([str(a) for a in argv], capture_output=True, timeout=timeout)
    return {"argv": [str(a) for a in argv], "returncode": p.returncode, "stdout": p.stdout.decode(errors="replace"),
            "stderr": p.stderr.decode(errors="replace")}


def traced_env(token=None, ownership=None, files=None):
    env = os.environ.copy()
    env.pop("LRB_SDK_LOG_CONSOLE", None)
    env.pop("LRB_GATE_TOKEN", None)
    if token:
        env["LRB_GATE_TOKEN"] = token
    if ownership:
        env["LRB_OWNERSHIP_FILE"] = str(ownership)
    env.update(files or {})
    return env


def find_one(root, name):
    found = sorted(root.rglob(name))
    require(len(found) == 1, f"expected exactly one {name} under {root}")
    return found[0]


def configure_and_build(source, build, cxx, cc, prefix, extra, log):
    G.build_step(["cmake", "-S", source, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                  "-DCMAKE_PREFIX_PATH=" + str(prefix), "-DCMAKE_CXX_COMPILER=" + cxx, "-DCMAKE_C_COMPILER=" + cc,
                  "-DCMAKE_ASM_COMPILER=" + cc, *extra], log)
    return G.build_step(["cmake", "--build", build, "--verbose"], log)


def native_config(out, key, cxx, cc, opt, prefix, private_dir, reference, args, row):
    log = row["commands"]
    build = out / "build" / key
    if build.exists():
        shutil.rmtree(build)
    row["cxx_version"] = L.command([cxx, "--version"], log)
    row["cc_version"] = L.command([cc, "--version"], log)
    configure_and_build(HERE, build, cxx, cc, prefix, ["-DLWR_OPT=" + opt, "-DLRB_ORDINARY_ONLY=OFF",
                                                       "-DLGE_GENERATED_DIR=" + str(private_dir)], log)
    exe, probe = build / "lwr_tests", build / "lwr_probe"
    exe_sha, probe_sha = sha(exe.read_bytes()), sha(probe.read_bytes())
    row["executable_sha256"], row["probe_sha256"] = exe_sha, probe_sha
    objects = build / "CMakeFiles/lwr_tests.dir"
    native = out / "native" / key
    native.mkdir(parents=True, exist_ok=True)
    sources = {"lwr_tests.elf": exe, "lwr_probe.elf": probe,
               "lge_generated.o": find_one(build / "CMakeFiles/lge_generated.dir", "*.o"),
               "lwr_restart.o": find_one(objects, "lwr_restart.c.o"), "lrb_owner.o": find_one(objects, "lrb_owner.c.o"),
               "lwr_test_leaf.o": find_one(objects, "lwr_test_leaf.S.o"),
               "lrb_access.o": find_one(objects, "lrb_access.S.o")}
    for name, src in sources.items():
        shutil.copyfile(src, native / name)
    for name, tool, flags, target in (
            ("final.objdump.txt", "objdump", ["-drwC"], native / "lwr_tests.elf"),
            ("restart.objdump.txt", "objdump", ["-drwC"], native / "lwr_restart.o"),
            ("owner.objdump.txt", "objdump", ["-drwC"], native / "lrb_owner.o"),
            ("generated.objdump.txt", "objdump", ["-drwC"], native / "lge_generated.o"),
            ("final.readelf.txt", "readelf", ["-a", "-W"], native / "lwr_tests.elf"),
            ("generated.nm.txt", "nm", ["--defined-only"], native / "lge_generated.o")):
        (native / name).write_text(L.command([tool, *flags, target], log), encoding="utf-8")
    row["artifacts"] = {n: sha((native / n).read_bytes()) for n in NATIVE_NAMES}
    require(row["artifacts"]["lwr_tests.elf"] == exe_sha, "executable changed during inspection")
    # Binary checks (the root audit re-derives them from the archived bytes).
    text = {n: (native / n).read_text(encoding="utf-8") for n in NATIVE_NAMES if n.endswith(".txt")}
    check_closure("lge", key, "lge_generated.o", row["artifacts"]["lge_generated.o"], row["cxx_version"])
    row["object_checks"] = {"bind_now": check_bind_now(text["final.readelf.txt"]),
                            "restart_admit": check_restart_object(text["restart.objdump.txt"]),
                            "owner_calls_admit": check_owner_calls_admit(text["owner.objdump.txt"]),
                            "signal_closure": check_signal_closure(text["owner.objdump.txt"], text["restart.objdump.txt"]),
                            "final_admit_instructions": check_final_admit(text["final.objdump.txt"]),
                            "generated_object_matches_lge_closure": True}
    # Probe, untraced then traced.
    row["probe_positive"], row["probe_negative"] = [], []
    for i in range(PROBE_POSITIVE_RUNS):
        run = run_simple([probe, "positive"])
        run["mode"] = "positive"
        row["probe_positive"].append(run)
        L.checked(run, validate_probe_positive)
    for mode in PROBE_NEGATIVE:
        record = {"mode": mode, "status": "INCOMPLETE"}
        row["probe_negative"].append(record)
        traced([probe, mode], traced_env(), result=record)
        L.checked(record, validate_probe_negative)
    # Normal matrix.
    row["normal"], row["traced_positive"], row["traced_fatal"] = [], [], []
    for i in range(args.repeats):
        run = run_normal([exe], out, f"{key}_normal_{i}", reference)
        row["normal"].append(run)
        summary = L.checked(run, lambda r: validate_normal(r, reference))
        row.setdefault("normal_summary", []).append(summary)
    claims = validate_claims(row["normal"][0]["claims_text"])
    row["claim_sites"] = check_claim_sites(claims, G.readelf_symbols(text["final.readelf.txt"]),
                                           instruction_index(text["final.objdump.txt"]))
    for i in range(args.traced_repeats):
        tag = f"{key}_traced_positive_{i}"
        paths, files = lwr_files(out, tag)
        token = secrets.token_hex(16)
        record = {"mode": TRACED_POSITIVE, "token": token, "status": "INCOMPLETE"}
        row["traced_positive"].append(record)
        own = L.ownership_path(out, tag)
        traced([exe, TRACED_POSITIVE], traced_env(token, own, files), timeout=120, ownership=own, result=record)
        record.update(read_lwr_files(paths)[0])
        L.checked(record, lambda r: validate_traced_positive(r, reference))
    for i in range(args.traced_repeats):
        for mode in FATAL_LWR:
            tag = f"{key}_{mode}_{i}"
            token = secrets.token_hex(16)
            record = {"mode": mode, "token": token, "status": "INCOMPLETE"}
            row["traced_fatal"].append(record)
            own = L.ownership_path(out, tag)
            traced([exe, mode], traced_env(token, own), ownership=own, result=record)
            L.checked(record, validate_traced_fatal)
    require(sha(exe.read_bytes()) == exe_sha and sha(probe.read_bytes()) == probe_sha, "binaries changed during runs")
    row["status"] = "PASS"


def regression_config(out, key, cxx, cc, opt, prefix, private_dir, lge_ref, lrb_row, lge_row):
    """Fill the (already recorded) LRB and LGE rows; partial facts stay in results.json on failure."""
    version = L.command([cxx, "--version"], lrb_row["commands"])
    lrb_row["cxx_version"] = lge_row["cxx_version"] = version
    base = out / "regression"
    # LRB, exactly as lrb_gate.run_native builds it.
    build = base / "lrb" / key
    if build.exists():
        shutil.rmtree(build)
    configure_and_build(HERE.parent / "linux_runtime_bootstrap", build, cxx, cc, prefix,
                        ["-DLRB_OPT=" + opt, "-DLRB_ORDINARY_ONLY=OFF"], lrb_row["commands"])
    exe = build / "lrb_tests"
    lrb_row["executable_sha256"] = sha(exe.read_bytes())
    lrb_row["owner_sha256"] = sha((build / "CMakeFiles/lrb_tests.dir/lrb_owner.c.o").read_bytes())
    check_closure("lrb", key, "lrb_tests.elf", lrb_row["executable_sha256"], version)
    check_closure("lrb", key, "lrb_owner.o", lrb_row["owner_sha256"], version)
    for i in range(REGRESSION_RUNS):
        run = L.run_plain([exe], "normal", base / "lrb", f"{key}_normal_{i}")
        lrb_row["normal"].append(run)
        L.checked(run, L.validate_normal)
    # LGE, exactly as lge_gate.run_native builds it.
    build = base / "lge" / key
    if build.exists():
        shutil.rmtree(build)
    configure_and_build(HERE.parent / "linux_guest_entry", build, cxx, cc, prefix,
                        ["-DLGE_OPT=" + opt, "-DLRB_ORDINARY_ONLY=OFF", "-DLGE_GENERATED_DIR=" + str(private_dir)],
                        lge_row["commands"])
    exe = build / "lge_tests"
    lge_row["executable_sha256"] = sha(exe.read_bytes())
    lge_row["generated_sha256"] = sha(find_one(build / "CMakeFiles/lge_generated.dir", "*.o").read_bytes())
    lge_row["owner_sha256"] = sha(find_one(build / "CMakeFiles/lge_tests.dir", "lrb_owner.c.o").read_bytes())
    for name, actual in (("lge_tests.elf", lge_row["executable_sha256"]), ("lge_generated.o", lge_row["generated_sha256"]),
                         ("lrb_owner.o", lge_row["owner_sha256"])):
        check_closure("lge", key, name, actual, version)
    for i in range(REGRESSION_RUNS):
        run = G.run_plain([exe], base / "lge", f"{key}_normal_{i}", lge_ref["cases_text"], lge_ref["aggregate"])
        lge_row["normal"].append(run)
        L.checked(run, lambda r: validate_lge_normal(r, lge_ref))


def run_native(args):
    require(platform.system() == "Linux" and platform.machine() == "x86_64" and struct.calcsize("P") == 8,
            "native Linux x86-64 required; no Windows/WSL fallback")
    register_fatal()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    sdk, prefix, private_dir = args.sdk.resolve(), args.prefix.resolve(), args.private.resolve()
    result = {"status": "INCOMPLETE", "platform": platform.platform(), "machine": platform.machine(),
              "kernel": platform.release(), "python": sys.version, "repeats": args.repeats,
              "traced_repeats": args.traced_repeats, "configurations": [], "regression": {"lrb": [], "lge": []}}
    before_names = L.shm_names()
    result["shm_snapshot"] = {"before": before_names}
    try:
        manifest, identity = source_identity()
        result.update(identity=identity, source_manifest=manifest)
        sdk_info = L.sdk_identity(sdk, prefix)
        result["sdk_identity"] = sdk_info
        _, lge_reference = G.private_identity(private_dir)
        reference = load_reference(args.reference, private_dir)
        result["private_identity"] = {
            "generated_manifest_sha256": sha((private_dir / "GENERATED_MANIFEST.json").read_bytes()),
            "lwr_reference_sha256": sha(Path(args.reference).read_bytes()),
            "reference_aggregate": reference["aggregate"], "reference_cases_sha256": reference["cases_sha256"],
            "lge_reference": {"aggregate": lge_reference["aggregate"], "cases_sha256": lge_reference["cases_sha256"]}}
        compilers = {}
        for cxx_name, cc_name, opt in L.CONFIGS:
            cxx, cc = shutil.which(cxx_name), shutil.which(cc_name)
            require(cxx and cc, "missing compiler pair " + cxx_name)
            key = f"{cxx_name}_O{opt}"
            compilers[key] = (cxx, cc, opt)
            row = {"key": key, "status": "INCOMPLETE", "commands": []}
            result["configurations"].append(row)
            native_config(out, key, cxx, cc, opt, prefix, private_dir, reference, args, row)
        for key, (cxx, cc, opt) in compilers.items():
            lrb_row = {"key": key, "status": "INCOMPLETE", "commands": [], "normal": []}
            lge_row = {"key": key, "status": "INCOMPLETE", "commands": [], "normal": []}
            result["regression"]["lrb"].append(lrb_row)
            result["regression"]["lge"].append(lge_row)
            regression_config(out, key, cxx, cc, opt, prefix, private_dir, lge_reference, lrb_row, lge_row)
            lrb_row["status"] = lge_row["status"] = "PASS"
        names = L.shm_names()
        ours = {r["ownership"]["shm_name"] for row in result["configurations"]
                for r in row["normal"] + row["traced_positive"] + row["traced_fatal"]
                if isinstance(r.get("ownership"), dict) and isinstance(r["ownership"].get("shm_name"), str)}
        for kind in ("lrb", "lge"):
            ours |= {r["ownership"]["shm_name"] for row in result["regression"][kind] for r in row["normal"]
                     if isinstance(r.get("ownership"), dict) and isinstance(r["ownership"].get("shm_name"), str)}
        result["shm_snapshot"].update(after=names, foreign_new=sorted(set(names) - set(before_names) - ours),
                                      own_left=sorted(set(names) & ours))
        require(not result["shm_snapshot"]["own_left"], "own shm residue left")
        require(L.sdk_identity(sdk, prefix) == sdk_info, "SDK changed during run")
        require(source_identity() == (manifest, identity), "sources changed during run")
        result["positive_checks"] = validate_results({**result, "status": "PASS"}, reference)
        result["status"] = "PASS"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        (out / "regression").mkdir(exist_ok=True)
        (out / "regression/regression.json").write_text(json.dumps(result["regression"], indent=2) + "\n", encoding="utf-8")
    n, t = args.repeats, args.traced_repeats
    print(f"LWR_GATE PASS configurations=4 normal={4 * n} traced_positive={4 * t} traced_fatal={4 * len(FATAL_LWR) * t} "
          f"probe_negative={4 * len(PROBE_NEGATIVE)} cases={CASE_COUNT} claims={TOTAL_CLAIMS} regression=PASS; "
          "independent audit still required")


# ------------------------------------------------------------------ evidence and audit

def package_evidence(out, path, failure):
    out = out.resolve()
    entries = {}
    results = out / "results.json"
    if results.exists():
        entries["results.json"] = results.read_bytes()
        if not failure:
            require(read_json(entries["results.json"]).get("status") == "PASS", "results status is not PASS")
    elif not failure:
        raise GateError("results.json missing")
    for src in sorted((out / "native").rglob("*")) if (out / "native").is_dir() else []:
        if src.is_file():
            entries[src.relative_to(out).as_posix()] = src.read_bytes()
    for src in sorted((out / "cases").glob("*.txt")) if (out / "cases").is_dir() else []:
        entries["cases/" + src.name] = src.read_bytes()
    if (out / "regression/regression.json").exists():
        entries["regression/regression.json"] = (out / "regression/regression.json").read_bytes()
    for name in ("SOURCE_MANIFEST.json", "IMPLEMENTATION_ID.json"):
        if (ROOT / name).exists():
            entries[name] = (ROOT / name).read_bytes()
    for name in ("console.log", "validator.log"):
        if (out / name).exists():
            entries[name] = (out / name).read_bytes()
    entries["PRIVATE.txt"] = (b"PRIVATE: this evidence contains compiled game code (generated objects, linked ELFs, "
                              b"disassembly). Never commit, publish or upload; return only to private/work/.\n")
    if failure:
        own = out / "ownership"
        for p in sorted(own.glob("*.json")) if own.is_dir() else []:
            entries["ownership/" + p.name] = p.read_bytes()
        entries["FAILURE.txt"] = b"INCOMPLETE/FAILED native LWR evidence; not a PASS claim.\n"
    require(entries, "nothing to package")
    entries["EVIDENCE_MANIFEST.json"] = (json.dumps({n: sha(b) for n, b in sorted(entries.items())}, indent=2)
                                         + "\n").encode()
    digest = L.write_zip(path, entries)
    print(f"LWR_EVIDENCE {'FAILURE' if failure else 'PASS'} entries={len(entries)} sha256={digest} path={path} "
          "(PRIVATE: contains compiled game code; return only to private/work/linux_write_watch_restart/)")


def audit_row(row, data):
    key = row["key"]
    for name in NATIVE_NAMES:
        full = f"native/{key}/{name}"
        require(full in data and sha(data[full]) == row["artifacts"][name], "artifact digest: " + full)
    require(row["executable_sha256"] == row["artifacts"]["lwr_tests.elf"], "ELF identity")
    require(row["probe_sha256"] == row["artifacts"]["lwr_probe.elf"], "probe ELF identity")
    check_closure("lge", key, "lge_generated.o", sha(data[f"native/{key}/lge_generated.o"]), row.get("cxx_version"))
    text = {n: data[f"native/{key}/{n}"].decode("utf-8") for n in NATIVE_NAMES if n.endswith(".txt")}
    recomputed = {"bind_now": check_bind_now(text["final.readelf.txt"]),
                  "restart_admit": check_restart_object(text["restart.objdump.txt"]),
                  "owner_calls_admit": check_owner_calls_admit(text["owner.objdump.txt"]),
                  "signal_closure": check_signal_closure(text["owner.objdump.txt"], text["restart.objdump.txt"]),
                  "final_admit_instructions": check_final_admit(text["final.objdump.txt"]),
                  "generated_object_matches_lge_closure": True}
    require(recomputed == row["object_checks"], "object checks re-derived: " + key)
    claims = validate_claims(row["normal"][0]["claims_text"])
    sites = check_claim_sites(claims, G.readelf_symbols(text["final.readelf.txt"]), instruction_index(text["final.objdump.txt"]))
    require(sites == row["claim_sites"], "claim sites re-derived: " + key)


def audit(archive, implementation, private_dir, reference_path):
    register_fatal()
    reference = read_json(Path(reference_path).read_bytes())
    check_reference(reference)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) and z.testzip() is None, "archive integrity")
        data = {n: z.read(n) for n in names}
    require("FAILURE.txt" not in data, "failure bundle is not PASS evidence")
    require(not any(n.endswith((".cpp", ".h")) for n in data), "no source or generated code in evidence")
    require(not any(b"\nDEFINE_REX_FUNC(" in b for b in data.values()), "no generated function definitions in evidence")
    manifest = read_json(data["EVIDENCE_MANIFEST.json"])
    require(set(manifest) == set(data) - {"EVIDENCE_MANIFEST.json"}, "evidence inventory")
    require(all(sha(data[n]) == h for n, h in manifest.items()), "evidence digest mismatch")
    identity = read_json(data["IMPLEMENTATION_ID.json"])
    require(identity["commit"] == implementation, "implementation commit mismatch")
    source = read_json(data["SOURCE_MANIFEST.json"])
    require(sorted(source) == source_files(), "transferred source inventory")
    for name, digest in source.items():
        blob = G.git("show", f"{implementation}:{name}").replace(b"\r\n", b"\n")
        require(sha(blob) == digest, "transferred source differs from Git: " + name)
    result = read_json(data["results.json"])
    require(result["identity"] == identity and result["source_manifest"] == source, "result source identity")
    require(result["sdk_identity"]["sdk"] == L.SDK_PIN and result["sdk_identity"]["simde"] == L.SIMDE_PIN, "SDK pins")
    for name, digest in result["sdk_identity"]["sources_sha256_lf"].items():
        blob = subprocess.run(["git", "-C", str(ROOT / "external/rexglue-sdk"), "show", f"{L.SDK_PIN}:{name}"],
                              capture_output=True, check=True).stdout.replace(b"\r\n", b"\n")
        require(sha(blob) == digest, "SDK source identity differs from pin: " + name)
    pid = result["private_identity"]
    require(pid["reference_aggregate"] == reference["aggregate"] and pid["reference_cases_sha256"] == reference["cases_sha256"]
            and pid["generated_manifest_sha256"] == reference["generated_manifest_sha256"],
            "native run compared against this LWR Windows reference")
    if private_dir is not None:
        _, lge_reference = G.private_identity(private_dir)
        require(pid["generated_manifest_sha256"] == sha((private_dir / "GENERATED_MANIFEST.json").read_bytes()),
                "native run used this private extract")
        require(reference["lge_reference_sha256"] == sha((private_dir / "windows_reference.json").read_bytes()),
                "LWR reference built from this LGE reference")
        require(pid["lge_reference"] == {"aggregate": lge_reference["aggregate"], "cases_sha256": lge_reference["cases_sha256"]},
                "regression compared against this LGE reference")
    checks = validate_results(result, reference)
    for row in result["configurations"]:
        audit_row(row, data)
    require("regression/regression.json" in data and read_json(data["regression/regression.json"]) == result["regression"],
            "regression results archived")
    print(f"LWR_AUDIT PASS cases={CASE_COUNT} claims={TOTAL_CLAIMS} positive_checks={checks} configurations=4 "
          f"entries={len(data)}; root disassembly review still required")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("windows"); w.add_argument("--repeats", type=int, default=5)
    w.add_argument("--private", type=Path, default=LGE_PRIVATE); w.add_argument("--prefix", type=Path, default=G.DEFAULT_WIN_PREFIX)
    w.add_argument("--work", type=Path, default=PRIVATE / "windows")
    p = sub.add_parser("private-zip"); p.add_argument("--zip", type=Path, default=PRIVATE / "lwr-private-reference.zip")
    s = sub.add_parser("source"); s.add_argument("--zip", type=Path, required=True)
    r = sub.add_parser("run")
    r.add_argument("--sdk", type=Path, required=True); r.add_argument("--prefix", type=Path, required=True)
    r.add_argument("--private", type=Path, required=True); r.add_argument("--reference", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--repeats", type=int, default=10); r.add_argument("--traced-repeats", type=int, default=2)
    e = sub.add_parser("evidence"); e.add_argument("--out", type=Path, required=True)
    e.add_argument("--zip", type=Path, required=True); e.add_argument("--failure", action="store_true")
    a = sub.add_parser("audit"); a.add_argument("--archive", type=Path, required=True)
    a.add_argument("--implementation", required=True)
    a.add_argument("--private", type=Path, default=None); a.add_argument("--reference", type=Path, default=PRIVATE / REFERENCE_NAME)
    args = ap.parse_args()
    if args.cmd == "windows":
        require(args.repeats >= 1, "positive repetition count")
        windows_reference(args.private.resolve(), args.prefix.resolve(), args.repeats, args.work.resolve())
    elif args.cmd == "private-zip":
        private_zip(args.zip.resolve())
    elif args.cmd == "source":
        package_source(args.zip.resolve())
    elif args.cmd == "run":
        require(args.repeats >= 1 and args.traced_repeats >= 1, "positive repetition counts")
        run_native(args)
    elif args.cmd == "evidence":
        package_evidence(args.out, args.zip.resolve(), args.failure)
    else:
        audit(args.archive, args.implementation, args.private.resolve() if args.private else None, args.reference)


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print(f"LWR_GATE FAIL: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:  # Unexpected runner fault: keep the traceback, still a FAIL.
        traceback.print_exc()
        print(f"LWR_GATE FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)

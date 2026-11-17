"""Validator tests for lrgd_gate.py (synthetic records only; no build, no game, no generated code, no private content)."""
import copy
import hashlib
from pathlib import Path
import random
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lrgd_gate as R  # noqa: E402

S, W, G, L = R.S, R.W, R.G, R.L
GateError = R.GateError
R.register_fatal()
TOKEN = "0123456789abcdef0123456789abcdef"
PID = 4242
THUNK, SEH = 0x1A2B30, 0x1C4D50
RESIDUE = {"present": False, "after": False}
SDK = R.DEFAULT_SDK
GUESTS = ["820e7440", "820eb7d8", "820e78a0", "820eb350", "820e7328", "820e6d08", "820f0a28", "820f7978"]
SLOT = R.LR_SLOT_OFFSET


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


# ------------------------------------------------------------------ synthetic audited cases and dispatch rows

def render_delta(bytes_map):
    parts, keys = [], sorted(bytes_map)
    i = 0
    while i < len(keys):
        j = i
        while j + 1 < len(keys) and keys[j + 1] == keys[j] + 1:
            j += 1
        parts.append(f"{keys[i]:x}:" + "".join(f"{bytes_map[k]:02x}" for k in keys[i:j + 1]))
        i = j + 1
    return ",".join(parts)


def resign(line):
    head = line[:line.rindex("|digest=")]
    return head + "|digest=" + sha(head)


def set_field(line, name, value):
    parts = line.split("|")
    for i, part in enumerate(parts):
        if part.startswith(name + "="):
            parts[i] = f"{name}={value}"
            return "|".join(parts)
    raise AssertionError("no field " + name)


def get_field(line, name):
    for part in line.split("|"):
        if part.startswith(name + "="):
            return part[len(name) + 1:]
    raise AssertionError("no field " + name)


def set_reg(line, field, key, value):
    state = R.parse_state(get_field(line, field), field)
    state[key] = value
    return set_field(line, field, R.fmt_state(state))


class World:
    """124 LGE + 8 LWR synthetic reference cases and the dispatch rows a correct dispatcher would produce."""

    def __init__(self):
        rng = random.Random(20260506)
        self.lge_lines, self.lwr_lines = [], []
        self.rows = {}  # id -> raw delta/state parts
        for suite, count, prefix in (("lge", 124, "LGE_CASE_V1"), ("lwr", 8, "LWR_CASE_V1")):
            for i in range(count):
                guest = GUESTS[i % 8] if suite == "lge" else GUESTS[(i + 4) % 8 if i != 7 else 7]
                if suite == "lwr" and i == 7:
                    guest = "820f7978"
                cid = f"{suite}/{i}"
                erase = guest == "820f7978"
                nargs = R.NARGS[guest]
                before = {f"r{k}": f"{rng.getrandbits(64):016x}" for k in range(32)}
                before.update(lr=R.RETURN_LR, ctr=f"{rng.getrandbits(64):016x}", xer=f"{rng.getrandbits(24):06x}",
                              cr=f"{rng.getrandbits(256):064x}")
                before["r1"] = f"{rng.randrange(0x20000000, 0x20010000) & ~0xF:016x}"
                entry = {**before, "lr": R.SENTINEL_LR}
                pre = dict(before)
                pre["r1"] = R.h16(int(before["r1"], 16) + R.PAD)
                for k in range(nargs):
                    pre[f"r{3 + k}"] = R.h16(~int(before[f"r{3 + k}"], 16))
                post = dict(pre)
                for key in ("r3", "r4", "ctr", "r31"):
                    post[key] = f"{rng.getrandbits(64):016x}"
                if erase:
                    post["r12"] = R.SENTINEL_LR
                after = dict(post)
                after["r1"] = R.h16(int(post["r1"], 16) - R.PAD)
                if erase:
                    after["r12"] = R.RETURN_LR
                body = {rng.randrange(0, 0x8000): rng.randrange(256) for _ in range(rng.randrange(0, 40))}
                raw, norm = dict(body), dict(body)
                if erase:
                    raw.update({SLOT + k: b for k, b in enumerate(bytes.fromhex("bcbcbcbc"))})
                    norm.update({SLOT + k: b for k, b in enumerate(bytes.fromhex("82fff000"))})
                for k in range(SLOT, SLOT + 4):
                    if not erase:
                        raw.pop(k, None)
                        norm.pop(k, None)
                trace = f"__imp__sub_{guest.upper()}"
                head = (f"{prefix}|id={cid}|fn=sub_{guest.upper()}|guest={guest}|seed={i}|input={rng.getrandbits(256):064x}"
                        f"|before={R.fmt_state(before)}|after={R.fmt_state(after)}|nonint=unchanged|writable=00000000-00000001"
                        f"|changed={len(norm)}|delta={render_delta(norm)}|trace={trace}|model=pass")
                line = head + "|digest=" + sha(head)
                (self.lge_lines if suite == "lge" else self.lwr_lines).append(line)
                self.rows[cid] = dict(suite=suite, id=cid, guest=guest, nargs=nargs, ret=post["r3"], pre=pre, entry=entry,
                                      post=post, slot="fef8" if erase else "-", raw=raw, trace=trace, digest=sha(head))
        self.lge_text = "".join(l + "\n" for l in self.lge_lines)
        self.lwr_text = "".join(l + "\n" for l in self.lwr_lines)
        self.refs = R.make_refs(self.lge_text, self.lwr_text)

    def dispatch_line(self, row, watched):
        return ("LRGD_CASE_V1|suite={suite}|watched={w}|pass=1|id={id}|guest={guest}|nargs={nargs}|ret={ret}|pre={pre}|entry={entry}"
                "|post={post}|bound=thread_state|ctx=thread_state|entry_ctx=input+lr_sentinel|lr_slot={slot}|raw_changed={n}"
                "|raw_delta={delta}|trace={trace}|canonical={digest}").format(
            w=watched, n=len(row["raw"]), delta=render_delta(row["raw"]), **{
                **row, "pre": R.fmt_state(row["pre"]), "entry": R.fmt_state(row["entry"]), "post": R.fmt_state(row["post"])})

    def dispatch(self, watched):
        out = []
        for line in self.lge_lines:
            out.append(self.dispatch_line(self.rows[get_field(line, "id")], 0))
        for line in self.lwr_lines:
            row = self.rows[get_field(line, "id")]
            out.append(self.dispatch_line(row, 0))
            if watched:
                out.append(self.dispatch_line(row, 1))
        return out


WORLD = World()


# ------------------------------------------------------------------ synthetic records

def plain(state="dfl"):
    return {"state": state, "siginfo": 0, "flags": 0, "mask": 0, "object": "-", "offset": 0}


def handler(flags, offset, obj="librexruntime.so.1", mask=0):
    return {"state": "fn", "siginfo": 1, "flags": flags, "mask": mask, "object": obj, "offset": offset}


THUNK_ROW = handler(S.SA_SIGINFO, THUNK)
SEH_ROW = handler(S.SA_SIGINFO | S.SA_NODEFER, SEH)
OWNER_ROW = handler(S.SA_ONSTACK | S.SA_SIGINFO, 0x3300, "lrgd_tests", S.OWNER_MASK)
ALLOCATED = 20_000_000


def entry_rows():
    rows = {s: plain() for s in S.SIGNALS}
    rows[13] = plain("ign")
    return rows


def with_rows(base, **named):
    rows = copy.deepcopy(base)
    for sig, row in named.items():
        rows[int(sig[1:])] = copy.deepcopy(row)
    return rows


IMAGE_LINE = ("LRGD_IMAGE_V1|mode={m}|cycle={c}|code_base=820e0000|code_size=007425e4|image_base=82000000|image_size=00ce0000"
              "|table_base=82ce0000|table_size=00ea4bc8|thunk_reserve=00010000|mappings=10|window_populated=10"
              "|window_empty=18422|codegen_flags=00000000|rexcrt_heap=0|register_modules=0")
REG_ROWS = [("820e6d08", "sub_820E6D08"), ("820e7328", "sub_820E7328"), ("820e73cc", "__savegprlr_29"),
            ("820e741c", "__restgprlr_29"), ("820e7440", "sub_820E7440"), ("820e78a0", "sub_820E78A0"),
            ("820eb350", "sub_820EB350"), ("820eb7d8", "sub_820EB7D8"), ("820f0a28", "sub_820F0A28"),
            ("820f7978", "sub_820F7978")]


def build(mode, native=True):
    """Blocks of a valid record file for `mode`, in the order lrgd_tests.cpp writes them."""
    variant, cycles = R.MODES[mode]
    latch, fatal = variant == "latch", mode in R.FATAL_LRGD
    B = []
    entry = entry_rows()
    if native:
        B += [["SIG", 0, "entry", entry], ["THREADS", 0, "entry"], ["LATCH", "entry", 0],
              ["SIG", 0, "after-logging", copy.deepcopy(entry)], ["THREADS", 0, "after-logging"]]
        if latch:
            B.append(["LATCH", "after-store", 1])
    for c in range(1, cycles + 1):
        if native:
            B.append(["THREADS", c, "after-setup"])
        B.append(["RUNTIME", c, f"/xenia_memory_{1000 + c}", 500 + c, 41, ALLOCATED])
        for guest, symbol in REG_ROWS:
            B.append(["RAW", f"LRGD_REG_V1|mode={mode}|cycle={c}|guest={guest}|symbol={symbol}|dispatcher=1|table_slot=1|indirect=1"])
        B.append(["RAW", IMAGE_LINE.format(m=mode, c=c)])
        if native:
            if c == 1:
                B.append(["LATCH", "after-setup", 1])
            if not latch:
                setup = with_rows(entry, s4=THUNK_ROW, s11=THUNK_ROW, s7=SEH_ROW, s8=SEH_ROW)
                seh = with_rows(entry, s4=SEH_ROW, s7=SEH_ROW, s8=SEH_ROW, s11=SEH_ROW)
                B.append(["SIG", c, "after-setup", setup])
                B.append(["RAW", f"LRGD_HANDOFF_V1|mode={mode}|cycle={c}|result=not-attempted|segv_beneath=sdk-seh"])
            else:
                owner = with_rows(entry, s11=OWNER_ROW)
                B += [["SIG", c, "after-setup", with_rows(entry, s4=THUNK_ROW, s11=THUNK_ROW)],
                      ["SIG", c, "after-thunk-removal", copy.deepcopy(entry)], ["SIG", c, "after-owner", owner],
                      ["THREADS", c, "after-owner"],
                      ["RAW", f"LRGD_HANDOFF_V1|mode={mode}|cycle={c}|result=installed|segv_beneath=sig_dfl"]]
        B.append(["RAW", f"LRGD_THREAD_STATE_V1|mode={mode}|cycle={c}|thread_id=0x4c524744|xthread=0|host_thread=main|bound_before=0"])
        if fatal:
            break
        B.append(["RAW", f"LRGD_NEGATIVE_V1|mode={mode}|cycle={c}|unregistered=820e0000|ret=0xdeadbabe|entered=0|bound=unchanged"
                         "|context=args-only|memory=unchanged|out_of_range_set=refused"])
        for number in (1, 2):
            B.append(["RAW", f"LRGD_PASS_V1|mode={mode}|cycle={c}|pass={number}|lge=124|lwr=8|watched={8 if latch else 0}"
                             f"|reproduced={'-' if (c, number) == (1, 1) else 1}"])
        if native:
            B += [["SIG", c, "after-dispatch", copy.deepcopy(owner if latch else setup)], ["THREADS", c, "after-dispatch"]]
        B.append(["RAW", f"LRGD_DISPATCH_V1|mode={mode}|cycle={c}|dispatches={281 if latch else 265}|claims={18 if latch else 0}"])
        if native:
            if latch:
                B.append(["SIG", c, "after-owner-removal", copy.deepcopy(entry)])
            B.append(["SIG", c, "after-shutdown", copy.deepcopy(entry) if latch else seh])
            B.append(["THREADS", c, "after-shutdown"])
        tail = "views_unmapped=1|shm_removed=1" if native else "views_unmapped=-|shm_removed=-"
        B.append(["RAW", f"LRGD_TEARDOWN_V1|mode={mode}|cycle={c}|instance=0|kernel_shared=0|mmio=0|dispatcher=0|{tail}"])
        if native and c == cycles:
            B.append(["LATCH", "after-shutdown", 1])
    for block in B:
        if block[0] == "THREADS":
            block += [2, 2, 1]  # count, baseline, equal
    return B


def render(mode, blocks, native=True, obj="librexruntime.so.1"):
    lines = []
    for b in blocks:
        if b[0] == "SIG":
            _, cycle, stage, rows = b
            for sig in S.SIGNALS:
                r = rows[sig]
                lines.append(f"LRGD_SIG_V1|mode={mode}|cycle={cycle}|stage={stage}|sig={sig}|state={r['state']}|siginfo={r['siginfo']}"
                             f"|flags=0x{r['flags']:x}|mask=0x{r['mask']:016x}|object={r['object']}|offset=0x{r['offset']:x}")
        elif b[0] == "THREADS":
            count = b[3] if len(b) > 3 else 2
            baseline = b[4] if len(b) > 4 else 2
            equal = b[5] if len(b) > 5 else 1
            lines.append(f"LRGD_THREADS_V1|mode={mode}|cycle={b[1]}|stage={b[2]}|count={count}|baseline={baseline}|equal={equal}")
        elif b[0] == "LATCH":
            lines.append(f"LRGD_LATCH_V1|mode={mode}|stage={b[1]}|value={b[2]}|object={obj}")
        elif b[0] == "RUNTIME":
            _, c, shm, inode, device, allocated = b
            if native:
                lines.append(f"LRGD_RUNTIME_V1|mode={mode}|cycle={c}|setup_status=0x0|instance=1|kernel_shared=1|mmio=1|dispatcher=1"
                             f"|membase=0x100000000|tool_mode=1|shm={shm}|inode={inode}|device={device}|allocated={allocated}")
            else:
                lines.append(f"LRGD_RUNTIME_V1|mode={mode}|cycle={c}|setup_status=0x0|instance=1|kernel_shared=1|mmio=1"
                             "|dispatcher=1|tool_mode=1")
        else:
            lines.append(b[1])
    return "\n".join(lines) + "\n"


def valid(mode, native=True):
    return render(mode, build(mode, native), native)


def mutated(mode, edit, native=True, **kw):
    blocks = build(mode, native)
    edit(blocks)
    return render(mode, blocks, native, **kw)


def find(blocks, kind, *key):
    return next(b for b in blocks if b[0] == kind and tuple(b[1:1 + len(key)]) == key)


def raw_index(blocks, prefix):
    return next(i for i, b in enumerate(blocks) if b[0] == "RAW" and b[1].startswith(prefix))


def sig_rows(blocks, cycle, stage):
    return find(blocks, "SIG", cycle, stage)[3]


# ------------------------------------------------------------------ synthetic runs

def ownership(fatal, shm="/xenia_memory_1001", inode=501, device=41, cycles=1):
    return {"format": "LRB_OWNERSHIP_V1", "stage": "started", "pid": PID, "shm_name": f"/xenia_memory_{1000 + cycles}",
            "device": device, "inode": 500 + cycles, "virtual_membase": 1 << 32, "apparent_size": 0x120001000,
            "allocated_bytes": ALLOCATED, "unlinked_early": fatal, "policy": "unlink-after-map" if fatal else "sdk-contract"}


def pass_text(mode, checks=77, **over):
    variant, cycles = R.MODES[mode]
    latch = variant == "latch"
    fields = {"mode": mode, "variant": variant, "cycles": cycles, "watched": 8 if latch else 0,
              "claims": 18 * cycles if latch else 0, "lge": WORLD.refs["lge_aggregate"], "lwr": WORLD.refs["lwr_aggregate"],
              "checks": checks, "native": 1}
    fields.update(over)
    return ("LRGD PASS mode={mode} variant={variant} cycles={cycles} lge=124 lwr=8 watched={watched} claims={claims} "
            "lge_aggregate={lge} lwr_aggregate={lwr} checks={checks} native={native}\n").format(**fields)


def claims_text():
    out, n = [], {}
    for line in W.EXPECTED_RESTART:
        cid = W.restart_id(line)
        for index, page in enumerate(W.restart_pages(line)):
            effective = page * 4096 + 0x20
            out.append(f"LRGD_CLAIM_V1|id={cid}|n={index}|page={page}|fn=__imp__sub_820E7440|offset=0x10|width=4|length=3"
                       f"|address=0x{effective + 1:x}|effective=0x{effective:x}|error=7|before=00000000\n")
    return "".join(out)


def texts_for(mode, native=True):
    latch = R.MODES[mode][0] == "latch"
    return {"record": valid(mode, native), "lge": WORLD.lge_text, "lwr": WORLD.lwr_text,
            "watched": WORLD.lwr_text if latch else "", "dispatch": "".join(l + "\n" for l in WORLD.dispatch(latch)),
            "restart": R.expected_restart_text() if latch else "", "claims": claims_text() if latch else ""}


def make_run(mode, texts=None, tag="t", **over):
    texts = texts or texts_for(mode)
    files, shas, store = {}, {}, {}
    for name, text in texts.items():
        path = f"files/{tag}.{name}.txt"
        files[name], shas[name] = path, hashlib.sha256(text.encode()).hexdigest()
        store[path] = text.encode()
    cycles = R.MODES[mode][1]
    run = {"mode": mode, "pid": PID, "returncode": 0, "stdout": pass_text(mode), "stderr": "", "cwd_entries": [],
           "files": files, "file_sha256": shas, "ownership": ownership(mode in R.FATAL_LRGD, cycles=cycles),
           "residue": dict(RESIDUE)}
    run.update(over)
    return run, store.__getitem__


def witness(mode, phase, claims, invalidations, address, token=TOKEN):
    return f"LRGD_GATE_V1 token={token} mode={mode} phase={phase} claims={claims} invalidations={invalidations} address=0x{address:x}\n"


def accerr(trace, address):
    return {"signal": 11, "code": 2, "errno": 0, "address": address, "sender_pid": 0, "trace": trace}


def tkill(trace):
    return {"signal": 11, "code": -6, "errno": 0, "address": 0, "sender_pid": PID, "trace": trace}


def positive_traced(**over):
    base = R.VA_REGION[0] + 0x4000
    rows, stops, written, expectations = [], [], "", R.positive_expectations()
    for i, (case_claims, before) in enumerate(expectations):
        address = base + 0x100 * i
        rows.append(witness(R.TRACED_POSITIVE, "claim", case_claims, 0, address))
    for i, (case_claims, before) in enumerate(expectations):
        stops.append(accerr("".join(rows[:before]), base + 0x100 * i))
    texts = texts_for(R.TRACED_POSITIVE)
    run, reader = make_run(R.TRACED_POSITIVE, texts, token=TOKEN, status="PASS", stderr="".join(rows), signals=stops)
    run.update(over)
    return run, reader


def fatal_run(mode, **over):
    address = R.GUARD_ADDRESS if mode == "lrgd-write-guard" else R.P4_ADDRESS
    stderr = witness(mode, "begin", 0, 0, address)
    texts = {"record": valid(mode)}
    run, reader = make_run(mode, texts, token=TOKEN, status="PASS", returncode=-11, stdout="", stderr=stderr,
                           signals=[accerr(stderr, address), tkill(stderr)])
    run.update(over)
    return run, reader


# ------------------------------------------------------------------ tests

def recode(text, offset, length):
    """The same claims as another compiler would place them: only offset/length change."""
    return "".join(set_field(line, "length", str(length)).replace("offset=0x10", f"offset=0x{offset:x}") + "\n"
                   for line in text.splitlines())


class ClaimConsistencyTests(unittest.TestCase):
    """Regression for LRGD native attempt 1: 'claims file differs between runs/configurations'.

    The four configurations placed the same stores at different instruction offsets with
    different encodings (length 3 vs 2/4/5); every other claim field was identical.
    """

    def setUp(self):
        base = claims_text()
        self.per_config = {"clang++_O0": [base] * 3, "clang++_O2": [recode(base, 0x59, 4)] * 3,
                           "g++_O0": [recode(base, 0x95, 2)] * 3, "g++_O2": [recode(base, 0x90, 5)] * 3}

    def test_attempt1_shape_passes(self):
        digest = R.check_claim_consistency(self.per_config)
        self.assertEqual(digest, R.check_claim_consistency({"clang++_O0": [claims_text()]}))

    def test_attempt1_shape_failed_the_old_global_rule(self):
        hashes = {sha(t) for texts in self.per_config.values() for t in texts}
        self.assertEqual(len(hashes), 4)  # the former single global hash requirement fails here

    def test_runs_of_one_configuration_must_be_identical(self):
        bad = copy.deepcopy(self.per_config)
        bad["g++_O2"][1] = recode(claims_text(), 0x91, 5)
        with self.assertRaises(GateError):
            R.check_claim_consistency(bad)

    def test_every_semantic_field_must_agree_across_configurations(self):
        line = claims_text().splitlines()[0]
        edits = {"id": "restart/other", "n": "1", "page": "5", "fn": "__imp__sub_820EB350", "width": "2",
                 "address": "0x4022", "effective": "0x4021", "error": "6", "before": "deadbeef"}
        caught_by_comparison = []
        for name, value in edits.items():
            changed = claims_text().replace(line, set_field(line, name, value), 1)
            try:
                R.validate_claims(changed)
                caught_by_comparison.append(name)  # individually valid: only the comparison can reject it
            except GateError:
                pass
            per = copy.deepcopy(self.per_config)
            per["g++_O0"] = [changed] * 3
            with self.subTest(field=name), self.assertRaises(GateError):
                R.check_claim_consistency(per)
        # Guest/restart facts that per-file validation cannot judge must differ only via the comparison.
        self.assertTrue({"fn", "before", "error"} <= set(caught_by_comparison), caught_by_comparison)

    def test_empty_inventory_rejected(self):
        for per in ({}, {"clang++_O0": []}):
            with self.assertRaises(GateError):
                R.check_claim_consistency(per)

    def test_projection_drops_only_offset_and_length(self):
        projected = R.claim_semantics(claims_text()).splitlines()[0]
        self.assertNotIn("offset=", projected)
        self.assertNotIn("length=", projected)
        for name in ("id", "n", "page", "fn", "width", "address", "effective", "error", "before"):
            self.assertIn(f"|{name}=", projected)


class RederiveTests(unittest.TestCase):
    def run_rederive(self, dispatch=None, lge=None, lwr=None, watched=False):
        return R.rederive(dispatch if dispatch is not None else WORLD.dispatch(watched),
                          lge if lge is not None else WORLD.lge_lines, lwr if lwr is not None else WORLD.lwr_lines, watched)

    def index_of(self, cid, watched=0):
        lines = WORLD.dispatch(True)
        return next(i for i, l in enumerate(lines) if get_field(l, "id") == cid and get_field(l, "watched") == str(watched))

    def edit(self, cid, edit, watched_run=False, watched=0):
        lines = WORLD.dispatch(watched_run)
        i = next(i for i, l in enumerate(lines) if get_field(l, "id") == cid and get_field(l, "watched") == str(watched))
        lines[i] = edit(lines[i])
        return lines

    def rejects(self, pattern, cid, edit, **kw):
        with self.assertRaisesRegex(GateError, pattern):
            self.run_rederive(self.edit(cid, edit, **kw), watched=kw.get("watched_run", False))

    def test_positive(self):
        summary = self.run_rederive()
        self.assertEqual((summary["rows"], summary["lr_slot_rows"], summary["watched_rows"]), (132, 16 + 1, 0))
        summary = self.run_rederive(watched=True)
        self.assertEqual((summary["rows"], summary["watched_rows"]), (140, 8))

    def test_world_has_every_function_and_the_erase_slot(self):
        guests = {get_field(l, "guest") for l in WORLD.dispatch(False)}
        self.assertEqual(guests, set(GUESTS))
        self.assertEqual(sum(get_field(l, "lr_slot") == "fef8" for l in WORLD.dispatch(False)), 17)

    def test_entry_rules(self):
        cid = "lge/0"
        self.rejects("entry lr", cid, lambda l: set_reg(l, "entry", "lr", R.RETURN_LR))
        self.rejects("entry differs", cid, lambda l: set_reg(l, "entry", "r20", "0" * 16))
        self.rejects("entry differs", cid, lambda l: set_reg(l, "entry", "cr", "f" * 64))

    def test_pre_rules(self):
        cid = "lge/1"
        self.rejects("pre differs", cid, lambda l: set_reg(l, "pre", "r1", "0" * 16))
        self.rejects("pre differs", cid, lambda l: set_reg(l, "pre", "r3", "0" * 16))
        self.rejects("pre differs", cid, lambda l: set_reg(l, "pre", "r5", "0" * 16))
        self.rejects("pre differs", cid, lambda l: set_reg(l, "pre", "r30", "1" * 16))
        # An argument register beyond nargs must stay un-poisoned (strstr takes two).
        strstr = next(r["id"] for r in WORLD.rows.values() if r["guest"] == "820e6d08")
        self.rejects("pre differs", strstr, lambda l: set_reg(l, "pre", "r5", R.h16(~int(R.parse_state(get_field(l, "pre"), "p")["r5"], 16))))
        # ... and the poisoned complement of a 4-arg function must reach r6.
        fmt = next(r["id"] for r in WORLD.rows.values() if r["guest"] == "820f0a28")
        self.rejects("pre differs", fmt, lambda l: set_reg(l, "pre", "r6", get_field(l, "entry") and R.parse_state(get_field(l, "entry"), "e")["r6"]))

    def test_post_rules(self):
        cid = "lge/2"
        self.rejects("did not restore", cid, lambda l: set_reg(l, "post", "r1", "0" * 16))
        self.rejects("did not restore", cid, lambda l: set_reg(l, "post", "lr", R.SENTINEL_LR))
        self.rejects("derived post", cid, lambda l: set_reg(l, "post", "r7", "1" * 16))
        self.rejects("ret is not post r3", cid, lambda l: set_field(l, "ret", "0" * 16))
        self.rejects("derived post", cid, lambda l: set_reg(l, "post", "r3", "1" * 16) and set_field(set_reg(l, "post", "r3", "1" * 16), "ret", "1" * 16))

    def test_erase_r12_rules(self):
        erase = "lge/7"
        self.assertEqual(get_field(WORLD.dispatch(False)[7], "lr_slot"), "fef8")
        self.rejects("sentinel", erase, lambda l: set_reg(l, "post", "r12", R.RETURN_LR))
        self.rejects("lr_slot", erase, lambda l: set_field(l, "lr_slot", "-"))
        self.rejects("lr_slot", "lge/0", lambda l: set_field(l, "lr_slot", "fef8"))
        self.rejects("lr_slot", erase, lambda l: set_field(l, "lr_slot", "fef0"))

    def test_non_erase_must_not_substitute_r12(self):
        # lge/0 is not the erase function: its reference 'after' must keep post r12 exactly.
        lge = list(WORLD.lge_lines)
        line = lge[0]
        state = R.parse_state(get_field(line, "after"), "a")
        state["r12"] = R.RETURN_LR
        lge[0] = resign(set_field(line, "after", R.fmt_state(state)))
        with self.assertRaisesRegex(GateError, "derived post"):
            self.run_rederive(lge=lge)

    def test_delta_rules(self):
        cid = "lge/3"
        self.rejects("raw_changed", cid, lambda l: set_field(l, "raw_changed", "999"))
        original = get_field(WORLD.dispatch(False)[3], "raw_delta")
        self.rejects("differ", cid, lambda l: set_field(l, "raw_delta", (original + "," if original else "") + "7fff:aa")
                     and set_field(set_field(l, "raw_delta", (original + "," if original else "") + "7fff:aa"), "raw_changed",
                                   str(WORLD.rows[cid]["raw"].__len__() + 1)))
        erase = "lge/7"
        # The slot bytes of the raw delta must be the sentinel bytes; the normalized ones the return-LR bytes.
        raw = dict(WORLD.rows[erase]["raw"])
        raw[SLOT + 1] = 0x00
        self.rejects("sentinel", erase, lambda l: set_field(set_field(l, "raw_delta", render_delta(raw)), "raw_changed", str(len(raw))))
        lge = list(WORLD.lge_lines)
        norm = R.parse_delta(get_field(lge[7], "delta"), "d")
        norm[SLOT + 2] = 0xAA
        lge[7] = resign(set_field(set_field(lge[7], "delta", render_delta(norm)), "changed", str(len(norm))))
        with self.assertRaisesRegex(GateError, "normalized LR slot"):
            self.run_rederive(lge=lge)
        # Outside the slot the two maps must be identical.
        lge = list(WORLD.lge_lines)
        norm = R.parse_delta(get_field(lge[7], "delta"), "d")
        norm[0x7ffe] = 1
        lge[7] = resign(set_field(set_field(lge[7], "delta", render_delta(norm)), "changed", str(len(norm))))
        with self.assertRaisesRegex(GateError, "outside the LR slot"):
            self.run_rederive(lge=lge)

    def test_ref_changed_count(self):
        lge = list(WORLD.lge_lines)
        lge[4] = resign(set_field(lge[4], "changed", "12345"))
        with self.assertRaisesRegex(GateError, "reference changed"):
            self.run_rederive(lge=lge)

    def test_trace_canonical_and_fixed_tokens(self):
        cid = "lge/5"
        self.rejects("trace", cid, lambda l: set_field(l, "trace", "__imp__sub_820E7440,__imp__sub_820E7440"))
        self.rejects("canonical", cid, lambda l: set_field(l, "canonical", "0" * 64))
        for name, value in (("bound", "none"), ("ctx", "local"), ("entry_ctx", "input")):
            self.rejects("fixed token", cid, lambda l, n=name, v=value: set_field(l, n, v))
        self.rejects("argument count", cid, lambda l: set_field(l, "nargs", "5"))
        self.rejects("only pass 1", cid, lambda l: set_field(l, "pass", "2"))
        self.rejects("identity", cid, lambda l: set_field(l, "id", "lge/6"))
        self.rejects("identity", cid, lambda l: set_field(l, "guest", "820e7328"))

    def test_row_sequence(self):
        lines = WORLD.dispatch(False)
        with self.assertRaisesRegex(GateError, "row count"):
            self.run_rederive(lines[:-1])
        swapped = lines[:]
        swapped[0], swapped[1] = swapped[1], swapped[0]
        with self.assertRaises(GateError):
            self.run_rederive(swapped)
        with self.assertRaisesRegex(GateError, "suite/watched"):
            self.run_rederive(self.edit("lge/0", lambda l: set_field(l, "watched", "1")))
        with self.assertRaisesRegex(GateError, "suite/watched"):
            self.run_rederive(self.edit("lge/0", lambda l: set_field(l, "suite", "lwr")))
        with self.assertRaisesRegex(GateError, "row count"):  # watched rows present in a non-watched run
            self.run_rederive(WORLD.dispatch(True), watched=False)
        with self.assertRaisesRegex(GateError, "row count"):  # watched rows missing from a watched run
            self.run_rederive(WORLD.dispatch(False), watched=True)

    def test_watched_row_equals_ordinary_row(self):
        for mutate in (lambda l: set_reg(l, "post", "r9", "1" * 16), lambda l: set_field(l, "raw_delta", "0:aa"),
                       lambda l: set_field(l, "trace", "x")):
            with self.assertRaises(GateError):
                self.run_rederive(self.edit("lwr/2", mutate, watched_run=True, watched=1), watched=True)
        self.run_rederive(watched=True)

    def test_malformed_rows(self):
        lines = WORLD.dispatch(False)
        for bad in (lines[0].replace("LRGD_CASE_V1|", "LGE_CASE_V1|", 1), lines[0] + "|extra=1",
                    lines[0].replace("|ret=", "|rett=", 1), set_reg(lines[0], "pre", "r0", "xyz")):
            with self.assertRaises(GateError):
                self.run_rederive([bad] + lines[1:])
        with self.assertRaises(GateError):
            self.run_rederive(lines, lge=WORLD.lge_lines[:-1])
        for text in ("1:zz", "1:aa,1:bb", "1:a"):
            with self.assertRaises(GateError):
                R.parse_delta(text, "x")
        self.assertEqual(R.parse_delta("a:0102,fef8:bc", "x"), {0xA: 1, 0xB: 2, 0xFEF8: 0xBC})


class RecordTests(unittest.TestCase):
    def rejects(self, mode, edit, pattern=None, native=True, **kw):
        text = mutated(mode, edit, native, **kw)
        if pattern:
            with self.assertRaisesRegex(GateError, pattern):
                R.validate_records(mode, text, native)
        else:
            with self.assertRaises(GateError):
                R.validate_records(mode, text, native)

    def test_every_mode_validates(self):
        for mode in R.MODES:
            summary = R.validate_records(mode, valid(mode), True)
            self.assertEqual(summary["thunk"], THUNK, mode)
            self.assertEqual(summary["seh"], SEH if mode == "default-dispatch" else None, mode)
        self.assertEqual(R.validate_records("default-dispatch", valid("default-dispatch", False), False)["shm"], [])

    def test_windows_records(self):
        text = valid("default-dispatch", False)
        self.assertEqual(len(text.splitlines()), 18)
        for bad in ("views_unmapped=1|shm_removed=1", "views_unmapped=1|shm_removed=-", "views_unmapped=0|shm_removed=0", "views_unmapped=-"):
            with self.assertRaises(GateError):
                R.validate_records("default-dispatch", text.replace("views_unmapped=-|shm_removed=-", bad), False)
        with self.assertRaises(GateError):  # a latch mode never exists without the native build
            R.validate_records("latch", valid("latch", False), False)
        with self.assertRaises(GateError):  # native records in a non-native claim
            R.validate_records("default-dispatch", valid("default-dispatch"), False)
        with self.assertRaises(GateError):
            R.validate_records("default-dispatch", text, True)

    def test_windows_content_mutations(self):
        text = valid("default-dispatch", False)
        for old, new in (("dispatches=265", "dispatches=264"), ("claims=0", "claims=18"), ("setup_status=0x0", "setup_status=0x1"),
                         ("window_populated=10", "window_populated=9"), ("window_empty=18422", "window_empty=18421"),
                         ("table_size=00ea4bc8", "table_size=00ea4bc0"), ("codegen_flags=00000000", "codegen_flags=00000001"),
                         ("rexcrt_heap=0", "rexcrt_heap=1"), ("register_modules=0", "register_modules=1"),
                         ("ret=0xdeadbabe", "ret=0x0"), ("entered=0", "entered=1"), ("reproduced=1", "reproduced=-"),
                         ("pass=2", "pass=3"), ("symbol=sub_820E7440", "symbol=sub_820E7441"), ("indirect=1", "indirect=0"),
                         ("table_slot=1", "table_slot=0"), ("dispatcher=1|table_slot", "dispatcher=0|table_slot"),
                         ("thread_id=0x4c524744", "thread_id=0x1"), ("xthread=0", "xthread=1"), ("bound_before=0", "bound_before=1"),
                         ("out_of_range_set=refused", "out_of_range_set=accepted"), ("instance=0", "instance=1"),
                         ("mode=default-dispatch|cycle=1|guest=820e7440", "mode=latch|cycle=1|guest=820e7440"),
                         ("lge=124", "lge=123"), ("lwr=8", "lwr=9"), ("watched=0", "watched=8")):
            self.assertIn(old, text, old)
            with self.assertRaises(GateError, msg=old):
                R.validate_records("default-dispatch", text.replace(old, new, 1), False)
        lines = text.splitlines()
        for broken in (lines[:-1], lines[:1] + lines[2:], [lines[1], lines[0]] + lines[2:], lines + [lines[-1]]):
            with self.assertRaises(GateError):
                R.validate_records("default-dispatch", "\n".join(broken) + "\n", False)

    def test_register_order(self):
        text = valid("default-dispatch", False)
        lines = text.splitlines()
        lines[1], lines[2] = lines[2], lines[1]
        with self.assertRaises(GateError):
            R.validate_records("default-dispatch", "\n".join(lines) + "\n", False)

    def test_framing_and_unknown_lines(self):
        text = valid("default-dispatch")
        for bad in (text.rstrip("\n"), text.replace("\n", "\r\n"), text + "LRGD_NOPE_V1|mode=default-dispatch\n",
                    text + "garbage\n", text.replace("LRGD_THREADS_V1", "LRSO_THREADS_V1", 1)):
            with self.assertRaises(GateError):
                R.validate_records("default-dispatch", bad, True)
        with self.assertRaises(GateError):
            R.validate_records("lrgd-nope", text, True)

    def test_mode_in_every_record(self):
        text = valid("latch").replace("mode=latch", "mode=default-dispatch", 1)
        with self.assertRaises(GateError):
            R.validate_records("latch", text, True)

    def test_native_default_stage_rules(self):
        m = "default-dispatch"
        self.rejects(m, lambda b: b.remove(find(b, "SIG", 1, "after-dispatch")), "record")
        self.rejects(m, lambda b: sig_rows(b, 1, "after-dispatch").update({5: handler(0, 1)}), "dispatch changed")
        self.rejects(m, lambda b: sig_rows(b, 1, "after-shutdown").update({11: THUNK_ROW}), "after-shutdown")
        self.rejects(m, lambda b: sig_rows(b, 1, "after-shutdown").update({2: SEH_ROW}), "after-shutdown")
        self.rejects(m, lambda b: sig_rows(b, 1, "after-setup").update({7: THUNK_ROW}), "SIGBUS and SIGFPE")
        self.rejects(m, lambda b: sig_rows(b, 1, "after-setup").update({11: SEH_ROW}), "thunk")
        self.rejects(m, lambda b: sig_rows(b, 1, "after-setup").update({4: handler(S.SA_SIGINFO, THUNK + 8)}), "SIGSEGV and SIGILL")
        self.rejects(m, lambda b: sig_rows(b, 1, "after-setup").update({2: THUNK_ROW}), "Setup changed")
        self.rejects(m, lambda b: sig_rows(b, 0, "after-logging").update({2: SEH_ROW}), "logging")
        self.rejects(m, lambda b: sig_rows(b, 0, "entry").update({11: SEH_ROW}), "not SIG_DFL")
        self.rejects(m, lambda b: sig_rows(b, 1, "after-setup").update({7: handler(S.SA_SIGINFO | S.SA_NODEFER, SEH, "libc.so.6"),
                                                                       8: handler(S.SA_SIGINFO | S.SA_NODEFER, SEH, "libc.so.6")}),
                     "SDK handler")

    def test_native_latch_stage_rules(self):
        for m in ("latch", "latch-cycles", R.TRACED_POSITIVE):
            self.rejects(m, lambda b: sig_rows(b, 1, "after-thunk-removal").update({11: THUNK_ROW}), "thunk removal")
            self.rejects(m, lambda b: sig_rows(b, 1, "after-owner").update({7: OWNER_ROW}), "owner changed")
            self.rejects(m, lambda b: sig_rows(b, 1, "after-dispatch").update({11: THUNK_ROW}), "dispatch changed")
            self.rejects(m, lambda b: sig_rows(b, 1, "after-owner-removal").update({11: OWNER_ROW}), "owner removal")
            self.rejects(m, lambda b: sig_rows(b, 1, "after-shutdown").update({4: THUNK_ROW}), "Shutdown")
            self.rejects(m, lambda b: sig_rows(b, 1, "after-setup").update({7: SEH_ROW}), "latch Setup changed")
            self.rejects(m, lambda b: sig_rows(b, 1, "after-setup").update({8: SEH_ROW, 7: SEH_ROW}), "latch Setup changed")
            self.rejects(m, lambda b: sig_rows(b, 1, "after-setup").update({4: handler(S.SA_SIGINFO, THUNK + 8)}), "SIGSEGV and SIGILL")

    def test_owner_row(self):
        for name, row in (("mask", handler(S.SA_ONSTACK | S.SA_SIGINFO, 0x3300, "lrgd_tests", 0)),
                          ("flags", handler(S.SA_SIGINFO, 0x3300, "lrgd_tests", S.OWNER_MASK)),
                          ("object", handler(S.SA_ONSTACK | S.SA_SIGINFO, 0x3300, "librexruntime.so.1", S.OWNER_MASK)),
                          ("dfl", plain())):
            with self.subTest(name):
                self.rejects("latch", lambda b, r=row: sig_rows(b, 1, "after-owner").update({11: r}))
        text = mutated("latch", lambda b: None).replace("object=lrgd_tests", "object=main")
        R.validate_records("latch", text, True)

    def test_fatal_modes_stop_after_owner_and_thread_state(self):
        for m in R.FATAL_LRGD:
            text = valid(m)
            self.assertNotIn("LRGD_NEGATIVE_V1", text)
            self.assertNotIn("after-dispatch", text)
            self.assertNotIn("after-shutdown", text)
            self.assertTrue(text.splitlines()[-1].startswith("LRGD_THREAD_STATE_V1"))
            self.rejects(m, lambda b: b.append(["RAW", f"LRGD_NEGATIVE_V1|mode={m}|cycle=1|unregistered=820e0000|ret=0xdeadbabe|entered=0"
                                                       "|bound=unchanged|context=args-only|memory=unchanged|out_of_range_set=refused"]))
            self.rejects(m, lambda b: b.pop())

    def test_thread_records(self):
        self.rejects("latch", lambda b: find(b, "THREADS", 1, "after-owner").__setitem__(5, 0), "thread set changed")
        self.rejects("latch", lambda b: find(b, "THREADS", 1, "after-dispatch").__setitem__(3, 3), "thread set changed")
        self.rejects("latch", lambda b: find(b, "THREADS", 0, "entry").__setitem__(4, 3), "thread set changed")
        self.rejects("latch", lambda b: find(b, "THREADS", 0, "entry").__setitem__(3, 1), "thread set changed")
        self.rejects("latch", lambda b: b.remove(find(b, "THREADS", 1, "after-shutdown")))
        self.rejects("default-dispatch", lambda b: b.remove(find(b, "THREADS", 1, "after-setup")))

    def test_latch_records(self):
        self.rejects("latch", lambda b: find(b, "LATCH", "entry").__setitem__(2, 1), "latch record")
        self.rejects("latch", lambda b: find(b, "LATCH", "after-store").__setitem__(2, 0), "latch record")
        self.rejects("latch", lambda b: b.remove(find(b, "LATCH", "after-shutdown")))
        self.rejects("default-dispatch", lambda b: b.insert(5, ["LATCH", "after-store", 1]))
        self.rejects("default-dispatch", lambda b: find(b, "LATCH", "after-shutdown").__setitem__(2, 0), "latch record")
        self.rejects("latch", lambda b: None, "not the SDK library", obj="libc.so.6")

    def test_cycles(self):
        self.rejects("latch-cycles", lambda b: find(b, "RUNTIME", 2).__setitem__(2, "/xenia_memory_1001"), "reuse a shm name")
        self.rejects("latch-cycles", lambda b: sig_rows(b, 2, "after-setup").update({4: handler(S.SA_SIGINFO, THUNK + 4),
                                                                                     11: handler(S.SA_SIGINFO, THUNK + 4)}),
                     "offsets differ")
        self.rejects("latch-cycles", lambda b: b.remove(find(b, "SIG", 2, "after-owner")))
        # Cycle 2 pass 1 reproduces cycle 1: reproduced=1, and only cycle 1 pass 1 is the capture.
        text = valid("latch-cycles")
        self.assertIn("cycle=2|pass=1|lge=124|lwr=8|watched=8|reproduced=1", text)
        self.assertEqual(text.count("reproduced=-"), 1)
        with self.assertRaises(GateError):
            R.validate_records("latch-cycles", text.replace("cycle=2|pass=1|lge=124|lwr=8|watched=8|reproduced=1",
                                                            "cycle=2|pass=1|lge=124|lwr=8|watched=8|reproduced=-"), True)

    def test_runtime_records(self):
        self.rejects("latch", lambda b: find(b, "RUNTIME", 1).__setitem__(5, 64 << 20 << 1), "runtime record")
        text = valid("latch")
        for old, new in (("setup_status=0x0", "setup_status=0x2"), ("membase=0x100000000", "membase=0x200000000"),
                         ("dispatcher=1|membase", "dispatcher=0|membase"), ("tool_mode=1", "tool_mode=0"),
                         ("kernel_shared=1", "kernel_shared=0"), ("shm=/xenia_memory_1001", "shm=/other")):
            with self.assertRaises(GateError, msg=old):
                R.validate_records("latch", text.replace(old, new, 1), True)

    def test_dispatch_and_teardown_counts(self):
        for old, new in (("dispatches=281", "dispatches=265"), ("claims=18", "claims=9"), ("claims=18", "claims=0"),
                         ("watched=8|reproduced=-", "watched=0|reproduced=-"), ("dispatcher=0|views_unmapped=1", "dispatcher=0|views_unmapped=0"),
                         ("shm_removed=1", "shm_removed=0"), ("result=installed", "result=refused-ebusy"), ("segv_beneath=sig_dfl", "segv_beneath=sdk-seh"),
                         ("unregistered=820e0000", "unregistered=82000000")):
            with self.assertRaises(GateError, msg=old):
                R.validate_records("latch", valid("latch").replace(old, new, 1), True)
        for old, new in (("dispatches=265", "dispatches=281"), ("claims=0", "claims=18"), ("result=not-attempted", "result=installed"),
                         ("segv_beneath=sdk-seh", "segv_beneath=sig_dfl")):
            with self.assertRaises(GateError, msg=old):
                R.validate_records("default-dispatch", valid("default-dispatch").replace(old, new, 1), True)

    def test_program_shape(self):
        self.assertEqual(len(R.program("default-dispatch", False)), 18)
        self.assertEqual(len([p for p in R.program("latch-cycles", True) if p[0][0] == "TEARDOWN"]), 2)
        self.assertEqual([p[0] for p in R.program("lrgd-write-guard", True)][-1], ("THREAD_STATE", 1))


class OutputTests(unittest.TestCase):
    refs = WORLD.refs

    def validate(self, mode, texts=None, stdout="auto", native=True):
        texts = texts or texts_for(mode, native)
        stdout = pass_text(mode, native=1 if native else 0) if stdout == "auto" else stdout
        return R.validate_outputs(mode, stdout, texts, self.refs, native)

    def test_positive_modes(self):
        for mode in (*R.POSITIVE, R.TRACED_POSITIVE):
            self.assertEqual(self.validate(mode)["checks"], 77)
        out = self.validate("default-dispatch", native=False)
        self.assertEqual(out["dispatch"]["rows"], 132)
        self.assertIsNone(R.validate_outputs("default-dispatch", None, texts_for("default-dispatch", False), self.refs, False)["checks"])

    def test_pass_line_mutations(self):
        text = pass_text("latch")
        self.assertIsNotNone(R.pass_pattern("latch", True, self.refs).fullmatch(text))
        for old, new in (("mode=latch", "mode=latch-cycles"), ("variant=latch", "variant=default"), ("cycles=1", "cycles=2"),
                         ("lge=124", "lge=123"), ("lwr=8", "lwr=7"), ("watched=8", "watched=0"), ("claims=18", "claims=9"),
                         ("native=1", "native=0"), (self.refs["lge_aggregate"], "0" * 64), (self.refs["lwr_aggregate"], "0" * 64),
                         ("\n", ""), ("checks=77", "checks=x")):
            with self.assertRaises(GateError, msg=old):
                self.validate("latch", stdout=text.replace(old, new, 1))
        with self.assertRaises(GateError):
            self.validate("latch", stdout=text + text)
        with self.assertRaises(GateError):
            self.validate("default-dispatch", stdout=pass_text("default-dispatch", claims=18))
        with self.assertRaises(GateError):
            self.validate("latch-cycles", stdout=pass_text("latch-cycles", claims=18))
        self.validate("latch-cycles", stdout=pass_text("latch-cycles"))

    def test_reference_files(self):
        for name in ("lge", "lwr"):
            texts = texts_for("latch")
            texts[name] = texts[name].replace("model=pass", "model=fail", 1)
            with self.assertRaisesRegex(GateError, "reference"):
                self.validate("latch", texts)
        texts = texts_for("latch")
        texts["lge"] = texts["lge"].rstrip("\n")
        with self.assertRaises(GateError):
            self.validate("latch", texts)

    def test_dispatch_file(self):
        texts = texts_for("latch")
        texts["dispatch"] = texts["dispatch"].replace("ret=", "ret=1", 1)
        with self.assertRaises(GateError):
            self.validate("latch", texts)
        texts = texts_for("latch")
        texts["dispatch"] = texts["dispatch"].rstrip("\n")
        with self.assertRaisesRegex(GateError, "framing"):
            self.validate("latch", texts)
        texts = texts_for("default-dispatch")
        texts["dispatch"] = "".join(l + "\n" for l in WORLD.dispatch(True))  # a watched file in the ordinary variant
        with self.assertRaisesRegex(GateError, "row count"):
            self.validate("default-dispatch", texts)

    def test_latch_files(self):
        texts = texts_for("latch")
        texts["watched"] = texts["watched"].replace("model=pass", "model=fail", 1)
        with self.assertRaisesRegex(GateError, "watched"):
            self.validate("latch", texts)
        texts = texts_for("latch")
        texts["restart"] = texts["restart"].replace("claimed=4|", "claimed=5|", 1)
        with self.assertRaisesRegex(GateError, "restart"):
            self.validate("latch", texts)
        texts = texts_for("latch")
        texts["restart"] = "".join(texts["restart"].splitlines(True)[:-1])
        with self.assertRaises(GateError):
            self.validate("latch", texts)
        for text in (claims_text().replace("page=4|", "page=5|", 1), claims_text().replace("error=7", "error=6", 1) + "x",
                     "".join(claims_text().splitlines(True)[:-1]), claims_text().replace("LRGD_CLAIM_V1", "LWR_CLAIM_V1", 1),
                     claims_text().replace("fn=__imp__sub_820E7440", "fn=__imp__sub_999", 1), ""):
            texts = texts_for("latch")
            texts["claims"] = text
            with self.assertRaises(GateError):
                self.validate("latch", texts)

    def test_default_variant_writes_empty_extra_files(self):
        for name, text in (("watched", WORLD.lwr_text), ("restart", R.expected_restart_text()), ("claims", claims_text())):
            texts = texts_for("default-dispatch")
            texts[name] = text
            with self.assertRaisesRegex(GateError, "non-empty"):
                self.validate("default-dispatch", texts)

    def test_records_failure_propagates(self):
        texts = texts_for("latch")
        texts["record"] = texts["record"].replace("claims=18", "claims=17")
        with self.assertRaises(GateError):
            self.validate("latch", texts)

    def test_expected_restart_text(self):
        self.assertEqual(R.expected_restart_text().count("\n"), 8)
        self.assertNotIn("LWR_", R.expected_restart_text())
        self.assertNotIn("digest", R.expected_restart_text())


class RunTests(unittest.TestCase):
    refs = WORLD.refs

    def test_untraced_modes(self):
        for mode in R.POSITIVE:
            run, reader = make_run(mode)
            summary = R.validate_untraced(run, reader, self.refs)
            self.assertEqual(summary["checks"], 77)

    def test_exit_stderr_timeout_cwd(self):
        for edit in ({"returncode": 1}, {"stderr": "oops"}, {"timeout": True}, {"cwd_entries": ["core"]}, {"stdout": ""},
                     {"mode": R.TRACED_POSITIVE}, {"mode": "lrgd-write-guard"}):
            run, reader = make_run("latch")
            run.update(edit)
            with self.assertRaises(GateError, msg=str(edit)):
                R.validate_untraced(run, reader, self.refs)

    def test_file_digest_and_inventory(self):
        run, reader = make_run("latch")
        run["file_sha256"]["dispatch"] = "0" * 64
        with self.assertRaisesRegex(GateError, "digest"):
            R.validate_untraced(run, reader, self.refs)
        run, reader = make_run("latch")
        del run["files"]["claims"]
        with self.assertRaisesRegex(GateError, "run files"):
            R.validate_untraced(run, reader, self.refs)

    def test_ownership(self):
        for edit in (lambda o: o.update(unlinked_early=True), lambda o: o.update(policy="unlink-after-map"),
                     lambda o: o.update(shm_name="/xenia_memory_999"), lambda o: o.update(inode=1), lambda o: o.update(device=2),
                     lambda o: o.update(allocated_bytes=ALLOCATED + 1), lambda o: o.update(stage="initialized"),
                     lambda o: o.update(pid=1), lambda o: o.update(apparent_size=1)):
            run, reader = make_run("latch-cycles")
            edit(run["ownership"])
            with self.assertRaises(GateError):
                R.validate_untraced(run, reader, self.refs)
        run, reader = make_run("latch")
        run["residue"] = {"present": True, "after": True}
        with self.assertRaises(GateError):
            R.validate_untraced(run, reader, self.refs)

    def test_traced_positive(self):
        run, reader = positive_traced()
        self.assertEqual(len(run["signals"]), 18)
        self.assertEqual(R.validate_traced_positive(run, reader, self.refs)["checks"], 77)

    def test_traced_positive_mutations(self):
        base = R.VA_REGION[0] + 0x4000

        def with_(**edit):
            run, reader = positive_traced()
            run.update(edit)
            return run, reader
        rows = parse = None
        run, reader = positive_traced()
        stderr = run["stderr"]
        lines = stderr.splitlines(True)
        mutations = {
            "status": dict(status="FAIL"), "returncode": dict(returncode=1), "timeout": dict(timeout=True),
            "token": dict(token="zz"), "mode": dict(mode="latch"), "missing row": dict(stderr="".join(lines[:-1])),
            "extra row": dict(stderr=stderr + lines[0]), "partial": dict(stderr=stderr + "LRGD_GATE_V1 tok"),
            "claim count": dict(stderr=stderr.replace("claims=2", "claims=1", 1)),
            "invalidation": dict(stderr=stderr.replace("invalidations=0", "invalidations=1", 1)),
            "phase": dict(stderr=stderr.replace("phase=claim", "phase=begin", 1)),
            "outside region": dict(stderr=stderr.replace(f"address=0x{base:x}", "address=0x1000", 1)),
            "stop count": dict(signals=run["signals"][:-1]),
            "stop kind": dict(signals=[tkill(s["trace"]) if i == 3 else s for i, s in enumerate(run["signals"])]),
            "stop address": dict(signals=[accerr(s["trace"], s["address"] + 8) if i == 0 else s for i, s in enumerate(run["signals"])]),
            "stop trace": dict(signals=[accerr("", s["address"]) if i == 5 else s for i, s in enumerate(run["signals"])]),
            "stop trace partial": dict(signals=[accerr(s["trace"] + "LRGD", s["address"]) if i == 5 else s for i, s in enumerate(run["signals"])]),
            "stdout": dict(stdout=pass_text(R.TRACED_POSITIVE, claims=9)),
        }
        for name, edit in mutations.items():
            r, rd = with_(**edit)
            with self.assertRaises(GateError, msg=name):
                R.validate_traced_positive(r, rd, self.refs)

    def test_traced_positive_expectations(self):
        expected = R.positive_expectations()
        self.assertEqual(len(expected), 18)
        self.assertEqual(expected[:9], expected[9:][:0] + expected[:9])
        self.assertEqual([k for k, _ in expected[:9]], [1, 1, 2, 2, 1, 1, 1, 2, 2])
        self.assertEqual(expected[9], (1, 9))

    def test_fatal_modes_validate(self):
        for mode in R.FATAL_LRGD:
            run, reader = fatal_run(mode)
            R.validate_traced_fatal(run, reader)

    def test_fatal_mutations(self):
        for mode in R.FATAL_LRGD:
            good, _ = fatal_run(mode)
            stderr = good["stderr"]
            other = R.P4_ADDRESS if mode == "lrgd-write-guard" else R.GUARD_ADDRESS
            for name, edit in {
                "returncode": dict(returncode=0), "stdout": dict(stdout="x"), "timeout": dict(timeout=True),
                "status": dict(status="FAIL"), "address": dict(stderr=stderr.replace(f"{good['signals'][0]['address']:x}", f"{other:x}")),
                "phase": dict(stderr=stderr.replace("phase=begin", "phase=claim")),
                "extra row": dict(stderr=stderr + stderr), "no rows": dict(stderr="", signals=[accerr("", other), tkill("")]),
                "one stop": dict(signals=good["signals"][:1]),
                "swapped stops": dict(signals=good["signals"][::-1]),
                "tkill from another pid": dict(signals=[good["signals"][0], {**good["signals"][1], "sender_pid": 1}]),
                "late trace": dict(signals=[accerr("", good["signals"][0]["address"]), good["signals"][1]]),
                "trace changed": dict(signals=[good["signals"][0], tkill("")]),
            }.items():
                run, reader = fatal_run(mode, **edit)
                with self.assertRaises(GateError, msg=f"{mode}: {name}"):
                    R.validate_traced_fatal(run, reader)

    def test_fatal_ownership_policy_and_records(self):
        run, reader = fatal_run("lrgd-unauthorized")
        run["ownership"]["unlinked_early"] = False
        with self.assertRaises(GateError):
            R.validate_traced_fatal(run, reader)
        # The record file must reach the owner but stop before dispatch.
        texts = {"record": valid("latch")}
        run, reader = fatal_run("lrgd-unauthorized")
        run2, reader2 = make_run("lrgd-unauthorized", texts, token=TOKEN, status="PASS", returncode=-11, stdout="",
                                 stderr=run["stderr"], signals=run["signals"])
        with self.assertRaises(GateError):
            R.validate_traced_fatal(run2, reader2)

    def test_modes_have_distinct_addresses(self):
        self.assertEqual(R.GUARD_ADDRESS, 0x100000000 + 0x20011000)
        self.assertEqual(R.P4_ADDRESS, 0x100000000 + 0xA4004000)
        self.assertNotEqual(R.GUARD_ADDRESS, R.P4_ADDRESS)


class GeneratedObjectTests(unittest.TestCase):
    NAMES = [s for _, s in R.MAPPINGS]

    def texts(self):
        nm = "".join(f"{0x100 * i:016x} T __imp__{n}\n{0x100 * i:016x} W {n}\n" for i, n in enumerate(self.NAMES))
        objdump = "".join(f"{0x100 * i:016x} <__imp__{n}>:\n   0:\t55\tpush %rbp\n   4:\te8 00 00 00 00\tcall 9 <__imp__{n}+0x9>\n"
                          f"\t\t5: R_X86_64_PLT32\t_Z7M2EnterPKcR10PPCContext-0x4\n" for i, n in enumerate(self.NAMES))
        return nm, objdump, ""

    def test_good(self):
        out = R.generated_checks(*self.texts())
        self.assertEqual(out["functions"], sorted(self.NAMES))

    def test_missing_weak_alias(self):
        nm, objdump, readelf = self.texts()
        with self.assertRaises(GateError):
            R.generated_checks(nm.replace(" W sub_820E7440", " T sub_820E7440"), objdump, readelf)

    def test_missing_body(self):
        nm, objdump, readelf = self.texts()
        with self.assertRaises(GateError):
            R.generated_checks(nm, objdump.replace("<__imp__sub_820E7440>", "<other>"), readelf)

    def test_external_reference(self):
        nm, objdump, readelf = self.texts()
        extra = objdump.replace("_Z7M2EnterPKcR10PPCContext-0x4", "memcpy-0x4", 1)
        with self.assertRaises(GateError):
            R.generated_checks(nm, extra, readelf)

    def test_stray_generated_function(self):
        nm, objdump, readelf = self.texts()
        with self.assertRaisesRegex(GateError, "unselected"):
            R.generated_checks(nm + "0000000000009000 T __imp__sub_820E0000\n", objdump, readelf)


class PrivateCheckTests(unittest.TestCase):
    PCH = ("#define REX_IMAGE_BASE 0x82000000ull\n#define REX_IMAGE_SIZE 0xCE0000ull\n#define REX_CODE_BASE 0x820E0000ull\n"
           "#define REX_CODE_SIZE 0x7425E4ull\n#define REXCRT_HEAP 0\n")

    def test_parse_pch(self):
        want = {"REX_IMAGE_BASE": 0x82000000, "REX_IMAGE_SIZE": 0xCE0000, "REX_CODE_BASE": 0x820E0000, "REX_CODE_SIZE": 0x7425E4,
                "REXCRT_HEAP": 0}
        self.assertEqual(R.parse_pch(self.PCH), want)
        self.assertEqual(R.parse_pch(self.PCH.replace("\n", "\r\n")), want)
        self.assertEqual(R.parse_pch("// comment\n" + self.PCH + "#define OTHER 5\n"), want)

    def test_parse_pch_rejects(self):
        for bad in (self.PCH.replace("#define REXCRT_HEAP 0\n", ""), self.PCH + "#define REX_CODE_SIZE 0x1ull\n",
                    self.PCH.replace("0x7425E4ull", "(0x7425E4)"), self.PCH.replace("#define REX_IMAGE_BASE", "#define REX_IMAGE_BASEX"),
                    self.PCH.replace("#define REX_IMAGE_SIZE", "// #define REX_IMAGE_SIZE")):
            with self.assertRaises(GateError):
                R.parse_pch(bad)
        self.assertNotEqual(R.parse_pch(self.PCH.replace("0x7425E4ull", "0x7425E5ull")), R.parse_pch(self.PCH))

    CPP = ("constexpr uint32_t kImageBase = 0x82000000u;\nconstexpr uint32_t kImageSize = 0x00CE0000u;\n"
           "constexpr uint32_t kCodeBase = 0x820E0000u;\nconstexpr uint32_t kCodeSize = 0x007425E4u;\n"
           "  info.rexcrt_heap = false;          // Production REXCRT_HEAP 0.\n")

    def test_parse_cpp_constants(self):
        self.assertEqual(R.parse_cpp_constants(self.CPP), R.parse_pch(self.PCH))
        for bad in (self.CPP.replace("0x820E0000u", "0x820E0004u"), self.CPP.replace("constexpr uint32_t kCodeSize", "uint32_t kCodeSize"),
                    self.CPP.replace("= false", "= true"), self.CPP + "constexpr uint32_t kImageBase = 0x1u;\n"):
            try:
                constants = R.parse_cpp_constants(bad)
            except GateError:
                continue
            self.assertNotEqual(constants, R.parse_pch(self.PCH))

    def test_committed_cpp_matches_gate(self):
        text = R.lf(R.CPP).decode()
        constants = R.parse_cpp_constants(text)
        self.assertEqual((constants["REX_IMAGE_BASE"], constants["REX_IMAGE_SIZE"], constants["REX_CODE_BASE"],
                          constants["REX_CODE_SIZE"]), (R.IMAGE_BASE, R.IMAGE_SIZE, R.CODE_BASE, R.CODE_SIZE))
        self.assertEqual(R.parse_cpp_mappings(text), R.MAPPINGS)
        self.assertEqual(R.TABLE_SIZE, 0x00EA4BC8)
        self.assertEqual(R.WINDOW_POPULATED + R.WINDOW_EMPTY, (0x820F8000 - 0x820E6000) // 4)
        with self.assertRaises(GateError):
            R.parse_cpp_mappings(text.replace('{0x820E7440u, sub_820E7440, "sub_820E7440"}', '{0x820E7444u, sub_820E7440, "sub_820E7440"}'))
        with self.assertRaises(GateError):
            R.parse_cpp_mappings(text.replace('{0x820E7440u, sub_820E7440, "sub_820E7440"}', '{0x820E7440u, sub_820E7440, "sub_820E7441"}'))

    INIT = "".join(f"\t{{ 0x{g:08X}, {s} }},\n" for g, s in R.MAPPINGS) + "".join(
        f"        .{f} = false,\n" for f in R.CODEGEN_FLAGS) + "    .rexcrt_heap = REXCRT_HEAP,\n"

    def test_check_init(self):
        self.assertEqual(R.check_init(self.INIT), {"rows": 10, "flags": 8})
        self.assertEqual(R.check_init(self.INIT.replace("\n", "\r\n")), {"rows": 10, "flags": 8})
        for bad in (self.INIT.replace("\t{ 0x820E6D08, sub_820E6D08 },\n", ""), self.INIT.replace("sub_820F7978 }", "sub_820F7979 }"),
                    self.INIT.replace(".skip_lr = false", ".skip_lr = true"), self.INIT.replace("    .rexcrt_heap = REXCRT_HEAP,\n", ""),
                    self.INIT + "\t{ 0x820E7440, sub_820E7440 },\n", self.INIT.replace(".cr_as_local = false,\n", "")):
            with self.assertRaises(GateError):
                R.check_init(bad)


class SourceContractTests(unittest.TestCase):
    EXEC = ("bool FunctionDispatcher::Execute(ThreadState* thread_state, uint32_t address) {\n  PPCFunc* fn = GetFunction(address);\n"
            "  if (!fn) {\n    return false;\n  }\n  auto* previous_thread_state = ThreadState::Get();\n"
            "  ThreadState::Bind(thread_state);\n  ctx->r1.u64 -= 64 + 112;\n  uint64_t previous_lr = ctx->lr;\n"
            "  ctx->lr = 0xBCBCBCBC;\n  fn(*ctx, memory_->virtual_membase());\n  ctx->lr = previous_lr;\n"
            "  ctx->r1.u64 += 64 + 112;\n  ThreadState::Bind(previous_thread_state);\n  return true;\n}\n")

    def test_synthetic_execute_private(self):
        R.fact_execute_private(self.EXEC)
        for needle in ("ctx->lr = 0xBCBCBCBC;", "ctx->r1.u64 -= 64 + 112;", "ThreadState::Bind(previous_thread_state);"):
            with self.assertRaises(GateError):
                R.fact_execute_private(self.EXEC.replace(needle, "", 1))
        with self.assertRaises(GateError):  # restore before the call
            R.fact_execute_private(self.EXEC.replace("fn(*ctx, memory_->virtual_membase());\n  ctx->lr = previous_lr;",
                                                     "ctx->lr = previous_lr;\n  fn(*ctx, memory_->virtual_membase());"))
        with self.assertRaises(GateError):
            R.fact_execute_private("")

    ARGS = ("uint64_t FunctionDispatcher::Execute(ThreadState* thread_state, uint32_t address, uint64_t args[],\n"
            "                                     size_t arg_count) {\n" + "".join(f"  ctx->r{3 + i}.u64 = args[{i}];\n" for i in range(8))
            + "  if (arg_count > 8) {\n  }\n  if (!Execute(thread_state, address)) {\n    return 0xDEADBABE;\n  }\n"
              "  return ctx->r3.u64;\n}\n")

    def test_synthetic_execute_args(self):
        R.fact_execute_args(self.ARGS)
        for i in range(8):
            with self.assertRaises(GateError):
                R.fact_execute_args(self.ARGS.replace(f"  ctx->r{3 + i}.u64 = args[{i}];\n", "", 1))
        with self.assertRaises(GateError):  # r4 and r5 swapped
            R.fact_execute_args(self.ARGS.replace("ctx->r4.u64 = args[1];", "ctx->r5.u64 = args[2];", 1))
        with self.assertRaises(GateError):
            R.fact_execute_args(self.ARGS.replace("0xDEADBABE", "0"))

    def test_dispatch_inventory(self):
        clean = {"a.cpp": "int f() { return 1; }\n", "b.cpp": "void g();\n"}
        self.assertEqual(set(R.fact_dispatch_inventory(clean)), set(R.DISPATCH_TOKENS))
        for token in R.DISPATCH_TOKENS:
            with self.assertRaises(GateError, msg=token):
                R.fact_dispatch_inventory({**clean, "b.cpp": f"x {token} y\n"})

    def test_prelude_lookup(self):
        text = f"#define REX_LOOKUP_FUNC(x, y) \\\n  (*(PPCFunc**)(x + {R.LOOKUP_TEXT}))\n"
        R.fact_prelude_lookup([R.LOOKUP_TEMPLATE], text)
        for files, body in (([], text), ([R.LOOKUP_TEMPLATE, "resources/other.inja"], text), ([R.LOOKUP_TEMPLATE], text.replace("* 2", "* 4")),
                            ([R.LOOKUP_TEMPLATE], text.replace("REX_IMAGE_SIZE", "REX_IMAGE_BASE"))):
            with self.assertRaises(GateError):
                R.fact_prelude_lookup(files, body)

    def test_thread_state_synthetic(self):
        cpp = ("thread_local ThreadState* thread_state_ = nullptr;\n\nThreadState::ThreadState(uint32_t thread_id, uint32_t stack_base, "
               "uint32_t pcr_address,\n                         memory::Memory* memory) {\n  context_->r1.u64 = stack_base;\n"
               "  context_->r13.u64 = pcr_address;\n}\n\nvoid ThreadState::Bind(ThreadState* thread_state) {\n"
               "  thread_state_ = thread_state;\n}\n")
        header, disp = "  alignas(64)::PPCContext context_storage_{};\n", "  static constexpr uint32_t kThunkReserveSize = 0x10000;\n"
        R.fact_thread_state(cpp, header, disp)
        for args in ((cpp.replace("thread_local ", ""), header, disp), (cpp.replace("pcr_address;", "0;"), header, disp),
                     (cpp.replace("thread_state_ = thread_state;", ""), header, disp), (cpp, header.replace("alignas(64)", ""), disp),
                     (cpp, header, disp.replace("0x10000", "0x20000"))):
            with self.assertRaises(GateError):
                R.fact_thread_state(*args)


def sdk_available():
    try:
        return S.git_out(SDK, "cat-file", "-t", R.SDK_PIN).strip() == b"commit"
    except (GateError, OSError):
        return False


@unittest.skipUnless(sdk_available(), "pinned SDK checkout unavailable")
class PinnedSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = {p: S.pinned_text(SDK, p) for p in R.LRGD_SDK_FILES}

    def edit(self, key, old, new, count=1, after=None):
        text = self.text[key]
        start = text.index(after) if after else 0
        at = text.index(old, start)
        return text[:at] + new + text[at + len(old):] if count == 1 else text.replace(old, new)

    def test_real_contract(self):
        contract = R.source_contract(SDK)
        self.assertEqual(len(contract["facts"]), 8)
        self.assertEqual(len(contract["lrso"]["facts"]), 13)
        self.assertEqual(R.fact_count(contract), 21)
        self.assertEqual(contract["lrso"], S.source_contract(SDK))
        self.assertEqual(contract["facts"]["g_prelude_lookup"]["template"], R.LOOKUP_TEMPLATE)
        self.assertEqual(R.source_contract(SDK), contract)

    def test_every_dispatch_needle_is_required(self):
        path = "src/system/function_dispatcher.cpp"
        header = "bool FunctionDispatcher::Execute(ThreadState* thread_state, uint32_t address) {"
        for needle in ("PPCFunc* fn = GetFunction(address);", "return false;", "auto* previous_thread_state = ThreadState::Get();",
                       "ThreadState::Bind(thread_state);", "ctx->r1.u64 -= 64 + 112;", "uint64_t previous_lr = ctx->lr;",
                       "ctx->lr = 0xBCBCBCBC;", "fn(*ctx, memory_->virtual_membase());", "ctx->lr = previous_lr;",
                       "ctx->r1.u64 += 64 + 112;", "ThreadState::Bind(previous_thread_state);"):
            with self.assertRaises(GateError, msg=needle):
                R.fact_execute_private(self.edit(path, needle, "", after=header))
        header = "uint64_t FunctionDispatcher::Execute(ThreadState* thread_state, uint32_t address, uint64_t args[],"
        for needle in [f"ctx->r{3 + i}.u64 = args[{i}];" for i in range(8)] + ["if (arg_count > 8)", "if (!Execute(thread_state, address))",
                                                                                   "return 0xDEADBABE;", "return ctx->r3.u64;"]:
            with self.assertRaises(GateError, msg=needle):
                R.fact_execute_args(self.edit(path, needle, "", after=header))

    def test_setup_image_needles(self):
        path = "src/system/runtime.cpp"
        header = "X_STATUS Runtime::Setup(const rex::PPCImageInfo& image_info, RuntimeConfig config) {"
        R.fact_setup_image(self.text[path])
        for needle in ("X_STATUS status = Setup(std::move(config));", "codegen_flags_ = image_info.codegen_flags;",
                       "InitializeFunctionTable(image_info.code_base, image_info.code_size,", "/*is_entrypoint=*/true",
                       "image_info.func_mappings[i].guest != 0", "function_dispatcher_->SetFunction(guest, host)", "if (rejected > 0)"):
            with self.assertRaises(GateError, msg=needle):
                R.fact_setup_image(self.edit(path, needle, "", after=header))

    def test_memory_table_needles(self):
        path = "src/system/xmemory.cpp"
        R.fact_memory_table(self.text[path])
        for needle, after in (("uint32_t table_base = image_base + image_size;", "bool Memory::InitializeFunctionTable("),
                              ("uint32_t table_size = (code_size + kThunkReserveSize) * 2;", "bool Memory::InitializeFunctionTable("),
                              ("heaps_.v80000000.AllocFixed(", "bool Memory::InitializeFunctionTable("),
                              ("Zero(table_base, table_size);", "bool Memory::InitializeFunctionTable("),
                              ("uint64_t offset = (uint64_t(guest_address) - entry.code_base) * 2;", "bool Memory::SetFunction("),
                              ("*slot = host_function;", "bool Memory::SetFunction(")):
            with self.assertRaises(GateError, msg=needle):
                R.fact_memory_table(self.edit(path, needle, "", after=after))

    def test_resolve_and_thread_state(self):
        R.fact_resolve_indirect(self.text["src/system/function_dispatcher.cpp"])
        with self.assertRaises(GateError):
            R.fact_resolve_indirect(self.edit("src/system/function_dispatcher.cpp", "Runtime* runtime = Runtime::instance();", ""))
        R.fact_thread_state(self.text["src/system/thread_state.cpp"], self.text["include/rex/system/thread_state.h"],
                            self.text["include/rex/system/function_dispatcher.h"])

    def test_real_template_contains_lookup(self):
        files = S.pinned_grep_files(SDK, [R.LOOKUP_TEXT], ["resources"])
        self.assertEqual(files, [R.LOOKUP_TEMPLATE])

    def test_real_dispatch_inventory(self):
        counts = R.fact_dispatch_inventory({p: self.text[p] for p in ("src/system/function_dispatcher.cpp", "src/system/thread_state.cpp")})
        self.assertTrue(all(n == 0 for per_file in counts.values() for n in per_file.values()))


class InventoryTests(unittest.TestCase):
    def test_source_inventory(self):
        names = R.source_files()
        for f in R.OWN_FILES:
            self.assertIn(R.REL + f, names)
        for name in S.source_files():
            self.assertIn(name, names)
        self.assertEqual(names, sorted(set(names)))

    def test_own_files_exist_and_are_lf(self):
        for f in R.OWN_FILES:
            path = HERE / f
            if path.exists():
                self.assertNotIn(b"\r\n", path.read_bytes() if f != "lrgd_tests.cpp" else R.lf(path), f)

    def test_no_generated_code_in_gate_files(self):
        for f in ("lrgd_gate.py", "test_lrgd_gate.py"):
            self.assertNotIn(b"\nDEFINE_REX_FUNC(", (HERE / f).read_bytes())

    def test_fatal_registration(self):
        R.register_fatal()
        for mode in R.FATAL_LRGD:
            self.assertIn(mode, L.FATAL)
        self.assertEqual(len(set(L.FATAL)), len(L.FATAL))

    def test_modes(self):
        self.assertEqual(sorted(R.MODES), sorted([*R.POSITIVE, R.TRACED_POSITIVE, *R.FATAL_LRGD]))
        self.assertEqual(R.MODES["latch-cycles"], ("latch", 2))
        self.assertEqual(R.CLAIMS_PER_CYCLE, 18)
        self.assertEqual(R.CONFIG_KEYS, ["clang++_O0", "clang++_O2", "g++_O0", "g++_O2"])

    def test_file_env_names(self):
        self.assertEqual(sorted(R.FILE_ENV), sorted(R.FILE_NAMES))
        text = R.lf(R.CPP).decode()
        for env in R.FILE_ENV.values():
            self.assertIn(f'"{env}"', text)


REAL_RUNS = sorted(R.WINDOWS_WORK.glob("run_O*_*")) if R.WINDOWS_WORK.is_dir() else []


@unittest.skipUnless(R.LGE_REFERENCE.is_file() and R.LWR_REFERENCE.is_file() and REAL_RUNS,
                     "private references and Windows run directories unavailable")
class RealWindowsRunTests(unittest.TestCase):
    """Reads private files only to validate them; nothing is copied into tracked content."""

    @classmethod
    def setUpClass(cls):
        cls.refs = R.load_raw_references(R.LGE_REFERENCE, R.LWR_REFERENCE)

    def test_all_runs_pass_and_agree(self):
        digests = {R.check_run(d, self.refs)["dispatch_sha256"] for d in REAL_RUNS}
        self.assertEqual(len(digests), 1)

    def test_mutated_copy_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, edit in (("dispatch.txt", lambda b: b.replace(b"|ret=", b"|ret=1", 1)),
                               ("lge.txt", lambda b: b.replace(b"model=pass", b"model=fail", 1)),
                               ("records.txt", lambda b: b.replace(b"dispatches=265", b"dispatches=266"))):
                target = Path(tmp) / name.split(".")[0]
                shutil.copytree(REAL_RUNS[0], target)
                (target / name).write_bytes(edit((target / name).read_bytes()))
                with self.assertRaises(GateError, msg=name):
                    R.check_run(target, self.refs)


if __name__ == "__main__":
    unittest.main()

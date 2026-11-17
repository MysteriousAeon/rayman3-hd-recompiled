"""Validator tests for lrso_gate.py (synthetic records only; no build, no game, no generated code)."""
import copy
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lrso_gate as R  # noqa: E402

L = R.L
GateError = R.GateError
R.register_fatal()
TOKEN = "0123456789abcdef0123456789abcdef"
PID = 4242
ADDRESS = R.EXPECTED_ADDRESS
THUNK, SEH = 0x1A2B30, 0x1C4D50
RESIDUE = {"present": False, "after": False}
SDK = R.DEFAULT_SDK


# ------------------------------------------------------------------ synthetic records

def plain(state="dfl"):
    return {"state": state, "siginfo": 0, "flags": 0, "mask": 0, "object": "-", "offset": 0}


def handler(flags, offset, obj="librexruntime.so.1", mask=0):
    return {"state": "fn", "siginfo": 1, "flags": flags, "mask": mask, "object": obj, "offset": offset}


THUNK_ROW = handler(R.SA_SIGINFO, THUNK)
SEH_ROW = handler(R.SA_SIGINFO | R.SA_NODEFER, SEH)
OWNER_ROW = handler(R.SA_ONSTACK | R.SA_SIGINFO, 0x3300, "lrso_tests", R.OWNER_MASK)


def entry_rows():
    rows = {s: plain() for s in R.SIGNALS}
    rows[13] = plain("ign")
    return rows


def with_rows(base, **named):
    rows = copy.deepcopy(base)
    for sig, row in named.items():
        rows[int(sig[1:])] = copy.deepcopy(row)
    return rows


def build(mode):
    """Parts of a valid record file for `mode`, in the order the fixture writes them."""
    variant, cycles = R.MODES[mode][:2]
    fatal = mode in R.FATAL_LRSO
    entry = entry_rows()
    stages = [[0, "entry", entry], [0, "after-logging", copy.deepcopy(entry)]]
    threads = [[0, "entry"], [0, "after-logging"]]
    teardown, handoff, restart, runtime = [], [], [], []
    for c in range(1, cycles + 1):
        if variant == "default":
            setup = with_rows(entry, s4=THUNK_ROW, s11=THUNK_ROW, s7=SEH_ROW, s8=SEH_ROW)
            seh = with_rows(entry, s4=SEH_ROW, s7=SEH_ROW, s8=SEH_ROW, s11=SEH_ROW)
            stages.append([c, "after-setup", setup])
            if mode == "default-originals":
                stages += [[c, "after-thunk-removal", copy.deepcopy(seh)], [c, "after-owner-refused", copy.deepcopy(seh)]]
                handoff.append(f"LRSO_HANDOFF_V1|mode={mode}|cycle={c}|result=refused-ebusy|segv_beneath=sdk-seh")
            else:
                handoff.append(f"LRSO_HANDOFF_V1|mode={mode}|cycle={c}|result=not-attempted|segv_beneath=unobserved")
            stages.append([c, "after-shutdown", seh])
            threads += [[c, "after-setup"], [c, "after-owner"], [c, "after-shutdown"]]
        else:
            owner = with_rows(entry, s11=OWNER_ROW)
            stages += [[c, "after-setup", with_rows(entry, s4=THUNK_ROW, s11=THUNK_ROW)],
                       [c, "after-thunk-removal", copy.deepcopy(entry)], [c, "after-owner", owner]]
            threads += [[c, "after-setup"], [c, "after-owner"]]
            handoff.append(f"LRSO_HANDOFF_V1|mode={mode}|cycle={c}|result=installed|segv_beneath=sig_dfl")
            if not fatal:
                stages += [[c, "after-restart", copy.deepcopy(owner)], [c, "after-owner-removal", copy.deepcopy(entry)],
                           [c, "after-shutdown", copy.deepcopy(entry)]]
                threads += [[c, "after-restart"], [c, "after-shutdown"]]
                restart.append(f"LRSO_RESTART_V1|mode={mode}|cycle={c}|page=4|target_offset=0x4100|width=4|length=3|error=7"
                               "|claims=1|invalidations=1|region_equal=1|watch_cleared=1")
        runtime.append({"cycle": c, "shm": f"/xenia_memory_{1000 + c}", "inode": 500 + c, "device": 41})
        if not fatal:
            teardown.append(f"LRSO_TEARDOWN_V1|mode={mode}|cycle={c}|instance=0|kernel_shared=0|mmio=0|views_unmapped=1"
                            "|shm_removed=1|altstack_disabled=1")
    latch = [["entry", 0]] + ([["after-store", 1]] if variant == "latch" else []) + [["after-setup", 1]]
    if not fatal:
        latch.append(["after-shutdown", 1])
    return {"mode": mode, "stages": stages, "threads": [t + [2, 2, 1] for t in threads], "latch": latch,
            "latch_object": "librexruntime.so.1", "runtime": runtime, "teardown": teardown, "handoff": handoff,
            "restart": restart}


def render(parts):
    mode = parts["mode"]
    lines = []
    for cycle, stage, rows in parts["stages"]:
        for sig in R.SIGNALS:
            r = rows[sig]
            lines.append(f"LRSO_SIG_V1|mode={mode}|cycle={cycle}|stage={stage}|sig={sig}|state={r['state']}|siginfo={r['siginfo']}"
                         f"|flags=0x{r['flags']:x}|mask=0x{r['mask']:016x}|object={r['object']}|offset=0x{r['offset']:x}")
    for cycle, stage, count, baseline, equal in [(t[0], t[1], t[2], t[3], t[4]) for t in parts["threads"]]:
        lines.append(f"LRSO_THREADS_V1|mode={mode}|cycle={cycle}|stage={stage}|count={count}|baseline={baseline}|equal={equal}")
    for stage, value in parts["latch"]:
        lines.append(f"LRSO_LATCH_V1|mode={mode}|stage={stage}|value={value}|object={parts['latch_object']}")
    for r in parts["runtime"]:
        lines.append(f"LRSO_RUNTIME_V1|mode={mode}|cycle={r['cycle']}|setup_status=0x0|instance=1|kernel_shared=1|mmio=1"
                     f"|membase=0x100000000|tool_mode=1|shm={r['shm']}|inode={r['inode']}|device={r['device']}")
    lines += parts["teardown"] + parts["handoff"] + parts["restart"]
    return "\n".join(lines) + "\n"


def stage_rows(parts, cycle, stage):
    return next(rows for c, s, rows in parts["stages"] if (c, s) == (cycle, stage))


def valid(mode):
    return render(build(mode))


def mutated(mode, edit):
    parts = build(mode)
    edit(parts)
    return render(parts)


# ------------------------------------------------------------------ synthetic runs

def ownership(fatal, cycles=1):
    # Names the last cycle's object, as lrso_tests.cpp writes it (see generator above).
    return {"format": "LRB_OWNERSHIP_V1", "stage": "started", "pid": PID, "shm_name": f"/xenia_memory_{1000 + cycles}",
            "virtual_membase": 1 << 32, "apparent_size": 0x120001000, "allocated_bytes": 4096, "unlinked_early": fatal,
            "policy": "unlink-after-map" if fatal else "sdk-contract"}


def pass_text(mode, checks=77, **over):
    variant, cycles, claims, invalidations = R.MODES[mode]
    fields = {"mode": mode, "variant": variant, "cycles": cycles, "claims": claims, "invalidations": invalidations,
              "checks": checks, "tasks": 2}
    fields.update(over)
    return ("LRSO PASS mode={mode} variant={variant} cycles={cycles} claims={claims} invalidations={invalidations} "
            "checks={checks} tasks={tasks} native=1\n").format(**fields)


def untraced_run(mode, **over):
    run = {"mode": mode, "pid": PID, "returncode": 0, "stdout": pass_text(mode), "stderr": "", "cwd_entries": [],
           "ownership": ownership(False, 3 if mode == "latch-cycles" else 1), "residue": dict(RESIDUE)}
    run.update(over)
    return run


def witness(mode, phase, claims, invalidations, address=ADDRESS, token=TOKEN):
    return f"LRSO_GATE_V1 token={token} mode={mode} phase={phase} claims={claims} invalidations={invalidations} address=0x{address:x}\n"


def accerr(trace, address=ADDRESS):
    return {"signal": 11, "code": 2, "errno": 0, "address": address, "sender_pid": 0, "trace": trace}


def tkill(trace):
    return {"signal": 11, "code": -6, "errno": 0, "address": 0, "sender_pid": PID, "trace": trace}


def positive_traced(**over):
    line = witness(R.TRACED_POSITIVE, "claim", 1, 0)
    run = {"mode": R.TRACED_POSITIVE, "token": TOKEN, "status": "PASS", "pid": PID, "returncode": 0,
           "stdout": pass_text(R.TRACED_POSITIVE), "stderr": line, "signals": [accerr("")],
           "ownership": ownership(False), "residue": dict(RESIDUE)}
    run.update(over)
    return run


def fatal_run(mode, **over):
    address = ADDRESS
    if mode == "latch-consumed":
        rows = [witness(mode, "begin", 0, 0), witness(mode, "claimed", 1, 0), witness(mode, "rewatched", 1, 1)]
        stderr = "".join(rows)
        stops = [accerr(rows[0]), accerr(stderr), tkill(stderr)]
    else:
        stderr = witness(mode, "begin", 0, 0, address)
        stops = [accerr(stderr), tkill(stderr)]
    run = {"mode": mode, "token": TOKEN, "status": "PASS", "pid": PID, "returncode": -11, "stdout": "", "stderr": stderr,
           "signals": stops, "ownership": ownership(True), "residue": dict(RESIDUE)}
    run.update(over)
    return run


# ------------------------------------------------------------------ binary text samples

HEADER = "   Num:    Value          Size Type    Bind   Vis      Ndx Name\n"
NULL_ROW = "     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND \n"


def symtab(row):
    return "Symbol table '.dynsym' contains 2 entries:\n" + HEADER + NULL_ROW + row + "\n"


EXE_UND = symtab("     1: 0000000000000000     1 OBJECT  UNIQUE DEFAULT  UND _ZN3rex8platform17g_seh_initializedE")
EXE_DEFINED = symtab("     1: 0000000000004010     1 OBJECT  UNIQUE DEFAULT   26 _ZN3rex8platform17g_seh_initializedE")
SDK_DEFINED = symtab("     1: 0000000000004010     1 OBJECT  UNIQUE DEFAULT   26 _ZN3rex8platform17g_seh_initializedE")
DYNAMIC_OK = " 0x000000000000001e (FLAGS)              BIND_NOW\n 0x000000006ffffffb (FLAGS_1)            Flags: NOW\n"
RELOCS = "0000000000005f00  0000000300000006 R_X86_64_GLOB_DAT 0000000000004010 _ZN3rex8platform17g_seh_initializedE + 0\n"
NM_TEXT = ("00000000001a2b30 t _ZN3rex4arch16ExceptionHandler24ExceptionHandlerCallbackEiP9siginfo_tPv\n"
           "00000000001c4d50 t _ZN3rex8platformL14signal_handlerEiP9siginfo_tPv\n"
           "0000000000004010 u _ZN3rex8platform17g_seh_initializedE\n")


# ------------------------------------------------------------------ tests

class RecordTests(unittest.TestCase):
    def fails(self, mode, text, fragment=None):
        with self.assertRaises(GateError) as ctx:
            R.validate_records(mode, text)
        if fragment:
            self.assertIn(fragment, str(ctx.exception))

    def test_every_mode_validates(self):
        for mode in R.MODES:
            with self.subTest(mode=mode):
                summary = R.validate_records(mode, valid(mode))
                self.assertEqual(summary["thunk"], THUNK)
                self.assertEqual(summary["seh"], None if mode not in ("default", "default-originals") else SEH)

    def test_cycles_have_distinct_shm(self):
        summary = R.validate_records("latch-cycles", valid("latch-cycles"))
        self.assertEqual(len(set(summary["shm"])), 3)

    def test_seh_left_on_sigsegv(self):
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 1, "after-setup").update({11: copy.deepcopy(SEH_ROW)})))

    def test_sigbus_changed_in_latch(self):
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 1, "after-setup").update({7: copy.deepcopy(SEH_ROW)})))

    def test_extra_changed_signal(self):
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 1, "after-setup").update({34: copy.deepcopy(THUNK_ROW)})))
        self.fails("default", mutated("default", lambda p: stage_rows(p, 1, "after-setup").update({34: copy.deepcopy(THUNK_ROW)})))

    def test_latch_shutdown_not_entry(self):
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 1, "after-shutdown").update({11: copy.deepcopy(THUNK_ROW)})))

    def test_default_shutdown_not_seh(self):
        for mode in ("default", "default-originals"):
            self.fails(mode, mutated(mode, lambda p: stage_rows(p, 1, "after-shutdown").update({11: plain()})))

    def test_thread_count(self):
        def edit(p):
            p["threads"][3][2] = 3
        self.fails("latch", mutated("latch", edit))

        def unequal(p):
            p["threads"][3][4] = 0
        self.fails("latch", mutated("latch", unequal))

    def test_missing_stage(self):
        def edit(p):
            p["stages"] = [s for s in p["stages"] if s[1] != "after-restart"]
        self.fails("latch", mutated("latch", edit), "stage sequence")

        def edit_default(p):
            p["stages"] = [s for s in p["stages"] if s[1] != "after-owner-refused"]
        self.fails("default-originals", mutated("default-originals", edit_default), "stage sequence")

    def test_duplicated_signal_line(self):
        lines = valid("latch").split("\n")
        index = next(i for i, line in enumerate(lines) if "stage=after-setup|sig=11|" in line)
        self.fails("latch", "\n".join(lines[:index] + [lines[index]] + lines[index:]))

    def test_missing_signal_line(self):
        lines = valid("latch").split("\n")
        index = next(i for i, line in enumerate(lines) if "stage=after-owner|sig=30|" in line)
        self.fails("latch", "\n".join(lines[:index] + lines[index + 1:]))

    def test_owner_mask_flags_object(self):
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 1, "after-owner").update(
            {11: handler(R.SA_ONSTACK | R.SA_SIGINFO, 0x3300, "lrso_tests", 0x40)})))
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 1, "after-owner").update(
            {11: handler(R.SA_SIGINFO, 0x3300, "lrso_tests", R.OWNER_MASK)})))
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 1, "after-owner").update(
            {11: handler(R.SA_ONSTACK | R.SA_SIGINFO, 0x3300, "librexruntime.so.1", R.OWNER_MASK)})))
        # The executable may be named main when dladdr has no name.
        parts = build("latch")
        stage_rows(parts, 1, "after-owner")[11]["object"] = "main"
        stage_rows(parts, 1, "after-restart")[11]["object"] = "main"
        R.validate_records("latch", render(parts))

    def test_owner_changes_other_signal(self):
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 1, "after-owner").update({7: copy.deepcopy(OWNER_ROW)})))

    def test_restart_changes_disposition(self):
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 1, "after-restart").update({11: copy.deepcopy(THUNK_ROW)})))

    def test_thunk_removal_not_entry(self):
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 1, "after-thunk-removal").update({11: copy.deepcopy(THUNK_ROW)})))

    def test_default_originals_stages(self):
        self.fails("default-originals", mutated("default-originals", lambda p: stage_rows(p, 1, "after-thunk-removal").update({11: plain()})))
        self.fails("default-originals", mutated("default-originals", lambda p: stage_rows(p, 1, "after-owner-refused").update({11: copy.deepcopy(OWNER_ROW)})))
        self.fails("default-originals", mutated("default-originals", lambda p: stage_rows(p, 1, "after-thunk-removal").update({34: copy.deepcopy(SEH_ROW)})))

    def test_default_handler_shapes(self):
        same = handler(R.SA_SIGINFO | R.SA_NODEFER, THUNK)
        self.fails("default", mutated("default", lambda p: stage_rows(p, 1, "after-setup").update({7: copy.deepcopy(same), 8: copy.deepcopy(same)})))
        self.fails("default", mutated("default", lambda p: stage_rows(p, 1, "after-setup").update({4: copy.deepcopy(SEH_ROW)})))
        self.fails("default", mutated("default", lambda p: stage_rows(p, 1, "after-setup").update({7: handler(R.SA_SIGINFO, SEH)})))
        self.fails("default", mutated("default", lambda p: stage_rows(p, 1, "after-setup").update({11: handler(R.SA_SIGINFO, THUNK, "main")})))

    def test_entry_and_logging(self):
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 0, "entry").update({11: copy.deepcopy(THUNK_ROW)})))
        self.fails("latch", mutated("latch", lambda p: stage_rows(p, 0, "after-logging").update({40: copy.deepcopy(THUNK_ROW)})))

    def test_latch_values(self):
        def entry_one(p):
            p["latch"][0][1] = 1
        self.fails("latch", mutated("latch", entry_one))
        self.fails("default", mutated("default", lambda p: p["latch"].insert(1, ["after-store", 1])))
        self.fails("latch", mutated("latch", lambda p: p["latch"].pop(1)))

        def clear_after_shutdown(p):
            p["latch"][-1][1] = 0
        self.fails("latch", mutated("latch", clear_after_shutdown))
        self.fails("latch", mutated("latch", lambda p: p.update(latch_object="lrso_tests")))

    def test_cycles_duplicate_shm_or_inode(self):
        def same_name(p):
            p["runtime"][2]["shm"] = p["runtime"][0]["shm"]
        self.fails("latch-cycles", mutated("latch-cycles", same_name))

        def same_inode(p):  # tmpfs may reuse an inode number after unlink: allowed.
            p["runtime"][1]["inode"] = p["runtime"][0]["inode"]
        R.validate_records("latch-cycles", mutated("latch-cycles", same_inode))

    def test_restart_records(self):
        self.fails("latch", valid("latch").replace("claims=1|invalidations=1", "claims=2|invalidations=1"))
        self.fails("latch-cycles", mutated("latch-cycles", lambda p: p["restart"].pop()))
        self.fails("default", valid("default") + build("latch")["restart"][0].replace("mode=latch", "mode=default") + "\n")

    def test_handoff_and_teardown(self):
        self.fails("latch", valid("latch").replace("segv_beneath=sig_dfl", "segv_beneath=sdk-seh"))
        self.fails("default-originals", valid("default-originals").replace("refused-ebusy", "installed"))
        self.fails("latch", valid("latch").replace("shm_removed=1", "shm_removed=0"))
        self.fails("latch-unregistered", mutated("latch-unregistered", lambda p: p["teardown"].append(build("latch")["teardown"][0])))

    def test_runtime_record(self):
        self.fails("latch", valid("latch").replace("setup_status=0x0", "setup_status=0x1"))
        self.fails("latch", valid("latch").replace("membase=0x100000000", "membase=0x200000000"))
        self.fails("latch", valid("latch").replace("shm=/xenia_memory_1001", "shm=/other"))

    def test_framing_and_unknown_lines(self):
        self.fails("latch", valid("latch")[:-1])
        self.fails("latch", valid("latch").replace("\n", "\r\n"))
        self.fails("latch", valid("latch") + "LRSO_EXTRA_V1|x\n")
        self.fails("latch", valid("latch").replace("mode=latch|", "mode=default|", 1))

    def test_offsets_differ_between_cycles(self):
        def edit(p):
            for stage in ("after-setup",):
                stage_rows(p, 2, stage)[11]["offset"] = THUNK + 0x10
                stage_rows(p, 2, stage)[4]["offset"] = THUNK + 0x10
        self.fails("latch-cycles", mutated("latch-cycles", edit))

    def test_fatal_records_stop_after_owner(self):
        for mode in R.FATAL_LRSO:
            self.fails(mode, valid(R.TRACED_POSITIVE).replace("mode=latch-traced-positive", "mode=" + mode))
            self.fails(mode, mutated(mode, lambda p: p["handoff"].clear()))


class RunTests(unittest.TestCase):
    def untraced(self, run):
        return R.validate_untraced(run, valid(run["mode"]))

    def fails(self, run, text=None):
        with self.assertRaises(GateError):
            R.validate_untraced(run, text if text is not None else valid(run["mode"]))

    def test_positive_modes(self):
        for mode in R.POSITIVE:
            with self.subTest(mode=mode):
                self.assertEqual(self.untraced(untraced_run(mode))["checks"], 77)

    def test_stdout_variants(self):
        for mode in R.POSITIVE:
            with self.subTest(mode=mode):
                good = pass_text(mode)
                for bad in (good.replace("native=1", "native=0"), good.replace("tasks=2", "tasks=3"), good + good,
                            good[:-1], good.replace("claims=", "claims=9"), good.replace("variant=", "variant=x"),
                            good.replace(f"mode={mode}", "mode=other"), "", good.replace(" checks=77", "")):
                    self.fails(untraced_run(mode, stdout=bad))
        self.fails(untraced_run("latch", stdout=pass_text("latch", cycles=3)))
        self.fails(untraced_run("default", stdout=pass_text("latch")))

    def test_exit_stderr_timeout(self):
        self.fails(untraced_run("latch", returncode=1))
        self.fails(untraced_run("latch", returncode=-11))
        self.fails(untraced_run("latch", stderr="warning\n"))
        self.fails(untraced_run("latch", timeout=True))

    def test_cwd_not_empty(self):
        self.fails(untraced_run("latch", cwd_entries=["rex.log"]))
        run = untraced_run("latch")
        del run["cwd_entries"]
        self.fails(run)

    def test_ownership(self):
        self.fails(untraced_run("latch", ownership=ownership(True)))
        wrong = ownership(False)
        wrong["shm_name"] = "/xenia_memory_999"  # Not the runtime record's object.
        self.fails(untraced_run("latch", ownership=wrong))
        self.fails(untraced_run("latch", residue={"present": True, "after": True}))
        self.fails(untraced_run("latch", ownership=None, ownership_error="missing ownership record"))

    def test_untraced_rejects_traced_modes(self):
        self.fails(untraced_run("latch-unregistered"))

    def test_traced_positive(self):
        self.assertEqual(R.validate_traced_positive(positive_traced(), valid(R.TRACED_POSITIVE))["checks"], 77)

    def traced_fails(self, run):
        with self.assertRaises(GateError):
            R.validate_traced_positive(run, valid(R.TRACED_POSITIVE))

    def test_traced_positive_mutations(self):
        line = witness(R.TRACED_POSITIVE, "claim", 1, 0)
        self.traced_fails(positive_traced(signals=[accerr(""), accerr("")]))
        self.traced_fails(positive_traced(signals=[]))
        self.traced_fails(positive_traced(signals=[accerr("", ADDRESS + 4)]))
        self.traced_fails(positive_traced(signals=[accerr(line)]))
        self.traced_fails(positive_traced(signals=[tkill("")]))
        self.traced_fails(positive_traced(stderr=line + line))
        self.traced_fails(positive_traced(stderr="", signals=[accerr("")]))
        self.traced_fails(positive_traced(stderr=witness(R.TRACED_POSITIVE, "claim", 0, 0)))
        self.traced_fails(positive_traced(stderr=witness(R.TRACED_POSITIVE, "claim", 1, 1)))
        other = ADDRESS + 8
        self.traced_fails(positive_traced(stderr=witness(R.TRACED_POSITIVE, "claim", 1, 0, other), signals=[accerr("", other)]))
        self.traced_fails(positive_traced(stderr=line.replace("LRSO_GATE_V1", "LWR_GATE_V1")))
        self.traced_fails(positive_traced(stderr=line.replace(TOKEN, "f" * 32)))
        self.traced_fails(positive_traced(returncode=-11))
        self.traced_fails(positive_traced(stdout=pass_text(R.TRACED_POSITIVE, claims=0)))
        self.traced_fails(positive_traced(ownership=ownership(True)))
        self.traced_fails(positive_traced(status="FAIL"))

    def test_fatal_modes_validate(self):
        for mode in R.FATAL_LRSO:
            with self.subTest(mode=mode):
                R.validate_traced_fatal(fatal_run(mode), valid(mode))

    def fatal_fails(self, run):
        with self.assertRaises(GateError):
            R.validate_traced_fatal(run, valid(run["mode"]))

    def test_fatal_stop_sequences(self):
        for mode in ("latch-unregistered", "latch-unauthorized", "latch-foreign-session"):
            with self.subTest(mode=mode):
                run = fatal_run(mode)
                stops = run["signals"]
                self.fatal_fails(fatal_run(mode, signals=stops[:1]))  # missing TKILL
                self.fatal_fails(fatal_run(mode, signals=[stops[0], stops[0], stops[1]]))  # extra ACCERR
                self.fatal_fails(fatal_run(mode, signals=[stops[1], stops[1]]))
                self.fatal_fails(fatal_run(mode, signals=[accerr(""), stops[1]]))  # row written after, not at, the stop
                self.fatal_fails(fatal_run(mode, signals=[stops[0], tkill("")]))  # trace != final stderr
                self.fatal_fails(fatal_run(mode, signals=[accerr(stops[0]["trace"], ADDRESS + 4), stops[1]]))
                self.fatal_fails(fatal_run(mode, signals=[stops[0], {**stops[1], "sender_pid": 1}]))

    def test_fatal_consumed_counters(self):
        mode = "latch-consumed"
        rows = [witness(mode, "begin", 0, 0), witness(mode, "claimed", 1, 0), witness(mode, "rewatched", 1, 1)]
        full = "".join(rows)
        for bad_rows in ([rows[0], rows[1], witness(mode, "rewatched", 1, 0)], [rows[0], witness(mode, "claimed", 0, 0), rows[2]],
                         [rows[0], rows[2]], [rows[0], rows[1], rows[2], rows[2]],
                         [rows[0], rows[1], witness(mode, "rewatched", 2, 1)]):
            stderr = "".join(bad_rows)
            self.fatal_fails(fatal_run(mode, stderr=stderr, signals=[accerr(rows[0]), accerr(stderr), tkill(stderr)]))
        self.fatal_fails(fatal_run(mode, signals=[accerr(rows[0]), accerr(rows[0] + rows[1]), tkill(full)]))
        self.fatal_fails(fatal_run(mode, signals=[accerr(rows[0]), tkill(full)]))
        self.fatal_fails(fatal_run(mode, signals=[accerr(rows[0]), accerr(full), accerr(full), tkill(full)]))

    def test_fatal_exit_and_ownership(self):
        mode = "latch-unregistered"
        self.fatal_fails(fatal_run(mode, returncode=0))
        self.fatal_fails(fatal_run(mode, returncode=-6))
        self.fatal_fails(fatal_run(mode, stdout="x"))
        self.fatal_fails(fatal_run(mode, ownership=ownership(False)))
        self.fatal_fails(fatal_run(mode, residue={"present": True, "after": True}))
        self.fatal_fails(fatal_run(mode, stderr=fatal_run(mode)["stderr"].replace("LRSO_GATE_V1", "LWR_GATE_V1")))
        self.fatal_fails(fatal_run(mode, token=None))

    def test_fatal_records_must_reach_owner(self):
        with self.assertRaises(GateError):
            R.validate_traced_fatal(fatal_run("latch-unregistered"), valid("latch"))
        with self.assertRaises(GateError):
            R.validate_traced_fatal(fatal_run("latch-unregistered"), mutated("latch-unregistered", lambda p: p["stages"].pop()))


class BinaryTests(unittest.TestCase):
    def check(self, exe=EXE_UND, sdk=SDK_DEFINED, dynamic=DYNAMIC_OK, relocs=RELOCS):
        return R.check_latch_binary(exe, sdk, dynamic, relocs)

    def test_good(self):
        result = self.check()
        self.assertFalse(result["exe_defines_latch"])
        self.assertTrue(result["sdk_relocation_against_latch"])
        self.assertFalse(self.check(relocs="")["sdk_relocation_against_latch"])
        self.assertEqual(self.check(exe="")["exe_references_latch"], False)

    def test_exe_defines_latch(self):
        with self.assertRaises(GateError):
            self.check(exe=EXE_DEFINED)

    def test_sdk_latch_not_exported(self):
        for row in ("     1: 0000000000004010     1 OBJECT  UNIQUE HIDDEN    26 _ZN3rex8platform17g_seh_initializedE",
                    "     1: 0000000000004010     1 OBJECT  LOCAL  DEFAULT   26 _ZN3rex8platform17g_seh_initializedE",
                    "     1: 0000000000004010     1 OBJECT  UNIQUE PROTECTED 26 _ZN3rex8platform17g_seh_initializedE",
                    "     1: 0000000000000000     1 OBJECT  UNIQUE DEFAULT  UND _ZN3rex8platform17g_seh_initializedE"):
            with self.subTest(row=row), self.assertRaises(GateError):
                self.check(sdk=symtab(row))
        with self.assertRaises(GateError):
            self.check(sdk=symtab("     1: 0000000000004010     1 OBJECT  UNIQUE DEFAULT   26 other"))
        row = "     1: 0000000000004010     1 OBJECT  UNIQUE DEFAULT   26 _ZN3rex8platform17g_seh_initializedE"
        with self.assertRaises(GateError):
            self.check(sdk=symtab(row + "\n" + row))
        for bind in ("WEAK", "GLOBAL"):
            self.check(sdk=symtab(row.replace("UNIQUE", bind)))

    def test_symbolic(self):
        with self.assertRaises(GateError):
            self.check(dynamic=" 0x000000000000001e (FLAGS)              SYMBOLIC BIND_NOW\n")
        with self.assertRaises(GateError):
            self.check(dynamic=" 0x0000000000000010 (SYMBOLIC)           0x0\n" + DYNAMIC_OK)
        self.check(dynamic=" 0x000000000000001e (FLAGS)              BIND_NOW\n")

    def test_provenance(self):
        self.assertEqual(R.check_provenance(NM_TEXT, THUNK, SEH), "symbolized")
        self.assertEqual(R.check_provenance("", THUNK, SEH), "unsymbolized")
        self.assertEqual(R.check_provenance(NM_TEXT.splitlines()[2] + "\n", THUNK, SEH), "unsymbolized")
        with self.assertRaises(GateError):
            R.check_provenance(NM_TEXT, THUNK + 4, SEH)
        with self.assertRaises(GateError):
            R.check_provenance(NM_TEXT, THUNK, SEH + 4)
        with self.assertRaises(GateError):
            R.check_provenance(NM_TEXT.splitlines()[0] + "\n", THUNK, SEH)

    def test_cross_run(self):
        base = {"thunk": THUNK, "seh": None}
        runs = [{**base, "seh": SEH}, dict(base), dict(base)]
        self.assertEqual(R.check_cross_run(runs, NM_TEXT), {"thunk": hex(THUNK), "seh": hex(SEH), "provenance": "symbolized"})
        with self.assertRaises(GateError):
            R.check_cross_run(runs + [{"thunk": THUNK + 4, "seh": None}], "")
        with self.assertRaises(GateError):
            R.check_cross_run(runs + [{"thunk": THUNK, "seh": SEH + 4}], "")
        with self.assertRaises(GateError):
            R.check_cross_run([{"thunk": SEH, "seh": SEH}], "")
        with self.assertRaises(GateError):
            R.check_cross_run([dict(base)], "")


def sdk_available():
    try:
        return R.git_out(SDK, "cat-file", "-t", R.SDK_PIN).strip() == b"commit"
    except (GateError, OSError):
        return False


@unittest.skipUnless(sdk_available(), "pinned SDK checkout unavailable")
class SourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = {p: R.pinned_text(SDK, p) for p in (
            "include/rex/platform/seh.h", "include/rex/platform/exceptions.h", "src/core/seh_posix.cpp",
            "src/system/runtime.cpp", "src/core/exception_handler_posix.cpp", "src/system/kernel_state.cpp",
            "src/core/threading_posix.cpp", "src/core/timer_queue.cpp")}
        cls.signals = {p: R.pinned_text(SDK, p) for p in R.pinned_grep_files(SDK, R.SIGNAL_TOKENS, ["src"])
                       if not p.endswith("_win.cpp")}
        cls.threads = {p: R.pinned_text(SDK, p) for p in R.pinned_grep_files(SDK, R.THREAD_TOKENS, ["src"])
                       if not p.endswith("_win.cpp")}

    def edit(self, key, old, new, count=1):
        text = self.text[key]
        self.assertGreaterEqual(text.count(old), 1, old)
        return text.replace(old, new, count)

    def test_real_contract(self):
        result = R.source_contract(SDK)
        self.assertEqual(len(result["facts"]), 13)
        self.assertEqual(result["facts"]["g_signal_inventory"], R.PINNED_SIGNAL_INVENTORY)
        self.assertEqual(result["facts"]["h_thread_inventory"], R.PINNED_THREAD_INVENTORY)

    def test_latch_declaration(self):
        R.fact_latch_declaration(self.text["include/rex/platform/seh.h"])
        decl = "inline std::atomic<bool> g_seh_initialized{false};"
        for new in ("std::atomic<bool> g_seh_initialized{false};", "inline std::atomic<bool> g_seh_initialized{true};", ""):
            with self.assertRaises(GateError):
                R.fact_latch_declaration(self.edit("include/rex/platform/seh.h", decl, new))
        with self.assertRaises(GateError):  # moved before the namespace
            R.fact_latch_declaration(decl + "\n" + self.edit("include/rex/platform/seh.h", decl, ""))

    def test_seh_posix(self):
        R.fact_seh_posix(self.text["src/core/seh_posix.cpp"])
        for old, new in (("  if (g_seh_initialized.exchange(true)) {", "  if (false) {"),
                         ("sigaction(SIGBUS, &sa, nullptr);", ""),
                         ("sa.sa_flags = SA_SIGINFO | SA_NODEFER;", "sa.sa_flags = SA_SIGINFO;"),
                         ("throw SehException(code, address);", "abort();"),
                         ("signal(sig, SIG_DFL);\n    raise(sig);\n    return;", "return;")):
            with self.subTest(old=old), self.assertRaises(GateError):
                R.fact_seh_posix(self.edit("src/core/seh_posix.cpp", old, new))
        with self.assertRaises(GateError):
            R.fact_seh_posix(self.edit("src/core/seh_posix.cpp", "sigaction(SIGILL, &sa, nullptr);",
                                       "sigaction(SIGILL, &sa, nullptr);\n  sigaction(SIGUSR1, &sa, nullptr);"))

    def test_latch_files(self):
        paths = ["include/rex/platform/seh.h", "src/core/seh_posix.cpp", "src/core/seh_win.cpp"]
        R.fact_latch_files(paths)
        for bad in (paths[:2], paths + ["src/foo.cpp"], paths[:2] + ["src/foo.cpp"]):
            with self.assertRaises(GateError):
                R.fact_latch_files(bad)

    def test_initialize_seh_sites(self):
        sites = {"src/system/runtime.cpp": [(105, "  rex::initialize_seh();")],
                 "include/rex/platform/exceptions.h": [(15, " * @usage       1. Call rex::initialize_seh() at startup"),
                                                       (89, "inline void initialize_seh() {")]}
        eh, sh = self.text["include/rex/platform/exceptions.h"], self.text["include/rex/platform/seh.h"]
        R.fact_initialize_seh_sites(sites, eh, sh)
        extra = copy.deepcopy(sites)
        extra["src/other.cpp"] = [(1, "  rex::initialize_seh();")]
        twice = copy.deepcopy(sites)
        twice["src/system/runtime.cpp"].append((300, "  rex::initialize_seh();"))
        moved = {"src/system/runtime.cpp": sites["src/system/runtime.cpp"]}
        for bad in (extra, twice, moved):
            with self.assertRaises(GateError):
                R.fact_initialize_seh_sites(bad, eh, sh)
        with self.assertRaises(GateError):
            R.fact_initialize_seh_sites(sites, eh.replace("platform::seh_initialize();", "platform::seh_initialize(); extra();"), sh)

    def test_setup_order(self):
        text = self.text["src/system/runtime.cpp"]
        R.fact_setup_order(text)
        moved = text.replace("  rex::initialize_seh();\n", "", 1).replace(
            "  export_resolver_ = std::make_unique<runtime::ExportResolver>();",
            "  rex::initialize_seh();\n  export_resolver_ = std::make_unique<runtime::ExportResolver>();", 1)
        self.assertNotEqual(moved, text)
        with self.assertRaises(GateError):
            R.fact_setup_order(moved)
        for old in ("memory_->Initialize()", "if (config.audio_factory)", "if (tool_mode_) {"):
            with self.subTest(old=old), self.assertRaises(GateError):
                R.fact_setup_order(text.replace(old, "", 1))
        swapped = text.replace("if (config.input_factory)", "if (config.XX)", 1).replace(
            "if (config.kernel_init)", "if (config.input_factory)", 1)
        with self.assertRaises(GateError):
            R.fact_setup_order(swapped)

    def test_shutdown_order(self):
        text = self.text["src/system/runtime.cpp"]
        R.fact_shutdown_order(text)
        for injected in ("  sigaction(SIGSEGV, nullptr, nullptr);\n", "  signal(SIGSEGV, SIG_DFL);\n", "  seh_reset();\n"):
            with self.subTest(injected=injected), self.assertRaises(GateError):
                R.fact_shutdown_order(text.replace("  memory_.reset();\n", "  memory_.reset();\n" + injected, 1))
        with self.assertRaises(GateError):
            R.fact_shutdown_order(text.replace("  memory_.reset();\n", "", 1).replace(
                "  file_system_.reset();\n", "  memory_.reset();\n  file_system_.reset();\n", 1))

    def test_setup_vfs(self):
        text = self.text["src/system/runtime.cpp"]
        R.fact_setup_vfs(text)
        with self.assertRaises(GateError):
            R.fact_setup_vfs(text.replace("bool Runtime::SetupVfs() {\n  if (game_data_root_.empty()) {",
                                          "bool Runtime::SetupVfs() {\n  auto early = std::filesystem::absolute(x);\n"
                                          "  if (game_data_root_.empty()) {", 1))
        with self.assertRaises(GateError):
            R.fact_setup_vfs(text.replace("    return true;\n  }\n\n  auto abs_game_root", "    return false;\n  }\n\n  auto abs_game_root", 1))

    def test_exception_handler(self):
        key = "src/core/exception_handler_posix.cpp"
        R.fact_exception_handler(self.text[key])
        with self.assertRaises(GateError):  # SIGBUS no longer inside the mac block
            R.fact_exception_handler(self.edit(key, "#if REX_PLATFORM_MAC\n    if (sigaction(SIGBUS, &signal_handler",
                                               "    if (sigaction(SIGBUS, &signal_handler"))
        with self.assertRaises(GateError):
            R.fact_exception_handler(self.edit(key, "signal_handler.sa_flags = SA_SIGINFO;", "signal_handler.sa_flags = SA_SIGINFO | SA_ONSTACK;"))
        with self.assertRaises(GateError):
            R.fact_exception_handler(self.edit(key, "sigaction(SIGILL, &signal_handler, &original_sigill_handler_)",
                                               "sigaction(SIGILL, &signal_handler, nullptr)"))
        with self.assertRaises(GateError):
            R.fact_exception_handler(self.edit(key, "  if (!has_any) {", "  if (true) {"))
        with self.assertRaises(GateError):
            R.fact_exception_handler(self.edit(key, "sigaction(SIGILL, &original_sigill_handler_, NULL)", "0"))

    def test_signal_inventory(self):
        R.fact_signal_inventory(self.signals)
        for path, text in (("src/core/exception_handler_posix.cpp", "\nvoid x() { sigaction(SIGUSR1, nullptr, nullptr); }\n"),
                           ("src/core/dbg_posix.cpp", "\nvoid y() { std::signal(SIGINT, SIG_DFL); }\n"),
                           ("src/core/seh_posix.cpp", "\nvoid z() { signal(SIGPIPE, SIG_IGN); }\n")):
            mutated_texts = dict(self.signals)
            mutated_texts[path] += text
            with self.subTest(path=path), self.assertRaises(GateError):
                R.fact_signal_inventory(mutated_texts)
        with self.assertRaises(GateError):
            R.fact_signal_inventory({**self.signals, "src/new/file.cpp": "void f() { sigaction(SIGUSR2, 0, 0); }"})
        removed = dict(self.signals)
        del removed["src/core/dbg_posix.cpp"]
        with self.assertRaises(GateError):
            R.fact_signal_inventory(removed)
        # Windows-only files are outside the inventory.
        R.fact_signal_inventory({**self.signals, "src/core/x_win.cpp": "void f() { signal(SIGINT, SIG_DFL); }"})

    def test_thread_inventory(self):
        R.fact_thread_inventory(self.threads)
        for token in R.THREAD_TOKENS:
            with self.subTest(token=token), self.assertRaises(GateError):
                R.fact_thread_inventory({**self.threads, "src/new/thread.cpp": "void f() { " + token + "...); }"})
        with self.assertRaises(GateError):
            R.fact_thread_inventory({**self.threads, "src/system/kernel_state.cpp":
                                     self.threads["src/system/kernel_state.cpp"] + "\nauto t = new XHostThread(this);\n"})

    def test_kernel_state_threads(self):
        key = "src/system/kernel_state.cpp"
        R.fact_kernel_state_threads(self.text[key])
        header = "KernelState::KernelState(Runtime* emulator)"
        for token in R.THREAD_TOKENS:
            with self.subTest(token=token), self.assertRaises(GateError):
                R.fact_kernel_state_threads(self.edit(key, header, header + " /* " + token + " */"))
        text = self.text[key]
        hosted = text.replace("new XHostThread(", "new XOtherThread(", 1) + "\nvoid KernelState::Other() {\n  new XHostThread(this);\n}\n"
        with self.assertRaises(GateError):
            R.fact_kernel_state_threads(hosted)

    def test_thread_signal_sites(self):
        key = "src/core/threading_posix.cpp"
        R.fact_thread_signal_sites(self.text[key])
        with self.assertRaises(GateError):
            R.fact_thread_signal_sites(self.text[key] + "\nvoid other() {\n  install_signal_handler(SignalType::kThreadSuspend);\n}\n")
        with self.assertRaises(GateError):
            R.fact_thread_signal_sites(self.text[key].replace("install_signal_handler(SignalType::", "install_signal_handler_x(SignalType::"))

    def test_timer_queue(self):
        key = "src/core/timer_queue.cpp"
        R.fact_timer_queue(self.text[key])
        with self.assertRaises(GateError):
            R.fact_timer_queue(self.edit(key, "std::jthread([this](std::stop_token stop_token)", "std::thread([this]"))


class InventoryTests(unittest.TestCase):
    def test_source_inventory(self):
        files = R.source_files()
        for name in ("lrso_gate.py", "test_lrso_gate.py", "lrso_tests.cpp", "CMakeLists.txt", "README.md"):
            self.assertIn(R.REL + name, files)
        base = "tools/experiments/"
        for name in ("linux_runtime_bootstrap/lrb_owner.c", "linux_runtime_bootstrap/lrb_bootstrap.cpp",
                     "linux_write_watch_restart/lwr_restart.c", "linux_write_watch_restart/lwr_test_leaf.S",
                     "linux_write_watch_restart/lwr_gate.py", "linux_guest_entry/lge_gate.py"):
            self.assertIn(base + name, files)
        self.assertEqual(files, sorted(set(files)))

    def test_no_generated_code(self):
        for name in R.OWN_FILES:
            path = HERE / name
            if path.exists():
                data = path.read_bytes()
                needle = b"\nDEFINE_REX" + b"_FUNC("
                self.assertNotIn(needle, data, name)
        self.assertFalse(any("generated" in n or "private" in n for n in R.source_files()))

    def test_fatal_registration(self):
        for mode in R.FATAL_LRSO:
            self.assertIn(mode, L.FATAL)
        self.assertNotIn("latch", L.FATAL)
        for mode in R.FATAL_LRSO:
            self.assertEqual(R.MODES[mode][0], "latch")

    def test_config_keys(self):
        self.assertEqual(len(R.CONFIG_KEYS), 4)
        self.assertEqual(sorted(R.NATIVE_NAMES), sorted(set(R.NATIVE_NAMES)))


if __name__ == "__main__":
    unittest.main()

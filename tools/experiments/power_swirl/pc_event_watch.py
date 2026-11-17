"""Read-only, bounded observer for a PERSON'S already-running original-PC session.

No game starter, injection, debugger, input, capture, process suspension or writes.
Requires the supplied executable hash; outputs derived metadata under private/ only.
PC layout candidates are from pinned Raymap and verified offline against local data
and native handlers. Live behavior is unverified until the person's first run.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = ROOT / "private/work/power_swirl/pc_pickup"
DEFAULT_GAME = Path("D:/Games/Rayman 3/Rayman3.exe")
EXE_SHA256 = "64deefd3a7b14a32124aa9b31ebba84e1a7c9a4a54ee40d9b65b4043ff1be15c"
EXE_SIZE = 2916704
ROOTS = (0x7D9934, 0x7D9A4C)
MAX_OBJECTS, MAX_SUBANIMS = 512, 24
READ_RIGHTS = 0x1000 | 0x0010  # QUERY_LIMITED_INFORMATION | VM_READ only
MAX_LOG_BYTES = 1024 * 1024
POWER_NAMES = ("Vortex", "Throttle Copter", "LockJaw", "Shock Rocket", "Heavy Metal Fist", "none")


class Refused(Exception):
    pass


class UnstableSample(Refused):
    pass


def valid_pointer(value):
    return isinstance(value, int) and 0x10000 <= value < 0x80000000 and value % 4 == 0


class Reader:
    def __init__(self, read):
        self.raw = read
        self.total = 0

    def read(self, address, length):
        if not valid_pointer(address) or not 1 <= length <= 256:
            raise Refused("invalid bounded read")
        self.total += length
        if self.total > 8 * 1024 * 1024:
            raise Refused("read budget exhausted")
        value = self.raw(address, length)
        if len(value) != length:
            raise Refused("incomplete read")
        return value

    def word(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]


def actor_chain(r, actor):
    data3d, std, _, brain = struct.unpack("<4I", r.read(actor, 16))
    if r.word(std + 4) != 0:  # supplied PC YLT_RaymanModel index
        raise Refused("actor is not the expected model")
    mind = r.word(brain)
    model = r.word(mind)
    normal = r.word(model)
    if r.word(normal + 4) != 72:
        raise Refused("unexpected player behavior count")
    schema = r.word(model + 8)
    mem = r.word(mind + 12)
    if r.word(mem) != model + 8 or r.read(schema + 12, 1)[0] < 3:
        raise Refused("designer schema identity mismatch")
    info = r.word(schema + 4)
    if (r.word(info + 32), r.word(info + 36)) != (0, 5):
        raise Refused("power mirror must be Int variable2 at buffer offset0")
    return data3d, r.word(mem + 8)


def discover(r):
    pending = [r.word(a) for a in ROOTS]
    seen = set()
    while pending:
        so = pending.pop()
        if not so or so in seen:
            continue
        if len(seen) >= MAX_OBJECTS:
            raise Refused("object traversal budget exhausted")
        seen.add(so)
        kind, data, child, _, _, sibling = struct.unpack("<6I", r.read(so, 24))
        pending.extend((child, sibling))
        if kind != 2 or not valid_pointer(data):
            continue
        try:
            actor_chain(r, data)
        except Refused:
            continue
        return data
    raise Refused("player not found in bounded world traversal; no scan fallback")


def sample(r, actor):
    data3d, buffer = actor_chain(r, actor)
    power = r.word(buffer)
    if power > 5:
        raise Refused("invalid power mirror")
    state = r.word(data3d + 4)
    animation = r.word(state + 4)
    anim_index = struct.unpack("<H", r.read(animation + 12, 2))[0]
    if anim_index >= 185:
        raise Refused("main animation outside verified player bank")
    sub = head = r.word(data3d + 0x188)
    subs, seen = [], set()
    while sub:
        if sub in seen or len(subs) >= MAX_SUBANIMS:
            raise Refused("invalid or excessive sub-animation chain")
        seen.add(sub)
        next_sub, _, _, entry = struct.unpack("<4I", r.read(sub, 16))
        ref = r.word(entry + 4)
        index = struct.unpack("<H", r.read(ref + 12, 2))[0]
        if index >= 185:
            raise Refused("subanimation outside verified player bank")
        flag = r.word(sub + 0x1C)
        frame = struct.unpack("<f", r.read(sub + 0x20, 4))[0]
        subs.append({"animation": index, "flag": flag,
                     "frame_parameter": frame if math.isfinite(frame) else None})
        sub = next_sub
    if (r.word(buffer), r.word(data3d + 4), r.word(data3d + 0x188)) != (power, state, head):
        raise UnstableSample("player changed during asynchronous sample")
    return {"power_mirror": power, "main_animation": anim_index,
            "subanimations": subs,
            "known_helix_animation_active": anim_index in (91, 169) or any(s["animation"] in (91, 169) for s in subs)}


def output_path(path):
    path = Path(path).resolve()
    private = OUTPUT_ROOT.resolve()
    if private != ROOT.resolve() / "private/work/power_swirl/pc_pickup":
        raise Refused("output folder redirects outside the fixed evidence location")
    if not path.is_relative_to(private) or path.suffix != ".jsonl":
        raise Refused("output must be a new .jsonl file under private/work/power_swirl/pc_pickup/")
    if path.exists():
        raise Refused("refusing to overwrite existing evidence")
    return path


def windows_api():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_size_t,
                                           ctypes.POINTER(ctypes.c_size_t)]
    api.ReadProcessMemory.restype = wintypes.BOOL
    api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                   wintypes.LPWSTR,
                                                   ctypes.POINTER(wintypes.DWORD)]
    api.QueryFullProcessImageNameW.restype = wintypes.BOOL
    api.IsWow64Process2.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.USHORT),
                                   ctypes.POINTER(wintypes.USHORT)]
    api.IsWow64Process2.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def verify_executable(path):
    path = Path(path).resolve()
    if path.name.lower() != "rayman3.exe" or path.stat().st_size != EXE_SIZE:
        raise Refused("executable identity/size mismatch")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXE_SHA256:
        raise Refused("executable hash mismatch")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if (data[:2] != b"MZ" or data[pe:pe+4] != b"PE\0\0"
        or struct.unpack_from("<H", data, pe+4)[0] != 0x14C
        or struct.unpack_from("<H", data, pe+24)[0] != 0x10B
        or struct.unpack_from("<I", data, pe+52)[0] != 0x400000
        or struct.unpack_from("<H", data, pe+94)[0] & 0x40):
        raise Refused("expected fixed-base x86 PE32 executable")
    return path


class Process:
    def __init__(self, pid, expected_path=DEFAULT_GAME):
        self.api = windows_api()
        self.handle = self.api.OpenProcess(READ_RIGHTS, False, pid)
        if not self.handle:
            raise Refused("cannot open existing process read-only (access denied or process gone); no elevation fallback")
        try:
            size = wintypes.DWORD(32768)
            value = ctypes.create_unicode_buffer(size.value)
            if not self.api.QueryFullProcessImageNameW(self.handle, 0, value, ctypes.byref(size)):
                raise Refused("cannot verify process image")
            path = Path(value.value)
            if path.resolve() != Path(expected_path).resolve():
                raise Refused("process executable identity mismatch")
            verify_executable(path)
            machine, native = wintypes.USHORT(), wintypes.USHORT()
            if not self.api.IsWow64Process2(self.handle, ctypes.byref(machine), ctypes.byref(native)):
                raise Refused("cannot verify process architecture")
            if (machine.value, native.value) != (0x14C, 0x8664):
                raise Refused("expected x86 game under x64 Windows WOW64")
            # Confirm the fixed image mapping before following any player addresses.
            image = self.read(0x400000, 64)
            pe = struct.unpack_from("<I", image, 60)[0]
            if image[:2] != b"MZ" or not 64 <= pe <= 0x1000:
                raise Refused("fixed executable mapping unavailable")
            if self.read(0x400000 + pe, 6) != b"PE\0\0\x4c\x01":
                raise Refused("loaded image is not expected x86 mapping")
        except Exception:
            self.close()
            raise

    def read(self, address, length):
        data = ctypes.create_string_buffer(length)
        count = ctypes.c_size_t()
        if not self.api.ReadProcessMemory(self.handle, address, data, length, ctypes.byref(count)):
            raise Refused("process memory unavailable; stop without fallback")
        if count.value != length:
            raise Refused("incomplete process memory read")
        return data.raw[:count.value]

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pid", type=int)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME)
    ap.add_argument("--preflight", action="store_true", help="Verify disk executable and Python only; no attachment or output")
    ap.add_argument("--seconds", type=int, default=30, choices=range(1, 61), metavar="1..60")
    args = ap.parse_args()
    process = None
    try:
        if os.name != "nt" or struct.calcsize("P") != 8:
            raise Refused("requires 64-bit Python on x64 Windows")
        if args.preflight:
            verify_executable(args.game)
            print("PC_SWIRL_PREFLIGHT PASS: exact-hash fixed-base x86 PE32; 64-bit Python. No process attached.")
            return 0
        if args.pid is None or args.pid <= 0 or args.out is None:
            raise Refused("pid must name an already-running game")
        out = output_path(args.out)
        process = Process(args.pid, args.game)
        reader = Reader(process.read)
        actor = discover(reader)
        # Validate the full sample before creating an evidence file.
        first = sample(reader, actor)
        out.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        with out.open("x", encoding="utf-8", newline="\n") as log:
            record(log, {"kind": "header", "schema": 2, "pid": args.pid,
                                  "exe_sha256": EXE_SHA256, "hz": 20,
                                  "seconds": args.seconds, "read_only": True,
                                  "verified_architecture": "x86-WOW64/x64", "handle_rights": "0x1010",
                                  "objects_directly_observed": False,
                                  "frame_parameter_is_current_frame": False,
                                  "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            print("PC_SWIRL_OBSERVER READY", out, flush=True)
            observe(log, reader, actor, first, args.seconds, start)
        print("PC_SWIRL_OBSERVER COMPLETE", out)
        return 0
    except KeyboardInterrupt:
        print("PC_SWIRL_OBSERVER STOPPED by person")
        return 130
    except (Refused, OSError, ValueError, AttributeError) as exc:
        print("PC_SWIRL_OBSERVER REFUSED:", exc)
        return 2
    finally:
        if process is not None:
            process.close()


def record(log, row, *, footer=False):
    line = json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n"
    if log.tell() + len(line.encode("utf-8")) > MAX_LOG_BYTES - (0 if footer else 1024):
        raise Refused("log size budget exhausted")
    log.write(line)
    log.flush()


def observe(log, reader, actor, first, seconds, start):
    previous, attempts, valid, unstable = None, 0, 0, 0
    last_time, max_gap, last_log = start, 0.0, -1.0
    status, reason = "complete", None
    try:
        while attempts < seconds * 20 and time.monotonic() - start < seconds:
            attempts += 1
            try:
                state = first if attempts == 1 else sample(reader, actor)
            except UnstableSample:
                unstable += 1
                time.sleep(0.05)
                continue
            now = time.monotonic()
            elapsed = round(now - start, 4)
            max_gap = max(max_gap, now - last_time)
            last_time = now
            valid += 1
            if previous is not None and state["power_mirror"] != previous["power_mirror"]:
                record(log, power_event(previous["power_mirror"], state["power_mirror"], elapsed))
            if state != previous or now - last_log >= 0.5:
                record(log, {"kind": "sample", "sample": valid, "elapsed_s": elapsed, **state})
                last_log = now
            previous = state
            time.sleep(0.05)
    except (Refused, OSError, ValueError, KeyboardInterrupt) as exc:
        status, reason = "aborted", str(exc) or "interrupted by person"
        raise
    finally:
        max_gap = max(max_gap, time.monotonic() - last_time)
        record(log, {"kind": "end", "status": status, "reason": reason,
                     "samples": valid, "attempts": attempts, "unstable_samples": unstable,
                     "elapsed_s": round(time.monotonic() - start, 4),
                     "max_valid_sample_gap_ms": round(max_gap * 1000, 2),
                     "bytes_read": reader.total}, footer=True)


def power_event(before, after, elapsed):
    return {"kind": "power_change", "elapsed_s": elapsed,
            "before": before, "after": after, "before_name": POWER_NAMES[before],
            "after_name": POWER_NAMES[after], "acquisition_candidate": after != 5}


if __name__ == "__main__":
    raise SystemExit(main())

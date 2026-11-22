"""Read-only snapshot of the title's licence and save-gate state in a live hidden run.

Opens the process with QUERY_INFORMATION|VM_READ only (m5_live); nothing is written to the guest.
Addresses are local static evidence (RE_NOTES.md, "M8 save / licence gate"):
  82875958+0x0C -> licence object; +0x10 mask from XamContentGetLicenseMask, +0x18 full-version latch
  828761B0 storage device id (0 = none selected), 828761C3 save-disabled byte, 828761D8 selector thread handle
  G6-P77 (RE_NOTES "Several controllers"): 828761EE active pad, 828761ED profile user (XAM user of the device selector
  and saves), 82B3C6F0 active-pad lock mask, 828750A0 the user whose sign-in state gates the save write (820F39D0)

Usage: python tools/m8_license_probe.py RUN_DIR [OUTPUT.json]
"""
import json
import re
import struct
import sys
from pathlib import Path

from m5_live import Process


def main() -> int:
    run = Path(sys.argv[1])
    pid = int(json.loads((run / "process.json").read_text(encoding="utf-8-sig"))["pid"])
    base = None
    for path in sorted(run.glob("runtime*.log")):
        with path.open(errors="replace") as stream:
            for line in stream:
                match = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", line)
                if match:
                    base = int(match.group(1), 16)
                    break
        if base is not None:
            break
    if base is None:
        raise SystemExit("guest virtual base not found in runtime logs")
    process = Process(pid, base)

    def u32(address):
        return struct.unpack(">I", process.read(address, 4))[0]

    licence = u32(0x82875958 + 0x0C)
    result = {
        "licence_object": f"{licence:08X}",
        "licence_mask": f"{u32(licence + 0x10):08X}" if licence else None,
        "full_version_latch": process.read(licence + 0x18, 1)[0] if licence else None,
        "storage_device_id": f"{u32(0x828761B0):08X}",
        "save_disabled_byte": process.read(0x828761C3, 1)[0],
        "selector_thread_handle": f"{u32(0x828761D8):08X}",
        "active_pad": process.read(0x828761EE, 1)[0],
        "profile_user": process.read(0x828761ED, 1)[0],
        "pad_lock_mask": process.read(0x82B3C6F0, 1)[0],
        "save_gate_user": f"{u32(0x828750A0):08X}",
        # G6-P79 (RE_NOTES "Profile handoff"): the title's per-user sign-in cache (40-byte records at 82875000,
        # XUID at +0, sign-in state at +0x0C), its XUID copy (82875100, 8 bytes per user), and its sign-in UI
        # flags: 828750C0 UI requested, 828750C8 awaiting the sign-in result, 82875930 save-gate user signed out,
        # 82875931 save-gate user newly signed in (consumed by the main loop, which reruns the START commit).
        "signin_cache": [{"xuid": process.read(0x82875000 + 40 * n, 8).hex().upper(),
                          "state": u32(0x82875000 + 40 * n + 0x0C),
                          "xuid_copy": process.read(0x82875100 + 8 * n, 8).hex().upper()} for n in range(4)],
        # sub_820F4BC8 rebuilds these on every refresh: 828750B0 mask of signed-in users, 828750B4 their count.
        # The XUID copy above is written only for a signed-in user and never cleared: the last signed-in XUID.
        "signed_in_mask": u32(0x828750B0),
        "signed_in_count": u32(0x828750B4),
        "system_ui_open": u32(0x828750BC),  # last XN_SYS_UI value the title's sign-in handler took
        "signin_ui_requested": u32(0x828750C0),
        "signin_awaiting": u32(0x828750C8),
        "signed_out_flag": process.read(0x82875930, 1)[0],
        "newly_signed_in_flag": process.read(0x82875931, 1)[0],
        # G6-P80 (RE_NOTES "Profile handoff", sub_820F4F28): 828750C4 the title's sign-in error box is open (set with
        # 828750BC when sub_820F47C8 shows it; cleared by XN_SYS_UI = 0 unless 82836CC8 is set); 828750CC the box's
        # XOVERLAPPED result word (997 = pending); 828750E8 the chosen button (0 "Sign In" sets 828750C0 again);
        # 82836CC8 the title's signed-out latch (set by the debounced refresh, cleared by every START commit in
        # sub_820F5290); 828750F4 a debounced refresh is armed.
        "signin_box_open": u32(0x828750C4),
        "signin_box_overlapped_result": u32(0x828750CC),
        "signin_box_button": u32(0x828750E8),
        "signed_out_latch": u32(0x82836CC8),
        "refresh_pending": u32(0x828750F4),
    }
    text = json.dumps(result, indent=2)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True)
        Path(sys.argv[2]).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

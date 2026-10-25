"""Read-only snapshot of the title's licence and save-gate state in a live hidden run.

Opens the process with QUERY_INFORMATION|VM_READ only (m5_live); nothing is written to the guest.
Addresses are local static evidence (RE_NOTES.md, "M8 save / licence gate"):
  82875958+0x0C -> licence object; +0x10 mask from XamContentGetLicenseMask, +0x18 full-version latch
  828761B0 storage device id (0 = none selected), 828761C3 save-disabled byte, 828761D8 selector thread handle

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
    }
    text = json.dumps(result, indent=2)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True)
        Path(sys.argv[2]).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""D-020 vertex-buffer residency regression (no SDK build, no game run; E-40, E-369).

The D3D12 edit must stay byte-for-byte what it was before the Vulkan port; the Vulkan edit must apply once to the
pinned Vulkan IssueDraw with the same two guards and the same R3HD_M5_VB_RESIDENCY_CACHE switch, and change nothing
else. With a patched SDK working copy (after tools/m5_runtime_patch.py) both files are also checked in place.

    python tools/m5_vb_residency_regression.py                -> M5_VB_RESIDENCY_REGRESSION PASS checks=N failures=0
    python tools/m5_vb_residency_regression.py --source-only  (pinned blobs only; the working copy is not read)
"""
import difflib
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from m5_runtime_patch import D3D12_VB_EDITS, VULKAN_VB_EDITS  # noqa: E402

SDK = ROOT / "external" / "rexglue-sdk"
SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
D3D12 = "src/graphics/d3d12/command_processor.cpp"
VULKAN = "src/graphics/vulkan/command_processor.cpp"
# The pinned D3D12 file after the D-020 edits as tools/m5_runtime_patch.py made them before the Vulkan port
# (computed from the commit before it). Any change to the D3D12 edit text changes this hash.
D3D12_D020_SHA256 = "1e299b6af15d598480a5a92e56bf3762788e3c7337a989ee86ac298e8a6a70f6"
GUARD_SKIP = "      if (m5_residency_cache && (vertex_buffers_in_sync_[vfetch_index >> 6] & vfetch_bit)) {"
GUARD_HIT = "      if (m5_residency_cache && state.address == vfetch_constant.address &&"
SWITCH = 'std::getenv("R3HD_M5_VB_RESIDENCY_CACHE") != nullptr'
MODE_LOG = 'REXGPU_INFO("M5 vb_residency backend=vulkan mode={}", pinned ? "pinned_cache" : "always_request");'
checks = failures = 0


def check(condition, label):
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def pinned(rel):
    return subprocess.check_output(["git", "-C", str(SDK), "show", f"{SDK_PIN}:{rel}"]).decode("utf-8")


def apply(text, edits, label):
    """tools/m3_runtime_patch.py patch() semantics: skip an edit already applied, else its anchor occurs once."""
    for before, after in edits:
        if after in text and before not in after:
            continue
        check(text.count(before) == 1, f"{label}: anchor occurs exactly once ({before.strip()[:50]})")
        text = text.replace(before, after, 1)
    return text


def added_and_removed(old, new):
    diff = [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
            if not l.startswith(("---", "+++", "@@"))]
    return [l[1:] for l in diff if l.startswith("+")], [l[1:] for l in diff if l.startswith("-")]


def main():
    source_only = "--source-only" in sys.argv[1:]
    d3d12_pin, vulkan_pin = pinned(D3D12), pinned(VULKAN)

    # D3D12: unchanged by the port.
    d3d12 = apply(d3d12_pin, D3D12_VB_EDITS, "d3d12")
    check(hashlib.sha256(d3d12.encode()).hexdigest() == D3D12_D020_SHA256, "d3d12: D-020 output byte-identical to before")
    check(d3d12.count(GUARD_SKIP) == 1 and d3d12.count(GUARD_HIT) == 1 and d3d12.count(SWITCH) == 1,
          "d3d12: both guards and the switch present once")
    check(apply(d3d12, D3D12_VB_EDITS, "d3d12 again") == d3d12, "d3d12: reapplying is a no-op")

    # Vulkan: the pinned shortcut exists (once) and is guarded by the same expressions.
    check(vulkan_pin.count("if (vertex_buffers_in_sync_[vfetch_index >> 6] & vfetch_bit) {") == 1,
          "vulkan pinned: one in-sync skip")
    check(vulkan_pin.count("if (state.address == vfetch_constant.address && state.size == vfetch_constant.size) {")
          == 1, "vulkan pinned: one cache hit")
    check(SWITCH not in vulkan_pin and "m5_residency_cache" not in vulkan_pin, "vulkan pinned: not yet patched")
    vulkan = apply(vulkan_pin, VULKAN_VB_EDITS, "vulkan")
    check(vulkan.count(GUARD_SKIP) == 1 and vulkan.count(GUARD_HIT) == 1 and vulkan.count(SWITCH) == 1,
          "vulkan: both guards and the switch present once")
    check(vulkan.count(MODE_LOG) == 1, "vulkan: one mode log line")
    check(vulkan.index(GUARD_SKIP) < vulkan.index(GUARD_HIT) < vulkan.index("shared_memory_->RequestRange(vfetch_constant"),
          "vulkan: guards precede the vertex RequestRange in IssueDraw order")
    check(apply(vulkan, VULKAN_VB_EDITS, "vulkan again") == vulkan, "vulkan: reapplying is a no-op")
    added, removed = added_and_removed(vulkan_pin, vulkan)
    check(sorted(removed) == sorted([
        "      if (vertex_buffers_in_sync_[vfetch_index >> 6] & vfetch_bit) {",
        "      if (state.address == vfetch_constant.address && state.size == vfetch_constant.size) {"]),
        f"vulkan: only the two shortcut conditions are replaced ({removed})")
    expected_added = {"#include <cstdlib>", GUARD_SKIP, GUARD_HIT, "          state.size == vfetch_constant.size) {",
                      "      static const bool m5_residency_cache = [] {",
                      f"        const bool pinned = {SWITCH};", f"        {MODE_LOG}", "        return pinned;",
                      "      }();"}
    check(set(added) == expected_added and len(added) == len(expected_added), f"vulkan: no other added line ({added})")
    # Same guard semantics as D3D12: identical guard lines and switch expression.
    for line in (GUARD_SKIP, GUARD_HIT):
        check(line in d3d12 and line in vulkan, f"guard identical in both backends: {line.strip()[:40]}")

    if not source_only:
        # The SDK working copy as the patch chain leaves it (tools/m5_runtime_patch.py has run).
        work_vulkan = (SDK / VULKAN).read_text(encoding="utf-8")
        # LX-3 and E-383 now also patch Vulkan. Keep the whole-file equality check by composing their exact
        # replay edits, rather than accepting arbitrary extra changes around the D-020 guards.
        import r3hd_vulkan_parity_patch as parity
        expected_vulkan = apply(vulkan, parity.edits() + parity.red_edits(), "Vulkan parity")
        check(work_vulkan == expected_vulkan, "working copy: Vulkan equals pinned + D-020 + HD+ parity")
        work_d3d12 = (SDK / D3D12).read_text(encoding="utf-8")
        check(work_d3d12.count(GUARD_SKIP) == 1 and work_d3d12.count(GUARD_HIT) == 1, "working copy: D3D12 guards in place")

    print(f"M5_VB_RESIDENCY_REGRESSION {'PASS' if failures == 0 else 'FAIL'} checks={checks} failures={failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

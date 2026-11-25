#!/usr/bin/env python3
"""Narrow, auditable m2_faults.log exception origin classifier (G6-P132).

Distinguishes three explicit categories without suppressing raw counts or provenance:
  - HOST_HANDLED_TEXTINPUT:
      ONLY when an E06D7363 first-chance record positively proves a handled Windows
      host TextInput / CoreMessaging WinRT exception on an isolated non-input desktop:
        1. Run-level handling context proves clean completion (exit_code == 0,
           not forced_termination, run_error is None, fatal_lines == 0).
        2. Header is well-formed with last_entered_function=host and zero guest
           context registers (lr=00000000, indirect=00000000, sp=00000000).
        3. M2 exception_location is present and resolves to Windows System32
           kernelbase.dll.
        4. Contiguous stack frames 0..N (at least 7 frames) are present:
             - Frame 0 is the VEH observer frame (r3hd.exe or rexruntime.dll).
             - Every frame 1..N resides under \\windows\\system32\\ and belongs
               strictly to the narrow Windows TextInput / CoreMessaging allow-list.
             - Frames >= 5 positively contain windows.ui.core.textinput.dll AND
               either coremessaging.dll or coreuicomponents.dll.
  - GUEST_OR_UNKNOWN:
      Any E06D7363 record that fails ANY of the above conditions (guest function,
      non-zero guest registers, game/runtime module in frame >= 1, unknown or
      non-System32 module, missing location or stack, unhandled/non-zero exit),
      or any malformed fault record. Always actionable.
  - OTHER_EXCEPTION:
      All non-E06D7363 exception codes. Routine transport/thread-name codes
      (406D1388, E0473458) are tracked separately from actionable other codes.
"""
from __future__ import annotations

import re
from pathlib import Path

ROUTINE_FAULTS = frozenset(("406D1388", "E0473458"))

HEADER_RE = re.compile(
    r"^M2 exception code=([0-9A-Fa-f]{8}) "
    r"host_pc=([0-9A-Fa-f]+) "
    r"last_entered_function=(\S+) "
    r"lr=([0-9A-Fa-f]{8}) "
    r"indirect=([0-9A-Fa-f]{8}) "
    r"sp=([0-9A-Fa-f]{8}) "
    r"fault_address=([0-9A-Fa-f]+)$"
)
LOC_RE = re.compile(r"^M2 exception_location module=(.+) offset=([0-9A-Fa-f]+)$")
STACK_RE = re.compile(r"^M2 stack (\d+) module=(.+) offset=([0-9A-Fa-f]+)$")

VEH_FRAME0_MODULES = frozenset(("r3hd.exe", "rexruntime.dll"))
ALLOWED_TEXTINPUT_SYSTEM32_MODULES = frozenset((
    "ntdll.dll",
    "kernelbase.dll",
    "ucrtbase.dll",
    "msvcrt.dll",
    "coremessaging.dll",
    "coreuicomponents.dll",
    "windows.ui.core.textinput.dll",
    "windowsudk.shellcommon.dll",
    "inputswitch.dll",
    "user32.dll",
    "win32u.dll",
    "duser.dll",
))
REQUIRED_TEXTINPUT_ANCHOR = "windows.ui.core.textinput.dll"
REQUIRED_COREMSG_ANCHORS = frozenset(("coremessaging.dll", "coreuicomponents.dll"))


def _norm_module(path_str: str) -> tuple[str, bool]:
    """Return (basename_lower, is_windows_system32)."""
    norm = path_str.strip().replace("/", "\\").lower()
    if not norm:
        return "", False
    base = norm.rsplit("\\", 1)[-1]
    # Must be directly inside <drive>:\windows\system32\<module>.dll (no subdirectory)
    is_sys32 = bool(re.fullmatch(r"[a-z]:\\windows\\system32\\[^\\]+", norm))
    return base, is_sys32


def parse_fault_records(text: str) -> tuple[list[dict], list[str]]:
    """Parse m2_faults.log into structured records plus any malformed-line errors."""
    records: list[dict] = []
    malformed: list[str] = []
    cur: dict | None = None

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("M2 exception "):
            if cur is not None:
                records.append(cur)
            m = HEADER_RE.match(line)
            if not m:
                code_m = re.search(r"code=([0-9A-Fa-f]{8})", line)
                cur = {
                    "line": lineno,
                    "malformed": True,
                    "malformed_reason": f"line {lineno}: malformed M2 exception header",
                    "code": code_m.group(1).upper() if code_m else None,
                    "last_entered_function": None,
                    "lr": None,
                    "indirect": None,
                    "sp": None,
                    "location": None,
                    "stack": [],
                }
                malformed.append(cur["malformed_reason"])
            else:
                cur = {
                    "line": lineno,
                    "malformed": False,
                    "malformed_reason": None,
                    "code": m.group(1).upper(),
                    "last_entered_function": m.group(3),
                    "lr": m.group(4).upper(),
                    "indirect": m.group(5).upper(),
                    "sp": m.group(6).upper(),
                    "location": None,
                    "stack": [],
                }
        elif line.startswith("M2 exception_location "):
            if cur is None:
                malformed.append(f"line {lineno}: orphan M2 exception_location")
                continue
            m = LOC_RE.match(line)
            if not m:
                cur["malformed"] = True
                cur["malformed_reason"] = f"line {lineno}: malformed M2 exception_location"
                malformed.append(cur["malformed_reason"])
            else:
                cur["location"] = m.group(1)
        elif line.startswith("M2 stack "):
            if cur is None:
                malformed.append(f"line {lineno}: orphan M2 stack")
                continue
            m = STACK_RE.match(line)
            if not m:
                cur["malformed"] = True
                cur["malformed_reason"] = f"line {lineno}: malformed M2 stack line"
                malformed.append(cur["malformed_reason"])
            else:
                cur["stack"].append((int(m.group(1)), m.group(2)))
        else:
            malformed.append(f"line {lineno}: unrecognized line in m2_faults.log")
            if cur is not None:
                cur["malformed"] = True
                cur["malformed_reason"] = f"line {lineno}: unrecognized line"

    if cur is not None:
        records.append(cur)
    return records, malformed


def classify_record(rec: dict, run_clean_handled: bool) -> tuple[str, str]:
    """Classify one parsed fault record into (category, detail).

    Categories:
      - HOST_HANDLED_TEXTINPUT
      - GUEST_OR_UNKNOWN
      - OTHER_EXCEPTION
    """
    if rec.get("malformed"):
        return "GUEST_OR_UNKNOWN", rec.get("malformed_reason") or "malformed record"

    code = rec.get("code")
    if not code:
        return "GUEST_OR_UNKNOWN", "missing exception code"

    if code != "E06D7363":
        if code in ROUTINE_FAULTS:
            return "OTHER_EXCEPTION", f"routine:{code}"
        return "OTHER_EXCEPTION", f"actionable:{code}"

    # Strict positive proof required for HOST_HANDLED_TEXTINPUT.
    if not run_clean_handled:
        return "GUEST_OR_UNKNOWN", "unhandled_or_unclean_run_context"

    if rec.get("last_entered_function") != "host":
        return "GUEST_OR_UNKNOWN", f"guest_function:{rec.get('last_entered_function')}"

    if rec.get("lr") != "00000000" or rec.get("indirect") != "00000000" or rec.get("sp") != "00000000":
        return "GUEST_OR_UNKNOWN", "non_zero_guest_context_registers"

    loc = rec.get("location")
    if not loc:
        return "GUEST_OR_UNKNOWN", "missing_exception_location"
    loc_base, loc_sys32 = _norm_module(loc)
    if not loc_sys32 or loc_base != "kernelbase.dll":
        return "GUEST_OR_UNKNOWN", f"unexpected_exception_location:{loc_base or 'empty'}"

    stack = rec.get("stack") or []
    if len(stack) < 7:
        return "GUEST_OR_UNKNOWN", f"insufficient_stack_frames:{len(stack)}"

    for expected_idx, (idx, _) in enumerate(stack):
        if idx != expected_idx:
            return "GUEST_OR_UNKNOWN", f"non_contiguous_stack_index:{idx}!={expected_idx}"

    f0_base, _ = _norm_module(stack[0][1])
    if f0_base not in VEH_FRAME0_MODULES:
        return "GUEST_OR_UNKNOWN", f"unexpected_veh_frame0:{f0_base or 'empty'}"

    post_veh_bases: list[str] = []
    for idx, mod_path in stack[1:]:
        base, is_sys32 = _norm_module(mod_path)
        if not base or not is_sys32 or base not in ALLOWED_TEXTINPUT_SYSTEM32_MODULES:
            return "GUEST_OR_UNKNOWN", f"unexpected_stack_module@{idx}:{base or 'empty'}"
        post_veh_bases.append(base)

    deep_bases = set(post_veh_bases[4:])  # frames >= 5
    if REQUIRED_TEXTINPUT_ANCHOR not in deep_bases:
        return "GUEST_OR_UNKNOWN", "missing_textinput_module"
    if not (deep_bases & REQUIRED_COREMSG_ANCHORS):
        return "GUEST_OR_UNKNOWN", "missing_coremessaging_module"

    return "HOST_HANDLED_TEXTINPUT", "verified_windows_system32_textinput"


def classify_fault_log_text(text: str, *, run_clean_handled: bool) -> dict:
    """Classify an entire m2_faults.log text while preserving original raw counts."""
    records, malformed = parse_fault_records(text)
    raw_codes: dict[str, int] = {}
    counts = {
        "HOST_HANDLED_TEXTINPUT": 0,
        "GUEST_OR_UNKNOWN": 0,
        "OTHER_EXCEPTION": 0,
    }
    actionable_other_codes: dict[str, int] = {}
    routine_other_codes: dict[str, int] = {}
    guest_or_unknown_reasons: dict[str, int] = {}

    for rec in records:
        code = rec.get("code")
        if code:
            raw_codes[code] = raw_codes.get(code, 0) + 1
        cat, detail = classify_record(rec, run_clean_handled=run_clean_handled)
        counts[cat] += 1
        if cat == "GUEST_OR_UNKNOWN":
            guest_or_unknown_reasons[detail] = guest_or_unknown_reasons.get(detail, 0) + 1
        elif cat == "OTHER_EXCEPTION" and code:
            if code in ROUTINE_FAULTS:
                routine_other_codes[code] = routine_other_codes.get(code, 0) + 1
            else:
                actionable_other_codes[code] = actionable_other_codes.get(code, 0) + 1

    # Fail closed on orphan malformed lines even if no M2 exception header was parsed.
    orphan_malformed = len(malformed) > 0 and counts["GUEST_OR_UNKNOWN"] == 0
    if orphan_malformed:
        counts["GUEST_OR_UNKNOWN"] += len(malformed)
        for msg in malformed:
            guest_or_unknown_reasons[msg] = guest_or_unknown_reasons.get(msg, 0) + 1

    return {
        "raw_codes": raw_codes,
        "total_records": len(records),
        "categories": counts,
        "host_handled_textinput_count": counts["HOST_HANDLED_TEXTINPUT"],
        "guest_or_unknown_count": counts["GUEST_OR_UNKNOWN"],
        "guest_or_unknown_reasons": guest_or_unknown_reasons,
        "routine_other_codes": routine_other_codes,
        "actionable_other_codes": actionable_other_codes,
        "malformed_lines": malformed,
        "actionable": (counts["GUEST_OR_UNKNOWN"] > 0 or bool(actionable_other_codes) or bool(malformed)),
    }


def classify_fault_log(run_dir: Path, *, run_clean_handled: bool) -> dict:
    """Classify run_dir/m2_faults.log if present; return empty non-actionable summary if absent."""
    log = run_dir / "m2_faults.log"
    if not log.is_file():
        return classify_fault_log_text("", run_clean_handled=run_clean_handled)
    return classify_fault_log_text(log.read_text(encoding="utf-8", errors="replace"),
                                   run_clean_handled=run_clean_handled)

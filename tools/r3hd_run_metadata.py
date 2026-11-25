#!/usr/bin/env python3
"""Shared schema parser/validator for run.json authoritative runtime_config metadata (G6-P132).

Distinguishes three explicit states:
  - "valid":     runtime_config_schema_version == 1 with all required normalized fields valid.
  - "legacy":    no run.json, or a historical run.json that carries neither
                 runtime_config_schema_version nor runtime_config.
  - "malformed": run.json is invalid JSON / non-object, or carries runtime_config /
                 runtime_config_schema_version with missing fields, wrong types, or an
                 unsupported schema version (callers must fail closed).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SUPPORTED_SCHEMA_VERSION = 1


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_runtime_config(meta: Any) -> tuple[str, dict | None, str | None]:
    """Validate runtime_config inside a parsed run.json object.

    Returns (state, runtime_config_or_none, error_or_none).
    """
    if not isinstance(meta, dict):
        return "malformed", None, "run.json root is not an object"

    has_ver = "runtime_config_schema_version" in meta
    has_cfg = "runtime_config" in meta
    if not has_ver and not has_cfg:
        return "legacy", None, None

    if not has_ver or not has_cfg:
        return "malformed", None, "incomplete runtime_config envelope (version or payload missing)"

    ver = meta.get("runtime_config_schema_version")
    if not _is_int(ver) or ver != SUPPORTED_SCHEMA_VERSION:
        return "malformed", None, f"unsupported runtime_config_schema_version: {ver!r}"

    rc = meta.get("runtime_config")
    if not isinstance(rc, dict):
        return "malformed", None, "runtime_config is not an object"

    if rc.get("execution_mode") != "unattended_hidden":
        return "malformed", None, f"invalid execution_mode: {rc.get('execution_mode')!r}"
    for bkey in ("nonintrusive", "hidden_window", "audio_hidden_mute"):
        if not _is_bool(rc.get(bkey)):
            return "malformed", None, f"runtime_config.{bkey} must be bool"

    dt = rc.get("m22_draw_trace")
    if not isinstance(dt, dict) or not _is_bool(dt.get("enabled")) or dt.get("source") not in ("R3HD_M22_DRAW_TRACE", "unset"):
        return "malformed", None, "invalid runtime_config.m22_draw_trace"

    ap = rc.get("m22_audio_probe")
    if not isinstance(ap, dict) or not _is_bool(ap.get("enabled")) or ap.get("source") not in ("R3HD_M22_AUDIO", "unset"):
        return "malformed", None, "invalid runtime_config.m22_audio_probe"

    lc = rc.get("layer_coords")
    if (not isinstance(lc, dict)
            or lc.get("effective") not in ("original", "separate")
            or lc.get("source") not in ("R3HD_LAYER_COORDS", "R3HD_WATER_LAYERS", "default")):
        return "malformed", None, "invalid runtime_config.layer_coords"

    iso = rc.get("desktop_isolation")
    if (not isinstance(iso, dict)
            or iso.get("requested") != "isolated_non_input_desktop"
            or not _is_bool(iso.get("verified"))
            or iso.get("source") not in ("inherited", "created_private", "none")):
        return "malformed", None, "invalid runtime_config.desktop_isolation"

    cap = rc.get("bounded_capture")
    if (not isinstance(cap, dict)
            or not _is_bool(cap.get("frame_request_enabled"))
            or not _is_bool(cap.get("m5_capture_enabled"))
            or not _is_int(cap.get("max_readbacks"))
            or not (0 <= cap["max_readbacks"] <= 8)):
        return "malformed", None, "invalid runtime_config.bounded_capture"

    return "valid", rc, None


def load_run_metadata(run_dir: Path) -> tuple[str, dict | None, dict | None, str | None]:
    """Load and validate run.json from a run directory.

    Returns (state, meta_or_none, runtime_config_or_none, error_or_none).
    """
    meta_path = run_dir / "run.json"
    if not meta_path.is_file():
        return "legacy", None, None, None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return "malformed", None, None, f"run.json parse error: {exc}"
    state, rc, err = validate_runtime_config(meta)
    return state, meta if isinstance(meta, dict) else None, rc, err

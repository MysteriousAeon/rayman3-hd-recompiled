#!/usr/bin/env python3
"""G6-P87 / E-573: offline reproducibility gate for the ReXGlue SDK's D3D12 renderer shaders.

Rebuilds the SDK's FXC-compiled compute shaders (`src/graphics/shaders/bytecode/d3d12_5_1/*_cs.h`)
from public Xenia shader sources and compares them with the SDK headers at three evidence levels:

  L1  compile success for the header's profile (cs_5_1);
  L2  semantic correspondence: the embedded FXC disassembly listing (interfaces, declarations and
      every instruction) is identical after normalising line endings / trailing spaces;
  L3  binary reproducibility: the DXBC container bytes are identical (whole container, including
      the MD5-style checksum). A chunk-level comparison that ignores the checksum is reported too.

It also runs one controlled source mutation in a scratch copy and checks that only the predicted
instructions change and the interface (RDEF / ISGN / OSGN / thread-group declaration) does not.

Nothing here reads title data. Sources, compiler outputs and listings go to a private scratch
directory given on the command line; nothing is written into the SDK or the repository.

The build recipe mirrors upstream `xenia-build buildshaders` at the pinned commit:
    fxc /D SHADING_LANGUAGE_HLSL_XE=1 /Fh <out>.h /T <stage>_5_1 /Vn <identifier> /nologo <src>

Usage:
  g6p87_shader_repro.py inventory --src SRC_ROOT --sdk SDK_ROOT --out inventory.json
  g6p87_shader_repro.py build     --src SRC_ROOT --sdk SDK_ROOT --fxc FXC --work DIR [--all]
  g6p87_shader_repro.py mutate    --src SRC_ROOT --sdk SDK_ROOT --fxc FXC --work DIR
  g6p87_shader_repro.py selftest

SRC_ROOT is a checkout/archive of the upstream tree (it contains src/xenia/gpu/shaders).
SDK_ROOT is the ReXGlue SDK checkout (it contains src/graphics/shaders/bytecode/d3d12_5_1).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

SHADER_REL = os.path.join("src", "xenia", "gpu", "shaders")
SDK_BC_REL = os.path.join("src", "graphics", "shaders", "bytecode", "d3d12_5_1")
FXC_DEFINE = "SHADING_LANGUAGE_HLSL_XE=1"
SDK_AUTHORED = {"resolve_downscale_cs.h"}  # SDK-authored HLSL, not an upstream Xenia shader

# ----------------------------------------------------------------------------- header parsing


def parse_header(text: str) -> tuple[str, bytes, str]:
    """Return (disassembly listing, DXBC bytes, array identifier) from an FXC /Fh header."""
    m = re.search(r"#if 0\r?\n(.*?)\r?\n#endif", text, re.S)
    if not m:
        raise ValueError("no #if 0 disassembly block")
    listing = "\n".join(line.rstrip() for line in m.group(1).replace("\r\n", "\n").split("\n"))
    a = re.search(r"const BYTE (\w+)\[\]\s*=\s*\{(.*?)\}", text, re.S)
    if not a:
        raise ValueError("no byte array")
    data = bytes(int(x) for x in re.findall(r"\d+", a.group(2)))
    return listing, data, a.group(1)


def dxbc_chunks(data: bytes) -> list[tuple[str, bytes]]:
    if data[:4] != b"DXBC":
        raise ValueError("not a DXBC container")
    total, count = struct.unpack_from("<II", data, 24)
    if total != len(data):
        raise ValueError(f"container size {total} != {len(data)}")
    offs = struct.unpack_from(f"<{count}I", data, 32)
    out = []
    for o in offs:
        fourcc = data[o:o + 4].decode("ascii", "replace")
        size = struct.unpack_from("<I", data, o + 4)[0]
        out.append((fourcc, data[o + 8:o + 8 + size]))
    return out


def listing_code(listing: str) -> list[str]:
    """Instruction/declaration lines (everything from the profile line on)."""
    lines = listing.split("\n")
    for i, line in enumerate(lines):
        if re.fullmatch(r"(vs|hs|ds|gs|ps|cs)_\d_\d", line.strip()):
            return [x for x in lines[i:] if x.strip() and not x.startswith("//")]
    return []


def listing_interface(listing: str) -> list[str]:
    code = listing_code(listing)
    head = [x for x in listing.split("\n") if x.startswith("//")]
    decl = [x for x in code if x.startswith("dcl_") or re.fullmatch(r"\w+_\d_\d", x.strip())]
    return head + decl


def listing_instructions(listing: str) -> list[str]:
    return [x for x in listing_code(listing) if not x.startswith("dcl_")][1:]


SCALE_OPS = ("udiv", "umul", "imul", "imad", "ubfe", "ishl", "ushr")


def scale_profile(listing: str) -> dict:
    ins = listing_instructions(listing)
    ops: dict[str, int] = {}
    for x in ins:
        op = x.strip().split(" ")[0]
        if op in SCALE_OPS:
            ops[op] = ops.get(op, 0) + 1
    return {"instructions": len(ins), "ops": ops}


# ----------------------------------------------------------------------------- sources


INCLUDE_RE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)


def include_closure(path: str) -> list[str]:
    seen: list[str] = []
    stack = [os.path.normpath(path)]
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.append(p)
        with open(p, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for inc in INCLUDE_RE.findall(text):
            q = os.path.normpath(os.path.join(os.path.dirname(p), inc))
            if os.path.exists(q):
                stack.append(q)
    return seen


def defines_of(path: str) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as f:
        return re.findall(r"^\s*#\s*define\s+(\S.*?)\s*$", f.read(), re.M)


def source_for_header(shader_dir: str, header: str) -> str | None:
    ident = header[:-2]  # foo_scaled_cs
    stage = ident[-2:]
    base = ident[:-3]
    for ext in (".xesl", ".hlsl"):
        cand = os.path.join(shader_dir, f"{base}.{stage}{ext}")
        if os.path.exists(cand):
            return cand
    return None


def role_of(name: str) -> str:
    if name.startswith("resolve_clear"):
        return "resolve-clear (EDRAM clear)"
    if name.startswith("resolve_fast"):
        return "resolve-fast (EDRAM to memory copy, MSAA-aware)"
    if name.startswith("resolve_full"):
        return "resolve-full (EDRAM to memory with format conversion)"
    if name.startswith("texture_load_depth"):
        return "texture-load (depth)"
    if name.startswith("texture_load"):
        return "texture-load"
    return "other"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: str) -> str:
    with open(path, "rb") as f:
        return sha256(f.read())


def rel(path: str, root: str) -> str:
    return os.path.relpath(path, root).replace("\\", "/")


def build_inventory(src_root: str, sdk_root: str, scaled_only: bool = True) -> dict:
    shader_dir = os.path.join(src_root, SHADER_REL)
    bc_dir = os.path.join(sdk_root, SDK_BC_REL)
    rows = []
    for h in sorted(os.listdir(bc_dir)):
        if not h.endswith("_cs.h") or (scaled_only and "_scaled" not in h):
            continue
        with open(os.path.join(bc_dir, h), encoding="utf-8") as f:
            listing, data, ident = parse_header(f.read())
        profile = next((x.strip() for x in listing.split("\n") if re.fullmatch(r"\w+_\d_\d", x.strip())), None)
        compiler = next((x[3:].strip() for x in listing.split("\n") if "Generated by" in x), None)
        tg = next((x.strip()[len("dcl_thread_group "):] for x in listing.split("\n")
                   if x.strip().startswith("dcl_thread_group")), None)
        src = source_for_header(shader_dir, h)
        row = {
            "header": h,
            "identifier": ident,
            "role": role_of(h),
            "stage": "cs",
            "entry_point": "main",
            "profile": profile,
            "embedded_compiler": compiler,
            "thread_group": tg,
            "dxbc_bytes": len(data),
            "dxbc_sha256": sha256(data),
            "chunks": [c for c, _ in dxbc_chunks(data)],
            "scale_ops": scale_profile(listing),
            "source": rel(src, src_root) if src else None,
        }
        if src:
            closure = include_closure(src)
            row["source_defines"] = defines_of(src)
            row["includes"] = [rel(p, src_root) for p in closure[1:]]
            texts = ""
            for p in closure:
                with open(p, encoding="utf-8", errors="replace") as f:
                    texts += f.read()
            row["scale_helpers_in_closure"] = sorted(set(re.findall(
                r"\b(XeTextureScaled\w*|XE_RESOLVE_RESOLUTION_SCALED|"
                r"XE_TEXTURE_LOAD_RESOLUTION_SCALED)\b", texts)))
        # Scale logic delegation (source reading, confirmed by the E-573 mutation, which changes
        # exactly the shaders that call XeTextureScaledTiledOffset).
        if h.startswith("resolve_clear"):
            row["scale_logic"] = ("resolve.xesli XeResolveGetInfo only: scaled EDRAM offset and "
                                  "width_div_8 x scale; no scaled destination addressing")
        else:
            row["scale_logic"] = ("delegated to texture_address.xesli XeTextureScaledTiledOffset and "
                                  "XeTextureScaledRightSubUnitOffsetInConsecutivePair (Nx1 sub-units, "
                                  "column-major, unit address x scale.x x scale.y)")
        row["relevance_1_5x"] = ("candidate subset (G6-P86 HYPOTHESIS, fixed only by G2)"
                                 if ident in G6P86_SUBSET else "needed only if G2 observes the format")
        rows.append(row)
    return {"sdk_bytecode_dir": SDK_BC_REL.replace("\\", "/"),
            "upstream": UPSTREAM, "count": len(rows), "shaders": rows}


UPSTREAM = {
    "repository": "https://github.com/xenia-canary/xenia-canary (history shared with xenia-project/xenia)",
    "commit": "0b2ffa31485318f18838afa142cdb51cf1b35213",
    "commit_subject": "[GPU] Change texture load cbuffer to push constants (2025-08-20)",
    "valid_until_exclusive": "28b69c21becd785364bb7c13dfe5b4dd757a8bb3 (2026-01-06, next change to the d3d12 bytecode)",
    "license": "BSD 3-clause (Xenia LICENSE, Copyright (c) 2015 Ben Vanik); per-file headers 'Released under the BSD license'",
    "correspondence": "upstream committed bytecode at this commit equals all 109 SDK d3d12_5_1 byte arrays",
}
G6P86_SUBSET = {"resolve_full_32bpp_scaled_cs", "resolve_fast_32bpp_1x2xmsaa_scaled_cs",
                "resolve_fast_32bpp_4xmsaa_scaled_cs", "resolve_clear_32bpp_scaled_cs",
                "texture_load_32bpb_scaled_cs", "texture_load_depth_unorm_scaled_cs"}


# ----------------------------------------------------------------------------- compile / compare


def fxc_identity(fxc: str) -> dict:
    ident = {"path": fxc, "sha256": file_sha(fxc)}
    dll = os.path.join(os.path.dirname(fxc), "d3dcompiler_47.dll")
    if os.path.exists(dll):
        ident["d3dcompiler_47_sha256"] = file_sha(dll)
    try:
        ps = ("(Get-Item -LiteralPath $env:G6P87_FXC).VersionInfo.FileVersion;"
              "if (Test-Path -LiteralPath $env:G6P87_DLL) {(Get-Item -LiteralPath $env:G6P87_DLL).VersionInfo.FileVersion}")
        env = dict(os.environ, G6P87_FXC=fxc, G6P87_DLL=dll)
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=60, env=env)
        v = [x.strip() for x in r.stdout.splitlines() if x.strip()]
        ident["fxc_file_version"] = v[0] if v else None
        ident["d3dcompiler_47_file_version"] = v[1] if len(v) > 1 else None
    except Exception as e:  # noqa: BLE001 - informational only
        ident["version_error"] = str(e)
    return ident


def fxc_command(fxc: str, src: str, out_h: str, ident: str) -> list[str]:
    stage = ident[-2:]
    return [fxc, "/D", FXC_DEFINE, "/Fh", out_h, "/T", f"{stage}_5_1", "/Vn", ident, "/nologo", src]


def compile_one(fxc: str, src: str, out_h: str, ident: str) -> tuple[int, str]:
    cmd = fxc_command(fxc, src, out_h, ident)
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(src))
    return r.returncode, r.stderr.strip()


def compare(ref_text: str, gen_text: str) -> dict:
    rl, rb, rid = parse_header(ref_text)
    gl, gb, gid = parse_header(gen_text)
    rc = dxbc_chunks(rb)
    gc = dxbc_chunks(gb)
    res = {
        "identifier_equal": rid == gid,
        "L2_listing_equal": rl == gl,
        "L2_interface_equal": listing_interface(rl) == listing_interface(gl),
        "L2_instructions_equal": listing_instructions(rl) == listing_instructions(gl),
        "L3_container_equal": rb == gb,
        "L3_chunks_equal_ignoring_checksum": [c for c in rc] == [c for c in gc],
        "ref_sha256": sha256(rb),
        "gen_sha256": sha256(gb),
    }
    if not res["L2_listing_equal"]:
        ra, ga = rl.split("\n"), gl.split("\n")
        res["listing_first_diff"] = next(
            ({"line": i + 1, "ref": a, "gen": b} for i, (a, b) in enumerate(zip(ra, ga)) if a != b),
            {"line": min(len(ra), len(ga)) + 1, "ref_lines": len(ra), "gen_lines": len(ga)})
    if not res["L3_container_equal"]:
        res["chunk_diffs"] = [f for (f, a), (_, b) in zip(rc, gc) if a != b]
    return res


def build(src_root: str, sdk_root: str, fxc: str, work: str, all_shaders: bool) -> dict:
    shader_dir = os.path.join(src_root, SHADER_REL)
    bc_dir = os.path.join(sdk_root, SDK_BC_REL)
    out_dir = os.path.join(work, "dxbc")
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for h in sorted(os.listdir(bc_dir)):
        if not h.endswith(".h") or h in SDK_AUTHORED:
            continue
        if not all_shaders and "_scaled" not in h:
            continue
        ident = h[:-2]
        src = source_for_header(shader_dir, h)
        row = {"header": h, "source": rel(src, src_root) if src else None}
        if not src:
            row["L1_compiled"] = False
            row["error"] = "no source"
            results.append(row)
            continue
        out_h = os.path.join(out_dir, h)
        if os.path.exists(out_h):
            os.remove(out_h)
        rc, err = compile_one(fxc, src, out_h, ident)
        row["L1_compiled"] = rc == 0 and os.path.exists(out_h)
        row["fxc_rc"] = rc
        if err:
            row["stderr"] = err[:2000]
        if row["L1_compiled"]:
            with open(os.path.join(bc_dir, h), encoding="utf-8") as f:
                ref = f.read()
            with open(out_h, encoding="utf-8", errors="replace") as f:
                gen = f.read()
            row.update(compare(ref, gen))
        results.append(row)
    summary = {
        "total": len(results),
        "L1": sum(1 for r in results if r.get("L1_compiled")),
        "L2_listing": sum(1 for r in results if r.get("L2_listing_equal")),
        "L3_container": sum(1 for r in results if r.get("L3_container_equal")),
        "warnings": sum(1 for r in results if r.get("stderr")),
    }
    return {"fxc": fxc_identity(fxc), "define": FXC_DEFINE,
            "command_template": "fxc /D SHADING_LANGUAGE_HLSL_XE=1 /Fh <out>.h /T cs_5_1 /Vn <identifier> /nologo <src>",
            "summary": summary, "results": results}


# ----------------------------------------------------------------------------- mutation

# One isolated, non-production change in the shared scaled texture-address helper
# `XeTextureScaledTiledOffset` (texture_address.xesli at the pinned revision). The replacement is
# applied to a scratch copy only. It changes the unit-local host sub-unit index from column-major
# (`sub.x * scale.y + sub.y`) to row-major (`sub.y * scale.x + sub.x`), the class of edit a
# rational 3:2 layout needs. Prediction: exactly the scaled shaders that call the helper change
# (scaled texture loads and scaled resolve copies); resolve_clear (XE_RESOLVE_CLEAR has no
# destination address), every unscaled shader and every interface stay unchanged. The companion
# helper XeTextureScaledRightSubUnitOffsetInConsecutivePair is deliberately left alone, so the
# mutated shaders are NOT a consistent layout and must never be loaded.
MUTATION_FILE = "texture_address.xesli"


def find_mutation_site(text: str) -> tuple[str, str] | None:
    """Locate the column-major sub-unit index in XeTextureScaledTiledOffset."""
    m = re.search(r"uint XeTextureScaledTiledOffset\([\s\S]*?\n\}", text)
    if not m:
        return None
    body = m.group(0)
    # Column-major index: host group x times scale y plus host group y (names vary by revision).
    pat = re.compile(r"\(\s*(\w+)\.x\s*\*\s*(\w+)\.y\s*\+\s*\1\.y\s*\)")
    mm = pat.search(body)
    if not mm:
        return None
    old = mm.group(0)
    new = f"({mm.group(1)}.y * {mm.group(2)}.x + {mm.group(1)}.x)"
    return old, new


def mutate(src_root: str, sdk_root: str, fxc: str, work: str) -> dict:
    scratch = os.path.join(work, "mutated_src")
    if os.path.exists(scratch):
        shutil.rmtree(scratch)
    shutil.copytree(os.path.join(src_root, "src"), os.path.join(scratch, "src"))
    target = os.path.join(scratch, SHADER_REL, MUTATION_FILE)
    with open(target, encoding="utf-8", newline="") as f:
        text = f.read()
    site = find_mutation_site(text)
    if not site:
        return {"error": "mutation site not found"}
    old, new = site
    if text.count(old) != 1:
        return {"error": f"mutation site not unique ({text.count(old)})"}
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace(old, new))
    out = {"file": MUTATION_FILE, "old": old, "new": new, "runs": []}
    for run in ("a", "b"):  # two clean builds must agree
        res = build(scratch, sdk_root, fxc, os.path.join(work, f"mutated_{run}"), True)
        out["runs"].append(res)
    a, b = out["runs"]
    out["clean_rebuild_identical"] = [r.get("gen_sha256") for r in a["results"]] == \
                                     [r.get("gen_sha256") for r in b["results"]]
    compiled = [r for r in a["results"] if r.get("L1_compiled")]
    out["not_compiled"] = [r["header"] for r in a["results"] if not r.get("L1_compiled")]
    changed = [r for r in compiled if not r.get("L3_container_equal")]
    out["changed"] = [r["header"] for r in changed]
    out["changed_interface"] = [r["header"] for r in changed if not r.get("L2_interface_equal")]
    out["unchanged_count"] = len(compiled) - len(changed)
    # Predicted set: every shader whose include closure has the mutated file and that compiles
    # the scaled branch.
    shader_dir = os.path.join(src_root, SHADER_REL)
    predicted = []
    for r in compiled:
        src = r["source"] and os.path.join(src_root, r["source"])
        if src and any(os.path.basename(p) == MUTATION_FILE for p in include_closure(src)) and \
                "_scaled" in r["header"] and not r["header"].startswith("resolve_clear"):
            predicted.append(r["header"])
    out["predicted"] = predicted
    out["prediction_exact"] = sorted(predicted) == sorted(out["changed"])
    # Instruction-level delta for each changed shader.
    deltas = {}
    bc_dir = os.path.join(sdk_root, SDK_BC_REL)
    for h in out["changed"]:
        with open(os.path.join(bc_dir, h), encoding="utf-8") as f:
            rl = parse_header(f.read())[0]
        with open(os.path.join(work, "mutated_a", "dxbc", h), encoding="utf-8", errors="replace") as f:
            gl = parse_header(f.read())[0]
        ri, gi = listing_instructions(rl), listing_instructions(gl)
        import difflib
        d = [x for x in difflib.unified_diff(ri, gi, lineterm="", n=0) if x[:1] in "+-" and x[:3] not in ("+++", "---")]
        deltas[h] = {"ref_instructions": len(ri), "gen_instructions": len(gi), "changed_lines": len(d),
                     "sample": d[:12]}
    out["deltas"] = deltas
    for r in out["runs"]:
        r.pop("results", None)
    return out


# ----------------------------------------------------------------------------- selftest


def _fake_header(listing: str, data: bytes, name: str) -> str:
    return "#if 0\n" + listing + "\n#endif\n\nconst BYTE " + name + "[] =\n{\n" + \
        ", ".join(str(b) for b in data) + "\n};\n"


def _fake_dxbc(chunks: list[tuple[bytes, bytes]]) -> bytes:
    hdr = 32 + 4 * len(chunks)
    body = b""
    offs = []
    for fourcc, payload in chunks:
        offs.append(hdr + len(body))
        body += fourcc + struct.pack("<I", len(payload)) + payload
    total = hdr + len(body)
    return b"DXBC" + b"\0" * 16 + struct.pack("<III", 1, total, len(chunks)) + \
        struct.pack(f"<{len(chunks)}I", *offs) + body


def selftest() -> int:
    lst = "//\n// Generated by Microsoft (R) HLSL Shader Compiler 10.1\n//\ncs_5_1\ndcl_thread_group 8, 8, 1\nudiv r0.x, null, r1.x, r2.x\nret"
    d = _fake_dxbc([(b"RDEF", b"x" * 8), (b"SHEX", b"y" * 12)])
    a = _fake_header(lst, d, "t_cs")
    # clang-formatted variant of the same header must compare equal at L2 and L3.
    head, arr = a.split("const BYTE", 1)
    b = head + "const BYTE" + arr.replace(", ", ",   ").replace("{\n", "{\n    ")
    r = compare(a, b)
    assert r["L2_listing_equal"] and r["L3_container_equal"], r
    # a changed checksum only: L3 container differs, chunks equal.
    d2 = bytearray(d); d2[5] ^= 1
    r = compare(a, _fake_header(lst, bytes(d2), "t_cs"))
    assert not r["L3_container_equal"] and r["L3_chunks_equal_ignoring_checksum"], r
    # a changed instruction: L2 instructions differ, interface equal.
    r = compare(a, _fake_header(lst.replace("udiv", "umul"), d, "t_cs"))
    assert not r["L2_instructions_equal"] and r["L2_interface_equal"], r
    # a changed declaration: interface differs.
    r = compare(a, _fake_header(lst.replace("8, 8, 1", "4, 32, 1"), d, "t_cs"))
    assert not r["L2_interface_equal"], r
    # mutation site detection
    src = ("uint XeTextureScaledTiledOffset(bool a,\n    uint2_xe scale) {\n"
           "  return ((((unit_subunit.x * scale.y + unit_subunit.y) << 2u)));\n}\n")
    old, new = find_mutation_site(src)
    assert old == "(unit_subunit.x * scale.y + unit_subunit.y)" and \
        new == "(unit_subunit.y * scale.x + unit_subunit.x)", (old, new)
    assert find_mutation_site("void f() {\n}\n") is None
    print("selftest PASS (6 checks)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["inventory", "build", "mutate", "selftest"])
    ap.add_argument("--src")
    ap.add_argument("--sdk")
    ap.add_argument("--fxc")
    ap.add_argument("--work")
    ap.add_argument("--out")
    ap.add_argument("--all", action="store_true", help="build every SDK D3D12 header, not only *_scaled")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "inventory":
        res = build_inventory(a.src, a.sdk)
    elif a.cmd == "build":
        res = build(a.src, a.sdk, a.fxc, a.work, a.all)
    else:
        res = mutate(a.src, a.sdk, a.fxc, a.work)
    text = json.dumps(res, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    if a.cmd == "build":
        print(json.dumps({"fxc": res["fxc"], "summary": res["summary"]}, indent=1))
    elif a.cmd == "mutate":
        print(text[:6000])
    else:
        print(f"inventory: {res['count']} shaders")
    return 0


if __name__ == "__main__":
    sys.exit(main())

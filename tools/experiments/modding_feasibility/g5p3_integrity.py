#!/usr/bin/env python3
"""E-479 (D-246) G5-P3: resource integrity of the development-only structural transaction.

usage:
  g5p3_integrity.py negtest    synthetic fixtures + g5p3_integrity_test.cpp built against four headers (no game)
Outputs stay under private/work/e479/ (fixtures are random bytes generated here, never the game's files; the live
copies the test mutates are deleted when it ends).

FIXTURES (seeded random, real-scale sizes): intro_10.lvl 7,661,836 bytes grown by 112 (an in-file 16-byte range at
1,000 and the 112-byte tail, mod g5p3.syn), plus a 32-byte range of a second, non-structural mod g5p3.tex at 4,000,000
(served on top of the transaction image, not part of its hash); intro_10.ptr 209,068 bytes grown by 72, one range of
g5p3.syn over the whole guest size; a second same-size "version" of both members (v2); plans: valid, a changed `.lvl`
result SHA-256 (badmeta), a changed transaction id (badid). The header's allow-list is swapped for the fixtures'
sizes and SHA-256 by `g5p1_dev_gate.py render --test-allow` (test builds only).

BUILDS: dev = the G5-P3 header (snapshot); old = the G5-P2b header (`--no-snapshot`, the reproduction); prod =
tools/m33_mod_overlay.h unchanged; budget = dev with R3HD_DEVTX_SNAPSHOT_BUDGET=1,000,000.

PRE-REGISTERED EXPECTATIONS (written before the first run of any build):
  dev: every scenario PASS (T0-T8 in both open orders, both refusals before activation, no-variable refusal,
       snapshot invariants: two images of exactly the expected sizes, no snapshot kept, 2 whole-member disk reads per
       load, images released with the plan).
  old (reproduction of the G5-P2b concern): FAIL exactly
       T1_same_size_after_activation_{lvl,ptr}_first, T1_same_size_mid_read_{lvl,ptr}_first,
       T2_truncate_extend_{lvl,ptr}_first, T3_atomic_replace_{lvl,ptr}_first, T4_removed_after_activation_{lvl,ptr}_first,
       T5_mixed_after_activation_ptr_first (the `.lvl` swapped), T6_between_verify_and_first_read_{lvl,ptr}_first,
       T7_between_reopens_{lvl,ptr}_first;
       PASS the rest: T0 (both), T5_mixed_after_activation_lvl_first (only the `.ptr` is swapped, and the old overlay
       already replaces every `.ptr` byte), T5 before activation (both), T8 after and before activation (both),
       no-variable (both).
  prod: refused `unknown_record` in both orders, every byte and size as on disk.
  budget: refused `tx_snapshot_budget` in both orders, every byte and size as on disk.
  Overhead limits (I5): dev steady images = 7,871,088 bytes (the two guest sizes) <= 16 MiB budget; dev private bytes
  after activation - before <= 2 x (images + range data) (no unbounded copy); dev load time <= 3 x old load time + 50
  ms; dev open (lvl) <= old open (lvl) + 50 ms.
"""
import hashlib
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
HERE = Path(__file__).resolve().parent
WORK = ROOT / "private" / "work" / "e479"
VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
LVL_SIZE, LVL_GROW, PTR_SIZE, PTR_GROW = 7661836, 112, 209068, 72
OLD_FAIL = {f"{t}_{o}_first" for t in ("T1_same_size_after_activation", "T1_same_size_mid_read", "T2_truncate_extend",
                                        "T3_atomic_replace", "T4_removed_after_activation",
                                        "T6_between_verify_and_first_read", "T7_between_reopens")
            for o in ("lvl", "ptr")} | {"T5_mixed_after_activation_ptr_first"}


def fnv(b):
    h = 0xCBF29CE484222325
    for x in b:
        h = ((h ^ x) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def fixtures():
    fx = WORK / "fixtures"
    if fx.exists():
        shutil.rmtree(fx)
    for d in ("pristine/blobs", "v2", "expect"):
        (fx / d).mkdir(parents=True)
    live = fx / "live"
    rnd = random.Random(479)
    lvl = rnd.randbytes(LVL_SIZE)
    ptr = rnd.randbytes(PTR_SIZE)
    (fx / "pristine" / "intro_10.lvl").write_bytes(lvl)
    (fx / "pristine" / "intro_10.ptr").write_bytes(ptr)
    (fx / "v2" / "intro_10.lvl").write_bytes(rnd.randbytes(LVL_SIZE))
    (fx / "v2" / "intro_10.ptr").write_bytes(rnd.randbytes(PTR_SIZE))
    # ranges: (file index, offset, new bytes, mod)
    lvl_ranges = [(1000, rnd.randbytes(16), "g5p3.syn"), (LVL_SIZE, rnd.randbytes(LVL_GROW), "g5p3.syn"),
                  (4000000, rnd.randbytes(32), "g5p3.tex")]
    ptr_new = rnd.randbytes(PTR_SIZE + PTR_GROW)
    img_l = bytearray(lvl) + bytearray(LVL_GROW)
    for off, data, mod in lvl_ranges:
        if mod == "g5p3.syn":
            img_l[off:off + len(data)] = data
    res_l = hashlib.sha256(img_l).hexdigest()
    served_l = bytearray(img_l)
    for off, data, mod in lvl_ranges:
        served_l[off:off + len(data)] = data
    res_p = hashlib.sha256(ptr_new).hexdigest()
    (fx / "expect" / "intro_10.lvl").write_bytes(served_l)
    (fx / "expect" / "intro_10.ptr").write_bytes(ptr_new)
    org_l, org_p = hashlib.sha256(lvl).hexdigest(), hashlib.sha256(ptr).hexdigest()
    canon = (f"level-tx 1 intro_10 g5p3.syn\n"
             f"tx-file lvl intro_10.lvl {LVL_SIZE} {org_l} {LVL_SIZE + LVL_GROW} {res_l}\n"
             f"tx-file ptr intro_10.ptr {PTR_SIZE} {org_p} {PTR_SIZE + PTR_GROW} {res_p}\n")
    txid = hashlib.sha256(canon.encode()).hexdigest()[:16]
    ranges = []
    for i, (off, data, mod) in enumerate(lvl_ranges):
        inside = lvl[off:off + len(data)] if off < LVL_SIZE else b""
        blob = fx / "pristine" / "blobs" / f"r{i}.bin"
        blob.write_bytes(data)
        ranges.append(f"range 0 {off} {len(data)} {fnv(inside)} {fnv(data)} {mod} {live / 'blobs' / blob.name}")
    blob = fx / "pristine" / "blobs" / "r3.bin"
    blob.write_bytes(ptr_new)
    ptr_range = f"range 1 0 {len(ptr_new)} {fnv(ptr)} {fnv(ptr_new)} g5p3.syn {live / 'blobs' / blob.name}"

    def plan(res_lvl=res_l, tid=txid):
        return "\n".join(["R3HD_MOD_PLAN 1", "mod g5p3.syn 1", "mod g5p3.tex 1", f"level-tx 1 intro_10 g5p3.syn {tid}",
                          f"file {LVL_SIZE} {live / 'intro_10.lvl'}",
                          f"tx-file 0 lvl {org_l} {LVL_SIZE + LVL_GROW} {res_lvl}", f"grow 0 {LVL_SIZE + LVL_GROW}",
                          *ranges, f"file {PTR_SIZE} {live / 'intro_10.ptr'}",
                          f"tx-file 1 ptr {org_p} {PTR_SIZE + PTR_GROW} {res_p}", f"grow 1 {PTR_SIZE + PTR_GROW}",
                          ptr_range, "gameplay g5p3.syn", f"end 2 {len(ranges) + 1}", ""])
    (fx / "pristine" / "plan.txt").write_text(plan(), encoding="utf-8", newline="\n")
    bad = res_l[:-1] + ("0" if res_l[-1] != "0" else "1")
    (fx / "pristine" / "plan_badmeta.txt").write_text(plan(res_lvl=bad), encoding="utf-8", newline="\n")
    badid = txid[:-1] + ("0" if txid[-1] != "0" else "1")
    (fx / "pristine" / "plan_badid.txt").write_text(plan(tid=badid), encoding="utf-8", newline="\n")
    allow = f"{LVL_SIZE}:{org_l}:{PTR_SIZE}:{org_p}"
    meta = {"lvl_sha256": org_l, "ptr_sha256": org_p, "lvl_image_sha256": res_l, "ptr_image_sha256": res_p,
            "tx_id": txid, "served_lvl_sha256": hashlib.sha256(served_l).hexdigest(),
            "image_bytes": len(served_l) + len(ptr_new), "range_bytes": sum(len(d) for _, d, _ in lvl_ranges) + len(ptr_new)}
    (WORK / "fixtures_meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    return fx, allow, meta


def build(kind, allow):
    d = WORK / "build" / kind
    d.mkdir(parents=True, exist_ok=True)
    hdr = d / "m33_mod_overlay.h"
    extra = ""
    if kind == "prod":
        shutil.copyfile(TOOLS / "m33_mod_overlay.h", hdr)
    else:
        args = ["render", str(hdr), "--test-allow", allow] + (["--no-snapshot"] if kind == "old" else [])
        subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), *args], check=True, capture_output=True)
        if kind == "budget":
            extra = "/DR3HD_DEVTX_SNAPSHOT_BUDGET=1000000ull "
    exe = d / f"g5p3_integrity_test_{kind}.exe"
    bat = d / "build.bat"
    bat.write_text(f'@echo off\ncall "{VCVARS}" >nul 2>&1\ncl /nologo /std:c++20 /EHsc /O2 /W3 /D_CRT_SECURE_NO_WARNINGS '
                   f'{extra}/I"{d}" "{HERE / "g5p3_integrity_test.cpp"}" /Fe:"{exe}" /Fo:"{d}\\\\" >"{d / "build.log"}" 2>&1\n'
                   f'exit /b %errorlevel%\n', encoding="ascii")
    r = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True)
    if r.returncode or not exe.is_file():
        raise SystemExit(f"build {kind} failed:\n{(d / 'build.log').read_text(errors='replace')[-3000:]}")
    return exe


def run(exe, fx, mode):
    r = subprocess.run([str(exe), str(fx), mode], capture_output=True, text=True, timeout=900)
    lines = r.stdout.splitlines()
    cases = {}
    for ln in lines:
        if ln.startswith(("PASS ", "FAIL ")):
            cases[ln.split()[1]] = ln.startswith("PASS")
    return {"exit": r.returncode, "cases": cases, "stdout": r.stdout, "stderr": r.stderr[-2000:],
            "perf": next((ln for ln in lines if ln.startswith("PERF")), None),
            "mem": next((ln for ln in lines if ln.startswith("MEM")), None),
            "summary": lines[-1] if lines else ""}


def kv(line):
    return {k: v for k, v in (t.split("=", 1) for t in (line or "").split() if "=" in t)}


def negtest():
    WORK.mkdir(parents=True, exist_ok=True)
    fx, allow, meta = fixtures()
    exes = {k: build(k, allow) for k in ("dev", "old", "prod", "budget")}
    out = {"meta": meta}
    for k, mode in (("dev", "dev"), ("old", "dev"), ("prod", "prod"), ("budget", "budget")):
        out[k] = run(exes[k], fx, mode)
        (WORK / f"result_{k}.txt").write_text(out[k]["stdout"] + out[k]["stderr"])
        print(f"--- {k}\n{out[k]['stdout']}", flush=True)
    for k in ("dev", "old"):
        out[f"mem_{k}"] = run(exes[k], fx, "mem")
        print(out[f"mem_{k}"]["mem"], flush=True)
    res = {}
    res["dev_all_pass"] = out["dev"]["exit"] == 0 and len(out["dev"]["cases"]) == 31
    old_fail = {c for c, ok in out["old"]["cases"].items() if not ok}
    res["old_reproduces_exactly"] = old_fail == OLD_FAIL and len(out["old"]["cases"]) == 30
    res["prod_refused"] = out["prod"]["exit"] == 0 and len(out["prod"]["cases"]) == 2
    res["budget_refused"] = out["budget"]["exit"] == 0 and len(out["budget"]["cases"]) == 2
    pd, po = kv(out["dev"]["perf"]), kv(out["old"]["perf"])
    md, mo = kv(out["mem_dev"]["mem"]), kv(out["mem_old"]["mem"])
    d_priv = int(md["private_after"]) - int(md["private_before"])
    o_priv = int(mo["private_after"]) - int(mo["private_before"])
    d_peak = int(md["peak_after"]) - int(md["private_before"])
    lim = 2 * (meta["image_bytes"] + meta["range_bytes"])
    res["i5_overhead"] = (meta["image_bytes"] == LVL_SIZE + LVL_GROW + PTR_SIZE + PTR_GROW <= 16 << 20 and d_priv <= lim
                          and float(pd["load_ms"]) <= 3 * float(po["load_ms"]) + 50
                          and float(pd["open_lvl_ms"]) <= float(po["open_lvl_ms"]) + 50)
    out["measures"] = {"dev": pd, "old": po, "dev_private_delta": d_priv, "old_private_delta": o_priv,
                       "dev_peak_minus_before": d_peak, "old_peak_minus_before": int(mo["peak_after"]) - int(mo["private_before"]),
                       "limit_private_delta": lim}
    out["old_fail_observed"] = sorted(old_fail)
    out["res"] = res
    out["pass"] = all(res.values())
    for k in ("dev", "old", "prod", "budget", "mem_dev", "mem_old"):
        out[k].pop("stdout", None)
    (WORK / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
    shutil.rmtree(fx / "live", ignore_errors=True)
    print(json.dumps({"res": res, "measures": out["measures"]}, indent=1))
    print("G5P3_NEGTEST", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "negtest":
        sys.exit(negtest())
    raise SystemExit(__doc__)

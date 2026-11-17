"""LM-2 (Windows host): the separately authorized DIAGNOSTIC, SEH-disabled generated tree for the first Linux r3hd.

Writes private/work/rex_linux_diag/ (never tracked) from the production work tree private/work/rex/:
  * r3hd_manifest.toml: the production manifest with exactly one line changed,
    `generate_exception_handlers = true` -> `false` (same relative paths: the directory is a sibling);
  * generated/default/: the pinned rexglue codegen output for that manifest, then the production build's own
    automated instrumentation steps (tools/m2_prepare.py instrument, tools/m5_prepare.py instrument) run against
    this tree through R3HD_REX_WORK. No generated function body is edited by hand;
  * src/: a copy of the production prepared host sources (the files the production r3hd target compiles);
  * DIAGNOSTIC_SEH_DISABLED.txt and diag_manifest.json (identity, audit, production-unchanged proof).

Gates: the production manifest, generated tree and prepared sources are byte-identical before and after; the
diagnostic tree has no __try / M4 emission; the target audit (tools/m3_target_audit.py) reports 0 untranslated data
targets, 0 unclassified synthesised pointers, 0 SEH bodies registered as functions, and the same dispatch-table
coverage as production. Startup or gameplay of a build from this tree is never compatibility evidence; portable
guest exception handling (LM-A) remains mandatory before a production Linux release.

Subcommands: generate [--replace], check, package --zip PATH
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PROD = ROOT / "private/work/rex"
DIAG = ROOT / "private/work/rex_linux_diag"
REXGLUE = ROOT / "external/rexglue-sdk/out/win-amd64/Release/rexglue.exe"
MARKER = "DIAGNOSTIC_SEH_DISABLED.txt"
FLAG_ON, FLAG_OFF = "generate_exception_handlers = true", "generate_exception_handlers = false"
AUDIT_INPUTS = ["private/work/default_image.bin", "private/work/pe_analysis.json", "reports/milestone3/data/eh_map.json"]
PROD_AUDIT = ROOT / "reports/milestone4/target_audit.json"
GEN_SUFFIXES = (".cpp", ".h", ".cmake")
sha = lambda b: hashlib.sha256(b).hexdigest()


class Fail(Exception):
    pass


def need(cond, what):
    if not cond:
        raise Fail(what)


def diag_manifest_text(production):
    """The production manifest with exactly the one flag line changed."""
    lines = production.split("\n")
    hits = [i for i, l in enumerate(lines) if l.strip() == FLAG_ON]
    need(len(hits) == 1 and sum(FLAG_OFF in l for l in lines) == 0, "production manifest must hold the flag once")
    lines[hits[0]] = lines[hits[0]].replace(FLAG_ON, FLAG_OFF)
    out = "\n".join(lines)
    diff = [(a, b) for a, b in zip(production.split("\n"), out.split("\n")) if a != b]
    need(len(diff) == 1 and len(out.split("\n")) == len(lines), "exactly one manifest line differs")
    return out


def tree_hashes(gen):
    return {p.name: sha(p.read_bytes()) for p in sorted(gen.iterdir()) if p.is_file() and p.suffix in GEN_SUFFIXES}


def build_step():
    sys.path.insert(0, str(ROOT / "tools"))
    import r3hd_build_step  # noqa: E402  (pure digest function; its actions run only under main)
    return r3hd_build_step


def prod_snapshot():
    gen = PROD / "generated/default"
    need(gen.is_dir() and (PROD / "r3hd_manifest.toml").is_file(), "production work tree missing (run the Windows build)")
    n, d = build_step().digest(gen)
    return {"manifest_sha256": sha((PROD / "r3hd_manifest.toml").read_bytes()), "codegen_files": n, "codegen_digest": d,
            "generated_sha256": tree_hashes(gen),
            "src_sha256": {p.name: sha(p.read_bytes()) for p in sorted((PROD / "src").iterdir()) if p.is_file()}}


def run(argv, log, env=None):
    p = subprocess.run([str(a) for a in argv], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with open(log, "ab") as f:
        f.write(f"$ {' '.join(map(str, argv))}\n".encode() + p.stdout + f"\n[exit {p.returncode}]\n".encode())
    need(p.returncode == 0, f"command failed ({p.returncode}): {argv[1] if len(argv) > 1 else argv[0]} (see {log.name})")
    return p.stdout.decode(errors="replace")


def count(value):
    """m3_target_audit writes lists of addresses; summaries print their length. Accept both."""
    return len(value) if isinstance(value, (list, dict)) else int(value)


def audit_summary(report):
    ex = report["exception_representation"]
    return {"dispatch_table_entries": report["dispatch_table_entries"], "translated_words": report["translated_words"],
            "untranslated_data_targets": count(report["data_pointers"]["untranslated"]),
            "data_targets": report["data_pointers"]["distinct_targets"],
            "data_target_classes": report["data_pointers"]["by_class"],
            "unclassified_synthesised": len(report["unclassified_synthesised"]),
            "seh_bodies_registered_as_functions": len(ex["seh_bodies_registered_as_functions"]),
            "seh_bodies_untranslated": len(ex["seh_bodies_untranslated"])}


def check_audit(diag, prod):
    need(diag["untranslated_data_targets"] == 0, "audit: untranslated data targets")
    need(diag["unclassified_synthesised"] == 0, "audit: unclassified synthesised pointers")
    need(diag["seh_bodies_registered_as_functions"] == 0, "audit: SEH bodies registered as functions")
    need(diag["dispatch_table_entries"] == prod["dispatch_table_entries"], "audit: dispatch-table coverage differs")
    need(diag["translated_words"] == prod["translated_words"], "audit: translated-word coverage differs")
    need(diag["data_targets"] == prod["data_targets"] and diag["data_target_classes"] == prod["data_target_classes"],
         "audit: data-target coverage or classification differs")


def generate(replace):
    before = prod_snapshot()
    if DIAG.exists():
        need(replace and (DIAG / MARKER).is_file(), f"{DIAG} exists (use --replace; only a marked diagnostic tree)")
        shutil.rmtree(DIAG)
    (DIAG / "generated/default").mkdir(parents=True)
    log = DIAG / "generate.log"
    (DIAG / MARKER).write_text("DIAGNOSTIC BUILD INPUT - guest SEH disabled (generate_exception_handlers = false).\n"
                               "Never compatibility evidence. Private: game-derived code. LM-A remains mandatory.\n")
    production = (PROD / "r3hd_manifest.toml").read_bytes().decode("utf-8")
    (DIAG / "r3hd_manifest.toml").write_bytes(diag_manifest_text(production).encode("utf-8"))
    partition = PROD / "generated/default/codegen.partition.json"
    if partition.is_file():  # Same partition assignment as production (E-151): same file layout.
        shutil.copyfile(partition, DIAG / "generated/default/codegen.partition.json")
    need(REXGLUE.is_file(), "pinned rexglue.exe missing (run the Windows build)")
    run([REXGLUE, "--log-level", "info", "codegen", "--ignore-stamp", DIAG.relative_to(ROOT) / "r3hd_manifest.toml"], log)
    env = dict(os.environ, R3HD_REX_WORK=str(DIAG))
    run([sys.executable, ROOT / "tools/m2_prepare.py", "instrument"], log, env)
    run([sys.executable, ROOT / "tools/m5_prepare.py", "instrument"], log, env)
    shutil.copytree(PROD / "src", DIAG / "src")
    gen = DIAG / "generated/default"
    cpp = [p for p in gen.glob("*.cpp")]
    try_count = sum(p.read_text(errors="replace").count("__try") for p in cpp)
    m4 = sum(p.read_text(errors="replace").count("M4Init(") for p in cpp)
    need(try_count == 0 and m4 == 0, f"diagnostic tree still has SEH emission (__try={try_count}, M4Init={m4})")
    out = run([sys.executable, ROOT / "tools/m3_target_audit.py", gen.relative_to(ROOT), *AUDIT_INPUTS,
               (DIAG / "target_audit.json").relative_to(ROOT)], log)
    diag_audit = audit_summary(json.loads((DIAG / "target_audit.json").read_text()))
    prod_audit = audit_summary(json.loads(PROD_AUDIT.read_text()))
    check_audit(diag_audit, prod_audit)
    n, d = build_step().digest(gen)
    after = prod_snapshot()
    need(after == before, "PRODUCTION TREE CHANGED during diagnostic generation")
    manifest = {"format": "R3HD_DIAG_TREE_V1", "diagnostic": "guest SEH disabled; never compatibility evidence",
                "manifest_change": [FLAG_ON, FLAG_OFF], "manifest_sha256": sha((DIAG / "r3hd_manifest.toml").read_bytes()),
                "codegen_files": n, "codegen_digest": d, "seh_emission": {"__try": try_count, "M4Init": m4},
                "audit": diag_audit, "production_audit": prod_audit,
                "production_unchanged": True, "production": {k: v for k, v in before.items() if k != "generated_sha256"},
                "production_generated_files": len(before["generated_sha256"]),
                "generated_sha256": tree_hashes(gen),
                "src_sha256": {p.name: sha(p.read_bytes()) for p in sorted((DIAG / "src").iterdir())}}
    (DIAG / "diag_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"R3HD_DIAG_TREE PASS files={n} digest={d} audit={json.dumps(diag_audit, sort_keys=True)} "
          f"production_digest={before['codegen_digest']} production_unchanged=1")
    return 0


def check():
    m = json.loads((DIAG / "diag_manifest.json").read_text())
    need((DIAG / MARKER).is_file(), "marker missing")
    need(m["generated_sha256"] == tree_hashes(DIAG / "generated/default"), "diagnostic generated tree changed")
    snap = prod_snapshot()
    need({k: v for k, v in snap.items() if k != "generated_sha256"} == m["production"] and
         len(snap["generated_sha256"]) == m["production_generated_files"], "production tree differs from the record")
    print(f"R3HD_DIAG_TREE CHECK PASS files={m['codegen_files']} digest={m['codegen_digest']} production unchanged")
    return 0


def package(zip_path):
    check()
    names = [MARKER, "diag_manifest.json", "r3hd_manifest.toml", "target_audit.json"]
    names += [f"generated/default/{n}" for n in json.loads((DIAG / "diag_manifest.json").read_text())["generated_sha256"]]
    names += [f"src/{p.name}" for p in sorted((DIAG / "src").iterdir())]
    entries = {n: (DIAG / n).read_bytes() for n in names}
    entries["PRIVATE_MANIFEST.json"] = (json.dumps({n: sha(b) for n, b in sorted(entries.items())}, indent=1) + "\n").encode()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in sorted(entries):
            info = zipfile.ZipInfo(f"rex_linux_diag/{n}", date_time=(2026, 11, 6, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, entries[n])
    data = Path(zip_path).read_bytes()
    Path(str(zip_path) + ".sha256").write_text(f"{sha(data)}  {Path(zip_path).name}\n")
    print(f"R3HD_DIAG_PACKAGE entries={len(entries)} size={len(data)} sha256={sha(data)} (PRIVATE: game-derived code)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--replace", action="store_true", help="replace an existing marked diagnostic tree")
    sub.add_parser("check")
    p = sub.add_parser("package")
    p.add_argument("--zip", type=Path, required=True)
    args = ap.parse_args()
    try:
        return {"generate": lambda: generate(args.replace), "check": check, "package": lambda: package(args.zip)}[args.cmd]()
    except Fail as error:
        print(f"R3HD_DIAG_TREE FAIL {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""G6-P104 (D-343 / E-587): focused offline regression for production_identity.json and build_identity.py."""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "experiments" / "modding_feasibility"))
import build_identity as bi  # noqa: E402


def main():
    results = {}

    def check(name, cond):
        results[name] = bool(cond)

    rec = json.loads(bi.RECORD.read_text(encoding="utf-8"))
    check("schema is 1", rec.get("schema") == 1)
    check("current is v1.3.0 (D-335)", rec["current"].get("decision") == "D-335")
    check("development is D-313 policy", rec["development"].get("decision") == "D-313")
    check(
        "current and development hashes are distinct",
        rec["current"]["binaries"] != rec["development"]["binaries"],
    )

    hist_decisions = [h.get("decision") for h in rec.get("history", [])]
    check("history decisions are unique", len(hist_decisions) == len(set(hist_decisions)))
    for d in ("D-332", "D-299", "D-313", "D-331", "D-329", "D-328", "D-292", "D-286"):
        check(f"history retains {d}", d in hist_decisions)

    # Live development and retained release/historical checks
    ok_dev, _, det_dev = bi.verify("development")
    check(
        "development identity passes with log/timestamp/ancestry",
        ok_dev and det_dev.get("log_ok") and det_dev.get("written_in_replay") and det_dev.get("commit_in_history"),
    )
    ok_rel, _, _ = bi.verify("release")
    check("release identity (v1.3.0) passes on retained artifact", ok_rel)

    for d in ("D-332", "D-299", "D-313", "D-331", "D-329", "D-328", "D-292"):
        ok_h, _, _ = bi.verify(d)
        check(f"historical identity {d} passes on retained artifact", ok_h)

    ok_286, lbl_286, _ = bi.verify("D-286", names=("r3hd.exe", "rexruntime.dll"))
    check("D-286 without retained artifact fails UNAVAILABLE", (not ok_286) and ("UNAVAILABLE" in lbl_286))

    # Cross-mismatch negative controls
    dev_dir = ROOT / rec["development"]["build_dir"]
    rel_dir = ROOT / rec["current"]["artifact"]
    check("release rejects live development binaries", not bi.verify("release", bdir=dev_dir)[0])
    check("development rejects v1.3.0 release binaries", not bi.verify("development", bdir=rel_dir)[0])
    check("unknown identity rejected", not bi.verify("D-9999")[0])

    # _log_ok positive and negative controls
    check("log_ok accepts direct build_milestone8.bat M8_BUILD_OK", bi._log_ok("PASS\r\nM8_BUILD_OK\r\n"))
    check(
        "log_ok accepts wrapped M8_BUILD_OK + BUILD_SCRIPT_ENDED rc=0",
        bi._log_ok("M8_BUILD_OK\r\nBUILD_SCRIPT_ENDED rc=0 start=1 end=2\r\n"),
    )
    check("log_ok rejects empty log", not bi._log_ok(""))
    check("log_ok rejects missing M8_BUILD_OK", not bi._log_ok("PASS\r\nBUILD_SCRIPT_ENDED rc=0\r\n"))
    check("log_ok rejects trailing error after M8_BUILD_OK", not bi._log_ok("M8_BUILD_OK\r\nERROR\r\n"))
    check(
        "log_ok rejects wrapped non-zero rc",
        not bi._log_ok("M8_BUILD_OK\r\nBUILD_SCRIPT_ENDED rc=1 start=1 end=2\r\n"),
    )
    check(
        "log_ok rejects trailing error after BUILD_SCRIPT_ENDED rc=0",
        not bi._log_ok("M8_BUILD_OK\r\nBUILD_SCRIPT_ENDED rc=0\r\nEXTRA FAIL\r\n"),
    )

    # Synthetic development negative controls in a temp folder inside private/work (so git merge-base sees the repo)
    synth_base = ROOT / "private" / "work" / "g6p104"
    synth_base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=synth_base) as td:
        tmp = Path(td)
        bdir = tmp / "bin"
        bdir.mkdir()
        logp = tmp / "build.log"
        logp.write_text("M8_BUILD_OK\n", encoding="utf-8")
        bins = {}
        for n in bi.NAMES:
            p = bdir / n
            data = f"synthetic-{n}".encode()
            p.write_bytes(data)
            bins[n] = hashlib.sha256(data).hexdigest()
        # Keep log mtime >= binary mtime so written_in_replay can succeed when valid
        ls = os.stat(logp)
        t_start = bi._birth(ls)
        t_end = max(t_start, max(os.stat(bdir / n).st_mtime for n in bi.NAMES)) + 1.0
        os.utime(logp, (t_end, t_end))

        synth = {
            "development": {
                "decision": "D-313",
                "source_commit": rec["development"]["source_commit"],
                "build_log": "build.log",
                "build_dir": "bin",
                "binaries": dict(bins),
            }
        }
        check("synthetic direct M8_BUILD_OK development passes", bi.verify("development", record=synth, root=tmp)[0])

        # Mutate binary timestamp past log end
        os.utime(bdir / "r3hd.exe", (t_end + 5.0, t_end + 5.0))
        check("synthetic post-log mtime rejected", not bi.verify("development", record=synth, root=tmp)[0])
        os.utime(bdir / "r3hd.exe", (t_end - 0.5, t_end - 0.5))

        # Mutate log to non-zero wrapper rc
        logp.write_text("M8_BUILD_OK\nBUILD_SCRIPT_ENDED rc=1\n", encoding="utf-8")
        os.utime(logp, (t_end, t_end))
        check("synthetic wrapped rc=1 log rejected", not bi.verify("development", record=synth, root=tmp)[0])

        # Mutate commit to non-ancestor hash
        logp.write_text("M8_BUILD_OK\n", encoding="utf-8")
        os.utime(logp, (t_end, t_end))
        bad_commit = dict(synth, development=dict(synth["development"], source_commit="0" * 40))
        check("synthetic non-ancestor commit rejected", not bi.verify("development", record=bad_commit, root=tmp)[0])

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for k, v in results.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"G6P104_PRODUCTION_IDENTITY_REGRESSION {'PASS' if passed == total else 'FAIL'} {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

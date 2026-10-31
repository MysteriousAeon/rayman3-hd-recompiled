"""HD+ lighting research (E-345). Usage: hdl_redcorrection_census.py [RUN_DIR...]

Census of the title's final red-correction pass (pixel shader DB19DF80422CD907, source psm/redcorrection.psh) in
M22 draw traces: for every traced frame, whether the pass runs and its coefficients (pixel constant c0: a pixel
whose red share r/(r+g+b) is at least c0.x gets green and blue raised so that the share becomes c0.x/(c0.x+c0.y)),
and which other post-processing pixel shaders run. Default: every run under private/work/m6_runs. Prints metadata
only; the traces stay under private/."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m22_draw_report as R

ROOT = Path(__file__).resolve().parents[1]
RED = 0xDB19DF80
POST = {0xE8819B7C: "mlaa_edge", 0x6EA2E39A: "mlaa_weight", 0xF796F61C: "mlaa_blend", RED: "redcorrection"}


def frame(trace):
    draws, _, _ = R.parse(trace)
    post = [POST[d["ps"] >> 32] for d in draws if (d["ps"] >> 32) in POST]
    coef = [tuple(round(R.f32(x), 3) for x in d["consts"][256 * 4:256 * 4 + 2]) for d in draws if (d["ps"] >> 32) == RED]
    return len(draws), post, coef


def main():
    runs = [Path(a) for a in sys.argv[1:]] or sorted(p for p in (ROOT / "private" / "work" / "m6_runs").iterdir() if p.is_dir())
    by_coef = {}
    for run in runs:
        for t in sorted(run.glob("m22_draws_*.bin")):
            try:
                n, post, coef = frame(t)
            except Exception as e:  # noqa: BLE001 - a truncated trace is reported, not fatal
                print(f"{run.name} {t.name}: unreadable ({e})")
                continue
            by_coef.setdefault(tuple(coef) or "none", set()).add(run.name)
            if len(sys.argv) > 1:
                print(f"{run.name} {t.name}: draws {n} post {post} red-correction c0 {coef or '-'}")
    for coef, names in sorted(by_coef.items(), key=str):
        if coef == "none":
            print(f"no red-correction pass: {len(names)} runs")
        else:
            cap = coef[0][0] / (coef[0][0] + coef[0][1])
            print(f"c0 {coef} (red share capped at {cap:.3f}): {len(names)} runs: {', '.join(sorted(names))}")


if __name__ == "__main__":
    main()

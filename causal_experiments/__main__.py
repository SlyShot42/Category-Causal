"""Run the core experiments or regenerate paper outputs from measured CSVs."""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["full", "smoke"], default="full")
    parser.add_argument("--output-dir", type=Path, help="Defaults to experiments_output/focused/<profile>.")
    parser.add_argument("--render-only", action="store_true", help="Rebuild tables and figures from saved CSVs.")
    args = parser.parse_args()
    if sys.flags.optimize:
        parser.error("Run without -O: the experimental correctness checks use assertions.")
    root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".runtime" / "matplotlib"))
    os.environ.setdefault("MPLBACKEND", "Agg")
    from .artifacts import write_paper_tables, record_presentation
    from .experiments import (
        RunConfig, start_run, build_small_collection, run_observational_checks,
        run_observational_distributions, run_intervention_checks, run_running_example,
        run_diagnostics, run_duplication_comparison, run_structural_benchmarks,
        run_supporting_validation, finalize_run,
    )
    from .plots import plot_running_example, plot_scaling
    import matplotlib.pyplot as plt
    out = args.output_dir or root / "experiments_output" / "focused" / args.profile
    if not args.render_only:
        full = args.profile == "full"
        config = RunConfig(
            profile=args.profile, small_sizes=[8, 16, 32] if full else [8],
            small_modules=[2, 4] if full else [2], small_copies=[0.0, 0.25],
            small_families=["chain", "layered", "random_acyclic"],
            small_seeds=list(range(10)) if full else [0],
            scale_sizes=[100, 1000, 10000] if full else [100],
            scale_modules=[2, 4, 8] if full else [2], scale_copies=[0.0, 0.25, 0.5],
            scale_seeds=[0, 1, 2] if full else [0], timing_repetitions=5,
        )
        run = start_run(root, config, output_dir=out)
        instances, correctness = build_small_collection(run)
        observational = run_observational_checks(run, instances)
        laws = run_observational_distributions(run, instances)
        interventions, distributions, correctness = run_intervention_checks(run, instances, correctness, laws)
        run_running_example(run)
        diagnostics, suite, assemblies = run_diagnostics(run)
        duplication, _ = run_duplication_comparison(run, instances)
        timings, memory, _ = run_structural_benchmarks(run)
        supporting = run_supporting_validation(run, suite, assemblies)
    write_paper_tables(out)
    for figure in [plot_running_example(out), *plot_scaling(out)]:
        plt.close(figure)
    if not args.render_only:
        finalize_run(run, correctness, observational, interventions, distributions,
                     diagnostics, duplication, timings, memory, supporting)
    record_presentation(out)
    print(f"Tables and figures saved to {out}")


if __name__ == "__main__":
    main()

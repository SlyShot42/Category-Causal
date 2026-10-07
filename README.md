# Reproducing the experiments

This anonymous supplement contains the experiment notebook, helper modules,
generated descriptors, independently checked certificates, measured CSVs, and
paper figures. The code is licensed under MIT; see `LICENSE`.

The supplementary archive includes the reference run in
`experiments_output/focused/full/` (descriptors, certificates, CSVs, figures,
and `run_manifest.json`). A code-only copy of this repository does not include
that directory; run the full command below to regenerate it before using
`--render-only`. Submit the supplementary ZIP for anonymous review; a normal
GitHub URL and Git history retain account and author information.

## Installation

The reference environment uses **Python 3.13.5**. From this directory:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

`requirements.txt` pins NumPy 2.1.3, pandas 2.2.3, Matplotlib 3.10.0, and all
direct notebook dependencies. No editable installation, external data, reference
PDFs, network access after installation, or accelerator is needed. On Windows,
use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.

## Commands and notebook cells

Run all experiments and regenerate every empirical table and figure:

```sh
.venv/bin/python -m causal_experiments --profile full
```

This uses the notebook's helpers and configuration and writes to
`experiments_output/focused/full/`. Reruns overwrite the selected outputs.
To preserve the supplied reference run, add `--output-dir results/full`.
Use normal Python execution: `-O` and `PYTHONOPTIMIZE` disable correctness checks.

Rebuild paper outputs from the supplied measurements without rerunning experiments:

```sh
.venv/bin/python -m causal_experiments --profile full --render-only
```

Each command below rebuilds the listed output and the other paper outputs. To
regenerate measurements first, run the full command above. All output paths in
the table are relative to `experiments_output/focused/full/`.

| Paper item | Command after installation | Notebook cells | Output and measured inputs |
| --- | --- | --- | --- |
| Table 2: paired duplicate comparison | `.venv/bin/python -m causal_experiments --profile full --render-only` | B4, B9, B13 | `duplicate_acceptance.csv`, from `duplication_summary.csv` |
| Table 3: executed exact checks | `.venv/bin/python -m causal_experiments --profile full --render-only` | B4–B6, B13 | `exact_checks_summary.csv`, from `correctness.csv`, `evaluation_checks.csv`, `intervention_checks.csv`, and `distribution_checks.csv` |
| Table 4: diagnostic outcomes | `.venv/bin/python -m causal_experiments --profile full --render-only` | B8, B13 | `diagnostic_summary.csv`, from `diagnostics.csv` |
| Table 5: structural resources at `n=10000` | `.venv/bin/python -m causal_experiments --profile full --render-only` | B10, B13 | Rows with `n=10000` in `appendix_scaling_summary.csv`, from `timing_summary.csv` and `memory.csv` |
| Figure 2: runtime | `.venv/bin/python -m causal_experiments --profile full --render-only` | B10–B11 | `figures/runtime.{pdf,png,svg}`, from timing CSVs |
| Figure 3: running example | `.venv/bin/python -m causal_experiments --profile full --render-only` | B7 | `figures/running_example.{pdf,png,svg}`, from `running_example_values.csv` and `running_example_response.csv` |
| Figure 4: stage contributions | `.venv/bin/python -m causal_experiments --profile full --render-only` | B10–B11 | `figures/stage_breakdown.{pdf,png,svg}` and `appendix_stage_summary_ms.csv`, from `timings.csv` |
| Figure 5: traced allocation | `.venv/bin/python -m causal_experiments --profile full --render-only` | B10–B11 | `figures/memory.{pdf,png,svg}`, from `memory.csv` |

The manuscript uses these image names: `runtimefigs.png` (Figure 2, from
`figures/runtime.png`), `runningexample.png` (Figure 3, from
`figures/running_example.png`), `stagebreakdown.png` (Figure 4, from
`figures/stage_breakdown.png`), and `memoryfigs.png` (Figure 5, from
`figures/memory.png`). Table 1 and Figure 1 are analytic and have no generated
output. Table 2 reports accepted counts out of 180 diagrams per condition.
Table 4 includes F01–F15 and the supporting F16–F19 fixtures.
`appendix_scaling_summary.csv` covers all 27 size/module/copy settings; Table 5
shows the nine settings at `n=10000`. `appendix_stage_summary_ms.csv` gives the
stage medians in milliseconds plotted in Figure 4. Round exported CSV values to
the precision used in the manuscript.

Rebuild the anonymous submission archive after changing released files:

```sh
.venv/bin/python -m causal_experiments --profile full --render-only --package
```

This writes `supplementary_material.zip` containing only the source, README,
license, requirements, tests, and completed reference artifacts. It excludes Git
history, environments, caches, and unrelated files, checks for identifying paths
and email addresses, and includes `SHA256SUMS`. From a code-only copy, run the
full profile first. The archive's artifact paths match the paths above.

For interactive execution:

```sh
.venv/bin/python -m ipykernel install --prefix .venv --name category-causal --display-name "Python 3.13 (experiments)"
.venv/bin/python -m jupyterlab category_causal_experiments.ipynb
```

Select **Python 3.13 (experiments)** and run B1–B13 in order. Released notebook
outputs, execution counts, and metadata are cleared. Restart the kernel after
helper changes. `CATEGORY_PROFILE=smoke` selects the small notebook profile;
`CATEGORY_OUTPUT_DIR` sets a different notebook output directory.

Quick end-to-end reproduction and core regression checks:

```sh
.venv/bin/python -m causal_experiments --profile smoke --output-dir results/smoke
.venv/bin/python -m unittest discover -s tests -v
```

## Generation settings

Each correctness SCM has four Boolean exogenous variables. For each endogenous
size in `{8, 16, 32}`, each family (`chain`, `layered`, `random_acyclic`)
uses ten seeds: `{0, 1, 2, 3, 4, 5, 6, 7, 8, 9}`. These 90 ground models each
yield four diagrams using module counts `{2, 4}` and mechanism-copy fractions
`{0, 0.25}`. Local identifiers are independently renamed. The complete
procedures are in `generation.py` and `fragmentation.py`.

The duplicate comparison takes the 180 zero-copy diagrams and 180 diagrams
with copy fraction 0.25, retains variable-only interfaces, and gives identical
inputs to raw and deduplicated assembly. From each copied diagram, a control
changes one copied equation to a different mechanism code with the same ordered
signature. Both methods check all 180 controls: 1,080 method cases overall.
Its recovery metric compares Var/Mech/Input; the separate four-table checks
account for representation-specific dependency multiplicity.

The 81 runtime configurations use `random_acyclic` models with endogenous sizes
`{100, 1000, 10000}`, 16 exogenous variables, module counts `{2, 4, 8}`,
copy fractions `{0, 0.25, 0.5}`, and seeds `{0, 1, 2}`. Each has one warm-up,
five timed repetitions, and a separate allocation run. Loops execute sequentially.
Generation, serialization, evaluation, plotting, and independent correctness
checks are excluded from the structural stage total. Parsing and normalization
are recorded separately.

Correctness checks exhaust all 16 exogenous assignments, no intervention, and
every singleton Boolean intervention: 220,800 distinct scenarios and 441,600
checks through two routes. Uniform, independent product with success probabilities
`(1/5, 2/5, 3/5, 4/5)`, and correlated all-zero/all-one laws give 82,800 exact
law/route cases. Local inputs retain the induced joint exogenous/boundary law.

Runtime bars show medians and interquartile ranges across seeds/repetitions.
Stage bars show separate stage medians at `n=10000`. Allocation bars show
medians and minimum–maximum seed ranges. `tracemalloc` measures allocations
during assembly, excluding the existing input object; these are not process RSS.

## Hardware and expected runtime

The reference full run used **Apple M3 Max (ARM64, 14 logical CPUs) with 36 GB
of RAM**, macOS 26.3.1, Python 3.13.5, and the pinned scientific libraries.
The manifest records **7 minutes 48 seconds** for the full run; allow about
**10 minutes** on comparable hardware, excluding installation. Smoke runs and
rendering saved CSVs take a few seconds. Full outputs occupy about 255 MB before
compression. No GPU is used. Timing and allocation vary by machine; finite
semantic checks are exact.

## Artifacts and provenance

Within `experiments_output/focused/full/`, `datasets/` holds ground equations, module/interface records, mechanism
libraries, configurations/seeds, noise-law descriptions, and oracle-only ground
correspondences. `certificates/` holds structural certificates, diagnostic
witnesses, and representative intervention certificates; all intervention
certificates are checked during execution. CSVs hold numerical results.
`run_manifest.json` records configuration, counts, environment, and SHA-256 hashes.

The reference run's `release` entry records the current notebook/helper hashes
and hashes of the released CSVs. `measurement_csv_sha256` retains the original
CSV hashes before metadata labels were renamed. Numerical measurements are
unchanged; diagnostic scope is now `primary` or `supporting`, and obsolete
private-document provenance is omitted. New runs record the released source
hashes directly. The package excludes Git history, environments/caches,
walkthroughs, narrative reports, and identifying paths.

## Software citations and licenses

The manuscript cites the scientific libraries used:

- Harris et al. (2020), *Array programming with NumPy*, Nature 585, 357–362.
  [NumPy citation](https://numpy.org/citing-numpy/).
- McKinney (2010), *Data structures for statistical computing in Python*,
  Proceedings of the 9th Python in Science Conference, 56–61.
  [pandas citation](https://pandas.pydata.org/about/citing.html).
- Hunter (2007), *Matplotlib: A 2D graphics environment*, Computing in Science
  & Engineering 9(3), 90–95.
  [Matplotlib citation](https://matplotlib.org/3.10.0/project/citing.html).

NumPy and pandas use BSD-3-Clause:
[NumPy license](https://github.com/numpy/numpy/blob/v2.1.3/LICENSE.txt),
[pandas license](https://github.com/pandas-dev/pandas/blob/v2.2.3/LICENSE).
Matplotlib uses its
[PSF-based Matplotlib license](https://matplotlib.org/3.10.0/project/license.html).
Dependencies retain their own licenses; MIT applies to this repository's code.

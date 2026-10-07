"""JSON descriptors, measured CSV exports, and reproducible instance releases."""
from __future__ import annotations
import gzip, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from .records import diagram_json, description_json
from .mechanisms import LIBRARY, library_json


def dump_json(path, value, compressed=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with (gzip.open if compressed else open)(path, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_csv(out, name, rows):
    frame = pd.DataFrame(rows)
    frame.to_csv(Path(out) / name, index=False)
    return frame


def release_instance(folder, ground, diagram, oracle, configuration, compressed=False, write_datasets=True):
    if not write_datasets: return
    suffix = ".json.gz" if compressed else ".json"
    raw = diagram_json(diagram)
    payloads = {
        "ground_model": {**description_json(ground.description), "ordered_equations": ground.equations, "exogenous_order": ground.exogenous},
        "modules": raw["modules"], "interfaces": raw["interfaces"], "oracle_map": oracle,
        "mechanism_library": library_json(LIBRARY),
        "noise_laws": {"uniform": True, "independent_probabilities": ["1/5", "2/5", "3/5", "4/5"] if len(ground.exogenous) == 4 else None,
                       "correlated": {"all_zero": "1/2", "all_one": "1/2"}},
        "manifest": {**configuration, "generator_version": "co10-modular-v2",
                     "variable_only_route": "retain Var records and Var maps in each supplied full interface",
                     "representation": "one dependency occurrence per ordered input"}}
    for name, payload in payloads.items(): dump_json(folder / (name + suffix), payload, compressed)


def write_paper_tables(out):
    """Rebuild empirical table values from the measured CSVs, without timing runs."""
    from .experiments import STAGES
    out = Path(out)
    duplicate = pd.read_csv(out / "duplication_summary.csv")
    duplicate["condition"] = ["Conflicting codes" if variant == "equation_conflict" else
                              "No copies" if fraction == 0 else "Identical copies"
                              for variant, fraction in zip(duplicate.variant, duplicate.copy_fraction)]
    comparison = duplicate.pivot(index="condition", columns="mode", values="accepted")
    comparison = comparison.loc[["No copies", "Identical copies", "Conflicting codes"], ["raw", "deduplicated"]]
    comparison.rename(columns={"raw": "Raw", "deduplicated": "With DE"}).to_csv(out / "duplicate_acceptance.csv")

    diagnostics = pd.read_csv(out / "diagnostics.csv")
    table = diagnostics.pivot(index="fixture", columns="mode", values="actual_valid")
    table = table.join(diagnostics.groupby("fixture").notes.first())
    table.to_csv(out / "diagnostic_summary.csv")

    timings = pd.read_csv(out / "timings.csv")
    scaling = pd.read_csv(out / "timing_summary.csv").rename(columns={"n_endogenous": "n"})
    memory = pd.read_csv(out / "memory.csv")
    if not memory.empty:
        allocation = memory.assign(peak_MiB=memory.peak_python_bytes / 2**20).groupby(
            ["n_endogenous", "modules", "copy_fraction"]).agg(
                median_peak_MiB=("peak_MiB", "median"), min_peak_MiB=("peak_MiB", "min"),
                max_peak_MiB=("peak_MiB", "max")).reset_index().rename(columns={"n_endogenous": "n"})
        scaling = scaling.merge(allocation, on=["n", "modules", "copy_fraction"], validate="one_to_one")
    columns = ["n", "modules", "copy_fraction", "median_N_plus_R", "median_s", "q25_s", "q75_s"]
    columns += [name for name in ["median_peak_MiB", "min_peak_MiB", "max_peak_MiB"] if name in scaling]
    scaling[columns].to_csv(out / "appendix_scaling_summary.csv", index=False)
    largest = timings[timings.n_endogenous == timings.n_endogenous.max()]
    (largest.groupby(["modules", "copy_fraction"])[STAGES].median() * 1000).to_csv(out / "appendix_stage_summary_ms.csv")


def record_presentation(out):
    """Hash the measured inputs, renderer, table exports, and current figures."""
    out = Path(out)
    root = Path(__file__).resolve().parents[1]
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    figures = [p for p in (out / "figures").iterdir() if p.suffix in {".pdf", ".png", ".svg"}]
    tables = [out / name for name in ["duplicate_acceptance.csv", "diagnostic_summary.csv",
                                    "appendix_scaling_summary.csv", "appendix_stage_summary_ms.csv"]]
    dump_json(out / "figures" / "presentation_manifest.json", {
        "rendered_utc": datetime.now(timezone.utc).isoformat(),
        "measurement_manifest": "../run_manifest.json",
        "measurement_manifest_sha256": digest(out / "run_manifest.json"),
        "input_csv_sha256": {p.name: digest(p) for p in sorted(out.glob("*.csv")) if p not in tables},
        "renderer_sha256": {"causal_experiments/" + name: digest(root / "causal_experiments" / name)
                            for name in ["plots.py", "artifacts.py", "experiments.py"]},
        "presentation_outputs_sha256": {p.name: digest(p) for p in sorted(figures + tables)},
    })

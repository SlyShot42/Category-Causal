"""JSON descriptors, measured CSV exports, and reproducible instance releases."""
from __future__ import annotations
import getpass, gzip, hashlib, json, os, re, tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import pandas as pd
from .records import diagram_json, description_json
from .mechanisms import LIBRARY, library_json

PAPER_INPUTS = (
    "correctness.csv", "evaluation_checks.csv", "intervention_checks.csv",
    "distribution_checks.csv", "diagnostics.csv", "duplication_summary.csv",
    "timings.csv", "timing_summary.csv", "memory.csv",
    "running_example_values.csv", "running_example_response.csv",
)


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
    correctness = pd.read_csv(out / "correctness.csv")
    exact = correctness.groupby("n_endogenous").agg(
        diagrams=("instance", "count"), observational_cases=("observational_scenarios", "sum"),
        interventional_cases=("interventional_scenarios", "sum"))
    evaluations = pd.read_csv(out / "evaluation_checks.csv")
    interventions = pd.read_csv(out / "intervention_checks.csv")
    exact["route_checks"] = evaluations.groupby("n_endogenous").assignments.sum() + interventions.groupby("n_endogenous").assignments.sum()
    exact["law_cases"] = pd.read_csv(out / "distribution_checks.csv").groupby("n_endogenous").size()
    exact.loc["Total"] = exact.sum()
    exact.rename_axis("n").to_csv(out / "exact_checks_summary.csv")
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
    tables = [out / name for name in ["exact_checks_summary.csv", "duplicate_acceptance.csv", "diagnostic_summary.csv",
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


def package_supplementary(root, out):
    """Export the completed reference run and required sources without local files."""
    root, out = Path(root), Path(out)
    manifest = json.loads((out / "run_manifest.json").read_text())
    if manifest["status"] != "complete" or manifest["profile"] != "full":
        raise ValueError("Package a completed full run; first run --profile full.")
    for name, expected in manifest["output_sha256"].items():
        if hashlib.sha256((out / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Recorded CSV hash does not match: {name}")
    notebook_path = root / "category_causal_experiments.ipynb"
    notebook = json.loads(notebook_path.read_text())
    code = "\n".join("".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code")
    notebook["metadata"] = {}
    for cell in notebook["cells"]:
        cell["metadata"] = {}
        if cell["cell_type"] == "code":
            cell["outputs"], cell["execution_count"] = [], None
    helpers = sorted((root / "causal_experiments").glob("*.py")) + sorted((root / "tests").glob("*.py"))
    manifest.pop("source_sha256", None)
    manifest["release"] = {
        "measurements_rerun": False,
        "changes": ["Anonymous source and artifact export", "Primary/supporting diagnostic labels", "CSV-derived paper tables"],
        "notebook_code_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "helper_sha256": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in helpers},
        "artifact_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob("*.csv"))},
    }
    dump_json(out / "run_manifest.json", manifest)
    record_presentation(out)
    files = [root / name for name in [".gitignore", "README.md", "LICENSE", "requirements.txt"]] + [notebook_path] + helpers
    files += sorted(p for p in out.rglob("*") if p.is_file() and p.suffix in {".csv", ".json", ".gz", ".pdf", ".png", ".svg"})
    patterns = [rb"/(?:Users|home)/", rb"[A-Za-z]:\\Users\\",
                rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"]
    username = getpass.getuser()
    if username.lower() not in {"root", "user", "runner", "ubuntu", "anonymous"}:
        patterns.append(rb"\b" + re.escape(username.encode()) + rb"\b")
    identifying = re.compile(b"|".join(patterns), re.I)
    destination = root / "supplementary_material.zip"
    with tempfile.NamedTemporaryFile(prefix="supplement-", suffix=".zip", dir=root, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        checksums = []
        with ZipFile(temporary_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(files):
                name = path.relative_to(root).as_posix() if path.is_relative_to(root) and not path.is_relative_to(out) else "experiments_output/focused/full/" + path.relative_to(out).as_posix()
                data = (json.dumps(notebook, indent=1, ensure_ascii=False) + "\n").encode() if path == notebook_path else path.read_bytes()
                searchable = gzip.decompress(data) if path.suffix == ".gz" else data
                if identifying.search(searchable):
                    raise ValueError(f"Identifying content found in release file: {name}")
                info = ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
                info.compress_type, info.external_attr = ZIP_DEFLATED, 0o644 << 16
                archive.writestr(info, data)
                checksums.append(hashlib.sha256(data).hexdigest() + "  " + name)
            info = ZipInfo("SHA256SUMS", date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, "\n".join(checksums) + "\n")
        with ZipFile(temporary_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("Supplementary ZIP integrity check failed.")
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination

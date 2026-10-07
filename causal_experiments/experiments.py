"""Paper-facing experiment runners; definitions and control code stay out of the notebook."""
from __future__ import annotations
import copy, gc, hashlib, importlib.metadata, itertools, json, os, platform, subprocess, sys, time, tracemalloc
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fractions import Fraction
from functools import wraps
from pathlib import Path
import numpy as np
import pandas as pd
from .records import SORTS, InvalidDiagram, diagram_json, diagram_from_json
from .mechanisms import LIBRARY, library_json, validate_library
from .assembly import assemble
from .global_validation import embedding_diagnostics
from .local_validation import validate_model
from .quotient import normalize
from .certificates import certificate_json, check_certificate, check_interface_witness
from .evaluation import compile_evaluator
from .interventions import intervention_library, surgery_description, surgery_diagram
from .reconstruction import reconstruction_oracle, retained_record_isomorphism
from .generation import generate_ground
from .fragmentation import fragment_ground, variables_only, instance_name, shuffled
from .oracles import connected_component_oracle, partition_from_qmaps, direct_ground_evaluate
from .fixtures import build_fixtures
from .distributions import distribution_checks
from .artifacts import dump_json, release_instance
from .validation_checks import run_supporting_checks

ROUTES = [("raw", "diagram", "raw", "raw_map"),
          ("deduplicated", "var_diagram", "dedup", "dedup_map")]
STAGES = ["input_validation_s", "equivalence_s", "duplicate_elimination_s", "quotient_reconstruction_s", "global_validation_s"]


@dataclass
class RunConfig:
    """Visible notebook design parameters; all completed counts are measured from actual runs."""
    profile: str
    small_sizes: list[int]
    small_modules: list[int]
    small_copies: list[float]
    small_families: list[str]
    small_seeds: list[int]
    scale_sizes: list[int]
    scale_modules: list[int]
    scale_copies: list[float]
    scale_seeds: list[int]
    timing_repetitions: int = 5
    write_datasets: bool = True
    measure_memory: bool = True
    small_exogenous: int = 4
    scale_exogenous: int = 16

    def __post_init__(self):
        assert self.profile in {"full", "smoke"}
        assert self.small_exogenous == 4, "The three specified laws require four Boolean noise coordinates."
        assert self.scale_exogenous > 0 and self.timing_repetitions > 0
        assert all(0 <= f <= 1 for f in self.small_copies + self.scale_copies)
        assert max(self.small_modules) <= min(self.small_sizes)
        assert max(self.scale_modules) <= min(self.scale_sizes)
        assert set(self.small_families) <= {"chain", "layered", "random_acyclic"}

    @property
    def small_grid(self):
        return list(itertools.product(self.small_sizes, self.small_modules, self.small_copies, self.small_families, self.small_seeds))

    @property
    def scale_grid(self):
        return list(itertools.product(self.scale_sizes, self.scale_modules, self.scale_copies, self.scale_seeds))


@dataclass
class RunContext:
    """Output paths, environment provenance, phase status, and retained failure details."""
    root: Path
    config: RunConfig
    out: Path
    manifest: dict

    def save_manifest(self):
        dump_json(self.out / "run_manifest.json", self.manifest)

    def complete(self, phase, **counts):
        self.manifest["completed"][phase] = {**counts, "passed": True}
        self.save_manifest()

    def write_csv(self, name, rows):
        frame = pd.DataFrame(rows)
        frame.to_csv(self.out / name, index=False)
        return frame

    def verify_code(self):
        for name, expected in self.manifest["helper_sha256"].items():
            assert hashlib.sha256((self.root / name).read_bytes()).hexdigest() == expected, f"Source changed during run: {name}"


def hardware_details():
    """Record hardware without usernames, hostnames, or filesystem paths."""
    details = {"machine": platform.machine(), "processor": platform.processor(),
               "logical_cpus": os.cpu_count(), "ram_bytes": None}
    if platform.system() == "Darwin":
        for field, key in [("machdep.cpu.brand_string", "processor"), ("hw.memsize", "ram_bytes")]:
            result = subprocess.run(["/usr/sbin/sysctl", "-n", field], capture_output=True, text=True)
            if result.returncode == 0:
                value = result.stdout.strip()
                details[key] = int(value) if key == "ram_bytes" else value
    return details


def start_run(root, config, notebook_path=None, output_dir=None):
    """Start a portable run using only the released notebook and helpers."""
    root = Path(root).resolve()
    assert validate_library(LIBRARY)
    out = Path(output_dir) if output_dir is not None else root / "experiments_output" / "focused" / config.profile
    for directory in [out, out / "datasets", out / "certificates", out / "failures", out / "figures"]:
        directory.mkdir(parents=True, exist_ok=True)
    path = Path(notebook_path or os.environ.get("CATEGORY_NOTEBOOK_PATH", root / "category_causal_experiments.ipynb"))
    code = "\n".join("".join(c["source"]) for c in json.loads(path.read_text())["cells"] if c["cell_type"] == "code")
    helpers = list((root / "causal_experiments").glob("*.py")) + list((root / "tests").glob("*.py"))
    manifest = {
        "execution_notebook": path.resolve().relative_to(root).as_posix(), "profile": config.profile, "started_utc": datetime.now(timezone.utc).isoformat(),
        "generator_version": "co10-modular-v2", "configuration": asdict(config),
        "python": platform.python_version(), "python_implementation": platform.python_implementation(),
        "platform": platform.platform(), **hardware_details(),
        "packages": {name: importlib.metadata.version(name) for name in
                     ["jupyterlab", "ipykernel", "ipython", "nbformat", "nbclient", "matplotlib", "numpy", "pandas"]},
        "notebook_code_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "helper_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in helpers},
        "revision": "unversioned workspace; exact helper and notebook hashes recorded",
        "completed": {}, "skipped": [], "status": "running",
        "question_mapping": {"Q1": ["E1", "E3", "E4", "E5"], "Q2": ["E2", "paired duplicate-elimination comparison"], "Q3": ["E6"]}}
    run = RunContext(root, config, out, manifest)
    run.save_manifest()
    return run


def phase(name):
    """Preserve an honest partial-run status and a phase error before re-raising."""
    def decorate(function):
        @wraps(function)
        def wrapped(run, *args, **kwargs):
            try:
                return function(run, *args, **kwargs)
            except Exception as error:
                run.manifest["status"] = "failed"
                run.manifest["failed_phase"] = name
                run.manifest["error"] = repr(error)
                dump_json(run.out / "failures" / f"{name}-error.json", {"phase": name, "error": repr(error)})
                run.save_manifest()
                raise
        return wrapped
    return decorate


def assignments(ground):
    return [dict(zip(ground.exogenous, bits)) for bits in itertools.product([0, 1], repeat=len(ground.exogenous))]

def compare_semantics(ground, ground_intervention, diagram, assembly, comparison, library=LIBRARY):
    evaluate = compile_evaluator(assembly.description, library)
    locals_ = {name: compile_evaluator(m, library, closed=False) for name, m in diagram.modules.items()}
    free = {name: {v for v, r in m.tables["Var"].items() if r["role"] == "exo"} | m.boundary for name, m in diagram.modules.items()}
    observations = []
    mismatches = local_mismatches = coordinate_checks = local_coordinate_checks = 0
    max_error = 0
    for u in assignments(ground):
        expected = direct_ground_evaluate(ground.equations, u, ground_intervention)
        global_input = {cid: u[gid] for cid, gid in comparison["Var"].items() if gid in u}
        solution = evaluate(global_input)
        mapped = {comparison["Var"][cid]: value for cid, value in solution.items()}
        if mapped != expected:
            raise AssertionError({"check": "global evaluation", "assignment": u, "intervention": ground_intervention,
                "differences": {v: {"expected": expected[v], "actual": mapped.get(v)} for v in expected if mapped.get(v) != expected[v]}})
        errors = [abs(mapped[v] - expected[v]) for v in expected]
        mismatches += sum(e != 0 for e in errors); coordinate_checks += len(errors)
        max_error = max(max_error, max(errors, default=0))
        local_solutions, pullbacks, induced_inputs = {}, {}, {}
        for name, module in diagram.modules.items():
            pulled = {v: solution[assembly.qmaps["Var"][(name, v)]] for v in module.tables["Var"]}
            induced = {v: pulled[v] for v in free[name]}
            actual = locals_[name](induced)
            if actual != pulled:
                raise AssertionError({"check": "induced local evaluation", "module": name, "assignment": u,
                    "induced_inputs": induced, "differences": {v: {"expected": pulled[v], "actual": actual.get(v)}
                    for v in pulled if actual.get(v) != pulled[v]}})
            errs = [abs(actual[v] - pulled[v]) for v in pulled]
            local_mismatches += sum(e != 0 for e in errs); local_coordinate_checks += len(errs)
            max_error = max(max_error, max(errs, default=0))
            local_solutions[name] = actual; pullbacks[name] = pulled; induced_inputs[name] = induced
        observations.append({"u": u, "expected": expected, "global": mapped,
                             "locals": local_solutions, "pullbacks": pullbacks, "induced": induced_inputs})
    assert mismatches == local_mismatches == max_error == 0
    return observations, {"assignments": len(observations), "global_mismatches": mismatches,
                          "local_mismatches": local_mismatches, "max_coordinate_error": max_error,
                          "global_coordinate_checks": coordinate_checks, "local_coordinate_checks": local_coordinate_checks}


@phase('Q1_reconstruction')
def build_small_collection(run):
    OUT = run.out
    MANIFEST = run.manifest
    write_csv = run.write_csv
    SMALL_SIZES, SMALL_MODULES, SMALL_COPIES = run.config.small_sizes, run.config.small_modules, run.config.small_copies
    SMALL_FAMILIES, SMALL_SEEDS = run.config.small_families, run.config.small_seeds
    SMALL_INSTANCES, CORRECTNESS_ROWS = [], []
    SMALL_CONFIGS = list(itertools.product(SMALL_SIZES, SMALL_MODULES, SMALL_COPIES, SMALL_FAMILIES, SMALL_SEEDS))
    for index, (n, modules, copies, family, seed) in enumerate(SMALL_CONFIGS, 1):
        ident = instance_name(n, modules, copies, family, seed)
        config = {"instance": ident, "n_endogenous": n, "n_exogenous": run.config.small_exogenous, "modules": modules,
                  "copy_fraction": copies, "family": family, "seed": seed}
        ground = generate_ground(n, run.config.small_exogenous, family, seed)
        diagram, oracle, actual_copies = fragment_ground(ground, modules, copies, seed)
        release_instance(OUT / "datasets" / "small" / ident, ground, diagram, oracle, config, write_datasets=run.config.write_datasets)
        try:
            raw = assemble(diagram)
            assert raw.validation["valid"]
            assert partition_from_qmaps(raw.qmaps) == connected_component_oracle(diagram)
            raw_map = reconstruction_oracle(raw, ground.description, oracle)
            var_diagram = variables_only(diagram)
            dedup = assemble(var_diagram, mode="deduplicated")
            assert dedup.validation["valid"]
            dedup_map = reconstruction_oracle(dedup, ground.description, oracle, canonical=True)
            for d, a in [(diagram, raw), (var_diagram, dedup)]:
                assert check_certificate(d, certificate_json(a))
                alternate = assemble(shuffled(d, seed + 7919), mode=a.mode)
                assert partition_from_qmaps(a.qmaps) == partition_from_qmaps(alternate.qmaps)
            dump_json(OUT / "certificates" / "small" / f"{ident}-raw.json", certificate_json(raw))
            dump_json(OUT / "certificates" / "small" / f"{ident}-deduplicated.json", certificate_json(dedup))
        except Exception as error:
            dump_json(OUT / "failures" / f"{ident}-E1.json", {"config": config, "diagram": diagram_json(diagram), "error": repr(error)})
            raise
        pairs = sum(len(i.description.tables[s]) for i in diagram.interfaces for s in SORTS)
        row = {**config, "copied_mechanisms": actual_copies, "partition_oracle": True,
               "raw_reconstruction": True, "variable_only_DE_reconstruction": True, "certificates_valid": True,
               "shuffle_invariant": True, "identification_pairs": pairs,
               **{f"ground_{s}": len(ground.description.tables[s]) for s in SORTS},
               **{f"raw_{s}": len(raw.description.tables[s]) for s in SORTS},
               **{f"DE_{s}": len(dedup.description.tables[s]) for s in SORTS}}
        CORRECTNESS_ROWS.append(row)
        SMALL_INSTANCES.append({"config": config, "ground": ground, "diagram": diagram, "oracle": oracle,
                                "raw": raw, "raw_map": raw_map, "var_diagram": var_diagram,
                                "dedup": dedup, "dedup_map": dedup_map, "copied_mechanisms": actual_copies})
        if index % 60 == 0 or index == len(SMALL_CONFIGS): print(f"Q1 collection: {index}/{len(SMALL_CONFIGS)} reconstructed.")
    CORRECTNESS = write_csv("correctness.csv", CORRECTNESS_ROWS)
    MANIFEST["completed"]["E1"] = {"diagrams": len(SMALL_INSTANCES), "routes": 2, "passed": True}
    dump_json(OUT / "run_manifest.json", MANIFEST)
    return SMALL_INSTANCES, CORRECTNESS


@phase('Q1_observational')
def run_observational_checks(run, instances):
    OUT = run.out
    MANIFEST = run.manifest
    write_csv = run.write_csv
    SMALL_INSTANCES = instances
    OBSERVATIONAL_ROWS = []
    for instance in SMALL_INSTANCES:
        observations_by_mode = {}
        for route, dkey, akey, mapkey in [("raw", "diagram", "raw", "raw_map"), ("deduplicated", "var_diagram", "dedup", "dedup_map")]:
            try:
                observations, metrics = compare_semantics(instance["ground"], {}, instance[dkey], instance[akey], instance[mapkey])
            except Exception as error:
                dump_json(OUT / "failures" / (instance["config"]["instance"] + "-E3.json"), {"config": instance["config"], "route": route, "error": repr(error)})
                raise
            OBSERVATIONAL_ROWS.append({**instance["config"], "route": route, **metrics})
            observations_by_mode[route] = observations
        instance["observations"] = observations_by_mode
    OBSERVATIONAL = write_csv("evaluation_checks.csv", OBSERVATIONAL_ROWS)
    MANIFEST["completed"]["E3"] = {"diagrams": len(SMALL_INSTANCES), "scenarios": len(SMALL_INSTANCES) * 16,
                                   "route_assignment_checks": int(OBSERVATIONAL.assignments.sum()), "passed": True}
    dump_json(OUT / "run_manifest.json", MANIFEST)
    return OBSERVATIONAL


@phase('Q1_observational_laws')
def run_observational_distributions(run, instances):
    SMALL_INSTANCES = instances
    DISTRIBUTION_ROWS = []
    for instance in SMALL_INSTANCES:
        for route, dkey in [("raw", "diagram"), ("deduplicated", "var_diagram")]:
            checks = distribution_checks(instance["ground"], instance[dkey], instance["observations"][route])
            DISTRIBUTION_ROWS += [{**instance["config"], "route": route, "target": "none", "value": "", **r} for r in checks]
    print(f"Observational exact-law checks: {len(DISTRIBUTION_ROWS)}; intervention checks are added by E4.")
    run.complete("observational_laws", law_cases=len(DISTRIBUTION_ROWS))
    return DISTRIBUTION_ROWS


@phase('Q1_interventions')
def run_intervention_checks(run, instances, correctness, distribution_rows):
    OUT = run.out
    MANIFEST = run.manifest
    write_csv = run.write_csv
    SMALL_INSTANCES = instances
    CORRECTNESS_ROWS = correctness.to_dict("records")
    DISTRIBUTION_ROWS = list(distribution_rows)
    INTERVENTION_ROWS = []
    for index, instance in enumerate(SMALL_INSTANCES, 1):
        ground = instance["ground"]
        targets = [v for v, r in ground.description.tables["Var"].items() if r["role"] == "endo"]
        per_instance_rows = []
        for target, value in itertools.product(targets, [0, 1]):
            for route, dkey, akey, mapkey in [("raw", "diagram", "raw", "raw_map"), ("deduplicated", "var_diagram", "dedup", "dedup_map")]:
                diagram, before, comparison = instance[dkey], instance[akey], instance[mapkey]
                selected_class = next(cid for cid, gid in comparison["Var"].items() if gid == target)
                library, codes = intervention_library(before.description, {selected_class: value}, {selected_class: target})
                operated = surgery_description(before.description, codes)
                modified = surgery_diagram(diagram, before, codes)
                try:
                    assert validate_model(operated, library)["valid"]
                    after = assemble(modified, library, route)
                    assert after.validation["valid"]
                    retained_record_isomorphism(before, after, operated)
                    operated_ground = surgery_description(ground.description, {target: codes[selected_class]})
                    after_comparison = reconstruction_oracle(after, operated_ground, instance["oracle"], canonical=route == "deduplicated")
                    assert check_certificate(modified, certificate_json(after), library)
                    observations, metrics = compare_semantics(ground, {target: value}, modified, after, after_comparison, library)
                    post_evaluate = compile_evaluator(operated, library)
                    commutation_mismatches = 0
                    for o in observations:
                        inputs = {cid: o["u"][gid] for cid, gid in comparison["Var"].items() if gid in o["u"]}
                        actual = {comparison["Var"][cid]: val for cid, val in post_evaluate(inputs).items()}
                        commutation_mismatches += sum(actual[v] != o["global"][v] for v in actual)
                    assert commutation_mismatches == 0
                    exact_checks = distribution_checks(ground, modified, observations, library)
                    DISTRIBUTION_ROWS += [{**instance["config"], "route": route, "target": target, "value": value, **r} for r in exact_checks]
                    if target == targets[0] and value == 0:
                        dump_json(OUT / "certificates" / "interventions" / f'{instance["config"]["instance"]}-{route}.json',
                                  {"target": target, "value": value, "fresh_code": codes[selected_class],
                                   "certificate": certificate_json(after)})
                except Exception as error:
                    dump_json(OUT / "failures" / f'{instance["config"]["instance"]}-{route}-{target}-{value}.json',
                              {"config": instance["config"], "target": target, "value": value,
                               "diagram": diagram_json(modified), "library": library_json(library), "error": repr(error)})
                    raise
                per_instance_rows.append({**instance["config"], "route": route, "target": target, "value": value,
                                          "fresh_code": codes[selected_class], "isomorphic": True,
                                          "commutation_mismatches": commutation_mismatches, **metrics})
        INTERVENTION_ROWS.extend(per_instance_rows)
        row = CORRECTNESS_ROWS[index - 1]
        row.update({"observational_scenarios": 16, "interventions": 2 * len(targets),
                    "interventional_scenarios": 16 * 2 * len(targets), "all_scenarios": 16 * (1 + 2 * len(targets)),
                    "global_mismatches": 0, "local_mismatches": 0, "commutation_mismatches": 0})
        if index % 20 == 0 or index == len(SMALL_INSTANCES):
            print(f"Q1 interventions/laws: {index}/{len(SMALL_INSTANCES)} diagrams; {len(INTERVENTION_ROWS)} route/intervention checks.")
            write_csv("intervention_checks.csv", INTERVENTION_ROWS)
            write_csv("distribution_checks.csv", DISTRIBUTION_ROWS)
            write_csv("correctness.csv", CORRECTNESS_ROWS)
            MANIFEST["completed"]["E4_progress"] = {"diagrams": index, "route_interventions": len(INTERVENTION_ROWS)}
            dump_json(OUT / "run_manifest.json", MANIFEST)
    INTERVENTIONS = write_csv("intervention_checks.csv", INTERVENTION_ROWS)
    CORRECTNESS = write_csv("correctness.csv", CORRECTNESS_ROWS)
    DISTRIBUTIONS = write_csv("distribution_checks.csv", DISTRIBUTION_ROWS)
    scenario_count = int(CORRECTNESS.all_scenarios.sum())
    assert scenario_count == sum(16 * (1 + 2 * c[0]) for c in run.config.small_grid)
    MANIFEST["completed"]["E4"] = {"diagrams": len(SMALL_INSTANCES), "route_interventions": len(INTERVENTIONS),
                                   "interventional_scenarios": int(CORRECTNESS.interventional_scenarios.sum()), "passed": True}
    MANIFEST["completed"]["E5"] = {"law_route_cases": len(DISTRIBUTIONS), "passed": True}
    dump_json(OUT / "run_manifest.json", MANIFEST)
    print("Distinct design scenarios, counting each assignment/intervention once:", scenario_count)
    print("Exact distribution comparisons:", len(DISTRIBUTIONS))
    run.complete("Q1", diagrams=len(CORRECTNESS), scenarios=scenario_count, route_assignment_checks=2 * scenario_count, law_cases=len(DISTRIBUTIONS))
    return INTERVENTIONS, DISTRIBUTIONS, CORRECTNESS


@phase('Q2_diagnostics')
def run_diagnostics(run):
    OUT = run.out
    MANIFEST = run.manifest
    write_csv = run.write_csv
    suite = build_fixtures()
    FIXTURES = suite["FIXTURES"]
    DIAGNOSTIC_ROWS = []
    FIXTURE_ASSEMBLIES = {}
    for fid, spec in FIXTURES.items():
        d, library = spec["diagram"], spec["library"]
        folder = OUT / "datasets" / "fixtures" / fid
        dump_json(folder / "diagram.json", diagram_json(d))
        dump_json(folder / "mechanism_library.json", library_json(library))
        dump_json(folder / "manifest.json", {k: spec[k] for k in ["raw", "deduplicated", "stage", "note"]})
        for mode in ["raw", "deduplicated"]:
            expected = spec[mode]
            try:
                a = assemble(d, library, mode)
                actual, issues = a.validation["valid"], a.validation["issues"]
                assert check_certificate(d, certificate_json(a), library)
                if mode == "raw": assert partition_from_qmaps(a.qmaps) == connected_component_oracle(d)
                for seed in range(3):
                    permuted = assemble(shuffled(d, seed), library, mode)
                    assert partition_from_qmaps(a.qmaps) == partition_from_qmaps(permuted.qmaps)
                FIXTURE_ASSEMBLIES[(fid, mode)] = a
                dump_json(OUT / "certificates" / f"{fid}-{mode}.json", certificate_json(a))
            except InvalidDiagram as error:
                actual, issues = False, error.issues
                assert spec["stage"] == "interface"
                assert all(check_interface_witness(d, issue) for issue in issues)
                dump_json(OUT / "certificates" / f"{fid}-{mode}.json", {"valid": False, "issues": issues})
            assert actual == expected, (fid, mode, expected, actual, issues)
            if not expected: assert spec["stage"] in {issue["stage"] for issue in issues}
            warnings = embedding_diagnostics(d, a) if (fid, mode) in FIXTURE_ASSEMBLIES else []
            if fid in {"F11", "F19"}: assert any(w["sort"] == "Var" for w in warnings)
            DIAGNOSTIC_ROWS.append({"fixture": fid, "mode": mode, "expected_valid": expected,
                                   "actual_valid": actual, "expected_stage": "accept" if expected else spec["stage"],
                                   "actual_stages": ",".join(sorted({i["stage"] for i in issues})) or "accept",
                                   "failure_kinds": ",".join(sorted({i["kind"] for i in issues})),
                                   "witness_valid": True, "noninjective_fibers": len(warnings), "notes": spec["note"]})
    DIAGNOSTICS = write_csv("diagnostics.csv", DIAGNOSTIC_ROWS)
    MANIFEST["completed"]["E2"] = {"fixtures": len(FIXTURES), "mode_checks": len(DIAGNOSTICS), "passed": True}
    dump_json(OUT / "run_manifest.json", MANIFEST)
    DIAGNOSTICS["scope"] = ["primary" if int(fid[1:]) <= 15 else "supporting" for fid in DIAGNOSTICS.fixture]
    DIAGNOSTICS.to_csv(OUT / "diagnostics.csv", index=False)
    run.complete("Q2_diagnostics", primary_fixtures=15, supporting_fixtures=4, mode_checks=len(DIAGNOSTICS))
    return DIAGNOSTICS, suite, FIXTURE_ASSEMBLIES


@phase('running_example')
def run_running_example(run, suite=None, fixture_assemblies=None):
    if suite is None: suite = build_fixtures()
    if fixture_assemblies is None: fixture_assemblies = {("F01", "raw"): assemble(suite["RUNNING_DIAGRAM"])}
    write_csv = run.write_csv
    RUNNING_DIAGRAM, RUNNING_GROUND = suite["RUNNING_DIAGRAM"], suite["RUNNING_GROUND"]
    running = fixture_assemblies[("F01", "raw")]
    running_maps = {name: {s: {rid: rid for rid in module.tables[s]} for s in SORTS} for name, module in RUNNING_DIAGRAM.modules.items()}
    RUNNING_COMPARISON = reconstruction_oracle(running, RUNNING_GROUND, running_maps)
    RESPONSE_ROWS = []
    selected_u = {"UX": 1, "UY": 0, "UZ": 1}
    baseline_inputs = {cid: selected_u[gid] for cid, gid in RUNNING_COMPARISON["Var"].items() if gid in selected_u}
    baseline_solution = compile_evaluator(running.description)(baseline_inputs)
    example_values = [{"context": "observational", **{RUNNING_COMPARISON["Var"][cid]: value for cid, value in baseline_solution.items()}}]
    y_class = running.qmaps["Var"][("upstream", "Y")]
    z_class = running.qmaps["Var"][("downstream", "Z")]
    for value in [0, 1]:
        library, codes = intervention_library(running.description, {y_class: value}, {y_class: "Y"})
        modified = surgery_diagram(RUNNING_DIAGRAM, running, codes)
        after = assemble(modified, library)
        theta = retained_record_isomorphism(running, after, surgery_description(running.description, codes))
        evaluate = compile_evaluator(after.description, library)
        probability = Fraction(0)
        for ux, uy, uz in itertools.product([0, 1], repeat=3):
            u = {"UX": ux, "UY": uy, "UZ": uz}
            before_inputs = {cid: u[gid] for cid, gid in RUNNING_COMPARISON["Var"].items() if gid in u}
            actual_inputs = {cid: before_inputs[image] for cid, image in theta["Var"].items() if image in before_inputs}
            sol = evaluate(actual_inputs)
            mapped_sol = {image: sol[cid] for cid, image in theta["Var"].items()}
            if u == selected_u:
                example_values.append({"context": f"do_Y_{value}",
                    **{RUNNING_COMPARISON["Var"][cid]: x for cid, x in mapped_sol.items()}})
            mass = Fraction(1, 4) * (Fraction(1, 5) if uz else Fraction(4, 5))
            probability += mass * mapped_sol[z_class]
            assert mapped_sol[y_class] == value
            downstream = modified.modules["downstream"]
            assert downstream.boundary == {"Y"} and "m:Y" not in downstream.tables["Mech"]
            assert compile_evaluator(downstream, library, closed=False)({"Y": value, "UZ": uz})["Z"] == mapped_sol[z_class]
        predicted = Fraction(1, 5) if value == 0 else Fraction(4, 5)
        assert probability == predicted
        RESPONSE_ROWS.append({"target": "Y", "value": value, "p_Z": "1/5", "P_Z_1_exact": str(probability), "prediction_exact": str(predicted)})
    write_csv("running_example_values.csv", example_values)
    RESPONSE = write_csv("running_example_response.csv", RESPONSE_ROWS)
    return RESPONSE


@phase('Q3_scaling')
def run_structural_benchmarks(run):
    OUT = run.out
    MANIFEST = run.manifest
    write_csv = run.write_csv
    SCALE_SIZES, SCALE_MODULES, SCALE_COPIES, SCALE_SEEDS = run.config.scale_sizes, run.config.scale_modules, run.config.scale_copies, run.config.scale_seeds
    TIMING_REPETITIONS, MEASURE_MEMORY = run.config.timing_repetitions, run.config.measure_memory
    TIMING_ROWS, MEMORY_ROWS = [], []
    SCALE_CONFIGS = list(itertools.product(SCALE_SIZES, SCALE_MODULES, SCALE_COPIES, SCALE_SEEDS))
    for index, (n, modules, copies, seed) in enumerate(SCALE_CONFIGS, 1):
        ident = instance_name(n, modules, copies, "random_acyclic", seed)
        config = {"instance": ident, "n_endogenous": n, "n_exogenous": run.config.scale_exogenous, "modules": modules,
                  "copy_fraction": copies, "family": "random_acyclic", "seed": seed, "mode": "deduplicated"}
        ground = generate_ground(n, run.config.scale_exogenous, "random_acyclic", seed)
        diagram, oracle, actual_copies = fragment_ground(ground, modules, copies, seed)
        release_instance(OUT / "datasets" / "structural" / ident, ground, diagram, oracle, config, compressed=True, write_datasets=run.config.write_datasets)
        normalized = normalize(diagram)
        pairs = sum(len(i.description.tables[s]) for i in diagram.interfaces for s in SORTS)
        rows = sum(len(m.tables[s]) for m in diagram.modules.values() for s in SORTS) + pairs
        headers = len(diagram.modules) + 3 * len(diagram.interfaces)
        scale = {"N_rows": rows, "N_headers": headers, "N": rows + headers, "R": 2 * pairs,
                 "identification_pairs": pairs, "copied_mechanisms": actual_copies}
        serialized = json.dumps(diagram_json(diagram), separators=(",", ":"))
        warmup = assemble(diagram, mode="deduplicated", normalized=normalized)
        assert warmup.validation["valid"]
        assert check_certificate(diagram, certificate_json(warmup))
        reconstruction_oracle(warmup, ground.description, oracle, canonical=True)
        # Independent raw quotient reference before interpreting any measured output.
        raw_reference = assemble(diagram)
        assert partition_from_qmaps(raw_reference.qmaps) == connected_component_oracle(diagram)
        del raw_reference
        for repetition in range(TIMING_REPETITIONS):
            gc.collect()
            start = time.perf_counter(); parsed = diagram_from_json(json.loads(serialized)); parsing_s = time.perf_counter() - start
            start = time.perf_counter(); indexed = normalize(parsed); normalization_s = time.perf_counter() - start
            measured = assemble(parsed, mode="deduplicated", normalized=indexed)
            assert measured.validation["valid"]
            assert check_certificate(parsed, certificate_json(measured))
            reconstruction_oracle(measured, ground.description, oracle, canonical=True)
            TIMING_ROWS.append({**config, **scale, "repetition": repetition, "parsing_s": parsing_s,
                                **measured.timings, "normalization_s": normalization_s,
                                "V": len(measured.description.tables["Var"]), "E": len(measured.validation["edges"]),
                                **{f"output_{s}": len(measured.description.tables[s]) for s in SORTS}, "correctness_checked": True})
            del parsed, indexed, measured
        if MEASURE_MEMORY:
            gc.collect(); tracemalloc.start()
            memory_assembly = assemble(diagram, mode="deduplicated")
            current_bytes, peak_bytes = tracemalloc.get_traced_memory(); tracemalloc.stop()
            assert memory_assembly.validation["valid"]
            assert check_certificate(diagram, certificate_json(memory_assembly))
            reconstruction_oracle(memory_assembly, ground.description, oracle, canonical=True)
            MEMORY_ROWS.append({**config, **scale, "current_python_bytes": current_bytes, "peak_python_bytes": peak_bytes,
                                "measurement": "tracemalloc; assembly allocations; input object excluded; not RSS", "correctness_checked": True})
            del memory_assembly
        dump_json(OUT / "certificates" / "structural" / f"{ident}.json.gz", certificate_json(warmup), compressed=True)
        print(f"Q3 scaling: {index}/{len(SCALE_CONFIGS)}; n={n}, modules={modules}, copy={copies}, seed={seed}; "
              f'median {np.median([r["structural_total_s"] for r in TIMING_ROWS[-TIMING_REPETITIONS:]]):.4f} s')
        write_csv("timings.csv", TIMING_ROWS)
        if MEMORY_ROWS: write_csv("memory.csv", MEMORY_ROWS)
        MANIFEST["completed"]["E6_progress"] = {"configurations": index, "timed_runs": len(TIMING_ROWS)}
        dump_json(OUT / "run_manifest.json", MANIFEST)
        del ground, diagram, oracle, normalized, warmup, serialized
    TIMINGS = write_csv("timings.csv", TIMING_ROWS)
    MEMORY = write_csv("memory.csv", MEMORY_ROWS) if MEMORY_ROWS else pd.DataFrame(columns=[
        "instance", "n_endogenous", "modules", "copy_fraction", "N", "R", "peak_python_bytes", "correctness_checked"])
    if MEMORY.empty: MEMORY.to_csv(OUT / "memory.csv", index=False)
    assert len(TIMINGS) == len(SCALE_CONFIGS) * TIMING_REPETITIONS
    MANIFEST["completed"]["E6"] = {"configurations": len(SCALE_CONFIGS), "timed_runs": len(TIMINGS),
                                   "memory_runs": len(MEMORY_ROWS), "passed": True}
    if not MEASURE_MEMORY: MANIFEST["skipped"].append("Optional separate Python allocation measurements")
    dump_json(OUT / "run_manifest.json", MANIFEST)
    TIMING_SUMMARY = TIMINGS.groupby(["n_endogenous", "modules", "copy_fraction"]).agg(
        N_R=("N", "median"), median_s=("structural_total_s", "median"),
        q25_s=("structural_total_s", lambda x: x.quantile(.25)), q75_s=("structural_total_s", lambda x: x.quantile(.75)),
        min_s=("structural_total_s", "min"), max_s=("structural_total_s", "max"), timed_runs=("repetition", "count")).reset_index()
    TIMING_SUMMARY["median_N_plus_R"] = TIMINGS.assign(N_plus_R=TIMINGS.N + TIMINGS.R).groupby(["n_endogenous", "modules", "copy_fraction"]).N_plus_R.median().to_numpy()
    TIMING_SUMMARY.drop(columns=["N_R"]).to_csv(OUT / "timing_summary.csv", index=False)
    TIMING_SUMMARY = TIMING_SUMMARY.drop(columns=["N_R"])
    run.complete("Q3", configurations=len(SCALE_CONFIGS), timed_runs=len(TIMINGS), memory_runs=len(MEMORY))
    return TIMINGS, MEMORY, TIMING_SUMMARY


@phase('supporting_validation')
def run_supporting_validation(run, suite, fixture_assemblies):
    write_csv = run.write_csv
    rows = run_supporting_checks(suite, fixture_assemblies)
    frame = write_csv("supporting_validation.csv", rows)
    run.complete("supporting_validation", controls=len(frame))
    return frame


def inject_copied_equation_conflict(diagram, oracle):
    """Change one copied mechanism to a different same-signature Boolean code.

    Interface records stay unchanged because this control uses variable-only maps.
    Every local module remains legal. The returned diagram is a deep copy.
    """
    copies = defaultdict(list)
    for name in sorted(diagram.modules):
        for rid in sorted(diagram.modules[name].tables["Mech"]):
            copies[oracle[name]["Mech"][rid]].append((name, rid))
    ground_id = next((g for g in sorted(copies) if len(copies[g]) > 1), None)
    if ground_id is None:
        return None, None
    name, rid = copies[ground_id][-1]
    result = copy.deepcopy(diagram)
    old_code = result.modules[name].tables["Mech"][rid]["code"]
    entry = LIBRARY[old_code]
    alternatives = [code for code, e in LIBRARY.items()
                    if code != old_code and code != "ID_ALIAS" and
                    e.signature == entry.signature and e.output_type == entry.output_type and e.table != entry.table]
    new_code = sorted(alternatives)[0]
    result.modules[name].tables["Mech"][rid]["code"] = new_code
    return result, {"ground_mechanism": ground_id, "module": name, "record": rid,
                    "original_code": old_code, "replacement_code": new_code}


@phase("Q2_duplication_comparison")
def run_duplication_comparison(run, instances):
    """Pair raw and deduplicated assembly on exactly the same variable-only diagram.

    Compare closed validity and Var/Mech/Input recovery against the same ground
    equation records. Dep multiplicity is deliberately excluded from this paired
    recovery metric: duplicate elimination merges parallel dependency rows.
    Q1 separately checks full four-table recovery against the appropriate target.
    """
    rows = []
    for index, instance in enumerate(instances, 1):
        base = instance["var_diagram"]
        conflict, change = inject_copied_equation_conflict(base, instance["oracle"])
        variants = [("faithful", base, None)]
        if conflict is not None:
            variants.append(("equation_conflict", conflict, change))
            folder = run.out / "datasets" / "duplication_controls" / instance["config"]["instance"]
            dump_json(folder / "diagram.json", diagram_json(conflict))
            dump_json(folder / "manifest.json", {**instance["config"], "change": change, "expected": "closed validity rejection"})
        for variant, diagram, change in variants:
            payload = json.dumps(diagram_json(diagram), sort_keys=True, separators=(",", ":"))
            input_hash = hashlib.sha256(payload.encode()).hexdigest()
            paired_rows = []
            for mode in ["raw", "deduplicated"]:
                result = assemble(diagram, mode=mode)
                assert check_certificate(diagram, certificate_json(result))
                if mode == "raw":
                    assert partition_from_qmaps(result.qmaps) == connected_component_oracle(diagram)
                try:
                    reconstruction_oracle(result, instance["ground"].description, instance["oracle"],
                                          sorts=("Var", "Mech", "Input"))
                    reconstructed, mismatch = True, ""
                except AssertionError as error:
                    reconstructed, mismatch = False, repr(error)
                owner_issues = [i for i in result.validation["issues"] if i["kind"] == "duplicate_owner"]
                incompatible_codes = any(len(set(i["witness"]["codes"])) > 1 for i in owner_issues)
                expected_accept = variant == "faithful" and (mode == "deduplicated" or instance["copied_mechanisms"] == 0)
                assert result.validation["valid"] == expected_accept, (instance["config"], variant, mode, result.validation["issues"])
                assert reconstructed == expected_accept
                if variant == "equation_conflict": assert incompatible_codes
                assert hashlib.sha256(json.dumps(diagram_json(diagram), sort_keys=True, separators=(",", ":")).encode()).hexdigest() == input_hash
                row = {**instance["config"], "variant": variant, "mode": mode,
                       "copied_mechanisms": instance["copied_mechanisms"], "input_sha256": input_hash, "interface_kind": "variable_only", "accepted": result.validation["valid"],
                       "equation_records_reconstructed": reconstructed, "reconstruction_mismatch": mismatch,
                       "reconstruction_sorts": "Var,Mech,Input", "duplicate_owner_classes": len(owner_issues),
                       "different_code_conflict": incompatible_codes, "witness_valid": True,
                       **{f"output_{s}": len(result.description.tables[s]) for s in SORTS}}
                paired_rows.append(row)
                dump_json(run.out / "certificates" / "duplication_comparison" /
                          f'{instance["config"]["instance"]}-{variant}-{mode}.json',
                          {"variant": variant, "input_sha256": input_hash, "change": change, "certificate": certificate_json(result)})
            assert paired_rows[0]["input_sha256"] == paired_rows[1]["input_sha256"]
            rows.extend(paired_rows)
        if index % 60 == 0 or index == len(instances):
            print(f"Q2 paired comparison: {index}/{len(instances)} diagrams; {len(rows)} method cases.")
            run.write_csv("duplication_comparison.csv", rows)
    frame = run.write_csv("duplication_comparison.csv", rows)
    summary = frame.groupby(["variant", "copy_fraction", "mode"]).agg(
        diagrams=("instance", "count"), accepted=("accepted", "sum"),
        equation_records_recovered=("equation_records_reconstructed", "sum"),
        owner_failures=("duplicate_owner_classes", lambda x: int((x > 0).sum())),
        conflict_witnesses=("different_code_conflict", "sum")).reset_index()
    summary.to_csv(run.out / "duplication_summary.csv", index=False)
    run.complete("Q2_duplication_comparison", faithful_diagrams=len(instances),
                 conflict_diagrams=int(frame[frame.variant == "equation_conflict"].instance.nunique()), method_cases=len(frame))
    return frame, summary


@phase("finalize")
def finalize_run(run, correctness, observational, interventions, distributions,
                 diagnostics, duplication, timings, memory, supporting):
    """Verify completed measurements, export counts, and finish the run manifest."""
    run.verify_code()
    assert correctness.raw_reconstruction.all() and correctness.variable_only_DE_reconstruction.all()
    assert observational.global_mismatches.sum() == observational.local_mismatches.sum() == 0
    assert interventions.global_mismatches.sum() == interventions.local_mismatches.sum() == interventions.commutation_mismatches.sum() == 0
    assert (distributions.global_TV_exact == "0").all() and (distributions.max_local_TV_exact == "0").all()
    assert timings.correctness_checked.all() and supporting.passed.all()
    assert diagnostics.actual_valid.equals(diagnostics.expected_valid)
    for name in ["Q1", "Q2_diagnostics", "Q2_duplication_comparison", "Q3", "supporting_validation"]:
        assert run.manifest["completed"][name]["passed"]
    notebook = run.root / run.manifest["execution_notebook"]
    code = "\n".join("".join(c["source"]) for c in json.loads(notebook.read_text())["cells"] if c["cell_type"] == "code")
    assert hashlib.sha256(code.encode()).hexdigest() == run.manifest["notebook_code_sha256"]
    scenarios = int(correctness.all_scenarios.sum())
    counts = {
        "small_diagrams": len(correctness),
        "ground_generation_configurations": correctness.groupby(["n_endogenous", "family", "seed"]).ngroups,
        "distinct_semantic_scenarios": scenarios,
        "route_assignment_checks": int(observational.assignments.sum() + interventions.assignments.sum()),
        "law_route_cases": len(distributions), "primary_fixtures": int(diagnostics[diagnostics.scope == "primary"].fixture.nunique()),
        "supporting_fixtures": int(diagnostics[diagnostics.scope == "supporting"].fixture.nunique()),
        "fixture_mode_checks": len(diagnostics), "paired_method_cases": len(duplication),
        "faithful_duplicated_diagrams": int(duplication[(duplication.variant == "faithful") & (duplication.copied_mechanisms > 0)].instance.nunique()),
        "conflict_control_diagrams": int(duplication[duplication.variant == "equation_conflict"].instance.nunique()),
        "structural_configurations": int(timings.instance.nunique()), "timed_repetitions": len(timings),
        "memory_runs": len(memory), "supporting_controls": len(supporting),
    }
    rows = [
        {"question": "Q1: recover model and behavior", "measurement": "Diagrams reconstructed through both routes", "executed": len(correctness), "discrepancies": 0},
        {"question": "Q1: recover model and behavior", "measurement": "Unique assignment/intervention scenarios", "executed": scenarios, "discrepancies": 0},
        {"question": "Q1: recover model and behavior", "measurement": "Exact law/route cases", "executed": len(distributions), "discrepancies": 0},
        {"question": "Q2: diagnose composition", "measurement": "Primary fixture/mode classifications", "executed": int((diagnostics.scope == "primary").sum()), "discrepancies": 0},
        {"question": "Q2: diagnose composition", "measurement": "Paired assembly method cases", "executed": len(duplication), "discrepancies": 0},
        {"question": "Q3: characterize cost", "measurement": "Correctness-checked structural repetitions", "executed": len(timings), "discrepancies": 0},
    ]
    summary = run.write_csv("experiment_summary.csv", rows)
    run.manifest.update({"status": "complete", "completed_utc": datetime.now(timezone.utc).isoformat(),
                         "executed_counts": counts, "measurement_scope": {
                             "pipeline": "deduplicated assembly with full-record benchmark interfaces",
                             "structural_total": STAGES, "reported_separately": ["parsing", "normalization"],
                             "memory": "traced assembly allocations; existing input excluded; not RSS"}})
    run.manifest["output_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in run.out.glob("*.csv")}
    run.save_manifest()
    return summary

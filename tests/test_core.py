"""Regression checks for record identity, assembly semantics, and the controlled comparison."""
import ast
import copy
import json
import unittest
from pathlib import Path
from causal_experiments.records import SORTS, InvalidDiagram, diagram_json, diagram_from_json
from causal_experiments.mechanisms import LIBRARY, validate_library
from causal_experiments.fixtures import build_fixtures
from causal_experiments.assembly import assemble
from causal_experiments.certificates import certificate_json, check_certificate, check_interface_witness
from causal_experiments.oracles import connected_component_oracle, partition_from_qmaps
from causal_experiments.reconstruction import reconstruction_oracle, retained_record_isomorphism
from causal_experiments.generation import generate_ground
from causal_experiments.fragmentation import fragment_ground, variables_only, shuffled
from causal_experiments.interventions import intervention_library, surgery_description, surgery_diagram
from causal_experiments.experiments import compare_semantics, inject_copied_equation_conflict
from causal_experiments.distributions import distribution_checks
from causal_experiments.validation_checks import run_supporting_checks


class CoreRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = build_fixtures()

    def test_library_totality_and_order(self):
        self.assertTrue(validate_library(LIBRARY))
        incomplete = copy.deepcopy(LIBRARY)
        del incomplete["AND"].table[(1, 0)]
        with self.assertRaises(AssertionError): validate_library(incomplete)
        self.assertEqual(LIBRARY["AND_NOT"].table[(1, 0)], 1)
        self.assertEqual(LIBRARY["AND_NOT"].table[(0, 1)], 0)

    def test_fixture_classifications_and_independent_witnesses(self):
        assemblies = {}
        for fid, spec in self.suite["FIXTURES"].items():
            for mode in ["raw", "deduplicated"]:
                with self.subTest(fixture=fid, mode=mode):
                    try:
                        a = assemble(spec["diagram"], spec["library"], mode)
                        self.assertEqual(a.validation["valid"], spec[mode])
                        self.assertTrue(check_certificate(spec["diagram"], certificate_json(a), spec["library"]))
                        assemblies[(fid, mode)] = a
                    except InvalidDiagram as error:
                        self.assertEqual(spec["stage"], "interface")
                        self.assertFalse(spec[mode])
                        for issue in error.issues: self.assertTrue(check_interface_witness(spec["diagram"], issue))
        self.assertEqual(len(run_supporting_checks(self.suite, assemblies)), 14)

    def test_serialized_diagram_and_shuffled_partition(self):
        d = self.suite["RUNNING_DIAGRAM"]
        restored = diagram_from_json(json.loads(json.dumps(diagram_json(d))))
        reference = connected_component_oracle(d)
        for variant in [restored, shuffled(d, 17)]:
            a = assemble(variant)
            self.assertEqual(partition_from_qmaps(a.qmaps), reference)
            self.assertTrue(check_certificate(variant, certificate_json(a)))

    def test_four_table_recovery_and_semantic_commutation(self):
        for family in ["chain", "layered", "random_acyclic"]:
            with self.subTest(family=family):
                ground = generate_ground(8, 4, family, 3)
                d, oracle, _ = fragment_ground(ground, 2, .25, 3)
                before = assemble(d)
                comparison = reconstruction_oracle(before, ground.description, oracle)
                observations, metrics = compare_semantics(ground, {}, d, before, comparison)
                self.assertEqual(metrics["assignments"], 16)
                self.assertEqual(metrics["local_mismatches"], 0)
                self.assertEqual(len(distribution_checks(ground, d, observations)), 3)
                target = next(cid for cid, gid in comparison["Var"].items() if gid == "V3")
                library, codes = intervention_library(before.description, {target: 1}, {target: "V3"})
                modified = surgery_diagram(d, before, codes)
                after = assemble(modified, library)
                self.assertTrue(retained_record_isomorphism(before, after, surgery_description(before.description, codes)))
                after_map = reconstruction_oracle(after, surgery_description(ground.description, {"V3": codes[target]}), oracle)
                observations, metrics = compare_semantics(ground, {"V3": 1}, modified, after, after_map, library)
                self.assertEqual(metrics["global_mismatches"], 0)
                self.assertEqual(len(distribution_checks(ground, modified, observations, library)), 3)

    def test_identical_interface_pair_repairs_duplicates_but_rejects_conflicts(self):
        ground = generate_ground(8, 4, "random_acyclic", 0)
        d, oracle, copied = fragment_ground(ground, 2, .25, 0)
        self.assertEqual(copied, 2)
        variable_d = variables_only(d)
        descriptor = json.dumps(diagram_json(variable_d), sort_keys=True)
        raw, dedup = assemble(variable_d), assemble(variable_d, mode="deduplicated")
        self.assertFalse(raw.validation["valid"])
        self.assertTrue(dedup.validation["valid"])
        self.assertTrue(reconstruction_oracle(dedup, ground.description, oracle, sorts=("Var", "Mech", "Input")))
        self.assertEqual(json.dumps(diagram_json(variable_d), sort_keys=True), descriptor)
        conflict, change = inject_copied_equation_conflict(variable_d, oracle)
        self.assertNotEqual(change["original_code"], change["replacement_code"])
        self.assertEqual(LIBRARY[change["original_code"]].signature, LIBRARY[change["replacement_code"]].signature)
        self.assertEqual(json.dumps(diagram_json(variable_d), sort_keys=True), descriptor)
        for mode in ["raw", "deduplicated"]:
            rejected = assemble(conflict, mode=mode)
            self.assertFalse(rejected.validation["valid"])
            self.assertTrue(check_certificate(conflict, certificate_json(rejected)))
            self.assertTrue(any(len(set(i["witness"]["codes"])) > 1 for i in rejected.validation["issues"] if i["kind"] == "duplicate_owner"))

    def test_paired_equation_metric_preserves_repeated_slots(self):
        d = self.suite["FIXTURES"]["F12"]["diagram"]
        ground = next(iter(d.modules.values()))
        oracle = {ground.name: {s: {r: r for r in ground.tables[s]} for s in SORTS}}
        raw, dedup = assemble(d), assemble(d, mode="deduplicated")
        for a in [raw, dedup]:
            self.assertTrue(reconstruction_oracle(a, ground, oracle, sorts=("Var", "Mech", "Input")))
            self.assertEqual(len(a.description.tables["Input"]), 2)
        self.assertEqual(len(raw.description.tables["Dep"]), 2)
        self.assertEqual(len(dedup.description.tables["Dep"]), 1)
        self.assertTrue(reconstruction_oracle(raw, ground, oracle))
        self.assertTrue(reconstruction_oracle(dedup, ground, oracle, canonical=True))

    def test_semantic_failure_retains_assignment_and_coordinates(self):
        ground = generate_ground(8, 4, "chain", 0)
        d, oracle, _ = fragment_ground(ground, 2, 0, 0)
        a = assemble(d)
        wrong = reconstruction_oracle(a, ground.description, oracle)
        noise = [cid for cid, gid in wrong["Var"].items() if gid in {"U0", "U1"}]
        wrong["Var"][noise[0]], wrong["Var"][noise[1]] = wrong["Var"][noise[1]], wrong["Var"][noise[0]]
        with self.assertRaises(AssertionError) as caught:
            compare_semantics(ground, {}, d, a, wrong)
        self.assertEqual(caught.exception.args[0]["check"], "global evaluation")
        self.assertIn("assignment", caught.exception.args[0])
        self.assertTrue(caught.exception.args[0]["differences"])

    def test_notebook_contains_only_setup_invocation_and_review_code(self):
        root = Path(__file__).resolve().parents[1]
        notebook = json.loads((root / "category_causal_experiments.ipynb").read_text())
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] != "code": continue
            self.assertEqual(notebook["cells"][index-1]["cell_type"], "markdown")
            tree = ast.parse("".join(cell["source"]))
            self.assertFalse(any(isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree)))


if __name__ == "__main__":
    unittest.main()

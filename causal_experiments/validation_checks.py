"""Supporting hand checks and rejection controls, separate from paper-facing experiments."""
from __future__ import annotations
import copy, itertools
from .records import SORTS
from .mechanisms import LIBRARY, validate_library
from .evaluation import compile_evaluator
from .oracles import direct_ground_evaluate
from .reconstruction import reconstruction_oracle, retained_record_isomorphism
from .certificates import certificate_json, check_certificate
from .interventions import surgery_description
from .local_validation import validate_model

def run_supporting_checks(suite, fixture_assemblies):
    """Hand-check semantics and reject corrupted certificates and invalid prerequisites."""
    FIXTURE_ASSEMBLIES = fixture_assemblies
    FIXTURES = suite['FIXTURES']
    RUNNING_DIAGRAM = suite['RUNNING_DIAGRAM']
    RUNNING_GROUND = suite['RUNNING_GROUND']
    RUNNING_EQUATIONS = suite['RUNNING_EQUATIONS']
    MULTI_LIBRARY = suite['MULTI_LIBRARY']
    base = suite['base']
    multi_codes = suite['multi_codes']
    repeat = suite['repeat']
    ordered = suite['ordered']
    typed = suite['typed']
    up = suite['up']
    running = FIXTURE_ASSEMBLIES[("F01", "raw")]
    running_maps = {name: {s: {rid: rid for rid in module.tables[s]} for s in SORTS} for name, module in RUNNING_DIAGRAM.modules.items()}
    RUNNING_COMPARISON = reconstruction_oracle(running, RUNNING_GROUND, running_maps)
    run_eval = compile_evaluator(running.description)
    for values in itertools.product([0, 1], repeat=3):
        u = dict(zip(["UX", "UY", "UZ"], values))
        expected = direct_ground_evaluate(RUNNING_EQUATIONS, u)
        global_input = {cid: u[ground] for cid, ground in RUNNING_COMPARISON["Var"].items() if ground in u}
        actual = run_eval(global_input)
        assert {RUNNING_COMPARISON["Var"][v]: x for v, x in actual.items()} == expected
        for name, module in RUNNING_DIAGRAM.modules.items():
            pulled = {rid: actual[running.qmaps["Var"][(name, rid)]] for rid in module.tables["Var"]}
            induced = {rid: x for rid, x in pulled.items() if rid in module.boundary or module.tables["Var"][rid]["role"] == "exo"}
            assert compile_evaluator(module, closed=False)(induced) == pulled

    for fid in ["F11", "F19"]:
        d, a = FIXTURES[fid]["diagram"], FIXTURE_ASSEMBLIES[(fid, "raw")]
        evaluator = compile_evaluator(a.description)
        exo = [v for v, r in a.description.tables["Var"].items() if r["role"] == "exo"]
        for bit in [0, 1]:
            solution = evaluator({v: bit for v in exo})
            for name, module in d.modules.items():
                pulled = {v: solution[a.qmaps["Var"][(name, v)]] for v in module.tables["Var"]}
                induced = {v: x for v, x in pulled.items() if module.tables["Var"][v]["role"] == "exo" or v in module.boundary}
                assert compile_evaluator(module, closed=False)(induced) == pulled
    for bit in [0, 1]: assert compile_evaluator(repeat)({"X": bit})["Y"] == 0
    assert len(repeat.tables["Input"]) == 2 and len(repeat.tables["Dep"]) == 2
    assert len(FIXTURE_ASSEMBLIES[("F12", "deduplicated")].description.tables["Dep"]) == 1
    assert compile_evaluator(ordered)({"X": 1, "U": 0})["Y"] == 1
    assert LIBRARY["AND_NOT"].table[(0, 1)] == 0
    for b, t in itertools.product([0, 1], [0, 1, 2]):
        assert compile_evaluator(typed)({"B": b, "T": t}) == {"B": b, "T": t, "Z": 2 * b, "W": t}
    multi_after = FIXTURE_ASSEMBLIES[("F14", "raw")]
    assert retained_record_isomorphism(base, multi_after, surgery_description(base.description, multi_codes))
    for value in [0, 1]:
        sol = compile_evaluator(multi_after.description, MULTI_LIBRARY)({multi_after.qmaps["Var"][("a", "U")]: value})
        assert sol[multi_after.qmaps["Var"][("a", "X")]] == 1
        assert sol[multi_after.qmaps["Var"][("a", "Y")]] == 0

    def must_reject_certificate(diagram, certificate):
        try: check_certificate(diagram, certificate)
        except (AssertionError, KeyError, ValueError): return True
        raise AssertionError("Corrupted certificate was accepted")

    cert = certificate_json(running)
    bad_rank = copy.deepcopy(cert); bad_rank["rank"] = {v: 0 for v in cert["rank"]}
    assert must_reject_certificate(RUNNING_DIAGRAM, bad_rank)
    bad_code = copy.deepcopy(cert)
    next(iter(bad_code["description"]["tables"]["Mech"].values()))["code"] = "NOT"
    assert must_reject_certificate(RUNNING_DIAGRAM, bad_code)
    bad_merge = copy.deepcopy(cert)
    first_class = bad_merge["qmaps"]["Var"][0]["class"]
    for record in bad_merge["qmaps"]["Var"]: record["class"] = first_class
    assert must_reject_certificate(RUNNING_DIAGRAM, bad_merge)
    print("Running example, induced pullbacks, ordered inputs, typed outputs, multi-target intervention, and corruption controls passed.")

    invalid_library = copy.deepcopy(LIBRARY)
    del invalid_library["AND"].table[(1, 0)]
    try: validate_library(invalid_library)
    except AssertionError: pass
    else: raise AssertionError("Incomplete finite library accepted")
    invalid_local = copy.deepcopy(up); invalid_local.boundary.add("UX")
    assert not validate_model(invalid_local, LIBRARY, closed=False)["valid"]
    dangling = copy.deepcopy(up)
    next(iter(dangling.tables["Input"].values()))["var"] = "nonexistent"
    assert any(i["kind"] == "structural_reference" for i in validate_model(dangling, LIBRARY, closed=False)["issues"])
    no_deps = copy.deepcopy(up); no_deps.tables["Dep"] = {}
    assert any(i["kind"] == "dependency_mismatch" for i in validate_model(no_deps, LIBRARY, closed=False)["issues"])
    uncovered = copy.deepcopy(RUNNING_GROUND); uncovered.tables["Var"]["unused_U"] = {"role": "exo", "type": "bool"}
    try: reconstruction_oracle(running, uncovered, running_maps)
    except AssertionError: pass
    else: raise AssertionError("Uncovered reference record accepted")
    print("All five precondition/reconstruction negative controls rejected as intended.")
    return [{"control": name, "passed": True} for name in ["running example", "noninjective pullback", "repeated slots", "ordered arguments", "typed values", "multi-target intervention", "corrupted rank", "corrupted code", "excessive merger", "incomplete library", "illegal boundary", "dangling reference", "missing dependency rows", "uncovered reference record"]]

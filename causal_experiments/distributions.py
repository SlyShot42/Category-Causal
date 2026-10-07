"""Exact rational noise laws and joint induced-input pushforward comparisons."""
from __future__ import annotations
import math
from fractions import Fraction
from collections import defaultdict
from .mechanisms import LIBRARY
from .evaluation import compile_evaluator

LAW_NAMES = ("uniform", "product", "correlated")
def exact_mass(u, order, law):
    bits = [u[v] for v in order]
    if law == "uniform": return Fraction(1, 2 ** len(bits))
    if law == "product":
        probabilities = [Fraction(i, 5) for i in [1, 2, 3, 4]]
        assert len(bits) == 4
        return math.prod(p if bit else 1 - p for bit, p in zip(bits, probabilities))
    if law == "correlated": return Fraction(1, 2) if all(b == 0 for b in bits) or all(b == 1 for b in bits) else Fraction(0)
    raise ValueError(law)

def atom(assignment, order): return tuple(assignment[v] for v in order)
def total_variation(a, b): return sum((abs(a.get(k, 0) - b.get(k, 0)) for k in set(a) | set(b)), Fraction(0)) / 2

def distribution_checks(ground, diagram, observations, library=LIBRARY):
    rows = []
    global_order = sorted(ground.description.tables["Var"])
    for law in LAW_NAMES:
        ground_mass, assembled_mass = defaultdict(Fraction), defaultdict(Fraction)
        weights = [exact_mass(o["u"], ground.exogenous, law) for o in observations]
        assert sum(weights) == 1
        for o, mass in zip(observations, weights):
            ground_mass[atom(o["expected"], global_order)] += mass
            assembled_mass[atom(o["global"], global_order)] += mass
        tv = total_variation(ground_mass, assembled_mass); assert tv == 0
        local_tv_max = Fraction(0)
        for name, module in diagram.modules.items():
            input_order = sorted({v for v, r in module.tables["Var"].items() if r["role"] == "exo"} | module.boundary)
            variable_order = sorted(module.tables["Var"])
            induced_law, pulled_mass = defaultdict(Fraction), defaultdict(Fraction)
            for o, mass in zip(observations, weights):
                induced_law[atom(o["induced"][name], input_order)] += mass
                pulled_mass[atom(o["pullbacks"][name], variable_order)] += mass
            evaluator = compile_evaluator(module, library, closed=False)
            evaluated_mass = defaultdict(Fraction)
            for input_atom, mass in induced_law.items():
                evaluated = evaluator(dict(zip(input_order, input_atom)))
                evaluated_mass[atom(evaluated, variable_order)] += mass
            local_tv_max = max(local_tv_max, total_variation(evaluated_mass, pulled_mass))
        assert local_tv_max == 0
        rows.append({"law": law, "global_TV_exact": str(tv), "max_local_TV_exact": str(local_tv_max),
                     "modules_checked": len(diagram.modules), "assignment_atoms": len(observations)})
    return rows

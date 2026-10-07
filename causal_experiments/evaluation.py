"""Iterative production evaluation from ordered quotient input records."""
from __future__ import annotations
from .records import ordered_inputs
from .mechanisms import DOMAINS, LIBRARY
from .local_validation import validate_model

def compile_evaluator(description, library=LIBRARY, closed=True):
    validation = validate_model(description, library, closed=closed)
    assert validation["valid"], validation["issues"]
    groups = ordered_inputs(description)
    owners = {m["output"]: mid for mid, m in description.tables["Mech"].items()}
    plan = []
    for variable in validation["order"]:
        if variable in owners:
            mid = owners[variable]; m = description.tables["Mech"][mid]
            plan.append((variable, tuple(v for _, _, v in groups.get(mid, [])), library[m["code"]].table))
    free = {v for v, r in description.tables["Var"].items() if r["role"] == "exo"} | (set() if closed else description.boundary)
    def evaluate(assignment):
        assert set(assignment) == free
        for v, value in assignment.items(): assert value in DOMAINS[description.tables["Var"][v]["type"]]
        values = dict(assignment)
        for variable, arguments, table in plan: values[variable] = table[tuple(values[v] for v in arguments)]
        return values
    return evaluate

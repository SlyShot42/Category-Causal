"""Seeded Boolean ground models with a separate topologically ordered equation list."""
from __future__ import annotations
import math, random
from dataclasses import dataclass
from .records import Description, bool_vars, make_description
from .mechanisms import LIBRARY
from .local_validation import validate_model

BOOL_CODES = [k for k, e in LIBRARY.items() if e.output_type == "bool" and k != "ID_ALIAS"]
@dataclass
class Ground:
    description: Description
    equations: list
    exogenous: list

def generate_ground(n, n_exo, family, seed):
    rng = random.Random(seed)
    exogenous = [f"U{i}" for i in range(n_exo)]
    endogenous = [f"V{i}" for i in range(n)]
    equations = []
    width = max(2, math.isqrt(n))
    for i, output in enumerate(endogenous):
        choices = [k for k in BOOL_CODES if len(LIBRARY[k].signature) > 0] if family == "chain" and i > 0 else BOOL_CODES
        code = rng.choice(choices); arity = len(LIBRARY[code].signature)
        arguments = []
        if family == "chain":
            if i > 0: arguments.append(endogenous[i - 1])
            arguments += [rng.choice(exogenous) for _ in range(arity - len(arguments))]
        else:
            allowed_endo = (i // width) * width if family == "layered" else i
            for _ in range(arity):
                index = rng.randrange(n_exo + allowed_endo)
                arguments.append(exogenous[index] if index < n_exo else endogenous[index - n_exo])
        equations.append((output, code, arguments))
    d = make_description("ground", bool_vars(exogenous, endogenous), equations)
    assert validate_model(d, LIBRARY)["valid"]
    return Ground(d, equations, exogenous)

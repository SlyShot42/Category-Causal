"""Four causal record sorts, descriptions, diagrams, and JSON conversion."""
from __future__ import annotations
import json
from collections import defaultdict
from dataclasses import dataclass, field

SORTS = ("Var", "Mech", "Input", "Dep")
ARROWS = {"Var": {}, "Mech": {"output": "Var"},
          "Input": {"mech": "Mech", "var": "Var"},
          "Dep": {"cause": "Var", "effect": "Var"}}
ATTRIBUTES = {"Var": ("type", "role"), "Mech": ("code",), "Input": ("pos",), "Dep": ()}
@dataclass
class Description:
    name: str
    tables: dict = field(default_factory=lambda: {s: {} for s in SORTS})
    boundary: set = field(default_factory=set)
@dataclass
class Interface:
    name: str
    description: Description
    left: str
    right: str
    left_map: dict
    right_map: dict
@dataclass
class Diagram:
    modules: dict[str, Description]
    interfaces: list[Interface]

class InvalidDiagram(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__(json.dumps(issues, default=str))

def description_json(d):
    return {"name": d.name, "tables": d.tables, "boundary": sorted(d.boundary)}
def diagram_json(d):
    return {"modules": {n: description_json(m) for n, m in d.modules.items()},
            "interfaces": [{"name": i.name, "description": description_json(i.description),
                            "left": i.left, "right": i.right,
                            "left_map": i.left_map, "right_map": i.right_map} for i in d.interfaces]}
def diagram_from_json(obj):
    def load(d):
        return Description(d["name"], d["tables"], set(d.get("boundary", [])))
    return Diagram({n: load(d) for n, d in obj["modules"].items()},
                   [Interface(i["name"], load(i["description"]), i["left"], i["right"],
                              i["left_map"], i["right_map"]) for i in obj["interfaces"]])

def make_description(name, variables, equations, boundary=()):
    d = Description(name, boundary=set(boundary))
    d.tables["Var"] = {v: {"role": role, "type": typ} for v, (role, typ) in variables.items()}
    for output, code, inputs in equations:
        mid = "m:" + output
        d.tables["Mech"][mid] = {"output": output, "code": code}
        for pos, var in enumerate(inputs, 1):
            d.tables["Input"][f"p:{output}:{pos}"] = {"mech": mid, "var": var, "pos": pos}
            d.tables["Dep"][f"d:{output}:{pos}"] = {"cause": var, "effect": output}
    return d

def ordered_inputs(d):
    groups = defaultdict(list)
    for pid, p in d.tables["Input"].items(): groups[p["mech"]].append((p["pos"], pid, p["var"]))
    return {m: sorted(group) for m, group in groups.items()}



def bool_vars(exogenous=(), endogenous=()):
    return {**{v: ("exo", "bool") for v in exogenous}, **{v: ("endo", "bool") for v in endogenous}}

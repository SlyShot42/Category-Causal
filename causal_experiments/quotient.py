"""Entitywise union-find, normalization, interface unions, and duplicate elimination."""
from __future__ import annotations
from dataclasses import dataclass
from .records import SORTS, ordered_inputs

@dataclass
class Normalized:
    tags: dict
    indices: dict
    pairs: dict

def normalize(diagram):
    tags = {s: [(name, rid) for name, m in diagram.modules.items() for rid in m.tables[s]] for s in SORTS}
    indices = {s: {tag: i for i, tag in enumerate(tags[s])} for s in SORTS}
    pairs = {s: [] for s in SORTS}
    for interface in diagram.interfaces:
        for sort in SORTS:
            for rid in interface.description.tables[sort]:
                a = indices[sort][(interface.left, interface.left_map[sort][rid])]
                b = indices[sort][(interface.right, interface.right_map[sort][rid])]
                pairs[sort].append((a, b, {"kind": "interface", "interface": interface.name, "record": rid}))
    return Normalized(tags, indices, pairs)

class DisjointSet:
    def __init__(self, size):
        self.parent = list(range(size)); self.size = [1] * size; self.forest = []
    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]; x = self.parent[x]
        return x
    def unite(self, a, b, evidence):
        x, y = self.find(a), self.find(b)
        if x == y: return
        if self.size[x] < self.size[y]: x, y = y, x
        self.parent[y] = x; self.size[x] += self.size[y]
        self.forest.append((a, b, evidence))

def impose_interfaces(normalized):
    sets = {s: DisjointSet(len(normalized.tags[s])) for s in SORTS}
    for sort in SORTS:
        for a, b, evidence in normalized.pairs[sort]: sets[sort].unite(a, b, evidence)
    return sets

def eliminate_duplicates(diagram, normalized, sets):
    def root(sort, name, rid): return sets[sort].find(normalized.indices[sort][(name, rid)])
    keys = {s: {} for s in ("Mech", "Input", "Dep")}
    for name, module in diagram.modules.items():
        groups = ordered_inputs(module)
        for rid, m in module.tables["Mech"].items():
            key = (m["code"], root("Var", name, m["output"]),
                   tuple(root("Var", name, v) for _, _, v in groups.get(rid, [])))
            index = normalized.indices["Mech"][(name, rid)]
            if key in keys["Mech"]: sets["Mech"].unite(index, keys["Mech"][key], {"kind": "duplicate"})
            else: keys["Mech"][key] = index
    for name, module in diagram.modules.items():
        for sort in ("Input", "Dep"):
            for rid, row in module.tables[sort].items():
                if sort == "Input": key = (root("Mech", name, row["mech"]), row["pos"], root("Var", name, row["var"]))
                else: key = (root("Var", name, row["cause"]), root("Var", name, row["effect"]))
                index = normalized.indices[sort][(name, rid)]
                if key in keys[sort]: sets[sort].unite(index, keys[sort][key], {"kind": "duplicate"})
                else: keys[sort][key] = index

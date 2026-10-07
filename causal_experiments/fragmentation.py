"""Faithful independently renamed modules and full-record or variable-only intersections."""
from __future__ import annotations
import copy, itertools, random
from collections import defaultdict
from .records import SORTS, ARROWS, ATTRIBUTES, Description, Diagram, Interface
from .mechanisms import LIBRARY
from .interfaces import fixture_interface, validate_diagram

def fragment_ground(ground, module_count, copy_fraction, seed):
    rng = random.Random(seed + 100003)
    records = ground.description.tables
    mids = list(records["Mech"]); rng.shuffle(mids)
    ownership = [set(mids[i::module_count]) for i in range(module_count)]
    assert all(ownership)
    copied = rng.sample(mids, round(len(mids) * copy_fraction))
    original_owner = {m: i for i, group in enumerate(ownership) for m in group}
    for mid in copied:
        alternatives = [j for j in range(module_count) if j != original_owner[mid]]
        ownership[rng.choice(alternatives)].add(mid)
    p_by_m, d_by_output = defaultdict(set), defaultdict(set)
    for pid, p in records["Input"].items(): p_by_m[p["mech"]].add(pid)
    for did, d in records["Dep"].items(): d_by_output[d["effect"]].add(did)
    modules, oracle, inverse, included = {}, {}, {}, {}
    for index, group in enumerate(ownership):
        name = f"module_{index}"
        selected = {s: set() for s in SORTS}; selected["Mech"] = group
        for mid in group:
            output = records["Mech"][mid]["output"]
            selected["Var"].add(output); selected["Input"].update(p_by_m[mid]); selected["Dep"].update(d_by_output[output])
        for pid in selected["Input"]: selected["Var"].add(records["Input"][pid]["var"])
        if index == 0: selected["Var"].update(ground.exogenous)
        renaming = {}
        for sort in SORTS:
            ids = sorted(selected[sort]); rng.shuffle(ids)
            renaming[sort] = {rid: f"{sort.lower()}_{rng.getrandbits(64):016x}" for rid in ids}
            assert len(set(renaming[sort].values())) == len(ids)
        module = Description(name)
        for sort in SORTS:
            for rid, local_id in renaming[sort].items():
                row = records[sort][rid]
                module.tables[sort][local_id] = {
                    **{a: row[a] for a in ATTRIBUTES[sort]},
                    **{a: renaming[ts][row[a]] for a, ts in ARROWS[sort].items()}}
        owned_outputs = {records["Mech"][m]["output"] for m in group}
        module.boundary = {renaming["Var"][v] for v in selected["Var"] if records["Var"][v]["role"] == "endo" and v not in owned_outputs}
        modules[name] = module; inverse[name] = renaming; included[name] = selected
        oracle[name] = {s: {local: rid for rid, local in renaming[s].items()} for s in SORTS}
    interfaces = []
    for left_name, right_name in itertools.combinations(modules, 2):
        common = {s: included[left_name][s] & included[right_name][s] for s in SORTS}
        if not any(common.values()): continue
        pairs = {s: {inverse[left_name][s][rid]: inverse[right_name][s][rid] for rid in sorted(common[s])} for s in SORTS}
        name = f"overlap_{left_name}_{right_name}"
        interface = fixture_interface(name, modules[left_name], modules[right_name], pairs)
        interfaces.append(interface)
    diagram = Diagram(modules, interfaces)
    validate_diagram(diagram, LIBRARY)
    return diagram, oracle, len(copied)

def variables_only(diagram):
    result = Diagram(diagram.modules, [])
    for interface in diagram.interfaces:
        d = Description(interface.name, {s: dict(interface.description.tables[s]) if s == "Var" else {} for s in SORTS})
        maps = [{s: dict(mapping[s]) if s == "Var" else {} for s in SORTS}
                for mapping in [interface.left_map, interface.right_map]]
        result.interfaces.append(Interface(interface.name, d, interface.left, interface.right, *maps))
    return result

def instance_name(n, modules, copies, family, seed):
    return f"{family}_n{n}_m{modules}_copy{int(copies * 100):02d}_seed{seed}"

def shuffled(diagram, seed):
    rng = random.Random(seed); result = copy.deepcopy(diagram)
    names = list(result.modules); rng.shuffle(names)
    result.modules = {n: result.modules[n] for n in names}
    for d in list(result.modules.values()) + [i.description for i in result.interfaces]:
        for s in SORTS:
            rows = list(d.tables[s].items()); rng.shuffle(rows); d.tables[s] = dict(rows)
    rng.shuffle(result.interfaces)
    return result

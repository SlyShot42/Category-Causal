"""Fresh constant codes and coherent surgery across every diagram object."""
from __future__ import annotations
from .records import SORTS, Description, Interface, Diagram
from .mechanisms import LIBRARY, DOMAINS, Mechanism, validate_library

def intervention_library(description, class_values, labels=None, library=LIBRARY):
    enlarged, codes = dict(library), {}
    for v, value in class_values.items():
        assert description.tables["Var"][v]["role"] == "endo"
        typ = description.tables["Var"][v]["type"]; assert value in DOMAINS[typ]
        label = labels[v] if labels else v
        code = f"DO::{label}::{value}"; assert code not in enlarged
        enlarged[code] = Mechanism((), typ, {(): value}); codes[v] = code
    assert validate_library(enlarged)
    return enlarged, codes

def surgery_description(description, variable_codes):
    result = Description(description.name, boundary=set(description.boundary))
    result.tables["Var"] = {rid: dict(row) for rid, row in description.tables["Var"].items()}
    for mid, row in description.tables["Mech"].items():
        result.tables["Mech"][mid] = {**row, "code": variable_codes.get(row["output"], row["code"])}
    for pid, row in description.tables["Input"].items():
        if description.tables["Mech"][row["mech"]]["output"] not in variable_codes:
            result.tables["Input"][pid] = dict(row)
    result.tables["Dep"] = {rid: dict(row) for rid, row in description.tables["Dep"].items() if row["effect"] not in variable_codes}
    return result

def surgery_diagram(diagram, assembly, class_codes):
    modules = {}
    for name, module in diagram.modules.items():
        codes = {rid: class_codes[cid] for rid in module.tables["Var"]
                 if (cid := assembly.qmaps["Var"][(name, rid)]) in class_codes}
        modules[name] = surgery_description(module, codes)
    interfaces = []
    for interface in diagram.interfaces:
        codes = {rid: class_codes[cid] for rid in interface.description.tables["Var"]
                 if (cid := assembly.qmaps["Var"][(interface.left, interface.left_map["Var"][rid])]) in class_codes}
        d = surgery_description(interface.description, codes)
        maps = [{s: {rid: mapping[s][rid] for rid in d.tables[s]} for s in SORTS}
                for mapping in [interface.left_map, interface.right_map]]
        interfaces.append(Interface(interface.name, d, interface.left, interface.right, *maps))
    return Diagram(modules, interfaces)

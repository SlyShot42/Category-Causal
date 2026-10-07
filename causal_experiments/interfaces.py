"""Partial interfaces, explicit embeddings, and pre-quotient diagram validation."""
from __future__ import annotations
from .records import SORTS, ARROWS, ATTRIBUTES, Description, Interface, InvalidDiagram
from .local_validation import description_issues, validate_model

def validate_diagram(diagram, library):
    issues = []
    for name, module in diagram.modules.items():
        if module.name != name:
            issues.append({"stage": "local_module", "kind": "object_name", "witness": {"object": name}})
        issues.extend(validate_model(module, library, closed=False, stage="local_module")["issues"])
    seen = set()
    for interface in diagram.interfaces:
        if interface.name in seen:
            issues.append({"stage": "interface", "kind": "interface_name", "witness": {"interface": interface.name}})
        seen.add(interface.name)
        issues.extend(description_issues(interface.description, library, "interface"))
        for side in ("left", "right"):
            target_name = getattr(interface, side)
            maps = getattr(interface, side + "_map")
            def add(kind, **w):
                issues.append({"stage": "interface", "kind": kind,
                               "witness": {"interface": interface.name, "side": side, **w}})
            if target_name not in diagram.modules:
                add("interface_target", target=target_name); continue
            target = diagram.modules[target_name]
            if set(maps) != set(SORTS): add("map_sorts"); continue
            for sort in SORTS:
                if set(maps[sort]) != set(interface.description.tables[sort]):
                    add("map_totality", sort=sort); continue
                values = list(maps[sort].values())
                if len(values) != len(set(values)): add("map_injectivity", sort=sort)
                for rid, image in maps[sort].items():
                    if image not in target.tables[sort]:
                        add("map_reference", sort=sort, record=rid, image=image); continue
                    row, image_row = interface.description.tables[sort][rid], target.tables[sort][image]
                    for attr in ATTRIBUTES[sort]:
                        if row.get(attr) != image_row.get(attr):
                            add("attribute_mismatch", sort=sort, record=rid, field=attr,
                                expected=row.get(attr), actual=image_row.get(attr))
                    for arrow, target_sort in ARROWS[sort].items():
                        if maps[target_sort].get(row.get(arrow)) != image_row.get(arrow):
                            add("naturality", sort=sort, record=rid, field=arrow)
    if issues: raise InvalidDiagram(issues)
    return True

def fixture_interface(name, left, right, pairs):
    # pairs[sort] maps selected left record IDs to selected right record IDs.
    pairs = {s: dict(pairs.get(s, {})) for s in SORTS}
    renaming = {s: {rid: f"o:{s}:{j}" for j, rid in enumerate(pairs[s])} for s in SORTS}
    d = Description(name)
    for sort in SORTS:
        for rid in pairs[sort]:
            row = left.tables[sort][rid]
            d.tables[sort][renaming[sort][rid]] = {
                **{a: row[a] for a in ATTRIBUTES[sort]},
                **{a: renaming[ts][row[a]] for a, ts in ARROWS[sort].items()}}
    left_map = {s: {renaming[s][r]: r for r in pairs[s]} for s in SORTS}
    right_map = {s: {renaming[s][r]: image for r, image in pairs[s].items()} for s in SORTS}
    return Interface(name, d, left.name, right.name, left_map, right_map)

def common_interface(name, left, right, sorts=SORTS):
    return fixture_interface(name, left, right,
        {s: {r: r for r in left.tables[s] if r in right.tables[s]} if s in sorts else {} for s in SORTS})

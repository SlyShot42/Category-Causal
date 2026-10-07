"""Independent connected-components and direct ordered-equation reference implementations."""
from __future__ import annotations
from collections import defaultdict
from .records import SORTS
from .mechanisms import LIBRARY

def connected_component_oracle(diagram):
    result = {}
    for sort in SORTS:
        graph = {(name, rid): set() for name, module in diagram.modules.items() for rid in module.tables[sort]}
        for interface in diagram.interfaces:
            for rid in interface.description.tables[sort]:
                a = (interface.left, interface.left_map[sort][rid])
                b = (interface.right, interface.right_map[sort][rid])
                graph[a].add(b); graph[b].add(a)
        components, unseen = set(), set(graph)
        while unseen:
            seed = unseen.pop(); found = {seed}; pending = [seed]
            while pending:
                for neighbor in graph[pending.pop()]:
                    if neighbor in unseen: unseen.remove(neighbor); found.add(neighbor); pending.append(neighbor)
            components.add(frozenset(found))
        result[sort] = components
    return result

def partition_from_qmaps(qmaps):
    result = {}
    for sort in SORTS:
        groups = defaultdict(set)
        for tag, cid in qmaps[sort].items(): groups[cid].add(tag)
        result[sort] = {frozenset(group) for group in groups.values()}
    return result

def direct_ground_evaluate(ground_equations, assignment, intervention=None, library=LIBRARY):
    values = dict(assignment)
    intervention = {} if intervention is None else intervention
    for output, code, arguments in ground_equations:
        if output in intervention: values[output] = intervention[output]
        else: values[output] = library[code].table[tuple(values[v] for v in arguments)]
    return values

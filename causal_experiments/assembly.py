"""Descend records and attributes to the quotient; assemble with fresh structural state."""
from __future__ import annotations
import time
from dataclasses import dataclass
from .records import SORTS, ARROWS, ATTRIBUTES, Description
from .mechanisms import LIBRARY
from .interfaces import validate_diagram
from .quotient import normalize, impose_interfaces, eliminate_duplicates
from .global_validation import validate_closed_assembly

def reconstruct_quotient(diagram, normalized, sets):
    qmaps = {s: {tag: f"{s}:{sets[s].find(i)}" for i, tag in enumerate(normalized.tags[s])} for s in SORTS}
    quotient = Description("assembly")
    for sort in SORTS:
        for name, rid in normalized.tags[sort]:
            row = diagram.modules[name].tables[sort][rid]
            transformed = {attr: row[attr] for attr in ATTRIBUTES[sort]}
            transformed.update({a: qmaps[target][(name, row[a])] for a, target in ARROWS[sort].items()})
            cid = qmaps[sort][(name, rid)]
            if cid in quotient.tables[sort]: assert quotient.tables[sort][cid] == transformed
            else: quotient.tables[sort][cid] = transformed
    forests = {s: [{"a": normalized.tags[s][a], "b": normalized.tags[s][b], "evidence": evidence}
                   for a, b, evidence in sets[s].forest] for s in SORTS}
    return quotient, qmaps, forests

@dataclass
class Assembly:
    description: Description
    qmaps: dict
    forest: dict
    validation: dict
    mode: str
    timings: dict

def assemble(diagram, library=LIBRARY, mode="raw", normalized=None):
    assert mode in {"raw", "deduplicated"}
    stamps = {}
    t = time.perf_counter(); validate_diagram(diagram, library); stamps["input_validation_s"] = time.perf_counter() - t
    t = time.perf_counter()
    normalized = normalize(diagram) if normalized is None else normalized
    stamps["normalization_s"] = time.perf_counter() - t
    t = time.perf_counter(); sets = impose_interfaces(normalized); stamps["equivalence_s"] = time.perf_counter() - t
    t = time.perf_counter()
    if mode == "deduplicated": eliminate_duplicates(diagram, normalized, sets)
    stamps["duplicate_elimination_s"] = time.perf_counter() - t
    t = time.perf_counter(); quotient, qmaps, forest = reconstruct_quotient(diagram, normalized, sets)
    stamps["quotient_reconstruction_s"] = time.perf_counter() - t
    t = time.perf_counter(); validation = validate_closed_assembly(quotient, library)
    stamps["global_validation_s"] = time.perf_counter() - t
    # Normalization has its own measurement and is excluded from the structural total.
    stamps["structural_total_s"] = sum(v for k, v in stamps.items() if k != "normalization_s")
    return Assembly(quotient, qmaps, forest, validation, mode, stamps)

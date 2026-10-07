"""Closed-assembly validity and optional injectivity diagnostics."""
from __future__ import annotations
from collections import defaultdict
from .records import SORTS
from .local_validation import validate_model

def validate_closed_assembly(description, library):
    """Check complete ownership, signatures, stored edges, and acyclicity."""
    return validate_model(description, library, closed=True, stage="assembled")

def embedding_diagnostics(diagram, assembly):
    warnings = []
    for name, module in diagram.modules.items():
        for sort in SORTS:
            fibers = defaultdict(list)
            for rid in module.tables[sort]: fibers[assembly.qmaps[sort][(name, rid)]].append(rid)
            for cid, records in fibers.items():
                if len(records) > 1:
                    warnings.append({"module": name, "sort": sort, "class": cid, "records": records})
    return warnings

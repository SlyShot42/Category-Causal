"""Structural reference checks, local signatures, ownership, and iterative graph traversal."""
from __future__ import annotations
from collections import Counter, defaultdict, deque
from .records import SORTS, ARROWS, ATTRIBUTES
from .mechanisms import DOMAINS

def description_issues(d, library, stage):
    issues = []
    def add(kind, **w): issues.append({"stage": stage, "kind": kind, "witness": {"object": d.name, **w}})
    if set(d.tables) != set(SORTS):
        add("entity_tables", actual=list(d.tables)); return issues
    for sort in SORTS:
        for rid, row in d.tables[sort].items():
            for arrow, target_sort in ARROWS[sort].items():
                if row.get(arrow) not in d.tables[target_sort]:
                    add("structural_reference", sort=sort, record=rid, field=arrow, target=row.get(arrow))
            for attr in ATTRIBUTES[sort]:
                if attr not in row: add("missing_attribute", sort=sort, record=rid, field=attr)
            if sort == "Var" and (row.get("type") not in DOMAINS or row.get("role") not in {"exo", "endo"}):
                add("variable_attribute", sort=sort, record=rid)
            if sort == "Mech" and row.get("code") not in library: add("unknown_code", sort=sort, record=rid)
            if sort == "Input" and (type(row.get("pos")) is not int or row["pos"] < 1):
                add("input_position", sort=sort, record=rid)
    return issues

def topological_order(vertices, edges):
    adjacent = {v: [] for v in vertices}
    indegree = {v: 0 for v in vertices}
    for a, b in edges: adjacent[a].append(b); indegree[b] += 1
    queue = deque(v for v in vertices if indegree[v] == 0)
    order = []
    while queue:
        v = queue.popleft(); order.append(v)
        for w in adjacent[v]:
            indegree[w] -= 1
            if indegree[w] == 0: queue.append(w)
    if len(order) == len(vertices): return order, []
    residual = {v for v in vertices if indegree[v] > 0}
    colors, parents = {}, {}
    for start in vertices:
        if start not in residual or colors.get(start): continue
        colors[start] = 1
        stack = [(start, iter(adjacent[start]))]
        while stack:
            v, neighbors = stack[-1]
            w = next(neighbors, None)
            if w is None:
                colors[v] = 2; stack.pop(); continue
            if w not in residual: continue
            if not colors.get(w):
                parents[w] = v; colors[w] = 1; stack.append((w, iter(adjacent[w])))
            elif colors[w] == 1:
                path = [v]
                while path[-1] != w: path.append(parents[path[-1]])
                path.reverse(); path.append(w)
                return order, path
    raise AssertionError("A cyclic residual must contain a DFS cycle.")

def validate_model(d, library, closed=True, stage="assembled"):
    issues = description_issues(d, library, stage)
    if issues: return {"valid": False, "issues": issues, "order": [], "edges": set()}
    def add(kind, **w): issues.append({"stage": stage, "kind": kind, "witness": w})
    variables, mechanisms, inputs, deps = (d.tables[s] for s in SORTS)
    boundary = set() if closed else d.boundary
    if not boundary <= set(variables) or any(variables[v]["role"] != "endo" for v in boundary & set(variables)):
        add("boundary_definition", boundary=list(boundary))
    owners = defaultdict(list)
    for mid, m in mechanisms.items(): owners[m["output"]].append(mid)
    for v, row in variables.items():
        owned = row["role"] == "endo" and v not in boundary
        if owned and not owners[v]: add("missing_owner", variable=v)
        if owned and len(owners[v]) > 1:
            add("duplicate_owner", variable=v, mechanisms=owners[v],
                codes=[mechanisms[m]["code"] for m in owners[v]])
        if not owned and owners[v]: add("unexpected_owner", variable=v, mechanisms=owners[v])
    groups = defaultdict(list)
    for pid, p in inputs.items(): groups[p["mech"]].append((pid, p))
    for mid, m in mechanisms.items():
        entry = library[m["code"]]
        if variables[m["output"]]["type"] != entry.output_type:
            add("output_type", mechanism=mid)
        counts = Counter(p["pos"] for _, p in groups[mid])
        expected = set(range(1, len(entry.signature) + 1))
        if set(counts) != expected: add("incomplete_signature", mechanism=mid, positions=dict(counts))
        for pos, count in counts.items():
            if count > 1:
                add("duplicate_input", mechanism=mid, position=pos,
                    inputs=[pid for pid, p in groups[mid] if p["pos"] == pos])
        for pid, p in groups[mid]:
            if p["pos"] in expected and variables[p["var"]]["type"] != entry.signature[p["pos"] - 1]:
                add("input_type", mechanism=mid, input=pid)
    edges = {(p["var"], mechanisms[p["mech"]]["output"]) for p in inputs.values()}
    stored = {(d["cause"], d["effect"]) for d in deps.values()}
    if stored != edges:
        add("dependency_mismatch", missing=list(edges - stored), extra=list(stored - edges))
    order, cycle = topological_order(variables, edges)
    if cycle:
        witness_inputs = []
        lookup = {}
        for pid, p in inputs.items(): lookup.setdefault((p["var"], mechanisms[p["mech"]]["output"]), pid)
        for edge in zip(cycle, cycle[1:]): witness_inputs.append(lookup[edge])
        issues.append({"stage": "acyclicity" if stage == "assembled" else stage,
                       "kind": "cycle", "witness": {"path": cycle, "inputs": witness_inputs}})
    return {"valid": not issues, "issues": issues, "order": order, "edges": edges}

def validate_local_module(description, library):
    """Validate an open module using its declared endogenous boundary."""
    return validate_model(description, library, closed=False, stage="local_module")

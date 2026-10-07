"""Serialize quotient provenance and independently verify success and failure evidence."""
from __future__ import annotations
from collections import defaultdict
from .records import SORTS, ARROWS, ATTRIBUTES, description_json
from .mechanisms import LIBRARY

def certificate_json(assembly):
    return {"description": description_json(assembly.description), "mode": assembly.mode,
            "qmaps": {s: [{"tag": tag, "class": cid} for tag, cid in assembly.qmaps[s].items()] for s in SORTS},
            "forest": assembly.forest, "valid": assembly.validation["valid"],
            "issues": assembly.validation["issues"],
            "rank": {v: i for i, v in enumerate(assembly.validation["order"])}}

def check_certificate(diagram, certificate, library=LIBRARY):
    q = {s: {tuple(r["tag"]): r["class"] for r in certificate["qmaps"][s]} for s in SORTS}
    target = certificate["description"]["tables"]
    interfaces = {i.name: i for i in diagram.interfaces}
    def row(sort, tag): return diagram.modules[tag[0]].tables[sort][tag[1]]
    def key(sort, tag):
        r = row(sort, tag); name = tag[0]
        if sort == "Mech":
            occurrences = [(p["pos"], q["Var"][(name, p["var"])])
                           for p in diagram.modules[name].tables["Input"].values() if p["mech"] == tag[1]]
            return (r["code"], q["Var"][(name, r["output"])], tuple(v for _, v in sorted(occurrences)))
        if sort == "Input": return (q["Mech"][(name, r["mech"])], r["pos"], q["Var"][(name, r["var"])])
        if sort == "Dep": return (q["Var"][(name, r["cause"])], q["Var"][(name, r["effect"])])
        raise AssertionError("Duplicate unions cannot identify variables.")
    # Cache mechanism keys to keep the independent checker linear in the input size.
    mech_keys = {}
    for name, module in diagram.modules.items():
        arguments = defaultdict(list)
        for p in module.tables["Input"].values(): arguments[p["mech"]].append((p["pos"], q["Var"][(name, p["var"])]))
        for rid, m in module.tables["Mech"].items():
            mech_keys[(name, rid)] = (m["code"], q["Var"][(name, m["output"])],
                                    tuple(v for _, v in sorted(arguments[rid])))
    original_key = key
    def key(sort, tag): return mech_keys[tag] if sort == "Mech" else original_key(sort, tag)
    for sort in SORTS:
        tags = {(name, rid) for name, m in diagram.modules.items() for rid in m.tables[sort]}
        assert set(q[sort]) == tags
        graph = {tag: [] for tag in tags}
        for edge in certificate["forest"][sort]:
            a, b = tuple(edge["a"]), tuple(edge["b"]); e = edge["evidence"]
            assert a in tags and b in tags
            if e["kind"] == "interface":
                interface = interfaces[e["interface"]]; rid = e["record"]
                expected = {(interface.left, interface.left_map[sort][rid]),
                            (interface.right, interface.right_map[sort][rid])}
                assert {a, b} == expected
            else:
                assert e["kind"] == "duplicate" and certificate["mode"] == "deduplicated"
                assert key(sort, a) == key(sort, b)
            graph[a].append(b); graph[b].append(a)
        unseen, classes = set(tags), set()
        while unseen:
            seed = unseen.pop(); pending = [seed]; members = {seed}
            while pending:
                for neighbor in graph[pending.pop()]:
                    if neighbor in unseen: unseen.remove(neighbor); pending.append(neighbor); members.add(neighbor)
            labels = {q[sort][tag] for tag in members}
            assert len(labels) == 1
            label = next(iter(labels)); assert label not in classes; classes.add(label)
        assert classes == set(target[sort])
        for interface in diagram.interfaces:
            for rid in interface.description.tables[sort]:
                assert q[sort][(interface.left, interface.left_map[sort][rid])] == q[sort][(interface.right, interface.right_map[sort][rid])]
        if certificate["mode"] == "deduplicated" and sort != "Var":
            key_classes = {}
            for tag in tags:
                k = key(sort, tag)
                assert k not in key_classes or key_classes[k] == q[sort][tag]
                key_classes[k] = q[sort][tag]
        for tag in tags:
            r, image = row(sort, tag), target[sort][q[sort][tag]]
            for attr in ATTRIBUTES[sort]: assert r[attr] == image[attr]
            for arrow, target_sort in ARROWS[sort].items(): assert q[target_sort][(tag[0], r[arrow])] == image[arrow]
    vars_, mechs, inputs, deps = (target[s] for s in SORTS)
    owners, slots = defaultdict(list), defaultdict(list)
    for mid, m in mechs.items(): owners[m["output"]].append(mid)
    for pid, p in inputs.items(): slots[p["mech"]].append((pid, p))
    edges = {(p["var"], mechs[p["mech"]]["output"]) for p in inputs.values()}
    if certificate["valid"]:
        assert not certificate["issues"]
        for v, r in vars_.items(): assert len(owners[v]) == (1 if r["role"] == "endo" else 0)
        for mid, m in mechs.items():
            entry = library[m["code"]]; ps = [p for _, p in slots[mid]]
            assert sorted(p["pos"] for p in ps) == list(range(1, len(entry.signature) + 1))
            assert vars_[m["output"]]["type"] == entry.output_type
            for p in ps: assert vars_[p["var"]]["type"] == entry.signature[p["pos"] - 1]
        assert {(r["cause"], r["effect"]) for r in deps.values()} == edges
        rank = certificate["rank"]; assert set(rank) == set(vars_)
        assert all(rank[a] < rank[b] for a, b in edges)
    else:
        assert certificate["issues"]
        for issue in certificate["issues"]:
            w, kind = issue["witness"], issue["kind"]
            if kind == "missing_owner": assert vars_[w["variable"]]["role"] == "endo" and not owners[w["variable"]]
            elif kind == "duplicate_owner":
                assert len(set(w["mechanisms"])) > 1 and all(mechs[m]["output"] == w["variable"] for m in w["mechanisms"])
                assert w["codes"] == [mechs[m]["code"] for m in w["mechanisms"]]
            elif kind == "duplicate_input":
                assert len(set(w["inputs"])) > 1
                assert all(inputs[p]["mech"] == w["mechanism"] and inputs[p]["pos"] == w["position"] for p in w["inputs"])
            elif kind == "cycle":
                path = w["path"]; assert len(path) >= 2 and path[0] == path[-1]
                assert len(w["inputs"]) == len(path) - 1
                for a, b, pid in zip(path, path[1:], w["inputs"]):
                    assert inputs[pid]["var"] == a and mechs[inputs[pid]["mech"]]["output"] == b
            else: raise AssertionError(("Unsupported failure witness", kind))
    return True

def check_interface_witness(diagram, issue):
    assert issue["stage"] == "interface"
    w = issue["witness"]
    interface = next(i for i in diagram.interfaces if i.name == w["interface"])
    maps = getattr(interface, w["side"] + "_map")
    target = diagram.modules[getattr(interface, w["side"])]
    sort = w["sort"]
    if issue["kind"] == "attribute_mismatch":
        rid, attr = w["record"], w["field"]
        assert interface.description.tables[sort][rid][attr] != target.tables[sort][maps[sort][rid]][attr]
    elif issue["kind"] == "naturality":
        rid, arrow = w["record"], w["field"]; ts = ARROWS[sort][arrow]
        assert maps[ts][interface.description.tables[sort][rid][arrow]] != target.tables[sort][maps[sort][rid]][arrow]
    else: raise AssertionError(("Unsupported interface witness", issue["kind"]))
    return True

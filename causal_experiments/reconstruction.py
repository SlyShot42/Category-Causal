"""Independent four-table recovery and retained-record intervention isomorphisms."""
from __future__ import annotations
import copy
from .records import SORTS, ARROWS, ATTRIBUTES

def canonical_ground(ground):
    target = copy.deepcopy(ground)
    redirects = {s: {rid: rid for rid in ground.tables[s]} for s in SORTS}
    by_pair, deps = {}, {}
    for rid, row in ground.tables["Dep"].items():
        pair = (row["cause"], row["effect"])
        if pair not in by_pair: by_pair[pair] = rid; deps[rid] = row
        redirects["Dep"][rid] = by_pair[pair]
    target.tables["Dep"] = deps
    return target, redirects

def reconstruction_oracle(assembly, ground, oracle_maps, canonical=False, sorts=SORTS):
    """Check a known-model cocone on all four sorts, or a closed subset for equation-only comparisons."""
    assert all(target in sorts for s in sorts for target in ARROWS[s].values())
    if canonical: target, redirects = canonical_ground(ground)
    else: target, redirects = ground, {s: {r: r for r in ground.tables[s]} for s in SORTS}
    comparison = {s: {} for s in sorts}
    for sort in sorts:
        for (name, rid), cid in assembly.qmaps[sort].items():
            image = redirects[sort][oracle_maps[name][sort][rid]]
            assert cid not in comparison[sort] or comparison[sort][cid] == image, (sort, "not well-defined", cid)
            comparison[sort][cid] = image
        images = list(comparison[sort].values())
        assert len(set(images)) == len(images), (sort, "not injective")
        assert set(images) == set(target.tables[sort]), (sort, "not surjective")
        assert set(comparison[sort]) == set(assembly.description.tables[sort])
    for sort in sorts:
        for cid, image in comparison[sort].items():
            row, expected = assembly.description.tables[sort][cid], target.tables[sort][image]
            for attr in ATTRIBUTES[sort]: assert row[attr] == expected[attr], (sort, cid, attr)
            for arrow, target_sort in ARROWS[sort].items():
                assert comparison[target_sort][row[arrow]] == expected[arrow], (sort, cid, arrow)
    return comparison

def retained_record_isomorphism(before, after, operated):
    # The comparison is induced by retained original tagged records, not raw class labels.
    comparison = {s: {} for s in SORTS}
    for sort in SORTS:
        for tag, cid in after.qmaps[sort].items():
            image = before.qmaps[sort][tag]
            assert image in operated.tables[sort]
            assert cid not in comparison[sort] or comparison[sort][cid] == image
            comparison[sort][cid] = image
        assert len(set(comparison[sort].values())) == len(comparison[sort])
        assert set(comparison[sort].values()) == set(operated.tables[sort])
        for cid, image in comparison[sort].items():
            row, expected = after.description.tables[sort][cid], operated.tables[sort][image]
            for attr in ATTRIBUTES[sort]: assert row[attr] == expected[attr]
            for arrow, ts in ARROWS[sort].items(): assert comparison[ts][row[arrow]] == expected[arrow]
    return comparison

"""F01-F15 diagnostics plus four supporting manuscript controls; constructed on demand."""
from __future__ import annotations
import copy
from .records import SORTS, Diagram, Interface, make_description, bool_vars
from .mechanisms import LIBRARY
from .interfaces import fixture_interface, common_interface
from .assembly import assemble
from .interventions import intervention_library, surgery_diagram, surgery_description

def build_fixtures():
    """Return diagnostics with expected stages and the running-example context."""
    FIXTURES = {}
    def fixture(fid, diagram, raw, deduplicated=None, stage="assembled", note="", library=LIBRARY):
        FIXTURES[fid] = {"diagram": diagram, "raw": raw, "deduplicated": raw if deduplicated is None else deduplicated,
                         "stage": stage, "note": note, "library": library}

    up = make_description("upstream", bool_vars(["UX", "UY"], ["X", "Y"]), [("X", "ID", ["UX"]), ("Y", "XOR", ["X", "UY"])])
    down = make_description("downstream", bool_vars(["UZ"], ["Y", "Z"]), [("Z", "XOR", ["Y", "UZ"])], ["Y"])
    RUNNING_DIAGRAM = Diagram({up.name: up, down.name: down}, [common_interface("handoff", up, down)])
    RUNNING_GROUND = make_description("running_ground", bool_vars(["UX", "UY", "UZ"], ["X", "Y", "Z"]),
        [("X", "ID", ["UX"]), ("Y", "XOR", ["X", "UY"]), ("Z", "XOR", ["Y", "UZ"])])
    RUNNING_EQUATIONS = [("X", "ID", ["UX"]), ("Y", "XOR", ["X", "UY"]), ("Z", "XOR", ["Y", "UZ"])]
    fixture("F01", RUNNING_DIAGRAM, True, note="Running example and exact reconstruction")
    m = make_description("unfilled", bool_vars([], ["Y"]), [], ["Y"])
    fixture("F02", Diagram({m.name: m}, []), False, note="Unfilled boundary")
    a = make_description("a", bool_vars([], ["Y"]), [("Y", "ZERO", [])])
    b = make_description("b", bool_vars([], ["Y"]), [("Y", "ZERO", [])])
    fixture("F03", Diagram({"a": a, "b": b}, [common_interface("variables", a, b, ["Var"])]), False, True, note="Duplicate owners; DE repairs")
    a = make_description("a", bool_vars(["U"], ["Y"]), [("Y", "ID", ["U"])])
    b = copy.deepcopy(a); b.name = "b"
    fixture("F04", Diagram({"a": a, "b": b}, [common_interface("no_inputs", a, b, ["Var", "Mech", "Dep"])]), False, True, note="Duplicate position; DE repairs")
    c = make_description("b", bool_vars(["U"], ["Y"]), [("Y", "NOT", ["U"])])
    fixture("F05", Diagram({"a": a, "b": c}, [common_interface("variables", a, c, ["Var"])]), False, note="ID versus NOT")
    a_cycle = make_description("a", bool_vars([], ["X", "Y"]), [("Y", "ID", ["X"])], ["X"])
    b_cycle = make_description("b", bool_vars([], ["X", "Y"]), [("X", "ID", ["Y"])], ["Y"])
    fixture("F06", Diagram({"a": a_cycle, "b": b_cycle}, [common_interface("feedback", a_cycle, b_cycle, ["Var"])]), False, stage="acyclicity", note="Actual directed cycle")
    a_t = make_description("a", {"x": ("exo", "bool")}, [])
    b_t = make_description("b", {"x": ("exo", "tri")}, [])
    fixture("F07", Diagram({"a": a_t, "b": b_t}, [common_interface("type", a_t, b_t)]), False, stage="interface", note="Boolean/three-valued mismatch")
    fixture("F08", Diagram({"a": a, "b": c}, [common_interface("code", a, c, ["Var", "Mech"])]), False, stage="interface", note="Code attribute mismatch")
    a_pos = make_description("a", bool_vars(["u", "w"], ["Y"]), [("Y", "AND", ["u", "w"])])
    b_pos = copy.deepcopy(a_pos); b_pos.name = "b"
    pairs = {"Var": {r: r for r in a_pos.tables["Var"]}, "Mech": {"m:Y": "m:Y"}, "Input": {"p:Y:1": "p:Y:2"}}
    fixture("F09", Diagram({"a": a_pos, "b": b_pos}, [fixture_interface("position", a_pos, b_pos, pairs)]), False, stage="interface", note="Position 1 mapped to 2")
    three = {n: copy.deepcopy(a) for n in ["a", "b", "c"]}
    for name, module in three.items(): module.name = name
    fixture("F10", Diagram(three, [common_interface("ab", three["a"], three["b"]), common_interface("bc", three["b"], three["c"])]), True, note="Transitive equation overlap")
    local = make_description("local", bool_vars(["a", "b"], ["C"]), [("C", "AND", ["a", "b"])])
    noise = make_description("noise", bool_vars(["c"]), [])
    i1 = fixture_interface("ac", local, noise, {"Var": {"a": "c"}})
    i2 = fixture_interface("bc", local, noise, {"Var": {"b": "c"}})
    fixture("F11", Diagram({"local": local, "noise": noise}, [i1, i2]), True, note="Non-injective variable map; induced (c,c)")
    repeat = make_description("repeat", bool_vars(["X"], ["Y"]), [("Y", "XOR", ["X", "X"])])
    fixture("F12", Diagram({repeat.name: repeat}, []), True, note="Two input slots and parallel dependency rows")
    ordered = make_description("ordered", bool_vars(["X", "U"], ["Y"]), [("Y", "AND_NOT", ["X", "U"])])
    fixture("F13", Diagram({ordered.name: ordered}, []), True, note="Non-symmetric argument order")
    a_multi = make_description("a", bool_vars(["U"], ["X", "Y"]), [("X", "ID", ["U"]), ("Y", "NOT", ["X"])])
    b_multi = copy.deepcopy(a_multi); b_multi.name = "b"
    MULTI_BASE = Diagram({"a": a_multi, "b": b_multi}, [common_interface("shared", a_multi, b_multi)])
    base = assemble(MULTI_BASE)
    class_values = {base.qmaps["Var"][("a", "X")]: 1, base.qmaps["Var"][("a", "Y")]: 0}
    MULTI_LIBRARY, multi_codes = intervention_library(base.description, class_values)
    MULTI_OPERATED = surgery_diagram(MULTI_BASE, base, multi_codes)
    fixture("F14", MULTI_OPERATED, True, library=MULTI_LIBRARY, note="Coherent two-variable intervention on all copies")
    shared = Diagram({"a": a, "b": copy.deepcopy(a)}, [])
    shared.modules["b"].name = "b"; shared.interfaces = [common_interface("shared", shared.modules["a"], shared.modules["b"])]
    shared_assembly = assemble(shared)
    cid = shared_assembly.qmaps["Var"][("a", "Y")]
    one_library, one_codes = intervention_library(shared_assembly.description, {cid: 0})
    left = surgery_description(shared.modules["a"], {"Y": one_codes[cid]})
    i = shared.interfaces[0]
    new_interface = surgery_description(i.description, {rid: one_codes[cid] for rid in i.description.tables["Var"]
                                                         if i.left_map["Var"][rid] == "Y"})
    new_maps = [{s: {rid: mapping[s][rid] for rid in new_interface.tables[s]} for s in SORTS}
                for mapping in [i.left_map, i.right_map]]
    incoherent = Diagram({"a": left, "b": shared.modules["b"]}, [Interface(i.name, new_interface, i.left, i.right, *new_maps)])
    fixture("F15", incoherent, False, stage="interface", library=one_library, note="Incoherent one-copy intervention")
    a_diff = make_description("a", bool_vars(["U"], ["Y"]), [("Y", "ID", ["U"])])
    b_diff = make_description("b", bool_vars(["W"], ["Y"]), [("Y", "ID", ["W"])])
    fixture("F16", Diagram({"a": a_diff, "b": b_diff}, [common_interface("different_inputs", a_diff, b_diff, ["Var"])]), False, note="Same code, different input classes")
    b_alias = make_description("b", bool_vars(["U"], ["Y"]), [("Y", "ID_ALIAS", ["U"])])
    fixture("F17", Diagram({"a": a_diff, "b": b_alias}, [common_interface("equal_tables", a_diff, b_alias, ["Var"])]), False, note="Equal truth tables, distinct codes")
    typed = make_description("typed", {"B": ("exo", "bool"), "T": ("exo", "tri"), "Z": ("endo", "tri"), "W": ("endo", "tri")},
                             [("Z", "BOOL_TO_TRI", ["B"]), ("W", "TRI_ID", ["T"])])
    fixture("F18", Diagram({typed.name: typed}, []), True, note="Valid three-valued signatures")
    same_object = make_description("same", bool_vars(["a", "b"], ["C"]), [("C", "AND", ["a", "b"])])
    fixture("F19", Diagram({same_object.name: same_object}, [fixture_interface("same_module", same_object, same_object, {"Var": {"a": "b"}})]), True, note="Two interface legs into the same module")

    return {'FIXTURES': FIXTURES, 'RUNNING_DIAGRAM': RUNNING_DIAGRAM, 'RUNNING_GROUND': RUNNING_GROUND, 'RUNNING_EQUATIONS': RUNNING_EQUATIONS, 'MULTI_BASE': MULTI_BASE, 'MULTI_LIBRARY': MULTI_LIBRARY, 'base': base, 'multi_codes': multi_codes, 'repeat': repeat, 'ordered': ordered, 'typed': typed, 'up': up}

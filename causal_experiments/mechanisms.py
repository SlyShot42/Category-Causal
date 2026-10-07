"""Finite typed truth tables and code identity; intervention codes extend this library."""
from __future__ import annotations
import itertools
from dataclasses import dataclass

DOMAINS = {"bool": (0, 1), "tri": (0, 1, 2)}
@dataclass
class Mechanism:
    signature: tuple[str, ...]
    output_type: str
    table: dict[tuple[int, ...], int]

LIBRARY: dict[str, Mechanism] = {}
def declare(code, signature, output_type, function):
    LIBRARY[code] = Mechanism(tuple(signature), output_type,
        {args: function(*args) for args in itertools.product(*(DOMAINS[t] for t in signature))})

declare("ZERO", (), "bool", lambda: 0)
declare("ONE", (), "bool", lambda: 1)
declare("ID", ("bool",), "bool", lambda a: a)
declare("NOT", ("bool",), "bool", lambda a: 1 - a)
declare("AND", ("bool", "bool"), "bool", lambda a, b: a * b)
declare("OR", ("bool", "bool"), "bool", lambda a, b: int(a or b))
declare("XOR", ("bool", "bool"), "bool", lambda a, b: a ^ b)
declare("AND_NOT", ("bool", "bool"), "bool", lambda a, b: a * (1 - b))
declare("XOR3", ("bool",) * 3, "bool", lambda a, b, c: a ^ b ^ c)
declare("MAJ3", ("bool",) * 3, "bool", lambda a, b, c: int(a + b + c >= 2))
declare("TRI_ID", ("tri",), "tri", lambda a: a)
declare("BOOL_TO_TRI", ("bool",), "tri", lambda a: 2 * a)
declare("ID_ALIAS", ("bool",), "bool", lambda a: a)  # Same table, a different library code.

def validate_library(library):
    for code, entry in library.items():
        assert entry.output_type in DOMAINS, (code, "unknown output type")
        assert all(t in DOMAINS for t in entry.signature), (code, "unknown input type")
        expected = set(itertools.product(*(DOMAINS[t] for t in entry.signature)))
        assert set(entry.table) == expected, (code, "not a total finite table")
        assert all(v in DOMAINS[entry.output_type] for v in entry.table.values()), (code, "output type")
    return True

def library_json(library):
    return {"domains": DOMAINS, "codes": {
        code: {"signature": e.signature, "output_type": e.output_type,
               "table": [{"args": list(a), "value": v} for a, v in e.table.items()]}
        for code, e in library.items()}}


assert validate_library(LIBRARY)

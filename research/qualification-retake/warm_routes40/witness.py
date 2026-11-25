"""Read the common graph witness independently of TPR1, and compare every ordered ID."""

import hashlib
import struct
from pathlib import Path


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(raw):
    require(len(raw) <= 1024**2 and raw[:4] == b"WRT1", "witness envelope")
    cursor = 4

    def take(n):
        nonlocal cursor
        value = raw[cursor : cursor + n]
        require(len(value) == n, "truncated witness")
        cursor += n
        return value

    def u8():
        return take(1)[0]

    def u16():
        return struct.unpack("<H", take(2))[0]

    call = ub = length = used = first = total = 0
    inside = False
    positions = []
    output_seen = False
    next_layer = 0
    rows = []
    graphs = []
    while cursor < len(raw):
        tag = take(1)
        if tag == b"C":
            require(not inside and not positions, "nested call")
            first, length = u16(), u16()
            require(first == total and 0 < length <= 256, "call plan")
            call += 1
            ub = used = 0
            inside = True
        elif tag == b"U":
            require(inside and not positions, "nested graph")
            width = u8()
            require(0 < width <= 32, "graph width")
            positions = [u16() for _ in range(width)]
            require(
                positions == list(range(first + used, first + used + width))
                and used + width <= length,
                "positions",
            )
            used += width
            ub += 1
            next_layer = 0
            output_seen = False
            graphs.append((call, ub, tuple(positions)))
        elif tag == b"O":
            require(
                inside
                and positions
                and next_layer == 35
                and used == length
                and u8() == len(positions) - 1
                and not output_seen,
                "output selection",
            )
            output_seen = True
        elif tag == b"R":
            layer, n, stride = u8(), u8(), u16()
            require(
                positions
                and layer == next_layer
                and layer < 36
                and 16 <= stride <= 512
                and stride % 4 == 0,
                "route view",
            )
            require(layer < 35 or output_seen, "no physical last output")
            which = positions if layer < 35 else positions[-1:]
            require(n == len(which), "route row count")
            for pos in which:
                ids = tuple(take(4))
                require(max(ids) < 128 and len(set(ids)) == 4, "invalid top-4")
                rows.append((call, ub, layer, pos, ids))
            next_layer += 1
        elif tag == b"E":
            require(
                positions
                and output_seen == (used == length)
                and next_layer == (36 if output_seen else 35),
                "incomplete graph",
            )
            positions = []
        elif tag == b"D":
            require(inside and not positions and used == length, "incomplete call")
            inside = False
            total += length
        elif tag == b"F":
            require(not inside and not positions and call and cursor == len(raw), "terminal")
            return graphs, rows
        else:
            raise ValueError("invalid witness tag")
    raise ValueError("no terminal")


def fixture(data):
    graphs, rows = read(data)
    require(graphs == [(1, 1, (0, 1, 2)), (1, 2, (3, 4))], "fixture graphs")
    for _, _, layer, pos, ids in rows:
        expected = tuple((127 - 3 * pos - 5 * layer - rank) % 128 for rank in range(4))
        require(ids == expected, "label/position/rank mismatch")
    require(len(rows) == 176, "row coverage 5*35+1")
    return {"graphs": len(graphs), "rows": len(rows), "sha256": hashlib.sha256(data).hexdigest()}


def compare_tpr(witness, tpr):
    import runpy

    parser = runpy.run_path(str(Path(__file__).resolve().parents[1] / "prefix_observer/journal.py"))
    _, rows = read(witness)
    decoded = []
    for record in parser["records"](tpr):
        if record[0] == "row":
            _, call, ubatch, layer, position, _, ids = record
            decoded.append((call, ubatch, layer, position, ids))
    require(rows == decoded, "independent graph IDs differ from TPR1")

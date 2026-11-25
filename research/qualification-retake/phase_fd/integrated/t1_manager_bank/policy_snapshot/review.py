"""Independently read the policy words, the PFJ1 cut and the C269 selector controls."""

import hashlib
import json
import os
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PFJ_SOURCE = HERE.parents[1] / "analyse.py"
PFJ_SHA = "28c224bd734f841fb87a9e3b1350f0a1008308898d2629a396c7b21d2a56b443"
ARMS = ("off", "heat-a", "heat-b", "age-a", "age-b", "pending", "missing", "duplicate")
HEADER = struct.Struct("<8s15Q")
LAYER = struct.Struct("<169Q")
GEOM = (2303, 2304, 4, 36, 40, 128)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def digest(data):
    return hashlib.sha256(
        json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def population(mode, layer):
    ages = list(range(1, 41))
    heat = [20] * 128
    heat[:3] = [0, 5, 7]
    if layer == 0:
        if mode == "heat-b":
            heat[1] = 9
        if mode in ("age-a", "age-b"):
            heat[1] = 7
        if mode == "age-b":
            ages[1], ages[2] = ages[2], ages[1]
    return (40, *ages, *heat)


def parse_policy(raw):
    require(len(raw) >= HEADER.size, "short sidecar header")
    magic, status, matches, call, n, p0, p1, *values = HEADER.unpack_from(raw)
    require(magic == b"TPOLICY1" and status in (0, 1, 2, 3, 4), "sidecar format")
    full = status == 1
    require(len(raw) == HEADER.size + int(full) * 36 * LAYER.size, "sidecar length/status")
    return (status, matches, call, n, p0, p1, *values), list(LAYER.iter_unpack(raw[HEADER.size :]))


def predicted(words, slots):
    # Prefer an empty slot, then lexicographic (hotness of logical expert, slot age, slot).
    def key(s):
        expert, state, _ = slots[s]
        return (0, 0, 0, s) if state == 0 else (1, words[41 + expert], words[1 + s], s)

    available = [s for s, (_, state, _) in enumerate(slots) if state != 1]
    tagged = [s for s in available if slots[s][0] in {1, 2}]
    return {"r0": min(available, key=key), "backed": min(tagged or available, key=key)}


def witness(rows, arm):
    # This fixture drives only ENTER/RETURN without a forward or real jobs.
    enters = [(r.call, r.a, r.b, r.c) for r in rows if r.kind == 1]
    need_calls = [(1, 1, 2044, 2044)] if arm == "missing" else [(1, 5, 2044, 2048)]
    if arm == "duplicate":
        need_calls.append((2, 5, 2044, 2048))
    require(
        enters == need_calls and rows[0].kind == 1 and rows[-1].kind == 25, "externals/terminal"
    )
    pending = arm == "pending"
    channel = None
    started = 0
    files = []
    slots = {}
    weights = {}
    queue = {1: [], 2: []}
    returned = []
    projection = []
    exits = set()
    previous_ns = 0
    for r in rows:
        k = r.kind
        require(
            r.ns >= previous_ns
            and r.ns > 0
            and 0 <= r.begin <= r.ns
            and not r.error
            and not r.reserved,
            "journal clock/flags",
        )
        previous_ns = r.ns
        if k == 1:
            require(channel is None and r.call == started + 1, "call nesting")
            channel = started = r.call
            projection.append([k, r.call, r.a, r.b, r.c])
        elif k == 2:
            require(
                channel == r.call and (r.a, r.b, r.c) == (0, 2 if pending else 0, int(pending)),
                "return service population",
            )
            channel = None
            returned.append(r.call)
            projection.append([k, r.call, r.a, r.b, r.c])
        elif k == 5:
            require(
                channel == r.call == 1
                and 0 <= r.layer < 36
                and 0 <= r.slot < 40
                and (r.layer, r.slot) not in slots,
                "duplicate/invalid slot",
            )
            state = 1 if pending and r.layer == 0 and r.slot in (1, 2) else 2
            claim = int(pending and r.layer == 0 and r.slot == 2)
            require(
                (r.expert, r.gen, r.a, r.b) == (r.slot, 1, state, claim),
                "slot binding/gen/state/claim",
            )
            slots[r.layer, r.slot] = (r.expert, state, claim)
            projection.append([k, r.layer, r.slot, r.expert, r.gen, r.a, r.b])
        elif k == 6:
            require(
                pending
                and r.call == 1
                and r.b in (1, 2)
                and (channel is not None) == (r.b == 1)
                and (r.layer, r.slot, r.expert, r.gen) == (0, 1, 1, 1)
                and r.a == len(queue[r.b]),
                "FIFO entry/order/cut",
            )
            queue[r.b].append((r.layer, r.slot, r.expert, r.gen))
            projection.append([k, r.call, r.b, r.a, *queue[r.b][-1]])
        elif k == 26:
            require(
                pending
                and channel is None
                and r.call == 1
                and r.slot in (1, 2)
                and (r.layer, r.expert, r.gen, r.a, r.b) == (0, r.slot, 1, 1, int(r.slot == 2)),
                "pending return descriptor",
            )
            projection.append([k, r.slot, r.b])
        elif k == 7:
            require(
                channel == r.call == 1
                and r.fd >= 0
                and r.fd not in files
                and r.b > 0
                and r.c & os.O_DIRECT
                and (r.c & os.O_ACCMODE) == os.O_RDONLY,
                "source descriptor",
            )
            files.append(r.fd)
            projection.append([k, len(files) - 1, r.c])
        elif k == 8:
            require(
                channel == r.call == 1
                and 0 <= r.layer < 36
                and 0 <= r.component < 3
                and (r.layer, r.component) not in weights
                and 0 <= r.c < len(files)
                and files[r.c] == r.fd
                and (r.a, r.b, r.c) == (4096 * r.component, 32, 0),
                "weight binding",
            )
            weights[r.layer, r.component] = (r.c, r.a, r.b)
            projection.append([k, r.layer, r.component, r.c, r.a, r.b])
        elif k == 24:
            require(channel is None and 0 <= r.worker < 4 and r.worker not in exits, "worker exit")
            exits.add(r.worker)
        elif k == 25:
            require(
                r is rows[-1] and channel is None and (r.a, r.b, r.c) == (0, 0, 0), "closed manager"
            )
            projection.append([k, r.a, r.b, r.c])
        else:
            raise ValueError("unexpected job/graph/invalid kind")
    require(
        returned == [x[0] for x in enters]
        and len(slots) == 1440
        and len(weights) == 108
        and len(files) == 1,
        "snapshot coverage",
    )
    require(
        queue[1] == queue[2]
        and len(queue[1]) == (2 if pending else 0)
        and [r.slot for r in rows if r.kind == 26] == ([1, 2] if pending else []),
        "duplicate FIFO conservation",
    )
    return [slots[0, s] for s in range(40)], digest(projection), enters, len(exits)


def grade_policy(arm, raw, enters):
    h, layers = parse_policy(raw)
    status, matches, call, n, p0, p1, *other = h
    expected_matches = sum((n, p0, p1) == (5, 2044, 2048) for _, n, p0, p1 in enters)
    expect_status = {"missing": 0, "pending": 2, "duplicate": 3}.get(arm, 1)
    require((status, matches) == (expect_status, expected_matches), "match classification")
    if arm == "missing":
        require(not any(h), "missing cut header")
    else:
        require((call, n, p0, p1) == (1, 5, 2044, 2048), "sidecar/PFJ call correlation")
        require(
            tuple(other[:6]) == GEOM
            and tuple(other[6:]) == ((2, 1, 2) if arm == "pending" else (0, 0, 0)),
            "snapshot counters/geometry",
        )
    if status == 1:
        for layer, words in enumerate(layers):
            require(words == population(arm, layer), "counter/age/hotness seed")
    return h, layers


def family(out):
    out = Path(out)
    require(sha(PFJ_SOURCE) == PFJ_SHA, "frozen PFJ1 parser")
    parse = run_path(PFJ_SOURCE)["read_journal"]
    compact = {}
    views = {}
    for arm in ARMS:
        folder = out / arm
        jf = folder / "journal.pfj"
        nf = folder / "native.json"
        side = folder / "policy.bin"
        require(
            jf.is_file()
            and not jf.is_symlink()
            and jf.stat().st_size < 2**20
            and nf.is_file()
            and not nf.is_symlink()
            and nf.stat().st_size < 8192,
            "arm files",
        )
        rows, header = parse(jf)
        slots, projection, enters, exits = witness(rows, arm)
        require(not side.is_symlink(), "sidecar symlink")
        if arm == "off":
            require(not side.exists(), "disabled sidecar")
            h, layers = None, []
        else:
            require(side.is_file() and side.stat().st_size <= 48800, "sidecar cap")
            h, layers = grade_policy(arm, side.read_bytes(), enters)
        native = json.loads(nf.read_bytes())
        require(
            set(native) == {"r0", "backed"} and all(type(v) is int for v in native.values()),
            "native decisions schema",
        )
        choices = predicted(layers[0] if layers else population(arm, 0), slots)
        require(native == choices, "native victim vs independent oracle")
        views[arm] = (projection, choices, layers)
        compact[arm] = {
            "pfj_sha256": header["journal_sha256"],
            "records": header["records"],
            "projection_sha256": projection,
            "choices": choices,
            "native_sha256": sha(nf),
            "sidecar_bytes": side.stat().st_size if h else 0,
            "sidecar_sha256": sha(side) if h else None,
            "calls": enters,
            "worker_exits": exits,
            "status": h[0] if h else None,
            "matches": h[1] if h else None,
        }
    require(
        len({views[a][0] for a in ARMS[:5]}) == 1 and views["off"][:2] == views["heat-a"][:2],
        "PFJ projection/OFF parity",
    )
    pairs = {}
    for label, count in (("heat", 1), ("age", 2)):
        a, b = (views[label + "-" + letter] for letter in ("a", "b"))
        different = sum(
            x != y for u, v in zip(a[2], b[2], strict=True) for x, y in zip(u, v, strict=True)
        )
        require(
            a[0] == b[0]
            and a[1]["r0"] == b[1]["r0"] == 0
            and (a[1]["backed"], b[1]["backed"]) == (1, 2)
            and different == count,
            label + " ambiguity",
        )
        pairs[label] = {
            "differing_policy_words": different,
            "same_PFJ_projection": True,
            "same_stock_victim": True,
            "backed_victims": [1, 2],
        }
    return {
        "status": "PASS_SYNTHETIC_POLICY_CUT_AND_AMBIGUITIES",
        "arms": compact,
        "pairs": pairs,
        "parser_sha256": PFJ_SHA,
        "forward_count": 0,
    }

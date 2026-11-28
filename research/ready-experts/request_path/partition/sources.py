"""Authenticate natural PFJ and supplied WRT observations, including the cut before scoring."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

from policy import EXPERTS, LAYERS, Wave, digest, need, waves

HERE = Path(__file__).resolve().parent
READY = HERE.parents[1]
QUAL = READY.parent / "qualification-retake"
REGISTRY = "8cd41f2de3d183c121b8123bb1fd619c1803c5df6dd48d5676c1dde2158c857c"
ENTRY = READY / "cpu_wave/frame_lease/group_service/shared_owner/renewal"
OBS = run_path(READY / "selection.py")
SRC, PFJ = OBS["SRC"], OBS["PROFILE"]
E = run_path(ENTRY / "entry.py")
METHOD = "6a807c1946fd64519f50c417ab5bdf64f5404fcb12574105990b18026c6bec4d"


def sha(path):
    with path.open("rb") as fd:
        return hashlib.file_digest(fd, "sha256").hexdigest()


def natural_phase(call):
    if call <= 2:
        return "prefill_5" if call == 1 else "prefill_148"
    return "decode_to_first" if call <= 46 else "tail"


def supplied_phase(call):
    return "prefill_153" if call == 9 else "decode_32"


def prefix_phase(call):
    return "T1_prefill" if call <= 9 else "T1_decode"


def cpu(groups):
    return [w for w in groups if w.layer < LAYERS]


def pf_routes(rows, shift=0, verify_demands=False):
    visits, remaps, expected = {}, [], {}
    for r in rows:
        key = r.call - shift, r.tile, r.layer
        if r.kind == 27:
            ranks = visits.setdefault(key, [])
            need(r.b * 4 == len(ranks), "PFJ rank ordinal")
            ranks.extend(r.a.to_bytes(4, "little"))
        elif verify_demands and r.kind == 9:
            remaps.append((*key, r.wave))
            expected[remaps[-1]] = []
        elif verify_demands and r.kind == 10:
            need(remaps[-1] == (*key, r.wave), "PFJ demand at a different callback")
            expected[remaps[-1]].append(r.expert + r.layer * EXPERTS)
    schedule = waves(visits)
    if verify_demands:
        actual = [Wave(*site, tuple(expected[site])) for site in remaps]
        need(actual == schedule, "native wave boundaries, parking-only wave, or demand order")
    return schedule, digest([[site, ranks] for site, ranks in visits.items()])


def cpu_snapshot(rows):
    return sorted(
        r.layer * EXPERTS + r.expert for r in rows if r.kind == 5 and r.layer < LAYERS and r.a == 2
    )


def natural(archive, prefix_only=False):
    new = archive / "part-106" / SRC["SOURCES"]["P106"][0] / "ON"
    old = archive / "part-97" / SRC["SOURCES"]["P97"][0] / "ON/raw/events.pfj"
    journal = new / "observer/events.pfj"
    seal = SRC["pinned"](new / "before-t2.json", OBS["T1_SEAL"])
    cut, total = PFJ["metadata"](journal, True)
    pre = list(PFJ["iter_rows"](journal, 0, cut))
    grade, _ = PFJ["prefix_grade"](pre, PFJ["T1"], 9)
    need(
        cut == 87736 == seal["records"] and all(seal[k] == v for k, v in grade.items()),
        "natural prefix seal",
    )
    warm, train_hash = pf_routes(pre)
    train_seed = cpu_snapshot(pre)
    need(len(train_seed) == 184 and len(set(train_seed)) == 184, "natural initial CPU ready")
    if prefix_only:
        return cpu(warm), [], train_seed, None, dict(training_ranks=train_hash)
    need(sha(journal) == E["P106"] and sha(old) == E["P97"], "natural journals")
    suffix = list(PFJ["iter_rows"](journal, cut, total - cut))
    old_rows, _ = PFJ["PFJ"]["read_journal"](old)
    actual, ranks_hash = pf_routes(suffix, seal["calls"], True)
    need(
        pf_routes(old_rows, 0, True) == (actual, ranks_hash) and len(actual) == 2987,
        "P106/P97 rank or wave",
    )

    def reservations(rows, shift):
        return [E["tx"](r, shift) for r in rows if r.kind == 11]

    tx1, tx2 = reservations(pre, 0), reservations(suffix, seal["calls"])
    need(tx2 == reservations(old_rows, 0) and len(tx2) == 2354, "natural reservation orders")
    pool, frequency, native, bank, gpu = {}, Counter(), Counter(), Counter(), Counter()
    for n, (call, _, layer, _, _, expert, victim) in enumerate(tx1 + tx2):
        part = prefix_phase(call) if n < len(tx1) else natural_phase(call)
        if layer < LAYERS:
            native[part] += 1
            hit, _ = E["reserve"](pool, frequency, n, layer, expert, victim)
            bank[part] += int(not hit)
        else:
            gpu[part] += 1
    entry_file = ENTRY / "evidence-entry-20261128-r01/decision.json"
    frozen = SRC["pinned"](
        entry_file, "5e815f588d0aacb559346eeca693311222c2a61d7683b03ede140db275107598"
    )
    # Link the compact bank receipt to the enrolled private transaction stream as well.
    transactions = ENTRY / "evidence-entry-20261128-r01/transactions.json.gz"
    need(
        sha(transactions) == "a6208d27a2b44a7aef1c56185e320b2af647a5dd0dc5478d46282a8aa45ff730",
        "bank source",
    )
    plan = E["F"]["unpack"](transactions)
    need(
        plan["suffix_sha256"] == E["digest"](tx2) and plan["prefix"] == tx1,
        "compiled bank transactions",
    )
    need(
        all(
            native[k] == v["reservations"] and bank[k] == v["misses"]
            for k, v in frozen["phases"].items()
        ),
        "compiled bank counts",
    )
    info = dict(
        source=dict(P106=E["P106"], P97=E["P97"], T1=seal["sha256"]),
        training_ranks=train_hash,
        suffix_ranks=ranks_hash,
        prefix_callbacks=len(warm),
        suffix_callbacks=len(actual),
        native_cpu=dict(native),
        native_cpu_and_bank=dict(bank),
        native_cuda=dict(gpu),
        before_post_calls=seal["calls"],
    )
    return cpu(warm), cpu(actual), train_seed, None, info


def wrt_prefix(data):
    """Cut at the eighth call return. The canonical witness reader validates the prefix."""
    need(data[:4] == b"WRT1", "WRT prefix header")
    offset, completed = 4, 0
    while offset < len(data):
        tag = data[offset : offset + 1]
        offset += 1
        if tag == b"C":
            offset += 4
        elif tag == b"U":
            offset += 1 + 2 * data[offset]
        elif tag == b"R":
            offset += 4 + 4 * data[offset + 1]
        elif tag == b"O":
            offset += 1
        elif tag == b"D":
            completed += 1
            if completed == 8:
                need(data[offset : offset + 1] == b"C", "WRT cut before increment")
                return data[:offset] + b"F"
        else:
            need(tag == b"E", "unexpected WRT prefix marker")
    raise ValueError("missing WRT cut")


def supplied(archive, prefix_only=False):
    receipt = QUAL / "warm_route_family/evidence-r1.json"
    need(sha(receipt) == REGISTRY, "WRT registry")
    registry = json.loads(receipt.read_bytes())
    need(
        registry["status"] == "PASS_WARM_ROUTE_FAMILY" and len(registry["arms"]) == 4, "WRT family"
    )
    read = run_path(QUAL / "warm_routes40/witness.py")["read"]
    pairs = defaultdict(list)
    for arm in registry["arms"]:
        root = archive / "part-04/tesy-wrt40-fam-p25-r01/raw" / (arm["run_id"] + ".native")
        for name in ("initial.json", "routed-witness.bin"):
            need(sha(root / name) == arm["native_sha256"][name], "WRT " + name)
        raw = (root / "routed-witness.bin").read_bytes()
        before = wrt_prefix(raw)
        graphs, rows = read(before if prefix_only else raw)
        need(
            graphs[-1][0] == (8 if prefix_only else 41)
            and (prefix_only or len(rows) == arm["groups"]),
            "WRT group count or cut",
        )
        visits = {}
        for call, tile, layer, _, ids in rows:
            visits.setdefault((call, tile, layer), []).extend(ids)
        schedule = waves(visits)
        slots = json.loads((root / "initial.json").read_bytes())
        need(not slots["pending_queue"], "WRT pending prefix")
        state, members = [], set()
        for layer, rec in enumerate(slots["layers"]):
            need(layer == rec["layer"] and len(rec["slot_expert"]) == 40, "WRT physical slot count")
            for e, g, state_id, claim in zip(
                rec["slot_expert"],
                rec["slot_generation"],
                rec["slot_state"],
                rec["slot_claimed"],
                strict=True,
            ):
                need(
                    state_id in (0, 2) and claim == 0 and (state_id == 2) == (e >= 0),
                    "WRT pending or corrupt",
                )
                state.append((layer, e, g, state_id, claim))
                if layer < LAYERS and e >= 0:
                    k = EXPERTS * layer + e
                    need(k not in members, "duplicate WRT member")
                    members.add(k)
        warm = [w for w in schedule if w.call <= 8]
        test = [w for w in schedule if w.call > 8]
        last = {}
        serial = 0
        for w in cpu(warm):
            for k in w.keys:
                serial += 1
                last[k] = serial
        initial = sorted(members, key=lambda k: (last.get(k, -1), k))
        summary = dict(
            ranks=arm["native_sha256"]["routed-witness.bin"],
            snapshot=digest(state),
            training_ranks=hashlib.sha256(before).hexdigest(),
            prefix_callbacks=len(warm),
            suffix_callbacks=len(test),
            supplied_rows=len(rows),
        )
        pairs[arm["case"]].append((cpu(warm), cpu(test), initial, summary, arm["mode"]))
    cases = {}
    for name, pair in pairs.items():
        a, b = pair
        need(a[:-1] == b[:-1] and {a[-1], b[-1]} == {"ON", "OFF"}, "WRT arms disagree")
        warm, test, initial, info, _ = a
        cases[name] = (warm, test, [], initial, info)
    return cases

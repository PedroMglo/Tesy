"""Select the seven real reservations and every pinned consumer of the timed C281 wave."""

from collections import Counter, deque
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(HERE.parent / "pair.py")
SRC, need, SCREEN = P["SRC"], P["need"], P["B"]["SCREEN"]
SITE = (2, 1, 1, 0)
FIFO = "c4da12c30db61c7213007a03bbf677f6eea72692687b23b11df1ccec021d5644"
W, SLAB = P["WINDOW"], P["SLAB"]


def capture(rows):
    queue, active, slots = deque(), set(), {}
    ranks, demands, reserves, original_order = [], [], [], []
    claimed, published = [], []
    bounds = {}
    waiting = selected = False
    for i, r in enumerate(rows):
        key = SRC["key"](r)
        site = SRC["origin"](r)
        if r.kind == 5:
            slots[key[:2]] = key, r.a
        if r.kind == 11:
            slots[key[:2]] = key, 1
            if site == SITE:
                reserves.append(key)
        if r.kind == 9 and site == SITE:
            need(not active and not queue, "incoming service")
        if r.kind == 27 and site == SITE:
            need(r.b == len(ranks), "target row order")
            ranks.append(list(r.a.to_bytes(4, "little")))
        if r.kind == 10 and site == SITE:
            demands.append(key)
        if r.kind == 12:
            queue.append(key)
        if r.kind == 19 and site == SITE:
            need(r.a == 1 and not waiting, "real blocking remap")
            waiting = True
            bounds["wait_enter"] = [i, r.ns]
        if r.kind in (13, 14):
            need(queue and queue[0] == key, "captured FIFO")
            if key == (1, 39, 11, 47) and r.kind == 13 and not selected:
                need(waiting and not active and len(queue) == 7 and len(demands) == 16, "admission")
                original_order = list(queue)
                need(
                    len(set(original_order)) == 7 and set(reserves) == set(original_order), "cohort"
                )
                for k in demands:
                    need(
                        slots[k[:2]] == (k, 1 if k in original_order else 2), "resident generation"
                    )
                bounds["first_claim"] = [i, r.ns]
                selected = True
            if waiting:
                need(r.kind == 13 and key in reserves, "foreign or skipped service during wait")
                claimed.append(key)
            queue.popleft()
            if r.kind == 13:
                active.add(key)
        if r.kind == 17:
            need(key in active, "publication")
            active.remove(key)
            slots[key[:2]] = key, 2
            if waiting:
                published.append(key)
                bounds["last_publish"] = [i, r.ns]
        if r.kind == 20 and site == SITE:
            need(
                waiting
                and selected
                and not active
                and not queue
                and claimed == original_order
                and Counter(published) == Counter(claimed),
                "original barrier drain",
            )
            bounds["wait_return"] = [i, r.ns]
            waiting = False
        if r.kind == 23 and site == SITE:
            bounds["remap_return"] = [i, r.ns]
            break
    need(
        [k[3] for k in original_order] == [47, 3, 10, 48, 82, 44, 98]
        and len(ranks) == 32
        and len(set(demands)) == len({k[1] for k in demands}) == 16
        and bounds.keys()
        == {"wait_enter", "first_claim", "last_publish", "wait_return", "remap_return"},
        "full queue, pins and cuts",
    )
    physical = {k[3]: k[1] for k in demands}
    expected = [[physical.get(e, -1) for e in rank] for rank in ranks]
    need({e for rank in ranks for e in rank} >= physical.keys(), "routed demand")
    return dict(
        fifo=[list(k) for k in original_order],
        pins=[list(k) for k in demands],
        ranks=ranks,
        remap=expected,
    ), bounds


def plan(archive, derived):
    historic = SRC["pinned"](HERE.parent / "evidence-fifo-20261128-r01/receipt.json", FIFO)
    prior = SRC["pinned"](
        SCREEN["NATURAL"] / "prefill_retention/request_cost/receipt.json", SCREEN["PRIOR"]
    )
    selection, journals = None, {}
    for tag in ("P97", "P106"):
        _, auth = SCREEN["read_arm"](archive, tag, prior[tag])
        need(auth["journal_sha256"] == historic["arms"][tag]["journal_sha256"], "journal identity")
        name, h, _ = SRC["SOURCES"][tag]
        root = archive / ("part-" + tag[1:]) / name
        if tag == "P97":
            rows, _ = SRC["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
        else:
            _, rows, _, _ = SRC["Q"]["read_new"](root, h)
        candidate, bounds = capture(rows)
        need(selection is None or candidate == selection, "different workload")
        selection = candidate
        journals[tag] = dict(journal_sha256=auth["journal_sha256"], bounds=bounds)
        del rows
    pack = SRC["pinned"](derived / "receipt.json", P["PACK"])
    idx = SRC["pinned"](derived / "integral-index.json", pack["index_sha256"])
    need(idx["weight_window"] == W, "pack geometry")
    entries = {(e["layer"], e["expert"]): e for e in idx["experts"]}
    records = {}
    for layer, slot, gen, e in selection["pins"]:
        record = entries[layer, e]
        parts = {c["name"]: c for c in record["components"]}
        digests = []
        for i, role in enumerate(("gate", "down", "up")):
            c = parts[f"blk.{layer}.ffn_{role}_exps.weight"]
            need(
                c["packed_relative_offset"] == i * SLAB and c["size_bytes"] == SLAB,
                "matrix geometry",
            )
            digests.append(c["sha256"])
        records[e] = dict(slot=slot, generation=gen, offset=record["pack_offset"], matrices=digests)
    need(records[48]["offset"] - records[47]["offset"] == W + 36864, "same adjacent records")
    return selection, journals, records, pack

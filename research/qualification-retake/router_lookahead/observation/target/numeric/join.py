"""Audit the optional C292 post-attention records against official routes and slot generations."""

import hashlib
import statistics
import struct
from collections import Counter, defaultdict

WIDTH = 2880
EXPERTS = 128
COEFFICIENTS = 4 * (2 * WIDTH + WIDTH * EXPERTS + EXPERTS)
REFERENCE = "b8f13ce9e80eb419273eedff02777501799755bc353da51756e0d0a356c8ada6"
BUFFERS = {1: "CPU", 2: "CPU_Mapped", 3: "CUDA0", 4: "CUDA_Host"}


def need(test, msg):
    if not test:
        raise ValueError(msg)


def quartet(packed):
    need(0 <= packed < 2**32, "packed quartet")
    ids = tuple(packed.to_bytes(4, "little"))
    need(max(ids) < EXPERTS and len(set(ids)) == 4, "four distinct IDs")
    return ids


def lookup(e, owners, state, claims):
    place = owners.get((e.layer, e.expert))
    if place is None:
        need((e.slot, e.gen, e.a, e.b) == (-1, 0, 0, 0), "reported absent binding")
    else:
        gen, expert, value = state[place]
        need((place[1], gen, expert, value) == (e.slot, e.gen, e.expert, e.a), "lookup slot/epoch")
        need(e.b == int((e.layer, e.slot, e.gen, e.expert) in claims), "lookup claim")
    need(e.c == 0, "lookup reserved field")


def source_site(events, output_rows):
    data, start = events[0], events[1]
    need(
        [e.kind for e in events] == [35, 32] + [36] * 5 + [33] * len(output_rows),
        "source record order",
    )
    n = data.c
    need(
        data.a == data.layer - 1 and data.b in (1, 3) and 0 < data.begin <= data.ns <= start.ns,
        "ASK/DATA",
    )
    need((start.a, start.b, start.c) == (data.a, 4 * n * WIDTH, COEFFICIENTS), "START shape")
    get = events[2:7]
    prev = start.ns
    sizes = (start.b, WIDTH * 4, WIDTH * 4, WIDTH * EXPERTS * 4, EXPERTS * 4)
    for j, (e, size) in enumerate(zip(get, sizes, strict=True)):
        need(
            e.component == j and e.a == size and e.b in BUFFERS and e.c in (0, 1),
            "GET bytes/role/buffer",
        )
        need(bool(e.c) == (e.b != 3) and prev <= e.begin <= e.ns, "GET host flag or order")
        prev = e.ns
    pred = {}
    for e, (index, pos) in zip(events[7:], output_rows, strict=True):
        need((e.b, e.c) == (index, pos) and prev <= e.ns and pos not in pred, "E33 position/clock")
        pred[pos] = (e.ns, quartet(e.a))
        prev = e.ns
    return pred


def compact(values):
    return dict(
        n=len(values),
        min=min(values),
        max=max(values),
        median=statistics.median(values),
        sum=sum(values),
    )


def audit(rows, enabled):
    need(rows and rows[-1].kind == 25, "complete native journal")
    need(all(1 <= e.kind <= (36 if enabled else 30) for e in rows), "unexpected event type")
    official = hashlib.sha256()
    physical = hashlib.sha256()
    probes, positions, actual, looks, demands = (defaultdict(dict) for _ in range(5))
    queries = defaultdict(list)
    tiles, starts, slots, owners, claims, reserves = {}, {}, {}, {}, set(), {}
    for index, e in enumerate(rows):
        tile = e.call, e.tile
        site, wave = (*tile, e.layer), (*tile, e.layer, e.wave)
        place, key = (e.layer, e.slot), (e.layer, e.slot, e.gen, e.expert)
        if e.kind == 3:
            need(tile not in tiles and e.a == e.c - e.b + 1, "tile geometry")
            tiles[tile] = (e.b, e.c)
        elif e.kind == 27:
            ranks = quartet(e.a)
            need(e.b == len(actual[site]), "ordered rank row")
            actual[site][e.b] = ranks
            official.update(struct.pack("<4i4B", *site, e.b, *ranks))
        elif e.kind == 10:
            need(e.expert not in demands[wave], "duplicate expert in demand wave")
            demands[wave][e.expert] = (index, key)
            physical.update(struct.pack("<7i", *wave, e.expert, e.slot, e.gen))
        if not enabled:
            continue
        if e.kind == 31:
            lo, hi = tiles[tile]
            need(
                e.layer == e.wave == -1 and len(positions[tile]) == e.a and e.b == lo + e.a <= hi,
                "input rows",
            )
            need(e.c == int(e.b >= 188), "output mask of supplied C292")
            positions[tile][e.a] = (e.b, e.c)
        elif e.kind in (32, 33, 35, 36):
            need(
                tile in tiles and 1 <= e.layer < 36 and e.wave == -1 and e.worker == -1,
                "source scope",
            )
            queries[site].append(e)
        elif e.kind == 9:
            starts.setdefault(site, e.ns)
        elif e.kind == 5:
            need(place not in slots and (e.gen, e.expert, e.a) == (0, -1, 0), "C292 initial state")
            slots[place] = e.gen, e.expert, e.a
        elif e.kind == 11:
            gen, old, state = slots[place]
            need(
                (e.gen, e.a) == (gen + 1, old) and state != 1 and key not in reserves,
                "reservation history",
            )
            if state == 2:
                need(owners.pop((e.layer, old)) == place, "victim")
            need((e.layer, e.expert) not in owners, "duplicate owner")
            owners[e.layer, e.expert] = place
            slots[place] = e.gen, e.expert, 1
            reserves[key] = (index, wave)
        elif e.kind == 13:
            need(key not in claims and slots[place] == (e.gen, e.expert, 1), "dispatch state")
            claims.add(key)
        elif e.kind == 17:
            need(key in claims and slots[place] == (e.gen, e.expert, 1), "publication state")
            claims.remove(key)
            slots[place] = e.gen, e.expert, 2
        elif e.kind == 34:
            lookup(e, owners, slots, claims)
            need(e.expert not in looks[wave], "duplicate lookup in wave")
            looks[wave][e.expert] = (index, e)
    result = dict(
        official_ordered_sha256=official.hexdigest(),
        demanded_slots_sha256=physical.hexdigest(),
        official_quartets=sum(map(len, actual.values())),
        physical_demands=sum(map(len, demands.values())),
    )
    need(len(tiles) == 38 and result["official_quartets"] == 7768, "C292 scope")
    if not enabled:
        return dict(status="PASS_LOOKAHEAD_OFF", **result)
    need(len(slots) == 1440 and not claims, "slot state at drain")
    need(
        positions.keys() == tiles.keys() and looks.keys() == demands.keys(),
        "tile or lookup population",
    )
    expected = set()
    calibration = {}
    totals, spans, transfer = defaultdict(Counter), defaultdict(list), defaultdict(Counter)
    for tile, (lo, hi) in tiles.items():
        p = positions[tile]
        need(len(p) == hi - lo + 1, "complete row positions")
        for layer in range(1, 36):
            site = (*tile, layer)
            selected = [(j, pos) for j, (pos, yes) in p.items() if layer != 35 or yes]
            if not selected:
                need(not actual.get(site) and site not in queries, "masked final layer")
                continue
            expected.add(site)
            records = queries.get(site)
            need(records and records[0].c == len(p), "missing source or wrong width")
            predictions = source_site(records, selected)
            q, start = records[:2]
            group = ("prefill" if tile[0] == 1 else "decode") + ("/CPU" if layer < 25 else "/CUDA")
            total = totals[group]
            total["sites"] += 1
            total["activation_source_CPU" if q.b == 1 else "activation_source_CUDA0"] += 1
            spans[group + "/ask_to_data_ns"].append(q.ns - q.begin)
            spans[group + "/data_to_start_ns"].append(start.ns - q.ns)
            spans[group + "/start_to_last_available_ns"].append(records[-1].ns - start.ns)
            spans[group + "/last_available_to_first_remap_ns"].append(starts[site] - records[-1].ns)
            for g in records[2:7]:
                transfer[group + f"/role{g.component}/" + BUFFERS[g.b]].update(
                    calls=1, bytes=g.a, ns=g.ns - g.begin
                )
            first_by_expert = {}
            need(len(actual.get(site, {})) == len(selected), "rank population")
            for j, (_, pos) in enumerate(selected):
                stamp, ranks = predictions[pos]
                truth = actual[site][j]
                total.update(rows=1, matched_row_ids=len(set(truth) & set(ranks)))
                for expert in ranks:
                    first_by_expert.setdefault(expert, stamp)
                if 0 <= pos < 32 or 128 <= pos <= 190 or pos in (196, 220):
                    calibration[pos, layer] = ranks
            probes[site] = first_by_expert
    need(queries.keys() == expected and len(calibration) == 3303, "complete source population")
    gold = hashlib.sha256()
    for (pos, layer), ranks in sorted(calibration.items()):
        gold.update(struct.pack("<II4B", pos, layer, *ranks))
    need(gold.hexdigest() == REFERENCE, "independent calibrated predictor")
    counted = set()
    for wave, batch in demands.items():
        site, layer = wave[:3], wave[2]
        need(batch.keys() == looks[wave].keys(), "lookup-demand conservation")
        offered = probes.get(site, {})
        for expert, (di, key) in batch.items():
            li, e = looks[wave][expert]
            need(li < di, "lookup before demand")
            if e.a == 0:
                ri, rw = reserves[key]
                need(li < ri < di and wave == rw, "absent generation not bound to that lookup")
            else:
                need((e.layer, e.slot, e.gen, e.expert) == key, "hit generation")
            if layer == 0:
                continue
            group = ("prefill" if wave[0] == 1 else "decode") + ("/CPU" if layer < 25 else "/CUDA")
            state = ("absent", "loading", "ready")[e.a]
            totals[group]["demand_" + state] += 1
            stamp = offered.get(expert)
            if stamp is not None and stamp <= e.ns:
                totals[group]["available_at_lookup_" + state] += 1
                if e.a == 0:
                    need(key not in counted, "duplicate miss credit")
                    counted.add(key)
                    spans[group + "/available_to_absent_lookup_ns"].append(e.ns - stamp)
    return dict(
        status="PASS_LOOKAHEAD_ON",
        **result,
        matching_calibrated_rows=len(calibration),
        calibrated_sha256=gold.hexdigest(),
        eligible_absent_generations=len(counted),
        totals=dict(totals),
        spans={k: compact(v) for k, v in spans.items()},
        get_by_role_and_buffer=dict(transfer),
    )

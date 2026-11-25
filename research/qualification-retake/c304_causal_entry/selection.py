"""Only consume C304 events through P16 of call zero to seal four selections."""

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path.insert(0, str(UNIT))
import cache_boundary as boundary  # noqa: E402

require = boundary.require
NAMES = [
    f"c304-heldout-{case}-{suffix}"
    for case in ("intervals", "inventory")
    for suffix in ("1-greedy", "2-estimate")
]
MANIFEST = "79749dc967b09a3a7319a60dba93ac3ebcf07b7c99354d10a9d85a156e24049b"


def memberships(published, current):
    broad, last = [], []
    witnesses = []
    for (layer, expert), tile_ids in sorted(published.items()):
        if expert not in current[layer] and len(tile_ids) >= 2:
            require(layer < 35 and set(tile_ids) <= set(range(5)), "nonexistent tile")
            broad.append([layer, expert])
            witnesses.append([layer, expert, sorted(tile_ids)])
            if 4 in tile_ids:
                last.append([layer, expert])
    return broad, last, witnesses


def before_decode(src, initial):
    require(next(src).strip() == boundary.HEADER, "journal schema")
    current = boundary.slots(initial)
    widths = [[] for _ in range(36)]
    routes, active = {}, {}
    published = defaultdict(set)
    p3 = Counter()
    saw_call_start = False
    for line in src:
        k, _, call, route, layer, e, slot, gen, comp, size, width = map(int, line.split())
        require(call == 0, "decode encountered before I")
        if k == 15:
            require(not saw_call_start, "duplicate call0")
            saw_call_start = True
        if k == 16:
            break
        if k == 2:
            require(0 <= layer < 36 and route not in routes, "geometry")
            routes[route] = (layer, len(widths[layer]))
            widths[layer].append(width)
        if k not in range(3, 11):
            continue
        require(route in routes and routes[route][0] == layer and 0 <= e < 128, "foreign route")
        pool = current[layer]
        if k == 3:
            p3[layer] += 1
            at = [i for i, v in enumerate(pool) if v[0] == e]
            require(
                (not at and slot == -1 and gen == size == 0)
                or (at == [slot] and pool[slot][:3] == (e, gen, size)),
                "demand state",
            )
            continue
        require(0 <= slot < 40, "slot")
        old = pool[slot]
        key = layer, slot
        if k == 4:
            if gen == old[1]:
                require(old[:3] == (e, gen, 1), "promotion identity")
            else:
                require(
                    gen == old[1] + 1
                    and old[2] in (0, 2)
                    and old[3] == 0
                    and all(x[0] != e for x in pool),
                    "reservation identity",
                )
                pool[slot] = (e, gen, 1, 0)
        elif k == 5:
            require(old == (e, gen, 1, 0) and key not in active, "claim")
            active[key] = (route, 0)
            pool[slot] = (e, gen, 1, 1)
        else:
            expected_route, index = active[key]
            require(expected_route == route and old == (e, gen, 1, 1), "lifetime/route")
            if 6 <= k <= 9:
                require(
                    index < 12 and k == 6 + index % 4 and comp == index // 4 and size == 4_406_400,
                    "component lifetime",
                )
                active[key] = (route, index + 1)
            else:
                require(index == 12, "early publication")
                del active[key]
                pool[slot] = (e, gen, 2, 0)
                published[layer, e].add(routes[route][1])
    else:
        raise ValueError("missing cut I")
    require(
        saw_call_start
        and not active
        and all(v[2] in (0, 2) and v[3] == 0 for pool in current for v in pool),
        "undrained I",
    )
    require(widths == [[32, 32, 32, 32, 25]] * 35 + [[1]], "C304 increment tile geometry")
    require(
        all(p3[layer] == 0 for layer in range(35)) and p3[35] == 4,
        "expected censored tile membership",
    )
    entry = [{e for e, _, s, _ in pool if s == 2} for pool in current]
    broad, last, cert = memberships(published, entry)
    return dict(
        I_sha256=boundary.digest(current),
        initial_residents=[sorted(s) for s in entry],
        P2_widths=widths,
        P3_groups_0_to_34=sum(len(w) for w in widths[:35]),
        P3_observations_0_to_34=sum(p3[layer] for layer in range(35)),
        P3_observations_35=p3[35],
        reload_twice=broad,
        reload_last=last,
        qualifying_tiles=cert,
    )


def select_arms(raw, study):
    blob = (study / "raw-manifest.json").read_bytes()
    require(hashlib.sha256(blob).hexdigest() == MANIFEST, "C304 manifest")
    files = {x["path"].split("/raw/")[-1]: x for x in json.loads(blob)["files"]}
    result = {}
    for name in NAMES:
        directory = raw / (name + ".native")
        hashes = {}
        for filename in ("initial.json", "events.tsv", "result.json"):
            fd = directory / filename
            item = files[f"{name}.native/{filename}"]
            with fd.open("rb") as source:
                require(
                    fd.stat().st_size == item["bytes"]
                    and hashlib.file_digest(source, "sha256").hexdigest() == item["sha256"],
                    "raw identity",
                )
            hashes[filename] = item["sha256"]
        # Only opaque hashes cover full journals and results. The picker stops before decode.
        initial = json.loads((directory / "initial.json").read_bytes())
        with (directory / "events.tsv").open(encoding="ascii") as journal:
            member = before_decode(journal, initial)
        member["raw_sha256"] = hashes
        result[name] = member
    for i in (0, 2):
        a, b = (result[name] for name in NAMES[i : i + 2])
        require(
            all(
                a[k] == b[k]
                for k in ("I_sha256", "reload_twice", "reload_last", "qualifying_tiles")
            ),
            "greedy/estimator causal inputs differ",
        )
    return result

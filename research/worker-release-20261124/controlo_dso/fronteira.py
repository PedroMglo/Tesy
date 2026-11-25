"""Retrospective C317 physical slot inventory; no model or counterfactual runtime."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import primary, require, source  # noqa: E402

FIELDS = ("slot_expert", "slot_generation", "slot_state", "slot_claimed")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def slots(snapshot):
    rows = sorted(snapshot["layers"], key=lambda row: row["layer"])
    require(
        snapshot["pending_queue"] == 0 and [r["layer"] for r in rows] == list(range(36)),
        "invalid drained anchor",
    )
    result = [list(zip(*(r[f] for f in FIELDS), strict=True)) for r in rows]
    for pool in result:
        require(
            len(pool) == 40
            and all(
                g >= 0
                and not claimed
                and ((e == -1 and state == 0) or (0 <= e < 128 and state == 2))
                for e, g, state, claimed in pool
            ),
            "invalid anchor",
        )
        ids = [e for e, _, state, _ in pool if state]
        require(len(ids) == len(set(ids)), "duplicate resident")
    return result


def inspect(data):
    initial = json.loads(data["initial.json"])
    result = json.loads(data["result.json"])
    text = data["events.tsv"].decode()
    primary(text)  # Certify decode generation lifecycles, including staged SET-only jobs.
    pools = slots(initial)
    require(initial == result["initial"], "initial anchor differs")
    counts = Counter()
    cuts = []
    for line in text.splitlines()[1:]:
        k, _, call, _, layer, expert, slot, gen, _, size, _ = map(int, line.split())
        if (k, call) in ((16, 0), (15, 1)):
            require(
                all(s in (0, 2) and not c for pool in pools for _, _, s, c in pool),
                "in-flight reservation at boundary",
            )
            cuts.append((k, call, fingerprint(pools)))
            present = sum(x[2] == 2 for pool in pools for x in pool)
            l4 = fingerprint(pools[4])
        if k not in (3, 4, 5, 10):
            continue
        pool = pools[layer]
        phase = "decode" if call else "prefill"
        if k == 3:
            seen = [i for i, x in enumerate(pool) if x[0] == expert]
            require(
                (slot == -1 and not seen and size == gen == 0)
                or (slot >= 0 and seen == [slot] and pool[slot][:3] == (expert, gen, size)),
                "P3 mismatch",
            )
            counts[phase + "_P3"] += 1
            continue
        require(0 <= slot < 40, "invalid destination")
        old = pool[slot]
        if k == 4:
            if gen == old[1]:
                require(old[:3] == (expert, gen, 1), "invalid promoted generation")
            else:
                require(
                    old[1] + 1 == gen
                    and old[2] in (0, 2)
                    and not old[3]
                    and all(x[0] != expert for x in pool),
                    "invalid reservation",
                )
                pool[slot] = (expert, gen, 1, 0)
                counts[phase + "_new"] += 1
        elif k == 5:
            require(old == (expert, gen, 1, 0), "invalid accept")
            pool[slot] = (expert, gen, 1, 1)
        else:
            require(old == (expert, gen, 1, 1), "invalid publication")
            pool[slot] = (expert, gen, 2, 0)
            counts[phase + "_publish"] += 1
    require(
        [v[:2] for v in cuts] == [(16, 0), (15, 1)] and cuts[0][2] == cuts[1][2],
        "inconsistent boundary",
    )
    require(
        pools == slots(result["final"]) and counts["decode_P3"] == 4608,
        "incomplete decode or final anchor mismatch",
    )
    return dict(
        boundary_sha256=cuts[0][2],
        layer4_sha256=l4,
        resident=present,
        empty=1440 - present,
        final_slots_verified=1440,
        counts=dict(counts),
    )


def report(root):
    name = source.C317 + "/raw-manifest.json"
    require(
        source.SOURCE_BLOBS[name] == "8181c3a8f958300033da765518bb0d27e7a52539",
        "changed C317 inventory",
    )
    manifest = {x["path"]: x for x in source.archived(name)["files"]}
    inputs, payloads = {}, {}
    for case in ("nominal153", "code153"):
        for arm in (2, 3):
            key = f"c317-{case}-{arm}-trace.native"
            payloads[key] = {}
            for f in ("initial.json", "events.tsv", "result.json"):
                rel = key + "/" + f
                pin = manifest[f"{source.C317}/raw/{rel}"]
                inputs[rel] = {k: pin[k] for k in ("size_bytes", "sha256")}
                payloads[key][f] = source.checked_bytes(root / rel, pin)
    return dict(
        status="REPRODUZIDO_TRACE_DERIVED",
        inputs=inputs,
        digest="SHA256 UTF8 compact JSON arrays in layer 0..35 / slot 0..39 order",
        slot_fields=FIELDS,
        arms={k: inspect(v) for k, v in payloads.items()},
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--raw-dir", required=True, type=Path)
    print(json.dumps(report(cli.parse_args().raw_dir), sort_keys=True, separators=(",", ":")))

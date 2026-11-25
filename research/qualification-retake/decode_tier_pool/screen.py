"""Compare causal decode replacement across and within layers, with exact endpoints."""

import argparse
import hashlib
import io
import json
import resource
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cache_boundary as c294  # noqa: E402
from warm_route_reference.verify import PROMPT, check_witness  # noqa: E402

require = c294.require
PAYLOAD = 13_219_200
PROTOCOL = "fe8b6249e77e5497ded58229a0198cf1e4665d7aadbbe9f8536374bd1107022a"


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def totals(rows):
    result = Counter()
    for row in rows:
        result.update(row)
    return result


def layout(vectors):
    return [
        (il, e) if state == 2 else None
        for il, pool in enumerate(vectors)
        for e, _, state, _ in pool
    ]


def index(slots):
    present = {k: i for i, k in enumerate(slots) if k is not None}
    require(len(present) == sum(k is not None for k in slots), "duplicate resident")
    return present


def repair(current, final):
    """Disjoint counts of F identities. Count destination changes without adding I/O."""
    require(len(current) == len(final), "different layouts")
    locations = index(current)
    targets = index(final)
    rows = defaultdict(Counter)
    for key, dest in targets.items():
        loc = locations.get(key)
        field = "restore" if loc is None else ("in_place" if loc == dest else "displaced")
        rows[key[0]][field] += 1
    return rows


class Bank:
    def __init__(self, initial):
        self.slots = list(initial)
        self.locations = index(initial)
        self.age = [0] * len(initial)

    def serve(self, keys, clock):
        pinned = set(keys)
        require(len(keys) == len(pinned) == 4, "invalid ranks")
        absent = []
        for rank, key in enumerate(keys):
            slot = self.locations.get(key)
            if slot is None:
                absent.append(key)
                eligible = (i for i, occupant in enumerate(self.slots) if occupant not in pinned)
                slot = min(eligible, key=lambda i: (self.slots[i] is not None, self.age[i], i))
                victim = self.slots[slot]
                if victim is not None:
                    del self.locations[victim]
                self.locations[key] = slot
                self.slots[slot] = key
            self.age[slot] = clock + rank + 1
        require(all(k in self.locations for k in keys), "lost pinned rank")
        return absent


def comparison(candidate, control):
    limit = 85 * control // 100
    return dict(
        control=control,
        ceiling=limit,
        candidate=candidate,
        excess_over_ceiling=candidate - limit,
        passes=100 * candidate <= 85 * control,
    )


def stats(masks, end, final):
    repaired = repair(end, final)
    layers = []
    for il in range(36):
        counts = masks[il::36]
        require(len(counts) == 32, "incomplete layer")
        misses = sum(counts)
        r = repaired[il]
        layers.append(
            dict(
                hits=128 - misses,
                misses=misses,
                groups_with_miss=sum(n > 0 for n in counts),
                restore=r["restore"],
                displaced=r["displaced"],
                in_place=r["in_place"],
                charged=misses + r["restore"],
            )
        )
    all_rows = totals(layers)
    require(
        all_rows["in_place"] + all_rows["displaced"] + all_rows["restore"] == len(index(final)),
        "F conservation",
    )
    return dict(
        layers=layers,
        tiers=dict(CPU=totals(layers[:25]), CUDA=totals(layers[25:])),
        total=all_rows,
        logical_charged_bytes=PAYLOAD * all_rows["charged"],
        displaced_payload_bytes=PAYLOAD * all_rows["displaced"],
    )


def changes(candidate, control):
    diffs = defaultdict(int)
    for a, b in zip(candidate, control, strict=True):
        diffs[
            "both_miss" if a and b else "new_miss" if a else "eliminated_miss" if b else "both_hit"
        ] += 1
    return dict(diffs)


def evaluate(start, final, groups, actual):
    require(len(start) == len(final) == 1440 and len(groups) == len(actual) == 1152, "geometry")
    masks = {"R0": actual}
    policies = {"R0": stats(actual, final, final)}
    for name, ranges in (
        ("local", [(il, il + 1) for il in range(36)]),
        ("shared", [(0, 25), (25, 36)]),
    ):
        banks = [Bank(start[a * 40 : b * 40]) for a, b in ranges]
        layer_bank = [bank for bank, (a, b) in zip(banks, ranges, strict=True) for _ in range(a, b)]
        masks[name] = []
        for n, (call, il, _pos, ranks) in enumerate(groups):
            require((call - 1) * 36 + il == n, "group order")
            missed = layer_bank[il].serve([(il, e) for e in ranks], n * 4)
            masks[name].append(len(missed))
        end = [key for bank in banks for key in bank.slots]
        require(
            all(key is None or (key[0] < 25) == (i < 1000) for i, key in enumerate(end)),
            "cross-tier migration",
        )
        policies[name] = stats(masks[name], end, final)
    gate = {
        name: comparison(policies["shared"]["total"]["charged"], policies[name]["total"]["charged"])
        for name in ("R0", "local")
    }
    return dict(
        policies=policies,
        groups_changed={name: changes(masks["shared"], masks[name]) for name in ("R0", "local")},
        gate=gate,
    )


def arm(raw, entries, name):
    blobs, hashes = {}, {}
    for fn in ("events.tsv", "initial.json", "result.json"):
        rel = f"{name}.native/{fn}"
        blob = (raw / rel).read_bytes()
        expected = entries[rel]
        require(len(blob) == expected["bytes"] and sha(blob) == expected["sha256"], "raw identity")
        blobs[fn], hashes[fn] = blob, expected["sha256"]
    initial = json.loads(blobs["initial.json"])
    result = json.loads(blobs["result.json"])
    case = name.split("-")[1]
    require(
        result["case"] == case and result["profile"] == "R0" and result["trace"], "wrong native arm"
    )
    layers = sorted(initial["layers"], key=lambda row: row["layer"])
    require(
        [r["native_cache_buffer"] for r in layers] == ["CPU"] * 25 + ["CUDA0"] * 11
        and all(r["logical_bytes_per_load"] == PAYLOAD for r in layers),
        "wrong device or payload",
    )
    journal = io.StringIO(blobs.pop("events.tsv").decode())
    _, facts = c294.replay(initial, result, journal)
    journal.seek(0)
    next(journal)
    entry = c294.slots(initial)
    ranks, counts, published = defaultdict(list), Counter(), Counter()
    for line in journal:
        kind, _, call, _, il, e, slot, gen, _, state, _ = map(int, line.split())
        if call == 0 and kind == 10:
            entry[il][slot] = (e, gen, 2, 0)
        elif call > 0 and kind == 3:
            require(state in (0, 2), "overlapping demand")
            ranks[call, il].append(e)
            counts[call, il] += state == 0
        elif call > 0 and kind == 10:
            published[call, il] += 1
    require(
        c294.digest(entry) == facts["boundary_slot_vector_sha256"] and counts == published,
        "unconfirmed I or R0 accounting",
    )
    groups = [(call, il, PROMPT[case] + call - 1, ids) for (call, il), ids in ranks.items()]
    ordered = check_witness(case, groups)
    final = c294.slots(result["final"])
    report = evaluate(
        layout(entry), layout(final), groups, [counts[c, il] for c, il, _, _ in groups]
    )
    require(
        report["policies"]["R0"]["total"]["misses"] == facts["counts"]["decode_publications"],
        "wrong R0 denominator",
    )
    return dict(
        raw_sha256=hashes,
        I_sha256=c294.digest(entry),
        F_sha256=c294.digest(final),
        ordered_rank_sha256=ordered,
        **report,
    )


def git(*args):
    return subprocess.check_output(
        ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1", *args],
        cwd=HERE,
        text=True,
    ).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = dict(status="FAIL_PRESERVED", arms={})
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 << 20, 32 << 20))
        require(
            not git("status", "--porcelain")
            and sha((HERE / "protocol.md").read_bytes()) == PROTOCOL,
            "unfrozen tree or protocol",
        )
        receipt.update(
            commit=git("rev-parse", "HEAD"),
            tree=git("rev-parse", "HEAD^{tree}"),
            program_sha256=sha(Path(__file__).read_bytes()),
            protocol_sha256=PROTOCOL,
            manifest_sha256=c294.MANIFEST_SHA,
        )
        blob = c294.MANIFEST.read_bytes()
        require(sha(blob) == c294.MANIFEST_SHA, "manifest identity")
        entries = {v["path"].split("/raw/")[1]: v for v in json.loads(blob)["files"]}
        for name in c294.NAMES:
            receipt["arms"][name] = arm(args.raw_dir, entries, name)
        passes = all(v["passes"] for a in receipt["arms"].values() for v in a["gate"].values())
        receipt["status"] = "GO_TO_REMAP_ACCOUNTING" if passes else "NO_GO_DECODE_TIER_LRU"
    except FileNotFoundError as exc:
        receipt.update(status="NOT_RUN_RAW_REQUIRED", error=Path(exc.filename).name)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        receipt["error"] = str(exc)
    (args.new_output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return int("error" in receipt)


if __name__ == "__main__":
    raise SystemExit(main())

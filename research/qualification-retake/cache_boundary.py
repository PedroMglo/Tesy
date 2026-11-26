"""Reconstruct C294 end-of-prefill residents from the drained prefix and native events."""

import argparse
import hashlib
import io
import json
import signal
from collections import Counter
from pathlib import Path

CAMPAIGN = "c294-feature-ready-service-window-20261006"
MANIFEST = Path(__file__).resolve().parents[2] / "results" / CAMPAIGN / "raw-manifest.json"
MANIFEST_SHA = "5a689ed0c3e7e328973a12de229c3a6ff4e151c14d568d49e517ff7dee98fd84"
NAMES = [f"c294-{case}-{rep}-on" for case in ("nominal153", "code153") for rep in (2, 3)]
HEADER = "kind us call route layer expert slot gen component bytes rows"
FIELDS = ["slot_expert", "slot_generation", "slot_state", "slot_claimed"]


def require(check, reason):
    if not check:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def slots(snap):
    require(snap["pending_queue"] == 0, "anchor queue is not drained")
    rows = sorted(snap["layers"], key=lambda row: row["layer"])
    require([row["layer"] for row in rows] == list(range(36)), "incomplete layer anchors")
    pools = [list(zip(*(row[key] for key in FIELDS), strict=True)) for row in rows]
    for pool in pools:
        require(len(pool) == 40, "incomplete physical pool")
        residents = []
        for expert, gen, state, claimed in pool:
            require(gen >= 0 and claimed == 0, "incomplete anchor generation")
            require(
                (state == 0 and expert == -1) or (state == 2 and 0 <= expert < 128),
                "anchor slot unavailable",
            )
            if state == 2:
                residents.append(expert)
        require(len(residents) == len(set(residents)), "duplicate anchored expert")
    return pools


def replay(initial, result, lines):
    current = slots(initial)
    require(result["initial"] == initial and result["trace"] is True, "initial anchor mismatch")
    require(next(lines).strip() == HEADER, "invalid event header")
    counts = Counter()
    active = {}
    at_end, resident_sets, boundary_sha = None, None, None
    cuts = []
    for line in lines:
        kind, _us, call, _route, layer, expert, slot, gen, component, size, _rows = map(
            int, line.split()
        )
        counts["events"] += 1
        if (kind, call) in [(16, 0), (15, 1)]:
            cuts.append((kind, call))
            states = Counter(entry[2] for pool in current for entry in pool)
            require(not active and set(states) <= {0, 2}, "work remains across prefill boundary")
            fingerprint = digest(current)
            if kind == 16:
                boundary_sha = fingerprint
                at_end = states
                resident_sets = [{e for e, _, state, _ in pool if state == 2} for pool in current]
            else:
                require(fingerprint == boundary_sha, "state changed before first decode")
        if kind not in range(3, 11):
            continue
        require(0 <= layer < 36 and 0 <= expert < 128, "invalid layer or expert")
        prefix = "prefill" if call == 0 else "decode"
        pool = current[layer]
        if kind == 3:
            present = [i for i, value in enumerate(pool) if value[0] == expert]
            if slot == -1:
                require(not present and size == gen == 0, "miss disagrees with slot map")
                counts[prefix + "_miss"] += 1
            else:
                require(
                    present == [slot] and pool[slot][:3] == (expert, gen, size),
                    "select disagrees with slot map",
                )
                counts[prefix + "_hit"] += 1
            continue
        require(0 <= slot < 40, "invalid destination")
        old, key = pool[slot], (layer, slot)
        if kind == 4:
            if gen == old[1]:
                require(old[:3] == (expert, gen, 1), "invalid same-generation promotion")
                counts[prefix + "_promotions"] += 1
            else:
                require(
                    gen == old[1] + 1 and old[2] in (0, 2) and old[3] == 0,
                    "invalid victim state or generation jump",
                )
                require(all(entry[0] != expert for entry in pool), "duplicate reserved expert")
                counts[prefix + "_new"] += 1
                counts[prefix + "_evictions"] += old[2] == 2
                pool[slot] = (expert, gen, 1, 0)
        elif kind == 5:
            require(old == (expert, gen, 1, 0) and key not in active, "invalid dequeue")
            pool[slot] = (expert, gen, 1, 1)
            active[key] = 0
        elif 6 <= kind <= 9:
            index = active.get(key, -1)
            require(
                old == (expert, gen, 1, 1)
                and 0 <= index < 12
                and kind == 6 + index % 4
                and component == index // 4
                and size == 4_406_400,
                "incomplete or misplaced component read/copy",
            )
            active[key] += 1
        else:
            require(old == (expert, gen, 1, 1) and active.pop(key, -1) == 12, "invalid publication")
            pool[slot] = (expert, gen, 2, 0)
            counts[prefix + "_publications"] += 1
    require(
        cuts == [(16, 0), (15, 1)] and counts["events"] == result["trace_events"],
        "missing or repeated event boundary",
    )
    require(not active and current == slots(result["final"]), "mismatch at final drained anchor")
    require(
        counts["decode_hit"] + counts["decode_miss"] == 32 * 36 * 4, "incomplete decode selects"
    )
    return resident_sets, {
        "boundary_slot_vector_sha256": boundary_sha,
        "empty_slots": at_end[0],
        "resident_slots": at_end[2],
        "loading_slots": 0,
        "claimed_slots": 0,
        "final_physical_slots_verified": 1440,
        "counts": dict(counts),
    }


def audit_arm(raw, name):
    name = name.removesuffix(".native")
    require(name in NAMES, "unsupported C294 arm")
    data = MANIFEST.read_bytes()
    require(hashlib.sha256(data).hexdigest() == MANIFEST_SHA, "C294 manifest mismatch")
    entries = {item["path"]: item for item in json.loads(data)["files"]}
    source, hashes = {}, {}
    for filename in ["initial.json", "events.tsv", "result.json"]:
        relative = Path(name + ".native") / filename
        entry = entries[(Path("results") / CAMPAIGN / "raw" / relative).as_posix()]
        blob = (Path(raw) / relative).read_bytes()
        hashes[filename] = hashlib.sha256(blob).hexdigest()
        require(
            len(blob) == entry["bytes"] and hashes[filename] == entry["sha256"],
            "raw identity mismatch",
        )
        source[filename] = (
            io.StringIO(blob.decode()) if filename == "events.tsv" else json.loads(blob)
        )
    residents, facts = replay(source["initial.json"], source["result.json"], source["events.tsv"])
    return residents, dict(facts, source_sha256=hashes)


def boundary(raw, name):
    """Return 36 validated sets of local expert IDs (0..127), indexed by layer."""
    return audit_arm(raw, name)[0]


def deadline(_signal, _frame):
    raise TimeoutError("C294 boundary budget expired")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.new_output_dir.resolve().is_relative_to(args.raw_dir.resolve()):
        parser.error("select an output directory outside C294 raws")
    args.new_output_dir.mkdir()
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(60)
    try:
        arms = {name: audit_arm(args.raw_dir, name)[1] for name in NAMES}
        result = {
            "status": "REPRODUZIDO_TRACE_DERIVED",
            "manifest_sha256": MANIFEST_SHA,
            "arms": arms,
        }
    except FileNotFoundError:
        result = {"status": "NOT_RUN_RAW_REQUIRED"}
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        result = {"status": "FAIL", "reason": type(exc).__name__}
    finally:
        signal.alarm(0)
    pending = args.new_output_dir / ".pending"
    with pending.open("x") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    pending.replace(args.new_output_dir / "receipt.json")
    print(result["status"])
    return int(result["status"] != "REPRODUZIDO_TRACE_DERIVED")


if __name__ == "__main__":
    raise SystemExit(main())

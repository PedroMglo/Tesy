"""Two free-start Belady bounds using the observed C294 prefix reservation bitmap."""

import argparse
import hashlib
import json
import signal
from pathlib import Path

import cache_bound as model
from cache_boundary import NAMES, audit_arm

FROZEN = "99a5e368cbaacdf459ce6078fc16ac733a63d0f19904a1dc365bd80773469331"


def floor(groups, eligible):
    streams = [groups[layer::36] for layer in range(36)]
    loads = sum(model.minimum(stream, 40, eligible_initial=eligible) for stream in streams)
    absent = len(set().union(*groups) - eligible)
    if not absent <= loads:
        raise ValueError("compulsory-miss lower bound violated")
    payload = loads * model.EXPERT_BYTES
    wall = 8 * payload / model.LINK_BPS
    return {
        "eligible_layer_experts": len(eligible),
        "distinct_decode_ids_outside_eligible": absent,
        "minimum_decode_loads": loads,
        "encoded_payload_bytes": payload,
        "integer_load_headroom": model.MAX_LOADS - loads,
        "ideal_service_s": wall,
        "signed_time_headroom_s": model.STEPS / model.RATE - wall,
        "decision": "NO_GO" if loads > model.MAX_LOADS else "INCONCLUSIVE_CAUSAL_SELECTION",
    }


def arm(raw, name, entries):
    # This check covers sizes, all three digests, and actual ordered reservation/publication events.
    boundary, verified = audit_arm(raw, name)
    folder = Path(name + ".native")
    initial_path, events_path = folder / "initial.json", folder / "events.tsv"

    def data(path):
        blob = (raw / path).read_bytes()
        if hashlib.sha256(blob).hexdigest() != verified["source_sha256"][path.name]:
            raise ValueError("evidence changed since boundary reconstruction")
        return blob

    init = json.loads(data(initial_path))
    seen = set()
    for layer in init["layers"]:
        i = layer["layer"]
        flags = layer["seen"]
        if len(flags) != 128 or any(type(flag) is not int or flag not in (0, 1) for flag in flags):
            raise ValueError("incomplete historical reservation bitmap")
        seen.update(i * 128 + e for e, flag in enumerate(flags) if flag)
    published = []
    for row in data(events_path).splitlines()[1:]:
        kind, _, call, _, layer, expert, *_ = row.split()
        if kind == b"10" and call == b"0":
            published.append(int(layer) * 128 + int(expert))
    both = seen.union(published)
    real = {layer * 128 + e for layer, ids in enumerate(boundary) for e in ids}
    if not real <= both or len(published) != verified["counts"]["prefill_publications"]:
        raise ValueError("eligibility disagrees with validated boundary")
    key = Path("results") / model.CAMPAIGN / "raw" / events_path
    groups, observed = model.read_arm(raw / events_path, entries[key.as_posix()])
    a, b = floor(groups, seen), floor(groups, both)
    if (
        b["minimum_decode_loads"] > a["minimum_decode_loads"]
        or b["minimum_decode_loads"] > observed
    ):
        raise ValueError("larger eligible set or R0 conservation failed")
    return {
        "source_sha256": verified["source_sha256"],
        "prefill_publications": len(published),
        "distinct_prefill_publications": len(set(published)),
        "new_eligible_from_prefill_publications": len(both - seen),
        "prefix_seen": a,
        "prefix_seen_or_prefill_published": b,
    }


def audit(raw):
    if (
        hashlib.sha256(Path(__file__).with_name("prefix_seen_protocol.md").read_bytes()).hexdigest()
        != FROZEN
    ):
        raise ValueError("changed screen protocol")
    data = model.MANIFEST.read_bytes()
    if hashlib.sha256(data).hexdigest() != model.MANIFEST_SHA:
        raise ValueError("changed C294 manifest")
    entries = {entry["path"]: entry for entry in json.loads(data)["files"]}
    return {
        "status": "TRACE_DERIVED_FORMAL_BOUND",
        "raw_manifest_sha256": model.MANIFEST_SHA,
        "screen_protocol_sha256": FROZEN,
        "expert_bytes": model.EXPERT_BYTES,
        "link_bits_per_s": model.LINK_BPS,
        "decode_tokens": model.STEPS,
        "target_tok_s": model.RATE,
        "maximum_integer_loads": model.MAX_LOADS,
        "arms": {name: arm(raw, name, entries) for name in NAMES},
    }


def deadline(_signum, _frame):
    raise TimeoutError("C294 prefix-seen budget expired")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.new_output_dir.resolve().is_relative_to(args.raw_dir.resolve()):
        parser.error("select an output root outside the raw evidence")
    args.new_output_dir.mkdir()
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(60)
    try:
        result = audit(args.raw_dir)
    except FileNotFoundError:
        result = {"status": "NOT_RUN_RAW_REQUIRED"}
    except (ValueError, KeyError, OSError) as e:
        result = {"status": "FAIL", "exception_type": type(e).__name__}
    finally:
        signal.alarm(0)
    pending = args.new_output_dir / ".pending"
    with pending.open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    pending.replace(args.new_output_dir / "receipt.json")
    print(result["status"])
    return int(result["status"] != "TRACE_DERIVED_FORMAL_BOUND")


if __name__ == "__main__":
    raise SystemExit(main())

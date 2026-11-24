"""Apply the routed payload bound starting at the reconstructed R0 decode boundary."""

import argparse
import hashlib
import json
from pathlib import Path

import cache_bound as model
from cache_boundary import boundary, slots


def prefill_inventory(raw, name, entries, groups, finite):
    def verified(filename):
        key = Path(name) / filename
        content = (raw / key).read_bytes()
        expected = entries[str(Path("results") / model.CAMPAIGN / "raw" / key)]
        if (
            len(content) != expected["bytes"]
            or hashlib.sha256(content).hexdigest() != expected["sha256"]
        ):
            raise ValueError("prefill input mismatch")
        return content

    before = slots(json.loads(verified("initial.json")))
    prefix = {
        layer * 128 + expert
        for layer, pool in enumerate(before)
        for expert, _, state, _ in pool
        if state == 2
    }
    issued = []
    for row in verified("events.tsv").splitlines()[1:]:
        kind, _, call, _, layer, expert, *_ = row.split()
        if call == b"0" and kind == b"10":
            issued.append(int(layer) * 128 + int(expert))
    seen = prefix.union(issued)
    missing = len(set().union(*groups) - seen)
    summary = {
        "prefix_residents": len(prefix),
        "prefill_publications": len(issued),
        "prefix_or_prefill_distinct_available": len(seen),
        "decode_distinct_unseen": missing,
        "additional_identities_needed_before_decode": max(0, missing - model.MAX_LOADS),
    }

    if finite:
        layer_sets = [set().union(*groups[layer::36]) for layer in range(36)]
        summary["distinct_lower_bound_with_40_initial_per_layer"] = sum(
            len(keys) - min(40, len(keys & seen)) for keys in layer_sets
        )
        summary["minimum_uniform40_from_seen"] = sum(
            model.minimum(groups[layer::36], 40, eligible_initial=seen) for layer in range(36)
        )
        summary["minimum_pooled1440_from_seen"] = model.minimum(groups, 1440, eligible_initial=seen)
    return summary


def compare(raw, include_prefill=False, finite=False):
    manifest = model.MANIFEST.read_bytes()
    if hashlib.sha256(manifest).hexdigest() != model.MANIFEST_SHA:
        raise ValueError("manifest mismatch")
    entries = {entry["path"]: entry for entry in json.loads(manifest)["files"]}
    result = {}
    for case in ("nominal153", "code153"):
        for repeat in (2, 3):
            name = f"c294-{case}-{repeat}-on.native"
            rel = Path(name) / "events.tsv"
            entry = entries[str(Path("results") / model.CAMPAIGN / "raw" / rel)]
            groups, observed = model.read_arm(raw / rel, entry)
            residents = boundary(raw, name)
            if len(residents) != 36 or any(
                len(ids) > 40 or not set(ids).issubset(range(128)) for ids in residents
            ):
                raise ValueError("invalid boundary shape")
            initial = [{128 * layer + i for i in ids} for layer, ids in enumerate(residents)]
            flat = set.union(*initial)
            compulsory = len(set().union(*groups) - flat)
            fixed = sum(model.minimum(groups[layer::36], 40, initial[layer]) for layer in range(36))
            shared = model.minimum(groups, 1440, flat)
            # A shared full pool can reproduce every layer-private victim policy.
            if not compulsory <= shared <= fixed <= observed:
                raise ValueError("derived bounds inconsistent with the observed run")
            result[name] = {
                "observed_loads": observed,
                "initial_residents": len(flat),
                "distinct_demands": len(set().union(*groups)),
                "distinct_absent_at_entry": compulsory,
                "minimum_uniform40": fixed,
                "minimum_pooled1440": shared,
                "min_otherwise_served_loads_even_with_unlimited_retention": max(
                    0, compulsory - model.MAX_LOADS
                ),
            }
            if include_prefill:
                result[name]["prefill_unlimited_retention"] = prefill_inventory(
                    raw, name, entries, groups, finite
                )
    return {
        "evidence": "FORMAL_CONDITIONAL_ON_C294_DECODE_ENTRY",
        "six_steps_per_second_budget_loads": model.MAX_LOADS,
        "payload_per_load": model.EXPERT_BYTES,
        "arms": result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    parser.add_argument("--include-prefill", action="store_true")
    parser.add_argument("--finite-prefill", action="store_true")
    args = parser.parse_args()
    if args.finite_prefill and not args.include_prefill:
        parser.error("--finite-prefill requires --include-prefill")
    args.new_output_dir.mkdir()
    try:
        result = compare(args.raw_dir, args.include_prefill, args.finite_prefill)
    except FileNotFoundError:
        result = {"status": "NOT_RUN_RAW_REQUIRED"}
    except (ValueError, KeyError, OSError) as exc:
        result = {"status": "FAIL", "type": type(exc).__name__, "reason": str(exc)}
    pending = args.new_output_dir / ".pending"
    pending.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    pending.replace(args.new_output_dir / "receipt.json")
    return int("arms" not in result)


if __name__ == "__main__":
    raise SystemExit(main())

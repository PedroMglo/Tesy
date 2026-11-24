"""Symbolic restoration at a drained cut, charged per layer and payload tier."""

from collections import Counter

BYTES = 13_219_200
STATIC = ("layer", "n_slots", "n_expert", "plan_capacity", "component_count", "components")


def need(test, message):
    if not test:
        raise ValueError(message)


def inspect_layer(sl):
    n = sl["n_slots"]
    experts = list(sl["slot_expert"])
    state = sl["slot_state"]
    need(len(experts) == len(state) == len(sl["slot_claimed"]) == n, "slot vector length")
    need(not any(sl["slot_claimed"]), "claimed slot at restore")
    valid = {x: slot for slot, x in enumerate(experts) if x != -1}
    need(len(valid) == sum(x >= 0 for x in experts), "duplicated resident")
    need(
        all(
            (x == -1 and st == 0) or (0 <= x < sl["n_expert"] and st == 2)
            for x, st in zip(experts, state, strict=True)
        ),
        "nonidle or invalid slot",
    )
    need(
        sl["expert_slot"] == [valid.get(x, -1) for x in range(sl["n_expert"])],
        "resident inverse differs",
    )
    return experts, valid


def execute(initial, target, *, scratch):
    """Settle paths before refilling absences. An empty destination requires only invalidation."""
    physical = list(initial)
    owners = {x: slot for slot, x in enumerate(initial) if x >= 0}
    preds = {dest: owners[x] for dest, x in enumerate(target) if x in owners and owners[x] != dest}
    missing = [dest for dest, x in enumerate(target) if x >= 0 and x not in owners]
    reads = copies = cycles = 0

    def move(src, dest):
        nonlocal copies
        need(physical[src] == target[dest], "loss of resident source during copy")
        physical[dest] = physical[src]
        copies += 1

    while endpoints := (preds.keys() - set(preds.values())):
        for dest in sorted(endpoints):
            move(preds.pop(dest), dest)

    # A slot still awaiting its GGUF load, or finally EMPTY, is safe scratch
    # after all paths have consumed the old values. Otherwise allocate once per tier.
    spare = next((s for s, x in enumerate(target) if x < 0 or s in missing), None)
    extra_workspace = 0
    while preds:
        cycles += 1
        first = dest = min(preds)
        saved = None
        if scratch:
            if spare is None:
                extra_workspace = BYTES
                saved = physical[first]
            else:
                physical[spare] = physical[first]
            copies += 1
        while (src := preds.pop(dest)) != first:
            move(src, dest)
            dest = src
        if scratch:
            physical[dest] = saved if spare is None else physical[spare]
            copies += 1
        else:
            physical[dest] = target[dest]
            reads += 1  # Isolated cycle, forbidding use of any slot as intermediate scratch.
        need(physical[dest] == target[dest], "cycle closed with wrong expert")
    for dest in missing:
        physical[dest] = target[dest]
        reads += 1
    for dest, x in enumerate(target):
        if x < 0:
            physical[dest] = -1  # Invalidate metadata; bytes in an empty slot are unobservable.
    need(physical == target, "restoration failed")
    return {
        "gguf_loads": reads,
        "local_copies": copies,
        "cycles": cycles,
        "gguf_read_payload_bytes": reads * BYTES,
        "local_copy_payload_bytes": copies * BYTES,
        "local_copy_read_plus_write_bytes": 2 * copies * BYTES,
        "gguf_destination_write_payload_bytes": reads * BYTES,
        "extra_scratch_peak_bytes": extra_workspace,
    }


def restore_layers(candidate_layers, target_layers):
    """Compute two constructive plans. Manager quiescence and snapshot identity are caller gates."""
    tiers = {}
    need(len(candidate_layers) == len(target_layers) == 36, "expected 36 layers")
    for layer, (sl, ref) in enumerate(zip(candidate_layers, target_layers, strict=True)):
        need(set(sl) == set(ref) and all(sl[f] == ref[f] for f in STATIC), "different layer layout")
        tier = "CPU" if layer < 25 else "CUDA0"
        need(
            sl["layer"] == layer
            and sl["n_slots"] == 44
            and sl["n_expert"] == 128
            and len(sl["components"]) == sl["component_count"] == 3
            and all(
                c["expert_bytes"] == BYTES // 3 and c["device"] == tier for c in sl["components"]
            ),
            "unexpected source geometry or tier",
        )
        initial, owners = inspect_layer(sl)
        target, _ = inspect_layer(ref)
        t = tiers.setdefault(
            tier,
            {
                "missing_experts": 0,
                "moved_resident_experts": 0,
                "different_payload_slots": 0,
                "cycles": 0,
                "metadata_differences": Counter(),
                "no_scratch": Counter(),
                "local_scratch": Counter(),
            },
        )
        t["missing_experts"] += sum(x >= 0 and x not in owners for x in target)
        t["moved_resident_experts"] += sum(
            x in owners and owners[x] != i for i, x in enumerate(target)
        )
        t["different_payload_slots"] += sum(x != y for x, y in zip(initial, target, strict=True))
        for f in sl.keys() - set(STATIC):
            a, b = sl[f], ref[f]
            if a == b:
                continue
            if isinstance(a, list):
                common = min(len(a), len(b))
                delta = sum(a[i] != b[i] for i in range(common)) + abs(len(a) - len(b))
            else:
                delta = 1
            t["metadata_differences"][f] += delta
        for key, scratch in (("no_scratch", False), ("local_scratch", True)):
            plan = execute(initial, target, scratch=scratch)
            if not scratch:
                t["cycles"] += plan["cycles"]
            for metric, value in plan.items():
                if metric == "extra_scratch_peak_bytes":
                    t[key][metric] = max(t[key][metric], value)
                else:
                    t[key][metric] += value
    for t in tiers.values():
        for field in ("no_scratch", "local_scratch", "metadata_differences"):
            t[field] = dict(sorted(t[field].items()))
    return tiers

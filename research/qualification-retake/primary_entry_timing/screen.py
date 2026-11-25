"""Minimum pre-decode primary placement for fixed service on the C294 cases."""

import argparse
import hashlib
import json
import resource
import subprocess
import sys
from collections import Counter
from pathlib import Path

from solver import solve

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path.insert(0, str(UNIT))
from l2_warm_critical import screen as warm  # noqa: E402
from primary_backing import screen as backing  # noqa: E402

require = backing.require
BOUND = "44ba456b19a1d4fcd44ecb7127a99db410344e304a4e51474d41dec1847fc9f5"
PROTOCOL = "aed00dce6a9f817a07b713521a3e91cf03d958d0f9c4ed519b63603118f5d65b"
EXPERT = 13_219_200
SCALES = [("1", 1, 1), ("0.8", 4, 5)]


def donors(entry, demanded):
    """Vacant + occupied positions whose original payload has no decode consumer."""
    require(len(entry) == len(demanded), "layers")
    rows = []
    for layer, (old, used) in enumerate(zip(entry, demanded, strict=True)):
        require(len(old) <= 40, "bad cache geometry")
        empty = 40 - len(old)
        unused = sorted(old - used)
        rows.append(
            dict(layer=layer, empty=empty, unused_residents=unused, cap=empty + len(unused))
        )
    return rows


def collect(rows, entry):
    _, ranks, components = backing.markers(rows)
    data = backing.c295.extract(rows)
    seen = [set(pool) for pool in entry]
    wanted = [set() for _ in entry]
    groups = []
    witness = []
    for i, g in enumerate(data[1]):
        call, layer = g["call"], g["layer"]
        require((call - 1, layer) == divmod(i, 36), "route order")
        req = [e for e, _ in ranks.pop((call, layer))]
        first = set(req) - seen[layer]
        work = {}
        for w in g["need"]:
            require(w[0] == layer and data[0][w]["owner"] == call, "foreign generation")
            spans = components.pop(w)
            if w[1] in first:
                durations = [spans[c, 7] - spans[c, 6] for c in range(3)]
                require(min(durations) >= 0 and sum(durations) == data[0][w]["read"], "READ link")
                require(w[1] not in work, "duplicate first generation")
                work[w[1]] = sum(max(0, t - 1) for t in durations)
        require(first == set(work), "first missing generation")
        seen[layer].update(req)
        wanted[layer].update(req)
        witness.append((call, layer, req))
        groups.append((layer, work))
    require(len(groups) == 1152 and not components and not ranks, "route/READ coverage")
    return groups, donors(entry, wanted), witness


def origin(key, published, resident, prefix):
    if key in published:
        return "increment_publication"
    if key in resident:
        return "resident_P"
    if key in prefix:
        return "prefix_routed_only"
    return "unproven"


def check_solution(solution, groups, caps, eligible, origins, fixed, num, den):
    chosen = set(solution["chosen"])
    require(
        chosen <= eligible and len(chosen) == solution["k"] == len(solution["chosen"]),
        "witness identity",
    )
    counts = Counter(layer for layer, _ in chosen)
    require(all(counts[layer] <= cap for layer, cap in enumerate(caps)), "witness capacity")
    by_tier = {"CPU": Counter(), "CUDA": Counter()}
    for layer, row in groups:
        tier = by_tier["CPU" if layer < 25 else "CUDA"]
        tier["base_read_us"] += max(row.values(), default=0)
        tier["remaining_read_us"] += max(
            (dt for e, dt in row.items() if (layer, e) not in chosen), default=0
        )
    for k in chosen:
        tier = by_tier["CPU" if k[0] < 25 else "CUDA"]
        tier["slots"] += 1
        tier["capacity_bytes"] += EXPERT
        tier["bytes_to_deliver_if_materialized"] += EXPERT
        tier[origins[k]] += 1
    base = sum(t["base_read_us"] for t in by_tier.values())
    rest = sum(t["remaining_read_us"] for t in by_tier.values())
    require(rest == solution["remaining_us"], "witness service")
    gate = backing.score(rest, fixed, num, den)
    require(solution["reaches"] == (not gate["excludes"]), "reach gate")
    prev = solution["k_minus_one_remaining_us"]
    if solution["k"]:
        require(
            rest < prev <= base and backing.score(prev, fixed, num, den)["excludes"],
            "k-1 certificate",
        )
    else:
        require(prev is None and rest == base, "empty witness")
    return dict(
        **solution,
        by_tier=by_tier,
        per_layer_slots_used=[counts[layer] for layer in range(36)],
        choice_origin={
            label: sum(origins[k] == label for k in chosen)
            for label in ("increment_publication", "resident_P", "prefix_routed_only", "unproven")
        },
        capacity_bytes=len(chosen) * EXPERT,
        bytes_to_deliver_if_materialized=len(chosen) * EXPERT,
        gain_wall_s=(base - rest) * num / (den * 1e6),
        removed_read_fraction=(base - rest) / base,
        seconds=gate["seconds"],
        slack_seconds=-gate["excess_seconds"],
        k_minus_one_seconds=backing.score(prev, fixed, num, den)["seconds"]
        if prev is not None
        else None,
    )


def arm(raw, name, off, prefix, expected, controls):
    paid, fixed_old, all_reads = controls
    control = backing.arm(raw, name, paid[name + ".native"], fixed_old[name], all_reads[name])
    require(
        control == expected and control["charged_fixed_us"] == control["original_fixed_us"],
        "sealed control or overlap",
    )
    entry, proof = backing.boundary.audit_arm(raw, name)
    require(
        proof["boundary_slot_vector_sha256"] == off["I_sha256"] == control["anchor_sha256"],
        "I identity",
    )
    root = raw / (name + ".native")
    h = proof["source_sha256"]
    original = json.loads(backing.pinned(root / "initial.json", h["initial.json"]))
    result = json.loads(backing.pinned(root / "result.json", h["result.json"]))
    require(
        warm.state(original) == off["P_sha256"] and warm.state(result["final"]) == off["F_sha256"],
        "P/F drift",
    )
    rows = backing.c295.events(root / "events.tsv", True)
    backing.pinned(root / "events.tsv", h["events.tsv"])
    groups, slots, ranks = collect(rows, entry)
    case = name.split("-")[1]
    require(
        backing.check_witness(
            case, ((c, layer, backing.PROMPT[case] + c - 1, ids) for c, layer, ids in ranks)
        )
        == control["ranks_sha256"]
        == off["decode_sha256"],
        "decode ranks",
    )
    all_keys = {(layer, e) for layer, row in groups for e in row}
    control_total = control["total"]
    require(
        sum(len(row) for _, row in groups) == len(all_keys) == control_total["required"],
        "first use",
    )
    require(
        sum(max(row.values(), default=0) for _, row in groups)
        == control_total["required_read_floor_us"],
        "k=0",
    )
    require(sum(s["empty"] for s in slots) == proof["empty_slots"] == 29, "I vacancies")
    published = {(r["layer"], r["expert"]) for r in rows if r["call"] == 0 and r["kind"] == 10}
    resident = {
        (layer, e)
        for layer, pool in enumerate(backing.boundary.slots(original))
        for e, _, s, _ in pool
        if s == 2
    }
    sources = {k: origin(k, published, resident, prefix) for k in all_keys}
    elig = all_keys.intersection(published | resident | prefix)
    strict = all_keys.intersection(published | resident)
    caps = [s["cap"] for s in slots]
    universes = {}
    for label, allowed, capacity in (
        ("unrestricted", all_keys, [128] * 36),
        ("same_layer_preI", elig, caps),
        ("P_or_increment_only", strict, caps),
    ):
        scales = {}
        for scale, n, d in SCALES:
            fixed = control["charged_fixed_us"]
            chosen = solve(groups, capacity, allowed, fixed, n, d)
            scales[scale] = check_solution(chosen, groups, capacity, allowed, sources, fixed, n, d)
        universes[label] = dict(eligible_keys=len(allowed), scales=scales)
    for label in ("same_layer_preI", "P_or_increment_only"):
        for s, _, _ in SCALES:
            item = universes[label]["scales"][s]
            more = universes["unrestricted" if label == "same_layer_preI" else "same_layer_preI"][
                "scales"
            ][s]
            require(
                not item["reaches"] or (more["reaches"] and item["k"] >= more["k"]),
                "nested feasible sets",
            )
    return dict(
        compulsory=len(all_keys),
        read_floor_us=control_total["required_read_floor_us"],
        fixed_us=control["charged_fixed_us"],
        raw_sha256=h,
        wrt_sha256=off["native_sha256"]["routed-witness.bin"],
        entry_sha256=off["I_sha256"],
        donor_capacity=sum(caps),
        positions=slots,
        universes=universes,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--family", type=Path, required=True)
    ap.add_argument("--raw-dir", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    require(
        all(
            not a.new_output_dir.resolve().is_relative_to(p.resolve())
            for p in (a.raw_dir, a.family)
        ),
        "protect inputs",
    )
    a.new_output_dir.mkdir(mode=0o700)
    report = {"status": "FAIL_PRESERVED", "arms": {}}
    try:
        for key, cap in (
            (resource.RLIMIT_CPU, 120),
            (resource.RLIMIT_AS, 512 << 20),
            (resource.RLIMIT_FSIZE, 8 << 20),
        ):
            soft, hard = resource.getrlimit(key)
            resource.setrlimit(key, (min(x for x in (soft, hard, cap) if x >= 0), hard))
        git = warm.p.git
        require(
            not git(
                HERE,
                "-c",
                "core.preloadIndex=false",
                "-c",
                "index.threads=1",
                "status",
                "--porcelain",
            ),
            "dirty tree",
        )
        report.update(
            commit=git(HERE, "rev-parse", "HEAD"),
            tree=git(HERE, "rev-parse", "HEAD^{tree}"),
            protocol_sha256=PROTOCOL,
            program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            solver_sha256=hashlib.sha256((HERE / "solver.py").read_bytes()).hexdigest(),
            primary_backing_receipt_sha256=BOUND,
            family_sha256=warm.p.FAMILY_SHA,
        )
        backing.pinned(HERE / "protocol.md", PROTOCOL)
        backing.pinned(Path(backing.c295.__file__), backing.critical.C295)
        baseline = json.loads(backing.pinned(UNIT / "primary_backing/evidence/receipt.json", BOUND))
        backing.pinned(Path(backing.__file__), baseline["source_sha256"])
        controls = [
            json.loads(backing.pinned(UNIT / path, sha))["arms"]
            for path, sha in backing.PINS.items()
        ]
        family = warm.p.family_inputs(a.family, warm.p.FAMILY_SHA)
        for case in ("nominal153", "code153"):
            keys, off = warm.wrt(a.family, case, family)
            for rep in (2, 3):
                name = f"c294-{case}-{rep}-on"
                report["arms"][name] = arm(
                    a.raw_dir, name, off, keys, baseline["arms"][name], controls
                )
        for scale, _, _ in SCALES:
            results = [
                r["universes"]["same_layer_preI"]["scales"][scale]["reaches"]
                for r in report["arms"].values()
            ]
            report.setdefault("scope_decisions", {})[scale] = (
                "GO_CAUSAL_SELECTION_FIXTURE_ONLY"
                if all(results)
                else "NO_GO_RESTRICTED_IN_FAILING_ARMS"
            )
        report["status"] = "PASS_OPTIMISTIC_ENTRY_SCREEN"
    except FileNotFoundError as exc:
        report.update(status="NOT_RUN_RAW_REQUIRED", error=Path(exc.filename).name)
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        MemoryError,
        subprocess.CalledProcessError,
    ) as exc:
        report["error"] = str(exc) or type(exc).__name__
    tmp = a.new_output_dir / ".pending"
    with tmp.open("x") as f:
        json.dump(report, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(report["status"])
    return int("error" in report)


if __name__ == "__main__":
    raise SystemExit(main())

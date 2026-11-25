"""Reconcile the two C269 service processes without opening weights or a GPU."""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
RAM = HERE.parent / "t1_primary_layout"
prev = run_path(str(RAM / "review.py"))
bench = run_path(str(RAM / "bench.py"))
need, digest, ORDER, STRATA = (prev[k] for k in ("need", "digest", "ORDER", "STRATA"))
SLAB, WIDTH, WINDOW = (bench[k] for k in ("WEIGHT", "WIDTH", "WINDOW"))
sys.path.insert(0, str(HERE.parents[4] / "tools"))
import c118_start_inventory as c118  # noqa: E402

BASE_SHA = "2a90de37b6ae809e9de63cd47ddabac192e743a2c44b037a0f472aa626d208bb"
MAP_SHA = "7e9d0efb4c9bac6ef88d0de0003e8643fc14f4f9942c72a8101e2c166b8b1729"
MIB = 1 << 20
PAIRS = {
    "layout_on_new": "CD",
    "policy_on_pack": "BD",
    "combined": "AD",
    "layout_only": "AB",
    "policy_only": "AC",
}


def read(path, expected):
    need(digest(path) == expected, f"hash: {path.name}")
    return json.loads(path.read_bytes())


def journal(path, expected):
    need(digest(path) == expected, f"journal hash: {path.name}")
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def plan_costs(plan, seal):
    entries = bench["checked_plan"](plan, seal)
    hashes = set()
    consumers = []
    costs = {cell: {} for cell in "ABCD"}
    for _, entry in entries.values():
        need(len(entry["gguf"]) == 3, "three roles")
        for c in entry["gguf"]:
            need(c["size"] == SLAB and re.fullmatch("[a-f0-9]{64}", c["sha256"]), "component")
            hashes.add(c["sha256"])
    for stratum, sample in plan["samples"].items():
        layer = sample["site"][2]
        tier = "cpu" if layer < 25 else "cuda"
        need(stratum.endswith("_" + tier), "physical tier")
        keys = [(layer, expert) for expert in sample["demand"]]
        consumers.extend(keys)
        for cell in costs:
            policy = "lru_ram" if cell in "AB" else "evict_backed_first"
            layout = "gguf" if cell in "AC" else "pack"
            sources = sample["paths"][policy]
            counts = Counter(sources)
            sealed = seal["sample_counts"][stratum]
            need(
                sealed["consumers"] == len(keys) and counts == sealed["origins"][policy], "origins"
            )
            fd_bytes = 0
            for key, source in zip(keys, sources, strict=True):
                need(source in ("primary", "ram", "disk"), "unknown source")
                record = entries[key][1]
                if source == "disk":
                    fd_bytes += (
                        WINDOW if layout == "pack" else sum(c["count"] for c in record["gguf"])
                    )
            dispatched = counts["disk"] + counts["ram"]
            costs[cell][stratum] = dict(
                policy=policy,
                layout=layout,
                tier=tier,
                served=len(keys),
                dispatched=dispatched,
                disk=counts["disk"],
                ram=counts["ram"],
                primary=counts["primary"],
                read_bytes=fd_bytes,
                fd_calls=counts["disk"] * (3 if layout == "gguf" else 1),
                bank_bytes=counts["ram"] * WIDTH,
                set_bytes=dispatched * WIDTH,
                set_calls=3 * dispatched,
                verified_components=len(keys) * 3,
            )
    need(
        len(hashes) == 87 and len(consumers) == 29 and set(consumers) == entries.keys(),
        "87 addressed roles",
    )
    prep_fd = len(entries) * WINDOW + sum(
        c["count"] for _, e in entries.values() for c in e["gguf"]
    )
    return costs, prep_fd


def paired(clocks):
    """Four complete paired comparisons, with block-level extremes retained untrimmed."""
    effects = {}
    for name, (control, candidate) in PAIRS.items():
        deltas = [b[control] - b[candidate] for b in clocks]
        pct = [100 * d / b[control] for d, b in zip(deltas, clocks, strict=True)]
        effects[name] = dict(
            positive=sum(d > 0 for d in deltas),
            median_ns=median(deltas),
            median_percent=median(pct),
            percent_by_block=pct,
            min_block=1 + pct.index(min(pct)),
            max_block=1 + pct.index(max(pct)),
        )
    return dict(
        block_ns=clocks,
        median_ms={c: median(b[c] for b in clocks) / 1e6 for c in "ABCD"},
        effects=effects,
        interaction_ns=[b["B"] + b["C"] - b["A"] - b["D"] for b in clocks],
    )


def service(rows, r, costs, prep_fd):
    need(
        [(row["block"], row["cell"]) for row in rows]
        == [(n, c) for n, seq in enumerate(ORDER) for c in seq],
        "warm and four complete paired blocks",
    )
    clocks = {k: [{} for _ in ORDER] for k in (*STRATA, "aggregate")}
    components = reads = 0
    native_blocks = [{} for _ in ORDER]
    for row in rows:
        block, cell, waves = row["block"], row["cell"], row["waves"]
        need(set(waves) == set(STRATA), "strata")
        native_blocks[block][cell] = waves
        for k, w in waves.items():
            e = costs[cell][k]
            need(
                set(w)
                == {
                    "tier",
                    "ns",
                    "served",
                    "dispatched",
                    "read_bytes",
                    "set_bytes",
                    "bank_bytes",
                    "verified_components",
                }
                and all(w[field] == e[field] for field in w if field != "ns")
                and type(w["ns"]) is int
                and w["ns"] > 0,
                f"service conservation at {block}/{cell}/{k}",
            )
            clocks[k][block][cell] = w["ns"]
            components += w["verified_components"]
            reads += w["read_bytes"]
        clocks["aggregate"][block][cell] = sum(w["ns"] for w in waves.values())
    contrast = bench["contrast"](native_blocks[1:])
    need(
        contrast == r["contrasts"]
        and reads == r["arm_read_bytes"]
        and components == r["verified_components"] == 1740
        and reads + prep_fd < 8_000_000_000,
        "read/check/clock conservation",
    )
    return dict(
        timing={k: paired(v[1:]) for k, v in clocks.items()},
        warm_ns={k: v[0] for k, v in clocks.items()},
        passes=contrast["passes"],
        service_fd_bytes=reads,
        preparation_fd_bytes=prep_fd,
        verified_components=components,
    )


def buffers(native, static_map):
    need(
        native["map_sha256"] == MAP_SHA and set(native["pools"]) == {"cpu", "cuda"},
        "native map and pools",
    )
    links = {k: v[1] for k, v in static_map["arms"]["C270"]["links"].items()} | static_map[
        "driver_aliases"
    ]
    allowed = {Path(p).name: static_map["files"][p]["sha256"] for p in links.values()}
    loaded = native["loaded_sha256"]
    required = list(static_map["driver_aliases"]) + [
        "libggml-cpu.so.0",
        "libggml-cuda.so.0",
        "libggml-base.so.0",
        "libcudart.so.13",
        "libcublas.so.13",
        "libcublasLt.so.13",
    ]
    need(
        all(Path(links[n]).name in loaded for n in required)
        and all(allowed.get(k) == v for k, v in loaded.items()),
        "loaded providers",
    )
    for k, p in native["pools"].items():
        spans = sorted(p["tensor_ranges"])
        need(
            p["buffer"] == {"cpu": "CPU", "cuda": "CUDA0"}[k]
            and p["weights"] is True
            and p["shape"] == [2880, 2880, 40, 1]
            and p["strides"] == [17, 1530, SLAB, 40 * SLAB]
            and len(spans) == 3
            and all(0 <= a < b <= p["bytes"] and b - a == 40 * SLAB for a, b in spans)
            and all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False)),
            "buffer geometry",
        )


def monitoring(root, r, gate_path):
    gate = read(gate_path, r["c55_sha256"])
    policy = read(gate_path.with_name("resource-policy.json"), gate["canonical_policy_sha256"])
    need(
        gate["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not gate["reason"]
        and gate["selected_stat"] == r["model_stat"],
        "resource gate",
    )
    inv = read(root / "inventory.json", r["inventory_sha256"])
    raw = root / "raw"
    inventory = journal(raw / (r["unit"] + ".start-inventory.jsonl"), inv["sha256"])
    samples = journal(raw / "service-monitor.jsonl", r["monitor_sha256"])
    stamps = [datetime.fromisoformat(s["utc"]) for s in samples]
    power = {"source": "AC", "profile": "performance"}
    kw = dict(policy=policy, cap_bytes=2**31, expected_power=power)
    c118.require_inventory(root, r["unit"], inv, **kw, now=stamps[0])
    gaps = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:], strict=False)]
    need(len(samples) >= 23 and gaps and 0 < min(gaps) and max(gaps) <= 5, "service cadence")
    owners = [s["observation"].get("gpu_owners") for s in samples]
    first_owned = next((i for i, o in enumerate(owners) if o), None)
    need(
        first_owned is not None
        and first_owned > 0
        and len(owners[first_owned]) == 1
        and all(o is None for o in owners[:first_owned])
        and len(owners[first_owned:-1]) >= 21
        and all(o == owners[first_owned] for o in owners[first_owned:-1])
        and owners[-1] in ([], owners[first_owned]),
        "one active GPU owner",
    )
    for s in samples:
        obs = s["observation"]
        c118.validate_sample(obs, **kw)
        need(
            0 < s["peak_bytes"] <= r["peak_bytes"] < 1856 * MIB
            and obs["gpu"]["used_mib"] < 1536
            and obs["gpu"]["bdf"] == policy["gpu"]["bdf"],
            "service footprint",
        )
    need(r["resource_cap"] == 2**31, "scope cap")
    obs = [s["observation"] for s in inventory + samples]
    return dict(
        inventory_sha256=inv["sha256"],
        policy_sha256=inv["policy_sha256"],
        inventory_samples=len(inventory),
        inventory_s=inv["duration_s"],
        service_samples=len(samples),
        service_span_s=(stamps[-1] - stamps[0]).total_seconds(),
        max_service_utc_gap_s=max(gaps),
        gpu_max_mib=max(j["gpu"]["used_mib"] for j in obs),
        gpu_cleanup_mib=obs[-1]["gpu"]["used_mib"],
        gpu_owner_still_at_cleanup=bool(owners[-1]),
        owned_service_samples=sum(bool(o) for o in owners),
        process_peak_bytes=r["peak_bytes"],
        cap_bytes=r["resource_cap"],
        stop_bytes=1856 * MIB,
        min_available_bytes=min(j["mem_available_bytes"] for j in obs),
        cpu_max_c=max(j["thermal"]["cpu_tctl_c"] for j in obs),
        nvme_max_c=max(max(j["thermal"]["nvme_composite_by_sensor"].values()) for j in obs),
        gpu_max_c=max(j["gpu"]["temperature_c"] for j in obs),
        gpu_stop_mib=1536,
    )


def review(a):
    seal = read(RAM / "plan-receipt.json", bench["SEAL"])
    plan = read(a.plan, bench["PLAN"])
    costs, prep_fd = plan_costs(plan, seal)
    baseline = read(a.ram_receipt, BASE_SHA)
    static_map = read(a.map, MAP_SHA)
    arms = []
    raw = []
    for n, (root, gate) in enumerate(
        zip((a.first, a.second), (a.c55, a.second_c55 or a.c55), strict=True), 1
    ):
        root = root.resolve()
        receipt = root / "receipt.json"
        r = json.loads(receipt.read_bytes())
        need(
            r["status"] == "PASS_NATIVE_SINKS"
            and r["arm"] == n
            and r["gpu_transfers"] is True
            and r["transformer_forwards"] == 0
            and r["plan_sha256"] == bench["PLAN"]
            and r["ram_receipt_sha256"] == BASE_SHA
            and baseline["status"] == "PASS_RAM_TRANSPORT"
            and all(
                r[k] == baseline[k]
                for k in (
                    "model_stat",
                    "partial_stat",
                    "partial_sha256",
                    "monitor_provider",
                    "arm_read_bytes",
                )
            )
            and r["first_sha256"] == (None if n == 1 else arms[0]["receipt_sha256"]),
            "process and parent identities",
        )
        buffers(r["native"], static_map)
        s = service(journal(root / "raw/blocks.jsonl", r["block_sha256"]), r, costs, prep_fd)
        mon = monitoring(root, r, gate)
        need(
            min(r["prepare_ns"], r["native_init_ns"], r["fixture_cleanup_ns"]) > 0,
            "fixed fixture costs",
        )
        arms.append(
            dict(
                **s,
                arm=n,
                unit=r["unit"],
                receipt_sha256=digest(receipt),
                block_sha256=r["block_sha256"],
                monitor_sha256=r["monitor_sha256"],
                inventory_receipt_sha256=r["inventory_sha256"],
                c55_sha256=r["c55_sha256"],
                prepare_ns=r["prepare_ns"],
                native_init_ns=r["native_init_ns"],
                fixture_cleanup_ns=r["fixture_cleanup_ns"],
                resources=mon,
            )
        )
        raw.append(r)
    first, second = raw
    passes = [s["passes"] for s in arms]
    need(
        first["unit"] != second["unit"]
        and all(first[k] == second[k] for k in ("commit", "tree", "native"))
        and second["both_processes_pass"] == all(passes),
        "two independent processes",
    )
    pooled = {}
    for k in (*STRATA, "aggregate"):
        pooled[k] = {}
        for effect in PAIRS:
            pct = [
                p for arm in arms for p in arm["timing"][k]["effects"][effect]["percent_by_block"]
            ]
            pooled[k][effect] = dict(
                positive=sum(p > 0 for p in pct), comparisons=len(pct), median_percent=median(pct)
            )
    return dict(
        status=(
            "GO_MANAGER_FIXTURE_ONLY"
            if all(passes)
            else "INCONCLUSIVE"
            if any(passes)
            else "NO_GO_IN_THIS_FIXTURE"
        ),
        arms=arms,
        pooled_descriptive=pooled,
        per_cell_per_stratum=costs,
        native=first["native"],
        monitor_provider=first["monitor_provider"],
        commit=first["commit"],
        tree=first["tree"],
        plan_sha256=bench["PLAN"],
        plan_seal_sha256=bench["SEAL"],
        partial_sha256=first["partial_sha256"],
        ram_receipt_sha256=BASE_SHA,
        distinct_consumer_components=87,
        transformer_forwards=0,
        limits=[
            "Dispatch, source and synchronous SET through drain share one service clock.",
            "Volumes count returned FD bytes and logical RAM and SET payloads. "
            "Physical NVMe and PCIe traffic were uninstrumented.",
            "Contrasts retain all four measured blocks per process. Extrema are descriptive.",
            "Physical execution checked the readback hashes. The journals bind 87 expected "
            "digests and per-wave counts without saving individual readback digests.",
            "Preparation, initialization and fixture cleanup have separate clocks. "
            "Readback validation and final CUDA process exit lack separate clocks.",
            "Four selected waves cover expert service. Logits, full turns and M3/M4 remain open.",
        ],
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "first",
        "second",
        "plan",
        "map",
        "ram-receipt",
        "c55",
        "second-c55",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=k != "second-c55")
    a = p.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        result = review(a)
    except (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError) as exc:
        result = dict(status="FAIL_REVIEW", reason=f"{type(exc).__name__}: {exc}")
    tmp = out / "pending.json"
    with tmp.open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    os.link(tmp, out / "receipt.json")
    tmp.unlink()
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_REVIEW")


if __name__ == "__main__":
    raise SystemExit(main())

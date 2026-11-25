"""Select four pre-registered strata and bind both transport layouts to identical weights."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
causal = run_path(str(HERE.parent / "t1_primary_victim/screen.py"))
src, check = causal["src"], causal["check"]
CAUSAL = "5a98dfe45eae6900c68b8ca6bea899d3222c1769f3ca99ccf1ab79eddd53c796"
INDEX = "f8961dcdaa58aa7774e63150b76d69add0dd080181493838528c8f36de543a57"
READBACK = "54273ebffab1294357932b5c4ee6823be7cb9d9d7420b5582b7294c744b658a0"
POLICIES = ("lru_ram", "evict_backed_first")
STRATA = ("148_cpu", "148_cuda", "decode_cpu", "decode_cuda")


def origins(pool, layer, demand, bank):
    return [
        "primary" if e in pool.slots else "ram" if (layer, e) in bank else "disk" for e in demand
    ]


def selected(x, arms):
    start, required, waves = causal["inputs"](x.rows)
    sites = list(dict.fromkeys((r.call, r.tile, r.layer, r.wave) for r in x.rows if r.kind == 10))
    bank = set(map(tuple, x.prefix["capacities"]["353"]["ordered_keys"]))
    pools = {name: [causal["Pool"](s) for s in start] for name in POLICIES}
    costs = {name: defaultdict(Counter) for name in POLICIES}
    chosen, tallies = {}, {s: Counter() for s in STRATA}
    next_phase = False
    for tick, ((call, layer, demand), site) in enumerate(zip(waves, sites, strict=True), 1):
        check((site[0], site[2]) == (call, layer), "wave site")
        if call > 2 and not next_phase:
            for name in POLICIES:
                for i, pool in enumerate(pools[name]):
                    pool.restore(i, required[i], bank, tick, costs[name]["restore"])
            next_phase = True
        phase = "prefill" if call <= 2 else "decode"
        paths = {}
        disks = []
        for name in POLICIES:
            pool = pools[name][layer]
            paths[name] = origins(pool, layer, demand, bank)
            disks.append({e for e, tier in zip(demand, paths[name], strict=True) if tier == "disk"})
            pool.wave(layer, demand, bank, name == POLICIES[1], tick, costs[name][phase])
        if call == 1:
            continue
        tier = "cpu" if layer < 25 else "cuda"
        stratum = ("148" if call == 2 else "decode") + "_" + tier
        t = tallies[stratum]
        t["nonempty_waves"] += 1
        t["disk_lru"] += len(disks[0])
        t["disk_candidate"] += len(disks[1])
        if disks[0] != disks[1]:
            t["eligible"] += 1
            delta = len(disks[1]) - len(disks[0])
            t["fewer" if delta < 0 else "more" if delta > 0 else "equal_count"] += 1
            chosen.setdefault(stratum, dict(site=site, demand=demand, paths=paths))
    for name in POLICIES:
        for phase in ("restore", "prefill", "decode"):
            check(costs[name][phase] == arms[name]["restore"][phase], "causal counts " + phase)
    return chosen, tallies


def bind(layer, expert, index, meta):
    entry = index["experts"][128 * layer + expert]
    offset = entry["pack_offset"]
    check(
        (entry["layer"], entry["expert"]) == (layer, expert)
        and entry["tier"] == ("CPU" if layer < 25 else "GPU")
        and offset == (128 * layer + expert) * index["stride"],
        "indexed record",
    )
    ranges = []
    for i, role in enumerate(("gate", "down", "up")):
        record = entry["components"][i]
        base, size = meta[layer, i]
        pos = base + expert * size
        aligned = pos // 4096 * 4096
        count = (pos - aligned + size + 4095) // 4096 * 4096
        digest = record["sha256"]
        check(
            record["name"] == f"blk.{layer}.ffn_{role}_exps.weight"
            and record["type"] == "mxfp4"
            and record["size_bytes"] == size == 4406400
            and record["source_offset"] == pos
            and record["packed_relative_offset"] == i * size
            and offset + i * size + size <= offset + index["weight_window"] <= index["pack_bytes"]
            and len(bytes.fromhex(digest)) == 32,
            "weight slice",
        )
        ranges.append(dict(logical=pos, aligned=aligned, count=count, size=size, sha256=digest))
    return dict(layer=layer, expert=expert, pack_offset=offset, gguf=ranges)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in (
        "part",
        "model",
        "inventory",
        "prepared-dir",
        "causal-dir",
        "index",
        "readback",
        "pack",
        "new-output-dir",
    ):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        prior = src.pinned(a.causal_dir / "receipt.json", CAUSAL)
        index = src.pinned(a.index, INDEX)
        rb = src.pinned(a.readback, READBACK)
        check(
            rb["status"] == "PASS_FULL_CANONICAL_PACK_READBACK"
            and rb["component_checks"] == 27648
            and index["pack_sha256_write_stream"] == rb["pack_sha256_write_stream"]
            and a.pack.stat().st_size == index["pack_bytes"] == rb["pack_identity"]["size_bytes"]
            and len(index["experts"]) == 4608
            and index["weight_window"] == 13221888,
            "qualified index",
        )
        x = src.load_inputs(a.part, a.model, a.inventory, a.prepared_dir)
        check(x.journal == prior["journal_sha256"], "process identity")
        samples, tallies = selected(x, prior["arms"])
        keys = sorted({(s["site"][2], e) for s in samples.values() for e in s["demand"]})
        entries = [bind(layer, e, index, x.meta) for layer, e in keys]
        plan = dict(
            samples=samples,
            entries=entries,
            weight_window=index["weight_window"],
            journal=x.journal,
            causal=CAUSAL,
            index=INDEX,
            readback=READBACK,
        )
        src.possible.save(a.new_output_dir / "plan.json", plan)
        totals = {
            k: dict(
                consumers=len(s["demand"]),
                origins={name: Counter(values) for name, values in s["paths"].items()},
            )
            for k, s in samples.items()
        }
        result = dict(
            status="GO_PREPARE_ONLY" if samples else "NO_DISCRIMINATING_WAVE",
            missing_strata=sorted(set(STRATA) - samples.keys()),
            tallies=tallies,
            sample_counts=totals,
            distinct_records=len(keys),
            partial_bytes=len(keys) * index["weight_window"],
            plan_sha256=src.sha(a.new_output_dir / "plan.json"),
            bound_components=3 * len(keys),
            inputs=dict(index=INDEX, readback=READBACK, causal=CAUSAL, journal=x.journal),
        )
    except (KeyError, IndexError, ValueError, OSError, StopIteration) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result.update(
        program_sha256=src.sha(Path(__file__)), protocol_sha256=src.sha(HERE / "protocol.md")
    )
    src.possible.save(a.new_output_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

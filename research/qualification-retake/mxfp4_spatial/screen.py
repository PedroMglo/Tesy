"""Upper bound on spatial byte-rANS for the 64 authenticated C287 expert records."""

import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from mxfp4_conditional import screen as base  # noqa: E402

m = base.marginal
PRIOR = "a7d0a1fc4c2bcf60af568457f8f10be7c71780fa8d2d61bd006c61b3abfba76b"
COMPONENTS = "cc8b5a516c6d0db6f82729699746f81dbbc9669dd8e5b3caf233f9565031555d"
CONTEXTS = 256 * 2 * 17
WINDOW = base.aligned(3 * base.WEIGHT, 4096)
CHECK = base.require


@lru_cache(maxsize=32768)
def n_log_n(n):
    """Directed nanobits for n log2(n); enclose n by adjacent 14-bit mantissas."""
    if n == 0:
        return 0, 0
    shift = max(0, n.bit_length() - 14)
    lower, rem = divmod(n, 1 << shift)
    upper = lower + bool(rem)
    lo = m.log2_bounds(lower)[0] + shift * m.Q
    hi = m.log2_bounds(upper)[1] + shift * m.Q
    return n * lo, n * hi


def analyse_hist(data, blocks, rows, prior):
    tables = {}
    joint = defaultdict(lambda: [0] * 16)
    terms = Counter()
    half_counts = [0, 0]
    starts = n_symbols = 0
    for line in data.splitlines():
        scale, half, previous, *counts = map(int, line.split())
        key = (scale, half, previous)
        CHECK(
            0 <= scale < 256
            and half in (0, 1)
            and 0 <= previous <= 16
            and key not in tables
            and len(counts) == 16
            and min(counts) >= 0,
            "invalid spatial context",
        )
        n = sum(counts)
        CHECK(n > 0 and not (half == 1 and previous == 16), "empty or invalid START context")
        tables[key] = n
        half_counts[half] += n
        n_symbols += n
        starts += n if previous == 16 else 0
        for symbol, value in enumerate(counts):
            joint[scale][symbol] += value
        terms[n] += 1
        terms.subtract(counts)
    CHECK(starts == rows and half_counts == [16 * blocks] * 2, "row resets or nibble census")
    actual = [[scale, joint[scale]] for scale in sorted(joint)]
    CHECK(base.canonical_digest(actual) == prior["joint_counts_sha256"], "C287 joint mismatch")
    lo = sum(
        multiplicity * n_log_n(n)[0 if multiplicity > 0 else 1]
        for n, multiplicity in terms.items()
        if multiplicity
    )
    penalty = m.log2_bounds(256)[1] - m.log2_bounds(255)[0]
    nibble_bits = max(0, -(-(lo - n_symbols * penalty - 8 * m.Q) // m.Q))
    # One separate scale stream; do not reset the nibble state at row or table changes.
    scale_bits = prior["scale_bits_floor"]
    floor_bytes = (scale_bits + 7) // 8 + (nibble_bits + 7) // 8
    return {
        "contexts": len(tables),
        "row_starts": starts,
        "encoded_bytes_floor": floor_bytes,
        "spatial_nibble_bits_floor": nibble_bits,
        "conditional_nibble_bits_floor": prior["conditional_nibble_bits_floor"],
        "tables_sha256": base.sha(data),
    }


def expert_row(layer, expert, tier, components):
    CHECK(len(components) == 3, "three weight matrices per transport unit")
    compressed = base.aligned(sum(row["encoded_bytes_floor"] for row in components), 4096)
    chosen = min(compressed, WINDOW)
    return {
        "layer": layer,
        "expert": expert,
        "tier": tier,
        "matrices": components,
        "aligned_bytes_floor": chosen,
        "gate20_possible": 5 * chosen <= 4 * WINDOW,
        "table_bytes_example_sparse": sum(512 + 35 * r["contexts"] for r in components),
    }


def summarize(rows):
    total = len(rows) * WINDOW
    emitted = sum(r["aligned_bytes_floor"] for r in rows)
    best = min(rows, key=lambda r: (r["aligned_bytes_floor"], r["layer"], r["expert"]))
    return {
        "experts": len(rows),
        "raw_aligned_bytes": total,
        "encoded_aligned_bytes_floor": emitted,
        "saving_percent_ceiling": round(100 * (total - emitted) / total, 8),
        "gate20_possible": 5 * emitted <= 4 * total,
        "experts_gate20_possible": sum(r["gate20_possible"] for r in rows),
        "best": {k: best[k] for k in ("layer", "expert", "aligned_bytes_floor")},
        "best_saving_percent_ceiling": round(100 * (1 - best["aligned_bytes_floor"] / WINDOW), 8),
        "table_bytes_example_sparse": sum(r["table_bytes_example_sparse"] for r in rows),
    }


def run(args):
    CHECK(not base.git("status", "--porcelain"), "measurement checkout must be clean")
    prior_dir = HERE.parent / "mxfp4_conditional"
    prior_raw = (prior_dir / "evidence/receipt.json").read_bytes()
    prior = json.loads(prior_raw)
    CHECK(base.sha(prior_raw) == PRIOR, "prior physical conditional receipt")
    for name in ("screen.py", "hist.cpp", "protocol.md"):
        CHECK(
            base.sha((prior_dir / name).read_bytes()) == prior["sources_sha256"][name],
            "prior source",
        )
    prev = (prior_dir / "evidence/components.json").read_bytes()
    CHECK(base.sha(prev) == COMPONENTS == prior["components_sha256"], "conditional component table")
    comp = {(r["layer"], r["expert"], r["name"]): r for r in json.loads(prev)}
    inputs, _, index, _ = base.reference(args.results_root)
    base.layout(index)
    compiler = base.COMPILER
    pack_hash = hashlib.sha256()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        program = Path(tmp) / "spatial"
        subprocess.run(
            [str(compiler), *base.FLAGS, str(HERE / "count.cpp"), "-o", str(program)],
            timeout=30,
            check=True,
        )
        binary_sha = base.sha(program.read_bytes())
        with args.sample_pack.open("rb", buffering=0) as f:
            initial = base.stat_id(f.fileno())
            CHECK(initial[2] == index["pack_bytes"], "pack size")
            for record in index["experts"]:
                chunk = f.read(index["stride"])
                CHECK(len(chunk) == index["stride"], "truncated pack")
                pack_hash.update(chunk)
                items = record["components"]
                views = base.record_components(chunk, items)
                matrices = []
                for item, slab in zip(items[:3], views[:3], strict=True):
                    ref = comp.pop((record["layer"], record["expert"], item["name"]))
                    CHECK(ref["source_sha256"] == item["sha256"], "weight identity")
                    proc = subprocess.run(
                        [str(program), "90"],
                        input=slab,
                        capture_output=True,
                        timeout=10,
                        check=True,
                    )
                    CHECK(not proc.stderr and len(proc.stdout) < 2 << 20, "counter output")
                    matrices.append(
                        {
                            "name": item["name"],
                            "sha256": item["sha256"],
                            **analyse_hist(proc.stdout, base.BLOCKS, 2880, ref),
                        }
                    )
                rows.append(expert_row(record["layer"], record["expert"], ref["tier"], matrices))
            CHECK(not f.read(1) and base.stat_id(f.fileno()) == initial, "pack end/stat")
    CHECK(not comp and len(rows) == 64 and pack_hash.hexdigest() == base.PACK_SHA, "pack integrity")
    all_rows = summarize(rows)
    tiers = {tier: summarize([r for r in rows if r["tier"] == tier]) for tier in ("CPU", "CUDA")}
    best = all_rows["best"]["aligned_bytes_floor"]
    decision = "INCONCLUSIVE"
    if not all_rows["experts_gate20_possible"]:
        decision = "NO_GO"
    elif all(v["gate20_possible"] for v in tiers.values()):
        decision = "GO_CODEC_FIXTURE_ONLY"
    sensitivities = {}
    for name, loads, budget in [
        ("part37_original", 1263, 10_938_366_806),
        ("part40_causal", 1160, 10_690_306_614),
        ("part40_unlimited_oracle", 839, 10_690_306_614),
    ]:
        sensitivities[name] = dict(
            loads=loads,
            budget_bytes=budget,
            favorable_aligned_bytes=loads * best,
            excess_bytes=loads * best - budget,
        )
    return {
        "decision": decision,
        "sample": all_rows,
        "tiers": tiers,
        "sensitivities": sensitivities,
        "expert_rows_sha256": m.write_json(args.new_output_dir / "experts.json", rows),
        "prior_conditional_receipt_sha256": PRIOR,
        "inputs": inputs,
        "pack_sha256": base.PACK_SHA,
        "pack_bytes_read": index["pack_bytes"],
        "authenticated_components": 384,
        "charged_table_bytes_in_bound": 0,
        "dense_example_bytes_per_matrix": 512 + 32 * CONTEXTS,
        "source_sha256": {
            p.name: base.sha(p.read_bytes())
            for p in (HERE / "protocol.md", HERE / "screen.py", HERE / "count.cpp")
        },
        "build": {
            "compiler_sha256": base.sha(compiler.read_bytes()),
            "flags": base.FLAGS,
            "binary_sha256": binary_sha,
        },
        "model_forwards": 0,
        "gpu": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results-root", "sample-pack", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    resource.setrlimit(resource.RLIMIT_AS, (384 << 20, 384 << 20))
    signal.signal(signal.SIGALRM, base.deadline_expired)
    signal.alarm(240)
    receipt = {
        "commit": base.git("rev-parse", "HEAD"),
        "tree": base.git("rev-parse", "HEAD^{tree}"),
    }
    try:
        receipt.update(run(args))
    except FileNotFoundError as exc:
        receipt.update(decision="NOT_RUN_RAW_REQUIRED", reason=os.path.basename(exc.filename))
    except Exception as exc:
        receipt.update(decision="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    m.write_json(args.new_output_dir / "receipt.json", receipt)
    print(receipt["decision"])
    return int(receipt["decision"] not in {"GO_CODEC_FIXTURE_ONLY", "NO_GO", "INCONCLUSIVE"})


if __name__ == "__main__":
    raise SystemExit(main())

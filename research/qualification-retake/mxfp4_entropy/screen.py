"""Offline marginal byte-rANS bound on the previously verified C319 receipts."""

import argparse
import hashlib
import json
import resource
import signal
import subprocess
import sys
from collections import defaultdict
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools"))
from expert_compressibility_gate import evaluate as check_c319  # noqa: E402

C319 = "c319-fixed-lossless-compressibility-20261007"
C287 = "c287-lossless-sample-producer-20261006"
PINS = {
    C319 + "/raw-manifest.json": (
        1892,
        "d02b39e0246b8584798c6d683721f9df109cc3668659ebde842efaba7582791c",
    ),
    C287 + "/raw-manifest.json": (
        3513,
        "51dd40a813eb05890f9a0a42238065811bb31b61895304805dbf23b31e9dd33e",
    ),
    C319 + "/protocol.json": (
        26104,
        "c590ade1371a8f9b456be984eeaf5df91e09e1d5339a34aa11d34284186d15fb",
    ),
}
Q = 10**9  # unit for directed fixed-point log bounds
BLOCKS = 259200
MATRIX_BYTES = 17 * BLOCKS
LAYERS = (0, 8, 16, 24, 25, 29, 32, 35)
EXPERTS = range(0, 120, 17)


@lru_cache(maxsize=32768)
def log2_bounds(n):
    """Enclose log2(n) in integer nanobits, even at a decision boundary."""
    if type(n) is not int or n < 1:
        raise ValueError("positive integral log argument required")
    if n & (n - 1) == 0:
        exact = (n.bit_length() - 1) * Q
        return exact, exact
    with localcontext() as ctx:
        ctx.prec = 50
        # Decimal.ln is correctly rounded. Enclose both operands, then the ratios.
        num, den = Decimal(n).ln(), Decimal(2).ln()
        lo = (num.next_minus() / den.next_plus()).next_minus()
        hi = (num.next_plus() / den.next_minus()).next_plus()
        return (
            int((lo * Q).to_integral_value(rounding=ROUND_FLOOR)),
            int((hi * Q).to_integral_value(rounding=ROUND_CEILING)),
        )


def stream_bound(counts, alphabet, population):
    if (
        type(counts) is not list
        or len(counts) != alphabet
        or any(type(x) is not int or x < 0 for x in counts)
        or sum(counts) != population
        or population < 1
    ):
        raise ValueError("invalid histogram alphabet, population or count")
    n_lo, n_hi = log2_bounds(population)
    h_lo, h_hi = n_lo * population, n_hi * population
    for count in counts:
        if count:
            lo, hi = log2_bounds(count)
            h_lo -= count * hi
            h_hi -= count * lo
    penalty = log2_bounds(256)[1] - log2_bounds(255)[0]
    # Emitted bits are integral. Ignore even their divisibility by eight.
    lower_bits = max(0, -(-(h_lo - population * penalty - 8 * Q) // Q))
    return max(0, h_lo), h_hi, lower_bits


def rows_for(value):
    rows = []
    expected = {
        (layer, expert, f"blk.{layer}.ffn_{kind}_exps.weight")
        for layer in LAYERS
        for expert in EXPERTS
        for kind in ("gate", "up", "down")
    }
    for item in value["components"]:
        if item["name"].endswith(".bias"):
            continue
        key = item["layer"], item["expert"], item["name"]
        tier = "CPU" if key[0] <= 24 else "GPU"
        if key not in expected or item["tier"] != tier or item["logical_bytes"] != MATRIX_BYTES:
            raise ValueError("invalid sample stratum or matrix size")
        expected.remove(key)
        sub = item["substreams"]
        if (sub["scale_bytes"], sub["qs_bytes"]) != (BLOCKS, 16 * BLOCKS):
            raise ValueError("invalid MXFP4 layout")
        scale = stream_bound(sub["scale_histogram"], 256, BLOCKS)
        nibble = stream_bound(sub["nibble_histogram"], 16, 32 * BLOCKS)
        rows.append(
            {
                "layer": key[0],
                "expert": key[1],
                "name": key[2],
                "tier": "CPU" if tier == "CPU" else "CUDA",
                "raw_bytes": MATRIX_BYTES,
                "h0_bits_lo": (scale[0] + nibble[0]) // Q,
                "h0_bits_hi": -(-(scale[1] + nibble[1]) // Q),
                "scale_bits_floor": scale[2],
                "nibble_bits_floor": nibble[2],
                "emitted_bits_floor": scale[2] + nibble[2],
            }
        )
    if expected or len(rows) != 192:
        raise ValueError("incomplete C319 population")
    return rows


def group(rows):
    bits = 8 * sum(row["raw_bytes"] for row in rows)
    emitted = sum(row["emitted_bits_floor"] for row in rows)
    best = min(rows, key=lambda row: (row["emitted_bits_floor"], row["name"], row["expert"]))
    one = 8 * best["raw_bytes"]
    return {
        "components": len(rows),
        "experts": len({(r["layer"], r["expert"]) for r in rows}),
        "raw_bits": bits,
        "h0_bits_lo": sum(r["h0_bits_lo"] for r in rows),
        "h0_bits_hi": sum(r["h0_bits_hi"] for r in rows),
        "emitted_bits_floor": emitted,
        "savings_percent_ceiling": round(100 * (bits - emitted) / bits, 8),
        "best": {
            "layer": best["layer"],
            "expert": best["expert"],
            "name": best["name"],
            "emitted_bits_floor": best["emitted_bits_floor"],
            "raw_bits": one,
            "savings_percent_ceiling": round(100 * (one - best["emitted_bits_floor"]) / one, 8),
        },
    }


def pinned_json(root, relative, expected, evidence):
    path = root / relative
    if path.stat().st_size != expected[0]:
        raise ValueError(f"size mismatch: {relative}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected[1]:
        raise ValueError(f"digest mismatch: {relative}")
    evidence[relative] = {"bytes": len(data), "sha256": digest}
    return json.loads(data)


def analyse(root):
    evidence = {}
    docs = {key: pinned_json(root, key, pin, evidence) for key, pin in PINS.items()}

    def raw(campaign, name):
        relative = f"{campaign}/raw/{name}"
        manifest = docs[campaign + "/raw-manifest.json"]["files"]
        (entry,) = (f for f in manifest if f["path"] == "results/" + relative)
        size = entry["size_bytes" if campaign == C319 else "bytes"]
        return pinned_json(root, relative, (size, entry["sha256"]), evidence)

    value, index = raw(C319, "characterization.json"), raw(C287, "sample-index.json")
    proto = docs[C319 + "/protocol.json"]
    if value["source_identity"] != proto["model_stat"]:
        raise ValueError("C319 model identity mismatch")
    check_c319(value, index, proto["codec_libraries_sha256"])
    rows = rows_for(value)
    strata = defaultdict(list)
    for row in rows:
        strata[row["tier"]].append(row)
        strata[f"{row['tier']}/layer{row['layer']}"].append(row)
    all_rows = group(rows)
    best = all_rows["best"]
    twenty_percent_unreachable = 5 * best["emitted_bits_floor"] > 4 * best["raw_bits"]
    return {
        "decision": "NO_GO" if twenty_percent_unreachable else "GO_ENCODER_FIXTURE_ONLY",
        "sample": all_rows,
        "strata": {key: group(vals) for key, vals in sorted(strata.items())},
        "minimum_decode_time_saving_percent": 100 * (1 - 4.52326 / 6),
        "decode_cut_unreachable_in_proportional_scenario": best["emitted_bits_floor"] * 600000
        > best["raw_bits"] * 452326,
        "inputs": evidence,
        "blocks_per_matrix": BLOCKS,
        "scale_symbols_per_matrix": BLOCKS,
        "nibble_symbols_per_matrix": 32 * BLOCKS,
    }, rows


def write_json(path, value):
    data = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()
    staging = path.with_suffix(".part")
    with staging.open("xb") as file:
        file.write(data)
    staging.rename(path)
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    dest = args.new_output_dir
    dest.mkdir(parents=False, exist_ok=False)
    proc = {
        "schema": "tesy-c319-marginal-rans-screen-v1",
        "code_commit": subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
        ).strip(),
        "sources_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                HERE / "protocol.md",
                REPO / "tools/expert_compressibility_gate.py",
            )
        },
    }
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    signal.alarm(30)
    try:
        summary, rows = analyse(args.results_root)
        proc.update(summary, component_results_sha256=write_json(dest / "components.json", rows))
    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
        proc["decision"] = (
            "NOT_RUN_RAW_REQUIRED" if isinstance(exc, FileNotFoundError) else "FAIL_INPUT"
        )
        proc["reason"] = Path(exc.filename).name if isinstance(exc, FileNotFoundError) else str(exc)
    write_json(dest / "receipt.json", proc)
    print(proc["decision"])
    return int(proc["decision"] not in {"NO_GO", "GO_ENCODER_FIXTURE_ONLY"})


if __name__ == "__main__":
    raise SystemExit(main())

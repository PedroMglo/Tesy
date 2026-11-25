"""Conditional byte-rANS lower bound with a single pass over the C287 sample pack."""

import argparse
import hashlib
import json
import os
import resource
import signal
import stat
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from mxfp4_entropy import screen as marginal  # noqa: E402

MARGINAL = HERE.parent / "mxfp4_entropy"
REF_COMMIT = "b5c438124f74447cf2c39b8107c9ad20b5ee9970"
PRIOR_SHA = "1101ab621a0c6648c376535f0ebfea599a04b7345b3dcbeb293de2f51fcfc999"
PACK_SHA = "cd1a29fa993e44421a03d55caee82d66d3a9ad788b982a4246743a67dc177f44"
MODEL = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
Q = marginal.Q
COMPILER = Path("/usr/bin/g++")
FLAGS = ["-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror"]
BLOCKS = marginal.BLOCKS
WEIGHT = marginal.MATRIX_BYTES
BIAS = 11520
STRATA = tuple((layer, expert) for layer in marginal.LAYERS for expert in marginal.EXPERTS)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(
        [
            "git",
            "--no-optional-locks",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            str(REPO),
            *args,
        ],
        text=True,
    ).strip()


def canonical_digest(data):
    encoded = json.dumps(data, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
    return sha(encoded)


def reference(results):
    """Replay the marginal campaign and cross-check its compact and 192 component records."""
    prior_bytes = (MARGINAL / "evidence/receipt.json").read_bytes()
    require(sha(prior_bytes) == PRIOR_SHA, "marginal receipt digest")
    prior = json.loads(prior_bytes)
    require(prior["code_commit"] == REF_COMMIT, "marginal measurement revision")
    for source in [
        MARGINAL / "screen.py",
        MARGINAL / "protocol.md",
        REPO / "tools/expert_compressibility_gate.py",
    ]:
        require(
            sha(source.read_bytes()) == prior["sources_sha256"][source.name],
            "marginal source version",
        )
    summary, rows = marginal.analyse(results)
    for key, value in summary.items():
        require(value == prior[key], "marginal receipt replay")
    reference_rows = (MARGINAL / "evidence/components.json").read_bytes()
    require(
        sha(reference_rows) == prior["component_results_sha256"]
        and json.loads(reference_rows) == rows,
        "marginal component replay",
    )
    inputs = summary["inputs"]
    raw = {}
    for campaign, name in [
        (marginal.C319, "characterization.json"),
        (marginal.C287, "sample-index.json"),
    ]:
        relative = f"{campaign}/raw/{name}"
        item = inputs[relative]
        raw[campaign] = marginal.pinned_json(results, relative, (item["bytes"], item["sha256"]), {})
    return inputs, rows, raw[marginal.C287], raw[marginal.C319]


def aligned(n, alignment):
    return (n + alignment - 1) // alignment * alignment


def layout(index):
    align = index["alignment"]
    require(align == index["memory_alignment"] == 4096, "pack alignment")
    window = aligned(3 * WEIGHT, align)
    stride = window + aligned(3 * BIAS, align)
    require(
        index["source_fd_direct"] is True
        and index["model_sha256_previous_verified"] == MODEL
        and index["weight_window"] == window
        and index["stride"] == stride
        and index["pack_bytes"] == stride * len(STRATA)
        and index["logical_bytes"] == len(STRATA) * 3 * (WEIGHT + BIAS)
        and index["pack_sha256_write_stream"] == PACK_SHA,
        "sample layout identity",
    )
    require(len(index["experts"]) == len(STRATA), "sample cardinality")
    for n, ((layer, expert), row) in enumerate(zip(STRATA, index["experts"], strict=True)):
        require(
            (row["layer"], row["expert"]) == (layer, expert)
            and row["tier"] == ("CPU" if layer < 25 else "GPU")
            and row["pack_offset"] == n * stride
            and len(row["components"]) == 6,
            "sample order or offset",
        )
        for k, component in enumerate(row["components"]):
            field = ("gate", "down", "up")[k % 3]
            is_weight = k < 3
            suffix = "weight" if is_weight else "bias"
            size = WEIGHT if is_weight else BIAS
            offset = k * WEIGHT if is_weight else window + (k - 3) * BIAS
            require(
                component["type"] == ("mxfp4" if is_weight else "f32")
                and component["size_bytes"] == size
                and component["packed_relative_offset"] == offset
                and component["name"] == f"blk.{layer}.ffn_{field}_exps.{suffix}"
                and component["source_offset"] >= 0
                and offset + size <= stride,
                "component type, size, order or offset",
            )


def record_components(record, descriptors):
    """Hash every component and check the zero-filled gaps before releasing any view."""
    view = memoryview(record)
    last = 0
    views = []
    for d in descriptors:
        start = d["packed_relative_offset"]
        end = start + d["size_bytes"]
        require(
            0 <= last <= start < end <= len(view) and not any(view[last:start]),
            "component overlap, truncation or nonzero padding",
        )
        slab = view[start:end]
        require(sha(slab) == d["sha256"], "component SHA mismatch")
        views.append(slab)
        last = end
    require(not any(view[last:]), "nonzero final alignment padding")
    return views


def entropy_bounds(joint, scales, nibbles, blocks):
    """Two terminal-state allowances; changing the nibble table does not reset its state."""
    scale_lo, scale_hi, scale_bits = marginal.stream_bound(scales, 256, blocks)
    nibble_lo, nibble_hi, marginal_bits = marginal.stream_bound(nibbles, 16, 32 * blocks)
    expected = [i for i, count in enumerate(scales) if count]
    require(isinstance(joint, list) and len(joint) == len(expected), "occupied scales")
    columns = [0] * 16
    conditional_lo = conditional_hi = 0
    for wanted, entry in zip(expected, joint, strict=True):
        scale, counts = entry
        require(type(scale) is int and scale == wanted, "duplicate, missing or out-of-order scale")
        lo, hi, _ = marginal.stream_bound(counts, 16, 32 * scales[scale])
        conditional_lo += lo
        conditional_hi += hi
        columns = [a + b for a, b in zip(columns, counts, strict=True)]
    require(columns == nibbles, "nibble marginal mismatch")
    # Sum the directed empirical entropies at each scale, then round ONCE. All
    # normalization tables have the same total and legal range of coder states.
    penalty_hi = marginal.log2_bounds(256)[1] - marginal.log2_bounds(255)[0]
    bits = max(0, -(-(conditional_lo - 32 * blocks * penalty_hi - 8 * Q) // Q))
    return {
        "h0_bits_lo": (scale_lo + conditional_lo) // Q,
        "h0_bits_hi": -(-(scale_hi + conditional_hi) // Q),
        "scale_bits_floor": scale_bits,
        "conditional_nibble_bits_floor": bits,
        "emitted_bits_floor": scale_bits + bits,
        "marginal_emitted_bits_floor": scale_bits + marginal_bits,
        "mutual_information_total_bits_lo": max(0, (nibble_lo - conditional_hi) // Q),
        "mutual_information_total_bits_hi": max(0, -(-(nibble_hi - conditional_lo) // Q)),
        "occupied_scales": len(joint),
        "joint_counts_sha256": canonical_digest(joint),
    }


def group(rows):
    record = marginal.group(rows)
    original = record["raw_bits"]
    emitted = record["emitted_bits_floor"]
    best = record["best"]
    old = sum(row["marginal_emitted_bits_floor"] for row in rows)
    record.update(
        gate20_percent_reachable=5 * emitted <= 4 * original,
        best_matrix_gate20_percent_reachable=5 * best["emitted_bits_floor"] <= 4 * best["raw_bits"],
        marginal_emitted_bits_floor=old,
        savings_ceiling_delta_percentage_points=round(100 * (old - emitted) / original, 8),
        mutual_information_total_bits_lo=sum(
            row["mutual_information_total_bits_lo"] for row in rows
        ),
        mutual_information_total_bits_hi=sum(
            row["mutual_information_total_bits_hi"] for row in rows
        ),
    )
    return record


def native_count(program, payload, blocks):
    proc = subprocess.run(
        [str(program), str(blocks)], input=payload, capture_output=True, timeout=10, check=True
    )
    require(len(proc.stdout) <= 65536 and not proc.stderr, "unexpected histogram output")
    return json.loads(proc.stdout)


def build(dest):
    binary = dest / "hist"
    subprocess.run(
        [str(COMPILER), *FLAGS, str(HERE / "hist.cpp"), "-o", str(binary)], check=True, timeout=30
    )
    return binary


def stat_id(fd):
    s = os.fstat(fd)
    require(stat.S_ISREG(s.st_mode), "pack must be a regular file")
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def inspect(pack_path, program, index, characterization, prior_rows):
    layout(index)
    rows = []
    pack_hash = hashlib.sha256()
    sources = iter(characterization["components"])
    marginals = iter(prior_rows)
    n_components = 0
    with pack_path.open("rb", buffering=0) as file:
        before = stat_id(file.fileno())
        require(before[2] == index["pack_bytes"], "pack size")
        for expert in index["experts"]:
            record = file.read(index["stride"])
            require(len(record) == index["stride"], "short pack read")
            pack_hash.update(record)
            descriptors = expert["components"]
            views = record_components(record, descriptors)
            for d, slab in zip(descriptors, views, strict=True):
                c = next(sources)
                require(
                    c["layer"] == expert["layer"]
                    and c["expert"] == expert["expert"]
                    and c["source_sha256"] == d["sha256"]
                    and c["name"] == d["name"]
                    and c["source_offset"] == d["source_offset"]
                    and c["logical_bytes"] == len(slab),
                    "C319 slice identity",
                )
                n_components += 1
                if d["type"] != "mxfp4":
                    continue
                prior = next(marginals)
                require(
                    (prior["layer"], prior["expert"], prior["name"])
                    == (expert["layer"], expert["expert"], d["name"]),
                    "marginal component order",
                )
                s = c["substreams"]
                joint = native_count(program, slab, BLOCKS)
                result = entropy_bounds(joint, s["scale_histogram"], s["nibble_histogram"], BLOCKS)
                require(
                    result["marginal_emitted_bits_floor"] == prior["emitted_bits_floor"],
                    "marginal bound mismatch",
                )
                rows.append(
                    {
                        "layer": prior["layer"],
                        "expert": prior["expert"],
                        "name": prior["name"],
                        "tier": prior["tier"],
                        "raw_bytes": len(slab),
                        "source_sha256": d["sha256"],
                        "savings_percent_ceiling": round(
                            100 * (1 - result["emitted_bits_floor"] / (8 * len(slab))), 8
                        ),
                        "gate20_percent_reachable": 5 * result["emitted_bits_floor"]
                        <= 4 * 8 * len(slab),
                        **result,
                    }
                )
        require(not file.read(1) and stat_id(file.fileno()) == before, "pack changed")
    require(
        pack_hash.hexdigest() == PACK_SHA
        and n_components == 384
        and len(rows) == 192
        and next(marginals, None) is None
        and next(sources, None) is None,
        "complete pack hash and population",
    )
    return rows


def execute(results, pack, dest):
    require(not git("status", "--porcelain"), "measurement checkout must be clean")
    inputs, prior_rows, index, characterization = reference(results)
    with tempfile.TemporaryDirectory(prefix="tesy-joint-hist-") as tmp:
        program = build(Path(tmp))
        binary_sha = sha(program.read_bytes())
        rows = inspect(pack, program, index, characterization, prior_rows)
    strata = defaultdict(list)
    for row in rows:
        strata[row["tier"]].append(row)
        strata[f"{row['tier']}/layer{row['layer']}"].append(row)
    sample = group(rows)
    best = sample["best"]
    return {
        "schema": "tesy-c319-scale-conditioned-rans-v1",
        "decision": "GO_ENCODER_FIXTURE_ONLY"
        if sample["best_matrix_gate20_percent_reachable"]
        else "NO_GO",
        "sample": sample,
        "strata": {name: group(r) for name, r in sorted(strata.items())},
        "decode_cut_unreachable_in_proportional_scenario": best["emitted_bits_floor"] * 600000
        > best["raw_bits"] * 452326,
        "components_sha256": marginal.write_json(dest / "components.json", rows),
        "pack_sha256": PACK_SHA,
        "pack_bytes_read": index["pack_bytes"],
        "verified_weights": len(rows),
        "verified_biases": 192,
        "model_forwards": 0,
        "inputs": inputs,
        "prior_marginal_commit": REF_COMMIT,
        "prior_marginal_receipt_sha256": PRIOR_SHA,
        "build": {
            "compiler_sha256": sha(COMPILER.read_bytes()),
            "flags": FLAGS,
            "binary_sha256": binary_sha,
        },
        "sources_sha256": {
            p.name: sha(p.read_bytes())
            for p in [HERE / "hist.cpp", HERE / "screen.py", HERE / "protocol.md"]
        },
    }


def deadline_expired(_number, _frame):
    raise TimeoutError("unit timeout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["results-root", "sample-pack", "new-output-dir"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    dest = args.new_output_dir
    dest.mkdir(exist_ok=False)
    signal.signal(signal.SIGALRM, deadline_expired)
    signal.alarm(120)
    resource.setrlimit(resource.RLIMIT_AS, (768 << 20, 768 << 20))
    receipt = {}
    try:
        receipt.update(
            measurement_commit=git("rev-parse", "HEAD"), tree=git("rev-parse", "HEAD^{tree}")
        )
        receipt.update(execute(args.results_root, args.sample_pack, dest))
    except FileNotFoundError as exc:
        receipt.update(decision="NOT_RUN_RAW_REQUIRED", reason=Path(exc.filename).name)
    except Exception as exc:
        # All exception messages in this runner describe metadata, never symbol counts or weights.
        receipt.update(decision="FAIL", reason=f"{type(exc).__name__}: {exc}")
    marginal.write_json(dest / "receipt.json", receipt)
    print(receipt["decision"])
    return 0 if receipt["decision"] in {"NO_GO", "GO_ENCODER_FIXTURE_ONLY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

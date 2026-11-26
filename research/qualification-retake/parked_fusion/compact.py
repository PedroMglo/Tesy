"""Verify the archived, descriptor-only C269 graph observations offline."""

import argparse
import hashlib
import json
from pathlib import Path


def read(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("changed " + path.name)
    return json.loads(data)


def need(condition, message):
    if not condition:
        raise ValueError(message)


def summarize(root, receipt_sha):
    receipt = read(root / "receipt.json", receipt_sha)
    need(receipt["status"] == "PASS_C269_TOPOLOGY_AUDIT", "complete scope required")
    phases = {}
    for mode in ("pre", "post"):
        ref = receipt["phases"][mode]
        graph = read(root / f"{mode}-seam.json", ref["seam_sha256"])
        native = ref["native"]
        need(
            graph["structure"] == ref["structure"] and graph["kernel_executed"] is False,
            "capture identity",
        )
        need(
            native["weight_payload_input_bytes"] == native["workers"] == native["wave_calls"] == 0,
            "descriptor-only observation",
        )
        waves = []
        for i, row in enumerate(graph["rows"]):
            need(row["wave"] == i, "wave order")
            record = {k: row[k] for k in ("wave", "certified", "reason") if k in row}
            if "indices" in row:
                indices = row["indices"]
                uses = row["uses"]
                need(
                    len(indices) == len(set(indices)) == len(uses) == 6
                    and [u["index"] for u in uses] == indices,
                    "six nodes",
                )
                contiguous = indices == list(range(indices[0], indices[0] + 6))
                internal = all(
                    not u["outside"] and not graph["nodes"][u["index"]]["output"] for u in uses[:-1]
                )
                need(
                    contiguous == row["contiguous"] and internal == row["no_internal_escape"],
                    "independent consumer check",
                )
                tail = row["tail"]
                certified = (
                    contiguous
                    and internal
                    and row["native_gate"]
                    and tail["remap"] < indices[0]
                    and indices[-1] < tail["down_bias"] < tail["product"]
                    and tail["mask"] not in indices
                )
                need(certified == row["certified"], "native acceptance")
                record.update(indices=indices, native_gate=row["native_gate"], tail=tail)
            waves.append(record)
        need(sum(w["certified"] for w in waves) == ref["certified_waves"], "conservation")
        phases[mode] = {
            k: ref[k]
            for k in (
                "phase",
                "graph_nodes",
                "graph_mmid_nodes",
                "graph_fingerprint",
                "seam_sha256",
                "structure",
            )
        }
        phases[mode].update(
            waves=waves,
            **{
                k: native[k]
                for k in (
                    "backend_splits",
                    "weight_cache_reserved_bytes",
                    "bias_reserved_bytes",
                    "scheduler_reserved_bytes",
                    "descriptor_context_used_bytes",
                )
            },
        )

    if any(v["structure"] == "UNIDENTIFIED_GRAPH" for v in phases.values()):
        decision = "INCONCLUSIVE"
    else:
        for v in phases.values():
            need(
                v["graph_fingerprint"] == "e569253a2f984a84"
                and v["graph_nodes"] == 110
                and v["graph_mmid_nodes"] == 24
                and len(v["waves"]) == 8,
                "historical identity",
            )
        decision = (
            "GO_FIXTURE"
            if all(w["certified"] for w in phases["post"]["waves"])
            else "NO_GO_LOCAL_FUSION"
        )
    need(decision == receipt["decision"], "decision")
    result = {
        k: receipt[k]
        for k in (
            "commit",
            "tree",
            "c269_commit",
            "status",
            "cap_bytes",
            "stop_bytes",
            "decision",
            "model_forwards",
            "weight_input_bytes",
            "memory_peak_bytes",
            "scope_memory_events",
            "elapsed_s",
            "source_sha256",
            "c55_sha256",
            "frontend_sha256",
            "seam_elf_sha256",
        )
    }
    result.update(receipt_sha256=receipt_sha, phases=phases)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.raw_root, args.receipt_sha256)
    args.new_output_dir.mkdir(mode=0o700)
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

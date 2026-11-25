"""Do actual WRT40 ubatches distinguish a change to the native 18-expert wave?"""

import argparse
import hashlib
import json
import resource
import signal
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT / "warm_routes40"))
import witness  # noqa: E402

PINS = {
    "tier_quotas/protocol.md": "5058d74b1e3ab2339902447b9d787990152c961937aa9c09f8081f70c08abc0f",
    "warm_routes40/witness.py": "51a8a71eaf84693fc261a25c686694e8361f6a6bda5d68c4c60890aba55dc058",
    "warm_route_family/evidence-r1.json":
        "8cd41f2de3d183c121b8123bb1fd619c1803c5df6dd48d5676c1dde2158c857c",
    "cold_gpu_rank/replay-r5/receipt.json":
        "7171cd393cc50fdfd6001a46b40a0ff356167e22a662af0a45c1f8811289d7a5",
    "prefill_dispatch/evidence-20261125-r1/receipt.json":
        "88b0c6ade76346b7e480983d225f895d59fa0cdbb94583839c816c1c37df02c2",
}
SRC = {
    "src/llama-graph.cpp": "d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288",
    "src/llama-moe-stream.cpp": "270ede951c3911c8acbd878600f7bab3692215b820d5853d67071b790297f9fc",
    "src/llama-context.cpp": "7d8cfa9f33f38d761cf18b8e548ab7811866fbb8fdfaa95eeb2211d56851681b",
    "src/llama-model.cpp": "7af9ef3bb6dc9491f7280b3dbcc4f6605da7739b4288e7bee51881772f58f010",
    "src/models/openai-moe.cpp": "239407aaa98f8b65eb280e4423588ba7cefc520371811b9c47d7457fc1f469d4",
}


def check(path, expected):
    witness.require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, "unexpected digest")


def n_waves(slots, rows):
    touched = min(128, 4 * rows)
    if touched <= slots:
        return 1
    capacity = (slots - 4) // 2
    return None if capacity < 4 else (touched + capacity - 1) // capacity


def arm(path, meta):
    sha = meta["native_sha256"]["routed-witness.bin"]
    check(path, sha)
    graphs, rows = witness.read(path.read_bytes())
    witness.require(len(rows) == meta["groups"] and graphs[-1][0] == 41, "WRT coverage")
    unique, counts = defaultdict(set), defaultdict(int)
    for call, ub, layer, _, ids in rows:
        key = call, ub, layer
        unique[key].update(ids)
        counts[key] += 1
    peak = [0] * 35
    for key, n in counts.items():
        layer = key[2]
        if layer < 35 and n == 32:
            peak[layer] = max(peak[layer], len(unique[key]))
    final_outputs = [n for key, n in counts.items() if key[2] == 35]
    witness.require(len(final_outputs) == 41, "missing last-layer output calls")
    return dict(case=meta["case"], mode=meta["mode"], witness_sha256=sha, graphs=len(graphs),
                rows=len(rows), max_distinct_experts_in_full_ubatch_by_layer_0_to_34=peak,
                layers_with_19_witness=sum(p >= 19 for p in peak),
                min_of_layer_peaks=min(peak), max_rows_layer35=max(final_outputs))


def run(args):
    for name, sha in PINS.items():
        check(PARENT / name, sha)
    for name, sha in SRC.items():
        check(args.c294_backend / name, sha)
    check(args.c294_stderr, "8d514dcb05ccd357c2e1c2742a85a7ebc4622da1891720f31a1b7a68f1582d64")
    stderr = args.c294_stderr.read_text()
    witness.require("n_outputs_max = 256" in stderr and "n_ubatch      = 32" in stderr,
                    "unexpected reserve parameters")
    registry = json.loads((PARENT / "warm_route_family/evidence-r1.json").read_text())
    witness.require(registry["status"] == "PASS_WARM_ROUTE_FAMILY" and len(registry["arms"]) == 4,
                    "family bridge")
    arms = [arm(args.wrt_raw / (r["run_id"] + ".native") / "routed-witness.bin", r)
            for r in registry["arms"]]
    donor = [s for s in range(4, 41)
             if all(n_waves(s, n) == n_waves(40, n) for n in [1, 16, 32])]
    original = json.loads((PARENT / "cold_gpu_rank/replay-r5/receipt.json").read_text())
    floors = {k: r["cpu24_floor_us"] for k, r in original["arms"].items()}
    history = PARENT / "prefill_dispatch/evidence-20261125-r1/receipt.json"
    service = json.loads(history.read_text())
    cpu = service["sum_service_worker_us_by_tier"]["CPU"]
    cpu_read_floor = (cpu["read"] - 3 * cpu["jobs"]) / 4
    same_cpu = all(a["layers_with_19_witness"] == 35 and a["max_rows_layer35"] == 1 for a in arms)
    no_go = same_cpu and min(floors.values()) * 6 > 32_000_000 and cpu_read_floor > 2427104.435
    return dict(classification="SOURCE_AUDITED_TRACE_DERIVED", arms=arms, source_sha256=SRC,
                input_sha256=PINS, min_layer35_slots_preserving_reserve_wave_counts=min(donor),
                max_gpu_donation_slots=40 - min(donor) if same_cpu else None,
                unchanged_cpu24_decode_floors_us=floors,
                c135_call148_cpu_read_floor_us=cpu_read_floor,
                decision="NO_GO_PRODUCT_TARGETS_FIXED_CPU_WORK" if no_go else "INCONCLUSIVE")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wrt-raw", type=Path, required=True)
    p.add_argument("--c294-backend", type=Path, required=True)
    p.add_argument("--c294-stderr", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    args = p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    signal.alarm(60)
    witness.require(not args.new_output_dir.resolve().is_relative_to(args.wrt_raw.resolve()),
                    "protect raw inputs")
    args.new_output_dir.mkdir(parents=True, exist_ok=False)
    out = run(args)
    tmp = args.new_output_dir / "receipt.pending"
    tmp.write_text(json.dumps(out, indent=2) + "\n")
    tmp.replace(args.new_output_dir / "receipt.json")


if __name__ == "__main__":
    main()

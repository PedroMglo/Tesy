"""Run the C110 supervisor with a per-arm witness gate and a private calibrated route journal."""

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[1] / "nvme_prefix_gate")]
import run_pair as supervisor  # noqa: E402
from witness import compare_tpr, read, require  # noqa: E402

REFERENCE_SHA = "507b70db15461ab9217d593dc92c6113557bfdb6c99cfc7806ca85c20e1e707a"
PROFILE = supervisor.Profile(
    32,
    supervisor.CAP,
    HERE,
    HERE / "build-attempt-01/receipt.json",
    "bb4cc325006bdb2d4c45f0a4f4b380d86aa6eefed004ba91fca616162bf26cbe",
)


def validator(reference_path):
    require(reference_path.stat().st_size == 3058, "historical 32-slot TPR1 length")
    reference = reference_path.read_bytes()
    require(hashlib.sha256(reference).hexdigest() == REFERENCE_SHA, "historical 32-slot TPR1 SHA")
    observations = []

    def validate(raw_c110, prefix, mode):
        require((mode, len(observations)) in (("OFF", 0), ("ON", 1)), "arm order")
        result = supervisor.numerical(raw_c110, prefix, mode)
        path = Path(str(prefix) + ".witness.bin")
        require(0 < path.stat().st_size <= 1024**2, "common witness missing or oversized")
        data = path.read_bytes()
        graphs, rows = read(data)
        require(
            graphs == [(1, 1, tuple(range(16))), (2, 1, (16,)), (3, 1, (17,))] and len(rows) == 633,
            "C110 graph coverage",
        )
        compare_tpr(data, reference)
        if mode == "ON":
            require(data == observations[0], "common OFF/ON divergence")
            tpr = Path(str(prefix) + ".routes.bin").read_bytes()
            require(tpr == reference, "historical and contemporary TPR1 differ")
            compare_tpr(data, tpr)
        observations.append(data)
        result["common_graph"] = {
            "graphs": len(graphs),
            "rows": len(rows),
            "logical_ids": 4 * len(rows),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "reference_tpr_sha256": REFERENCE_SHA,
            "coverage": "all supplied positions and ordered ranks",
        }
        return result

    return validate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--reference-routes", type=Path, required=True)
    args, rest = parser.parse_known_args()
    gate = validator(args.reference_routes)
    sys.argv[1:] = rest
    supervisor.main(PROFILE, gate)

"""Count +1 candidates and byte budgets from sealed C281 ranks, without opening a model."""

import argparse
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
Q = HERE.parents[2]
RELEASE = run_path(
    str(Q / "igpu_resident_rank/request_budget/device/pack_native/natural_trace/release/run.py")
)
SHA = "e5012e559a2403145abc6f5317bddc8b83f95f1e09b592eb83a6baa2c18980a9"
ROW_BYTES = 2880 * 4
check = RELEASE["check"]


def count(family):
    _, _, receipt, _ = RELEASE["chain"](family, SHA)
    src = family / "ON/raw"
    rows, header = RELEASE["NATURAL"]["PFJ"]["read_journal"](src / "events.pfj")
    stderr = next(src.glob("*.stderr"))
    check(RELEASE["digest"](stderr) == receipt["native_ids"]["stderr_sha256"], "stderr identity")
    log = stderr.read_text()
    for layer in range(36):
        device = "CPU" if layer < 25 else "CUDA0"
        check(f"layer {layer:3} assigned to device {device}," in log, "weight placement")
    check("graph splits = 324 (with bs=32), 24 (with bs=1)" in log, "reservation examples")
    calls = [r.a for r in rows if r.kind == 1]
    check(
        calls == [5, 148] + [1] * 46
        and [r.call for r in rows if r.kind == 2] == list(range(1, 49)),
        "requests",
    )
    ranks = Counter((e.call, e.tile, e.layer) for e in rows if e.kind == 27)
    tiles = [(e.call, e.tile, e.a) for e in rows if e.kind == 3]
    check([n for _, _, n in tiles] == [5, 32, 32, 32, 32, 20] + [1] * 46, "native tile sizes")
    cuts = {}
    for label, selected in (
        ("call5", tiles[:1]),
        ("call148", tiles[1:6]),
        ("decode_first", tiles[6:7]),
        ("decode46", tiles[6:]),
        ("all", tiles),
    ):
        c = Counter()
        for call, tile, n in selected:
            check(all(ranks[call, tile, layer] == n for layer in range(35)), "full router rows")
            check(ranks[call, tile, 35] == int(call > 2 or (call, tile) == (2, 5)), "output mask")
            for source in range(35):
                dest = source + 1
                active = ranks[call, tile, dest]
                c["unmasked_positive_nodes"] += 1
                c["unmasked_source_bytes"] += n * ROW_BYTES
                c["selected_positive_nodes"] += int(active > 0)
                c["selected_source_rows"] += active
                c["selected_source_bytes"] += active * ROW_BYTES
                c["dense_get_on_selected_nodes_bytes"] += n * ROW_BYTES * int(active > 0)
                if source >= 25:
                    c["if_source_on_cuda_selected_D2H_bytes"] += active * ROW_BYTES
                    c["if_source_on_cuda_dense_selected_D2H_bytes"] += (
                        n * ROW_BYTES * int(active > 0)
                    )
                    c["if_source_on_cuda_unmasked_D2H_bytes"] += n * ROW_BYTES
                    c["if_source_on_cuda_selected_nodes"] += int(active > 0)
        cuts[label] = dict(c)
    return {
        "family_sha256": SHA,
        "journal_sha256": header["journal_sha256"],
        "stderr_sha256": receipt["native_ids"]["stderr_sha256"],
        "cuts": cuts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family", type=Path)
    result = count(parser.parse_args().family)
    print(json.dumps(result, indent=2, sort_keys=True))

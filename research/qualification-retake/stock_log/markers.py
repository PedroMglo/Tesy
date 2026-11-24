"""Extract public, scoped placement and internal probe counters from the sealed native journal."""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stock_startup"))
from start import check, sha  # noqa: E402


def extract(root, receipt):
    r = json.loads(receipt.read_text())
    check(
        r["status"] == "PASS_STOCK_NVME_PLACEMENT_AT_READY" and r["server_starts"] == 1,
        "unexpected_run",
    )
    check(
        all(Path(n).name == n and sha(root / n) == h for n, h in r["raw_sha256"].items()),
        "unsealed_raw",
    )
    log = (root / "server.log").read_text()

    def single(p):
        matches = re.findall(p, log)
        check(len(matches) == 1, "nonunique_marker_" + p)
        return matches[0]

    hits, misses, cpu, uploaded = single(
        r"ubatch <= 8: hits = (\d+), misses = (\d+) \((\d+) on the CPU\), "
        r"hit rate = [\d.]+%, uploaded = ([\d.]+) MiB"
    )
    hits, misses, cpu = int(hits), int(misses), int(cpu)
    src = HERE.parent / "stock_cache_evidence/receipt.json"
    header = json.loads(src.read_text())
    check(
        header["header_sha256"]
        == "ab931ef553e32c03e325cb2c7b322b2f52dcb231b6cda088797e515467cfec2c",
        "GGUF_header",
    )
    per_expert = header["all_expert_encoded_bytes_host_mapped"] // (36 * 128)
    bytes_sent = (misses - cpu) * per_expert
    check(f"{bytes_sent / 2**20:.2f}" == uploaded, "rounded_upload_conservation")
    return {
        "scope": "NATIVE_STARTUP_ONLY_NO_CLIENT_REQUEST",
        "raw_receipt_sha256": sha(receipt),
        "server_journal_sha256": r["raw_sha256"]["server.log"],
        "rs_seq": int(single(r"n_rs_seq\s+= (\d+)")),
        "gpu_model_mib": float(single(r"CUDA0 model buffer size =\s+([\d.]+) MiB")),
        "gpu_kv_buffers_mib": [
            float(v) for v in re.findall(r"CUDA0 KV buffer size =\s+([\d.]+) MiB", log)
        ],
        "gpu_moe_bank_mib": float(single(r"CUDA0 MoE cache size =\s+([\d.]+) MiB")),
        "gpu_compute_mib": float(single(r"CUDA0 compute buffer size =\s+([\d.]+) MiB")),
        "ubatch_le_8": {
            "hits": hits,
            "misses": misses,
            "misses_on_cpu": cpu,
            "reported_host_to_device_mib": float(uploaded),
            "derived_payload_bytes": bytes_sent,
            "payload_per_expert_bytes": per_expert,
        },
        "source_attribution": "common_context_can_seq_rm decodes two zero IDs before slot setup",
        "client_requests": r["http_requests_sent"],
        "explicit_warmup": r["warmup_requested"],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", required=True, type=Path)
    p.add_argument("--receipt", required=True, type=Path)
    p.add_argument("--new-output", required=True, type=Path)
    a = p.parse_args()
    result = extract(a.raw, a.receipt)
    with a.new_output.open("x") as f:
        f.write(json.dumps(result, indent=2, sort_keys=True) + "\n")

"""Rebuild the public decision from size- and digest-checked private receipts."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
MANIFEST = "b95c0b9632cb700ecf55922084af96818e93f34640e103af8f99ac470472f864"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def keep(row, names):
    return {name: row[name] for name in names.split()}


def run(root):
    path = root / "manifest.json"
    if sha(path) != MANIFEST:
        raise ValueError("archive manifest")
    files = json.loads(path.read_bytes())["files"]
    for key, (size, digest) in files.items():
        p = root / key
        if p.stat().st_size != size or sha(p) != digest:
            raise ValueError("archive member " + key)

    def load(name):
        return json.loads((root / name / "receipt.json").read_bytes())

    base, interval, comp, last, phys = [
        load(n) for n in ("renewal", "intervals", "composition", "deadlines", "physical")
    ]
    if (
        any(s["status"] != "TRACE_DERIVED" for s in (base, interval, comp, last))
        or phys["status"] != "MEASURED"
    ):
        raise ValueError("incomplete source")
    for name in ("renewal", "composition", "deadlines"):
        if load("check-" + name) != load(name):
            raise ValueError("standalone verification " + name)
    grade = run_path(HERE / "reader/physical.py")["grade"]
    plan = load("plan")
    stat = [plan["pack_stat"][k] for k in ("dev", "inode", "size_bytes", "mtime_ns", "ctime_ns")]
    if grade((root / "physical/stdout").read_text().splitlines(), stat) != phys["grade"]:
        raise ValueError("native output differs from receipt")
    clocks = {
        p: {
            g: {m: x["with_full_client_cost_ns"] for m, x in modes.items()}
            for g, modes in data.items()
        }
        for p, data in last["results"].items()
    }
    prior_witness = comp["results"]["critical_oracle"]["unchanged"]["copied"]
    return {
        "schema": "tesy.ready_renewal_decision.v1",
        "m3": "PARTIAL",
        "m4": "NOT_MET",
        "manifest_sha256": MANIFEST,
        "verified_archive_files": len(files),
        "verified_archive_bytes": sum(n for n, _ in files.values()),
        "source_receipts_sha256": {
            k: files[k + "/receipt.json"][1]
            for k in (
                "renewal",
                "intervals",
                "composition",
                "deadlines",
                "placement",
                "plan",
                "build",
                "c55",
                "physical",
            )
        },
        "t1": keep(interval, "t1_prefix_sha256 t1_reservations initial_secondary"),
        "routing_and_reservations": interval["routing_and_reservations"],
        "initial_screen": {
            "four_clocks_ns": {k: v["with_full_client_cost_ns"] for k, v in base["causal"].items()},
            "phase_and_tier": base["arms"]["P106"]["by_phase_and_tier"],
            "hindsight_paid_ns_before_all_consumers": prior_witness["with_full_client_cost_ns"],
            "intervals": {
                p: keep(v, "peak all_hits mandatory_hits_by_phase payload_by_tier")
                for p, v in interval["results"].items()
            },
        },
        "request": {
            **keep(
                last,
                "population mandatory eligible oracle_hits peak exchanges oracle_counts_by_tier "
                "witness_sha256 decisions read_service",
            ),
            "full_client_and_decode_ns": clocks,
            "p106_max_client_credit_ns": 646428255,
            "p106_placed_granted_direct_ns": {
                k: r["placed"]["direct"]["p106_full_grant_first_ns"]
                for k, r in last["results"].items()
            },
            "eligible_empty_cpu": comp["empty_graph"],
        },
        "physical": {
            **keep(
                phys,
                "commit tree kernel source_sha256 elf_sha256 protocol_sha256 plan_sha256 "
                "build_sha256 model_sha256 pack_sha256 child_wall_s whole_device_delta samples "
                "full_model_requests gpu_compute",
            ),
            "cgroup": keep(
                phys["final_cgroup"], "memory_peak memory_max swap_current swap_max events_local"
            ),
            **keep(
                phys["grade"],
                "decision local_gain blocks verified_component_hashes requested_bytes",
            ),
            "c55": keep(
                load("c55"),
                "span_s cpu_c_max gpu_c_max nvme_c_max gpu_driver gpu_name gpu_total_mib "
                "gpu_compute_max",
            ),
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    result = run(a.archive)
    a.new_output_dir.mkdir(mode=0o700)
    out = a.new_output_dir / "decision.json"
    temp = a.new_output_dir / ".pending"
    temp.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temp.rename(out)
    print(sha(out), out.name)

"""Bound the number of retained RAM records at fixed bytes using sealed, model-free inputs."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
INTEGRATED = HERE.parents[3]
QUAL = INTEGRATED.parents[1]
STUDY = QUAL / "mxfp4_spatial/evidence"
INPUTS = {
    "spatial": (
        STUDY / "receipt.json",
        "b40f8f9c97d5d4d5f50723bcc8cd4feb72e8ae0990c271de8477553f6977575c",
    ),
    "experts": (
        STUDY / "experts.json",
        "4a893ad344dc865f05bc292a3206aae9f655056746d7d3c61bbe7889c44eed98",
    ),
    "cache": (
        INTEGRATED / "host_cache/evidence/receipt.json",
        "a3398265b4bf33ed75f4898b346c2d9a988865cd5ca9cf98668826b52d41f700",
    ),
    "bank": (
        INTEGRATED / "t1_bank_capture/evidence/receipt.json",
        "6c444c8edf073416d539ca07e3ea19797f69e4b28ac881f0bafc76af6e749160",
    ),
    "source": (
        INTEGRATED / "t1_source_bank/receipt.json",
        "f2e1232d2466835931bdbe43420a61cb05fd0d473705c42ea5c5fbcabe87f049",
    ),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pinned(path, checksum):
    require(sha(path) == checksum, "input hash: " + path.name)
    return json.loads(path.read_bytes())


def capacity(budget, sample_total, extra_worker_bytes, descriptors, h):
    page = h["page"]
    raw = page(h["TRIPLE"])
    sample_size = 64

    def terms(k):
        index = h["additional"](k) - (k + 4) * raw
        return dict(
            resident_records=page((sample_total * k + sample_size - 1) // sample_size),
            raw_assembly=4 * raw,
            index=index,
            extra_codec_index=page(descriptors * k),
            extra_workers=extra_worker_bytes,
        )

    # Ignore the index for an upper estimate, then certify both adjacent integer capacities.
    k = (budget - 4 * raw - extra_worker_bytes) * sample_size // sample_total
    while k > 0 and sum(terms(k).values()) > budget:
        k -= 1
    require(k > 0, "empty envelope")
    costs = terms(k)
    used = sum(costs.values())
    next_used = sum(terms(k + 1).values())
    require(used <= budget < next_used, "maximal integer capacity")
    return dict(
        slots=k,
        cost=costs,
        total_bytes=used,
        unmatched_budget_bytes=budget - used,
        extra_bytes_needed_for_next=next_used - budget,
    )


def score():
    ds = {k: pinned(*source) for k, source in INPUTS.items()}
    host = INTEGRATED / "host_cache/screen.py"
    require(
        sha(host) == "79b212ddf51892875de96f5b96ce2e9e02dd60b5ce0709910f96ca395e10965c",
        "bank accounting code",
    )
    h = run_path(host)
    page, raw, payload = h["page"], h["page"](h["TRIPLE"]), h["TRIPLE"]
    calibration = [pinned(QUAL / path, digest) for path, (digest, _) in h["BASELINE"].items()]
    peaks = [report["maxima"]["cgroup_peak_bytes"] for report in calibration]
    cap = calibration[0]["cap_bytes"]
    require(cap == calibration[1]["r0_cgroup_cap_bytes"] == 20 * 2**30, "hard E20 caps")
    require(peaks == [x[1] for x in h["BASELINE"].values()], "calibration peaks")
    spatial, experts, cache, bank, source = (
        ds[k] for k in ("spatial", "experts", "cache", "bank", "source")
    )
    raw_total = len(experts) * raw
    ideal = sum(e["aligned_bytes_floor"] for e in experts)
    require(
        len({(x["layer"], x["expert"]) for x in experts}) == 64
        and all(len(e["matrices"]) == 3 for e in experts)
        and Counter(e["tier"] for e in experts) == {"CPU": 32, "CUDA": 32}
        and raw_total == spatial["sample"]["raw_aligned_bytes"]
        and ideal == spatial["sample"]["encoded_aligned_bytes_floor"]
        and spatial["expert_rows_sha256"] == INPUTS["experts"][1]
        and bank["capacity"] == 353
        and bank["extra_bytes"] == h["additional"](353) == source["bank_extra_bytes"],
        "geometry, sample or K353",
    )
    table_sum = sum(x["table_bytes_example_sparse"] for x in experts)
    require(table_sum == spatial["sample"]["table_bytes_example_sparse"], "table receipts")
    # Tables start after each aligned coded extent. Raw fallback needs no transmitted table.
    charged = sum(
        min(raw, page(e["aligned_bytes_floor"] + e["table_bytes_example_sparse"])) for e in experts
    )
    dense = spatial["dense_example_bytes_per_matrix"]
    # One raw output and count/frequency/cumulative arrays per worker, one matrix at a time.
    workspace = 4 * (raw + page(4 * dense))
    stop = h["STOP"]
    before = {
        "fixed_K353": bank["extra_bytes"],
        "historical_calibration": stop - max(peaks) - h["JOURNAL"],
        "part37_paired": stop - max(cache["off_peak"] + h["JOURNAL"], cache["on_peak"]),
        "part40_process": bank["headroom_bytes"],
    }
    require(
        before["part37_paired"] == cache["observed_memory_margin_bytes"]
        and before["part40_process"] == source["headroom_at_observed_peak"],
        "process headroom",
    )
    rows = {}
    for name, allowance in before.items():
        sidecar = 0 if name == "fixed_K353" else page(48800)
        # A fixed bank byte envelope is inclusive. A monitored process must remain below the stop.
        budget = allowance - sidecar - int(name != "fixed_K353")
        arms = {}
        for method, total, worker, desc in (
            ("raw", raw_total, 0, 0),
            ("ideal_spatial", ideal, 0, 0),
            ("charged_spatial", charged, workspace, 64),
            ("all_raw_in_codec", raw_total, workspace, 64),
        ):
            arms[method] = capacity(budget, total, worker, desc, h)
        rows[name] = dict(
            allowance_before_sidecar=allowance, sidecar_bytes=sidecar, budget=budget, arms=arms
        )
    k = rows["fixed_K353"]["arms"]["charged_spatial"]["slots"]
    extra = k - 353
    affected = source["t2"]["priority_source"]
    floor = affected["compulsory_disk_with_restore"]
    require(floor * payload == affected["floor_payload_bytes"], "compulsory T2 footprint")
    bounds = {}
    for denom, budget in source["conditional_volume_budgets"].items():
        gate = budget // payload
        needed = max(0, floor - gate)
        bounds[denom] = dict(
            payload_budget=budget,
            max_full_disk_reads=gate,
            needed_distinct_useful_extras=needed,
            best_distinct_floor=max(0, floor - max(0, extra)),
            possible_if_every_extra_useful=needed <= extra,
        )
    return dict(
        status="CONDITIONAL_CAPACITY_SCREEN",
        protocol_sha256=sha(HERE / "protocol.md"),
        program_sha256=sha(Path(__file__)),
        input_sha256={k: v[1] for k, v in INPUTS.items()},
        raw_record_bytes=raw,
        payload_bytes=payload,
        modeled_cap_bytes=cap,
        stop_bytes=stop,
        calibration_peaks=peaks,
        pfj_allowance_bytes=h["JOURNAL"],
        part37_off_on_peaks=[cache["off_peak"], cache["on_peak"]],
        part40_peak=stop - before["part40_process"],
        sample=dict(
            raw=raw_total,
            ideal_floor=ideal,
            sparse_tables=table_sum,
            charged_records=charged,
            additional_worker_bytes=workspace,
            dense_frequency_bytes_per_matrix=dense,
        ),
        envelopes=rows,
        prospective=dict(k=k, extra_records=extra, source_K353_floor=floor, by_denominator=bounds),
        gpu_calls=0,
        model_forwards=0,
        weight_bytes_read=0,
        raw_journal_bytes_read=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = score()
    except (KeyError, ValueError, OSError) as e:
        result = {"status": "FAIL_PRESERVED", "reason": str(e)}
    tmp = a.new_output_dir / "receipt.tmp"
    tmp.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))

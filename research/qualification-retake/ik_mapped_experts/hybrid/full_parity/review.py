"""Reopen both instrumented C110 bank arms, raw reference rows and phase counters."""

import argparse
import hashlib
import json
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
GRADE = run_path(str(HERE / "grade.py"))
RUN = run_path(str(HERE / "admission/run.py"))
need = GRADE["need"]
ROOT_SHA = "1d18c701fa45e8fac072ff73059f7f2415a765e0ff4e6247ceee5d9947c2747e"
# Frozen io.stat device of this family's nvme0n1 namespace.
MODEL_DEVICE = "259:0"
ACKS = "ELCPTF"


def checked(path, digest):
    data = GRADE["CPU"]["pinned"](path, digest)
    return json.loads(data)


def counter_delta(after, before):
    need(type(after) is int and type(before) is int and after >= before >= 0, "counter reset")
    return after - before


def by_phase(journal, arm):
    samples = [json.loads(line) for line in journal.read_text().splitlines()]
    need(
        samples[0]["phase"] == "before_launch"
        and samples[-1]["phase"] == "exit"
        and all(a["monotonic_ns"] < b["monotonic_ns"] for a, b in pairwise(samples)),
        "monitor endpoints or clock",
    )
    markers = [s for s in samples if s["phase"] not in ("before_launch", "running", "exit")]
    need([s["phase"] for s in markers] == list(ACKS), "missing or repeated monitor boundary")
    cuts = {s["phase"]: s["data"] for s in markers}
    ack = arm["ack_elapsed_s"]
    need(set(ack) == set(ACKS) and all(ack[a] < ack[b] for a, b in pairwise(ACKS)), "ACKs")
    total = counter_delta(samples[-1]["disk_read_sectors"], samples[0]["data"]["disk_read_sectors"])
    need(512 * total == arm["namespace_read_bytes"], "whole-device read counter")
    phases = {}
    for phase, left, right in (("prefill", "C", "P"), ("teacher", "P", "T")):
        x, y = cuts[left], cuts[right]
        first, last = x["cgroup"], y["cgroup"]
        phases[phase] = dict(
            ack_interval_s=round(ack[right] - ack[left], 6),
            nvme_namespace_read_B=512
            * counter_delta(y["disk_read_sectors"], x["disk_read_sectors"]),
            scope_nvme_read_B=counter_delta(
                y["io"][MODEL_DEVICE]["rbytes"], x["io"][MODEL_DEVICE]["rbytes"]
            ),
            pid_read_B=counter_delta(y["proc"]["read_bytes"], x["proc"]["read_bytes"]),
            scope_refault_file_pages=counter_delta(
                last["memory_stat"]["workingset_refault_file"],
                first["memory_stat"]["workingset_refault_file"],
            ),
            scope_memory_high_events=counter_delta(
                last["events_local"]["high"], first["events_local"]["high"]
            ),
        )
    return phases


def serial(obj):
    # The original JSON receipts serialize integer position keys as strings.
    return json.loads(json.dumps(obj))


def review(a):
    r = checked(a.family / "receipt.json", ROOT_SHA)
    need(r["model_starts"] == 2 and r["http_requests"] == 0, "original family")
    ref = GRADE["C"]["references"](a.c110_parent, a.stock_file, a.cpu_d0, a.cpu_d1)
    need(
        {
            k: {str(p): hashlib.sha256(v).hexdigest() for p, v in rows.items()}
            for k, rows in ref.items()
        }
        == r["reference_sha256"],
        "independent reference identities",
    )
    grades, arms = {}, {}
    for mode in RUN["MODES"]:
        folder = a.family / mode
        arm = checked(folder / "receipt.json", r["arms"][mode]["receipt_sha256"])
        need(
            r["arms"][mode]["status"] == arm["status"] == "PASS_IK_GPU_BANK_ARM"
            and arm["mode"] == mode
            and arm["model_starts"] == 1
            and arm["returncode"] == arm["swap_peak"] == 0
            and arm["restored"]
            and arm["child_gone"]
            and RUN["inventory"](folder) == arm["raw_sha256"],
            "arm identity, output inventory or cleanup",
        )
        g = GRADE["check_arm"](
            mode,
            (folder / "raw/stdout").read_text(),
            (folder / "raw/stderr").read_text(),
            folder / "native",
            a.plan,
        )
        rc = GRADE["against_references"](folder / "native", g, ref)
        need(serial(g) == arm["grade"] and serial(rc) == arm["reference_contrasts"], "regraded arm")
        grades[mode] = g
        phases = by_phase(folder / "raw/monitor.jsonl", arm)
        for phase, service in g["service_by_phase"].items():
            phases[phase].update(service)
        arms[mode] = dict(
            receipt_sha256=r["arms"][mode]["receipt_sha256"],
            phases=phases,
            gpu_matrix_ops=g["consumer_ops"] // 2,
            bias_sources=g["bias_sources"],
            startup_matrix_h2d_B=g["expert_startup_h2d_bytes"],
            logits_sha256=g["logits_sha256"],
            entry_peak_exit_vram_MiB=[
                arm[k] for k in ("entry_vram_mib", "peak_vram_mib_sampled", "exit_vram_mib")
            ],
            lifetime_s=round(arm["elapsed_s"], 6),
            namespace_read_B=arm["namespace_read_bytes"],
            cleanup_ack_interval_s=round(arm["ack_elapsed_s"]["F"] - arm["ack_elapsed_s"]["T"], 6),
            swap_peak_B=arm["swap_peak"],
            references={
                k: dict(
                    status=v["status"],
                    changed_words=[v["rows"][p]["changed_words"] for p in (15, 16)],
                )
                for k, v in rc.items()
            },
        )
    pair = GRADE["check_pair"](
        a.family / "BANK288/native",
        grades["BANK288"],
        a.family / "BANK161/native",
        grades["BANK161"],
    )
    need(serial(pair) == r["pair"] and pair["status"] == r["status"], "paired verdict")
    return dict(
        status=pair["status"],
        physical_sha256=ROOT_SHA,
        commit=r["commit"],
        tree=r["tree"],
        model_sha256=r["model_sha256"],
        client_sha256=r["client_sha256"],
        dso_sha256=r["dso_sha256"],
        resource_policy_sha256=r["resource_policy_sha256"],
        cgroup_contract=r["cgroup_contract"],
        model_starts_original=r["model_starts"],
        model_starts_review=0,
        http_requests=0,
        placements=pair["placements"],
        changed_words=[pair["rows"][p]["changed_words"] for p in (15, 16)],
        greedy=[pair["rows"][p]["candidate"]["top5"][0] for p in (15, 16)],
        arms=arms,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in (
        "family",
        "plan",
        "c110-parent",
        "stock-file",
        "cpu-d0",
        "cpu-d1",
        "new-output-dir",
    ):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    out = args.new_output_dir
    out.mkdir(mode=0o700)
    try:
        result = review(args)
    except Exception as exc:
        result = {"status": "FAIL_PRESERVED", "reason": str(exc)}
    with (out / "review.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")

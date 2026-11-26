"""Independently price adjacent physical A/B pairs from immutable operator receipts."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
M = run_path(str(HERE / "run.py"))
G, need, sha, save = (M[k] for k in ("G", "need", "sha", "save"))
ARMS = {
    "ABBA": "95c07e8e9a0f3b0c5d0ae895da3b82e374a9f5d3afaf3ad5702c5f90835d42ea",
    "BAAB": "a6bd788b780186a8565559dd73574c5527137bd32e90b7334c76a333f928f072",
}


def review(inputs, agenda):
    source = G["read"](agenda / "result.json", M["SLOTS"])
    allowances = {
        k: v["free"]["signed_time_budget_s"]
        for k, v in source["pricing"].items()
        if k.startswith("context_filter")
    }
    rows, processes = [], []
    for (order, pin), root in zip(ARMS.items(), inputs, strict=True):
        r = G["read"](root / "result.json", pin)
        need(
            r["status"] == "PASS_PAIRED_COPY_OPERATOR"
            and r["order"] == order
            and r["schedule_sha256"] == M["SLOTS"]
            and r["window_sha256"] == M["WINDOW"]
            and r["protocol_sha256"] == M["METHOD"]
            and r["exact_components_per_arm"] == 105
            and r["one_byte_negative"] == [34, 2]
            and r["provider_pins"] == M["PINS"]
            and r["model_starts"] == r["requests"] == 0,
            "physical arm",
        )
        phases = [
            "before",
            "allocated",
            *[f"arm-{i}-{when}" for i in range(4) for when in ("start", "end")],
            "cleanup",
        ]
        samples = [json.loads((root / (k + ".json")).read_bytes()) for k in phases]
        need(
            max(v["limits"]["memory.peak"] for v in samples) == r["peak_cgroup_B"]
            and max(v["gpu"]["used_mib"] for v in samples) == r["maximum_gpu_used_MiB"]
            and not any(v["limits"]["memory.swap.current"] for v in samples),
            "independent telemetry",
        )
        energy = {}
        for name, initial in r["energy_first"].items():
            last = r["energy_last"][name]
            need(last["max_uj"] == initial["max_uj"], "energy domain")
            energy[name] = (last["uj"] - initial["uj"]) % last["max_uj"]
        processes.append(
            dict(
                order=order,
                sha256=pin,
                wall_s=r["wall_s"],
                peak_cgroup_B=r["peak_cgroup_B"],
                gpu_used_MiB=r["maximum_gpu_used_MiB"],
                cpu_c=r["maximum_cpu_c"],
                gpu_c=r["maximum_gpu_c"],
                provider_count=len(r["observed_executable_files"]),
                energy_by_domain_uj=energy,
            )
        )
        for i, a in enumerate(r["arms"]):
            need(
                a == json.loads((root / f"arm-{i}.json").read_bytes())
                and a["mode"] == order[i]
                and 0 < sum(a["transfer_site_ns"].values()) <= a["wall_ns"],
                "timed row",
            )
        for i in (0, 2):
            pair = {x["mode"]: x for x in r["arms"][i : i + 2]}
            a, b = pair["A"], pair["B"]
            delta = b["wall_ns"] - a["wall_ns"]
            rows.append(
                dict(
                    order=order[i : i + 2],
                    A_ns=a["wall_ns"],
                    B_ns=b["wall_ns"],
                    increment_ns=delta,
                    by_tier_increment_ns={
                        k: b["transfer_site_ns"][k] - v for k, v in a["transfer_site_ns"].items()
                    },
                    residual_budget_s={k: v - delta / 1e9 for k, v in allowances.items()},
                    partial_saving_s_at_rate=source["aligned_reads_avoided_bytes"] / 4_500_000_000
                    - delta / 1e9,
                )
            )
        if len(processes) == 1:
            first = r
        else:
            for k in (
                "commit",
                "tree",
                "provider_pins",
                "observed_executable_files",
                "expected_digest",
                "explicit_device_B",
                "explicit_host_component_B",
            ):
                need(first[k] == r[k], "independent process identity: " + k)
    return dict(
        status="MEASURED_PAIRED_OPERATOR_COST",
        program_commit=r["commit"],
        program_tree=r["tree"],
        model_starts=0,
        requests=0,
        target_payloads=105,
        schedule_sha256=M["SLOTS"],
        protocol_sha256=M["METHOD"],
        expected_payload_digest=r["expected_digest"],
        explicit_device_B=r["explicit_device_B"],
        explicit_host_component_B=r["explicit_host_component_B"],
        pairs=rows,
        processes=processes,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("abba", "baab", "schedule", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = review([a.abba, a.baab], a.schedule)
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", error=f"{type(exc).__name__}: {exc}")
    save(a.new_output_dir / "result.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")

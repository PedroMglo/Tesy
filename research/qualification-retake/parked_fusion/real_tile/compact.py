"""Independently read back C266 outputs, native witnesses and the historical C118 window."""

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILE_SHA = "3e3039e0f9f6b4277f604a7cc631858a10f0b1892cf3d95993af36e569160551"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def verify_resources(p, root, top, c55_dir, prior, repo):
    sys.path.insert(0, str(repo / "tools"))
    import c118_start_inventory as inv
    import host_resource_policy as policy

    need = p.need
    c55 = prior.sealed_json(c55_dir / "receipt.json", top["c55_sha256"])
    pol = prior.sealed_json(c55_dir / "resource-policy.json", c55["canonical_policy_sha256"])
    need(
        pol == policy.derive_policy(snapshot=pol["snapshot"])
        and c55["status"] == "PASS_RESOURCE_WINDOW_ONLY",
        "C55 policy",
    )
    prior.sealed_file(c55_dir / "samples.jsonl", c55["window_sha256"])
    c118 = top["c118"]
    unit = top["unit"]
    need(
        re.fullmatch(r"tesy-[a-z0-9-]+", unit)
        and top["cap_bytes"] == 4 << 30
        and top["stop_bytes"] == 7 << 29,
        "scope identity",
    )
    path = root / "raw" / (unit + ".start-inventory.jsonl")
    power = {k: pol["power"][k] for k in ("source", "profile")}
    inv.require_inventory(
        root,
        unit,
        c118 | {"path": str(path)},
        policy=pol,
        cap_bytes=top["cap_bytes"],
        expected_power=power,
        now=dt.datetime.fromisoformat(top["arms"][0]["started_utc"]),
    )
    monitor = root / "raw/samples.jsonl"
    prior.sealed_file(monitor, top["monitor_sha256"])
    samples = [json.loads(line) for line in monitor.read_bytes().splitlines()]
    need(len(samples) == top["monitor_samples"] >= 2, "sampling coverage")
    limits = policy.freeze_protocol_resource_limits(
        pol, cgroup_memory_max_bytes=top["cap_bytes"], start_mode="CAPACITY_ADMISSION_START"
    )
    guard = policy.RuntimeGuard({"resources": limits, "limits": {}}, samples[0]["cgroup"])
    for s in samples:
        cg = s["cgroup"]
        need(
            not s["compute_pids"]
            and 0 <= s["gap_s"] <= 3
            and s["elapsed_s"] < 720
            and cg["memory_peak"] <= top["peak_bytes"]
            and cg["path"].endswith("/" + unit + ".scope")
            and not any(cg["events"][k] for k in ("high", "max", "oom", "oom_kill"))
            and not guard.check(s),
            "monitor sample",
        )
    final = top["cgroup_final"]
    need(
        final["path"] == samples[0]["cgroup"]["path"]
        and final["memory_max"] == top["cap_bytes"]
        and final["memory_peak"] == top["peak_bytes"] < top["stop_bytes"]
        and top["elapsed_s"] < 720
        and not any(final["events"][k] for k in ("high", "max", "oom", "oom_kill"))
        and top["child_processes_at_cleanup"]
        == top["swap_peak_bytes"]
        == top["swap_max_bytes"]
        == final["swap_current"]
        == final["swap_max"]
        == 0,
        "cleanup or resource limit",
    )
    return {
        "c118": {k: c118[k] for k in ("duration_s", "sample_count", "sha256")},
        "gpu_peak_mib": max(s["gpu"]["used_mib"] for s in samples),
        "cpu_peak_c": max(s["thermal"]["cpu_tctl_c"] for s in samples),
    }


def verify(a):
    repo = a.repo.resolve()
    study = Path("research/qualification-retake/parked_fusion/real_tile")
    q = (repo / study).parents[1]
    path = repo / study / "profile.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != PROFILE_SHA:
        raise ValueError("unrecognised physical verifier")
    p = module("fusion_real_profile", path)
    mm, c, prior, svc = p.modules()
    top = prior.sealed_json(a.raw_root / "receipt.json", a.receipt_sha256)
    need = p.need
    success = top["status"] == p.PASS
    need(success or top["status"] == "FAIL_PRESERVED", "terminal status")
    modes = p.MODES
    arms = top["arms"]
    need(
        len(arms) <= len(modes) and [x["mode"] for x in arms] == list(modes[: len(arms)]),
        "arm order",
    )
    out = {
        "status": top["status"],
        "decision": "INCONCLUSIVE",
        "terminal_sha256": a.receipt_sha256,
        "not_run": list(modes[len(arms) :]),
        "arms": [],
    }

    def git(*args):
        return subprocess.check_output(["/usr/bin/git", "--no-optional-locks", "-C", repo, *args])

    if "commit" in top:
        h = top["commit"]
        need(
            re.fullmatch("[a-f0-9]{40}", h)
            and git("rev-parse", h + "^{tree}").decode().strip() == top["tree"],
            "tree identity",
        )
        need(
            top["source_sha256"].keys() == {"profile.py", "protocol.md"}
            and all(
                svc.frozen(repo, repo / study / n, h) == v for n, v in top["source_sha256"].items()
            )
            and top["supervisor_sha256"] == PROFILE_SHA == top["source_sha256"]["profile.py"],
            "supervisor provenance",
        )
        out.update(
            {
                k: top[k]
                for k in (
                    "commit",
                    "tree",
                    "source_sha256",
                    "build_sha256",
                    "executable_sha256",
                    "numerical_receipt_sha256",
                )
            }
        )
        build = prior.sealed_json(a.build_dir / "receipt.json", top["build_sha256"])
        need(
            build["status"] == "PASS_C291_FUSION_COUNTER_CLIENT_BUILD"
            and build["original_build_sha256"] == p.ORIGINAL_BUILD
            and top["numerical_receipt_sha256"] == p.NUMERIC
            and build["binary_sha256"]
            == top["executable_sha256"]
            == prior.sha(a.build_dir / "suffix-layer")
            and build["worker_commit"] == c.WORKER
            and build["worker_tree"] == c.TREE
            and top["candidate_cpu_sha256"] == p.CANDIDATE
            and top["reference_sha256"] == mm.REFERENCE
            and top["parent_profile_sha256"] == p.MMID,
            "build identity",
        )
        git("merge-base", "--is-ancestor", build["commit"], h)
        for n, v in build["sources"].items():
            need(
                svc.frozen(repo, repo / study / n, build["commit"])
                == v
                == svc.frozen(repo, repo / study / n, h),
                "client source",
            )
    if not success:
        need(top["decision"] == "INCONCLUSIVE" and top.get("reason"), "failure closure")
        out["failure_stage"] = "execution_or_validation"
    ref = prior.sealed_json(q / "cpu0_suffix/physical-r01/receipt.json", mm.REFERENCE)
    if "input_sha256" in top:
        prior_result = prior.sealed_json(
            q / "packed_real_layer/physical-r01/receipt.json", svc.PRIOR_RESULT
        )
        need(
            top["input_sha256"] == prior_result["preparation_sha256"]
            and top["pack_sha256"] == prior_result["pack_sha256"]
            and top["gguf_opened_by_family"] is False,
            "input provenance",
        )
    if arms:
        with (a.input_dir / "ffn_moe_out-0.bin").open("rb") as f:
            f.seek(p.ROW_BYTES)
            gold = f.read(p.ROW_BYTES)
        need(hashlib.sha256(gold).hexdigest() == c.GOLD, "C266 complete numerical gold")
    pids = set()
    verdict = None
    total_bytes = service_bytes = 0
    for i, row in enumerate(arms):
        mode = modes[i]
        folder = a.raw_root / f"{i:02d}-{mode}"
        need(
            row["run_index"] == i and json.loads((folder / "receipt.json").read_bytes()) == row,
            "independent arm receipt",
        )
        result = {k: row[k] for k in ("mode", "status", "child_started")}
        out["arms"].append(result)
        for name in ("stdout", "stderr"):
            if name + "_sha256" in row:
                prior.sealed_file(folder / name, row[name + "_sha256"])
                result[name + "_sha256"] = row[name + "_sha256"]
        if row["status"] == "FAIL_PRESERVED":
            need(not success and i == len(arms) - 1, "unqualified arm")
            break
        need(
            verdict is None and row["child_started"] is True and row["pid"] not in pids,
            "unexpected child or post-verdict work",
        )
        pids.add(row["pid"])
        labels = [
            line.removeprefix("PARKED_PROVIDERS ")
            for line in (folder / "stderr").read_text().splitlines()
            if line.startswith("PARKED_PROVIDERS ")
        ]
        need(len(labels) == 1, "counter marker count")
        marker = json.loads(labels[0])
        cpu = ref["provider_sha256"][prior.LIB_CODES["cpu"]] if mode == "ORIGINAL" else p.CANDIDATE
        expected = {"cpu": cpu, "base": ref["provider_sha256"][prior.LIB_CODES["base"]]}
        need(
            row["provider_sha256"] == expected and all(row[k] == marker[k] for k in p.COUNTER),
            "counter marker or recorded providers",
        )
        providers = {k: (Path(marker["providers"][k]), v) for k, v in expected.items()}
        delta = p.counter_gate(mode, marker, row["pid"], providers, prior.sha)
        need(
            row["kernel_env"]
            == {
                "TESY_CPU_SUFFIX": "OFF",
                "TESY_CPU_MMX_ALL_PARKED": (None, "0", "1", "1")[i],
                "TESY_CPU_PARKED_FUSION": (None, "0", "0", "1")[i],
            },
            "arm flags",
        )
        tile = folder / "native/tile.f32"
        prior.sealed_file(tile, row["tile_sha256"])
        bits = tile.read_bytes()
        mismatch = p.diff(gold, bits)
        need(
            mismatch == row["first_difference"]
            and len(bits) == row["tile_bytes"] == p.ROW_BYTES
            and all(row[k] == v for k, v in p.finiteness(bits).items()),
            "tile bits",
        )
        verdict = p.verdict(mode, delta, mismatch)
        total_bytes += len(bits)
        result.update(
            counter_delta=delta,
            tile_bytes=len(bits),
            tile_sha256=row["tile_sha256"],
            provider_sha256=expected,
            first_difference=mismatch,
        )
        if mismatch:
            need(
                row["status"] == "MISMATCH_IDENTIFIED"
                and row["returncode"] == 1
                and row["nonfinite_count"] == 0
                and "FAIL_C291_CPU0_TILE full FFN tile" in (folder / "stderr").read_text(),
                "unqualified mismatch",
            )
            continue
        native = json.loads((folder / "stdout").read_bytes())
        p.after_join(native, marker)
        fields = mm.native_row(prior, c, ref, native, providers, folder / "native", gold)
        need(
            row["status"] == "PASS_TILE"
            and row["returncode"] == 0
            and row["counter_after_join_verified"] is True
            and all(
                row[k] == v
                for k, v in fields.items()
                if k not in {"graph_ns", "suffix_ns", "start_ns", "end_ns", "return_ns"}
            ),
            "completed graph work",
        )
        result["counter_after_join_verified"] = True
        service_bytes += native["expected_pread_bytes"]
    if "monitor_sha256" in top and top["monitor_sha256"] and arms and success:
        out.update(verify_resources(p, a.raw_root, top, a.c55_dir, prior, repo))
    if success:
        need(
            "c118" in out
            and total_bytes == top["total_output_bytes"]
            and service_bytes == top["expected_aligned_service_bytes"]
            and top["complete_work_arms"] == sum(row["status"] == "PASS_TILE" for row in arms),
            "family conservation",
        )
        if verdict is None:
            need(
                len(arms) == 4 and service_bytes == 264437760 and total_bytes == 1474560,
                "complete family",
            )
            verdict = "GO_TIMING_FIXTURE"
        need(verdict == top["decision"], "recomputed verdict")
        out["decision"] = verdict
    for k in (
        "input_sha256",
        "pack_sha256",
        "c55_sha256",
        "peak_bytes",
        "swap_peak_bytes",
        "child_processes_at_cleanup",
        "monitor_sha256",
        "monitor_samples",
        "elapsed_s",
        "expected_aligned_service_bytes",
        "total_output_bytes",
    ):
        if k in top:
            out[k] = top[k]
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for n in ("repo", "raw-root", "build-dir", "input-dir", "c55-dir", "new-output-dir"):
        parser.add_argument("--" + n, required=True, type=Path)
    parser.add_argument("--receipt-sha256", required=True)
    args = parser.parse_args()
    data = verify(args)
    args.new_output_dir.mkdir(mode=0o700)
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(data, sort_keys=True, indent=2) + "\n"
    )
    print(data["status"], data["decision"])

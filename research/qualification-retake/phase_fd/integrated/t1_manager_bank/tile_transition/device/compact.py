"""Independently bind each complete FFN, C291 transition and PID-qualified service window."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
b = run_path(str(HERE / "build.py"))
sha, need = b["sha"], b["need"]
validate = run_path(str(HERE / "review.py"))["check_child"]
previous = run_path(str(b["PRIOR"] / "review.py"))
ARMS = ("reference", "disk", "bank", "broken")


def pinned(path, expected):
    need(sha(path) == expected, "input hash " + path.name)
    return json.loads(path.read_bytes())


def resources(root, arm, family, summary, policy):
    inv = json.loads((root / (arm + "-inventory.json")).read_bytes())
    name = family["unit"] + "-" + arm
    source = root / "raw" / (name + ".start-inventory.jsonl")
    need(sha(source) == summary["start_inventory_sha256"] == inv["sha256"], "C118 identity")
    logs = root / "raw" / (arm + ".monitor.jsonl")
    need(sha(logs) == summary["monitor_sha256"], "service monitor identity")
    service = previous["lines"](logs)
    kw = {
        "policy": policy,
        "cap_bytes": 2**31,
        "expected_power": {"source": "AC", "profile": "performance"},
    }
    previous["c118"].require_inventory(
        root, name, inv | {"path": str(source)}, **kw, now=datetime.fromisoformat(service[0]["utc"])
    )
    inv_rows = previous["lines"](source)
    need(
        len(inv_rows) == summary["inventory_samples"]
        and len(service) == summary["service_samples"]
        and summary["wall_s"] < 60,
        "sample coverage",
    )
    need(
        [x["phase"] for x in service if x["phase"] != "periodic"]
        == ["entry", "active", "finish", "after_exit"],
        "owner transitions",
    )
    for s in service:
        obs = s["observation"]
        phase = s["phase"]
        owners = obs["gpu_owners"]
        allowed = [summary["pid"]]
        if phase in ("entry", "after_exit"):
            need(owners == [], "unowned boundary")
        elif phase in ("active", "finish") or (phase == "periodic" and s["stage"] == 2):
            need(owners == allowed, "exclusive child")
        else:
            need(owners in ([], allowed), "no foreign owner")
        need(
            obs["gpu"]["used_mib"] < 1536
            and s["peak_bytes"] <= family["peak_bytes"] < 1856 * 2**20
            and all(obs["power"][k] == v for k, v in kw["expected_power"].items())
            and obs["thermal"]["cpu_tctl_c"] < policy["cpu"]["warning_c"]
            and obs["gpu"]["temperature_c"] < policy["gpu"]["warning_c"]
            and all(
                v["warning_c"] is None
                or obs["thermal"]["nvme_composite_by_sensor"][v["sensor"]] < v["warning_c"]
                for v in policy["nvme"]
            ),
            "resources",
        )
    all_obs = [s["observation"] for s in inv_rows + service]
    return {
        "inventory_samples": len(inv_rows),
        "inventory_s": inv["duration_s"],
        "service_samples": len(service),
        "child_wall_s": summary["wall_s"],
        "gpu_used_mib_by_handoff": {
            s["phase"]: s["observation"]["gpu"]["used_mib"]
            for s in service
            if s["phase"] != "periodic"
        },
        "peak_gpu_mib_observed": max(x["gpu"]["used_mib"] for x in all_obs),
        "cpu_max_c": max(x["thermal"]["cpu_tctl_c"] for x in all_obs),
        "gpu_max_c": max(x["gpu"]["temperature_c"] for x in all_obs),
        "nvme_max_c": max(max(x["thermal"]["nvme_composite_by_sensor"].values()) for x in all_obs),
    }


def review(a):
    r = pinned(a.family / "receipt.json", a.receipt_sha256)
    need(
        r["status"] == "PASS_C291_TILE_TRANSITION_CUDA_FAMILY"
        and r["pack_cleaned"] is True
        and r["scope_cap"] == 2**31
        and r["model_forwards"] == 0,
        "closed family",
    )
    build = pinned(a.build / "receipt.json", r["build_sha256"])
    need(
        build["status"] == "PASS_TILE_CUDA_BUILD_ONLY"
        and build["commit"] == r["commit"]
        and build["tree"] == r["tree"],
        "build revision",
    )
    need(
        sha(a.build / "device") == build["binary_sha256"]
        and sha(a.build / "device.cpp")
        == build["source_sha256"]
        == hashlib.sha256(b["source"]()).hexdigest()
        and sha(a.build / "allowed.tsv") == build["allow_sha256"],
        "reproduced native source",
    )
    gate = pinned(a.c55, r["c55_sha256"])
    need(
        gate["status"] == "PASS_RESOURCE_WINDOW_ONLY" and not gate["reason"],
        "resource admission",
    )
    policy = pinned(a.c55.with_name("resource-policy.json"), gate["canonical_policy_sha256"])
    gold = pinned(a.family / "gold.json", r["gold_sha256"])
    # Recover the frozen allowed paths without requiring that the reader has these DSOs installed.
    paths = {}
    for line in (a.build / "allowed.tsv").read_text().splitlines():
        file = Path(line.split(maxsplit=3)[3])
        paths[file.name] = file
    for lib in (
        "libggml-cpu.so.0",
        "libggml-cuda.so.0",
        "libggml-base.so.0",
        "libcuda.so.1",
        "libcudart.so.13",
        "libcublas.so.13",
    ):
        prefix = "libcuda.so." if lib == "libcuda.so.1" else lib
        (resolved,) = [p for name, p in paths.items() if name.startswith(prefix)]
        paths[lib] = resolved
    arms = {}
    for arm in ARMS:
        x = r["arms"][arm]
        d = a.family / arm
        need(
            x["child_launches"] == 1
            and {p.name: {"bytes": p.stat().st_size, "sha256": sha(p)} for p in d.iterdir()}
            == x["files"],
            "every child artifact",
        )
        raw = pinned(d / "raw.json", x["raw_sha256"])
        align = raw["offset_alignment"]
        need(type(align) is int and align > 0, "FD alignment")
        request_bytes = ((3 * gold["slab"] + align - 1) // align) * align
        need(
            previous["device"]["verify_maps"](d, paths) == x["providers"]
            and sha(a.family / "raw" / (arm + ".stdout")) == x["stdout_sha256"]
            and sha(a.family / "raw" / (arm + ".stderr")) == x["stderr_sha256"]
            and raw["pack_sha256"] == gold["pack_sha256"]
            and raw["pack_proof_bytes"] == 2 * gold["pack_bytes"]
            and raw["read_extent"] == request_bytes,
            "provider closure, process streams or checked FD",
        )
        grade = validate(arm, d, a.family / "reference", raw, gold)
        need(
            grade == x["device"] and grade["transport"] == r["verified"][arm] == x["manager"],
            "same arm oracle",
        )
        arms[arm] = dict(
            grade,
            resources=resources(a.family, arm, r, x, policy),
            raw_sha256=x["raw_sha256"],
            operator_rows=raw["operator_rows"],
        )
    return dict(
        status=r["status"],
        receipt_sha256=a.receipt_sha256,
        build_sha256=r["build_sha256"],
        binary_sha256=build["binary_sha256"],
        commit=r["commit"],
        tree=r["tree"],
        protocol_sha256=build["protocol_sha256"],
        source_sha256=build["source_sha256"],
        c55_sha256=r["c55_sha256"],
        cpu_receipt_sha256=r["cpu_receipt_sha256"],
        arms=arms,
        pack_bytes=gold["pack_bytes"],
        scope_peak_bytes=r["peak_bytes"],
        family_wall_s=r["family_wall_s"],
        model_forwards=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("family", "build", "c55", "new-output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--receipt-sha256", required=True)
    a = p.parse_args()
    a.new_output.mkdir(mode=0o700)
    try:
        out = review(a)
    except (ValueError, OSError, KeyError) as exc:
        (a.new_output / "receipt.json").write_text(
            json.dumps({"status": "FAIL_PRESERVED", "reason": str(exc)}) + "\n"
        )
        raise
    tmp = a.new_output / "receipt.tmp"
    tmp.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(a.new_output / "receipt.json")

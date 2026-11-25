"""Offline independent review of the preserved R02 postflight failure."""

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RUN = run_path(HERE / "run.py")
sha, need, pre, old, qual = (RUN[k] for k in ("sha", "need", "PRE", "OLD", "QUAL"))
R02 = "5b9dfecec28619ae502916a58db82ffd480f9f8f94818b7210e127808a7f09e1"
mon = run_path(HERE / "monitor.py")["monitoring"]


def evaluate(a):
    inp = a.family.resolve()
    cold = run_path(RUN["INT"] / "cold_read_fixture/runner.py")
    io, inv, load = cold["io"], cold["c135"], cold["load"]
    family = load(inp / "receipt.json", R02)
    need(
        family["status"] == "FAIL_PRESERVED"
        and family["reason"] == "KeyError: 'gpu_owners'"
        and family["commit"] == "59a44f433c12854a67cc2dfa848291b93ee9f618",
        "R02 preserved provenance",
    )
    prior = load(a.prior, RUN["PRIOR"])
    need(family["provider"] == prior["provider"] and family["model_forwards"] == 0, "NVML evidence")
    gate = load(a.c55, family["c55_sha256"])
    policy = load(a.c55.with_name("resource-policy.json"), gate["canonical_policy_sha256"])
    need(
        gate["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and policy == io.derive_policy(snapshot=policy["snapshot"]),
        "C55 policy",
    )
    resolved, files = pre["providers"](a.map)
    need(sha(a.map) == family["map_sha256"], "original loader map")
    pre["verify_files"](resolved, files)
    b, p = family["build"], family["process"]
    for name, digest in [
        ("device", "binary_sha256"),
        ("device.cpp", "generated_sha256"),
        ("allowed.tsv", "allowed_sha256"),
        ("loader.json", "loader_sha256"),
    ]:
        need(sha(inp / name) == b[digest], "build " + name)
    need(
        sha(inp / "raw/alias.stdout") == p["stdout_sha256"]
        and RUN["parse_epochs"](inp / "raw/alias.stdout", "alias", resolved) == p["journal"],
        "native report",
    )
    need(old["verify_maps"](inp / "alias", resolved) == p["providers"], "four VMA tables")
    obs = mon(inp / "raw/alias.monitor.jsonl", p["monitor_sha256"])
    need(
        len(obs) == p["service_samples"] and obs[-1]["elapsed_s"] <= p["wall_s"] < 30,
        "native budget",
    )
    for v in obs:
        io.validate_sample(
            v["observation"], policy=policy, cap_bytes=2**31, expected_power=inv.POWER
        )
    invrec = json.loads((inp / "alias-inventory.json").read_bytes())
    rid = invrec["run_id"]
    need("/" not in rid and "\\" not in rid and rid.endswith("-alias"), "C118 identity")
    rel = Path("raw") / (rid + ".start-inventory.jsonl")
    need(
        Path(invrec["path"]).parts[-2:] == rel.parts
        and sha(inp / rel) == p["start_inventory_sha256"] == invrec["sha256"],
        "C118 raw",
    )
    historical = dict(invrec, path=str(inp / rel))
    now = datetime.fromisoformat(obs[0]["utc"])
    age = (now - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(0 <= age < 3300, "contemporaneous C55 at entry")
    n = inv.require_inventory(
        inp, rid, historical, policy=policy, cap_bytes=2**31, expected_power=inv.POWER, now=now
    )
    need(
        n == p["inventory_samples"] and historical["duration_s"] == p["inventory_s"],
        "all C118 rows",
    )
    proof = RUN["REVIEW"]["review"](inp / "alias")
    need(proof == family["numbers"], "complete arrays vs references and observed failures")
    nbytes = sum(f.stat().st_size for f in inp.rglob("*") if not f.is_symlink() and f.is_file())
    need(nbytes < 32 << 20 and family["family_wall_s"] < 240, "output and wall budget")
    return dict(
        status="REPRODUCED_MIXED_CPU_MAPPED_NUMERICS_AND_RECORDED_RESOURCES",
        family_status=family["status"],
        family_sha256=R02,
        review_commit=subprocess.check_output(
            ["git", "-C", HERE, "rev-parse", "HEAD"], text=True
        ).strip(),
        postflight_sha256=sha(HERE / "postflight.md"),
        c55_sha256=family["c55_sha256"],
        c118_samples=n,
        c118_s=p["inventory_s"],
        model_forwards=0,
        process_completed=True,
        drained=True,
        entry_and_exit_gpu_owners=0,
        stage_gpu_used_mib=[v["observation"]["gpu"]["used_mib"] for v in obs],
        max_cgroup_peak_captured=max(v["peak_bytes"] for v in obs),
        cgroup_peak_at_scope_extinction=None,
        observed_max_tctl_c=max(v["observation"]["thermal"]["cpu_tctl_c"] for v in obs),
        observed_max_gpu_c=max(v["observation"]["gpu"]["temperature_c"] for v in obs),
        observed_max_nvme_c=max(
            max(v["observation"]["thermal"]["nvme_composite_by_sensor"].values()) for v in obs
        ),
        raw_sha256={
            str(f.relative_to(inp)): sha(f)
            for f in sorted([*sorted((inp / "raw").glob("*")), *sorted((inp / "alias").glob("*"))])
            if f.is_file()
        },
        raw_total_bytes=nbytes,
        proof=proof,
        journal=p["journal"],
        review_gpu_calls=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "map", "prior", "c55", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        need(
            not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]), "clean audit"
        )
        value = evaluate(a)
    except Exception as e:
        value = {"status": "FAIL_PRESERVED", "reason": f"{type(e).__name__}: {e}"}
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n"
    )
    print(value["status"], value.get("reason", ""))
    return int(value["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

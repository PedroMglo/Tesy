"""Reopen a closed ik capacity run, keeping its own frozen grade and resource gates."""

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CAPACITY = HERE.parent
IK = CAPACITY.parents[1]
REVIEW = run_path(str(CAPACITY.parent / "device/review.py"))
need, sha, bound = REVIEW["need"], REVIEW["digest"], REVIEW["bound"]
PASS = "PASS_IK_REAL_CAPACITY_NO_FORWARD"
FIRST = "35abb80c85446c4754b6602fb258d2a0841021e8524290ab48d2ecd4ec9bbd00"


def mappings(folder, model, inode):
    records = {}
    for cut in ("load", "context", "freed"):
        spans = []
        for line in (folder / (cut + ".maps")).read_text().splitlines():
            f = line.split(maxsplit=5)
            if len(f) != 6 or f[-1] != model:
                continue
            a, b = (int(x, 16) for x in f[0].split("-"))
            need(int(f[4]) == inode and f[1] == "r--s" and a < b, "GGUF mapping")
            spans.append((a, b, int(f[2], 16), f[3]))
        records[cut] = spans
    need(
        records["load"] and records["load"] == records["context"] and not records["freed"],
        "VMA lifecycle",
    )
    return records


def census(text, grade, plan, maps):
    # The R01 grader inlined the same interval walk before its placement test.
    check = CAPACITY / "grade.py"
    need(
        sha(check) == "6707f9f3597001aad04da091c3c987f836ce42454d07cefb74feba451143e71a",
        "offline interval checker drift",
    )
    coverage = run_path(str(check))["check_device_upload"]
    rows = text.splitlines()
    tensors = grade["tensor_plan"](plan)
    totals, sent = grade["controlled_transfers"](rows, tensors)
    counts, sizes = Counter(), Counter()
    seen, biases, uploads = set(), set(), set()
    memory = {}
    for line in rows:
        if line.startswith("MEMORY "):
            name, *v = line[7:].split("\t")
            fields = ("device", "model", "context", "compute", "mmproj", "total", "free")
            need(name not in memory, "duplicate breakdown")
            memory[name] = dict(zip(fields, map(int, v), strict=True))
        if not line.startswith("PLACE "):
            continue
        _, name, typ, nb, host, off, addr, tier = line.split()
        pos, size, kind = tensors[name]
        off, addr = int(off), int(addr)
        need(name not in seen and int(nb) == size and int(typ) == kind, "tensor census")
        seen.add(name)
        if host == "1":
            need(
                tier == "CPU"
                and off == pos
                and any(
                    lo <= addr and addr + size <= hi and fo + addr - lo == off
                    for lo, hi, fo, _ in maps["load"]
                ),
                "CPU view not in original GGUF",
            )
            role = (
                "matrix"
                if name.endswith("_exps.weight")
                else ("bias_first_lookup" if name.endswith("_exps.bias") else "other")
            )
            counts[role + "_CPU"] += 1
            sizes[role + "_CPU"] += size
        else:
            need(host == "0" and tier == "CUDA0" and off == -1, "CUDA tensor identity")
            coverage(sent[name], addr, size, name)
            counts["first_lookup_CUDA"] += 1
            sizes["first_lookup_CUDA"] += size
        if name.endswith("_exps.bias"):
            parts = sent[name]
            need(parts, "bias upload absent")
            dest = parts[0][2]
            coverage(parts, dest, size, name)
            if host == "1":
                need(dest != addr, "bias destination is first CPU view")
                counts["bias_upload_distinct_from_first_CPU"] += 1
            need(name not in biases and dest not in uploads, "duplicate bias destination")
            biases.add(name)
            uploads.add(dest)
            sizes["bias_upload"] += size
    need(
        seen == set(tensors) and len(biases) == len(uploads) == 108 and counts["matrix_CPU"] == 108,
        "incomplete matrix/bias evidence",
    )
    need(set(memory) == {"Host", "CUDA0"}, "memory devices")
    need(
        [s for s in rows if s.startswith("CONTEXT ")] == ["CONTEXT 8192 1 256 32 0 0"]
        and [s for s in rows if s.startswith("KV_CELLS ")] == ["KV_CELLS 8192"]
        and [s for s in rows if s.startswith("STATUS ")]
        == ["STATUS COMPLETED_IK_CAPACITY_ZERO_FORWARD"],
        "native endpoint",
    )
    return dict(
        first_lookup_counts=dict(counts),
        bytes=dict(sizes),
        copy_or_memset_request_bytes=dict(totals),
        memory=memory,
        set_calls=sum(s.startswith("SET ") for s in rows),
        copy_calls=sum(s.startswith("COPY ") for s in rows),
        matrix_H2D_bytes=0,
        matrix_registrations=0,
        graph_submissions=0,
        context_bias_instances=sum(s.startswith("BIAS_INSTANCE ") for s in rows),
        mmap_ranges={k: len(v) for k, v in maps.items()},
    )


def resources(folder, c55, r, api):
    s, stock = api["S"], api["stock"]
    inv, pid = r["c118"], r["pid"]
    at = datetime.fromisoformat(inv["last_utc"])
    witness = bound(c55 / "receipt.json", r["c55_sha256"])
    authority = s["AUTH"]
    _, policy, _ = authority["window_authority"](
        c55 / "receipt.json", r["c55_sha256"], authority["select"](witness), now=at
    )
    limits = stock.policy_api.freeze_protocol_resource_limits(
        policy,
        cgroup_memory_max_bytes=s["CAP"],
        start_mode="CAPACITY_ADMISSION_START",
        execution_class="FILE_PAGING",
    )
    need(r["cgroup_contract"] == limits["cgroup"], "cgroup contract")
    rid = r["unit"]
    ip = folder / "raw" / (rid + ".start-inventory.jsonl")
    stock.c118.require_inventory(
        folder,
        rid,
        inv | {"path": str(ip)},
        policy=policy,
        cap_bytes=s["CAP"],
        expected_power={k: policy["power"][k] for k in ("source", "profile")},
        now=at,
    )
    guard = stock.policy_api.RuntimeGuard({"limits": {}, "resources": limits}, r["cgroup_initial"])
    rows = REVIEW["lines"](folder / "raw/monitor.jsonl")
    phases = [x["phase"] for x in rows]
    need(
        phases[0] == "before_launch"
        and phases[-1] == "exit"
        and tuple(x for x in phases if x not in ("before_launch", "running", "exit"))
        == tuple("ELCF"),
        "handoff order",
    )
    times = [x["monotonic_ns"] for x in rows]
    need(all(b > a for a, b in pairwise(times)), "monitor clock")
    marks, cut, used = r["ack_elapsed_s"], {}, []
    for x in rows:
        tag, d = x["phase"], x["data"]
        used.append(d["gpu"]["used_mib"])
        if "owner_observation" in x:
            o = x["owner_observation"]
            api["owner"](tag, o["gpu_owners"], pid)
            used.append(o["gpu"]["used_mib"])
            need(guard.check(d) is None, "resource guard " + tag)
        elif tag == "exit":
            api["owner"](tag, x["gpu_owners"], pid)
        elif tag != "before_launch":
            raise ValueError("missing owner witness")
        if tag != "running":
            cut[tag] = d["gpu"]["used_mib"]
    api["vram_gate"](used, policy["gpu"]["memory_stop_total_mib"])
    need(
        max(used) == r["peak_vram_mib_sampled"]
        and cut["before_launch"] == r["entry_vram_mib"]
        and cut["exit"] == r["exit_vram_mib"] <= cut["before_launch"] + 64,
        "VRAM restoration",
    )
    need(
        0 <= marks["E"] < marks["L"] <= 180
        and marks["L"] < marks["C"] <= marks["L"] + 90
        and marks["C"] < marks["F"] <= r["elapsed_s"] <= marks["C"] + 10,
        "deadlines",
    )
    cg = r["cgroup_end"]
    need(
        r["swap_peak"] == 0
        and cg["swap_current"] == cg["swap_max"] == 0
        and cg["events_local"]["oom"] == cg["events_local"]["oom_kill"] == 0,
        "swap/oom",
    )
    base = rows[0]["data"]
    last = rows[-1]
    captured = (last["disk_read_sectors"] - base["disk_read_sectors"]) * 512
    need(
        0 <= captured <= r["namespace_read_bytes"] < r["namespace_read_stop_bytes"],
        "namespace read counter",
    )
    last_io = stock.io_delta(base["io"], last["io"])
    need(
        all(v["rbytes"] <= r["cgroup_io"][dev]["rbytes"] for dev, v in last_io.items()), "scope IO"
    )
    return dict(
        c118_s=inv["duration_s"],
        c118_samples=inv["sample_count"],
        ack_elapsed_s=marks,
        through_child_exit_s=r["elapsed_s"],
        entry_load_s=marks["L"] - marks["E"],
        load_context_s=marks["C"] - marks["L"],
        context_free_s=marks["F"] - marks["C"],
        vram_mib_at_handoff=cut,
        vram_mib_max_sampled=max(used),
        telemetry_samples=len(rows),
        peak_cgroup_B=cg["memory_peak"],
        cgroup_high_B=cg["memory_high"],
        cgroup_max_B=cg["memory_max"],
        cgroup_io=r["cgroup_io"],
        namespace_read_B=r["namespace_read_bytes"],
        namespace_read_B_through_final_sample=captured,
        cgroup_events_local=cg["events_local"],
        child_gone=r["child_gone"],
        restored=r["restored"],
        returncode=r["returncode"],
        swap_peak_B=r["swap_peak"],
    )


def review(a):
    r = bound(a.family / "receipt.json", a.family_sha256)
    authority = a.freeze / "research/qualification-retake/ik_mapped_experts"
    for key, h in r["sources"].items():
        need(sha(authority / key) == h, "freeze mismatch " + key)
    api = run_path(str(authority / "hybrid/capacity/admission/run.py"))
    official = run_path(str(authority / "hybrid/capacity/grade.py"))
    prepared = bound(a.prepared / "receipt.json", r["prepared_sha256"])
    need(
        prepared["status"] == "PREPARED_ONLY"
        and all(
            prepared[k] == r[k]
            for k in (
                "commit",
                "tree",
                "sources",
                "providers",
                "monitor_provider",
                "model_stat",
                "client_sha256",
                "plan_sha256",
                "model_sha256",
                "resource_policy_sha256",
                "c55_sha256",
                "tiny_sha256",
                "input_sha256",
            )
        ),
        "preparation",
    )
    b = bound(a.client / "receipt.json", r["client_sha256"])
    i = bound(a.inputs / "receipt.json", r["input_sha256"])
    need(
        sha(a.client / b["binary"]) == b["binary_sha256"] == r["executable_sha256"]
        and b["dso_build_sha256"] == r["dso_sha256"]
        and i["plan_sha256"] == sha(a.inputs / "plan.tsv") == r["plan_sha256"]
        and i["model_sha256"] == r["model_sha256"],
        "client/plan",
    )
    raw = REVIEW["identity_tree"](a.family, r)
    need(
        r["model_starts"] == 1
        and r["http_requests"] == 0
        and r["child_gone"]
        and r["restored"]
        and r["returncode"] == 0
        and r["energy_j"] is None,
        "process lifecycle",
    )
    native = a.family / "native"
    text = (a.family / "raw/stdout").read_text()
    stderr = (a.family / "raw/stderr").read_text()
    need(
        "UNEXPECTED_GRAPH_SUBMISSION" not in stderr
        and re.findall(r"(\d+) layer\(s\), (\d+) expert slots", stderr) == [("36", "288")]
        and re.findall(r"active MoE cache policy: (\w+)", stderr) == ["classlru"],
        "bank",
    )
    plan = a.inputs / "plan.tsv"
    maps = mappings(native, i["model"], r["model_stat"][1])
    partial = census(text, official, plan, maps)
    try:
        result = official["check_arm"](text, stderr, native, plan)
    except ValueError as e:
        need(
            a.family_sha256 == FIRST
            and r["status"] == "FAIL_PRESERVED"
            and r["reason"] == "ValueError: " + str(e)
            and str(e) == "bias/output placement"
            and partial["context_bias_instances"] == 0,
            "unexpected native grade failure",
        )
        verdict = "REPRODUCED_R01_PLACEMENT_FAILURE"
    else:
        need(
            r["status"] == PASS
            and result == r["grade"]
            and result["status"] == "PASS_IK_CAPACITY_ZERO_FORWARD"
            and result["matrix_mmap_count"]
            == result["bias_cuda_count"]
            == result["bias_mapped_twins"]
            == 108
            and partial["context_bias_instances"] == 216
            and result["memory_breakdown"] == partial["memory"],
            "capacity grade drift",
        )
        verdict = "REPRODUCED_ZERO_FORWARD_CAPACITY"
    return dict(
        status=verdict,
        family_status=r["status"],
        reason=r.get("reason"),
        family_sha256=a.family_sha256,
        raw_sha256=raw,
        resources=resources(a.family, a.c55, r, api),
        geometry=partial,
        sources={
            k: r[k]
            for k in (
                "commit",
                "client_sha256",
                "input_sha256",
                "plan_sha256",
                "dso_sha256",
                "prepared_sha256",
                "tiny_sha256",
                "c55_sha256",
            )
        },
        reviewer_sha256=sha(HERE / "review.py"),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "freeze", "prepared", "client", "inputs", "c55", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    out = a.new_output_dir / "receipt.json"
    try:
        report = review(a)
    except Exception as exc:
        out.write_text(json.dumps(dict(status="FAIL_PRESERVED", reason=str(exc))) + "\n")
        raise
    out.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n")
    print(report["status"], sha(out))

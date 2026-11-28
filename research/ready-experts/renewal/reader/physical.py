"""Check exact payload, shape, resource and ordering contracts around the native reader."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
BUILD = run_path(HERE / "build.py")
sha = BUILD["sha"]
PAIR = HERE.parents[2] / "qualification-retake/nvme_admission/io_pair"
TARGET_PPM = 731182
STAT = ("dev", "inode", "size_bytes", "mtime_ns", "ctime_ns")


def need(ok, why):
    if not ok:
        raise ValueError(why)


def grade(lines, identity):
    need(
        len(lines) == 122
        and lines[0].split() == ["fd", *map(str, identity)]
        and lines[-1] == "drained",
        "descriptor identity, output extent or drain",
    )
    arms = []
    for arm in range(30):
        mode = ("PRE", "RING")[arm % 2 if arm < 16 else 1 - arm % 2]
        costs = []
        for group in range(4):
            a, m, g, n, t = lines[1 + 4 * arm + group].split()
            need(
                (int(a), m, int(g), int(n)) == (arm, mode, group, 4 if group < 2 else 1)
                and int(t) > 0,
                "shape, arm or clock",
            )
            costs.append(int(t))
        arms.append({"mode": mode, "group_ns": costs})
    blocks = []
    for block in range(2):
        rows = {}
        for label, portion in (("quartets", slice(0, 2)), ("singletons", slice(2, 4))):
            pre, ring = [], []
            for pair in range(7):
                start = 2 + 14 * block + pair * 2
                times = {x["mode"]: sum(x["group_ns"][portion]) for x in arms[start : start + 2]}
                pre.append(times["PRE"])
                ring.append(times["RING"])
            # For seven pairs the middle rational ratio decides the exact inequality.
            wins = sum(r * 1_000_000 <= p * TARGET_PPM for p, r in zip(pre, ring, strict=True))
            rows[label] = {
                "pre_ns": pre,
                "ring_ns": ring,
                "median_saving_ns": median(a - b for a, b in zip(pre, ring, strict=True)),
                "median_ratio": median(b / a for a, b in zip(pre, ring, strict=True)),
                "reached_threshold": wins >= 4,
            }
        blocks.append(rows)
    pairs = [r for b in blocks for r in b.values()]
    decision = (
        "GO_SERVICE_PROFILE"
        if all(r["reached_threshold"] for r in pairs)
        else (
            "NO_GO_UNIFORM_CUT_THIS_FIXTURE"
            if all(not all(r["reached_threshold"] for r in b.values()) for b in blocks)
            else "INCONCLUSIVE"
        )
    )
    sign = (
        "POSITIVE_COMPONENT"
        if all(r["median_ratio"] < 1 for r in pairs)
        else "NO_GAIN"
        if all(r["median_ratio"] >= 1 for r in pairs)
        else "INCONCLUSIVE"
    )
    return {
        "blocks": blocks,
        "arms": arms,
        "decision": decision,
        "local_gain": sign,
        "verified_component_hashes": 30 * 10 * 3,
        "requested_bytes": 30 * 10 * 13221888,
    }


def run(a, receipt):
    sys.path.insert(0, str(PAIR))
    guards = run_path(PAIR / "run.py")
    commit, tree = BUILD["version"]()
    spec = json.loads((a.build / "receipt.json").read_bytes())
    plan = json.loads((a.plan / "receipt.json").read_bytes())
    c55 = json.loads((a.c55 / "receipt.json").read_bytes())
    need(
        spec["status"] == plan["status"] == "PASS"
        and (commit, tree) == (spec["commit"], spec["tree"])
        and sha(a.plan / "receipt.json") == a.plan_sha256
        and sha(a.build / "receipt.json") == a.build_sha256
        and sha(a.c55 / "receipt.json") == a.c55_sha256
        and plan["source_sha256"] == spec["sources"]["prepare.py"]
        and plan["method_sha256"] == spec["sources"]["protocol.md"]
        and sha(a.plan / "windows.tsv") == plan["plan_sha256"]
        and sha(a.build / "reader") == spec["elf_sha256"],
        "input or build authority",
    )
    for p, h in spec["libraries"].items():
        need(sha(p) == h, "runtime library changed")
    policy_path = a.c55 / "resource-policy.json"
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and c55["span_s"] >= 60
        and sha(policy_path) == c55["canonical_policy_sha256"],
        "60-second C55",
    )
    policy = json.loads(policy_path.read_bytes())
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(
        0 <= age <= 3600
        and policy == guards["derive_policy"](snapshot=policy["snapshot"])
        and guards["operational_session_ready"](policy)[0],
        "C55 resource authority",
    )
    pack = Path(plan["pack_path"]).resolve(strict=True)
    identity = [plan["pack_stat"][k] for k in STAT]
    need(guards["stat_id"](pack) == identity, "pack changed")
    disk = guards["disk"](pack, "nvme")
    receipt.update(
        commit=commit,
        tree=tree,
        build_sha256=a.build_sha256,
        plan_sha256=a.plan_sha256,
        c55_sha256=a.c55_sha256,
        pack_sha256=plan["pack_sha256"],
        model_sha256=plan["model_sha256"],
        source_sha256=sha(__file__),
        elf_sha256=spec["elf_sha256"],
        protocol_sha256=plan["method_sha256"],
        host=os.uname().nodename,
        kernel=os.uname().release,
        c55_age_s=age,
        policy_sha256=c55["canonical_policy_sha256"],
    )
    samples = []

    def sample():
        s = guards["monitor"](policy)
        with (a.new_output_dir / "samples.jsonl").open("a") as f:
            f.write(json.dumps(s, allow_nan=False) + "\n")
        samples.append(s)

    sample()
    counters = guards["diskstats"](disk)
    now = time.monotonic()
    cmd = [str(a.build / "reader"), str(pack), str(a.plan / "windows.tsv")]
    receipt["command"] = cmd
    with (
        (a.new_output_dir / "stdout").open("x") as stdout,
        (a.new_output_dir / "stderr").open("x") as stderr,
    ):
        proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr)
        try:
            while True:
                try:
                    code = proc.wait(timeout=0.75)
                    break
                except subprocess.TimeoutExpired:
                    sample()
                    need(time.monotonic() - now < 100, "child deadline")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
    receipt["child_wall_s"] = time.monotonic() - now
    after = guards["diskstats"](disk)
    receipt["whole_device_delta"] = {k: v - counters[k] for k, v in after.items()}
    sample()
    need(code == 0, "native reader: " + (a.new_output_dir / "stderr").read_text()[:150])
    need(guards["stat_id"](pack) == identity, "changed pack after run")
    receipt.update(
        grade=grade((a.new_output_dir / "stdout").read_text().splitlines(), identity),
        samples=len(samples),
        final_cgroup=guards["cgroup_state"](),
        gpu_compute=0,
        full_model_requests=0,
        status="MEASURED",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("plan", "build", "c55", "new-output-dir"):
        p.add_argument("--" + arg, type=lambda s: Path(s).resolve(), required=True)
    for name in ("plan", "build", "c55"):
        p.add_argument("--" + name + "-sha256", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    receipt = {"status": "FAIL_PRESERVED"}

    def expire(*_):
        raise TimeoutError("scope deadline")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(112)
    try:
        run(a, receipt)
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.SubprocessError) as e:
        receipt["reason"] = str(e)
    finally:
        signal.alarm(0)
        tmp = a.new_output_dir / ".pending"
        tmp.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n")
        tmp.rename(a.new_output_dir / "receipt.json")
    print(receipt["status"], receipt.get("reason", receipt.get("grade", {}).get("decision", "")))
    raise SystemExit(receipt["status"] != "MEASURED")

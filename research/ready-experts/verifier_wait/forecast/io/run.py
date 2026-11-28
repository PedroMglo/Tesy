"""Execute the enrolled QD4 pack replay in its resource-limited user scope."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(HERE / "grade.py")
M = G["M"]
need, load, sha, verified, save = (M[k] for k in ("need", "load", "sha", "verified", "save"))


def run(
    a,
    receipt,
    *,
    protocol=M["PROTOCOL"],
    source=HERE / "protocol.md",
    parse=G["parse"],
    maximum_bytes=126427693056,
    requested_records=None,
):
    old = run_path(M["R"] / "physical.py")
    sys.path.insert(0, str(old["PAIR"]))
    guards = run_path(old["PAIR"] / "run.py")
    commit, tree = M["B"]["version"]()
    plan = verified(a.plan / "receipt.json", a.plan_sha256)
    build = verified(a.build / "receipt.json", a.build_sha256)
    window = verified(a.c55 / "receipt.json", a.c55_sha256)
    need(
        all(
            r["status"] == "PASS"
            and (r["commit"], r["tree"], r["protocol"]) == (commit, tree, protocol)
            for r in (plan, build)
        )
        and sha(source) == protocol,
        "frozen preparation",
    )
    exe, windows = a.build / "reader", a.plan / "windows.tsv"
    need(
        sha(exe) == build["binary"]
        and sha(windows) == plan["windows"]
        and all(sha(p) == h for p, h in build["libraries"].items()),
        "binary, plan or library",
    )
    policy = verified(a.c55 / "resource-policy.json", window["canonical_policy_sha256"])
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(
        window["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and window["span_s"] >= 60
        and window["selected_stat"] == plan["model_stat"]
        and 0 <= age <= 3600
        and policy == guards["derive_policy"](snapshot=policy["snapshot"])
        and guards["operational_session_ready"](policy)[0],
        "resource window",
    )
    pack = Path(plan["pack_path"])
    need(
        guards["stat_id"](pack) == plan["pack_stat"]
        and guards["stat_id"](Path(plan["model_path"])) == plan["model_stat"],
        "model or pack",
    )
    disk = guards["disk"](pack, "nvme")
    cmd = [str(exe), str(pack), str(windows)]
    receipt.update(
        commit=commit,
        tree=tree,
        host=os.uname().nodename,
        kernel=os.uname().release,
        protocol=protocol,
        elf=build["binary"],
        model=plan["model"],
        pack=plan["pack"],
        index=plan["index"],
        plan_sha256=a.plan_sha256,
        build_sha256=a.build_sha256,
        c55_sha256=a.c55_sha256,
        c55_age_s=age,
        command=cmd,
        pack_stat=plan["pack_stat"],
        c55={
            k: window[k]
            for k in (
                "cpu",
                "gpu_name",
                "gpu_total_mib",
                "gpu_driver",
                "model_fs",
                "model_device",
                "gpu_compute_max",
                "concurrent",
                "nvme",
            )
        },
    )
    samples = []
    stamps = []

    def sample():
        stamp = time.monotonic()
        obs = guards["monitor"](policy)
        with (a.new_output_dir / "samples.jsonl").open("a") as f:
            f.write(json.dumps(obs, allow_nan=False) + "\n")
        samples.append(obs)
        if stamps:
            need(stamp - stamps[-1] < 3, "missing periodic telemetry")
        stamps.append(stamp)

    sample()
    before = guards["diskstats"](disk)
    begin = time.monotonic()
    with (
        (a.new_output_dir / "stdout").open("x") as out,
        (a.new_output_dir / "stderr").open("x") as err,
    ):
        proc = subprocess.Popen(cmd, stdout=out, stderr=err)
        try:
            while True:
                try:
                    code = proc.wait(timeout=0.65)
                    break
                except subprocess.TimeoutExpired:
                    sample()
                    need(time.monotonic() - begin < 134, "reader budget")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
    receipt["child_s"] = time.monotonic() - begin
    after = guards["diskstats"](disk)
    sample()
    need(code == 0, "native reader: " + (a.new_output_dir / "stderr").read_text()[:200])
    timing = parse((a.new_output_dir / "stdout").read_text().splitlines(), plan)
    records = (
        2 * sum(map(sum, plan["counts"])) + timing["parity_records"]
        if requested_records is None
        else requested_records(timing, plan)
    )
    need(isinstance(records, int) and records > 0, "requested record count")
    count = records * G["P"]["SIZE"]
    disk_delta = {k: v - before[k] for k, v in after.items()}
    need(
        count <= maximum_bytes and disk_delta["read_sectors_512B"] * 512 >= count,
        "requested volume or whole-device sector deficit",
    )
    need(guards["stat_id"](pack) == plan["pack_stat"], "changed pack after close")
    cg = guards["cgroup_state"]()
    observations = [s["observation"] for s in samples]
    thermal = [s["thermal"] for s in observations]
    receipt.update(
        timing=timing,
        requested_B=count,
        disk_delta=disk_delta,
        samples=len(samples),
        cpu_max_c=max(s["cpu_tctl_c"] for s in thermal),
        gpu_max_c=max(s["gpu"]["temperature_c"] for s in observations),
        nvme_max_c=max(max(s["nvme_composite_by_sensor"].values()) for s in thermal),
        max_sample_gap_s=max(b - a for a, b in pairwise(stamps)),
        cgroup=cg,
        samples_sha256=sha(a.new_output_dir / "samples.jsonl"),
        stdout_sha256=sha(a.new_output_dir / "stdout"),
        full_model_requests=0,
        status="MEASURED",
    )


def main(runner=run):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "plan", "c55", "new-output-dir"):
        p.add_argument("--" + name, required=True, type=lambda s: Path(s).resolve())
    for name in ("build", "plan", "c55"):
        p.add_argument("--" + name + "-sha256", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    receipt = dict(status="FAIL_PRESERVED")

    def timed_out(*_):
        raise TimeoutError("physical family deadline")

    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(144)
    try:
        runner(a, receipt)
    except Exception as exc:
        receipt["reason"] = str(exc)
    finally:
        signal.alarm(0)
        pending = a.new_output_dir / ".pending"
        save(pending, receipt)
        pending.rename(a.new_output_dir / "receipt.json")
    print(receipt["status"], receipt.get("reason", ""))
    raise SystemExit(receipt["status"] != "MEASURED")


if __name__ == "__main__":
    main()

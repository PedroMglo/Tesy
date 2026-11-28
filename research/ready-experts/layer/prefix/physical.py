"""Run both cuts through the same laptop C55/C118 and NVMe guards as the full-rank comparator."""

import argparse
import importlib.util
import json
import os
import signal
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
recipe = run_path(HERE / "build.py")
parent = recipe["parent"]
SUPERVISOR = "45011a17072f6c122d4ed146940aef3b59fdfac7c4ba50cfbe3b3560707e1f20"


def run(a, result):
    # The historical supervisor uses its own directory and grade callback as experiment parameters.
    # Load a private instance so its CPU/C118/process-tree/byte ceilings apply verbatim.
    script = parent.sealed(HERE.parent / "physical.py", SUPERVISOR)
    spec = importlib.util.spec_from_file_location("tesy_prefix_layer_supervisor", script)
    supervisor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(supervisor)
    supervisor.HERE = HERE
    supervisor.grade = run_path(HERE / "grade.py")["grade"]
    build = json.loads(parent.sealed(a.build_dir / "receipt.json", a.build_sha256).read_bytes())
    parent.check(
        build["variant"] == recipe["VARIANT"] and build["strong_source_sha256"] == recipe["STRONG"],
        "complete consumer build",
    )
    parent.sealed(HERE.parent / "native.cpp", recipe["STRONG"])
    rank = json.loads(
        parent.sealed(a.rank_dir / "receipt.json", supervisor.S["RANK_RECEIPT"]).read_bytes()
    )
    gold = rank["arm"]["rank"]["files_sha256"]
    files = [a.rank_dir / "ALIAS/rank" / name for name in gold]
    window = json.loads(parent.sealed(a.c55_receipt, a.c55_sha256).read_bytes())
    policy = json.loads(
        parent.sealed(
            a.c55_receipt.with_name("resource-policy.json"), window["canonical_policy_sha256"]
        ).read_bytes()
    )
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    parent.check(
        window["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not window["reason"]
        and 0 <= age <= 3600,
        "fresh admitted C55",
    )
    for f in files:
        parent.sealed(f, gold[f.name])
    result.update(
        c55_sha256=a.c55_sha256,
        c55_age_at_entry_s=age,
        prior_supervisor_sha256=SUPERVISOR,
        grader_sha256=parent.sha(HERE / "grade.py"),
        stage_authority=gold,
        unit=a.unit,
    )
    supervisor.run(a, result)
    for f in files:
        parent.sealed(f, gold[f.name])


def expire(*_):
    raise TimeoutError("bounded request deadline")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "old-build",
        "build-dir",
        "input-dir",
        "reference-dir",
        "rank-dir",
        "libs",
        "placement-receipt",
        "prestate-receipt",
        "c55-receipt",
        "new-output-dir",
    ):
        p.add_argument("--" + name, type=lambda s: Path(s).resolve(), required=True)
    for name in ("commit", "unit", "build-sha256", "c55-sha256"):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    result = dict(status="FAIL_PRESERVED", _tic=time.monotonic())
    signal.signal(signal.SIGALRM, expire)
    signal.alarm(360)
    try:
        run(a, result)
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=repr(exc))
    finally:
        signal.alarm(0)
        result["elapsed_s"] = time.monotonic() - result.pop("_tic")
        (a.new_output_dir / "receipt.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] != "MEASURED")

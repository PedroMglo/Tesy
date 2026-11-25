"""Run the isolated four-row kernel family on the sealed outputs of the one-row operator."""

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from decision import evaluate

HERE = Path(__file__).resolve().parent
# Both scripts are named run.py. Load the prior, tracked supervisor by its exact path.
spec = importlib.util.spec_from_file_location(
    "tesy_one_row_supervisor", HERE.parent / "mxfp4_vnni/run.py"
)
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
io = common.io
require = common.require
RUN_ID = "cpu-mxfp4-four-rows"
ACT = "cdba177b2040d9ea5672e29e18bb8ac95203a44ac45085c57bc791b73ebd2344"
ONE_ROW_RECEIPT = "32ef813a048c3444b169606a6a3df1a66bcdd2f6269f473f877e37d73bbc5e24"
INDEX = "f8961dcdaa58aa7774e63150b76d69add0dd080181493838528c8f36de543a57"


def reference(root, digest):
    receipt = root / "receipt.json"
    require(io.sha256(receipt) == digest == ONE_ROW_RECEIPT, "one-row receipt hash")
    prior = json.loads(receipt.read_text())
    require(
        prior["schema"] == "mxfp4-vnni-supervised-operator-v1"
        and prior["decision"] in ("GO_ROUTED_MMID_FIXTURE", "NO_GO_GLOBAL_KERNEL_PROMOTION")
        and len(prior["arms"]) == 24
        and prior["parity"] == {"real_rows": 23040, "synthetic_rows": 160, "quant_bytes": 3060}
        and prior["mapped_elf_sha256"]["r0"] == common.R0
        and prior["mapped_elf_sha256"]["base"] == common.BASE,
        "one-row numerical qualification",
    )
    inp = prior["inputs"]
    require(
        inp == json.loads((root / "inputs/inputs.json").read_text())
        and inp["status"] == "PASS_AUTHENTICATED_OPERATOR_INPUTS"
        and inp["source_fd_stable"]
        and inp["c290_index_sha256"] == INDEX
        and inp["original_gguf_sha256_previously_verified"] == io.TARGET
        and inp["activation_sha256"] == ACT
        and inp["ordered_experts"] == [28, 73, 46, 56]
        and len(inp["slabs"]) == 8,
        "inputs differ from one-row numerical receipt",
    )
    return {
        "weights.bin": (root / "inputs/weights.bin", 35251200, inp["weights_sha256"]),
        "activation.f32": (root / "inputs/activation.f32", 11520, ACT),
        "activation.q8": (
            root / "native/activation.q8",
            3060,
            prior["artifacts_sha256"]["activation.q8"],
        ),
        "gold.f32": (root / "native/gold.f32", 92160, prior["artifacts_sha256"]["gold.f32"]),
    }


def check_inputs(pinned):
    for label, (path, size, digest) in pinned.items():
        require(
            path.stat().st_size == size and io.sha256(path) == digest, "wrong reference " + label
        )


def execute(a, report):
    root = a.new_output_dir
    raw = root / "raw"
    raw.mkdir()
    commit, tree = subprocess.check_output(
        ["git", "-C", common.REPO, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    require(
        len(a.commit) == 40
        and commit == a.commit
        and not subprocess.check_output(["git", "-C", common.REPO, "status", "--porcelain"]),
        "clean frozen commit required",
    )
    report.update(
        commit=commit,
        tree=tree,
        protocol_sha256=io.sha256(HERE / "protocol.md"),
        cpu_cache=common.cache_inventory(),
        reference_receipt_sha256=a.reference_sha256,
    )
    pinned = reference(a.reference_root, a.reference_sha256)
    check_inputs(pinned)
    report["reference_files_sha256"] = {label: digest for label, (_, _, digest) in pinned.items()}
    policy = json.loads(a.policy.read_text())
    require(
        policy == io.derive_policy(snapshot=policy["snapshot"])
        and io.operational_session_ready(policy)[0],
        "C55 admission",
    )
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    require(0 <= age <= 3600, "same-hour C55 required")
    build = a.build_dir.resolve(strict=True)
    require(io.sha256(build / "build.json") == a.build_sha256, "build hash")
    b = json.loads((build / "build.json").read_text())
    require(
        b["status"] == "PASS_BUILD_FOUR_ROW_DISASSEMBLY"
        and b["ggml_cpu_sha256"] == common.R0
        and b["c_sha256"] == io.sha256(HERE / "four_rows.c"),
        "build/source contract",
    )
    report.update(
        c55_sha256=io.sha256(a.policy),
        c55_age_s_at_admission=age,
        build_receipt_sha256=a.build_sha256,
        clockbench_sha256=a.clockbench_sha256,
        abi_symbol="tesy_four_rows",
        gcc_sha256=b["gcc_sha256"],
    )
    libdir = a.lab.resolve(strict=True) / "backends/c269-layer-last-use/build-c269-cuda/bin"
    libs = {
        "clockbench": (a.clockbench.resolve(strict=True), a.clockbench_sha256),
        "r0": (libdir / "libggml-cpu.so.0.15.3", common.R0),
        "base": (libdir / "libggml-base.so.0.15.3", common.BASE),
    }
    for name in ("control", "separate", "shared"):
        libs[name] = (build / (name + ".so"), b["arms"][name]["sha256"])
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "HOME": str(root),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MALLOC_ARENA_MAX": "2",
        "LD_LIBRARY_PATH": str(libdir),
        "TESY_FOUR_REFERENCE_NATIVE": str((a.reference_root / "native").resolve(strict=True)),
    }
    native = root / "native"
    native.mkdir()
    with ExitStack() as stack:
        refs = {k: common.Reference(stack, p, h) for k, (p, h) in libs.items()}
        require(len({r.key for r in refs.values()}) == len(refs), "duplicate ELF identity")
        report["frozen_elf_sha256"] = {k: r.digest for k, r in refs.items()}
        conditions = dict(policy=policy, cap_bytes=common.CAP, expected_power=common.POWER)
        inv = common.collect(root, RUN_ID, **conditions, sample=lambda: common.observed(policy))
        io.save(root / "c118.json", inv)
        report["inventory"] = {k: v for k, v in inv.items() if k != "path"}
        report["c118_summary"] = common.summary(raw / (RUN_ID + ".start-inventory.jsonl"))
        cmd = [libs[k][0] for k in ("clockbench", "r0", "control", "separate", "shared")]
        cmd.extend([pinned["weights.bin"][0], pinned["activation.f32"][0], native])
        with (raw / "telemetry.jsonl").open("x") as log:
            common.require_inventory(root, RUN_ID, inv, **conditions, max_age_s=3)
            common.measured_child(cmd, "operator", env, raw, policy, report, log)
        report["mapped_elf_sha256"] = common.verified_maps((native / "maps.tsv").read_text(), refs)
    check_inputs(pinned)
    for label in ("activation.q8", "gold.f32"):
        _, size, digest = pinned[label]
        require(
            (native / label).stat().st_size == size and io.sha256(native / label) == digest,
            "independent reference mismatch: " + label,
        )
    (parity,) = common.tsv(native / "parity.tsv")
    parity = {k: int(v) for k, v in parity.items()}
    distinctive = parity.get("distinguishing_rows", 0)
    require(
        0 < distinctive <= 480
        and parity
        == {
            "real_rows": 23040,
            "shared_rows": 1600,
            "distinct_rows": 1600,
            "guarded_calls": 3840,
            "distinguishing_rows": distinctive,
            "odd_fma_rows": 4,
            "quant_bytes": 3060,
        },
        "incomplete parity",
    )
    arms = common.tsv(native / "arms.tsv")
    for arm in arms:
        for field in ("cpu", "arm", "rows", "repeats", "duration_ns"):
            arm[field] = int(arm[field])
    report.update(
        evaluate(arms),
        arms=arms,
        parity=parity,
        cgroup_peak_bytes=common.scope()["memory_peak"],
        run_summary=common.summary(raw / "telemetry.jsonl"),
        artifacts_sha256={p.name: io.sha256(p) for p in native.iterdir() if p.is_file()},
    )
    require(
        sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) < 199 * 2**20, "output budget"
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("lab", "policy", "reference-root", "build-dir", "clockbench", "new-output-dir"):
        cli.add_argument("--" + name, type=Path, required=True)
    for name in ("reference-sha256", "build-sha256", "clockbench-sha256", "commit"):
        cli.add_argument("--" + name, required=True)
    a = cli.parse_args()
    a.new_output_dir = a.new_output_dir.resolve()
    os.umask(0o077)
    a.new_output_dir.mkdir(exist_ok=False)
    report = {
        "schema": "mxfp4-four-row-kernel-v1",
        "decision": "FAIL_PRESERVED",
        "children": {},
        "gguf_logical_bytes_read": 0,
        "model_forwards": 0,
        "gpu_compute": 0,
    }
    start = time.monotonic()

    def expire(*_):
        raise TimeoutError("300 s family limit")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(300)
    try:
        execute(a, report)
    except Exception as error:
        report["decision"] = "FAIL_PRESERVED"
        report["reason"] = f"{type(error).__name__}: {error}"
        for p in (a.new_output_dir, a.build_dir, a.reference_root, a.clockbench.parent, a.lab):
            report["reason"] = report["reason"].replace(str(p), "<private>")
        for n in ("parity.tsv", "arms.tsv"):
            artifact = a.new_output_dir / "native" / n
            if artifact.exists():
                report[n + "_preserved_sha256"] = io.sha256(artifact)
    finally:
        signal.alarm(0)
    report["family_wall_s"] = time.monotonic() - start
    pending = a.new_output_dir / ".receipt.pending"
    io.save(pending, report)
    pending.rename(a.new_output_dir / "receipt.json")
    print(report["decision"])
    return int(report["decision"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

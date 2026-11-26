"""Verify the incomplete T1 stream, native failure, sampler prefix and cleanup offline."""

import argparse
import json
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
F = run_path(str(HERE / "family.py"))
T, C, need, sha = (F[k] for k in ("T", "F", "need", "sha"))
V = T["V"]
FAMILY = "8ded50541e00c395920eb5e690329ac5b923473b8e9b075dfb312af122aef2b7"
CLOSED = "59b9a64488a1032c0562a247b142fb2b0aa7caf9aef00ba018ebab3133c7721b"
STALL = "3bb1844458b35ea75830d80e7c9c93169ebb94cd9334130a3e5c598c90d22e6a"
ASSERT = b"GGML_ASSERT(q->ne[3] == 1 && k->ne[1] > 0 && (il != 25 || k->ne[1] == 256)) failed"


def review(a):
    root = a.family
    gate = F["G"]["read"](root / "receipt.json", FAMILY)
    need(
        {
            str(f.relative_to(root)): sha(f)
            for f in root.rglob("*")
            if f.is_file() and f != root / "receipt.json"
        }
        == gate["raw_sha256"]
        and gate["status"] == "FAIL_PRESERVED"
        and list(gate["arms"]) == ["ON"]
        and gate["model_starts"] == gate["started_requests"] == 1,
        "closed failed family",
    )
    arm = root / "ON"
    r = F["G"]["read"](arm / "receipt.json", gate["arms"]["ON"]["sha256"])
    evidence = F["read"](arm / "arm-inputs.json")
    preset = F["read"](arm / "preset.json")
    raw, unit = arm / "raw", preset["run_id"]
    launch = F["read"](raw / (unit + ".launch.json"))
    ident = launch["process_identity"]
    client = F["read"](arm / "client-receipt.json")
    events = [json.loads(x) for x in (raw / "T1-request.jsonl").read_bytes().splitlines()]
    need(
        client["status"] == "CLIENT_FAILED_PRESERVED"
        and not client["rows"]
        and events[-1]["kind"] == "REQUEST_TERMINAL"
        and not events[-1]["accepted"]
        and not (raw / "T2-input.json").exists()
        and not (raw / (unit + ".json")).exists(),
        "client or monitor completeness",
    )
    data = C["inputs"](SimpleNamespace(capture=a.capture, verified=a.verified))
    frozen = F["G"]["read"](a.plan / "receipt.json", F["PLAN_PIN"])
    plan = F["G"]["read"](a.plan / "r0.stdout", frozen["same_output_sha256"])
    b3 = next(step for step in plan["T1"] if step["proposal"])
    log = (raw / (unit + ".stderr")).read_bytes()
    samples = [ev[3] for _, owner, ev in V["events"](log) if owner == 0 and ev[0] == "sample"]
    dispatched = list(T["DRAFT"].finditer(log))
    pos = len(data["T1"]["prompt"]) + len(samples) - 1
    need(
        len(samples) == b3["at"] == 20
        and samples == data["T1"]["target"][:20]
        and len(dispatched) == 1
        and tuple(map(int, dispatched[0].groups()[4:]))
        == (0, samples[-1], pos, len(b3["proposal"]), pos)
        and log.count(b"n_outputs_max = 3") == 1
        and log.find(ASSERT, dispatched[0].end()) > 0
        and not T["ACCEPT"].search(log),
        "first failed block",
    )
    done = F["G"]["read"](a.closed / "receipt.json", CLOSED)
    wait = F["G"]["read"](a.stall / "observation.json", STALL)
    need(
        done["pid"] == ident["pid"]
        and done["signal"] == 6
        and done["process_gone"]
        and done["unit_end"] == "inactive"
        and done["port_18442_listeners"] == 0
        and wait["identity"] == ident
        and len(wait["samples"]) == 3
        and all(
            s["decoded"] == 20
            and s["accepted"] == 0
            and any(t["wchan"] == "do_coredump" for t in s["tasks"].values())
            for s in wait["samples"]
        ),
        "independent abort and closure",
    )
    inv = run_path(str(F["Q"] / "nvme_r0_gate/qualified_profile/compact.py"))["validate_inventory"](
        arm, unit, dict(native_explicit_env=evidence["env"]), launch
    )
    points = [json.loads(x) for x in (raw / (unit + ".samples.jsonl")).read_bytes().splitlines()]
    need(all(s["process_identity"] == ident for s in points), "telemetry owner")
    return dict(
        status="NO_GO_256_L25_ON_NATURAL_T1",
        scope="fixed-width binary",
        family_sha256=FAMILY,
        commit=r["commit"],
        protocol_sha256=F["METHOD"],
        arm_order=list(F["MODES"]),
        actual=["ON"],
        other_arms="NOT_RUN_AFTER_STOP",
        model_starts=1,
        started_requests=1,
        completed_requests=0,
        input_ids=len(data["T1"]["prompt"]),
        matching_generated_ids=len(samples),
        proposal_width=2,
        dispatch_position=pos,
        completed_blocks=0,
        signal=6,
        terminal_monitor="MISSING",
        client_status=client["status"],
        wall_s=gate["wall_s"],
        cpu_gpu_samples=len(points),
        last_sample_s=points[-1]["elapsed_s"],
        gpu_peak_MiB=max(s["gpu"]["used_mib"] for s in points),
        cgroup_observed_peak_B=max(s["cgroup"]["memory_peak"] for s in points),
        cgroup_observed_swap_max_B=max(s["cgroup"]["swap_current"] for s in points),
        verified_cleanup=True,
        first_final_s=None,
        valid_s=None,
        decode_tok_s=None,
        inventory=inv,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "capture", "verified", "plan", "stall", "closed", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    F["save"](a.new_output_dir / "result.json", review(a))

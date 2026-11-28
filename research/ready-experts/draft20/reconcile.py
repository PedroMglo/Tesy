"""Locate previously verified code blocks and check full residency within the same envelope."""

import argparse
import re
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CPU = HERE.parent / "cpu_wave"
SEL = run_path(CPU / "code_chat/price/selection/run.py")
need, sha, read, publish = (SEL[k] for k in ("need", "sha", "read", "publish"))


def hundredths(line, pattern):
    values = re.findall(pattern + r"\s*=\s*([0-9]+\.\d\d) MiB", line)
    need(len(values) == 1, pattern)
    return int(Decimal(values[0]) * 100)


def verify(a):
    study = read(a.study)
    source = study["evidence"]
    receipt = read(a.physical / "receipt.json")
    need(
        sha(a.physical / "receipt.json") == source["physical_sha256"]
        and sha(a.physical / "draft.stdout") == receipt["execution"]["stdout_sha256"]
        and sha(a.physical / "draft.stderr") == receipt["execution"]["stderr_sha256"],
        "draft price source",
    )
    raw = (a.physical / "draft.stdout").read_text().split("case code\n")[1]
    draft = {}
    for line in raw.splitlines():
        if line.startswith("block "):
            at, q1, q2, depth, *_ = map(int, line.split()[1:])
            need(at not in draft, "duplicate anchor")
            draft[at] = ([q1, q2], depth)
    need(
        [(k, v[1]) for k, v in draft.items()]
        == [(b[0], b[1]) for b in source["draft"]["code"]["blocks"]],
        "different physical draft",
    )
    old = read(CPU / "code_chat/price/result.json")
    need(
        sha(a.price / "receipt.json") == old["family_sha256"]
        and sha(a.lookup / "steps.json") == read(CPU / "code_chat/lookup.json")["steps_sha256"],
        "native 120B family",
    )
    steps = {r["at"]: r for r in read(a.lookup / "steps.json")["T2"] if r["proposal"]}
    need(len(steps) == 46 and len(draft) == 93, "opportunities")
    shared = sorted(steps.keys() & draft.keys())
    exact = [i for i in shared if steps[i]["proposal"] == draft[i][0]]
    witnessed = [i for i in exact if steps[i]["accepted"] == draft[i][1] == 2]
    need(
        all(steps[i]["accepted"] == draft[i][1] for i in exact),
        "equal inputs and differing target decision",
    )
    prices = []
    for arm in old["arms"][2:4]:
        need(arm["role"] == "ON", "previous verified-block target")
        control = source["clocks"]["code"][0]
        need(
            arm["trajectories"]["2"]["sampled_sha256"] == control["target_sha256"]
            and arm["turns"][1]["official_ids_sha256"] == control["prompt_sha256"],
            "different target prefix",
        )
        ticks = SEL["sampled"](a.price, arm)
        ns = [ticks[i + 2] - ticks[i - 1] for i in witnessed]
        rest = []
        for w in study["result"]["cases"]["code"]["arms"]:
            allocations = {}
            for label in ("first_final", "decode"):
                q = w[label]
                known = [
                    cost for i, cost in zip(witnessed, ns, strict=True) if i - 1 < q["cut_index"]
                ]
                missing = q["blocks"] - len(known)
                available = (
                    q["covered_native_ns"] - q["proposal_ns"] - q["prior_alignment_and_undo_ns"]
                )
                allocations[label] = dict(
                    missing=missing,
                    remaining_ns=available - sum(known),
                    max_mean_ns=(available - sum(known)) // missing,
                )
            rest.append(dict(W=w["W"], **allocations))
        prices.append(
            dict(
                arm=arm["folder"],
                native_intervals_ns=ns,
                total_ns=sum(ns),
                if_prior_intervals_transfer=rest,
            )
        )

    buffers = []
    for name, family, role, compact in (
        ("nominal", a.nominal, "ON", read(CPU / "decision.json")["client"]["receipt_sha256"]),
        ("code", a.code, "W", read(CPU / "code_chat/code-chat.json")["family_sha256"]),
    ):
        need(sha(family / "receipt.json") == compact, "W allocator family")
        arms = read(family / "receipt.json")["arms"]
        for i in (3, 4):
            trial = arms[i - 1]
            folder = family / (f"{i}-ON" if name == "nominal" else f"{i}W")
            need(
                trial["role"] == role
                and sha(folder / "session.json") == source["clocks"][name][i - 3]["session_sha256"],
                "W source session",
            )
            monitor = read(folder / "session.json")["monitor_sha256"]
            need(sha(folder / "raw" / (trial["unit"] + ".json")) == monitor, "W source monitor")
            log = folder / "raw" / (trial["unit"] + ".stderr")
            need(
                sha(log)
                == read(folder / "raw" / (trial["unit"] + ".json"))["output_sha256"][".stderr"],
                "W log",
            )
            lines = log.read_text(errors="replace")
            buffers.append(
                [
                    hundredths(lines, "CPU expert cache size"),
                    hundredths(lines, "CUDA0 expert cache size"),
                ]
            )
    need(len(set(tuple(b) for b in buffers)) == 1, "different primary allocations")
    draft_buffer = hundredths(
        (a.physical / "draft.stderr").read_text(), "CPU_Mapped model buffer size"
    )
    proof = read(a.physical / "provenance.json")
    need(
        sha(a.physical / "provenance.json") == receipt["provenance_sha256"]
        and sha(a.c55 / "receipt.json") == proof["c55_sha256"],
        "device budget",
    )
    win = read(a.c55 / "receipt.json")
    ram = win["r0_cap_bytes"] // 2**20
    vram = int(win["gpu_total_mib"])
    need(ram == 20480 and vram == 8188, "changed hardware envelope")
    cpu, gpu = buffers[0]
    # Each allocator prints two decimal places. Drop an entire hundredth from each.
    return dict(
        status="TRACE_DERIVED_SHARED_INPUTS_AND_CAPACITY",
        study_sha256=sha(a.study),
        prior_opportunities=len(steps),
        new_opportunities=len(draft),
        same_anchor=len(shared),
        same_two_proposed_ids=len(exact),
        directly_confirmed_both=witnessed,
        prices=prices,
        missing_direct_witness=len(draft) - len(witnessed),
        hundredths_MiB=dict(
            target_cpu_primary=cpu,
            target_gpu_primary=gpu,
            draft_cpu_buffer=draft_buffer,
            min_cpu_excess=cpu + draft_buffer - 2 - 100 * ram,
            min_combined_excess=cpu + gpu + draft_buffer - 3 - 100 * (ram + vram),
        ),
        RAM_cap_MiB=ram,
        GPU_total_MiB=vram,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "study",
        "physical",
        "lookup",
        "price",
        "c55",
        "nominal",
        "code",
        "new-output-dir",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = verify(a)
    except Exception as exc:
        publish(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
    publish(a.new_output_dir / "receipt.json", result)
    print(result["status"])

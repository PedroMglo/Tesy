"""Price the previously omitted last width-two proposal and permit EOG at every DAG edge."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "evidence-20261128-r01/study.json"
DP = run_path(HERE.parent / "frontier.py")


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def acquire(new, previous, study):
    rec = json.loads((new / "receipt.json").read_bytes())
    old = json.loads((previous / "receipt.json").read_bytes())
    need(
        rec["status"] == "MEASURED_20B_TERMINAL"
        and rec["execution"]["live_providers"]
        and sha(previous / "receipt.json") == study["evidence"]["physical_sha256"]
        and sha(new / "provenance.json") == rec["provenance_sha256"],
        "sealed processes",
    )
    for directory, receipt in ((new, rec), (previous, old)):
        need(
            sha(directory / "draft.stdout") == receipt["execution"]["stdout_sha256"],
            "changed logits witness",
        )
    source = json.loads((new / "provenance.json").read_bytes())
    need(
        source["input_sha256"] == study["evidence"]["inputs_sha256"] and rec["c118_s"] >= 60,
        "different trajectory",
    )
    raw = (new / "draft.stdout").read_text().splitlines()
    need(raw[0] == "vocabulary 201088" and raw[-1] == "done", "terminal execution")
    original = (previous / "draft.stdout").read_text().split("case code\n")[1]
    serial = [
        [int(r.split()[1]), int(r.split()[2])]
        for r in original.splitlines()
        if r.startswith("serial ")
    ]
    refs = [list(map(int, r.split()[1:])) for r in raw if r.startswith("reference ")]
    terminal = [list(map(int, r.split()[1:])) for r in raw if r.startswith("terminal ")]
    need(
        refs == serial and [i for i, _ in refs] == list(range(255)) and len(terminal) == 1,
        "full code reference",
    )
    q1, q2, n1, n2 = terminal[0]
    need(q1 == refs[-1][1] and 0 <= q2 < 201088 and min(n1, n2) > 0, "two real forwards")
    return dict(
        accepted_terminal=int(q1 == 200002),
        proposal_ns=[n1, n2],
        rows=len(refs),
        c118_s=rec["c118_s"],
        model_wall_s=rec["execution"]["wall_s"],
        cgroup_peak_B=rec["execution"]["peak_B"],
        max_swap_B=rec["execution"]["max_swap_B"],
        max_cpu_C=rec["execution"]["max_cpu_C"],
        max_gpu_C=rec["execution"]["max_gpu_C"],
        max_nvme_C=rec["execution"]["max_nvme_C"],
        gpu_total_MiB=rec["execution"]["max_gpu_MiB"],
        gpu_sampled_J=rec["execution"]["gpu_sampled_J"],
        gpu_covered_s=rec["execution"]["gpu_covered_s"],
        source_commit=source["commit"],
        source_tree=source["tree"],
        binary_sha256=source["binary_sha256"],
        c55_sha256=source["c55_sha256"],
        provenance_sha256=rec["provenance_sha256"],
        receipt_sha256=sha(new / "receipt.json"),
        hash_wall_s=rec["hash"]["wall_s"],
    )


def score(data, witness):
    s = data["evidence"]
    case = s["draft"]["code"]
    need(
        len(case["tail_ns"]) == 1
        and witness["rows"] == 255
        and int(case["serial_matches"][-1]) == witness["accepted_terminal"],
        "only one open terminal site",
    )
    n = len(case["blocks"]) + 1
    proposal = sum(b[2] + b[3] for b in case["blocks"]) + sum(witness["proposal_ns"])
    align = sum(b[4] + b[5] for b in case["blocks"])
    arms = []
    for w in s["clocks"]["code"]:
        v = (w["ticks_ns"][-1] - proposal - align) // n
        arms.append(dict(W=w["arm"], mean_target_ns_to_preserve_decode=v))
    nominal = dict(s["draft"]["nominal"], issue_through_eog=True)
    frontier = [
        {m: DP["frontier"](nominal, w, m) for m in ("perfect", "free", "paid")} | {"W": w["arm"]}
        for w in s["clocks"]["nominal"]
    ]
    return dict(
        code=dict(
            blocks=n,
            proposed=2 * n,
            accepted=sum(b[1] for b in case["blocks"]) + witness["accepted_terminal"],
            terminal_emitted=1,
            tail_serial=0,
            proposal_ns=proposal,
            alignment_before_end_ns=align,
            nominal_fixed_schedule_unchanged=True,
            arms=arms,
        ),
        nominal_frontier=frontier,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--physical", type=Path)
    p.add_argument("--previous", type=Path)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--new-output-dir", type=Path)
    g.add_argument("--check", type=Path)
    a = p.parse_args()
    if a.new_output_dir:
        a.new_output_dir.mkdir(mode=0o700)
    try:
        data = json.loads(OLD.read_bytes())
        witness = (
            acquire(a.physical, a.previous, data)
            if a.physical
            else json.loads(a.check.read_bytes())["observed"]
        )
        full = dict(observed=witness, results=score(data, witness))
        if a.check:
            need(full == json.loads(a.check.read_bytes()), "published correction differs")
        else:
            with (a.new_output_dir / "receipt.json").open("x") as f:
                json.dump(full, f, separators=(",", ":"), sort_keys=True)
        print("REPRODUCED_ONLINE_EOG")
    except Exception as exc:
        if a.new_output_dir:
            (a.new_output_dir / "failure.json").write_text(
                json.dumps(dict(status="FAIL_PRESERVED", reason=str(exc)))
            )
        raise

"""Prepare the earliest rejected and fully matched real proposals for a target verifier."""

import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
LOOK = run_path(HERE / "lookup.py")
S = LOOK["S"]
need, sha, read, publish = (S[k] for k in ("need", "sha", "read", "publish"))


def endpoints(rows):
    return [
        next(r for r in rows if len(r["proposal"]) == 2 and r["accepted"] == depth)
        for depth in (0, 2)
    ]


def write_ids(out, name, ids):
    path = out / (name + ".i32")
    with path.open("xb") as dest:
        dest.write(S["NATIVE"]["ids_bytes"](ids))
    return dict(file=path.name, ids=len(ids), sha256=sha(path))


def prepare(family, replay, out):
    phys = read(HERE / "code-chat.json")
    prices = read(HERE / "lookup.json")
    need(
        sha(family / "receipt.json") == phys["family_sha256"]
        and sha(HERE / "code-chat.json") == prices["physical_sha256"]
        and sha(replay / "steps.json") == prices["steps_sha256"],
        "sealed physical and replay inputs",
    )
    arm = family / "1R"
    root = read(family / "receipt.json")
    trial = phys["arms"][0]
    need(
        sha(arm / "receipt.json") == trial["receipt_sha256"] and trial["role"] == "R",
        "independent serial reference",
    )
    trace = (arm / "raw" / (trial["unit"] + ".stderr")).read_bytes()
    samples = list(S["NATIVE"]["events"](trace))
    starts = [t for _, t, e in samples if e == ("start",)]
    need(len(starts) == 2, "two real turns")
    native = [[e[3] for _, t, e in samples if t == task and e[0] == "sample"] for task in starts]
    files = {}
    prompts = [read(arm / "raw" / f"T{i}-input.json")["official_ids"] for i in (1, 2)]
    for i, (prompt, ids) in enumerate(zip(prompts, native, strict=True), 1):
        files[f"T{i}-prompt"] = write_ids(out, f"T{i}-prompt", prompt)
        need(
            S["H"]["SESSION"].ids_hash(prompt) == trial["turns"][i - 1]["official_ids_sha256"]
            and S["NATIVE"]["digest"](S["NATIVE"]["ids_bytes"](ids))
            == trial["target_ids"][str(i)]["sampled_sha256"],
            "native trace and official prompt",
        )
        if i == 1:
            files["T1-output"] = write_ids(out, "T1-output", ids)
    target = native[1]
    entry = dict(prompt=prompts[1], target=target, cap=768)
    rows = read(replay / "steps.json")["T2"]
    need(LOOK["STUDY"]["validate"](rows, entry) == prices["counts"], "causal draft and target")
    cases = []
    for row in endpoints(rows):
        at = row["at"]
        prefix = target[:at]
        predicted = [prefix[-1], *row["proposal"]]
        emitted = target[at : at + row["emitted"]]
        label = f"T2-after-{at}"
        cases.append(
            dict(
                confirmed=at,
                first_model_input_position=len(prompts[1]) + at - 1,
                accepted=row["accepted"],
                observed_emitted=len(emitted),
                prefix=write_ids(out, label + "-confirmed", prefix),
                verifier_inputs=write_ids(out, label + "-inputs", predicted),
                serial_decisions=write_ids(out, label + "-output", emitted),
            )
        )
    return dict(
        status="REPRODUCED_PREFIX_FIXTURES",
        program_sha256=sha(Path(__file__)),
        family_sha256=phys["family_sha256"],
        replay_steps_sha256=prices["steps_sha256"],
        physical_commit=root["commit"],
        files=files,
        cases=cases,
        t2_cached=trial["turns"][1]["cached"],
        t2_evaluated=trial["turns"][1]["evaluated"],
        kv_snapshot="NOT_CAPTURED",
        full_block_logits="NOT_CAPTURED",
        model_forwards=0,
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("family", "replay", "new-output-dir"):
        cli.add_argument("--" + name, type=Path, required=True)
    a = cli.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        record = prepare(a.family, a.replay, a.new_output_dir)
    except Exception as exc:
        publish(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
    publish(a.new_output_dir / "receipt.json", record)
    print(record["status"])

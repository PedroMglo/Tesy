"""Price past-only proposals in the six observed serial code trajectories."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(HERE / "run.py")
H, need, read, sha = (S[k] for k in ("H", "need", "read", "sha"))
STUDY = H["T"]["PLAN"]
INTRO = [
    b"<|end|>",
    b"<|start|>",
    b"assistant",
    b"<|channel|>",
    b"final",
    b"<|message|>",
]
METHOD = "1126d912f9d70e66509eda07e53c1f03a57daa2d5ba524143a2fe84b03bdd98a"
FREEZE = "8328e0a960b70786bf24bd17a24a5690d70050a4bfbd03ee8667ebec695c4f63"


def first_final(pieces, deltas):
    locations = [i + len(INTRO) for i in range(len(pieces)) if pieces[i : i + len(INTRO)] == INTRO]
    if len(locations) != 1 or not deltas or pieces[-1] != b"":
        return None
    begin = locations[0]
    if b"".join(pieces[begin:-1]) != b"".join(deltas):
        return None
    total = 0
    for i in range(begin, len(pieces) - 1):
        total += len(pieces[i])
        if total == len(deltas[0]):
            return i
        if total > len(deltas[0]):
            return None
    return None


def evidence(arm, trial):
    raw = arm / "raw"
    log = (raw / (trial["unit"] + ".stderr")).read_bytes()
    records = list(S["NATIVE"]["events"](log))
    tasks = [(clock, task) for clock, task, e in records if e == ("start",)]
    need(len(tasks) == 2, "task count")
    start_clock, owner = tasks[1]

    def ns(clock):
        minute, sec, ms, us = clock
        return (((minute * 60 + sec) * 1000 + ms) * 1000 + us) * 1000

    ticks, feeds, ids, pieces = [], [], [], []
    for clock, task, event in records:
        if task != owner:
            continue
        if event[0] == "feed":
            feeds.append(ns(clock))
        if event[0] != "sample":
            continue
        ticks.append(ns(clock))
        ids.append(event[3])
        start = event[4]
        pieces.append(log[start : log.index(b"'\n", start)])
    need(
        all(a < b for a, b in zip(ticks[:-1], ticks[1:], strict=True))
        and ns(start_clock) <= ticks[0]
        and all(a <= f <= b for a, f, b in zip(ticks[:-1], feeds, ticks[1:], strict=True))
        and S["NATIVE"]["digest"](S["NATIVE"]["ids_bytes"](ids))
        == trial["target_ids"]["2"]["sampled_sha256"],
        "serial producer identity and monotonicity",
    )
    frames = (json.loads(x) for x in (raw / "T2-request.jsonl").read_bytes().splitlines())
    deltas = []
    for frame in frames:
        if frame["kind"] != "SSE_FRAGMENT":
            continue
        fragment = frame["fragment"]
        if not fragment.startswith("data: ") or fragment[6:].strip() == "[DONE]":
            continue
        for entry in json.loads(fragment[6:]).get("choices", []):
            content = entry["delta"].get("content")
            if content:
                deltas.append(content.encode())
    result = read(raw / "T2-result.json")
    need(
        b"".join(deltas) == result["message"]["content"].encode() and result["accepted"],
        "SSE content",
    )
    cut = first_final(pieces, deltas)
    # This feed precedes the evaluation that produces the first visible final delta.
    # Its own sample log can come after queueing the HTTP chunk.
    interior = feeds[cut - 1] - ns(start_clock) if cut is not None and cut > 0 else None
    return (
        dict(prompt=result["official_ids"], target=ids, cap=768),
        ticks,
        cut,
        interior,
    )


def budget(steps, ticks, cut, decode_ns):
    cursor = 0
    block_ns = ordinary_ns = before_ns = before_blocks = before_accepted = 0
    accepted = blocks = 0
    for row in steps:
        start = row["at"] - 1
        end = start + row["emitted"]
        need(start == cursor and start < end < len(ticks), "contiguous producer interval")
        cost = ticks[end] - ticks[start]
        if row["proposal"]:
            block_ns += cost
            blocks += 1
            accepted += row["accepted"]
            if cut is not None and start < cut:
                before_blocks += 1
                before_ns += ticks[min(cut, end)] - ticks[start]
                before_accepted += min(row["accepted"], cut - start)
        else:
            ordinary_ns += cost
        cursor = end
    need(
        cursor == len(ticks) - 1 and ordinary_ns + block_ns == ticks[-1] - ticks[0] and blocks > 0,
        "conservation of the full native decode",
    )
    zero = decode_ns - block_ns
    six_allowance = len(ticks) * 1_000_000_000 // 6 - zero
    return dict(
        samples=len(ticks),
        calls=len(steps),
        target_confirmable_proposal_ids=accepted,
        blocks=blocks,
        ordinary_ns=ordinary_ns,
        observed_service_replaced_ns=block_ns,
        average_verification_ns_at_decode_break_even=block_ns // blocks,
        server_decode_ns=decode_ns,
        decode_ns_if_all_blocks_free=zero,
        six_tps_allowance_all_blocks_ns=six_allowance,
        average_verification_ns_at_six_tps=six_allowance // blocks if six_allowance >= 0 else None,
        first_final_sample=cut + 1 if cut is not None else None,
        blocks_to_first_final=before_blocks if cut is not None else None,
        accepted_before_final=before_accepted if cut is not None else None,
        native_replaced_to_first_final_ns=before_ns if cut is not None else None,
        mean_verification_ns_at_first_final_native_cut=before_ns // before_blocks
        if before_blocks
        else None,
    )


def run(family, physical, archive, out):
    need(
        sha(HERE / "lookup.md") == METHOD and sha(HERE / "lookup-freeze.json") == FREEZE,
        "prior protocol or seal",
    )
    compact = read(physical)
    need(
        sha(family / "receipt.json") == compact["family_sha256"] and len(compact["arms"]) == 6,
        "physical family",
    )
    prev = archive / "part-177/tesy-packed-causal-plan-20261126-r03"
    driver = H["G"]["read"](prev / "receipt.json", H["PLAN_PIN"])
    stored = prev / "server-plan"
    static = H["G"]["read"](
        archive / "part-161/tesy-pack-sys73-static-files-20261126-r01/receipt.json",
        S["T"]["N"]["STATIC"],
    )["arms"]["C281_PACK"]
    need(
        driver["status"] == "GO_CAUSAL_SERVER_PLAN" and sha(stored) == driver["binary_sha256"],
        "dispatcher",
    )
    # Archived executables are read-only data. Reconstruct their verified runtime in this run.
    exe = out / "server-plan"
    shutil.copyfile(stored, exe)
    exe.chmod(0o700)
    need(sha(exe) == driver["binary_sha256"], "dispatcher copy")
    lib = out / "providers"
    lib.mkdir()
    for name in driver["providers"]:
        (lib / name).symlink_to(static["closure"][name]["file"])
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        CUDA_VISIBLE_DEVICES="",
        LD_LIBRARY_PATH=str(lib),
    )
    cmd = subprocess.run(
        ["/usr/bin/ldd", "-r", exe],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    need(
        "undefined symbol" not in cmd.stdout and "not found" not in cmd.stdout,
        "loader relocation",
    )
    closure = STUDY["GRAPH"]["START"]["interpret"](cmd.stdout)
    need(
        set(closure) == set(driver["providers"])
        and all(
            str(Path(path).resolve(strict=True)) == static["closure"][k]["file"]
            and sha(Path(path)) == driver["providers"][k]
            for k, path in closure.items()
        ),
        "linked dispatcher providers",
    )
    results = []
    fixed = None
    for i, trial in enumerate(compact["arms"], 1):
        arm = family / (str(i) + trial["role"])
        need(sha(arm / "receipt.json") == trial["receipt_sha256"], "physical arm")
        entry, ticks, cut, interior = evidence(arm, trial)
        if fixed is None:
            proc = subprocess.run(
                [exe, *driver["options"]],
                input=json.dumps({"T2": entry}).encode(),
                env=env,
                capture_output=True,
                check=True,
                timeout=30,
            )
            steps = json.loads(proc.stdout)["T2"]
            counts = STUDY["validate"](steps, entry)
            (out / "steps.json").write_bytes(proc.stdout)
            fixed = entry
        need(fixed == entry, "different target work in serial arms")
        timed = budget(steps, ticks, cut, round(trial["turns"][1]["decode_s"] * 1e9))
        client = round(trial["turns"][1]["first_final_s"] * 1e9)
        need(
            interior is None or 0 <= interior <= client,
            "causal interior of client request",
        )
        timed["native_task_to_feed_before_first_final_ns"] = interior
        timed["max_exterior_saving_ns_with_fixed_producer_span"] = (
            client - interior if interior is not None else None
        )
        results.append(dict(role=trial["role"], receipt_sha256=trial["receipt_sha256"], **timed))
    return dict(
        classification="TRACE_DERIVED_CONDITIONAL",
        protocol_sha256=METHOD,
        program_sha256=sha(Path(__file__)),
        physical_sha256=sha(physical),
        dispatcher_sha256=driver["binary_sha256"],
        steps_sha256=sha(out / "steps.json"),
        counts=counts,
        arms=results,
        model_starts=0,
        gpu_forwards=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("family", "physical", "archive", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    try:
        r = run(a.family, a.physical, a.archive, out)
    except Exception as exc:
        S["publish"](out / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
    S["publish"](out / "lookup.json", r)
    print(r["classification"])

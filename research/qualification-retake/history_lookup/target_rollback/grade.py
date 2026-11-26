"""Reconcile the native sampler, serialized states and both continuation vectors."""

import math
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(str(HERE / "build.py"))
need, read, sha = (B[k] for k in ("need", "read", "sha"))
WIDTH = 201088
CASES = ("AR", "R0", "R1", "R2")
EOG = {199999, 200002, 200012}


def choices(path):
    values = struct.unpack(f"<{WIDTH}f", path.read_bytes())
    need(all(map(math.isfinite, values)), "finite logits")
    first = max(range(WIDTH), key=values.__getitem__)
    second = max((i for i in range(WIDTH) if i != first), key=values.__getitem__)
    need(values[first] > values[second], "unique argmax")
    return [first, second]


def compare(cap, mode, official, serial, ar):
    proof = read(cap / "native.json")
    need(
        proof["mode"] == mode
        and proof["callback_installed"] is False
        and proof["restored_prefix"] == 189,
        "native mode",
    )

    def match(left, right):
        signature = sha(left)
        need(signature == sha(right), "mismatch " + left.name)
        return signature

    prefix = match(cap / "initial.kv", serial / "initial-kv.bin")
    need(match(cap / "entry.kv", official / "initial-kv.bin") == prefix, "entry twice")
    post = match(cap / "cal-post3.kv", official / "post3-kv.bin")
    need(sha(serial / "post3-kv.bin") == post, "integrated/serial bridge")
    calibrated = {}
    for j in range(4):
        f = f"decode{j}.logits.f32"
        calibrated[f] = match(cap / ("cal-" + f), official / f)
        need(calibrated[f] == sha(serial / f), "calibration and serial")
    anchor = choices(official / "prefill_final.logits.f32")[0]
    need(proof["anchor"] == anchor and anchor not in EOG, "anchor")
    record = read(ar / "native.json")
    tokens, ranks = record["tokens"], record["ranks"]
    need(
        tokens[0] == anchor
        and len(tokens) == 6
        and len(ranks) == 5
        and record["single_calls"] == 5
        and not EOG.intersection(tokens[:-1]),
        "serial live trajectory",
    )
    entry = match(cap / "entry.pool", ar / "entry.pool")
    final = sha(cap / "final.pool")
    if mode == "AR":
        need(final == sha(cap / "keep-5.pool"), "drained AR pool")
        for j in range(5):
            need(
                ranks[j] == choices(cap / f"step-{j}.f32") and tokens[j + 1] == ranks[j][0],
                "serial sampler",
            )
        decision = dict(
            serial_tokens=tokens,
            finite_rows=5,
            matched_KV={str(j): sha(cap / f"keep-{j}.kv") for j in range(1, 6)},
        )
    else:
        k = int(mode[1])
        proposal = tokens[1:3]
        if k < 2:
            proposal[k] = ranks[k][1]
        confirmed = tokens[k + 1]
        stop = 1 + k
        need(
            proof["proposal"] == proposal
            and proof["accepted"] == k
            and proof["discarded"] == 2 - k
            and proof["kept"] == stop
            and proof["confirmed"] == confirmed
            and proof["seq_rm_calls"] == int(k < 2)
            and proof["consulted"] == list(range(stop))
            and set(cap.glob("decision-*.f32")) == {cap / f"decision-{j}.f32" for j in range(stop)},
            "causal decision",
        )
        decision_rows = {
            str(j): match(cap / f"decision-{j}.f32", ar / f"step-{j}.f32") for j in range(stop)
        }
        states = {"trim": match(cap / "trim.kv", ar / f"keep-{stop}.kv")}
        pools = {"trim": sha(cap / "trim.pool") == sha(ar / f"keep-{stop}.pool")}
        next_rows = {}
        for i in (0, 1):
            next_rows[str(i)] = match(cap / f"next-{i}.f32", ar / f"step-{stop + i}.f32")
            states[str(i)] = match(cap / f"next-{i}.kv", ar / f"keep-{stop + i + 1}.kv")
            pools[str(i)] = sha(cap / f"next-{i}.pool") == sha(ar / f"keep-{stop + i + 1}.pool")
            need(
                choices(cap / f"next-{i}.f32")[0]
                == proof["subsequent_tokens"][i]
                == tokens[stop + i + 1],
                "next sample",
            )
        decision = dict(
            accepted=k,
            discarded=2 - k,
            proposal=proposal,
            confirmed=confirmed,
            subsequent=proof["subsequent_tokens"],
            consulted_full_rows=decision_rows,
            next_full_rows=next_rows,
            matched_KV=states,
            pool_matches_at_same_depth=pools,
        )
        need(final == sha(cap / "next-1.pool"), "drained speculative pool")
    return dict(
        status="PASS_ROLLBACK_" + mode,
        mode=mode,
        anchor=anchor,
        calibration_logits=calibrated,
        calibration_kv=post,
        prefix_kv=prefix,
        entry_pool=entry,
        final_pool=final,
        decision=decision,
    )

"""Delete only authenticated host remap intervals in each observed natural C281 clock."""

import argparse
import hashlib
import json
import re
from collections import Counter
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
NATIVE = run_path(str(HERE.parent / "analyse.py"))
PFJ = NATIVE["PFJ"]
check = PFJ["check"]
MAPPING = re.compile(rb"load_tensors: layer +(\d+) assigned to device (\S+),")
BUFFERS = re.compile(
    rb"alloc_bufs:\s+(\S+) expert cache size =\s*([\d.]+) MiB \((\d+) slots per layer\)"
)
TIERS = ("CPU", "CUDA0")
SLAB = 4406400
NSEC = 10**9
METHOD = "18330b89d99604b13248b186e3effb85f40c2d45d72b43330b668fb3e17349b3"
C269 = "78c3a5bb34353d2b880b14bfa80634cd06dfe465beec529446206a8728af3f43"
PINNED = {
    "src/llama-model.cpp": "7af9ef3bb6dc9491f7280b3dbcc4f6605da7739b4288e7bee51881772f58f010",
    "tools/server/server-context.cpp": (
        "657c331a707f0faf74615d19387088070c3dbd7559328619c9ef606a4ec8cc55"
    ),
}
MANAGERS = {
    "C269": "584aecb73900aa1164f00ec93126bc5b8b07c4d330d0f421641331b0c278d5a0",
    "P": "044d8879be19e5c22331a29bf7a273307756de10675b1341ee9d7077e2dabc62",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(path, digest):
    check(sha(path) == digest, "source identity: " + path.name)
    return json.loads(path.read_bytes())


def mapping(log, rows):
    layers = [(int(n), t.decode()) for n, t in MAPPING.findall(log)]
    check(
        layers == [(i, "CPU" if i < 25 else "CUDA0") for i in range(37)], "actual layer assignments"
    )
    mapping = dict(layers[:36])
    sizes = Counter()
    keys = set()
    for r in rows:
        if r.kind == 8:
            key = r.layer, r.component
            check(key not in keys and r.b == SLAB, "duplicate or different expert weights")
            keys.add(key)
            sizes[mapping[r.layer]] += r.b * 40
    check(keys == {(layer, c) for layer in range(36) for c in range(3)}, "three weights per layer")
    allocated = BUFFERS.findall(log)
    check(
        len(allocated) == 2 and {tier.decode() for tier, _, _ in allocated} == set(TIERS),
        "actual cache pool allocation",
    )
    for tier, size, slots in allocated:
        check(
            int(slots) == 40
            and abs(Decimal(size.decode()) - Decimal(sizes[tier.decode()]) / 2**20)
            <= Decimal("0.005"),
            "fallback or changed cache pool size",
        )
    return mapping, {t.decode(): s.decode() for t, s, _ in allocated}


def intervals(rows, host_spans):
    active = None
    result = []
    for r in rows:
        if r.kind == 9:
            check(active is None, "nested host remap")
            active = r
        elif r.kind == 23:
            check(
                active is not None
                and r.ns >= active.ns
                and (active.call, active.tile, active.layer, active.wave)
                == (r.call, r.tile, r.layer, r.wave),
                "unpaired callback",
            )
            result.append((r.call, r.layer, active.ns, r.ns))
            active = None
    check(
        not active
        and [(c, a, b) for c, _, a, b in result] == host_spans
        and all(a[3] <= b[2] for a, b in zip(result, result[1:], strict=False)),
        "unions disagree with host timeline",
    )
    return result


def buckets(spans, tiers, calls, final_cut):
    out = {t: [0, 0, 0] for t in TIERS}
    for c, layer, a, b in spans:
        call = calls[c - 1]
        check(
            call["number"] == c and call["enter_ns"] <= a <= b <= call["return_ns"],
            "cut outside call",
        )
        end = min(b, final_cut) if c <= 46 else a
        first = max(0, end - a)
        decode = b - a if c >= 3 else 0
        both = first if c >= 3 else 0
        q = out[tiers[layer]]
        q[0] += first - both
        q[1] += both
        q[2] += decode - both
    return out


def minimum_other(a, b, other):
    only_first, common, only_decode = other
    max_first, max_decode = only_first + common, common + only_decode
    remaining = [max(0, a - max_first), max(0, b - max_decode)]
    feasible = not any(remaining)
    minimum = max(a, b, a + b - common)
    return {
        "required_first_ns": a,
        "required_decode_ns": b,
        "minimum_fraction_of_other_first": (a / max_first if max_first else None),
        "minimum_fraction_of_other_decode": (b / max_decode if max_decode else None),
        "minimum_distinct_other_ns": minimum if feasible else None,
        "minimum_fraction_of_other_union": minimum / sum(other)
        if feasible and sum(other)
        else None,
        "other_regions_suffice": feasible,
        "still_required_outside_both_ns": {
            "first": remaining[0],
            "decode": remaining[1],
            "distinct_at_least": max(remaining),
        },
    }


def scenario(prices, first_ns, dec_ns):
    need_first = max(0, first_ns - 10 * NSEC)
    # 47 outputs per 46 native post-first evaluations. Round up the time allowed.
    need_decode = max(0, dec_ns - ((47 * NSEC + 5) // 6))
    scopes = {}
    both = [sum(values) for values in zip(*(prices[t] for t in TIERS), strict=True)]
    for label, price in (*prices.items(), ("both", both)):
        f, d = price[0] + price[1], price[1] + price[2]
        check(f <= first_ns + 1 and d <= dec_ns + 1, "remap exceeds interval measured on its clock")
        missing = [max(0, need_first - f), max(0, need_decode - d)]
        result = {
            "exclusive_regions_ns": dict(
                zip(("first_only", "intersection", "decode_only"), price, strict=True)
            ),
            "free_max_ns": {"first": f, "decode": d},
            "remaining_floor_ns": {"first": first_ns - f, "decode": dec_ns - d},
            "unmet_ns": {"first": missing[0], "decode": missing[1]},
            "first": "NO_GO_FIXED_EXTERIOR" if missing[0] else "HEADROOM_ONLY",
            "decode": "NO_GO_FIXED_EXTERIOR" if missing[1] else "HEADROOM_ONLY",
            "joint": "NO_GO_FIXED_EXTERIOR" if any(missing) else "HEADROOM_ONLY",
        }
        if label != "both":
            other = prices[next(t for t in TIERS if t != label)]
            result["if_this_tier_free"] = minimum_other(*missing, other)
        scopes[label] = result
    return {
        "observed_ns": {"first": first_ns, "decode": dec_ns},
        "necessary_ns": {"first": need_first, "decode": need_decode},
        "scenarios": scopes,
    }


def packed_inputs(a):
    chain = run_path(str(HERE.parent / "release/run.py"))["chain"]
    _, binding, receipt, stored = chain(a.family, a.family_sha256)
    check(stored["status"] == "PASS_PACK_NATURAL_TRACE", "incomplete journal")
    raw = a.family / "ON/raw"
    hashes = {"T2-result.json": a.result_sha256, "T2-request.jsonl": a.http_sha256}
    check(all(sha(raw / name) == value for name, value in hashes.items()), "HTTP raw identity")
    return binding, receipt, stored, {"family_sha256": a.family_sha256, "http_sha256": hashes}


def assess(a):
    check(sha(HERE / "protocol.md") == METHOD, "protocol")
    pins = PINNED | {"src/llama-moe-stream.cpp": MANAGERS[a.arm]}
    check(all(sha(a.backend / f) == h for f, h in pins.items()), "backend source pin")
    inputs = {}
    if a.arm == "C269":
        receipt_hash = C269
        where = a.arm_dir
        receipt = checked(where / "receipt.json", receipt_hash)
    else:
        binding, receipt, stored, inputs = packed_inputs(a)
        receipt_hash = binding["receipt_sha256"]
        where = a.family / "ON"
    old = receipt["rows"][1]
    check(
        old["functional"] == "PASS"
        and old["completion"] == "stop"
        and old["predicted_n"] == 47
        and receipt["native_ids"]["native_task_source_sha256"]
        == pins["tools/server/server-context.cpp"],
        "validator and server source",
    )
    rows, header = PFJ["read_journal"](where / "raw/events.pfj")
    host = NATIVE["host_trace"](rows)
    if a.arm == "C269":
        ref = NATIVE["historical"](where)
        check(
            ref == json.loads((HERE.parent / "historical.json").read_bytes()),
            "C269 original projection",
        )
        authority = checked(where / "journal-audit.json", receipt["journal_audit_sha256"])
        got = PFJ["audit"](rows, header)
        check(
            got["status"] == "PASS"
            and authority["fd_identity_checked"]
            and json.loads(json.dumps(got | {"fd_identity_checked": True})) == authority,
            "C269 job conservation",
        )
        cut = ref["http_cut"]
    else:
        full = NATIVE["audit_arm"](where, receipt, receipt["pack_events"]["before_second_ns"])
        check(
            full["status"] == "PASS_PACK_NATURAL_TRACE"
            and full["jobs"]["eligible_clean_run"]
            and json.loads(json.dumps(full)) == stored,
            "P job conservation",
        )
        cut = full["http_cut"]
    check(cut["sample_number"] == 45 and cut["sample_call"] == 46, "first final trajectory")
    logname = receipt["native_ids"]["raw_stderr_file"]
    check(Path(logname).name == logname, "log path")
    log = where / "raw" / logname
    check(sha(log) == receipt["native_ids"]["stderr_sha256"], "same PID log")
    tiers, allocated = mapping(log.read_bytes(), rows)
    spans = intervals(rows, host["callback_spans"])
    final = host["calls"][45]["return_ns"] + cut["last_relevant_return_to_first_final_ns"]
    prices = buckets(spans, tiers, host["calls"], final)
    full = json.loads((where / "raw/T2-result.json").read_bytes())
    first = int(
        (
            Decimal(str(full["stream_metrics"]["first_final_content_chunk_s"])) * NSEC
        ).to_integral_value(rounding=ROUND_FLOOR)
    )
    decode = int(
        (Decimal(str(full["timings"]["predicted_ms"])) * 10**6).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    return {
        "status": "TRACE_DERIVED_FIXED_EXTERIOR",
        "arm": a.arm,
        **inputs,
        "arm_sha256": receipt_hash,
        "source_sha256": pins,
        "journal_sha256": header["journal_sha256"],
        "stderr_sha256": sha(log),
        "route": host["route"],
        "sampled_ids_sha256": receipt["trajectories"][1]["sampled_ids_sha256"],
        "tier_layers": {t: [layer for layer in tiers if tiers[layer] == t] for t in TIERS},
        "logged_cache_MiB": allocated,
        "callback_count": len(spans),
        "first_final_sample": 45,
        "outputs": 47,
        "post_first_calls": 46,
        "method_sha256": METHOD,
        **scenario(prices, first, decode),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arm", choices=("C269", "P"), required=True)
    for name in ("backend", "arm-dir", "family", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=name in ("backend", "new-output-dir"))
    p.add_argument("--family-sha256")
    p.add_argument("--result-sha256")
    p.add_argument("--http-sha256")
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = assess(a)
    except Exception as exc:
        r = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(r, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

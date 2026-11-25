"""Reopen two sealed C281 blocks, authenticate physical order, compare like-for-like contrasts."""

import argparse
import hashlib
import json
import math
import os
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
legacy = run_path(HERE / "compact.py")
need, sha, save = (legacy[k] for k in ("need", "sha", "save"))
ROP_SHA = "d3c4a498b0b774e70c281134fea885a3189fe8a81304f7bd1f2b7d9d321a0c4b"
LEGACY_SHA = "8fa67698295e2686580541d0495f549a804aa1d72341087335ef45336a0cd368"


def read(path):
    return json.loads(path.read_bytes())


def signature(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def verify_wait(wait, left, right, expected_elapsed):
    samples = wait["samples"]
    need(
        wait["previous"] == left["mode"]
        and wait["pid"] == left["pid"]
        and wait["port"] == 18442
        and wait["bind_available"] is True
        and wait["limit_s"] == 75
        and 0 <= wait["elapsed_s"] == expected_elapsed <= 75
        and samples,
        "predecessor/strict bind",
    )
    ts = [s["elapsed_s"] for s in samples]
    need(
        0 <= ts[0] <= ts[-1] <= expected_elapsed
        and all(x < y for x, y in pairwise(ts))
        and all(
            type(count) is int and count > 0 and state == "06"
            for s in samples
            for state, count in s["tcp_states"].items()
        )
        and all(s["tcp_states"] for s in samples[:-1]),
        "only TIME_WAIT before bind",
    )
    # C118 duration and wait are wholly between predecessor cleanup and next Popen,
    # measured with monotonic() in the same boot. Their origins need not be equated.
    dt = (right["spawn_ns"] - left["clean_ns"]) / 1e9
    need(
        left["pid"] != right["pid"] and dt >= right["c118_s"] + expected_elapsed,
        "overlapping predecessor, wait or C118",
    )
    return dict(
        previous=left["mode"],
        current=right["mode"],
        closed_to_popen_s=dt,
        wait_s=expected_elapsed,
        samples=len(samples),
    )


def evidence(root, mode, meta, grad):
    base = root / mode
    late = read(base / "receipt.json")
    saved = read(base / "arm.json")
    need(
        meta["arms"][mode]["arm"] == saved and saved["status"] == "PASS_ONE_NATURAL_ARM",
        "embedded arm",
    )
    preset = read(base / "preset.json")
    run = preset["run_id"]
    stem = base / "raw" / run
    need(
        run == meta["identity"]["unit_prefix"] + "-" + mode.lower()
        and run == Path(run).name
        and preset["window_sha256"] == meta["identity"]["window"]
        and preset["measurement_commit"] == meta["identity"]["commit"]
        and preset["tree"] == meta["identity"]["tree"],
        "unit / C55 / checkout",
    )
    launch = read(stem.with_suffix(".launch.json"))
    m = read(stem.with_suffix(".json"))
    t = late["transport"]
    auth = late["runtime_authority"]
    payload = read(base / "resource-policy.json")
    resource = read(base / "resource-protocol.json")
    need(
        sha(base / "resource-protocol.json") == launch["resource_protocol_sha256"]
        and resource["resources"]["snapshot_sha256"]
        == payload["snapshot_sha256"]
        == signature(payload["snapshot"]),
        "canonical C55 snapshot",
    )
    iv = read(stem.with_suffix(".start-inventory.receipt.json"))
    need(iv["policy_sha256"] == signature(payload), "C55 / C118 binding")
    age = (
        datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])
        - datetime.fromisoformat(payload["snapshot"]["utc"])
    ).total_seconds()
    need(
        0 <= t["c55_age_at_entry_s"] <= age == t["c55_age_at_spawn_s"] < 55 * 60,
        "C55 at native Popen",
    )
    identity = launch["process_identity"]
    cut0, cut1 = t["cuts"]
    spawn = launch["start_inventory"]["popen_invoked_monotonic_ns"]
    clean = t["shutdown"]["server_port_scope_verified_ns"]
    need(
        cut0["identity"] == cut1["identity"] == identity
        and spawn
        < cut0["monotonic_ns"]
        < cut1["monotonic_ns"]
        <= t["shutdown"]["sigint_before_ns"]
        <= clean,
        "native monotonic lifecycle",
    )
    hardware = {
        (s["gpu"]["uuid"], s["gpu"]["bdf"])
        for s in map(json.loads, stem.with_suffix(".samples.jsonl").read_bytes().splitlines())
    }
    need(len(hardware) == 1, "GPU identity")
    dsos = {soname: obj["sha256"] for soname, obj in preset["dso"].items()}
    need(dsos.pop("libllama.so.0") == t["libllama"]["sha256"], "libllama binding")
    work = [
        {
            k: x[k]
            for k in (
                "input_bytes_sha256",
                "official_ids_sha256",
                "sampled_ids_sha256",
                "stable_frames_sha256",
                "completion_n",
                "frames",
                "feed_echoes",
            )
        }
        for x in grad["rows"]
    ]
    common = dict(
        work=work,
        server=preset["binary_sha256"],
        argv=late["native_ids"]["argv_sha256"],
        model=preset["model_sha256"],
        model_stat=preset["model_stat"],
        data=t["data_stat"],
        dependencies=dsos,
        hardware=sorted(hardware),
        platform={
            k: auth[k]
            for k in (
                "kernel",
                "deployment_commit",
                "preflight_sha256",
                "c270_sha256",
                "selected_sha256",
            )
        },
        controls={
            k: t[k]
            for k in ("c292_sha256", "closure_sha256", "constructor_sha256", "derived_sha256")
        },
    )
    need(
        m["binary_sha256"] == common["server"] and mode == grad["transport"]["mode"] == t["mode"],
        "mode/ELF",
    )
    return dict(
        mode=mode,
        pid=identity["pid"],
        spawn_ns=spawn,
        clean_ns=clean,
        c118_s=iv["duration_s"],
        c55_spawn_age_s=age,
        gpu_driver_and_work_sha256=signature(common),
        libllama_sha256=t["libllama"]["sha256"],
        arm_sha256=sha(base / "arm.json"),
    )


def block(root, order, expected, history):
    path = root / "family.json"
    need(sha(path) == expected and (order != "ROP" or expected == ROP_SHA), "sealed family")
    meta = read(path)
    frozen = meta["identity"]
    need(
        set(meta["arms"]) == set(order)
        and sha(HERE / "compact.py") == LEGACY_SHA
        and frozen["protocol"] == sha(HERE / "protocol.md")
        and all(
            sha(HERE / name) == frozen["supervisor"][name]
            for name in ("transport_profile.py", "review.py")
        ),
        "arms or original measurement/review source",
    )
    if order == "POR":
        need(
            meta["order"] == frozen["order"] == order
            and frozen["order_protocol_sha256"] == sha(HERE / "order.md"),
            "reverse order preregistration",
        )
    else:
        need(
            order == "ROP" and frozen["commit"] == "7aae40d22a2fe466a7ab5e25a717cfb65dcf60e5",
            "original ROP",
        )
    compact = legacy["extract"](root, history)
    arms = [evidence(root, m, meta, compact["arms"][m]) for m in order]
    need(
        len({a["pid"] for a in arms}) == 3
        and len({a["gpu_driver_and_work_sha256"] for a in arms}) == 1
        and set(meta["closed_endpoint_wait_before_arm_s"]) == set(order[1:]),
        "same work / separate servers",
    )
    waits = []
    for a, b in pairwise(arms):
        p = root / (a["mode"] + "-closed-endpoint.json")
        waits.append(
            verify_wait(read(p), a, b, meta["closed_endpoint_wait_before_arm_s"][b["mode"]])
            | {"receipt_sha256": sha(p)}
        )
    return dict(
        order=order,
        family_sha256=expected,
        commit=frozen["commit"],
        tree=frozen["tree"],
        arm_sha256={a["mode"]: a["arm_sha256"] for a in arms},
        c55_spawn_age_s={a["mode"]: a["c55_spawn_age_s"] for a in arms},
        libllama_sha256={a["mode"]: a["libllama_sha256"] for a in arms},
        gpu_driver_and_work_sha256=arms[0]["gpu_driver_and_work_sha256"],
        transitions=waits,
        differences=compact["differences"],
        targets=compact["nominal_targets"],
        rows={m: compact["arms"][m]["rows"] for m in order},
        family_elapsed_s=compact["family_elapsed_s"],
    )


def classify(first, second):
    need(all(math.isfinite(v) for v in (first, second)), "nonfinite contrast")
    if first > 0 and second > 0:
        return "BENEFIT_IN_BOTH_ORDERS"
    if first <= 0 and second <= 0:
        return "NO_POSITIVE_BENEFIT_IN_EITHER_BLOCK"
    return "BLOCK_DEPENDENT_OR_TIE"


def compare_blocks(forward, reverse):
    need(
        forward["order"] == "ROP"
        and reverse["order"] == "POR"
        and forward["gpu_driver_and_work_sha256"] == reverse["gpu_driver_and_work_sha256"]
        and forward["libllama_sha256"] == reverse["libllama_sha256"],
        "cross-block work/providers",
    )
    spans = {}
    for contrast in ("R_O", "O_P", "R_P"):
        spans[contrast] = {}
        for label in ("T1", "T2"):
            left, right = [b["differences"][contrast][label] for b in (forward, reverse)]
            fields = {}
            for k in (*legacy["TIMES"], "decode_tok_s_delta"):
                vals = [
                    r[k] if k == "decode_tok_s_delta" else r[k]["seconds_saved"]
                    for r in (left, right)
                ]
                fields[k] = dict(ROP=vals[0], POR=vals[1], span=max(vals) - min(vals))
            spans[contrast][label] = fields
    sign = spans["O_P"]["T2"]["first_final_s"]
    return dict(
        status="REPRODUCED_TWO_C281_TRANSPORT_ORDERS",
        ROP=forward,
        POR=reverse,
        by_contrast=spans,
        t2_first_final_pack_effect=classify(sign["ROP"], sign["POR"]),
        observations_per_arm=2,
        servers=6,
        natural_requests=12,
        order_protocol_sha256=sha(HERE / "order.md"),
        review_sha256=sha(Path(__file__)),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("rop", "por", "history-dir", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--por-sha256", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = compare_blocks(
            block(a.rop, "ROP", ROP_SHA, a.history_dir),
            block(a.por, "POR", a.por_sha256, a.history_dir),
        )
    except (ValueError, OSError, KeyError, TypeError, IndexError) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    save(a.new_output_dir / "receipt.json", result)
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

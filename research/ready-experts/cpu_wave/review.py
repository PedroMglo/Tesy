"""Reproduce the public decision or rebuild its compact evidence from a private sealed family."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CLIENT = run_path(HERE / "client.py")
LAYER = run_path(HERE / "layer.py")
T = CLIENT["T"]
need, sha, read = T["need"], T["sha"], T["read"]
TIMING = run_path(CLIENT["HTTP"] / "kv_width/natural/cpu_attention/target/http/review_family.py")
POWER = run_path(T["Q"] / "packed_nvme_manifest/server_profile/system_driver/review.py")["power"]
PREFIX = "tesy-native-wave-"
DATE = "-20261127-"


def folder(root, name, attempt="r01"):
    return root / (PREFIX + name + DATE + attempt)


def evidence(path):
    return read(path / "receipt.json")


def digest(path):
    return sha(path / "receipt.json")


def phases(row):
    keys = (
        "prompt",
        "cached",
        "evaluated",
        "output",
        "predicted",
        "prefill_s",
        "decode_s",
        "decode_tok_s",
        "first_reasoning_s",
        "first_final_s",
        "transport_s",
        "valid_s",
        "stop",
        "official_ids_sha256",
        "validator",
    )
    return {k: row[k] for k in keys}


def prefix_clock(root, unit):
    """Bound strictly interior service on one native clock, without aligning HTTP timestamps."""
    ticks, cut = TIMING["ticks"](root, 2)
    need(len(ticks) == 47 and cut == 44, "SSE and target identify final sample 45")
    log = (root / "raw" / (unit + ".stderr")).read_bytes()
    events = list(CLIENT["H"]["T"]["V"]["events"](log))
    starts = [(tick, task) for tick, task, event in events if event[0] == "start"]
    need(len(starts) == 2, "two natural tasks")
    start, owner = starts[1]
    feed = [
        TIMING["elapsed_us"](tick) for tick, task, e in events if task == owner and e[0] == "feed"
    ]
    need(
        len(feed) == 46
        and ticks[0] >= TIMING["elapsed_us"](start)
        and all(
            left <= middle <= right
            for left, middle, right in zip(ticks[:-1], feed, ticks[1:], strict=True)
        ),
        "serial feed between adjacent target samples",
    )
    # process_token may log sample 45 after queuing its partial HTTP response.
    # Feeding sample 44 is necessarily earlier. It starts the evaluation that produces sample 45.
    interior_us = feed[cut - 1] - ticks[0]
    before_decode_us = ticks[0] - TIMING["elapsed_us"](start)
    return dict(
        first_final_sample=45,
        sampled=47,
        serial_feeds=46,
        first_to_feed_44_us=interior_us,
        start_to_sample_1_us=before_decode_us,
        remaining_if_only_prefill_changes_us=10_000_000 - interior_us,
        remaining_if_only_decode_changes_us=10_000_000 - before_decode_us,
    )


def compact(root, http):
    build = folder(root, "build")
    layer = folder(root, "layer", "r02")
    initial, resumed = (folder(root, "target", k) for k in ("r01", "r02"))
    build_result, layer_result, target_result = map(evidence, (build, layer, resumed))
    need(
        (digest(build), digest(layer), digest(initial)) == (T["BUILD"], T["LAYER"], T["STOPPED"]),
        "upstream gates",
    )
    need(
        layer_result["build_sha256"] == digest(build)
        and target_result["prior_sha256"] == digest(initial)
        and target_result["decision"] == "GO_UNCOUNTED_CLIENT",
        "gate order",
    )
    need(
        all(sha(build / (k + ".bin")) == v["sha256"] for k, v in build_result["fixture"].items()),
        "native samples",
    )
    need(
        all(
            sha(layer / (row["name"] + ".json")) == row["native_sha256"]
            for row in layer_result["arms"]
        )
        and sha(layer / "monitor.jsonl") == layer_result["monitor_sha256"],
        "physical layer",
    )
    price = layer_result["arms"][3:]
    layer_pairs, layer_gate = LAYER["grade"](price)
    need(
        layer_pairs == layer_result["pairs"] and layer_gate == layer_result["decision"],
        "independent layer prices",
    )
    numeric = []
    first = None
    for mode, src in (("ORIGINAL", initial), ("OFF", initial), ("ON", resumed), ("PRICE", resumed)):
        arm = src / mode
        obs = read(arm / "checked.json")
        raw = arm / "raw" / (obs["unit"] + ".capture")
        native = read(raw / "native.json")
        need(
            obs["mode"] == mode
            and native == obs["native"]
            and len(obs["files"]) == 19
            and all(sha(raw / k) == v for k, v in obs["files"].items()),
            "original numeric " + mode,
        )
        baseline = (obs["files"], obs["kv"], native, sha(raw / "native.json"))
        if first is None:
            first = baseline
        need(baseline == first, "numerical cuts " + mode)
        if mode in target_result["prior_controls"]:
            need(sha(arm / "checked.json") == target_result["prior_controls"][mode], "R01 control")
        numeric.append(
            {
                k: obs[k]
                for k in (
                    "mode",
                    "counts",
                    "cpu_sha256",
                    "model_s",
                    "scope_s",
                    "maxima",
                    "inventory",
                )
            }
            | dict(checked_sha256=sha(arm / "checked.json"), gpu_energy=POWER(arm, obs))
        )
    windows = {
        name: digest(path)
        for name, path in (
            ("layer", folder(root, "c55")),
            ("numeric_r01", folder(root, "target-c55")),
            ("numeric_r02", folder(root, "target-c55", "r02")),
        )
    }
    machine = evidence(folder(root, "target-c55", "r02"))
    host = {
        k: machine[k]
        for k in (
            "cpu",
            "gpu_name",
            "gpu_driver",
            "gpu_total_mib",
            "model_device",
            "model_fs",
            "gpu_compute_max",
        )
    }
    host.update(
        ram_b=machine["memory"]["total_bytes"],
        power=machine["power"]["source"],
        profile=machine["power"]["profile"],
    )
    need(
        layer_result["c55_sha256"] == windows["layer"]
        and evidence(initial)["window_sha256"] == windows["numeric_r01"]
        and target_result["window_sha256"] == windows["numeric_r02"],
        "C55 provenance",
    )
    receipts = {}
    for p in sorted(root.glob(PREFIX + "*" + DATE + "r*")):
        if p.is_dir():
            r = evidence(p)
            receipts[p.name] = {
                k: r[k]
                for k in ("status", "decision", "commit", "tree", "stage", "reason", "elapsed_s")
                if k in r
            }
            receipts[p.name]["sha256"] = digest(p)
    client = evidence(http)
    need(
        client["target_sha256"] == digest(resumed) and client["method"] == sha(HERE / "http.md"),
        "HTTP admission",
    )
    trials = []
    for lab, row in enumerate(client["arms"], 1):
        arm = http / f"{lab}-{row['role']}"
        rec = evidence(arm)
        need(
            rec["status"] == "MEASURED"
            and rec["trial"] == row
            and sha(arm / "session.json") == row["native_sha256"]
            and rec["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE",
            "HTTP raw identity",
        )
        proof = rec["runtime_authority"]
        clock = prefix_clock(arm, row["unit"])
        trials.append(
            dict(
                role=row["role"],
                turns=list(map(phases, row["turns"])),
                energy=row["energy"],
                maxima=row["maxima"],
                c118_s=row["c118_s"],
                raw_bytes=row["raw_bytes"],
                model_s=row["model_s"],
                session_sha256=row["native_sha256"],
                trajectories=row["target_ids"],
                cleanup=rec["cleanup"],
                ready_s=rec["ready_s"],
                last_client_cut_to_cleanup_s=(
                    proof["verified_cleanup_ns"] - proof["cuts"][-1]["monotonic_ns"]
                )
                / 1e9,
                native_t2=clock,
            )
        )
    sources = build_result["sources"] | {
        k: sha(HERE / k)
        for k in (
            "protocol.md",
            "target.md",
            "retoma.md",
            "http.md",
            "client.py",
            "layer.py",
            "target.py",
        )
    }
    result = dict(
        schema="tesy-cpu-wave-v1",
        receipts=receipts,
        source_sha256=sources,
        host=host,
        windows=windows,
        build=dict(
            fixture=build_result["fixture"],
            providers=build_result["arms"],
            scope_peak_b=build_result["memory_peak"],
            scope_swap_b=build_result["swap_peak"],
            model_reads=build_result["model_reads"],
        ),
        layer=dict(
            prices=price,
            pairs=layer_result["pairs"],
            decision=layer_result["decision"],
            counted=[x["counted"] for x in layer_result["arms"][:3]],
            returned_pack_bytes=sum(x["returned_bytes"] for x in layer_result["arms"]),
            c118_s=layer_result["c118"]["duration_s"],
            samples=layer_result["samples"],
            scope_peak_b=layer_result["final_cgroup"]["memory_peak"],
        ),
        numeric=dict(
            arms=numeric,
            files=first[0],
            kv=first[1],
            native=dict(
                live_prefix=first[2]["live_prefix"],
                single_calls=first[2]["single_calls"],
                store_entry=first[2]["store_entry"],
                store_end=first[2]["store_end"],
                callback_installed=first[2]["callback_installed"],
                receipt_sha256=first[3],
            ),
            decision=target_result["decision"],
            reference_manifests=target_result["archive_manifests"],
        ),
        client=dict(
            arms=trials,
            receipt_sha256=digest(http),
            status=client["status"],
            decision=client.get("decision", "NOT_RUN_COMPLETE_PAIRS"),
            pairs=client.get("pairs", []),
        ),
    )
    return result


def verify(r):
    need(
        r["schema"] == "tesy-cpu-wave-v1"
        and all(sha(HERE / k) == h for k, h in r["source_sha256"].items()),
        "source identities",
    )
    fixture = r["build"]["fixture"]
    need(
        len({(x["bytes"], x["sha256"]) for x in fixture.values()}) == 1
        and [fixture[k]["fusions"] for k in ("ORIGINAL", "OFF", "ON")] == [0, 0, 36],
        "fixture parity",
    )
    layer_result = r["layer"]
    need(
        LAYER["grade"](layer_result["prices"]) == (layer_result["pairs"], layer_result["decision"])
        and layer_result["decision"] == "GO_SERVER_NUMERICAL",
        "physical layer gate",
    )
    numeric_result = r["numeric"]
    need(
        [a["mode"] for a in numeric_result["arms"]] == ["ORIGINAL", "OFF", "ON", "PRICE"]
        and [a["counts"] for a in numeric_result["arms"]] == [[], [0], [765], []]
        and numeric_result["decision"] == "GO_UNCOUNTED_CLIENT"
        and len(numeric_result["files"]) == 19
        and len(numeric_result["kv"]) == 6
        and numeric_result["reference_manifests"] == {str(k): v for k, v in T["SEALS"].items()},
        "mixed numerical gate",
    )
    client_result = r["client"]
    if client_result["status"] == "MEASURED":
        need(
            CLIENT["compare"](client_result["arms"])
            == (client_result["pairs"], client_result["decision"]),
            "natural client evaluator",
        )
        reference = T["Q"] / "history_lookup/native_ids/evidence/verified.json"
        need(sha(reference) == CLIENT["H"]["F"]["OLD"]["VERIFIED"], "independent trajectory")
        expected = read(reference)["turns"]
        for a in client_result["arms"]:
            clock = a["native_t2"]
            need(
                clock["first_final_sample"] == 45
                and clock["serial_feeds"] == 46
                and clock["start_to_sample_1_us"] + clock["remaining_if_only_decode_changes_us"]
                == 10_000_000
                and clock["first_to_feed_44_us"] + clock["remaining_if_only_prefill_changes_us"]
                == 10_000_000,
                "conditional chronology",
            )
            for i, t in enumerate(a["turns"]):
                need(
                    t["validator"] == "PASS"
                    and t["stop"] == "stop"
                    and (t["prompt"], t["cached"], t["evaluated"], t["output"], t["predicted"])
                    == ((2043, 0, 2043, 78, 78), (2197, 2044, 153, 47, 47))[i],
                    "work",
                )
                ids = a["trajectories"][str(i + 1)]
                need(
                    t["official_ids_sha256"] == expected[i]["official_ids_sha256"]
                    and ids["sampled_sha256"] == expected[i]["sampled_ids_sha256"]
                    and ids["sampled"] == expected[i]["count"]
                    and ids["serial"] == ids["sampled"] - 1
                    and ids["eos"] == 1
                    and ids["proposed"] == ids["accepted"] == 0,
                    "natural target trajectory",
                )
    else:
        need(
            client_result["status"] == "FAIL_PRESERVED"
            and not client_result["pairs"]
            and client_result["decision"] == "NOT_RUN_COMPLETE_PAIRS",
            "partial family cannot earn a verdict",
        )


def write_exclusive(path, data):
    with path.open("x") as f:
        json.dump(data, f, sort_keys=True, indent=2)
        f.write("\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", type=Path)
    group.add_argument("--raw-root", type=Path)
    p.add_argument("--http", type=Path)
    p.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    if a.check:
        need(a.http is None and a.new_output_dir is None, "check arguments")
        r = read(a.check)
    else:
        need(
            a.http is not None and a.new_output_dir is not None, "output and HTTP receipt required"
        )
        a.new_output_dir.mkdir()
        r = compact(a.raw_root, a.http)
    verify(r)
    if a.new_output_dir:
        write_exclusive(a.new_output_dir / "decision.json", r)
    print(r["numeric"]["decision"], r["client"]["decision"])


if __name__ == "__main__":
    main()

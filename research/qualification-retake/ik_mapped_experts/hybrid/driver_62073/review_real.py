"""Reopen the system-driver arms and their independent references without loading a model."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(str(HERE / "real_authority.py"))
OFF, FR, G, need, sha, receipt = (A[k] for k in ("OFF", "FR", "G", "need", "sha", "receipt"))


def phase_report(folder, arm, mode_grade):
    journal = folder / "raw/monitor.jsonl"
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    scope_delta = 512 * (records[-1]["disk_read_sectors"] - records[0]["data"]["disk_read_sectors"])
    trailing = arm["namespace_read_bytes"] - scope_delta
    need(trailing >= 0, "namespace counter regressed after exit observation")
    # The terminal counter can be read after the exit sample. Retain those extra
    # sectors separately; phase deltas use only markers from the original journal.
    p = OFF["R"]["by_phase"](journal, arm | {"namespace_read_bytes": scope_delta})
    if "service_by_phase" in mode_grade:
        for k, x in p.items():
            x.update(mode_grade["service_by_phase"][k])
    elif mode_grade.get("source_and_slot"):
        for k, x in p.items():
            x["matrix_h2d_B"] = mode_grade["source_and_slot"]["matrix_requests_B"][k]
    return dict(
        phases=p,
        namespace_read_B=arm["namespace_read_bytes"],
        post_exit_sample_B=trailing,
        peak_vram_MiB=arm["peak_vram_mib_sampled"],
        exit_vram_MiB=arm["exit_vram_mib"],
        process_s=arm["elapsed_s"],
        swap_B=arm["swap_peak"],
        cleanup_ack_s=round(arm["ack_elapsed_s"]["F"] - arm["ack_elapsed_s"]["T"], 6),
    )


def review(a):
    tiny = receipt(a.tiny / "receipt.json", a.tiny_sha256)
    monitor = A["check_tiny"](a.tiny, a.tiny_sha256)
    cap = receipt(a.capacity / "receipt.json", a.capacity_sha256)
    need(
        cap["status"] == "PASS_SYSTEM_CAPACITY_ZERO_FORWARD"
        and FR["inventory"](a.capacity) == cap["raw_sha256"],
        "capacity inventory",
    )
    c = A["capacity_grade"](a.capacity, a.plan)
    need(c == cap["grade"], "capacity grade")
    A["require_capacity"](c)
    pair = receipt(a.pair / "receipt.json", a.pair_sha256)
    need(
        pair["authority"]["tiny_sha256"] == a.tiny_sha256
        and pair["authority"]["capacity_sha256"] == a.capacity_sha256
        and cap["authority"]["monitor"] == pair["authority"]["monitor"] == monitor,
        "live comparators",
    )
    historical = OFF["reference"](a.historical, a.plan)
    refs = FR["OPS"]["CUT"]["references"](a.c110_parent, a.stock_file, a.cpu_d0, a.cpu_d1)
    grades = {}
    arms = {}
    starts = 0
    for selection, mode in (
        ("ON", "BANK288"),
        ("OFF", "BANK288"),
        ("ON", "BANK161"),
        ("OFF", "BANK161"),
    ):
        name = selection + "/" + mode
        p = a.pair / name
        if name not in pair["arms"]:
            need(not p.exists(), "unreported physical arm")
            arms[name] = {"status": "NOT_RUN"}
            continue
        r = receipt(p / "receipt.json", pair["arms"][name]["receipt_sha256"])
        need(
            r["status"] == pair["arms"][name]["status"] and FR["inventory"](p) == r["raw_sha256"],
            "arm raw or status",
        )
        starts += r["model_starts"]
        result = dict(
            status=r["status"],
            model_starts=r["model_starts"],
            receipt_sha256=pair["arms"][name]["receipt_sha256"],
        )
        if selection == "ON":
            independent = G["rows_from_grade"](a.historical / mode / "native", historical[mode])
        else:
            independent = G["rows_from_grade"](a.pair / "ON" / mode / "native", grades[mode])
        available = FR["available_rows"](p)
        kept = {
            k: v for k, v in independent.items() if available.get(str(k), {}).get("bytes") == 804352
        }
        observed = OFF["compare_rows"](p / "native", kept)
        need(observed == r["available_contrasts"], "preserved logits")
        result["on_or_historical_changed_words"] = {
            k: v["changed_words"] for k, v in observed.items()
        }
        result["first_changed_indices"] = {k: v["first_changed_index"] for k, v in observed.items()}
        result["cuts"] = {
            k: {n: v[n] for n in ("unique_greedy_equal", "max_abs", "mean_abs", "rmse")}
            for k, v in observed.items()
        }
        if r["status"] == "FAIL_PRESERVED":
            result.update(
                reason=r.get("reason", r.get("final_error")),
                child_gone=r.get("child_gone"),
                returncode=r.get("returncode"),
            )
        else:
            need(
                r["returncode"] == 0
                and r["child_gone"]
                and r["restored"]
                and r["model_starts"] == 1,
                "cleanup",
            )
            if selection == "ON":
                grade = G["check_arm"](
                    mode,
                    (p / "raw/stdout").read_text(),
                    (p / "raw/stderr").read_text(),
                    p / "native",
                    a.plan,
                )
                grades[mode] = grade
                compare = G["against_references"](p / "native", grade, refs)
                need(OFF["R"]["serial"](compare) == r["references"], "independent gold")
                result["independent"] = {
                    k: {str(pos): v["rows"][pos]["changed_words"] for pos in (15, 16)}
                    for k, v in compare.items()
                }
                result["bias_sources"] = grade["bias_sources"]
            else:
                grade = OFF["grade"](mode, p, a.plan, a.pair / "ON", grades[mode])
                result.update(
                    source_and_slot=grade["source_and_slot"],
                    width_match=grade["width_match"],
                    submission_counts_match=grade["submission_counts_match"],
                    individual_routes=grade["individual_route_order"],
                )
            need(OFF["R"]["serial"](grade) == r["grade"], "regraded arm differs")
            result.update(phase_report(p, r, grade))
        arms[name] = result
    need(starts == pair["model_starts"], "starts")
    if set(grades) == {"BANK161", "BANK288"}:
        between = G["check_pair"](
            a.pair / "ON/BANK288/native",
            grades["BANK288"],
            a.pair / "ON/BANK161/native",
            grades["BANK161"],
        )
        need(OFF["R"]["serial"](between) == pair["between_on"], "current ON pair")
    if "between_off" in pair:
        off = {p: (a.pair / "OFF/BANK288/native" / f"pos{p}.f32").read_bytes() for p in (15, 16)}
        result = OFF["compare_rows"](a.pair / "OFF/BANK161/native", off)
        need(
            result == pair["between_off"] and OFF["decision"](result, True) == pair["status"],
            "current OFF pair",
        )
    return dict(
        status=pair["status"],
        physical_sha256=a.pair_sha256,
        commit=pair["authority"]["commit"],
        tree=pair["authority"]["tree"],
        monitor=monitor,
        model_sha256=pair["authority"]["model_sha256"],
        model_starts_pair=starts,
        stop_arm=pair.get("stop_arm"),
        arms=arms,
        tiny=dict(
            receipt_sha256=a.tiny_sha256,
            status=tiny["status"],
            memory_peak_B=tiny["memory_peak_B"],
            sampled_vram_MiB={k: v["sampled_vram_mib_max"] for k, v in tiny["arms"].items()},
            all_three_bitwise_to_history=all(
                v["cross_driver"]["bitwise"] for v in tiny["arms"].values()
            ),
        ),
        capacity=dict(
            receipt_sha256=a.capacity_sha256,
            peak_vram_MiB=cap["peak_vram_mib_sampled"],
            exit_vram_MiB=cap["exit_vram_mib"],
            namespace_read_B=cap["namespace_read_bytes"],
            startup_matrix_h2d_B=c["expert_H2D_request_bytes"],
            process_s=cap["elapsed_s"],
        ),
        review_model_starts=0,
        http_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "tiny",
        "capacity",
        "pair",
        "plan",
        "historical",
        "cpu-d0",
        "cpu-d1",
        "stock-file",
        "c110-parent",
        "new-output-dir",
    ):
        p.add_argument("--" + key, type=Path, required=True)
    for key in ("tiny-sha256", "capacity-sha256", "pair-sha256"):
        p.add_argument("--" + key, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = review(a)
    except Exception as exc:
        result = {"status": "FAIL_REVIEW_PRESERVED", "reason": str(exc)}
    with (a.new_output_dir / "review.json").open("x") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] == "FAIL_REVIEW_PRESERVED")

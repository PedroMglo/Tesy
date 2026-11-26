"""Reopen the four 120B sessions and price the groups missing from the earlier projection."""

import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
NATIVE = run_path(str(HERE / "http.py"))
AUDIT = run_path(str(HERE.parent / "review_family.py"))
R, H, G, need, save = (AUDIT[k] for k in ("R", "H", "G", "need", "save"))
MODES = NATIVE["MODES"]
FAILED = "98e0c9637454f5a00f4c449847ee9e6aae7820b1a743bb7f6addf2f1052ea864"
PREPARED = "6a5f2b0de63c32184bedbe19e9346b7914be55a31117fbcb8cb7ed541621fc87"
PROJECTION = "7b4be853003d9c52c84f11c2b7e6ac846842893e7424be7b0255d49c0d3e420d"
COMMIT = "59a12bfab5972e829c4a5bc55a8059cbe27727d0"


def arm(args, family, mode, cases, original, lookup):
    root = args.family / mode
    AUDIT["inputs_agree"](args.prepared, args.family, mode)
    child = R["reopen"](root, family["arms"][mode]["sha256"])
    provider = H["read"](root / "filter-provider.json")
    inputs = H["read"](root / "arm-inputs.json")
    need(
        provider == H["read"](args.prepared / mode / "filter-provider.json")
        and provider["arm"] == child["arm_label"] == mode
        and provider["numerical_mode"] == child["mode"] == MODES[mode]
        and inputs["commit"] == child["commit"] == COMMIT
        and inputs["protocol_sha256"] == child["protocol_sha256"] == NATIVE["METHOD"]
        and provider["active_schedule_sha256"] == inputs["plan_sha256"],
        "sealed provider and arm",
    )
    common = inputs["dso"]["libllama-common.so.0"]["sha256"]
    expected = lookup["images"]["CONTROL" if mode == "R" else "FILTER"]["ELF_sha256"]
    need(
        common == expected
        and inputs["env"].get("TESY_NGRAM_PREVIOUS_TOKEN") == ("1" if mode == "FILTER" else None),
        "common library and actual filter switch",
    )
    steps = original
    if mode in ("FILTER", "FIXED"):
        tag = "ON" if mode == "FILTER" else "OFF"
        sig = lookup["raw_digests"][tag]
        need(sig == inputs["plan_sha256"], "native proposal schedule")
        steps = G["read"](args.lookup_run / tag / "proposals.json", sig)
    evidence = R["observe"](root, MODES[mode], cases, steps)
    closure = H["read"](root / "closed-session.json")
    proof = H["read"](root / "runtime-proof.json")
    need(
        child["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
        and all(child[k] == v for k, v in closure.items())
        and proof == child["runtime_authority"]
        and proof["trajectories"] == evidence["trajectories"]
        and child["client_rows"] == evidence["rows"]
        and child["energy"] == evidence["energy"]
        and child["maxima"] == evidence["maxima"]
        and child["model_starts"] == 1
        and child["started_requests"] == 2
        and child["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE"
        and len(proof["cuts"]) >= 4
        and child["nominal_first_final_le_10s"] == (evidence["rows"][1]["first_final_s"] <= 10)
        and child["nominal_decode_ge_6"] == (evidence["rows"][1]["decode_tok_s"] >= 6),
        "raw clocks, complete native IDs, same-owner closure and resource gates",
    )
    summary = {k: evidence[k] for k in ("rows", "trajectories", "energy", "inventory", "maxima")}
    summary.update(
        common_sha256=common,
        graph_sha256=evidence["image_sha256"],
        plan_sha256=inputs["plan_sha256"],
        scope_s=child["wall_s"],
        ready_s=child["ready_s"],
        cleanup=child["cleanup"],
        post_signal_ms=(proof["verified_cleanup_ns"] - proof["signal"]["after_ns"]) / 1e6,
        c55_age_at_spawn_s=proof["c55_age_at_spawn_s"],
        fd_cuts=len(proof["cuts"]),
    )
    return summary, steps


def price(forecast, steps, ticks, reference, cut, row):
    total = AUDIT["position_cost"](steps, ticks, reference, cut)
    by_site = {s["at"]: s for s in steps if s["proposal"]}
    prices = forecast["pricing"]
    missing = prices["first_ON"]["unpriced"]
    need(missing == prices["second_ON"]["unpriced"], "same previously unpriced groups")
    measured = []
    for site in missing:
        at, count = site["at"], site["emitted"]
        end = at + count - 1
        need(
            count == by_site[at]["emitted"] and site["accepted"] == by_site[at]["accepted"],
            "previously unpriced group identified on target",
        )
        measured.append(
            dict(
                at=at,
                accepted=site["accepted"],
                confirmed=count,
                filter_us=ticks[end] - ticks[at - 1],
                serial_us=reference[end] - reference[at - 1],
                before_final=None if cut is None else at <= cut,
            )
        )
    cost = sum(v["filter_us"] for v in measured) / 1e6
    comparisons = {}
    for label, prediction in prices.items():
        combined = row["decode_s"] - prediction["conditional_zero_unpriced_decode_s"]
        comparisons[label] = dict(
            group_cost_plus_residual_s=combined,
            remaining_decode_residual_s=combined - cost,
            budget_to_equal_historical_serial_s=prediction[
                "available_new_cost_or_residency_change_to_equal_off_s"
            ],
            budget_to_six_s=prediction["available_new_cost_or_residency_change_to_six_s"],
        )
    return dict(
        conservation=total,
        new_groups=measured,
        new_group_sum_s=cost,
        server_decode_minus_producer_span_s=row["decode_s"] - total["on_span_us"] / 1e6,
        historical_projection=comparisons,
    )


def review(a):
    failed = R["reopen"](a.failed, FAILED)
    pre = R["reopen"](a.prepared, PREPARED)
    family = R["reopen"](a.family, a.family_sha256)
    need(
        failed["status"] == "FAIL_PRESERVED"
        and failed["model_starts"] == failed["started_requests"] == 0
        and failed["error"] == "ValueError: FILTER: ValueError: invalid session identity"
        and pre["status"] == "PREPARED_FOUR_ARMS"
        and pre["model_starts"] == pre["started_requests"] == 0
        and family["status"] == "GO_FOUR_NATURAL_DIAGNOSTICS"
        and pre["commit"] == family["commit"] == COMMIT
        and family["protocol_sha256"] == pre["protocol_sha256"] == NATIVE["METHOD"]
        and family["report_fixture_sha256"] == R["SERVER"]["REPORT_FIXTURE"]
        and family["report_protocol_sha256"] == R["METHOD"]
        and set(family["arms"]) == set(pre["arms"]) == set(MODES)
        and family["model_starts"] == 4
        and family["started_requests"] == 8,
        "failed first family and closed four-arm authority",
    )
    lookup = G["read"](HERE / "result.json", NATIVE["REVIEW"])
    forecast = G["read"](HERE.parent / "context-result.json", PROJECTION)
    cases, original = R["cases"](a)
    arms, steps = {}, {}
    for mode in MODES:
        arms[mode], steps[mode] = arm(a, family, mode, cases, original, lookup)
    positions, differences = {}, {}
    for i, label in enumerate(("T1", "T2"), 1):
        series = {m: AUDIT["ticks"](a.family / m, i) for m in MODES}
        clocks, cut = series["FILTER"]
        serial, serial_cut = series["SERIAL"]
        need(
            all(v[1] == cut for v in series.values())
            and cut == serial_cut
            and all(len(v[0]) == len(cases[label]["target"]) for v in series.values()),
            "same final-content boundary and output positions",
        )
        filtered = arms["FILTER"]["rows"][i - 1]
        positions[label] = price(
            forecast["turns"][label], steps["FILTER"][label], clocks, serial, cut, filtered
        )
        differences[label] = {
            m: {
                k: filtered[k] - arms[m]["rows"][i - 1][k]
                for k in ("prefill_s", "decode_s", "decode_tok_s", "first_final_s", "valid_s")
            }
            for m in MODES
            if m != "FILTER"
        }
    transitions = {}
    for m in list(MODES)[:-1]:
        p = H["read"](a.family / (m + "-closed-endpoint.json"))
        need(p["bind_available"] and p["previous"] == m, "independent process and closed port")
        transitions[m] = p["elapsed_s"]
    return dict(
        status=family["status"],
        commit=COMMIT,
        family_sha256=a.family_sha256,
        prepared_sha256=PREPARED,
        preserved_failure_sha256=FAILED,
        method_sha256=NATIVE["METHOD"],
        forecast_sha256=PROJECTION,
        arm_order=list(MODES),
        model_starts=4,
        natural_requests=8,
        wall_s=family["wall_s"],
        port_wait_s=transitions,
        arms=arms,
        positions=positions,
        filter_minus_control=differences,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "failed",
        "prepared",
        "family",
        "lookup-run",
        "capture",
        "verified",
        "plan",
        "new-output-dir",
    ):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    save(args.new_output_dir / "result.json", review(args))

"""Bound the four servers' physical read accounting across T1/T2 and price the nominal prefill."""

import argparse
import math
import os
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
AUDIT = run_path(str(HERE / "review_family.py"))
H, G, R, sha, need, save = (AUDIT[k] for k in ("H", "G", "R", "sha", "need", "save"))
PH = run_path(str(H["Q"] / "nvme_conversation/phase_reads/screen.py"))
METHOD = "b58d7e1b4253929dff925165dd85af1cdd15aefd1cb8ae911a7d398f2c8c8e4d"
FILTER = "7b4be853003d9c52c84f11c2b7e6ac846842893e7424be7b0255d49c0d3e420d"
PHYSICAL_REVIEW = "aa1f06224bfa702e79d5c351b94b11a51c2978436b37780cf021e880cf07f1df"
RATE = 4_500_000_000


def budget(seconds, bounds):
    # Round time and admissible bytes upwards to favor the candidate.
    ns = int((Decimal(str(seconds)) * 10**9).to_integral_value(rounding=ROUND_CEILING)) + 1
    need(ns > 0 and bounds["min"] >= 0, "admissible window")
    cap = (RATE * ns + 10**9 - 1) // 10**9
    lo, hi = bounds["min"], bounds["max"]
    state = (
        "NO_GO_SERVICE_FIXED"
        if lo > cap
        else "HEADROOM"
        if hi is not None and hi <= cap
        else "INCONCLUSIVE"
    )
    return dict(
        status=state,
        available_ns_rounded_up=ns,
        available_bytes_rounded_up=cap,
        minimum_removed_bytes=max(lo - cap, 0),
        minimum_mean_Bps_rounded_down=lo * 10**9 // ns,
    )


def compact(old, new):
    need(
        0 <= new["common_epoch_width_ns"] <= old["common_epoch_width_ns"]
        and all(
            old[k] == new[k]
            for k in (
                "samples",
                "sample_fd_counts",
                "backend_commit",
                "sample_support_extra_ns",
                "boundary_margin_ns",
            )
        ),
        "epoch intersection",
    )
    phases = {}
    for a, b in zip(old["turns"], new["turns"], strict=True):
        need(all(a[k] == b[k] for k in a if k != "phases"), "frozen durations")
        fields = {}
        for name, original in a["phases"].items():
            now = b["phases"][name]
            for metric, previous in original["counters"].items():
                v = now["counters"][metric]
                need(
                    v["min"] >= previous["min"]
                    and (
                        previous["max"] is None
                        or v["max"] is not None
                        and v["max"] <= previous["max"]
                    ),
                    "broader counter range after intersection",
                )
            fields[name] = dict(
                counters=now["counters"],
                samples=now["definitely_inside_samples"],
                previous_read_bytes=original["counters"]["read_bytes"],
            )
        phases["T" + str(b["turn"])] = dict(
            cache=b["cache_n"],
            prompt=b["prompt_n"],
            predicted=b["predicted_n"],
            prompt_ns=b["prompt_ns"],
            decode_ns=b["decode_ns"],
            first_final_ns=b["first_final_ns"],
            transport_ns=b["transport_ns"],
            valid_ns=b["validated_ns"],
            phases=fields,
        )
    return dict(
        samples=new["samples"],
        model_direct_fds=new["sample_fd_counts"],
        original_epoch_width_ns=old["common_epoch_width_ns"],
        tight_epoch_width_ns=new["common_epoch_width_ns"],
        turns=phases,
    )


def study(a):
    head, tree = G["tree"](G["REPO"])
    need(a.commit == head and sha(HERE / "io-protocol.md") == METHOD, "frozen source")
    family = R["reopen"](a.family, AUDIT["FAMILY"])
    physical = G["read"](a.review / "result.json", PHYSICAL_REVIEW)
    filt = G["read"](a.context / "result.json", FILTER)
    need(
        family["status"] == physical["status"] == "GO_FOUR_NATURAL_DIAGNOSTICS"
        and filt["four_arm_review_sha256"] == PHYSICAL_REVIEW,
        "candidate and controls",
    )
    for path, digest in PH["SOURCE"].items():
        need(sha(G["REPO"] / path) == digest, "monitor or client source")
    arms = {}
    for mode in H["MODES"]:
        root = a.family / mode
        child = R["reopen"](root, family["arms"][mode]["sha256"])
        proof = H["read"](root / "runtime-proof.json")
        cfg = H["read"](root / "preset.json")
        backend = Path(cfg["backend"])
        need(
            child["runtime_authority"] == proof
            and child["client_rows"] == physical["arms"][mode]["rows"]
            and proof["cuts"][-1]["monotonic_ns"]
            <= proof["signal"]["before_ns"]
            <= proof["signal"]["after_ns"]
            <= proof["verified_cleanup_ns"]
            and all(sha(backend / k) == v for k, v in PH["NATIVE"].items()),
            "native clock and close",
        )
        original = PH["phase_observations"](root)
        tightened = PH["phase_observations"](root, verified_cleanup_ns=proof["verified_cleanup_ns"])
        observed = compact(original, tightened)
        t = observed["turns"]["T2"]
        price = (
            Decimal(t["prompt_ns"] + 10**10 - t["first_final_ns"] + t["decode_ns"]) / 10**9
            - Decimal(t["predicted"]) / 6
        )
        observed["exact_six_fixed_exterior"] = budget(
            price, t["phases"]["native_prompt"]["counters"]["read_bytes"]
        )
        arms[mode] = observed
    bounds = arms["OFF"]["turns"]["T2"]["phases"]["native_prompt"]["counters"]["read_bytes"]
    fixed = physical["positions"]["T2"]["conditional_prefill_s_for_ten_s_if_best_priced_blocks"]
    prices = filt["turns"]["T2"]["pricing"]
    scenarios = {"perfect_selection_at_observed_groups": budget(fixed, bounds)}
    for label, rec in prices.items():
        x = rec["conditional_prefill_s_to_ten_with_free_unpriced"]
        need(math.isfinite(x), "filter budget")
        scenarios["context_filter_free_new_groups_" + label] = budget(x, bounds)
    return dict(
        status="REPRODUCED_PHASE_ENVELOPES",
        commit=head,
        tree=tree,
        method_sha256=METHOD,
        family_sha256=AUDIT["FAMILY"],
        context_sha256=FILTER,
        rate_Bps=RATE,
        denominator="process read_bytes at block layer; service-in-window is conditional",
        arms=arms,
        OFF_nominal_prefill_scenarios=scenarios,
        model_starts=0,
        new_http_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "review", "context", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = study(a)
    except Exception as exc:
        result = dict(
            status="FAIL_PRESERVED",
            error=f"{type(exc).__name__}: {exc}",
            commit=a.commit,
            protocol_sha256=METHOD,
            new_http_requests=0,
            model_starts=0,
        )
    save(a.new_output_dir / "result.json", result)
    print(result["status"], result.get("error", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")

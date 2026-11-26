"""Conditional traffic and exposed-time budgets in the measured natural packed arm."""

import argparse
import hashlib
import json
from decimal import Decimal
from fractions import Fraction
from math import ceil, floor
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[3]
DEVICE = "ee3541fe94f5b4b332ee4928249bd7e7084e5da88848572984adc54fa0b9564c"
PHASES = "c61f26fa85bb27dd2e7b20c36ebd939f189aab9955381f7382d6e12fe24fe574"
REPLAY = "78a53e6d93fed1ad9a9236d74b60b234546d32041f5e572998240b243b82fb7e"
NATURAL = QUAL / "phase_fd/integrated/t1_manager_bank/policy_snapshot/natural"
TERMINAL = "ea74c80eafd0038753454c0a3ee2f5266205d805d872ce4827babd6817e54c41"
NS = 10**9
BANDS = {"nominal_micron": 4_500_000_000, "ideal_link_without_overhead": 8_000_000_000}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned(path, expected):
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == expected, "pin " + path.name)
    return json.loads(raw)


def decision(rate, required, max_exposed=None, feasible_net=None):
    if rate < 6:
        return "INSUFFICIENT_DECODE_IN_THIS_SCENARIO"
    if max_exposed is None:
        return "UNIDENTIFIED_EXPOSED_SERVICE"
    need(
        max_exposed >= 0 and (feasible_net is None or feasible_net <= max_exposed),
        "inconsistent saving bounds",
    )
    if max_exposed < required:
        return "EXCLUDE_SCHEDULE_ONLY_IN_THIS_SCENARIO"
    if feasible_net is None or feasible_net < required:
        return "NO_WITNESS_AT_REQUIRED_GAIN"
    return "ADMIT_CONTROLLED_TEST_ONLY"


def transport(duration, byte_range):
    lo, hi = byte_range
    need(0 < lo <= hi and duration > 0, "range or budget")
    out = {}
    for name, bps in BANDS.items():
        cap = floor(duration * bps / NS)
        out[name] = {
            "Bps": bps,
            "budget_whole_bytes": cap,
            "minimum_bytes_to_avoid_or_move_outside_if_all_lower_must_cross": max(0, lo - cap),
            "fraction_of_lower_that_can_cross": cap / lo,
            "residual_after_all_lower_cross_ns_floor": floor(duration - Fraction(lo * NS, bps)),
        }
    return dict(
        lower_bytes=lo,
        upper_bytes=hi,
        needed_Bps_if_all_cross=[float(lo * NS / duration), float(hi * NS / duration)],
        scenarios=out,
    )


def budget(f, p, d, rate, outputs, span, fraction, pre, dec):
    need(
        rate > 0 and outputs in (46, 47) and 0 <= fraction <= 1 and 0 < span <= d,
        "rate, denominator or exposed credit",
    )
    d_new = Fraction(outputs * NS, rate)
    need(d_new <= d, "reprice only non-increasing native decode")
    x = fraction * min(d - d_new, span)
    available = p + 10 * NS - f + x
    need(available > 0, "no prompt budget")
    required = max(0, p - available)
    # Only an effective 47-output rate can be compared with the contract.
    product_rate = Fraction(47 * NS, d_new)
    return dict(
        denominator=outputs,
        requested_rate=float(rate),
        effective_product_tok_s=float(product_rate),
        exposed_fraction_of_max=float(fraction),
        exposed_credit_ns_floor=floor(x),
        prefill_available_ns_floor=floor(available),
        required_prefill_saving_ns_ceil=ceil(required),
        native_decode_budget_ns_floor=floor(d_new),
        decision=decision(product_rate, required),
        prefill=transport(available, pre),
        decode=transport(d_new, dec),
    )


def bounds(row):
    v = row["counters"]["cgroup_submitted_rbytes"]
    need(
        row["status"] == "BOUNDED_NATIVE_PHASE"
        and row["density"] == "SUFFICIENT"
        and v["observed_monotone_in_window"],
        "phase coverage",
    )
    return v["lower"], v["upper"]


def assess():
    dev = pinned(HERE.parent / "receipt.json", DEVICE)
    phase = pinned(HERE.parent / "phases/receipt.json", PHASES)
    replay = pinned(NATURAL / "prefill_frontier/transport/joint/receipt.json", REPLAY)
    need(
        phase["terminal_sha256"] == dev["receipt_sha256"] == TERMINAL
        and phase["trace_sha256"] == dev["observer_trace_sha256"]
        and phase["arm_sha256"] == dev["arm_sha256"]
        and phase["archive_manifest_sha256"] == dev["archive"]["manifest"]["sha256"]
        and phase["turns"]["T2"]["sampled_ids_sha256"] == dev["ordered_id_sha256"]
        and dev["unit_closed"]
        and dev["launches"] == 1
        and dev["requests"] == 2,
        "one terminal P",
    )
    t = phase["turns"]["T2"]
    f, p, d = dev["first_final_ns"], dev["prefill_ns"], dev["decode_ns"]
    need(
        Decimal(t["times"]["prompt_ns"]) == p and Decimal(t["times"]["decode_ns"]) == d,
        "same clocks",
    )
    sample = dev["clocks"]["sample"]
    span = sample["span_ns"]
    need(
        sample["evaluations"] == 44 and f - span == sample["fixed_exterior_ns"] and 0 < span <= d,
        "up to first final",
    )
    pre, dec = bounds(t["phases"]["prompt"]), bounds(t["phases"]["decode"])
    r0 = Fraction(47 * NS, d)
    need(abs(float(r0) - dev["t2_decode_tok_s"]) < 1e-12, "47 product outputs")
    args = (f, p, d)
    cases = {"observed": budget(*args, r0, 47, span, Fraction(0), pre, dec)}
    for r in (6, 8, 10):
        cases[f"at_{r}"] = {
            name: budget(*args, r, 47, span, fr, pre, dec)
            for name, fr in (
                ("none_exposed", Fraction(0)),
                ("half", Fraction(1, 2)),
                ("all_exposed", Fraction(1)),
            )
        }
    old = {}
    for order in ("RP", "PR"):
        packet = replay["arms"][order]["P"]
        calls = packet["calls"]
        need(
            [c["tokens"] for c in calls] == [5, 148]
            and sum(c["jobs"] for c in calls) == 1058
            and sum(c["service_ns"] for c in calls) == packet["service_ns"],
            "isolated replay",
        )
        payload = sum(c["payload_bytes"] for c in calls)
        old[order] = dict(
            jobs=1058,
            payload_bytes=payload,
            drain_ns=packet["service_ns"],
            useful_Bps=float(Fraction(payload * NS, packet["service_ns"])),
            transferred_to_new_scope=False,
        )
    return dict(
        status="CONDITIONAL_BUDGET_NO_SERVICE_ATTRIBUTION",
        arm_sha256=dev["arm_sha256"],
        terminal_sha256=TERMINAL,
        source_receipts={"device": DEVICE, "phases": PHASES, "isolated_replay": REPLAY},
        code_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
        first_final_ns=f,
        prefill_ns=p,
        decode_ns=d,
        producer_span_through_final_ns=span,
        producer_tail_after_first_final_ns=sample["tail_ns"],
        first_sample_of_final=45,
        intercept_prefill_budget_ns=p + 10 * NS - f,
        intercept_required_saving_ns=f - 10 * NS,
        scenarios_47_outputs=cases,
        alternative_46_evaluations_per_six=budget(*args, 6, 46, span, Fraction(1), pre, dec),
        isolated_other_population=old,
        assumptions="FIXED_EXTERIOR_ORDERED_PHASES_AND_NONREGRESSING_TAIL",
        schedules_measured=0,
        new_model_launches=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    out = parser.parse_args().new_output_dir
    out.mkdir(mode=0o700)
    try:
        record = assess()
    except Exception as err:
        record = {"status": "FAIL_PRESERVED", "reason": f"{type(err).__name__}: {err}"}
    with (out / "receipt.json").open("x") as f:
        print(json.dumps(record, indent=2, sort_keys=True, allow_nan=False), file=f)
    print(record["status"], record.get("reason", ""))
    raise SystemExit(int(record["status"] == "FAIL_PRESERVED"))

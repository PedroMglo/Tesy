"""Evaluate all independent prefill/decode order combinations on the nominal T2 wall clock."""


def price(volume, prefill_ns, decode_ns, gap_ns, total_ns):
    if min(volume, prefill_ns, decode_ns, total_ns) <= 0 or gap_ns < 0:
        raise ValueError("invalid payload or elapsed time")
    allowed = total_ns - decode_ns - gap_ns
    margin = allowed - prefill_ns
    return dict(
        prefill_read_service_ns=prefill_ns,
        decode_price_ns=decode_ns,
        gap_ns=gap_ns,
        margin_ns=margin,
        observed_phase_budget_ns=total_ns,
        projected_first_final_ns=10_000_000_000 - margin,
        useful_bytes_per_s=1e9 * volume / prefill_ns,
        payload_budget_at_this_mean_rate_bytes=max(0, volume * allowed // prefill_ns),
        decision="HEADROOM_ONLY" if margin >= 0 else "NO_GO_FIXED_PRICES",
    )


def cross(frontier, prefill):
    total = frontier["budget_prefill_plus_decode_ns"]
    gaps = {
        "serial": frontier["gaps"]["total_ns"],
        "ideal_two_tiles": frontier["gaps"]["protected_ns"],
        "all_gaps_free": 0,
    }
    volume = frontier["work"]["prefill"]["payload_bytes"]
    if set(prefill) != {"RP", "PR"} or set(frontier["pack_orders"]) != set(prefill):
        raise ValueError("expected both orders in each independent measurement")
    by_gap = {}
    for label, gap in gaps.items():
        results = {
            p + "_" + d: price(volume, measured, prices["conditional_decode_ns"], gap, total)
            for p, measured in prefill.items()
            for d, prices in frontier["pack_orders"].items()
        }
        decisions = {r["decision"] for r in results.values()}
        by_gap[label] = dict(
            pairs=results,
            decision=decisions.pop() if len(decisions) == 1 else "INCONCLUSIVE_ORDERS",
            least_margin_ns=min(r["margin_ns"] for r in results.values()),
            greatest_margin_ns=max(r["margin_ns"] for r in results.values()),
        )
    return by_gap

"""Exact initial placement on disjoint, at-most-four-job decode barriers.

A state at cardinality k maximizes (saved barrier microseconds, selection mask).
Higher bits represent earlier (layer, expert) keys. Among equal-cardinality
sets with equal savings the higher mask contains the smallest differing key
and is therefore lexicographically first.
"""

from collections import Counter
from collections.abc import Mapping
from itertools import combinations

LAYERS = 36
EXPERTS = 128
BUDGET_NUMERATOR_US = 16_000_000


def bit(layer, expert):
    return 1 << (LAYERS * EXPERTS - 1 - (layer * EXPERTS + expert))


def index(value, bound):
    return type(value) is int and 0 <= value < bound


def merge(left, right, capacity):
    """Independent groups/layers add gains; every split of k is visited."""
    width = min(capacity + 1, len(left) + len(right) - 1)
    result = [None] * width
    for j, (right_gain, right_mask) in enumerate(right[:width]):
        for i in range(min(width - j, len(left))):
            left_gain, left_mask = left[i]
            candidate = (left_gain + right_gain, left_mask | right_mask)
            pos = i + j
            if result[pos] is None or candidate > result[pos]:
                result[pos] = candidate
    return result


def local_options(layer, jobs, possible, cap, baseline):
    allowed = [e for e in jobs if (layer, e) in possible]
    choices = [(0, 0)]
    for k in range(1, min(len(allowed), cap) + 1):
        candidates = []
        for removed in combinations(allowed, k):
            residual = max(
                (us for e, us in jobs.items() if e not in removed), default=0
            )
            mask = sum(bit(layer, e) for e in removed)
            candidates.append((baseline - residual, mask))
        choices.append(max(candidates))
    return choices


def solve(groups, caps, eligible, fixed_us, numerator, denominator):
    """Return optimal placement, remaining unscaled READ us, and k-1 certificate.

    Each group is (layer, {expert: service_us}); service_us is its complete
    serial READ chain, already corrected by the caller. Each key occurs once.
    Capacity concerns initial slots in each of 36 layers. Eligibility
    may include valid keys absent from this decode: those cannot contribute.
    If unreachable, k is the smallest placement achieving maximum gain.
    """
    caps = tuple(caps)
    if len(caps) != LAYERS or any(type(c) is not int or c < 0 for c in caps):
        raise ValueError("expected 36 nonnegative integral layer capacities")
    if any(type(v) is not int for v in (fixed_us, numerator, denominator)) or (
        fixed_us < 0 or numerator <= 0 or denominator <= 0
    ):
        raise ValueError("invalid unscaled fixed time or positive rational scale")
    possible = set(eligible)
    if any(
        not isinstance(key, tuple)
        or len(key) != 2
        or not index(key[0], LAYERS)
        or not index(key[1], EXPERTS)
        for key in possible
    ):
        raise ValueError("invalid eligible expert identity")

    layers = [[(0, 0)] for _ in caps]
    demand = set()
    entries = []
    baseline = 0
    for layer, supplied in groups:
        if (
            not index(layer, LAYERS)
            or not isinstance(supplied, Mapping)
            or len(supplied) > 4
        ):
            raise ValueError("invalid four-worker barrier")
        jobs = dict(supplied)
        for e, us in jobs.items():
            if not index(e, EXPERTS) or type(us) is not int or us < 0:
                raise ValueError("invalid expert or READ microseconds")
            if (layer, e) in demand:
                raise ValueError("first miss represented more than once")
            demand.add((layer, e))
        entries.append((layer, jobs))
        old = max(jobs.values(), default=0)
        baseline += old
        local = local_options(layer, jobs, possible, caps[layer], old)
        if len(local) > 1:
            layers[layer] = merge(layers[layer], local, caps[layer])

    states = [(0, 0)]
    for layer_states in layers:
        if len(layer_states) > 1:
            states = merge(states, layer_states, len(states) + len(layer_states) - 2)

    def fits(residual):
        return (
            3 * (denominator * fixed_us + numerator * residual)
            <= BUDGET_NUMERATOR_US * denominator
        )

    maximum_gain = max(row[0] for row in states)
    first_feasible = next(
        (i for i, (gain, _) in enumerate(states) if fits(baseline - gain)), None
    )
    k = (
        first_feasible
        if first_feasible is not None
        else next(i for i, (gain, _) in enumerate(states) if gain == maximum_gain)
    )
    gain, mask = states[k]
    chosen = sorted(key for key in demand if mask & bit(*key))
    picked = set(chosen)
    residual = sum(
        max((v for e, v in jobs.items() if (layer, e) not in picked), default=0)
        for layer, jobs in entries
    )
    counts = Counter(layer for layer, _ in chosen)
    previous = baseline - states[k - 1][0] if k else None
    feasible = first_feasible is not None
    if (
        len(chosen) != k
        or not picked <= possible
        or any(counts[i] > caps[i] for i in counts)
        or residual != baseline - gain
        or fits(residual) != feasible
        or previous is not None
        and (fits(previous) or previous <= residual and not feasible)
    ):
        raise ArithmeticError("placement or minimality certificate inconsistent")
    return dict(
        reaches=feasible,
        k=k,
        chosen=chosen,
        remaining_us=residual,
        k_minus_one_remaining_us=previous,
        maximum_gain_us=maximum_gain,
    )

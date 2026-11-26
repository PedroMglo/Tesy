"""Best offline allocation of initial encoded copies to independent C295 service barriers."""

from itertools import combinations


def choices(group, seen):
    """For each copy count keep only the best enumerated subset on this barrier."""
    rows = list(group)
    if len(rows) > 4:
        raise ValueError("barrier has more than four services")
    local = set()
    eligible = {}
    for key, read, retained, state in rows:
        if not (
            isinstance(key, tuple)
            and len(key) == 2
            and all(type(k) is int for k in key)
            and 0 <= key[0] < 36
            and 0 <= key[1] < 128
        ):
            raise ValueError("invalid (layer, expert)")
        if (
            key in local
            or state not in ("free", "eligible", "cold")
            or state != "free"
            and key in seen
        ):
            raise ValueError("inconsistent service identity or state")
        if any(type(x) is not int or x < 0 for x in (read, retained)):
            raise ValueError("expected nonnegative integer microseconds")
        local.add(key)
        if state == "eligible":
            # A higher-order bit means a lexicographically smaller key.
            eligible[key] = 1 << (4607 - (key[0] * 128 + key[1]))
    if len({layer for layer, _ in local}) > 1:
        raise ValueError("mixed layers in a barrier")
    seen.update(local)

    def duration(chosen):
        return max(
            (
                retained if state == "free" or key in chosen else retained + read
                for key, read, retained, state in rows
            ),
            default=0,
        )

    baseline = duration(())
    options = []
    for count in range(len(eligible) + 1):
        options.append(
            max(
                (baseline - duration(subset), sum(eligible[key] for key in subset))
                for subset in combinations(eligible, count)
            )
        )
    return baseline, options


def resolve(groups, limits):
    """Maximize the sum of group gains over disjoint eligible first-service keys.

    DP[c] records the greatest gain achievable with exactly c copies across the
    processed groups. Extending by every local count enumerates all partitions of c.
    The maximal tie mask keeps the lexicographically first equal-size key set.
    At each requested budget choose the greatest gain, then the fewest copies,
    then the first key set. gain_us measures improvement over the free-repeat K=0 case.
    """
    limits = list(limits)
    if any(type(k) is not int or k < 0 for k in limits):
        raise ValueError("invalid slot budget")
    limits = sorted({0, *limits})
    seen = set()
    dp = [(0, 0)]
    baseline = 0
    for group in groups:
        old, options = choices(group, seen)
        baseline += old
        if len(options) == 1 or len(dp) == 1 and limits[-1] == 0:
            continue
        width = min(limits[-1] + 1, len(dp) + len(options) - 1)
        after = [None] * width
        for count, (gain, mask) in enumerate(options):
            for n in range(min(len(dp), width - count)):
                prior_gain, prior_mask = dp[n]
                candidate = (prior_gain + gain, prior_mask | mask)
                at = n + count
                if after[at] is None or candidate > after[at]:
                    after[at] = candidate
        dp = after
    answers = {}
    for cap in limits:
        gain, _, mask = max((g, -n, m) for n, (g, m) in enumerate(dp[: cap + 1]))
        chosen = sorted(key for key in seen if mask & (1 << (4607 - (key[0] * 128 + key[1]))))
        answers[cap] = {"gain_us": gain, "chosen": chosen, "group_max_sum_us": baseline - gain}
    return answers

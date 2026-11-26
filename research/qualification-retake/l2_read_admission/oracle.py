"""Coverage ceilings for an offline encoded L2 that may bypass any P10 publication."""

from bisect import bisect_right, insort


def maximum_hits(intervals, capacity):
    """Maximum number of intervals that can be kept with <= capacity overlapping.

    A kept interval consumes one encoded slot from publication to the next lookup.
    At each new start consider retaining it along with all previously retained live
    intervals. On overflow every solution must forgo at least one of these overlapping
    intervals. Dropping the latest end leaves the remaining resources free at least as
    early as dropping any other. By exchange, the choice can be imposed on an optimum:
    replacing the kept latest end by the shorter rejected interval preserves feasibility
    from this start onward; prior to this start all previously kept intervals fitted.
    Intervals already completed retain their hits. This is the unit-value interval
    scheduling algorithm for K interchangeable slots.
    """
    if type(capacity) is not int or capacity < 0:
        raise ValueError("capacity must be a nonnegative integer")
    active_ends = []
    hits = 0
    for start, end in sorted(intervals):
        if type(start) is not int or type(end) is not int or not 0 <= start < end:
            raise ValueError("invalid retention interval")
        del active_ends[: bisect_right(active_ends, start)]
        insort(active_ends, end)
        if len(active_ends) > capacity:
            active_ends.pop()
        else:
            hits += 1
    return hits


def bounds(increment, decode, capacity):
    """Inputs are (P5 seq, P10 seq, (layer, expert)) in claim order in each phase.

    Empty at P. A key can first enter L2 at a real P10. Even a hit gets a free new
    copy at its P10, leaving P5→P10 staging outside L2; a published value can bypass.
    Thus eligible hits are exactly the retained intervals in this relaxation. For
    decode only, prefill hits carry zero weight: retain the intervals that end
    in decode, including those beginning at a publication before I. The two optima
    use future knowledge and may require different schedules.
    """
    increment, decode = tuple(increment), tuple(decode)
    complete, decoded = [], []
    last_publication = {}
    seen_events = set()
    previous_claim = -1
    last_increment_publication = -1
    eligible_count = 0
    for is_decode, phase in ((False, increment), (True, decode)):
        for claim, publication, key in phase:
            if (
                type(claim) is not int
                or type(publication) is not int
                or not 0 <= claim < publication
                or claim <= previous_claim
                or claim in seen_events
                or publication in seen_events
            ):
                raise ValueError("invalid P5/P10 linearization")
            if not isinstance(key, tuple) or len(key) != 2 or any(type(x) is not int for x in key):
                raise ValueError("expected (layer, expert) key")
            if not (0 <= key[0] < 36 and 0 <= key[1] < 128):
                raise ValueError("expert key outside C294")
            if is_decode and claim <= last_increment_publication:
                raise ValueError("I cut is not drained")
            if not is_decode:
                last_increment_publication = max(last_increment_publication, publication)
            if key in last_publication:
                start = last_publication[key]
                if start >= claim:
                    raise ValueError("same identity already in flight")
                interval = (start, claim)
                complete.append(interval)
                if is_decode:
                    decoded.append(interval)
            last_publication[key] = publication
            previous_claim = claim
            seen_events.update((claim, publication))
        if not is_decode:
            eligible_count = len(last_publication)
    joint = maximum_hits(complete, capacity)
    last = maximum_hits(decoded, capacity)
    return {
        "capacity": capacity,
        "increment_reads": len(increment),
        "decode_reads": len(decode),
        "distinct_seen_at_I": eligible_count,
        "joint_hits": joint,
        "joint_misses": len(increment) + len(decode) - joint,
        "decode_only_hits": last,
        "decode_only_misses": len(decode) - last,
    }

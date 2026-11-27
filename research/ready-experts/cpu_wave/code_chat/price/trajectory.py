"""Reconcile actual sampled tokens, feeds, proposals, and accepted depths on one task clock."""

from itertools import pairwise


def evaluate(log, index, entry, steps, block, trajectory):
    native = trajectory["V"]
    need = trajectory["need"]
    events = list(native["events"](log))
    tasks = [task for _, task, e in events if e == ("start",)]
    need(len(tasks) == len(set(tasks)) and index <= len(tasks) <= 2, "native task count")
    task = tasks[index - 1]
    rows = [(t, e) for t, owner, e in events if owner == task]
    need(all(a[0] <= b[0] for a, b in pairwise(rows)), "native clock")
    tokens = entry["target"]
    n = len(tokens)
    prompt = len(entry["prompt"])
    cap = entry["cap"]
    samples = [(t, e) for t, e in rows if e[0] == "sample"]
    need(
        [e[0] for _, e in rows if e[0] != "feed"]
        == ["start", *(["sample"] * (n - 1)), "eos", "sample", "end"]
        and rows[-1][1] == ("end", prompt + n - 1)
        and tokens[-1] == 200002
        and [(e[1], e[2], e[3]) for _, e in samples]
        == [(j, cap - j, id_) for j, id_ in enumerate(tokens, 1)],
        "frozen greedy output, prompt or budget",
    )
    batches = []
    decisions = []
    feeds = []
    schedule = (
        steps if block else [dict(at=j, proposal=[], accepted=0, emitted=1) for j in range(1, n)]
    )

    def tick(t):
        m, s, ms, us = t
        return ((m * 60 + s) * 1000 + ms) * 1000000 + us * 1000

    times = [tick(t) for t, _ in samples]
    ordinary_ns = block_ns = 0
    for step in schedule:
        at = step["at"]
        proposal = step["proposal"]
        pos = prompt + at - 1
        elapsed = times[at + step["emitted"] - 1] - times[at - 1]
        if proposal:
            accepted = step["accepted"]
            batches.append((tokens[at - 1], pos, len(proposal), pos))
            decisions.append((tokens[at + accepted], accepted + 1, len(proposal)))
            block_ns += elapsed
        else:
            feeds.append(("feed", tokens[at - 1], pos))
            ordinary_ns += elapsed

    def native_rows(key):
        return [
            tuple(map(int, m.groups()[5:]))
            for m in trajectory[key].finditer(log)
            if int(m.group(5)) == task
        ]

    need(
        [e for _, e in rows if e[0] == "feed"] == feeds
        and native_rows("DRAFT") == batches
        and native_rows("ACCEPT") == decisions
        and ordinary_ns + block_ns == times[-1] - times[0],
        "causal service conservation",
    )
    return dict(
        sampled=n,
        sampled_sha256=native["digest"](native["ids_bytes"](tokens)),
        eos=1,
        proposed=sum(x[2] for x in batches),
        accepted=sum(x[1] - 1 for x in decisions),
        blocks=len(batches),
        serial=len(feeds),
        ordinary_ns=ordinary_ns,
        block_ns=block_ns,
        sample_span_ns=times[-1] - times[0],
    )

"""Replay two causal small-memory proposers on sealed target IDs, through sampled EOG."""

import argparse
import hashlib
import json
import resource
import struct
import time
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
N2 = ROOT / "research/qualification-retake/history_lookup/causal_pair/screen.py"
clock = time.perf_counter_ns


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


class Index:
    def __init__(self):
        self.history = []
        self.counts = defaultdict(Counter)

    def add(self, token):
        h = self.history
        h.append(token)
        pair = tuple(h[-2:])
        for k in range(1, min(4, len(h) - 2) + 1):
            self.counts[tuple(h[-k - 2 : -2])][pair] += 1

    def propose(self):
        for k in range(min(4, len(self.history)), 0, -1):
            seen = self.counts.get(tuple(self.history[-k:]))
            if seen:
                pair, votes = seen.most_common(1)[0]
                total = seen.total()
                if total >= 2 and 2 * votes > total:
                    return pair
        return ()


class Scan:
    def __init__(self, old=None):
        self.history = []
        self.old = old

    def add(self, token):
        self.history.append(token)

    def propose(self):
        h = self.history
        if self.old:
            return tuple(self.old(tuple(h), 2, 2))
        for size in range(4, 0, -1):
            key = h[-size:]
            pairs = [
                tuple(h[i + size : i + size + 2])
                for i in range(len(h) - size - 1)
                if h[i : i + size] == key
            ]
            if len(pairs) >= 2:
                top, count = Counter(pairs).most_common(1)[0]
                if count > len(pairs) // 2:
                    return top
        return ()


def replay(model, prompt, target, cap, eog):
    need(
        target and target[-1] == eog and eog not in target[:-1] and len(target) <= cap,
        "target stop",
    )
    at = 1
    start = clock()
    for token in prompt:
        model.add(token)
    model.add(target[0])
    prep = clock() - start
    rows, timing = [], []
    while True:
        begin = clock()
        pair = model.propose() if cap - at >= 3 else ()
        choose = clock() - begin
        depth = 0
        emitted = []
        for q in pair:
            token = target[at + depth]
            if token != q:
                break
            depth += 1
            emitted.append(token)
            if token == eog:
                break
        if not emitted or emitted[-1] != eog:
            emitted.append(target[at + depth])
        update = clock()
        for v in emitted:
            model.add(v)
        end = clock()
        rows.append((at, pair, depth, len(emitted)))
        timing.append([choose, end - update])
        at += len(emitted)
        if emitted[-1] == eog or at == cap:
            break
    need(at == len(target) and emitted[-1] == eog, "emissions through EOG")
    return rows, timing, prep


def run(inputs):
    receipt = inputs / "receipt.json"
    need(
        hashlib.sha256(receipt.read_bytes()).hexdigest()
        == "17285d7438cedc23a0db6c119ee8a315eb06b4a45ab97aeaef623bb25c20c356",
        "target inputs",
    )
    need(
        hashlib.sha256(N2.read_bytes()).hexdigest()
        == "797746256c463790abc44463e56948636fa63b03f9d0e710daa29203f8a9846e",
        "N2 source",
    )
    old = run_path(N2)["draft"]
    seal = json.loads(receipt.read_bytes())
    result = {}
    for name, cap in (("nominal", 256), ("code", 768)):

        def ids(kind, case=name):
            f = f"{case}-{kind}.i32"
            b = (inputs / f).read_bytes()
            need(hashlib.sha256(b).hexdigest() == seal["files"][f], "trajectory changed")
            return [x[0] for x in struct.iter_unpack("<i", b)]

        prompt, target = ids("prompt"), ids("target")
        # Both declared EOGs are the same Harmony special verified against both vocabularies.
        need(target[-1] == 200002, "unexpected terminal ID")
        args = (prompt, target, cap, 200002)
        result[name] = {}
        for key, model in (("N2", Scan(old)), ("majority", Index())):
            rows, times, prep = replay(model, *args)
            if key == "majority":
                independently, _, _ = replay(Scan(), *args)
                need(
                    rows == independently, "indexed proposal differs from independent prefix search"
                )
            result[name][key] = dict(
                decisions_sha256=hashlib.sha256(
                    json.dumps(rows, separators=(",", ":")).encode()
                ).hexdigest(),
                rows=[[at, len(q), depth, n] for at, q, depth, n in rows],
                timing_ns=times,
                prep_ns=prep,
            )
    return dict(
        status="REPRODUCED_CAUSAL_EOG",
        cases=result,
        max_rss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a.inputs)
        need(result["max_rss_KiB"] < 128 * 1024, "memory budget")
        with (a.new_output_dir / "receipt.json").open("x") as f:
            json.dump(result, f, sort_keys=True, separators=(",", ":"))
    except Exception as exc:
        (a.new_output_dir / "failure.json").write_text(
            json.dumps(dict(status="FAIL_PRESERVED", reason=str(exc)))
        )
        raise
    print(result["status"])

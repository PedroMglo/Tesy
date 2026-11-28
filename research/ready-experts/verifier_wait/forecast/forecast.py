"""Replay two causal sources of expert forecasts on the authenticated nominal trajectory."""

import argparse
import gzip
import hashlib
import json
import os
import struct
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SERVICE = run_path(HERE.parent / "service.py")
T = SERVICE["T"]
need, sha, load = (SERVICE[k] for k in ("need", "sha", "load"))
TRAIN = run_path(HERE.parents[1] / "selection.py")
PROFILE = TRAIN["PROFILE"]
PROTOCOL = "7027b6bcc0f412997b4d3f9f100e7c8a2d009795c8f92b064946f97668baf3f8"
WORK = "36e75d97017211eeffebb8877e0da0dc4ee15977fb7600cc1f141053c0caae9c"
PREFIX = "5ea6f7c31dadef873b200c8912ca17d07d98ede4b91c2e17ea2590b3f751aad1"
JOURNAL = "cb13ff990afb3164bb61086e57a6caeff14187b66a1784c88e79cd3d521121bd"
SERIAL = "659010baad96c09bbd26d709f24addd8601dcdcad5c8cb6ca94fe1172333784a"
CONTROL = HERE.parent / "evidence-service-20261128-r03/service.json"
CONTROL_SHA = "f1ef8293af3c9c0f872f9fb301f131fde7319821ebf04717bf8ae31c7e092c23"
MODES = (
    "off",
    "token",
    "token_marginal",
    "token_top4_free",
    "token_support_free",
    "upstream",
    "upstream_marginal",
    "upstream_top4_free",
)
PPM = 1_000_000


def save(path, data):
    raw = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if path.suffix == ".gz":
        raw = gzip.compress(raw, compresslevel=6, mtime=0)
    with path.open("xb") as out:
        out.write(raw)


def verified(path, digest):
    need(sha(path) == digest, "digest: " + path.name)
    return load(path)


def split(work, out):
    w = verified(work, WORK)
    tokens = w["t1"] + w["first"][:-1]
    raw = struct.pack(f"<{len(tokens)}i", *tokens)
    need(len(tokens) == 2120 and hashlib.sha256(raw).hexdigest() == PREFIX, "consumed T1 IDs")
    with (out / "prefix.i32").open("xb") as f:
        f.write(raw)


def positions(rows):
    """The final router gets only the requested last position, even in a multi-token tile."""
    tile = None
    for r in rows:
        if r.kind == 3:
            need(tile is None, "nested tile")
            start, tile = r.b, [{} for _ in range(r.a)]
        elif r.kind == 27:
            need(tile is not None and 0 <= r.b < len(tile), "rank outside tile")
            pos = len(tile) - 1 if r.layer == 35 else r.b
            need(r.layer not in tile[pos] and (r.layer != 35 or r.b == 0), "duplicate routed row")
            tile[pos][r.layer] = tuple(r.a.to_bytes(4, "little"))
        elif r.kind == 4:
            need(tile is not None, "empty tile")
            for i, layers in enumerate(tile):
                need(set(layers) in (set(range(35)), set(range(36))), "incomplete router coverage")
                yield start + i, layers
            tile = None
    need(tile is None, "unterminated tile")


class Frequencies:
    def __init__(self):
        self.by_token = defaultdict(Counter)
        self.by_upstream = defaultdict(Counter)
        self.marginal = [Counter() for _ in range(36)]

    def observe(self, token, layers):
        for layer, ids in layers.items():
            self.by_token[token, layer].update(ids)
            self.marginal[layer].update(ids)
            if layer >= 2:
                for source in layers[layer - 2]:
                    self.by_upstream[source, layer].update(ids)

    def token_scores(self, token, layer):
        counts = self.by_token.get((token, layer), {})
        return counts, sum(counts.values()) // 4

    def upstream_scores(self, sources, layer):
        scores = Counter()
        for source in sources:
            counts = self.by_upstream.get((source, layer), {})
            n = sum(counts.values()) // 4
            for expert, count in counts.items():
                scores[expert] += count * PPM // n
        return scores, 4 * PPM

    def pack(self):
        def table(counts):
            return [[key, layer, sorted(c.items())] for (key, layer), c in sorted(counts.items())]

        return {"token": table(self.by_token), "upstream": table(self.by_upstream)}

    @classmethod
    def unpack(cls, data):
        model = cls()
        for token, layer, rows in data["token"]:
            counts = Counter(dict(rows))
            model.by_token[token, layer] = counts
            model.marginal[layer].update(counts)
        for source, layer, rows in data["upstream"]:
            model.by_upstream[source, layer] = Counter(dict(rows))
        return model


def train(a, out):
    need(sha(a.prefix) == PREFIX, "private prefix")
    tokens = [v for (v,) in struct.iter_unpack("<i", a.prefix.read_bytes())]
    seal = verified(a.arm / "before-t2.json", TRAIN["T1_SEAL"])
    n = seal["records"]
    path = a.arm / "observer/events.pfj"
    grade, _ = PROFILE["prefix_grade"](PROFILE["iter_rows"](path, 0, n), PROFILE["T1"], 9)
    need(n == 87736 and all(grade[k] == seal[k] for k in grade), "T1 seal")
    model = Frequencies()
    ranks = seen = 0
    for pos, layers in positions(PROFILE["iter_rows"](path, 0, n)):
        need(pos == seen, "T1 ordinal")
        model.observe(tokens[pos], layers)
        seen += 1
        ranks += len(layers)
    need(seen == len(tokens) and ranks == grade["ranks"], "T1 training extent")
    table = out / "model.json.gz"
    save(table, model.pack())
    save(
        out / "train.json",
        dict(
            prefix=PREFIX,
            journal_prefix=grade["sha256"],
            records=n,
            positions=seen,
            ranks=ranks,
            table=sha(table),
            program=sha(Path(__file__)),
            protocol=PROTOCOL,
        ),
    )


def choices(scores, total, present, marginal):
    eligible = sorted(
        (e for e, n in scores.items() if n > 0 and e not in present),
        key=lambda e: (-scores[e], e),
    )
    top = eligible[:4]
    issued = [e for e in top if 2 * scores[e] >= total]
    control = sorted((e for e in marginal if e not in present), key=lambda e: (-marginal[e], e))[
        : len(issued)
    ]
    need(len(control) == len(issued), "matched issue count")
    return tuple(map(set, (issued, control, top, eligible)))


class Inventory:
    """Compare each transition with the sealed two-stage bank before exposing another snapshot."""

    def __init__(self, data):
        self.primary = {
            (layer, slot): (expert, gen) for layer, slot, expert, gen in data["initial"]
        }
        self.present = [set() for _ in range(36)]
        for (layer, _), (expert, _) in self.primary.items():
            self.present[layer].add(expert)
        freq = Counter({(layer, expert): n for layer, expert, n in data["counts"]})
        caps = T["quotas"](freq)
        seed = list(map(tuple, data["seed"]))
        self.pools = [
            T["Pool"](
                cap,
                [k for k in seed if k[1] not in self.present[k[0]] and T["stage"](k[0]) == i],
                freq,
            )
            for i, cap in enumerate(caps)
        ]
        tx = data["reservations"]
        effects, self.bank = T["run_order"](tx, data["initial"], seed, freq, caps, True)
        self.by_site = defaultdict(list)
        for row, effect in zip(tx, effects, strict=True):
            if row[0] <= 2:
                self.apply(row, effect)
            else:
                self.by_site[row[0] - 2, row[2]].append((row, effect))

    def resident(self, layer):
        second = self.pools[T["stage"](layer)].held
        return self.present[layer] | {expert for owner, expert in second if owner == layer}

    def apply(self, row, effect):
        _, _, layer, slot, gen, expert, old = row
        owner, src, dst = effect
        need(self.primary[layer, slot] == (old, gen - 1), "generation at demand")
        need(expert not in self.present[layer], "primary slot already resident")
        self.primary[layer, slot] = expert, gen
        self.present[layer].remove(old)
        self.present[layer].add(expert)
        need(
            self.pools[owner].reserve((layer, expert), (layer, old)) == (src, dst),
            "secondary transition differs from sealed pipeline",
        )


def measure_step(model, token, layers, memory, at):
    # Plan at call entry from a token confirmed before this graph starts.
    lexical = [
        choices(*model.token_scores(token, layer), memory.resident(layer), model.marginal[layer])
        for layer in range(36)
    ]
    pending, result = {}, []
    loads = 0
    for layer in range(36):
        if layer + 2 < 36:
            dest = layer + 2
            pending[dest] = choices(
                *model.upstream_scores(layers[layer], dest),
                memory.resident(dest),
                model.marginal[dest],
            )
        proposed, control, top, support = lexical[layer]
        ahead, other, loose, _ = pending.pop(layer, (set(),) * 4)
        predictions = (set(), proposed, control, top, support, ahead, other, loose)
        jobs = memory.by_site[at, layer]
        demand = {r[5] for r, _ in jobs}
        need(demand == set(layers[layer]) - memory.present[layer], "actual primary misses")
        cold = sorted(r[5] for r, effect in jobs if effect[1] is None)
        masks = []
        for name, selected in zip(MODES, predictions, strict=True):
            mask = sum(1 << i for i, e in enumerate(cold) if e in selected)
            issued = mask.bit_count() if name.endswith("_free") else len(selected)
            masks.append([issued, mask])
        result.append(masks)
        for row, effect in jobs:
            memory.apply(row, effect)
        loads += len(jobs)
    need(not pending, "missing downstream consumer")
    return result, loads


def observe(a, out):
    model_file = a.trained / "model.json.gz"
    train_receipt = verified(a.trained / "train.json", a.train_sha256)
    need(
        train_receipt["table"] == sha(model_file)
        and train_receipt["protocol"] == PROTOCOL
        and train_receipt["program"] == sha(Path(__file__)),
        "frozen training",
    )
    model = Frequencies.unpack(load(model_file))
    w = verified(a.work, WORK)
    physical = verified(a.serial, SERIAL)
    path = a.arm / "observer/events.pfj"
    need(sha(path) == JOURNAL, "full source journal")
    cut, end = PROFILE["metadata"](path, True)
    need(cut == train_receipt["records"], "independent prefix boundary")
    off = len(PROFILE["T1"])
    rows = [
        r._replace(call=r.call - off) if r.call else r
        for r in PROFILE["iter_rows"](path, cut, end - cut)
    ]
    host = PROFILE["NAT"]["host_trace"](rows)
    history = PROFILE["NAT"]["read"](PROFILE["NAT"]["HERE"] / "historical.json")
    need(host["route"] == history["route"], "reference target route and output mask")
    target = w["target"]
    need(
        len(target) == 47 and physical["role"] == "S" and len(physical["decode"]) == 46,
        "nominal serial trajectory",
    )
    tx_path = SERVICE["PATHS"]["transactions"]
    parent = verified(CONTROL, CONTROL_SHA)
    memory = Inventory(verified(tx_path, parent["inputs"]["transactions"]))
    need(
        memory.bank["hits"] == load(SERVICE["PATHS"]["bank"])["result"]["partition"]["hits"],
        "secondary counts",
    )
    start, prompt_end = w["cached"], len(w["t2"])
    need((start, prompt_end) == (2044, 2197), "T2 geometry")
    calls = []
    rank_count = 0
    token = target[0]
    for i, (pos, layers) in enumerate(positions(rows)):
        need(pos == start + i, "T2 position")
        if pos < prompt_end:
            model.observe(w["t2"][pos], layers)
            rank_count += len(layers)
            continue
        at = len(calls) + 1
        r = physical["decode"][at - 1]
        need(
            len(layers) == 36
            and len(r["routes"]) == 36
            and all(set(layers[layer]) == set(r["routes"][layer]) for layer in range(36)),
            "journal ranks and independently observed target unions",
        )
        need(r["at"] == at and r["keep"] == 1 and token == target[at - 1], "target-confirmed input")
        selected, loads = measure_step(model, token, layers, memory, at)
        need(loads == r["counts"][2], "independent load count")
        calls.append(selected)
        model.observe(token, layers)
        need(r["ids"] == [target[at]], "confirmed successor")
        token = r["ids"][0]
    need(len(calls) == 46 and rank_count == 153 * 35 + 1, "T2 coverage")
    save(
        out / "witness.json.gz",
        dict(
            calls=calls,
            modes=MODES,
            train=train_receipt,
            t2_prefill_ranks=rank_count,
            serial=SERIAL,
            work=WORK,
            journal=JOURNAL,
            service=CONTROL_SHA,
            protocol=PROTOCOL,
        ),
    )


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    split_p = sub.add_parser("split")
    split_p.add_argument("--work", required=True, type=Path)
    train_p = sub.add_parser("train")
    train_p.add_argument("--prefix", required=True, type=Path)
    obs_p = sub.add_parser("observe")
    for key in ("work", "serial", "trained"):
        obs_p.add_argument("--" + key, required=True, type=Path)
    obs_p.add_argument("--train-sha256", required=True)
    for sp in (train_p, obs_p):
        sp.add_argument("--arm", required=True, type=Path)
    for sp in (split_p, train_p, obs_p):
        sp.add_argument("--new-output-dir", required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    try:
        need(sha(HERE / "protocol.md") == PROTOCOL, "protocol drift")
        if a.action == "split":
            split(a.work, out)
        elif a.action == "train":
            train(a, out)
        else:
            observe(a, out)
    except Exception as exc:
        save(out / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    cli()

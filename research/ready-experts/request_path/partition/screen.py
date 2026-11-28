"""Score a sealed T1 partition on natural and supplied target routes."""

import argparse
import gzip
import hashlib
import json
import resource
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import policy as p  # noqa: E402
import sources as s  # noqa: E402


def totals(phases):
    return sum(phases.values())


def account(counts, end, entry, target):
    restore = len(set(target).difference(end))
    return dict(
        phases=counts,
        reads=totals(counts),
        entry_members=entry,
        terminal_members=len(end),
        terminal_sha256=p.digest(sorted(end)),
        restore=restore,
        charged=totals(counts) + restore,
        requested_B=totals(counts) * p.STRIDE,
        restore_B=restore * p.STRIDE,
    )


def train_plan(data):
    train, _, seed, supplied_entry, source = data
    natural = supplied_entry is None
    training, _ = p.curves(train, seed)
    learned, training_hits = p.allocate(training)
    training_demands = sum(len(w.keys) for w in train)
    if natural:
        warm, common, _ = p.local_run(train, seed, p.EQUAL, s.prefix_phase)
        shared_warm, global_entry, _ = p.global_run(train, seed, s.prefix_phase)
        p.prove_curve(training, p.EQUAL, training_demands, warm)
        prefix = dict(equal=warm, learned=warm, global_lru=shared_warm)
    else:
        # WRT did not observe a secondary directory or a known initial payload before its prefix.
        # Only the physical P members are available at score time, in all three causal arms.
        common = global_entry = supplied_entry
        prefix = None
    plan = dict(
        source_ranks=source["training_ranks"],
        training_waves=len(train),
        training_demands=training_demands,
        training_seed_sha256=p.digest(seed),
        training_hits=training_hits,
        quotas=learned,
        common_order_sha256=p.digest(common),
        global_order_sha256=p.digest(global_entry),
    )
    return plan, training, common, global_entry, prefix


def assess(data, sealed):
    _, test, _, supplied_entry, source = data
    phase = s.natural_phase if supplied_entry is None else s.supplied_phase
    plan, training, common, global_entry, prefix = train_plan(data)
    p.need(plan == sealed, "allocation or member order differs from pre-increment seal")
    learned = sealed["quotas"]
    demands = Counter()
    wave_count = Counter()
    for w in test:
        demands[phase(w.call)] += len(w.keys)
        wave_count[phase(w.call)] += 1
    total = sum(demands.values())
    control, terminal, entry = p.local_run(test, common, p.EQUAL, phase)
    arms = {"equal": account(control, terminal, entry, terminal)}
    holdout, end_stacks = p.curves(test, common)
    p.prove_curve(holdout, p.EQUAL, total, control)
    terminal_set = set(terminal)
    repair = []
    for layer, stack in enumerate(end_stacks):
        wanted = {k for k in terminal_set if k // p.EXPERTS == layer}
        repair.append(
            [len(wanted.difference(stack[-q:] if q else ())) for q in range(p.EXPERTS + 1)]
        )
    scored_repair = [
        [h - cost for h, cost in zip(row, penalty, strict=True)]
        for row, penalty in zip(holdout, repair, strict=True)
    ]
    oracle_quotas, maximum_hits = p.allocate(holdout)
    restore_quotas, maximum_net = p.allocate(scored_repair)
    for label, quotas in (
        ("learned", learned),
        ("future_quota", oracle_quotas),
        ("future_quota_restore", restore_quotas),
    ):
        counts, end, admitted = p.local_run(test, common, quotas, phase)
        p.prove_curve(holdout, quotas, total, counts)
        arms[label] = account(counts, end, admitted, terminal)
        p.need(
            arms[label]["restore"] == sum(repair[i][q] for i, q in enumerate(quotas)),
            "terminal repair from stack",
        )
    shared, shared_end, shared_n = p.global_run(test, global_entry, phase)
    arms["global_lru"] = account(shared, shared_end, shared_n, terminal)
    for label, target in (("future_pool", ()), ("future_pool_restore", terminal)):
        counts, end = p.ideal(test, common, p.CAPACITY, phase, target)
        final_charge = counts.pop("restore", 0)
        arms[label] = account(counts, end, len(common), terminal)
        if target:
            p.need(arms[label]["restore"] == final_charge, "ideal terminal identity debit")
    p.need(
        arms["future_quota"]["reads"] == total - maximum_hits
        and arms["future_quota_restore"]["charged"] == total - maximum_net,
        "quota optimization witness",
    )
    for label in ("equal", "learned", "future_quota", "future_quota_restore"):
        p.need(
            arms["future_pool"]["reads"] <= arms[label]["reads"]
            and arms["future_pool_restore"]["charged"] <= arms[label]["charged"],
            "oracle dominance",
        )
    result = dict(
        source=source,
        training=sealed,
        prefix_cpu_reads=prefix,
        demands=dict(demands),
        cpu_waves=dict(wave_count),
        empty_cpu_waves=sum(not w.keys for w in test),
        peak_wave=max(map(lambda w: len(w.keys), test)),
        arms=arms,
        best_static_quotas=oracle_quotas,
        best_charged_static_quotas=restore_quotas,
    )
    certificate = dict(train_hits=training, test_hits=holdout, restore=repair)
    return result, certificate


def decision(cases):
    natural = cases["natural_nominal"]
    control, learned = (natural["arms"][n] for n in ("equal", "learned"))

    def first(arm):
        return arm["reads"] - arm["phases"]["tail"]

    incumbent = natural["source"]["native_cpu_and_bank"]
    native_first = sum(incumbent[k] for k in ("prefill_5", "prefill_148", "decode_to_first"))
    gates = dict(
        natural_first_vs_equal=first(learned) < first(control),
        natural_charged_vs_equal=learned["charged"] < control["charged"],
        natural_first_vs_bank=first(learned) < native_first,
        natural_total_vs_bank=learned["reads"] < native_first + incumbent["tail"],
    )
    for key in ("nominal153", "code153"):
        arms = cases[key]["arms"]
        gates[key + "_charged_vs_equal"] = arms["learned"]["charged"] < arms["equal"]["charged"]
    code = cases["code153"]["arms"]
    gates["code_decode_protection"] = (
        code["learned"]["phases"]["decode_32"] <= code["equal"]["phases"]["decode_32"]
    )
    return gates, "GO_NUMERICAL_FIXTURE" if all(gates.values()) else "NO_GO_T1_QUOTAS"


def verify(receipt, certificate):
    p.need(
        receipt["method"] == s.METHOD == s.sha(HERE / "protocol.md")
        and receipt["schema"] == "tesy.cpu_partition.v1",
        "frozen method",
    )
    cases = receipt["cases"]
    p.need(set(cases) == set(certificate) == {"natural_nominal", "nominal153", "code153"}, "cases")
    plan_bytes = (
        json.dumps({k: v["training"] for k, v in cases.items()}, sort_keys=True, indent=2) + "\n"
    ).encode()
    p.need(
        hashlib.sha256(plan_bytes).hexdigest() == receipt["plan_sha256"], "sealed training receipt"
    )
    for name, case in cases.items():
        c = certificate[name]
        for matrix in c.values():
            p.need(
                len(matrix) == p.LAYERS and all(len(r) == 129 and min(r) >= 0 for r in matrix),
                "curve shape or sign",
            )
        total = totals(case["demands"])
        for key in ("train_hits", "test_hits"):
            p.need(all(row == sorted(row) for row in c[key]), "hit curve not monotone")
        p.need(
            all(row == sorted(row, reverse=True) for row in c["restore"]),
            "repair curve not monotone",
        )
        learned, hits = p.allocate(c["train_hits"])
        future, _ = p.allocate(c["test_hits"])
        net = [
            [a - b for a, b in zip(x, y, strict=True)]
            for x, y in zip(c["test_hits"], c["restore"], strict=True)
        ]
        future_net, _ = p.allocate(net)
        p.need(
            (learned, hits) == (case["training"]["quotas"], case["training"]["training_hits"])
            and (future, future_net)
            == (case["best_static_quotas"], case["best_charged_static_quotas"]),
            "changed quota choice",
        )
        for label, quotas in (
            ("equal", p.EQUAL),
            ("learned", learned),
            ("future_quota", future),
            ("future_quota_restore", future_net),
        ):
            arm = case["arms"][label]
            p.prove_curve(c["test_hits"], quotas, total, arm["phases"])
            p.need(
                arm["restore"] == sum(row[q] for row, q in zip(c["restore"], quotas, strict=True)),
                "changed restoration",
            )
        for arm in case["arms"].values():
            p.need(
                set(arm["phases"]) == set(case["demands"])
                and all(0 <= v <= case["demands"][k] for k, v in arm["phases"].items())
                and arm["reads"] == totals(arm["phases"])
                and arm["reads"] + arm["restore"] == arm["charged"]
                and arm["reads"] * p.STRIDE == arm["requested_B"]
                and arm["restore"] * p.STRIDE == arm["restore_B"]
                and 0 <= arm["entry_members"] <= p.CAPACITY
                and 0 <= arm["terminal_members"] <= p.CAPACITY,
                "volume or capacity",
            )
        p.need(
            case["peak_wave"] <= p.SCRATCH and case["arms"]["equal"]["restore"] == 0,
            "scratch or reference",
        )
    gates, status = decision(cases)
    p.need(receipt["gates"] == gates and receipt["status"] == status, "decision")
    return status


def write(path, value):
    tmp = path.with_suffix(path.suffix + ".partial")
    with tmp.open("xb") as f:
        f.write(value)
    tmp.rename(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--new", type=Path)
    action.add_argument("--seal", type=Path)
    action.add_argument("--check", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--plan-sha256")
    args = parser.parse_args()
    if args.check:
        receipt = json.loads((args.check / "decision.json").read_bytes())
        binary = (args.check / "curves.json.gz").read_bytes()
        p.need(hashlib.sha256(binary).hexdigest() == receipt["curves_sha256"], "curve digest")
        print(verify(receipt, json.loads(gzip.decompress(binary))))
        return
    if not args.archive:
        parser.error("--new and --seal require --archive")
    p.need(s.sha(HERE / "protocol.md") == s.METHOD, "protocol")
    if args.seal:
        args.seal.mkdir(parents=False, exist_ok=False)
        try:
            inputs = {
                "natural_nominal": s.natural(args.archive, True),
                **s.supplied(args.archive, True),
            }
            sealed = {k: train_plan(v)[0] for k, v in inputs.items()}
            write(
                args.seal / "plan.json",
                (json.dumps(sealed, sort_keys=True, indent=2) + "\n").encode(),
            )
            print(s.sha(args.seal / "plan.json"))
        except Exception as exc:
            write(
                args.seal / "FAIL.json",
                (json.dumps(dict(error=type(exc).__name__, reason=str(exc))) + "\n").encode(),
            )
            raise
        return
    if not args.plan or not args.plan_sha256:
        parser.error("--new requires a separate --plan and --plan-sha256")
    args.new.mkdir(parents=False, exist_ok=False)
    try:
        p.need(s.sha(args.plan) == args.plan_sha256, "pre-increment plan digest")
        sealed = json.loads(args.plan.read_bytes())
        inputs = {"natural_nominal": s.natural(args.archive), **s.supplied(args.archive)}
        results, cert = {}, {}
        for name, data in inputs.items():
            results[name], cert[name] = assess(data, sealed[name])
        binary = gzip.compress(
            json.dumps(cert, sort_keys=True, separators=(",", ":")).encode(), mtime=0
        )
        gates, status = decision(results)
        receipt = dict(
            schema="tesy.cpu_partition.v1",
            method=s.METHOD,
            evidence="TRACE_DERIVED",
            status=status,
            gates=gates,
            cases=results,
            plan_sha256=args.plan_sha256,
            curves_sha256=hashlib.sha256(binary).hexdigest(),
            source_sha256={n: s.sha(HERE / n) for n in ("policy.py", "sources.py", "screen.py")},
            model_forwards=0,
            weight_reads=0,
            client_seconds=None,
        )
        print(verify(receipt, cert))
        write(args.new / "curves.json.gz", binary)
        write(
            args.new / "decision.json",
            (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode(),
        )
    except Exception as exc:
        write(
            args.new / "FAIL.json",
            (json.dumps(dict(error=type(exc).__name__, reason=str(exc))) + "\n").encode(),
        )
        raise


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    resource.setrlimit(resource.RLIMIT_AS, (900 << 20, 900 << 20))
    main()

"""Replay RAM admission below an unchanged 288-slot GPU planner, starting before T1."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter, OrderedDict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
HYBRID = HERE.parents[2]
NAT = HYBRID / "cold_gate/backend_input/c110_graph/price/natural"
N = run_path(str(NAT / "score.py"))
need, sha = N["need"], N["sha"]
EXPERT = 3 * N["STRIDE"]
HOST = 10 << 30
SLOTS = HOST // EXPERT
KEYS = 36 * 128
MODES = ("LRU", "SECOND_MISS")
PRIOR = "a67f0a599ca989fd1176526fb13f4c536a57097fe3fd59bfaf449d7e453884f7"


class Bank:
    def __init__(self, slots, mode):
        need(0 < slots <= KEYS and mode in MODES, "RAM bank geometry or policy")
        self.slots = slots
        self.mode = mode
        self.resident = OrderedDict()
        self.waiting = OrderedDict()
        self.peak = [0, 0]

    def request(self, key, count):
        count["requests"] += 1
        if key in self.resident:
            self.resident.move_to_end(key)
            count["hits"] += 1
            return
        count["misses"] += 1
        if self.mode == "SECOND_MISS" and key not in self.waiting:
            if len(self.waiting) == self.slots:
                self.waiting.popitem(last=False)
            self.waiting[key] = None
            count["bypass"] += 1
        else:
            self.waiting.pop(key, None)
            if len(self.resident) == self.slots:
                self.resident.popitem(last=False)
                count["evictions"] += 1
            self.resident[key] = None
            count["admits"] += 1
        self.peak[0] = max(self.peak[0], len(self.resident))
        self.peak[1] = max(self.peak[1], len(self.waiting))

    def state(self):
        need(self.resident.keys().isdisjoint(self.waiting), "dual ownership")
        encoded = json.dumps([list(self.resident), list(self.waiting)], separators=(",", ":"))
        return [len(self.resident), len(self.waiting), hashlib.sha256(encoded.encode()).hexdigest()]


def decisions(a, previous):
    ranks, geom, _, sources = N["PAGES"]["reopen"](a.p97, a.p106)
    need(sources == previous["sources"], "route provenance")
    path = a.p106 / "ON/observer/events.pfj"
    cut, _ = N["FULL"]["metadata"](path, True)
    sites, initial = N["S"]["t1_sites"](N["FULL"]["iter_rows"](path, 0, cut), N["FULL"]["T1"])
    sites.extend((2, *k, [v % 128 for v in keys]) for k, keys in N["BASE"]["flatten"](ranks, geom))
    data = N["encode"](sites)
    need(
        len(sites) == 6880
        and sum(initial.values()) == 1440
        and hashlib.sha256(data).hexdigest() == previous["natural_input_sha256"]
        and sha(a.planner) == previous["build"]["elf"],
        "sites or native executable",
    )
    links = subprocess.check_output(
        ["/usr/bin/ldd", a.planner], text=True, env=N["BASE"]["IK"]["ENV"]
    )
    providers = [
        line.split("=>", 1)[1].split()[0]
        for line in links.splitlines()
        if line.strip().startswith("libggml.so => ")
    ]
    need(
        len(providers) == 1 and sha(Path(providers[0])) == previous["build"]["cpu_library"],
        "CPU closure",
    )
    proc = subprocess.run(
        [a.planner, "classlru", "288"],
        input=data,
        check=True,
        capture_output=True,
        timeout=35,
        env=N["BASE"]["IK"]["ENV"],
    )
    census = hashlib.sha256()
    work = []
    for (turn, call, tile, layer, ids), line in zip(sites, proc.stdout.splitlines(), strict=True):
        hits, fills, evicts, *pairs = map(int, line.split())
        experts, slots = pairs[::2], pairs[1::2]
        need(
            len(experts) == len(set(experts)) == len(slots) == len(set(slots)) == fills
            and hits + fills == len(set(ids))
            and set(experts) <= set(ids)
            and all(0 <= slot < 288 for slot in slots)
            and 0 <= layer < 36,
            "GPU fill identities",
        )
        census.update(f"{hits} {fills} {evicts}\n".encode())
        work.append((turn, call, tile, [128 * layer + e for e in experts]))
    need(census.hexdigest() == previous["native_census_sha256"], "native counts")
    return work


def replay(work, mode, previous):
    bank = Bank(SLOTS, mode)
    totals, tiles, cuts = {}, {}, {}
    per_call = {}
    for index, (turn, call, tile, keys) in enumerate(work):
        count = Counter()
        for key in keys:
            bank.request(key, count)
        tags = N["S"]["phases"](turn, call, tile)
        for name in tags:
            if name.startswith("T2_decode_call_"):
                per_call.setdefault(call, Counter()).update(count)
            elif name.startswith("T2_prefill_"):
                tiles.setdefault(name, Counter()).update(count)
            else:
                totals.setdefault(name, Counter()).update(count)
        next_cut = None if index + 1 == len(work) else work[index + 1][:3]
        if (turn, call, tile) != next_cut and (
            (turn == 1 and (not next_cut or next_cut[0] != 1))
            or (turn == 2 and (call <= 2 or call in (3, 46, 48)))
        ):
            cuts[f"T{turn}_call{call}_tile{tile}"] = bank.state()
    for name, counts in totals.items():
        need(
            counts["hits"] + counts["misses"] == counts["requests"]
            and counts["bypass"] + counts["admits"] == counts["misses"]
            and counts["requests"] * EXPERT == previous["natural"][name]["counts"]["payload_B"],
            "conservation in " + name,
        )
    need(
        len(bank.resident) == totals["session"]["admits"] - totals["session"]["evictions"],
        "final resident balance",
    )

    def detail(c):
        return dict(
            requests=c["requests"],
            hits=c["hits"],
            misses=c["misses"],
            bypass=c["bypass"],
            admissions=c["admits"],
            evictions=c["evictions"],
            source_B=c["misses"] * EXPERT,
            retained_writes_B=c["admits"] * EXPERT,
            h2d_payload_B=c["requests"] * EXPERT,
        )

    phases = {k: detail(v) for k, v in totals.items()}
    budgets = {}
    for label, num, den in (("T2_through_first_final", 10, 1), ("T2_decode", 47, 6)):
        c = phases[label]
        # Both services may overlap completely; launch, compute and copies into RAM are free here.
        disk_ns = (c["source_B"] * 10**9 + 4_500_000_000 - 1) // 4_500_000_000
        gpu_ns = (c["h2d_payload_B"] * 10**9 + 16_000_000_000 - 1) // 16_000_000_000
        meets = (
            c["source_B"] * den <= num * 4_500_000_000
            and c["h2d_payload_B"] * den <= num * 16_000_000_000
        )
        budgets[label] = dict(
            disk_ns_ceil=disk_ns,
            pcie_ns_ceil=gpu_ns,
            residual_ns=num * 10**9 // den - max(disk_ns, gpu_ns),
            fits=meets,
        )
    return dict(
        phases=phases,
        budgets=budgets,
        max_resident_waiting=bank.peak,
        cuts=cuts,
        prefill_tiles={k: detail(v) for k, v in tiles.items()},
        decode_calls=[
            [c, d["requests"], d["hits"], d["misses"], d["admits"], d["evictions"]]
            for c, d in per_call.items()
        ],
    )


def analyze(a):
    need(sha(NAT / "result.json") == PRIOR, "previous authority")
    prior = json.loads((NAT / "result.json").read_bytes())
    work = decisions(a, prior)
    arms = {m: replay(work, m, prior) for m in MODES}
    delta = {
        k: arms["LRU"]["phases"][k]["source_B"] - arms["SECOND_MISS"]["phases"][k]["source_B"]
        for k in arms["LRU"]["phases"]
    }
    return dict(
        evidence="TRACE_DERIVED",
        protocol_sha256=sha(HERE / "protocol.md"),
        previous_sha256=PRIOR,
        method_sha256=sha(Path(__file__)),
        native_census_sha256=prior["native_census_sha256"],
        offers_sha256=hashlib.sha256(json.dumps(work, separators=(",", ":")).encode()).hexdigest(),
        full_expert_B=EXPERT,
        host_budget_B=HOST,
        slots=SLOTS,
        host_payload_B=SLOTS * EXPERT,
        scratch_B=N["CAP"],
        model_starts=0,
        new_requests=0,
        arms=arms,
        source_saving_B=delta,
        selective_improves_protected_cases=delta["T2_through_first_final"] > 0
        and delta["T2_decode"] >= 0
        and delta["session"] >= 0,
        decisions={
            m: "HEADROOM_BYTES_ONLY"
            if all(x["fits"] for x in a["budgets"].values())
            else "NO_GO_FIXED_SERVICE"
            for m, a in arms.items()
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("p97", "p106", "planner", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        result = analyze(args)
    except Exception as exc:
        result = dict(decision="FAIL_PRESERVED", error=f"{type(exc).__name__}: {exc}")
    with (args.new_output_dir / "receipt.json").open("x") as file:
        json.dump(result, file, sort_keys=True, indent=2, allow_nan=False)
        file.write("\n")
    print(result.get("decisions", result.get("error")))
    raise SystemExit(result.get("decision") == "FAIL_PRESERVED")

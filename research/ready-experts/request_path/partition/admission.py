"""Pay for CPU expert delivery before deciding whether to retain its frame."""

import argparse
import gzip
import hashlib
import json
import resource
import sys
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import policy as p  # noqa: E402
import sources as s  # noqa: E402
from screen import account, write  # noqa: E402

METHOD = "ea39593f19056ea9cba257ea2702f017637e66a9a637c8cfd8f0e8325537e3ce"
PREVIOUS = "3994b9e73505a28423e9682699d72648a0c70609596ec5703358a237ad1551ff"
MODES = ("lru", "filter_lru", "filter_min")
UNIVERSE = p.LAYERS * p.EXPERTS


class Directory:
    def __init__(self, mode, seed=(), capacity=p.CAPACITY):
        p.need(mode in MODES and capacity > 0, "policy or capacity")
        self.mode, self.capacity = mode, capacity
        self.bank = dict.fromkeys(seed)
        self.count = [0] * UNIVERSE
        self.sample = 0

    def freeze(self):
        return dict(members=list(self.bank), counts=self.count.copy(), sample=self.sample)

    @classmethod
    def reopen(cls, mode, state):
        obj = cls(mode, state["members"])
        obj.count = state["counts"].copy()
        obj.sample = state["sample"]
        p.need(
            len(obj.bank) == len(state["members"]) <= obj.capacity
            and len(obj.count) == UNIVERSE
            and 0 <= min(obj.count) <= max(obj.count) < 65536
            and 0 <= obj.sample < 10 * obj.capacity,
            "sealed directory",
        )
        return obj

    def serve(self, wave):
        keys = wave.keys
        missing = tuple(k for k in keys if k not in self.bank)
        events = Counter(references=len(keys), reads=len(missing))
        for k in keys:
            self.sample += 1
            self.count[k] += 1
            if self.sample == 10 * self.capacity:
                self.count = [v // 2 for v in self.count]
                self.sample //= 2
                events["resets"] += 1
            if k in self.bank:
                del self.bank[k]
            elif len(self.bank) == self.capacity:
                if self.mode == "filter_min":
                    victim = min(self.bank, key=self.count.__getitem__)
                else:
                    victim = next(iter(self.bank))
                if self.mode != "lru" and self.count[k] <= self.count[victim]:
                    events["bypasses"] += 1
                    continue
                del self.bank[victim]
                events["substitutions"] += 1
            self.bank[k] = None
        return missing, events


def play(controller, waves, phase):
    counts, rows = {}, []
    for w in waves:
        missing, events = controller.serve(w)
        label = phase(w.call)
        counts.setdefault(label, Counter()).update(events)
        rows.append([w.call, w.tile, w.layer, w.index, list(missing)])
    p.need(len(controller.bank) <= p.CAPACITY, "resident capacity")
    return counts, rows


def train(inputs):
    states = {}
    for name, (warm, _, seed, published, info) in inputs.items():
        states[name] = {}
        for mode in MODES:
            obj = Directory(mode, seed)
            pre, _ = play(obj, warm, s.prefix_phase)
            if published is not None:
                obj.bank = dict.fromkeys(published)
            states[name][mode] = dict(
                state=obj.freeze(),
                source=info["training_ranks"],
                observed_prefix=pre if published is None else None,
            )
    return states


def state_digest(value):
    return p.digest([value["members"], value["counts"], value["sample"]])


def nat_control():
    path = s.ENTRY / "evidence-entry-20261128-r01/transactions.json.gz"
    p.need(
        s.sha(path) == "a6208d27a2b44a7aef1c56185e320b2af647a5dd0dc5478d46282a8aa45ff730",
        "T1 bank stream",
    )
    plan = s.E["F"]["unpack"](path)
    second, _ = s.E["V"]["sources"]()
    p.need(s.E["digest"](second) == plan["suffix_sha256"], "T2 bank stream")
    pool, freq, demand = {}, Counter(), Counter()
    slots = {(layer_id, slot): (e, g) for layer_id, slot, e, g in plan["initial"]}
    for i, (call, _, layer_id, slot, g, e, old) in enumerate(plan["prefix"] + second):
        if layer_id >= p.LAYERS:
            continue
        p.need(slots[layer_id, slot] == (old, g - 1), "native generation")
        slots[layer_id, slot] = (e, g)
        hit, _ = s.E["reserve"](pool, freq, i, layer_id, e, old)
        phase = s.prefix_phase(call) if i < len(plan["prefix"]) else s.natural_phase(call)
        demand[phase] += int(not hit)
    p.need(
        sorted([layer_id, slot, e, g] for (layer_id, slot), (e, g) in slots.items())
        == plan["terminal"],
        "native terminal owner",
    )
    primary = {layer_id * p.EXPERTS + e for (layer_id, _), (e, _) in slots.items() if e >= 0}
    secondary = {layer_id * p.EXPERTS + e for layer_id, e in pool}
    p.need(
        not primary & secondary and (len(primary), len(secondary)) == (1000, 252),
        "native exclusive frames",
    )
    return dict(demand), primary | secondary


def supplied_control(raw, case, expected, published):
    historical = run_path(s.QUAL / "warm_residency/replay.py")
    common, hashes = None, {}
    for rep in (2, 3):
        name = f"c294-{case}-{rep}-on"
        stream, auth = historical["primary"](raw, name)
        root = raw / (name + ".native")
        result = json.loads(historical["checked"](root / "result.json", auth["result.json"]))
        physical = historical["boundary"].slots(result["initial"])
        p.need(
            p.digest([(layer_id, *v) for layer_id, layer in enumerate(physical) for v in layer])
            == expected["snapshot"],
            "C294 and WRT P differ",
        )
        prim = set(published)
        pool, freq, demand = {}, Counter(), Counter()
        for i, (phase, tier, key, old) in enumerate(stream):
            if tier != "CPU":
                continue
            layer, expert = divmod(key, p.EXPERTS)
            p.need(layer < p.LAYERS and key not in prim, "C294 CPU placement")
            if old is not None:
                prim.remove(old)
            prim.add(key)
            victim = -1 if old is None else old % p.EXPERTS
            hit, _ = s.E["reserve"](pool, freq, i, layer, expert, victim)
            demand["prefill_153" if phase == "prefill" else "decode_32"] += int(not hit)
        final = historical["boundary"].slots(result["final"])
        p.need(
            prim
            == {
                layer_id * p.EXPERTS + e
                for layer_id, entries in enumerate(final[: p.LAYERS])
                for e, _, state, _ in entries
                if state == 2
            },
            "C294 terminal",
        )
        secondary = {layer_id * p.EXPERTS + e for layer_id, e in pool}
        p.need(not prim & secondary and len(prim | secondary) <= 1252, "C294 exclusive frames")
        current = dict(demand), prim | secondary
        p.need(common is None or common == current, "C294 repeats differ")
        common = current
        hashes[name] = auth
    return *common, hashes


def calculate(inputs, states, raw, baseline):
    natural_control, natural_end = nat_control()
    results, certificates = {}, {}
    for name, (_, test, _, published, info) in inputs.items():
        natural = published is None
        if natural:
            before = {k: v for k, v in natural_control.items() if k.startswith("T1_")}
            control = {k: v for k, v in natural_control.items() if k not in before}
            p.need(natural_control == info["native_cpu_and_bank"], "bank control phases")
            end, refs = natural_end, info["source"]
        else:
            control, end, refs = supplied_control(raw, name, info, published)
            before = {}
        reference = baseline["cases"][name]["arms"]["global_lru"]
        phase = s.natural_phase if natural else s.supplied_phase
        results[name] = dict(
            incumbent=control,
            incumbent_prefix=before,
            terminal_members=len(end),
            incumbent_end_sha256=p.digest(sorted(end)),
            inputs=refs,
            arms={},
        )
        certificates[name] = dict(terminal=sorted(end), arms={})
        for mode in MODES:
            sealed = states[name][mode]
            obj = Directory.reopen(mode, sealed["state"])
            initial = len(obj.bank)
            counts, rows = play(obj, test, phase)
            cost = {label: stats["reads"] for label, stats in counts.items()}
            if mode == "lru":
                ablation_end = set(obj.bank)
                p.need(
                    reference["phases"] == cost
                    and reference["terminal_sha256"] == p.digest(sorted(ablation_end)),
                    "frozen LRU ablation",
                )
            account_end = account(cost, list(obj.bank), initial, end)
            prefix_cost = {k: v["reads"] for k, v in (sealed["observed_prefix"] or {}).items()}
            results[name]["arms"][mode] = dict(
                **account_end,
                restore_global_lru=len(ablation_end.difference(obj.bank)),
                observed_prefix=prefix_cost,
                events=counts,
                misses_sha256=p.digest(rows),
                order_sha256=p.digest(list(obj.bank)),
                state_at_cut_sha256=state_digest(sealed["state"]),
            )
            certificates[name]["arms"][mode] = dict(end=sorted(obj.bank), misses=rows)
    return results, certificates


def gates(results):
    flags = {}
    for mode in MODES[1:]:
        role = {}
        natural = results["natural_nominal"]
        a, c = natural["arms"][mode], natural["incumbent"]
        prefix, ac = sum(natural["incumbent_prefix"].values()), sum(a["observed_prefix"].values())
        role["natural_first"] = a["reads"] - a["phases"]["tail"] < sum(c.values()) - c["tail"]
        role["natural_total"] = a["reads"] < sum(c.values())
        role["natural_decode"] = (
            a["phases"]["decode_to_first"] + a["phases"]["tail"] < c["decode_to_first"] + c["tail"]
        )
        role["two_turns"] = ac + a["reads"] < prefix + sum(c.values())
        for k in ("nominal153", "code153"):
            case = results[k]
            role[k + "_charged"] = case["arms"][mode]["charged"] < sum(case["incumbent"].values())
        code = results["code153"]
        role["code_decode"] = (
            code["arms"][mode]["phases"]["decode_32"] <= code["incumbent"]["decode_32"]
        )
        flags[mode] = role
    return flags, "GO_NUMERICAL_FIXTURE" if any(
        all(v.values()) for v in flags.values()
    ) else "NO_GO_CAUSAL_ADMISSION"


def verify(receipt, cert, states):
    p.need(receipt["method"] == s.sha(HERE / "admission-protocol.md") == METHOD, "method")
    cases = receipt["cases"]
    p.need(
        set(cases) == set(cert) == set(states) == {"natural_nominal", "nominal153", "code153"},
        "cases",
    )
    for name, case in cases.items():
        info = cert[name]
        target = set(info["terminal"])
        p.need(
            len(target) == case["terminal_members"]
            and p.digest(sorted(target)) == case["incumbent_end_sha256"],
            "native end",
        )
        for mode in MODES:
            arm, evidence = case["arms"][mode], info["arms"][mode]
            rows = evidence["misses"]
            phase = s.natural_phase if name == "natural_nominal" else s.supplied_phase
            counted = Counter()
            for call, _, layer_id, _, keys in rows:
                p.need(
                    len(keys) <= p.SCRATCH
                    and len(set(keys)) == len(keys)
                    and all(k // p.EXPERTS == layer_id and 0 <= layer_id < p.LAYERS for k in keys),
                    "invalid miss list",
                )
                counted[phase(call)] += len(keys)
            end = set(evidence["end"])
            p.need(
                arm["misses_sha256"] == p.digest(rows)
                and arm["phases"] == dict(counted)
                and arm["reads"] == sum(counted.values())
                and arm["requested_B"] == arm["reads"] * p.STRIDE
                and arm["events"].keys() == arm["phases"].keys()
                and all(arm["events"][k]["reads"] == v for k, v in counted.items())
                and arm["restore"] == len(target - end)
                and arm["charged"] == arm["reads"] + arm["restore"]
                and arm["restore_B"] == arm["restore"] * p.STRIDE
                and len(end) == arm["terminal_members"] <= p.CAPACITY
                and arm["terminal_sha256"] == p.digest(sorted(end))
                and arm["restore_global_lru"] == len(set(info["arms"]["lru"]["end"]) - end)
                and arm["state_at_cut_sha256"] == state_digest(states[name][mode]["state"]),
                "arm conservation",
            )
    flags, status = gates(cases)
    p.need(receipt["gates"] == flags and receipt["status"] == status, "exit decision")
    return status


def pack(value):
    return gzip.compress(json.dumps(value, separators=(",", ":"), sort_keys=True).encode(), mtime=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("seal", "new", "check"):
        modes.add_argument("--" + name, type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--c294-raw", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--plan-sha256")
    a = parser.parse_args()
    p.need(s.sha(HERE / "admission-protocol.md") == METHOD, "protocol")
    if a.check:
        if not a.plan:
            parser.error("--check requires the enrolled --plan")
        r = json.loads((a.check / "decision.json").read_bytes())
        b = (a.check / "certificate.json.gz").read_bytes()
        p.need(
            hashlib.sha256(b).hexdigest() == r["certificate_sha256"]
            and s.sha(a.plan) == r["plan_sha256"],
            "certificate or plan",
        )
        print(
            verify(
                r, json.loads(gzip.decompress(b)), json.loads(gzip.decompress(a.plan.read_bytes()))
            )
        )
        return
    if not a.archive or (a.new and not (a.c294_raw and a.plan and a.plan_sha256)):
        parser.error("supply --archive, and for --new also --c294-raw, --plan and --plan-sha256")
    out = a.seal or a.new
    out.mkdir(exist_ok=False)
    try:
        prefix_only = bool(a.seal)
        inputs = {
            "natural_nominal": s.natural(a.archive, prefix_only),
            **s.supplied(a.archive, prefix_only),
        }
        states = train(inputs)
        encoded = pack(states)
        digest = hashlib.sha256(encoded).hexdigest()
        if prefix_only:
            write(out / "states.json.gz", encoded)
            print(digest)
            return
        p.need(
            digest == a.plan_sha256 == s.sha(a.plan) and encoded == a.plan.read_bytes(),
            "independent prefix seal",
        )
        base = s.SRC["pinned"](HERE / "evidence-20261128-r01/decision.json", PREVIOUS)
        results, cert = calculate(inputs, states, a.c294_raw, base)
        flags, status = gates(results)
        binary = pack(cert)
        receipt = dict(
            schema="tesy.cpu_frame_admission.v1",
            evidence="TRACE_DERIVED",
            method=METHOD,
            source_sha256=s.sha(Path(__file__)),
            plan_sha256=digest,
            cases=results,
            gates=flags,
            status=status,
            certificate_sha256=hashlib.sha256(binary).hexdigest(),
            model_forwards=0,
            measured_client_ns=None,
        )
        print(verify(receipt, cert, states))
        write(out / "certificate.json.gz", binary)
        write(
            out / "decision.json", (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
        )
    except Exception as exc:
        write(
            out / "FAIL.json",
            (json.dumps(dict(error=type(exc).__name__, reason=str(exc))) + "\n").encode(),
        )
        raise


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    resource.setrlimit(resource.RLIMIT_AS, (900 << 20, 900 << 20))
    main()

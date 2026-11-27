"""Optimistic wall-time bounds for an exact ready-expert executor on two packed T2s."""

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parent / "qualification-retake"
NATURAL = QUAL / "igpu_resident_rank/request_budget/device/pack_native/natural_trace"
SOURCE = run_path(str(NATURAL / "prefill_retention/request_cost/score.py"))
METHOD = "dbde654dcc1d84c3d800027eac0f41009c5fa0b099eadb80f630249f29cb9274"
PRIOR = "340b3dfa3d0e3979c83875f309873c8f42b554fb6c7b11f27a6de275a978ef19"
NS = 10**9
PPM = 10**6
FIRST_LIMIT = 10 * NS
DECODE_LIMIT = 47 * NS // 6


def require(ok, message):
    if not ok:
        raise ValueError(message)


def layer_fourths(prices):
    """Lower bound in quarter-nanoseconds for indivisible jobs on four workers."""
    return max(4 * max(prices, default=0), sum(prices))


@dataclass(frozen=True)
class Call:
    number: int
    span: int
    remap: int
    service_fourths: int
    reserved: int
    charged: int

    def measures(self, ppm):
        outside = self.span - self.remap
        service = (self.service_fourths * ppm + 4 * PPM - 1) // (4 * PPM)
        return {
            "control": self.span,
            "fixed_callbacks": max(outside, self.remap),
            "ready": max(outside, service),
            "outside": outside,
            "remap": self.remap,
            "charged_service_floor": service,
        }


def partition(calls, waves):
    by_call = defaultdict(list)
    for w in waves:
        by_call[w.site[0]].append(w)
    require(set(by_call) == {c["number"] for c in calls}, "missing or extra call")
    result = []
    for call in calls:
        number = call["number"]
        begin, end = call["enter_ns"], call["return_ns"]
        cursor = begin
        service = defaultdict(list)
        inside = reserved = charged = 0
        seen = set()
        for w in by_call[number]:
            require(cursor <= w.start <= w.end <= end, "overlapping remap or return")
            cursor = w.end
            inside += w.end - w.start
            reserved += len(w.reserved)
            for k, price in w.required_service.items():
                require(k not in seen and price >= 0, "duplicate generation or negative service")
                seen.add(k)
                service[w.site[1:3]].append(price)
                charged += 1
        floor = sum(layer_fourths(v) for v in service.values())
        require(floor <= 4 * inside and charged <= reserved, "charges exceed observed service")
        result.append(Call(number, end - begin, inside, floor, reserved, charged))
    return result


def phase(number):
    if number <= 2:
        return "prefill"
    return "decode_before_final" if number <= 46 else "decode_tail"


def margins(first, decode):
    return {"first_final": FIRST_LIMIT - first, "decode": DECODE_LIMIT - decode}


def joint(clock):
    return min(margins(clock["first_final"], clock["decode"]).values())


def clocks(calls, first, decode, ppm=PPM):
    phases = defaultdict(Counter)
    for c in calls:
        s = phases[phase(c.number)]
        s.update(c.measures(ppm))
        s.update(calls=1, reserved=c.reserved, charged=c.charged)
    p, b, z = (phases[k] for k in ("prefill", "decode_before_final", "decode_tail"))
    external = {
        "first_final": first - p["control"] - b["control"],
        "decode": decode - b["control"] - z["control"],
    }
    require(min(external.values()) >= 0, "native calls exceed client or server clock")
    result = {}
    for mode in ("control", "fixed_callbacks", "ready"):
        f = external["first_final"] + p[mode] + b[mode]
        v = external["decode"] + b[mode] + z[mode]
        result[mode] = {"first_final": f, "decode": v, "margin_ns": margins(f, v)}
    require(
        (result["control"]["first_final"], result["control"]["decode"]) == (first, decode),
        "control clock reconstruction",
    )
    return result, dict(phases), external


def read_arm(archive, label, prior):
    name, family_sha, manifest_sha = SOURCE["SOURCES"][label]
    part = archive / ("part-" + label[1:])
    root = part / name
    pinned = SOURCE["pinned"]
    manifest = pinned(part / "manifest.json", manifest_sha)
    journal = "observer/events.pfj" if label == "P106" else "raw/events.pfj"
    SOURCE["authenticate_raw"](
        root, manifest, [journal, "raw/T2-result.json", "raw/T2-request.jsonl", "receipt.json"]
    )
    family = pinned(root / "family.json", family_sha)
    meta = pinned(root / "ON/arm.json", family["arms"]["ON"]["sha256"])
    receipt = pinned(root / "ON/receipt.json", meta["receipt_sha256"])
    if label == "P106":
        _, rows, _, _ = SOURCE["Q"]["read_new"](root, family_sha)
    else:
        rows, _ = SOURCE["T"]["PFJ"]["read_journal"](root / "ON" / journal)
    host = SOURCE["NATIVE"]["host_trace"](rows)
    waves, jobs = SOURCE["timeline"](rows)
    spans = [(w.site[0], w.start, w.end) for w in waves]
    require(
        spans == host["callback_spans"] and host["route"] == prior["route"],
        "route or serialized remap spans",
    )
    cut = SOURCE["CLIENT"]["inspect"](root / "ON", receipt, host["calls"])
    require((cut["sample_number"], cut["sample_call"]) == (45, 46), "client cut")
    raw = json.loads((root / "ON/raw/T2-result.json").read_bytes())
    pub = receipt["rows"][1]
    require(
        (pub["functional"], pub["cache_n"], pub["prompt_n"], pub["predicted_n"])
        == ("PASS", 2044, 153, 47),
        "workload",
    )
    first = int(Decimal(str(raw["stream_metrics"]["first_final_content_chunk_s"])) * NS)
    decode = int(Decimal(str(raw["timings"]["predicted_ms"])) * 10**6)
    require(
        (first, decode, len(jobs), len(waves))
        == (prior["first_final_ns"], prior["decode_ns"], prior["jobs"], prior["callbacks"]),
        "previous clock and conservation receipt",
    )
    calls = partition(host["calls"], waves)
    require(
        [c.number for c in calls] == list(range(1, 49))
        and sum(c.reserved for c in calls) == len(jobs),
        "48 calls and unique reservations",
    )
    bounds, phases, outside = clocks(calls, first, decode)
    require([p["calls"] for p in phases.values()] == [2, 44, 2], "phase boundaries")
    client_cut = host["calls"][45]["return_ns"] + cut["last_relevant_return_to_first_final_ns"]
    tail_callback = sum(max(0, min(stop, client_cut) - start) for n, start, stop in spans if n > 46)
    require(tail_callback == 0, "tail callback before first final")
    report = {
        "route": host["route"],
        "manifest_sha256": manifest_sha,
        "family_sha256": family_sha,
        "journal_sha256": manifest["files"][f"{name}/ON/{journal}"]["sha256"],
        "trajectory_sha256": receipt["trajectories"][1]["sampled_ids_sha256"],
        "callbacks": len(waves),
        "jobs": len(jobs),
        "phases": phases,
        "clock_ns": bounds,
        "outside_calls_ns": outside,
        "tail_callback_before_client_ns": tail_callback,
        "free_jobs": len(jobs) - sum(c.charged for c in calls),
    }
    return (calls, first, decode), report


def frontier(price_fits):
    if not price_fits(0):
        return {"status": "FAIL_EVEN_WITH_FREE_SERVICE", "max_ppm": None}
    if price_fits(PPM):
        return {"status": "OBSERVED_PRICE_HAS_HEADROOM", "max_ppm_tested": PPM}
    lo, hi = 0, PPM
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if price_fits(mid):
            lo = mid
        else:
            hi = mid
    return {"status": "CONDITIONAL_MAXIMUM", "max_ppm": lo, "first_excluded_ppm": hi}


def consensus(passes):
    if all(passes):
        return "GO_NEXT_FIXTURE_ONLY"
    return "INCONCLUSIVE_BETWEEN_RUNS" if any(passes) else "NO_GO_FIXED_PRICES"


def study(archive):
    require(SOURCE["digest"](HERE / "protocol.md") == METHOD, "protocol hash")
    prior = SOURCE["pinned"](NATURAL / "prefill_retention/request_cost/receipt.json", PRIOR)
    arms, models = {}, {}
    for label in ("P97", "P106"):
        models[label], arms[label] = read_arm(archive, label, prior[label])
    a, b = arms.values()
    require(
        a["route"] == b["route"] and a["trajectory_sha256"] == b["trajectory_sha256"],
        "different target trajectories",
    )
    for label, args in models.items():
        arm = arms[label]
        arm["service_free_ns"] = clocks(*args, 0)[0]["ready"]
        arm["service_price_frontier"] = frontier(
            lambda p, args=args: joint(clocks(*args, p)[0]["ready"]) >= 0
        )
    shared = frontier(
        lambda p: all(joint(clocks(*args, p)[0]["ready"]) >= 0 for args in models.values())
    )
    return {
        "schema": "tesy.expert_ready_bounds.v1",
        "status": "TRACE_DERIVED",
        "protocol_sha256": METHOD,
        "source_sha256": SOURCE["digest"](Path(__file__)),
        "clock_unit": "ns",
        "service_price_unit": "ppm_of_same_arm_read_plus_set_time",
        "decisions": {
            m: consensus([joint(a["clock_ns"][m]) >= 0 for a in arms.values()])
            for m in ("fixed_callbacks", "ready")
        },
        "joint_service_price_frontier": shared,
        "arms": arms,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--archive", type=Path, required=True)
    cli.add_argument("--new-output-dir", type=Path, required=True)
    args = cli.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        result = study(args.archive)
    except FileNotFoundError as exc:
        missing = Path(exc.filename).resolve() if exc.filename else None
        is_raw = missing and missing.is_relative_to(args.archive.resolve())
        result = {
            "status": "NOT_RUN_RAW_REQUIRED" if is_raw else "FAIL",
            "missing_file": missing.name if missing else None,
        }
    except (AssertionError, KeyError, OSError, TypeError, ValueError) as exc:
        result = {"status": "FAIL", "reason": str(exc)}
    tmp = args.new_output_dir / ".receipt.tmp"
    with tmp.open("x") as out:
        json.dump(result, out, sort_keys=True, indent=2, allow_nan=False)
        out.write("\n")
    tmp.rename(args.new_output_dir / "receipt.json")
    print(result["status"], result.get("decisions", result.get("reason", "")))
    return 0 if result["status"] == "TRACE_DERIVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

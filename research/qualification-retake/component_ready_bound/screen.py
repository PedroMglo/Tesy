"""Conditional decode floor for fixed serial component service and immediate readiness."""

import argparse
import hashlib
import io
import json
import resource
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cache_boundary as c294  # noqa: E402
from warm_route_reference.verify import PROMPT, check_witness  # noqa: E402

require = c294.require
PROTOCOL = "a7468d074a5d0fa809123cbcc00ac0945f81b7ddc45161edbd95c1280bb518ba"
C294_PROTOCOL = "ac8c25f5a38313e75d4fbb25ba15908be16a350e733582e46ef11eb17b6b2c6e"
COMPONENT = 4_406_400
CHAIN = [(-1, 4), (-1, 5)] + [(c, k) for c in range(3) for k in range(6, 10)] + [(-1, 10)]


class Inconclusive(ValueError):
    pass


def causal(ok, why):
    if not ok:
        raise Inconclusive(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def certificate(ranks, jobs, left, right):
    """One route. All rank services may overlap; each job owns a serial component chain."""
    causal(left <= right, "reversed route interval")
    require(len(ranks) == len({e for e, *_ in ranks}) == 4, "rank set")
    pending = jobs.copy()
    longest = misses = 0
    for expert, state, slot, gen in ranks:
        job = pending.pop(expert, None)
        if state == 2:
            causal(job is None, "resident produced service")
            continue
        causal(state == 0 and slot == -1 and gen == 0 and job is not None, "unowned or late read")
        phases = job[1]
        require(list(phases) == CHAIN, "incomplete or reordered generation")
        stamps = list(phases.values())
        causal(left <= stamps[0] and stamps[-1] <= right, "generation crosses route")
        causal(stamps == sorted(stamps), "generation overlaps its own service")
        service = sum(max(0, phases[c, 7] - phases[c, 6] - 1) for c in range(3))
        longest = max(longest, service)
        misses += 1
    causal(not pending, "orphan generation")
    return longest, misses


def threshold(floor, n, d):
    margin = 3 * n * floor - 16_000_000 * d
    return dict(
        floor_s=floor * n / (d * 1_000_000),
        excess_s=margin / (3_000_000 * d),
        exceeds_six_step_budget=margin > 0,
    )


def summarize(lines, case):
    require(next(lines).strip() == c294.HEADER, "schema")
    markers, ranks, jobs = {}, defaultdict(list), defaultdict(dict)
    for line in lines:
        kind, stamp, call, route, layer, expert, slot, gen, comp, size, rows = map(
            int, line.split()
        )
        if call == 0:
            continue
        require(1 <= call <= 32, "unknown call")
        group = call, layer
        if kind in (2, 15, 16):
            key = call, layer, kind
            require(key not in markers, "duplicate marker")
            markers[key] = stamp, route
            if kind == 2:
                require(rows == 1 and route > 0, "foreign router geometry")
        elif 3 <= kind <= 10:
            causal(markers.get((call, layer, 2), (None, None))[1] == route, "foreign route")
            if kind == 3:
                ranks[group].append((expert, size, slot, gen))
                continue
            generation, phases = jobs[group].setdefault(expert, ((slot, gen), {}))
            causal(generation == (slot, gen), "changed destination")
            phase = comp, kind
            if 6 <= kind <= 9:
                require(size == COMPONENT, "unexpected component payload")
            if phase in phases:
                require(kind == 4, "duplicate phase")
            else:
                phases[phase] = stamp
    totals = {tier: Counter() for tier in ("CPU", "CUDA")}
    witness = []
    end = 0
    for call in range(1, 33):
        start = markers[call, -1, 15][0]
        causal(end <= start, "overlapping calls")
        end = markers[call, -1, 16][0]
        routers = [markers[call, il, 2][0] for il in range(36)]
        causal(start <= routers[0] <= end, "call boundary")
        for il, (left, right) in enumerate(zip(routers, [*routers[1:], end], strict=True)):
            row = ranks.pop((call, il))
            witness.append((call, il, PROMPT[case] + call - 1, [e for e, *_ in row]))
            value, misses = certificate(row, jobs.pop((call, il), {}), left, right)
            totals["CPU" if il < 25 else "CUDA"].update(
                groups=1,
                hits=4 - misses,
                misses=misses,
                read_pairs=3 * misses,
                logical_read_bytes=3 * COMPONENT * misses,
                read_floor_us=value,
                all_resident_groups=int(misses == 0),
            )
    causal(not ranks and not jobs, "extra groups")
    ordered = check_witness(case, witness)
    total = sum(t["read_floor_us"] for t in totals.values())
    return dict(
        ordered_rank_sha256=ordered,
        tiers=totals,
        read_floor_us=total,
        scales={"1": threshold(total, 1, 1), "0.8": threshold(total, 4, 5)},
    )


def git(*args):
    return subprocess.check_output(
        ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1", *args],
        cwd=HERE,
        text=True,
    ).strip()


def arm(raw, entries, name):
    blobs, hashes = {}, {}
    for fn in ("events.tsv", "initial.json", "result.json"):
        rel = f"{name}.native/{fn}"
        item = entries[rel]
        data = (raw / rel).read_bytes()
        require(len(data) == item["bytes"] and sha(data) == item["sha256"], "raw identity")
        blobs[fn], hashes[fn] = data, item["sha256"]
    case = name.split("-")[1]
    native = json.loads(blobs["result.json"])
    require(native["case"] == case and native["trace"] and native["profile"] == "R0", "arm")
    lines = io.StringIO(blobs.pop("events.tsv").decode())
    _, boundary = c294.replay(json.loads(blobs["initial.json"]), native, lines)
    lines.seek(0)
    result = summarize(lines, case)
    counts = boundary["counts"]
    require(
        sum(t["misses"] for t in result["tiers"].values())
        == counts["decode_miss"]
        == counts["decode_publications"],
        "miss conservation",
    )
    return dict(
        **result,
        raw_sha256=hashes,
        entry_slot_sha256=boundary["boundary_slot_vector_sha256"],
        native_decode32_s=native["decode32_s"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = {"status": "FAIL_PRESERVED", "arms": {}}
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (240, 240))
        resource.setrlimit(resource.RLIMIT_FSIZE, (256 << 20, 256 << 20))
        require(not git("status", "--porcelain"), "dirty checkout")
        receipt.update(
            commit=git("rev-parse", "HEAD"),
            tree=git("rev-parse", "HEAD^{tree}"),
            program_sha256=sha(Path(__file__).read_bytes()),
            protocol_sha256=PROTOCOL,
            c294_protocol_sha256=C294_PROTOCOL,
            manifest_sha256=c294.MANIFEST_SHA,
        )
        require(sha((HERE / "protocol.md").read_bytes()) == PROTOCOL, "protocol")
        manifest = c294.MANIFEST.read_bytes()
        require(sha(manifest) == c294.MANIFEST_SHA, "manifest")
        require(
            sha(c294.MANIFEST.with_name("protocol.json").read_bytes()) == C294_PROTOCOL,
            "C294 protocol",
        )
        entries = {x["path"].split("/raw/")[1]: x for x in json.loads(manifest)["files"]}
        for name in c294.NAMES:
            receipt["arms"][name] = arm(args.raw_dir, entries, name)
        excluded = all(
            s["exceeds_six_step_budget"]
            for a in receipt["arms"].values()
            for s in a["scales"].values()
        )
        receipt["status"] = "NO_GO_COMPONENT_READY_FIXED_READ" if excluded else "INCONCLUSIVE"
    except FileNotFoundError as exc:
        receipt.update(status="NOT_RUN_RAW_REQUIRED", error=Path(exc.filename).name)
    except Inconclusive as exc:
        receipt.update(status="INCONCLUSIVE", error=str(exc))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        receipt["error"] = str(exc)
    (args.new_output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return int("error" in receipt)


if __name__ == "__main__":
    raise SystemExit(main())

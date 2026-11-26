"""Indivisible READ per component, four continuously available workers per route."""

import argparse
import hashlib
import json
import os
import resource
import signal
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path.insert(0, str(UNIT))
PROTOCOL = "22a4e4f47cd2f88dfa6834cdd015df5635c343edbd6ba1f469cc64d5acd0f6b4"
COMPONENT = 4_406_400
PINS = {
    "component_ready_bound/evidence/receipt.json": (
        "3473a9506fbb4d4e2e5051b243e9cbce04c76ecb96707a5c0fd3e1628d11eebe"
    ),
    "primary_backing/evidence/receipt.json": (
        "44ba456b19a1d4fcd44ecb7127a99db410344e304a4e51474d41dec1847fc9f5"
    ),
}


def require(test, reason):
    if not test:
        raise ValueError(reason)


def solve(tasks):
    """Return optimal makespan and four lists of task indices, including zero-duration tasks."""
    require(
        len(tasks) <= 12 and all(type(v) is int and v >= 0 for v in tasks), "invalid READ tasks"
    )
    jobs = sorted(range(len(tasks)), key=lambda i: (-tasks[i], i))
    loads = [0] * 4
    witness = [[] for _ in loads]
    for i in jobs:
        lane = min(range(4), key=loads.__getitem__)
        witness[lane].append(i)
        loads[lane] += tasks[i]
    best = max(loads)
    lower = max(max(tasks, default=0), (sum(tasks) + 3) // 4)
    if best > lower:
        path = [[] for _ in range(4)]
        loads = [0] * 4

        def search(step):
            nonlocal best, witness
            if step == len(jobs):
                if max(loads) < best:
                    best = max(loads)
                    witness = [lane.copy() for lane in path]
                return
            task = jobs[step]
            tried = set()
            for lane in sorted(range(4), key=loads.__getitem__):
                old = loads[lane]
                # Equal loads are interchangeable for all remaining jobs.
                if old in tried or old + tasks[task] >= best:
                    continue
                tried.add(old)
                loads[lane] += tasks[task]
                path[lane].append(task)
                search(step + 1)
                path[lane].pop()
                loads[lane] = old
                if best == lower:
                    return

        search(0)
    require(
        sorted(i for lane in witness for i in lane) == list(range(len(tasks)))
        and max(sum(tasks[i] for i in lane) for lane in witness) == best
        and best >= lower,
        "lane assignment",
    )
    return best, witness


def score(read_us, fixed_us, payload):
    require(
        all(type(v) is int and v >= 0 for v in (read_us, fixed_us, payload)), "nonnegative units"
    )
    # Budget is 16,000,000/3 microseconds. Use integers to classify ties.
    left = 16_000_000 - 3 * fixed_us
    decisions = {}
    for tag, n, d in (("1", 1, 1), ("0.8", 4, 5)):
        credit = left * d - 3 * n * read_us
        decisions[tag] = dict(
            reaches=credit >= 0,
            seconds=(fixed_us * d + n * read_us) / (d * 1e6),
            excess_s=max(0, -credit) / (d * 3e6),
            additional_cost_allowed_s=max(0, credit) / (d * 3e6),
        )
    return dict(
        fixed_us=fixed_us,
        read_floor_us=read_us,
        scales=decisions,
        max_service_factor=left / (3 * read_us) if read_us and left >= 0 else None,
        logical_payload_bytes=payload,
        required_payload_B_per_s=((3_000_000 * payload + left - 1) // left if left > 0 else None),
    )


def analyze(rows, data, case, old, prior):
    from primary_backing import screen as backing

    jobs, groups, tail, native, initial, late, previous = data
    require(not initial and not late, "unreconciled I")
    clocks, ranks, components = backing.markers(rows)
    totals = {tier: Counter() for tier in ("CPU", "CUDA")}
    hist = {i: Counter() for i in range(5)}
    witness = []
    schedule = hashlib.sha256()
    consumed = set()
    for i, g in enumerate(groups):
        cl = call, layer = g["call"], g["layer"]
        require((call - 1, layer) == divmod(i, 36), "group order")
        z = clocks.pop(cl)
        req = ranks.pop(cl)
        ids = [e for e, s in req]
        witness.append((call, layer, backing.PROMPT[case] + call - 1, ids))
        require(
            set(z) in ({2, 14}, {2, 11, 12, 14})
            and previous <= z[2] <= z[14] == g["original_ready"],
            "group clocks",
        )
        wait = (z[11], z[12]) if 11 in z else None
        require(not wait or z[2] <= wait[0] <= wait[1] <= z[14], "wait clock")
        fixed = g["after"] + g["attention"] + g["pre"]
        stall = wait[1] - wait[0] if wait else 0
        require(stall == g["wait"] and stall + fixed == z[14] - previous, "C295 interval")
        previous = z[14]
        reads = {}
        labels = []
        durations = []
        for w in g["need"]:
            j = jobs[w]
            require(
                w not in consumed
                and w[0] == layer
                and w[1] not in reads
                and j["owner"] == call
                and z[2] <= j["begin"] <= j["end"] <= z[14],
                "unowned or overlapping job",
            )
            consumed.add(w)
            cc = components.pop(w)
            require(set(cc) == {(c, k) for c in range(3) for k in (6, 7)}, "READ boundaries")
            spans = [(cc[c, 6], cc[c, 7]) for c in range(3)]
            require(
                j["begin"] <= spans[0][0]
                and spans[-1][1] <= j["end"]
                and sum(b - a for a, b in spans) == j["read"],
                "READ envelope",
            )
            reads[w[1]] = spans
            for c, (a, b) in enumerate(spans):
                labels.append((*w, c))
                durations.append(max(0, b - a - 1))
        require(
            all(state in (0, 2) for _, state in req)
            and set(reads) == {e for e, state in req if state == 0},
            "historical demand generations",
        )
        # Only actual hits are free here. All observed misses still pay, including reloads.
        v = backing.contribution(set(ids) - set(reads), ids, reads, wait)
        serial = v["all_read_floor_us"]
        outside = v["union_outside_wait_us"]
        require(
            v["required"] == len(reads)
            and v["required_read_floor_us"] == serial
            and outside <= fixed,
            "observed baseline or union",
        )
        optimum, lanes = solve(durations)
        require(optimum <= serial, "four-worker serial baseline is feasible")
        schedule.update(
            (
                json.dumps(
                    [cl, [(labels[j], durations[j]) for j in range(len(labels))], lanes],
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
        )
        stats = dict(
            groups=1,
            jobs=len(reads),
            reads=len(durations),
            payload_bytes=COMPONENT * len(durations),
            serial_floor_us=serial,
            parallel_floor_us=optimum,
            read_worker_us=sum(durations),
            read_union_outside_wait_us=outside,
            nonwait_us=fixed,
            observed_wait_us=stall,
        )
        totals["CPU" if layer < 25 else "CUDA"].update(stats)
        hist[len(reads)].update(stats)
    require(
        len(groups) == 1152
        and not ranks
        and not clocks
        and not components
        and consumed == {w for w, j in jobs.items() if j["owner"] > 0},
        "incomplete service",
    )
    require(
        backing.check_witness(case, witness) == old["ordered_rank_sha256"] == prior["ranks_sha256"],
        "rank witness",
    )
    total = sum(totals.values(), Counter())
    require(
        total["reads"] == total["jobs"] * 3
        and total["payload_bytes"] == total["reads"] * COMPONENT
        and sum(hist.values(), Counter()) == total,
        "conservation",
    )
    for k, v in totals.items():
        ctrl = old["tiers"][k]
        require(
            (v["serial_floor_us"], v["jobs"], v["reads"], v["payload_bytes"])
            == (
                ctrl["read_floor_us"],
                ctrl["misses"],
                ctrl["read_pairs"],
                ctrl["logical_read_bytes"],
            )
            and v["serial_floor_us"] == prior["tiers"][k]["all_read_floor_us"],
            "serial tier control",
        )
    original = total["nonwait_us"] + tail
    require(
        total["serial_floor_us"] == old["read_floor_us"]
        and original == prior["original_fixed_us"]
        and native == original + total["observed_wait_us"] == prior["native_us"],
        "clock controls",
    )
    fixed = original - total["read_union_outside_wait_us"]
    require(
        0 <= fixed <= prior["charged_fixed_us"],
        "whole-miss overlap must include first-miss overlap",
    )
    payload = total["payload_bytes"]
    return dict(
        tiers=totals,
        groups_by_misses=hist,
        total=total,
        lanes_sha256=schedule.hexdigest(),
        ordered_rank_sha256=old["ordered_rank_sha256"],
        native_window_journal_us=int(native),
        native_decode32_s=old["native_decode32_s"],
        observed_tail_us=tail,
        observed_nonwait_including_tail_us=original,
        charged_nonwait_us=fixed,
        max_service_gain_us=total["serial_floor_us"] - total["parallel_floor_us"],
        serial_control={
            scope: score(total["serial_floor_us"], f, payload)
            for scope, f in (("service", 0), ("with_fixed", fixed))
        },
        parallel={
            scope: score(total["parallel_floor_us"], f, payload)
            for scope, f in (("service", 0), ("with_fixed", fixed))
        },
    )


def run(raw, out):
    from component_ready_bound import screen as ready
    from primary_backing import screen as backing

    require(not ready.git("status", "--porcelain"), "dirty checkout")
    pins = {
        "component_ready_bound/screen.py": (
            "aa9684f2179f3781e50d07eb6c4e22a00cd50439d21f1c7486a58480d5d7f9be"
        ),
        "primary_backing/screen.py": (
            "ec2290dda690bfc4a820675812586b01f5eac53fe32232cdab75ff5022181e4d"
        ),
        "cache_boundary.py": ("be5df42b7731dbb0c0cb2565a1d7b73dcb01a3ba5a5ccec101629ad2bbb267b2"),
    }
    for rel, fingerprint in pins.items():
        backing.pinned(UNIT / rel, fingerprint)
    backing.pinned(Path(backing.c295.__file__), backing.critical.C295)
    backing.pinned(HERE / "protocol.md", PROTOCOL)
    names = ready.c294.NAMES
    manifest = ready.c294.MANIFEST
    entries = {
        v["path"].split("/raw/")[1]: v
        for v in json.loads(backing.pinned(manifest, ready.c294.MANIFEST_SHA))["files"]
    }
    backing.pinned(manifest.with_name("protocol.json"), ready.C294_PROTOCOL)
    old, prior = [json.loads(backing.pinned(UNIT / path, h))["arms"] for path, h in PINS.items()]
    out.update(
        commit=ready.git("rev-parse", "HEAD"),
        tree=ready.git("rev-parse", "HEAD^{tree}"),
        protocol_sha256=PROTOCOL,
        program_sha256=ready.sha(Path(__file__).read_bytes()),
        manifest_sha256=ready.c294.MANIFEST_SHA,
        controls_sha256=PINS,
        sources_sha256=pins,
    )
    for name in names:
        value = ready.arm(raw, entries, name)
        require(
            value == old[name]
            and value["raw_sha256"] == prior[name]["raw_sha256"]
            and value["entry_slot_sha256"] == prior[name]["anchor_sha256"],
            "independent serial control",
        )
        path = raw / (name + ".native") / "events.tsv"
        rows = backing.c295.events(path, True)
        backing.pinned(path, value["raw_sha256"]["events.tsv"])
        data = backing.c295.extract(rows)
        out["arms"][name] = dict(
            **analyze(rows, data, name.split("-")[1], value, prior[name]),
            raw_sha256=value["raw_sha256"],
            entry_sha256=value["entry_slot_sha256"],
        )
        del rows, data
    out["decisions"] = {}
    for scope in ("service", "with_fixed"):
        out["decisions"][scope] = {}
        for scale in ("1", "0.8"):
            verdict = {
                n: a["parallel"][scope]["scales"][scale]["reaches"] for n, a in out["arms"].items()
            }
            out["decisions"][scope][scale] = {
                "reaches": verdict,
                "screen": "NOT_EXCLUDED_BY_READ_ONLY"
                if all(verdict.values()) and scope == "service"
                else "GO_PAID_STORAGE_FIXTURE_ONLY"
                if all(verdict.values())
                else "NO_GO_IN_FAILING_ARMS",
            }
    out["status"] = "PASS_FIXED_DURATION_COMPONENT_SCREEN"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ("raw-dir", "new-output-dir"):
        ap.add_argument("--" + arg, required=True, type=Path)
    args = ap.parse_args()
    root = args.new_output_dir
    require(not root.resolve().is_relative_to(args.raw_dir.resolve()), "protect raw")
    root.mkdir(mode=0o700)
    out = {"status": "FAIL_PRESERVED", "arms": {}}

    def expired(*_):
        raise TimeoutError("wall budget")

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(120)
    try:
        for k, cap in (
            (resource.RLIMIT_AS, 512 << 20),
            (resource.RLIMIT_CPU, 120),
            (resource.RLIMIT_FSIZE, 8 << 20),
        ):
            soft, hard = resource.getrlimit(k)
            resource.setrlimit(k, (min(x for x in (soft, hard, cap) if x >= 0), hard))
        run(args.raw_dir, out)
    except FileNotFoundError as e:
        out.update(error=Path(e.filename).name, status="NOT_RUN_RAW_REQUIRED")
    except (
        OSError,
        ValueError,
        ArithmeticError,
        KeyError,
        TypeError,
        MemoryError,
        IndexError,
        RuntimeError,
    ) as e:
        out["error"] = str(e) or type(e).__name__
    finally:
        signal.alarm(0)
        data = (json.dumps(out, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        require(len(data) < 8 << 20, "output budget")
        tmp = root / ".pending"
        with tmp.open("xb") as f:
            f.write(data)
        os.link(tmp, root / "receipt.json")
        tmp.unlink()
    print(out["status"])
    return int("error" in out)


if __name__ == "__main__":
    raise SystemExit(main())

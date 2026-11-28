"""Audit real local CPU consumer clocks alongside the complete numerical two-turn run."""

import argparse
import fcntl
import gzip
import json
import os
import sys
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
E = HERE / "evidence-20261128-r01"
OLD = run_path(HERE.parent / "consumer_run.py")
C, BASE, need, sha, read, save, checked = (
    OLD[k] for k in ("C", "BASE", "need", "sha", "read", "save", "checked")
)
ORDER, MODES = OLD["ORDER"], OLD["MODES"]
WAIT = "11a4e1396c185ae7e7e3f720e14e2aad4c83867979451e7032c1e69f84f05592"
PROTOCOL = "d348c35e819a87f5772a783a449b4e70faf6c4a851a8a28c98d9e36f1c0346aa"
REFERENCE = "1cc9714e9bb32d22d9488bf5b4d294ae240520c25feffff40618e0ce1b93d1a8"


def truth():
    need(sha(E / "waits.json.gz") == WAIT, "authentic wave receipts")
    all_traces = json.loads(gzip.decompress((E / "waits.json.gz").read_bytes()))["traces"]
    spec = None
    for t in all_traces.values():
        events = t["site_events"]
        order = [[r[2], r[3], r[4], r[7]] for r in events if r[0] == 11]
        ranks = [v for r in events if r[0] == 27 for v in r[7].to_bytes(4, "little")]
        waves = []
        for site, pins, _ in t["site_pins"]:
            active = {e: s for _, s, _, e in pins}
            waves.append(
                dict(
                    wave=site[3],
                    pins=[[e, s, g] for _, s, g, e in pins],
                    ids=ranks,
                    remap=[active.get(e, -1) for e in ranks],
                )
            )
        current = dict(order=order, waves=waves)
        need(
            (spec is None or spec == current)
            and len(order) == 13
            and len(ranks) == 80
            and len(waves) == 5,
            "two journals must identify the same queue and ranks",
        )
        spec = current
    return spec


def local(row, spec):
    need(
        row["source_replaced"] == 1 and [v["reservation"] for v in row["jobs"]] == spec["order"],
        "native reservation order or stale generation",
    )
    begin = row["waves"][0]["begin"]
    previous = begin
    by_expert = {}
    workers = set()
    for job in row["jobs"]:
        expert, slot, gen, old = job["reservation"]
        r0, r1 = job["read"]
        need(
            0 <= slot < 40
            and gen > 0
            and old != expert
            and begin <= r0 <= r1
            and len(job["sets"]) == 3,
            "read begun before reservation or changed slot",
        )
        t = r1
        for a, b in job["sets"]:
            need(t <= a <= b, "overlap or component reorder")
            t = b
        need(
            t <= job["publication"]
            and job["tid"] > 0
            and expert not in by_expert
            and job["from_ram"] == (row["mode"] in ("V", "H") and expert == 54),
            "wrong byte source",
        )
        by_expert[expert] = job["publication"]
        workers.add(job["tid"])
    need(len(workers) == 4, "target cohort must actually exercise four workers")
    counts = []
    for expected, w in zip(spec["waves"], row["waves"], strict=True):
        need(
            all(w[k] == expected[k] for k in ("ids", "pins", "remap"))
            and previous <= w["begin"] < w["end"],
            "observed target order, pins, parking remap or clock",
        )
        own = [(by_expert[e], e) for e, _, _ in w["pins"] if e in by_expert]
        latest = max(own, default=(0, None))
        need(latest[0] <= w["end"], "unpublished weight consumed")
        counts.append(
            dict(
                last=latest[1],
                last_relative_ns=latest[0] - begin if own else None,
                duration_ns=w["end"] - w["begin"],
            )
        )
        previous = w["end"]
    end = row["waves"][1]["end"]
    return dict(
        site_ns=end - begin,
        wave1_ns=counts[1]["duration_ns"],
        waves=counts,
        weight54_pub_ns=by_expert[54] - begin,
        workers=len(workers),
    )


def row_ok(r, spec, reference):
    mode = r["mode"]
    need(
        r["numerical"] == reference["numerical"]
        and r["census_sha256"] == reference["census_sha256"]
        and r["all_ns"] == r["arm_ns"] + r["forward_ns"] + r["cleanup_ns"] < r["whole_ns"]
        and 0 < r["native148_ns"] <= r["forward_ns"]
        and r["selected"] == 70
        and r["logical"] == r["served"] + r["disk"] == 1212
        and r["stage_copy_bytes"] == 0
        and r["served"] == (70 if mode in ("H", "V") else 0)
        and r["training_reads"] >= 69
        and r["full_hashes"] == (207 if mode == "V" else 0)
        and r["parity_read_bytes"] == (69 * 13221888 if mode == "V" else 0)
        and len(r["captures"]) == r["captured"] == (0 if mode == "R" else 69),
        "whole numerical trajectory, traffic or clock",
    )
    caps = r["captures"]
    need(
        len({v[0] for v in caps}) == len(caps)
        and all(0 <= v[1] < 40 and v[2] > 0 and v[3] > 0 for v in caps),
        "materialized records or source generation",
    )
    return local(r, spec)


def reference():
    return checked(HERE.parent / "evidence-20261128-r01/consumer-grade.json", REFERENCE)["rows"][0]


def grade(rows):
    need(
        [r["role"] for r in rows] == list(ORDER) and [r["mode"] for r in rows] == list(MODES),
        "paired order",
    )
    spec, ref = truth(), reference()
    sites = [row_ok(r, spec, ref) for r in rows]
    captured_ids = {v[0] for v in rows[1]["captures"]}
    need(
        all(
            r["training_reads"] == rows[0]["training_reads"]
            and (r["mode"] == "R" or {v[0] for v in r["captures"]} == captured_ids)
            for r in rows
        ),
        "T1 work or retained identities",
    )
    clocks = {}
    pairs = {}
    for k in ("site_ns", "wave1_ns", "all_ns", "whole_ns"):
        series = sites if k in ("site_ns", "wave1_ns") else rows
        diffs = [
            {name: series[h][k] - series[j][k] for name, j in (("H-O", o), ("H-R", r))}
            for r, o, h in ((2, 3, 4), (7, 6, 5))
        ]
        pairs[k] = diffs
        clocks[k] = (
            "GO_NEXT_STAGE"
            if all(max(d.values()) < 0 for d in diffs)
            else ("NO_GO" if all(d["H-R"] >= 0 for d in diffs) else "INCONCLUSIVE")
        )
    if clocks["site_ns"] == "GO_NEXT_STAGE" and any(d["H-O"] > 0 for d in pairs["wave1_ns"]):
        clocks["site_ns"] = "INCONCLUSIVE"
    return dict(
        status=clocks,
        paired_ns=pairs,
        sites=sites,
        protocol=PROTOCOL,
        wait_sha256=WAIT,
        evidence="MEASURED_120B_FIXED_FUTURE_COHORT",
        http_requests=0,
    )


def run(a, out, report):
    _, prov, history = C["previous"](a.previous)
    reg = C["settings"](prov)
    reg.window, reg.window_sha256, reg.prepare_only, reg.commit = (
        a.window,
        a.window_sha256,
        False,
        a.commit,
    )
    head, tree = OLD["U"]["M"]["B"]["version"]()
    need(head == a.commit and sha(HERE / "provider.md") == PROTOCOL, "clean frozen protocol")
    image = checked(a.images / "receipt.json", a.images_sha256)
    need(
        image["status"] == "BUILT"
        and image["protocol"] == PROTOCOL
        and all(sha(HERE / k) == v for k, v in image["inputs"].items()),
        "source closure",
    )
    build = checked(reg.build_dir / "receipt.json", BASE["T"]["BUILD"])
    template = checked(reg.template / "receipt.json", BASE["PREVIOUS"])
    policy, model_id = C["admission"](reg)
    spec, ref = truth(), reference()
    report.update(
        commit=head,
        tree=tree,
        window=a.window_sha256,
        images=a.images_sha256,
        protocol=PROTOCOL,
        expected=spec,
        prior=REFERENCE,
        rows=[],
    )
    save(
        out / "provenance.json",
        report | dict(argv=sys.argv, order=ORDER, runner=sha(Path(__file__))),
    )
    for role, mode in zip(ORDER, MODES, strict=True):
        reg.unit = out.name + "-" + role
        reg.client = a.images / mode
        files = image["modes"][mode]
        need(all(sha(reg.client / k) == v for k, v in files.items()), "pinned executable or inputs")
        work = read(reg.client / "work.json")
        need(
            work["owner_mode"] == mode and work["owner_plan"] == image["plan"],
            "source intervention",
        )
        report["stage"] = role
        dest = out / role
        rec = BASE["arm"](reg, dest, "S", dict(files=files), build, policy, model_id, template)
        native = checked(
            dest / "raw" / (rec["unit"] + ".capture/native.json"), rec["native_sha256"]
        )
        numeric = OLD["numeric"](native, history["S"], work)
        metrics = native["entry_delivery"].copy()
        census = metrics.pop("census")
        need(len(census) == 4608 and sum(census) == 1212, "acquisition census")
        for k in ("pool148", "pool_first_decode"):
            del metrics[k]
        row = dict(
            **metrics,
            role=role,
            numerical=numeric,
            census_sha256=OLD["digest"](census),
            authority=rec,
            native148_ns=native["prefill"][1]["wall_ns"],
            native5_ns=native["prefill"][0]["wall_ns"],
            decode46_ns=sum(r["wall_ns"] for r in native["decode"]),
        )
        site = row_ok(row, spec, ref)
        need(row["mode"] == mode, "observed mode")
        if report["rows"]:
            need(row["training_reads"] == report["rows"][0]["training_reads"], "same prior work")
        report["rows"].append(row)
        save(dest / "verified-arm.json", row)
        print(role, mode, "PASS", site["site_ns"], row["all_ns"], row["whole_ns"], flush=True)
        need(
            time.monotonic() - report["_start"] < 1600
            and OLD["B"]["measure"].file_bytes(out) < 512 << 20,
            "family budget",
        )
    report["grade"] = grade(report["rows"])
    report["status"] = "MEASURED"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    live = sub.add_parser("run")
    for key in ("previous", "images", "window", "new-output-dir"):
        live.add_argument("--" + key, type=lambda s: Path(s).resolve(), required=True)
    for key in ("images-sha256", "window-sha256", "commit"):
        live.add_argument("--" + key, required=True)
    check = sub.add_parser("check")
    check.add_argument("evidence", type=Path)
    args = p.parse_args()
    if args.action == "check":
        rows = json.loads(gzip.decompress((args.evidence / "arms.json.gz").read_bytes()))
        got = grade(rows)
        need(got == read(args.evidence / "physical-grade.json"), "public grade")
        print(got["status"])
        return
    os.umask(0o077)
    out = args.new_output_dir
    out.mkdir()
    report = dict(status="FAIL_PRESERVED", _start=time.monotonic())
    try:
        with (out.parent / "tesy-verifier-wait.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(args, out, report)
    except Exception as exc:
        report.update(reason=repr(exc))
    report["elapsed_s"] = time.monotonic() - report.pop("_start")
    save(out / "receipt.json", report)
    print(report["status"], report.get("reason", ""), flush=True)
    raise SystemExit(int(report["status"] != "MEASURED"))


if __name__ == "__main__":
    main()

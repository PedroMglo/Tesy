"""Close the delivered weight records, both paid control pairs, and finite frame counts."""

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import visit as v  # noqa: E402


def solve(w):
    visits, cap = v.cases()
    meta, phy = w["plan"], w["physical"]
    timing = v.parse(w["stdout"].splitlines(), meta)
    h = hashlib.sha256(w["stdout"].encode()).hexdigest()
    v.need(
        phy["status"] == "MEASURED"
        and phy["protocol"] == v.METHOD
        and phy["stdout_sha256"] == h
        and phy["requested_B"] == v.requested(timing, meta) * v.T["SIZE"]
        and phy["disk_delta"]["read_sectors_512B"] * 512 >= phy["requested_B"]
        and phy["full_model_requests"] == 0
        and phy["cgroup"]["swap_current"] == 0
        and phy["max_sample_gap_s"] < 3
        and phy["pcie"] == ["16.0 GT/s PCIe", "4"]
        and meta["capacity"] == cap,
        "physical scope, counter or residency",
    )
    for (site, jobs), rec in zip(visits, meta["visits"], strict=True):
        v.need(
            rec["site"] == list(site)
            and (rec["served"], rec["seed"]) == (len(jobs), sum(h for _, _, h in jobs)),
            "different cohort",
        )
    arms = []
    for i, rows in enumerate(timing["arms"]):
        arms.append(
            dict(
                role="HOLD" if i in (1, 2) else "RELOAD",
                records=sum(r["reads"] for r in rows),
                service_ns=sum(r["wall_ns"] for r in rows),
                entry_ns=sum(r["seed_ns"] for r in rows),
                dispatches=sum(r["dispatches"] for r in rows),
            )
        )
    delta = [arms[a]["service_ns"] - arms[b]["service_ns"] for a, b in ((0, 1), (3, 2))]
    at_site = {(a, b): (active, park) for a, b, _, active, park in cap}
    evidence = []
    for j, (site, jobs) in enumerate(visits):
        evidence.append(
            dict(
                site=list(site),
                held=sum(h for _, _, h in jobs),
                active_peak=at_site[site][0],
                park_upper_peak=at_site[site][1],
                service_saved_ns=[
                    timing["arms"][a][j]["wall_ns"] - timing["arms"][b][j]["wall_ns"]
                    for a, b in ((0, 1), (3, 2))
                ],
            )
        )

    def capacity_decision():
        if max(row["active_peak"] for row in evidence) > 1252:
            return "NO_GO_ALL_ELEVEN_1252"
        if max(row["park_upper_peak"] for row in evidence) <= 1252:
            return "FITS_SERIAL_GIVEN_TERMINAL_MEMBERSHIP"
        return "INCONCLUSIVE_PARKING_ORDER"

    return dict(
        status="GO_LOCAL_DELIVERY"
        if min(delta) > 0
        else "INCONCLUSIVE_LOCAL_DELIVERY"
        if max(delta) > 0
        else "NO_GO_LOCAL_DELIVERY",
        capacity=capacity_decision(),
        arms=arms,
        service_saved_ns=delta,
        visits=evidence,
        max_active_all_125=max(r[-2] for r in cap),
        max_park_upper_all_125=max(r[-1] for r in cap),
        required_pack_bytes=phy["requested_B"],
        physical_read_sectors=phy["disk_delta"]["read_sectors_512B"],
        parity_components=timing["matrix_sha256_comparisons"],
        delivered_markers=timing["delivered_markers"],
        seed_markers=timing["initial_markers"],
        model_forwards=0,
        client_measured_ns=None,
        m3="PARTIAL",
        m4="NOT_MET",
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--new", type=Path)
    mode.add_argument("--check", type=Path)
    cli.add_argument("--plan", type=Path)
    cli.add_argument("--physical", type=Path)
    args = cli.parse_args()
    if args.check:
        w = json.loads(gzip.decompress((args.check / "reads.json.gz").read_bytes()))
        result = solve(w)
        v.need(result == json.loads((args.check / "decision.json").read_bytes()), "public replay")
    else:
        if not (args.plan and args.physical):
            cli.error("--new requires --physical and --plan")
        args.new.mkdir(exist_ok=False)
        try:
            phy = json.loads((args.physical / "receipt.json").read_bytes())
            plan = v.verified(args.plan / "receipt.json", phy["plan_sha256"])
            v.need(
                v.sha(args.physical / "samples.jsonl") == phy["samples_sha256"]
                and v.sha(args.plan / "windows.tsv") == plan["windows"]
                and phy["tree"] == plan["tree"],
                "inputs",
            )
            w = dict(
                physical={k: val for k, val in phy.items() if k != "timing"},
                physical_sha256=v.sha(args.physical / "receipt.json"),
                plan={k: plan[k] for k in ("visits", "capacity", "unique", "pack_stat", "windows")},
                stdout=(args.physical / "stdout").read_text(),
            )
            v.need(v.parse(w["stdout"].splitlines(), plan) == phy["timing"], "timing archive")
            result = solve(w)
            with (args.new / "reads.json.gz").open("xb") as f:
                f.write(
                    gzip.compress(
                        json.dumps(w, sort_keys=True, separators=(",", ":")).encode(), mtime=0
                    )
                )
            v.save(args.new / ".pending", result)
            (args.new / ".pending").rename(args.new / "decision.json")
        except Exception as exc:
            v.save(args.new / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
            raise
    print(result["status"], result["capacity"], result["service_saved_ns"])


if __name__ == "__main__":
    main()

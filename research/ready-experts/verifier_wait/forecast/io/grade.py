"""Check transfer lineage and combine measured QD4 reads with the two protected client cuts."""

import argparse
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
M = run_path(HERE / "prepare.py")
P, F, S, J = (M[k] for k in ("P", "F", "S", "J"))
need, load, sha, save, verified = (F[k] for k in ("need", "load", "sha", "save", "verified"))


def parse(lines, plan):
    need(
        len(lines) == 187
        and lines[0].split() == ["fd", *map(str, plan["pack_stat"])]
        and lines[-1] == "drained",
        "FD, output extent or terminal drain",
    )
    what, n, t = lines[1].split()
    need(what == "parity" and int(n) == plan["unique"] and int(t) > 0, "pre-timing parity")
    arms = []
    for i, mode in enumerate((0, 1, 1, 0)):
        rows = []
        for c, line in enumerate(lines[2 + 46 * i : 2 + 46 * (i + 1)]):
            kind, *fields = line.split()
            arm, m, at, count, batches, rd, wall = map(int, fields)
            need(
                kind == "step"
                and (arm, m, at, count) == (i + 1, mode, c + 1, plan["counts"][mode][c])
                and batches == (count + 3) // 4
                and wall >= rd >= 0
                and bool(rd) == bool(count),
                "arm, step, byte count or clocks",
            )
            rows.append([count, batches, rd, wall])
        arms.append(dict(arm=i + 1, mode="H" if mode else "D", steps=rows))
    return dict(
        arms=arms,
        parity_records=int(n),
        parity_ns=int(t),
        parity_component_hashes=3 * int(n),
        checked_timed_markers=9 * sum(row[0] for a in arms for row in a["steps"]),
    )


def review(data):
    cert = verified(HERE.parent / "evidence-joint-20261128-r01/receipt.json", M["CERT"])
    score = verified(HERE.parent / "evidence-joint-20261128-r01/scores.json.gz", cert["scores"])
    single = verified(J["BASE"] / "witness.json.gz", J["WITNESS_SHA"])
    offers = J["events"](score["calls"])
    chosen = {
        k: J["materialize"](single["calls"], offers, flag, M["CUT"] if flag else J["MAX"])
        for k, flag in (("D", False), ("H", True))
    }
    parent = verified(F["CONTROL"], F["CONTROL_SHA"])
    p = {k: verified(path, parent["inputs"][k]) for k, path in S["PATHS"].items()}
    inventory = F["Inventory"](p["transactions"])
    hots = p["resident"]["evidence"]["arms"]["S"]
    out = []
    for a in data["arms"]:
        rows = a["steps"]
        times = [s[2] for s in rows]
        counts = [s[0] for s in rows]
        arms = []
        for tag in ("P97", "P106"):
            jobs = P["groups"](tag, p, inventory)
            residual = []
            for c, layers in enumerate(chosen[a["mode"]], 1):
                wait = volume = 0
                for layer, (issued, mask) in enumerate(layers):
                    ns, cold = P["remaining"](jobs.get((c, layer), []), mask, 8_000_000_000)
                    wait += ns
                    volume += cold + issued - mask.bit_count()
                need(volume == counts[c - 1], "physical census vs analytic cut")
                residual.append(wait)
            for f in p["resident"]["prices"]:
                if f["role"] != "S" or f["replay"] != 1 or f["prefill"] != tag:
                    continue
                hot = [v["hot_ns"][f["repeat"] - 1] for v in hots]
                extra = [max(r, io - h) for r, io, h in zip(residual, times, hot, strict=True)]
                first = [v + sum(extra[:44]) for v in f["all_hot_first_range_ns"]]
                io_first = [
                    v - sum(hot[:44]) + sum(times[:44]) for v in f["all_hot_first_range_ns"]
                ]
                dec = f["all_hot_decode_ns"] + sum(extra)
                arms.append(
                    dict(
                        tag=tag,
                        W=f["W"],
                        repeat=f["repeat"],
                        first_ns=first,
                        decode_ns=dec,
                        common_slack_ns=min(10**10 - first[1], P["DECODE_MAX"] - dec),
                        device_only_first_ns=io_first,
                    )
                )
        need(len(arms) == 8, "two journals, two clients and two resident prices")
        out.append(
            dict(
                arm=a["arm"],
                mode=a["mode"],
                requested_B=sum(counts) * P["SIZE"],
                early_B=sum(counts[:44]) * P["SIZE"],
                read_ns=sum(times),
                early_read_ns=sum(times[:44]),
                step_wall_ns=sum(s[3] for s in rows),
                arms=arms,
                verdict=P["decision"](arms),
            )
        )
    return dict(
        evidence="MEASURED_QD4_READS_TRACE_DERIVED_CLIENT",
        physical=out,
        status={
            m: P["decision"]([r for arm in out if arm["mode"] == m for r in arm["arms"]])
            for m in ("D", "H")
        },
        parity_records=data["parity_records"],
        parity_ns=data["parity_ns"],
        component_hashes=data["parity_component_hashes"],
        markers=data["checked_timed_markers"],
        requested_B=sum(a["requested_B"] for a in out) + P["SIZE"] * data["parity_records"],
        forward_passes=0,
        protocol=M["PROTOCOL"],
        program=sha(Path(__file__)),
    )


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--observed", type=Path, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", type=Path)
    g.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        raw = load(a.observed)
        need(raw["status"] == "MEASURED" and raw["protocol"] == M["PROTOCOL"], "physical receipt")
        r = review(raw["timing"])
        r["observed_sha256"] = sha(a.observed)
        if a.check:
            need(r == load(a.check), "clock or decision changed")
        else:
            save(a.new_output_dir / "grade.json", r)
        print(r["status"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    cli()

"""Price fully resident n1/B3 calls on the same prefix and on both client-clock boundaries."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(HERE / "grade.py")
need = G["need"]
STUDY = HERE.parent / "draft20/evidence-20261128-r01/study.json"
COMBINED = HERE.parent / "draft20/joint/evidence-20261128-r01/combined.json"


def read(p):
    return json.loads(p.read_bytes())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def acquire(a):
    H = run_path(HERE / "hot_run.py")
    _, _, ref = H["C"]["previous"](a.previous)
    r, p = read(a.family / "receipt.json"), read(a.family / "provenance.json")
    need(
        r["status"] == "MEASURED_LIVE_HOT_SHADOWS"
        and [v["role"] for v in r["arms"]] == ["S", "B1"]
        and sha(a.client / "receipt.json") == p["client_sha256"]
        and sha(a.client / "work.json") == read(a.client / "receipt.json")["files"]["work.json"],
        "measured shadows",
    )
    work = read(a.client / "work.json")
    evidence = {}
    for v in r["arms"]:
        role, unit = v["role"], v["unit"]
        file = a.family / role / "raw" / (unit + ".capture/native.json")
        need(
            sha(file) == v["native_sha256"]
            and sha(a.family / role / "raw" / (unit + ".json")) == v["monitor_sha256"]
            and v["c118"]["s"] >= 60,
            "closed native capture",
        )
        actual = read(file)
        H["compare"](actual, ref[role])
        G["verify"](ref | {role: actual}, work)
        evidence[role] = [
            dict(
                at=d["at"],
                keep=d["keep"],
                width=len(d["ids"]),
                ordinary_ns=d["wall_ns"],
                ordinary_loads=d["counts"][2],
                hot_ns=[h["wall_ns"] for h in d["hot"]],
                hot_loads=[h["counts"][2] for h in d["hot"]],
                verified_rows=len(d["hashes"]),
                union=sum(map(len, d["routes"])),
            )
            for d in actual["decode"]
        ]
    return dict(
        arms=evidence,
        source=p,
        model_s=[v["model_s"] for v in r["arms"]],
        resources=r["arms"],
        elapsed_s=r["elapsed_s"],
        receipt_sha256=sha(a.family / "receipt.json"),
        native_binary_sha256=read(a.client / "receipt.json")["files"]["code-cut"],
    )


def price(e):
    wdata = read(STUDY)["evidence"]["clocks"]["nominal"]
    joint = [r for r in read(COMBINED)["result"]["N2"]["arms"] if r["case"] == "nominal"]
    result = []
    for role, rows in e["arms"].items():
        at = 1
        for r in rows:
            need(
                r["at"] == at
                and r["hot_loads"] == [0, 0]
                and len(r["hot_ns"]) == 2
                and min(r["hot_ns"]) > 0
                and r["verified_rows"] == r["width"]
                and 144 <= r["union"] <= 144 * r["width"],
                "observed hot calls",
            )
            at += r["keep"]
        need(at == 47 and len(rows) == (46 if role == "S" else 34), "complete schedule")
        for rep in (0, 1):

            def service(cut, blocks=False, rows=rows, rep=rep):
                return sum(
                    r["hot_ns"][rep]
                    for r in rows
                    if r["at"] <= cut and (not blocks or r["width"] == 3)
                )

            first, decode = service(44), service(46)
            for j in joint:
                w = next(v for v in wdata if v["arm"] == j["W"])
                c = w["cut"]
                need(
                    c == 44 and w["ticks_ns"][c - 1] <= w["feed_ns"] <= w["ticks_ns"][c],
                    "sample and feed",
                )
                lookup_first = j["first"]["controller_ns"] if role == "B1" else 0
                lookup_decode = j["decode"]["controller_ns"] if role == "B1" else 0
                ext = w["first_final_ns"] - w["prefill_ns"]
                ff = [
                    j["prefill_ns"] + ext - t + first + lookup_first
                    for t in (w["ticks_ns"][c], w["feed_ns"])
                ]
                d = w["decode_ns"] - w["ticks_ns"][-1] + decode + lookup_decode
                firm = min(10**10 - ff[1], 47 * 10**9 // 6 - d)
                optimistic = min(10**10 - ff[0], 47 * 10**9 // 6 - d)
                block_only = (
                    j["first"]["free_target_ns"] + service(44, True) if role == "B1" else None
                )
                block_decode = (
                    j["decode"]["free_target_ns"] + service(46, True) if role == "B1" else None
                )
                result.append(
                    dict(
                        role=role,
                        repeat=rep + 1,
                        W=j["W"],
                        replay=j["replay"],
                        prefill=j["prefill_source"],
                        block_only_first_ns=block_only,
                        block_only_decode_ns=block_decode,
                        all_hot_first_range_ns=ff,
                        all_hot_decode_ns=d,
                        common_extra_ns=[firm, optimistic],
                        first_target_ns=first,
                        decode_target_ns=decode,
                    )
                )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("previous", "family", "client"):
        p.add_argument("--" + k, type=Path)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", type=Path)
    g.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    need(
        all((a.previous, a.family, a.client))
        or (a.check and not any((a.previous, a.family, a.client))),
        "raw inputs",
    )
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        prior = read(a.check) if a.check else None
        e = acquire(a) if a.family else prior["evidence"]
        need(
            all(sha(HERE / k) == v for k, v in e["source"]["source_sha256"].items())
            and sha(HERE / "hot-protocol.md") == e["source"]["protocol_sha256"],
            "audited source",
        )
        output = dict(
            evidence=e, prices=price(e), sources={f.name: sha(f) for f in (STUDY, COMBINED)}
        )
        if a.check:
            need(output == prior, "hot assessment differs")
        else:
            with (a.new_output_dir / "receipt.json").open("x") as w:
                json.dump(output, w, separators=(",", ":"), sort_keys=True)
                w.write("\n")
        print("REPRODUCED_HOT_CUTS")
    except Exception as exc:
        if a.new_output_dir:
            (a.new_output_dir / "failure.json").write_text(
                json.dumps(dict(status="FAIL_PRESERVED", reason=str(exc)))
            )
        raise

"""Reproduce the decision from service intervals and optionally verify the original captures."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(HERE / "grade.py")
need = G["need"]
COMBINED = HERE.parent / "draft20/joint/evidence-20261128-r01/combined.json"


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def acquire(family, build, last):
    closed = read(family / "receipt.json")
    p = read(family / "provenance.json")
    need(
        closed["commit"] == p["commit"]
        and closed["tree"] == p["tree"]
        and sha(build / "receipt.json") == p["client_sha256"],
        "physical family",
    )
    for k, h in p["source_sha256"].items():
        need(sha(HERE / k) == h, "physical instrument source " + k)
    client = read(build / "receipt.json")
    locations = [(family, r) for r in closed["arms"]]
    additional = {}
    if closed["status"] == "FAIL_PRESERVED":
        complete = run_path(HERE / "complete.py")
        complete["previous"](family)
        need(last is not None, "separate B0b required")
        more, lp = read(last / "receipt.json"), read(last / "provenance.json")
        need(
            more["status"] == "MEASURED_INDEPENDENT_B0B"
            and more["previous_sha256"] == complete["FAIL"]
            and lp["previous_provenance"] == complete["PROVENANCE"]
            and lp["client_sha256"] == p["client_sha256"]
            and sha(HERE / "completion.md") == lp["protocol_sha256"]
            and sha(HERE / "complete.py") == lp["source_sha256"],
            "independent B0b identity",
        )
        locations.extend((last, r) for r in more["arms"])
        additional = dict(
            status=more["status"],
            receipt_sha256=sha(last / "receipt.json"),
            provenance_sha256=sha(last / "provenance.json"),
            commit=more["commit"],
            tree=more["tree"],
            elapsed_s=more["elapsed_s"],
            c55_sha256=lp["window_sha256"],
        )
    else:
        need(closed["status"] == "MEASURED_VERIFIER_WAIT" and not last, "physical closure")
    need(
        sha(build / "work.json") == client["files"]["work.json"]
        and [r["role"] for _, r in locations] == p["order"] == ["S", "B0a", "B1", "B0b"],
        "role order and inputs",
    )
    arms = {}
    for owner, a in locations:
        role, unit = a["role"], a["unit"]
        folder = owner / role
        cap = folder / "raw" / (unit + ".capture") / "native.json"
        need(
            sha(cap) == a["native_sha256"]
            and sha(folder / "raw" / (unit + ".json")) == a["monitor_sha256"]
            and sha(folder / "invocation.json") == a["argv_sha256"]
            and a["c118"]["s"] >= 60
            and a["fd_samples"] > 0,
            role + " raw provenance",
        )
        arms[role] = read(cap)
    work = read(build / "work.json")
    G["verify"](arms, work)
    hash_count = {role: 1 + sum(len(r["hashes"]) for r in a["decode"]) for role, a in arms.items()}
    counts = {
        role: dict(full_rows=n, confirmed_rows=len(work["target"]), kv_cuts=len(arms[role]["kv"]))
        for role, n in hash_count.items()
    }
    proof = dict(
        family_sha256=sha(family / "receipt.json"),
        provenance_sha256=sha(family / "provenance.json"),
        commit=closed["commit"],
        tree=closed["tree"],
        client_sha256=p["client_sha256"],
        executable_sha256=client["files"]["code-cut"],
        inputs_sha256=client["inputs_sha256"],
        protocol_sha256=closed["protocol_sha256"],
        programs=p["source_sha256"],
        c55_sha256=p["window_sha256"],
        elapsed_s=closed["elapsed_s"],
        original_status=closed["status"],
        completion=additional,
        arms=[a for _, a in locations],
        numeric=counts,
        model_starts=len(arms),
        vocabulary=201088,
        model_scope="120B greedy exact in one nominal conversation",
    )
    return dict(evidence=G["compact"](arms), provenance=proof, combined_sha256=sha(COMBINED))


def verify_public(receipt):
    p = receipt["provenance"]
    need(
        sha(COMBINED) == receipt["combined_sha256"]
        and sha(HERE / "protocol.md") == p["protocol_sha256"]
        and all(sha(HERE / k) == h for k, h in p["programs"].items()),
        "public input identity",
    )
    schedule = read(COMBINED)["receipts"][0]["cases"]["nominal"]["N2"]["rows"]
    final = 0
    for role, a in receipt["evidence"].items():
        need([r["size"] for r in a["prefill"]] == [5, 148], "external return geometry")
        seq = [[r["at"], r["width"] - 1, r["accepted"], r["keep"]] for r in a["decode"]]
        n = 1
        for r in a["decode"]:
            need(
                r["at"] == n and 1 <= r["keep"] <= r["width"] and r["wall_ns"] > 0, "sample ledger"
            )
            n += r["keep"]
            if role in ("S", "B1"):
                calls, waves, loads, size, hits, misses, preloads, w, ww = r["counts"]
                u = r["union_by_tier"]
                need(
                    calls == 36
                    and not (waves or ww or preloads)
                    and 0 <= w <= (r["wall_ns"] + 999) // 1000
                    and 0 <= loads == misses
                    and size == G["PAYLOAD"] * loads
                    and hits + misses == sum(u)
                    and all(
                        4 * layers <= count <= 4 * layers * r["width"]
                        for layers, count in zip((25, 11), u, strict=True)
                    ),
                    "compact counters",
                )
        need(n == 47 and (seq == schedule if role != "S" else len(seq) == 46), "frozen work")
        final += n
    need(final == 4 * 47, "four arms")
    # JSON object order may differ between the raw family and the portable copy.
    order = ("S", "B0a", "B1", "B0b")
    need(set(receipt["evidence"]) == set(order), "four distinct arms")
    return G["price"]({k: receipt["evidence"][k] for k in order}, read(COMBINED))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", type=Path)
    p.add_argument("--client", type=Path)
    p.add_argument("--last", type=Path)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--new-output-dir", type=Path)
    g.add_argument("--check", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    need(bool(a.family) == bool(a.client) and (a.check or a.family), "raw inputs")
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        prior = read(a.check) if a.check else None
        capture = (
            acquire(a.family, a.client, a.last)
            if a.family
            else {k: v for k, v in prior.items() if k != "result"}
        )
        result = capture | dict(result=verify_public(capture))
        if a.check:
            need(result == prior, "decision or physical witness differs")
        else:
            with (a.new_output_dir / "receipt.json").open("x") as f:
                json.dump(result, f, sort_keys=True, separators=(",", ":"))
                f.write("\n")
        print(result["result"]["decision"])
    except Exception as exc:
        if a.new_output_dir:
            (a.new_output_dir / "failure.json").write_text(
                json.dumps(dict(status="FAIL_PRESERVED", reason=str(exc)))
            )
        raise

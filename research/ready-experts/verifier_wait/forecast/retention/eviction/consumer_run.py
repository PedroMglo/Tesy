"""Check the full numerical trajectory and time the charged 148-position return."""

import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
U = run_path(HERE / "consumer_build.py")
C = run_path(HERE.parents[2] / "complete.py")
B, BASE, need, sha, read, save, checked = (
    C[k] for k in ("B", "BASE", "need", "sha", "read", "save", "checked")
)
ORDER = U["ORDER"]
MODES = ("R", "V", "R", "O", "H", "H", "O", "R")


def numeric(actual, reference, work):
    BASE["G"]["verify"]({"S": actual}, work)
    need(
        actual.keys() == reference.keys() | {"entry_delivery"}
        and all(actual[k] == reference[k] for k in ("role", "kv", "anchor")),
        "reference KV and anchor",
    )
    for k in ("prefill", "decode"):
        for n, r in zip(actual[k], reference[k], strict=True):
            need(
                n.keys() == r.keys()
                and n["counts"][:7] == r["counts"][:7]
                and all(n[key] == r[key] for key in r.keys() - {"wall_ns", "counts"}),
                "complete logits, greedy IDs, routes or actual reservations",
            )
    return dict(
        anchor=actual["anchor"],
        kv={k: v["sha256"] for k, v in actual["kv"].items()},
        logits_digest=digest([r["hashes"] for r in actual["decode"]]),
        routes_digest=digest([r["routes"] for r in actual["decode"]]),
        ids_digest=digest([r["ids"] for r in actual["decode"]]),
        full_rows=47,
        pool=[actual["entry_delivery"][k] for k in ("pool148", "pool_first_decode")],
    )


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def grade(rows):
    need(
        [r["role"] for r in rows] == list(ORDER) and [r["mode"] for r in rows] == list(MODES),
        "order or roles",
    )
    for r in rows:
        need(
            r["numerical"] == rows[0]["numerical"]
            and r["selected"] == rows[0]["selected"]
            and r["census_sha256"] == rows[0]["census_sha256"]
            and r["all_ns"] == r["capture_ns"] + r["forward_ns"] + r["cleanup_ns"]
            and 0 < r["native148_ns"] <= r["forward_ns"]
            and r["logical"] == r["disk"] + r["served"] == 1212
            and r["served"] == (r["selected"] if r["mode"] in ("V", "H") else 0)
            and r["full_hashes"] == (222 if r["mode"] == "V" else 0)
            and r["captured"] == (0 if r["mode"] == "R" else 74),
            "parity, traffic or charged clock",
        )
    delta = []
    for off, hit, ref in ((3, 4, 2), (6, 5, 7)):
        pairs = {
            k: rows[hit]["all_ns"] - rows[i]["all_ns"]
            for k, i in (("H_minus_O_ns", off), ("H_minus_R_ns", ref))
        }
        delta.append(pairs)
    status = "INCONCLUSIVE"
    if all(max(p.values()) < 0 for p in delta):
        status = "GO_CAUSAL_SELECTION_ONLY"
    elif all(p["H_minus_R_ns"] >= 0 for p in delta):
        status = "NO_GO"
    return dict(
        status=status,
        paired=delta,
        rows=rows,
        evidence="MEASURED_TARGET_PREFILL_ORACLE_SELECTION",
        http_requests=0,
        protocol=U["PROTO"],
    )


def run(cli, out, report):
    _, prov, old = C["previous"](cli.previous)
    a = C["settings"](prov)
    a.window, a.window_sha256, a.prepare_only, a.commit = (
        cli.window,
        cli.window_sha256,
        False,
        cli.commit,
    )
    commit, tree = U["M"]["B"]["version"]()
    need(commit == cli.commit and sha(HERE / "consumer.md") == U["PROTO"], "frozen source")
    client = checked(cli.images / "receipt.json", cli.images_sha256)
    need(
        client["status"] == "BUILT"
        and client["protocol"] == U["PROTO"]
        and all(sha(HERE / k) == v for k, v in client["programs"].items())
        and client["parent"] == U["PARENT"],
        "compiled client",
    )
    build = checked(a.build_dir / "receipt.json", BASE["T"]["BUILD"])
    template = checked(a.template / "receipt.json", BASE["PREVIOUS"])
    policy, model_id = C["admission"](a)
    report.update(
        commit=commit,
        tree=tree,
        protocol=U["PROTO"],
        images_sha256=cli.images_sha256,
        c55_sha256=cli.window_sha256,
        baseline_sha256=sha(cli.previous / "provenance.json"),
        arms=[],
    )
    save(
        out / "provenance.json",
        report | dict(argv=sys.argv, order=ORDER, runner_sha256=sha(Path(__file__))),
    )
    start = time.monotonic()
    for role, mode in zip(ORDER, MODES, strict=True):
        f = out / role
        a.unit = out.name + "-" + role
        a.client = cli.images / mode
        files = client["modes"][mode]
        need(all(sha(a.client / k) == v for k, v in files.items()), "arm's executable or workload")
        work = read(a.client / "work.json")
        need(work["entry_plan"] == client["plan"] and work["entry_mode"] == mode, "enrolled source")
        report["stage"] = role
        rec = BASE["arm"](a, f, "S", dict(files=files), build, policy, model_id, template)
        native = checked(f / "raw" / (rec["unit"] + ".capture/native.json"), rec["native_sha256"])
        numerical = numeric(native, old["S"], work)
        entry = native["entry_delivery"].copy()
        for k in ("pool148", "pool_first_decode"):
            del entry[k]
        census = entry.pop("census")
        need(
            len(census) == 4608
            and sum(census) == entry["logical"] == 1212
            and sum(census[r["layer"] * 128 + r["expert"]] for r in client["plan"]["records"])
            == entry["selected"]
            == client["expected_hits"],
            "observed native calls",
        )
        row = dict(
            **entry,
            role=role,
            numerical=numerical,
            census_sha256=digest(census),
            native148_ns=native["prefill"][1]["wall_ns"],
            native5_ns=native["prefill"][0]["wall_ns"],
            decode46_ns=sum(r["wall_ns"] for r in native["decode"]),
            authority=rec,
        )
        if report["arms"]:
            need(
                row["numerical"] == report["arms"][0]["numerical"]
                and row["census_sha256"] == report["arms"][0]["census_sha256"],
                "independent pool or read census",
            )
        if role == "parity":
            need(
                row["served"] == client["expected_hits"] and row["full_hashes"] == 222,
                "pre-timing parity",
            )
        report["arms"].append(row)
        save(f / "verified-arm.json", row)
        print(role, "PASS", entry["all_ns"], entry["served"], flush=True)
        need(
            time.monotonic() - start < 1600 and B["measure"].file_bytes(out) < 512 << 20,
            "family resources",
        )
    report["grade"] = grade(report["arms"])
    report["status"] = "MEASURED"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    live = sub.add_parser("run")
    for k in ("previous", "images", "window", "new-output-dir"):
        live.add_argument("--" + k, required=True, type=lambda s: Path(s).resolve())
    for k in ("commit", "images-sha256", "window-sha256"):
        live.add_argument("--" + k, required=True)
    check = sub.add_parser("check")
    check.add_argument("grade", type=Path)
    a = p.parse_args()
    if a.action == "check":
        r = read(a.grade)
        need(grade(r["rows"]) == r, "public numerical grade")
        print(r["status"], r["paired"])
    else:
        os.umask(0o077)
        out = a.new_output_dir
        out.mkdir()
        result = dict(status="FAIL_PRESERVED")
        start = time.monotonic()
        try:
            with (out.parent / "tesy-verifier-wait.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                run(a, out, result)
        except Exception as exc:
            result.update(reason=str(exc), error_type=type(exc).__name__)
        result["elapsed_s"] = time.monotonic() - start
        save(out / "receipt.json", result)
        print(result["status"], result.get("reason", ""), flush=True)
        raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))

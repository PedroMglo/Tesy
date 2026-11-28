"""Run S and B1 on a live KV sequence with fully resident per-step shadow forwards."""

import argparse
import fcntl
import os
import re
import sys
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
C = run_path(HERE / "complete.py")
B, BASE, need, sha, read, checked, save = (
    C[k] for k in ("B", "BASE", "need", "sha", "read", "checked", "save")
)


def compare(new, old):
    need(
        new.keys() == old.keys() and all(new[k] == old[k] for k in ("kv", "anchor", "role")),
        "independent KV, anchor or role",
    )
    for n, o in zip(new["prefill"], old["prefill"], strict=True):
        need(n["size"] == o["size"] and n["counts"][:7] == o["counts"][:7], "prefill conservation")
    for n, o in zip(new["decode"], old["decode"], strict=True):
        need(
            set(n) == set(o) | {"hot"}
            and all(n[k] == o[k] for k in o if k not in ("counts", "wall_ns"))
            and n["counts"][:7] == o["counts"][:7],
            "ordinary graph, logits, route union or cache changed",
        )
        need(len(n["hot"]) == 2, "two live warm replays")
        for h in n["hot"]:
            c, w, loads, b, hits, m, p, s, sw = h["counts"]
            need(
                h["wall_ns"] > 0
                and c == 36
                and (w, loads, b, m, p, s, sw) == (0,) * 7
                and hits == sum(map(len, n["routes"])),
                "nonresident shadow",
            )


def run(cli, out, r):
    _, p, data = C["previous"](cli.previous)
    last = checked(cli.last / "receipt.json", cli.last_sha256)
    need(
        last["status"] == "MEASURED_INDEPENDENT_B0B" and last["previous_sha256"] == C["FAIL"],
        "numerical controls",
    )
    m = last["arms"][0]
    data["B0b"] = checked(
        cli.last / "B0b/raw" / (m["unit"] + ".capture/native.json"), m["native_sha256"]
    )
    a = C["settings"](p)
    a.unit, a.commit, a.prepare_only = out.name, cli.commit, False
    a.client, a.window, a.window_sha256 = cli.client, cli.window, cli.window_sha256
    git = B["prepare"].git
    head, tree = git(HERE, "rev-parse", "HEAD", "HEAD^{tree}").split()
    need(
        head == a.commit
        and not git(HERE, "status", "--porcelain")
        and re.fullmatch("tesy-verifier-hot-[a-z0-9-]+", a.unit),
        "clean measurement identity",
    )
    client = checked(a.client / "receipt.json", cli.client_sha256)
    work = read(a.client / "work.json")
    need(
        client["parent_sha256"] == p["client_sha256"]
        and client["protocol_sha256"]
        == work["hot_protocol_sha256"]
        == sha(HERE / "hot-protocol.md")
        and client["native_source_sha256"] == sha(HERE / "hot.cpp.in")
        and all(sha(a.client / k) == v for k, v in client["files"].items()),
        "hot client",
    )
    BASE["G"]["verify"](data, work)
    build = checked(a.build_dir / "receipt.json", BASE["T"]["BUILD"])
    prior = checked(a.template / "receipt.json", BASE["PREVIOUS"])
    policy, model_id = C["admission"](a)
    r.update(commit=head, tree=tree, base_sha256=C["FAIL"], last_sha256=cli.last_sha256, arms=[])
    save(
        out / "provenance.json",
        dict(
            args=sys.argv,
            commit=head,
            tree=tree,
            protocol_sha256=sha(HERE / "hot-protocol.md"),
            source_sha256={
                k: sha(HERE / k)
                for k in (
                    "hot_run.py",
                    "hot_build.py",
                    "hot.cpp.in",
                    "run.py",
                    "grade.py",
                    "complete.py",
                )
            },
            client_sha256=cli.client_sha256,
            c55_sha256=cli.window_sha256,
            base_sha256=C["FAIL"],
            last_sha256=cli.last_sha256,
        ),
    )
    start = time.monotonic()
    for role in ("S", "B1"):
        r["stage"] = role
        receipt = BASE["arm"](a, out / role, role, client, build, policy, model_id, prior)
        r["arms"].append(receipt)
        actual = checked(
            out / role / "raw" / (receipt["unit"] + ".capture/native.json"),
            receipt["native_sha256"],
        )
        compare(actual, data[role])
        BASE["G"]["verify"](data | {role: actual}, work)
        need(
            time.monotonic() - start < 720 and B["measure"].file_bytes(out / role) < 128 << 20,
            "shadow family budget",
        )
        print(role, "PASS_HOT_REPLAYS", flush=True)
    r["status"] = "MEASURED_LIVE_HOT_SHADOWS"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("previous", "last", "window", "client", "new-output-dir"):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    for k in ("commit", "window-sha256", "last-sha256", "client-sha256"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    r = dict(status="FAIL_PRESERVED")
    start = time.monotonic()
    try:
        with (out.parent / "tesy-verifier-wait.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(a, out, r)
    except Exception as exc:
        r.update(reason=str(exc), error_type=type(exc).__name__)
    r["elapsed_s"] = time.monotonic() - start
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""), flush=True)
    raise SystemExit(int(r["status"] == "FAIL_PRESERVED"))

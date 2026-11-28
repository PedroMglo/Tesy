"""Measure the absent B0b in a new scope and verify it against the three closed arms."""

import argparse
import fcntl
import os
import re
import sys
import time
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
BASE = run_path(HERE / "run.py")
B, need, sha, read, checked, save = (
    BASE[k] for k in ("B", "need", "sha", "read", "checked", "save")
)
FAIL = "c69fe1571f358f000b06145b35ef91a0d3b2fecd7b0d50d5499f3c8345bb475c"
PROVENANCE = "c6fbe71166759899b2f4535d34814d045183993f51e1cdb5010124b1e5a5c589"


def previous(path):
    r = checked(path / "receipt.json", FAIL)
    p = checked(path / "provenance.json", PROVENANCE)
    failed = path / "B0b"
    need(
        r["status"] == "FAIL_PRESERVED"
        and r["stage"] == "B0b"
        and [v["role"] for v in r["arms"]] == ["S", "B0a", "B1"]
        and "start inventory cadence gap" in (failed / "scope.log").read_text()
        and not list((failed / "raw").glob("*.launch.json"))
        and not list((failed / "raw").glob("*.capture")),
        "scope of original failure",
    )
    data = {}
    for v in r["arms"]:
        role, unit = v["role"], v["unit"]
        data[role] = checked(
            path / role / "raw" / (unit + ".capture/native.json"), v["native_sha256"]
        )
    return r, p, data


def settings(p):
    fields = dict(zip(p["args"][1::2], p["args"][2::2], strict=True))
    return SimpleNamespace(
        **{
            k: Path(fields["--" + k.replace("_", "-")])
            for k in (
                "archive",
                "derived",
                "client",
                "build_dir",
                "rows",
                "template",
                "loader_probe",
            )
        }
    )


def admission(a):
    win = checked(a.window / "receipt.json", a.window_sha256)
    need(
        win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not win["reason"]
        and win["span_s"] >= 60
        and win["window_sha256"] == sha(a.window / "samples.jsonl"),
        "complete C55",
    )
    return B["PLACE"](a.window, a.archive / "part-01/placement/r1/receipt.json")


def run(cli, out, result):
    _, p, data = previous(cli.previous)
    a = settings(p)
    a.unit, a.commit, a.prepare_only = out.name, cli.commit, False
    a.window, a.window_sha256 = cli.window, cli.window_sha256
    git = B["prepare"].git
    head, tree = git(HERE, "rev-parse", "HEAD", "HEAD^{tree}").split()
    need(
        head == a.commit
        and not git(HERE, "status", "--porcelain")
        and re.fullmatch("tesy-verifier-wait-[a-z0-9-]+", a.unit),
        "clean physical identity",
    )
    need(all(sha(HERE / k) == v for k, v in p["source_sha256"].items()), "unchanged probe")
    client = checked(a.client / "receipt.json", p["client_sha256"])
    need(all(sha(a.client / k) == v for k, v in client["files"].items()), "client closure")
    build = checked(a.build_dir / "receipt.json", BASE["T"]["BUILD"])
    prior = checked(a.template / "receipt.json", BASE["PREVIOUS"])
    policy, model_id = admission(a)
    work = read(a.client / "work.json")
    BASE["G"]["verify"](data, work)
    result.update(previous_sha256=FAIL, commit=head, tree=tree, unit=a.unit, arms=[])
    save(
        out / "provenance.json",
        dict(
            args=sys.argv,
            previous_sha256=FAIL,
            previous_provenance=PROVENANCE,
            commit=head,
            tree=tree,
            client_sha256=p["client_sha256"],
            window_sha256=a.window_sha256,
            protocol_sha256=sha(HERE / "completion.md"),
            source_sha256=sha(HERE / "complete.py"),
        ),
    )
    v = BASE["arm"](a, out / "B0b", "B0b", client, build, policy, model_id, prior)
    result["arms"].append(v)
    data["B0b"] = checked(
        out / "B0b/raw" / (v["unit"] + ".capture/native.json"), v["native_sha256"]
    )
    BASE["G"]["verify"](data, work)
    result["status"] = "MEASURED_INDEPENDENT_B0B"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("previous", "window", "new-output-dir"):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--window-sha256", required=True)
    a = p.parse_args()
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

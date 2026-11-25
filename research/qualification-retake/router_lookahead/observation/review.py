"""Reproduce the clocked join and the OFF witness from a sealed model-free family."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
grade = run_path(HERE / "audit.py")
need = grade["check"]


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def replay(folder, digest):
    need(sha(folder / "receipt.json") == digest, "native receipt")
    record = json.loads((folder / "receipt.json").read_bytes())
    need(record["status"] == "PASS_OBSERVATION_FIXTURE_ONLY", "completed family")
    left, right = [folder / mode / "native.json" for mode in ("OFF", "ON")]
    journal = folder / "ON/journal.bin"
    need(
        sha(left) == sha(right) == record["native_sha256"]
        and sha(journal) == record["journal_sha256"]
        and not (folder / "OFF/journal.bin").exists(),
        "arm identities",
    )
    audit = grade["audit"](journal)
    native = json.loads(left.read_bytes())
    need(
        hashlib.sha256(json.dumps(native["rows"], separators=(",", ":")).encode()).hexdigest()
        == audit["official_rows_sha256"]
        and audit["service"]["jobs"] == native["misses"]
        and sum(audit["state_at_lookup"].values()) == native["misses"] + native["hits"]
        and sha(folder / "audit.json") == record["audit_sha256"]
        and audit == json.loads((folder / "audit.json").read_bytes()),
        "independent journal and OFF rows",
    )
    return {
        "status": "REPRODUCED_ROUTER_OBSERVATION_FIXTURE",
        "family_sha256": digest,
        "commit": record["commit"],
        "source_pin": record["source_pin"],
        "sources": record["sources"],
        "wall_s": record["wall_s"],
        "native_sha256": sha(left),
        "before": record["before"],
        "after": record["resource_after"],
        "audit": audit,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = replay(a.family, a.family_sha256)
    except Exception as e:
        r = {"status": "FAIL_PRESERVED", "reason": f"{type(e).__name__}: {e}"}
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(int(r["status"] == "FAIL_PRESERVED"))

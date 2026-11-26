"""Reopen the sealed attempts and independently grade the causal proposals on the original IDs."""

import argparse
import json
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
F = run_path(str(HERE / "run.py"))
PINS = (
    "4739bee278713602e6481cbf6c932c5b01d7c82afcda8e9e593f7f3ff6d85931",
    "ac68f63e9f7ac5938c5bf56645ff563444d65c3ad8f0bdd2d69013d616bc20fa",
    "51644c12d221fd72e6e36bec6000ed3f3cbda2b63d1154a8cfd97bb99fe9d570",
)


def review(attempts, inputs):
    data = F["inputs"](SimpleNamespace(capture=inputs[0], verified=inputs[1]))
    cases = []
    for i, (folder, pin) in enumerate(zip(attempts, PINS, strict=True)):
        r = F["GRAPH"]["read"](folder / "receipt.json", pin)
        files = {p.name: F["sha"](p) for p in folder.iterdir() if p.name != "receipt.json"}
        F["need"](files == r["files"] and r["model_starts"] == r["generation_requests"] == 0, "raw")
        if i < 2:
            F["need"](r["status"] == "FAIL_PRESERVED", "missing failure")
        elif r["status"] == "GO_CAUSAL_SERVER_PLAN":
            F["need"](
                r["protocol_sha256"] == F["METHOD"] and r["physical_sha256"] == F["GATE"], "gate"
            )
            for j in range(2):
                F["need"](
                    F["sha"](folder / f"r{j}.stdout") == r["same_output_sha256"]
                    and "PLAN_CONFIG none,ngram-simple max=2"
                    in (folder / f"r{j}.stderr").read_text(),
                    "native dispatcher",
                )
                trace = json.loads((folder / f"r{j}.stdout").read_bytes())
                F["need"](trace.keys() == data.keys(), "cases")
                counts = {k: F["validate"](trace[k], v) for k, v in data.items()}
                F["need"](counts == r["turns"], "independent count")
        else:
            raise ValueError("unqualified third attempt")
        cases.append(
            dict(commit=r.get("commit"), receipt_sha256=pin, status=r["status"], wall_s=r["wall_s"])
        )
    return dict(
        status="REPRODUCED_CAUSAL_SERVER_PLAN",
        attempts=cases,
        protocol_sha256=F["METHOD"],
        physical_sha256=F["GATE"],
        turns=counts,
        journal_sha256=r["same_output_sha256"],
        model_starts=0,
        generation_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--attempts", nargs=3, type=Path, required=True)
    p.add_argument("--capture", type=Path, required=True)
    p.add_argument("--verified", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    F["save"](a.new_output_dir / "result.json", review(a.attempts, [a.capture, a.verified]))

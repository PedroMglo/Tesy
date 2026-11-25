"""Reopen the CPU providers, resource receipt and graphs without accessing weights."""

import argparse
import hashlib
import json
import os
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
G = runpy.run_path(str(HERE / "grade.py"))
need = G["need"]
GOLD = "bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24"


def sha(file):
    with file.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(file, digest):
    need(sha(file) == digest, "receipt changed: " + file.name)
    return json.loads(file.read_bytes())


def review(raw, digest, build):
    receipt = read(raw / "receipt.json", digest)
    detail = read(raw / "detail.json", receipt["detail_sha256"])
    built = read(build / "receipt.json", detail["build_sha256"])
    need(built["status"] == "PASS_C266_RESIDENT_TEAM_BUILD", "build status")
    for name, h in built["executables"].items():
        need(sha(build / name) == h, "executable")
    need(sha(build / "smoke-check.log") == built["small_ggml_sha256"], "synthetic gate")
    checks = []
    for idx, saved in enumerate(detail["arms"]):
        dest = raw / f"{idx:02d}-{saved['team']}"
        need(json.loads((dest / "receipt.json").read_text()) == saved, "arm not bound")
        for k in ("stdout", "stderr", "native/tile.f32"):
            if k + "_sha256" in saved:
                need(sha(dest / k) == saved[k + "_sha256"], "raw changed")
        if saved["status"] != "PASS_ARM":
            continue
        need(
            saved["returncode"] == 0 and sha(dest / "native/tile.f32") == GOLD, "gold tile or exit"
        )
        row = json.loads((dest / "stdout").read_bytes())
        for k, n in (("cpu", "libggml-cpu.so.0.15.3"), ("base", "libggml-base.so.0.15.3")):
            need(
                Path(row["providers"][k]).name == n
                and sha(Path(row["providers"][k])) == built["libs"][n],
                "CPU DSOs",
            )
        grade = G["verify"](row, saved["team"], saved["stock"], row["providers"])
        need(all(json.loads(json.dumps(v)) == saved[k] for k, v in grade.items()), "arm summary")
        checks.append(grade)
    result = dict(
        physical_sha256=digest,
        build_sha256=detail["build_sha256"],
        c55_sha256=detail.get("c55_sha256"),
        input_sha256=detail.get("input_sha256"),
        c118=detail.get("c118", {}),
        scope_rc=receipt["scope_rc"],
        child_statuses=[(x["team"], x["status"], x.get("returncode")) for x in detail["arms"]],
    )
    if receipt["status"] == "FAIL_PRESERVED":
        return result | dict(status="REOPENED_FAILED_RESIDENT_TEAM", reason=detail.get("reason"))
    need(
        receipt["scope_rc"] == 0
        and receipt["status"] == detail["status"] == "PASS_C266_RESIDENT_TEAM_FAMILY"
        and detail["swap_peak_bytes"] == detail["children_after_cleanup"] == 0
        and detail["peak_bytes"] < (3584 << 20)
        and sha(raw / "raw/samples.jsonl") == detail["monitors_sha256"],
        "scope or telemetry",
    )
    d = G["decision"](checks)
    need(d == receipt["assessment"] == detail["assessment"], "terminal decision")
    return result | dict(
        status="REPRODUCED_RESIDENT_TEAM",
        assessment=d,
        peak_bytes=detail["peak_bytes"],
        swap_peak_bytes=detail["swap_peak_bytes"],
        monitor_samples=detail["monitor_samples"],
        per_process=[
            dict(
                team=a["team"],
                stock=a["stock"],
                off_ms=a["off_median_ns"] / 1e6,
                on_ms=(a["on_median_ns"] / 1e6 if a["on_median_ns"] else None),
                wall_ms=[x["wall_ns"] / 1e6 for x in a["iterations"]],
                observed_mmids=[
                    {
                        k: v
                        for k, v in x.items()
                        if k.endswith("_ns") or k == "different_cpu_endpoints"
                    }
                    for x in a["iterations"]
                    if "mmid_union_ns" in x
                ],
            )
            for a in checks
        ],
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("physical", "build", "new-output-dir"):
        ap.add_argument("--" + k, type=Path, required=True)
    ap.add_argument("--physical-sha256", required=True)
    a = ap.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    out = review(a.physical, a.physical_sha256, a.build)
    (a.new_output_dir / "receipt.json").write_text(json.dumps(out, sort_keys=True, indent=2) + "\n")
    print(out["status"], out.get("assessment", {}).get("status"))

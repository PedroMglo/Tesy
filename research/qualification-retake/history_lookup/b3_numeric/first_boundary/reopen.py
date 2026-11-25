"""Regrade a completed pair offline from its preserved raw tree and both archived controls."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grade  # noqa: E402

need, sha = grade.need, grade.sha


def read(path):
    return json.loads(path.read_bytes())


def reopen(family, expected, archived):
    need(sha(family / "receipt.json") == expected, "terminal family receipt")
    r = read(family / "receipt.json")
    need(
        r["status"] in ("DIFFERENT_AT_OBSERVED_CUT", "EQUAL_THROUGH_OBSERVED_CUTS"),
        "family stopped before comparison",
    )
    need(grade.historical(archived) == r["archived_witnesses"], "old controls")
    sources, arms = {}, {}
    for mode in ("AR", "B3"):
        root = family / mode
        arm_path = root / "receipt.json"
        need(sha(arm_path) == r["arms"][mode]["receipt_sha256"], "arm receipt digest")
        arm = read(arm_path)
        unit = arm["unit"]
        need(
            arm["status"] == "PASS_NUMERIC_ARM_" + mode
            and arm["model_launch_receipts"] == 1
            and unit == Path(unit).name,
            "measured arm",
        )
        raw = root / "raw"
        sources[mode] = cap = raw / (unit + ".capture")
        for path, field in [
            (raw / (unit + ".json"), "monitor_sha256"),
            (raw / (unit + ".launch.json"), "launch_sha256"),
            (raw / (unit + ".start-inventory.jsonl"), "c118_sha256"),
            (root / "loader-audit.json", "loader_audit_sha256"),
        ]:
            need(sha(path) == arm[field], "physical witness " + field)
        need(
            grade.bridge(cap, mode) == arm["same_mode_off"] and arm["same_mode_off"]["bitwise"],
            "new-to-OFF bridge",
        )
        need(grade.check_arm(cap, mode) == arm["coverage"], "geometry and all cuts")
        # All 2,248 numerical prefill witnesses were compared to independent C127 in the child.
        # Reproduce the sealed aggregate, including every name, byte count and file SHA.
        import hashlib

        h = hashlib.sha256()
        n = total = 0
        for path in sorted(cap.glob("prefill*")):
            size = path.stat().st_size
            h.update(
                path.name.encode() + b"\0" + str(size).encode() + b"\0" + bytes.fromhex(sha(path))
            )
            total += size
            n += 1
        need(
            dict(files=n, bytes=total, ordered_name_size_digest_sha256=h.hexdigest())
            == arm["grade"]["prefix"]
            == grade.old_rows()[mode]["prefix"],
            "full prefill",
        )
        arms[mode] = dict(
            receipt_sha256=sha(arm_path),
            scope_wall_s=arm["scope_wall_s"],
            native_elapsed_s=arm["native_elapsed_s"],
            c118_sha256=arm["c118_sha256"],
            raw_bytes=arm["raw_bytes"],
            maxima=arm["maxima"],
            off=arm["same_mode_off"],
            payloads=arm["coverage"]["payloads"],
            cut_bytes=arm["coverage"]["bytes"],
            geometry_sha256=arm["coverage"]["geometry_sha256"],
        )
    res = grade.compare(sources["AR"], sources["B3"])
    need(
        res == read(family / "comparison.json")
        and sha(family / "comparison.json") == r["comparison_sha256"]
        and res["status"] == r["status"]
        and res["first"] == r["first"]
        and res["per_position"] == r["per_position"],
        "comparison reproduction",
    )
    by_layer = {}
    for row in res["comparisons"]:
        x = by_layer.setdefault(
            row["layer"], {"different_rows": 0, "rows": 0, "changed_words": 0, "words": 0}
        )
        x["rows"] += 1
        x["different_rows"] += int(row["changed_words"] != 0)
        x["changed_words"] += row["changed_words"]
        x["words"] += row["words"]
    return dict(
        status="REPRODUCED_" + res["status"],
        arms=arms,
        layers=by_layer,
        first=res["first"],
        per_position=res["per_position"],
        historical_sha256=grade.OFF_FAMILY,
        comparison_sha256=r["comparison_sha256"],
        build_sha256=r["build_sha256"],
        binary_sha256=r["binary_sha256"],
        measurement_commit=r["measurement_commit"],
        c55_sha256=r["c55_sha256"],
        measured_family_sha256=expected,
        family_wall_s=r["wall_s"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("family", "archived-family", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        receipt = reopen(a.family, a.family_sha256, a.archived_family)
    except Exception as exc:
        receipt = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(receipt["status"])
    raise SystemExit(int(receipt["status"] == "FAIL_PRESERVED"))

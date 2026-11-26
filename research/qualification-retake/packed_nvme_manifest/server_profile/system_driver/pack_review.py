"""Regrade the two sealed captures, their resource monitors and the contemporary C269 reference."""

import argparse
import subprocess
import sys
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(str(HERE / "pack_numeric.py"))
R = run_path(str(HERE / "review.py"))
need, read, sha, save, grade = (P[k] for k in ("need", "read", "sha", "save", "grade"))
FAMILY = "b21feeadd304d87974e7cc6a174ee5291a91b70258ed2a331ecd22c01d4f4431"


def review(pair, reference, out):
    r = R["reopen"](pair, FAMILY)
    c = R["reopen"](reference, P["REFERENCE"])
    need(
        c["status"] == "GO_C269_CURRENT_C127"
        and r["reference_sha256"] == P["REFERENCE"]
        and r["status"] == "PASS_C292_OFF_ON_SELECTED"
        and r["model_starts"] == 2
        and r["generation_requests"] == 0
        and sha(HERE / "pack_numeric.py") == r["implementation_sha256"]
        and sha(HERE / "pack-protocol.md") == r["protocol_sha256"],
        "sealed family and source",
    )
    ref = reference / "raw" / (c["unit"] + ".capture")
    ref_tree = grade.tree_digest(ref)
    need(ref_tree == grade.anchors()["gold"], "reference differs from independent C127")
    detail, caps = {}, []
    end = None
    for mode in ("OFF", "ON"):
        arm = pair / mode
        unit = r["unit"] + "-" + mode.lower()
        prefix = arm / "raw" / unit
        manifest = read(prefix.with_suffix(".json"))
        launch = read(prefix.with_suffix(".launch.json"))
        protocol = read(arm / "resource-store.json")
        expected = read(arm / "pack-argv.json")["expected"]
        P["PK"]["validate_monitor"](manifest, expected, protocol)
        row = r["arms"][mode]
        inv = P["PK"]["compact"].validate_inventory(
            arm, unit, {"native_explicit_env": expected}, launch
        )
        start = launch["start_inventory"]["popen_invoked_utc"]
        need(
            inv == row["c118"]
            and row["scope_cleanup"]
            and manifest["process_identity"] == launch["process_identity"]
            and sha(arm / "resource-store.json")
            == launch["resource_protocol_sha256"]
            == manifest["limits"]["resource_protocol_sha256"]
            and row["maxima"] == manifest["maxima"]
            and (P["live"].STORE_ENV in expected) == (mode == "ON")
            and (end is None or end < start),
            "identity, resource monitor or arm order",
        )
        end = manifest["ended_utc"]
        capture = prefix.with_suffix(".capture")
        checked = out / (mode + "-c127.json")
        subprocess.run(
            [
                sys.executable,
                "-B",
                str(P["REPO"] / "tools/block_layer_reuse_gate.py"),
                capture,
                "--bridge-reference",
                ref,
                "--output",
                checked,
            ],
            capture_output=True,
            check=True,
            timeout=45,
        )
        bridge = read(checked)
        P["measure"].check_gate(bridge)
        numeric = grade.check_arm(capture, prefix.with_suffix(".stdout"), ref, bridge)
        need(
            sha(checked) == row["c127_sha256"]
            and numeric == read(arm / "numerical.json")
            and sha(arm / "numerical.json") == row["numerical_sha256"],
            "independent C127 or C292 result",
        )
        detail[mode] = dict(
            native=numeric["native"],
            captured_tree=numeric["c292"]["capture"],
            complete_tree_equals_C127=numeric["c292"]["capture"] == ref_tree,
            c127_sha256=sha(checked),
            numerical_sha256=row["numerical_sha256"],
            monitor_sha256=sha(prefix.with_suffix(".json")),
            resource_maxima=manifest["maxima"],
            gpu_energy=R["power"](arm, dict(unit=unit)),
            inventory=inv,
            model_s=manifest["elapsed_s"],
            scope_including_inventory_s=row["scope_s"],
            c55_age_s=row["c55_age_at_spawn_s"],
            live_map_samples=row["live_samples"],
            live_pack_fd=row["pack_fd"],
            native_initialized_sha256=row["loader"]["initialized"],
        )
        caps.append(capture)
    joined = grade.check_pair(*caps)
    need(
        joined == read(pair / "pair.json") and sha(pair / "pair.json") == r["pair_sha256"],
        "independent OFF/ON pair",
    )
    return dict(
        status=joined["status"],
        commit=r["commit"],
        tree=r["tree"],
        family_sha256=FAMILY,
        reference_sha256=P["REFERENCE"],
        model_sha256=c["model_sha256"],
        driver=c["kernel"],
        window_sha256=r["window_sha256"],
        full_logits=joined["c292"]["logit_sha256"],
        core_payloads=joined["c292"]["core_payloads"],
        numeric_states=joined["c292"]["numeric_states"],
        masked_states=joined["c292"]["masked_states"],
        arms=detail,
        model_starts=2,
        generation_requests=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("pair", "reference", "new-output-dir"):
        parser.add_argument("--" + arg, required=True, type=Path)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    report = review(args.pair, args.reference, args.new_output_dir)
    save(args.new_output_dir / "pack-result.json", report)
    print(report["status"])

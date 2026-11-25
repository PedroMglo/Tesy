"""Reopen all three observed C292 outputs and numerical, loader, FD and resource evidence."""

import argparse
import json
import os
from pathlib import Path
from runpy import run_path

p = run_path(str(Path(__file__).with_name("profile.py")))
prior = p["mod"](p["CAPTURE"] / "report.py", "archived_c292_reviewer")
grade, need, sha = p["grade"], p["need"], p["sha"]
sealed = grade.read


def review(a):
    family = sealed(a.family / "receipt.json", a.family_sha256)
    failed = sealed(a.failed_family / "receipt.json", p["FAILED"])
    fd_obs = sealed(a.control_fds / "receipt.json", p["LIVE_CONTROL"])
    need(
        family["status"] == "PASS_C292_PACK_OBSERVER_NUMERIC"
        and family["libraries"] == p["LIBS"]
        and family["build_receipt_sha256"] == p["BUILD"]
        and family["model_launch_receipts"] == 2
        and family["revalidated_prior_launch_receipts"] == 1
        and set(family["arms"]) == set(p["MODES"])
        and family["unexecuted_arms"] == []
        and failed["model_launch_receipts"] == 1
        and failed["status"] == "FAIL_PRESERVED"
        and sha(a.control_fds / "samples.jsonl") == fd_obs["sample_sha256"],
        "physical terminal coverage",
    )
    build = sealed(a.build_dir / "receipt.json", p["BUILD"])
    gold = grade.reference(a.r0_dir)
    original = p["original"](a.original_family, gold)
    rows = {}
    pids = []
    for mode in p["MODES"]:
        saved = a.family / mode
        old = mode == "control_off"
        directory = (a.failed_family / mode) if old else saved
        raw = directory / "raw"
        binding = family["arms"][mode]
        r = sealed(saved / "receipt.json", binding["receipt_sha256"])
        need(
            r["capture_tree"] == binding["capture_tree"] == original
            and r["cleanup"]
            and r["model_launch_receipts"] == int(not old),
            "capture or launch accounting",
        )
        unit = r["unit"]
        m = sealed(raw / (unit + ".json"), r["monitor_sha256"])
        launch = sealed(raw / (unit + ".launch.json"), r["launch_sha256"])
        spec = sealed(directory / "argv-observer.json", r["contract_sha256"])
        pro = sealed(directory / "resource-store.json", spec["resource_sha256"])
        pid = launch["process_identity"]["pid"]
        pids.append(pid)
        need(
            pro["pinned"]["capture_sha256"] == p["live"].static.CAPTURE
            and spec["resource_sha256"]
            == m["limits"]["resource_protocol_sha256"]
            == launch["resource_protocol_sha256"]
            and m["process_identity"] == launch["process_identity"]
            and r["loader"]["native_pid"] == pid
            and m["returncode"] == 0
            and m["stop_reason"] is None
            and m["maxima"] == r["maxima"]
            and m["maxima"]["swap_bytes"] == 0
            and m["maxima"]["direct_model_fds"] > 0
            and m["explicit_env"] == spec["explicit_env"]
            and p["TRIGGER"] not in m["relevant_environment"]
            and (p["FILE"] in m["relevant_environment"]) == (mode == "overlay_on")
            and set(m["output_sha256"]) == {".stderr", ".stdout", ".samples.jsonl"}
            and all(sha(raw / (unit + suffix)) == d for suffix, d in m["output_sha256"].items()),
            "live process",
        )
        env = {k: v for k, v in spec["explicit_env"].items() if k != p["FILE"]}
        p["base"].validate_monitor(m | {"explicit_env": env}, env, pro)
        c118 = p["base"].compact.validate_inventory(
            directory, unit, {"native_explicit_env": env}, launch
        )
        need(c118 == r["c118"] and 0 <= r["c55_age_at_spawn_s"] < 55 * 60, "C55/C118")
        ctl = {
            "startup": build["control_capture_startup" if old else "capture_startup"],
            "explicit_search": build["control_explicit_search" if old else "explicit_search"],
        }
        ld = prior.loader(r["loader"], directory, ctl, a.preflight_dir)
        image = ctl["startup"][p["live"].static.SONAME]
        need(
            ld["startup_count"] == 18
            and ld["initialized_sha256"][Path(image["file"]).name]
            == image["sha256"]
            == binding["image_sha256"]
            == r["image_sha256"],
            "independent loader closure",
        )
        fd = r["pack"]
        need(
            fd["model_and_pack_stat_verified"]
            and fd["store_environment_verified"]
            and 0 < fd["positive_samples"] <= r["live_samples"]
            and len(fd["fd_and_flags"]) == 1
            and fd["fd_and_flags"][0][1] & os.O_DIRECT
            and fd["fd_and_flags"][0][1] & os.O_ACCMODE == os.O_RDONLY,
            "live direct pack",
        )
        if old:
            need(
                fd == fd_obs["pack"]
                and launch["process_identity"] == fd_obs["process_identity"]
                and r["live_fd_sha256"] == p["LIVE_CONTROL"]
                and r["r01_family_sha256"] == p["FAILED"]
                and r["launch_sha256"] == fd_obs["launch_sha256"],
                "independent live witness",
            )
        phase = p["inspect_journal"](
            raw / "phase.pfj1", mode == "overlay_on", spec["pack_stat"], spec["model_stat"]
        )
        need(phase == r["journal"], "journal conservation")
        q = grade.check_arm(
            raw / (unit + ".capture"),
            raw / (unit + ".stdout"),
            gold,
            sealed(saved / "selected.json", r["c127_sha256"]),
        )
        need(
            q == sealed(saved / "numerical.json", r["numerical_sha256"])
            and q["c292"]["capture"] == original,
            "completed numerical equality",
        )
        rows[mode] = {
            "processes": 1,
            "image_sha256": image["sha256"],
            "startup_count": ld["startup_count"],
            "loader_objects": ld["objects"],
            "positive_pack_samples": fd["positive_samples"],
            "c118_s": c118["s"],
            "model_s": m["elapsed_s"],
            "maxima": m["maxima"],
            "scope_wall_s": r["scoped_wall_s"],
            "boundaries": q["c292"]["core_payloads"],
            "full_logits": q["c292"]["full_logits"],
            "witness": q["c292"]["prospective_witness"],
            "numerical_sha256": r["numerical_sha256"],
            "capture_tree": original,
            "journal": phase,
        }
    need(len(set(pids)) == 3, "duplicate PID")
    return {
        "status": "REPRODUCED_C292_PACK_OBSERVER_NUMERIC",
        "arms": rows,
        "family_sha256": a.family_sha256,
        "build_sha256": p["BUILD"],
        "failed_family_sha256": p["FAILED"],
        "live_control_sha256": p["LIVE_CONTROL"],
        "gold_receipt_sha256": grade.R0,
        "original_family_sha256": p["FAMILY"],
        "model_launches_by_reviewer": 0,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in (
        "family",
        "build-dir",
        "failed-family",
        "control-fds",
        "preflight-dir",
        "r0-dir",
        "original-family",
        "new-output-dir",
    ):
        ap.add_argument("--" + key, type=Path, required=True)
    ap.add_argument("--family-sha256", required=True)
    a = ap.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        r = review(a)
    except Exception as exc:
        r = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(r, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

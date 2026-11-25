"""Rebuild a terminal C292 report from archived files, without opening weights or using CUDA."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grade  # noqa: E402

_spec = importlib.util.spec_from_file_location("physical_c292_profile", HERE / "profile.py")
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

need, sha, read = grade.need, grade.digest, grade.read
PREP = "dc568982a389b69fd2bfbc453f5aabb6c3876912b98e16a56a001df2f798b3c2"
MODES = ("OFF", "ON")
SUCCESS = "PASS_SELECTED_C292_NVME_PAIR"


def phases(terminal):
    status = terminal["status"]
    need(status in (SUCCESS, "FAIL_PRESERVED"), "physical family needs terminal receipt")
    arms = terminal["arms"]
    names = [a["mode"] for a in arms]
    need(
        names == list(MODES[: len(names)])
        and terminal["unexecuted_arms"] == list(MODES[len(names) :]),
        "arm sequence or terminal accounting",
    )
    for i, (name, arm) in enumerate(zip(names, arms, strict=True)):
        passed = arm["status"] == "PASS_C292_" + name
        need(
            passed
            or (
                arm["status"] == "FAIL_PRESERVED"
                and i == len(arms) - 1
                and status == "FAIL_PRESERVED"
            ),
            "attempted child after failed gate",
        )
    if status == SUCCESS:
        need(
            names == list(MODES)
            and terminal["model_launch_receipts"] == 2
            and len(terminal["pair_sha256"]) == 64,
            "incomplete physical pair",
        )
    return arms


def preparatory(root):
    f = read(root / "receipt.json", PREP)
    need(
        f["status"] == "PREPARED_ONLY"
        and f["model_launch_receipts"] == 0
        and [r["mode"] for r in f["arms"]] == list(MODES),
        "prepared family identity",
    )
    for row in f["arms"]:
        p = read(root / row["mode"] / "receipt.json", row["receipt_sha256"])
        need(
            p["mode"] == row["mode"]
            and p["status"] == "PREPARED_ONLY"
            and p["model_launch_receipts"] == 0,
            "prepared child",
        )
    return f


def loader(j, directory, ctl, preflight):
    pre = read(preflight / "receipt.json", run.live.static.PREFLIGHT)
    static = read(preflight / "static-map.json", pre["static_map_sha256"])
    raw = (directory / "raw" / ("loader." + str(j["native_pid"]))).read_bytes()

    need(
        hashlib.sha256(raw).hexdigest() == j["loader_sha256"]
        and j["preflight_sha256"] == run.live.static.PREFLIGHT,
        "authenticated loader/authority",
    )
    text = raw.decode()
    cnt = 0
    for line in text.splitlines():
        if line.strip():
            m = re.match(r"\s*(\d+):", line)
            need(m and int(m[1]) == j["native_pid"], "foreign loader PID")
            cnt += 1
    need(cnt > 0, "empty loader evidence")
    package = run.Q / "nvme_r0_gate/driver_pair"
    parser = run.live.linkage.load_module(package / "compact_mixed.py", "safe_archive_loader")
    origin = run.live.linkage.load_module(package / "driver_origin.py", "driver_r02_number")
    links = dict(static["arms"]["C270"]["links"])
    candidate = ctl["startup"][run.live.static.SONAME]
    images = static["files"] | {candidate["file"]: {"sha256": candidate["sha256"]}}
    links[run.live.static.SONAME] = [
        str(Path(ctl["explicit_search"][0]) / run.live.static.SONAME),
        candidate["file"],
    ]
    loaded = parser.archived_initializers(
        text, j["native_pid"], links, static["driver_aliases"], images, j["initialized_sha256"]
    )
    startup = {p[1] for p in links.values()}
    searches = origin.all_requests(text, j["native_pid"])
    need(
        len(startup) == 18
        and startup <= loaded <= startup | set(static["driver_aliases"].values())
        and searches <= set(links) | set(static["driver_aliases"]) | {origin.ABSENT}
        and sorted(searches) == j["all_search_names"]
        and origin.validate_driver_log(
            origin.requests(text, j["native_pid"]),
            loaded,
            {k: Path(p) for k, p in static["driver_aliases"].items()},
        )
        == j["driver_providers"],
        "loader provider census",
    )
    return {
        "sha256": j["loader_sha256"],
        "initialized_sha256": j["initialized_sha256"],
        "drivers": j["driver_providers"],
        "startup_count": len(startup),
        "objects": len(loaded),
    }


def observed_failure(directory, receipt, unit):
    raw = directory / "raw"
    files = [p for p in raw.rglob("*") if p.is_file()] if raw.is_dir() else []
    launches = int((raw / (unit + ".launch.json")).is_file())
    need(launches == receipt["model_launch_receipts"], "incomplete failed launch evidence")
    return {
        "status": "FAIL_PRESERVED",
        "fidelity": receipt.get("fidelity"),
        "model_launch_receipts": launches,
        "raw_files": len(files),
        "raw_bytes": sum(p.stat().st_size for p in files),
        "observed_file_sha256": {
            kind: sha(raw / (unit + suffix))
            for kind, suffix in (
                ("launch", ".launch.json"),
                ("monitor", ".json"),
                ("stdout", ".stdout"),
                ("stderr", ".stderr"),
                ("samples", ".samples.jsonl"),
            )
            if (raw / (unit + suffix)).is_file()
        },
        "selected_grade_present": (directory / "selected.json").is_file(),
        "c292_grade_present": (directory / "numerical.json").is_file(),
    }


def arm(directory, binding, gold, a, terminal, ctl):
    mode = binding["mode"]
    r = read(directory / "receipt.json", binding["receipt_sha256"])
    unit = r["unit"]
    need(
        r["mode"] == mode
        and r["status"] == binding["status"]
        and re.fullmatch(r"[A-Za-z0-9_-]+", unit)
        and unit.endswith("-" + mode.lower()),
        "arm binding",
    )
    if r["status"] == "FAIL_PRESERVED":
        return observed_failure(directory, r, unit), None
    raw = directory / "raw"
    spec = read(directory / "store-argv.json", r["contract_sha256"])
    pro = read(directory / "resource-store.json", r["resource_sha256"])
    base = read(directory / "qualified-protocol.json", spec["control_sha256"])
    need(
        spec["mode"] == mode
        and spec["method_sha256"] == pro["method_sha256"] == run.METHOD
        and pro["metadata_sha256"] == run.live.DERIVED
        and spec["closure_sha256"] == pro["static_receipt_sha256"] == run.live.CLOSURE
        and spec["c55_sha256"] == terminal["c55_sha256"] == base["c55_sha256"]
        and spec["resource_sha256"] == r["resource_sha256"]
        and pro["pinned"]["capture_sha256"] == run.live.static.CAPTURE
        and pro["pinned"]["ids_sha256"] == grade.anchors()["ids_sha256"],
        "arm protocol",
    )
    m = read(raw / (unit + ".json"), r["monitor_sha256"])
    launch = read(raw / (unit + ".launch.json"), r["launch_sha256"])
    pid = launch["process_identity"]["pid"]
    need(
        launch["resource_protocol_sha256"]
        == r["resource_sha256"]
        == m["limits"]["resource_protocol_sha256"]
        and m["process_identity"] == launch["process_identity"]
        and r["loader"]["native_pid"] == pid
        and r["model_launch_receipts"] == 1
        and r["scope_cleanup"]
        and r["live_samples"] > 0
        and r["child_exit"] == m["returncode"] == 0
        and r["monitor_stop"] is None,
        "launch/cleanup",
    )
    env = spec["explicit"]
    need(
        (run.live.STORE_ENV in env) == (mode == "ON")
        and (mode == "OFF" or env[run.live.STORE_ENV] == ctl["manifest"]),
        "manifest mode changed",
    )
    run.validate_monitor(m, env, pro)
    need(
        set(m["output_sha256"]) == {".stdout", ".stderr", ".samples.jsonl"}
        and all(
            sha(raw / (unit + suffix)) == digest for suffix, digest in m["output_sha256"].items()
        ),
        "monitor output hashes",
    )
    inventory = run.compact.validate_inventory(
        directory, unit, {"native_explicit_env": env}, launch
    )
    need(
        inventory == r["c118"]
        and 0 <= r["c55_age_at_spawn_s"] < 3600
        and 0 <= inventory["age_at_spawn_s"] <= 3,
        "C118",
    )
    ld = loader(r["loader"], directory, ctl, a.preflight_dir)
    pack = r["pack"]
    fds = pack["fd_and_flags"]
    need(
        pack["model_and_pack_stat_verified"]
        and pack["store_environment_verified"]
        and len(fds) == int(mode == "ON")
        and 0 <= pack["positive_samples"] <= r["live_samples"]
        and bool(fds) == bool(pack["positive_samples"])
        and all(
            fd >= 0 and fl & os.O_DIRECT and fl & os.O_ACCMODE == os.O_RDONLY for fd, fl in fds
        ),
        "observed pack FD",
    )
    capture = raw / (unit + ".capture")
    selected = read(directory / "selected.json", r["c127_sha256"])
    saved = read(directory / "numerical.json", r["numerical_sha256"])
    rebuilt = grade.check_arm(capture, raw / (unit + ".stdout"), gold, selected)
    need(rebuilt == r["numerical"] == saved, "numerical grade does not replay")
    events = {k: m["cgroup_end"]["events"][k] - v for k, v in m["cgroup_start"]["events"].items()}
    need(
        r["maxima"] == m["maxima"]
        and not any(events[k] for k in ("oom", "oom_kill"))
        and m["maxima"]["direct_model_fds"] > 0
        and m["maxima"]["swap_bytes"] == 0
        and r["model_s"] == m["elapsed_s"]
        and run.measure.file_bytes(raw) == r["raw_bytes"],
        "integrity of resources",
    )
    return {
        "status": r["status"],
        "model_launch_receipts": 1,
        "measured_captures": 1,
        "c127_sha256": r["c127_sha256"],
        "numerical_sha256": r["numerical_sha256"],
        "monitor_sha256": r["monitor_sha256"],
        "launch_sha256": r["launch_sha256"],
        "resource_sha256": r["resource_sha256"],
        "contract_sha256": r["contract_sha256"],
        "output_sha256": m["output_sha256"],
        "numerical": saved,
        "pack": pack,
        "loader": ld,
        "live_samples": r["live_samples"],
        "c118": inventory,
        "c55_age_at_spawn_s": r["c55_age_at_spawn_s"],
        "model_s": r["model_s"],
        "scoped_wall_s": r["scoped_wall_s"],
        "raw_bytes": r["raw_bytes"],
        "maxima": r["maxima"],
        "cgroup_event_deltas": events,
        "scope_cleanup": True,
    }, capture


def audit(a):
    root = a.family
    terminal = read(root / "receipt.json", a.family_sha256)
    admitted = phases(terminal)
    prepared = preparatory(a.prepared)
    ctl = read(a.closure / "receipt.json", run.live.CLOSURE)
    need(
        ctl["status"] == "PASS_C292_CAPTURE_STATIC_CLOSURE"
        and ctl["derived_sha256"] == run.live.DERIVED
        and ctl["constructor_sha256"] == run.live.CONSTRUCTOR
        and ctl["library_sha256"] == run.live.static.C291
        and prepared["commit"] == terminal["commit"]
        and terminal["closure_sha256"] == run.live.CLOSURE,
        "family and closure identity",
    )
    gold = grade.reference(a.r0_dir)
    arms, caps = {}, {}
    for row in admitted:
        mode = row["mode"]
        arms[mode], caps[mode] = arm(root / mode, row, gold, a, terminal, ctl)
        arms[mode]["receipt_sha256"] = row["receipt_sha256"]
    for mode in terminal["unexecuted_arms"]:
        need(
            not (root / mode / "receipt.json").exists()
            and not list((root / mode / "raw").glob("*.launch.json")),
            "missing attempted arm",
        )
        arms[mode] = {"status": "NOT_RUN", "model_launch_receipts": 0, "measured_captures": 0}
    need(
        sum(r["model_launch_receipts"] for r in arms.values()) == terminal["model_launch_receipts"],
        "number of child launches",
    )
    result = {
        "status": terminal["status"],
        "arms": arms,
        "model_launch_receipts": terminal["model_launch_receipts"],
        "family_sha256": a.family_sha256,
        "family_wall_s": terminal["elapsed_s"],
        "commit": terminal["commit"],
        "prepared_sha256": PREP,
        "c55_sha256": terminal["c55_sha256"],
        "closure_sha256": run.live.CLOSURE,
        "derived_sha256": run.live.DERIVED,
        "constructor_sha256": run.live.CONSTRUCTOR,
        "libllama_sha256": run.live.static.C291,
        "binary_sha256": run.live.static.CAPTURE,
        "reference_receipt_sha256": grade.R0,
        "historical_store_protocol_sha256": run.live.static.C292,
    }
    if terminal["status"] == SUCCESS:
        expected = read(root / "pair.json", terminal["pair_sha256"])
        need(grade.check_pair(caps["OFF"], caps["ON"]) == expected, "direct pair does not replay")
        result["direct_grade"] = expected
        result["pair_sha256"] = terminal["pair_sha256"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("family", "prepared", "closure", "preflight-dir", "r0-dir", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--family-sha256", required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = audit(a)
    except Exception as exc:
        result = {"status": "FAIL_AUDIT", "reason": type(exc).__name__ + ": " + str(exc)}
    with (a.new_output_dir / "receipt.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(result["status"])
    return int(result["status"] == "FAIL_AUDIT")


if __name__ == "__main__":
    raise SystemExit(main())

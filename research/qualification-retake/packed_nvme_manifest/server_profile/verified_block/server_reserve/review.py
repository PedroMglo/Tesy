"""Verify sealed client, C55/C118, physical providers and numerical cuts without opening weights."""

import argparse
from datetime import datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = run_path(str(HERE / "family.py"))
C, RB, need, read, sha = (F[k] for k in ("C", "RB", "need", "read", "sha"))
R = RB["R"]
POOL = run_path(str(C["QUAL"] / "history_lookup/target_rollback/live_rollback/review.py"))


def controls(a):
    prior = R["reopen"](a.history, F["GRAPH"]["NUMERIC"])
    target = R["reopen"](a.target, RB["B"]["PARENT"])
    ar = R["reopen"](a.serial, RB["K"]["D"]["SERIAL"])
    return (
        RB["capture"](a.history, prior["unit"], "AR"),
        RB["capture"](a.target, target["unit"], "CUDA"),
        RB["F"]["targets"](a.serial, ar)["AR"],
    )


def audit(a, r, d, case, history, target, serial):
    root = a.family / case
    unit = r["unit"] + "-" + case.lower()
    out = root / "raw"
    image, reserve, mode = F["CASES"][case]
    m, launch = (read(out / (unit + s)) for s in (".json", ".launch.json"))
    cfg = read(root / "packed-resource.json")
    spec = read(root / "argv-packed.json")
    cmd, expected = spec["command"], spec["expected"]
    logged = {}
    i = cmd.index("--env")
    for j in range(i, cmd.index("--", i), 2):
        key, value = cmd[j + 1].split("=", 1)
        need(cmd[j] == "--env" and key not in logged, "unambiguous environment")
        logged[key] = value
    native = {
        k: v
        for k, v in expected.items()
        if k.startswith("TESY_") and k != "TESY_CPU_WAVE_SKIP_PARKED"
    }
    flags = RB["T"]["flags"]("CUDA")
    need(
        {k: v for k, v in native.items() if k in flags} == (flags if reserve == 3 else {})
        and native["TESY_TEST_OUTPUT_RESERVE"] == str(reserve)
        and Path(native[F["PK"]["live"].STORE_ENV]).name == "expert-store-runtime.json",
        "store/reserve/graph options",
    )
    need(
        expected == logged == m["explicit_env"]
        and all(m["relevant_environment"].get(k) == v for k, v in native.items())
        and m["command"] == cmd[-6:]
        and m["variant"] == "C291-packed-reserve-" + case
        and m["process_identity"] == launch["process_identity"]
        and m["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(root / "packed-resource.json"),
        "process provenance",
    )
    standard = {k: v for k, v in expected.items() if k not in native}
    F["PF"]["check_native_manifest"](
        dict(m, explicit_env=standard), cfg, cfg["pinned"], standard, F["measure"]
    )
    inv = F["PK"]["PK"]["compact"].validate_inventory(
        root, unit, {"native_explicit_env": expected}, launch
    )
    arm = r["arms"][case]
    need(
        arm["inventory"] == inv
        and arm["maxima"] == m["maxima"]
        and arm["scope_cleanup"]
        and arm["model_s"] == m["elapsed_s"]
        and arm["fd"]["positive_samples"] > 0
        and arm["fd"]["store_environment_verified"]
        and arm["fd"]["model_and_pack_stat_verified"]
        and len(arm["fd"]["fd_and_flags"]) == 1
        and arm["loader"]["initialized"][F["GRAPH"]["IMAGE"]]
        == d["arms"][image]["image_sha256"]
        == arm["image_sha256"]
        and cfg["pinned"]["capture_sha256"] == d["elf_sha256"]
        and cfg["output_reserve"] == reserve,
        "live pack and cap",
    )
    cap = F["capture"](a.family, r["unit"], case)
    control = cap if mode == "AR" else F["capture"](a.family, r["unit"], "ON3")
    g = F["grade"](cap, case, history, target, serial, control)
    need(
        g == read(root / "grade.json")
        and sha(root / "grade.json") == arm["grade_sha256"]
        and g["store"] == arm["store"],
        "numerical proof",
    )
    delta = {}
    if mode != "AR":
        RB["G"]["compare"](
            cap, mode, target, serial, F["capture"](a.family, r["unit"], "HIST1"), live=True
        )
        n = g["grade"]["decision"]["accepted"] + 1
        for j, sub in enumerate(("trim", "next-0", "next-1")):
            delta[sub] = POOL["footprint"](control / f"keep-{n + j}.pool", cap / (sub + ".pool"))
    return dict(
        mode=mode,
        reserve=reserve,
        image_sha256=arm["image_sha256"],
        status=arm["status"],
        serial_files_matched=len(g["serial_matches"]),
        decision=g["grade"]["decision"],
        store=g["store"],
        pool_delta=delta,
        fd=arm["fd"],
        model_s=arm["model_s"],
        scope_s=arm["scope_s"],
        maxima=m["maxima"],
        energy=R["power"](root, {"unit": unit}),
        c118=inv,
    )


def reservation_counts(cap, labels):
    rows = {}
    previous = None
    for label in labels:
        layers = POOL["pool"](cap / (label + ".pool"))
        generations = [v for layer in layers for v in layer["generation"]]
        need(
            previous is None or all(a <= b for a, b in zip(previous, generations, strict=True)),
            "monotone generation counters",
        )
        previous = generations
        rows[label] = {
            tier: sum(sum(layer["generation"]) for layer in layers[first:last])
            for tier, first, last in (("CPU", 0, 25), ("CUDA", 25, 36))
        }
    return rows


def reconcile(a, r):
    raw = F["GRAPH"]["read"](
        a.forecast / "receipt.json",
        "75fdb2ae99a49572e63be33b90aa6a926a466fa0e43167f46d9b5b0dd8df2ec7",
    )
    report = read(a.forecast / "forecast.json")
    need(
        all(sha(a.forecast / k) == v for k, v in raw["files"].items())
        and sha(HERE / "loads.py") == raw["files"]["loads.py"]
        and raw["family_commit"] == r["commit"]
        and raw["model_starts"] == 0
        and not {"B0", "B1", "B2"}.intersection(raw["family_at_freeze"]),
        "independent forecast",
    )
    actual = {}
    for case, (_, _, mode) in F["CASES"].items():
        p = F["capture"](a.family, r["unit"], case)
        if case in ("B0", "B1", "B2"):
            start = read(p.with_suffix(".launch.json"))["start_inventory"]["popen_invoked_utc"]
            need(
                datetime.fromisoformat(raw["utc"]) < datetime.fromisoformat(start),
                "pre-launch forecast",
            )
        expected = report["predicted_cumulative_reservations"][mode]
        labels = (
            ["entry", *(f"keep-{i}" for i in range(1, 6))]
            if mode == "AR"
            else ["entry", "trim", "next-0", "next-1"]
        )
        counts = reservation_counts(p, labels)
        closure = read(p / "native.json")
        need(
            sum(counts["entry"].values()) == closure["store_entry"]["loads"]
            and sum(counts[labels[-1]].values()) == closure["store_end"]["loads"],
            "completed loads vs reservation generations",
        )
        actual[case] = dict(matches_prior=counts == expected, counts=counts)
    observed = {}
    for k in range(3):
        rows = {}
        for j, label in enumerate(("trim", "next-0", "next-1")):
            base = actual["ON3"]["counts"][f"keep-{k + 1 + j}"]
            block = actual[f"B{k}"]["counts"][label]
            diff = {t: block[t] - base[t] for t in ("CPU", "CUDA")}
            rows[label] = dict(
                serial=base,
                block=block,
                delta=diff,
                delta_logical_bytes=sum(diff.values()) * 13219200,
            )
        observed[f"B{k}"] = rows
    return dict(
        forecast_receipt_sha256=sha(a.forecast / "receipt.json"),
        freeze_utc=raw["utc"],
        all_cuts_match=all(v["matches_prior"] for v in actual.values())
        and observed == report["equal_confirmed_depth"],
        measured_and_reconciled=actual,
        observed_at_equal_committed_depth=observed,
    )


def review(a):
    r = R["reopen"](a.family, a.family_sha256)
    d = F["GRAPH"]["read"](a.client / "receipt.json", F["CLIENT"])
    win = F["GRAPH"]["read"](a.window / "receipt.json", r["window_sha256"])
    need(
        r["status"] == "GO_PACKED_SERVER_RESERVE_GREEDY"
        and r["model_starts"] == len(F["CASES"]) == 7
        and r["generation_requests"] == 0
        and set(r["arms"]) == F["CASES"].keys()
        and sha(a.client / "b3-numeric") == d["elf_sha256"]
        and sha(a.client / "reserve.cpp") == d["source_sha256"]
        and d["combo_sha256"] == r["combo_sha256"] == C["COMBO"]
        and sha(HERE / "protocol.md") == r["protocol_sha256"] == C["METHOD"]
        and win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(a.window / "samples.jsonl") == win["window_sha256"],
        "sealed family",
    )
    refs = controls(a)
    return dict(
        status=r["status"],
        model_starts=r["model_starts"],
        http_requests=0,
        product_latency="NOT_RUN",
        commit=r["commit"],
        tree=r["tree"],
        family_sha256=a.family_sha256,
        client_sha256=F["CLIENT"],
        protocol_sha256=C["METHOD"],
        window_sha256=r["window_sha256"],
        combo_sha256=r["combo_sha256"],
        device=win["gpu_name"],
        driver=win["gpu_driver"],
        load_prediction=reconcile(a, r),
        arms={k: audit(a, r, d, k, *refs) for k in F["CASES"]},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "family",
        "client",
        "window",
        "history",
        "target",
        "serial",
        "forecast",
        "new-output-dir",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--family-sha256", required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    data = review(a)
    F["save"](a.new_output_dir / "result.json", data)
    print(data["status"])

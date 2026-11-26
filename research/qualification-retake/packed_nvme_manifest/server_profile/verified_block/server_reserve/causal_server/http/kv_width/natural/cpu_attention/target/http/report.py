"""Reproduce the reporting failure and independently verify both closed natural requests."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SERVER = run_path(str(HERE / "serve.py"))
H, G, need, sha, save = (SERVER[k] for k in ("H", "G", "need", "sha", "save"))
METHOD = "93e082e65634b1178a8b9d0163028a0daca4052508ceaba9cf4e350e7005f37f"
PREPARED = "dee236dd49622f0135fb5d99d996b108af7603393e6d9b7267a8737fd5e4b07a"
FAMILY = "bad233f91e4011d7be7caeaabec169356d0efc50512a3586ec848a0f7cb67915"
OLD = "b428afa59a48509176b9fb83cbc695a860346da2"
IK = "research/qualification-retake/ik_mapped_experts/frontend/server/session.py"
LEGACY = """from pathlib import Path
import json, sys
src, module, root = sys.argv[1:]
namespace = {"__file__": module, "__name__": "legacy"}
exec(compile(Path(src).read_bytes(),module,"exec"),namespace)
p=Path(root)
rows=json.loads((p/"client-receipt.json").read_text())["rows"]
print(json.dumps([namespace["summarize"](row,p/"raw",i) for i,row in enumerate(rows,1)]))
"""


def reopen(root, digest):
    r = G["read"](root / "receipt.json", digest)
    files = {
        str(p.relative_to(root)): sha(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p != root / "receipt.json"
    }
    need(files == r["raw_sha256"], "complete HTTP artifact set")
    return r


def cases(a):
    data = H["F"]["inputs"](SimpleNamespace(capture=a.capture, verified=a.verified))
    plan = G["read"](a.plan / "receipt.json", H["PLAN_PIN"])
    steps = G["read"](a.plan / "r0.stdout", plan["same_output_sha256"])
    for k, v in data.items():
        need(H["F"]["validate"](steps[k], v) == plan["turns"][k], "causal proposal schedule")
    return data, steps


def observe(folder, mode, data, steps):
    raw = folder / "raw"
    client = H["read"](folder / "client-receipt.json")
    inputs = H["read"](folder / "arm-inputs.json")
    preset = H["read"](folder / "preset.json")
    rid = preset["run_id"]
    mon, launch, stop = [
        H["read"](raw / (rid + s)) for s in (".json", ".launch.json", ".owner-stop.json")
    ]
    need(
        mon["returncode"] == mon["maxima"]["swap_bytes"] == 0
        and mon["mapped_libraries_match_ldd"]
        and mon["stop_reason"] == stop["status"] == "INTERRUPTED_BY_OWNER"
        and mon["process_identity"] == launch["process_identity"] == stop["process_identity"]
        and mon["command"] == inputs["argv"]
        and mon["explicit_env"] == inputs["env"]
        and mon["artifact_identity"]["stat_at_launch"]
        == mon["artifact_identity"]["stat_at_end"]
        == preset["model_stat"],
        "target, monitor, placement and termination",
    )
    for cut in ("cgroup_start", "cgroup_end"):
        need(
            mon[cut]["memory_max"] == mon[cut]["memory_high"] == 20 << 30
            and mon[cut]["swap_max"] == 0,
            "E20",
        )
    inv = run_path(str(H["Q"] / "nvme_r0_gate/qualified_profile/compact.py"))["validate_inventory"](
        folder, rid, dict(native_explicit_env=inputs["env"]), launch
    )
    energy = run_path(str(H["Q"] / "packed_nvme_manifest/server_profile/system_driver/review.py"))[
        "power"
    ](folder, dict(unit=rid))
    reader = run_path(str(H["Q"] / "nvme_conversation/client_rows.py"))["summarize"]
    log = (raw / (rid + ".stderr")).read_bytes()
    need(
        client["status"] == "CLIENT_TWO_REQUESTS_PASS" and len(client["rows"]) == 2,
        "both accepted turns",
    )
    rows, trajectory = [], {}
    for i, row in enumerate(client["rows"], 1):
        label = "T" + str(i)
        out = reader(row, raw, i, ids_hash=H["SESSION"].ids_hash)
        ids = H["T"]["grade"](log, i, data, steps, mode)
        expected = data[label]
        timing = H["read"](raw / (label + "-timings-observed.json"))
        need(
            row == H["read"](raw / (label + "-result.json"))
            and row["prefix_gate"] == "PASS"
            and out["validator"] == "PASS"
            and out["stop"] == "stop"
            and out["official_ids_sha256"] == H["SESSION"].ids_hash(expected["prompt"])
            and out["output"] == out["predicted"] == ids["sampled"] == len(expected["target"])
            and (out["cached"], out["evaluated"]) == [(0, 2043), (2044, 153)][i - 1]
            and timing.get("draft_n", 0) == ids["proposed"]
            and timing.get("draft_n_accepted", 0) == ids["accepted"],
            "native decisions and client clocks",
        )
        rows.append(out)
        trajectory[str(i)] = ids
    return dict(
        rows=rows,
        trajectories=trajectory,
        inventory=inv,
        energy=energy,
        maxima=mon["maxima"],
        monitor_elapsed_s=mon["elapsed_s"],
        monitor_stop=mon["stop_reason"],
        image_sha256=inputs["dso"]["libllama.so.0"]["sha256"],
        data_observer=H["read"](folder / "loader-data-after.json"),
    )


def study(a):
    need(sha(HERE / "report_protocol.md") == METHOD, "report protocol")
    pre = reopen(a.prepared, PREPARED)
    r = reopen(a.family, FAMILY)
    need(
        pre["status"] == "PREPARED_FOUR_ARMS"
        and pre["model_starts"] == 0
        and r["commit"] == pre["commit"] == OLD
        and r["status"] == "FAIL_PRESERVED"
        and list(r["arms"]) == ["ON"]
        and r["model_starts"] == 1
        and r["started_requests"] == 2,
        "stop and siblings",
    )
    folder = a.family / "ON"
    arm = reopen(folder, r["arms"]["ON"]["sha256"])
    error = "AttributeError: module 'measure' has no attribute 'io'"
    need(
        arm["error"] == error and not (folder / "closed-session.json").exists(),
        "failed report provenance",
    )
    repo = G["REPO"]
    src = subprocess.check_output(["git", "-C", str(repo), "show", OLD + ":" + IK])
    namespace = {"__file__": str(repo / IK), "__name__": "old_report"}
    try:
        exec(compile(src, str(repo / IK), "exec"), namespace)
    except AttributeError as exc:
        need(type(exc).__name__ + ": " + str(exc) == error, "different historical failure")
    else:
        raise ValueError("historical collision absent")
    science = observe(folder, "ON", *cases(a))
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        previous = root / "legacy.py"
        previous.write_bytes(src)
        old = json.loads(
            subprocess.check_output(
                [sys.executable, "-IB", "-c", LEGACY, str(previous), str(repo / IK), str(folder)]
            )
        )
        need(old == science["rows"], "all legacy clocks and fields")
        row = H["read"](folder / "client-receipt.json")["rows"][0]
        stream = root / "T1-request.jsonl"
        original = (folder / "raw/T1-request.jsonl").read_bytes().splitlines()
        stream.write_bytes(b"\n".join(original[:-1]) + b"\n")
        reader = run_path(str(H["Q"] / "nvme_conversation/client_rows.py"))["summarize"]
        try:
            reader(row, root, 1, ids_hash=H["SESSION"].ids_hash)
        except ValueError as exc:
            need(str(exc) == "terminal", "correct missing terminal")
        else:
            raise ValueError("missing accepted terminal passed")
    return dict(
        status="GO_REPORT_FIXTURE_ONLY",
        family_status=r["status"],
        model_starts=0,
        physical_starts=1,
        physical_http_requests=2,
        protocol_sha256=METHOD,
        failed_family_sha256=FAMILY,
        prepare_sha256=PREPARED,
        failed_source=OLD,
        report_sha256=hashlib.sha256(src).hexdigest(),
        reported_error=error,
        absent_live_evidence=["FD cuts", "signal timestamps"],
        not_run=["OFF", "P", "R"],
        physical_wall_s=r["wall_s"],
        recomputed=science,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "prepared", "capture", "verified", "plan", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = study(a)
    except Exception as exc:
        result = dict(
            status="FAIL_PRESERVED",
            error=f"{type(exc).__name__}: {exc}",
            model_starts=0,
            failed_family_sha256=FAMILY,
            protocol_sha256=METHOD,
        )
    save(a.new_output_dir / "receipt.json", result)
    print(result["status"], result.get("error", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")

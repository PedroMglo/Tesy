"""Run the original two-turn C281 client against a privately monitored contemporary R0."""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

from contract import (
    C281,
    CAP,
    HERE,
    PORT,
    REPO,
    check,
    file_identity,
    git,
    idle_port,
    ids_hash,
    load,
    owned_listener,
    placement,
    sha256,
    source_digest,
    sources,
)

# isort: split
# Import the original client after the repository tool path is installed by contract.
import optin_integration_client as client
from host_resource_policy import freeze_protocol_resource_limits, validate_resource_protocol
from mappings import Guard
from measure import check_gate
from parallel_runtime import validate_launch_runtime
from prepare import save
from run_bounded import process_identity, relevant_environment
from vma_identity import Reference, stable


def source_seal(out):
    sealed = sources()
    save(out / "inputs.json", sealed)
    print("PASS_INPUTS_ONLY", flush=True)


def validate_c270(path):
    summary = load(path)
    check(
        summary["status"] == "PASS_SELECTED_C269_BRIDGE"
        and summary["model_launch_receipts"] == 1
        and summary["scope_returncode"] == 0
        and summary["monitor_stop"] is None
        and summary["envelope"] in {"E20_R0", "E18_DIAGNOSTIC_ONLY"},
        "contemporary C270 did not pass",
    )
    check_gate(summary["numerical_gate"])
    p = load(path.parent / "protocol.json")
    check(
        p["pinned"]["model_sha256"]
        == load(HERE.parent / "nvme_placement/receipt.json")["source_sha256"],
        "C270 model differs",
    )
    return p, sha256(path)


def require_session_id(rid):
    check(
        rid.startswith("tesy-c281-nvme-") and rid.replace("-", "").isalnum(),
        "invalid session identity",
    )


def campaign(a, out, runtime=None):
    workload = getattr(runtime, "workload", None)
    cache_counts = [(0, 2043), (2044, 153)] if workload is None else workload.cache_counts
    frozen = sources() if runtime is None else sources(runtime.selection)
    historical = frozen if runtime is None else runtime.historical_projection(frozen)
    check(
        source_digest(historical) == load(HERE / "inputs.json")["actual_inputs_sha256"],
        "frozen server, load-time objects or workload differ",
    )
    check(
        git(REPO, "rev-parse", "HEAD") == a.commit and not git(REPO, "status", "--porcelain"),
        "clean measurement checkout required",
    )
    check(not relevant_environment(os.environ), "inherited runtime override")
    g, g_sha = validate_c270(a.c270)
    if runtime is not None:
        runtime.bind_c270(a, g, g_sha)
    policy, model_id = placement(a.window, a.placement)
    check(
        g["model_stat"] == model_id and g["pinned"]["server_sha256"] == frozen["binary_sha256"],
        "C270 certificate differs",
    )
    for name, identity in g["pinned"]["startup_dso_sha256"].items():
        check(
            any(
                Path(r["path"]).name == name and r["sha256"] == identity
                for r in frozen["dso"].values()
            ),
            "C270 selected ELF differs",
        )
    check(shutil.disk_usage(out).free >= 11 * 2**30, "11 GiB destination reserve unavailable")
    idle_port()
    rid = a.unit
    require_session_id(rid)
    check(
        subprocess.check_output(
            ["systemctl", "--user", "show", rid + ".service", "-p", "LoadState", "--value"],
            text=True,
        ).strip()
        == "not-found",
        "systemd unit already exists",
    )
    validate_launch_runtime(frozen["parallel_runtime"], os.environ | frozen["explicit_env"])
    raw = out / "raw"
    raw.mkdir()
    shutil.copyfile(a.window / "resource-policy.json", out / "resource-policy.json")
    preset = frozen | dict(
        run_id=rid,
        model_stat=model_id,
        measurement_commit=a.commit,
        tree=git(REPO, "rev-parse", "HEAD^{tree}"),
        c270_receipt_sha256=g_sha,
        operational_control="C281 exact command, contemporary E20 ELF/placement",
        window_sha256=sha256(a.window / "receipt.json"),
        swap_max_bytes=0,
    )
    save(out / "preset.json", preset)
    psha = sha256(out / "preset.json")
    protocol = dict(
        limits={},
        schema="tesy-c281-contemporary-e20-v1",
        execution_scope_unit=rid,
        resources=freeze_protocol_resource_limits(policy, cgroup_memory_max_bytes=CAP),
        start_inventory=dict(
            schema="c120-start-inventory-v1",
            duration_s=60,
            max_age_s=3,
            policy_sha256=sha256(out / "resource-policy.json"),
        ),
        parallel_runtime=frozen["parallel_runtime"],
    )
    validate_resource_protocol(protocol)
    save(out / "resource-protocol.json", protocol)
    cmd = [
        "systemd-run",
        "--user",
        "--collect",
        "--pipe",
        "--wait",
        "--service-type=exec",
        "--unit=" + rid,
        "-p",
        f"MemoryMax={CAP}",
        "-p",
        f"MemoryHigh={CAP}",
        "-p",
        "MemorySwapMax=0",
        "-p",
        "RuntimeMaxSec=565",
        "-p",
        "TimeoutStopSec=10",
        "-p",
        "KillMode=control-group",
        "--",
        sys.executable,
        "-B",
        str(REPO / "tools/run_bounded.py"),
        "--run-id",
        rid,
        "--model-id",
        "gpt-oss-120b-mxfp4-gguf",
        "--backend",
        "streaming",
        "--backend-root",
        frozen["backend"],
        "--output-root",
        str(raw),
        "--variant",
        "C281-NVMe-contemporary-E20",
        "--workload",
        str(out / "preset.json"),
        "--cache-condition",
        "session-fresh-expert-pools-prefix-reuse-in-process",
        "--timeout-s",
        "480",
        "--resource-protocol",
        str(out / "resource-protocol.json"),
        "--require-telemetry",
        "--collect-start-inventory",
        "--env",
        "TESY_CPU_WAVE_SKIP_PARKED=1",
        "--",
        *frozen["server_command"],
    ]
    if runtime is not None:
        cmd = runtime.monitor_command(cmd, out)
    save(out / "argv.json", dict(command=cmd))
    launch = raw / (rid + ".launch.json")
    identity = {}
    model = Path(frozen["server_command"][frozen["server_command"].index("-m") + 1])
    holder = {}
    stoplock = threading.Lock()

    def verified(root):
        check(
            root == out
            and sha256(out / "preset.json") == psha
            and file_identity(model) == model_id,
            "frozen session changed",
        )
        return preset

    def own():
        checked = load(launch)["process_identity"]
        check(
            checked["cgroup_path"].endswith("/" + rid + ".service")
            and process_identity(checked["pid"]) == checked
            and Path(f"/proc/{checked['pid']}/exe").resolve()
            == Path(frozen["server_command"][0]).resolve(),
            "foreign or recycled server",
        )
        if identity:
            check(identity == checked, "process identity changed")
        identity.update(checked)
        return checked["pid"]

    def stop(root):
        verified(root)
        with stoplock:
            marker = raw / (rid + ".owner-stop.json")
            if not marker.exists() and launch.is_file():
                pid = own()
                save(marker, dict(status="INTERRUPTED_BY_OWNER", process_identity=dict(identity)))
                os.killpg(pid, signal.SIGINT)

    def safe_terminate():
        if launch.is_file() and not (raw / (rid + ".json")).exists():
            try:
                stop(out)
            except (OSError, ValueError):
                pass
        if holder["proc"].poll() is None:
            try:
                holder["proc"].wait(timeout=18)
            except subprocess.TimeoutExpired:
                # A unique unit started by this process. Never address any other service or PID.
                subprocess.run(
                    ["systemctl", "--user", "stop", rid + ".service"], timeout=20, check=False
                )
                holder["proc"].wait(timeout=15)

    with ExitStack() as stack:
        refs = {
            name: Reference(stack, Path(select["path"]), select["sha256"])
            for name, select in frozen["dso"].items()
        }
        guard = Guard(refs)

        def mappings(pid, _preset):
            check(pid == own(), "wrong mapping owner")
            guard.observed.clear()
            guard.scan(Path(f"/proc/{pid}/maps").read_text().splitlines())
            check(guard.observed == set(refs), "server ELF set incomplete")
            for ref in refs.values():
                check(
                    stable(ref.path.stat()) == ref.identity
                    and stable(os.fstat(ref.file.fileno())) == ref.identity,
                    "DSO file changed",
                )
            owned_listener(pid, PORT)
            if runtime is not None:
                runtime.first(pid)
            return {str(ref.path): ref.digest for ref in refs.values()}

        original_fetch = client.fetch
        original_stream = client.stream_chat
        ix = 0

        def guarded_fetch(path, *args, **kwargs):
            nonlocal ix
            owned_listener(own(), PORT)
            result = original_fetch(path, *args, **kwargs)
            if path == "/tokenize":
                check(
                    ix < 2 and ids_hash(result["tokens"]) == frozen["official_ids"][ix],
                    "official IDs differ before POST",
                )
            return result

        def guarded_stream(*args, **kwargs):
            nonlocal ix
            check(
                ix < 2
                and (raw / f"T{ix + 1}-input.json").exists()
                and sha256(raw / f"T{ix + 1}-input.json") == frozen["historical_inputs"][ix],
                "natural-history input differs before POST",
            )
            owned_listener(own(), PORT)
            response, metrics = original_stream(*args, **kwargs)
            # Preserve the original streaming boundaries before checking the envelope.
            t = response["timings"]
            save(raw / f"T{ix + 1}-timings-observed.json", t)
            check(
                (t["cache_n"], t["prompt_n"]) == cache_counts[ix],
                "cache/prompt accounting differs",
            )
            ix += 1
            return response, metrics

        def watching(proc):
            proc.wait()
            save(out / "serve-receipt.json", dict(monitor_exit=proc.returncode))

        def guard_output(proc):
            while proc.poll() is None:
                if sum(p.stat().st_size for p in raw.iterdir() if p.is_file()) > 64 * 2**20:
                    save(out / "raw-limit.json", dict(status="RAW_LIMIT_EXCEEDED"))
                    subprocess.run(
                        ["systemctl", "--user", "stop", rid + ".service"], timeout=20, check=False
                    )
                    return
                time.sleep(0.5)

        client.launcher = SimpleNamespace(verified=verified, stop=stop)
        client.fetch = guarded_fetch
        client.stream_chat = guarded_stream
        client.persistent_mappings = mappings
        check(file_identity(model) == model_id, "GGUF changed before spawn")
        with (out / "scope.log").open("xb") as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            holder["proc"] = proc
            waiter = threading.Thread(target=watching, args=(proc,))
            waiter.start()
            size_guard = threading.Thread(target=guard_output, args=(proc,))
            size_guard.start()
            try:
                if workload is None:
                    result = client.run(out, C281 / "protocol.json")
                else:
                    result = workload.run(out, client, preset, own)
                check(
                    result["status"] == "CLIENT_TWO_REQUESTS_PASS" and ix == 2,
                    result.get("failure") or "two requests not accepted",
                )
                mappings(own(), preset)
                if runtime is not None:
                    runtime.last(own())
            finally:
                safe_terminate()
                waiter.join(timeout=2)
                size_guard.join(timeout=2)
    m = load(raw / (rid + ".json"))
    check(
        m["returncode"] == 0
        and m["stop_reason"] == "INTERRUPTED_BY_OWNER"
        and m["mapped_libraries_match_ldd"]
        and m["artifact_identity"]["stat_at_launch"]
        == m["artifact_identity"]["stat_at_end"]
        == model_id
        and m["maxima"]["swap_bytes"] == 0
        and m["maxima"]["direct_model_fds"] > 0
        and not (out / "raw-limit.json").exists(),
        "monitored endpoint failed",
    )
    for key in ["cgroup_start", "cgroup_end"]:
        c = m[key]
        check(
            c["memory_max"] == c["memory_high"] == CAP and c["swap_max"] == 0,
            "E20 boundary differs",
        )
    check(not Path(f"/proc/{identity['pid']}").exists(), "server still present")
    # TCP may legitimately retain closed connections in TIME_WAIT.
    # Cleanup concerns the listener and the owning unit.
    listeners = [r.split() for r in Path("/proc/net/tcp").read_text().splitlines()[1:]]
    check(
        not any(r[1] == f"0100007F:{PORT:04X}" and r[3] == "0A" for r in listeners),
        "loopback service still listening after cleanup",
    )
    state = subprocess.check_output(
        ["systemctl", "--user", "show", rid + ".service", "-p", "ActiveState", "--value"], text=True
    ).strip()
    check(state in {"inactive", "failed"}, "owned service not closed")
    runtime_evidence = {}
    if runtime is not None:
        runtime_evidence["runtime_authority"] = runtime.finish(identity, m, out, rid)
    rows = []
    for row in result["rows"]:
        t = row["timings"]
        rows.append(
            dict(
                id=row["id"],
                functional=row["content_gate"],
                prefix=row["prefix_gate"],
                completion=row["finish_reason"],
                official_ids_sha256=ids_hash(row["official_ids"]),
                input_n=len(row["official_ids"]),
                cache_n=t["cache_n"],
                prompt_n=t["prompt_n"],
                completion_n=row["usage"]["completion_tokens"],
                predicted_n=t["predicted_n"],
                prefill_s=t["prompt_ms"] / 1000,
                decode_s=t["predicted_ms"] / 1000,
                decode_tok_s=t["predicted_per_second"],
                first_final_s=row["stream_metrics"]["first_final_content_chunk_s"],
                valid_wall_s=row["request_wall_s"],
            )
        )
    return dict(
        status="PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY",
        rows=rows,
        model_launches=1,
        **(
            dict(
                nominal_first_final_le_10s=rows[1]["first_final_s"] <= 10,
                nominal_decode_ge_6=rows[1]["decode_tok_s"] >= 6,
            )
            if workload is None
            else dict(workload=workload.name)
        ),
        start_inventory=sha256(raw / (rid + ".start-inventory.jsonl")),
        ready_s=result["readiness_after_popen_s"],
        maxima=m["maxima"],
        monitor_sha256=sha256(raw / (rid + ".json")),
        cleanup="SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE",
        preset_sha256=psha,
        **runtime_evidence,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["inputs", "run"])
    ap.add_argument("--new-output-dir", required=True, type=Path)
    for name in ("window", "placement", "c270"):
        ap.add_argument("--" + name, type=Path)
    ap.add_argument("--commit")
    ap.add_argument("--unit")
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    if a.mode == "inputs":
        source_seal(out)
        return
    started = time.monotonic()
    try:
        result = campaign(a, out)
    except Exception as exc:
        result = dict(
            status="FAIL_PRESERVED",
            failure=f"{type(exc).__name__}: {exc}",
            model_launches=len(list(out.glob("raw/*.launch.json"))),
        )
    result["envelope_s"] = time.monotonic() - started
    if result["envelope_s"] > 650:
        result.update(status="FAIL_PRESERVED", failure="650s envelope")
    save(out / "receipt.json", result)
    print(result["status"], flush=True)
    raise SystemExit(result["status"] != "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY")


if __name__ == "__main__":
    main()

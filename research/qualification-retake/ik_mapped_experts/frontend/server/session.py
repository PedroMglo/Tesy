"""Serve the two frozen natural turns on the laptop and retain the client's own clocks."""

import argparse
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
P = run_path(str(HERE / "pilot.py"))
import optin_integration_client as client  # noqa: E402

need, sha, CON, R = (P[k] for k in ("need", "sha", "CON", "R"))
load = CON["load"]


def save(path, value):
    with path.open("x") as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def summarize(row, raw, i):
    events = [json.loads(line) for line in (raw / f"T{i}-request.jsonl").read_text().splitlines()]
    terminal = events[-1]
    need(
        terminal["kind"] == "REQUEST_TERMINAL" and terminal["accepted"] and row["accepted"],
        "terminal",
    )
    t = row["timings"]
    return dict(
        official_ids_sha256=CON["ids_hash"](row["official_ids"]),
        prompt=len(row["official_ids"]),
        cached=t["cache_n"],
        evaluated=t["prompt_n"],
        output=row["usage"]["completion_tokens"],
        predicted=t["predicted_n"],
        prefill_s=t["prompt_ms"] / 1000,
        decode_s=t["predicted_ms"] / 1000,
        decode_tok_s=t["predicted_per_second"],
        first_reasoning_s=row["stream_metrics"]["first_reasoning_chunk_s"],
        first_final_s=row["stream_metrics"]["first_final_content_chunk_s"],
        transport_s=row["request_wall_s"],
        valid_s=terminal["monotonic_s"] - row["request_started_monotonic"],
        validator=row["content_gate"],
        stop=row["finish_reason"],
        output_ids_authority=row["output_ids_authority"],
    )


def run(a, out, r):
    preset, protocol, policy = P["freeze"](a)
    rid = a.unit
    need(rid.startswith("tesy-ik-http-pilot-") and rid.replace("-", "").isalnum(), "dedicated unit")
    need(
        shutil.disk_usage(out).free >= 11 << 30
        and R["CPU"]["window"].mount(out)[0].split("[")[0]
        == R["CPU"]["window"].mount(Path(preset["env"]["TESY_IK_BANK_MODEL"]))[0].split("[")[0],
        "raw NVMe or free space",
    )
    CON["idle_port"]()

    def unit_state(prop):
        return subprocess.check_output(
            ["systemctl", "--user", "show", rid + ".service", "-p", prop, "--value"], text=True
        ).strip()

    need(unit_state("LoadState") == "not-found", "service already exists")
    raw = out / "raw"
    raw.mkdir()
    save(out / "preset.json", preset)
    seal = sha(out / "preset.json")
    shutil.copyfile(a.window / "resource-policy.json", out / "resource-policy.json")
    save(out / "resource-protocol.json", protocol)
    command = [
        "systemd-run",
        "--user",
        "--collect",
        "--pipe",
        "--wait",
        "--service-type=exec",
        "--unit=" + rid,
        "-p",
        "MemoryMax=20G",
        "-p",
        "MemoryHigh=19968M",
        "-p",
        "MemorySwapMax=0",
        "-p",
        "RuntimeMaxSec=565",
        "-p",
        "TimeoutStopSec=10",
        "-p",
        "KillMode=control-group",
        "--",
        "/usr/bin/env",
        "-i",
        *(k + "=" + v for k, v in preset["env"].items()),
        "/usr/bin/python3",
        "-B",
        str(P["REPO"] / "tools/run_bounded.py"),
        "--run-id",
        rid,
        "--model-id",
        "gpt-oss-120b-mxfp4-gguf",
        "--backend",
        "streaming",
        "--backend-root",
        str(a.build / "source"),
        "--output-root",
        str(raw),
        "--variant",
        "ik-native-bounded-PREAD-C281",
        "--workload",
        str(out / "preset.json"),
        "--cache-condition",
        "fresh-KV-observed-OS-cache",
        "--timeout-s",
        "480",
        "--resource-protocol",
        str(out / "resource-protocol.json"),
        "--require-telemetry",
        "--collect-start-inventory",
        "--",
        *preset["argv"],
    ]
    save(out / "argv.json", command)
    r.update(commit=preset["commit"], tree=preset["tree"], preset_sha256=seal, unit=rid)
    if a.prepare_only:
        r["status"] = "PREPARED_ONLY"
        return
    prior = P["receipt"](a.prepared / "receipt.json", a.prepared_sha256)
    need(
        prior["status"] == "PREPARED_ONLY" and prior["preset_sha256"] == seal,
        "different preparation",
    )
    launch = raw / (rid + ".launch.json")
    r["file_pages_before_C118"] = json.loads(
        subprocess.check_output(
            [
                "/usr/bin/fincore",
                "--json",
                "--bytes",
                "--output",
                "SIZE,RES,PAGES",
                preset["env"]["TESY_IK_BANK_MODEL"],
            ],
            text=True,
        )
    )["fincore"][0]
    cap = 64 << 20
    mutex = threading.Lock()

    def own():
        ident = load(launch)["process_identity"]
        pid = ident["pid"]
        need(
            client.process_identity(pid) == ident
            and ident["cgroup_path"].endswith("/" + rid + ".service")
            and Path(f"/proc/{pid}/exe").resolve() == Path(preset["argv"][0]),
            "server ownership",
        )
        return pid

    def stop(_):
        with mutex:
            if not launch.exists():
                return
            mark = raw / (rid + ".owner-stop.json")
            if mark.exists():
                return
            pid = own()
            save(
                mark,
                dict(status="INTERRUPTED_BY_OWNER", process_identity=client.process_identity(pid)),
            )
            os.killpg(pid, signal.SIGINT)

    libs = preset["libraries"]
    saved_stat = {k: R["stock"].identity(Path(v["path"])) for k, v in libs.items()}
    observed = []

    def maps(pid, _):
        need(pid == own(), "unexpected serving PID")
        CON["owned_listener"](pid, P["PORT"])
        m = Path(f"/proc/{pid}/maps").read_text()
        paths = {
            str(Path(p[5]).resolve())
            for line in m.splitlines()
            if len(p := line.split(maxsplit=5)) == 6 and p[5].startswith("/")
        }
        need(
            all(
                v["path"] in paths and R["stock"].identity(Path(v["path"])) == saved_stat[k]
                for k, v in libs.items()
            ),
            "changed or missing DSO",
        )
        model = preset["env"]["TESY_IK_BANK_MODEL"]
        need(
            model in paths and R["stock"].bounded.file_identity(model) == preset["model_stat"],
            "model view",
        )
        active = R["DEV"]["ACTIVE"](pid, policy["gpu"]["uuid"], True)
        need(active["gpu_owners"] == [pid], "foreign CUDA owner")
        observed.append(
            dict(
                phase=len(observed),
                gpu_owners=active["gpu_owners"],
                vram_MiB=active["gpu"]["used_mib"],
            )
        )
        return {v["path"]: v["sha256"] for v in libs.values()}

    original_fetch, original_stream = client.fetch, client.stream_chat
    inputs = []

    def fetch(path, *args, **kwargs):
        CON["owned_listener"](own(), P["PORT"])
        data = original_fetch(path, *args, **kwargs)
        if path == "/tokenize":
            digest = CON["ids_hash"](data["tokens"])
            need(
                len(inputs) < 2 and (inputs or digest == preset["official_ids"][0]),
                "first official input",
            )
            inputs.append((len(data["tokens"]), digest))
        return data

    def stream(*args, **kwargs):
        i = len(inputs)
        need(i in (1, 2), "missing tokenization")
        if i == 1:
            need(
                sha(raw / "T1-input.json") == preset["historical_inputs"][0],
                "first full request changed",
            )
        CON["owned_listener"](own(), P["PORT"])
        r["generation_requests"] += 1
        response, metrics = original_stream(*args, **kwargs)
        save(
            raw / f"T{i}-native-accounting.json",
            dict(timings=response["timings"], usage=response["usage"]),
        )
        return response | dict(
            timings=P["normalize"](response["usage"], response["timings"], inputs[-1][0])
        ), metrics

    def verified(root):
        need(root == out and sha(root / "preset.json") == seal, "preset changed")
        return preset

    old_launcher, old_maps = client.launcher, client.persistent_mappings
    client.launcher = SimpleNamespace(verified=verified, stop=stop)
    client.fetch, client.stream_chat, client.persistent_mappings = fetch, stream, maps
    with (out / "scope.log").open("xb") as log:
        proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)

        def watch():
            while proc.poll() is None:
                if sum(p.stat().st_size for p in raw.iterdir() if p.is_file()) > cap:
                    save(out / "raw-limit.json", dict(status="RAW_LIMIT_EXCEEDED"))
                    subprocess.run(
                        ["systemctl", "--user", "stop", rid + ".service"], timeout=20, check=False
                    )
                    break
                time.sleep(0.5)
            proc.wait()
            save(out / "serve-receipt.json", dict(monitor_exit=proc.returncode))

        watcher = threading.Thread(target=watch)
        watcher.start()
        try:
            result = client.run(out, CON["C281"] / "protocol.json")
            need(
                result["status"] == "CLIENT_TWO_REQUESTS_PASS",
                result.get("failure") or "client status",
            )
            maps(own(), preset)
            r["rows"] = [summarize(row, raw, i) for i, row in enumerate(result["rows"], 1)]
            r["ready_s"] = result["readiness_after_popen_s"]
        finally:
            client.launcher, client.persistent_mappings = old_launcher, old_maps
            client.fetch, client.stream_chat = original_fetch, original_stream
            if proc.poll() is None:
                try:
                    stop(out)
                except (OSError, ValueError):
                    pass
                try:
                    proc.wait(timeout=17)
                except subprocess.TimeoutExpired:
                    subprocess.run(
                        ["systemctl", "--user", "stop", rid + ".service"], timeout=20, check=False
                    )
                    proc.wait(timeout=15)
            watcher.join(timeout=3)
            r.update(
                listener_checks=observed, model_starts=int(launch.exists()), actual_inputs=inputs
            )
            if launch.exists():
                ident = load(launch)["process_identity"]
                r["child_gone"] = not Path(f"/proc/{ident['pid']}").exists()
            r["unit_end"] = unit_state("ActiveState")
            if (raw / (rid + ".json")).exists():
                m = load(raw / (rid + ".json"))
                r["monitor"] = {
                    k: m.get(k)
                    for k in (
                        "returncode",
                        "stop_reason",
                        "elapsed_s",
                        "maxima",
                        "mapped_libraries_match_ldd",
                    )
                }
    m = load(raw / (rid + ".json"))
    need(
        m["returncode"] == 0
        and m["stop_reason"] == "INTERRUPTED_BY_OWNER"
        and m["mapped_libraries_match_ldd"]
        and m["maxima"]["swap_bytes"] == 0
        and m["artifact_identity"]["stat_at_launch"]
        == m["artifact_identity"]["stat_at_end"]
        == preset["model_stat"]
        and r["child_gone"]
        and r["unit_end"] == "inactive"
        and not (out / "raw-limit.json").exists(),
        "monitored cleanup",
    )
    server_log = (raw / (rid + ".stderr")).read_text() + (raw / (rid + ".stdout")).read_text()
    need(
        "36 layer(s), 288 expert slots" in server_log
        and server_log.count("TESY_NATIVE_INPUT PREAD_RANDOM 648155136 0") == 1
        and server_log.count("TESY_NATIVE_END ") == 1,
        "native cache or final drain",
    )
    r["native_summary"] = [line for line in server_log.splitlines() if "TESY_NATIVE_END " in line]
    r["status"] = "TWO_NATURAL_TURNS"
    t1, t2 = r["rows"]
    r["nominal"] = (t1["cached"], t1["evaluated"], t2["cached"], t2["evaluated"]) == (
        0,
        2043,
        2044,
        153,
    ) and [t1["official_ids_sha256"], t2["official_ids_sha256"]] == preset["official_ids"]
    r["nominal_goals"] = (
        dict(first_final=t2["first_final_s"] <= 10, decode=t2["decode_tok_s"] >= 6)
        if r["nominal"]
        else None
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("build", "window", "placement", "template", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("window-sha256", "commit", "unit"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--prepare-only", action="store_true")
    p.add_argument("--prepared", type=Path)
    p.add_argument("--prepared-sha256")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", model_starts=0, generation_requests=0, energy_J=None)
    try:
        need(a.prepare_only != bool(a.prepared and a.prepared_sha256), "prepare or execute")
        with (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(a, out, r)
    except Exception as e:
        r.update(error=f"{type(e).__name__}: {e}")
    r["raw_sha256"] = {str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()}
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    sys.exit(r["status"] == "FAIL_PRESERVED")

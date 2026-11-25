"""Read a terminal C281 conversation and check work and clocks against their own authorities."""

import json
import math
import os
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[2]
INT = QUAL / "phase_fd/integrated"
NATURAL = INT / "t1_manager_bank/policy_snapshot/natural"
conv = run_path(str(INT / "conversation/profile.py"))
pair = run_path(str(NATURAL / "pair.py"))
native = conv["samples"]
need, read, sha, pinned = conv["need"], conv["read"], conv["sha"], conv["pinned"]
CLEAN = "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE"
CAP = 20 * 2**30
STOP = 39 * 2**29


def lines(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 64 * 2**20, "raw file")
    return [json.loads(row) for row in path.read_bytes().splitlines()]


def fragments(journal):
    return [
        (n, json.loads(row["fragment"][6:]))
        for n, row in enumerate(journal)
        if row["kind"] == "SSE_FRAGMENT" and row["fragment"].startswith("data: {")
    ]


def stable_frame(frame):
    # The server generates a new request ID/date; its two timing objects price each actual arm.
    obj = {k: v for k, v in frame.items() if k not in ("id", "created", "timings")}
    if "__verbose" in obj:
        obj["__verbose"] = {k: v for k, v in obj["__verbose"].items() if k != "timings"}
    return obj


def compare_transport(raw, historical, i, full, geometry):
    prefix = f"T{i}"
    journal = lines(raw / (prefix + "-request.jsonl"))
    gold = fragments(lines(historical / "raw" / (prefix + "-request.jsonl")))
    frames = fragments(journal)
    need(
        [stable_frame(f) for _, f in frames] == [stable_frame(f) for _, f in gold]
        and len(frames) == geometry[3]
        and sha(raw / (prefix + "-input.json"))
        == sha(historical / "raw" / (prefix + "-input.json")),
        "complete stable SSE frames or original input bytes",
    )
    previous = [r["monotonic_s"] for r in journal]
    need(
        all(math.isfinite(x) for x in previous)
        and all(a <= b for a, b in pairwise(previous))
        and all(r["request_id"] == full["id"] for r in journal)
        and [r["kind"] for r in journal if r["kind"] != "SSE_FRAGMENT"]
        == ["REQUEST_START", "RESPONSE_COMPLETE", "REQUEST_TERMINAL"]
        and journal[-2]["response"] == full["response"]
        and journal[-2]["completed_monotonic"] == full["request_ended_monotonic"]
        and journal[-1]["accepted"] is True
        and full["invalid_reason"] is None,
        "journal chronology or completion",
    )
    watchdog = journal[-1]["watchdog"]
    need(
        watchdog["watchdog_alive"] is False
        and all(
            watchdog[k] is None
            for k in (
                "expired_monotonic",
                "cancel_requested_monotonic",
                "cancel_finished_monotonic",
                "cancel_error",
            )
        )
        and watchdog["deadline_monotonic"] == full["deadline_monotonic"]
        and full["deadline_s"] == (180 if i == 1 else 90),
        "client deadline/cancellation",
    )
    start, end = full["request_started_monotonic"], full["request_ended_monotonic"]
    stream = full["stream_metrics"]
    need(
        start <= previous[0] <= previous[frames[0][0]] <= end <= previous[-2] <= previous[-1]
        and end <= full["deadline_monotonic"]
        and end - start == full["request_wall_s"]
        and stream["sse_event_count"] == len(frames)
        and frames[-1][1]["timings"]
        == read(raw / (prefix + "-timings-observed.json"))
        == full["response"]["timings"]
        == full["timings"]
        and [f["__verbose"]["timings"] for _, f in frames if "__verbose" in f] == [full["timings"]],
        "HTTP/server clocks or timings payload",
    )
    # Client stamps after journal.write, before fetching the next line. Use this bracket,
    # which remains valid even if that write blocks; don't force both clocks to be identical.
    for field, channels in (
        ("first_text_chunk_s", ("content", "reasoning_content")),
        ("first_reasoning_chunk_s", ("reasoning_content",)),
        ("first_final_content_chunk_s", ("content",)),
    ):
        row = next(
            (
                n
                for n, f in frames
                if any((c["delta"].get(k) or "").strip() for c in f["choices"] for k in channels)
            ),
            None,
        )
        need(
            row is not None and previous[row] - start <= stream[field] <= previous[row + 1] - start,
            "first client chunk does not price its actual SSE frame",
        )
    return dict(
        first_sse_fragment_s=previous[frames[0][0]] - start,
        transport_complete_s=end - start,
        validated_terminal_s=previous[-1] - start,
        terminal_monotonic_s=previous[-1],
        input_bytes_sha256=sha(raw / (prefix + "-input.json")),
        stable_frames_sha256=conv["projected_digest"]([stable_frame(f) for _, f in frames]),
    )


def monitor_summary(root, receipt, unit, client):
    raw = root / "raw"
    mon = pinned(raw / (unit + ".json"), receipt["monitor_sha256"])
    launchfile = raw / (unit + ".launch.json")
    launch = pinned(launchfile, client["launch_sha256"])
    identity = launch["process_identity"]
    owner = read(raw / (unit + ".owner-stop.json"))
    need(
        identity
        == client["process_identity"]
        == mon["process_identity"]
        == owner["process_identity"]
        and mon["run_id"] == unit
        and receipt["native_ids"]["pid"] == identity["pid"]
        and owner["status"] == mon["stop_reason"] == "INTERRUPTED_BY_OWNER"
        and mon["returncode"] == 0
        and mon["cgroup_limit_enforced"] is True
        and mon["maxima"] == receipt["maxima"]
        and receipt["maxima"]["swap_bytes"] == 0
        and receipt["maxima"]["cgroup_memory_bytes"] < STOP
        and 0 < mon["elapsed_s"] <= 480,
        "server identity, cgroup, stop or peak",
    )
    begin = mon["start_inventory"]
    need(begin == launch["start_inventory"], "launch inventory")
    inv = pinned(raw / (unit + ".start-inventory.receipt.json"), begin["receipt_sha256"])
    invfile = raw / (unit + ".start-inventory.jsonl")
    need(sha(invfile) == inv["sha256"] == receipt["start_inventory"], "inventory hash")
    inventory = lines(invfile)
    age = (
        datetime.fromisoformat(begin["popen_invoked_utc"])
        - datetime.fromisoformat(inventory[-1]["utc"])
    ).total_seconds()
    need(
        inv["run_id"] == unit
        and inv["duration_s"] >= 60
        and 0 <= age <= 3
        and inv["cap_bytes"] == CAP
        and inv["sample_count"] == len(inventory)
        and inventory[-1]["utc"] == inv["last_utc"],
        "C118 span/freshness",
    )
    sample_file = raw / (unit + ".samples.jsonl")
    need(sha(sample_file) == mon["output_sha256"][".samples.jsonl"], "sample identity")
    samples = lines(sample_file)
    need(all(s["process_identity"] == identity for s in samples), "sample process")
    for cg in [mon["cgroup_start"], mon["cgroup_end"], *(s["cgroup"] for s in samples)]:
        need(
            cg["memory_max"] == cg["memory_high"] == CAP
            and cg["swap_current"] == cg["swap_max"] == 0
            and cg["path"] == identity["cgroup_path"]
            and not any(cg["events_local"][k] for k in ("oom", "oom_kill", "max")),
            "E20 cap",
        )
    e = pair["energy"](samples, mon["elapsed_s"])
    pw = [s["gpu"]["power_w"] for s in samples if s["gpu"]["power_w"] is not None]
    e.update(
        power_min_w=min(pw, default=None),
        power_max_w=max(pw, default=None),
        time_weighted_mean_gpu_w=e["estimated_gpu_j"] / e["covered_s"] if e["covered_s"] else None,
        method="trapezoids_between_observed_GPU_samples",
        host_energy_j=None,
    )
    popen = begin["popen_invoked_monotonic_ns"] / 1e9
    need(
        math.isclose(client["ready_monotonic"] - popen, receipt["ready_s"], abs_tol=1e-8)
        and client["readiness_after_popen_s"] == receipt["ready_s"]
        and 0 < receipt["ready_s"] <= 30,
        "client ready/popen clock",
    )
    return dict(
        energy=e,
        monitor_sha256=receipt["monitor_sha256"],
        sample_sha256=sha(sample_file),
        maxima=mon["maxima"],
        native_monitor_elapsed_s=mon["elapsed_s"],
        ready_s=receipt["ready_s"],
        envelope_s=receipt["envelope_s"],
        cgroup_cap_bytes=CAP,
        preventive_stop_bytes=STOP,
        start_inventory_sha256=inv["sha256"],
        start_window_span_s=inv["duration_s"],
        start_window_age_at_popen_s=age,
        server_exitcode=mon["returncode"],
        cleanup=receipt["cleanup"],
        unit_closed=True,
        port_available=True,
    )


def shutdown_clock(cut_ns, marks):
    begin, end = marks["sigint_before_ns"], marks["sigint_after_ns"]
    exit_ns, clean_ns = marks["pidfd_exit_observed_ns"], marks["server_port_scope_verified_ns"]
    need(
        all(type(t) is int for t in (cut_ns, begin, end, exit_ns, clean_ns))
        and 0 < cut_ns <= begin <= end <= clean_ns
        and begin <= exit_ns <= clean_ns,
        "shutdown witness chronology",
    )
    # poll() can wake after delivery and before killpg() has returned.
    return dict(
        sigint_invocation_s=(end - begin) / 1e9,
        sigint_to_pidfd_observation_lower_s=max(0, exit_ns - end) / 1e9,
        sigint_to_pidfd_observation_upper_s=(exit_ns - begin) / 1e9,
        pidfd_observation_to_verified_cleanup_s=(clean_ns - exit_ns) / 1e9,
        post_client_to_verified_cleanup_s=(clean_ns - cut_ns) / 1e9,
    )


def transport_summary(root, receipt, traces, checked, terminals, digest):
    if digest == "8825a62338b9aebf913b3dc676dfb5b17ffa98885604e5f12091a3d47cae5f3a":
        return dict(mode="HISTORICAL_FIXTURE_ONLY", shutdown=None)
    t = receipt["transport"]
    mode = t["mode"]
    base = run_path(HERE.parents[1] / "capture_profile/screen.py")
    pid = receipt["native_ids"]["pid"]
    provider = base["C269"] if mode == "R" else base["C291"]
    need(
        mode in ("R", "O", "P")
        and t["libllama"]["sha256"] == provider
        and receipt["trajectories"] == traces,
        "transport selection and work",
    )
    before, after = t["cuts"]
    for c, tag, stamp in (
        (before, "READY_BEFORE_FIRST_POST", "first-client-map.json"),
        (after, "AFTER_SECOND_ACCEPT_BEFORE_STOP", "last-client-map.json"),
    ):
        live = read(root / stamp)
        need(
            c["point"] == live["point"] == tag
            and c["identity"]["pid"] == live["pid"] == pid
            and live["mapped_sha256"]["libllama.so.0.0.9884"] == provider,
            "live transport ELF",
        )
        fds = c["fds"]
        need(
            fds["model"]
            and len(fds["pack"]) == int(mode == "P")
            and all(
                f["flags"] & os.O_DIRECT and f["flags"] & os.O_ACCMODE == os.O_RDONLY
                for f in fds["model"] + fds["pack"]
            ),
            "live transport descriptor",
        )
    need(
        before["identity"] == after["identity"]
        and before["fds"] == after["fds"]
        and before["monotonic_ns"] / 1e9
        <= checked[0]["start_s"]
        <= terminals[1]
        <= after["monotonic_ns"] / 1e9,
        "transport cut interval",
    )
    marks = t["shutdown"]
    shutdown = shutdown_clock(after["monotonic_ns"], marks)
    need(
        t["post_client_to_verified_cleanup_ns"]
        == marks["server_port_scope_verified_ns"] - after["monotonic_ns"],
        "cleanup duration",
    )
    return dict(
        mode=mode,
        libllama_sha256=provider,
        shutdown=shutdown,
        model_fds_per_cut=len(before["fds"]["model"]),
        pack_fds_per_cut=len(before["fds"]["pack"]),
    )


def grade_arm(root: Path, receipt: dict, historical_dir: Path) -> dict:
    """Reopen one terminal arm. The caller authenticates the experiment/transport receipt."""
    root, historical_dir = Path(root), Path(historical_dir)
    expected = sha(root / "receipt.json")
    need(
        read(root / "receipt.json") == receipt
        and receipt["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
        and receipt["cleanup"] == CLEAN
        and receipt["model_launches"] == 1
        and 0 < receipt["envelope_s"] <= 650,
        "terminal arm/cleanup",
    )
    history_seal = native.historic_manifest(historical_dir)
    # This admission also checks the raw stderr, both live ELF samples and PID-bound argv.
    native.capture_log(root, historical_dir, expected)
    preset = pinned(root / "preset.json", receipt["preset_sha256"])
    client = read(root / "client-receipt.json")
    need(
        client["status"] == "CLIENT_TWO_REQUESTS_PASS"
        and client["failure"] is None
        and client["preset_sha256"] == receipt["preset_sha256"],
        "accepted client",
    )
    unit, raw = preset["run_id"], root / "raw"
    need(unit == Path(unit).name and len(list(raw.glob("*.launch.json"))) == 1, "owned launch")
    traces = conv["trajectories"](raw, receipt, historical_dir)
    checked = pair["turns"](raw, receipt)
    rows, counts = [], []
    for i, (g, traj, sm, clocks, complete) in enumerate(
        zip(native.GEOMETRY, traces, receipt["rows"], checked, client["rows"], strict=True), 1
    ):
        full = read(raw / f"T{i}-result.json")
        need(
            full == complete
            and (sm["input_n"], sm["cache_n"], sm["completion_n"]) == g[:3]
            and sm["predicted_n"] == g[2]
            and sm["prompt_n"] == g[0] - g[1]
            and sm["completion"] == "stop"
            and sm["functional"] == sm["prefix"] == "PASS"
            and sm["valid_wall_s"] == full["request_wall_s"]
            and sm["id"] == full["id"]
            and math.isclose(sm["decode_tok_s"], sm["predicted_n"] / sm["decode_s"], rel_tol=1e-7),
            "published turn work/price",
        )
        more = compare_transport(raw, historical_dir, i, full, g)
        counts.append(more.pop("terminal_monotonic_s"))
        rows.append(
            dict(
                label=f"T{i}",
                id=sm["id"],
                input_n=g[0],
                official_ids_sha256=sm["official_ids_sha256"],
                **{
                    k: v
                    for k, v in clocks.items()
                    if k not in ("start_s", "end_s", "valid_wall_s", "transport_s")
                },
                **more,
                **traj,
                prefix=sm["prefix"],
                functional=sm["functional"],
                completion="stop",
            )
        )
    need(counts[0] <= checked[1]["start_s"], "T2 before T1 validation")
    sc = monitor_summary(root, receipt, unit, client)
    transport = transport_summary(root, receipt, traces, checked, counts, expected)
    return dict(
        status="PASS_REVIEWED_TWO_NATURAL_TURNS",
        receipt_sha256=expected,
        historical_manifest_sha256=history_seal,
        historical_sha256=native.HISTORICAL,
        verified_ids_sha256=conv["VERIFIED"],
        stderr_sha256=receipt["native_ids"]["stderr_sha256"],
        rows=rows,
        trajectories=traces,
        model_launches=1,
        requests=2,
        interturn_after_validated_s=checked[1]["start_s"] - counts[0],
        t2_first_final_le_10s=rows[1]["first_final_s"] <= 10,
        t2_decode_ge_6=rows[1]["decode_tok_s"] >= 6,
        transport=transport,
        **sc,
    )

"""Audit the four physical controls and partition native decode time at matched output positions."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
R = run_path(str(HERE / "report.py"))
H, G, need, sha, save = (R[k] for k in ("H", "G", "need", "sha", "save"))
SERVER = R["SERVER"]
FAMILY = "8e52a3e200fa03d005f4b25a036a3860ece0f359d42f38d0166e900fa6d655ae"
PREPARED = "96fff2c7ab0116b6948766acead2c781d8fa2cc6c7196154812facd08fcf74c2"


def elapsed_us(clock):
    minute, sec, millis, micros = clock
    return ((minute * 60 + sec) * 1000 + millis) * 1000 + micros


def ticks(root, index):
    preset = H["read"](root / "preset.json")
    raw = root / "raw"
    log = (raw / (preset["run_id"] + ".stderr")).read_bytes()
    stream = list(H["T"]["V"]["events"](log))
    tasks = [task for _, task, e in stream if e[0] == "start"]
    samples = [
        (elapsed_us(t), e) for t, task, e in stream if task == tasks[index - 1] and e[0] == "sample"
    ]
    pieces = [log[e[4] : log.index(b"'\n", e[4])] for _, e in samples]
    deltas = []
    for line in (raw / f"T{index}-request.jsonl").read_bytes().splitlines():
        frame = json.loads(line)
        if frame["kind"] != "SSE_FRAGMENT":
            continue
        fragment = frame["fragment"]
        if not fragment.startswith("data: ") or fragment[6:].strip() == "[DONE]":
            continue
        for item in json.loads(fragment[6:]).get("choices", []):
            value = item["delta"].get("content")
            if value:
                deltas.append(value.encode())
    boundary = run_path(str(H["Q"] / "history_lookup/packed_step_budget/screen.py"))["text_cut"](
        pieces, deltas
    )
    return [t for t, _ in samples], boundary


def position_cost(plans, on, off, cut):
    need(
        len(on) == len(off)
        and all(
            x <= y for series in (on, off) for x, y in zip(series[:-1], series[1:], strict=True)
        ),
        "complete monotone producer positions",
    )
    groups = {}
    next_position = 1
    oracle_gain = 0
    early_gain = 0
    for step in plans:
        at = step["at"]
        count = step["emitted"]
        end = at + count - 1
        block = bool(step["proposal"])
        need(
            at == next_position and count == step["accepted"] + 1 and end < len(on),
            "closed output group",
        )
        key = "B" + str(step["accepted"]) if block else "AR"
        row = groups.setdefault(key, dict(groups=0, confirmed=0, on_us=0, off_us=0, lower_on=0))
        left = on[end] - on[at - 1]
        right = off[end] - off[at - 1]
        need(left > 0 and right > 0, "positive producer interval")
        row["groups"] += 1
        row["confirmed"] += count
        row["on_us"] += left
        row["off_us"] += right
        row["lower_on"] += int(left < right)
        if block:
            oracle_gain += max(right - left, 0)
            if cut is not None and at <= cut:
                to = min(end, cut)
                early_gain += max((off[to] - off[at - 1]) - (on[to] - on[at - 1]), 0)
        next_position = end + 1
    need(
        next_position == len(on)
        and sum(g["on_us"] for g in groups.values()) == on[-1] - on[0]
        and sum(g["off_us"] for g in groups.values()) == off[-1] - off[0],
        "native-time conservation",
    )
    return dict(
        groups=groups,
        confirmed_intervals=next_position - 1,
        on_span_us=on[-1] - on[0],
        off_span_us=off[-1] - off[0],
        conditional_oracle_saving_us_at_priced_blocks=oracle_gain,
        first_final_sample_one_based=None if cut is None else cut + 1,
        conditional_oracle_saving_before_final_us=None if cut is None else early_gain,
    )


def inputs_agree(prepared, actual, mode):
    first = H["read"](prepared / mode / "arm-inputs.json")
    second = H["read"](actual / mode / "arm-inputs.json")
    for record in (first, second):
        env = record["env"].copy()
        path = Path(env.pop("LD_DEBUG_OUTPUT"))
        need(path.parts[-3:] == (mode, "raw", "loader"), "observed arm trace path")
        record["env"] = env
    need(first == second, "prepared input mismatch")


def review(a):
    p = R["reopen"](a.prepared, PREPARED)
    family = R["reopen"](a.family, FAMILY)
    need(
        p["commit"] == family["commit"]
        and p["status"] == "PREPARED_FOUR_ARMS"
        and family["status"] == "GO_FOUR_NATURAL_DIAGNOSTICS"
        and family["model_starts"] == 4
        and family["started_requests"] == 8
        and family["report_fixture_sha256"] == SERVER["REPORT_FIXTURE"]
        and family["report_protocol_sha256"] == R["METHOD"],
        "four-arm authority",
    )
    data, steps = R["cases"](a)
    arms = {}
    for mode in H["MODES"]:
        root = a.family / mode
        inputs_agree(a.prepared, a.family, mode)
        child = R["reopen"](root, family["arms"][mode]["sha256"])
        evidence = R["observe"](root, mode, data, steps)
        closed = H["read"](root / "closed-session.json")
        proof = H["read"](root / "runtime-proof.json")
        need(
            all(closed[k] == child[k] for k in closed)
            and child["runtime_authority"] == proof
            and child["client_rows"] == evidence["rows"]
            and proof["trajectories"] == evidence["trajectories"]
            and child["energy"] == evidence["energy"]
            and child["model_starts"] == 1
            and child["started_requests"] == 2
            and child["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE"
            and child["maxima"] == evidence["maxima"]
            and len(proof["cuts"]) >= 4
            and child["nominal_first_final_le_10s"] == (evidence["rows"][1]["first_final_s"] <= 10)
            and child["nominal_decode_ge_6"] == (evidence["rows"][1]["decode_tok_s"] >= 6),
            "closed turn, controller and live evidence",
        )
        evidence.update(
            scope_s=child["wall_s"],
            readiness_s=child["ready_s"],
            cleanup=child["cleanup"],
            post_signal_ms=(proof["verified_cleanup_ns"] - proof["signal"]["after_ns"]) / 1e6,
            live_cuts=len(proof["cuts"]),
            c55_age_s=proof["c55_age_at_spawn_s"],
        )
        arms[mode] = evidence
    positions = {}
    for i in (1, 2):
        key = "T" + str(i)
        on, on_cut = ticks(a.family / "ON", i)
        off, off_cut = ticks(a.family / "OFF", i)
        cut = off_cut if off_cut == on_cut else None
        stats = position_cost(steps[key], on, off, cut)
        stats["conditional_best_first_final_s"] = (
            None
            if cut is None
            else arms["OFF"]["rows"][i - 1]["first_final_s"]
            - stats["conditional_oracle_saving_before_final_us"] / 1e6
        )
        stats["on_server_minus_native_ms"] = (
            arms["ON"]["rows"][i - 1]["decode_s"] * 1000 - stats["on_span_us"] / 1000
        )
        stats["off_server_minus_native_ms"] = (
            arms["OFF"]["rows"][i - 1]["decode_s"] * 1000 - stats["off_span_us"] / 1000
        )
        stats["conditional_best_decode_s"] = (
            arms["OFF"]["rows"][i - 1]["decode_s"]
            - stats["conditional_oracle_saving_us_at_priced_blocks"] / 1e6
        )
        stats["conditional_prefill_s_for_ten_s_if_best_priced_blocks"] = (
            None
            if i != 2 or cut is None
            else arms["OFF"]["rows"][i - 1]["prefill_s"]
            + 10
            - stats["conditional_best_first_final_s"]
        )
        positions[key] = stats
    cooldowns = {}
    for mode in ("ON", "OFF", "P"):
        c = H["read"](a.family / (mode + "-closed-endpoint.json"))
        need(c["bind_available"] and c["previous"] == mode, "strict port transition")
        cooldowns[mode] = c["elapsed_s"]
    return dict(
        status=family["status"],
        commit=family["commit"],
        family_sha256=FAMILY,
        prepared_sha256=PREPARED,
        method_sha256=family["protocol_sha256"],
        reporting_protocol_sha256=R["METHOD"],
        arm_order=H["MODES"],
        model_starts=4,
        requests=8,
        wall_s=family["wall_s"],
        port_wait_s=cooldowns,
        arms=arms,
        positions=positions,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("prepared", "family", "capture", "verified", "plan", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    save(a.new_output_dir / "result.json", review(a))

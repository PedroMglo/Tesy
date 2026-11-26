"""Reopen a natural server pilot, including failed requests, without running inference."""

import argparse
import json
import math
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE / "session.py"))
P = S["P"]
need, sha, read = S["need"], S["sha"], S["load"]


def trace(folder, index, result, first_answer):
    raw = folder / "raw"
    x = read(raw / f"T{index}-input.json")
    path = raw / f"T{index}-request.jsonl"
    lines = [json.loads(line) for line in path.read_bytes().splitlines()]
    need(
        lines[0]["kind"] == "REQUEST_START"
        and all(
            a["monotonic_s"] <= b["monotonic_s"] for a, b in zip(lines, lines[1:], strict=False)
        ),
        "request clock",
    )
    starts = result["request_started_monotonic"]
    messages = {"reasoning_content": [], "content": []}
    spans = {}
    for j, row in enumerate(lines):
        if row["kind"] != "SSE_FRAGMENT" or not row["fragment"].startswith("data: "):
            continue
        event = row["fragment"][6:].strip()
        if event == "[DONE]":
            continue
        for c in json.loads(event)["choices"]:
            delta = c.get("delta", {})
            for k in messages:
                piece = delta.get(k)
                if piece:
                    messages[k].append(piece)
                    if piece.strip() and k not in spans:
                        spans[k] = [
                            row["monotonic_s"] - starts,
                            lines[j + 1]["monotonic_s"] - starts,
                        ]
    for field, key in (
        ("content", "first_final_content_chunk_s"),
        ("reasoning_content", "first_reasoning_chunk_s"),
    ):
        v = result["stream_metrics"][key]
        need(
            "".join(messages[field]) == result["message"].get(field, "")
            and spans[field][0] - 1e-7 <= v <= spans[field][1] + 1e-7,
            "SSE content or clock",
        )
    original = read(raw / f"T{index}-native-accounting.json")
    need(
        P["normalize"](original["usage"], original["timings"], len(x["official_ids"]))
        == result["timings"]
        and original["usage"] == result["usage"]
        and S["client"].grade(index - 1, result["message"]["content"], first_answer),
        "native usage or validator",
    )
    return S["summarize"](result, raw, index)


def review(a):
    folder = a.family
    r = P["receipt"](folder / "receipt.json", a.family_sha256)
    raw = folder / "raw"
    files = {
        str(p.relative_to(folder)): sha(p)
        for p in folder.rglob("*")
        if p.is_file() and p != folder / "receipt.json"
    }
    need(files == r["raw_sha256"], "raw inventory")
    preset = read(folder / "preset.json")
    need(
        sha(folder / "preset.json") == r["preset_sha256"] and preset["build_sha256"] == P["BUILD"],
        "build/command",
    )
    pilot = read(raw / (r["unit"] + ".json")) if (raw / (r["unit"] + ".json")).exists() else {}
    result = dict(
        status=r["status"],
        family_sha256=a.family_sha256,
        commit=r["commit"],
        tree=r["tree"],
        build_sha256=preset["build_sha256"],
        model_sha256=preset["model_sha256"],
        window_sha256=preset["window_sha256"],
        generation_requests=r["generation_requests"],
        model_starts=r["model_starts"],
        energy_J=None,
        pages_before_C118=r.get("file_pages_before_C118"),
        monitor_reason=pilot.get("stop_reason"),
        maxima=pilot.get("maxima"),
        unit_end=r.get("unit_end"),
        rows=[],
        native_summary=r.get("native_summary"),
    )
    if (folder / "client-receipt.json").exists():
        client = read(folder / "client-receipt.json")
        control = S["CON"]["C281"] / "protocol.json"
        need(sha(control) == preset["workload_sha256"], "frozen workload")
        tasks = read(control)["tasks"]
        first = None
        for i, row in enumerate(client["rows"], 1):
            if not row["accepted"]:
                break
            inp = read(raw / f"T{i}-input.json")
            expected = (
                tasks[0]["messages"]
                if i == 1
                else S["client"].assistant_history_messages(
                    tasks[0]["messages"], first, tasks[1]["messages"]
                )
            )
            need(
                inp["messages"] == expected and inp["official_ids"] == row["official_ids"],
                "natural history chain",
            )
            result["rows"].append(
                trace(folder, i, row, None if first is None else first["content"])
            )
            if i == 1:
                first = row["message"]
        result["client_status"] = client["status"]
        result["client_failure"] = client.get("failure")
        result["ready_s"] = client["readiness_after_popen_s"]
    if r["status"] == "TWO_NATURAL_TURNS":
        need(
            len(result["rows"]) == 2
            and result["rows"] == r["rows"]
            and r["child_gone"]
            and pilot["returncode"] == pilot["maxima"]["swap_bytes"] == 0
            and pilot["stop_reason"] == "INTERRUPTED_BY_OWNER",
            "natural or cleanup gates",
        )
        t1, t2 = result["rows"]
        nominal = [x["official_ids_sha256"] for x in (t1, t2)] == preset["official_ids"] and (
            t1["cached"],
            t1["evaluated"],
            t2["cached"],
            t2["evaluated"],
        ) == (0, 2043, 2044, 153)
        need(
            nominal == r["nominal"]
            and math.isfinite(t2["first_final_s"])
            and t2["decode_tok_s"] > 0,
            "nominal condition",
        )
        result["nominal"] = nominal
        if nominal:
            result["distance"] = dict(
                first_final_excess_s=t2["first_final_s"] - 10,
                decode_shortfall_tok_s=6 - t2["decode_tok_s"],
            )
            result["meets_nominal"] = t2["first_final_s"] <= 10 and t2["decode_tok_s"] >= 6
        result["decision"] = "GO_PAIRED_ATTRIBUTION" if nominal else "INCONCLUSIVE_NOMINAL_GEOMETRY"
    else:
        need(r["status"] == "FAIL_PRESERVED", "unknown outcome")
        result["decision"] = "FAIL_PRESERVED"
        result["failure"] = r.get("error")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = review(a)
    S["save"](a.new_output_dir / "result.json", result)
    print(result["decision"])

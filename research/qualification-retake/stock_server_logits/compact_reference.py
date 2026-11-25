"""Compare only C110 position 15 between two authenticated stock E10 runs."""

import argparse
import json
import re
import resource
import signal
import subprocess
from pathlib import Path

from compare import STOCK, bounded, summarize, verified_row
from inputs import PACKED_18_SHA, VOCAB, digest, load_prompt, require

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "stock_numeric"
PROTOCOL_SHA = "b1aba878f7c590f0ff0c9a6a49aa556cbc89733a1c0d3d03e6bf15f26bd5e22b"
OLD_RECEIPT_SHA = "ebd19afb495957175eedc994a3fa35a069d17d135a3f82c14df62ac16e88715a"
S_RECEIPT_SHA = "4f20993fe15969cedea0ae78cb84da292f81244bd418f6ba3c80a3136a27fab3"
MODEL_SHA = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
PAYLOAD_SHA = "df15a25bfec9c498bbb8bdaf111b14228912d85c1cd4ebb053784cf77bfa05ec"
BUILD_SHA = "c19b653c8980a88bcc18495ca77fa7482d129bae6f215fd530a4f15dcdd4717f"
ROW_BYTES = 4 * VOCAB
STATUS = "PASS_DIAGNOSTIC_BITWISE_POSITION_15"
LIMITS = [
    "different_client_and_SWA_geometry",
    "observer_only_in_HTTP_server",
    "same_position_only",
    "no_attribution_to_SWA_or_observer",
    "no_E20_or_product_qualification",
]


def pinned(path, expected, max_size):
    data = bounded(path, max_size)
    require(digest(data) == expected, "source identity: " + path.name)
    return data


def select_first_row(data, expected_sha, *, width=VOCAB):
    size = 4 * width
    require(
        len(data) == 3 * size and digest(data) == expected_sha, "entire three-row historical object"
    )
    return data[:size]


def historical(raw_parent):
    r = json.loads(pinned(OLD / "physical-r1/receipt.json", OLD_RECEIPT_SHA, 1 << 20))
    build = json.loads(pinned(OLD / "build-r2/receipt.json", BUILD_SHA, 1 << 20))
    pinned(OLD / "client.cpp", build["source_sha256"], 1 << 20)
    pinned(OLD / "run.py", r["runner_sha256"], 1 << 20)
    pinned(OLD / "protocol.md", r["protocol_sha256"], 1 << 20)
    require(
        r["status"] == "FINITE_DIFFERENT_BITS_PARITY_INCONCLUSIVE"
        and r["scope"] == "SUPPLIED_C110_16_1_1"
        and r["client_starts"] == 1
        and r["child_gone"] is True
        and r["client_returncode"] == 0
        and r["build_receipt_sha256"] == BUILD_SHA
        and r["client_sha256"] == build["executable_sha256"]
        and build["own_libraries"]["libllama.so.0"] == STOCK
        and build["protocol_sha256"] == r["protocol_sha256"]
        and r["c118"]["cap_bytes"] == 10 * 2**30
        and r["swap_current"] == 0
        and r["model_sha256"] == MODEL_SHA
        and r["input_sha256"] == PACKED_18_SHA
        and r["sha256"] == r["raw_sha256"]["candidate.logits.f32"] == PAYLOAD_SHA,
        "historical run or model",
    )
    raw = raw_parent / "raw"
    log = pinned(raw / "client.log", r["raw_sha256"]["client.log"], 1 << 20).decode(
        errors="replace"
    )
    require(
        log.count("STOCK_NUMERIC_READY probe=common_context_can_seq_rm") == 1
        and re.findall(r"STOCK_NUMERIC_ROW begin=(\d+) count=(\d+) last=(\d+) n=(\d+)", log)
        == [("0", "16", "15", "201088"), ("16", "1", "16", "201088"), ("17", "1", "17", "201088")]
        and "non-SWA KV cache, size = 8192 cells" in log
        and re.search(r"creating\s+SWA KV cache, size = 256 cells", log)
        and "warming up the model" not in log,
        "historical row positions, startup probe or SWA",
    )
    data = bounded(raw / "candidate.logits.f32", 3 * ROW_BYTES)
    return r, build, select_first_row(data, PAYLOAD_SHA)


def check_pair(s, h, build, prompt):
    flags = {"full_kv", "full_swa_mode", "swa_kv", "group", "slot", "ready"}
    require(
        s["arm"] == "S"
        and s["warmup_requested"] is False
        and s["model"]["sha256"] == h["model_sha256"] == MODEL_SHA
        and s["build_receipt_sha256"] == build["stock_build_receipt_sha256"]
        and s["stock_libllama_sha256"] == s["active_libllama_sha256"] == STOCK
        and s["cap_bytes"] == h["c118"]["cap_bytes"]
        and s["scope"] == "FULL_SWA_C110_FIRST_16_SINGLE_GREEDY_TOKEN"
        and all(s["ready_log_geometry"][k] is True for k in flags)
        and all(
            s["ready_vma"][k] is True
            for k in (
                "observer_present",
                "gguf",
                "active_libllama_present",
                "other_libllama_absent",
            )
        )
        and set(build["own_libraries"]) <= set(s["mapped_own_libraries"])
        and all(s[k] == v for k, v in prompt.items())
        and h["input_sha256"] == prompt["packed_18_ids_sha256"],
        "cross-run identity/geometry",
    )


def audit(a):
    pinned(HERE / "compact-reference.md", PROTOCOL_SHA, 1 << 20)
    pinned(a.stock_report / "receipt.json", S_RECEIPT_SHA, 1 << 20)
    _, prompt = load_prompt(a.c110_raw)
    s, server_row = verified_row(a.stock_report, a.stock_raw_parent)
    h, build, client_row = historical(a.historical_raw_parent)
    check_pair(s, h, build, prompt)
    diff = summarize(client_row, server_row)
    require(diff["finite_gold"] and diff["finite_candidate"], "nonfinite position 15")
    return dict(
        status=STATUS if diff["bitwise_equal"] else "DIAGNOSTIC_DIFFERENT_BITS_POSITION_15",
        comparison=diff,
        position=15,
        row_bytes=ROW_BYTES,
        vocab=VOCAB,
        full_swa=dict(
            server_receipt_sha256=S_RECEIPT_SHA,
            measurement_commit=s["measurement_commit"],
            measurement_tree=s["measurement_tree"],
            server_sha256=s["server_sha256"],
            capture_sha256=s["capture_sha256"],
            observer_sha256=s["observer_sha256"],
            request_sha256=s["request_sha256"],
            cache_n=s["after_ready"]["cache_n"],
        ),
        compact_swa=dict(
            client_receipt_sha256=OLD_RECEIPT_SHA,
            client_sha256=h["client_sha256"],
            raw_three_rows_sha256=PAYLOAD_SHA,
            raw_three_rows_bytes=3 * ROW_BYTES,
            client_build_receipt_sha256=BUILD_SHA,
            client_source_sha256=build["source_sha256"],
            probe="common_context_can_seq_rm",
            calls=[16, 1, 1],
        ),
        shared=dict(
            stock_build_receipt_sha256=s["build_receipt_sha256"],
            stock_pin=build["pin"],
            gguf_sha256=MODEL_SHA,
            libllama_sha256=STOCK,
            cap_bytes=s["cap_bytes"],
            **prompt,
        ),
        limits=LIMITS,
    )


def revision(*params):
    return subprocess.check_output(
        [
            "git",
            "--no-optional-locks",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            *params,
        ],
        cwd=HERE,
        text=True,
        timeout=10,
    ).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in (
        "stock-report",
        "stock-raw-parent",
        "c110-raw",
        "historical-raw-parent",
        "new-output-dir",
    ):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)

    def expired(sig, frame):
        raise TimeoutError("30s unit budget")

    result = {
        "status": "FAIL_PRESERVED",
        "scope": "TRACE_DERIVED_STOCK_CROSS_CLIENT_POSITION_15",
        "protocol_sha256": PROTOCOL_SHA,
        "program_sha256": digest(Path(__file__).read_bytes()),
    }
    try:
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(30)
        current, hard = resource.getrlimit(resource.RLIMIT_AS)
        soft = min(x for x in (current, hard, 256 << 20) if x != resource.RLIM_INFINITY)
        resource.setrlimit(resource.RLIMIT_AS, (soft, hard))
        result.update(
            measurement_commit=revision("rev-parse", "HEAD"),
            measurement_tree=revision("rev-parse", "HEAD^{tree}"),
        )
        require(not revision("status", "--porcelain"), "dirty measurement checkout")
        result.update(audit(a))
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        MemoryError,
        subprocess.SubprocessError,
    ) as exc:
        result["error"] = str(exc)
    finally:
        signal.alarm(0)
    contents = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    require(len(contents) <= 1 << 20, "output budget")
    pending = a.new_output_dir / "receipt.pending"
    with pending.open("xb") as f:
        f.write(contents)
    pending.rename(a.new_output_dir / "receipt.json")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

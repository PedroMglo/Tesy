"""Reopen the aborted first import and locate the guard before any target decode."""

import argparse
import math
import re
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = run_path(str(HERE / "family.py"))
need, sha, read, save = (F[k] for k in ("need", "sha", "read", "save"))
FIRST = "21b98704e311a74db6907cb31fb985fe71f02afd9299f39cec60d1a4fb4b9551"
SECOND = "d3d6cdd5a26ffcc26be4097bf7db627a658f3b1fbac126e914345af0ebbd2ed6"


def distribution(actual, expected):
    need(actual.stat().st_size == expected.stat().st_size == 201088 * 4, "complete vocabulary")
    left, right = (p.read_bytes() for p in (actual, expected))
    a, b = (struct.unpack("<201088f", v) for v in (left, right))
    need(all(map(math.isfinite, a)) and all(map(math.isfinite, b)), "finite vectors")
    delta = [abs(x - y) for x, y in zip(a, b, strict=True)]
    return dict(
        f32_words=len(a),
        different_words=sum(left[j : j + 4] != right[j : j + 4] for j in range(0, len(left), 4)),
        max_abs=max(delta),
        rms=math.sqrt(math.fsum(x * x for x in delta) / len(delta)),
        actual_greedy=F["G"]["choices"](actual)[0],
        reference_greedy=F["G"]["choices"](expected)[0],
        actual_sha256=sha(actual),
        reference_sha256=sha(expected),
    )


def review(a):
    digest = sha(a.family / "receipt.json")
    need(digest in (FIRST, SECOND), "closed import family")
    repaired = digest == SECOND
    protocol, method = F["B"]["contract"](repaired)
    r = F["R"]["reopen"](a.family, digest)
    b = read(a.build / "receipt.json")
    win = read(a.window / "receipt.json")
    need(
        sha(a.build / "receipt.json") == (F["SWA_BUILD"] if repaired else F["BUILD"])
        and sha(a.build / "receipt.json") == r["build_sha256"]
        and sha(a.build / "b3-numeric") == b["elf_sha256"]
        and sha(a.build / "libllama.so.0.0.9884") == b["image_sha256"]
        and (a.build / "rollback.cpp").read_text() == F["B"]["source"](repaired)
        and sha(a.window / "receipt.json") == r["window_sha256"]
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(HERE / protocol) == r["protocol_sha256"] == method
        and r["stage"] == "AR"
        and r["model_starts"] == 1
        and r["status"] == "FAIL_PRESERVED"
        and r["arms"] == {},
        "first failure identity",
    )
    root = a.family / "AR"
    unit = r["unit"] + "-ar"
    raw = root / "raw"
    monitor = read(raw / (unit + ".json"))
    launch = read(raw / (unit + ".launch.json"))
    log = (raw / (unit + ".stderr")).read_text()
    capture = F["capture"](a.family, r["unit"], "AR")
    counts = re.findall(r"^state_read_meta: cell_count = (\d+), dest_seq_id = 0$", log, re.M)
    error = "calibration logits" if repaired else "KV positions"
    names = {"initial.kv", "cal-decode0.logits.f32"} if repaired else set()
    need(
        counts == ["189", "128"]
        and log.strip().endswith("ROLLBACK_FAIL " + error)
        and {p.name for p in capture.iterdir()} == names
        and monitor["returncode"] == 1
        and monitor["stop_reason"] is None
        and monitor["maxima"]["swap_bytes"] == 0
        and monitor["binary_sha256"] == b["elf_sha256"]
        and monitor["process_identity"] == launch["process_identity"]
        and monitor["start_inventory"] == launch["start_inventory"]
        and monitor["cgroup_limit_enforced"]
        and monitor["mapped_libraries_match_ldd"],
        "import without supplied decode",
    )
    module = F["P"]["G"]["probes"].load(
        F["T"]["S"]["QUAL"] / "nvme_r0_gate/qualified_profile/compact.py", "r01_failure_inventory"
    )
    inv = module.validate_inventory(
        root, unit, {"native_explicit_env": monitor["explicit_env"]}, launch
    )
    prior = F["R"]["reopen"](a.target, r["target_sha256"])
    target = F["capture"](a.target, prior["unit"], "CUDA")
    swa = F["SWA"]
    ranges = re.findall(r"^SWA_KV (.+)$", (raw / (unit + ".stdout")).read_text(), re.M)
    need(ranges == (["initial.kv 189 61 188"] if repaired else []), "observed public range")
    comparison = None
    if repaired:
        need(sha(capture / "initial.kv") == sha(target / "initial-kv.bin"), "KV round trip")
        comparison = distribution(capture / "cal-decode0.logits.f32", target / "decode0.logits.f32")
        need(comparison["different_words"] > 0, "calibration difference")
    return dict(
        status="INCONCLUSIVE_CALIBRATION" if repaired else "INCONCLUSIVE_IMPORT_GUARD",
        decision_cases="NOT_RUN",
        model_starts=1,
        supplied_decode_calls=int(repaired),
        native_error=error,
        public_min_observed=61 if repaired else None,
        public_max_observed=188 if repaired else None,
        calibration_row=comparison,
        bank_cell_counts_imported=list(map(int, counts)),
        serialized_input=swa["contents"](target / "initial-kv.bin", 189, swa["banks"](target)),
        commit=r["commit"],
        tree=r["tree"],
        build_sha256=r["build_sha256"],
        elf_sha256=b["elf_sha256"],
        library_sha256=b["image_sha256"],
        parent_sha256=r["target_sha256"],
        input_sha256=sha(target / "initial-kv.bin"),
        family_sha256=digest,
        protocol_sha256=r["protocol_sha256"],
        resource_window_sha256=r["window_sha256"],
        c118=inv,
        model_s=monitor["elapsed_s"],
        maxima=monitor["maxima"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "build", "window", "target", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = review(a)
    save(a.new_output_dir / "result.json", result)
    print(result["status"])

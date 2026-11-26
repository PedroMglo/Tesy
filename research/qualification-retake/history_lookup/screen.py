"""Literal history-copy acceptance and a conditional AR/B8 cost envelope."""

import argparse
import hashlib
import json
import resource
import signal
import subprocess
import sys
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIXTURE = ROOT / "results/c244-multigrid-continuity-20261004/development-native-inputs.json"
BASE = ROOT / "results/c247-b8-complete-output-amortization-20261004"
PINS = {
    FIXTURE: (64068, "788020f22322bc4a6d90cfdf1e05b3554dd31804c2d72d795e13af9eb9a7754d"),
    BASE / "protocol.json": (
        55009,
        "c1bbcd9d195836f3bf86dfe103545f67ddfaca4c01632835f7140422b5015594",
    ),
    BASE / "result-compact.json": (
        13372,
        "1861ae51b8530fd41b30c66b02e0a5330351f1cf74a4bd777145c66b21e6b556",
    ),
    BASE / "amortization-summary.json": (
        16607,
        "3ffb8e426fc646b730df77daabb678616086abfded3fc05ab2b7f84b0a3a1cd6",
    ),
}
CASES = ("development-code-rle", "development-structured-route", "anchor-nominal153")


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    data = path.read_bytes()
    check((len(data), hashlib.sha256(data).hexdigest()) == PINS[path], "input pin " + path.name)
    return json.loads(data)


def matches(prompt, continuation):
    """Return longest exact prefix and a source entirely available at each step."""
    chain = prompt + continuation
    fence = len(prompt) + 1
    n = len(continuation) - 1
    result = []
    for i in range(n):
        boundary = fence + i
        longest, witness = 0, None
        for start in range(boundary):
            length = 0
            while (
                length < min(7, n - i, boundary - start)
                and chain[start + length] == chain[boundary + length]
            ):
                length += 1
            if length > longest:
                longest, witness = length, start
        result.append((longest, witness))
    return result


def optimize(rows, ar, block, block_only=False):
    """Suffix DP over a DAG on confirmed positions. No text in output."""
    n = len(rows)
    costs, paths = [0.0] * (n + 1), [[] for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        limit, at = rows[i]
        candidates = [(block + costs[j], "B8", j) for j in range(i + 1, min(n, i + limit + 1) + 1)]
        if not block_only:
            candidates.append((ar + costs[i + 1], "AR", i + 1))
        cost, mode, j = min(candidates, key=lambda x: (x[0], x[1] != "AR", -x[2]))
        matched = j - i - 1
        costs[i] = cost
        paths[i] = [
            {
                "p": i,
                "q": j,
                "action": mode,
                "literal_matches_used": matched,
                "source": at if matched else None,
            }
        ] + paths[j]
    return costs[0], paths[0]


def verify_path(actions, prompt, continuation, ar, block):
    history = prompt + continuation[:1]
    target = continuation[1:]
    pos, cost = 0, 0.0
    for a in actions:
        end, m, src = a["q"], a["literal_matches_used"], a["source"]
        check(a["p"] == pos < end <= len(target) and 0 <= m == end - pos - 1 <= 7, "action extent")
        check(a["action"] in ("AR", "B8") and (a["action"] == "B8" or m == 0), "action mode")
        check(
            (src is None and m == 0)
            or (
                m
                and type(src) is int
                and 0 <= src
                and src + m <= len(history)
                and history[src : src + m] == target[pos : pos + m]
            ),
            "literal source crosses boundary, changes IDs or is missing",
        )
        history += target[pos:end]
        pos = end
        cost += ar if a["action"] == "AR" else block
    check(pos == len(target), "incomplete output")
    return cost


def raw_summaries(raw, expected):
    # The historical c94 digest covers direct files. If an inventory instead
    # covers nested paths, include every member of that same recorded tree.
    files = sorted(f for f in raw.iterdir() if f.is_file())
    if len(files) != expected["files"]:
        files = sorted(f for f in raw.rglob("*") if f.is_file())
    check(len(files) == expected["files"], "raw tree cardinality")
    hashes = {}
    total = 0
    for f in files:
        name = f.relative_to(raw).as_posix()
        data = f.read_bytes()
        encoded = name.encode()
        hashes[name] = (
            len(encoded).to_bytes(4, "big")
            + encoded
            + len(data).to_bytes(8, "big")
            + hashlib.sha256(data).digest()
        )
        total += len(data)
    digests = {
        hashlib.sha256(b"".join(hashes[name] for name in order)).hexdigest()
        for order in (list(hashes), sorted(hashes))
    }
    check(
        total == expected["total_bytes"] and expected["sha256_name_size_content_v1"] in digests,
        "raw C247 tree digest",
    )
    return set(hashes)


def evaluate(raw):
    fixture, proto = read(FIXTURE), read(BASE / "protocol.json")
    compact, summary = read(BASE / "result-compact.json"), read(BASE / "amortization-summary.json")
    gate = ROOT / "tools/block_amortization_gate.py"
    check(
        hashlib.sha256(gate.read_bytes()).hexdigest()
        == "5094a39733cde5f37d274d0fab9d8890e993410894797da8dc7242ed89ef0d6e",
        "C247 gate",
    )
    spec = proto["timing_contract"]
    check(
        spec["case_order"] == list(CASES)
        and (spec["B"], spec["K"], spec["positions_per_arm"], spec["full_logits_rows"])
        == (8, 7, 32, 32),
        "scope or geometry",
    )
    check(
        summary["status"] == "GO_A1_COMPLETE_BLOCK_AMORTIZATION"
        and [c["case"] for c in summary["classes"]] == list(CASES),
        "C247 pair results",
    )
    refs = {x["id"]: x for x in compact["arms"]}
    check(len(refs) == 12, "arm roster")
    members = raw_summaries(raw, compact["raw_tree"]) if raw else set()
    cases = {}
    for c in summary["classes"]:
        case = c["case"]
        prompt, tokens = fixture[case]["ids"], fixture[case]["continuation_ids"][:33]
        check(
            prompt
            and len(tokens) == 33
            and all(type(t) is int and 0 <= t < 201088 for t in prompt + tokens),
            "invalid frozen IDs",
        )
        row = matches(prompt, tokens)
        count, verify_only = optimize(row, 0, 1, True)
        check(verify_path(verify_only, prompt, tokens, 0, 1) == count, "B8-only witness")
        pairs = []
        for (a, b), pair in zip(((1, 2), (4, 3)), c["pairs"], strict=True):
            control, variant = [refs[f"c247-{case}-{i}"] for i in (a, b)]
            check(
                (control["mode"], variant["mode"]) == ("ar", "block")
                and control["initial_sha256"] == variant["initial_sha256"]
                and control["wall_s"] == pair["control_s"]
                and variant["wall_s"] == pair["block_s"]
                and pair["argmax_rows"] == pair["cross_shape_argmax_equal"] == 32,
                "pair proof",
            )
            if raw:
                for arm in (control, variant):
                    summary_name = arm["id"] + ".native.timing-summary.json"
                    check(summary_name in members, "unauthenticated timing summary")
                    z = json.loads((raw / summary_name).read_bytes())
                    native = raw / (arm["id"] + ".native")
                    native_members = raw_summaries(native, z["raw_tree"])
                    check("result.json" in native_members, "unauthenticated native result")
                    original = json.loads((native / "result.json").read_bytes())
                    check(
                        original["official_prefix_ids"] == prompt
                        and original["native_teacher_forced_inputs"] == tokens[:32]
                        and original["native_argmax_ids"] == tokens[1:]
                        and original["complete_logit_rows"] == 32,
                        "native teacher-forced work or argmax",
                    )
                    check(
                        z["case"] == case
                        and z["mode"] == arm["mode"]
                        and z["positions"] == 32
                        and z["native_argmax_ids"] == tokens[1:]
                        and z["wall_s"] == arm["wall_s"]
                        and z["initial_sha256"] == arm["initial_sha256"],
                        "native R0/B8 IDs",
                    )
            ar, block = pair["T_AR_s"], pair["V_B_s"]
            check(ar == control["wall_s"] / 32 and block == variant["wall_s"] / 4, "timing units")
            cost, path = optimize(row, ar, block)
            check(abs(cost - verify_path(path, prompt, tokens, ar, block)) < 1e-8, "hybrid witness")
            n_ar = sum(step["action"] == "AR" for step in path)
            n_b8 = len(path) - n_ar
            paid = n_ar * ar + n_b8 * block
            check(abs(cost - paid) < 1e-8, "hybrid action accounting")
            pairs.append(
                {
                    "AR_arm": control["id"],
                    "B8_arm": variant["id"],
                    "AR32_s": 32 * ar,
                    "four_B8_s": 4 * block,
                    "T_AR_s": ar,
                    "V_B_s": block,
                    "hybrid_s": paid,
                    "AR_calls": n_ar,
                    "B8_calls": n_b8,
                    "gain_percent": 100 * ((32 - n_ar) * ar - n_b8 * block) / (32 * ar),
                    "charged_rows": sum(1 if x["action"] == "AR" else 8 for x in path),
                    "actions": path,
                }
            )
        gains = [z["gain_percent"] for z in pairs]
        cases[case] = {
            "history_ids_before_anchor": len(prompt),
            "next_target_ids": 32,
            "max_match_by_p": [n for n, _ in row],
            "minimum_B8_verifications": int(count),
            "B8_only_witness": verify_only,
            "pairs": pairs,
            "median_gain_percent": median(gains),
            "passes_economics": min(gains) > 0 and median(gains) >= 15,
        }
    go = all(cases[c]["passes_economics"] for c in CASES[:2])
    return {
        "status": "GO_CAUSAL_FIXTURE_ONLY" if go else "NO_GO_LITERAL_FIXED_B8_COST",
        "argmax_evidence": "DIRECT_PRIVATE_ALL_12"
        if raw
        else "SEALED_C247_GATE_AND_ALL_SIX_32_OF_32_PAIRS",
        "next_causal_control": (
            "Only if separately prefrozen: match the last three confirmed IDs "
            "to the latest earlier triple, copy its following seven fully "
            "historical IDs or use AR, and verify with the target."
        )
        if go
        else None,
        "C247_raw_tree": compact["raw_tree"],
        "inputs": {f.name: sha for f, (_, sha) in PINS.items()},
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    a = parser.parse_args()
    dest = a.new_output_dir.resolve()
    check(not a.raw_dir or not dest.is_relative_to(a.raw_dir.resolve()), "protect raw")
    cap = 512 << 20
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (min(cap, hard) if hard >= 0 else cap, hard))

    def expired(*_):
        raise TimeoutError("120s envelope")

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(120)
    dest.mkdir(mode=0o700)
    meta = {}

    def git(*args):
        return subprocess.check_output(
            ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1", *args],
            cwd=HERE,
            text=True,
        ).strip()

    try:
        meta.update(
            commit=git("rev-parse", "HEAD"),
            tree=git("rev-parse", "HEAD^{tree}"),
            clean=not git("status", "--porcelain=v1", "--untracked-files=normal"),
            program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            protocol_sha256=hashlib.sha256((HERE / "protocol.md").read_bytes()).hexdigest(),
        )
        check(meta["clean"], "dirty checkout")
        result = evaluate(a.raw_dir)
    except (
        ValueError,
        OSError,
        KeyError,
        IndexError,
        TypeError,
        MemoryError,
        subprocess.CalledProcessError,
    ) as e:
        result = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(e, FileNotFoundError)
            else "FAIL_PRESERVED",
            "error": str(e),
        }
    blob = json.dumps({**meta, **result}, sort_keys=True, indent=2, allow_nan=False) + "\n"
    check(len(blob.encode()) < 8 << 20, "output budget")
    temp = dest / ".pending"
    with temp.open("x") as handle:
        handle.write(blob)
    temp.rename(dest / "receipt.json")
    print(result["status"])
    return int("cases" not in result)


if __name__ == "__main__":
    sys.exit(main())

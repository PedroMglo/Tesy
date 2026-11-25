"""Price the frozen proposals up to formation of the first final-text delta in a sealed pack arm."""

import argparse
import hashlib
import json
import math
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
IDS = HERE.parent / "native_ids"
EXPECTED = (23, 11, 12)
INTRO = [b"<|end|>", b"<|start|>", b"assistant", b"<|channel|>", b"final", b"<|message|>"]


def check(ok, error):
    if not ok:
        raise ValueError(error)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, sha):
    raw = path.read_bytes()
    check(digest(raw) == sha, path.name)
    return json.loads(raw)


def module(path, sha):
    check(digest(path.read_bytes()) == sha, path.name)
    return run_path(path)


def text_cut(pieces, deltas):
    hits = [j for j in range(len(pieces)) if pieces[j : j + len(INTRO)] == INTRO]
    if len(hits) != 1 or pieces[-1] != b"":
        return None
    begin = hits[0] + len(INTRO)
    final_pieces = pieces[begin:-1]
    if not deltas or final_pieces != deltas or any(not s.strip() for s in final_pieces):
        return None
    return begin


def budget(labels, ticks, end, final_ns, native_ns):
    elapsed = [(b - a) * 1000 for a, b in zip(ticks[:-1], ticks[1:], strict=True)]
    check(len(elapsed) == len(labels) and all(n > 0 for n in elapsed), "tick order/coverage")
    cols = ("ar", "anchor", "skip")
    lengths = [labels.count(code) for code in cols]
    check(tuple(lengths) == EXPECTED, "frozen action counts")
    sums = [sum(t for c, t in zip(labels, elapsed, strict=True) if c == code) for code in cols]
    removable = sums[1] + sums[2]
    span = sum(sums)
    baseline = native_ns - removable
    result = dict(
        full_class_ns=dict(zip(cols, sums, strict=True)),
        full_span_ns=span,
        native_minus_producer_ns=native_ns - span,
        ordinary_native_if_all_eligible_free_ns=baseline,
        average_verify_six_s=(47 / 6 - baseline / 1e9) / 11,
        average_verify_six_producer_only_s=(47 / 6 - sums[0] / 1e9) / 11,
        excessive_tail_credit_first_final_ns=final_ns - removable,
    )
    if end is None:
        result["first_final_status"] = "INCONCLUSIVE_TEXT_CUT"
        return result
    check(0 <= end <= len(labels), "first final index")
    credited = sum(t for c, t in zip(labels[:end], elapsed[:end], strict=True) if c != "ar")
    count = labels[:end].count("anchor")
    floor = final_ns - credited
    result.update(
        first_final_status="CONDITIONAL_PRODUCER_TEXT_CUT",
        first_final_sample_one_based=end + 1,
        evaluations_through_cut=end,
        before_counts={code: labels[:end].count(code) for code in cols},
        before_total_ns=sum(elapsed[:end]),
        before_ordinary_ns=sum(elapsed[:end]) - credited,
        eligible_before_ns=credited,
        after_total_ns=sum(elapsed[end:]),
        eligible_after_ns=removable - credited,
        first_final_if_all_eligible_free_ns=floor,
        required_prefill_or_exterior_reduction_ns=max(0, floor - 10**10),
        total_verification_and_overhead_available_ns=10**10 - floor,
        mean_verify_before_cut_available_s=(10**10 - floor) / 1e9 / count if count else None,
    )
    return result


def assess(path, arm_sha):
    step = module(
        IDS / "step_cost/screen.py",
        "e104fe51158cd4239934ba29c90c24c7cb402139ab0b87c7302df72c6a3e6012",
    )
    native = module(
        IDS / "verify.py", "9d3f76702d1ca044b6d854085394f56a0c5325b2a96181d2c5e2e2826e36abc4"
    )
    fixture = module(
        IDS / "b3_fixture/run.py",
        "a2223b1a4b1d4e3243e8506eeec88965d9f4ceb15f1e37b0a03382973a0e6c75",
    )
    original = pinned(IDS / "evidence/b3.json", step["B3"])
    arm = pinned(path / "arm.json", arm_sha)
    g = arm["grade"]
    r = pinned(path / "receipt.json", arm["receipt_sha256"])
    check(
        arm["status"] == "PASS_ONE_NATURAL_ARM"
        and arm["mode"] == g["transport"]["mode"] == "P"
        and g["receipt_sha256"] == arm["receipt_sha256"]
        and g["status"] == "PASS_REVIEWED_TWO_NATURAL_TURNS"
        and g["unit_closed"]
        and g["server_exitcode"] == 0
        and g["requests"] == 2
        and g["model_launches"] == 1
        and g["transport"]["pack_fds_per_cut"] == g["transport"]["model_fds_per_cut"] == 1
        and g["verified_ids_sha256"] == step["VERIFY"],
        "arm grade/FD/exit",
    )
    verified = pinned(IDS / "evidence/verified.json", g["verified_ids_sha256"])
    raw = path / "raw"
    no = r["native_ids"]
    name = no["raw_stderr_file"]
    check(
        Path(name).name == name and no["verbosity"] == 5 and no["stderr_bytes"] <= 4 << 20,
        "stderr contract",
    )
    log = (raw / name).read_bytes()
    check(
        len(log) == no["stderr_bytes"] and digest(log) == no["stderr_sha256"] == g["stderr_sha256"],
        "stderr",
    )
    turns = native["trajectories"](log)
    for i, (rows, ref, geom) in enumerate(
        zip(turns, verified["turns"], native["GEOMETRY"], strict=True), 1
    ):
        ids = native["ids_bytes"]([n for n, _ in rows])
        check(
            digest(ids)
            == g["trajectories"][i - 1]["sampled_ids_sha256"]
            == ref["sampled_ids_sha256"],
            "trajectory",
        )
        projected = native["projection"](raw, i, geom)
        check(
            digest(json.dumps(projected, sort_keys=True, separators=(",", ":")).encode())
            == g["trajectories"][i - 1]["projected_sha256"],
            "projected input/frames/settings",
        )
    target = [n for n, _ in turns[1]]
    check(
        digest(native["ids_bytes"](target)) == original["sampled_i32_sha256"],
        "frozen lookup trajectory",
    )
    prompt = projected[0]["official_ids"]
    check(
        digest(native["ids_bytes"](prompt)) == original["prompt_i32_sha256"], "frozen lookup prompt"
    )
    actions = fixture["trace"](fixture["python_rule"](), prompt, target, 46)
    labels = []
    for a in actions:
        check(a["position"] == len(labels), "proposal boundary")
        labels.append("ar" if a["ar"] else "anchor")
        labels.extend(["skip"] * (a["emitted"] - 1))
    pieces = [log[pos : log.index(b"'\n", pos)] for _, pos in turns[1]]
    frames = [c["delta"].get("content") for f in projected[2] for c in f.get("choices", [])]
    end = text_cut(pieces, [s.encode() for s in frames if s])
    result = json.loads((raw / "T2-result.json").read_bytes())
    sm = result["stream_metrics"]["first_final_content_chunk_s"]
    t = result["timings"]
    row = g["rows"][1]
    check(
        sm == row["first_final_s"] == r["rows"][1]["first_final_s"]
        and math.isclose(t["predicted_ms"] / 1000, row["decode_s"], abs_tol=1e-9)
        and math.isclose(t["prompt_ms"] / 1000, row["prefill_s"], abs_tol=1e-9),
        "sealed clock totals",
    )
    marker = list(native["events"](log))
    tasks = [task for _, task, e in marker if e[0] == "start"]
    sub = [(step["clock_us"](tick), e[0]) for tick, task, e in marker if task == tasks[1]]
    ticks = [v for v, kind in sub if kind == "sample"]
    feeds = [v for v, kind in sub if kind == "feed"]
    check(
        len(ticks) == 47
        and len(feeds) == 46
        and all(a <= b < c for a, b, c in zip(ticks[:-1], feeds, ticks[1:], strict=True)),
        "two monotone position witnesses",
    )
    fn = round(sm * 1e9)
    dn = round(t["predicted_ms"] * 1e6)
    fields = {
        k: budget(labels, t, end, fn, dn)
        for k, t in [("sample", ticks), ("feed_terminal_sample", feeds + [ticks[-1]])]
    }
    return dict(
        status="CONDITIONAL_PACK_B3_COST" if end is not None else "INCONCLUSIVE_TEXT_CUT",
        arm_sha256=arm_sha,
        arm_receipt_sha256=arm["receipt_sha256"],
        stderr_sha256=digest(log),
        protocol_sha256=digest((HERE / "protocol.md").read_bytes()),
        source_sha256=digest(Path(__file__).read_bytes()),
        prefill_ns=round(t["prompt_ms"] * 1e6),
        decode_ns=dn,
        first_final_ns=fn,
        projected_sha256=g["trajectories"][1]["projected_sha256"],
        sampled_ids_sha256=original["sampled_i32_sha256"],
        windows=fields,
        unconditional_position_price="UNIDENTIFIED",
        model_forwards=0,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", type=Path, required=True)
    ap.add_argument("--arm-sha256", required=True)
    ap.add_argument("--output", required=True, type=Path)
    a = ap.parse_args()
    with a.output.open("x") as f:
        try:
            result = assess(a.arm, a.arm_sha256)
        except Exception as e:
            json.dump(dict(status="FAIL_PRESERVED", error=str(e)), f)
            raise
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

"""Bound cross-matrix MXFP4 coding on the authenticated 64-expert transport sample."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
spatial = run_path(HERE.parent / "mxfp4_spatial/screen.py")
base, marginal = spatial["base"], spatial["m"]
need = base.require
WINDOW = spatial["WINDOW"]
PRIOR = "b40f8f9c97d5d4d5f50723bcc8cd4feb72e8ae0990c271de8477553f6977575c"
OLD_EXPERTS = "4a893ad344dc865f05bc292a3206aae9f655056746d7d3c61bbe7889c44eed98"
ORDER = (0, 2, 1)  # gate and up are reconstructible before down.


def parse(raw, symbols):
    lines = iter(raw.splitlines(keepends=True))
    matrices = []
    for peer in range(3):
        header = next(lines).split()
        need(len(header) == 3 and header[:2] == [b"ROLE", str(peer).encode()], "peer order")
        contexts = int(header[2])
        need(0 < contexts <= symbols, "context count")
        spatial_rows = []
        for row in lines:
            if row == b"TERMS\n":
                break
            spatial_rows.append(row)
        coefficients = {}
        for row in lines:
            if row == b"END\n":
                break
            n, coefficient = map(int, row.split())
            need(0 < n <= symbols and n not in coefficients and coefficient, "entropy coefficient")
            coefficients[n] = coefficient
        need(row == b"END\n" and sum(n * c for n, c in coefficients.items()) == 0, "mass balance")
        matrices.append((b"".join(spatial_rows), contexts, coefficients))
    need(next(lines, None) is None, "trailing histograms")
    return matrices


def directed_floor(terms, symbols):
    # Directed bound on the total empirical information across all context tables.
    amount = sum(v * spatial["n_log_n"](n)[0 if v > 0 else 1] for n, v in terms.items())
    penalty = marginal.log2_bounds(256)[1] - marginal.log2_bounds(255)[0]
    return max(0, -(-(amount - symbols * penalty - 8 * marginal.Q) // marginal.Q))


def expert(chunk, record, previous, conditional, counter):
    desc = record["components"]
    views = base.record_components(chunk, desc)
    need(len(views) == 6 and len(views[0]) == base.WEIGHT, "weight payloads")
    result = subprocess.run(
        [str(counter), "2880"],
        input=memoryview(chunk)[: 3 * base.WEIGHT],
        capture_output=True,
        timeout=15,
        check=True,
    )
    need(not result.stderr and len(result.stdout) < 2 << 20, "counter budget")
    symbols = base.BLOCKS * 32
    rows = []
    for physical, (table, contexts, terms) in zip(
        ORDER, parse(result.stdout, symbols), strict=True
    ):
        weight = desc[physical]
        old = previous["matrices"][physical]
        c = conditional[weight["name"]]
        need(
            old["name"] == weight["name"]
            and c["source_sha256"] == old["sha256"] == weight["sha256"]
            and base.sha(table) == old["tables_sha256"],
            "wrong weight or folded histogram",
        )
        bits = directed_floor(terms, symbols)
        if physical == 0:
            need(bits == old["spatial_nibble_bits_floor"], "gate ablation")
        rows.append(
            dict(
                name=weight["name"],
                contexts=contexts,
                spatial_contexts=old["contexts"],
                nibble_bits_floor=bits,
                scale_bits_floor=c["scale_bits_floor"],
                encoded_bytes_floor=(bits + 7) // 8 + (c["scale_bits_floor"] + 7) // 8,
                spatial_bytes_floor=old["encoded_bytes_floor"],
            )
        )
    size = min(WINDOW, base.aligned(sum(r["encoded_bytes_floor"] for r in rows), 4096))
    return dict(
        layer=record["layer"],
        expert=record["expert"],
        tier=previous["tier"],
        matrices=rows,
        aligned_bytes_floor=size,
        spatial_aligned_bytes_floor=previous["aligned_bytes_floor"],
        gate20_possible=5 * size <= 4 * WINDOW,
    )


def summarize(rows):
    raw = len(rows) * WINDOW
    floor = sum(r["aligned_bytes_floor"] for r in rows)
    best = min(r["aligned_bytes_floor"] for r in rows)
    return dict(
        experts=len(rows),
        raw_bytes=raw,
        cross_bytes_floor=floor,
        spatial_bytes_floor=sum(r["spatial_aligned_bytes_floor"] for r in rows),
        best_aligned_bytes=best,
        max_saving_fraction=(raw - floor) / raw,
        best_saving_fraction=(WINDOW - best) / WINDOW,
        gate20=5 * floor <= 4 * raw,
        experts_passing_optimistically=sum(r["gate20_possible"] for r in rows),
        example_dense_frequency_bytes=sum(32 * m["contexts"] for r in rows for m in r["matrices"]),
    )


def read_json(path, digest):
    raw = path.read_bytes()
    need(base.sha(raw) == digest, "source digest " + path.name)
    return json.loads(raw)


def measure(a):
    old = HERE.parent / "mxfp4_spatial"
    receipt = read_json(old / "evidence/receipt.json", PRIOR)
    previous = read_json(old / "evidence/experts.json", OLD_EXPERTS)
    need(receipt["expert_rows_sha256"] == OLD_EXPERTS, "spatial source")
    cond = read_json(
        HERE.parent / "mxfp4_conditional/evidence/components.json", spatial["COMPONENTS"]
    )
    conditions = {(r["layer"], r["expert"], r["name"]): r for r in cond}
    _, _, index, _ = base.reference(a.results_root)
    base.layout(index)
    rows = []
    content = hashlib.sha256()
    with tempfile.TemporaryDirectory() as temp:
        counter = Path(temp) / "count"
        subprocess.run(
            [str(base.COMPILER), *base.FLAGS, str(HERE / "count.cpp"), "-o", str(counter)],
            timeout=30,
            check=True,
        )
        counter_sha = base.sha(counter.read_bytes())
        with a.sample_pack.open("rb", buffering=0) as stream:
            initial = base.stat_id(stream.fileno())
            need(initial[2] == index["pack_bytes"], "sample size")
            for record, prior in zip(index["experts"], previous, strict=True):
                key = (record["layer"], record["expert"])
                need(key == (prior["layer"], prior["expert"]), "record order")
                chunk = stream.read(index["stride"])
                need(len(chunk) == index["stride"], "short record")
                content.update(chunk)
                refs = {
                    m["name"]: conditions.pop((*key, m["name"])) for m in record["components"][:3]
                }
                rows.append(expert(chunk, record, prior, refs, counter))
            need(not stream.read(1) and base.stat_id(stream.fileno()) == initial, "sample changed")
    need(
        not conditions and len(rows) == 64 and content.hexdigest() == base.PACK_SHA,
        "sample integrity",
    )
    all_rows = summarize(rows)
    tiers = {tier: summarize([r for r in rows if r["tier"] == tier]) for tier in ("CPU", "CUDA")}
    sources = {
        p.name: base.sha(p.read_bytes())
        for p in (HERE / "protocol.md", HERE / "count.cpp", HERE / "screen.py", HERE / "prices.py")
    }
    prices = run_path(HERE / "prices.py")["request_prices"](
        a.prefill_plan,
        a.decode_plan,
        a.decode_rp,
        a.decode_pr,
        {(r["layer"], r["expert"]) for r in rows},
        all_rows["best_aligned_bytes"],
    )
    return dict(
        status="REPRODUCED_CROSS_ROLE_BOUND",
        sample=all_rows,
        tiers=tiers,
        compared_matrices=192,
        verified_components=384,
        bytes_read=index["pack_bytes"],
        sample_sha256=content.hexdigest(),
        ablation_sha256=PRIOR,
        prices=prices,
        experts_sha256=marginal.write_json(a.new_output_dir / "experts.json", rows),
        model_forwards=0,
        codec_executions=0,
        gpu_compute=0,
        source_sha256=sources,
        compiler_sha256=base.sha(base.COMPILER.read_bytes()),
        flags=base.FLAGS,
        counter_sha256=counter_sha,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "results-root",
        "sample-pack",
        "prefill-plan",
        "decode-plan",
        "decode-rp",
        "decode-pr",
        "new-output-dir",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    signal.signal(signal.SIGALRM, base.deadline_expired)
    signal.alarm(240)
    receipt = {}
    try:
        need(not base.git("status", "--porcelain"), "dirty measurement tree")
        receipt = dict(
            commit=base.git("rev-parse", "HEAD"), tree=base.git("rev-parse", "HEAD^{tree}")
        )
        receipt.update(measure(a))
    except Exception as exc:
        receipt.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    marginal.write_json(a.new_output_dir / "receipt.json", receipt)
    print(receipt["status"], receipt.get("reason", ""))
    return int(receipt["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

"""Charge only complete observed N2 intervals strictly before the first final cut."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
Q = HERE.parents[2] / "qualification-retake"
HTTP = Q / (
    "packed_nvme_manifest/server_profile/verified_block/server_reserve/causal_server/"
    "http/kv_width/natural/cpu_attention/target/http"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def acquire(family):
    model = run_path(HTTP / "review_family.py")
    need, read = model["need"], json.loads
    compact = read((HTTP / "family-result.json").read_bytes())
    manifest = read((family / "receipt.json").read_bytes())
    need(
        digest(family / "receipt.json") == compact["family_sha256"]
        and digest(family / "ON/receipt.json") == manifest["arms"]["ON"]["sha256"],
        "historical target",
    )
    arm = read((family / "ON/receipt.json").read_bytes())
    for k, v in arm["raw_sha256"].items():
        if k.endswith((".stderr", "T2-request.jsonl", "preset.json")):
            need(digest(family / "ON" / k) == v, "changed target journal")
    ticks, cut = model["ticks"](family / "ON", 2)
    need(
        len(ticks) == 47
        and cut == 44
        and compact["arms"]["ON"]["trajectories"]["2"]["sampled_sha256"]
        == "4a8a47b3ec0a64220e9734237eae9fd7b886ce35ed81964408eacdc4034931f9",
        "native output identity",
    )
    return dict(
        ticks_ns=[(x - ticks[0]) * 1000 for x in ticks],
        cut=cut,
        reported=compact["positions"]["T2"]["groups"],
        source_sha256=digest(HTTP / "family-result.json"),
        family_sha256=compact["family_sha256"],
    )


def calculate(study, obs):
    ticks, cut = obs["ticks_ns"], obs["cut"]
    schedule = study["receipts"][0]["cases"]["nominal"]["N2"]["rows"]
    verified = [(at - 1, at + n - 1, depth) for at, w, depth, n in schedule if w]
    times = [ticks[end] - ticks[start] for start, end, _ in verified]
    for depth in (0, 2):
        group = obs["reported"]["B" + str(depth)]
        if (
            sum(t for t, b in zip(times, verified, strict=True) if b[2] == depth)
            != group["on_us"] * 1000
        ):
            raise ValueError("N2 block service differs by depth")
    early = [t for t, b in zip(times, verified, strict=True) if b[1] < cut]
    arms = []
    for r in study["result"]["N2"]["arms"]:
        if r["case"] == "nominal":
            first = r["first"]["free_target_ns"] + sum(early)
            decode = r["decode"]["free_target_ns"] + sum(times)
            arms.append(
                dict(
                    W=r["W"],
                    pipeline=r["prefill_source"],
                    replay=r["replay"],
                    first_ns_with_crossing_free=first,
                    full_decode_ns=decode,
                )
            )
    return dict(
        complete_blocks_before_cut=len(early),
        early_ns=sum(early),
        all_blocks=len(times),
        all_ns=sum(times),
        arms=arms,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("study", type=Path)
    p.add_argument("--family", type=Path)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--new-output-dir", type=Path)
    g.add_argument("--check", type=Path)
    a = p.parse_args()
    if a.new_output_dir:
        a.new_output_dir.mkdir(mode=0o700)
    try:
        obs = acquire(a.family) if a.family else json.loads(a.check.read_bytes())["observed"]
        data = dict(observed=obs, results=calculate(json.loads(a.study.read_bytes()), obs))
        if a.check:
            if json.loads(a.check.read_bytes()) != data:
                raise ValueError("historical prices differ")
        else:
            with (a.new_output_dir / "receipt.json").open("x") as f:
                json.dump(data, f, separators=(",", ":"), sort_keys=True)
        print("REPRODUCED_N2_INTERVALS")
    except Exception as exc:
        if a.new_output_dir:
            (a.new_output_dir / "failure.json").write_text(
                json.dumps(dict(status="FAIL_PRESERVED", reason=str(exc)))
            )
        raise

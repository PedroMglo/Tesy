"""Apply the pre-registered product envelope to the identified source-policy trajectories."""

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYLOAD = 13_219_200
PACK = 13_221_888
BPS = 4_500_000_000


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pinned(path, seal):
    if digest(path) != seal:
        raise ValueError("receipt identity: " + path.name)
    return json.loads(path.read_bytes())


def price(jobs, decode_jobs, pack, gap_ns, budget, count):
    volume = jobs * PAYLOAD
    if pack != jobs * PACK:
        raise ValueError("pack job charge")
    spare = (budget * BPS + 10**9 - 1) // 10**9 - volume
    rest = budget / 1e9 - gap_ns / 1e9
    time_for_decode = rest + count / 6 - volume / BPS
    return dict(
        prefill_jobs_including_restore=jobs,
        decode_jobs=decode_jobs,
        prefill_payload_bytes=volume,
        decode_payload_bytes=decode_jobs * PAYLOAD,
        decode_payload_bytes_per_confirmed_token=decode_jobs * PAYLOAD / 47,
        prefill_packed_fd_bytes=pack,
        at_6_and_4p5_spare_bytes_before_gaps=spare,
        at_6_and_4p5_spare_s_after_gaps=rest - volume / BPS,
        min_prefill_useful_GBs_at_6_if_gaps_retained=volume / rest / 1e9 if rest > 0 else None,
        min_decode_rate_at_4p5_if_gaps_retained=count / time_for_decode
        if time_for_decode > 0
        else None,
    )


def calculate(pair, replay):
    on = pair["arms"]["ON"]
    if not (
        pair["status"] == "REPRODUCED_SNAPSHOT_CLIENT_PAIR"
        and replay["status"] == "PASS_OBSERVED_R0_AND_CAUSAL_SCREEN"
        and replay["on_receipt_sha256"] == on["receipt_sha256"]
        and replay["policy_sha256"] == on["policy"]["sha256"]
        and replay["pfj_sha256"] == on["journal_sha256"]
    ):
        raise ValueError("replay/observations from different natural processes")
    cases = {}
    for path in ("r0", "carry", "restored"):
        arm = replay[path]
        if arm.get("decision") == "INCONCLUSIVE_SERVICE_ORDER":
            cases[path] = {"decision": arm["decision"], "reason": arm["reason"]}
            continue
        priced = cases[path] = {}
        for source, phases in arm["variants"].items():
            p, r, d = (phases[key]["all"] for key in ("prefill", "restore", "decode"))
            jobs = p.get("disk_jobs", 0) + r.get("disk_jobs", 0)
            packed_bytes = p.get("packed_pread_bytes", 0) + r.get("packed_pread_bytes", 0)
            priced[source] = {
                num: price(
                    jobs,
                    d.get("disk_jobs", 0),
                    packed_bytes,
                    on["prefill_gaps"]["drained_ns"],
                    budget,
                    int(num),
                )
                for num, budget in on["deadlines_prefill_ns"].items()
            }
    return cases


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("pair", "replay", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    for key in ("pair-sha256", "replay-sha256"):
        p.add_argument("--" + key, required=True)
    a = p.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        cases = calculate(pinned(a.pair, a.pair_sha256), pinned(a.replay, a.replay_sha256))
        result = dict(
            status="REPRODUCED_CONDITIONAL_SAME_REQUEST_COSTS",
            cases=cases,
            method_sha256=digest(HERE / "accounting.md"),
            program_sha256=digest(Path(__file__)),
            pair_sha256=a.pair_sha256,
            replay_sha256=a.replay_sha256,
        )
    except (ValueError, OSError, KeyError) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    tmp = out / "report.tmp"
    with tmp.open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    tmp.rename(out / "receipt.json")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

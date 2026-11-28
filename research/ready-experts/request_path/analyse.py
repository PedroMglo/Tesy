"""Replay both nominal requests, or verify the public proof with no model."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(HERE / "source.py")
R = run_path(HERE / "replay.py")
need = S["need"]


def compact(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()


def write(path, data):
    tmp = path.with_name("." + path.name + ".partial")
    with tmp.open("xb") as out:
        out.write(data)
    tmp.rename(path)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--archive", type=Path)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--new-output-dir", type=Path)
    mode.add_argument("--check", type=Path)
    args = cli.parse_args()
    out = args.new_output_dir
    if out:
        if not args.archive:
            cli.error("--new-output-dir requires --archive")
        out.mkdir(mode=0o700)
    try:
        service, queues, hits = S["inputs"]()
        if args.archive:
            captured = {
                t: S["capture"](args.archive, t, service[t]["jobs"]) for t in ("P97", "P106")
            }
        else:
            captured = S["F"]["unpack"](args.check / "spans.json.gz")
        need(
            set(captured) == {"P97", "P106"}
            and all(
                captured["P97"][k] == captured["P106"][k]
                for k in ("route", "trajectory", "requested_ids_sha256")
            ),
            "two target trajectories",
        )
        raw = compact(captured)
        arms = {t: R["grade"](obs, service[t], queues[t], hits) for t, obs in captured.items()}
        fixed = [R["passes"](a["fixed_fifo"]["ID"]) for a in arms.values()]
        relaxed = [R["passes"](a["relaxed"]["ID"]) for a in arms.values()]
        result = dict(
            schema="tesy.request_path.v1",
            evidence="TRACE_DERIVED_CONDITIONAL",
            protocol_sha256=S["METHOD"],
            spans_sha256=hashlib.sha256(raw).hexdigest(),
            source_sha256={p: S["sha"](HERE / p) for p in ("analyse.py", "source.py", "replay.py")},
            bank_hits=len(hits),
            workers=4,
            arms=arms,
            code_control=S["code_control"](),
            fixed_fifo_joint_both=all(fixed),
            relaxed_joint_both=all(relaxed),
            decision=(
                "NO_GO_FIXED_PEER_PRICES"
                if not all(relaxed)
                else "INCONCLUSIVE_SCHEDULE"
                if not all(fixed)
                else "GO_FIXTURE_ONLY"
            ),
            m3="PARTIAL",
            m4="NOT_MET",
            model_forwards=0,
            gpu_runs=0,
        )
        if out:
            write(out / "spans.json.gz", gzip.compress(raw, mtime=0))
            write(
                out / "decision.json",
                (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(),
            )
        else:
            need(
                raw == gzip.decompress((args.check / "spans.json.gz").read_bytes())
                and result == json.loads((args.check / "decision.json").read_bytes()),
                "public replay",
            )
        print(result["decision"])
        for t, arm in arms.items():
            print(
                t,
                arm["fixed_fifo"]["ID"]["first"],
                arm["relaxed"]["ID"]["first"],
                arm["max_peer_service_ppm_for_joint"],
            )
    except Exception as exc:
        if out:
            missing = (
                isinstance(exc, FileNotFoundError)
                and exc.filename
                and args.archive
                and (Path(exc.filename).resolve().is_relative_to(args.archive.resolve()))
            )
            write(
                out / "failure.json",
                compact(dict(status="NOT_RUN_RAW_REQUIRED" if missing else "FAIL", error=str(exc)))
                + b"\n",
            )
        raise


if __name__ == "__main__":
    main()

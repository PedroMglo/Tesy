"""Run the original C110 observer against the tiny-qualified bounded backend on the laptop."""

import json
from datetime import datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
C = run_path(str(HERE / "grade.py"))
FULL = run_path(str(HERE.parents[2] / "c110_graph/run.py"))
SMALL = run_path(str(HERE.parent / "review.py"))
A, sha, receipt, need = (FULL[k] for k in ("A", "sha", "receipt", "need"))
TINY = "18d5cbce12d961fcae705735a9caec861b00785dcd2c5e09cb478838a68309e5"


def freeze(a):
    prior = SimpleNamespace(
        **(vars(a) | dict(stage="parity", execute=False, prepared=None, prepared_sha256=None))
    )
    profile, bound, w, policy, limits, end, monitor, _, refs = A["prepare"](prior)
    old, model, identity, plan, client, env, providers, paths, drivers = bound
    first = json.loads((a.c55.parent / "samples.jsonl").read_text().splitlines()[0])["utc"]
    stamp = FULL["B"]["git"](HERE, "log", "-1", "--format=%ct", "--", "protocol.md")
    need(datetime.fromisoformat(first).timestamp() >= int(stamp), "C55 before native protocol")
    tiny = SMALL["review"](
        SimpleNamespace(
            family=a.native_tiny,
            family_sha256=TINY,
            historical=a.tiny,
            graph=a.reader_tiny,
            tiny=a.small_model,
        )
    )
    need(
        json.loads(json.dumps(tiny)) == json.loads((HERE.parent / "result.json").read_bytes())
        and tiny["decision"] == "GO_NATIVE_C110"
        and tiny["build_sha256"] == a.build_sha256,
        "native prerequisite",
    )
    build = receipt(a.build / "receipt.json", a.build_sha256)
    candidate = (a.build / "candidate/libllama.so").resolve()
    control = (a.dso / "objects/src/libllama.so").resolve()
    need(
        sha(candidate) == build["candidate_sha256"] == tiny["arms"]["DIRECT"]["libllama_sha256"]
        and sha(control) == build["control_sha256"] == tiny["arms"]["ORIGINAL"]["libllama_sha256"]
        and all(sha(HERE.parents[6] / p) == v for p, v in build["inputs"].items()),
        "backend or sources changed",
    )
    closure = client["closure"] | {"libllama.so": dict(file=str(candidate), sha256=sha(candidate))}
    ce, cp, cd = A["SYS"]["system_loader"](
        old, client | {"closure": closure}, a.dso.resolve() / "objects", llama_dir=candidate.parent
    )
    need(
        paths - {str(control)} == set(cp) - {str(candidate)}
        and str(control) in paths
        and str(candidate) in cp
        and all(providers[k]["sha256"] == v for k, v in (cp | cd).items() if k != str(candidate)),
        "other loaded files changed",
    )
    tracked = providers | {
        str(candidate): dict(sha256=sha(candidate), stat=A["DEV"]["IO"].stat_id(candidate))
    }
    on, schedules = C["C"]["history"](a.sys73, plan)
    gold = C["reference"](a.numerical, plan)
    state = dict(
        profile=profile,
        tiny_sha256=TINY,
        numerical_sha256=C["P"]["FAMILY"],
        build_sha256=a.build_sha256,
        candidate_library_sha256=sha(candidate),
        providers=tracked,
        environment=ce,
        sources={
            p.name: sha(p) for p in (HERE / "run.py", HERE / "grade.py", HERE / "protocol.md")
        },
    )
    return (
        state,
        (old, old, model, identity, plan, client, ce, tracked, set(cp), drivers),
        (w, policy, limits, end, monitor),
        (on, schedules, refs, gold),
    )


def bank_environment(mode, model):
    return dict(
        TESY_IK_BANK_INPUT=mode,
        TESY_IK_BANK_MODEL=str(model),
        TESY_IK_BANK_CAPACITY=str(C["CAP"]),
        TESY_IK_BANK_TRACE="1",
    )


def run(a, out, r):
    FULL["run"](
        a,
        out,
        r,
        prepare=freeze,
        evaluate=C["evaluate"],
        sources={k: (k, "OFF") for k in C["MODES"]},
        prefix="tesy-ik-e10-native-",
        status="PASS_NATIVE_C110",
        arm_status="PASS_NATIVE_C110_ARM",
        arm_environment=bank_environment,
    )


if __name__ == "__main__":
    raise SystemExit(FULL["main"](run, ("numerical", "native-tiny")))

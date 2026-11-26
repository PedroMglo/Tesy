"""Qualify the native bounded CUDA library with one unchanged BANK9 executable."""

import json
import time
from datetime import datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
G = run_path(str(HERE / "grade.py"))
R = G["R"]["R"]
S = R["SYS73"]
need, sha, load, IO, D = (R[k] for k in ("need", "sha", "load", "IO", "D"))
B = run_path(str(HERE / "build.py"))
LABELS = ("ORIGINAL", "DIRECT", "PREAD_RANDOM")


def freeze(a):
    head = B["git"](HERE, "rev-parse", "HEAD")
    need(head == a.commit and not B["git"](HERE, "status", "--porcelain"), "dirty hook fixture")
    past = G["R"]["review"](a.graph, G["GRAPH"], a.historical, a.tiny)
    need(
        json.loads(json.dumps(past)) == json.loads((G["TINY"] / "result.json").read_bytes()),
        "prior graph qualification",
    )
    reference = G["reference"](a.graph)
    need(G["layout"](reference)[1:] == (4, 262144), "pressure prediction")
    old = load(a.client / "receipt.json", S["CLIENT"])
    lib = load(a.dso / "receipt.json", S["LIBS"])
    build = load(a.build / "receipt.json", a.build_sha256)
    obj = a.dso.resolve() / "objects"
    candidate = a.build.resolve() / "candidate/libllama.so"
    exe = a.client.resolve() / "hybrid-client"
    original = obj / "src/libllama.so"
    need(
        build["status"] == "GO_BUILD_NATIVE_CACHE_HOOK"
        and build["build_parent"] == B["DSO"] == S["LIBS"]
        and build["control_sha256"] == lib["libraries"]["objects/src/libllama.so"] == sha(original)
        and sha(candidate) == build["candidate_sha256"]
        and sha(a.tiny) == D["TINY"]
        and sha(exe) == old["binary_sha256"],
        "hook build and controls",
    )
    need(
        all(sha(HERE.parents[5] / k) == v for k, v in build["inputs"].items()),
        "hook sources changed",
    )
    replacements = old["closure"] | {
        "libllama.so": {"file": str(candidate), "sha256": build["candidate_sha256"]}
    }
    env, paths, drivers = S["SYS"]["system_loader"](exe, old, obj)
    ce, cp, cd = S["SYS"]["system_loader"](
        exe, old | {"closure": replacements}, obj, llama_dir=candidate.parent
    )
    need(
        drivers == cd
        and paths | {str(candidate): sha(candidate)} == cp | {str(original): sha(original)},
        "other provider changed",
    )
    provider = run_path(str(D["QUAL"] / "packed_layer_service/profile.py"))
    monitor, check = provider["monitor_provider"](SimpleNamespace(token=IO.stat_id))
    hist = load(a.historical / "receipt.json", R["HIST"])
    need(hist["authority"]["monitor"] == monitor, "live NVML")
    policy, end = D["c55"](a)
    first = json.loads((a.c55.parent / "samples.jsonl").read_text().splitlines()[0])["utc"]
    need(
        datetime.fromisoformat(first).timestamp()
        >= int(B["git"](HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "stale cost protocol",
    )
    hashes = paths | cp | drivers | {str(exe): sha(exe), str(a.tiny): D["TINY"]}
    state = dict(
        commit=head,
        tree=B["git"](HERE, "rev-parse", "HEAD^{tree}"),
        build_commit=build["commit"],
        c55_sha256=a.c55_sha256,
        build_sha256=a.build_sha256,
        graph_sha256=G["GRAPH"],
        historical_sha256=R["HIST"],
        monitor=monitor,
        baseline_library_sha256=sha(original),
        candidate_library_sha256=sha(candidate),
        files={k: dict(stat=IO.stat_id(Path(k)), sha256=v) for k, v in hashes.items()},
        original_environment=env,
        candidate_environment=ce,
        sources={k: sha(HERE / k) for k in ("run.py", "grade.py", "protocol.md")},
    )
    allowed = {
        p
        for p in drivers
        if Path(p).name.startswith(("libcuda.", "libnvidia-")) and "nvidia-ml" not in p
    }
    return state, (policy, end, exe, env, set(paths), ce, set(cp), allowed, check), reference


def run(a, out, r):
    state, params, reference = freeze(a)
    r["authority"] = state
    if a.prepared is None:
        r["status"] = "PREPARED_ONLY"
        return
    old = load(a.prepared / "receipt.json", a.prepared_sha256)
    need(old["status"] == "PREPARED_ONLY" and old["authority"] == state, "changed preparation")
    r["prepared_sha256"] = a.prepared_sha256
    policy, end, exe, env, paths, ce, cp, drivers, check = params
    cg = R["scope"](a)
    deadline = time.monotonic() + 600
    for mode in LABELS:
        check()
        r["arms"][mode] = arm = dict(starts=0)
        selected = mode != "ORIGINAL"
        settings = (
            ce
            | {
                "TESY_IK_BANK_INPUT": mode,
                "TESY_IK_BANK_MODEL": str(a.tiny),
                "TESY_IK_BANK_CAPACITY": str(G["CAP"]),
                "TESY_IK_BANK_TRACE": "1",
            }
            if selected
            else env
        )
        native = D["sample_arm"](
            mode,
            out,
            a,
            policy,
            end,
            exe,
            a.tiny,
            settings,
            cp if selected else paths,
            drivers,
            arm,
            client_mode="BANK9",
        )
        arm["grade"] = G["grade"](mode, native.parent, a.tiny, a.historical, reference)
        need(
            time.monotonic() < deadline and int((cg / "memory.peak").read_text()) < D["STOP"],
            "family deadline or memory",
        )
    check()
    need(all(IO.stat_id(Path(k)) == v["stat"] for k, v in state["files"].items()), "provider drift")
    r["status"] = "PASS_NATIVE_CACHE_HOOK"


if __name__ == "__main__":
    raise SystemExit(R["main"](run, ("graph",)))

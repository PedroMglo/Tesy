"""Bind the numerical client to the physically validated capacity arm and tiny fixture."""

import hashlib
import json
import struct
import subprocess
from datetime import datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
OPS = run_path(str(HERE / "process.py"))
BASE, S, CPU, DEVICE, stock = (OPS[k] for k in ("BASE", "S", "CPU", "DEVICE", "stock"))
need, sha, receipt = S["need"], S["sha"], S["receipt"]
TINY = "2d165f3e9c8f8108a04e758a5496e610cdbe0051afaee1fe1da35123b8373bfd"
TINY_REVIEW = "8bd67de71f07326e5d7fac23d32a7c9748b11388856e259949ee3591ca459293"
IDS = OPS["CUT"]["CPU"]["IDS17"]
PREFIX = "d6a1f114bb22668e36cf1eaf1af14861b4e5b9a688704b06aff5298ecbb25a8d"


def c55(a):
    need(a.c55.parent.name.startswith("tesy-ik-full-parity-c55-"), "dedicated parity C55")
    w = receipt(a.c55, a.c55_sha256)
    sample = (a.c55.parent / "samples.jsonl").read_text().splitlines()
    first = datetime.fromisoformat(json.loads(sample[0])["utc"])
    protocol_epoch = int(
        subprocess.check_output(
            ["git", "-C", HERE, "log", "-1", "--format=%ct", "--", "../protocol.md"], text=True
        )
    )
    need(first.timestamp() >= protocol_epoch, "window predates protocol")
    _, policy, _ = CPU["window_authority"](a.c55, a.c55_sha256, S["AUTH"]["select"](w))
    limits = stock.policy_api.freeze_protocol_resource_limits(
        policy,
        cgroup_memory_max_bytes=S["CAP"],
        start_mode="CAPACITY_ADMISSION_START",
        execution_class="FILE_PAGING",
    )
    stock.policy_api.validate_resource_protocol({"limits": {}, "resources": limits})
    need(
        policy["gpu"]["total_mib"] == 8188
        and min(w[k]["cap_max_bytes"] for k in ("memory", "canonical_memory")) >= S["CAP"],
        "E10/VRAM admission",
    )
    end = datetime.fromisoformat(json.loads(sample[-1])["utc"])
    S["age"](end)
    return w, policy, limits, end


def capacity_gate(a):
    cap = receipt(a.capacity / "receipt.json", a.capacity_sha256)
    need(
        cap["status"] == "PASS_IK_REAL_CAPACITY_NO_FORWARD"
        and cap["model_starts"] == 1
        and cap["child_gone"]
        and cap["restored"]
        and cap["returncode"] == cap["swap_peak"] == 0,
        "physical capacity gate",
    )
    need(
        (cap["tiny_sha256"], cap["tiny_review_sha256"], cap["dso_sha256"], cap["input_sha256"])
        == (TINY, TINY_REVIEW, S["LIB_BUILD"], a.inputs_sha256),
        "different capacity prerequisites",
    )
    need(
        cap["model_sha256"] == stock.MODEL_SHA and cap["placement_sha256"] == CPU["PLACEMENT"],
        "capacity model",
    )
    S["TINY"]["identity_tree"](a.capacity, cap)
    reread = run_path(str(S["CAPACITY"] / "grade.py"))["check_arm"](
        (a.capacity / "raw/stdout").read_text(),
        (a.capacity / "raw/stderr").read_text(),
        a.capacity / "native",
        a.inputs / "plan.tsv",
    )
    need(
        cap["grade"] == reread
        and reread["status"] == "PASS_IK_CAPACITY_ZERO_FORWARD"
        and (
            reread["slots"],
            reread["matrix_mmap_count"],
            reread["bias_cuda_count"],
            reread["group_layers"],
            reread["registrations"],
            reread["expert_H2D_request_bytes"],
            reread["forwards"],
        )
        == (288, 108, 108, 36, 0, 0, 0),
        "capacity grade or census",
    )
    return cap


def input_ids(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_size == 68, "C110 IDs size")
    raw = path.read_bytes()
    need(
        hashlib.sha256(raw).hexdigest() == IDS
        and hashlib.sha256(raw[:64]).hexdigest() == PREFIX
        and struct.unpack_from("<i", raw, 64) == 976,
        "C110 IDs or teacher",
    )
    return IDS


def bound(a, w, tiny, cap, prior):
    parent = SimpleNamespace(
        **(vars(a) | {"client": a.capacity_client, "client_sha256": cap["client_sha256"]})
    )
    cexe, model, identity, plan, build, env, providers, paths, drivers = S["inputs"](
        parent, w, tiny, prior
    )
    need(
        sha(cexe) == cap["executable_sha256"]
        and list(identity) == cap["model_stat"]
        and sha(plan) == cap["plan_sha256"],
        "capacity inputs changed",
    )
    b = receipt(a.client / "receipt.json", a.client_sha256)
    exe = a.client / "parity-client"
    need(
        b["status"] == "PASS_IK_FULL_PARITY_CLIENT_BUILD"
        and b["binary"] == exe.name
        and sha(exe) == b["binary_sha256"]
        and b["capacity_client_sha256"] == cap["client_sha256"]
        and b["inputs_sha256"] == input_ids(a.ids),
        "numeric build or inputs",
    )
    for key in (
        "libraries",
        "closure",
        "explicit_search",
        "native_search",
        "native_search_sha256",
        "tiny_family_sha256",
        "tiny_review_sha256",
        "ik_commit",
        "dso_build_sha256",
        "compiler_sha256",
    ):
        need(b[key] == build[key], "different numerical build " + key)
    required = {
        n: sha(HERE.parent / n)
        for n in ("protocol.md", "parity.hpp", "build.py", "grade.py", "contrast.py")
    }
    for n in ("parity.cpp", "parity_rank_view.hpp", "observe_prefix.hpp", "ids_expected.hpp"):
        required[n] = sha(a.client / n)
    need(required == b["sources"] and b["forwards"] == b["model_loads"] == 0, "build source drift")
    providers[str(exe)] = {"stat": DEVICE["IO"].stat_id(exe), "sha256": b["binary_sha256"]}
    CPU["loader"](exe, b, env)
    return exe, model, identity, plan, b, env, providers, paths, drivers


def prepare(a):
    head, tree = subprocess.check_output(
        ["git", "-C", HERE, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    need(
        head == a.commit
        and not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]),
        "unclean/different measurement freeze",
    )
    need((a.tiny_sha256, a.tiny_review_sha256) == (TINY, TINY_REVIEW), "wrong tiny family")
    need(bool(a.execute) == bool(a.prepared and a.prepared_sha256), "preparation and execute")
    if a.execute:
        need(a.unit.startswith("tesy-ik-e10-full-parity-"), "dedicated scope unit")
        prior = receipt(a.prepared / "receipt.json", a.prepared_sha256)
        need(
            prior["status"] == "PREPARED_ONLY" and prior["model_starts"] == 0, "invalid preparation"
        )
    else:
        need(not a.prepared and not a.prepared_sha256, "unexpected preparation")
        prior = None
    cap = capacity_gate(a)
    tiny = S["tiny_gate"](a.tiny, TINY, a.tiny_review, TINY_REVIEW)
    w, policy, limits, end = c55(a)
    inputs = bound(a, w, tiny, cap, prior)
    exe, _, identity, plan, b, env, providers, _, _ = inputs
    refs = OPS["CUT"]["references"](a.c110_parent, a.stock_file, a.cpu_d0, a.cpu_d1)
    sources = S["sources"]()
    for p in [
        *HERE.glob("*.py"),
        *(HERE.parent / n for n in ("protocol.md", "contrast.py", "grade.py")),
    ]:
        sources[p.relative_to(S["IK"]).as_posix()] = sha(p)
    profile = dict(
        commit=head,
        tree=tree,
        sources=sources,
        providers=providers,
        executable_sha256=sha(exe),
        model_sha256=cap["model_sha256"],
        model_stat=list(identity),
        plan_sha256=sha(plan),
        placement_sha256=cap["placement_sha256"],
        ids_sha256=b["inputs_sha256"],
        tiny_sha256=TINY,
        tiny_review_sha256=TINY_REVIEW,
        dso_sha256=S["LIB_BUILD"],
        capacity_sha256=a.capacity_sha256,
        capacity_build_sha256=cap["client_sha256"],
        input_sha256=a.inputs_sha256,
        client_sha256=a.client_sha256,
        c55_sha256=a.c55_sha256,
        cgroup_contract=limits["cgroup"],
        child_env=env,
        resource_policy_sha256=w["canonical_policy_sha256"],
        reference_sha256={
            name: {str(k): hashlib.sha256(row).hexdigest() for k, row in pair.items()}
            for name, pair in refs.items()
        },
    )
    monitor_probe = run_path(str(CPU["Q"] / "packed_layer_service/profile.py"))["monitor_provider"]
    profile["monitor_provider"], verify = BASE["monitor_authority"](prior, monitor_probe)
    if prior is not None:
        need(
            all(prior.get(k) == v for k, v in profile.items()),
            "authority changed after preparation",
        )
    return profile, inputs, w, policy, limits, end, refs, verify

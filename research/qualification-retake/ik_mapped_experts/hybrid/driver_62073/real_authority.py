"""Bind a real E10 arm to the requalified bank, the immutable GGUF and the system driver."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SYS = run_path(str(HERE / "system.py"))
TINY = run_path(str(HERE / "run.py"))
OFF = run_path(str(HERE.parent / "full_parity/callback/grade.py"))
FR = OFF["R"]["RUN"]
CAP = FR["OPS"]["BASE"]
S, CPU, DEV, stock = (CAP[k] for k in ("S", "CPU", "DEVICE", "stock"))
G = OFF["G"]
need, sha, receipt = S["need"], S["sha"], S["receipt"]
CAP_CLIENT = "68b8489fff21e4d9d1be1406a0542b989ba2a34869073591fe67f4867f7579e8"
INPUT = "0c5a1e8b6f0155857b45336a1f8e6df6c3c0e6338415c3db943ddff7652e3a8a"
PLAN = "4c60c7ad261c4f61e85c576a08866dd71abb3d1003369bb2876ed3669f9f5730"
BRIDGE = "90efe5e2c39b0da9a47f656670f3f041941f376a1c5bd251a6ef1178faf59c3c"


def check_tiny(folder, digest):
    rec = receipt(folder / "receipt.json", digest)
    need(
        rec["status"] == "PASS_SYSTEM_TINY_BANKS"
        and rec["swap_peak_B"] == 0
        and rec["authority"]["dso_sha256"] == S["LIB_BUILD"]
        and rec["authority"]["tiny_sha256"] == TINY["D"]["TINY"]
        and FR["inventory"](folder) == rec["raw_sha256"],
        "system tiny evidence",
    )
    grades = {}
    for mode in TINY["D"]["MODES"]:
        arm = rec["arms"][mode]
        grades[mode] = TINY["arm_grade"](mode, folder / mode)
        need(
            grades[mode] == arm["grade"]
            and arm["starts"] == 1
            and arm["child_gone"]
            and arm["returncode"] == 0
            and arm["same_consumer_placement"]
            and arm["cross_driver"]["bitwise"]
            and arm["cross_driver"]["routes_equal"],
            "incomplete tiny qualification",
        )
    contrast = TINY["G"]["compare_arms"](
        folder / "RESIDENT/native", grades["RESIDENT"], folder / "BANK9/native", grades["BANK9"]
    )
    need(
        contrast["bitwise"]
        and contrast["routes_equal"]
        and contrast == rec["arms"]["BANK9"]["versus_resident"],
        "tiny bank",
    )
    return rec["authority"]["monitor"]


def capacity_grade(folder, plan):
    return G["CAP"]["check_arm"](
        (folder / "raw/stdout").read_text(),
        (folder / "raw/stderr").read_text(),
        folder / "native",
        plan,
    )


def require_capacity(g):
    need(
        g["status"] == "PASS_IK_CAPACITY_ZERO_FORWARD"
        and [
            g[k]
            for k in (
                "matrix_mmap_count",
                "bias_cuda_count",
                "bias_mapped_twins",
                "first_lookup_bias_host",
                "slots",
                "group_layers",
                "expert_H2D_request_bytes",
                "forwards",
                "registrations",
            )
        ]
        == [108, 108, 108, 108, 288, 36, 0, 0, 0],
        "incomplete 120B capacity",
    )


def prepare(a):
    head, tree = subprocess.check_output(
        ["git", "-C", HERE, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    need(
        head == a.commit
        and not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]),
        "unclean freeze",
    )
    need(bool(a.execute) == bool(a.prepared and a.prepared_sha256), "preparation identity")
    is_cap = a.stage == "capacity"
    prefix = "tesy-ik-e10-" + ("capacity" if is_cap else "full-parity") + "-sys73-"
    need(not a.execute or a.unit.startswith(prefix), "dedicated unit")
    need(bool(a.capacity and a.capacity_sha256) != is_cap, "capacity prerequisite")
    original_monitor = check_tiny(a.tiny, a.tiny_sha256)
    w, policy, limits, end = (S["c55"] if is_cap else FR["AUTH"]["c55"])(a)
    first = json.loads((a.c55.parent / "samples.jsonl").read_text().splitlines()[0])["utc"]
    frozen = int(
        subprocess.check_output(
            ["git", "-C", HERE, "log", "-1", "--format=%ct", "--", "real-protocol.md"], text=True
        )
    )
    need(
        datetime.fromisoformat(first).timestamp() >= frozen and w["gpu_driver"] == SYS["VERSION"],
        "C55 protocol or driver",
    )
    model, identity = CPU["placed"](w, a.placement)
    plan = a.inputs / "plan.tsv"
    data = receipt(a.inputs / "receipt.json", INPUT)
    need(
        data["status"] == "PASS_IK_CAPACITY_INPUT_IDENTITY"
        and data["model_stat"] == list(identity)
        and data["model_sha256"] == stock.MODEL_SHA
        and data["placement_sha256"] == CPU["PLACEMENT"]
        and Path(data["model"]).samefile(model)
        and data["plan_sha256"] == sha(plan) == PLAN,
        "immutable GGUF/plan",
    )
    FR["AUTH"]["input_ids"](a.ids)
    b = receipt(a.client / "receipt.json", a.client_sha256)
    if is_cap:
        need(
            a.client_sha256 == CAP_CLIENT
            and b["status"] == "PASS_IK_CAPACITY_CLIENT_BUILD"
            and b["dso_build_sha256"] == S["LIB_BUILD"],
            "capacity build",
        )
        exe = a.client.resolve() / "capacity-client"
    else:
        need(
            b["status"] == "PASS_CALLBACK_CLIENT_BUILD"
            and b["dso_sha256"] == S["LIB_BUILD"]
            and b["binary_sha256"] == BRIDGE,
            "paired client build",
        )
        exe = a.client.resolve() / "callback-client"
    need(sha(exe) == b["binary_sha256"], "changed ELF")
    ds = receipt(a.dso / "receipt.json", S["LIB_BUILD"])
    need(
        ds["status"] == "PASS_IK_SM89_LINK_ONLY"
        and all(ds["libraries"]["objects/" + k] == h for k, h in b["libraries"].items()),
        "SM89 DSOs",
    )
    env, paths, driver = SYS["system_loader"](exe, b, a.dso.resolve() / "objects")
    accepted = {
        p
        for p in driver
        if Path(p).name.startswith(("libcuda.", "libnvidia-")) and "nvidia-ml" not in p
    }
    all_files = {**paths, **driver, str(exe): b["binary_sha256"]}
    providers = {p: {"stat": DEV["IO"].stat_id(Path(p)), "sha256": h} for p, h in all_files.items()}
    monitor, unchanged = run_path(str(CPU["Q"] / "packed_layer_service/profile.py"))[
        "monitor_provider"
    ](SimpleNamespace(token=DEV["IO"].stat_id))
    need(monitor == original_monitor, "system monitor differs from tiny")
    refs = historical = None
    if not is_cap:
        cap = receipt(a.capacity / "receipt.json", a.capacity_sha256)
        need(
            cap["status"] == "PASS_SYSTEM_CAPACITY_ZERO_FORWARD"
            and cap["model_starts"] == 1
            and cap["swap_peak"] == 0
            and cap["restored"]
            and cap["child_gone"]
            and cap["returncode"] == 0
            and cap["authority"]["model_stat"] == list(identity)
            and cap["authority"]["monitor"] == monitor
            and cap["authority"]["tiny_sha256"] == a.tiny_sha256
            and FR["inventory"](a.capacity) == cap["raw_sha256"],
            "system capacity prerequisite",
        )
        cg = capacity_grade(a.capacity, plan)
        require_capacity(cg)
        need(cg == cap["grade"], "capacity raw disagreement")
        historical = OFF["reference"](a.historical, plan)
        refs = FR["OPS"]["CUT"]["references"](a.c110_parent, a.stock_file, a.cpu_d0, a.cpu_d1)
    profile = dict(
        stage=a.stage,
        commit=head,
        tree=tree,
        executable_sha256=b["binary_sha256"],
        dso_sha256=S["LIB_BUILD"],
        model_stat=list(identity),
        model_sha256=stock.MODEL_SHA,
        plan_sha256=PLAN,
        placement_sha256=CPU["PLACEMENT"],
        tiny_sha256=a.tiny_sha256,
        capacity_sha256=a.capacity_sha256,
        client_sha256=a.client_sha256,
        c55_sha256=a.c55_sha256,
        monitor=monitor,
        providers=providers,
        environment=env,
        limits=limits["cgroup"],
        policy_sha256=w["canonical_policy_sha256"],
        references={}
        if refs is None
        else {
            name: {str(p): G["CPU"]["digest"](v) for p, v in rs.items()}
            for name, rs in refs.items()
        },
        prior_on_sha256=None if is_cap else OFF["R"]["ROOT_SHA"],
        sources={
            p.name: sha(p)
            for p in (
                HERE / "real.py",
                HERE / "real_authority.py",
                HERE / "real-protocol.md",
                HERE / "system.py",
            )
        },
    )
    if a.execute:
        prior = receipt(a.prepared / "receipt.json", a.prepared_sha256)
        need(
            prior["status"] == "PREPARED_ONLY"
            and prior["model_starts"] == 0
            and prior["authority"] == profile,
            "preparation changed",
        )
    bound = exe, model, identity, plan, b, env, providers, set(paths), accepted
    return profile, bound, w, policy, limits, end, unchanged, historical, refs

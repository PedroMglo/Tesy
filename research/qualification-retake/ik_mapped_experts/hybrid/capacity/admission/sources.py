"""Read-only predecessor adapters and receipt bindings for the one capacity process."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CAPACITY = HERE.parent
HYBRID = CAPACITY.parent
IK = HYBRID.parent
CPU = run_path(str(IK / "cpu_numeric/admission/profile.py"))
AUTH = run_path(str(IK / "cpu_numeric/admission/authority.py"))
TINY = run_path(str(HYBRID / "device/review.py"))
DEVICE = TINY["API"]
stock = CPU["stock"]
need, sha, receipt = CPU["need"], CPU["sha"], CPU["receipt"]
GIB, MIB = CPU["GIB"], CPU["MIB"]
CAP = 10 * GIB
VRAM = 7676
LIB_BUILD = "5c648c09e18d29bc47d57af018053f5251f67f85bdd56cfe8f1b954c95470753"
PROTOCOL_EPOCH = 1795655100


def sources():
    return {
        p.relative_to(IK).as_posix(): sha(p)
        for p in (
            HERE / "protocol.md",
            HERE / "sources.py",
            HERE / "run.py",
            CAPACITY / "grade.py",
            CAPACITY / "protocol.md",
            CAPACITY / "inventory.py",
            HYBRID / "device/run.py",
            HYBRID / "device/review.py",
            IK / "cpu_numeric/admission/profile.py",
            IK / "cpu_numeric/admission/authority.py",
        )
    }


def tiny_gate(folder, expected, review_dir, review_sha):
    r = receipt(folder / "receipt.json", expected)
    modes = ("RESIDENT", "BANK9", "BANK7")
    need(r["status"] == TINY["PASS"] and set(r["arms"]) == set(modes), "tiny CUDA prerequisite")
    review = receipt(review_dir / "receipt.json", review_sha)
    need(
        review["status"] == "REPRODUCED_TINY_HYBRID_GPU_FIXTURE"
        and review["family_sha256"] == expected
        and review["launches"] == 3
        and review["family_status"] == TINY["PASS"],
        "independent tiny review",
    )
    TINY["identity_tree"](folder, r)
    gold = None
    for mode in modes:
        rec, native = r["arms"][mode], folder / mode / "native"
        grade = TINY["native_grade"](mode, native)
        need(
            rec["starts"] == 1 and rec["child_gone"] is True and rec["returncode"] == 0,
            "tiny drain",
        )
        need(rec["grade"] == grade and grade["host_registration_events"] == 0, "tiny grade drift")
        if mode == "RESIDENT":
            gold = grade
        else:
            contrast = TINY["GRADE"]["compare_arms"](
                folder / "RESIDENT/native", gold, native, grade
            )
            need(contrast == rec["resident_comparison"], "tiny cross-arm comparison")
            if mode == "BANK9":
                need(
                    contrast["bitwise"] and contrast["routes_equal"], "tiny numerical qualification"
                )
    need(r["dso_sha256"] == LIB_BUILD and r["swap_peak_bytes"] == 0, "tiny DSO / swap")
    return r


def c55(a):
    w = receipt(a.c55, a.c55_sha256)
    need(a.c55.parent.name.startswith("tesy-ik-capacity-c55-"), "dedicated C55")
    rows = (a.c55.parent / "samples.jsonl").read_text().splitlines()
    first = datetime.fromisoformat(json.loads(rows[0])["utc"])
    need(first.timestamp() >= PROTOCOL_EPOCH, "C55 predates protocol")
    _, policy, _ = CPU["window_authority"](a.c55, a.c55_sha256, AUTH["select"](w))
    limits = stock.policy_api.freeze_protocol_resource_limits(
        policy,
        cgroup_memory_max_bytes=CAP,
        start_mode="CAPACITY_ADMISSION_START",
        execution_class="FILE_PAGING",
    )
    stock.policy_api.validate_resource_protocol({"limits": {}, "resources": limits})
    need(
        policy["gpu"]["total_mib"] == 8188
        and min(w[k]["cap_max_bytes"] for k in ("memory", "canonical_memory")) >= CAP,
        "E10/VRAM admission",
    )
    return w, policy, limits, datetime.fromisoformat(json.loads(rows[-1])["utc"])


def inputs(a, w, tiny, before):
    b = receipt(a.client / "receipt.json", a.client_sha256)
    lib = receipt(a.dso / "receipt.json", LIB_BUILD)
    data = receipt(a.inputs / "receipt.json", a.inputs_sha256)
    model, model_id = CPU["placed"](w, a.placement)
    plan = a.inputs / "plan.tsv"
    need(
        data["status"] == "PASS_IK_CAPACITY_INPUT_IDENTITY"
        and sha(plan) == data["plan_sha256"]
        and Path(data["model"]).samefile(model)
        and data["model_stat"] == list(model_id)
        and data["model_sha256"] == stock.MODEL_SHA
        and data["placement_sha256"] == CPU["PLACEMENT"],
        "input/placement receipt",
    )
    need(
        data["inventory_sha256"]
        == "2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82",
        "inventory identity",
    )
    exe = a.client / "capacity-client"
    need(
        b["status"] == "PASS_IK_CAPACITY_CLIENT_BUILD"
        and b["dso_build_sha256"] == LIB_BUILD
        and b["tiny_client_sha256"] == tiny["client_sha256"]
        and b["binary"] == exe.name
        and b["binary_sha256"] == sha(exe),
        "capacity client/build chain",
    )
    need(
        b["tiny_family_sha256"] == a.tiny_sha256
        and b["tiny_review_sha256"] == a.tiny_review_sha256
        and b["ik_commit"] == "7a5d90009b7ae55d3239cdd33244977c4eb10ff6"
        and b["model_loads"] == b["forwards"] == 0,
        "frozen tiny/ik build",
    )
    required_sources = {
        str(p.name): p
        for p in (
            CAPACITY / n
            for n in ("capacity.cpp", "build.py", "inventory.py", "grade.py", "protocol.md")
        )
    }
    required_sources["observe_prefix.hpp"] = a.client / "observe_prefix.hpp"
    required_sources.update(
        {"client/" + n: HYBRID / "client" / n for n in ("copy.cpp", "hooks.hpp", "client.cpp")}
    )
    required_sources.update(
        {n: IK / n for n in ("tiny_loader/probe.cpp", "cpu_numeric/vma/inspect.hpp")}
    )
    need(
        {k: sha(p) for k, p in required_sources.items()} == b["sources"],
        "capacity build sources drift",
    )
    need(
        b["libraries"] == {n.removeprefix("objects/"): h for n, h in lib["libraries"].items()},
        "DSO hashes",
    )
    need(
        (
            data["tensors"],
            data["matrix_tensors"],
            data["bias_tensors"],
            data["requested_bytes"],
            data["slots"],
            data["guard_slots"],
            data["tuple_bytes"],
            data["bytes_read_from_model"],
        )
        == (687, 108, 108, 3644 * MIB, 288, 1, 13219200, 0),
        "capacity plan numbers",
    )
    desc = receipt(a.env49_map, DEVICE["ENV49"])
    driver = Path(desc["driver_dir"])
    for soname, target in desc["driver_aliases"].items():
        need((driver / soname).resolve(strict=True) == Path(target), "GPU provider alias")
    lookup = [
        str(a.dso.resolve() / "objects/ggml/src"),
        str(a.dso.resolve() / "objects/src"),
        str(driver),
        "/usr/local/cuda-13.3/lib64",
    ]
    need(
        b["explicit_search"] == lookup
        and b["native_search"] == ":".join(lookup)
        and hashlib.sha256(b["native_search"].encode()).hexdigest() == b["native_search_sha256"],
        "loader path",
    )
    paths = {row["file"]: row["sha256"] for row in b["closure"].values()}
    for rel, digest in lib["libraries"].items():
        need(paths[str((a.dso / rel).resolve(strict=True))] == digest, "wrong ik library")
    need(
        all(paths.get(p) == h for deps in lib["closure"].values() for p, h in deps.items()),
        "DSO closure",
    )
    expected = dict(paths)
    for p in desc["driver_aliases"].values():
        expected[p] = desc["files"][p]["sha256"]
    expected[str(exe)] = b["binary_sha256"]
    ids = {}
    for p, h in expected.items():
        path = Path(p)
        meta = DEVICE["IO"].stat_id(path)
        if before is None:
            need(sha(path) == h and DEVICE["IO"].stat_id(path) == meta, "provider SHA/stat")
        else:
            need(
                before["providers"].get(p) == {"stat": meta, "sha256": h},
                "provider changed after preparation",
            )
        ids[p] = {"stat": meta, "sha256": h}
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LD_LIBRARY_PATH=b["native_search"],
        CUDA_VISIBLE_DEVICES="0",
        CUDA_CACHE_DISABLE="1",
        GGML_CUDA_NO_PINNED="1",
        GGML_MOE_PREFETCH_AHEAD="0",
        OMP_NUM_THREADS="8",
    )
    CPU["loader"](exe, b, env)
    return exe, model, model_id, plan, b, env, ids, set(paths), set(desc["driver_aliases"].values())


def bind(a, r):
    h = subprocess.check_output(["git", "-C", HERE, "rev-parse", "HEAD"], text=True).strip()
    need(
        h == a.commit and not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]),
        "unclean freeze",
    )
    r.update(
        commit=h,
        tree=subprocess.check_output(
            ["git", "-C", HERE, "rev-parse", "HEAD^{tree}"], text=True
        ).strip(),
        sources=sources(),
        model_sha256=stock.MODEL_SHA,
        placement_sha256=CPU["PLACEMENT"],
        c55_sha256=a.c55_sha256,
        client_sha256=a.client_sha256,
        tiny_sha256=a.tiny_sha256,
        tiny_review_sha256=a.tiny_review_sha256,
        dso_sha256=LIB_BUILD,
        input_sha256=a.inputs_sha256,
    )
    prior = None
    if a.execute:
        need(
            a.prepared and a.prepared_sha256 and a.unit.startswith("tesy-ik-e10-capacity-"),
            "execute arguments",
        )
        prior = receipt(a.prepared / "receipt.json", a.prepared_sha256)
        need(
            prior["status"] == "PREPARED_ONLY"
            and all(
                prior.get(k) == r[k]
                for k in (
                    "commit",
                    "tree",
                    "sources",
                    "model_sha256",
                    "placement_sha256",
                    "c55_sha256",
                    "client_sha256",
                    "tiny_sha256",
                    "tiny_review_sha256",
                    "dso_sha256",
                    "input_sha256",
                )
            ),
            "different preparation",
        )
        r["prepared_sha256"] = a.prepared_sha256
    else:
        need(not a.prepared and not a.prepared_sha256, "unexpected preparation")
    return prior


def same_files(ids):
    need(all(DEVICE["IO"].stat_id(Path(p)) == v["stat"] for p, v in ids.items()), "provider drift")


def raw_size(folder):
    files = list(folder.rglob("*"))
    need(all(not f.is_symlink() for f in files), "linked raw")
    return sum(f.stat().st_size for f in files if f.is_file())


def other_clients(pid=None):
    CPU["conflicts"](pid)
    for comm in Path("/proc").glob("[0-9]*/comm"):
        try:
            n = comm.read_text().strip()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        if n in ("capacity-client", "hybrid-client", "warm-transfer"):
            need(int(comm.parent.name) == pid, "another ik job")


def age(end):
    need(0 <= (datetime.now(UTC) - end).total_seconds() < 3300, "expired C55")

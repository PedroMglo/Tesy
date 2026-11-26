"""Bind the C281 client, the admitted NVMe placement and the complete runtime of the HTTP pilot."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[2]
REPO = QUAL.parents[1]
B = run_path(str(HERE / "build.py"))
R = run_path(str(QUAL / "ik_mapped_experts/hybrid/driver_62073/real_authority.py"))
CON = run_path(str(QUAL / "nvme_conversation/contract.py"))
sys.path.insert(0, str(REPO / "tools"))
import parallel_runtime as parallel  # noqa: E402

need, sha, receipt = B["need"], B["sha"], B["receipt"]
BUILD = "3bad85a508f91896daee9c8ceb922f37e3acd495ab0213ea68fc30a80cfe43ec"
PORT = CON["PORT"]
CAP = 20 << 30


def server_argv(server, model, template):
    return list(
        map(
            str,
            [
                server,
                "-m",
                model,
                "--host",
                "127.0.0.1",
                "--port",
                PORT,
                "--threads-http",
                2,
                "-ngl",
                99,
                "-ncmoe",
                36,
                "--defer-experts",
                "--moe-cache-mib",
                3644,
                "--moe-cache-policy",
                "classlru",
                "--moe-cache-cpu-share",
                0,
                "--split-mode",
                "layer",
                "-c",
                8192,
                "-np",
                1,
                "-b",
                256,
                "-ub",
                32,
                "-t",
                8,
                "-tb",
                8,
                "-ctk",
                "f16",
                "-ctv",
                "f16",
                "--no-flash-attn",
                "--no-fused-moe",
                "--no-fused-up-gate",
                "--no-fused-mul-multiadd",
                "--no-warmup",
                "--no-context-shift",
                "--jinja",
                "--chat-template-file",
                template,
                "--reasoning-format",
                "deepseek",
            ],
        )
    )


def normalize(usage, timing, expected):
    cached = usage["prompt_tokens_details"]["cached_tokens"]
    processed = timing["prompt_n"]
    need(
        all(type(n) is int and n >= 0 for n in (cached, processed, usage["prompt_tokens"]))
        and cached + processed == usage["prompt_tokens"] == expected
        and "cache_n" not in timing,
        "native prompt accounting",
    )
    return timing | dict(cache_n=cached)


def freeze(a):
    need(
        B["git"](HERE, "rev-parse", "HEAD") == a.commit
        and not B["git"](HERE, "status", "--porcelain"),
        "unclean pilot commit",
    )
    b = receipt(a.build / "receipt.json", BUILD)
    server = (a.build / "objects/bin/llama-server").resolve()
    need(
        b["status"] == "GO_SERVER_ELF"
        and sha(server) == b["executable_sha256"]
        and b["source_commit"] == B["PIN"]
        and sha(HERE / "build.py") == b["source_sha256"]
        and sha(HERE / "protocol.md") == b["protocol_sha256"],
        "server certificate",
    )
    front = receipt(
        HERE.parent / "evidence.json",
        "bbe7167250d93586b15e729d1d18729927a32652128acc33d6e89ba34f414d56",
    )
    inp = receipt(
        QUAL / "nvme_conversation/inputs.json",
        "e6b8346b326ae3f41449d55983c296de6faad5288e9b9f3bcf913de9ef3b1264",
    )
    workload = CON["C281"] / "protocol.json"
    need(
        sha(workload) == inp["historical_workload_sha256"]
        and sha(a.template) == front["jinja_sha256"]
        and sha(REPO / "tools/optin_integration_client.py") == CON["CLIENT_SHA"],
        "controlled C281 inputs",
    )
    x = receipt(a.window / "receipt.json", a.window_sha256)
    w, policy, _ = R["CPU"]["window_authority"](a.window / "receipt.json", a.window_sha256, 20)
    need(
        x == w and w["gpu_driver"] == R["SYS"]["VERSION"] and w["gpu_total_mib"] == 8188,
        "host or GPU",
    )
    first = json.loads((a.window / "samples.jsonl").read_text().splitlines()[0])["utc"]
    need(
        datetime.fromisoformat(first).timestamp()
        >= int(B["git"](HERE, "log", "-1", "--format=%ct", "--", "session-protocol.md")),
        "C55 before prospective session",
    )
    model, identity = R["CPU"]["placed"](w, a.placement)
    limits = R["stock"].policy_api.freeze_protocol_resource_limits(
        policy,
        cgroup_memory_max_bytes=CAP,
        start_mode="OPERATIONAL_SESSION_START",
        execution_class="FILE_PAGING",
    )
    need(limits["cgroup"]["memory_high_bytes"] == CAP - (512 << 20), "E20 FILE_PAGING")
    libs = b["closures"]["NATIVE"]
    need(all(sha(Path(v["path"])) == v["sha256"] for v in libs.values()), "loader hash")

    def directory(name):
        return str(Path(libs[name]["path"]).parent)

    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LD_LIBRARY_PATH=os.pathsep.join(
            (
                directory("libggml.so"),
                directory("libllama.so"),
                directory("libmtmd.so"),
                "/usr/local/cuda-13.3/lib64",
            )
        ),
        CUDA_VISIBLE_DEVICES="0",
        CUDA_CACHE_DISABLE="1",
        GGML_CUDA_NO_PINNED="1",
        GGML_MOE_PREFETCH_AHEAD="0",
        OMP_NUM_THREADS="8",
        TESY_IK_BANK_INPUT="PREAD_RANDOM",
        TESY_IK_BANK_CAPACITY="648155136",
        TESY_IK_BANK_MODEL=str(model),
        TESY_IK_BANK_TRACE="0",
    )
    R["CPU"]["loader"](server, {"closure": {k: {"file": v["path"]} for k, v in libs.items()}}, env)
    gomp = libs["libgomp.so.1"]
    par = dict(
        schema="parallel-runtime-v1",
        environment=parallel.parallel_environment(env),
        libraries_sha256={gomp["path"]: gomp["sha256"]},
    )
    parallel.validate_launch_runtime(par, env)
    preset = dict(
        commit=a.commit,
        tree=B["git"](HERE, "rev-parse", "HEAD^{tree}"),
        build_sha256=BUILD,
        binary_sha256=sha(server),
        source_commit=B["PIN"],
        model_sha256=R["stock"].MODEL_SHA,
        model_stat=R["stock"].bounded.file_identity(model),
        session_date=CON["DATE"],
        port=PORT,
        run_id=a.unit,
        argv=server_argv(server, model, a.template),
        env=env,
        libraries=libs,
        workload_sha256=sha(workload),
        template_sha256=sha(a.template),
        window_sha256=a.window_sha256,
        official_ids=inp["official_ids"],
        historical_inputs=inp["historical_inputs"],
        sources={
            p.name: sha(p)
            for p in (
                HERE / "session-protocol.md",
                HERE / "session.py",
                HERE / "pilot.py",
                REPO / "tools/run_bounded.py",
                REPO / "tools/c2_server_run.py",
                REPO / "tools/optin_integration_client.py",
            )
        },
    )
    resources = dict(
        limits={},
        execution_scope_unit=a.unit,
        resources=limits,
        parallel_runtime=par,
        start_inventory=dict(
            schema="c120-start-inventory-v1",
            duration_s=60,
            max_age_s=3,
            policy_sha256=w["canonical_policy_sha256"],
        ),
    )
    return preset, resources, policy

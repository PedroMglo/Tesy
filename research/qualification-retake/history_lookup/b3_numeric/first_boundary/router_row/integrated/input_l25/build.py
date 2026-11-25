"""Compile the observer and reuse the qualified C269 library byte-for-byte."""

import argparse
import json
import os
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import probes  # noqa: E402

old, sha = probes.engine, probes.sha
need, read, module = old.need, old.read, old.module
SOURCES = ("build.py", "probes.py", "protocol.md")


def run(a, out, r):
    need(
        sha(HERE / "protocol.md") == probes.PROTOCOL
        and sha(a.parent_build / "receipt.json") == probes.BUILD_SHA,
        "frozen protocol and parent",
    )
    base = read(a.parent_build / "receipt.json")
    prior = a.parent_build / "client"
    need(
        base["status"] == "PASS_INTEGRATED_ROUTER_BUILD"
        and base["model_launches"] == 0
        and base["candidate_sha256"] == probes.IMAGE_SHA
        and base["smoke"]["objects"] == 18
        and sha(prior / "receipt.json") == base["client_receipt_sha256"]
        and sha(prior / "b3-numeric") == base["client_sha256"]
        and sha(prior / "boundary.cpp") == read(prior / "receipt.json")["native_source_sha256"]
        and (prior / "boundary.cpp").read_bytes() == probes.old.client(),
        "qualified ON observer baseline",
    )
    need(
        base["sources"] == {n: sha(probes.PARENT / n) for n in old.SOURCE_NAMES},
        "parent source provenance",
    )
    target = a.parent_build / base["candidate_file"]
    need(sha(target) == probes.IMAGE_SHA, "reused graph ELF")
    cd = out / "candidate"
    cd.mkdir()
    image = cd / target.name
    shutil.copyfile(target, image)
    image.chmod(0o500)
    (cd / "libllama.so.0").symlink_to(image.name)
    need(sha(image) == base["candidate_sha256"], "reused DSO copy")
    r.update(
        physical_parent_build_sha256=probes.BUILD_SHA,
        prior_client_sha256=base["client_sha256"],
        candidate_file=base["candidate_file"],
        candidate_sha256=probes.IMAGE_SHA,
        worker_commit=base["worker_commit"],
        protocol_sha256=probes.PROTOCOL,
        static_preflight_sha256=base["static_preflight_sha256"],
        model_launches=0,
        sources={name: sha(HERE / name) for name in SOURCES},
        stage="compile main TU",
    )
    parent = module(old.source.FB / "build.py", "previous_boundary_compiler")
    dst = out / "client"
    dst.mkdir()
    qualified = parent.qualified_builder()
    qualified.update(render=probes.render, source_names=SOURCES, unit=HERE)
    child = {}
    qualified["run"](a.backend, a.preflight_dir, dst, child)
    need(
        child["status"] == "PASS_C269_B3_NUMERIC_BUILD"
        and child["self_test"] == "PASS_B3_NUMERIC_ROW_PLAN"
        and sha(dst / "boundary.cpp") == child["native_source_sha256"]
        and child["worker_commit"] == base["worker_commit"],
        "derived main TU",
    )
    (dst / "receipt.json").write_text(json.dumps(child, sort_keys=True, indent=2) + "\n")
    exe = dst / child["executable"]
    r.update(
        commit=child["commit"],
        tree=child["tree"],
        client_sha256=sha(exe),
        client_receipt_sha256=sha(dst / "receipt.json"),
        stage="load closure",
    )
    static = module(old.Q / "nvme_r0_gate/driver_pair/server_startup/screen.py", "l25_startup")
    pfj = module(old.Q / "phase_fd/integrated/build.py", "l25_bind_image")
    need(sha(a.preflight_dir / "receipt.json") == base["static_preflight_sha256"], "preflight")
    pre = read(a.preflight_dir / "receipt.json")
    need(
        sha(a.preflight_dir / "static-map.json") == pre["static_map_sha256"]
        and sha(Path(static.__file__)) == pre["source_sha256"],
        "closure sources",
    )
    arm = read(a.preflight_dir / "static-map.json")["arms"]["C270"]
    map_ = pfj.verify(
        arm | {"executable": str(exe)},
        "candidate",
        image,
        pre["arms"]["C270"]["objects"],
        probes.IMAGE_SHA,
        static,
        static.Files(),
    )
    need(map_ == base["startup"]["candidate"] and len(map_) == 18, "parent/extended startup ELF")
    env = static.environment([str(cd), *arm["native_search"]])
    for label, tool in (("parent", prior / "b3-numeric"), ("extended", exe)):
        proc = subprocess.run(
            [tool, "--self-test"],
            env=env | {"CUDA_VISIBLE_DEVICES": "", "TESY_B3_ROUTER_ROW": "1"},
            capture_output=True,
            timeout=12,
        )
        need(
            proc.returncode == 0 and proc.stdout == b"PASS_B3_NUMERIC_ROW_PLAN\n",
            "no-model stride/shape ON " + label,
        )
    r.update(
        startup={"candidate": map_},
        smoke=old.smoke(exe, env, map_, arm, out),
        graph_builds=0,
        new_main_tus=1,
        model_free_positive_self_tests=2,
        status="PASS_INPUT_L25_OBSERVER_BUILD",
        stage="closed",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("backend", "parent-build", "preflight-dir", "new-output-dir"):
        parser.add_argument("--" + key, type=lambda value: Path(value).resolve(), required=True)
    a = parser.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    r = {"status": "FAIL_PRESERVED", "model_launches": 0}
    start = time.monotonic()
    try:
        run(a, out, r)
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    r.update(
        wall_s=time.monotonic() - start,
        max_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )
    (out / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(int(r["status"] == "FAIL_PRESERVED"))

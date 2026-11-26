"""Run only the independently linked CPU reference with the sealed tiny GGUF."""

import argparse
import json
import resource
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import grade  # noqa: E402


def bound():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 20, 8 << 20))


def run(a, out, r):
    b = json.loads(build.pin(a.build / "receipt.json", a.build_sha256).read_bytes())
    build.need(
        b["status"] == "PASS_TINY_HYBRID_CLIENT_BUILD"
        and b["variant"] == "cpu"
        and b["sources"]["grade.py"] == build.sha(HERE / "grade.py"),
        "CPU build",
    )
    exe = build.pin(a.build / "hybrid-client", b["binary_sha256"])
    build.need(build.FRONT["closure"](exe, a.objects.resolve()) == b["closure"], "CPU-only closure")
    t = json.loads(build.pin(a.tiny / "receipt.json", build.TINY_SHA).read_bytes())
    build.need(
        t["status"] == "PASS_TINY_IK_DEFERRED_GPT_OSS_LOGITS" and t["gguf_sha256"] == build.GOLD,
        "fixture",
    )
    model = build.pin(a.tiny / "synthetic.gguf", build.GOLD)
    cg = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("::")[
        1
    ].lstrip("/")
    build.need(
        cg.name == a.scope + ".scope"
        and int((cg / "memory.max").read_text()) == 256 << 20
        and int((cg / "memory.swap.max").read_text()) == 0,
        "CPU scope",
    )
    before = (cg / "memory.events").read_text()
    r.update(
        build_sha256=a.build_sha256,
        binary_sha256=b["binary_sha256"],
        tiny_loader_sha256=build.TINY_SHA,
        model_sha256=build.GOLD,
        native_dir="native",
        mode="CPU",
    )
    env = build.FRONT["env"](a.objects.resolve()) | {
        "GGML_MOE_PREFETCH_AHEAD": "0",
        "OMP_NUM_THREADS": "8",
        "MALLOC_ARENA_MAX": "1",
        "OMP_STACKSIZE": "512K",
        "CUDA_VISIBLE_DEVICES": "",
    }
    with (out / "stdout").open("xb") as f, (out / "stderr").open("xb") as e:
        proc = subprocess.run(
            [exe, "CPU", model, out / "native"],
            env=env,
            stdout=f,
            stderr=e,
            timeout=30,
            preexec_fn=bound,
        )
    r.update(
        returncode=proc.returncode,
        stdout_sha256=build.sha(out / "stdout"),
        stderr_sha256=build.sha(out / "stderr"),
        cgroup_peak_bytes=int((cg / "memory.peak").read_text()),
        swap_peak=int((cg / "memory.swap.peak").read_text()),
    )
    build.need(
        proc.returncode == 0
        and before == (cg / "memory.events").read_text()
        and not r["swap_peak"],
        "native or cgroup",
    )
    r["grade"] = grade.check_arm(
        "CPU", (out / "stdout").read_text(), (out / "stderr").read_text(), out / "native"
    )
    return "PASS_TINY_HYBRID_CPU_REFERENCE"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("build", "objects", "tiny", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--scope", required=True)
    p.add_argument("--build-sha256", required=True)
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = {}
    try:
        r["status"] = run(a, out, r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", error=str(exc))
    (out / "receipt.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(r["status"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

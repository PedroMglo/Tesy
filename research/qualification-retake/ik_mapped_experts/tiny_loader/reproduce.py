"""Reopen both resident scopes and compare stable outputs independently of telemetry."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

DRIVER = run_path(str(Path(__file__).with_name("run.py")))
MODES, need, sha = DRIVER["MODES"], DRIVER["need"], DRIVER["sha"]
SEALS = [
    "b10222365dec972020668e3e9a9874018f8af2a7170ddef2c9f97ff60018cd92",
    "0cdf0a7138cc216569e372842951e956e1e92516444585c53a3c638f9c7e7851",
]


def reopen(root, expected):
    r = json.loads(DRIVER["FRONT"]["pinned"](root / "receipt.json", expected).read_bytes())
    need(
        r["status"] == "PASS_TINY_IK_DEFERRED_GPT_OSS_LOGITS"
        and sha(root / "synthetic.gguf") == r["gguf_sha256"],
        "closed family",
    )
    v = r["cgroup_after"]
    need(
        v["memory.peak"] <= v["memory.max"] == 150 << 20
        and v["memory.swap.max"] == v["memory.swap.peak"] == sum(v["events"].values()) == 0,
        "resources",
    )
    invariant = {}
    for mode in MODES:
        arm = r["arms"][mode]
        stdout = root / mode / "stdout"
        need(
            sha(stdout) == arm["stdout_sha256"]
            and sha(root / mode / "stderr") == arm["stderr_sha256"],
            "process logs",
        )
        raw = (root / mode / "logits.f32").read_bytes()
        need(len(raw) == 128 and hashlib.sha256(raw).hexdigest() == arm["logits_sha256"], "32 F32")
        obs = [
            s
            for s in stdout.read_text().splitlines()
            if s.startswith(("MAP ", "MAD ", "POSIX ", "VIEW ", "POOL "))
        ]
        invariant[mode] = (obs, raw)
    return r, invariant


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("r02", type=Path)
    p.add_argument("r03", type=Path)
    a = p.parse_args()
    (left, o1), (right, o2) = [
        reopen(path, h) for path, h in zip((a.r02, a.r03), SEALS, strict=True)
    ]
    need(
        o1 == o2 and len({raw for _, raw in o1.values()}) == 1,
        "loader address proofs, hints, pool or complete bitwise logits",
    )
    for k in (
        "sources",
        "controller_sha256",
        "supplement_sha256",
        "ik_commit",
        "libraries",
        "gguf_sha256",
        "build_sha256",
    ):
        need(left[k] == right[k], "different method or data: " + k)
    print(
        json.dumps(
            {
                "status": "REPRODUCED_TINY_IK_LOAD_AND_LOGITS",
                "source_sha256": SEALS,
                "logits_sha256": left["arms"]["OFF"]["logits_sha256"],
                "cgroup_peaks_bytes": [r["cgroup_after"]["memory.peak"] for r in (left, right)],
                "rss_kib_off_defer_prefetch": [
                    [r["arms"][m]["max_rss_kib"] for m in MODES] for r in (left, right)
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

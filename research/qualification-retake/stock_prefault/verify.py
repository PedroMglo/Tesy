"""Check the stock mmap constructor on a warm memfd without loading a backend or GGUF."""

import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = "e95426f16982054c379ca7bdc8186996dd22f0fe"
PROTOCOL = "8d9fb999d20d6b65f8e5cbf2ec9e988be057bda047f5e737baf3023186590c6f"
SOURCE = {
    "src/llama-model.cpp": "9956da154d2a34fdb2ae627a4c70ef34f046b86c145039de754a7ad7a4b67667",
    "src/llama-model-loader.cpp": "b856b513340e9e86ab81e2d8d110fedd07b60f508e0e4f8513690150f8efd7e1",  # noqa: E501
    "src/llama-quant.cpp": "f3d57d3a8ec8688604742d3b8c345c00a1c5cde3e06f254294ca57873f98ba6e",
    "src/llama-mmap.cpp": "130601ff8c2b6e16668b70a1dca07cc09ae84328d91bbd5bd259aea5658103e7",
    "src/llama-impl.cpp": "abd5851762a157ae477588537e0cfe8dddfa1d2a2efb596d17efa4a19b45c769",
    "src/llama-mmap.h": "0fff03ce62bc51b1649833f6017fbd84dc0aac7fce3b38484439153fc13ba8f5",
}
OBJECTS = {
    "llama-mmap.cpp.o": "f55d793fc77cd8ec4519fbe2d7a4ed19aca34908c31018f3a451a0001f702156",
    "llama-impl.cpp.o": "4e139697a87cc906ce0d83555abd5ce6d86063dff77fbce212217ad4861b622e",
}
BASE = "c58db87a08edfe5d499f24c1bdbd3efd844c40368f030282ef750c4e56b52c4d"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify(build_root, work, receipt):
    source, build = build_root / "source", build_root / "build"
    objects = build / "src/CMakeFiles/llama.dir"
    libdir = build / "bin"
    probe = HERE / "probe.cpp"
    exe = work / "mapping-test"
    base = libdir / "libggml-base.so.0"
    require(sha(HERE / "protocol.md") == PROTOCOL, "protocol")
    require(
        subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip()
        == PIN,
        "stock pin",
    )
    require(all(sha(source / n) == h for n, h in SOURCE.items()), "stock source")
    require(
        all(sha(objects / n) == h for n, h in OBJECTS.items()) and sha(base) == BASE,
        "stock objects",
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "CUDA_VISIBLE_DEVICES": "",
        "LD_LIBRARY_PATH": str(libdir),
    }
    command = [
        "/usr/bin/g++-15",
        "-std=c++17",
        "-O2",
        "-I",
        source / "src",
        probe,
        *(objects / n for n in OBJECTS),
        base,
        "-o",
        exe,
        "-Wl,--wrap=mmap,--wrap=posix_fadvise,--wrap=posix_madvise",
    ]
    with (work / "build.log").open("xb") as f:
        subprocess.run(command, env=env, check=True, timeout=30, stdout=f, stderr=subprocess.STDOUT)
    linked = subprocess.check_output(["ldd", exe], text=True, env=env)
    require(
        str(base) in linked
        and not any(x in linked.lower() for x in ("cuda", "libllama", "libggml-cpu", "not found")),
        "unexpected fixture linkage",
    )
    with (work / "fixture.stdout").open("xb") as out, (work / "fixture.stderr").open("xb") as err:
        subprocess.run([exe], env=env, timeout=10, check=True, stdout=out, stderr=err)
    arms = [json.loads(s) for s in (work / "fixture.stdout").read_text().splitlines()]
    require([r["prefetch"] for r in arms] == [True, False], "incomplete native pair")
    receipt.update(
        arms=arms,
        pin=PIN,
        source_sha256=SOURCE,
        stock_objects_sha256=OBJECTS,
        linked_ggml_base_sha256=BASE,
        client_sha256=sha(exe),
        client_source_sha256=sha(probe),
        runner_sha256=sha(Path(__file__)),
        private_bytes=sum(f.stat().st_size for f in work.iterdir()),
        native_child_max_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )
    require(
        receipt["private_bytes"] <= 8 * 2**20 and receipt["native_child_max_rss_kib"] < 256 * 1024,
        "fixture budget",
    )
    receipt["status"] = "PASS_MAPPING_PTE_FIXTURE_ONLY"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("stock-build-root", "new-private", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_private.mkdir(exist_ok=False)
    a.new_output_dir.mkdir(exist_ok=False)
    start = time.monotonic()
    result = {"status": "FAIL_PRESERVED", "protocol_sha256": PROTOCOL}
    try:
        resource.setrlimit(resource.RLIMIT_AS, (256 * 2**20, 256 * 2**20))
        signal.alarm(60)
        verify(a.stock_build_root.resolve(), a.new_private.resolve(), result)
    except Exception as e:
        result["failure"] = (
            type(e).__name__
            + ": "
            + str(e)
            .replace(str(a.new_private), "<private>")
            .replace(str(a.stock_build_root), "<stock>")
        )
    result["elapsed_s"] = time.monotonic() - start
    pending = a.new_output_dir / ".receipt.pending"
    pending.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    pending.rename(a.new_output_dir / "receipt.json")
    print(result["status"])
    raise SystemExit(0 if result["status"].startswith("PASS") else 1)


if __name__ == "__main__":
    main()

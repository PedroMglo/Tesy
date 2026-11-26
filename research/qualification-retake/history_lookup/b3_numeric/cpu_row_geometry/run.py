"""Freeze the CPU-only executable, or run its measured 3×1 versus 1×3 numerical contrast."""

import argparse
import hashlib
import json
import math
import os
import platform
import resource
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = "afaded8c2279c44379242337eb4ca73120fa0f6185dfdfb971baa7a52767af9c"
COMMIT = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
PINS = {
    "ggml/include/ggml.h": "98c5fcf96279e16c09d42dcba482be1b03434839db723bba4b65518e424ba181",
    "ggml/include/ggml-cpu.h": "1aafe97e576ea38c0da57517fb2492955d0b69c1a799842481fc069d6d9d28ef",
    "ggml/include/ggml-alloc.h": "94e4cd069b9313b2ceb35dacec901981e0bb478d8bb31035b7126be091998c23",
    "ggml/include/ggml-backend.h": "a620e815b43a44cc72d5f216629a3a91980335b61bc37eb6b2d0813368c3704f",  # noqa: E501
    "ggml/src/ggml-cpu/ggml-cpu.c": "bda1c2c81077d89813c3b4776079a5ddf65eaf28bf1e33338473818cc56831f5",  # noqa: E501
    "ggml/src/ggml-cpu/arch/x86/quants.c": "3c489fdc77e3ab484a5f188bff9c60c0e9483c951ed65c1a562a04c249d5628e",  # noqa: E501
    "ggml/src/ggml-cpu/repack.cpp": "b3a1d6953fc61f2a4088337384166fb5102db617afe37a4b92f7cf07992a9f8a",  # noqa: E501
    "src/llama-moe-stream.cpp": "584aecb73900aa1164f00ec93126bc5b8b07c4d330d0f421641331b0c278d5a0",
}
LIBS = {
    "libggml-cpu.so.0.15.3": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
    "libggml-base.so.0.15.3": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
}
ROUTES = ((3, 0, 6, 2), (1, 3, 4, 0), (6, 5, 2, 3))
F32 = struct.Struct("<f")
LIMIT = 256 << 20


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def bounds():
    path = Path("/proc/self/cgroup").read_text().splitlines()
    need(len(path) == 1 and path[0].startswith("0::/"), "unified cgroup")
    cg = Path("/sys/fs/cgroup") / path[0][3:].lstrip("/")
    need(
        int((cg / "memory.max").read_text()) == LIMIT
        and int((cg / "memory.swap.max").read_text()) == 0,
        "256 MiB RAM and zero swap",
    )
    return cg


def words(gold, candidate):
    need(len(gold) == len(candidate) and len(gold) % 4 == 0, "float population")
    distinct, first = 0, None
    for i, (a, b) in enumerate(
        zip(struct.iter_unpack("<I", gold), struct.iter_unpack("<I", candidate), strict=True)
    ):
        if a != b:
            distinct += 1
            if first is None:
                first = dict(index=i, reference=f"{a[0]:08x}", candidate=f"{b[0]:08x}")
    return {"changed": distinct, "first": first}


def compare_positions(packed, one_bytes, order):
    need(len(packed) == 3 * one_bytes, "three complete positions")
    return b"".join(packed[i * one_bytes : (i + 1) * one_bytes] for i in order)


def grade(directory, shared):
    sizes = {
        "f32": 4 * 4 * 2880,
        "ids": 4 * 4,
        "x": 4 * shared * 2880,
        "q8": shared * 3060,
        "reference-q8": shared * 3060,
    }
    prefix = str(shared) + "-"
    captured = {}
    for tag in ("ar0", "ar1", "ar2", "batch", "permuted", "wrong"):
        ar = tag.startswith("ar")
        blob = {}
        for suffix, per_position in sizes.items():
            path = directory / (prefix + tag + "." + suffix)
            need(
                path.is_file()
                and not path.is_symlink()
                and path.stat().st_size == per_position * (1 if ar else 3),
                "file/shape " + path.name,
            )
            blob[suffix] = path.read_bytes()
        need(all(math.isfinite(v[0]) for v in F32.iter_unpack(blob["f32"])), "finite F32")
        captured[tag] = blob
    batch = captured["batch"]
    single = {k: b"".join(captured["ar" + str(i)][k] for i in range(3)) for k in sizes}
    wrong = captured["wrong"]
    need(single["ids"] == batch["ids"] == struct.pack("<12i", *sum(ROUTES, ())), "rank order")
    need(wrong["ids"] == struct.pack("<i", 5) + batch["ids"][4:], "wrong expert assignment")
    need(
        single["x"] == batch["x"] == wrong["x"]
        and batch["reference-q8"] == single["reference-q8"] == wrong["reference-q8"],
        "identical source activation and direct conversions",
    )
    need(
        len({batch["x"][i * 11520 : (i + 1) * 11520] for i in range(3 * shared)}) == 3 * shared,
        "distinct RHS per position/rank",
    )
    need(single["reference-q8"] == single["q8"], "AR Q8 workspace independent converter")
    for suffix, stride in sizes.items():
        need(
            captured["permuted"][suffix] == compare_positions(batch[suffix], stride, (2, 0, 1)),
            "native position permutation " + suffix,
        )
    row = 2880 * 4
    need(
        wrong["f32"][row:] == batch["f32"][row:] and wrong["q8"] == batch["q8"],
        "corruption outside mutated rank",
    )
    changed_control = words(batch["f32"][:row], wrong["f32"][:row])["changed"]
    need(
        changed_control > 0
        and len({batch["f32"][i * row : (i + 1) * row] for i in range(12)}) == 12,
        "rank/weight discrimination",
    )
    detail = []
    for i in range(3):
        by_rank = []
        for rank in range(4):
            at = (4 * i + rank) * row
            by_rank.append(words(single["f32"][at : at + row], batch["f32"][at : at + row]))
        detail.append(by_rank)
    return dict(
        shape=[2880, shared, 3],
        output_shape=[2880, 4, 3],
        f32_words=34560,
        by_position_rank=detail,
        first_position_changed=sum(x["changed"] for x in detail[0]),
        all_changed=sum(x["changed"] for pos in detail for x in pos),
        q8_bytes=len(batch["q8"]),
        q8_changed=sum(x != y for x, y in zip(single["q8"], batch["q8"], strict=True)),
        wrong_expert_changed=changed_control,
        unchanged_other_ranks=11,
        distinct_output_rows=12,
        ar_sha256={k: hashlib.sha256(v).hexdigest() for k, v in single.items()},
        batch_sha256={k: hashlib.sha256(v).hexdigest() for k, v in batch.items()},
        native_position_permutation_verified=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "run"))
    for name in ("backend", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--build-sha256")
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    out = args.new_output_dir.resolve()
    os.umask(0o077)
    out.mkdir()
    result = {"status": "FAIL_PRESERVED", "mode": args.mode, "native_executions": 0}
    start = time.monotonic()
    try:
        cg = bounds()
        need(
            git(HERE, "rev-parse", "HEAD") == args.commit
            and not git(HERE, "status", "--porcelain"),
            "clean frozen method",
        )
        need(
            git(args.backend, "rev-parse", "HEAD") == COMMIT
            and sha(HERE / "protocol.md") == PROTOCOL,
            "protocol/source pin",
        )
        libs = args.backend / "build-c269-cuda/bin"
        need(
            all(sha(args.backend / f) == h for f, h in PINS.items())
            and all(sha(libs / f) == h for f, h in LIBS.items()),
            "pinned sources/libraries",
        )
        sources = {
            n: sha(HERE / n) for n in ("fixture.cpp", "run.py", "protocol.md", "test_run.py")
        }
        result.update(
            commit=args.commit,
            tree=git(HERE, "rev-parse", "HEAD^{tree}"),
            backend_commit=COMMIT,
            source_sha256=sources,
            libs=LIBS,
            cgroup_max_bytes=LIMIT,
            swap_max_bytes=0,
            architecture=platform.machine(),
            cpu_model=next(
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            kernel=platform.release(),
        )
        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "LD_LIBRARY_PATH": str(libs),
            "OMP_DYNAMIC": "FALSE",
            "OMP_THREAD_LIMIT": "8",
            "OMP_NUM_THREADS": "8",
            "TMPDIR": str(out),
        }
        if args.mode == "build":
            need(args.build_dir is None and args.build_sha256 is None, "unexpected build input")
            binary = out / "fixture"
            cmd = [
                "/usr/bin/g++",
                "-std=c++17",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-fopenmp",
                "-fPIC",
                "-pie",
                "-fno-plt",
                "-I",
                args.backend / "ggml/include",
                HERE / "fixture.cpp",
                "-L",
                libs,
                "-lggml-cpu",
                "-lggml-base",
                "-lcrypto",
                "-ldl",
                "-o",
                binary,
            ]
            with (out / "compile.log").open("xb") as log:
                subprocess.run(
                    cmd, env=env, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=50
                )
            result.update(
                status="BUILT_CPU_ROW_GEOMETRY",
                binary_sha256=sha(binary),
                compiler_sha256=sha(Path(cmd[0])),
                compiler_options=list(map(str, cmd[1:])),
            )
        else:
            build_file = args.build_dir / "receipt.json"
            need(sha(build_file) == args.build_sha256, "build seal")
            build = json.loads(build_file.read_bytes())
            binary = args.build_dir / "fixture"
            need(
                build["status"] == "BUILT_CPU_ROW_GEOMETRY"
                and build["libs"] == LIBS
                and build["source_sha256"] == sources
                and sha(binary) == build["binary_sha256"]
                and build["commit"] == args.commit,
                "frozen executable",
            )
            result.update(build_sha256=args.build_sha256, binary_sha256=sha(binary))
            with (
                (out / "native.tsv").open("xb") as stdout,
                (out / "native.stderr").open("xb") as stderr,
            ):
                result["native_executions"] = 1
                subprocess.run(
                    [binary, out / "rows"],
                    env=env,
                    check=True,
                    timeout=40,
                    stdout=stdout,
                    stderr=stderr,
                )
            pairs = [v.split(" ", 1) for v in (out / "native.tsv").read_text().splitlines()]
            native = dict(pairs)
            need(
                len(native) == len(pairs) == 6
                and native["status"] == "PASS_CAPTURED_CPU_MMID"
                and set(native) == {"weight_sha256", "dot", "convert", "cpu", "base", "status"},
                "native witness",
            )
            for k in ("dot", "convert", "cpu", "base"):
                role = "base" if k == "base" else "cpu"
                selected = libs / ("libggml-" + role + ".so.0.15.3")
                need(
                    Path(native[k]) == selected.resolve() and sha(selected) == LIBS[selected.name],
                    "provider mismatch " + k,
                )
            arms = {str(s): grade(out / "rows", s) for s in (1, 4)}
            sizes = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
            need(sizes < 8 << 20, "output cap")
            result.update(
                status="MEASURED_CPU_ROW_GEOMETRY",
                cases=arms,
                providers={k: Path(native[k]).name for k in ("dot", "convert", "cpu", "base")},
                weight_sha256=native["weight_sha256"],
                weights_bytes=40 * 4406400,
                configured_threads=8,
                model_bytes_read=0,
                raw_bytes=sizes,
                decision="DEPENDENCE_OBSERVED"
                if any(i["all_changed"] or i["q8_changed"] for i in arms.values())
                else "BITWISE_EQUAL_FOR_BOTH_FIXTURE_INPUTS",
            )
        result.update(
            cgroup_peak_bytes=int((cg / "memory.peak").read_text()),
            swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
        )
        need(
            result["cgroup_peak_bytes"] <= LIMIT and result["swap_peak_bytes"] == 0, "resource cap"
        )
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result["tool_wall_s"] = time.monotonic() - start
    result["child_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    with (out / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", result.get("decision", "")), flush=True)
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    sys.exit(main())

"""Authenticated C269 mixed-scheduler synthetic fixture, under external hardware supervision."""

import argparse
import hashlib
import json
import resource
import struct
import subprocess
import sys
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from packed_cpu_views import test_direct_io as dio  # noqa: E402
from packed_cpu_views import test_operator as cpu  # noqa: E402

PROTOCOL = "8bd267ff7756ddf54684c459f4f64544ce833692e6a8cc2bfdee0e1771f1df23"
OBSERVATION = "b7583e6e8b2d1940063512a2b0f6936b5c405bc199d12acd9ebb45d51a83900a"
CRYPTO = Path("/usr/lib64/libcrypto.so.3")
CRYPTO_SHA = "695648ac8dc5e6a2b70e5e72399940de0f84bf24fddb7dd18949ba40bc575c72"
FROZEN = {
    "operator.cpp": "8bba9315cb8647f42e1cae68b5384195f67f5aa3f55f4ec9946cd28d1aa4ec23",
    "test_operator.py": "1fd218dc882717c4a877bdfbe519401749d00cf5e5eeab99e68ef8d980e74031",
    "test_direct_io.py": "c97ad4daa175b2f14c3532b1f968e47a6d04978da7bac356a1caf65a12b26d63",
}
LIBS = {
    **cpu.LIBS,
    "libggml-cuda.so.0.15.3": "ff43655b15df5f3de1d5e00b0da18469a14f118bd644eb4b6d7f1915c85a4493",
}
HEADERS = {
    **cpu.HEADERS,
    "ggml-cuda.h": "84122bf381c24709eab9e888034956eafc1dfe436f9d826c10fa0e1a695f8a5e",
}
require = cpu.require


def prerequisite(path, sha):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == sha, "prerequisite digest")
    return json.loads(data)


def route(n, p, r):
    return 34 + r if n == 3 and r >= 2 else (39, 0, 7, 23)[(r + p) % 4]


def stage_witness(line, layout, n, k, before, masked):
    fields = line.split()
    require(len(before) == len(masked) == n * 4 * 2880 * 4, "stage sample extent")
    require(len(fields) == 15 and fields[:3] == [layout, str(n), str(k)], "stage journal order")
    buf, addr = map(int, fields[3:5])
    require(buf in (0, 1) and addr in (0, 1), "alias flags")
    cpu_hash, pre_hash, mask_hash, late_hash, out_hash = fields[5:10]
    count, outside, first, old_bits, new_bits = map(int, fields[10:])
    masks = [float(n != 3 or r < 2) for _ in range(n) for r in range(4)]
    mask_bytes = struct.pack(f"<{4 * n}f", *masks)

    def digest(b):
        return hashlib.sha256(b).hexdigest()

    require(
        cpu_hash == pre_hash == digest(before)
        and out_hash == digest(masked)
        and mask_hash == digest(mask_bytes),
        "CPU/pre-mask transfer or masked result",
    )
    require(
        len(late_hash) == 64 and all(c in "0123456789abcdef" for c in late_hash),
        "invalid late diagnostic digest",
    )
    require(
        0 <= outside <= count <= n * 4 * 2880 and ((count == 0) == (late_hash == pre_hash)),
        "late comparison counts",
    )
    require(
        (count == 0 and (first, old_bits, new_bits) == (-1, 0, 0))
        or (
            count > 0
            and 0 <= first < n * 4 * 2880
            and old_bits != new_bits
            and old_bits == struct.unpack_from("<I", before, first * 4)[0]
        ),
        "first V2 disagreement",
    )
    if addr:
        require(late_hash == out_hash, "same address but different post-MUL values")
        previous = memoryview(before).cast("I")
        current = memoryview(masked).cast("I")
        differences = [i for i, (a, b) in enumerate(zip(previous, current, strict=True)) if a != b]
        outside_expected = sum(n != 3 or (i // 2880) % 4 < 2 for i in differences)
        i = differences[0] if differences else -1
        require(
            (count, outside, first) == (len(differences), outside_expected, i)
            and (i == -1 or new_bits == current[i]),
            "V2 counterfactual bytes",
        )
    return dict(
        layout=layout,
        component=k,
        same_buffer=bool(buf),
        same_address=bool(addr),
        cpu_mmid_sha256=cpu_hash,
        cuda_source_before_sha256=pre_hash,
        mask_sha256=mask_hash,
        cuda_source_after_sha256=late_hash,
        cuda_output_sha256=out_hash,
        late_v2_mismatches=count,
        late_v2_mismatches_outside_parking=outside,
        first_late_v2_difference=None
        if first < 0
        else dict(
            position=first // (4 * 2880),
            rank=(first // 2880) % 4,
            row=first % 2880,
            before_bits=old_bits,
            after_bits=new_bits,
        ),
    )


def verify_native(out, libs):
    scopes = {}
    summary = (out / "stdout.txt").read_text().splitlines()
    require(len(summary) == 3, "wrong graph count")
    journal = (out / "native/boundary.tsv").read_text().splitlines()
    require(len(journal) == 18, "missing callback observations")
    seq = 0
    for n, line in zip((1, 32, 3), summary, strict=True):
        fields = line.split()
        require(len(fields) == 5 and fields[0] == "PASS", "incomplete split observation")
        size, dense, packed, count = map(int, fields[1:])
        require(
            n == size and min(dense, packed) >= 3 and count == 3 * n * 4 * 2880,
            "mixed graph or coverage",
        )
        path = out / "native" / f"{n}.f32"
        require(
            path.stat().st_size == 2 * count * 4 and sys.byteorder == "little",
            "output size or endian",
        )
        values = array("f")
        with path.open("rb") as source:
            values.fromfile(source, 2 * count)
        i = 0
        for k in range(3):
            for p in range(n):
                for r in range(4):
                    slot = route(n, p, r)
                    ch = r if k == 1 else 0
                    for y in range(2880):
                        col = (29 * y + 67 * slot + 347 * k + 31) % 2880
                        x = 127 if col % 32 == 0 else (19 * col + 31 * p + 37 * ch) % 223 - 111
                        gold = -x if (slot + y // 7 + k) % 2 else x
                        require(
                            values[i] == gold
                            and values[count + i] == (0 if n == 3 and r >= 2 else gold),
                            "independent mixed numeric or parking mask",
                        )
                        i += 1
        scopes[n] = dict(
            position_count=n,
            raw_and_masked_values_each=count,
            dense_splits=dense,
            packed_splits=packed,
            result_sha256=cpu.digest(path),
            cpu_weight_operand_witnesses_per_layout=3,
            cuda_to_cpu_activation_and_id_edges_per_layout=6,
            cpu_to_cuda_output_edges_per_layout=3,
        )
        records = []
        as_bytes = memoryview(values).cast("B")
        step = (count // 3) * 4
        for layout in ("dense", "packed"):
            for k in range(3):
                start = k * step
                records.append(
                    stage_witness(
                        journal[seq],
                        layout,
                        n,
                        k,
                        as_bytes[start : start + step],
                        as_bytes[4 * count + start : 4 * count + start + step],
                    )
                )
                seq += 1
        scopes[n]["cuda_mask_boundary"] = records
    paths_digest = dict(LIBS)
    paths_digest[CRYPTO.name] = CRYPTO_SHA
    paths = (out / "native/providers.txt").read_text().splitlines()
    for name, p in zip(paths_digest, paths, strict=True):
        expected = CRYPTO if name == CRYPTO.name else libs / name
        require(
            Path(p).samefile(expected) and cpu.digest(Path(p)) == paths_digest[name],
            "mapped GGML provider",
        )
    return scopes


def main(args):
    out = args.new_output_dir.resolve()
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = dict(status="FAIL_PRESERVED")
    try:
        require(not cpu.git(HERE, "status", "--porcelain"), "dirty checkout")
        require(cpu.digest(HERE / "contract.md") == PROTOCOL, "protocol")
        require(
            cpu.digest(HERE / "observacao.md") == OBSERVATION and cpu.digest(CRYPTO) == CRYPTO_SHA,
            "observation contract or witness hashing provider",
        )
        for name, pin in FROZEN.items():
            require(cpu.digest(HERE.parent / "packed_cpu_views" / name) == pin, "frozen fixture")
        before = prerequisite(args.cpu_receipt, args.cpu_sha256)
        require(
            before["status"] == "PASS_CPU_MMID_SYNTHETIC_PACKED_VIEWS"
            and before["program_sha256"] == FROZEN["operator.cpp"]
            and before["finite_bitwise_values"] == 103680
            and before["providers_sha256"] == cpu.LIBS
            and min(before["wrong_component_mismatches"], before["wrong_stride_mismatches"]) > 0,
            "CPU gate",
        )
        io = dio.verify(prerequisite(args.io_receipt, args.io_sha256), True)
        require(io["status"] == "PASS_BTRFS_NVME_DIRECT_FIXTURE", "physical direct I/O gate")
        backend = args.backend.resolve(strict=True)
        require(cpu.git(backend, "rev-parse", "HEAD") == cpu.PIN, "C269 pin")
        include = backend / "ggml/include"
        libs = backend / "build-c269-cuda/bin"
        for name, pin in HEADERS.items():
            require(cpu.digest(include / name) == pin, "header " + name)
        for name, pin in LIBS.items():
            require(cpu.digest(libs / name) == pin, "ELF " + name)
        receipt.update(
            commit=cpu.git(HERE, "rev-parse", "HEAD"),
            tree=cpu.git(HERE, "rev-parse", "HEAD^{tree}"),
            protocol_sha256=PROTOCOL,
            observation_sha256=OBSERVATION,
            hash_provider_sha256=CRYPTO_SHA,
            program_sha256=cpu.digest(HERE / "mixed.cpp"),
            runner_sha256=cpu.digest(Path(__file__)),
            prerequisite_sha256={"cpu": args.cpu_sha256, "io": args.io_sha256},
            backend_commit=cpu.PIN,
            headers_sha256=HEADERS,
            providers_sha256=LIBS,
        )
        cxx = Path("/usr/bin/g++")
        exe = out / "mixed"
        cmd = [
            str(cxx),
            "-std=c++17",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fPIC",
            "-pie",
            "-fno-plt",
            "-I" + str(include),
            str(HERE / "mixed.cpp"),
            *(str(libs / name) for name in LIBS),
            str(CRYPTO),
            "-ldl",
            "-o",
            str(exe),
        ]
        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "OMP_NUM_THREADS": "2",
            "OMP_DYNAMIC": "FALSE",
            "LD_LIBRARY_PATH": str(libs),
            "CUDA_VISIBLE_DEVICES": "0",
            "CUDA_CACHE_DISABLE": "1",
        }
        with (out / "compile.log").open("wb") as log:
            subprocess.run(
                cmd, stdout=log, stderr=subprocess.STDOUT, env=env, check=True, timeout=60
            )
        receipt.update(compiler_sha256=cpu.digest(cxx), executable_sha256=cpu.digest(exe))
        (out / "native").mkdir()
        with (out / "stdout.txt").open("w") as stdout, (out / "stderr.txt").open("w") as stderr:
            subprocess.run(
                [str(exe), str(out / "native")],
                stdout=stdout,
                stderr=stderr,
                env=env,
                check=True,
                timeout=150,
            )
        scopes = verify_native(out, libs)
        reproduced = any(
            w["layout"] == "dense"
            and w["same_buffer"]
            and w["same_address"]
            and w["late_v2_mismatches"] > 0
            and w["late_v2_mismatches_outside_parking"] == 0
            for w in scopes[3]["cuda_mask_boundary"]
        )
        receipt.update(
            scopes=scopes,
            boundary_journal_sha256=cpu.digest(out / "native/boundary.tsv"),
            observation="REPRODUCED_V2_PREDICATE_ON_PARKED_ALIAS"
            if reproduced
            else "INCONCLUSIVE_PRIOR_MISMATCH",
            numeric_gates="PASS",
        )
        if not reproduced:
            receipt["status"] = "INCONCLUSIVE_PRIOR_MISMATCH"
            raise ValueError("prior mismatch not identified in the new dense tail")
        receipt["status"] = "PASS_C269_MIXED_PACKED_MMID_POINTERS"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        receipt.update(
            error=type(exc).__name__, reason=str(exc) if isinstance(exc, ValueError) else None
        )
        if (out / "stderr.txt").is_file():
            errors = [
                line
                for line in (out / "stderr.txt").read_text().splitlines()
                if line.startswith("n=")
            ]
            if errors:
                receipt["native_first_error"] = errors[0][:600]
    receipt["child_maxrss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return int("error" in receipt)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for option in ("backend", "cpu-receipt", "io-receipt", "new-output-dir"):
        p.add_argument("--" + option, type=Path, required=True)
    p.add_argument("--cpu-sha256", required=True)
    p.add_argument("--io-sha256", required=True)
    raise SystemExit(main(p.parse_args()))

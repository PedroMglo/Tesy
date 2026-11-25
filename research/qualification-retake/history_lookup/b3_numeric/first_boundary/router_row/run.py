"""Build and qualify the captured F32 router on the isolated C269 CPU backend."""

import argparse
import hashlib
import json
import math
import os
import resource
import runpy
import struct
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parents[1] / "cpu_row_geometry/run.py"
OLD_SHA = "729cc8950de2cf7886ab108f4f10b46c2f905a419df9daccf5dbdb6e8b02f955"
FAMILY = "9f4f7d6006cac1befa989df086af85a193778d8e5cae26775114b2ad66532fac"
ARCHIVE = "8baed0c5fe6f89d234107cf40e84fcb25bb2f77a7a682e3fac69be04bb7d7dfd"
WEIGHT_PREP = "a3a6028b45719ee0a1c63f689a2e6896b5a401ee394d5aa9d3188d98e72dc269"
PROTO = "6016c048e1fe10b9860f20be3a84ed63fc9817a5898449d4d62493d9e97c9634"
FIELDS = {
    "logits": "ffn_moe_logits",
    "biased": "ffn_moe_probs",
    "ids": "ffn_moe_topk",
    "mix": "ffn_moe_weights_softmax",
}
TAGS = ("ar0", "ar1", "ar2", "batch", "split", "mutant")
PINS = {
    "ggml/src/ggml-cpu/vec.cpp": "cda0babb53f9c8ff1faa7459b2c49019d15e5970dfe0c613d58e2659e919f524",
    "ggml/src/ggml-cpu/llamafile/sgemm.cpp": "f24aeb1fc097335801942337af7581e0003e793e62fc82311e13421ef2df9806",  # noqa: E501
    "src/llama-graph.cpp": "d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288",
    "src/models/openai-moe.cpp": "239407aaa98f8b65eb280e4423588ba7cefc520371811b9c47d7457fc1f469d4",
}


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path, expected):
    need(sha(path) == expected, "changed " + path.name)
    return json.loads(path.read_bytes())


def prepare(a, out):
    family = a.family
    archive = sealed(family.parent / "manifest.json", ARCHIVE)["files"]
    r = sealed(family / "receipt.json", FAMILY)
    need(r["status"] == "DIFFERENT_AT_OBSERVED_CUT", "graph reference")
    refs = {}
    inputs = {}
    for mode, item in r["arms"].items():
        arm = sealed(family / mode / "receipt.json", item["receipt_sha256"])
        need(
            arm["same_mode_off"]["bitwise"] and arm["status"] == "PASS_NUMERIC_ARM_" + mode,
            "OFF gate",
        )
        raw = family / mode / "raw"
        unit = arm["unit"]
        stderr = raw / (unit + ".stderr")
        ident = archive[str(stderr.relative_to(family.parent))]
        need(
            sha(stderr) == ident["sha256"]
            and "load_tensors: layer   0 assigned to device CPU, is_swa = 1" in stderr.read_text(),
            "original placement",
        )
        folder = raw / (unit + ".capture") / "boundary"

        def rows(stage, folder=folder, arm=arm):
            result = []
            for i in range(189, 192):
                key = f"{i}.{stage}-0.bin"
                path = folder / key
                need(sha(path) == arm["coverage"]["files_sha256"][key], "capture " + key)
                result.append(path.read_bytes())
            return b"".join(result)

        inputs[mode] = rows("attn_post_norm")
        refs[mode] = {field: rows(stage) for field, stage in FIELDS.items()}
    need(
        set(refs) == {"AR", "B3"}
        and inputs["AR"] == inputs["B3"]
        and len(inputs["AR"]) == 3 * 2880 * 4,
        "identical three router inputs",
    )
    x = out / "source.f32"
    x.write_bytes(inputs["AR"])
    p = sealed(a.weights_dir / "prepare.json", WEIGHT_PREP)
    need(
        p["status"] == "PASS_PREPARED_REAL_TILE"
        and p["router_source_offsets"] == {"bias": 2402924576, "weight": 2402925088},
        "source offsets",
    )
    params = [a.weights_dir / "router.weight", a.weights_dir / "router.bias", x]
    for path, size in zip(params[:2], (1474560, 512), strict=True):
        need(
            path.stat().st_size == size and sha(path) == p["file_sha256"][path.name],
            "source " + path.name,
        )
    return params, refs


def difference(a, b):
    need(len(a) == len(b) and len(a) % 4 == 0, "word shape")
    return sum(
        x != y
        for x, y in zip(struct.iter_unpack("<I", a), struct.iter_unpack("<I", b), strict=True)
    )


def control(original, mutant):
    need(len(original) == len(mutant) == 3 * 128 * 4, "mutation geometry")
    for start in (0, 512, 1024):
        row = original[start : start + 512]
        need(
            row[:4] != row[4:8] and mutant[start : start + 512] == row[4:8] + row[:4] + row[8:],
            "mutated two expert rows",
        )


def results(root, refs):
    outputs = {}
    grades = {}
    for tag in TAGS:
        outputs[tag] = {f: (root / (tag + "." + f)).read_bytes() for f in FIELDS}
        for field, data in outputs[tag].items():
            n = 128 if field in ("logits", "biased") else 4
            need(len(data) == 4 * n * (1 if tag.startswith("ar") else 3), "output length")
            if field == "ids":
                ids = struct.unpack("<" + "i" * (len(data) // 4), data)
                need(
                    all(
                        len(set(ids[i : i + 4])) == 4
                        and min(ids[i : i + 4]) >= 0
                        and max(ids[i : i + 4]) < 128
                        for i in range(0, len(ids), 4)
                    ),
                    "top-four domain",
                )
            else:
                need(
                    all(math.isfinite(v[0]) for v in struct.iter_unpack("<f", data)),
                    "finite output",
                )
    for tag, mode in [("single", "AR"), ("batch", "B3"), ("split", "AR")]:
        grades[tag] = {}
        for field in FIELDS:
            data = (
                b"".join(outputs[t][field] for t in TAGS[:3])
                if tag == "single"
                else outputs[tag][field]
            )
            grades[tag][field] = difference(refs[mode][field], data)
    control(outputs["batch"]["logits"], outputs["mutant"]["logits"])
    return grades, {p.name: sha(p) for p in sorted(root.iterdir())}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["build", "run"])
    for name in ("backend", "new-output-dir", "build-dir", "family", "weights-dir"):
        p.add_argument("--" + name, type=Path, required=name in ("backend", "new-output-dir"))
    p.add_argument("--build-sha256")
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    started = time.monotonic()
    r = {"status": "FAIL_PRESERVED", "native_executions": 0}
    try:
        need(sha(OLD) == OLD_SHA, "previous CPU authority")
        base = runpy.run_path(str(OLD))
        cg = base["bounds"]()
        git = base["git"]
        b = a.backend.resolve()
        need(
            git(b, "rev-parse", "HEAD") == base["COMMIT"]
            and git(HERE, "rev-parse", "HEAD") == a.commit
            and not git(HERE, "status", "--porcelain"),
            "clean frozen checkout and C269",
        )
        need(sha(HERE / "protocol.md") == PROTO, "protocol")
        for file, h in (PINS | base["PINS"]).items():
            need(sha(b / file) == h, "C269 " + file)
        libs = b / "build-c269-cuda/bin"
        for file, h in base["LIBS"].items():
            need(sha(libs / file) == h, "provider " + file)
        r.update(
            commit=a.commit,
            tree=git(HERE, "rev-parse", "HEAD^{tree}"),
            backend_commit=base["COMMIT"],
            libs=base["LIBS"],
            sources={
                f: sha(HERE / f) for f in ("fixture.cpp", "run.py", "test_run.py", "protocol.md")
            },
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
        variants = ("plain", "counted")
        if a.mode == "build":
            executables = {}
            cxx = Path("/usr/bin/g++-15")
            need(
                sha(cxx) == "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a",
                "CXX",
            )
            for variant in variants:
                extra = ["-DCOUNT_DISPATCH", "-Wl,--export-dynamic"] if variant == "counted" else []
                cmd = [
                    cxx,
                    "-std=c++17",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-fPIC",
                    "-pie",
                    "-fno-plt",
                    *extra,
                    "-I",
                    b / "ggml/include",
                    HERE / "fixture.cpp",
                    "-L",
                    libs,
                    "-lggml-cpu",
                    "-lggml-base",
                    "-ldl",
                    "-o",
                    out / variant,
                ]
                with (out / (variant + ".compile")).open("xb") as log:
                    subprocess.run(
                        cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=60, check=True
                    )
                executables[variant] = sha(out / variant)
            r.update(status="BUILT_ROUTER_ROW", executables=executables, compiler_sha256=sha(cxx))
        else:
            build = sealed(a.build_dir / "receipt.json", a.build_sha256)
            need(
                build["status"] == "BUILT_ROUTER_ROW"
                and all(
                    build[k] == r[k]
                    for k in ("commit", "tree", "libs", "backend_commit", "sources")
                ),
                "builder provenance",
            )
            r.update(build_sha256=a.build_sha256, executables=build["executables"])
            params, refs = prepare(a, out)
            r["inputs"] = {p.name: sha(p) for p in params}
            r["reference_sha256"] = {
                k: {f: hashlib.sha256(v).hexdigest() for f, v in row.items()}
                for k, row in refs.items()
            }
            counts, hashes = {}, {}
            for variant in variants:
                exe = a.build_dir / variant
                need(sha(exe) == build["executables"][variant], "frozen process")
                with (
                    (out / (variant + ".out")).open("xb") as log,
                    (out / (variant + ".err")).open("xb") as err,
                ):
                    r["native_executions"] += 1
                    subprocess.run(
                        [exe, *params, out / variant],
                        env=env,
                        stdout=log,
                        stderr=err,
                        check=True,
                        timeout=60,
                    )
                rows = [
                    line.split() for line in (out / (variant + ".out")).read_text().splitlines()
                ]
                names = {row[0]: row[1:] for row in rows}
                providers = {"cpu": "cpu", "base": "base"} | (
                    {"llamafile_sgemm": "cpu", "ggml_vec_dot_f32": "cpu"}
                    if variant == "counted"
                    else {}
                )
                need(
                    len(rows) == len(names) and names.keys() == set(providers) | set(TAGS),
                    "native records",
                )
                for key, role in providers.items():
                    real = libs / ("libggml-" + role + ".so.0.15.3")
                    need(names[key] == [str(real.resolve())], "native provider " + key)
                counts[variant] = {t: list(map(int, names[t])) for t in TAGS}
                for v in counts[variant].values():
                    need(len(v) == 5 and min(v) >= 0, "dispatch counters")
                grades, hashes[variant] = results(out / variant, refs)
                r[variant + "_vs_target"] = grades
            r["dispatch"] = counts["counted"]
            need(
                hashes["counted"] == hashes["plain"]
                and all(not any(v) for v in counts["plain"].values()),
                "observer changes output",
            )
            r["output_sha256"] = hashes["plain"]
            grades = r["plain_vs_target"]
            r["same_mode_reproduced"] = not any(
                v for k in ("single", "batch") for v in grades[k].values()
            )
            c = counts["counted"]
            switch = all(
                c[t][0] > 0 and c[t][1:4] == [0, 0, 0] and c[t][4] > 0 for t in (*TAGS[:3], "split")
            ) and all(
                c[t][:3] == [0, 0, 0] and c[t][3] > 0 and c[t][4] == 0 for t in ("batch", "mutant")
            )
            r.update(
                status="MEASURED_ROUTER_ROW",
                dispatch_result="N1_DOT_N3_SGEMM" if switch else "INCONCLUSIVE_DISPATCH",
                full_router_restored=r["same_mode_reproduced"]
                and not any(grades["split"].values()),
                logits_restored=r["same_mode_reproduced"] and grades["split"]["logits"] == 0,
            )
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    r["wall_s"] = time.monotonic() - started
    r["child_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if "cg" in locals():
        r["cgroup_peak_bytes"] = int((cg / "memory.peak").read_text())
    if (
        sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) >= (8 << 20)
        or r["wall_s"] > 120
    ):
        r.update(status="FAIL_PRESERVED", reason="output or wall cap")
    (out / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

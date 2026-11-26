"""Reproduce the crashing C291 library, generalize L25, and test the actual CUDA row expression."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = run_path(str(HERE.parent / "family.py"))
G, Q, need, sha, save = (F[k] for k in ("G", "Q", "need", "sha", "save"))
OLD = "55a0322b12a108fa1b15ab01ac8a7f4194934d32b659f2cd97f0c17ae20ed59b"
METHOD = "740b62b092ca9950468b55ac25d6b6e7b238fe0b4743e3fe320b548424bb5ffa"
FAIL = "8ded50541e00c395920eb5e690329ac5b923473b8e9b075dfb312af122aef2b7"
OP = (
    Q
    / "history_lookup/b3_numeric/first_boundary/router_row/integrated/input_l25"
    / "serial_reference/attention/row_operator"
)
P = run_path(str(OP / "run.py"))
WIDTHS = (256, 512, 2048, 2304, 8192)
OLD_GUARD = "q->ne[3] == 1 && k->ne[1] > 0 && (il != 25 || k->ne[1] == 256)"
NEW_GUARD = "q->ne[3] == 1 && k->ne[1] > 0 && k->ne[1] <= 8192"


def same_graph(source):
    need(source.count(OLD_GUARD) == 1 and NEW_GUARD not in source, "unique old constraint")
    for binding in (
        "kq_mask->ne[0] == k->ne[1]",
        "ggml_are_same_shape(k,v)",
        "ggml_view_2d(ctx0, kq_mask, k->ne[1], 1, kq_mask->nb[1], j * kq_mask->nb[1])",
    ):
        need(source.count(binding) >= 1, "KV/mask agreement")
    candidate = source.replace(OLD_GUARD, NEW_GUARD)
    need(candidate.replace(NEW_GUARD, OLD_GUARD) == source, "single source substitution")
    return candidate


def build(a, out, r):
    previous = G["read"](a.old / "receipt.json", OLD)
    failed = G["read"](a.failed / "receipt.json", FAIL)
    static = G["read"](a.static / "receipt.json", G["STATIC"])
    need(failed["status"] == "FAIL_PRESERVED" and failed["model_starts"] == 1, "real first draft")
    prefix = a.old / "BLOCK"
    image = G["IMAGE"]

    def original(name):
        p = prefix / name
        need(sha(p) == previous["files"]["BLOCK/" + name], name)
        return p

    source = original("llama-graph.cpp").read_text()
    fixed = same_graph(source)
    work = (
        Path(static["arms"]["C281_PACK"]["closure"]["libllama.so.0"]["file"]).parents[1] / "llama"
    )
    inv = G["read"](a.old / "objects.json", previous["files"]["objects.json"])

    def check_objects():
        need(G["digest"]({k: sha(work / k) for k in inv}) == G["OBJECTS"], "166 C291 objects")

    check_objects()
    headers = json.loads(original("headers.json").read_bytes())
    need(all(sha(Path(k)) == h for k, h in headers.items()), "previous headers")
    env = dict(PATH="/usr/bin:/bin", LC_ALL="C", LANG="C", TMPDIR=str(out), CUDA_VISIBLE_DEVICES="")
    need(
        G["toolchain"](env) == previous["compiler_tools"]
        and sha(Path("/usr/bin/c++")) == G["DRIVER"],
        "same compiler",
    )
    for k, h in previous["link_inputs"].items():
        need(sha(Path(k)) == h, "ggml link input")
    image_sha = previous["arms"]["BLOCK"]["image_sha256"]
    need(sha(prefix / image) == image_sha, "published original")
    r["arms"] = {}
    for name, code in (("CONTROL", source), ("WIDE", fixed)):
        dest = out / name
        dest.mkdir()
        new = dest / "llama-graph.cpp"
        new.write_text(code)

        for cmd in ("compile", "link"):
            old_args = json.loads(original(cmd + "-argv.json").read_bytes())
            args = [word.replace(str(prefix), str(dest)) for word in old_args]
            G["command"](args, work, dest, cmd, env)
        deps = G["headers"](dest / "actual.d", work)
        expect = dict(headers)
        del expect[str(prefix / "llama-graph.cpp")]
        need(deps == expect | {str(new): sha(new)}, "compiler header set")
        so = dest / image
        (dest / "libllama.so.0").symlink_to(image)
        need(G["ABI"](so) == previous["original_abi"], "export and ABI")
        new_hash = sha(so)
        if name == "CONTROL":
            need(
                new_hash == image_sha
                and sha(dest / "llama-graph.cpp.o") == previous["arms"]["BLOCK"]["object_sha256"],
                "current rebuild of the crashing control",
            )
        else:
            need(new_hash != image_sha, "compiled guard")
        r["arms"][name] = dict(
            image_sha256=new_hash,
            source_sha256=sha(new),
            providers={
                k: G["loader"](static["arms"][k], so, dest, k, env)["providers"]
                for k in ("C270_PACK", "C281_PACK")
            },
        )
    check_objects()
    start = fixed.index("            ggml_tensor *rows[3];", fixed.index(NEW_GUARD))
    stop = fixed.index("            cb(cur, LLAMA_TENSOR_NAME_FATTN, il);", start)
    expr = fixed[start:stop]
    need(
        expr.count("ggml_flash_attn_ext(") == 1
        and expr.count("ggml_concat(") == 2
        and "ggml_view_4d(ctx0, q," in expr
        and "ggml_view_2d(ctx0, kq_mask," in expr,
        "production expression",
    )
    template = (HERE / "fixture.cpp.in").read_text()
    need(template.count("@PRODUCTION_ROWS@") == 1, "fixture insertion")
    (out / "fixture.cpp").write_text(template.replace("@PRODUCTION_ROWS@", expr))
    compiler = Path("/usr/bin/g++-15")
    need(
        sha(compiler) == "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a"
        and G["tree"](a.backend)[0] == F["F"]["OLD"]["C269"],
        "fixture compiler and ggml source",
    )
    lib = a.backend / "build-c269-cuda/bin"
    env = G["START"]["environment"]([str(lib)])
    G["command"](
        [
            compiler,
            "-std=c++17",
            "-O2",
            "-MMD",
            "-MF",
            out / "fixture.d",
            "-I",
            a.backend / "ggml/include",
            out / "fixture.cpp",
            "-L",
            lib,
            "-Wl,-rpath," + str(lib),
            "-lggml-cuda",
            "-lggml-base",
            "-o",
            out / "fixture",
        ],
        out,
        out,
        "fixture",
        env,
    )
    text = subprocess.check_output(["/usr/bin/ldd", "-r", out / "fixture"], text=True, env=env)
    need("undefined symbol" not in text and "not found" not in text, "fixture closure")
    (out / "fixture.ldd").write_text(text)
    providers = {
        k: dict(file=str(p.resolve(strict=True)), sha256=sha(p))
        for k, p in G["START"]["interpret"](text).items()
    }
    need(
        all(static["arms"]["C281_PACK"]["closure"][k] == v for k, v in providers.items()),
        "all fixture providers qualified",
    )
    r.update(
        status="GO_STATIC_WIDE_KV",
        fixture_sha256=sha(out / "fixture"),
        providers=providers,
        program_sha256=sha(out / "fixture.cpp"),
        previous_sha256=OLD,
    )


def execute(a, out, r):
    b = G["read"](a.build / "receipt.json", a.build_sha256)
    need(
        b["status"] == "GO_STATIC_WIDE_KV"
        and sha(a.build / "fixture") == b["fixture_sha256"]
        and b["protocol_sha256"] == METHOD
        and b["commit"] == a.commit,
        "admitted fixture",
    )
    s = G["read"](a.static / "receipt.json", G["STATIC"])
    win = G["read"](a.window / "receipt.json", a.window_sha256)
    policy = G["read"](a.window / "resource-policy.json", win["canonical_policy_sha256"])
    from datetime import UTC, datetime

    F["TRANS"]["c55_age"](policy["snapshot"]["utc"], datetime.now(UTC))
    permitted = {Path(v["file"]).name: v["sha256"] for v in b["providers"].values()}
    permitted.update(
        {Path(k).name: h for k, h in s["driver_files"].items() if k.startswith("/usr/lib64/")}
    )
    r["admission"] = P["sampled"](policy, None, None)
    r.update(build_sha256=a.build_sha256, window_sha256=a.window_sha256, live={})
    known = dict(permitted_providers=permitted, current_providers=b["providers"])
    env = G["START"]["environment"]([str(a.backend / "build-c269-cuda/bin")])
    data = out / "device"
    with (
        (out / "stdout").open("xb") as so,
        (out / "stderr").open("xb") as se,
        subprocess.Popen([a.build / "fixture", data], env=env, stdout=so, stderr=se) as child,
    ):
        r["operator_starts"] = 1
        try:
            for point in ("before", "after"):
                limit = time.monotonic() + 45
                flag = data / (point + ".ready")
                while not flag.exists():
                    need(child.poll() is None and time.monotonic() < limit, "missing " + point)
                    time.sleep(0.01)
                need(flag.read_text() == point, "checkpoint")
                obs = P["sampled"](policy, child.pid, r["admission"]["gpu"]["used_mib"])
                r["live"][point] = dict(gpu=obs["gpu"], providers=P["loaded"](child.pid, known, {}))
                (data / (point + ".ack")).touch(exist_ok=False)
            need(child.wait(timeout=4) == 0, "operator exit")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
    r["after_exit"] = P["sampled"](policy, None, r["admission"]["gpu"]["used_mib"])
    r["rows"] = {}
    import math
    import struct

    for n in WIDTHS:
        dest = data / str(n)
        raw = [(dest / (k + ".f32")).read_bytes() for k in ("serial", "block", "mutant")]
        need(
            len(raw[0]) == 3 * 4096 * 4
            and raw[0] == raw[1]
            and len(raw[2]) == len(raw[0])
            and all(math.isfinite(v[0]) for arr in raw for v in struct.iter_unpack("<f", arr)),
            "full finite output",
        )
        refs = list(struct.iter_unpack("<I", raw[0]))
        muts = list(struct.iter_unpack("<I", raw[2]))
        differences = [
            sum(x != y for x, y in zip(refs[j : j + 4096], muts[j : j + 4096], strict=True))
            for j in (0, 4096, 8192)
        ]
        need(
            differences[0] > 0 and differences[1] == 0 and differences[2] > 0,
            "wrong-mask falsification",
        )
        r["rows"][str(n)] = dict(
            equal_F32=len(refs),
            serial_sha256=sha(dest / "serial.f32"),
            wrong_mask_different_by_row=differences,
        )
    r["status"] = "GO_CUDA_WIDE_ATTENTION_OPERATOR"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("build", "run"))
    for k in ("old", "failed", "static", "backend", "window", "build", "new-output-dir"):
        p.add_argument(
            "--" + k,
            type=Path,
            required=k in {"old", "failed", "static", "backend", "new-output-dir"},
        )
    for k in ("commit", "window-sha256", "build-sha256"):
        p.add_argument("--" + k, required=k == "commit")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    start = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED",
        model_starts=0,
        operator_starts=0,
        protocol_sha256=METHOD,
        commit=a.commit,
    )
    try:
        cg = Path("/sys/fs/cgroup") / Path(
            Path("/proc/self/cgroup").read_text().strip()[3:]
        ).relative_to("/")
        need(
            cg.name.startswith("tesy-kv-width-")
            and (cg / "memory.max").read_text().strip() == str(4 << 30)
            and (cg / "memory.swap.max").read_text().strip() == "0",
            "bounded scope",
        )
        head, r["tree"] = G["tree"](G["REPO"])
        need(head == a.commit and sha(HERE / "protocol.md") == METHOD, "clean technical gate")
        (build if a.mode == "build" else execute)(a, out, r)
    except Exception as err:
        r.update(status="FAIL_PRESERVED", error=f"{type(err).__name__}: {err}")
    r.update(
        wall_s=time.monotonic() - start,
        files={str(x.relative_to(out)): sha(x) for x in sorted(out.rglob("*")) if x.is_file()},
    )
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""), flush=True)
    raise SystemExit(r["status"] == "FAIL_PRESERVED")

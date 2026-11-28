"""Build the C269 CPU wave experiment and compare all observable F32 bits."""

import argparse
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "research/qualification-retake/parked_fusion/numerical/build.py"
mm, _ = run_path(str(OLD))["old_modules"]()
sha, need = mm.sha, mm.need
SOURCE = "bda1c2c81077d89813c3b4776079a5ddf65eaf28bf1e33338473818cc56831f5"


def insert(data, anchor, text):
    need(data.count(anchor) == 1, "C269 source anchor")
    return data.replace(anchor, text + anchor)


def materialize(original):
    need(sha(original) == SOURCE, "CPU executor identity")
    src = insert(
        original.read_text(),
        "static int ggml_cpu_try_fuse_ops(\n",
        '#ifdef TESY_C47_CPU_SKIP_PARKED\n#include "wave.inc"\n#endif\n\n',
    )
    src = insert(
        src,
        "    if (node->op == GGML_OP_RMS_NORM) {",
        """#ifdef TESY_C47_CPU_SKIP_PARKED
    if (tesy_wave_enabled && node->op == GGML_OP_MUL_MAT_ID && !cplan->abort_callback &&
        tesy_parked_wave(cgraph, node_n, params)) return 9;
#endif
""",
    )
    return insert(
        src,
        '            const char * env = getenv("GGML_CPU_DISABLE_FUSION");',
        """#ifdef TESY_C47_CPU_SKIP_PARKED
            const char * wave = getenv("TESY_NATIVE_CPU_WAVE");
            tesy_wave_enabled = wave && !strcmp(wave, "1");
#endif
""",
    )


def cgroup(cap):
    group = (
        Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("::/", 1)[1]
    )
    need(
        int((group / "memory.max").read_text()) == cap
        and int((group / "memory.swap.max").read_text()) == 0,
        "cgroup cap/swap",
    )
    return group


def run(a, out, record):
    backend = a.backend.resolve()
    group = cgroup(1 << 30)
    build = backend / "build-c269-cuda"
    libs = build / "bin"
    need(
        mm.git(ROOT, "rev-parse", "HEAD") == a.commit
        and not mm.git(ROOT, "status", "--porcelain")
        and mm.git(backend, "rev-parse", "HEAD") == mm.PIN
        and not mm.git(backend, "status", "--porcelain", "--", "ggml"),
        "clean pins",
    )
    record.update(
        commit=a.commit,
        tree=mm.git(ROOT, "rev-parse", "HEAD^{tree}"),
        backend=mm.PIN,
        protocol=sha(HERE / "protocol.md"),
        sources={},
    )
    for f in ("wave.inc", "fixture.cpp", "build.py"):
        record["sources"][f] = sha(HERE / f)
    for base, pins in (
        (Path("/"), mm.TOOLS),
        (build, mm.CMAKE),
        (libs, {mm.BASE: mm.BASE_SHA, mm.CPU: mm.CPU_SHA}),
    ):
        need(all(sha(base / name) == value for name, value in pins.items()), "C269 dependencies")
    original = backend / mm.SOURCE
    link = mm.text(["/usr/bin/ninja", "-C", build, "-t", "commands", mm.TARGET]).splitlines()[-1]
    inputs = {s: sha(build / s) for s in shlex.split(link) if s.endswith(".o") or s in mm.DEPS}
    need(mm.manifest(inputs) == mm.INPUTS_SHA and mm.sha_text(link) == mm.LINK_SHA, "link inputs")
    record.update(link_inputs_sha256=mm.INPUTS_SHA, original_cpu_sha256=mm.CPU_SHA)
    commands = json.loads((build / "compile_commands.json").read_text())
    (recipe,) = [item for item in commands if Path(item["file"]).name == original.name]
    need(Path(recipe["file"]).samefile(original), "translation unit")
    arms = {}
    for name in ("AUDIT", "PRICE"):
        d = out / name
        d.mkdir()
        src, obj = d / original.name, d / (original.name + ".o")
        src.write_text(materialize(original))
        cc = shlex.split(recipe["command"])
        mm.replace(cc, mm.OBJECT, obj)
        mm.replace(cc, recipe["file"], src)
        cc += [
            "-iquote",
            str(original.parent),
            "-iquote",
            str(HERE),
            f"-fmacro-prefix-map={d}={original.parent}",
        ]
        if name == "AUDIT":
            cc += ["-DTESY_WAVE_AUDIT"]
        mm.commands(cc, build, out, "compile-" + name, record)
        mm.commands(mm.linker(link, d, obj), build, out, "link-" + name, record)
        (d / "libggml-cpu.so.0").symlink_to(mm.CPU)
        symbols = mm.text(["/usr/bin/nm", "-D", "--defined-only", d / mm.CPU])
        need(("tesy_cpu_wave_count" in symbols) == (name == "AUDIT"), "counter isolation")
        arms[name] = sha(d / mm.CPU)
    need(len({*arms.values(), mm.CPU_SHA}) == 3, "different images")
    record.update(arms=arms, fixture={})
    exe = out / "fixture"
    mm.commands(
        [
            "/usr/bin/g++-15",
            "-std=c++20",
            "-O2",
            "-pthread",
            "-I" + str(backend / "ggml/include"),
            "-I" + str(backend / "ggml/src"),
            HERE / "fixture.cpp",
            libs / mm.CPU,
            libs / mm.BASE,
            "-ldl",
            "-o",
            exe,
        ],
        build,
        out,
        "fixture-compile",
        record,
    )
    record["fixture_sha256"] = sha(exe)
    outputs = []
    for role in ("ORIGINAL", "OFF", "ON"):
        provider = libs if role == "ORIGINAL" else out / "AUDIT"
        env = mm.ENV | dict(
            LD_LIBRARY_PATH=os.pathsep.join(map(str, (provider, libs))),
            OMP_NUM_THREADS="8",
            OMP_DYNAMIC="FALSE",
            TESY_NATIVE_CPU_WAVE=str(int(role == "ON")),
        )
        resolved = mm.loader(
            exe, env, {"libggml-cpu.so.0": provider / mm.CPU, "libggml-base.so.0": libs / mm.BASE}
        )
        output = out / (role + ".bin")
        mm.commands([exe, role, output], out, out, role, record, env)
        data = output.read_bytes()
        line = (out / (role + ".log")).read_text().strip()
        count = 36 if role == "ON" else 0
        need(
            line == f"submissions=144 remaps=144 masks=144 fusions={count} bytes={len(data)}",
            "fixture conservation",
        )
        record["fixture"][role] = dict(
            bytes=len(data),
            sha256=sha(output),
            fusions=count,
            provider=resolved["libggml-cpu.so.0"]["sha256"],
        )
        outputs.append(data)
    need(outputs[0] == outputs[1] == outputs[2] and len(outputs[0]) > 0, "complete F32 bit parity")
    need(all(sha(build / s) == h for s, h in inputs.items()), "link inputs intact")
    record.update(
        status="PASS_NATIVE_WAVE_FIXTURE",
        memory_peak=int((group / "memory.peak").read_text()),
        swap_peak=int((group / "memory.swap.peak").read_text()),
        model_reads=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    folder = args.new_output_dir.resolve()
    folder.mkdir()
    receipt = {"status": "FAIL_PRESERVED", "commands": {}}
    start = time.monotonic()
    try:
        run(args, folder, receipt)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        receipt["reason"] = str(exc)
    receipt["elapsed_s"] = time.monotonic() - start
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(receipt["status"], receipt.get("reason", ""))
    raise SystemExit(int(receipt["status"] == "FAIL_PRESERVED"))

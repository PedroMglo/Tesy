"""Build and run two private C291 remaps on marker bytes. No model dependency."""

import argparse
import json
import os
import resource
import shutil
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = run_path(HERE.parents[1] / "packed_worker/run.py")
sha, need = BASE["sha"], BASE["need"]
R02 = "625b0e50c920938e478ff5b2f2a8bd0c85bbe2fb1f78fa4278f0e040f2ea3759"
PROTO = "dc32cfef99fe2b61b7be13c7c7232da52150220997f1301e58c9a6dedbb3090a"
CXX = "ca48a2d27d0796399adc3387225eec4be62974e26fa299710edfde0c1af5aa63"


def save(path, obj):
    with path.open("x") as f:
        json.dump(obj, f, sort_keys=True, indent=2)
        f.write("\n")


def overlay(src):
    """Insert an observation immediately after both distinct real demand lookups."""
    source = (src / "llama-moe-stream.cpp").read_text()
    needle = '#include "phase-fd-integrated.h"'
    need(source.count(needle) == 1, "PFJ header")
    source = source.replace(needle, needle + '\n#include "lookahead.h"')
    for width, declaration, sl, access in [
        (8, "const auto it", "*sl", "sl->"),
        (12, "const auto    it", "sl", "sl."),
    ]:
        prefix = " " * width
        lookup = prefix + f"{declaration} = {access}expert_slot.find(e);"
        guard = prefix + f"if (it != {access}expert_slot.end())"
        boundary = lookup + "\n" + guard
        need(source.count(boundary) == 1, "one authoritative branch in each remap")
        slot = f"it == {access}expert_slot.end() ? -1 : it->second"
        observer = prefix + f"lookahead::lookup_locked({sl}, e, {slot});"
        source = source.replace(boundary, lookup + "\n" + observer + "\n" + guard)
    (src / "llama-moe-stream.cpp").write_text(source)
    shutil.copyfile(HERE / "lookahead.h", src / "lookahead.h")
    # The actual C291 ubatch and the fixture both pass through this identical hook.
    anchor = "    const auto status = graph_compute(res->get_gf(), ubatch.n_tokens > 1);"
    hook = "    if (pfj::active()) lookahead::emit_tile(*model.moe_stream(), ubatch, n_outputs);"
    for name in ("llama-context.cpp", "borrowed-context.inc"):
        path = src / name
        data = path.read_text()
        need(data.count(anchor) == 1, "unique original graph invocation")
        if name.endswith(".cpp"):
            need(data.count(needle) == 1, "PFJ context header")
            data = data.replace(needle, needle + '\n#include "lookahead.h"')
        else:
            data = data.replace(anchor, "    const int n_outputs = ubatch.outputs;\n" + anchor)
        path.write_text(data.replace(anchor, hook + "\n" + anchor))


def inspect_source(args, out):
    r02 = json.loads((args.parent / "receipt.json").read_bytes())
    need(sha(args.parent / "receipt.json") == R02, "authenticated PFJ predecessor")
    need(r02["backend"] == BASE["PIN"] and sha(HERE / "protocol.md") == PROTO, "study pin")
    private = out / "private"
    inputs = BASE["extract"](args.backend, private)
    need(BASE["canonical"](inputs) == r02["input_blobs"], "all C291 headers and sources")
    for name in (
        "llama-moe-stream.cpp",
        "llama-context.cpp",
        "phase-fd-integrated.h",
        "borrowed-context.inc",
    ):
        path = args.parent / "private/src" / name
        need(sha(path) == r02["overlay"][name], "R02 source " + name)
        shutil.copyfile(path, private / "src" / name)
    overlay(private / "src")
    libraries = [args.libs / f"libggml-{name}.so.0.15.3" for name in ("cpu", "base")]
    need(
        all(sha(p) == r02["libs"][k] for p, k in zip(libraries, ("cpu", "base"), strict=True)),
        "CPU DSOs",
    )
    return private, libraries


def materialize(path):
    with path.open("xb") as f:
        for layer in range(36):
            for role in range(3):
                for expert in range(128):
                    f.write(bytes([(7 * layer + 13 * role + expert) % 256]) * 128)
    path.chmod(0o400)


def run(a, out, result):
    need(
        BASE["git"](ROOT, "rev-parse", "HEAD").decode().strip() == a.commit
        and not BASE["git"](ROOT, "status", "--porcelain"),
        "frozen clean measurement checkout",
    )
    cg = BASE["cgroup_reader"](ROOT, a.unit)
    result["before"] = cg()
    start = time.monotonic()
    need(sha(Path("/usr/bin/c++")) == CXX, "compiler")
    fs = subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", out], text=True)
    need(fs.strip() == "tmpfs", "tmpfs marker and byte accounting")
    private, libs = inspect_source(a, out)
    result.update(
        commit=a.commit,
        compiler_sha256=CXX,
        source_pin=BASE["PIN"],
        parent_receipt=R02,
        tree=BASE["git"](ROOT, "rev-parse", "HEAD^{tree}").decode().strip(),
        sources={
            p: sha(HERE / p)
            for p in ("protocol.md", "run.py", "fixture.cpp", "lookahead.h", "audit.py")
        },
        manager_sha256=sha(private / "src/llama-moe-stream.cpp"),
    )
    exe = out / "worker"
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "OMP_NUM_THREADS": "1",
        "LD_LIBRARY_PATH": str(a.libs),
    }

    def invoke(cmd, label, environ):
        with (
            (out / (label + ".stdout")).open("xb") as stdout,
            (out / (label + ".stderr")).open("xb") as stderr,
        ):
            subprocess.run(
                cmd, cwd=out, env=environ, check=True, timeout=120, stdout=stdout, stderr=stderr
            )

    invoke(
        [
            "/usr/bin/c++",
            "-std=c++17",
            "-pthread",
            "-O0",
            "-g0",
            "-fPIC",
            "-pie",
            "-ffunction-sections",
            "-fdata-sections",
            *["-I" + str(private / p) for p in ("src", "include", "ggml/include")],
            HERE / "fixture.cpp",
            *[private / "src" / p for p in BASE["BUILD_INPUTS"]],
            "-Wl,--gc-sections",
            *libs,
            "-o",
            exe,
        ],
        "compile",
        env,
    )
    invoke(["/usr/bin/ldd", exe], "loader", env)
    listed = (out / "loader.stdout").read_text().splitlines()
    for path in libs:
        name = path.name.split(".so")[0] + ".so.0"
        rows = [line.split() for line in listed if line.strip().startswith(name + " => ")]
        need(len(rows) == 1 and Path(rows[0][2]).resolve(strict=True) == path.resolve(), name)
    need(
        {Path(line.split()[0]).name for line in listed}
        == {
            "linux-vdso.so.1",
            "libggml-cpu.so.0",
            "libggml-base.so.0",
            "ld-linux-x86-64.so.2",
            "libstdc++.so.6",
            "libm.so.6",
            "libgcc_s.so.1",
            "libc.so.6",
            "libgomp.so.1",
        },
        "CPU-only loader closure",
    )
    marker = out / "direct-marker.bin"
    materialize(marker)
    result["binary_sha256"] = sha(exe)
    result["marker_sha256"] = sha(marker)
    arms = {}
    for mode in ("OFF", "ON"):
        arm = out / mode
        arm.mkdir()
        pfj = arm / "journal.bin"
        native = arm / "native.json"
        child_env = env | ({"TESY_PHASE_FD_FILE": str(pfj)} if mode == "ON" else {})
        invoke([exe, marker, native], mode, child_env)
        need(pfj.exists() == (mode == "ON"), "OFF opt-out")
        arms[mode] = json.loads(native.read_bytes())
    need(
        arms["OFF"] == arms["ON"] and arms["ON"]["status"] == "PASS_MARKER_BINDINGS_AND_DRAIN",
        "same native remaps",
    )
    need(len(arms["ON"]["rows"]) == 157, "154 L1 rows and three L35 outputs")
    audit = run_path(HERE / "audit.py")["audit"](out / "ON/journal.bin")
    need(
        audit["official_rows_sha256"] == BASE["canonical"](arms["OFF"]["rows"])
        and audit["service"]["jobs"] == arms["ON"]["misses"]
        and sum(audit["state_at_lookup"].values()) - audit["service"]["jobs"] == arms["ON"]["hits"],
        "native routed slots and counters vs raw job replay",
    )
    save(out / "audit.json", audit)
    need(sha(marker) == result["marker_sha256"], "same marker")
    result.update(
        status="PASS_OBSERVATION_FIXTURE_ONLY",
        native_sha256=sha(out / "ON/native.json"),
        journal_sha256=sha(out / "ON/journal.bin"),
        audit_sha256=sha(out / "audit.json"),
        resource_after=cg(),
        native_rows=157,
        hits=arms["ON"]["hits"],
        misses=arms["ON"]["misses"],
        wall_s=time.monotonic() - start,
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "parent", "libs", "new-output-dir"):
        cli.add_argument("--" + name, type=lambda s: Path(s).resolve(), required=True)
    cli.add_argument("--commit", required=True)
    cli.add_argument("--unit", required=True)
    a = cli.parse_args()
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    out = a.new_output_dir
    out.mkdir()
    result = {"status": "FAIL_PRESERVED"}
    try:
        run(a, out, result)
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    save(out / "receipt.json", result)
    print(result["status"], result.get("reason", ""), flush=True)
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))

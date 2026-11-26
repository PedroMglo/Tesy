"""Build the pinned ik HTTP frontend against the two already qualified SM89 shared libraries."""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = "7a5d90009b7ae55d3239cdd33244977c4eb10ff6"
CONFIG = "826ee49eaedc00faf8990aaedfd5d3c4875e308eed6745f16bc48511e2e0e477"
BACKEND = "5c648c09e18d29bc47d57af018053f5251f67f85bdd56cfe8f1b954c95470753"
NATIVE = "a851a28f117342ea105a17915c7b1d03a3efc116e1424f8278b792ca1d95e45c"
GIB = 1 << 30


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def receipt(path, digest):
    need(sha(path) == digest, f"receipt {path.name}")
    return json.loads(path.read_bytes())


def git(folder, *args):
    return subprocess.check_output(["git", "-C", folder, *args], text=True).strip()


def size(folder):
    total = 0
    for f in folder.rglob("*"):
        try:
            if not f.is_symlink() and f.is_file():
                total += f.stat().st_size
        except FileNotFoundError:
            continue  # a compiler can remove a temporary object during sampling
    return total


def imported_plan(plan, libraries):
    # Keep the upstream frontend targets, generated assets, definitions and link lines.
    # Each pretrained backend link edge becomes an explicit dependency on its qualified DSO.
    for dest, path in libraries.items():
        need(" " not in str(path) and "$" not in str(path), "unsupported Ninja path")
        pattern = rf"^build {re.escape(dest)}: CXX_SHARED_LIBRARY_LINKER__[^\n]+\n(?:  [^\n]+\n)*"
        plan, count = re.subn(pattern, f"build {dest}: phony {path}\n", plan, flags=re.M)
        need(count == 1, f"unique upstream library link edge {dest}")
    return plan


def build(a, out, r):
    need(
        git(HERE, "rev-parse", "HEAD") == a.commit and not git(HERE, "status", "--porcelain"),
        "clean Tesy build commit",
    )
    cg_name = next(
        line[3:]
        for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    cg = Path("/sys/fs/cgroup") / cg_name.lstrip("/")
    need(
        cg.name == a.unit + ".scope"
        and a.unit.startswith("tesy-ik-http-build-")
        and (cg / "memory.max").read_text().strip() == str(6 * GIB)
        and (cg / "memory.swap.max").read_text().strip() == "0",
        "bounded build scope",
    )
    conf = receipt(a.configure / "receipt.json", CONFIG)
    dso = receipt(a.dso / "receipt.json", BACKEND)
    hook = receipt(a.hook / "receipt.json", NATIVE)
    native = json.loads(
        (
            HERE.parents[1] / "hybrid/cold_gate/backend_input/bounded/native_hook/c110/result.json"
        ).read_bytes()
    )
    candidate = (a.hook / "candidate/libllama.so").resolve()
    need(
        native["decision"] == "GO_SERVER_CONVERSATION_GATE"
        and native["native_library_sha256"] == sha(candidate) == hook["candidate_sha256"]
        and dso["configure_sha256"] == CONFIG
        and hook["build_parent"] == BACKEND
        and sha(a.configure / "cmake-argv.json") == conf["logs_sha256"]["cmake-argv.json"]
        and all(sha(Path(k)) == v for k, v in conf["tools_sha256"].items()),
        "qualified toolchain",
    )
    src = a.source.resolve()
    need(
        git(src, "rev-parse", "HEAD") == PIN and not git(src, "status", "--porcelain"),
        "pinned ik source",
    )
    deps = {k.removeprefix("objects/"): (a.dso / k).resolve() for k in dso["libraries"]}
    need(
        set(deps) == {"ggml/src/libggml.so", "src/libllama.so"}
        and all(sha(v) == dso["libraries"]["objects/" + k] for k, v in deps.items()),
        "pinned backend DSOs",
    )
    tree = git(HERE, "rev-parse", "HEAD^{tree}")
    r.update(
        commit=a.commit,
        tree=tree,
        source_commit=PIN,
        source_tree=git(src, "rev-parse", "HEAD^{tree}"),
        configure_sha256=CONFIG,
        backend_sha256=BACKEND,
        hook_sha256=NATIVE,
        source_sha256=sha(__file__),
        protocol_sha256=sha(HERE / "protocol.md"),
    )
    obj = out / "objects"
    local = out / "source"
    logs = out / "evidence"
    logs.mkdir()
    tmp = out / "tmp"
    tmp.mkdir()
    mount = [
        "/usr/bin/bwrap",
        "--die-with-parent",
        "--unshare-net",
        "--unshare-pid",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/etc",
        "/etc",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]
    for link in ("bin", "sbin", "lib", "lib64"):
        mount += ["--symlink", os.readlink("/" + link), "/" + link]
    for path in (src, *deps.values(), candidate):
        mount += ["--ro-bind", str(path), str(path)]
    mount += ["--bind", str(out), str(out), "--chdir", str(out), "--"]
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        TMPDIR=str(tmp),
        CUDA_VISIBLE_DEVICES="",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_OPTIONAL_LOCKS="0",
    )
    start = time.monotonic()
    events0 = (cg / "memory.events").read_text()

    def run(name, args, extra=None):
        log = logs / name
        with log.open("xb") as stream:
            proc = subprocess.Popen(
                mount + list(map(str, args)),
                env=env | (extra or {}),
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                while proc.poll() is None:
                    need(
                        time.monotonic() - start < 1200 and shutil.disk_usage(out).free >= 11 * GIB,
                        "time or free space",
                    )
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        need(size(out) <= 2 * GIB, "build size")
                need(proc.returncode == 0, f"{name} exit {proc.returncode}")
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
        return log

    run("clone.log", ["git", "clone", "--local", "--no-hardlinks", "--no-checkout", src, local])
    run("checkout.log", ["git", "-C", local, "checkout", "--detach", PIN])
    need(git(local, "rev-parse", "HEAD^{tree}") == r["source_tree"], "isolated source differs")
    cmd = json.loads((a.configure / "cmake-argv.json").read_bytes())
    cmd[cmd.index("-S") + 1] = str(local)
    cmd[cmd.index("-B") + 1] = str(obj)
    for k in ("LLAMA_BUILD_EXAMPLES", "LLAMA_BUILD_SERVER"):
        cmd[cmd.index("-D" + k + "=OFF")] = "-D" + k + "=ON"
    run("configure.log", cmd)
    plan = obj / "build.ninja"
    alt = obj / "frontend.ninja"
    alt.write_text(imported_plan(plan.read_text(), deps))
    r.update(configure_argv=cmd, upstream_ninja_sha256=sha(plan), frontend_ninja_sha256=sha(alt))
    for target, lib in deps.items():
        (obj / target).symlink_to(lib)
    ninja = ["/usr/bin/ninja", "-C", obj, "-f", alt.name]
    commands = (
        run("commands.log", [*ninja, "-t", "commands", "llama-server"]).read_text().splitlines()
    )
    compile_lines = [line for line in commands if " -c " in line]
    need(
        30 <= len(compile_lines) <= 80
        and all(
            any(
                str(local / k) + "/" in line.rsplit(" -c ", 1)[1]
                for k in ("common", "examples/server", "examples/mtmd", "vendor/cpp-httplib")
            )
            and "nvcc" not in line
            for line in compile_lines
        ),
        "unexpected compile plan",
    )
    need(
        any("server.cpp" in line for line in compile_lines)
        and all(
            "-DGGML_USE_CUDA" in line
            for line in compile_lines
            if line.endswith(("/common.cpp", "/clip.cpp"))
        ),
        "unexpected server or CUDA frontend",
    )
    extra = dict(
        LD_LIBRARY_PATH=os.pathsep.join(
            [
                str(deps["ggml/src/libggml.so"].parent),
                str(deps["src/libllama.so"].parent),
                str(obj / "examples/mtmd"),
                "/usr/local/cuda-13.3/lib64",
            ]
        )
    )
    run("build.log", [*ninja, "-j2", "llama-server"], extra)
    server = obj / "bin/llama-server"
    mtmd = obj / "examples/mtmd/libmtmd.so"
    closures = {}
    for label, lib in (("ORIGINAL", deps["src/libllama.so"]), ("NATIVE", candidate)):
        path = extra["LD_LIBRARY_PATH"].split(os.pathsep)
        path[1] = str(lib.parent)
        selected = {"LD_LIBRARY_PATH": os.pathsep.join(path)}
        output = run(label + ".ldd", ["/usr/bin/ldd", "-r", server], selected).read_text()
        need(
            "not found" not in output
            and "undefined symbol" not in output
            and "/stubs/" not in output,
            "runtime loader",
        )
        providers = {
            soname: Path(p).resolve(strict=True)
            for soname, p in re.findall(r"^\s*(\S+) => (/\S+) \(0x", output, re.M)
        }
        need(
            providers["libllama.so"] == lib
            and providers["libggml.so"] == deps["ggml/src/libggml.so"]
            and providers["libmtmd.so"] == mtmd
            and providers["libcuda.so.1"].name == "libcuda.so.620.73.04",
            "server loaded unexpected providers",
        )
        loader = Path("/lib64/ld-linux-x86-64.so.2").resolve(strict=True)
        providers[loader.name] = loader
        closures[label] = {k: dict(path=str(p), sha256=sha(p)) for k, p in providers.items()}
        version = run(label + ".version", [server, "--version"], selected).read_text()
        need(PIN[:7] in version, "server pin in version")
    need(
        {k: v for k, v in closures["NATIVE"].items() if k != "libllama.so"}
        == {k: v for k, v in closures["ORIGINAL"].items() if k != "libllama.so"},
        "uncontrolled library change",
    )
    def events(text):
        return {k: int(v) for k, v in (line.split() for line in text.splitlines())}

    now = events((cg / "memory.events").read_text())
    before = events(events0)
    need(
        all(before[k] == now[k] for k in ("max", "oom", "oom_kill"))
        and int((cg / "memory.swap.peak").read_text()) == 0
        and size(out) <= 2 * GIB,
        "build resource violation",
    )
    r.update(
        status="GO_SERVER_ELF",
        executable_sha256=sha(server),
        mtmd_sha256=sha(mtmd),
        closures=closures,
        compile_units=len(compile_lines),
        seconds=time.monotonic() - start,
        output_B=size(out),
        scope_peak_B=int((cg / "memory.peak").read_text()),
        swap_B=0,
        logs_sha256={p.name: sha(p) for p in sorted(logs.iterdir())},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("source", "dso", "hook", "configure", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", model_starts=0, gpu_dispatches=0, http_requests=0)
    try:
        build(a, out, r)
    except Exception as e:
        r.update(error=f"{type(e).__name__}: {e}")
    (out / "receipt.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")

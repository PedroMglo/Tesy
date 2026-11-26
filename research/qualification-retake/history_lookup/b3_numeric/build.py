"""Build the B3 numerical client with the qualified C270 objects. No model argument."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import resource
import shlex
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
QUAL = REPO / "research/qualification-retake/nvme_r0_gate"
WORKER = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
HIST = REPO / "results/c269-layer-last-use-engineering-20261004/c270-c75-capture-build.json"
HIST_SHA = "b51d0ea00f849872930162d69d298a666f0222e58af9605814f4305ecb909659"
CAPTURE_SHA = "295e710af6efbd59944ae999911aeb94f0a7aef633895f1f3404161e56bdb0e6"
DIRECT_SHA = "cb386577d0b424d531a484d81619e29887b2419dd03c05578004b0878f601af6"
E20_SHA = "aa62ae8d848bfef8b9f90a6fb97ae455d15273293c752d2ec2da8708521555a0"
E20_RAW = "1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6"
CXX = Path("/usr/bin/g++-15")
CXX_SHA = "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a"
READELF = "/usr/bin/readelf"
ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"}
REQUIRED_HEADERS = {
    "src/llama-moe-stream.h",
    "src/llama-model.h",
    "include/llama.h",
    "ggml/include/ggml.h",
    "ggml/include/ggml-backend.h",
    "ggml/include/gguf.h",
}


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def sealed(path, sha):
    need(digest(path) == sha, "origin: " + path.name)
    return json.loads(path.read_bytes())


def cmd(args, env=None):
    return subprocess.check_output(args, env=ENV if env is None else env, timeout=45, text=True)


def git(folder, *args):
    return cmd(
        ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1", "-C", folder, *args]
    ).strip()


def dynamic(text, phdr):
    needed = re.findall(r"\(NEEDED\).*?\[(.*?)\]", text)
    search = re.findall(r"\((RUNPATH|RPATH)\).*?\[(.*?)\]", text)
    interp = re.findall(r"\[Requesting program interpreter: (.*?)\]", phdr)
    need(
        needed and len(set(needed)) == len(needed) and len(search) == len(interp) == 1,
        "ambiguous ELF link metadata",
    )
    return {"needed": needed, "search": list(search[0]), "interpreter": interp[0]}


def metadata(exe):
    return dynamic(cmd([READELF, "-dW", exe]), cmd([READELF, "-lW", exe]))


def matched_closure(links, expected, objects, files):
    need(links.keys() == expected.keys() == objects.keys(), "startup object set")
    for name, path in links.items():
        target = files.require(path, objects[name]["sha256"])
        need(
            str(target) == expected[name][1] and target.name == objects[name]["file"],
            "foreign provider: " + name,
        )


def headers(dep, backend, native, capture, direct):
    # -MMD excludes system headers, including the compiler's standard library.
    paths = shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1])
    wanted = {
        native.resolve(): "native.cpp",
        capture.resolve(): "C236/capture.cpp",
        direct.resolve(): "C210/c210_direct_reader.h",
    }
    tree = {}
    for line in git(backend, "ls-tree", "-r", WORKER).splitlines():
        meta, name = line.split("\t", 1)
        tree[name] = meta.split()[2]
    result = {}
    for item in paths:
        path = Path(item).resolve(strict=True)
        if path in wanted:
            key = wanted[path]
        else:
            name = path.relative_to(backend).as_posix()
            data = path.read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            need(tree.get(name) == blob, "uncommitted project header: " + name)
            key = "C269/" + name
        result[key] = digest(path)
    need(
        set(wanted.values()) <= result.keys()
        and {"C269/" + name for name in REQUIRED_HEADERS} <= result.keys(),
        "missing project header",
    )
    return result


def run(backend, preflight, out, record):
    backend = backend.resolve(strict=True)
    for folder in (REPO, backend):
        need(not git(folder, "status", "--porcelain"), "dirty checkout")
    need(git(backend, "rev-parse", "HEAD") == WORKER, "backend commit")
    record.update(
        commit=git(REPO, "rev-parse", "HEAD"),
        tree=git(REPO, "rev-parse", "HEAD^{tree}"),
        worker_commit=WORKER,
        worker_tree=git(backend, "rev-parse", "HEAD^{tree}"),
    )
    native = HERE / "native.cpp"
    need(git(REPO, "ls-files", "--error-unmatch", str(native)), "untracked native source")
    e20 = sealed(QUAL / "qualified_profile/evidence/receipt.json", E20_SHA)
    need(e20["receipt_sha256"] == E20_RAW, "C270 E20 identity")
    pre_sha = e20["loader"]["preflight_sha256"]
    pre = sealed(preflight / "receipt.json", pre_sha)
    map_sha = pre["static_map_sha256"]
    need(
        pre["status"] == "PASS_STATIC_C270_C281_DRIVER_SELECTION"
        and map_sha == e20["loader"]["static_map_sha256"],
        "C270 startup authority",
    )
    arm = sealed(preflight / "static-map.json", map_sha)["arms"]["C270"]
    search = arm["native_search"]
    parent = Path(arm["executable"])
    old = sealed(HIST, HIST_SHA)["argv"]
    capture = next(Path(i) for i in old if i.endswith("/capture.cpp"))
    direct = capture.parents[3] / "tools/c210_direct_reader.h"
    need(
        Path(old[-1]).samefile(parent)
        and Path(old[old.index("-L") + 1]).samefile(backend / "build-c269-cuda/bin"),
        "C270 command",
    )
    need(
        digest(capture) == CAPTURE_SHA
        and digest(direct) == DIRECT_SHA
        and digest(parent) == arm["executable_sha256"] == e20["capture_sha256"],
        "capture authority",
    )
    need(digest(CXX) == CXX_SHA, "compiler selection")
    module = QUAL / "driver_pair/server_startup/screen.py"
    need(digest(module) == pre["source_sha256"], "static loader helper")
    spec = importlib.util.spec_from_file_location("b3_static", module)
    static = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(static)
    objects = pre["arms"]["C270"]["objects"]
    env = static.environment(search)
    files = static.Files()
    files.require(static.LOADER, objects[static.LOADER.name]["sha256"])

    def verify_closure(exe):
        links = static.interpret(cmd([static.LOADER, "--list", exe], env))
        matched_closure(links, arm["links"], objects, files)

    verify_closure(parent)
    reference = metadata(parent)
    dep = out / "headers.d"
    exe = out / "b3-numeric"
    args = old.copy()
    args[0] = str(CXX)
    args[args.index(str(capture))] = str(native)
    args[-1] = str(exe)
    args[1:1] = [f'-DTESY_B3_PARENT_CAPTURE="{capture}"', "-MMD", "-MF", str(dep)]
    (out / "command.json").write_text(json.dumps(args) + "\n")
    record.update(
        static_preflight_sha256=pre_sha,
        static_map_sha256=map_sha,
        c270_e20_receipt_sha256=E20_RAW,
        historical_command_sha256=HIST_SHA,
        parent_capture_source_sha256=CAPTURE_SHA,
        direct_reader_sha256=DIRECT_SHA,
        native_source_sha256=digest(native),
        original_binary_sha256=digest(parent),
        command_sha256=digest(out / "command.json"),
        executable=exe.name,
        protocol_sha256=digest(HERE / "protocol.md"),
        compiler_sha256=CXX_SHA,
        compiler_version=cmd([CXX, "-dumpfullversion"]).strip(),
        cc1plus_sha256=digest(cmd([CXX, "-print-prog-name=cc1plus"]).strip()),
        readelf_sha256=digest(READELF),
        stage="compile",
    )
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(args, env=ENV, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    record.update(
        stage="validate",
        compiler_log_sha256=digest(out / "compiler.log"),
        binary_sha256=digest(exe),
        binary_bytes=exe.stat().st_size,
    )
    record["headers_sha256"] = headers(dep, backend, native, capture, direct)
    need(metadata(exe) == reference, "changed DT_NEEDED, search path or interpreter")
    verify_closure(exe)
    record.update(
        startup_objects=objects,
        dt_needed=reference["needed"],
        interpreter=Path(reference["interpreter"]).name,
        search_tag=reference["search"][0],
        search_sha256=hashlib.sha256(reference["search"][1].encode()).hexdigest(),
        stage="self-test",
    )
    with (out / "self-test.stderr").open("xb") as err:
        res = subprocess.run(
            [exe, "--self-test"],
            env=dict(env, CUDA_VISIBLE_DEVICES=""),
            capture_output=False,
            stdout=subprocess.PIPE,
            stderr=err,
            timeout=20,
        )
    (out / "self-test.stdout").write_bytes(res.stdout)
    need(res.returncode == 0 and res.stdout == b"PASS_B3_NUMERIC_ROW_PLAN\n", "native self-test")
    record.update(
        stage="done",
        status="PASS_C269_B3_NUMERIC_BUILD",
        self_test=res.stdout.decode().strip(),
        self_test_stderr_sha256=digest(err.name),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "preflight-dir", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.new_output_dir.absolute()
    out.mkdir(mode=0o700)
    before = time.monotonic()
    record = dict(status="FAIL_PRESERVED", stage="authenticate", model_forwards=0)
    try:
        run(args.backend, args.preflight_dir, out, record)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        record["error_type"] = type(exc).__name__
        (out / "error.txt").write_text(str(exc) + "\n")
    record.update(
        elapsed_s=round(time.monotonic() - before, 6),
        max_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )
    tmp = out / "receipt.json.tmp"
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, out / "receipt.json")
    print(record["status"], record["stage"])
    return int(record["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

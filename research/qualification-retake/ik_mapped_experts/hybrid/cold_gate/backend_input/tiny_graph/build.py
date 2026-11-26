"""Build a second tiny client against the frozen ik headers and the original SM89 DSOs."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[2] / "client"
ORIGINAL = "5761ef3190ac8d46e26861292c5c2c1a8fb597cfbaaa5ca54849a608ee27e728"
IK = "7a5d90009b7ae55d3239cdd33244977c4eb10ff6"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def git(path, *args):
    return subprocess.check_output(["git", "-C", path, *args], text=True).strip()


def render(src):
    changes = [
        ('extern "C" void ggml_backend_tensor_set(', '#include "graph_input.hpp"\n\n'),
        (
            "    real(b,t,src,off,n);",
            "    if (graph_input::active &&\n"
            "        graph_input::active->send(b,t,src,off,n,real)) return;\n",
        ),
        ('        std::printf("ORIG ', "        graph_input::active->add(i,role,kind,w);\n"),
        ("    handoff(cpu,'E');", "    graph_input::Session session(argv[2], argv[1]);\n"),
        ("    llama_free(ctx);", "    session.finish();\n"),
    ]
    for anchor, before in changes:
        need(src.count(anchor) == 1, "client insertion: " + anchor)
        src = src.replace(anchor, before + anchor)
    anchor = "auto mode=std::string(argv[1]);"
    need(src.count(anchor) == 1, "client mode")
    return src.replace(anchor, 'auto mode=std::string("BANK9");')


def build(a, out, r):
    need(
        git(HERE, "rev-parse", "HEAD") == a.commit and not git(HERE, "status", "--porcelain"),
        "dirty or changed experiment",
    )
    need(
        git(a.source, "rev-parse", "HEAD") == IK and not git(a.source, "status", "--porcelain"),
        "ik pin",
    )
    authority = a.client / "receipt.json"
    need(sha(authority) == ORIGINAL, "original client build")
    old = json.loads(authority.read_bytes())
    for name, digest in old["sources"].items():
        base = CLIENT.parents[1] if "/" in name else CLIENT
        need(sha(base / name) == digest, "client source " + name)
    src = out / "client.cpp"
    src.write_text(render((CLIENT / src.name).read_text()))
    compiler = Path("/usr/bin/g++-15")
    cuda = Path("/usr/local/cuda-13.3")
    obj = a.objects.resolve(strict=True)
    need(
        sha(compiler) == old["compiler_sha256"]
        and sha(cuda / "include/cuda_runtime_api.h") == old["runtime_header_sha256"],
        "toolchain",
    )
    for name, digest in old["libraries"].items():
        need(sha(obj / name) == digest, "ik DSO " + name)
    exe = out / "bank-graph"
    cmd = [
        str(compiler),
        "-std=c++17",
        "-O1",
        "-pthread",
        "-rdynamic",
        "-fPIC",
        "-pie",
        "-fno-plt",
        *(f"-I{a.source / p}" for p in ("include", "ggml/include", "ggml/src")),
        f"-I{cuda / 'include'}",
        f"-I{CLIENT}",
        f"-I{HERE}",
        str(src),
        str(CLIENT / "copy.cpp"),
        str(obj / "src/libllama.so"),
        str(obj / "ggml/src/libggml.so"),
        "-ldl",
        "-o",
        str(exe),
        *("-Wl,-rpath-link," + str(p) for p in (obj / "ggml/src", "/usr/lib64", cuda / "lib64")),
    ]
    r.update(
        commit=a.commit,
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        ik=IK,
        sources={
            p.name: sha(p)
            for p in (
                HERE / "build.py",
                HERE / "graph_input.hpp",
                HERE.parent / "bank_input.hpp",
                src,
            )
        },
        original_build=ORIGINAL,
        compiler_sha256=old["compiler_sha256"],
        argv=cmd,
    )
    with (out / "compiler.log").open("xb") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=45)
    r.update(status="PASS_GRAPH_CLIENT_BUILD", binary_sha256=sha(exe))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "objects", "client", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    dest = args.new_output_dir.resolve()
    dest.mkdir(mode=0o700)
    receipt = {"status": "FAIL_PRESERVED", "model_starts": 0}
    try:
        build(args, dest, receipt)
    except Exception as exc:
        receipt["reason"] = f"{type(exc).__name__}: {exc}"
    (dest / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(receipt["status"], receipt.get("reason", ""))
    raise SystemExit(receipt["status"] == "FAIL_PRESERVED")

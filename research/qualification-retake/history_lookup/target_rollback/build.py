"""Build a callback-free consumer of the real 189-position target KV snapshot."""

import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
TARGET = HERE.parent / "b3_numeric/first_boundary/router_row/integrated/input_l25/ffn_cuda/target"
T = run_path(str(TARGET / "family.py"))
K, F, P, R, need, read, save, sha = (
    T[k] for k in ("K", "F", "P", "R", "need", "read", "save", "sha")
)
METHOD = "76d709eef5f1ca9b5a00e94c909459a073120703e2399580f5ac95641f59207e"
PARENT = "a233656bdb9a74a2494bc669ec0b8138c2e780ce6580eefbf45d960c1863c888"
RECIPE = "2e9e106e3518d3d9629259e76e6fc9d12e495c8edd05686a6648b16820acfb7f"


def section(text, start, end):
    need(text.count(start) == text.count(end) == 1, "unique source anchors")
    return text[text.index(start) : text.index(end)]


def source():
    text = F["M"]["observer"]().decode()
    helpers = section(text, "bool same_file(", "void prefix_agreement(") + section(
        text, "bool finite_row(", "std::vector<int> batch_rows("
    )
    ctx = section(text, "    llama_backend_init();", "    cp.cb_eval=Observer::callback;")
    code = (HERE / "rollback.cpp.in").read_text()
    need(code.count("@SERIALIZED_HELPERS@") == code.count("@MODEL_CONTEXT@") == 1, "template")
    return code.replace("@SERIALIZED_HELPERS@", helpers).replace("@MODEL_CONTEXT@", ctx)


def build(a, out):
    git = P["prepare"].git
    need(
        git(HERE, "rev-parse", "HEAD") == a.commit
        and not git(HERE, "status", "--porcelain")
        and sha(HERE / "protocol.md") == METHOD
        and sha(a.target / "receipt.json") == T["BUILD"]
        and sha(a.observer / "receipt.json") == K["PREVIOUS"],
        "method and libraries",
    )
    b = read(a.target / "receipt.json")
    prior = read(a.observer / "receipt.json")
    need(
        sha(a.observer / "client-compile.json") == RECIPE
        and (a.observer / "boundary.cpp").read_bytes() == F["M"]["observer"]()
        and sha(a.observer / "b3-numeric") == prior["elf_sha256"] == b["elf_sha256"]
        and sha(a.target / "libllama.so.0.0.9884") == b["image_sha256"],
        "qualified capture and target",
    )
    src = out / "rollback.cpp"
    src.write_text(source())
    exe = out / "b3-numeric"
    cmd = read(a.observer / "client-compile.json")
    for before, after in (
        ("boundary.cpp", src),
        ("headers.d", out / "headers.d"),
        ("b3-numeric", exe),
    ):
        name = str(a.observer / before)
        need(cmd.count(name) == 1, "compiler argv " + name)
        cmd[cmd.index(name)] = str(after)
    need(sha(Path(cmd[0])) == b["compiler_sha256"], "compiler")
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TMPDIR": str(out)}
    K["OLD"]["native"](cmd, out, env, out / "compile.log", 100)
    lib = out / "libllama.so.0.0.9884"
    shutil.copy2(a.target / lib.name, lib)
    need(sha(lib) == b["image_sha256"], "unaltered target library")
    (out / "libllama.so.0").symlink_to(lib.name)
    auth = K["OLD"]["Authority"](a.static, out, sha(exe), sha(lib))
    env = F["SC"]["OLD"]["environment"](auth.search.split(os.pathsep))
    ldd = subprocess.check_output(["/usr/bin/ldd", "-r", exe], env=env, text=True, timeout=20)
    (out / "ldd.txt").write_text(ldd)
    need(
        "not found" not in ldd
        and "undefined symbol" not in ldd
        and {k: str(v.resolve()) for k, v in F["SC"]["OLD"]["interpret"](ldd).items()}
        == {k: v["file"] for k, v in auth.verified["closure"].items()},
        "native providers",
    )
    test = subprocess.run(
        [exe, "--self-test"],
        env=env | {"CUDA_VISIBLE_DEVICES": ""},
        capture_output=True,
        check=True,
        timeout=20,
    )
    (out / "self-test.log").write_bytes(test.stdout + test.stderr)
    need(test.stdout == b"PASS_ROLLBACK_ROW_PLAN\n", "fault test")
    deps = (out / "headers.d").read_text().replace(chr(92) + "\n", " ").split(":", 1)[1].split()
    return dict(
        status="GO_ROLLBACK_AR_CONTROL",
        commit=a.commit,
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        protocol_sha256=METHOD,
        qualified_build_sha256=T["BUILD"],
        elf_sha256=sha(exe),
        image_sha256=sha(lib),
        source_sha256=sha(src),
        current_providers=auth.verified["closure"],
        headers_sha256={str(Path(k).resolve()): sha(Path(k)) for k in deps},
        compiler_sha256=b["compiler_sha256"],
        model_starts=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("target", "observer", "static", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    try:
        r = build(a, out)
        need(
            time.monotonic() - start < 180
            and sum(p.stat().st_size for p in out.iterdir() if p.is_file()) < 32 << 20,
            "build envelope",
        )
    except Exception as e:
        r = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}", model_starts=0)
    r["wall_s"] = time.monotonic() - start
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")

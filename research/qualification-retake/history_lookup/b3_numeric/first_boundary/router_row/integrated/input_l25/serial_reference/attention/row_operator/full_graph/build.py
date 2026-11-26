"""Build the attention ablation from the authenticated C269 router and link inputs."""

import argparse
import hashlib
import os
import shlex
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
M = run_path(str(HERE / "materialize.py"))
P, B, S, Q, need, read, sha, save = (
    M[k] for k in ("P", "B", "S", "QUAL", "need", "read", "sha", "save")
)
N = P["N"]


class Authority(N["Current"]):
    def __init__(self, static, out, elf, graph_sha):
        super().__init__(static, capture=(out / "b3-numeric", elf))
        self.search = os.pathsep.join((str(out), self.search))
        name = P["SC"]["SONAME"]
        library = out / "libllama.so.0.0.9884"
        need(
            sha(library) == graph_sha and (out / name).resolve(strict=True) == library, "graph file"
        )
        prev = self.verified["closure"][name]["file"]
        for tbl in (self.files, self.stats, self.keys):
            del tbl[prev]
        self.files[str(library)] = graph_sha
        self.stats[str(library)] = N["AU"]["identity"](library)
        self.keys[str(library)] = N["AU"]["reference_key"](str(library), self.stats[str(library)])
        self.allowed = set(self.files)
        self.initial = (self.initial - {prev}) | {str(library)}
        self.verified = self.verified | dict(
            closure=self.verified["closure"] | {name: dict(file=str(library), sha256=graph_sha)}
        )


def native(cmd, work, env, log, timeout):
    save(log.with_suffix(".json"), cmd)
    with log.open("xb") as f:
        subprocess.run(
            cmd, cwd=work, env=env, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=timeout
        )


def build(a, out):
    need(
        sha(HERE / "protocol.md") == M["METHOD"]
        and sha(a.parent / "receipt.json") == P["BUILD"]
        and P["prepare"].git(HERE, "rev-parse", "HEAD") == a.commit
        and not P["prepare"].git(HERE, "status", "--porcelain"),
        "study and build authority",
    )
    pfj = S["G"]["probes"].load(Q / "phase_fd/integrated/build.py", "layer25_link")
    stock = S["G"]["probes"].load(Q / "stock_prefault_build/build.py", "layer25_abi")
    backend = a.backend.resolve(strict=True)
    directory = backend / "build-c269-cuda"
    original = backend / "src/llama-graph.cpp"
    need(
        sha(original) == M["S"]["G"]["probes"].old.GRAPH
        and pfj.git(backend, "rev-parse", "HEAD") == pfj.WORKER
        and not pfj.git(backend, "status", "--porcelain")
        and all(
            sha(directory / k) == v
            for k, v in (
                ("compile_commands.json", pfj.DB),
                ("build.ninja", pfj.NINJA),
                ("CMakeFiles/rules.ninja", pfj.RULES),
            )
        )
        and sha(Path(pfj.CXX)) == stock.GCC,
        "pinned backend and flags",
    )
    parent = read(a.parent / "receipt.json")
    need(
        sha(a.parent / "b3-numeric") == parent["elf_sha256"]
        and sha(a.parent / "libllama.so.0.0.9884") == parent["graph_sha256"] == B["IMAGE"]
        and sha(a.parent / "boundary.cpp") == parent["source_sha256"]
        and (a.parent / "boundary.cpp").read_bytes() == B["render"](),
        "parent pair",
    )
    source = original.read_text()
    need(
        hashlib.sha256(S["G"]["probes"].old.graph(source).encode()).hexdigest() == M["PRIOR_SHA"],
        "parent router graph TU",
    )
    graph = out / "llama-graph.cpp"
    graph.write_text(M["graph"](source))
    tokens = shlex.split(
        pfj.cmd("ninja", "-C", directory, "-t", "commands", "bin/" + pfj.IMAGE).splitlines()[-1]
    )
    ins = {
        i: sha(directory / i)
        for i in tokens
        if i.endswith(".o") or (not i.startswith("-") and ".so" in i and i != "bin/" + pfj.IMAGE)
    }
    need(
        len(ins) == 171 and pfj.stamp(ins) == pfj.INPUTS and pfj.stamp(tokens) == pfj.LINK,
        "original 166 objects and five DSOs",
    )
    obj = pfj.obj("src/llama-graph.cpp")
    (cfg,) = [
        x
        for x in read(directory / "compile_commands.json")
        if Path(x["file"]).resolve() == original
    ]
    cc = shlex.split(cfg["command"])
    need(
        cc[0] == pfj.CXX
        and cc[-4:] == ["-o", obj, "-c", cfg["file"]]
        and Path(cfg["directory"]).resolve() == directory,
        "graph recipe",
    )
    cc[-3] = str(out / Path(obj).name)
    cc[-1] = str(graph)
    cc.insert(1, f"-fmacro-prefix-map={out}={Path(cfg['file']).parent}")
    env = pfj.ENV | {"TMPDIR": str(out)}
    native(cc, directory, env, out / "graph-compile.log", 150)
    pfj.SOURCES = {"src/llama-graph.cpp": sha(original)}
    ld = pfj.link_args(tokens, out)
    native(ld, directory, env, out / "graph-link.log", 60)
    image = out / pfj.IMAGE
    need(
        stock.abi(image)["dynamic"] == stock.abi(a.parent / pfj.IMAGE)["dynamic"]
        and sha(image) != B["IMAGE"]
        and all(sha(directory / k) == v for k, v in ins.items()),
        "ABI and preserved original objects",
    )
    (out / pfj.SONAME).symlink_to(image.name)
    client = read(a.parent / "command.json")
    src = out / "boundary.cpp"
    src.write_bytes(M["observer"]())
    for filename in ("boundary.cpp", "headers.d", "b3-numeric"):
        before = str(a.parent / filename)
        need(client.count(before) == 1, "client compile command path")
        client[client.index(before)] = str(out / filename)
    native(client, directory, env, out / "client-compile.log", 50)
    hdr = (out / "headers.d").read_text().replace("\\\n", " ").split(":", 1)[1].split()
    prior = (a.parent / "headers.d").read_text().replace("\\\n", " ").split(":", 1)[1].split()
    need(
        {Path(v).resolve() for v in hdr} - {src}
        == {Path(v).resolve() for v in prior} - {a.parent / "boundary.cpp"},
        "observer headers",
    )
    exe = out / "b3-numeric"
    auth = Authority(a.static, out, sha(exe), sha(image))
    env = P["SC"]["OLD"]["environment"](auth.search.split(os.pathsep))
    commands = {
        "list": [P["SC"]["OLD"]["LOADER"], "--list", exe],
        "relocate": ["/usr/bin/ldd", "-r", exe],
    }
    for label, cmd in commands.items():
        answer = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=15, check=True
        )
        text = answer.stdout + answer.stderr
        (out / (label + ".txt")).write_text(text)
        need(
            "undefined symbol" not in text
            and "not found" not in text
            and {k: str(v.resolve()) for k, v in P["SC"]["OLD"]["interpret"](text).items()}
            == {k: v["file"] for k, v in auth.verified["closure"].items()},
            "current providers",
        )
    for val in ("0", "1"):
        child = subprocess.run(
            [exe, "--self-test"],
            env=env | {"CUDA_VISIBLE_DEVICES": "", B["ON"]: "1", M["OPTION"]: val},
            capture_output=True,
            timeout=15,
        )
        (out / ("self-" + val + ".log")).write_bytes(child.stdout + child.stderr)
        need(
            child.returncode == 0 and child.stdout == b"PASS_B3_NUMERIC_ROW_PLAN\n",
            "no-model observer " + val,
        )
    return dict(
        status="GO_INTEGRATED_ATTENTION_PAIR",
        commit=a.commit,
        tree=pfj.git(HERE, "rev-parse", "HEAD^{tree}"),
        protocol_sha256=M["METHOD"],
        parent_build_sha256=P["BUILD"],
        prior_graph_tu_sha256=M["PRIOR_SHA"],
        link_inputs_sha256=pfj.INPUTS,
        reused_objects=165,
        graph_source_sha256=sha(graph),
        client_source_sha256=sha(src),
        image_sha256=sha(image),
        elf_sha256=sha(exe),
        current_providers=auth.verified["closure"],
        compiler_sha256=stock.GCC,
        model_starts=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("backend", "static", "parent", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--commit", required=True)
    args = p.parse_args()
    out = args.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    try:
        result = build(args, out)
        need(
            time.monotonic() - start <= 300
            and sum(p.stat().st_size for p in out.iterdir() if p.is_file()) < 150 << 20,
            "build envelope",
        )
    except Exception as exc:
        result = dict(
            status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}", model_starts=0
        )
    result["wall_s"] = time.monotonic() - start
    save(out / "receipt.json", result)
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")

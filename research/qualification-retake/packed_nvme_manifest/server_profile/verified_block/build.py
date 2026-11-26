"""Rebuild the C291 graph in isolation and authenticate the client and server loaders."""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[2]
REPO = QUAL.parents[1]
SC = run_path(str(HERE.parent / "system_driver/screen.py"))
START = SC["OLD"]
ABI = run_path(str(QUAL / "stock_prefault_build/build.py"))["abi"]
need, sha = SC["need"], SC["sha"]
METHOD = "68d736efc8a2c630e638b92a7d0bd839e967587477c60b3608dbdb8fff51462a"
STATIC = "0c50a2657aa1dd5ba53a862e0e3e5cf4c2e366eb4663109ce2f2c03c2557df3b"
BUILD = "9b9625d808b09e017d99f69907db2cfb4f6a0603b3ba950c1fab32d5418aede6"
NUMERIC = "9f384fe141eac5b8aa28128d778565870884f4f18c5105b4f7761c62548a3d86"
PACK = "04af70ea943b816769e2c6d62873ded11f00603df6c3be42340b3785aa880819"
DRIVER = "ca48a2d27d0796399adc3387225eec4be62974e26fa299710edfde0c1af5aa63"
OBJECTS = "d982f488d9ec01b78d28217c1a14ef0cca47ca1cbe7149e3ac6f39e2c4ded162"
RECIPES = {
    "flags.make": "5c1b8d87242694e5514a668cebee7ff0d3f11fe5cdc083bfbd8be62b87fca00b",
    "link.txt": "1dd184076de82564f8dd3d5a0d31e4d5acc6a46fe3b9420db8e02c4ce6401f1a",
    "build.make": "eaefa2fc7fa0422a7621925403945ee34c2a79b7bccd1b6ce556594ed0835c37",
}
CONTROL_GRAPH = "d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288"
BLOCK_GRAPH = "13bf19e28515b81100fe95ef6e66e2975cdd79cf0431fee4bc874008b65b469b"
SERVER_CONTEXT = "657c331a707f0faf74615d19387088070c3dbd7559328619c9ef606a4ec8cc55"
SERVER_SOURCES = {
    "tools/server/server-context.cpp": SERVER_CONTEXT,
    "common/speculative.cpp": "5cfdcda8d617c9b527b343338360db58432539e6adae55a389fbd8b2caeec0ac",
    "src/llama-context.cpp": "7d8cfa9f33f38d761cf18b8e548ab7811866fbb8fdfaa95eeb2211d56851681b",
}
IMAGE = "libllama.so.0.0.9884"
SLOT = "CMakeFiles/llama.dir/llama-graph.cpp.o"


def save(p, obj):
    with p.open("x") as file:
        json.dump(obj, file, sort_keys=True, indent=2, allow_nan=False)
        file.write("\n")


def read(path, expected):
    need(sha(path) == expected, "changed " + path.name)
    return json.loads(path.read_bytes())


def digest(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def tree(path):
    def git(*args):
        return subprocess.check_output(["git", "-C", path, *args], text=True).strip()

    need(not git("status", "--porcelain"), "dirty input")
    return git("rev-parse", "HEAD", "HEAD^{tree}").splitlines()


def command(cmd, cwd, folder, tag, env):
    cmd = list(map(str, cmd))
    save(folder / (tag + "-argv.json"), cmd)
    with (folder / (tag + ".log")).open("xb") as log:
        subprocess.run(
            cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120
        )


def headers(path, cwd):
    items = shlex.split(path.read_text().replace(chr(92) + "\n", " ").split(":", 1)[1])
    return {str((cwd / x).resolve(strict=True)): sha((cwd / x).resolve(strict=True)) for x in items}


def toolchain(env):
    programs = {}
    for name in ("cc1plus", "as", "collect2", "ld"):
        raw = subprocess.check_output(
            ["/usr/bin/c++", "-print-prog-name=" + name], env=env, text=True
        ).strip()
        binary = Path(shutil.which(raw, path=env["PATH"])).resolve(strict=True)
        programs[name] = {"file": str(binary), "sha256": sha(binary)}
    return programs


def compile_graph(out, flags, source, src_root, work, env):
    # Preserve __FILE__ paths in diagnostics in the two compilations.
    prefix = ["/usr/bin/c++", *flags, "-fmacro-prefix-map=" + str(out) + "=" + str(src_root)]
    cmd = prefix + ["-M", "-MT", "graph", "-MF", out / "before.d", source]
    command(cmd, work, out, "dependencies", env)
    before = headers(out / "before.d", work)
    obj = out / "llama-graph.cpp.o"
    cmd = prefix + ["-MD", "-MT", "graph", "-MF", out / "actual.d", "-o", obj, "-c", source]
    command(cmd, work, out, "compile", env)
    need(before == headers(out / "actual.d", work), "compiler dependency drift")
    need(str((src_root / "llama-moe-stream.h").resolve()) in before, "C291 manager layout")
    save(out / "headers.json", before)
    return obj


def loader(arm, image, out, key, env):
    binary = Path(arm["binary"])
    need(sha(binary) == arm["binary_sha256"], "frozen client/server")
    search = os.pathsep.join([str(out), *arm["search"]])
    cmd = ["/usr/bin/ldd", "-r", binary]
    command(cmd, out, out, key, env | {"LD_LIBRARY_PATH": search})
    data = (out / (key + ".log")).read_text()
    need("not found" not in data and "undefined symbol" not in data, "failed relocations")
    actual = {k: v.resolve(strict=True) for k, v in START["interpret"](data).items()}
    expected = {k: Path(v["file"]).resolve(strict=True) for k, v in arm["closure"].items()}
    expected["libllama.so.0"] = image
    need(actual == expected, "different loaded provider")
    for k, path in actual.items():
        if k != "libllama.so.0":
            need(sha(path) == arm["closure"][k]["sha256"], "changed provider " + k)
    return {"binary_sha256": sha(binary), "providers": len(actual), "image_sha256": sha(image)}


def build(a, out, r):
    root = tree(REPO)
    need(root[0] == a.commit and sha(HERE / "protocol.md") == METHOD, "scientific protocol")
    cg = Path("/sys/fs/cgroup") / Path(
        next(
            s[3:] for s in Path("/proc/self/cgroup").read_text().splitlines() if s.startswith("0::")
        )
    ).relative_to("/")
    need(
        cg.name.startswith("tesy-pack-block-")
        and (cg / "memory.max").read_text().strip() == str(4 << 30)
        and (cg / "memory.swap.max").read_text().strip() == "0",
        "build scope",
    )
    pack = tree(a.pack_source)
    base = tree(a.base_source)
    need(
        pack
        == ["c89c88b342054223e3f27a17fbfd0954803147ac", "3962daa588dfa89971c60c95ce4c5054bc27fd3f"]
        and base
        == ["d0ebfbcc6c8f456bc1083027c1b08075a32824d8", "49812e6f011a8cf0fc14a71074e5f4b120f87216"],
        "source lineage",
    )
    static = read(a.static / "receipt.json", STATIC)
    prev = read(a.block / "receipt.json", BUILD)
    prior = read(a.numeric / "receipt.json", NUMERIC)
    src = a.pack_source / "src" / "llama-graph.cpp"
    graph = a.block / "llama-graph.cpp"
    need(
        sha(src) == sha(a.base_source / "src" / src.name) == CONTROL_GRAPH
        and sha(graph) == prev["graph_source_sha256"] == BLOCK_GRAPH
        and prior["status"] == "GO_GREEDY_ROLLBACK_AND_CONTINUATION"
        and sha(a.block / IMAGE) == prev["image_sha256"]
        and static["status"] == "GO_CURRENT_NUMERICAL_GATE",
        "qualified inputs",
    )
    binary = Path(static["arms"]["C281_PACK"]["closure"]["libllama.so.0"]["file"])
    need(
        sha(binary) == PACK and sha(Path("/usr/bin/c++")) == DRIVER, "historical image and compiler"
    )
    work = binary.parents[1] / "llama"
    recipes = work / "CMakeFiles/llama.dir"
    need({k: sha(recipes / k) for k in RECIPES} == RECIPES, "original CMake recipe")
    link = shlex.split((recipes / "link.txt").read_text())
    objects = [s for s in link if s.endswith(".o")]

    def inventory():
        return {s: sha(work / s) for s in objects}

    inv = inventory()
    need(
        len(inv) == len(objects) == 166 and digest(inv) == OBJECTS and objects.count(SLOT) == 1,
        "ordered C291 objects",
    )
    save(out / "objects.json", inv)
    includes = {}
    for line in (recipes / "flags.make").read_text().splitlines():
        if line.startswith("CXX_"):
            key, val = line.split(" = ", 1)
            includes[key] = shlex.split(val)
    flags = includes["CXX_DEFINES"] + includes["CXX_INCLUDES"] + includes["CXX_FLAGS"]
    need(
        includes["CXX_FLAGS"] == ["-O3", "-DNDEBUG", "-std=gnu++17", "-fPIC"]
        and link[:1] == ["/usr/bin/c++"],
        "C291 flags",
    )
    link_inputs = {str(Path(s).resolve()): sha(Path(s)) for s in link if s.endswith(".so")}
    need(
        len(link_inputs) == 2
        and all(
            v in {x["sha256"] for x in static["arms"]["C281_PACK"]["closure"].values()}
            for v in link_inputs.values()
        ),
        "ggml link inputs",
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "TMPDIR": str(out),
        "CUDA_VISIBLE_DEVICES": "",
    }
    refabi = ABI(binary)
    need(
        all(
            sha(source / key) == val
            for source in (a.base_source, a.pack_source)
            for key, val in SERVER_SOURCES.items()
        ),
        "server reservation/rollback code",
    )
    r.update(
        commit=a.commit,
        tree=root[1],
        pack_source=pack,
        base_source=base,
        protocol_sha256=METHOD,
        historical_image_sha256=PACK,
        previous_build_sha256=BUILD,
        numerical_family_sha256=NUMERIC,
        static_sha256=STATIC,
        object_inventory_sha256=OBJECTS,
        compiler_sha256=DRIVER,
        compiler_tools=toolchain(env),
        server_sources=SERVER_SOURCES,
        link_inputs=link_inputs,
        original_abi=refabi,
        arms={},
    )
    for name in ("RELINK", "RECOMPILE", "BLOCK"):
        r["stage"] = name
        dest = out / name
        dest.mkdir()
        cmd = list(link)
        if name != "RELINK":
            local = dest / src.name
            local.write_bytes((graph if name == "BLOCK" else src).read_bytes())
            # Match the original compiler's spelling of the source path recorded in build.make.
            source_line = next(
                x
                for x in (recipes / "build.make").read_text().splitlines()
                if "-c " in x and "/llama-graph.cpp" in x
            )
            original = Path(shlex.split(source_line)[-1])
            need(original.samefile(src), "historical source spelling")
            obj = compile_graph(dest, flags, local, original.parent, work, env)
            cmd[cmd.index(SLOT)] = str(obj)
        image = dest / IMAGE
        cmd[cmd.index("-o") + 1] = str(image)
        j = next(i for i, s in enumerate(cmd) if s.startswith("-Wl,--dependency-file="))
        cmd[j] = "-Wl,--dependency-file=" + str(dest / "link.d")
        command(cmd, work, dest, "link", env)
        (dest / "libllama.so.0").symlink_to(image.name)
        abi = ABI(image)
        record = {"image_sha256": sha(image), "abi": abi}
        if name != "RELINK":
            record["object_sha256"] = sha(obj)
        r["arms"][name] = record
        need(name != "RELINK" or record["image_sha256"] == PACK, "original link reproducibility")
        need(abi == refabi, "exported symbols or dynamic ABI")
        record["relocation"] = {
            k: loader(static["arms"][k], image, dest, k, env) for k in ("C270_PACK", "C281_PACK")
        }
    need(
        r["arms"]["RECOMPILE"]["image_sha256"] != r["arms"]["BLOCK"]["image_sha256"]
        and inventory() == inv
        and sha(src) == CONTROL_GRAPH
        and sha(binary) == PACK,
        "isolated delta",
    )
    r["status"] = "GO_STATIC_COMBINED_PACK_BLOCK"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("pack-source", "base-source", "static", "block", "numeric", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = dict(status="FAIL_PRESERVED", model_starts=0, server_starts=0)

    def expire(*_):
        raise TimeoutError("four minute build cap")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(240)
    start = time.monotonic()
    try:
        build(a, out, r)
        raw_bytes = sum(x.lstat().st_size for x in out.rglob("*") if x.is_file())
        need(raw_bytes < 64 << 20, "raw size")
        r["build_output_bytes"] = raw_bytes
    except Exception as e:
        r["status"] = "FAIL_PRESERVED"
        r["error"] = f"{type(e).__name__}: {e}"
    finally:
        signal.alarm(0)
    r["wall_s"] = time.monotonic() - start
    r["files"] = {
        str(x.relative_to(out)): sha(x)
        for x in sorted(out.rglob("*"))
        if x.is_file() and not x.is_symlink()
    }
    save(out / "receipt.json", r)
    print(r["status"], r.get("stage", ""), r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")

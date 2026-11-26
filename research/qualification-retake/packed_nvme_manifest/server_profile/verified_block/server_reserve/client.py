"""Compile the live rollback witness against C291's private layout for server reserves 1 and 3."""

import argparse
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
GRAPH = run_path(str(HERE.parent / "build.py"))
QUAL, need, sha = (GRAPH[k] for k in ("QUAL", "need", "sha"))
RB = run_path(str(QUAL / "history_lookup/target_rollback/family.py"))
B, save = RB["B"], RB["save"]
METHOD = "03a39712f3bc971b439340707b9f55ca1ec236cf6c31806899975a08b8482f45"
COMBO = "55a0322b12a108fa1b15ab01ac8a7f4194934d32b659f2cd97f0c17ae20ed59b"
RECIPE = "40b9b4035338d6777d46a96fc69c80187010f2dd321a0dd7b7e8b00bd5d8e627"


def source():
    code = B["source"](live_rollback=True)
    insert = code.index("void execute(")
    code = code[:insert] + (HERE / "reserve.cpp.in").read_text() + "\n" + code[insert:]
    rule = B["section"](code, "    for (const auto &flag: {", "    llama_backend_init();")
    code = code.replace(rule, "    const int reserve = product_reserve();\n")
    for before, after in (
        ("    cp.n_ctx=8192;", "    cp.n_outputs_max=reserve;\n    cp.n_ctx=8192;"),
        (
            "    using Sampler=",
            "    const json entry_store=completed_store(model.get());\n    using Sampler=",
        ),
        (
            '    receipt["anchor"]=anchor;',
            """    receipt["output_reserve"]=reserve;
    receipt["store_entry"]=entry_store;
    receipt["store_end"]=completed_store(model.get());
    receipt["anchor"]=anchor;""",
        ),
    ):
        need(code.count(before) == 1, "unique anchor in qualified source")
        code = code.replace(before, after)
    return code


def build(a, out):
    commit, tree = GRAPH["tree"](GRAPH["REPO"])
    need(commit == a.commit and sha(HERE / "protocol.md") == METHOD, "study and clean tree")
    old = GRAPH["read"](a.previous / "receipt.json", RB["LIVE_ROLLBACK_BUILD"])
    choice = GRAPH["read"](a.libraries / "receipt.json", COMBO)
    need(
        choice["status"] == "GO_STATIC_COMBINED_PACK_BLOCK"
        and GRAPH["tree"](a.pack) == choice["pack_source"]
        and GRAPH["tree"](a.base) == choice["base_source"],
        "backend source roots",
    )
    need(
        sha(a.previous / "compile.json") == RECIPE
        and (a.previous / "rollback.cpp").read_text() == B["source"](live_rollback=True)
        and all(sha(Path(k)) == v for k, v in old["headers_sha256"].items()),
        "prior client",
    )
    cg = Path("/sys/fs/cgroup") / Path(
        Path("/proc/self/cgroup").read_text().strip()[3:]
    ).relative_to("/")
    need(
        cg.name.startswith("tesy-pack-reserve-client-")
        and (cg / "memory.max").read_text().strip() == str(3 << 30)
        and (cg / "memory.swap.max").read_text().strip() == "0",
        "build scope",
    )
    cmd = json.loads((a.previous / "compile.json").read_bytes())
    target = out / "reserve.cpp"
    target.write_text(source())
    exe = out / "b3-numeric"
    includes = 0
    for i, word in enumerate(cmd):
        if word in (
            str(a.previous / "rollback.cpp"),
            str(a.previous / "b3-numeric"),
            str(a.previous / "headers.d"),
        ):
            cmd[i] = str(target if word.endswith(".cpp") else out / Path(word).name)
        if i and cmd[i - 1] == "-I":
            path = Path(word).resolve(strict=True)
            if path.is_relative_to(a.base):
                cmd[i] = str(a.pack / path.relative_to(a.base))
                includes += 1
    need(includes == 4 and sha(Path(cmd[0])) == old["compiler_sha256"], "C291 headers and compiler")
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TMPDIR": str(out)}
    B["K"]["OLD"]["native"](cmd, out, env, out / "compile.log", 110)
    deps = shlex.split(
        (out / "headers.d").read_text().replace(chr(92) + "\n", " ").split(":", 1)[1]
    )
    hs = {str(Path(p).resolve(strict=True)): sha(Path(p)) for p in deps}
    need(
        str(a.pack / "src/llama-moe-stream.h") in hs
        and not any(Path(p).is_relative_to(a.base) for p in hs),
        "all private headers from C291",
    )
    static = GRAPH["read"](a.static / "receipt.json", GRAPH["STATIC"])["arms"]["C270_PACK"]
    results = {}
    for name in ("HIST", "RECOMPILE", "BLOCK"):
        dso = (
            Path(static["closure"]["libllama.so.0"]["file"])
            if name == "HIST"
            else a.libraries / name / GRAPH["IMAGE"]
        )
        expected = GRAPH["PACK"] if name == "HIST" else choice["arms"][name]["image_sha256"]
        need(sha(dso) == expected, "numerical DSO")
        search = os.pathsep.join([str(dso.parent), *static["search"]])
        local = env | {"LD_LIBRARY_PATH": search, "CUDA_VISIBLE_DEVICES": ""}
        log = subprocess.check_output(["/usr/bin/ldd", "-r", exe], env=local, text=True, timeout=25)
        (out / (name + ".relocate")).write_text(log)
        actual = {
            k: str(v.resolve(strict=True)) for k, v in GRAPH["START"]["interpret"](log).items()
        }
        expected_map = {k: v["file"] for k, v in static["closure"].items()} | {
            "libllama.so.0": str(dso)
        }
        need(actual == expected_map, "consumer providers")
        test = subprocess.check_output([exe, "--self-test"], env=local, timeout=25)
        need(test == b"PASS_ROLLBACK_ROW_PLAN\n", "client plan")
        results[name] = dict(image_sha256=expected, image=str(dso), providers=len(actual))
    return dict(
        status="GO_PACKED_CONTROL_CLIENT",
        commit=commit,
        tree=tree,
        protocol_sha256=METHOD,
        combo_sha256=COMBO,
        previous_build_sha256=RB["LIVE_ROLLBACK_BUILD"],
        source_sha256=sha(target),
        elf_sha256=sha(exe),
        headers=hs,
        arms=results,
        model_starts=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("previous", "base", "pack", "libraries", "static", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.new_output_dir.resolve()
    out.mkdir()
    start = time.monotonic()
    try:
        result = build(args, out)
        need(
            time.monotonic() - start < 180
            and sum(p.stat().st_size for p in out.iterdir()) < 32 << 20,
            "client build budget",
        )
    except Exception as e:
        result = dict(status="FAIL_PRESERVED", error=f"{type(e).__name__}: {e}", model_starts=0)
    result["wall_s"] = time.monotonic() - start
    save(out / "receipt.json", result)
    print(result["status"], result.get("error", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")

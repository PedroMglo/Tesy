"""Relink one C269 graph TU and verify the derived client and startup closures."""

import argparse
import hashlib
import importlib.util
import json
import os
import resource
import selectors
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import source  # noqa: E402

Q = source.Q
PRE = "2508e245fcde7ff411c93474919c3701ac95e98c1f76505d74a248d34a6aff16"
SOURCE_NAMES = ("source.py", "build.py", "protocol.md")
PROTO = "01c6db429fa7954365814c61812722106a653e1e78638a476c28e1ae5a2b3749"


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def need(ok, msg):
    if not ok:
        raise ValueError(msg)


def read(p):
    return json.loads(p.read_bytes())


def smoke(exe, native_env, startup, row, out):
    authority = module(Q / "nvme_r0_gate/qualified_profile/authority.py", "vma_checks")
    from_paths = {
        str(Path(files[1]).resolve(strict=True))
        for files in row["links"].values()
        if Path(files[1]).name != startup["libllama.so.0"]["file"]
    }
    candidate = out / "candidate" / startup["libllama.so.0"]["file"]
    expected = from_paths | {str(candidate)}
    pins = {v["file"]: v["sha256"] for v in startup.values()}
    need(len(expected) == len(pins) == 18, "startup population")
    keys = {}
    for path in expected:
        need(sha(path) == pins[Path(path).name], "model-free mapped object hash")
        keys[path] = authority.reference_key(path, authority.identity(path))
    with (out / "smoke.stderr").open("xb") as err:
        child = subprocess.Popen(
            [exe, "--mapping-test"],
            env=dict(native_env, CUDA_VISIBLE_DEVICES=""),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=err,
        )
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(child.stdout, selectors.EVENT_READ)
                need(bool(sel.select(10)) and child.stdout.readline() == b"READY\n", "smoke ready")
            proc = Path("/proc") / str(child.pid)
            need((proc / "exe").resolve(strict=True) == exe, "model-free executable identity")
            live = authority.check_maps((proc / "maps").read_text(), expected, keys)
            need(live == expected, "incomplete or extra startup VMA")
            data, _ = child.communicate(b"G", timeout=10)
            need(child.returncode == 0 and data == b"PASS_B3_NUMERIC_ROW_PLAN\n", "smoke return")
            return {"status": "PASS_LIVE_CANDIDATE", "objects": len(live), "pid": child.pid}
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()


def run(a, out, r):
    parent = module(source.FB / "build.py", "first_bound_elf")
    pfj = module(Q / "phase_fd/integrated/build.py", "pfj_elf")
    stock = module(Q / "stock_prefault_build/build.py", "ref_link")
    sec = module(
        Q / "igpu_resident_rank/request_budget/device/pack_native/dso/build.py", "ref_sections"
    )
    static = module(Q / "nvme_r0_gate/driver_pair/server_startup/screen.py", "check_startup")
    b = a.backend.resolve(strict=True)
    directory = b / "build-c269-cuda"
    base = directory / "bin" / pfj.IMAGE
    need(
        sha(HERE / "protocol.md") == PROTO
        and sha(b / "src/llama-graph.cpp") == source.GRAPH
        and sha(base) == pfj.ORIGINAL
        and sha(a.preflight_dir / "receipt.json") == PRE
        and pfj.git(b, "rev-parse", "HEAD") == pfj.WORKER
        and not pfj.git(b, "status", "--porcelain")
        and not pfj.git(HERE, "status", "--porcelain"),
        "origin",
    )
    pre = read(a.preflight_dir / "receipt.json")
    need(
        sha(a.preflight_dir / "static-map.json") == pre["static_map_sha256"]
        and sha(static.__file__) == pre["source_sha256"]
        and sha(pfj.CXX) == stock.GCC,
        "toolchain/preflight",
    )
    arm = read(a.preflight_dir / "static-map.json")["arms"]["C270"]
    for n, h in [
        ("compile_commands.json", pfj.DB),
        ("build.ninja", pfj.NINJA),
        ("CMakeFiles/rules.ninja", pfj.RULES),
    ]:
        need(sha(directory / n) == h, "frozen build " + n)
    toks = shlex.split(
        pfj.cmd("ninja", "-C", directory, "-t", "commands", "bin/" + pfj.IMAGE).splitlines()[-1]
    )
    inputs = {
        i: sha(directory / i)
        for i in toks
        if i.endswith(".o") or (not i.startswith("-") and ".so" in i and i != "bin/" + pfj.IMAGE)
    }
    objects = [i for i in inputs if i.endswith(".o")]
    need(
        len(objects) == 166
        and len(inputs) == 171
        and pfj.stamp(toks) == pfj.LINK
        and pfj.stamp(inputs) == pfj.INPUTS,
        "reference link object closure",
    )
    r.update(
        commit=pfj.git(HERE, "rev-parse", "HEAD"),
        tree=pfj.git(HERE, "rev-parse", "HEAD^{tree}"),
        worker_commit=pfj.WORKER,
        original_sha256=pfj.ORIGINAL,
        static_preflight_sha256=PRE,
        original_link_inputs_sha256=pfj.INPUTS,
        reused_objects=165,
        protocol_sha256=PROTO,
        compile_db_sha256=pfj.DB,
        compiler_sha256=stock.GCC,
        sources={n: sha(HERE / n) for n in SOURCE_NAMES},
    )
    obj = pfj.obj("src/llama-graph.cpp")
    (cfg,) = [
        x
        for x in read(directory / "compile_commands.json")
        if Path(x["file"]).resolve() == b / "src/llama-graph.cpp"
    ]
    cc = shlex.split(cfg["command"])
    need(
        cc[0] == pfj.CXX
        and cc[-4:] == ["-o", obj, "-c", cfg["file"]]
        and Path(cfg["directory"]).resolve() == directory,
        "graph compile flags",
    )
    pfj.SOURCES = {}
    baseabi = stock.abi(base)["dynamic"]
    base_syms = sec.abi_symbols(base)
    patch = out / "llama-graph.cpp"
    patch.write_text(source.graph((b / "src/llama-graph.cpp").read_text()))
    r["patched_tu_sha256"] = sha(patch)
    files = static.Files()
    startup = {}
    for mode in ("relink", "control", "candidate"):
        r["stage"] = mode
        dst = out / mode
        dst.mkdir()
        env = pfj.ENV | {"TMPDIR": str(dst)}
        ld = pfj.link_args(toks, dst)
        if mode != "relink":
            cmd = cc.copy()
            cmd[-3] = str(dst / Path(obj).name)
            if mode == "candidate":
                cmd[-1] = str(patch)
                cmd.insert(1, f"-fmacro-prefix-map={out}={Path(cfg['file']).parent}")
            stock.produce(cmd, directory, dst / "compile.log", env, time.monotonic() + 180)
            ld[ld.index(obj)] = cmd[-3]
        stock.produce(ld, directory, dst / "link.log", env, time.monotonic() + 90)
        image = dst / pfj.IMAGE
        (dst / pfj.SONAME).symlink_to(pfj.IMAGE)
        digest = sha(image)
        need(stock.abi(image)["dynamic"] == baseabi, "dynamic ABI")
        defs = sec.abi_delta(base_syms, sec.abi_symbols(image))
        diff = sec.section_diff(base, image)
        changed = sec.loadable_differences(diff)
        if mode == "relink":
            need(not changed and set(diff) <= {".comment", ".note.gnu.build-id"}, "control relink")
        if mode == "candidate":
            need(digest != r["control_sha256"] and changed, "candidate effect")
        r[mode + "_sha256"] = digest
        r[mode + "_file"] = str(image.relative_to(out))
        r[mode + "_alloc_differences"] = changed
        r[mode + "_cpp_abi_delta"] = defs
        startup[mode] = pfj.verify(
            arm, mode, image, pre["arms"]["C270"]["objects"], digest, static, files
        )
    need(all(sha(directory / k) == v for k, v in inputs.items()), "original objects changed")
    r["stage"] = "client"
    dst = out / "client"
    dst.mkdir()
    fn = parent.qualified_builder()
    fn.update(render=source.client, source_names=SOURCE_NAMES, unit=HERE)
    client_record = {}
    fn["run"](b, a.preflight_dir, dst, client_record)
    need(client_record["status"] == "PASS_C269_B3_NUMERIC_BUILD", "derived client")
    (dst / "receipt.json").write_text(json.dumps(client_record, sort_keys=True, indent=2) + "\n")
    exe = dst / client_record["executable"]
    probe = arm | {"executable": str(exe)}
    links = pfj.verify(
        probe,
        "candidate",
        out / r["candidate_file"],
        pre["arms"]["C270"]["objects"],
        r["candidate_sha256"],
        static,
        files,
    )
    need(links == startup["candidate"] and len(links) == 18, "client load closure")
    native_env = static.environment([str(out / "candidate"), *arm["native_search"]])
    r.update(
        status="PASS_INTEGRATED_ROUTER_BUILD",
        stage="closed",
        smoke=smoke(exe, native_env, links, arm, out),
        startup=startup,
        client_sha256=sha(exe),
        client_receipt_sha256=sha(dst / "receipt.json"),
        model_launches=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("backend", "preflight-dir", "new-output-dir"):
        p.add_argument("--" + n, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = {"stage": "origin", "status": "FAIL_PRESERVED", "model_launches": 0}
    start = time.monotonic()
    try:
        run(a, out, r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    r.update(
        wall_s=time.monotonic() - start,
        max_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )
    (out / "receipt.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(r["status"], r["stage"])
    raise SystemExit(int(r["status"] == "FAIL_PRESERVED"))

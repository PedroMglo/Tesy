"""Exercise the original C291 store constructor using GGML tensor headers and no forward."""

import argparse
import json
import os
import resource
import signal
import subprocess
import sys
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import derive  # noqa: E402

worker = run_path(str(derive.QUAL / "packed_worker/run.py"))
COMPILER = "ca48a2d27d0796399adc3387225eec4be62974e26fa299710edfde0c1af5aa63"


def native(a, out, result):
    receipt = a.derived_dir / "receipt.json"
    d = derive.load(receipt, a.derived_sha256)
    need = derive.need
    manifest = a.derived_dir / "expert-store-runtime.json"
    index = a.derived_dir / "integral-index.json"
    bases = a.derived_dir / "native-bases.tsv"
    model, pack = Path(d["model_path"]), Path(d["pack_path"])

    def current():
        need(
            d["status"] == derive.STATUS
            and d["protocol_sha256"] == derive.METHOD
            and d["commit"] == a.commit
            and derive.sha(bases) == d["bases_sha256"]
            and derive.sha(manifest) == d["manifest_sha256"]
            and derive.sha(index) == d["index_sha256"]
            and all(
                derive.runtime_stat(f.stat()) == d[key + "_stat"]
                for key, f in (
                    ("index", index),
                    ("manifest", manifest),
                    ("model", model),
                    ("pack", pack),
                )
            ),
            "private artifact integrity",
        )
        need(
            not any(f.stat().st_mode & 0o222 for f in (manifest, index, bases, pack)),
            "mutable derived inputs",
        )

    current()
    private = out / "source"
    files = worker["extract"](a.backend, private)
    base = a.ggml_base.resolve(strict=True)
    cc = Path("/usr/bin/g++")
    need(
        derive.sha(cc) == COMPILER and derive.sha(base) == worker["LIBS"]["ggml"],
        "compiler/ggml source",
    )
    exe = out / "native-parser"
    env = {
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "LD_LIBRARY_PATH": str(base.parent),
        "LD_BIND_NOW": "1",
        "TMPDIR": str(out),
    }

    def call(argv, name):
        log, err = out / (name + ".out"), out / (name + ".err")
        with log.open("xb") as stdout, err.open("xb") as stderr:
            with subprocess.Popen(
                argv, env=env, stdout=stdout, stderr=stderr, cwd=out, start_new_session=True
            ) as proc:
                try:
                    code = proc.wait(timeout=110)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
        need(not code, f"{name} exit {code}")
        return log.read_text()

    result.update(
        derived_sha256=a.derived_sha256,
        c291_commit=worker["PIN"],
        c291_tree=worker["TREE"],
        native_sha256=derive.sha(HERE / "native.cpp"),
        constructor_sha256=files["src/c291-expert-store.h"]["sha256"],
        reader_sha256=files["src/c291-direct-reader.h"]["sha256"],
        compiler_sha256=COMPILER,
        ggml_base_sha256=worker["LIBS"]["ggml"],
    )
    call(
        [
            str(cc),
            "-std=c++17",
            "-O0",
            "-g0",
            "-Wall",
            "-Wextra",
            "-pthread",
            "-fPIC",
            "-pie",
            "-fno-plt",
            *["-I" + str(private / name) for name in ("src", "include", "ggml/include")],
            HERE / "native.cpp",
            "-Wl,--wrap=pread",
            base,
            "-ldl",
            "-o",
            exe,
        ],
        "compile",
    )
    listing = call(["/usr/bin/ldd", exe], "link")
    lines = listing.splitlines()
    names = [Path(w).name.lower() for line in lines for w in line.split() if ".so" in w]
    need(
        "not found" not in listing
        and not any(
            part in name
            for name in names
            for part in ("libllama", "cuda", "nvidia", "cublas", "nvrtc")
        ),
        "unexpected shared object",
    )
    proof = json.loads(call([exe, manifest, model, pack, bases], "constructor"))
    need(
        proof["status"] == "PASS_C291_NATIVE_CONSTRUCTOR"
        and proof["layers"] == 36
        and proof["records"] == 4608
        and proof["tensor_headers"] == 108
        and proof["pread_calls"] == 0
        and proof["last_layer_offset_rejected"]
        and proof["pack_fd_direct"]
        and proof["ggml_provider"] == str(base)
        and proof["pack_stat"] == d["pack_stat"]
        and proof["model_stat"] == d["model_stat"]
        and proof["pack_bytes"] == derive.PLACER["SIZE"],
        "native loader evidence",
    )
    current()
    need(derive.sha(base) == worker["LIBS"]["ggml"], "changed ggml-base provider")
    result.update(
        status=proof["status"],
        proof=proof,
        executable_sha256=derive.sha(exe),
        child_peak_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )
    del result["proof"]["ggml_provider"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("derived-dir", "backend", "ggml-base", "new-output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--derived-sha256", required=True)
    p.add_argument("--commit", required=True)
    raise SystemExit(derive.bounded(p.parse_args(), native))

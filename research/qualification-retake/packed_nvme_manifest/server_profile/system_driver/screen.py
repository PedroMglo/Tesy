"""Authenticate the R0 and pack closures for numerical capture and HTTP on system CUDA."""

import argparse
import json
import os
import re
import signal
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[2]
REPO = QUAL.parents[1]
OLD = run_path(str(QUAL / "nvme_r0_gate/driver_pair/server_startup/screen.py"))
ORIGIN = run_path(str(QUAL / "nvme_r0_gate/driver_pair/driver_origin.py"))
SYS = run_path(str(QUAL / "ik_mapped_experts/hybrid/driver_62073/system.py"))
need, sha = SYS["need"], SYS["sha"]
SONAME = "libllama.so.0"
PACK = "9e553bcfa3dd8889100c8836bc3b873491248567672f93e7859e7f8b76e35116"


def validate(table, expected, files):
    need(set(table) == set(expected), "different SONAME set")
    result = {}
    for name, path in table.items():
        ref = expected[name]
        real = path.resolve(strict=True)
        need(str(real) == ref["file"] and "/stubs/" not in str(real), "unexpected path " + name)
        files.require(real, ref["sha256"])
        result[name] = ref
    return result


def measure(a, r):
    need(
        sha(a.pack_receipt) == PACK
        and not OLD["command"](["git", "-C", REPO, "status", "--porcelain"]),
        "pack authority or clean checkout",
    )
    pack = json.loads(a.pack_receipt.read_bytes())
    public = HERE.parent / "evidence/static.json"
    need(
        sha(public) == "3890cc76927d17845425550c5c36785297a0291969efb5433a62cea5bd0df716",
        "public pack map",
    )
    proof = json.loads(public.read_bytes())
    need(proof["raw_receipt_sha256"] == PACK and pack["status"] == proof["status"], "prior pack")
    locks = OLD["locks"](REPO)
    inp = locks[OLD["Q"] + "nvme_r0_gate/inputs/receipt.json"]
    original = locks[OLD["C270"]]
    capture = Path(original["runs"][0]["command"][0]).resolve(strict=True)
    server = Path(pack["server"]).resolve(strict=True)
    root = (Path(original["backend_root"]) / "build-c269-cuda/bin").resolve(strict=True)
    control = (root / SONAME).resolve(strict=True)
    candidate = Path(pack["startup"][SONAME]["file"]).resolve(strict=True)
    kernel = ORIGIN["kernel"]()
    version = SYS["VERSION"]
    need(kernel["release"] == version, "NVIDIA module")
    driver = Path("/usr/lib64")
    reported = {
        p.name: p.resolve(strict=True)
        for p in [
            driver / n
            for n in (
                "libcuda.so.1",
                "libnvidia-ptxjitcompiler.so.1",
                "libnvidia-nvvm70.so.4",
                "libnvidia-nvvm.so.4",
                "libnvidia-gpucomp.so." + version,
                "libnvidia-ml.so.1",
            )
        ]
        + [Path("/usr/bin/nvidia-smi")]
    }
    rpm = SYS["rpm_files"](reported.values())
    cuda = reported["libcuda.so.1"]
    need(rpm[str(cuda)] == SYS["DRIVER"], "current driver SHA")
    files = OLD["Files"]()
    files.require(capture, inp["capture_sha256"])
    files.require(server, inp["server_sha256"])
    files.require(control, pack["original_library_sha256"])
    files.require(candidate, pack["library_sha256"])
    overlay = a.new_output_dir / "libs"
    overlay.mkdir()
    (overlay / SONAME).symlink_to(candidate)
    table = pack["startup"]
    server_names = set(table)
    registry = locks[OLD["Q"] + "elf-evidence/receipt.json"]["selected_frozen_and_unpinned"]
    numeric_names = {
        s["load_name"] for s in registry if s["resolved_file"] in inp["startup_dso_sha256"]
    }
    ld = OLD["LOADER"]
    numeric_names.add(ld.name)
    need(len(server_names) == 24 and len(numeric_names) == 18, "reference sizes")
    r.update(
        commit=OLD["command"](["git", "-C", REPO, "rev-parse", "HEAD"]).strip(),
        tree=OLD["command"](["git", "-C", REPO, "rev-parse", "HEAD^{tree}"]).strip(),
        kernel=kernel,
        driver_files=rpm,
        previous_pack_sha256=PACK,
        source_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
        arms={},
    )
    for client, exe, names in (("C270", capture, numeric_names), ("C281", server, server_names)):
        common = [root] if client == "C270" else [root, server.parent]
        for variant, image in (("R0", control), ("PACK", candidate)):
            dirs = ([overlay] if variant == "PACK" else []) + common
            env = OLD["environment"](dirs)
            expected = {n: table[n] for n in names}
            expected["libcuda.so.1"] = dict(file=str(cuda), sha256=rpm[str(cuda)])
            expected[SONAME] = dict(file=str(image), sha256=files.rows[str(image)]["sha256"])
            key = client + "_" + variant
            listings = {}
            for operation, cmd in (
                ("list", [ld, "--list", exe]),
                ("relocate", ["/usr/bin/ldd", "-r", exe]),
            ):
                proc = subprocess.run(cmd, text=True, env=env, capture_output=True, timeout=25)
                text = proc.stdout + proc.stderr
                log = a.new_output_dir / (key + "." + operation)
                with log.open("x") as stream:
                    stream.write(text)
                need(
                    proc.returncode == 0
                    and not re.search("undefined symbol|not found|/stubs/", text),
                    key + " " + operation,
                )
                mapped = OLD["interpret"](text)
                listings[operation] = validate(mapped, expected, files)
            need(listings["list"] == listings["relocate"], "relocation differs")
            other = candidate if variant == "R0" else control
            wrong = expected | {
                SONAME: dict(file=str(other), sha256=files.rows[str(other)]["sha256"])
            }
            try:
                validate(mapped, wrong, files)
            except ValueError as exc:
                need(str(exc) == "unexpected path " + SONAME, "wrong-provider rejection")
            else:
                raise ValueError("wrong provider accepted")
            r["arms"][key] = dict(
                binary=str(exe),
                binary_sha256=files.rows[str(exe)]["sha256"],
                search=list(map(str, dirs)),
                closure=expected,
                wrong_provider_rejected=True,
            )
    need(
        all(
            OLD["info"](Path(p).stat()) == {k: v for k, v in row.items() if k != "sha256"}
            for p, row in files.rows.items()
        ),
        "ELF changed",
    )
    need(
        ORIGIN["kernel"]() == kernel and (overlay / SONAME).resolve(strict=True) == candidate,
        "module or overlay changed",
    )
    r.update(unique_elf_B=files.size, status="GO_CURRENT_NUMERICAL_GATE")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack-receipt", required=True, type=Path)
    p.add_argument("--new-output-dir", required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir = a.new_output_dir.resolve()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    state = dict(status="FAIL_PRESERVED", model_starts=0, gpu_allocations=0)

    def timeout(*_):
        raise TimeoutError("static budget")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(180)
    try:
        measure(a, state)
    except Exception as exc:
        state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
    state["raw_sha256"] = {f.name: sha(f) for f in a.new_output_dir.iterdir() if f.is_file()}
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(state, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(state["status"], state.get("error", ""))
    raise SystemExit(state["status"] == "FAIL_PRESERVED")

"""Verify C292 loader names and relocations without calling the capture's main."""

import argparse
import datetime as dt
import json
import os
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import derive  # noqa: E402

sys.path.insert(0, str(derive.QUAL / "nvme_r0_gate/qualified_profile"))
from authority import Authority, aliases, need, sha  # noqa: E402

PROTOCOL = "973f64ebf97ff9b91ab567f99e6ed88222a7604cb94c36a5dd32c9beb4b79085"
PREFLIGHT = "2508e245fcde7ff411c93474919c3701ac95e98c1f76505d74a248d34a6aff16"
ADDENDUM = "b7cc2e57f10e81250552c29920b9f4891e93c6e515bc394c48ffb82d89e4e978"
DERIVED_R01 = "80d71b6ee146be81c4e07c5b17dde0786effde6fa58ecd3268491eda6c810810"
DERIVED_R02 = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9"
CHAINS = {
    DERIVED_R01: "ddeabdee9c60a0c5bc5eb4ec9726c864c800d066ec8c55bfccb41a412a2be2ba",
    DERIVED_R02: "c81c15cb9614fd2780f35d5f3fc2b96ce280056f9da363ca74b42b112d1642f1",
}
PLACEMENT = "adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000"
C292 = "a936cb62c11a9eb070f52ddd5db53cc6923803994bf5a688f9bb46d679c9a1d3"
CAPTURE = "5367cd38bb2792f82a482bb3fa14f4c38ba3f949cfde8c482683683e0238e2dd"
C291 = "04af70ea943b816769e2c6d62873ded11f00603df6c3be42340b3785aa880819"
C269 = "347267b2e9cbf920dbf912d6aaf1884e5eff4cccc41c349e93c42bd6403a658f"
LDD = "59731556246d2f07d39b072592442f774996b2b0c0166ce3f8d094a8c2785d56"
PIN = "c89c88b342054223e3f27a17fbfd0954803147ac"
TREE = "3962daa588dfa89971c60c95ce4c5054bc27fd3f"
SONAME = "libllama.so.0"
CLEAN = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}


def verify_listing(listed, sealed, candidate_alias, candidate_image):
    need(len(listed) == len(sealed) == 18 and listed.keys() == sealed.keys(), "SONAME census")
    for name, path in listed.items():
        real = path.resolve(strict=True)
        if name == SONAME:
            need(path == candidate_alias and real == candidate_image, "wrong libllama provider")
        else:
            need(str(real) == sealed[name][1], "wrong provider: " + name)
    return {n: str(p.resolve(strict=True)) for n, p in listed.items()}


def chain(derived_sha, constructor_sha):
    need(
        derived_sha in CHAINS and CHAINS[derived_sha] == constructor_sha,
        "unknown or crossed derivation and constructor",
    )


def metadata(a):
    folder = a.derived_dir.resolve(strict=True)
    chain(a.derived_sha256, a.constructor_sha256)
    row = derive.load(folder / "receipt.json", a.derived_sha256)
    prior = derive.load(a.constructor_receipt, a.constructor_sha256)
    manifest = folder / "expert-store-runtime.json"
    index = folder / "integral-index.json"
    need(
        row["status"] == derive.STATUS
        and row["pack_placement_sha256"] == PLACEMENT
        and prior["status"] == "PASS_C291_NATIVE_CONSTRUCTOR"
        and prior["derived_sha256"] == a.derived_sha256
        and prior["proof"]["pack_fd_direct"]
        and prior["proof"]["pread_calls"] == 0
        and prior["c291_commit"] == PIN
        and prior["c291_tree"] == TREE,
        "derived metadata and constructor",
    )
    for name, path in (
        ("manifest", manifest),
        ("index", index),
        ("pack", Path(row["pack_path"])),
        ("model", Path(row["model_path"])),
    ):
        need(
            not path.is_symlink() and derive.runtime_stat(path.stat()) == row[name + "_stat"],
            "current stat: " + name,
        )
    data = derive.load(manifest, row["manifest_sha256"])
    need(
        sha(index) == row["index_sha256"] == data["index_sha256"]
        and Path(data["index_path"]) == index
        and data["model_stat"] == prior["proof"]["model_stat"] == row["model_stat"]
        and data["pack_stat"] == prior["proof"]["pack_stat"] == row["pack_stat"]
        and data["index_stat"] == row["index_stat"]
        and not any(p.stat().st_mode & 0o222 for p in (manifest, index)),
        "private manifest/index and original payload identities",
    )
    return manifest, row


def git(*args):
    env = CLEAN | {"GIT_OPTIONAL_LOCKS": "0"}
    return subprocess.check_output(
        [
            "/usr/bin/git",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            derive.REPO,
            *args,
        ],
        env=env,
        timeout=10,
        text=True,
    ).strip()


def scope(unit):
    raw = Path("/proc/self/cgroup").read_text().strip()
    need(raw.startswith("0::/") and raw.endswith("/" + unit + ".scope"), "isolated cgroup")
    base = Path("/sys/fs/cgroup") / raw[3:].lstrip("/")
    values = {
        k: (base / k).read_text().strip()
        for k in ("memory.max", "memory.high", "memory.swap.max", "memory.peak")
    }
    need(
        values["memory.max"] == values["memory.high"] == str(2 << 30)
        and values["memory.swap.max"] == "0",
        "frozen memory/swap envelope",
    )
    return {k: int(v) for k, v in values.items()}


def query(out, label, cmd, env, trace):
    start = time.monotonic_ns()
    stdout, stderr = [out / f"{label}.{ext}" for ext in ("out", "err")]
    with stdout.open("xb") as out_file, stderr.open("xb") as err_file:
        child = subprocess.run(
            cmd, cwd=out, env=env, stdout=out_file, stderr=err_file, timeout=18, check=False
        )
    trace[label] = dict(
        argv=list(map(str, cmd)),
        elapsed_ns=time.monotonic_ns() - start,
        returncode=child.returncode,
        stdout_sha256=sha(stdout),
        stderr_sha256=sha(stderr),
    )
    need(
        not child.returncode and stderr.stat().st_size == 0 and stdout.stat().st_size <= 1 << 20,
        "unresolved/diagnostic query: " + label,
    )
    return stdout.read_text().strip()


def historical(a):
    ledger = derive.load(
        derive.REPO / "results/c292-expert-store-inventory-sha-repair-20261006/protocol.json", C292
    )
    need(ledger["backend_commit"] == PIN and ledger["backend_tree"] == TREE, "C291 source")
    exe = (a.bin_dir / "expert-store-capture").resolve(strict=True)
    lib = (a.bin_dir / "libllama.so.0").resolve(strict=True)
    for path, digest, section in ((exe, CAPTURE, "file_sha256"), (lib, C291, "binary_libraries")):
        rows = [v for k, v in ledger[section].items() if Path(k).name == path.name]
        need(rows == [digest] and sha(path) == digest, "C292 binary: " + path.name)
    return exe, lib, ledger


def screen(a, out, r):
    need(
        sha(HERE / "protocol.md") == PROTOCOL
        and git("rev-parse", "HEAD") == a.commit
        and sha(HERE / "metadata-pairs.md") == ADDENDUM
        and not git("status", "--porcelain"),
        "frozen checkout",
    )
    r.update(
        commit=a.commit,
        tree=git("rev-parse", "HEAD^{tree}"),
        protocol_sha256=PROTOCOL,
        supervisor_sha256=sha(Path(__file__)),
        initial_scope=scope(a.unit),
        queries={},
        metadata_addendum_sha256=ADDENDUM,
        derived_sha256=a.derived_sha256,
        constructor_sha256=a.constructor_sha256,
        static_preflight_sha256=PREFLIGHT,
    )
    auth = Authority(derive.REPO, a.preflight_dir, PREFLIGHT, "C270")
    manifest, inputs = metadata(a)
    exe, lib, historical_contract = historical(a)
    original = Path(auth.links[SONAME][1])
    known = {Path(k).name: v for k, v in historical_contract["binary_libraries"].items()}
    need(
        auth.files[str(original)]["sha256"] == C269
        and len(known) == 5
        and all(
            known[Path(real).name] == auth.files[real]["sha256"]
            for name, (_, real) in auth.links.items()
            if name.startswith("libggml")
        ),
        "C292 and current C270 must agree on all four GGML providers",
    )
    ld = auth.static.LOADER
    ldd = Path("/usr/bin/ldd")
    need(sha(ldd) == LDD and sha(ld) == auth.files[str(ld.resolve())]["sha256"], "loader tools")
    private = out / "libs"
    private.mkdir(mode=0o700)
    alias = private / SONAME
    alias.symlink_to(lib)
    aliases(private, {SONAME: str(lib)})
    selection = [str(private), *auth.arm["native_search"]]
    got = {}
    for mode in ("original-control", "off", "on"):
        control = mode == "original-control"
        env = auth.static.environment(auth.arm["native_search"] if control else selection)
        if mode == "on":
            env["TESY_EXPERT_STORE_MANIFEST"] = str(manifest)
        if not control:
            result = query(out, mode + "-verify", [ld, "--verify", exe], env, r["queries"])
            need(result == "", "interpreter verification")
        text = query(out, mode + "-list", [ld, "--list", exe], env, r["queries"])
        listing = auth.static.interpret(text)
        if control:
            verify_listing(listing, auth.links, Path(auth.links[SONAME][0]), original)
            try:
                verify_listing(listing, auth.links, alias, lib)
            except ValueError as exc:
                need(str(exc) == "wrong libllama provider", "wrong negative control")
            else:
                raise ValueError("original provider accepted as C291")
        else:
            got[mode] = verify_listing(listing, auth.links, alias, lib)
            text = query(out, mode + "-relocations", [ldd, "-r", exe], env, r["queries"])
            relocated = verify_listing(auth.static.interpret(text), auth.links, alias, lib)
            need(relocated == got[mode], "relocation map differs")
    need(got["off"] == got["on"], "OFF/ON providers")
    auth.recheck()
    aliases(private, {SONAME: str(lib)})
    need(sha(lib) == C291 and sha(exe) == CAPTURE and sha(ldd) == LDD, "control images changed")
    metadata(a)
    alias_image = (a.bin_dir / "libllama.so.0").resolve(strict=True)
    need(alias_image == lib, "source libllama alias changed")
    again = auth.static.interpret(
        query(
            out,
            "original-end",
            [ld, "--list", auth.exe],
            auth.static.environment(auth.arm["native_search"]),
            r["queries"],
        )
    )
    need(
        {k: [str(p), str(p.resolve(strict=True))] for k, p in again.items()} == auth.links,
        "terminal C270 control",
    )
    mapped = {
        k: {"file": v, "sha256": C291 if k == SONAME else auth.files[v]["sha256"]}
        for k, v in got["on"].items()
    }
    r.update(
        status="PASS_C292_CAPTURE_STATIC_CLOSURE",
        binary_sha256=CAPTURE,
        library_sha256=C291,
        startup=mapped,
        original_provider_rejected=True,
        manifest_sha256=inputs["manifest_sha256"],
        index_sha256=inputs["index_sha256"],
        preflight_map_sha256=auth.pre["static_map_sha256"],
        driver_deployment=auth.origin.COMMIT,
        kernel=auth.pre["kernel"],
        loader_sha256=sha(ld),
        ldd_sha256=LDD,
        explicit_search=selection,
        manifest=str(manifest),
        executable=str(exe),
        c270_executable=str(auth.exe),
        final_scope=scope(a.unit),
        payload_read_bytes=0,
        backend_enumerations=0,
        model_processes=0,
        transformer_forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("bin-dir", "preflight-dir", "derived-dir", "constructor-receipt", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--derived-sha256", required=True)
    p.add_argument("--constructor-sha256", required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--unit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic_ns()
    row = {"status": "FAIL_PRESERVED", "started_utc": dt.datetime.now(dt.UTC).isoformat()}

    def stop(*_):
        raise TimeoutError("120 s closure budget")

    signal.signal(signal.SIGALRM, stop)
    signal.alarm(120)
    try:
        screen(a, out, row)
        size = sum(p.stat().st_size for p in out.iterdir() if p.is_file())
        need(size + len(json.dumps(row)) + 65536 < 8 << 20, "private output budget")
    except Exception as exc:
        row.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    row.update(
        finished_utc=dt.datetime.now(dt.UTC).isoformat(),
        elapsed_ns=time.monotonic_ns() - start,
        self_peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        children_peak_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )
    derive.save(out / "receipt.json", row)
    print(row["status"])
    return int(row["status"] != "PASS_C292_CAPTURE_STATIC_CLOSURE")


if __name__ == "__main__":
    raise SystemExit(main())

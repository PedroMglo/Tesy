"""Derive C291-private metadata for the authenticated C290 NVMe placement."""

import argparse
import fcntl
import hashlib
import json
import os
import resource
import signal
import stat
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
QUAL = HERE.parent
REPO = QUAL.parents[1]
PLACER = run_path(str(QUAL / "packed_nvme_placement/install_pack.py"))
need = PLACER["need"]
METHOD = "7fb7597c9f70023946198fb0b4be0a2e66842d5f213fa404daea980175297672"
PLACER_SHA = "0299a870d0ee8b37e782983f4e82ce1586c7284976bde8ae5b9eaa416084628b"
HISTORICAL_STAT = "4f87414f2660f8afe25ae619c04239d2cb8b4f1c0a331d7114af24e17229a9c0"
LIMIT = 32 << 20
STATUS = "PASS_DERIVED_C290_NVME_METADATA"
INDEX_FIELDS = {"pack_path", "model_stat"}
MANIFEST_FIELDS = {"model_stat", "index_path", "index_sha256", "index_stat", "pack_stat"}


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load(path, digest):
    need(
        not path.is_symlink() and path.is_file() and path.stat().st_size <= LIMIT,
        "metadata type/size",
    )
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == digest, "metadata digest " + path.name)
    return json.loads(raw)


def stored(path, data):
    with path.open("xb") as f:
        f.write(data)
        f.flush()
        os.fchmod(f.fileno(), 0o444)
        os.fsync(f.fileno())
        need(path.stat() == os.fstat(f.fileno()), "metadata publication race")


def save(path, data):
    stored(path, json.dumps(data, separators=(",", ":"), allow_nan=False).encode() + b"\n")


def runtime_stat(st):
    return dict(
        dev=st.st_dev,
        inode=st.st_ino,
        size_bytes=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


def fd_stat(fd, path):
    st = os.fstat(fd)
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    need(
        stat.S_ISREG(st.st_mode)
        and flags & os.O_DIRECT
        and flags & os.O_ACCMODE == os.O_RDONLY
        and runtime_stat(st) == runtime_stat(path.lstat()),
        "DIRECT FD/path identity",
    )
    return st


def validate_changes(original, view, replacements, allowed):
    need(
        set(replacements) == allowed
        and original.keys() == view.keys()
        and view == (original | replacements),
        "change outside the derivation contract",
    )


def check_placement(p):
    need(
        p["status"] == "PASS_NVME_C290_FULL_PACK_PLACEMENT"
        and p["program_sha256"] == PLACER_SHA
        and p["protocol_sha256"] == PLACER["METHOD"]
        and p["source_sha256"] == p["destination_sha256"] == PLACER["DIGEST"]
        and p["source_read_bytes"]
        == p["destination_reread_bytes"]
        == p["destination_write_bytes"]
        == p["size_bytes"]
        == PLACER["SIZE"]
        and (p["source_transport"], p["destination_transport"]) == ("usb", "nvme")
        and p["runtime_manifest_sha256"] == PLACER["MANIFEST"]
        and p["index_sha256"] == PLACER["INDEX"]
        and p["readback_sha256"] == PLACER["READBACK"]
        and p["readback_analysis_sha256"] == PLACER["READBACK_ANALYSIS"],
        "C290 placement authority",
    )


def verify_descriptors(index, meta, roles):
    need(len(meta) == 108 and len(index["experts"]) == 36 * 128, "coverage")
    for pos, entry in enumerate(index["experts"]):
        layer, expert = divmod(pos, 128)
        need(
            (entry["layer"], entry["expert"], entry["pack_offset"])
            == (layer, expert, pos * index["stride"])
            and len(entry["components"]) == 6,
            "expert/record position",
        )
        for component, role in enumerate(roles):
            weight = entry["components"][component]
            base, slab = meta[layer, component]
            need(
                weight["name"] == f"blk.{layer}.ffn_{role}_exps.weight"
                and weight["source_offset"] == base + expert * slab
                and weight["packed_relative_offset"] == component * slab
                and weight["type"] == "mxfp4"
                and weight["size_bytes"] == slab == 4_406_400,
                "GGUF inventory and C290 record disagree",
            )


def derive(a, out, result):
    p = load(a.pack_placement, a.pack_sha256)
    check_placement(p)
    cold_root = QUAL / "phase_fd/integrated/cold_read_fixture"
    cold = run_path(str(cold_root / "runner.py"))
    io = cold["io"]
    inv = run_path(str(cold_root / "plan.py"))
    g = load(a.model_placement, io.PLACEMENT_SHA)
    c = load(a.c55, p["c55_sha256"])
    h = load(QUAL / "aster_fixed_reference/c55-r01/receipt.json", HISTORICAL_STAT)
    need(
        p["placement_sha256"] == io.PLACEMENT_SHA
        and g["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and g["source_sha256"] == g["destination_direct_reread"]["sha256"] == io.TARGET
        and g["source_size"] == g["destination_direct_reread"]["size_bytes"] == inv["MODEL_SIZE"]
        and c["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not c["reason"]
        and c["selected_stat"] == h["selected_stat"],
        "model and C55 authority",
    )
    for path, digest in [
        (a.pack_placement.with_name("inventory.json"), p["inventory_sha256"]),
        (a.pack_placement.parent / "raw/transfer.jsonl", p["monitor_sha256"]),
        (a.c55.with_name("resource-policy.json"), c["canonical_policy_sha256"]),
    ]:
        need(
            path.is_file() and path.stat().st_size <= LIMIT and sha(path) == digest,
            "placement evidence",
        )
    model = Path(g["working_copy"]).resolve(strict=True)
    pack = Path(p["destination"]).resolve(strict=True)
    origin = SimpleNamespace(
        runtime_manifest=a.runtime_manifest,
        index=a.index,
        readback=a.readback,
        source=Path(p["source"]),
    )
    src = PLACER["authorities"](origin, load, io.TARGET)
    need(
        PLACER["identity"](src.stat()) == p["source_stat"]
        and pack == Path(p["destination"])
        and pack.parent == model.parent
        and io.mount(pack)[1] == io.mount(model)[1] == "btrfs"
        and io.disk(pack, "nvme") == io.disk(model, "nvme"),
        "storage placement",
    )
    m, idx = load(a.runtime_manifest, PLACER["MANIFEST"]), load(a.index, PLACER["INDEX"])
    meta = inv["metadata"](a.inventory)
    verify_descriptors(idx, meta, inv["ROLES"])
    need(idx["metadata_sha256"] == inv["INVENTORY"], "C290 inventory binding")
    with ExitStack() as stack:
        model_fd = PLACER["open_direct"](model, os.O_RDONLY)
        stack.callback(os.close, model_fd)
        pack_fd = PLACER["open_direct"](pack, os.O_RDONLY)
        stack.callback(os.close, pack_fd)
        ms, ps = fd_stat(model_fd, model), fd_stat(pack_fd, pack)
        need(
            io.stat_id(model) == c["selected_stat"]
            and PLACER["identity"](ps) == p["destination_stat"]
            and not ps.st_mode & 0o222,
            "current model or readonly pack identity",
        )
        index_path = out / "integral-index.json"
        manifest_path = out / "expert-store-runtime.json"
        it = dict(pack_path=str(pack), model_stat=runtime_stat(ms))
        save(index_path, idx | it)
        ih = sha(index_path)
        validate_changes(idx, load(index_path, ih), it, INDEX_FIELDS)
        mt = dict(
            index_path=str(index_path),
            index_sha256=ih,
            index_stat=runtime_stat(index_path.stat()),
            model_stat=runtime_stat(ms),
            pack_stat=runtime_stat(ps),
        )
        save(manifest_path, m | mt)
        mh = sha(manifest_path)
        validate_changes(m, load(manifest_path, mh), mt, MANIFEST_FIELDS)
        bases = out / "native-bases.tsv"
        stored(
            bases,
            "".join(
                f"{layer} {role} {meta[layer, role][0]} {meta[layer, role][1]}\n"
                for layer in range(36)
                for role in range(3)
            ).encode("ascii"),
        )
        need(
            runtime_stat(ms) == runtime_stat(fd_stat(model_fd, model))
            and runtime_stat(ps) == runtime_stat(fd_stat(pack_fd, pack))
            and runtime_stat(index_path.stat()) == mt["index_stat"]
            and sha(a.index) == PLACER["INDEX"]
            and sha(a.runtime_manifest) == PLACER["MANIFEST"],
            "final input/metadata identity",
        )
        result.update(
            status=STATUS,
            pack_placement_sha256=a.pack_sha256,
            c55_sha256=p["c55_sha256"],
            model_placement_sha256=io.PLACEMENT_SHA,
            historical_model_stat_sha256=HISTORICAL_STAT,
            original_index_sha256=PLACER["INDEX"],
            original_manifest_sha256=PLACER["MANIFEST"],
            original_readback_sha256=PLACER["READBACK"],
            original_readback_analysis_sha256=PLACER["READBACK_ANALYSIS"],
            model_sha256=io.TARGET,
            pack_sha256=PLACER["DIGEST"],
            pack_path=str(pack),
            model_path=str(model),
            model_stat=mt["model_stat"],
            pack_stat=mt["pack_stat"],
            index_sha256=ih,
            index_stat=mt["index_stat"],
            manifest_sha256=mh,
            manifest_stat=runtime_stat(manifest_path.stat()),
            bases_sha256=sha(bases),
            inventory_sha256=inv["INVENTORY"],
            layers=36,
            experts=4608,
            weights=13824,
            descriptors=27648,
            payload_read_bytes=0,
        )


def bounded(args, step):
    os.umask(0o077)
    out = args.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    result = {"status": "FAIL_PRESERVED"}
    start = time.monotonic()

    def stop(*_):
        raise TimeoutError("120 s phase")

    signal.signal(signal.SIGALRM, stop)
    signal.alarm(120)
    try:
        cap = 512 << 20
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        resource.setrlimit(resource.RLIMIT_AS, (min(cap, soft) if soft >= 0 else cap, hard))

        def git(*cmd):
            return subprocess.check_output(
                [
                    "git",
                    "-c",
                    "core.preloadIndex=false",
                    "-c",
                    "index.threads=1",
                    "-C",
                    str(REPO),
                    *cmd,
                ],
                text=True,
                timeout=10,
            ).strip()

        need(
            git("rev-parse", "HEAD") == args.commit
            and not git("status", "--porcelain")
            and sha(HERE / "protocol.md") == METHOD,
            "clean frozen checkout/protocol",
        )
        result.update(
            commit=args.commit, tree=git("rev-parse", "HEAD^{tree}"), protocol_sha256=METHOD
        )
        result["program_sha256"] = sha(Path(step.__code__.co_filename))
        step(args, out, result)
        need(
            sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) + 65536 <= LIMIT,
            "32 MiB output budget",
        )
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    result.update(
        elapsed_s=time.monotonic() - start,
        peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    save(out / "receipt.json", result)
    dfd = os.open(out, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "pack-placement",
        "model-placement",
        "c55",
        "runtime-manifest",
        "index",
        "readback",
        "inventory",
        "new-output-dir",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--pack-sha256", required=True)
    p.add_argument("--commit", required=True)
    raise SystemExit(bounded(p.parse_args(), derive))

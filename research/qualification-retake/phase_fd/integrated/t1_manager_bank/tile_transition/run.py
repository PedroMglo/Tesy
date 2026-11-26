"""Run the four synthetic C291 tile-transition arms in one new, externally bounded CPU scope."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("reference", "disk", "bank", "broken")
SOURCES = {
    "run.py": "67523bc7c44d6cf1182b45008e7414d160254b62a64c1ffe142fe934ab65509e",
    "generate.py": "3b9c94261e71e3a0aef16311670ca907343e89b5474af3bbf13899e5eadc6c5d",
}


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path, obj):
    with path.open("x") as f:
        json.dump(obj, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def execute(a, out, result):
    started = time.monotonic()
    repo = a.repo.resolve(strict=True)
    pw = repo / "research/qualification-retake/packed_worker"
    if HERE.parents[5] != repo or any(sha(pw / n) != s for n, s in SOURCES.items()):
        raise ValueError("measurement checkout or packed_worker source identity")
    old = load("tile_packed_worker", pw / "run.py")
    head = old.git(repo, "rev-parse", "HEAD").decode().strip()
    old.need(
        head == a.commit and not old.git(repo, "status", "--porcelain"),
        "clean measurement revision",
    )
    old.need(
        sha(HERE / "protocol.md")
        == "67a19616821b09d901deb1d491c48b4c33eb6cc6b4de9592751b667c40ca111e",
        "frozen protocol",
    )
    result.update(
        commit=head,
        tree=old.git(repo, "rev-parse", "HEAD^{tree}").decode().strip(),
        sources={
            n: sha(HERE / n)
            for n in ("protocol.md", "run.py", "overlay.py", "fixture.cpp", "review.py")
        },
        reused=SOURCES,
        model_processes=0,
        arms={},
        commands={},
    )
    native = a.backend.resolve(strict=True)
    private = out / "private-c291"
    extracted = old.extract(native, private)
    result.update(
        worker_commit=old.PIN, worker_tree=old.TREE, native_sources_sha256=old.canonical(extracted)
    )
    load("tile_transition_overlay", HERE / "overlay.py").patch_private(private)
    result["patched_worker_sha256"] = sha(private / "src/llama-moe-stream.cpp")
    if a.source_only:
        result["status"] = "PASS_PIN_AND_PRIVATE_OVERLAY_ONLY"
        return
    old.need(a.scope_unit and a.new_nvme_dir, "supply --scope-unit and --new-nvme-dir")
    observe = old.cgroup_reader(repo, a.scope_unit)
    result["scope_before"] = observe()
    nvme = a.new_nvme_dir.resolve()
    old.need(
        not nvme.exists()
        and nvme.parent.is_dir()
        and not nvme.is_relative_to(out)
        and not out.is_relative_to(nvme),
        "new separate NVMe root",
    )
    mount = json.loads(
        old.cmd(["findmnt", "--json", "--target", nvme.parent, "--output", "FSTYPE,SOURCE"])
    )["filesystems"]
    old.need(
        len(mount) == 1
        and mount[0]["fstype"] == "btrfs"
        and re.fullmatch(r"/dev/nvme\d+n\d+(?:p\d+)?(?:\[.*\])?", mount[0]["source"]),
        "internal Btrfs NVMe required",
    )
    base = (
        native.parent / "c269-layer-last-use/build-c269-cuda/bin/libggml-base.so.0.15.3"
    ).resolve(strict=True)
    crypto = Path("/usr/lib64/libcrypto.so.3").resolve(strict=True)
    libs = {"ggml": base, "crypto": crypto}
    before = {name: old.identity(path) for name, path in libs.items()}
    old.need({name: sha(path) for name, path in libs.items()} == old.LIBS, "provider hashes")
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        TMPDIR=str(out),
        CUDA_VISIBLE_DEVICES="",
        MALLOC_ARENA_MAX="2",
        OMP_NUM_THREADS="1",
        LD_LIBRARY_PATH=str(base.parent),
    )
    deadline = started + old.WALL

    def step(argv, label):
        return old.record_command(argv, out, label, env, result["commands"], deadline, observe)

    old.HERE = HERE  # Reuse the pinned compiler/linker with this unit's fixture.cpp.
    exe, result["binary"] = old.compile_fixture(private, "tile-transition", base, crypto, out, step)
    review = load("tile_transition_review", HERE / "review.py")
    step([sys.executable, "-IB", pw / "generate.py", "--new-output-dir", nvme], "generate")
    pack, goldfile = nvme / "experts.pack", nvme / "gold.json"
    identity = old.identity(pack)
    original_gold = goldfile.read_bytes()
    with (out / "gold.json").open("xb") as f:
        f.write(original_gold)
    gold = json.loads(original_gold)
    result["gold_sha256"] = sha(goldfile)
    old.need(
        sha(out / "gold.json") == result["gold_sha256"]
        and pack.stat().st_size == gold["pack_bytes"] == 6 * old.STRIDE,
        "pack metadata",
    )
    rows = {}
    for arm in ARMS:
        label = "case-" + arm
        raw = out / label / "raw.json"
        step([exe, arm, pack, goldfile, raw], label)
        row = json.loads(raw.read_bytes())
        old.need(
            row["arm"] == arm
            and row["status"] == "PASS_C291_TILE_TRANSITION_CPU"
            and row["destructor_returned"] is True
            and row["workers"] == 4,
            "child status",
        )
        for name, path in libs.items():
            provider = row["providers"][name]
            old.need(
                Path(provider["path"]) == path
                and provider["identity"] == before[name] == old.identity(path)
                and Path(result["binary"]["load_paths"][name]) == path
                and sha(path) == old.LIBS[name],
                "ELF identity: " + name,
            )
        align = row["offset_alignment"]
        old.need(
            type(align) is int
            and align > 0
            and old.STRIDE % align == 0
            and row["read_extent"] == ((3 * old.SLAB + align - 1) // align) * align,
            "direct transport geometry",
        )
        old.need(
            row["pack_sha256"] == gold["pack_sha256"]
            and row["pack_proof_bytes"] == 2 * identity["size_bytes"]
            and old.identity(pack) == identity
            and sha(goldfile) == result["gold_sha256"],
            "pack file identity",
        )
        rows[arm] = row
        result["arms"][arm] = {
            "raw_sha256": sha(raw),
            "child_launches": 1,
            "maxrss_kib": result["commands"][label]["maxrss_kib"],
        }
        review.case(arm, row, gold)
    result["verified"] = review.family(rows, gold)
    result["scope_final"] = observe()
    old.need(
        set(p.name for p in nvme.iterdir()) == {"gold.json", "experts.pack"}
        and old.identity(pack) == identity,
        "cleanup contents",
    )
    pack.unlink()
    goldfile.unlink()
    nvme.rmdir()
    result["status"] = "PASS_C291_TILE_TRANSITION_CPU_FAMILY"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("repo", "backend", "new-output"):
        p.add_argument("--" + field, type=Path, required=True)
    p.add_argument("--new-nvme-dir", type=Path)
    p.add_argument("--scope-unit")
    p.add_argument("--source-only", action="store_true")
    p.add_argument("--commit", required=True, help="frozen Tesy HEAD")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output.resolve()
    out.mkdir(mode=0o700)
    result = {"status": "FAIL_PRESERVED"}
    try:
        execute(a, out, result)
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    write(out / "receipt.json", result)
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

"""Future execution in an isolated 1-GiB scope; --source-only never compiles."""

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
ORIGINAL = {
    "run.py": "67523bc7c44d6cf1182b45008e7414d160254b62a64c1ffe142fe934ab65509e",
    "generate.py": "3b9c94261e71e3a0aef16311670ca907343e89b5474af3bbf13899e5eadc6c5d",
}
CASES = ("off", "on", "eio", "stale", "shutdown")


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(a):
    out = a.new_output.resolve()
    out.mkdir(mode=0o700)
    pw = a.repo.resolve() / "research/qualification-retake/packed_worker"
    result = {"status": "FAIL_PRESERVED", "cases": {}, "commands": {}}
    try:
        if any(sha(pw / name) != digest for name, digest in ORIGINAL.items()):
            raise ValueError("packed_worker source identity")
        old = module("c291_original", pw / "run.py")
        overlay = module("test_overlay", HERE / "overlay.py")
        result["sources"] = {
            n: sha(HERE / n) for n in ("protocol.md", "fixture.cpp", "overlay.py", "run.py")
        }
        result["reused"] = ORIGINAL
        private = out / "private-c291"
        src = old.extract(a.backend.resolve(), private)
        result.update(pin=old.PIN, tree=old.TREE, native_sources_sha256=old.canonical(src))
        overlay.patch_private(private)
        result["private_tu_sha256"] = sha(private / "src/llama-moe-stream.cpp")
        if a.source_only:
            result["status"] = "PASS_PIN_AND_PRIVATE_OVERLAY_ONLY"
            return
        if not a.scope_unit or not a.new_nvme_dir:
            raise ValueError("supply --scope-unit and --new-nvme-dir")
        obs = old.cgroup_reader(a.repo.resolve(), a.scope_unit)
        result["scope_before"] = obs()
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
            "project NVMe Btrfs",
        )
        base = (
            a.backend.parent / "c269-layer-last-use/build-c269-cuda/bin/libggml-base.so.0.15.3"
        ).resolve(strict=True)
        crypto = Path("/usr/lib64/libcrypto.so.3").resolve(strict=True)
        old.need(
            sha(base) == old.LIBS["ggml"] and sha(crypto) == old.LIBS["crypto"], "provider identity"
        )
        deadline = time.monotonic() + old.WALL
        env = dict(
            PATH="/usr/bin:/bin",
            LC_ALL="C",
            TMPDIR=str(out),
            CUDA_VISIBLE_DEVICES="",
            MALLOC_ARENA_MAX="2",
            OMP_NUM_THREADS="1",
            LD_LIBRARY_PATH=str(base.parent),
        )

        def step(argv, label):
            return old.record_command(argv, out, label, env, result["commands"], deadline, obs)

        # The compiler helper accepts only its sibling fixture.cpp. Rebind its path
        # in the imported module to this frozen test directory; never edit another source.
        old.HERE = HERE
        exe, result["binary"] = old.compile_fixture(private, "victims", base, crypto, out, step)
        step([sys.executable, "-IB", pw / "generate.py", "--new-output-dir", nvme], "generate")
        pack, goldfile = nvme / "experts.pack", nvme / "gold.json"
        identity = old.identity(pack)
        result["gold_sha256"] = sha(goldfile)
        with (out / "gold.json").open("xb") as archive_gold:
            archive_gold.write(goldfile.read_bytes())
            archive_gold.flush()
            os.fsync(archive_gold.fileno())
        old.need(sha(out / "gold.json") == result["gold_sha256"] == sha(goldfile), "archived gold")
        gold = json.loads((out / "gold.json").read_bytes())
        historical_providers = {"ggml": base, "crypto": crypto}
        before_provider = {
            label: old.identity(path) for label, path in historical_providers.items()
        }
        states = {}
        for name in CASES:
            label = "case-" + name
            raw = out / label / "raw.json"
            step([exe, name, pack, goldfile, raw], label)
            row = json.loads(raw.read_bytes())
            expected_disk = 4 if name == "off" else 1
            for label, lib in historical_providers.items():
                recorded = row["providers"][label]
                old.need(
                    Path(recorded["path"]) == lib
                    and old.identity(lib) == before_provider[label] == recorded["identity"]
                    and sha(lib) == old.LIBS[label]
                    and Path(result["binary"]["load_paths"][label]) == lib,
                    "live dladdr/stat/ELF for " + label,
                )
            alignment = row["offset_alignment"]
            old.need(
                type(alignment) is int and alignment > 0 and old.STRIDE % alignment == 0,
                "fd alignment",
            )
            extent = (3 * old.SLAB + alignment - 1) // alignment * alignment
            transfer_counts = [40, 4, expected_disk]
            returns = [40, 4, expected_disk - (name == "eio")]
            old.need(
                row["read_extent"] == extent
                and row["requested_bytes"] == [extent * k for k in transfer_counts]
                and row["returned_bytes"] == [extent * k for k in returns],
                "exact requested and returned transport per phase",
            )
            old.need(
                row["mode"] == name
                and row["status"] == "PASS_C291_T1_VICTIM_FIXTURE"
                and row["pack_sha256"] == gold["pack_sha256"]
                and row["workers"] == 4
                and row["destructor_returned"]
                and row["preads"] == [40, 4, expected_disk]
                and row["claims"] == [40, 4, 4]
                and row["sets"] == [120, 12, 9 if name == "eio" else 12],
                "native phase conservation " + name,
            )
            expected = {"off": 4, "on": 4, "eio": 3, "stale": 3, "shutdown": 0}[name]
            old.need(
                row["actual_publications_T2"] == expected
                and len(row["terminal_slots"]) == 40
                and len({s["slot"] for s in row["terminal_slots"]}) == 40
                and sum(s["resident"] for s in row["terminal_slots"]) == 36 + expected,
                "terminal publication set " + name,
            )
            for slot in row["terminal_slots"]:
                if slot["resident"]:
                    e = slot["expert"]
                    rec = 0 if e < 36 else min(5, e - 35)
                    old.need(
                        slot["role_sha256"] == gold["records"][rec]["role_sha256"],
                        "primary data gold",
                    )
            old.need(
                [x["expert"] for x in row["capture"]]
                == ([] if name == "off" else list(range(36, 40)))
                and row["bank_hits_T2"] == (0 if name == "off" else 3),
                "bank population/provenance",
            )
            result["cases"][name] = {
                "sha256": sha(raw),
                "claims": row["claims"],
                "reads": row["preads"],
                "sets": row["sets"],
                "t2_published": expected,
                "requested_bytes": row["requested_bytes"],
                "returned_bytes": row["returned_bytes"],
                "offset_alignment": alignment,
                "provider_sha256": old.LIBS,
                "t1_captured_bytes": row["bank_payload_captured_T1"],
                "peak_bank_bytes": row["peak_bank_payload_bytes"],
            }
            states[name] = old.canonical(row["terminal_slots"])
        old.need(
            states["off"] == states["on"] and old.identity(pack) == identity,
            "original state parity and file identity",
        )
        result["scope_final"] = obs()
        result["common_primary_sha256"] = states["off"]
        old.need(
            set(p.name for p in nvme.iterdir()) == {"gold.json", "experts.pack"}, "cleanup contents"
        )
        goldfile.unlink()
        pack.unlink()
        nvme.rmdir()
        result["status"] = "PASS_C291_VICTIM_BANK_FAMILY"
    except Exception as exc:
        result["reason"] = str(exc)
        raise
    finally:
        with (out / "receipt.json").open("x") as f:
            json.dump(result, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--backend", type=Path, required=True)
    p.add_argument("--new-output", type=Path, required=True)
    p.add_argument("--new-nvme-dir", type=Path)
    p.add_argument("--scope-unit")
    p.add_argument("--source-only", action="store_true")
    run(p.parse_args())

"""Run a sealed-selector replay, then four CPU-only C291 service cases in a bounded scope."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QR = HERE.parents[4]
PW = QR / "packed_worker"
SRC = "67523bc7c44d6cf1182b45008e7414d160254b62a64c1ffe142fe934ab65509e"
GEN = "3b9c94261e71e3a0aef16311670ca907343e89b5474af3bbf13899e5eadc6c5d"
PROTO = "8f938071c21f1954fa8678e52fd1549db7a9df7252f86fa1f871441aa59620ce"
PFJ = "cb13ff990afb3164bb61086e57a6caeff14187b66a1784c88e79cd3d521121bd"
SEAL = "c25153fdb39d7776088645f0f9c10ca848fe99d45f1ed2092a17663c79615845"
CAND = "19d4a2502b41eb96d84017677c2dbdf876b479c247f49134cec0af82ae48eeb8"
ARMS = ("freq_disk", "freq_bank", "lru_bank", "wrong")
S = 4_406_400
WIN = 13_221_888
OLD = run_path(str(PW / "run.py"))
sha, need = OLD["sha"], OLD["need"]


def verify(mode, raw, gold):
    freq = mode != "lru_bank"
    hits = ({36, 38, 39} if freq else {37, 38, 39}) if mode != "freq_disk" else set()
    work = sorted(raw["work"], key=lambda j: (j["phase"], j["slot"]))
    sites = [(2, 36, 4), (2, 38, 5), (2, 39, 6), (2, 44, 7), (3, 37, 8)]
    need(len(work) == 5, "one claim/publication per demand")
    for j, (phase, e, slot) in zip(work, sites, strict=True):
        expected = 38 if mode == "wrong" and e == 36 else e
        need(
            j
            == dict(
                phase=phase,
                expert=e,
                slot=slot,
                generation=2,
                sets=3,
                preads=int(e not in hits),
                bank_expert=expected if e in hits else -1,
            ),
            "per-generation source and transport",
        )
    read = [40, 4, 4 - len(hits & {36, 38, 39, 44}), int(37 not in hits)]
    need(
        raw["status"] == "COMPLETED_C291_RETAINED_DELIVERY"
        and raw["mode"] == mode
        and raw["pack_extent"] == WIN
        and raw["workers_joined"] == 4
        and raw["reads"] == read
        and raw["sets"] == [120, 12, 12, 3]
        and raw["publications"] == [40, 4, 4, 1],
        "conservation",
    )
    retained = [36, 38, 39] if freq else [37, 38, 39]
    need(
        raw["bank"]["ordered_keys"] == [[0, e] for e in retained]
        and raw["captures"] == [[36 + i, i, 1] for i in range(4)]
        and raw["bank"]["copies"] == {"CPU": 4, "CUDA0": 0},
        "selected payloads",
    )
    bad = []
    need(len(raw["terminal"]) == 40, "40 terminal bindings")
    for i, (slot, e, generation, comp) in enumerate(raw["terminal"]):
        expected = 40 + i if i < 4 else ([36, 38, 39, 44, 37][i - 4] if i < 9 else i - 4)
        need((slot, e, generation) == (i, expected, 2 if i < 9 else 1), "slot identity")
        for k in range(3):
            source = 38 if mode == "wrong" and e == 36 else e
            index = 0 if source < 36 else min(5, source - 35)
            need(comp[k] == gold["records"][index]["role_sha256"][k], "independent payload")
            if source != e:
                bad.append([slot, e, k, comp[k]])
    need(
        raw["mismatches"] == bad and len(bad) == (3 if mode == "wrong" else 0),
        "negative control or payload",
    )
    return {
        "reads": read,
        "pread_returned_bytes": [n * WIN for n in read],
        "sets": raw["sets"],
        "publications": raw["publications"],
        "acquisition_bytes": 4 * 3 * S,
        "terminal_component_mismatches": len(bad),
        "T2_deliveries_from_bank": [4 - read[2], 1 - read[3]],
    }


def run(a, r):
    repo = HERE.parents[6]
    need((repo / "research") == QR.parent, "repository layout")
    git = lambda *args: subprocess.check_output(["git", "-C", repo, *args], text=True).strip()  # noqa: E731
    need(git("rev-parse", "HEAD") == a.commit and not git("status", "--porcelain"), "clean freeze")
    need(
        sha(HERE / "protocol.md") == PROTO
        and sha(PW / "run.py") == SRC
        and sha(PW / "generate.py") == GEN,
        "frozen protocol and source authorities",
    )
    need(
        not a.new_nvme_dir.exists()
        and a.new_nvme_dir.parent.is_dir()
        and not a.new_nvme_dir.is_relative_to(a.new_output_dir)
        and not a.new_output_dir.is_relative_to(a.new_nvme_dir),
        "exclusive separate NVMe root",
    )
    mounted = json.loads(
        OLD["cmd"](
            ["findmnt", "--json", "--target", a.new_nvme_dir.parent, "--output", "FSTYPE,SOURCE"]
        )
    )["filesystems"]
    need(
        len(mounted) == 1
        and mounted[0]["fstype"] == "btrfs"
        and re.fullmatch(r"/dev/nvme\d+n\d+(?:p\d+)?(?:\[.*\])?", mounted[0]["source"]),
        "NVMe Btrfs",
    )
    obs = OLD["cgroup_reader"](repo, a.unit)
    r.update(
        commit=a.commit,
        tree=git("rev-parse", "HEAD^{tree}"),
        scope_before=obs(),
        source_sha256={
            p.name: sha(p)
            for p in HERE.iterdir()
            if p.suffix in (".py", ".h", ".cpp", ".inc", ".md")
        },
        model_launches=0,
        gpu_launches=0,
    )
    deadline = time.monotonic() + 90
    out = a.new_output_dir
    private = out / "private"
    blobs = OLD["extract"](a.backend, private)
    r["backend_pin"] = OLD["PIN"]
    r["input_blobs_sha256"] = OLD["canonical"](blobs)
    run_path(str(HERE / "overlay.py"))["install"](private)
    base = (
        a.backend.parent / "c269-layer-last-use/build-c269-cuda/bin/libggml-base.so.0.15.3"
    ).resolve(strict=True)
    crypto = Path("/usr/lib64/libcrypto.so.3").resolve(strict=True)
    need({"ggml": sha(base), "crypto": sha(crypto)} == OLD["LIBS"], "providers")
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
        return OLD["record_command"](argv, out, label, env, r["commands"], deadline, obs)

    # Keep the predecessor's compiler and DSO checks; use this fixture as its translation unit.
    build = OLD["compile_fixture"]
    build.__globals__["HERE"] = HERE
    exe, r["binary"] = build(private, "retained", base, crypto, out, step)
    on = a.session / "ON"
    pfj = on / "observer/events.pfj"
    proof = on / "before-t2.json"
    candidates = on / "before-t2-candidates.json"
    need(
        sha(pfj) == PFJ and sha(proof) == SEAL and sha(candidates) == CAND, "authenticated part 106"
    )
    sealed = json.loads(proof.read_bytes())
    selection = json.loads(candidates.read_bytes())
    need(
        sealed["candidate_file_sha256"] == CAND
        and sealed["records"] == 87736
        and sealed["prefill_calls"] == list(range(1, 10))
        and selection["capacity"] == 353,
        "prefix cut",
    )
    cmp = out / "replay" / "raw.json"
    step([exe, "replay", pfj, str(sealed["records"]), cmp], "replay")
    actual = json.loads(cmp.read_bytes())
    need(
        actual
        == {
            **selection["banks"],
            "offered_keys": selection["offered_keys"],
            "prefix_records": sealed["records"],
        },
        "both sealed policies and all offers",
    )
    r["replay"] = {
        "journal_sha256": PFJ,
        "sealed_selection_sha256": CAND,
        "prefix_sha256": sealed["sha256"],
        "records": sealed["records"],
        "offers": actual["prefill"]["offers"],
        "raw_sha256": sha(cmp),
    }
    step(
        [sys.executable, "-IB", PW / "generate.py", "--new-output-dir", a.new_nvme_dir], "synthetic"
    )
    pack = a.new_nvme_dir / "experts.pack"
    gold_file = a.new_nvme_dir / "gold.json"
    gold = json.loads(gold_file.read_bytes())
    identity = OLD["identity"](pack)
    need(sha(pack) == gold["pack_sha256"] and identity["size_bytes"] == 6 * 13_258_752, "pack gold")
    r["pack_sha256"] = gold["pack_sha256"]
    r["gold_sha256"] = sha(gold_file)
    (out / "gold.json").write_bytes(gold_file.read_bytes())
    common = None
    for mode in ARMS:
        dest = out / mode / "raw.json"
        step([exe, mode, pack, gold_file, dest], mode)
        raw = json.loads(dest.read_bytes())
        need(
            raw["providers"] == {"ggml": str(base), "crypto": str(crypto)},
            "loaded symbol providers",
        )
        r["cases"][mode] = verify(mode, raw, gold) | {"raw_sha256": sha(dest)}
        needs = (raw["ranks"], [x[:3] for x in raw["terminal"]])
        need(common is None or needs == common, "same ranks and terminal generations")
        common = needs
    need(OLD["identity"](pack) == identity and sha(pack) == gold["pack_sha256"], "unchanged pack")
    r["pack_proof_bytes"] = 2 * identity["size_bytes"]
    r["scope_after"] = obs()
    r["status"] = "PASS_CAUSAL_RETAINED_CPU_DELIVERY"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "session", "new-nvme-dir", "new-output-dir"):
        parser.add_argument("--" + name, type=lambda s: Path(s).resolve(), required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--unit", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    receipt = {"status": "FAIL_PRESERVED", "commands": {}, "cases": {}}
    started = time.monotonic()
    try:
        run(args, receipt)
    except Exception as exc:
        receipt["reason"] = f"{type(exc).__name__}: {exc}"
    receipt["elapsed_s"] = time.monotonic() - started
    with (args.new_output_dir / "receipt.json").open("x") as out:
        json.dump(receipt, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    print(receipt["status"], receipt.get("reason", ""))
    raise SystemExit(int(receipt["status"] == "FAIL_PRESERVED"))

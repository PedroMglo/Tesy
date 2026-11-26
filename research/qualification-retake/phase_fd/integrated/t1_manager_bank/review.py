"""Recheck the archived C291 experiment without loading its ELF or regenerating weights."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARCHIVE = "8457726e5c7688e3654dd11b1a0603f82413696565dc7bf2feecf8bde813dea7"
PHYSICAL = "c64685ecb982b223d4a44e48faf6c8b71ce46e7fec1265fa4348692f8d84747c"
STATIC = (
    "dbe56f6b11d3289bc512a2a7dc6df07e678bbf691e9060abfc4610ccda008652",
    "988694316b54ff1f4aa95cdc21ce58e3e3683bc84124188813ba2762ca2e6791",
    "92493e28b5f3229cb413c1347a67ddbb2ac255b2f97349596dcbcd7f7a882fb4",
)
PROVIDERS = {
    "ggml": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
    "crypto": "695648ac8dc5e6a2b70e5e72399940de0f84bf24fddb7dd18949ba40bc575c72",
}
MODES = ("off", "on", "eio", "stale", "shutdown")
SLAB = 4_406_400
PAYLOAD = 3 * SLAB
WINDOW = 13_221_888
PACK = 79_552_512


def require(ok, description):
    if not ok:
        raise ValueError(description)


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def raw(p):
    return json.loads(p.read_bytes())


def signature(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def read_sealed(root, manifest):
    require(sha(manifest) == ARCHIVE, "part-47 manifest SHA")
    m = raw(manifest)
    require(
        m["schema"] == "tesy-private-raw-archive-v1" and m["part"] == "part-47", "archive identity"
    )
    n = 0
    for name, reference in m["files"].items():
        rel = Path(name)
        require(not rel.is_absolute() and ".." not in rel.parts, "unexpected archive path")
        f = root / rel
        require(
            f.is_file()
            and not f.is_symlink()
            and f.stat().st_size == reference["bytes"]
            and sha(f) == reference["sha256"],
            "archived bytes: " + name,
        )
        n += reference["bytes"]
    require(len(m["files"]) == 171 and n == 6_698_847, "archived population")


def verify_slots(mode, slots, role_digests):
    require(len(slots) == 40, "primary pool size")
    target = (39, 36, 38, 37)
    incomplete = {"off": set(), "on": set(), "eio": {5}, "stale": {4}, "shutdown": {4, 5, 6, 7}}[
        mode
    ]
    failures = []
    for s, item in enumerate(slots):
        e = s + 40 if s < 4 else target[s - 4] if s < 8 else s - 4
        is_new_claim = mode == "stale" and s == 4
        is_resident = s not in incomplete
        require(
            item["slot"] == s
            and item["expert"] == e
            and item["generation"] == (2 if s < 8 else 1) + is_new_claim
            and item["claimed"] is is_new_claim
            and item["resident"] is is_resident,
            "slot ownership",
        )
        if is_resident:
            rec = 0 if e < 36 else min(5, e - 35)
            require(item["role_sha256"] == role_digests[rec], "published role bytes")
        else:
            require("role_sha256" not in item, "unpublished bytes cannot count as verified")
            failures.append([s, e, item["generation"], item["claimed"]])
    return failures


def verify_work(mode, data):
    bank = mode != "off"
    count = 1 if bank else 4
    require(
        data["offset_alignment"] == 4096 and data["read_extent"] == WINDOW, "direct-read alignment"
    )
    reads = [40, 4, count]
    returned = [40, 4, count - (mode == "eio")]
    require(
        data["claims"] == [40, 4, 4]
        and data["preads"] == reads
        and data["requested_bytes"] == [n * WINDOW for n in reads]
        and data["returned_bytes"] == [n * WINDOW for n in returned],
        "per-phase reads",
    )
    sets = [120, 12, 9 if mode == "eio" else 12]
    require(
        data["sets"] == sets
        and data["bank_hits_T2"] == (3 if bank else 0)
        and data["bank_payload_captured_T1"] == (4 * PAYLOAD if bank else 0)
        and data["peak_bank_payload_bytes"] == (3 * PAYLOAD if bank else 0),
        "bank and SET totals",
    )
    committed = {"off": 48, "on": 45, "eio": 44, "stale": 45, "shutdown": 44}
    require(
        data["manager_store_reads_committed"] == committed[mode]
        and data["pack_proof_bytes"] == 2 * PACK,
        "native counters and independent FD hash cost",
    )
    return {
        "claims": data["claims"],
        "preads": reads,
        "requested_bytes": data["requested_bytes"],
        "returned_bytes": data["returned_bytes"],
        "sets": sets,
        "set_bytes": [n * SLAB for n in sets],
        "captured_payload_bytes": data["bank_payload_captured_T1"],
        "bank_peak_payload_bytes": data["peak_bank_payload_bytes"],
        "bank_hits": data["bank_hits_T2"],
        "committed_disk_reads": committed[mode],
    }


def review(root, manifest):
    read_sealed(root, manifest)
    folder = root / "tesy-c291-victims-physical-20261125-r01"
    require(sha(folder / "receipt.json") == PHYSICAL, "physical root seal")
    r = raw(folder / "receipt.json")
    require(
        r["status"] == "PASS_C291_VICTIM_BANK_FAMILY" and set(r["cases"]) == set(MODES),
        "family status",
    )
    require(
        {name: sha(HERE / name) for name in r["sources"]} == r["sources"],
        "frozen measurement source",
    )
    require(
        sha(folder / "worker-victims") == r["binary"]["sha256"]
        and sha(folder / "gold.json") == r["gold_sha256"]
        and sha(folder / "private-c291/src/llama-moe-stream.cpp") == r["private_tu_sha256"],
        "fixture, data and TU",
    )
    prechecks = []
    for number, digest in enumerate(STATIC, start=1):
        f = root / f"tesy-c291-victims-lifecycle-static-20261125-r{number:02}" / "receipt.json"
        d = raw(f)
        require(
            sha(f) == digest
            and d["status"] == "PASS_PIN_AND_PRIVATE_OVERLAY_ONLY"
            and not d["cases"]
            and not d["commands"]
            and d["pin"] == r["pin"]
            and d["tree"] == r["tree"]
            and d["native_sources_sha256"] == r["native_sources_sha256"]
            and d["private_tu_sha256"] == r["private_tu_sha256"]
            and (number != 3 or d["sources"] == r["sources"]),
            "static-only receipt",
        )
        prechecks.append(
            {"sha256": digest, "fixture_sha256": d["sources"]["fixture.cpp"], "status": d["status"]}
        )
    gold = raw(folder / "gold.json")
    require(
        gold["roles"] == ["gate", "down", "up"]
        and gold["slab"] == SLAB
        and gold["window"] == WINDOW
        and gold["pack_bytes"] == PACK
        and len(gold["records"]) == 6,
        "gold geometry/order",
    )
    roles = [entry["role_sha256"] for entry in gold["records"]]
    phases = ("build-victims", "loader-victims", "generate", *("case-" + m for m in MODES))
    require(set(r["commands"]) == set(phases), "commands")
    last = None
    for phase in phases:
        cmd = r["commands"][phase]
        a, b = (datetime.fromisoformat(cmd[k]) for k in ("started_utc", "finished_utc"))
        require(
            (last is None or last <= a)
            and a < b
            and 0 < cmd["wall_s"] < 180
            and cmd["returncode"] == 0,
            "serial bounded processes",
        )
        last = b
        require(
            int((folder / phase / "maxrss.kib").read_text()) == cmd["maxrss_kib"] < 1024 * 1024,
            "process RSS",
        )
        for name, info in cmd["logs"].items():
            p = folder / phase / name
            require(p.stat().st_size == info["bytes"] and sha(p) == info["sha256"], "command proof")
        for bound in ("scope_before", "scope_after"):
            s = cmd[bound]
            require(
                s["memory.max"] == 2**30
                and s["memory.swap.max"] == s["memory.swap.current"] == 0
                and s["sole_process"]
                and 0 < s["memory.peak"] <= 2**30
                and s["cgroup_inode"] == r["scope_before"]["cgroup_inode"]
                and not any(
                    s["memory.events"][k]
                    for k in ("high", "max", "oom", "oom_kill", "oom_group_kill")
                ),
                "scope admission or memory event",
            )
    arms = {}
    for mode in MODES:
        name = "case-" + mode
        p = folder / name / "raw.json"
        data = raw(p)
        summary = r["cases"][mode]
        cmd = r["commands"][name]
        require(
            sha(p) == summary["sha256"]
            and data["status"] == "PASS_C291_T1_VICTIM_FIXTURE"
            and data["mode"] == cmd["argv"][1] == mode
            and data["workers"] == 4
            and data["destructor_returned"]
            and data["pack_sha256"] == gold["pack_sha256"],
            "arm identity",
        )
        w = verify_work(mode, data)
        bad = verify_slots(mode, data["terminal_slots"], roles)
        require(
            data["actual_publications_T2"] == summary["t2_published"] == 4 - len(bad),
            "published count",
        )
        expected = [
            {"expert": 36 + i, "generation": 1, "slot": i, "roles": roles[i + 1]} for i in range(4)
        ]
        require(
            data["capture"] == ([] if mode == "off" else expected), "T1 victim origin/generation"
        )
        require(
            summary["provider_sha256"] == PROVIDERS
            and set(data["providers"]) == set(PROVIDERS)
            and all(
                o["path"] == r["binary"]["load_paths"][key] and o["identity"]["inode"] > 0
                for key, o in data["providers"].items()
            ),
            "recorded live providers",
        )
        arms[mode] = {
            **w,
            "raw_sha256": sha(p),
            "published_T2": 4 - len(bad),
            "quarantine_slot_expert_gen_claimed": bad,
            "verified_resident_components": 3 * (40 - len(bad)),
            "state_sha256": signature(data["terminal_slots"]),
            "wall_s": cmd["wall_s"],
            "maxrss_kib": cmd["maxrss_kib"],
        }
    require(
        arms["off"]["state_sha256"] == arms["on"]["state_sha256"] == r["common_primary_sha256"],
        "control state parity",
    )
    return {
        "status": "PASS_C291_VICTIM_LIFECYCLE_OFFLINE",
        "archive_manifest_sha256": ARCHIVE,
        "archive_files": 171,
        "archive_bytes": 6_698_847,
        "family_sha256": PHYSICAL,
        "build_sha256": r["binary"]["sha256"],
        "pin": r["pin"],
        "tree": r["tree"],
        "sources": r["sources"],
        "gold_sha256": r["gold_sha256"],
        "pack_sha256": gold["pack_sha256"],
        "pack_bytes": PACK,
        "proof_read_bytes_per_child": 2 * PACK,
        "static": prechecks,
        "provider_sha256": PROVIDERS,
        "arms": arms,
        "build_wall_s": r["commands"]["build-victims"]["wall_s"],
        "sum_command_wall_s": round(sum(x["wall_s"] for x in r["commands"].values()), 6),
        "scope_peak_bytes": r["scope_final"]["memory.peak"],
        "model_forwards": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs-root", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = review(a.runs_root, a.manifest)
    except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        (a.new_output_dir / "receipt.json").write_text(
            json.dumps({"status": "FAIL_PRESERVED", "reason": str(exc)}) + "\n"
        )
        raise
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )

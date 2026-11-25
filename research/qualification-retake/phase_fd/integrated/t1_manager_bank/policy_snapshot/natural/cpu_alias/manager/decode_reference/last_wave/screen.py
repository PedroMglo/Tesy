"""Recover witnessed CPU0 slot owners after the final C270 prefill tile."""

import argparse
import json
import os
import resource
import signal
import struct
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
m = run_path(HERE.parent / "prepare.py")
pre = run_path(HERE.parent / "prestate.py")
need = m["need"]
PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
TREE = "49812e6f011a8cf0fc14a71074e5f4b120f87216"
CP = "10ee7ec18d4b7d1d44b80eca7dbc2ff2a48ccebdd83bc2c73dadc26289f6a616"
PRE = "9bc5d91831e50f4f8cacc73f5b34b02542c2c8b5010cb1e620f7ddb7d2101ec6"
PINNED = {
    "src/llama-moe-stream.cpp": "584aecb73900aa1164f00ec93126bc5b8b07c4d330d0f421641331b0c278d5a0",
    "src/llama-graph.cpp": "d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288",
}
IDS = "ffn_moe_wave_ids"
MASK = "ffn_moe_wave_mask"


def geometry(n, slots, k):
    cap = (slots - k) // 2
    need(cap >= k and n * k > slots, "single remap or geometry")
    return cap, (min(128, n * k) + cap - 1) // cap


def decode_wave(entries, ranks, cap, slots, skip):
    need(ranks and ranks[0] and cap > 0 and slots > 0, "empty ranks or pool")
    first = list(dict.fromkeys(e for token in ranks for e in token))
    n = len(ranks)
    k = len(ranks[0])
    need(
        all(
            len(token) == len(set(token)) == k and 0 <= min(token) <= max(token) < 128
            for token in ranks
        ),
        "invalid logical ranks",
    )
    expected = {e: i // cap for i, e in enumerate(first)}
    coverage = [0] * (n * k)
    last = {}
    reports = []
    for w, (ids, mask) in enumerate(entries):
        need(len(ids) == len(mask) == len(coverage), "wave payload length")
        bindings = {}
        active, parked = 0, 0
        for t, token in enumerate(ranks):
            row_slots = set()
            for rank, e in enumerate(token):
                i = t * k + rank
                s = ids[i]
                participates = expected[e] == w
                need(mask[i] == (0x3F800000 if participates else 0), "rank wave or nonbinary mask")
                if participates or not skip:
                    need(0 <= s < slots and s not in row_slots, "slot range or duplicate row slot")
                    row_slots.add(s)
                if participates:
                    need(bindings.setdefault(e, s) == s, "expert moved inside one wave")
                    coverage[i] += 1
                    active += 1
                else:
                    need(not skip or s == -1, "masked CPU sentinel")
                    parked += 1
        need(len(set(bindings.values())) == len(bindings), "simultaneous slot conflict")
        need(set(bindings) == set(first[w * cap : (w + 1) * cap]), "incomplete wave members")
        for e, s in bindings.items():
            last[s] = (e, w)
        reports.append(
            dict(
                wave=w,
                active_ranks=active,
                masked_ranks=parked,
                active_ordered_experts=first[w * cap : (w + 1) * cap],
                slot_for_ordered_expert=[bindings[e] for e in first[w * cap : (w + 1) * cap]],
            )
        )
    need(
        all(x == 1 for x in coverage) and len({e for e, w in last.values()}) == len(last),
        "uncovered rank or duplicate final owner",
    )
    return last, reports


def extract(a):
    p = m["sealed"](m["REPO"] / "results" / m["C270"] / "protocol.json", CP)
    manifest = m["sealed"](
        a.lab / "results" / m["C270"] / "raw-manifest.json", m["schema"]["REFS"]["C270"]
    )
    root = a.lab / "results" / m["C270"] / "raw"
    files = {r["path"]: r for r in manifest["files"]}
    reads = {}

    def raw(name):
        r = files[str(Path("results") / m["C270"] / "raw" / name)]
        reads[name] = r["sha256"]
        return m["read"](root / name, r["sha256"], r["size"])

    def capture(name):
        return raw("c270-r0.capture/" + name)

    mon = json.loads(raw("c270-r0.json"))
    b = a.lab / "backends/c269-layer-last-use"
    git = ["git", "-C", str(b)]
    need(
        subprocess.check_output([*git, "rev-parse", "HEAD", "HEAD^{tree}"], text=True).splitlines()
        == [PIN, TREE]
        and (p["backend_commit"], p["backend_tree"]) == (PIN, TREE)
        and mon["backend_sha"] == PIN,
        "C269 source tree",
    )
    for f, h in PINNED.items():
        need(
            m["sha"](b / f)
            == h
            == m["blob_sha"](subprocess.check_output([*git, "show", PIN + ":" + f])),
            "C269 source file",
        )
    hist_build = a.lab / "results/c236-post-c235-blocks-expert-reuse-20261004T105527Z/build"
    executable = Path(mon["command"][0])
    expected = p["file_sha256"]
    capture_cpp = executable.with_name("capture.cpp")
    need(
        m["sha"](hist_build / "capture.cpp")
        == expected[str(capture_cpp)]
        == "295e710af6efbd59944ae999911aeb94f0a7aef633895f1f3404161e56bdb0e6"
        and m["sha"](hist_build / executable.name)
        == mon["binary_sha256"]
        == expected[str(executable)]
        and mon["command"] == p["runs"][0]["command"]
        and mon["run_id"] == p["runs"][0]["id"] == "c270-r0"
        and mon["returncode"] == 0
        and mon["stop_reason"] is None
        and mon["mapped_libraries_match_ldd"] is True
        and mon["relevant_environment"] == p["common_env"] == {"TESY_CPU_WAVE_SKIP_PARKED": "1"}
        and mon["explicit_env"] == p["runs"][0]["env"] == {}
        and p["implementation_build"]["CPU_SKIP_PARKED_compile_flag"] is True
        and all(
            mon["mapped_backend_libraries_sha256"][f] == h for f, h in p["binary_libraries"].items()
        ),
        "actual C270 R0 code, closure or flag",
    )
    old = m["sealed"](a.prestate / "receipt.json", PRE)
    index = m["table"](capture("index.tsv"))
    rows = [r for r in index if r["phase"] == "prefill_final" and r["layer"] == "0"]
    (logical,) = [r for r in rows if r["name"] == "ffn_moe_topk"]
    pairs = [r for r in rows if r["name"] in (IDS, MASK)]
    cap, count = geometry(29, 40, 4)
    need(
        [r["name"] for r in pairs] == [IDS, MASK] * count
        and all(
            (r["chunk"], r["first_abs"], r["state_tokens"]) == ("5", "160", "29") for r in rows
        ),
        "complete final tile ordering",
    )
    if a.original_count:
        need(
            len(pairs) == 2 * 8,
            f"required 8 pairs, captured {len(pairs) // 2}; owners not examined",
        )
    need(
        count == 7
        and cap == 18
        and logical["type"] == "i32"
        and logical["ne"] == "4,29,1,1"
        and logical["nb"] == "4,512,14848,14848"
        and len({r["file"] for r in pairs}) == 2 * count,
        "wave geometry",
    )
    blob = capture(logical["file"])
    need(m["blob_sha"](blob) == old["last_tile"]["topk_file_sha256"], "prestate tile binding")
    ranks = pre["ranks"](blob, 29, (4, 512))
    items = []
    for left, right in zip(pairs[::2], pairs[1::2], strict=True):
        for r, ty, shape, strides in (
            (left, "i32", "4,29,1,1", "4,16,464,464"),
            (right, "f32", "1,4,29,1", "4,4,16,464"),
        ):
            need(
                (r["type"], r["ne"], r["nb"], r["bytes"]) == (ty, shape, strides, "464"),
                "declared operand layout",
            )
        items.append(
            (
                struct.unpack("<116i", capture(left["file"])),
                struct.unpack("<116I", capture(right["file"])),
            )
        )
    last, report = decode_wave(items, ranks, cap, 40, True)
    need(len(set().union(*ranks)) == old["last_tile"]["distinct"] == 55, "rank coverage")
    for r in old["ranks"]:
        if r["state_before"] == "READY":
            need(
                last.get(r["slot_before"], (None, None))[0] == r["expert"],
                "known READY contradiction",
            )
    (miss,) = [r for r in old["ranks"] if r["state_before"] == "ABSENT_RELOAD"]
    slot = miss["consumer_slot"]
    owner = last.get(slot)
    if owner:
        need(
            owner[0] not in m["IDS"] and (slot, miss["consumer_generation"]) == (14, 6),
            "previous owner or replaced generation",
        )
    return dict(
        status="IDENTIFIED_C270_SLOT14_VICTIM" if owner else "UNKNOWN_C270_SLOT14_VICTIM",
        slot=slot,
        old_expert=owner[0] if owner else None,
        previous_generation=miss["consumer_generation"] - 1 if owner else None,
        last_active_wave=owner[1] if owner else None,
        new_expert=miss["expert"],
        new_generation=miss["consumer_generation"],
        known_final_slots=len(last),
        unknown_slots=sorted(set(range(40)) - set(last)),
        last_active={str(s): dict(expert=e, wave=w) for s, (e, w) in sorted(last.items())},
        waves=report,
        clipped_parking_sentinel=-1,
        positions=29,
        ordered_ranks=116,
        prestate_receipt_sha256=PRE,
        protocol_sha256=m["sha"](HERE / "protocol.md"),
        corrected_geometry_sha256=m["sha"](HERE / "geometry.md"),
        program_sha256=m["sha"](Path(__file__)),
        sources=PINNED,
        backend_commit=PIN,
        backend_tree=TREE,
        capture_protocol_sha256=CP,
        raw_manifest_sha256=m["schema"]["REFS"]["C270"],
        inputs=reads,
        capture_cpp_sha256=expected[str(capture_cpp)],
        capture_executable_sha256=mon["binary_sha256"],
        model_launches=0,
        pack_reads=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("lab", "prestate", "new-output-dir"):
        p.add_argument("--" + n, type=Path, required=True)
    p.add_argument("--original-count", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    provenance = {}
    try:
        repo = ["git", "-C", str(m["REPO"])]
        need(not subprocess.check_output([*repo, "status", "--porcelain"]), "dirty program tree")
        commit, tree = subprocess.check_output(
            [*repo, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
        ).splitlines()
        provenance = dict(commit=commit, tree=tree, original_count=a.original_count)
        signal.alarm(60)
        resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
        out = extract(a)
    except Exception as exc:
        out = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}", model_launches=0)
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump({**provenance, **out}, f, sort_keys=True, indent=2)
        f.write("\n")
    print(out["status"], out.get("reason", ""))
    return int(out["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

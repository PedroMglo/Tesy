"""Reopen the sealed native and client observations without retaining prompts."""

import json
import subprocess
from collections import Counter
from decimal import Decimal
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
BANK = HERE.parent / "cpu_wave/frame_lease/group_service/shared_owner/renewal"
Q = run_path(BANK / "queue.py")
E, F, V, L, need, sha = (Q[k] for k in ("E", "F", "V", "L", "need", "sha"))
SRC = F["SRC"]
METHOD = "92aca31d5a2f98c583dac66cc3d61cccb367b2b9adb81f4008c07aef156b4f7e"
QUEUE = "907d272467d1f8ac2fb2d11ccb8553f5681dba6d1835fe78ce3f72a29188ef39"
ENTRY = "a6208d27a2b44a7aef1c56185e320b2af647a5dd0dc5478d46282a8aa45ff730"
CODE = "c9b09af1afefe6173b17d8843d5dfb6f3d3f1d53a8ec07fd313ac1c4702f1d63"


def inputs():
    service = L["X"]["ORIGINAL"] / "service.json.gz"
    queue = BANK / "evidence-queue-20261128-r02/enqueues.json.gz"
    bank = BANK / "evidence-entry-20261128-r01/transactions.json.gz"
    need(sha(HERE / "protocol.md") == METHOD, "protocol")
    for path, expected in ((service, V["SERVICE"]), (queue, QUEUE), (bank, ENTRY)):
        need(sha(path) == expected, f"input hash {path.name}")
    first = F["unpack"](bank)
    tx, _ = V["sources"]()
    need(E["digest"](tx) == first["suffix_sha256"], "reservations")
    with TemporaryDirectory(prefix="tesy-path-bank-") as tmp:
        exe = Path(tmp) / "bank"
        subprocess.run(
            ["c++", "-std=c++20", "-O2", BANK / "check_bank.cpp", "-o", exe], check=True, timeout=30
        )
        result, hits = E["execute"](exe, first, tx)
    previous = SRC["pinned"](BANK / "evidence-entry-20261128-r01/decision.json", Q["ENTRY"])
    need(
        result["replay_sha256"] == previous["replay_sha256"]
        and len(hits) == previous["continuous_hits"],
        "two-turn native controller",
    )
    return F["unpack"](service), F["unpack"](queue), hits


def ns(seconds):
    return int(Decimal(str(seconds)) * 10**9)


def capture(archive, tag, jobs):
    name, family_hash, manifest_hash = SRC["SOURCES"][tag]
    part = archive / ("part-" + tag[1:])
    root = part / name
    rel = "observer/events.pfj" if tag == "P106" else "raw/events.pfj"
    manifest = SRC["pinned"](part / "manifest.json", manifest_hash)
    SRC["authenticate_raw"](
        root, manifest, [rel, "raw/T2-result.json", "raw/T2-request.jsonl", "receipt.json"]
    )
    files = manifest["files"]
    need(files[f"{name}/ON/{rel}"]["sha256"] == E[tag], "registered PFJ")
    family = SRC["pinned"](root / "family.json", family_hash)
    meta = SRC["pinned"](root / "ON/arm.json", family["arms"]["ON"]["sha256"])
    receipt = SRC["pinned"](root / "ON/receipt.json", meta["receipt_sha256"])
    file = root / "ON" / rel
    profile = SRC["Q"]["PROFILE"]
    if tag == "P97":
        rows, _ = profile["PFJ"]["read_journal"](file)
    else:
        cut, count = profile["metadata"](file, True)
        seal = SRC["pinned"](root / "ON/before-t2.json", meta["before_t2_sha256"])
        need((cut, seal["calls"], seal["sha256"]) == (seal["records"], 86, E["PREFIX"]), "T1 cut")
        rows = [
            r._replace(call=r.call - 86) if r.call else r
            for r in profile["iter_rows"](file, cut, count - cut)
        ]
    host = SRC["NATIVE"]["host_trace"](rows)
    waves, origins = SRC["timeline"](rows)
    calls = host["calls"]
    client = SRC["CLIENT"]["inspect"](root / "ON", receipt, calls)
    need((client["sample_number"], client["sample_call"]) == (45, 46), "client cut")
    raw = json.loads((root / "ON/raw/T2-result.json").read_bytes())
    row = receipt["rows"][1]
    need(
        (row["functional"], row["prefix"], row["cache_n"], row["prompt_n"], row["predicted_n"])
        == ("PASS", "PASS", 2044, 153, 47),
        "official task",
    )
    need(receipt["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE", "cleanup")
    receipts = dict(
        first=ns(raw["stream_metrics"]["first_final_content_chunk_s"]),
        valid=ns(raw["request_wall_s"]),
        prefill=ns(row["prefill_s"]),
        decode=int(Decimal(str(raw["timings"]["predicted_ms"])) * 10**6),
    )
    need(
        receipts["valid"] == ns(row["valid_wall_s"])
        and receipts["first"] == ns(row["first_final_s"])
        and receipts["decode"] == ns(row["decode_s"]),
        "different client/server receipts",
    )
    ids = {tuple(j[0]): i for i, j in enumerate(jobs)}
    need(
        list(map(list, (origins[tuple(j[0])] for j in jobs))) == [j[1] for j in jobs],
        "reservation origin",
    )
    begins = {SRC["origin"](r): r.ns for r in rows if r.kind == 19}
    ends = {SRC["origin"](r): r.ns for r in rows if r.kind == 20}
    spans = []
    for wave in waves:
        key = wave.site
        demanded = sorted(ids[k] for k in wave.demands if k in ids)
        spans.append(
            [
                list(key),
                wave.start,
                begins[key],
                ends[key],
                wave.end,
                demanded,
                len(wave.demands) - len(demanded),
            ]
        )
    counts = Counter(r.kind for r in rows)
    need(
        counts[21] == counts[22] == counts[18] == counts[28] == counts[26] == 0
        and counts[19] == counts[20] == len(waves) == 2987
        and counts[24] == 4
        and counts[25] == 1,
        "victim, cancel, drain or scope",
    )
    exits = sorted([r.ns, r.worker] for r in rows if r.kind == 24)
    need(
        sorted(w for _, w in exits) == list(range(4))
        and all(c["queued"] == c["claimed"] == 0 for c in calls[-1:]),
        "last return and worker exit",
    )
    return dict(
        waves=spans,
        calls=[[c["enter_ns"], c["return_ns"]] for c in calls],
        raw_counts={str(k): v for k, v in counts.items()},
        client=receipts,
        cuts=client,
        route=host["route"],
        trajectory=receipt["trajectories"][1]["sampled_ids_sha256"],
        exits=exits,
        end=next(r.ns for r in rows if r.kind == 25),
        cleanup=receipt["cleanup"],
        raw_bytes=file.stat().st_size,
        raw_sha256=E[tag],
        receipt_sha256=meta["receipt_sha256"],
        requested_ids_sha256=row["official_ids_sha256"],
    )


def code_control():
    code = SRC["pinned"](HERE.parent / "cpu_wave/code_chat/code-chat.json", CODE)
    pairs = code["comparison"]["pairs"]
    need(
        len(code["arms"]) == 6
        and len(pairs) == 4
        and all(p["t1_protected"] and p["decode_protected"] for p in pairs),
        "code controls",
    )
    return dict(
        roles=[a["role"] for a in code["arms"]],
        turns=[
            {
                k: a["turns"][1][k]
                for k in (
                    "first_final_s",
                    "valid_s",
                    "decode_tok_s",
                    "evaluated",
                    "predicted",
                    "validator",
                )
            }
            for a in code["arms"]
        ],
        comparison=code["comparison"],
        bank="NOT_RUN_RAW_REQUIRED",
        missing="Matched four-worker PFJ and T1 entry for the 61-new-ID natural code T2",
    )

"""Audit source pins, natural call metadata and the existing AR/B3 KV serialization witness."""

import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
Q = HERE.parents[3]
B = run_path(str(HERE / "boundary.py"))
KV = Q / "history_lookup/b3_numeric/kv_difference"
OLD = run_path(str(KV / "screen.py"))
need, sha = B["need"], hashlib.sha256
PIN = "c89c88b342054223e3f27a17fbfd0954803147ac"
FAMILY = "e5012e559a2403145abc6f5317bddc8b83f95f1e09b592eb83a6baa2c18980a9"
PROTO = "bc793f459fdecf7b9d625d9f22acb83bcba39b3df96062c1a1e4e10b475dd34a"
OLD_RESULT = "36847d6fc28512ecb19204edaad3f32f390f27ef8f8f2b3ee087bf147c289156"


def evaluate(backend, b3_family, natural, ids_dir):
    OLD["pinned"](HERE / "protocol.md", PROTO)
    source = dict(OLD["SOURCES"])
    source["tools/server/server-context.cpp"] = (
        "657c331a707f0faf74615d19387088070c3dbd7559328619c9ef606a4ec8cc55"
    )
    for path, expected in source.items():
        data = subprocess.check_output(["git", "-C", str(backend), "show", f"{PIN}:{path}"])
        need(sha(data).hexdigest() == expected, "changed source " + path)

    progress = json.loads(OLD["pinned"](natural / "family.json", FAMILY))
    arm = progress["arms"]["ON"]["arm"]
    audit = json.loads(
        OLD["pinned"](natural / "ON/journal-audit.json", arm["journal_audit_sha256"])
    )
    need(audit["status"] == "PASS_PACK_NATURAL_TRACE" and len(audit["calls"]) == 48, "T2 journal")
    expected = [
        [(5, 2044, 2048)],
        [(32, 2049, 2080), (32, 2081, 2112), (32, 2113, 2144), (32, 2145, 2176), (20, 2177, 2196)],
        [(1, 2197, 2197)],
    ]
    calls = [[tuple(g) for g in rec["geometry"]] for rec in audit["calls"][:3]]
    need(
        calls == expected and [r["number"] for r in audit["calls"]] == list(range(1, 49)),
        "call IDs",
    )
    official = json.loads((natural / "ON/raw/T2-input.json").read_bytes())["official_ids"]
    sampled = OLD["pinned"](ids_dir / "T2-sampled.i32", B["SAMPLES"])
    need(
        len(official) == 2197
        and B["token_hash"](official) == B["PROMPT"]
        and len(sampled) == 47 * 4,
        "historical trajectory",
    )
    need(0 <= struct.unpack_from("<i", sampled)[0] < B["VOCAB"], "first sample")
    old = json.loads(OLD["pinned"](KV / "evidence/receipt.json", OLD_RESULT))
    b3 = json.loads(OLD["pinned"](b3_family / "receipt.json", old["family_sha256"]))
    logical = {}
    for arm in ("AR", "B3"):
        child = b3_family / arm
        physical = json.loads(
            OLD["pinned"](child / "receipt.json", b3["arms"][arm]["receipt_sha256"])
        )
        name = physical["unit"]
        need(name == Path(name).name, "unit name")
        monitor = json.loads(
            OLD["pinned"](child / "raw" / (name + ".json"), physical["monitor_sha256"])
        )
        banks = OLD["layers_from_log"](
            OLD["pinned"](child / "raw" / (name + ".stderr"), monitor["output_sha256"][".stderr"])
        )
        need(tuple(map(tuple, banks)) == B["BANKS"], "layer assignment")
        logical[arm] = {}
        for filename, n in (("initial-kv.bin", 189), ("post3-kv.bin", 192)):
            identity = old["inputs"][arm][filename]
            blob = OLD["pinned"](child / "raw" / (name + ".capture") / filename, identity["sha256"])
            need(len(blob) == B["extent"](n)["kv_bytes"] == identity["bytes"], "archived extent")
            logical[arm][n] = B["decode_kv"](blob, n)
            offsets, _ = OLD["parse"](blob, n, banks)
            # Independently compare all components to the previous decoder's row offsets.
            for bank, layers in zip(("base", "swa"), banks, strict=True):
                start = 0 if bank == "base" else n - 128
                label = "global" if bank == "base" else "swa"
                for role in ("K", "V"):
                    for layer in layers:
                        h = sha()
                        for pos in range(start, n):
                            i = offsets[bank, role, layer, pos]
                            h.update(blob[i : i + 1024])
                        need(
                            h.hexdigest() == logical[arm][n][f"{label}.{role}.{layer}"],
                            "old grammar",
                        )
    changed = {
        str(n): sum(logical["AR"][n][k] != logical["B3"][n][k] for k in logical["AR"][n])
        for n in (189, 192)
    }
    need(changed["189"] == 0 and changed["192"] > 0, "prior positive/negative controls")
    return dict(
        status="PASS_SOURCE_BOUNDARY_FIXTURE_ONLY",
        natural_numeric="NOT_RUN_MODEL_REQUIRED",
        backend=PIN,
        source_sha256=source,
        protocol_sha256=PROTO,
        natural_family_sha256=FAMILY,
        natural_audit_sha256=progress["arms"]["ON"]["arm"]["journal_audit_sha256"],
        prompt_and_samples_sha256=[B["PROMPT"], B["SAMPLES"]],
        observed_first_calls=calls,
        historical_b3_family_sha256=old["family_sha256"],
        historical_kv_files=4,
        historical_group_comparisons=4 * 72,
        historical_differing_groups=changed,
        bounds={str(n): B["extent"](n) for n in (2197, 2198)},
        proposed_rows=[
            dict(call=2, tile=5, position=2196, batch_row=147, tile_row=19, compact_row=0),
            dict(call=3, tile=1, position=2197, batch_row=0, tile_row=0, compact_row=0),
        ],
        actual_mask_buffers="UNOBSERVED",
        forwards=0,
        server_launches=0,
        gguf_bytes=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("backend", "b3-family", "natural", "ids-dir", "new-output-dir"):
        p.add_argument("--" + key, required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        report = evaluate(a.backend, a.b3_family, a.natural, a.ids_dir)
    except Exception as exc:
        (a.new_output_dir / "receipt.json").write_text(
            json.dumps(dict(status="FAIL_PRESERVED", error=repr(exc))) + "\n"
        )
        raise
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n"
    )

"""Reconcile bare target logits, KV banks, public positions and resident pools."""

import re
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
IMPORT = run_path(str(HERE.parent / "import_failure.py"))
F, compare, need, sha, read = (IMPORT[k] for k in ("F", "distribution", "need", "sha", "read"))


def grade(cap, mode, target, ar, cold):
    native = read(cap / "native.json")
    # These are supplied C127 IDs. They deliberately do not follow a greedy conversation.
    need(
        native
        == dict(
            mode=mode,
            ids=[40, 738, 3566, 290],
            prefill_positions=189,
            prefill_ubatch=32,
            callback_installed=False,
            restored=mode == "RESTORE",
        ),
        "bare target configuration",
    )
    positions = re.findall(
        r"^LIVE_KV (\S+) (\d+) (-?\d+) (-?\d+)$", cap.with_suffix(".stdout").read_text(), re.M
    )
    lo = 61 if mode == "RESTORE" else 0
    need(len(positions) == 3, "three native ranges")
    ranges = {}
    layers = F["SWA"]["banks"](cap)
    for (name, count, minimum, maximum), (file, n) in zip(
        positions, (("initial.kv", 189), ("entry.kv", 189), ("post3.kv", 192)), strict=True
    ):
        first, last = int(minimum), int(maximum)
        need(name == file and int(count) == n and last == n - 1, "KV upper bound")
        if file == "post3.kv":
            need(lo <= first <= n - 128, "available SWA window")
        else:
            need(first == (0 if file == "initial.kv" else lo), "public entry minimum")
        ranges[name] = dict(public=[first, last], **F["SWA"]["contents"](cap / file, n, layers))
    known = {
        "prefill.f32": "prefill_final.logits.f32",
        **{f"step-{j}.f32": f"decode{j}.logits.f32" for j in range(4)},
    }
    diagnostic = {k: compare(cap / k, target / v) for k, v in known.items()}
    cold_cap = F["capture"](cold, read(cold / "receipt.json")["unit"], "AR")
    cold_row = compare(cap / "step-0.f32", cold_cap / "cal-decode0.logits.f32")
    kv = {name: sha(cap / name) for name in ("initial.kv", "entry.kv", "post3.kv")}
    pools = {
        name: sha(cap / name) for name in ("initial.pool", "entry.pool", "post3.pool", "final.pool")
    }
    need(
        kv["initial.kv"] == kv["entry.kv"] == sha(ar / "entry.kv")
        and pools["initial.pool"] == pools["entry.pool"] == sha(ar / "entry.pool")
        and sha(cap / "prefill.f32") == sha(ar / "prefill.f32"),
        "common input",
    )
    rows = {k: compare(cap / k, ar / k) for k in known if k.startswith("step-")}
    post_matches = kv["post3.kv"] == sha(ar / "post3.kv")
    passed = all(v["different_words"] == 0 for v in rows.values()) and post_matches
    status = "PASS_" + mode if passed else "NO_GO_" + mode + "_BITWISE"
    return dict(
        status=status,
        mode=mode,
        native=native,
        serial_rows=rows,
        post3_equals_serial=post_matches,
        kv_sha256=kv,
        pools_sha256=pools,
        ranges=ranges,
        instrumented_logits=diagnostic,
        instrumented_entry_KV=kv["entry.kv"] == sha(target / "initial-kv.bin"),
        instrumented_entry_pool=pools["entry.pool"] == sha(target / "initial-pool.bin"),
        instrumented_post3_KV=kv["post3.kv"] == sha(target / "post3-kv.bin"),
        cold_restore_row0=cold_row,
    )

"""Grade the integrated intervention against serial AR and the independent B3 from the same GPU."""

from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
M = run_path(str(HERE / "materialize.py"))
P, S, need, sha, read = (M[k] for k in ("P", "S", "need", "sha", "read"))
BASE = P["G"]["base"]
OLD = P["OLD"]
POS = (189, 190, 191)
PARENT = "72819fc1e0f5c31b688c81d554e22693b04ba29feb26d8303253bdc1ec9af777"


def cuts(mode, joined=False):
    item = P["SITE"]._replace(ops=("CONCAT",)) if joined else P["SITE"]
    return (
        list(S["GOLD"].cuts("AR" if mode == "AR" else "ON"))
        + P["G"]["probes"].sites()
        + [(25, P["NAME"], item)]
    )


def earliest(rows):
    low = min(((r["layer"], r["stage"]) for r in rows), default=None)
    return [r for r in rows if (r["layer"], r["stage"]) == low]


def diff(ar, cap, reference, candidate):
    need(set(reference) == set(candidate) and len(reference) == 1185, "coverage in both modes")
    by_file, layer25, routes = {}, {}, {}
    for layer, name, site in cuts("AR"):
        for pos in POS:
            leaf = f"{pos}.{name}.bin"
            equal = reference[leaf] == candidate[leaf]
            row = dict(
                layer=layer,
                stage=2.5 if name == P["NAME"] else site.group,
                tensor=name,
                position=pos,
            )
            if not equal or layer == 25:
                delta = S["GOLD"].diff(
                    ar / "boundary" / leaf, cap / "boundary" / leaf, pos, layer, name, site
                )
                need(
                    delta["reference_sha256"] == reference[leaf]
                    and delta["actual_sha256"] == candidate[leaf],
                    "payload digest",
                )
                row.update(
                    changed_words=delta["changed_words"],
                    words=delta["words"],
                    first=delta["first_changed_index"],
                )
                if layer == 25:
                    layer25[leaf] = row
                if not equal:
                    by_file[leaf] = row
                    if site.name == "ffn_moe_topk":
                        routes[leaf] = row
    return dict(
        equal_payloads=len(reference) - len(by_file),
        different_payloads=len(by_file),
        first_by_position={
            str(p): earliest([r for r in by_file.values() if r["position"] == p]) for p in POS
        },
        layer25=layer25,
        changed_routes=routes,
    )


def contrast(cap, which, refs, gold, pins):
    raw = OLD.require_arm(cap, "B3", gold, pins["gold_full_logits_sha256"])
    original = OLD.require_arm(refs["B3"], "B3", gold, pins["gold_full_logits_sha256"])
    serial = OLD.require_arm(refs["AR"], "AR", gold, pins["gold_full_logits_sha256"])
    check = BASE.check_arm(cap, "B3", cuts("B3", which == "ON"))
    known = {k: BASE.check_arm(v, k, cuts(k)) for k, v in refs.items()}
    f = check["files_sha256"]
    s = raw["states"]
    need(
        raw["prefix"] == original["prefix"] == serial["prefix"]
        and all(
            s[key] == original["states"][key] == serial["states"][key]
            for key in ("initial-kv.bin", "initial-pool.bin")
        ),
        "prefix and initial state",
    )
    masks = {}
    for p in POS:
        leaf = f"mask-25-{p}.f16"
        m = P["mask"](cap / leaf)
        need(
            m == P["mask"](refs["B3"] / leaf) == P["mask"](refs["AR"] / leaf), "effective row mask"
        )
        masks[str(p)] = dict(sha256=sha(cap / leaf), cells=len(m), visible=m.count(0))
    rows = {
        key: {n: OLD.logits_grade.compare_rows(OLD.row(ref, n), OLD.row(cap, n)) for n in OLD.ROWS}
        for key, ref in refs.items()
    }
    need(
        all(v["finite"] and v["n_vocab"] == 201088 for arm in rows.values() for v in arm.values()),
        "finite full logits",
    )
    for p in POS:
        for name in ("l_out-24", "attn_norm-25", "Qcur-25", "Kcur-25", "Vcur-25"):
            leaf = f"{p}.{name}.bin"
            need(
                f[leaf] == known["AR"]["files_sha256"][leaf] == known["B3"]["files_sha256"][leaf],
                "upstream intervention " + leaf,
            )
    if which == "OFF":
        need(
            raw == original
            and f == known["B3"]["files_sha256"]
            and all(v["bitwise"] for v in rows["B3"].values()),
            "neutral ablation",
        )
    delta = diff(refs["AR"], cap, known["AR"]["files_sha256"], f)
    recovered = all(delta["layer25"][f"{p}.{P['NAME']}.bin"]["changed_words"] == 0 for p in POS)
    kv = s["post3-kv.bin"] == serial["states"]["post3-kv.bin"]
    full = (
        delta["different_payloads"] == 0
        and kv
        and all(v["bitwise"] and v["same_greedy"] for v in rows["AR"].values())
    )
    status = (
        "PASS_CONTEMPORARY_OFF"
        if which == "OFF"
        else "GO_NUMERIC_AT_CAPTURED_CUTS"
        if full
        else "RESTORED_L25_ATTENTION_PARTIAL"
        if recovered
        else "NO_GO_INTEGRATED_ATTENTION_REPAIR"
    )
    return dict(
        status=status,
        vs_serial=delta,
        masks=masks,
        prefix=raw["prefix"],
        states=s,
        post3_kv_equals_serial=kv,
        full_logits=rows,
        all_covered_equal_to_serial=full,
        attention_restored=recovered,
        geometry_sha256=check["geometry_sha256"],
        checked_payloads=check["payloads"],
    )

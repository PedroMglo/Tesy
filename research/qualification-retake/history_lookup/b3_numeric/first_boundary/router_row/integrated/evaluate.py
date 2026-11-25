"""Compare integrated cuts with the independent 120B captures on their exact positions."""

import csv
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parents[1]
Q = FB.parents[2]
sys.path.insert(0, str(FB))
import grade as boundary  # noqa: E402
from schema import POSITIONS, SITES, population  # noqa: E402

HISTORICAL = "9f4f7d6006cac1befa989df086af85a193778d8e5cae26775114b2ad66532fac"
ROUTER = tuple(s for s in SITES if 6 <= s.group <= 9)
need, sha = boundary.need, boundary.sha


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def read(path):
    return json.loads(path.read_bytes())


def cuts(mode):
    need(mode in {"ON", "OFF", "AR"}, "arm")
    extra = [(i, f"{s.name}-{i}", s) for i in range(14, 36) for s in ROUTER]
    for i, name, s in list(population()) + extra:
        if mode == "ON" and s.name == "ffn_moe_logits":
            s = s._replace(ops=("CONCAT",))
        yield i, name, s


def reference(family):
    need(sha(family / "receipt.json") == HISTORICAL, "first-boundary family identity")
    r = read(family / "receipt.json")
    need(r["status"] == "DIFFERENT_AT_OBSERVED_CUT", "archived contrast")
    roots = {}
    for mode in ("AR", "B3"):
        arm_path = family / mode / "receipt.json"
        need(sha(arm_path) == r["arms"][mode]["receipt_sha256"], "archived arm hash")
        arm = read(arm_path)
        root = family / mode / "raw" / (arm["unit"] + ".capture")
        need(
            arm["status"] == "PASS_NUMERIC_ARM_" + mode
            and arm["model_launch_receipts"] == 1
            and arm["same_mode_off"] == boundary.bridge(root, mode)
            and arm["same_mode_off"]["bitwise"]
            and arm["coverage"] == boundary.check_arm(root, mode),
            "archived observation or same-mode OFF changed",
        )
        roots[mode] = root
    return roots


def later_reference(c270):
    authoritative = load(Q / "packed_nvme_manifest/capture_numeric/grade.py", "c270_gate")
    root = authoritative.reference(c270)
    nodes = {}
    with (root / "index.tsv").open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            phase, layer, name = row["phase"], int(row["layer"]), row["name"]
            if phase not in ("decode0", "decode1") or layer not in range(14, 36):
                continue
            if name not in {s.name for s in ROUTER}:
                continue
            site = next(s for s in ROUTER if s.name == name)
            position = 189 + int(phase[-1])
            key = (position, layer, name)
            p = root / row["file"]
            shape = site.dims + (1,) * (4 - len(site.dims))
            need(
                key not in nodes
                and row["state_tokens"] == "1"
                and int(row["first_abs"]) == position
                and tuple(map(int, row["ne"].split(","))) == shape
                and row["type"] == site.kind.lower()
                and p.parent == root
                and int(row["bytes"]) == p.stat().st_size == 4 * math.prod(site.dims),
                "C270 canonical row or position",
            )
            boundary.validate_words(p.read_bytes(), site)
            nodes[key] = p
    need(len(nodes) == 44 * 4, "C270 second independent reference population")
    return nodes


def diff(ref, actual, position, layer, name, site):
    left, right = ref.read_bytes(), actual.read_bytes()
    unequal, first = boundary.word_diff(left, right)
    return dict(
        position=position,
        layer=layer,
        site=site.name,
        tensor=name,
        group=site.group,
        words=len(left) // 4,
        changed_words=unequal,
        first_changed_index=first,
        reference_sha256=hashlib.sha256(left).hexdigest(),
        actual_sha256=hashlib.sha256(right).hexdigest(),
    )


def frontiers(rows):
    def first(items):
        bad = [r for r in items if r["changed_words"]]
        if not bad:
            return []
        key = min((r["layer"], r["group"]) for r in bad)
        return [r for r in bad if (r["layer"], r["group"]) == key]

    return {
        "all": first(rows),
        **{str(p): first(r for r in rows if r["position"] == p) for p in POSITIONS},
    }


def compare(capture, mode, reference_dir, later, old):
    native_mode = "AR" if mode == "AR" else "B3"
    coverage = boundary.check_arm(capture, native_mode, cuts(mode))
    need(coverage["payloads"] == 1149 and coverage["bytes"] == 19394688, "full coverage")
    rows = []
    for layer, name, site in population():
        for pos in POSITIONS:
            fn = f"{pos}.{name}.bin"
            rows.append(
                diff(
                    reference_dir / "boundary" / fn,
                    capture / "boundary" / fn,
                    pos,
                    layer,
                    name,
                    site,
                )
            )
    common_equal = all(r["changed_words"] == 0 for r in rows)
    router = [r for r in rows if 6 <= r["group"] <= 9]
    if mode != "OFF":
        for (pos, layer, name), path in sorted(later.items()):
            site = next(s for s in ROUTER if s.name == name)
            tensor = f"{name}-{layer}"
            row = diff(path, capture / "boundary" / f"{pos}.{tensor}.bin", pos, layer, tensor, site)
            router.append(row)
            rows.append(row)
    indexed = {}
    for r in router:
        key = (r["position"], r["layer"])
        indexed.setdefault(key, []).append(r)
    expected = 42 if mode == "OFF" else 86
    need(
        len(indexed) == expected and all(len(v) == 4 for v in indexed.values()),
        "router denominator",
    )
    router_equal = sum(all(r["changed_words"] == 0 for r in v) for v in indexed.values())
    final = {
        n: old.logits_grade.compare_rows(old.row(reference_dir, n), old.row(capture, n))
        for n in old.ROWS
    }
    states = {
        n: sha(reference_dir / n) == sha(capture / n)
        for n in ("initial-kv.bin", "initial-pool.bin", "post3-kv.bin")
    }
    need(states["initial-kv.bin"] and states["initial-pool.bin"], "changed initial state")
    bitwise = (
        common_equal
        and router_equal == expected
        and all(states.values())
        and all(z["bitwise"] for z in final.values())
    )
    same_mode = boundary.bridge(capture, native_mode) if mode in {"OFF", "AR"} else None
    if same_mode is not None:
        bitwise = bitwise and same_mode["bitwise"]
    return dict(
        bitwise=bitwise,
        common_equal=common_equal,
        same_mode_control=same_mode,
        common_payloads=885,
        status="EQUAL_AVAILABLE" if bitwise else "DIFFERENT_AT_OBSERVED_CUT_OR_OUTPUT",
        routers_equal=router_equal,
        routers_with_gold=expected,
        observed_router_rows=108,
        extended_missing_ar_rows=22,
        coverage=coverage,
        first=frontiers(rows),
        comparisons=rows,
        logits=final,
        states=states,
    )


def complete_third(ar, on):
    rows = []
    for layer, name, site in cuts("AR"):
        if site in ROUTER:
            for p in POSITIONS:
                fn = f"{p}.{name}.bin"
                rows.append(diff(ar / "boundary" / fn, on / "boundary" / fn, p, layer, name, site))
    need(len(rows) == 108 * 4, "all-router pairing")
    return {
        "comparisons": rows,
        "all_108": all(r["changed_words"] == 0 for r in rows),
        "first": frontiers(rows),
    }

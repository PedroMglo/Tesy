"""Compare every stored decision row and complete sequence fingerprint across the four roles."""

import array
import hashlib
import json
import math


def inspect(cap, role):
    def read(name):
        return json.loads((cap / name).read_bytes())

    native = read("native.json")
    if native != dict(
        role=role,
        reserve=3 if role == "ON" else 1,
        T1_samples=78,
        T2_samples=14,
        T1_ends=[61, 317, 573, 829, 1085, 1341, 1597, 1853, 2043],
        T2_ends=[2049, 2105],
    ):
        raise ValueError("natural boundaries")
    expected = {"native.json", "T2-start.f32"}
    visible = {"T2-start.f32"}
    for at, accept in ((1, 0), (9, 2)):
        prefix = f"{at}-"
        scheduled = 3 if role in ("R", "ON") else 1 + accept
        row = read(prefix + "decision.json")
        if (
            row["accepted"],
            row["scheduled"],
            len(row["decisions"]),
            row["kept"],
            row["next_confirmed"],
        ) != (accept, scheduled, scheduled, accept + 1, at + accept + 3):
            raise ValueError("acceptance transcript")
        expected.add(prefix + "decision.json")
        for name, n in (
            ("entry", 2104 + at),
            ("branch", 2104 + at + scheduled),
            ("keep", 2105 + at + accept),
            ("next-0", 2106 + at + accept),
            ("next-1", 2107 + at + accept),
        ):
            name = prefix + name + ".json"
            kv = read(name)
            if not (
                kv["public_max"] == n - 1
                and 0 <= kv["public_min"] <= n - 128
                and 0 < kv["bytes"] <= 96 << 20
                and len(bytes.fromhex(kv["sha256"])) == 32
            ):
                raise ValueError("complete KV range " + name)
            expected.add(name)
            visible.add(name)
        for name in [*(f"row-{j}" for j in range(scheduled)), "next-0", "next-1"]:
            name = prefix + name + ".f32"
            expected.add(name)
            visible.add(name)
        if role != "R":
            expected.update(prefix + n for n in ("entry.pool", "keep.pool", "store.json"))
            store = read(prefix + "store.json")
            if not (
                store["loads"] > 0 and store["logical_weight_bytes"] == store["loads"] * 3 * 4406400
            ):
                raise ValueError("pack counts")
    if expected != {p.name for p in cap.iterdir()}:
        raise ValueError("incomplete or extra native output")
    values = {}
    for name in sorted(visible):
        if name.endswith(".json"):
            values[name] = read(name)
        else:
            data = (cap / name).read_bytes()
            a = array.array("f")
            a.frombytes(data)
            if a.itemsize != 4 or len(a) != 201088 or not all(map(math.isfinite, a)):
                raise ValueError("finite complete row " + name)
            values[name] = hashlib.sha256(data).hexdigest()
    return dict(
        role=role,
        values=values,
        service={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(cap.glob("*.pool"))
        },
        loads={p.stem: read(p.name) for p in sorted(cap.glob("*-store.json"))},
    )


def compare(proofs, role):
    current = proofs[role]
    out = {}
    if role == "R":
        return out
    for refrole in ("R", "W", "OFF"):
        if refrole == role or refrole not in proofs:
            continue
        ref = proofs[refrole]
        common = ref["values"].keys() & current["values"].keys()
        for name in sorted(common):
            if name == "1-branch.json" and (role in ("R", "ON")) != (refrole in ("R", "ON")):
                continue
            out[refrole + "/" + name] = current["values"][name] == ref["values"][name]
        if role == "OFF" and refrole == "W":
            out["W/pools"] = current["service"] == ref["service"]
            out["W/loads"] = current["loads"] == ref["loads"]
    return out

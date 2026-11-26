"""Reconcile ordered routing, executed graph submissions and actual mapped H2D fills."""

import hashlib
import math
import re
import struct
from collections import Counter, defaultdict

ROLES = ("gate", "up", "down")
SLAB = 34816
TENSOR = 8 * SLAB
OFFSETS = ((870464, 1157184, 1443904), (2530432, 2817152, 3103872))
WEIGHTS = {
    (layer, role): offset
    for layer, spans in enumerate(OFFSETS)
    for role, offset in zip(ROLES, spans, strict=True)
}
MODES = ("CPU", "RESIDENT", "BANK9", "BANK7")
WIDTHS = {3: 32, 4: 1}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def records(text, tag):
    return [row.split()[1:] for row in text.splitlines() if row.startswith(tag + " ")]


def pids(word):
    return tuple(map(int, word.split(",")))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def weight_slice(offset, n):
    overlap = [
        (key, off) for key, off in WEIGHTS.items() if off < offset + n and offset < off + TENSOR
    ]
    if offset < 0 or not overlap:
        return None
    need(len(overlap) == 1, "crossing matrix transfer")
    key, off = overlap[0]
    need(off <= offset < offset + n <= off + TENSOR, "partly mapped weight")
    return key, offset - off


def coverage(spans, expected):
    end = 0
    for start, n in sorted(spans):
        need(start == end and n > 0, "missing, repeated or overlapping range")
        end += n
    need(end == expected, "missing transfer extent")


def nonmatrix_source(offset, size, enclosing):
    if offset >= 0:
        for (layer, role), base in WEIGHTS.items():
            if base + TENSOR <= offset < offset + size <= base + TENSOR + 8192:
                return f"mapped_bias_L{layer}_{role}"
        return "other_mapped_GGUF"
    name = enclosing["name"] if enclosing else ""
    if name and ("slot_map" in name or "inp_pos" in name or "inp_tokens" in name):
        return "ids_or_positions"
    if name and "_exps.weight" in name:
        return "unknown_staged_expert"
    if name and name != "-":
        return "other_named_host"
    return "unattributed_host"


def transfer_order(text):
    """SET IDs precede their calls, and a bank fill lies between route and consumer."""
    sets = {}
    submitted = {}
    finished = {}
    routed = {}
    bank_calls = []
    for index, line in enumerate(text.splitlines()):
        words = line.split()
        if not words:
            continue
        tag = words[0]
        if tag == "ROUTE":
            routed[int(words[1]), int(words[2].rsplit("-", 1)[1])] = index
        elif tag == "SET":
            sets[int(words[2])] = (int(words[1]), words[5])
        elif tag == "COPY":
            p, owner, kind, n, off = map(int, (words[1], words[2], words[4], words[7], words[8]))
            if not (kind == 1 and n):
                continue
            if owner:
                need(owner in sets and sets[owner][0] == p, "copy before enclosing SET")
            part = weight_slice(off, n)
            if part and owner and sets[owner][1].startswith("moe_cache."):
                (layer, role), _ = part
                need((p, layer) in routed, "bank transfer before routed site")
                bank_calls.append((index, p, layer, role))
        elif tag == "SUBMIT":
            submitted[words[1], words[2]] = index
        elif tag == "NODE":
            p, ptr = words[1], words[2]
            layer = int(words[4].rsplit("-", 1)[1])
            need(
                (p, ptr) in submitted and (int(p), layer) in routed,
                "consumer before submit or route",
            )
            if words[3] == "mm":
                role = words[4].split("_")[2].rsplit("-", 1)[0]
                finished[int(p), layer, role] = submitted[p, ptr]
    for index, phase, layer, role in bank_calls:
        need(index < finished.get((phase, layer, role), -1), "bank copy after consumer submission")


def evidence(text):
    sets = {}
    for p, idx, parent, api, name, dst, off, n, src, fo in records(text, "SET"):
        key = int(idx)
        need(key not in sets and api in ("sync", "async"), "SET identity")
        sets[key] = dict(
            phase=int(p),
            parent=int(parent),
            name=name,
            dst=int(dst),
            offset=int(off),
            size=int(n),
            src=int(src),
            file=int(fo),
        )
    copies = defaultdict(list)
    counts = Counter()
    other = Counter()
    for p, owner, api, k, dst, src, n, fo, rc in records(text, "COPY"):
        phase, owner, kind, dst, src, n, offset, rc = map(int, (p, owner, k, dst, src, n, fo, rc))
        need(api in ("sync", "async", "sync2d", "async2d") and n >= 0 and rc == 0, "CUDA transfer")
        counts[phase, kind] += n
        if kind == 4:
            raise ValueError("cudaMemcpyDefault direction unknown")
        if kind != 1 or n == 0:
            continue
        match = weight_slice(offset, n)
        if not match:
            other[phase, nonmatrix_source(offset, n, sets.get(owner))] += n
            continue
        need(owner in sets, "H2D from matrix has no enclosing SET")
        event = sets[owner]
        need(
            event["phase"] == phase
            and event["file"] >= 0
            and src - event["src"]
            == offset - event["file"]
            == dst - event["dst"] - event["offset"],
            "H2D source/destination identity",
        )
        copies[owner].append((offset - event["file"], n))
    uploads = []
    for i, s in sets.items():
        sliced = weight_slice(s["file"], s["size"])
        # CPU destinations perform ordinary memory copies, without a CUDA runtime event.
        if sliced and i in copies:
            coverage(copies[i], s["size"])
            (layer, role), offset = sliced
            uploads.append(dict(layer=layer, role=role, relative=offset, **s))
    for _p, _start, n, off, _flags, rc in records(text, "REG"):
        need(int(rc) == 0 and int(n) > 0, "failed registration")
        if int(off) >= 0:
            need(
                not any(
                    lo < int(off) + int(n) and int(off) < lo + TENSOR for lo in WEIGHTS.values()
                ),
                "registered expert data",
            )
    return (
        uploads,
        {f"{p}:{k}": v for (p, k), v in sorted(counts.items())},
        dict((f"{p}:{k}", v) for (p, k), v in sorted(other.items())),
    )


def sites(text):
    submitted = {}
    for phase, ptr, device, rc in records(text, "SUBMIT"):
        need(int(rc) == 0 and (phase, ptr) not in submitted, "graph submission")
        submitted[phase, ptr] = device
    logical = {}
    for p, name, ids in records(text, "ROUTE"):
        m = re.fullmatch(r"ffn_moe_topk-([01])", name)
        need(m and (int(p), int(m[1])) not in logical, "router identity")
        logical[int(p), int(m[1])] = pids(ids)
    nodes = {}
    for p, ptr, op, name, weight, dst, ne2, stride, wb, ob, ids in records(text, "NODE"):
        pat = r"ffn_moe_(gate|up|down)" + (r"_biased" if op == "bias" else "") + r"-([01])"
        m = re.fullmatch(pat, name)
        need(m and op in ("mm", "bias") and (p, ptr) in submitted, "executed named consumer")
        role, layer = m[1], int(m[2])
        key = (int(p), layer, op, role)
        need(
            key not in nodes
            and f"blk.{layer}.ffn_{role}_exps." + ("weight" if op == "mm" else "bias") in weight,
            "expert operand identity",
        )
        nodes[key] = dict(
            device=submitted.pop((p, ptr)),
            weight=weight,
            ptr=int(dst),
            extent=int(ne2),
            stride=int(stride),
            buffer=wb,
            output=ob,
            ids=pids(ids),
        )
    need(not submitted, "unreconciled graph submission")
    require = {(p, layer) for p in WIDTHS for layer in range(2)}
    need(set(logical) == require and len(nodes) == 24, "incomplete sites")
    for (p, layer), ids in logical.items():
        need(len(ids) == 4 * WIDTHS[p] and all(0 <= i < 8 for i in ids), "top4 width/range")
        need(
            all(len(set(ids[i : i + 4])) == 4 for i in range(0, len(ids), 4)),
            "duplicate in one top4",
        )
        for role in ROLES:
            need(
                nodes[p, layer, "bias", role]["ids"] == ids, "bias consumed different logical ranks"
            )
    return logical, nodes


def bank_step(routes, bound, fills, state, nslots):
    need(len(routes) == len(bound) and all(0 <= s < nslots for s in bound), "physical slot range")
    mapping = {}
    for expert, slot in zip(routes, bound, strict=True):
        need(mapping.setdefault(expert, slot) == slot, "unstable rank binding")
    need(len(set(mapping.values())) == len(mapping), "two experts in same slot")
    prior = dict(state)
    for key, slot in fills.items():
        need(
            key in mapping and mapping[key] == slot and key not in prior.values(),
            "spurious fill or slot",
        )
        state[slot] = key
    for key, slot in mapping.items():
        need(
            state.get(slot) == key and (key in fills or prior.get(slot) == key),
            "unproved hit or missing fill",
        )
    return len(mapping) - len(fills), len(fills)


def check_arm(mode, text, log, folder):
    need(
        mode in MODES and records(text, "STATUS") == [["COMPLETED_TINY_HYBRID_CLIENT"]],
        "native closure",
    )
    transfer_order(text)
    uploads, total_bytes, other = evidence(text)
    memset_bytes = Counter()
    for p, api, _dst, _value, n, rc in records(text, "MEMSET"):
        need(api in ("sync", "async") and int(n) >= 0 and int(rc) == 0, "CUDA memset")
        memset_bytes[p] += int(n)
    peer = records(text, "PEER")
    need(not peer, "unexpected peer transfer with a single visible device")
    if mode != "CPU":
        unknown = sum(
            other.get(f"{p}:{src}", 0)
            for p in (1, 2)
            for src in ("unattributed_host", "unknown_staged_expert")
        )
        need(unknown == 0, "INCONCLUSIVE unattributed H2D before ranks")
    route, nodes = sites(text)
    orig = {}
    for name, ptr, size, offset, typ, buf in records(text, "ORIG"):
        need(name not in orig, "duplicate original")
        orig[name] = (int(ptr), int(size), int(offset), int(typ), buf)
    need(len(orig) == 12, "missing original")
    for (layer, role), off in WEIGHTS.items():
        p, sz, fo, typ, buf = orig[f"blk.{layer}.ffn_{role}_exps.weight"]
        need(sz == TENSOR and typ == 39, "original MXFP4")
        if mode == "RESIDENT":
            need("CUDA" in buf and fo < 0, "resident placement")
        else:
            need(fo == off, "mapped expert placement")
        ptr, sz, fo, typ, buf = orig[f"blk.{layer}.ffn_{role}_exps.bias"]
        need(sz == 8192 and typ == 0, "bias type")
    startup = [u for u in uploads if u["phase"] in (1, 2)]
    for layer, role in WEIGHTS:
        parts = [u for u in startup if (u["layer"], u["role"]) == (layer, role)]
        if mode == "RESIDENT":
            dst = orig[f"blk.{layer}.ffn_{role}_exps.weight"][0]
            for u in parts:
                need(u["dst"] + u["offset"] - u["relative"] == dst, "resident SET destination")
            coverage([(u["relative"], u["size"]) for u in parts], TENSOR)
        else:
            need(not parts, "early expert upload")
    slots = {"BANK7": 7, "BANK9": 9}.get(mode, 0)
    if slots:
        need(re.search(rf"2 layer\(s\), {slots} expert slots", log), "group geometry")
    if mode == "BANK7":
        skip = re.search(r"skipped (\d+) large-batch and (\d+) ineligible layer accesses", log)
        need(skip and int(skip[2]) >= 2, "missing conservative skip in stock")
    bindings = {}
    prices = {}
    fallback = {}
    used_uploads = set()
    for phase, width in WIDTHS.items():
        hits = fills = 0
        for layer in range(2):
            ids = route[phase, layer]
            bank = bool(slots and (slots == 9 or width == 1))
            role_sets = []
            physical = None
            for role in ROLES:
                m = nodes[phase, layer, "mm", role]
                need(
                    "moe_cache." in m["weight"] if bank else "moe_cache." not in m["weight"],
                    "bank/fallback path",
                )
                if bank or mode == "RESIDENT":
                    need("CUDA" in m["device"] and "CUDA" in m["buffer"], "CUDA work placement")
                elif mode == "CPU":
                    need(m["device"] == "CPU", "CPU execution")
                current = [
                    u
                    for u in uploads
                    if u["phase"] == phase and u["layer"] == layer and u["role"] == role
                ]
                if not bank:
                    need(m["ids"] == ids and m["extent"] == 8, "original ranks/extent")
                    fallback[f"{phase}:{layer}:{role}"] = {
                        "backend": m["device"],
                        "weight_buffer": m["buffer"],
                        "mapped_H2D_bytes": sum(u["size"] for u in current),
                    }
                    continue
                need(m["extent"] == slots and m["stride"] == SLAB, "real cache view")
                if physical is None:
                    physical = m["ids"]
                need(physical == m["ids"], "different physical IDs among roles")
                produced = {}
                for u in current:
                    need(
                        "moe_cache." in u["name"]
                        and u["dst"] == m["ptr"]
                        and not (u["offset"] % SLAB or u["relative"] % SLAB or u["size"] % SLAB),
                        "bank ranges",
                    )
                    for k in range(u["size"] // SLAB):
                        key = (layer, u["relative"] // SLAB + k)
                        need(key not in produced, "duplicate fill")
                        produced[key] = u["offset"] // SLAB + k
                    used_uploads.add(id(u))
                role_sets.append(produced)
            if bank:
                need(role_sets[0] == role_sets[1] == role_sets[2], "three-role publication")
                h, f = bank_step([(layer, e) for e in ids], physical, role_sets[0], bindings, slots)
                hits += h
                fills += f
        prices["prefill" if phase == 3 else "teacher"] = dict(
            hits=hits, fills=fills, logical_uploaded_bytes=fills * 3 * SLAB
        )
        if slots and (slots == 9 or width == 1):
            label = "ubatch 9-32" if width == 32 else "ubatch <= 8"
            match = re.findall(
                re.escape(label)
                + r" hits=(\d+) gpu_fills=(\d+) cpu_serviced_unique_misses=(\d+) unique_keys=(\d+)"
                r" unique_key_hit_rate=[0-9.]+% logical_uploaded_bytes=(\d+)",
                log,
            )
            need(
                len(match) == 1
                and tuple(map(int, match[0])) == (hits, fills, 0, hits + fills, fills * 3 * SLAB),
                "stock counters",
            )
    if slots:
        need(any(v["fills"] for v in prices.values()), "unobserved cache fills")
        need(
            not any(
                u["name"].startswith("moe_cache.") and id(u) not in used_uploads for u in uploads
            ),
            "unconsumed bank fill",
        )
    outputs = {}
    for f, count in (("prefill.f32", 32 * 32), ("teacher.f32", 32)):
        data = (folder / f).read_bytes()
        need(
            len(data) == count * 4 and all(map(math.isfinite, struct.unpack(f"<{count}f", data))),
            "finite complete logits",
        )
        outputs[f] = sha(data)
    route_sha = {
        f"{p}:{layer}": sha(struct.pack(f"<{len(v)}i", *v))
        for (p, layer), v in sorted(route.items())
    }
    return dict(
        mode=mode,
        slots=slots,
        logits_sha256=outputs,
        ordered_top4_sha256=route_sha,
        reconciled=prices,
        original_or_fallback=fallback,
        consumer_ops=len(nodes),
        startup_matrix_H2D_bytes=sum(x["size"] for x in startup),
        cuda_copy_request_bytes=total_bytes,
        other_H2D_bytes=other,
        device_memset_bytes=dict(memset_bytes),
        peer_copy_events=len(peer),
        host_registration_events=len(records(text, "REG")),
    )


def compare_arms(reference_dir, reference_grade, candidate_dir, candidate_grade):
    """Reopen both full files. Compare ordered routes and logits as separate contracts."""
    routes = [g["ordered_top4_sha256"] for g in (reference_grade, candidate_grade)]
    keys = {"3:0", "3:1", "4:0", "4:1"}
    need(all(set(r) == keys for r in routes), "complete per-layer route identities")
    rows = {}
    for name, count in (("prefill.f32", 32), ("teacher.f32", 1)):
        data = []
        values = []
        for path, g in ((reference_dir, reference_grade), (candidate_dir, candidate_grade)):
            buf = (path / name).read_bytes()
            need(len(buf) == 128 * count and sha(buf) == g["logits_sha256"][name], "logit identity")
            data.append(buf)
            vals = struct.unpack(f"<{count * 32}f", buf)
            need(all(map(math.isfinite, vals)), "nonfinite logits")
            values.append(vals)
        a, b = values
        delta = [x - y for x, y in zip(a, b, strict=True)]
        words = [struct.unpack(f"<{count * 32}I", v) for v in data]
        diff = [x != y for x, y in zip(*words, strict=True)]
        argmax_unequal = tied = 0
        for i in range(0, count * 32, 32):
            left, right = a[i : i + 32], b[i : i + 32]
            ml, mr = max(left), max(right)
            tied += left.count(ml) > 1 or right.count(mr) > 1
            argmax_unequal += left.index(ml) != right.index(mr)
        rows[name] = dict(
            rows=count,
            columns=32,
            different_words=sum(diff),
            different_rows=sum(any(diff[i : i + 32]) for i in range(0, len(diff), 32)),
            different_first_argmax=argmax_unequal,
            tied_rows_either=tied,
            max_abs=max(map(abs, delta)),
            rmse=math.sqrt(sum(x * x for x in delta) / len(delta)),
            bitwise=data[0] == data[1],
        )
    return dict(
        reference=reference_grade["mode"],
        candidate=candidate_grade["mode"],
        routes_equal=routes[0] == routes[1],
        ordered_route_agreement={k: routes[0][k] == routes[1][k] for k in sorted(keys)},
        bitwise=all(r["bitwise"] for r in rows.values()),
        rows=rows,
    )

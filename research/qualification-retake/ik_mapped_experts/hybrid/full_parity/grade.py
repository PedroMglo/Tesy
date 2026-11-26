"""Reopen the C110 CUDA trajectory, including each physical matrix slot and logical bias."""

import re
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
C = run_path(str(HERE / "contrast.py"))
CAP = run_path(str(HERE.parent / "capacity/grade.py"))
TINY, CPU, need = C["TINY"], C["CPU"], C["need"]
SLOTS = {"BANK288": 288, "BANK161": 161}
ROLES = ("gate", "up", "down")
SLAB, BIAS = 4406400, 11520
REC = TINY["records"]


def startup(lines, log, plan, slots):
    tensors = CAP["tensor_plan"](plan)
    init = [
        r
        for r in lines
        if not r.startswith(("COPY ", "SET ", "MEMSET ", "PEER ", "REG "))
        or r.split()[1] in ("1", "2", "5")
    ]
    _, sent = CAP["controlled_transfers"](init, tensors)
    biases = CAP["check_bias_instances"](init, tensors, sent)
    placed = {}
    for r in lines:
        if not r.startswith("PLACE "):
            continue
        _, name, typ, nb, host, off, ptr, buffer = r.split()
        need(
            name in tensors
            and name not in placed
            and int(typ) == tensors[name][2]
            and int(nb) == tensors[name][1]
            and int(ptr) > 0
            and host in ("0", "1"),
            "placement",
        )
        if host == "1":
            need(buffer == "CPU" and int(off) == tensors[name][0], "host tensor origin")
        else:
            need(buffer == "CUDA0" and int(off) == -1, "CUDA tensor origin")
            CAP["check_device_upload"](sent[name], int(ptr), int(nb), name)
        if name in biases:
            need((int(off), int(ptr), buffer) == biases[name][int(host)], "bias census drift")
        placed[name] = (buffer, int(ptr))
    need(set(placed) == set(tensors), "incomplete model census")
    mats = {f"blk.{layer}.ffn_{r}_exps.weight": (layer, r) for layer in range(36) for r in ROLES}
    need(
        all(placed[n][0] == "CPU" and tensors[n][1:] == (SLAB * 128, 39) for n in mats)
        and placed["token_embd.weight"][0] == "CPU"
        and all(placed[n][0] == "CUDA0" for n in ("output.weight", "output_norm.weight")),
        "weight placements",
    )
    need(
        re.findall(r"(\d+) layer\(s\), (\d+) expert slots", log) == [("36", str(slots))]
        and re.findall(r"active MoE cache policy: (\w+)", log) == ["classlru"]
        and "CPU-share bank rows" not in log,
        "eligible bank",
    )
    return tensors, biases, mats


def origin_for_bias(ptr, experts, host, device, writes):
    """Find the last observed write covering each byte of the selected bias slices."""
    if ptr == device:
        return "resident_cuda_instance"
    if ptr == host:
        return "mapped_host_instance"
    for e in experts:
        bounds = [(ptr + e * BIAS, ptr + (e + 1) * BIAS)]
        for dst, n, src in reversed(writes):
            if not bounds:
                break
            remain = []
            for a, b in bounds:
                lo, hi = max(a, dst), min(b, dst + n)
                if lo >= hi:
                    remain.append((a, b))
                    continue
                need(src is not None and src - dst == host - ptr, "unproved effective bias source")
                if a < lo:
                    remain.append((a, lo))
                if hi < b:
                    remain.append((hi, b))
            bounds = remain
        need(not bounds, "unobserved staging copy for active bias")
    return "staged_from_mapped_duplicate"


def trajectory(lines, tensors, biases, mats, slots):
    starts = sorted((tensors[n][0], layer, role) for n, (layer, role) in mats.items())
    offsets = [s[0] for s in starts]
    sets, current, ledger = {}, None, []
    bank_addresses, submitted, views, readbacks = {}, {}, {}, {}
    coverage, fills_by_role = defaultdict(list), {}
    writes = []
    logical = physical = None
    nodes = set()
    origins = Counter()
    ranges = {}
    seen_phase = None
    last_fill_copy = {}
    bias_placement = {}
    cuda_bytes = Counter()

    def close():
        if current is None:
            return
        need(
            nodes == {(op, r) for op in ("mm", "bias") for r in ROLES}
            and logical is not None
            and physical is not None,
            "incomplete MoE consumers",
        )
        gate = fills_by_role.get("gate", {})
        need(all(fills_by_role.get(r, {}) == gate for r in ROLES), "unmatched role fill")
        phase, layer = current
        ledger.append(
            dict(
                phase="prefill" if phase == 3 else "teacher",
                layer=layer,
                logical=list(logical),
                physical=list(physical),
                fills=sorted(gate.items()),
            )
        )

    for ordinal, line in enumerate(lines):
        fields = line.split()
        if not fields or fields[0] not in (
            "ROUTE",
            "RANK_VIEW",
            "SET",
            "COPY",
            "SUBMIT",
            "NODE",
            "BIAS_READ",
            "MEMSET",
            "REG",
            "PEER",
        ):
            continue
        tag, p = fields[0], int(fields[1])
        need(tag not in ("REG", "PEER"), "registration/peer request")
        if p not in (3, 4):
            continue
        if seen_phase != p:
            writes = []
            seen_phase = p
        if tag == "RANK_VIEW":
            phase, kind, name, dtype, ne0, ne1, ne2, ne3, s0, s1, s2, s3, size = fields[1:]
            layer = int(name.rsplit("-", 1)[1])
            width = 16 if p == 3 and layer < 35 else 1
            vals = list(map(int, (dtype, ne0, ne1, ne2, ne3, s0, s1, s2, s3, size)))
            key = (p, name)
            need(
                key not in views
                and vals[:6] == [26, 4, width, 1, 1, 4]
                and vals[6] >= 16
                and vals[6] % 4 == 0
                and min(vals[7:9]) > 0
                and vals[9] == 16 + (width - 1) * vals[6],
                "rank view layout",
            )
            views[key] = kind
        elif tag == "ROUTE":
            close()
            name = fields[2]
            match = re.fullmatch(r"ffn_moe_topk-(\d+)", name)
            need(match and views.pop((p, name)) == "logical", "original router")
            current = (p, int(match[1]))
            logical = TINY["pids"](fields[3])
            physical = None
            nodes = set()
            fills_by_role = {}
            last_fill_copy = {}
        elif tag == "SET":
            _, _, idx, parent, api, name, dst, off, n, src, fo = fields
            need(idx not in sets and api in ("sync", "async"), "SET ticket")
            sets[idx] = (p, name, int(dst), int(off), int(n), int(src), int(fo))
        elif tag == "MEMSET":
            _, _, api, dst, unused, n, rc = fields
            need(int(rc) == 0 and int(n) >= 0 and api in ("sync", "async"), "CUDA memset")
            writes.append((int(dst), int(n), None))
        elif tag == "COPY":
            _, _, owner, api, kind, dst_, src_, n_, fo_, rc = fields
            k, dst, src, n, fo = map(int, (kind, dst_, src_, n_, fo_))
            need(
                k in range(4)
                and int(rc) == 0
                and n >= 0
                and api in ("async", "sync", "async2d", "sync2d"),
                "unknown/failed transfer",
            )
            cuda_bytes[p, k] += n
            if k in (1, 3):
                writes.append((dst, n, src if k == 1 else None))
            if (
                k == 1
                and n
                and owner in sets
                and sets[owner][1].startswith("moe_cache.")
                and "_exps.weight" in sets[owner][1]
            ):
                need(fo >= 0, "bank payload has no mapped origin")
            if k != 1 or fo < 0 or not n:
                continue
            i = bisect_right(offsets, fo + n - 1) - 1
            if i < 0 or fo >= offsets[i] + 128 * SLAB:
                continue
            start, layer, role = starts[i]
            need(
                fo >= start
                and fo + n <= start + 128 * SLAB
                and current == (p, layer)
                and owner in sets
                and ("mm", role) not in nodes,
                "matrix origin/order",
            )
            sp, name, addr, off, num, src0, file0 = sets[owner]
            delta = fo - file0
            need(
                sp == p
                and name.startswith("moe_cache.")
                and 0 <= delta <= num - n
                and src - src0 == dst - addr - off == delta,
                "matrix-to-bank SET/COPY origin or late fill",
            )
            if owner not in ranges:
                need(
                    (file0 - start) % SLAB == off % SLAB == num % SLAB == 0
                    and start <= file0
                    and file0 + num <= start + SLAB * 128
                    and 0 <= off < off + num <= slots * SLAB,
                    "slab bounds",
                )
                produced = fills_by_role.setdefault(role, {})
                for j in range(num // SLAB):
                    e = (file0 - start) // SLAB + j
                    need(e not in produced, "repeated fill")
                    produced[e] = off // SLAB + j
                ranges[owner] = num
                need(bank_addresses.setdefault(role, addr) == addr, "shared bank address")
            coverage[owner].append((delta, n))
            last_fill_copy[role] = ordinal
        elif tag == "SUBMIT":
            _, _, ptr, device, rc = fields
            need(
                current is not None
                and current[0] == p
                and (p, ptr) not in submitted
                and int(rc) == 0,
                "unbound consumer submission",
            )
            submitted[p, ptr] = (device, current, len(writes), ordinal)
        elif tag == "BIAS_READ":
            _, _, name, key, addr, host, off, unique, bytes_ = fields
            need((p, name) not in readbacks and key in biases, "duplicate or unknown bias readback")
            readbacks[p, name] = (key, int(addr), int(host), int(off), int(unique), int(bytes_))
        elif tag == "NODE":
            _, _, ptr, op, name, weight, addr_, ne2, stride, buf, out, ids_ = fields
            role_match = re.fullmatch(
                r"ffn_moe_(gate|up|down)" + ("_biased" if op == "bias" else "") + r"-(\d+)", name
            )
            need(op in ("mm", "bias") and role_match and (p, ptr) in submitted, "consumer identity")
            role, layer = role_match[1], int(role_match[2])
            device, site, nwrites, submit_order = submitted.pop((p, ptr))
            need(
                site == current == (p, layer)
                and (op, role) not in nodes
                and device in ("CPU", "CUDA0")
                and out == device,
                "routed consumer backend/output or stale site",
            )
            ids = TINY["pids"](ids_)
            addr = int(addr_)
            key = f"blk.{layer}.ffn_{role}_exps." + ("weight" if op == "mm" else "bias")
            need(
                key in weight and views.pop((p, name)) == ("physical" if op == "mm" else "bias"),
                "routed name/view",
            )
            if op == "mm":
                need(
                    "moe_cache." in weight
                    and int(ne2) == slots
                    and int(stride) == SLAB
                    and buf == "CUDA0"
                    and device == "CUDA0"
                    and bank_addresses.get(role) == addr
                    and last_fill_copy.get(role, -1) < submit_order,
                    "matrix consumer bank or late fill",
                )
                if physical is None:
                    physical = ids
                need(physical == ids, "different rank slots for three roles")
            else:
                read = readbacks.pop((p, name))
                host = biases[key][1][1]
                need(
                    ids == logical
                    and buf == device
                    and read
                    == (key, addr, host, tensors[key][0], len(set(ids)), len(set(ids)) * BIAS),
                    "logical bias IDs, source or selected content",
                )
                origin = origin_for_bias(addr, set(ids), host, biases[key][0][1], writes[:nwrites])
                need(
                    (device == "CPU") == (origin == "mapped_host_instance"),
                    "bias execution/source tier",
                )
                origins[origin] += 1
                bias_placement[f"{p}:{layer}:{role}"] = [device, origin]
            nodes.add((op, role))
    close()
    need(
        not views and not readbacks and not submitted and len(bank_addresses) == 3,
        "unconsumed evidence",
    )
    ptrs = sorted(bank_addresses.values())
    need(
        all(a + (slots + 1) * SLAB <= b for a, b in zip(ptrs, ptrs[1:], strict=False)),
        "overlapping bank guards",
    )
    for owner, num in ranges.items():
        TINY["coverage"](coverage[owner], num)
    return (
        ledger,
        dict(origins),
        bias_placement,
        {f"{p}:{k}": v for (p, k), v in sorted(cuda_bytes.items())},
    )


def service(ledger, log):
    counters = defaultdict(Counter)
    for row in ledger:
        fills = len(row["fills"])
        unique = len(set(row["logical"]))
        bucket = "ubatch <= 8" if len(row["logical"]) == 4 else "ubatch 9-32"
        for tag in (row["phase"], bucket):
            counters[tag].update(
                hits=unique - fills, fills=fills, logical_uploaded_bytes=fills * 3 * SLAB
            )
    for bucket in ("ubatch <= 8", "ubatch 9-32"):
        counts = counters[bucket]
        hits, fills = counts["hits"], counts["fills"]
        pattern = (
            re.escape(bucket)
            + r" hits=(\d+) gpu_fills=(\d+) cpu_serviced_unique_misses=(\d+) unique_keys=(\d+)"
            r" unique_key_hit_rate=[0-9.]+% logical_uploaded_bytes=(\d+)"
        )
        match = re.findall(pattern, log)
        need(
            len(match) == 1
            and tuple(map(int, match[0])) == (hits, fills, 0, hits + fills, fills * 3 * SLAB),
            "stock per-width counters",
        )
    return {k: dict(counters[k]) for k in ("prefill", "teacher")}


def profile(lines, slots):
    device, host = [], []
    for line in lines:
        if line.startswith("MEMORY "):
            name, dev, model, context, compute, mmproj, total, free = line[7:].split("\t")
            row = dict(
                zip(
                    ("model", "context", "compute", "mmproj", "total", "free"),
                    map(int, (model, context, compute, mmproj, total, free)),
                    strict=True,
                )
            )
            need(min(row.values()) >= 0 and dev in ("0", "1"), "memory breakdown")
            if dev == "1":
                device.append(row)
            else:
                host.append(name)
    need(
        host == ["Host"]
        and len(device) == 1
        and device[0]["model"] > 0
        and device[0]["compute"] > 0
        and device[0]["context"] >= (slots + 1) * 3 * SLAB
        and device[0]["mmproj"] == 0
        and device[0]["free"] <= device[0]["total"],
        "device budget",
    )
    return device[0]


def check_arm(mode, stdout_text, stderr_text, native_dir, plan):
    slots = SLOTS[mode]
    lines = stdout_text.splitlines()
    need(
        [s for s in lines if s.startswith("STATUS ")] == ["STATUS COMPLETED_IK_GPU_BANK_CUTS"],
        "unfinished native process",
    )
    need(
        [s for s in lines if s.startswith(("CONTEXT ", "KV_CELLS ", "KV ", "ROW "))]
        == [
            "CONTEXT 8192 1 256 32 0 0",
            "KV_CELLS 8192",
            "KV 15 16",
            "ROW 15 201088 3659 1",
            "KV 16 17",
            "ROW 16 201088 3992 1",
        ],
        "native geometry, KV or supplied cuts",
    )
    for label in ("load", "context", "prefill", "teacher", "freed"):
        m = native_dir / (label + ".maps")
        need(m.is_file() and not m.is_symlink() and m.stat().st_size > 0, "missing VMA cut")
    mmap = [list(map(int, r.split()[1:])) for r in lines if r.startswith("MAP ")]
    need(
        len(mmap) == 1
        and mmap[0][:3] == [0, CAP["INPUT"]["STAT"][2], 1]
        and len(mmap[0]) == 4
        and mmap[0][3] & 1
        and not mmap[0][3] & 0x8000,
        "file mapping",
    )
    need(
        not any(int(r.split()[3]) == 3 for r in lines if r.startswith(("MAD ", "POSIX "))),
        "unexpected prefetch",
    )
    need(
        CPU["digest"](plan.read_bytes())
        == "4c60c7ad261c4f61e85c576a08866dd71abb3d1003369bb2876ed3669f9f5730",
        "C283 plan",
    )
    tensors, biases, mats = startup(lines, stderr_text, plan, slots)
    ledger, origins, placement, traffic = trajectory(lines, tensors, biases, mats, slots)
    sites = C["bank_sites"](ledger, slots)
    prices = service(ledger, stderr_text)
    rows = {}
    for pos, top in ((15, 3659), (16, 3992)):
        f = native_dir / f"pos{pos}.f32"
        need(
            f.is_file() and not f.is_symlink() and f.stat().st_size == CPU["WIDTH"],
            "complete preserved row",
        )
        desc = CPU["describe"](f.read_bytes())
        need(
            desc["finite"] and desc["max_ties"] == 1 and desc["top5"][0] == top, "finite unique cut"
        )
        rows[f.name] = desc
    need(len(placement) == 216 and sum(origins.values()) == 216, "bias coverage")
    return dict(
        status="PASS_IK_GPU_BANK_ARM",
        mode=mode,
        slots=slots,
        group_layers=36,
        sites=len(sites),
        consumer_ops=len(placement) * 2,
        ordered_quartets=sum(len(x[0]) // 4 for x in sites.values()),
        matrix_mmap_count=len(mats),
        bias_mapped_and_uploaded_pairs=len(biases),
        expert_startup_h2d_bytes=0,
        host_registration_requests=0,
        memory=profile(lines, slots),
        rows=rows,
        logits_sha256={k: d["sha256"] for k, d in rows.items()},
        ledger=ledger,
        bias_sources=origins,
        bias_placement=placement,
        service_by_phase=prices,
        cuda_copy_request_bytes=traffic,
    )


def rows_from_grade(folder, g):
    need(g["status"] == "PASS_IK_GPU_BANK_ARM", "arm has not passed")
    return {
        p: CPU["pinned"](folder / f"pos{p}.f32", g["logits_sha256"][f"pos{p}.f32"], CPU["WIDTH"])
        for p in (15, 16)
    }


def against_references(native_dir, grade, refs):
    candidate = rows_from_grade(native_dir, grade)
    need(set(refs) == {"C110", "ik_cpu", "stock_e95426f"}, "missing independent reference")
    out = {}
    for name, rows in refs.items():
        compared = {p: C["cut"](rows[p], candidate[p]) for p in (15, 16)}
        need(all(c["unique_greedy_equal"] for c in compared.values()), "reference greedy identity")
        status = (
            "BITWISE_TWO_CUTS"
            if all(c["bitwise"] for c in compared.values())
            else "GREEDY_TWO_CUTS_ONLY"
        )
        out[name] = dict(status=status, rows=compared)
    return out


def check_pair(native288, grade288, native161, grade161):
    need((grade288["mode"], grade161["mode"]) == ("BANK288", "BANK161"), "pair order")
    a, b = rows_from_grade(native288, grade288), rows_from_grade(native161, grade161)
    rows = {p: C["cut"](a[p], b[p]) for p in a}
    placements = C["compare_placements"](grade288["ledger"], grade161["ledger"])
    status = C["numeric_decision"](rows, placements)
    bias_equal = grade288["bias_placement"] == grade161["bias_placement"]
    if not bias_equal:
        status = "INCONCLUSIVE_BANK_SIZE_PARITY"
    elif status == "PASS_PAIRED_NUMERIC_COMPONENT":
        status = "PASS_BANK_SIZE_PARITY_TWO_CUTS"
    return dict(status=status, rows=rows, placements=placements, bias_placement_equal=bias_equal)

"""Reconcile real mapped views and device allocations from a zero-forward capacity process."""

import re
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
INPUT = run_path(str(HERE / "inventory.py"))
need = INPUT["need"]


def tensor_plan(path):
    lines = path.read_text().splitlines()
    meta = lines[0].split()
    need(meta == ["MODEL", str(INPUT["ORIGINAL"]), *map(str, INPUT["STAT"])], "plan file identity")
    tensor = {}
    for row in lines[1:]:
        tag, name, *nums = row.split()
        off, length, typ, *dims = map(int, nums)
        need(tag == "T" and name not in tensor and len(dims) == 4 and min(dims) > 0, "tensor plan")
        tensor[name] = (off, length, typ)
    need(len(tensor) == 687, "687 tensors")
    return tensor


def controlled_transfers(lines, tensors):
    """Count requested H2D payload from exact mapped intervals at verified destinations."""
    by_off = sorted((off, off + n, name) for name, (off, n, _) in tensors.items())
    starts = [x[0] for x in by_off]
    sets = {}
    sent = defaultdict(list)
    totals = Counter()
    for row in lines:
        fields = row.split()
        if not fields:
            continue
        tag = fields[0]
        if tag == "REG":
            raise ValueError("host registration attempted")
        if tag == "PEER":
            raise ValueError("unexpected peer transfer")
        if tag == "MEMSET":
            phase, api, _, _, size, code = fields[1:]
            need(api in ("sync", "async") and int(code) == 0 and int(size) >= 0, "device memset")
            totals[f"{phase}:memset"] += int(size)
        if tag == "SET":
            phase, idx, parent, api, name, dst, off, n, src, file = fields[1:]
            need(api in ("sync", "async") and idx not in sets, "SET identity")
            sets[idx] = (phase, name, int(dst) + int(off), int(src), int(file), int(n))
        if tag != "COPY":
            continue
        phase, owner, api, kind, dst, src, nb, fo, rc = fields[1:]
        n = int(nb)
        off = int(fo)
        need(
            api in ("sync", "async", "sync2d", "async2d")
            and int(rc) == 0
            and n >= 0
            and kind in ("0", "1", "2", "3"),
            "unknown CUDA copy",
        )
        totals[f"{phase}:cudaMemcpyKind{kind}"] += n
        if kind != "1" or not n:
            continue
        idx = bisect_right(starts, off) - 1
        need(idx >= 0 and owner in sets, "unattributed H2D")
        lo, hi, key = by_off[idx]
        need(
            lo <= off < off + n <= hi and not key.endswith("_exps.weight"),
            "early expert H2D or mixed range",
        )
        ph, name, d0, s0, f0, num = sets[owner]
        delta = off - f0
        need(
            ph == phase
            and name == key
            and 0 <= delta <= num - n
            and int(dst) - d0 == int(src) - s0 == delta,
            "H2D/SET identity",
        )
        sent[key].append((off - lo, n, int(dst) - (off - lo)))
    return totals, sent


def check_device_upload(chunks, addr, size, name):
    end = 0
    for begin, width, base in sorted(chunks):
        need(begin == end and base == addr, "unverified/repeated device upload")
        end += width
    need(end == size, "incomplete mapped H2D of device tensor: " + name)


def check_bias_instances(lines, tensors, sent):
    pairs = defaultdict(dict)
    for row in lines:
        if not row.startswith("BIAS_INSTANCE "):
            continue
        _, name, typ, nb, host, file, address, buffer = row.split()
        need(name in tensors and name.endswith("_exps.bias"), "unknown bias instance")
        off, size, dtype = tensors[name]
        h, addr = int(host), int(address)
        need(int(typ) == dtype == 0 and int(nb) == size and addr > 0, "bias geometry")
        need(h in (0, 1) and h not in pairs[name], "duplicate bias tier")
        if h:
            need(buffer == "CPU" and int(file) == off, "bias GGUF view")
        else:
            need(buffer == "CUDA0" and int(file) == -1, "bias CUDA instance")
            check_device_upload(sent.get(name, []), addr, size, name)
        pairs[name][h] = (int(file), addr, buffer)
    names = {name for name in tensors if name.endswith("_exps.bias")}
    need(len(names) == 108 and set(pairs) == names, "bias inventory")
    for pair in pairs.values():
        need(set(pair) == {0, 1} and pair[0][1] != pair[1][1], "missing or aliased bias tier")
    return pairs


def check_arm(stdout_text, stderr_text, native_dir, plan):
    lines = stdout_text.splitlines()
    need(
        [s for s in lines if s.startswith("STATUS ")]
        == ["STATUS COMPLETED_IK_CAPACITY_ZERO_FORWARD"]
        and "UNEXPECTED_GRAPH_SUBMISSION" not in stderr_text,
        "native did not close cleanly",
    )
    need(
        [s for s in lines if s.startswith("CONTEXT ")] == ["CONTEXT 8192 1 256 32 0 0"]
        and [s for s in lines if s.startswith("KV_CELLS ")] == ["KV_CELLS 8192"],
        "geometry/empty KV",
    )
    need(
        all((native_dir / k).is_file() for k in ("load.maps", "context.maps", "freed.maps")),
        "VMA cuts missing",
    )
    need(
        re.findall(r"([0-9]+) layer\(s\), ([0-9]+) expert slots", stderr_text) == [("36", "288")]
        and re.findall(r"active MoE cache policy: (\w+)", stderr_text) == ["classlru"],
        "bank groups/slots/policy",
    )
    need("CPU-share bank rows" not in stderr_text, "CPU share")
    tensors = tensor_plan(plan)
    mmap = [list(map(int, s.split()[1:])) for s in lines if s.startswith("MAP ")]
    need(
        len(mmap) == 1
        and mmap[0][:3] == [0, INPUT["STAT"][2], 1]
        and len(mmap[0]) == 4
        and mmap[0][3] & 1
        and not mmap[0][3] & 0x8000,
        "original mapping or unexpected eager population",
    )
    need(
        not any(int(s.split()[3]) == 3 for s in lines if s.startswith(("MAD ", "POSIX "))),
        "unexpected expert prefetch",
    )
    totals, sent = controlled_transfers(lines, tensors)
    biases = check_bias_instances(lines, tensors, sent)
    seen = set()
    cpu_mats = gpu_bias = 0
    placement = Counter()
    sizes = Counter()
    instance_counts = Counter()
    instance_payloads = Counter()
    host_bias_lookups = 0
    for row in lines:
        if not row.startswith("PLACE "):
            continue
        _, name, typ, nb, host, offset, addr, buffer = row.split()
        need(name in tensors and name not in seen, "unexpected/duplicate tensor")
        seen.add(name)
        off, n, t = tensors[name]
        h = int(host)
        need(
            int(typ) == t and int(nb) == n and h in (0, 1) and int(addr) > 0, "bad tensor identity"
        )
        placement[buffer] += 1
        sizes[buffer] += n
        instance_counts[buffer] += 1
        instance_payloads[buffer] += n
        if name.endswith("_exps.weight") or name == "token_embd.weight":
            need(h == 1 and int(offset) == off, "expert/embedding lost its file view")
            cpu_mats += name.endswith("_exps.weight")
        if name in biases:
            need((int(offset), int(addr), buffer) == biases[name][h], "first bias lookup drift")
            gpu_bias += 1
            host_bias_lookups += h
            other_buffer = biases[name][1 - h][2]
            instance_counts[other_buffer] += 1
            instance_payloads[other_buffer] += n
        elif name in ("output.weight", "output_norm.weight"):
            need(h == 0 and buffer == "CUDA0" and int(offset) == -1, "output placement")
        if not h and name not in biases:
            check_device_upload(sent.get(name, []), int(addr), n, name)
    need(seen == set(tensors) and (cpu_mats, gpu_bias) == (108, 108), "expert census")
    memory = {}
    for row in lines:
        if row.startswith("MEMORY "):
            name, dev, model, context, compute, mmproj, total, free = row[7:].split("\t")
            values = list(map(int, (dev, model, context, compute, mmproj, total, free)))
            need(name not in memory and min(values) >= 0 and values[0] in (0, 1), "breakdown row")
            memory[name] = dict(
                zip(
                    ("device", "model", "context", "compute", "mmproj", "total", "free"),
                    values,
                    strict=True,
                )
            )
    devices = [v for v in memory.values() if v["device"]]
    need(len(devices) == 1 and "Host" in memory and not memory["Host"]["device"], "memory devices")
    gpu = devices[0]
    need(
        gpu["model"] > 0
        and gpu["context"] >= 289 * INPUT["TUPLE"]
        and gpu["compute"] > 0
        and gpu["mmproj"] == 0
        and 0 <= gpu["free"] <= gpu["total"],
        "capacity memory breakdown",
    )
    return dict(
        status="PASS_IK_CAPACITY_ZERO_FORWARD",
        tensors=687,
        matrix_mmap_count=cpu_mats,
        bias_cuda_count=gpu_bias,
        bias_mapped_twins=len(biases),
        first_lookup_bias_host=host_bias_lookups,
        instance_count_by_buffer=dict(instance_counts),
        instance_logical_bytes_by_buffer=dict(instance_payloads),
        requested_bytes=INPUT["BUDGET"],
        slots=288,
        group_layers=36,
        context_rows=8192,
        batch=256,
        ubatch=32,
        empty_kv=True,
        forwards=0,
        registrations=0,
        expert_H2D_request_bytes=0,
        tensor_count_by_buffer=dict(placement),
        logical_bytes_by_buffer=dict(sizes),
        copy_or_memset_request_bytes=dict(totals),
        memory_breakdown=memory,
    )

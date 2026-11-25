"""Prepare two authenticated C270 FFN tiles and the observed C292 prefetch opportunity."""

import argparse
import csv
import hashlib
import json
import math
import os
import resource
import stat
import struct
import time
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CAP = 32 << 20
WIDTH, EXPERTS, SLOTS = 2880, 128, 40
SLAB, WINDOW, STRIDE = 4406400, 13221888, 13258752
ROLES = ("gate", "down", "up")
PART23 = "d79d180a18cf6c0f0767d02307904e679c0edd4fa10c12a3256b87a398dd8002"
PART116 = "a47b843dfb51393bd91cf7edcf0f94239ff8e80ec82b6d3449560eb83a655fca"
C270 = "tesy-c270-driver-20261125-r01"
C292 = "tesy-lookahead-c292-physical-20261125-r01"
FAMILY = "e762554f1ab0372a9534da0ec857aaccf3fc82ddf4f586f2e84dca1df3a65156"
REVIEW = "fa9490aca066e4df0d44d7f457bc6732b6b6ef530aae6b80de4470ebdfda4e49"
PFJ = "cc2b79a1897f58da66018da9a2d11f204988bb0e2d456994061059ce992b5028"
DERIVED = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9"
BUNDLE = "48a9e35554d2805c04b484b2a51d2e057d1e0cd453f535ee44f7db8e3c7ab2de"
PROTOCOL = "fea738585838e46af6ededcd6d072ccb7ad71853a79557724397f7c92cfb0a7e"
OFFERS = [42, 19, 56, 113]


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(st):
    return dict(
        dev=st.st_dev,
        inode=st.st_ino,
        size_bytes=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


class Inputs:
    def __init__(self, output):
        self.out = output
        self.reads = Counter()
        self.returned = Counter()
        self.files = {}

    def charge(self, length, kind):
        need(0 < length <= CAP - sum(self.reads.values()), "preparation read budget")
        self.reads[kind] += length

    def sealed(self, path, expected, length=None):
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), "rb") as f:
            st = os.fstat(f.fileno())
            need(
                stat.S_ISREG(st.st_mode) and length in (None, st.st_size), "file size " + path.name
            )
            self.charge(st.st_size, "metadata_and_capture")
            data = f.read(st.st_size)
            self.returned["metadata_and_capture"] += len(data)
            need(len(data) == st.st_size and sha(data) == expected, "digest " + path.name)
            need(
                identity(st) == identity(os.fstat(f.fileno())) == identity(path.stat()),
                "FD changed",
            )
        return data

    def archive(self, folder, pin):
        files = json.loads(self.sealed(folder / "manifest.json", pin))["files"]

        def member(name):
            m = files[name]
            return self.sealed(folder / name, m["sha256"], m["bytes"])

        return member

    def emit(self, name, data):
        need(name == Path(name).name and name not in self.files and data, "output name")
        with (self.out / name).open("xb") as f:
            need(f.write(data) == len(data), "short output")
        self.files[name] = sha(data)


def numbers(buf, fmt):
    return [x for (x,) in struct.iter_unpack("<" + fmt, buf)]


def packed(values, fmt):
    return struct.pack(f"<{len(values)}{fmt}", *values)


def finite(buf):
    need(all(math.isfinite(v) for (v,) in struct.iter_unpack("<f", buf)), "non-finite F32")


def tensor(row, data):
    suffixes = {
        "attn_post_norm": ("x.f32", WIDTH),
        "ffn_moe_logits": ("logits.f32", 128),
        "ffn_moe_topk": ("ids.i32", 4),
        "ffn_moe_weights_softmax": ("mix.f32", 4),
        "ffn_moe_wave_ids": ("ids.i32", 4),
        "ffn_moe_wave_mask": ("mask.f32", 4),
        "ffn_moe_out": ("ffn.f32", WIDTH),
    }
    stage = row["name"]
    name, n = suffixes[stage]
    pitch = 512 if stage == "ffn_moe_topk" else 4 * n
    if stage in ("ffn_moe_weights_softmax", "ffn_moe_wave_mask"):
        shape, stride = (1, 4, 32, 1), (4, 4, 16, 512)
    else:
        shape, stride = (n, 32, 1, 1), (4, pitch, 32 * pitch, 32 * pitch)
    need(
        tuple(map(int, row["ne"].split(","))) == shape
        and tuple(map(int, row["nb"].split(","))) == stride
        and row["type"] == name[-3:]
        and int(row["bytes"]) == len(data) == 31 * pitch + 4 * n
        and (row["chunk"], row["first_abs"], row["state_tokens"]) == ("0", "0", "32"),
        "C270 tensor descriptor " + stage,
    )
    result = b"".join(data[i * pitch : i * pitch + 4 * n] for i in range(32))
    if name.endswith("f32"):
        finite(result)
    return name, result


def capture(io, member):
    ref = json.loads(member(C270 + "/receipt.json"))
    need(ref["status"] == "PASS_SELECTED_C269_BRIDGE", "historical C270")
    base = f"{C270}/raw/{C270}.capture/"
    data = member(base + "index.tsv")
    population = [
        "attn_post_norm",
        "ffn_moe_logits",
        "ffn_moe_probs",
        "ffn_moe_topk",
        "ffn_moe_weights_softmax",
        *(["ffn_moe_wave_ids", "ffn_moe_wave_mask"] * 8),
        "ffn_moe_out",
    ]
    golds = []
    for layer in (0, 1):
        rows = [
            r
            for r in csv.DictReader(data.decode().splitlines(), delimiter="\t")
            if r["phase"] == "prefill0" and r["layer"] == str(layer)
        ]
        need([r["name"] for r in rows] == population, "C270 complete ordered FFN capture")
        gold = {}
        for i, r in enumerate(rows):
            if r["name"] == "ffn_moe_probs":
                continue
            file = r["file"]
            need(file == Path(file).name, "capture member")
            name, value = tensor(r, member(base + file))
            if 5 <= i < 21:
                name = f"w{(i - 5) // 2}." + name
            need(name not in gold, "duplicate tensor")
            gold[name] = value
            io.emit(f"L{layer}.{name}", value)
        golds.append(gold)
    return golds, list(
        csv.DictReader(member(base + "byte_checks.tsv").decode().splitlines(), delimiter="\t")
    )


def rank4(word):
    need(0 <= word < 2**32, "invalid packed IDs")
    ids = word.to_bytes(4, "little")
    need(max(ids) < EXPERTS and len(set(ids)) == 4, "invalid rank quartet")
    return ids


def wave_generations(logical, physical, masks, demands):
    generations = []
    active = set()
    for e, s, bits in zip(logical, physical, masks, strict=True):
        need(-1 <= s < SLOTS and bits in (0, 0x3F800000), "mask or slot")
        if bits:
            need(e in demands and demands[e][0] == s, "active C270/PFJ slot differs")
            generations.append(demands[e][1])
            active.add(e)
        else:
            generations.append(0)
    need(active == set(demands), "incomplete active demand")
    return generations


def routes(io, data, golds, byte_checks):
    parser = run_path(str(HERE.parents[4] / "phase_fd/integrated/analyse.py"))
    header, record = parser["HEADER"], parser["RECORD"]
    magic, version, width, cap, attempted, saved, flags, reserved = header.unpack_from(data)
    need(
        (magic, version, width, cap, flags, reserved) == (b"TESYPF1\0", 1, 96, 262144, 1, 0)
        and 0 < saved == attempted <= cap
        and len(data) == 64 + width * saved,
        "PFJ seal",
    )
    slots, reservations, demands = {}, [], {}
    ranks, waves, predicted = [[], []], [[], []], []
    target_tile = None
    for fields in record.iter_unpack(memoryview(data)[64:]):
        r = parser["Row"](*fields)
        if r.kind == 5 and r.layer in (0, 1):
            p = r.layer, r.slot
            need(
                p not in slots and 0 <= r.slot < SLOTS and (r.gen, r.expert, r.a) == (0, -1, 0),
                "40 cold primaries per layer",
            )
            slots[p] = (-1, 0)
        if r.kind == 3 and r.call == 1 and (r.a, r.b, r.c) == (32, 0, 31):
            need(target_tile is None and len(slots) == 80, "first tile, complete cold state")
            target_tile = (r.call, r.tile)
        if (r.call, r.tile) != target_tile or r.layer not in (0, 1):
            continue
        layer = r.layer
        key = layer, r.slot
        if r.kind == 9:
            waves[layer].append(r.wave)
        elif r.kind == 11:
            need(slots[key] == (r.a, r.gen - 1) and 0 <= r.expert < 128, "reservation generation")
            slots[key] = (r.expert, r.gen)
            reservations.append(
                dict(layer=layer, expert=r.expert, slot=r.slot, gen=r.gen, wave=r.wave)
            )
        elif r.kind == 10:
            jobs = demands.setdefault((layer, r.wave), {})
            need(slots[key] == (r.expert, r.gen) and r.expert not in jobs, "demand binding")
            jobs[r.expert] = (r.slot, r.gen)
        elif r.kind == 27:
            need(4 * r.b == len(ranks[layer]), "official rank order")
            ranks[layer].extend(rank4(r.a))
        elif r.kind == 33:
            need(
                layer == 1 and 4 * r.b == 4 * r.c == len(predicted) and not waves[1],
                "prediction source position",
            )
            predicted.extend(rank4(r.a))
    need(target_tile is not None and all(w == list(range(8)) for w in waves), "16 remaps")
    need(
        len(predicted) == 128
        and sorted(Counter(predicted), key=lambda e: (-predicted.count(e), e))[:4] == OFFERS,
        "official 32 predictions and four offers",
    )
    io.emit("predicted.i32", packed(predicted, "i"))
    for layer, gold in enumerate(golds):
        logical = numbers(gold["ids.i32"], "i")
        need(logical == ranks[layer] and len(logical) == 128, "ordered official ranks")
        keys = [r["expert"] for r in reservations if r["layer"] == layer]
        need(
            set(logical) == set(keys) and len(keys) == len(set(keys)) == (66, 59)[layer],
            "unique reservations",
        )
        consumed = [0] * 128
        for w in range(8):
            mask = numbers(gold[f"w{w}.mask.f32"], "I")
            jobs = demands.get((layer, w), {})
            gen = wave_generations(logical, numbers(gold[f"w{w}.ids.i32"], "i"), mask, jobs)
            need(len(jobs) == max(0, min(18, len(keys) - 18 * w)), "18-expert wave geometry")
            io.emit(f"L{layer}.w{w}.gen.u64", packed(gen, "Q"))
            consumed = [k + bool(g) for k, g in zip(consumed, gen, strict=True)]
        need(consumed == [1] * 128, "each logical rank consumed once")
    checked = 0
    for row in byte_checks:
        layer = int(row["layer"])
        if row["phase"] == "prefill0" and layer in (0, 1):
            e = int(row["logical"])
            need(
                row["status"] == "EQUAL"
                and demands[layer, int(row["wave"])][e]
                == (int(row["slot"]), int(row["generation"])),
                "C270 selected byte check differs from PFJ demand",
            )
            checked += 1
    need(checked > 0, "C270 byte-check control")
    return reservations, checked


def add_parameters(io, bundle):
    index = json.loads(io.sealed(bundle / "parameters.json", BUNDLE))
    for layer in (0, 1):
        for name, role, n in (
            ("gamma", "post_attention_norm.weight", WIDTH),
            ("router", "ffn_gate_inp.weight", WIDTH * EXPERTS),
            ("bias", "ffn_gate_inp.bias", EXPERTS),
        ):
            file = f"blk.{layer}.{role}.f32"
            need(index[file]["bytes"] == n * 4, "trained parameter shape")
            data = io.sealed(bundle / "parameters" / file, index[file]["sha256"], n * 4)
            finite(data)
            io.emit(f"L{layer}.{name}.f32", data)


def add_store(io, folder, reservations):
    derived = json.loads(io.sealed(folder / "receipt.json", DERIVED))
    need(derived["status"] == "PASS_DERIVED_C290_NVME_METADATA", "derived pack metadata")
    runtime = json.loads(
        io.sealed(folder / "expert-store-runtime.json", derived["manifest_sha256"])
    )
    index = json.loads(io.sealed(folder / "integral-index.json", derived["index_sha256"]))
    lines = io.sealed(folder / "native-bases.tsv", derived["bases_sha256"]).decode().splitlines()
    bases = {}
    for line in lines:
        layer, role, base, size = map(int, line.split())
        need((layer, role) not in bases and size == SLAB, "weight bases")
        bases[layer, role] = base
    need(
        len(bases) == 108
        and len(index["experts"]) == 4608
        and index["stride"] == STRIDE
        and index["weight_window"] == WINDOW
        and index["pack_bytes"] == runtime["pack_bytes"] == STRIDE * 4608
        and index["pack_sha256_write_stream"]
        == runtime["pack_sha256_write_stream"]
        == derived["pack_sha256"]
        and runtime["pack_stat"] == derived["pack_stat"],
        "store closure",
    )
    path = Path(derived["pack_path"])
    need(path.resolve(strict=True) == path, "canonical pack path")
    bias_bytes = WIDTH * 4
    dense = {(layer, role): bytearray(EXPERTS * bias_bytes) for layer in (0, 1) for role in ROLES}
    with os.fdopen(
        os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), "rb", buffering=0
    ) as f:
        fd = f.fileno()
        st = os.fstat(fd)
        need(
            stat.S_ISREG(st.st_mode)
            and identity(st) == identity(path.stat()) == derived["pack_stat"],
            "pack FD identity",
        )
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
        for r in reservations:
            layer, expert = r["layer"], r["expert"]
            i = layer * EXPERTS + expert
            item = index["experts"][i]
            need(
                (item["layer"], item["expert"], item["tier"], item["pack_offset"])
                == (layer, expert, "CPU", i * STRIDE)
                and len(item["components"]) == 6,
                "record geometry",
            )
            r.update(pack_offset=i * STRIDE, hashes=[])
            for j, role in enumerate(ROLES):
                wt, bias = item["components"][j], item["components"][j + 3]
                need(
                    wt["name"] == f"blk.{layer}.ffn_{role}_exps.weight"
                    and wt["size_bytes"] == SLAB
                    and wt["type"] == "mxfp4"
                    and wt["packed_relative_offset"] == j * SLAB
                    and wt["source_offset"] == bases[layer, j] + expert * SLAB,
                    "weight descriptor",
                )
                r["hashes"].append(wt["sha256"])
                need(
                    bias["name"] == f"blk.{layer}.ffn_{role}_exps.bias"
                    and bias["size_bytes"] == bias_bytes
                    and bias["type"] == "f32"
                    and bias["packed_relative_offset"] == WINDOW + j * bias_bytes
                    and WINDOW + (j + 1) * bias_bytes <= STRIDE,
                    "bias-only read descriptor",
                )
                io.charge(bias_bytes, "pack_bias")
                data = os.pread(fd, bias_bytes, r["pack_offset"] + bias["packed_relative_offset"])
                io.returned["pack_bias"] += len(data)
                need(len(data) == bias_bytes and sha(data) == bias["sha256"], "bias bytes")
                finite(data)
                dense[layer, role][expert * bias_bytes : (expert + 1) * bias_bytes] = data
        need(identity(st) == identity(os.fstat(fd)) == identity(path.stat()), "pack changed")
    for (layer, role), data in dense.items():
        io.emit(f"L{layer}.{role}.bias.f32", data)
    need(io.returned["pack_bias"] == 125 * 3 * bias_bytes, "375 bias slabs")
    return derived, [[bases[layer, role] for role in range(3)] for layer in (0, 1)]


def prepare(args, io, result):
    need(sha((HERE / "protocol.md").read_bytes()) == PROTOCOL, "frozen protocol")
    p23, p116 = io.archive(args.part23, PART23), io.archive(args.part116, PART116)
    family = p116(C292 + "/receipt.json")
    review = p116("tesy-lookahead-c292-review-20261125-r01/receipt.json")
    need(
        sha(family) == FAMILY
        and sha(review) == REVIEW
        and json.loads(family)["status"] == "PASS_C292_ROUTER_LOOKAHEAD_NUMERIC"
        and json.loads(review)["family_sha256"] == FAMILY,
        "C292 closure",
    )
    golds, checks = capture(io, p23)
    journal = p116(C292 + "/overlay_on/raw/phase.pfj1")
    need(sha(journal) == PFJ, "C292 ON journal")
    reservations, checked = routes(io, journal, golds, checks)
    add_parameters(io, args.bundle)
    derived, bases = add_store(io, args.manifest_dir, reservations)
    need(io.reads == io.returned, "all input bytes returned")
    result.update(
        status="PASS_REAL_TILE_INPUT",
        pack_stat=derived["pack_stat"],
        entries=reservations,
        weight_bases=bases,
        offers=OFFERS,
        verified_c270_byte_checks=checked,
        gguf_read_bytes=0,
        weight_matrix_read_bytes=0,
        pack_bias_reads=375,
        authorities=dict(
            part23=PART23,
            part116=PART116,
            c292_family=FAMILY,
            c292_review=REVIEW,
            c292_journal=PFJ,
            trained_parameters=BUNDLE,
            derived=DERIVED,
            index=derived["index_sha256"],
            manifest=derived["manifest_sha256"],
            pack=derived["pack_sha256"],
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("part23", "part116", "manifest-dir", "bundle", "new-output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    io = Inputs(args.new_output_dir)
    start = time.monotonic()
    result = dict(
        status="FAIL_PRESERVED",
        program_sha256=sha(Path(__file__).read_bytes()),
        protocol_sha256=PROTOCOL,
    )
    try:
        prepare(args, io, result)
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result.update(
        file_sha256=io.files,
        requested_bytes=dict(io.reads),
        returned_bytes=dict(io.returned),
        elapsed_s=time.monotonic() - start,
        peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    with (args.new_output_dir / "prepare.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(result["status"], flush=True)
    return int(result["status"] != "PASS_REAL_TILE_INPUT")


if __name__ == "__main__":
    raise SystemExit(main())

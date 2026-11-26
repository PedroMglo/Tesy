"""Select the first adjacent first-tile CPU projection with an unconsumed causal offer."""

import argparse
import csv
import json
import os
import stat
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(str(HERE.parent / "prepare.py"))
JOIN = run_path(str(HERE.parents[2] / "numeric/join.py"))
FD = run_path(str(HERE.parents[5] / "phase_fd/integrated/analyse.py"))
need, sha = P["need"], P["sha"]
PROTOCOL = "2a444ffa807a1e07e52d087590ce83b05d4013b5af362a7d4b0ffc4dd66fe074"
C299 = "c299-true-routing-score-alias-repair-20261006"
C299_MANIFEST = "3b270b0d010f64ad53c3aa4e968a81a22e144ffaa785fc888b9338d788b5f240"
STAGES = [
    "attn_post_norm",
    "ffn_moe_logits",
    "ffn_moe_topk",
    "ffn_moe_weights_softmax",
    *(["ffn_moe_wave_ids", "ffn_moe_wave_mask"] * 8),
    "ffn_moe_out",
]
CAPTURE = f"{P['C270']}/raw/{P['C270']}.capture/"


def blob(data):
    return (json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def rows_tsv(data):
    return list(csv.DictReader(data.decode().splitlines(), delimiter="\t"))


def archive(io, root, pin):
    files = json.loads(io.sealed(root / "manifest.json", pin))["files"]

    def read(rel):
        entry = files[rel]
        return io.sealed(root / rel, entry["sha256"], entry["bytes"])

    return files, read


def votes(rows, occupied):
    counts = Counter(x for row in rows for x in row)
    return sorted(counts.keys() - occupied, key=lambda e: (-counts[e], e))[:4]


def offer_result(predictions, occupied, demand):
    offers = votes(predictions, occupied)
    return offers, [e for e in offers if e not in demand]


def first_candidate(candidates):
    visited = []
    for src, offers, unused, missing in candidates:
        reasons = []
        if len(offers) != 4:
            reasons.append("fewer_than_four_eligible_offers")
        if not unused:
            reasons.append("all_offers_consumed")
        if missing:
            reasons.append("missing_gold")
        visited.append(
            dict(
                source=src,
                destination=src + 1,
                offer_count=len(offers),
                unused_count=len(unused),
                missing=missing,
                reasons=reasons,
            )
        )
        if not reasons:
            return src, visited
    return None, visited


def capture_info(index, archive_files, root, layers):
    result = {}
    for layer in layers:
        rows = [
            r
            for r in index
            if r["phase"] == "prefill0" and r["layer"] == str(layer) and r["name"] in STAGES
        ]
        count = Counter(r["name"] for r in rows)
        needed = Counter(STAGES)
        missing = []
        for stage, n in needed.items():
            need(count[stage] <= n, "ambiguous extra C270 gold")
            if count[stage] != n:
                missing.append(f"{stage}:{count[stage]}/{n}")
        for r in rows:
            name = r["file"]
            need(Path(name).name == name, "gold member path")
            if CAPTURE + name not in archive_files:
                missing.append("unarchived:" + name)
            elif not (root / CAPTURE / name).is_file():
                # A file promised by this sealed archive is corruption, not an exclusion criterion.
                raise ValueError("missing sealed member: " + name)
        if not missing:
            need([r["name"] for r in rows] == STAGES, "misordered capture")
        result[layer] = (rows, missing)
    return result


def journal(data):
    header, record = FD["HEADER"], FD["RECORD"]
    magic, version, width, cap, attempted, saved, flags, reserved = header.unpack_from(data)
    need(
        (magic, version, width, cap, flags, reserved) == (b"TESYPF1\0", 1, 96, 262144, 1, 0)
        and 0 < saved == attempted <= cap
        and len(data) == 64 + saved * width,
        "sealed C292 PFJ",
    )
    rows = [FD["Row"](*r) for r in record.iter_unpack(memoryview(data)[64:])]
    verified = JOIN["audit"](rows, True)
    need(
        verified["status"].startswith("PASS") and verified["official_quartets"] == 7768,
        "C292 independent E27/33/34 audit",
    )
    return rows


def collect(events):
    state, claimed, pending, fifo = {}, set(), set(), 0
    workers = set()
    predictions, actual, demands, reserves, edges = (defaultdict(list) for _ in range(5))
    cuts = {}

    def snapshot(src, dst):
        def resident(layer):
            cells = [state[layer, s] for s in range(40)]
            return dict(
                cold=sum(gen == 0 and e == -1 for e, gen in cells),
                occupied=sum(e >= 0 for e, gen in cells),
            )

        return dict(
            source=resident(src),
            destination=resident(dst),
            queue=fifo,
            claimed=len(claimed),
            loading=len(pending),
            productive_workers_seen=len(workers),
        )

    first = None
    for r in events:
        site = (r.call, r.tile)
        if r.kind == 3 and r.call == 1 and (r.a, r.b, r.c) == (32, 0, 31):
            need(first is None and len(state) == 1440, "first tile and all pools")
            first = site
        if first is not None and r.kind == 4 and site == first:
            break
        loc = r.layer, r.slot
        key = (r.layer, r.expert, r.slot, r.gen)
        if r.kind == 5:
            need(loc not in state and (r.gen, r.expert, r.a) == (0, -1, 0), "initial primaries")
            state[loc] = (r.expert, r.gen)
        elif r.kind == 11:
            need(state[loc] == (r.a, r.gen - 1) and key not in pending, "reservation state")
            state[loc] = (r.expert, r.gen)
            pending.add(key)
            if site == first:
                reserves[r.layer].append(
                    dict(expert=r.expert, slot=r.slot, gen=r.gen, wave=r.wave, previous=r.a)
                )
        elif r.kind == 12:
            fifo += 1
        elif r.kind in (13, 14):
            fifo -= 1
            if r.kind == 13:
                need(key in pending and key not in claimed, "claim")
                claimed.add(key)
                workers.add(r.worker)
        elif r.kind == 17:
            claimed.remove(key)
            pending.remove(key)
        need(fifo >= 0 and len(claimed) <= 4, "worker and FIFO bounds")
        if site != first or first is None:
            continue
        layer = r.layer
        if r.kind == 9:
            edges[layer].append(r.wave)
        elif r.kind == 27:
            need(r.b == len(actual[layer]), "authority row order")
            actual[layer].append(list(P["rank4"](r.a)))
        elif r.kind == 10:
            need(state[loc] == (r.expert, r.gen), "demand binding")
            demands[layer, r.wave].append((r.expert, r.slot, r.gen))
        elif r.kind in (32, 35) and 0 < layer <= 24:
            need(r.a == layer - 1 and (layer, r.kind) not in cuts, "causal projection source")
            cuts[layer, r.kind] = snapshot(layer - 1, layer)
        elif r.kind == 33 and 0 < layer <= 24:
            need(r.c == r.b == len(predictions[layer]) and (layer, 32) in cuts, "prediction order")
            predictions[layer].append(list(P["rank4"](r.a)))
            if r.b == 31:
                cuts[layer, 33] = snapshot(layer - 1, layer)
                cuts[layer, "occupied"] = {state[layer, s][0] for s in range(40)} - {-1}
        elif r.kind == 23 and r.wave == 7 and 0 < layer <= 24:
            cuts[layer, 23] = snapshot(layer - 1, layer)
    need(
        first is not None and all(edges[layer] == list(range(8)) for layer in range(25)),
        "first tile geometry",
    )

    def candidate(dst):
        qs = actual[dst]
        demanded = {x for w in range(8) for x, _, _ in demands[dst, w]}
        need(
            len(predictions[dst]) == len(qs) == 32 and demanded == set(sum(qs, [])),
            "full destination",
        )
        return offer_result(predictions[dst], cuts[dst, "occupied"], demanded)

    need(candidate(1) == (P["OFFERS"], []), "CPU0 to CPU1 selector control")
    return predictions, actual, demands, reserves, cuts, candidate


def materialize(io, layer, rows, read, actual, demands, reserves, checks):
    arrays = {}
    counts = Counter()
    for row in rows:
        name, data = P["tensor"](row, read(CAPTURE + row["file"]))
        stage = row["name"]
        if stage in ("ffn_moe_wave_ids", "ffn_moe_wave_mask"):
            name = f"w{counts[stage]}." + name
            counts[stage] += 1
        arrays[name] = data
        io.emit(f"L{layer}.{name}", data)
    logical = P["numbers"](arrays["ids.i32"], "i")
    need(logical == sum(actual[layer], []), "C270/C292 official logical ranks")
    usage = [0] * 128
    by_wave = {}
    for wave in range(8):
        bindings = demands[layer, wave]
        jobs = {e: (s, g) for e, s, g in bindings}
        need(len(jobs) == len(bindings), "unique active experts")
        ids = P["numbers"](arrays[f"w{wave}.ids.i32"], "i")
        mask = P["numbers"](arrays[f"w{wave}.mask.f32"], "I")
        epochs = P["wave_generations"](logical, ids, mask, jobs)
        io.emit(f"L{layer}.w{wave}.gen.u64", P["packed"](epochs, "Q"))
        usage = [n + bool(g) for n, g in zip(usage, epochs, strict=True)]
        by_wave[wave] = jobs
    need(
        usage == [1] * 128 and {r["expert"] for r in reserves[layer]} == set(logical),
        "128 routed incidences and authoritative loads",
    )
    matching = [r for r in checks if r["phase"] == "prefill0" and int(r["layer"]) == layer]
    for r in matching:
        need(
            r["status"] == "EQUAL"
            and by_wave[int(r["wave"])][int(r["logical"])]
            == (int(r["slot"]), int(r["generation"])),
            "historical sampled byte check",
        )
    return dict(
        reservations=len(reserves[layer]),
        distinct=len(set(logical)),
        selected_byte_checks=len(matching),
        c270_source_files={r["name"] + ":" + r["file"]: r["file"] for r in rows},
    )


def parameters(io, a, src):
    bundle = json.loads(io.sealed(a.bundle / "parameters.json", P["BUNDLE"]))
    rel = f"results/{C299}/raw/c299-code153-2-estimate.native"
    meta = json.loads(io.sealed(a.c7 / "results" / C299 / "raw-manifest.json", C299_MANIFEST))
    files = {r["path"]: r for r in meta["files"]}
    refs = {}
    for layer, role, tag, n in [
        (src, "post_attention_norm.weight", "gamma", 2880),
        (src + 1, "post_attention_norm.weight", "gamma", 2880),
        (src + 1, "ffn_gate_inp.weight", "router", 2880 * 128),
        (src + 1, "ffn_gate_inp.bias", "bias", 128),
    ]:
        base = f"blk.{layer}.{role}.f32"
        path = f"{rel}/{base}"
        if layer >= 2:
            data = io.sealed(a.c7 / path, files[path]["sha256"], 4 * n)
            need(files[path]["size_bytes"] == 4 * n, "original C299 parameter bounds")
        else:
            path = "parameters/" + base
            data = io.sealed(a.bundle / path, bundle[base]["sha256"], 4 * n)
        P["finite"](data)
        out = f"L{layer}.{tag}.f32"
        io.emit(out, data)
        refs[out] = {"source": path, "sha256": sha(data)}
    return refs


def records(io, folder, src, reservations, unused):
    seal = json.loads(io.sealed(folder / "receipt.json", P["DERIVED"]))
    r = json.loads(io.sealed(folder / "expert-store-runtime.json", seal["manifest_sha256"]))
    idx = json.loads(io.sealed(folder / "integral-index.json", seal["index_sha256"]))
    bases = {}
    for line in io.sealed(folder / "native-bases.tsv", seal["bases_sha256"]).decode().splitlines():
        layer, role, base, n = map(int, line.split())
        need((layer, role) not in bases and n == P["SLAB"], "weight base")
        bases[layer, role] = base
    path = Path(seal["pack_path"])
    need(
        seal["status"] == "PASS_DERIVED_C290_NVME_METADATA"
        and path == path.resolve(strict=True)
        and idx["stride"] == P["STRIDE"]
        and idx["weight_window"] == P["WINDOW"]
        and idx["pack_sha256_write_stream"] == r["pack_sha256_write_stream"] == seal["pack_sha256"]
        and idx["pack_bytes"]
        == r["pack_bytes"]
        == seal["pack_stat"]["size_bytes"]
        == 4608 * P["STRIDE"]
        and r["pack_stat"] == seal["pack_stat"],
        "integral pack seal",
    )
    need(len(idx["experts"]) == 4608 and len(bases) == 108, "integral descriptor population")
    entries = {}
    with os.fdopen(
        os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW), "rb", buffering=0
    ) as f:
        initial = os.fstat(f.fileno())
        need(
            stat.S_ISREG(initial.st_mode) and P["identity"](initial) == seal["pack_stat"],
            "open pack FD",
        )
        for layer in (src, src + 1):
            keys = {x["expert"] for x in reservations[layer]}
            for e in sorted(keys | (set(unused) if layer == src + 1 else set())):
                ix = layer * 128 + e
                item = idx["experts"][ix]
                need(
                    (item["layer"], item["expert"], item["tier"], item["pack_offset"])
                    == (layer, e, "CPU", ix * P["STRIDE"])
                    and len(item["components"]) == 6,
                    "expert descriptor",
                )
                for j, c in enumerate(item["components"]):
                    role = j % 3
                    bias = j >= 3
                    n = 4 * 2880 if bias else P["SLAB"]
                    off = P["WINDOW"] + role * n if bias else role * n
                    need(
                        c["name"]
                        == f"blk.{layer}.ffn_{P['ROLES'][role]}_exps."
                        + ("bias" if bias else "weight")
                        and c["type"] == ("f32" if bias else "mxfp4")
                        and c["size_bytes"] == n
                        and c["packed_relative_offset"] == off
                        and off + n <= P["STRIDE"]
                        and len(bytes.fromhex(c["sha256"])) == 32,
                        "component descriptor",
                    )
                    if not bias:
                        need(
                            c["source_offset"] == bases[layer, role] + e * n, "weight registration"
                        )
                entries[f"{layer}/{e}"] = dict(
                    layer=layer,
                    expert=e,
                    authoritative=e in keys,
                    pack_offset=item["pack_offset"],
                    components=item["components"],
                )
        need(
            P["identity"](initial)
            == P["identity"](os.fstat(f.fileno()))
            == P["identity"](path.stat()),
            "pack FD changed",
        )
    return dict(
        pack_sha256=seal["pack_sha256"],
        pack_stat=seal["pack_stat"],
        pack_bytes_read=0,
        index_sha256=seal["index_sha256"],
        manifest_sha256=seal["manifest_sha256"],
        records=entries,
        weight_bases={layer: [bases[layer, r] for r in range(3)] for layer in (src, src + 1)},
    )


def run(a, io):
    need(
        sha((HERE / "protocol.md").read_bytes()) == PROTOCOL
        and sha((HERE.parent / "prepare.py").read_bytes())
        == "884dbe4ac3347fb003357647ae4bf32cb45cb4ee9e25109f5b29bb3c0219c0a8",
        "frozen contract",
    )
    files, p23 = archive(io, a.part23, P["PART23"])
    _, p116 = archive(io, a.part116, P["PART116"])
    need(
        json.loads(p23(P["C270"] + "/receipt.json"))["status"] == "PASS_SELECTED_C269_BRIDGE",
        "C270",
    )
    fam = p116(P["C292"] + "/receipt.json")
    review = p116("tesy-lookahead-c292-review-20261125-r01/receipt.json")
    need(
        sha(fam) == P["FAMILY"]
        and sha(review) == P["REVIEW"]
        and json.loads(review)["family_sha256"] == sha(fam),
        "C292 closure",
    )
    idx = rows_tsv(p23(CAPTURE + "index.tsv"))
    sources = {}
    data = p116(P["C292"] + "/overlay_on/raw/phase.pfj1")
    need(sha(data) == P["PFJ"], "C292 journal identity")
    predictions, actual, demands, reserves, cuts, choice = collect(journal(data))

    def candidates():
        for s in range(1, 24):
            sources.update(
                capture_info(
                    idx, files, a.part23, [layer for layer in (s, s + 1) if layer not in sources]
                )
            )
            offers, unused = choice(s + 1)
            yield (
                s,
                offers,
                unused,
                [f"L{layer}/{why}" for layer in (s, s + 1) for why in sources[layer][1]],
            )

    src, walk = first_candidate(candidates())
    result = dict(
        status="NO_ELIGIBLE_ADJACENT_PAIR",
        protocol_sha256=PROTOCOL,
        code_sha256=sha(Path(__file__).read_bytes()),
        visited=walk,
        searched=len(walk),
        excluded=sum(bool(r["reasons"]) for r in walk),
        authorities=dict(
            part23=P["PART23"],
            part116=P["PART116"],
            c270_index=files[CAPTURE + "index.tsv"]["sha256"],
            c292_review=P["REVIEW"],
            c292_journal=P["PFJ"],
            c292_family=P["FAMILY"],
        ),
    )
    if src is None:
        return result
    dst = src + 1
    offers, unused = choice(dst)
    checks = rows_tsv(p23(CAPTURE + "byte_checks.tsv"))
    layers = {
        layer: materialize(io, layer, sources[layer][0], p23, actual, demands, reserves, checks)
        for layer in (src, dst)
    }
    io.emit("predicted.i32", P["packed"](sum(predictions[dst], []), "i"))
    params = parameters(io, a, src)
    pack = records(io, a.manifest_dir, src, reserves, unused)
    snapshots = {str(k): cuts[dst, k] for k in (35, 32, 33, 23)}
    clean = all(cuts[dst, k][p]["cold"] == 40 for k in (35, 33) for p in ("source", "destination"))
    drained = all(
        not any(cuts[dst, k][f] for f in ("queue", "claimed", "loading")) for k in (35, 33, 23)
    )
    status = (
        "PAIR_IDENTIFIED_COLD_DRAINED"
        if clean and drained
        else "PAIR_IDENTIFIED_RECONSTRUCTION_REQUIRED"
    )
    plan = dict(
        source=src,
        destination=dst,
        offers=offers,
        unused=unused,
        layers=layers,
        parameters=params,
        protocol_sha256=PROTOCOL,
        source_seals=result["authorities"]
        | {"derived": P["DERIVED"], "bundle": P["BUNDLE"], "c299": C299_MANIFEST},
        reservations={layer: reserves[layer] for layer in (src, dst)},
        state=snapshots,
        logical_layer_map={"local_0": src, "local_1": dst},
        store=pack,
        file_sha256=dict(io.files),
    )
    io.emit("input-plan.json", blob(plan))
    result.update(
        status=status,
        source=src,
        destination=dst,
        offers=offers,
        unused=unused,
        proposed_but_no_consumer=len(unused),
        initially_cold=clean,
        observed_boundaries_drained=drained,
        state=snapshots,
        small_inputs=len(plan["file_sha256"]),
        authoritative_loads={layer: len(reserves[layer]) for layer in (src, dst)},
        gold_ffn_sha256={layer: io.files[f"L{layer}.ffn.f32"] for layer in (src, dst)},
        records_with_descriptors=len(pack["records"]),
        biases_and_weights_read_from_pack=0,
        gguf_bytes=0,
        plan_sha256=io.files["input-plan.json"],
        received_bytes=dict(io.returned),
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("part23", "part116", "c7", "manifest-dir", "bundle", "new-output-dir"):
        parser.add_argument("--" + field, type=Path, required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    try:
        receipt = run(a, P["Inputs"](a.new_output_dir))
    except Exception as exc:
        receipt = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    with (a.new_output_dir / "receipt.json").open("xb") as output:
        output.write(blob(receipt))
    print(receipt["status"], receipt.get("reason", ""))
    raise SystemExit(int(receipt["status"] == "FAIL_PRESERVED"))

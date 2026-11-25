"""Visit causal offers in prefill order and bind the first eligible pair to actual C270 gold."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OLD = run_path(str(HERE.parent / "screen.py"))
P, need, sha, blob = (OLD[k] for k in ("P", "need", "sha", "blob"))
CAPTURE = OLD["CAPTURE"]
PROTOCOL = "09348f8b2e8ad9449fca1d9b2c9f82ef977c48cc07e02dc4b58fdd386f5fef76"


def select(sites):
    visited = []
    for item in sites:
        tile, src, offers, unused, missing = item
        reasons = []
        if len(offers) != 4:
            reasons.append("fewer_than_four_eligible_offers")
        if not unused:
            reasons.append("all_offers_consumed")
        if missing:
            reasons.append("missing_independent_golds")
        visited.append(
            dict(
                tile=tile,
                source=src,
                offers=len(offers),
                unused=len(unused),
                missing=missing,
                reasons=reasons,
            )
        )
        if not reasons:
            return item, visited
    return None, visited


def collect(rows):
    cells, sites, tiles = {}, defaultdict(lambda: defaultdict(list)), {}
    for i, e in enumerate(rows):
        if e.kind == 2:
            break
        loc = (e.layer, e.slot)
        if e.kind == 5:
            need(loc not in cells and (e.expert, e.gen, e.a) == (-1, 0, 0), "cold process")
            cells[loc] = (e.expert, e.gen)
        if e.kind == 11:
            need(cells[loc] == (e.a, e.gen - 1), "previous binding")
            cells[loc] = (e.expert, e.gen)
        if e.call != 1:
            continue
        site = sites[e.tile, e.layer]
        if e.kind == 3:
            need(len(cells) == 1440 and e.tile not in tiles, "geometry")
            tiles[e.tile] = (e.a, e.b, e.c, i)
        elif e.kind == 35:
            site["begin"] = i
        elif e.kind == 33:
            n, start, _, _ = tiles[e.tile]
            need(e.b == len(site["pred"]) and e.c == start + e.b, "E33 row/position")
            site["pred"].append(list(P["rank4"](e.a)))
            if e.b == n - 1:
                site["last_pred"] = i
                site["occupied"] = {cells[e.layer, s][0] for s in range(40)} - {-1}
        elif e.kind == 27:
            need(e.b == len(site["ranks"]), "E27 row")
            site["ranks"].append(list(P["rank4"](e.a)))
        elif e.kind == 10:
            need(cells[loc] == (e.expert, e.gen), "demand binding")
            site["demands"].append((e.wave, e.expert, e.slot, e.gen))
        elif e.kind == 11:
            site["reserves"].append(
                dict(wave=e.wave, expert=e.expert, slot=e.slot, gen=e.gen, previous=e.a)
            )
        elif e.kind == 23:
            site["ends"].append(i)
    need(
        [(t, n, b, c) for t, (n, b, c, _) in tiles.items()]
        == [
            (t, min(32, 189 - 32 * (t - 1)), 32 * (t - 1), min(t * 32 - 1, 188))
            for t in range(1, 7)
        ],
        "six prefill tiles",
    )
    return sites, tiles


def gold(index, files, part, tile, n, start, layer):
    rows = [
        r
        for r in index
        if r["phase"].startswith("prefill")
        and int(r["first_abs"]) == start
        and int(r["layer"]) == layer
        and r["name"] in OLD["STAGES"]
    ]
    w = (4 * n + 17) // 18
    stages = OLD["STAGES"][:4] + ["ffn_moe_wave_ids", "ffn_moe_wave_mask"] * w + ["ffn_moe_out"]
    missing = []
    counts = Counter(r["name"] for r in rows)
    for stage, count in Counter(stages).items():
        need(counts[stage] <= count, "ambiguous C270 stage")
        if counts[stage] != count:
            missing.append(stage)
    for r in rows:
        name = r["file"]
        need(
            Path(name).name == name and int(r["chunk"]) == tile - 1 and int(r["state_tokens"]) == n,
            "C270 position/shape metadata",
        )
        need(
            CAPTURE + name in files and (part / CAPTURE / name).is_file(),
            "unavailable indexed data",
        )
    if not missing:
        need(stages == [r["name"] for r in rows], "ordered gold stages")
    return rows, missing


def array(r, data, n):
    k = r["name"]
    name, width = {
        "attn_post_norm": ("x.f32", 2880),
        "ffn_moe_logits": ("logits.f32", 128),
        "ffn_moe_topk": ("ids.i32", 4),
        "ffn_moe_weights_softmax": ("mix.f32", 4),
        "ffn_moe_wave_ids": ("ids.i32", 4),
        "ffn_moe_wave_mask": ("mask.f32", 4),
        "ffn_moe_out": ("ffn.f32", 2880),
    }[k]
    pitch = 512 if k == "ffn_moe_topk" else width * 4
    shape, stride = (width, n, 1, 1), (4, pitch, n * pitch, n * pitch)
    if k in ("ffn_moe_weights_softmax", "ffn_moe_wave_mask"):
        shape, stride = (1, 4, n, 1), (4, 4, 16, 16 * n)
    need(
        tuple(map(int, r["ne"].split(","))) == shape
        and tuple(map(int, r["nb"].split(","))) == stride
        and r["type"] == name[-3:]
        and len(data) == int(r["bytes"]) == (n - 1) * pitch + width * 4,
        "C270 descriptor " + k,
    )
    out = b"".join(data[t * pitch : t * pitch + width * 4] for t in range(n))
    if name.endswith(".f32"):
        P["finite"](out)
    return name, out


def obtain(args, io):
    need(sha((HERE / "protocol.md").read_bytes()) == PROTOCOL, "protocol")
    files, p23 = OLD["archive"](io, args.part23, P["PART23"])
    _, p116 = OLD["archive"](io, args.part116, P["PART116"])
    fam = p116(P["C292"] + "/receipt.json")
    rev = p116("tesy-lookahead-c292-review-20261125-r01/receipt.json")
    need(
        sha(fam) == P["FAMILY"]
        and sha(rev) == P["REVIEW"]
        and json.loads(rev)["family_sha256"] == sha(fam)
        and json.loads(p23(P["C270"] + "/receipt.json"))["status"] == "PASS_SELECTED_C269_BRIDGE",
        "families",
    )
    raw = p116(P["C292"] + "/overlay_on/raw/phase.pfj1")
    need(sha(raw) == P["PFJ"], "journal")
    rows = OLD["journal"](raw)
    sites, tiles = collect(rows)
    index = OLD["rows_tsv"](p23(CAPTURE + "index.tsv"))

    def offer(site):
        ids = set(sum(site["ranks"], []))
        need(
            ids == {e for _, e, _, _ in site["demands"]}
            and len(site["ranks"]) == len(site["pred"]),
            "topk rows and complete demand",
        )
        return OLD["offer_result"](site["pred"], site["occupied"], ids)

    need(
        all(len(o) == 4 and not f for o, f in [offer(sites[1, d]) for d in range(1, 25)]),
        "first tile independent control",
    )

    def population():
        for tile in range(2, 7):
            n, start, _, _ = tiles[tile]
            available = {
                layer: gold(index, files, args.part23, tile, n, start, layer) for layer in range(25)
            }
            for src in range(24):
                offers, unused = offer(sites[tile, src + 1])
                absent = [layer for layer in (src, src + 1) if available[layer][1]]
                yield tile, src, offers, unused, absent

    item, visited = select(population())
    result = dict(
        status="NO_ELIGIBLE_LATER_PAIR",
        visited=visited,
        protocol_sha256=PROTOCOL,
        journal_sha256=P["PFJ"],
        c270_index_sha256=files[CAPTURE + "index.tsv"]["sha256"],
        excluded=sum(bool(x["reasons"]) for x in visited),
    )
    if item is not None:
        tile, src, offers, unused, _ = item
        n, start, end, tile_enter = tiles[tile]
        checks = OLD["rows_tsv"](p23(CAPTURE + "byte_checks.tsv"))
        evidence = {}
        for layer in (src, src + 1):
            members, missing = gold(index, files, args.part23, tile, n, start, layer)
            need(not missing, "selected gold coverage")
            site = sites[tile, layer]
            q = sum(site["ranks"], [])
            arrays, counts = {}, Counter()
            for r in members:
                stage = r["name"]
                name, data = array(r, p23(CAPTURE + r["file"]), n)
                if stage.startswith("ffn_moe_wave"):
                    name = f"w{counts[stage]}." + name
                    counts[stage] += 1
                io.emit(f"L{layer}." + name, data)
                arrays[name] = data
            need(q == P["numbers"](arrays["ids.i32"], "i"), "C270 logical ranks")
            coverage = [0] * len(q)
            bindings = {}
            for w in range(len(site["ends"])):
                b = {e: (s, g) for wave, e, s, g in site["demands"] if wave == w}
                bindings[w] = b
                gens = P["wave_generations"](
                    q,
                    P["numbers"](arrays[f"w{w}.ids.i32"], "i"),
                    P["numbers"](arrays[f"w{w}.mask.f32"], "I"),
                    b,
                )
                coverage = [a + bool(g) for a, g in zip(coverage, gens, strict=True)]
                io.emit(f"L{layer}.w{w}.gen.u64", P["packed"](gens, "Q"))
            need(coverage == [1] * len(q), "all routed incidences")
            ch = [
                r for r in checks if r["phase"] == members[0]["phase"] and int(r["layer"]) == layer
            ]
            for r in ch:
                need(
                    r["status"] == "EQUAL"
                    and bindings[int(r["wave"])][int(r["logical"])]
                    == (int(r["slot"]), int(r["generation"])),
                    "C270 sampled slot check",
                )
            evidence[layer] = dict(
                ffn_sha256=sha(arrays["ffn.f32"]),
                reference_files=len(members),
                active_ranks=len(q),
                sampled_byte_checks=len(ch),
            )
        site = sites[tile, src + 1]
        io.emit("predicted.i32", P["packed"](sum(site["pred"], []), "i"))
        result.update(
            status="PAIR_AND_GOLDS_IDENTIFIED",
            call=1,
            tile=tile,
            rows=n,
            positions=[start, end],
            source=src,
            destination=src + 1,
            offers=offers,
            unused=unused,
            tile_enter=tile_enter,
            source_boundary=site["begin"],
            last_offer=site["last_pred"],
            last_wave=site["ends"][-1],
            golds=evidence,
        )
    return result, rows, sites, tiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("part23", "part116", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    io = P["Inputs"](args.new_output_dir)
    try:
        result = obtain(args, io)[0]
        result["files_sha256"] = io.files.copy()
        result["selector_sha256"] = sha(Path(__file__).read_bytes())
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", reason=str(exc))
    io.emit("receipt.json", blob(result))
    print(
        result["status"], result.get("reason", ""), result.get("source", ""), result.get("tile", "")
    )
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())

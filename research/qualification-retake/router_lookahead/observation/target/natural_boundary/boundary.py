"""Select the two C281 sampling sites and compare complete sequence states by logical position."""

import hashlib
import math
import struct

VOCAB = 201_088
ROW = 1_024
WINDOW = 128
BANKS = (tuple(range(1, 36, 2)), tuple(range(0, 36, 2)))
PROMPT = "cf7e9b19362c5aeaf5e54e2185048acac09ec55459fb4a6fc262ec434f037425"
SAMPLES = "4a8a47b3ec0a64220e9734237eae9fd7b886ce35ed81964408eacdc4034931f9"
SHA = hashlib.sha256


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def token_hash(ids):
    return SHA(struct.pack(f"<{len(ids)}i", *ids)).hexdigest()


def select(views, cached, sampled, *, request, prompt_sha=PROMPT, samples_sha=SAMPLES):
    """Views carry the before-sampling batch plus the independent PFJ ubatch positions."""
    need(len(views) == 3 and len(cached) == 2044 and len(sampled) == 47, "trajectory extents")
    need(token_hash(sampled) == samples_sha, "independent output IDs")
    all_prompt = list(cached)
    sites = []
    position = 2044
    for call, widths in enumerate(((5,), (32, 32, 32, 32, 20), (1,)), 1):
        v = views[call - 1]
        n = sum(widths)
        positions = list(range(position, position + n))
        mask = [0] * n
        if call > 1:
            mask[-1] = 1
        need(
            v["request"] == request
            and v["call"] == call
            and v["rc"] == 0
            and v["slot"] == 0
            and v["seqs"] == [[0]] * n,
            "request/call/sequence",
        )
        need(v["positions"] == positions and v["mask"] == mask, "batch positions/output mask")
        need(len(v["tiles"]) == len(widths), "PFJ tile count")
        cursor = 0
        for tile, (rows, width) in enumerate(zip(v["tiles"], widths, strict=True), 1):
            need(rows == (tile, positions[cursor : cursor + width]), "PFJ tile identity/positions")
            cursor += width
        need(len(v["tokens"]) == n, "input IDs")
        if call < 3:
            all_prompt.extend(v["tokens"])
        else:
            need(v["tokens"] == sampled[:1], "first decode input vs prefill sample")
        if call == 1:
            need(v["sampler_index"] is None, "sample from return without outputs")
        else:
            # The public ith accessor prefers a sampled/logit buffer when a backend sampler exists.
            # Positive batch index alone does not prove that the pointer spans the vocabulary.
            need(
                v["full_row0_alias"] is True
                and v["sampled_logits_count"] == 0
                and v["n_outputs"] == 1
                and v["vocab"] == VOCAB,
                "full raw logit row authority",
            )
            i = v["slot_i_batch"] - v["offset"]
            need(v["offset"] >= 0 and i == n - 1 == v["sampler_index"], "sampler batch row")
            sites.append(
                dict(
                    call=call,
                    tile=len(widths),
                    position=positions[i],
                    tile_row=widths[-1] - 1,
                    sampler_row=i,
                    compact_row=sum(mask[:i]),
                    seq=0,
                )
            )
        position += n
    need(len(all_prompt) == 2197 and token_hash(all_prompt) == prompt_sha, "full historical prefix")
    return sites


def visible(query):
    """Inclusive-start, exclusive-end causal ranges under C291 standard SWA, single sequence."""
    return ((0, query + 1), (max(0, query - WINDOW + 1), query + 1))


def extent(cells):
    live = cells + min(WINDOW, cells)
    payload = 36 * ROW * live
    metadata = 8 + 2 * (16 + 36 * 12) + 12 * live
    return dict(
        kv_payload=payload,
        kv_metadata=metadata,
        kv_bytes=payload + metadata,
        logit_bytes=VOCAB * 4,
        max_get_ranges=36 * live,
    )


def logit_digest(blob):
    need(len(blob) == VOCAB * 4, "incomplete output row")
    need(all(math.isfinite(v[0]) for v in struct.iter_unpack("<f", blob)), "non-finite logit")
    return SHA(blob).hexdigest()


def decode_kv(blob, cells, *, seq=0):
    """Hash host-serialized K/V by position, independently of physical cell order."""
    need(0 < cells <= 8192 and seq == 0, "unsupported contract")
    need(len(blob) == extent(cells)["kv_bytes"], "KV extent")
    raw = memoryview(blob)
    cursor = 0

    def unpack(fmt):
        nonlocal cursor
        fmt = struct.Struct("<" + fmt)
        result = fmt.unpack_from(raw, cursor)
        cursor += fmt.size
        return result

    need(unpack("Ii") == (0xAF143CD8, seq), "state magic/sequence")
    digests = {}
    for (name, layers), (begin, end) in zip(
        zip(("global", "swa"), BANKS, strict=True), visible(cells - 1), strict=True
    ):
        n = end - begin
        need(unpack("II") == (1, n), "stream or live cell count")
        order = {}
        for ordinal in range(n):
            pos, owners, owner = unpack("iIi")
            need(
                begin <= pos < end and pos not in order and (owners, owner) == (1, seq),
                "missing/duplicate/foreign position",
            )
            order[pos] = ordinal
        need(unpack("II") == (0, len(layers)), "V transpose/layer count")
        for kind in ("K", "V"):
            for layer in layers:
                need(unpack("iQ") == (1, ROW), "K/V type or GQA row extent")
                h = SHA()
                for pos in range(begin, end):
                    offset = cursor + ROW * order[pos]
                    h.update(raw[offset : offset + ROW])
                digests[f"{name}.{kind}.{layer}"] = h.hexdigest()
                cursor += n * ROW
    need(cursor == len(raw), "trailing bytes")
    return digests


def agree(a, b):
    need(a["site"] == b["site"], "different sampling sites")
    need(a["logits"] == b["logits"], "logits mismatch")
    need(a["kv"].keys() == b["kv"].keys() and len(a["kv"]) == 72, "component census")
    for key in a["kv"]:
        need(a["kv"][key] == b["kv"][key], f"KV mismatch in {key}")

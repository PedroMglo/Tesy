"""Frozen graph cuts. Shapes omit the position axis; positions are always the next axis."""

from typing import NamedTuple


class Site(NamedTuple):
    name: str
    group: int
    dims: tuple
    ops: tuple
    kind: str = "F32"


EMBED = Site("embd", 0, (2880,), ("GET_ROWS",))
LAYERS = range(14)
POSITIONS = range(189, 192)
SITES = (
    Site("attn_norm", 1, (2880,), ("MUL",)),
    Site("Qcur", 2, (64, 64), ("ROPE",)),
    Site("Kcur", 2, (64, 8), ("ROPE",)),
    Site("Vcur", 2, (64, 8), ("RESHAPE", "VIEW")),
    Site("attn_out", 3, (2880,), ("ADD",)),
    Site("ffn_inp", 4, (2880,), ("ADD",)),
    Site("attn_post_norm", 5, (2880,), ("MUL",)),
    Site("ffn_moe_logits", 6, (128,), ("MUL_MAT",)),
    Site("ffn_moe_probs", 7, (128,), ("ADD",)),
    Site("ffn_moe_topk", 8, (4,), ("VIEW",), "I32"),
    Site("ffn_moe_weights_softmax", 9, (1, 4), ("RESHAPE",)),
    Site("ffn_moe_gate", 10, (2880, 4), ("MUL_MAT_ID",)),
    Site("ffn_moe_up", 10, (2880, 4), ("MUL_MAT_ID",)),
    Site("ffn_moe_gate_biased", 11, (2880, 4), ("ADD_ID",)),
    Site("ffn_moe_up_biased", 11, (2880, 4), ("ADD_ID",)),
    Site("ffn_moe_swiglu_oai", 12, (2880, 4), ("GLU",)),
    Site("ffn_moe_down", 13, (2880, 4), ("MUL_MAT_ID",)),
    Site("ffn_moe_down_biased", 14, (2880, 4), ("ADD_ID",)),
    Site("ffn_moe_weighted", 15, (2880, 4), ("MUL",)),
    Site("ffn_moe_out", 16, (2880,), ("ADD",)),
    Site("l_out", 17, (2880,), ("ADD",)),
)


def population():
    yield -1, EMBED.name, EMBED
    for layer in LAYERS:
        for site in SITES:
            yield layer, f"{site.name}-{layer}", site

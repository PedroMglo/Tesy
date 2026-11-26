"""Derive one graph translation unit and teach its observer to inspect the reassembled rows."""

from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(str(HERE.parents[1] / "pair.py"))
B, S, need, read, save, sha = (P[k] for k in ("B", "S", "need", "read", "save", "sha"))
QUAL = S["QUAL"]
METHOD = "7a02495d34d902d90a2fed9914e5035b292c847cafc8965b47f7ebb7bafab8ec"
PRIOR_SHA = "3ba064e64cc834f08dc6edf721be07c7013fc2f4b6641b3de13003488e4c2f71"
OPTION = "TESY_B3_ATTN25_ROWS"
once = S["G"]["probes"].old.historical.once


def graph(source):
    interface = S["G"]["probes"].old.graph(source)
    original = ("        cur = ggml_flash_attn_ext(ctx0, q, k, v, kq_mask, kq_scale, "
                + """hparams.f_max_alibi_bias,
                                  hparams.attn_soft_cap ? hparams.f_attn_logit_softcapping : 0.0f);
        cb(cur, LLAMA_TENSOR_NAME_FATTN, il);

        ggml_flash_attn_ext_add_sinks(cur, sinks);
        ggml_flash_attn_ext_set_prec (cur, GGML_PREC_F32);""")
    replacement = (HERE / "attention.inc").read_text().rstrip().replace("@ORIGINAL@", original)
    return once(interface, original, replacement)


def observer():
    src = B["render"]().decode()
    marker = "        if (split) {"
    selector = """        const bool join = name == "__fattn__-25" && width == 3 &&
            std::getenv("TESY_B3_ATTN25_ROWS") &&
            std::string(std::getenv("TESY_B3_ATTN25_ROWS")) == "1";
        if (join) {
            check(t->op == GGML_OP_CONCAT && t->op_params[0] == 2 && t->src[0] && t->src[1] &&
                  t->src[0]->op == GGML_OP_CONCAT && t->src[0]->op_params[0] == 2 &&
                  t->src[0]->ne[2] == 2 && t->src[1]->ne[2] == 1, "reassembled L25");
        } else if (split) {"""
    src = once(src, marker, selector)
    old = "                auto words = attention_mask_row(t->src[3],width,i);"
    new = """                auto *row = join ? (i == 2 ? t->src[1] : t->src[0]->src[i]) : t;
                check(row && row->op == GGML_OP_FLASH_ATTN_EXT && row->ne[2] == (join ? 1 : width),
                      "effective attention row");
                auto words = attention_mask_row(row->src[3],join ? 1 : width,join ? 0 : i);"""
    return once(src, old, new).encode()

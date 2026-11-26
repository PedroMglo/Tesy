        const char *rows_mode = std::getenv("TESY_B3_ATTN25_ROWS");
        if (arch == LLM_ARCH_OPENAI_MOE && il == 25 && q->ne[1] == 3 &&
                q->ne[3] == 1 && k->ne[1] == 256 && rows_mode && std::strcmp(rows_mode, "1") == 0) {
            GGML_ASSERT(!v_mla && q->type == GGML_TYPE_F32 && k->type == GGML_TYPE_F16 &&
                        v->type == GGML_TYPE_F16 && q->ne[0] == 64 && q->ne[2] == 64 &&
                        k->ne[0] == 64 && k->ne[2] == 8 && k->ne[3] == 1 &&
                        ggml_are_same_shape(k,v) && kq_mask && kq_mask->type == GGML_TYPE_F16 &&
                        kq_mask->ne[0] == 256 && kq_mask->ne[1] == 3 && kq_mask->ne[2] == 1 &&
                        kq_mask->ne[3] == 1 && sinks && sinks->ne[0] == 64 && kq_scale == 0.125f &&
                        !hparams.attn_soft_cap && hparams.f_max_alibi_bias == 0.0f);
            ggml_tensor *rows[3];
            for (int j = 0; j < 3; ++j) {
                auto *qi = ggml_view_4d(ctx0, q, 64, 1, 64, 1, q->nb[1], q->nb[2], q->nb[3],
                                        j * q->nb[1]);
                auto *mi = ggml_view_2d(ctx0, kq_mask, 256, 1, kq_mask->nb[1], j * kq_mask->nb[1]);
                rows[j] = ggml_flash_attn_ext(ctx0, qi, k, v, mi, kq_scale, 0.0f, 0.0f);
                ggml_flash_attn_ext_add_sinks(rows[j], sinks);
                ggml_flash_attn_ext_set_prec(rows[j], GGML_PREC_F32);
                ggml_format_name(rows[j], "__fattn__-%d-row%d", il, j);
            }
            cur = ggml_concat(ctx0, ggml_concat(ctx0, rows[0], rows[1], 2), rows[2], 2);
            cb(cur, LLAMA_TENSOR_NAME_FATTN, il);
        } else {
@ORIGINAL@
        }

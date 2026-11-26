    const char *down_mode = std::getenv("TESY_B3_GPU_REPAIR");
    const bool split_down = down_mode && (std::strcmp(down_mode, "CUDA") == 0 ||
            (il == 25 && std::strcmp(down_mode, "D25") == 0));
    if (split_down && arch == LLM_ARCH_OPENAI_MOE && il >= 25 && il <= 35 && n_tokens == 3) {
        GGML_ASSERT(msl && msl->n_slots == 40 && n_stream_waves == 1 && n_expert_used == 4 &&
                    loras && loras->empty() && !weight_before_ffn && !gate_up_exps &&
                    !down_exps_s && down_exps_b && down_exps_b->type == GGML_TYPE_F32 &&
                    down_exps_b->ne[0] == 2880 && down_exps_b->ne[1] == 128 &&
                    down_exps->type == GGML_TYPE_MXFP4 && down_exps->ne[0] == 2880 &&
                    down_exps->ne[1] == 2880 && down_exps->ne[2] == 40 &&
                    cur->type == GGML_TYPE_F32 && cur->ne[0] == 2880 && cur->ne[1] == 4 &&
                    cur->ne[2] == 3 && cur->ne[3] == 1 &&
                    logical_ids->type == GGML_TYPE_I32 && ids_gemm->type == GGML_TYPE_I32 &&
                    logical_ids != ids_gemm && logical_ids->ne[0] == 4 && logical_ids->ne[1] == 3 &&
                    ggml_are_same_shape(logical_ids, ids_gemm));
        ggml_tensor *row[3];
        for (int i = 0; i < 3; ++i) {
            auto *hidden = ggml_view_3d(ctx0, cur, 2880, 4, 1, cur->nb[1], cur->nb[2], i*cur->nb[2]);
            auto *physical = ggml_view_2d(ctx0, ids_gemm, 4, 1, ids_gemm->nb[1], i*ids_gemm->nb[1]);
            auto *logical = ggml_view_2d(ctx0, logical_ids, 4, 1, logical_ids->nb[1], i*logical_ids->nb[1]);
            auto *out = build_lora_mm_id(down_exps, hidden, physical, nullptr, logical);
            row[i] = ggml_add_id(ctx0, out, down_exps_b, logical);
        }
        auto *all = ggml_concat(ctx0, ggml_concat(ctx0, row[0], row[1], 2), row[2], 2);
        cb(all, "ffn_moe_down_biased", il);
        std::fprintf(stderr, "tesy_b3_built down %d 3\n", il);
        return all;
    }


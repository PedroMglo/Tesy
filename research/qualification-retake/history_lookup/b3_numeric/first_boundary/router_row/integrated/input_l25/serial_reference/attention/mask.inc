static std::vector<uint16_t> attention_mask_row(const ggml_tensor *mask, int width, int row) {
    check(mask && mask->type == GGML_TYPE_F16 && mask->ne[0] > 0 && mask->ne[0] <= 8192 &&
          mask->ne[1] == width && mask->ne[2] == 1 && mask->ne[3] == 1 &&
          mask->nb[0] == sizeof(uint16_t) && mask->nb[1] >= mask->nb[0] * size_t(mask->ne[0]) &&
          row >= 0 && row < width, "active layer-25 mask geometry");
    std::vector<uint16_t> values(mask->ne[0]);
    const size_t size = values.size() * sizeof(uint16_t);
    const size_t offset = size_t(row) * mask->nb[1];
    check(offset + size <= ggml_nbytes(mask), "active mask bounds");
    ggml_backend_tensor_get(mask, values.data(), offset, size);
    return values;
}

static void test_attention_mask_row() {
    ggml_init_params p{1024*1024, nullptr, true};
    ggml_context *ctx = ggml_init(p);
    check(ctx != nullptr, "test mask context");
    auto *storage = ggml_new_tensor_2d(ctx, GGML_TYPE_F16, 8, 3);
    auto *view = ggml_view_2d(ctx, storage, 4, 3, storage->nb[1], 0);
    auto *buf = ggml_backend_alloc_ctx_tensors_from_buft(ctx, ggml_backend_cpu_buffer_type());
    check(buf != nullptr, "test mask buffer");
    std::array<uint16_t,24> data{};
    for (int j=0;j<3;++j) for (int i=0;i<8;++i) {
        data[j*8+i] = i<=j ? 0 : (i<4 ? 0xfc00 : 0x5555);
    }
    ggml_backend_tensor_set(storage,data.data(),0,sizeof(data));
    for (int j=0;j<3;++j) {
        const auto got=attention_mask_row(view,3,j);
        for (int i=0;i<4;++i) check(got.at(i) == data[j*8+i], "test visibility and row pitch");
    }
    bool refused=false;
    try { (void)attention_mask_row(view,1,0); } catch (const std::exception &) { refused=true; }
    check(refused,"test rejected mismatched query width");
    ggml_backend_buffer_free(buf);
    ggml_free(ctx);
}

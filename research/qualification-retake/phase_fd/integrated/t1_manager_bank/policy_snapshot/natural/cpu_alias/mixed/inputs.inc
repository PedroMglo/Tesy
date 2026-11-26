    // The graph allocator may recycle an input's bytes after its last consumer.
    // Keep canonical fixture inputs outside GGML and resubmit all five before each compute.
    std::array<std::pair<Tensor,Values>,5> canonical_inputs;
    canonical_inputs[0] = {scores, std::move(scores_in)};
    canonical_inputs[1] = {mask, std::move(masks)};
    for (int k=0; k<3; ++k) {
        Values input;
        for(int p=0;p<n;++p) for(int r=0;r<(k==1?ranks:1);++r) for(int c=0;c<width;++c)
            input.push_back(activation(p,r,c));
        canonical_inputs[k+2] = {state.stages[k].input, std::move(input)};
    }
    auto differences=[](const std::pair<Tensor, Values> &input) {
        const auto &[t,expected] = input;
        Values actual(expected.size());
        ggml_backend_tensor_get(t,actual.data(),0,actual.size()*sizeof(float));
        size_t count = 0;
        for (size_t i=0; i<expected.size(); ++i) count += bits(actual[i]) != bits(expected[i]);
        return count;
    };
    auto refill=[&](bool seen, int epoch) {
        if (seen) {
            std::cout << "INPUT_DELTA " << epoch+1;
            for (const auto &input:canonical_inputs) std::cout << ' ' << differences(input);
            std::cout << std::endl;
        }
        for (const auto &[t,v]:canonical_inputs)
            ggml_backend_tensor_set(t,v.data(),0,v.size()*sizeof(float));
        for (const auto &input:canonical_inputs) check(differences(input)==0, "input readback");
    };

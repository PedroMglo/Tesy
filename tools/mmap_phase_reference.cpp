#include "ggml-backend.h"
#include "ggml-backend-impl.h"
#include "ggml-impl.h"
#include "ggml-cpu.h"
#include "ggml.h"
#include "gguf.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <fcntl.h>
#include <unistd.h>

namespace {

constexpr int64_t embd = 2880;
constexpr int64_t experts = 128;
constexpr int64_t topk = 4;

void require(bool ok, const std::string & message) {
    if (!ok) throw std::runtime_error(message);
}

struct owner {
    ggml_context * ctx = nullptr;
    ggml_backend_buffer_t buffer = nullptr;
    ~owner() { if (buffer) ggml_backend_buffer_free(buffer); if (ctx) ggml_free(ctx); }
};

struct backend_owner {
    ggml_backend_t value = nullptr;
    ~backend_owner() { if (value) ggml_backend_free(value); }
};

struct spec {
    std::string name;
    ggml_type type;
    size_t offset;
    size_t bytes;
    ggml_tensor * tensor;
};

ggml_context * context(size_t size) {
    ggml_init_params p{size, nullptr, true};
    ggml_context * result = ggml_init(p);
    require(result != nullptr, "ggml_init failed");
    return result;
}

std::vector<std::string> split(const std::string & text, char delimiter) {
    std::vector<std::string> out;
    std::istringstream stream(text);
    std::string item;
    while (std::getline(stream, item, delimiter)) out.push_back(item);
    return out;
}

struct captured {
    std::string phase;
    int layer;
    std::string name;
    std::array<size_t, 4> ne{};
    std::array<size_t, 4> nb{};
    std::filesystem::path path;
};

std::vector<captured> index(const std::filesystem::path & root, int layer) {
    std::ifstream source(root / "index.tsv");
    require(bool(source), "capture index missing");
    std::string line;
    std::getline(source, line);
    require(line == "phase\tlayer\tchunk\tfirst_abs\tstate_tokens\tname\ttype\tne\tnb\tbytes\tfile", "capture index header changed");
    std::vector<captured> out;
    while (std::getline(source, line)) {
        auto fields = split(line, '\t');
        require(fields.size() == 11, "capture index row malformed");
        if (std::stoi(fields[1]) != layer) continue;
        require(fields[6] == "f32" || fields[6] == "i32", "capture type unsupported");
        captured row{fields[0], layer, fields[5], {}, {}, {}};
        auto ne = split(fields[7], ',');
        auto nb = split(fields[8], ',');
        require(ne.size() == 4 && nb.size() == 4, "capture shape/strides malformed");
        for (int i = 0; i < 4; ++i) {
            row.ne[i] = std::stoull(ne[i]); row.nb[i] = std::stoull(nb[i]);
        }
        row.path = root / fields[10];
        require(std::filesystem::is_regular_file(row.path) &&
                std::filesystem::file_size(row.path) == std::stoull(fields[9]),
                "capture file size differs from index");
        out.push_back(row);
    }
    return out;
}

const captured & one(const std::vector<captured> & rows,
                     const std::string & phase, const char * name) {
    const captured * found = nullptr;
    for (const auto & row : rows) if (row.phase == phase && row.name == name) {
        require(found == nullptr, std::string("duplicate capture stage: ") + name);
        found = &row;
    }
    require(found != nullptr, "capture stage missing: " + phase + "/" + name);
    return *found;
}

std::vector<uint8_t> bytes(const std::filesystem::path & path) {
    std::ifstream source(path, std::ios::binary);
    require(bool(source), "cannot open " + path.string());
    return std::vector<uint8_t>(std::istreambuf_iterator<char>(source), {});
}

template<typename T> std::vector<T> read_strided(const captured & row, size_t n0, size_t n1,
                                                   size_t stride0, size_t stride1) {
    const auto raw = bytes(row.path);
    std::vector<T> out(n0*n1);
    for (size_t y = 0; y < n1; ++y) for (size_t x = 0; x < n0; ++x) {
        const size_t offset = x*stride0 + y*stride1;
        require(offset + sizeof(T) <= raw.size(), "capture stride exceeds file");
        std::memcpy(&out[y*n0+x], raw.data()+offset, sizeof(T));
    }
    return out;
}

spec get_spec(gguf_context * gguf, ggml_context * meta, ggml_tensor * target,
              const std::string & name, ggml_type type,
              const std::vector<int64_t> & shape) {
    const int64_t id = gguf_find_tensor(gguf, name.c_str());
    require(id >= 0, "GGUF tensor missing: " + name);
    ggml_tensor * source = ggml_get_tensor(meta, name.c_str());
    require(source != nullptr && gguf_get_tensor_type(gguf,id) == type &&
            ggml_n_dims(source) == static_cast<int>(shape.size()),
            "GGUF tensor type/rank mismatch: " + name);
    for (size_t i = 0; i < shape.size(); ++i)
        require(source->ne[i] == shape[i] && target->ne[i] == shape[i],
                "GGUF tensor shape mismatch: " + name);
    const size_t size = gguf_get_tensor_size(gguf,id);
    require(size == ggml_nbytes(target), "GGUF tensor bytes mismatch: " + name);
    if (shape.back() == experts && shape.size() > 1)
        require(size % experts == 0 && source->nb[shape.size()-1] == size/experts,
                "expert slices are not canonical contiguous order: " + name);
    const size_t base = gguf_get_data_offset(gguf);
    const size_t relative = gguf_get_tensor_offset(gguf,id);
    require(relative <= std::numeric_limits<size_t>::max() - base,
            "GGUF tensor offset overflow");
    return {name,type,base+relative,size,target};
}

void load_exact(int fd, const spec & item, size_t file_size) {
    require(item.offset <= file_size && item.bytes <= file_size-item.offset,
            "GGUF tensor outside file: " + item.name);
    std::vector<uint8_t> payload(item.bytes);
    size_t done = 0;
    while (done < payload.size()) {
        const ssize_t n = pread(fd,payload.data()+done,payload.size()-done,item.offset+done);
        require(n > 0, "short/error canonical GGUF read: " + item.name);
        done += static_cast<size_t>(n);
    }
    ggml_backend_tensor_set(item.tensor,payload.data(),0,payload.size());
}

struct comparison {
    bool bitwise = false;
    double max_abs = 0;
    double rmse = 0;
    size_t nonfinite = 0;
};

comparison compare(const std::vector<float> & reference,
                   const std::vector<float> & candidate) {
    require(reference.size() == candidate.size(), "comparison shape mismatch");
    comparison out;
    out.bitwise = std::memcmp(reference.data(),candidate.data(),
                              reference.size()*sizeof(float)) == 0;
    double squares = 0;
    for (size_t i = 0; i < reference.size(); ++i) {
        if (!std::isfinite(reference[i]) || !std::isfinite(candidate[i])) {
            ++out.nonfinite; continue;
        }
        const double error = double(reference[i])-candidate[i];
        out.max_abs = std::max(out.max_abs,std::abs(error));
        squares += error*error;
    }
    out.rmse = std::sqrt(squares/reference.size());
    return out;
}

template<typename T> std::vector<T> tensor_get(ggml_tensor * tensor) {
    std::vector<T> out(static_cast<size_t>(ggml_nelements(tensor)));
    require(ggml_is_contiguous(tensor) && ggml_nbytes(tensor) == out.size()*sizeof(T),
            std::string("reference output not contiguous: ") + tensor->name +
            " bytes=" + std::to_string(ggml_nbytes(tensor)) +
            " elements=" + std::to_string(out.size()));
    ggml_backend_tensor_get(tensor,out.data(),0,out.size()*sizeof(T));
    return out;
}

struct row_result {
    std::string phase;
    size_t tokens = 0;
    bool routing_ids_equal = false;
    comparison routing_weights;
    comparison ffn;
};

row_result replay(const std::string & phase, const std::vector<captured> & rows,
                  ggml_backend_t backend, ggml_backend_t route_backend,
                  const std::array<ggml_tensor *,8> & tensors, ggml_backend_t reduction_backend = nullptr) {
    const auto & activation = one(rows,phase,"attn_post_norm");
    const auto & ids_capture = one(rows,phase,"ffn_moe_topk");
    const auto & weights_capture = one(rows,phase,"ffn_moe_weights_softmax");
    const auto & output_capture = one(rows,phase,"ffn_moe_out");
    const size_t n = activation.ne[1];
    require(n > 0 && n <= 64 && activation.ne[0] == embd &&
            ids_capture.ne[0] == topk && ids_capture.ne[1] == n &&
            weights_capture.ne[1] == topk && weights_capture.ne[2] == n &&
            output_capture.ne[0] == embd && output_capture.ne[1] == n,
            "capture tensor shapes differ from expected FFN boundary");
    const auto input = read_strided<float>(activation,embd,n,activation.nb[0],activation.nb[1]);
    const auto ids = read_strided<int32_t>(ids_capture,topk,n,ids_capture.nb[0],ids_capture.nb[1]);
    const auto mix = read_strided<float>(weights_capture,topk,n,
                                         weights_capture.nb[1],weights_capture.nb[2]);
    const auto expected = read_strided<float>(output_capture,embd,n,
                                              output_capture.nb[0],output_capture.nb[1]);
    for (int32_t id : ids) require(id >= 0 && id < experts, "invalid logical expert ID");
    for (float value : mix) require(std::isfinite(value) && value >= 0,
                                    "invalid route weight");
    owner graph;
    graph.ctx = context(16u*1024u*1024u);
    auto * c = graph.ctx;
    auto * inp = ggml_new_tensor_2d(c,GGML_TYPE_F32,embd,n);
    auto * logits = ggml_mul_mat(c,tensors[6],inp);
    ggml_set_output(logits); // Native observer requests raw router matmul before bias.
    logits = ggml_add(c,logits,tensors[7]);
    ggml_set_output(logits); // Native observer requests biased logits/probs.
    ggml_tensor * biased_logits = logits;
    auto * route_ids = ggml_cont(c,ggml_argsort_top_k(c,logits,topk));
    auto * prob = ggml_reshape_3d(c,logits,1,experts,n);
    auto * route_weights = ggml_get_rows(c,prob,route_ids);
    route_weights = ggml_reshape_2d(c,route_weights,topk,n);
    route_weights = ggml_soft_max(c,route_weights);
    route_weights = ggml_cont(c,ggml_reshape_3d(c,route_weights,1,topk,n));
    auto * inp3 = ggml_reshape_3d(c,inp,embd,1,n);
    auto * up = ggml_mul_mat_id(c,tensors[1],inp3,route_ids);
    up = ggml_add_id(c,up,tensors[4],route_ids);
    auto * gate = ggml_mul_mat_id(c,tensors[0],inp3,route_ids);
    gate = ggml_add_id(c,gate,tensors[3],route_ids);
    auto * act = ggml_swiglu_oai(c,gate,up,1.702f,7.0f);
    auto * down = ggml_mul_mat_id(c,tensors[2],act,route_ids);
    down = ggml_add_id(c,down,tensors[5],route_ids);
    auto * expert_down = down;
    auto * weighted = ggml_mul(c,down,route_weights);
    down = weighted;
    std::array<ggml_tensor *,4> views;
    for (int e = 0; e < topk; ++e) views[e] = ggml_view_2d(c,down,embd,n,down->nb[2],e*down->nb[1]);
    ggml_tensor * sum = views[0];
    for (int e = 1; e < topk; ++e) sum = ggml_add(c,sum,views[e]);
    auto * output = ggml_cont(c,sum);
    // These intermediates are read after all downstream FFN operations. Merely
    // expanding them into the graph does not keep their storage alive.
    ggml_set_output(route_ids);
    ggml_set_output(route_weights);
    ggml_set_output(output);
    auto * gf = ggml_new_graph(c);
    ggml_build_forward_expand(gf,route_ids);
    ggml_build_forward_expand(gf,route_weights);
    ggml_build_forward_expand(gf,weighted);
    for(auto*t:views) ggml_build_forward_expand(gf,t);
    ggml_build_forward_expand(gf,output);
    std::vector<ggml_backend_t> backends;
    for(auto b:{reduction_backend,route_backend,backend}) if(b && std::find(backends.begin(),backends.end(),b)==backends.end()) backends.push_back(b);
    auto sched = ggml_backend_sched_new(backends.data(),nullptr,backends.size(),GGML_DEFAULT_GRAPH_SIZE,false,false);
    require(sched != nullptr,"reference scheduler init");
    ggml_backend_sched_set_tensor_backend(sched,inp,route_backend);
    if(reduction_backend){
        ggml_backend_sched_set_tensor_backend(sched,weighted,reduction_backend);
        for(auto * t:views) ggml_backend_sched_set_tensor_backend(sched,t,reduction_backend);
        ggml_backend_sched_set_tensor_backend(sched,sum,reduction_backend);
        ggml_backend_sched_set_tensor_backend(sched,output,reduction_backend);
    }
    // Same observer checkpoints as C166; no native outputs are supplied to reference.
    std::array<ggml_tensor *,4> checkpoints{biased_logits->src[0],biased_logits,route_ids,route_weights};
    ggml_backend_sched_set_eval_callback(sched,[](ggml_tensor * t,bool,void * u){
        auto & c=*static_cast<std::array<ggml_tensor *,4> *>(u);return std::find(c.begin(),c.end(),t)!=c.end();
    },&checkpoints);
    require(ggml_backend_sched_alloc_graph(sched,gf),"reference graph allocation");
    require(ggml_backend_sched_get_tensor_backend(sched,expert_down)==backend && ggml_backend_sched_get_tensor_backend(sched,act)==backend && ggml_backend_sched_get_tensor_backend(sched,gate)==backend && ggml_backend_sched_get_tensor_backend(sched,up)==backend,"reference expert plan must CPU");
    require(ggml_backend_sched_get_tensor_backend(sched,weighted)==reduction_backend && ggml_backend_sched_get_tensor_backend(sched,sum)==reduction_backend,"reference tail map");
    require(ggml_backend_sched_get_tensor_backend(sched,biased_logits)==route_backend,"reference router map");
    ggml_backend_tensor_set(inp,input.data(),0,input.size()*sizeof(float));
    require(ggml_backend_sched_graph_compute(sched,gf) == GGML_STATUS_SUCCESS,
            "reference graph compute failed");
    ggml_backend_sched_synchronize(sched);
    const auto logical_ids = tensor_get<int32_t>(route_ids);
    const auto logical_weights = tensor_get<float>(route_weights);
    const auto actual = tensor_get<float>(output);
    row_result result;
    result.phase = phase;
    result.tokens = n;
    result.routing_ids_equal = logical_ids == ids;
    result.routing_weights = compare(logical_weights,mix);
    result.ffn = compare(actual,expected);
    ggml_backend_sched_free(sched);
    return result;
}

std::string render(const row_result & row) {
    std::ostringstream out;
    out << std::setprecision(12) << "{\"phase\":\"" << row.phase << "\",\"state\":\"NUMERIC\",\"tokens\":" << row.tokens
        << ",\"routing_ids_equal\":" << (row.routing_ids_equal ? "true" : "false")
        << ",\"routing_weights_bitwise\":" << (row.routing_weights.bitwise ? "true" : "false")
        << ",\"routing_weights_max_abs\":" << row.routing_weights.max_abs
        << ",\"routing_weights_rmse\":" << row.routing_weights.rmse
        << ",\"routing_weights_nonfinite\":" << row.routing_weights.nonfinite
        << ",\"ffn_bitwise\":" << (row.ffn.bitwise ? "true" : "false")
        << ",\"ffn_max_abs\":" << row.ffn.max_abs
        << ",\"ffn_rmse\":" << row.ffn.rmse
        << ",\"ffn_nonfinite\":" << row.ffn.nonfinite << '}';
    return out.str();
}

} // namespace

int main(int argc, char ** argv) {
    if (argc != 8) {
        std::cerr << "usage: c7_layer_reference MODEL.gguf CAPTURE_DIR LAYER --ngl 12 --plan-map MAP.tsv\n";
        return 2;
    }
    try {
        const std::string model = argv[1];
        const auto capture_root = std::filesystem::path(argv[2]);
        const int layer = std::stoi(argv[3]);
        require(std::string(argv[4]) == "--ngl", "unknown reference option");
        const int ngl = std::stoi(argv[5]);
        require(layer >= 0 && layer < 36 && ngl == 12, "reference outside frozen P12 map");
        const int first_gpu_layer = 36 - (ngl - 1); // one of the ngl placements is output
        const std::string device = "cpu";
        require(std::string(argv[6])=="--plan-map","explicit native map required");
        std::ifstream map(argv[7]);std::string line;std::getline(map,line);require(line=="layer\trouter\texperts\treduction\tfusion","plan map header");
        std::string router_name,tail_name;int seen=0;
        for(int l=0;std::getline(map,line);++l){auto f=split(line,'\t');require(f.size()==5 && std::stoi(f[0])==l && f[2]=="CPU" && (f[1]=="CPU"||f[1]=="CUDA0") && (f[3]=="CPU"||f[3]=="CUDA0") && f[4]==(f[3]=="CPU"?"0":"1"),"plan map contract");if(l==layer){router_name=f[1];tail_name=f[3];}++seen;}
        require(seen==36 && !router_name.empty(),"exact36 plan map");
        const std::string route_device=router_name=="CPU"?"cpu":"gpu";
        const auto rows = index(capture_root,layer);
        std::vector<std::string> phases;
        {
            std::ifstream source(capture_root / "phases.txt");
            require(bool(source), "frozen capture phase index missing");
            std::string phase;
            while (std::getline(source,phase)) {
                require(!phase.empty() &&
                        std::find(phases.begin(),phases.end(),phase) == phases.end(),
                        "empty or duplicated capture phase");
                phases.push_back(phase);
            }
        }
        const std::vector<std::string> broad{"prefill0","decode0","decode1","decode2","decode3"};
        require(phases == broad, "capture phase schedule changed");
        ggml_backend_load_all();
        auto * dev = ggml_backend_dev_by_type(device == "cpu" ?
                         GGML_BACKEND_DEVICE_TYPE_CPU : GGML_BACKEND_DEVICE_TYPE_GPU);
        require(dev != nullptr, "requested backend unavailable");
        backend_owner backend{ggml_backend_dev_init(dev,nullptr)};
        require(backend.value != nullptr, "backend initialization failed");
        if (device == "cpu") ggml_backend_cpu_set_n_threads(backend.value,8);
        owner storage; owner router_storage;
        storage.ctx = context(8u*1024u*1024u); router_storage.ctx = context(1024u*1024u);
        auto * c = storage.ctx; auto * rctx = router_storage.ctx;
        backend_owner router_backend;
        ggml_backend_t route = backend.value;
        if (route_device == "gpu") {
            auto * gpu = ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_GPU);
            require(gpu != nullptr,"router GPU backend missing");
            router_backend.value = ggml_backend_dev_init(gpu,nullptr);
            require(router_backend.value != nullptr,"router backend init");
            route = router_backend.value;
        }
        backend_owner tail; ggml_backend_t reduction=backend.value;
        if(tail_name=="CUDA0"){
            if(router_backend.value)reduction=router_backend.value;
            else {auto*d=ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_GPU);require(d,"tail GPU device");tail.value=ggml_backend_dev_init(d,nullptr);require(tail.value,"tail backend init");reduction=tail.value;}
        }
        std::array<ggml_tensor *,8> tensors{
            ggml_new_tensor_3d(c,GGML_TYPE_MXFP4,embd,embd,experts),
            ggml_new_tensor_3d(c,GGML_TYPE_MXFP4,embd,embd,experts),
            ggml_new_tensor_3d(c,GGML_TYPE_MXFP4,embd,embd,experts),
            ggml_new_tensor_2d(c,GGML_TYPE_F32,embd,experts),
            ggml_new_tensor_2d(c,GGML_TYPE_F32,embd,experts),
            ggml_new_tensor_2d(c,GGML_TYPE_F32,embd,experts),
            ggml_new_tensor_2d(rctx,GGML_TYPE_F32,embd,experts),
            ggml_new_tensor_1d(rctx,GGML_TYPE_F32,experts),
        };
        ggml_context * meta = nullptr;
        gguf_init_params params{true,&meta};
        gguf_context * gguf = gguf_init_from_file(model.c_str(),params);
        require(gguf != nullptr && meta != nullptr,"GGUF metadata load failed");
        const std::string base = "blk." + std::to_string(layer) + ".";
        std::array<spec,8> specs{
            get_spec(gguf,meta,tensors[0],base+"ffn_gate_exps.weight",GGML_TYPE_MXFP4,{embd,embd,experts}),
            get_spec(gguf,meta,tensors[1],base+"ffn_up_exps.weight",GGML_TYPE_MXFP4,{embd,embd,experts}),
            get_spec(gguf,meta,tensors[2],base+"ffn_down_exps.weight",GGML_TYPE_MXFP4,{embd,embd,experts}),
            get_spec(gguf,meta,tensors[3],base+"ffn_gate_exps.bias",GGML_TYPE_F32,{embd,experts}),
            get_spec(gguf,meta,tensors[4],base+"ffn_up_exps.bias",GGML_TYPE_F32,{embd,experts}),
            get_spec(gguf,meta,tensors[5],base+"ffn_down_exps.bias",GGML_TYPE_F32,{embd,experts}),
            get_spec(gguf,meta,tensors[6],base+"ffn_gate_inp.weight",GGML_TYPE_F32,{embd,experts}),
            get_spec(gguf,meta,tensors[7],base+"ffn_gate_inp.bias",GGML_TYPE_F32,{experts}),
        };
        ggml_free(meta); gguf_free(gguf);
        size_t bytes_total = 0;
        for (const auto & item : specs) bytes_total += item.bytes;
        require(bytes_total == 1697956352u, "layer byte inventory changed");
        storage.buffer = ggml_backend_alloc_ctx_tensors_from_buft(
            c,ggml_backend_dev_buffer_type(dev));
        require(storage.buffer != nullptr, "canonical layer allocation failed");
        router_storage.buffer = ggml_backend_alloc_ctx_tensors_from_buft(rctx,ggml_backend_get_default_buffer_type(route));
        require(router_storage.buffer != nullptr,"canonical router allocation");
        ggml_backend_buffer_set_usage(storage.buffer,GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
        ggml_backend_buffer_set_usage(router_storage.buffer,GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
        const int fd = open(model.c_str(),O_RDONLY|O_CLOEXEC);
        require(fd >= 0, "cannot open canonical GGUF file");
        const size_t model_size = std::filesystem::file_size(model);
        for (const auto & item : specs) load_exact(fd,item,model_size);
        close(fd);
        ggml_backend_synchronize(backend.value);
        std::vector<std::string> rendered_rows;
        bool pass = true;
        int numeric_rows = 0;
        int masked_rows = 0;
        for (const auto & phase : phases) {
            const auto row = replay(phase,rows,backend.value,route,tensors,reduction);
            const size_t expected_tokens = phase == "prefill0" || phase == "prefill128" ? 32 :
                phase == "prefill_final" ? 29 : 1;
            require(row.tokens == expected_tokens, "reference phase token count changed");
            pass &= row.routing_ids_equal && row.routing_weights.bitwise &&
                    row.ffn.bitwise && row.routing_weights.nonfinite == 0 &&
                    row.ffn.nonfinite == 0;
            rendered_rows.push_back(render(row));
            ++numeric_rows;
        }
        std::cout << "{\"schema\":\"c149-upstream-cpu-expert-layer-reference-v1\","
                  << "\"classification\":\"DIAGNOSTIC_UNQUALIFIED\","
                  << "\"layer\":" << layer << ",\"device\":\"" << device << "\","
                  << "\"router_backend\":\"" << router_name << "\",\"expert_backend\":\"CPU\",\"reduction_backend\":\"" << tail_name << "\",\"plan_assertions\":true,"
                  << "\"canonical_layer_bytes\":" << bytes_total << ","
                  << "\"all_bitwise\":" << (pass ? "true" : "false")
                  << ",\"numeric_rows\":" << numeric_rows << ",\"masked_rows\":" << masked_rows
                  << ",\"rows\":[";
        for (size_t i = 0; i < rendered_rows.size(); ++i)
            std::cout << (i ? "," : "") << rendered_rows[i];
        std::cout << "]}\n";
        return pass ? 0 : 1;
    } catch (const std::exception & exc) {
        std::cerr << "C7_REFERENCE_FAIL: " << exc.what() << '\n';
        return 1;
    }
}

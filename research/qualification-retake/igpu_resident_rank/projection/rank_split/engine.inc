// Included only after the original input, manager, graph and route types have been defined.
#include "split_graph.inc"
#include <time.h>

namespace {
constexpr const char *split_names[] = {"Full", "Serial", "Free"};
constexpr const char *weighted_sha = "d80c7ba29c304d76099cf7dd28cfe58f365f919cc494ea247507614097c44a4b";
constexpr const char *ffn_sha = "6bc70d200ac08db00f6c3fa34098bd660d2ba4bc4c02368de319cbadf6167333";

uint64_t split_clock() {
    timespec t{};
    need(clock_gettime(CLOCK_MONOTONIC_RAW, &t) == 0, "split clock");
    return uint64_t(t.tv_sec)*1000000000 + uint64_t(t.tv_nsec);
}

void write_split(const fs::path &out, const json &row) {
    std::ofstream f(out);
    f << row.dump() << '\n';
    f.close();
    need(bool(f), "split receipt");
}

json check_split(SplitGraph &graph, const F &weighted, const F &gold, bool& exact) {
    const auto rows = graph.contributions();
    auto result = graph.output();
    json obs;
    auto compare = [&](const F &row, const float *expected) {
        need(row.size() == width, "rank extent");
        unsigned unequal=0, nonfinite=0;
        for (int i=0; i<width; ++i) {
            unequal += std::memcmp(row.data()+i, expected+i, sizeof(float)) != 0;
            nonfinite += !std::isfinite(row[i]);
        }
        if(unequal || nonfinite) exact=false;
        return json{{"unequal",unequal},{"nonfinite",nonfinite},
                    {"sha256",digest(row.data(),row.size()*sizeof(float))}};
    };
    for (int rank=0;rank<4;++rank) obs["weighted"].push_back(compare(rows[rank],weighted.data()+rank*width));
    obs["ffn"]=compare(result,gold.data());
    return obs;
}

void run_split(ggml_backend_t cpu, const Input &in, const I &physical,
               const fs::path &ref, const fs::path &out) {
    const auto file=out.parent_path()/"split.json";
    const char *rank_file=std::getenv("TESY_SPLIT_WEIGHTED");
    need(rank_file, "missing sealed rank source");
    const F weighted=read<float>(rank_file,4*width), gold=read<float>(ref/"ffn_moe_out.bin",width);
    need(digest(weighted.data(),weighted.size()*4)==weighted_sha && digest(gold.data(),gold.size()*4)==ffn_sha,
         "independent FFN and weighted anchors");
    json r={{"status","CHECKING_PARITY"},{"order",in.ids},{"physical",physical},{"generations",gens},
            {"weighted_sha256",weighted_sha},{"ffn_sha256",ffn_sha},{"threads",8}};
    const json expected={{"x",digest(in.x.data(),in.x.size()*4)},
        {"logical",digest(in.ids.data(),in.ids.size()*4)},{"physical",digest(physical.data(),physical.size()*4)},
        {"mix",digest(in.weights.data(),in.weights.size()*4)}};
    auto verify_inputs=[&](SplitGraph &graph,int mode,const float *free_row) {
        auto ideal=expected;
        if(mode==2) ideal["free_e28"]=digest(free_row,width*4);
        auto observed=graph.input_sha256();
        return json{{"exact",observed==ideal},{"observed",observed},{"expected",ideal}};
    };
    std::array<std::unique_ptr<SplitGraph>,3> graphs;
    bool exact=true;
    for (int i=0;i<3;++i) {
        graphs[i]=std::make_unique<SplitGraph>(cpu,split_names[i],in,physical,weighted);
        auto &inputs=r["inputs"][split_names[i]];
        inputs["initial"]=verify_inputs(*graphs[i],i,weighted.data());
        if(!inputs["initial"]["exact"].get<bool>()) {
            r["status"]="FAIL_INITIAL_INPUT_IDENTITY";write_split(file,r);return;
        }
        graphs[i]->execute();
        inputs["after_parity"]=verify_inputs(*graphs[i],i,weighted.data());
        if(!inputs["after_parity"]["exact"].get<bool>()) {
            r["status"]="FAIL_PARITY_INPUT_LIFETIME";write_split(file,r);return;
        }
        r["parity"][split_names[i]]=check_split(*graphs[i],weighted,gold,exact);
    }
    if(!exact) {
        r["status"]="NO_GO_CROSS_SHAPE_EXACTNESS";write_split(file,r);return;
    }
    // The real three trailing ranks must survive substituting e24 for the free e28 row.
    {
        F wrong(weighted.begin()+width,weighted.begin()+2*width);
        SplitGraph fault(cpu,"Free",in,physical,wrong);
        r["negative_inputs_before"]=verify_inputs(fault,2,wrong.data());
        fault.execute();
        r["negative_inputs_after"]=verify_inputs(fault,2,wrong.data());
        if(!r["negative_inputs_before"]["exact"].get<bool>() || !r["negative_inputs_after"]["exact"].get<bool>()) {
            r["status"]="FAIL_NEGATIVE_INPUT_LIFETIME";write_split(file,r);return;
        }
        bool same=true;
        auto seen=check_split(fault,weighted,gold,same);
        r["negative"]=seen;
        bool detected=!same && seen["weighted"][0]["unequal"]>0 && seen["ffn"]["unequal"]>0 &&
                      seen["weighted"][0]["sha256"]==seen["weighted"][1]["sha256"] && seen["ffn"]["nonfinite"]==0;
        for(int i=1;i<4;++i) detected=detected && seen["weighted"][i]["unequal"]==0;
        if(!detected) {r["status"]="FAIL_NEGATIVE_NOT_DETECTED";write_split(file,r);return;}
    }
    for(int i=0;i<3;++i) {
        auto &graph=graphs[i];
        graph->execute();
        r["warmup"][split_names[i]]=check_split(*graph,weighted,gold,exact);
        r["inputs"][split_names[i]]["after_warmup"]=verify_inputs(*graph,i,weighted.data());
        if(!r["inputs"][split_names[i]]["after_warmup"]["exact"].get<bool>()) exact=false;
    }
    if(!exact){r["status"]="FAIL_WARMUP_EXACTNESS";write_split(file,r);return;}
    // No GET, allocation or comparison runs inside the primary interval.
    r["timings"]=json::array();
    std::array<int,3> checks{};
    for(int block=0;block<2;++block) {
        for(int rep=0;rep<7;++rep) {
            for(int j=0;j<3;++j) {
                const int i=block ? 2-j : j;
                const auto begin=split_clock();
                graphs[i]->execute();
                const auto end=split_clock();
                need(end>begin,"positive execution interval");
                auto obs=check_split(*graphs[i],weighted,gold,exact);
                r["timings"].push_back({{"block",block},{"rep",rep},{"mode",split_names[i]},
                                         {"start_ns",begin},{"end_ns",end}});
                auto inputs=verify_inputs(*graphs[i],i,weighted.data());
                if(inputs["exact"].get<bool>()) {
                    ++checks[i];
                } else {
                    exact=false; r["failed_inputs"]=inputs;
                }
                if(!exact) {
                    r["status"]="FAIL_TIMED_EXACTNESS";r["failure"]=obs;write_split(file,r);return;
                }
            }
        }
    }
    r["timed_input_checks"]=checks;
    r["status"]="PASS_RESIDENT_RANK_SPLIT_EXACT_TIMINGS";
    write_split(file,r);
}
}

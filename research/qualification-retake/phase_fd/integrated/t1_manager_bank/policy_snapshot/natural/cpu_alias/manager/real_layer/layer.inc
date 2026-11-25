/*TILE_FUNCTION*/
static json evaluate(const fs::path &p,const fs::path &output,ggml_backend_ptr &backend,
                     Inputs &in,std::array<ggml_tensor*,6> &t,Audit &observed) {
    observed.mmids.clear();observed.wave_ids.clear();observed.masks.clear();
    observed.seen_ids.fill(0);observed.seen_masks.fill(0);
    for(auto &a:observed.seen_mm)a.fill(0);
    const auto ids=tile(in.ids,4);
    std::copy(ids.begin(),ids.end(),observed.logical.begin());
    const std::set<int> active(ids.begin(),ids.end());
    const int count=first==32?5:4;
    need(active==std::set<int>(selected.begin(),selected.begin()+count),"tile rank union");
    /*CANONICAL_GRAPH*/
    const auto found=values<float>(out);
    const auto reference=tile(read<float>(p/"ffn_moe_out-0.bin",all*width),width);
    const auto filename="tile"+std::to_string(first)+".f32";
    {std::ofstream f(output/filename,std::ios::binary);
     need(bool(f.write(reinterpret_cast<const char*>(found.data()),found.size()*sizeof(float))),"tile write");}
    size_t unequal=0;bool finite=true;
    need(found.size()==size_t(width*nt) && found.size()==reference.size(),"tile shape");
    for(size_t i=0;i<found.size();++i){
        finite=finite && std::isfinite(found[i]) && std::isfinite(reference[i]);
        unequal+=std::memcmp(&found[i],&reference[i],sizeof(float))!=0;
    }
    need(complete(observed) && !observed.invalid && finite,"invalid consumer coverage or nonfinite");
    need((unequal!=0)==(state.mode=="WRONG" && first==96),"FFN expected bit verdict");
    return {{"first",first},{"unequal",unequal},{"finite",finite},{"mmid_nodes",24},
            {"bindings",bindings(*observed.layer)}};
}
static json run(const fs::path &p,const std::string &mode,const fs::path &output) {
    need(mode=="COPY" || mode=="ALIAS" || mode=="WRONG","arm");
    need(std::getenv("TESY_CPU_WAVE_SKIP_PARKED") && std::string(std::getenv("TESY_CPU_WAVE_SKIP_PARKED"))=="1",
         "parked path");
    state.mode=mode;
    ggml_backend_ptr backend(ggml_backend_cpu_init());need(bool(backend),"CPU init");
    ggml_backend_cpu_set_n_threads(backend.get(),8);
    auto in=routing(p,backend.get());
    Arena arena;state.base=arena.base;
    /*ORIGINAL_REGISTRATION*/
    state.mgr=&manager;state.audit=&observed;observed.layer=manager.layer(0);
    reset_views(meta.get(),manager,observed,t);
    ggml_backend_buffer_ptr biasmem(ggml_backend_alloc_ctx_tensors(biases.get(),backend.get()));need(bool(biasmem),"bias buffers");
    for(int k=0;k<3;++k)put(t[3+order[k]],read<float>(p/(std::string(roles[order[k]])+".bias"),width*128));
    /*PINNED_STORE_INDEX*/
    const int fd=store.data.descriptor();
    const auto stat=fd_identity(fd);
    need(stat==info.at("pack_identity") && (fcntl(fd,F_GETFL)&O_DIRECT) &&
         window%store.data.offset_alignment()==0 && 4096%store.data.memory_alignment()==0,"verified aligned store FD");
    json tiles=json::array(),moves=json::array();
    for(int i=0;i<3;++i){
        first=32+32*i;
        tiles.push_back(evaluate(p,output,backend,in,t,observed));
        if(i<2)moves.push_back(handover(manager,i+1));
    }
    {std::lock_guard<std::mutex> lock(manager.mtx);
     state.held.fill(0);
     need(!manager.load_failed && manager.workers.size()==4 && manager.q_demand.empty() &&
          manager.stats.n_store_loads==13 && state.reads==5 && state.returned==5*window &&
          state.copies==(mode=="COPY"?16*window:0) && fd_identity(fd)==stat,"final work or store identity");}
    audit=nullptr; state.audit=nullptr;
    return {{"mode",mode},{"router_positions",all},{"tiles",tiles},{"transitions",moves},{"source_reads",state.reads.load()},
            {"source_bytes",state.returned.load()},{"copy_bytes",state.copies.load()},{"pack_stat",stat},{"native_publications",13},
            {"providers",{{"cpu",provider(reinterpret_cast<void *>(&ggml_backend_cpu_init))},
                          {"base",provider(reinterpret_cast<void *>(&ggml_backend_sched_graph_compute))}}}};
}
int main(int argc,char **argv) {
    try {
        need(argc==4 && sysconf(_SC_PAGESIZE)==4096,"CLI/page size");
        fs::path out=argv[3];need(fs::create_directory(out),"exclusive arm output");
        auto result=run(argv[1],argv[2],out);result["joined_workers"]=4;
        result["status"]="PASS_C291_CPU0_ALIAS_TILES";std::cout<<result.dump()<<'\n';return 0;
    } catch(const std::exception &e){std::cerr<<"FAIL_C291_CPU0_ALIAS "<<e.what()<<'\n';return 1;}
}

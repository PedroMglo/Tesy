#pragma once
// Called once after storage allocation, before the measured layer's routing is consumed.
static void populate_seed(Audit &a) {
    auto &manager=*a.manager;
    auto &layer=*a.layer;
    std::unique_lock<std::mutex> lock(manager.mtx);
    need(manager.workers.empty() && layer.expert_slot.empty() && manager.q_demand.empty(),"expected cold seed");
    manager.start_workers_locked();
    for (int e=0;e<40;++e) {
        manager.reserve_slot_locked(layer,e,e);
        manager.q_demand.push_back({&layer,e,e,layer.slot_gen[e]});
    }
    manager.cv_work.notify_all();
    manager.cv_done.wait(lock,[&]{ return manager.load_failed ||
        std::all_of(layer.slot_state.begin(),layer.slot_state.end(),[](auto s){return s==LLAMA_MOE_STREAM_SLOT_RESIDENT;}); });
    need(!a.invalid && !manager.load_failed && manager.q_demand.empty() && manager.stats.n_store_loads==40,
         "seed delivery/queue incomplete");
    for (int e=0;e<40;++e) {
        need(layer.slot_expert[e]==e && layer.expert_slot.at(e)==e && layer.slot_gen[e]==1 &&
             !layer.slot_claimed[e] && layer.slot_last_use[e]==uint64_t(e+1) && !layer.route_hotness[e] &&
             a.reads[e]==1 && a.copies[e]==3,"seed identity/generation/age");
        if(e>=35) policy.backing[e-35].resize(3*slab);
        for (int k=0;k<3;++k) {
            const auto *src=a.addresses[k]+size_t(e)*slab;
            need(digest(src,slab)==policy.component_sha[e][k],"wrong seeded weight payload");
            ++policy.seed_verified;
            if(e<35) continue;
            auto *dst=policy.backing[e-35].data()+k*slab;
            std::memcpy(dst,src,slab);
            need(digest(dst,slab)==policy.component_sha[e][k],"wrong backup payload");
            ++policy.bank_verified;
        }
        if(e>=35) policy_backed_experts[e]=true;
    }
    policy_use_backing=policy.mode!="R0";
}

// Descriptors and already published active slots are stable while timed graph evaluation
// is synchronously paused on the only graph thread and the four workers are idle.
static void policy_after_remap(Audit &a) {
    if (policy.mode!="MUTANT") return;
    need(!policy.swapped && a.manager->q_demand.empty() && !a.manager->load_failed,"unsafe mutation boundary");
    for (int e : selected) {
        const int s=a.layer->expert_slot.at(e);
        need(s>=0 && s<40 && a.layer->slot_state[s]==LLAMA_MOE_STREAM_SLOT_RESIDENT &&
             !a.layer->slot_claimed[s] && a.layer->slot_gen[s]==2,"unpublished mutation operand");
    }
    auto *left=a.addresses[0]+size_t(a.slots[45])*slab;
    auto *right=a.addresses[0]+size_t(a.slots[49])*slab;
    need(left!=right && digest(left,slab)==policy.component_sha[45][0] &&
         digest(right,slab)==policy.component_sha[49][0],"mutation addressing");
    std::swap_ranges(left,left+slab,right);
    policy.swapped=true;
}

static void check_weight(Audit &a,ggml_tensor *source,int k) {
    for (int e : selected) {
        const auto *base=static_cast<const uint8_t *>(source->data);
        const auto *ptr=base+size_t(a.slots[e])*source->nb[2];
        if(digest(ptr,slab)!=policy.component_sha[e][k]) policy.mismatches.emplace_back(e,component_roles[k]);
        ++policy.weights_checked;
    }
}

static void check_bias(Audit &a,ggml_tensor *node,int w,int k) {
    auto *bias=node->src[1];
    need(node->op==GGML_OP_ADD_ID && node->src[2]==policy.logical_ids && bias==policy.biases[k] &&
         bias->type==GGML_TYPE_F32 && bias->nb[1]==width*sizeof(float) &&
         ggml_backend_sched_get_tensor_backend(a.sched,node)==a.cpu,"bias consumer identity");
    if (w==0) {
        std::array<int32_t,128> ids;
        ggml_backend_tensor_get(node->src[2],ids.data(),0,sizeof(ids));
        need(ids==a.logical,"bias indices differ from router");
        for(int e : selected) {
            const auto *p=static_cast<const uint8_t *>(bias->data)+size_t(e)*bias->nb[1];
            need(digest(p,width*sizeof(float))==policy.component_sha[e][k+3],"wrong logical bias");
            ++policy.biases_checked;
        }
    }
    ++policy.seen_bias[w][k];
}

static json finish_policy(Audit &a,const std::vector<float> &found,const std::vector<float> &gold) {
    need(found.size()==gold.size() && found.size()==nt*width,"wrong full FFN row count");
    int unequal=0;
    for(size_t i=0;i<found.size();++i) {
        need(std::isfinite(found[i]) && std::isfinite(gold[i]),"nonfinite FFN");
        if(std::memcmp(&found[i],&gold[i],sizeof(float))) ++unequal;
    }
    const bool mutant=policy.mode=="MUTANT";
    std::sort(policy.mismatches.begin(),policy.mismatches.end());
    const std::vector<std::pair<int,std::string>> expected = mutant ?
        std::vector<std::pair<int,std::string>>{{45,"gate"},{49,"gate"}} : std::vector<std::pair<int,std::string>>{};
    need(policy.mismatches==expected && policy.swapped==mutant,"weight mismatch count/identity");
    need(policy.weights_checked==15 && policy.biases_checked==15 &&
         policy.seed_verified==120 && policy.bank_verified==15,"weight/bias coverage");
    for(auto &waves:policy.seen_bias) for(auto count:waves) need(count==1,"missing/duplicate bias node");
    need(mutant ? unequal>0 : unequal==0,"full FFN differs from registered expectation");
    json binds=json::array();
    std::vector<int> victims;
    for (int e:selected) {binds.push_back({e,a.slots[e],a.generations[e]});victims.push_back(a.slots[e]);}
    // A seeded slot's original expert ID equals its physical index.
    std::sort(victims.begin(),victims.end());
    for(int i=0;i<5;++i) need(victims[i]==(policy_use_backing?35:0)+i,"wrong policy victims");
    auto &layer=*a.layer;
    for(int s=0;s<40;++s) {
        const bool replaced=std::binary_search(victims.begin(),victims.end(),s);
        need(layer.slot_state[s]==LLAMA_MOE_STREAM_SLOT_RESIDENT && !layer.slot_claimed[s] &&
             (replaced || layer.slot_expert[s]==s) && layer.slot_gen[s]==(replaced?2U:1U) &&
             layer.expert_slot.at(layer.slot_expert[s])==s,"terminal full pool");
    }
    need(pack_identity(a.fd,policy.pack_path,policy.pack_stat)==policy.public_fd_stat,"pack FD changed");
    return {{"selected_bindings",binds},{"evicted_experts",victims},{"backing_enabled",policy_use_backing},
            {"backing_experts",{35,36,37,38,39}},{"backing_bytes",15*slab},{"seed_roles_verified",policy.seed_verified},
            {"backing_roles_verified",policy.bank_verified},{"selected_weight_roles",policy.weights_checked},
            {"selected_bias_roles",policy.biases_checked},{"weight_mismatches",policy.mismatches},
            {"ffn_unequal",unequal},{"bias_nodes_observed",24},{"fd_stat",policy.public_fd_stat},{"fd_odirect",true}};
}

// Original R0 training-data capture only. No learned weights or byte forecasting.
#define main original_native_entrypoint
#include "block_native_run.cpp"
#undef main
#include "llama-context.h"
#include "chat.h"
#include "common.h"
#include <ctime>
#include "expert_activation_estimator.h"

double seconds(clock_type::time_point a,clock_type::time_point b) {
    return std::chrono::duration<double>(b-a).count();
}

struct corpus_bank {
    static constexpr int cap=128;
    ggml_backend_t backend=nullptr;
    std::array<std::unique_ptr<activation_estimator>,23> estimators;
    std::vector<float> score_inputs,labels;
    std::vector<int> router_ids=std::vector<int>(cap*23*4);
    std::array<uint8_t,cap*23> input_seen{},label_seen{};
    size_t input_count=0,label_count=0;
    double native_feature_cost_us=0;
    explicit corpus_bank(llama_model *model):score_inputs(cap*23*128),labels(cap*23*128) {
        backend=ggml_backend_cpu_init();check(backend,"corpus CPU backend");ggml_backend_cpu_set_n_threads(backend,8);
        for(int i=0;i<23;i++)estimators[i]=std::make_unique<activation_estimator>(model,i+2,backend);
    }
    ~corpus_bank(){for(auto &p:estimators)p.reset();if(backend)ggml_backend_free(backend);}
    static size_t index(int call,int target) {
        check(call>=1&&call<=cap&&target>=2&&target<=24,"corpus row/layer bound");return size_t(call-1)*23+target-2;
    }
    void feature(ggml_tensor *norm,int source,int call) {
        const size_t i=index(call,source+2);check(!input_seen[i],"duplicate corpus feature");
        check(norm->op==GGML_OP_MUL&&norm->src[0]&&norm->src[0]->op==GGML_OP_RMS_NORM,"source raw dependency changed");
        auto *raw=norm->src[0]->src[0];check(raw&&raw->type==GGML_TYPE_F32&&raw->ne[0]==2880&&raw->ne[1]==1&&ggml_is_contiguous(raw)&&raw->buffer&&ggml_backend_buffer_is_host(raw->buffer),"corpus feature shape/lifetime/device");
        const auto begin=clock_type::now();std::array<float,2880> x{};ggml_backend_tensor_get(raw,x.data(),0,x.size()*sizeof(float));
        for(float f:x)check(std::isfinite(f),"nonfinite corpus residual");
        auto scores=estimators.at(source)->score(x.data());std::copy(scores.begin(),scores.end(),score_inputs.begin()+i*128);
        native_feature_cost_us+=std::chrono::duration<double,std::micro>(clock_type::now()-begin).count();input_seen[i]=1;input_count++;
    }
    void label(ggml_tensor *t,int target,int call) {
        const size_t i=index(call,target);check(!label_seen[i],"duplicate corpus label");
        check(t->type==GGML_TYPE_F32&&t->ne[0]==128&&t->ne[1]==1&&ggml_is_contiguous(t)&&t->buffer&&ggml_backend_buffer_is_host(t->buffer),"true label shape/device");
        auto *out=labels.data()+i*128;ggml_backend_tensor_get(t,out,0,128*sizeof(float));
        for(int k=0;k<128;k++)check(std::isfinite(out[k]),"nonfinite true label");label_seen[i]=1;label_count++;
    }
    void verify_routes(runtime &r,int call) {
        auto routed=r.last_routes();
        for(int target=2;target<=24;target++) {
            auto i=index(call,target);check(input_seen[i]&&label_seen[i],"corpus feature/label coverage absent");
            std::array<int,128> rank{};for(int j=0;j<128;j++)rank[j]=j;
            const float *y=labels.data()+i*128;std::stable_sort(rank.begin(),rank.end(),[&](int a,int b){return y[a]>y[b];});
            std::vector<int> expected(rank.begin(),rank.begin()+4);std::sort(expected.begin(),expected.end());
            auto actual=routed.at(target);std::sort(actual.begin(),actual.end());check(actual==expected,"true biased scores do not match authoritative router");
            std::copy(actual.begin(),actual.end(),router_ids.begin()+i*4);
        }
    }
};
struct corpus_observer {runtime *r=nullptr;corpus_bank *bank=nullptr;bool active=false;};
bool observe_corpus(ggml_tensor *t,bool ask,void *opaque) {
    auto &o=*static_cast<corpus_observer *>(opaque);if(o.r)observe_rows(t,ask,&o.r->rows);
    int layer=-1,label=-1;const std::string name=ggml_get_name(t);
    const bool feature=o.active&&sscanf(name.c_str(),"attn_norm-%d",&layer)==1&&name=="attn_norm-"+std::to_string(layer)&&layer>=0&&layer<=22;
    const bool truth=o.active&&sscanf(name.c_str(),"ffn_moe_probs-%d",&label)==1&&name=="ffn_moe_probs-"+std::to_string(label)&&label>=2&&label<=24;
    if(ask)return feature||truth;
    if(feature)o.bank->feature(t,layer,int(o.r->model->moe_stream()->window.call.load()));
    if(truth)o.bank->label(t,label,int(o.r->model->moe_stream()->window.call.load()));
    return true;
}
struct corpus_input {common_chat_params chat;std::vector<llama_token> ids;};
corpus_input render_corpus(llama_model *model,const json &task) {
    auto templates=common_chat_templates_init(model,"","","");common_chat_templates_inputs in;
    in.messages=common_chat_msgs_parse_oaicompat(task.at("messages"));in.reasoning_format=COMMON_REASONING_FORMAT_AUTO;
    in.chat_template_kwargs["reasoning_effort"]=R"("medium")";in.chat_template_kwargs["tesy_template_date"]=R"("2026-09-30")";
    std::tm date{};date.tm_year=126;date.tm_mon=8;date.tm_mday=30;in.now=std::chrono::system_clock::from_time_t(timegm(&date));
    auto chat=common_chat_templates_apply(templates.get(),in);check(chat.prompt.find("2026-09-30")!=std::string::npos&&chat.prompt.find("Reasoning: medium")!=std::string::npos,"corpus template identity");
    std::vector<llama_token> ids(chat.prompt.size()+4096);int n=llama_tokenize(llama_model_get_vocab(model),chat.prompt.data(),chat.prompt.size(),ids.data(),ids.size(),false,true);
    check(n>0&&n<=int(ids.size()),"corpus official tokenization");ids.resize(n);return {std::move(chat),std::move(ids)};
}
int main(int argc,char **argv){try{
    if(argc==2&&std::string(argv[1])=="--self-test") {
        check(corpus_bank::index(1,2)==0&&corpus_bank::index(33,2)==32*23&&corpus_bank::index(128,24)==128*23-1,"128-row corpus position mapping");
        for(auto key:std::vector<std::pair<int,int>>{{0,2},{129,2},{1,1},{1,25}}){bool rejected=false;try{corpus_bank::index(key.first,key.second);}catch(const std::exception&){rejected=true;}check(rejected,"corpus invalid row/layer accepted");}
        corpus_observer o;o.active=true;ggml_tensor t{};
        for(const char *name:{"attn_norm-0","attn_norm-22","ffn_moe_probs-2","ffn_moe_probs-24"}){ggml_set_name(&t,name);check(observe_corpus(&t,true,&o),"corpus real node not selected");}
        for(const char *name:{"attn_norm-23","attn_norm-0-future","ffn_moe_probs-25","ffn_moe_logits_biased-2"}){ggml_set_name(&t,name);check(!observe_corpus(&t,true,&o),"corpus noncanonical node selected");}
        o.active=false;ggml_set_name(&t,"attn_norm-0");check(!observe_corpus(&t,true,&o),"prefix captured before admitted decode");
        check(size_t(128)*23*128*8+size_t(33)*vocab*4+23*1024*1024+2*1024*1024<=64*1024*1024,"corpus capture/workspace projection bound");
        std::this_thread::sleep_for(std::chrono::seconds(5));std::cout<<"PASS_MODEL_FREE_CORPUS_BOUNDARY\n";return 0;
    }
    if(argc==5&&std::string(argv[4])=="--render-training") {
        std::ifstream f(argv[2]);json tasks;f>>tasks;check(bool(f)&&tasks.is_array()&&tasks.size()==8,"exact8corpus tasks");
        llama_backend_init();auto mp=llama_model_default_params();mp.vocab_only=true;mp.n_gpu_layers=0;mp.use_extra_bufts=false;
        auto *model=llama_model_load_from_file(argv[1],mp);check(model,"vocab-only load");json out=json::object();
        for(const auto &task:tasks){auto v=render_corpus(model,task);const auto id=task.at("id").get<std::string>();check(!out.contains(id),"duplicate corpus ID");out[id]={{"ids",v.ids},{"rendered_prompt",v.chat.prompt},{"task",task},{"template_date","2026-09-30"},{"reasoning_effort","medium"},{"weights_loaded",false},{"forwards",0}};}
        check(!std::filesystem::exists(argv[3]),"vocabulary root reused");save(argv[3],out);std::this_thread::sleep_for(std::chrono::seconds(5));llama_model_free(model);llama_backend_free();return 0;
    }
    check(argc==7&&(std::string(argv[5])=="reference32"||std::string(argv[5])=="train128")&&std::string(argv[6])=="v1","usage MODEL OFFICIALFIXTURE CASE NEWROOT reference32|train128 v1");
    const bool reference=std::string(argv[5])=="reference32";std::ifstream f(argv[2]);json fixture;f>>fixture;check(bool(f),"fixture absent");const auto spec=fixture.at(argv[3]);
    const auto ids=spec.at("ids").get<std::vector<llama_token>>();check(ids.size()>=1800&&ids.size()<=2600,"corpus context range");for(int id:ids)check(id>=0&&id<vocab,"official ID invalid");
    const auto root=std::filesystem::path(argv[4]);check(std::filesystem::create_directory(root),"corpus root reused");
    for(const char *env:{"TESY_C262_LAYER_SPAN","TESY_C269_LAST_USE_ORDER","TESY_EXPERT_STORE_MANIFEST","TESY_C305_ARENA","TESY_C305_STAGE","TESY_C294_WINDOW"})check(!getenv(env),"corpus must be original R0/no movement/capture arena");
    corpus_observer o;runtime r(argv[1],observe_corpus,&o);o.r=&r;corpus_bank bank(r.model);o.bank=&bank;
    if(!reference){auto v=render_corpus(r.model,spec.at("task"));check(v.ids==ids&&v.chat.prompt==spec.at("rendered_prompt"),"task official rendered input diverges");}
    const int prefix=int(ids.size())-153;int pos=0;const auto prepare=clock_type::now();
    save(root/"prefix-progress.json",{{"required_prefix_positions",prefix},{"completed_positions",0}});
    while(pos<prefix){int n=std::min(256,prefix-pos);r.call({ids.begin()+pos,ids.begin()+pos+n},pos,false);pos+=n;save(root/"prefix-progress.json",{{"required_prefix_positions",prefix},{"completed_positions",pos}});}
    const auto prepared=clock_type::now();const auto initial=r.snapshot();auto row=r.call({ids.begin()+prefix,ids.end()},prefix,false);
    std::vector<float> full33;full33.reserve(size_t(33)*vocab);full33.insert(full33.end(),row.begin(),row.end());
    std::vector<int> winners{greedy(row.data())},consumed;bool eog=false;int n=0;std::vector<int> supplied;if(reference)supplied=spec.at("continuation_ids").get<std::vector<int>>();check(!reference||supplied.size()==32,"reference32 supplied IDs");
    const auto begin=clock_type::now();o.active=true;
    for(int i=0;i<(reference?32:128);i++) {
        const int token=reference?supplied[i]:greedy(row.data());
        if(!reference&&llama_vocab_is_eog(llama_model_get_vocab(r.model),token)){eog=true;break;}
        check(token>=0&&token<vocab,"native continuation ID");consumed.push_back(token);r.model->moe_stream()->window.call.store(i+1);
        row=r.call({token},int(ids.size())+i,false);bank.verify_routes(r,i+1);winners.push_back(greedy(row.data()));n++;
        if(i<32)full33.insert(full33.end(),row.begin(),row.end());
    }
    const auto end=clock_type::now();o.active=false;const auto final=r.snapshot();
    check(bank.input_count==size_t(n*23)&&bank.label_count==size_t(n*23),"corpus native capture coverage");bank.score_inputs.resize(size_t(n)*23*128);bank.labels.resize(size_t(n)*23*128);
    binary(root/"early-native-scores.f32",bank.score_inputs);binary(root/"true-routing-scores.f32",bank.labels);binary(root/"first33.logits.f32",full33);
    bank.router_ids.resize(size_t(n)*23*4);
    save(root/"actual-router-ids.json",bank.router_ids);
    save(root/"result.json",{{"schema","task-separated-original-R0-score-corpus-v1"},{"case",argv[3]},{"model_original",true},{"profile","R0"},{"mode",0},{"input_ids",ids},{"consumed_native_ids",consumed},{"native_argmax_ids",winners},{"capture_cap",reference?32:128},{"decode_calls",n},{"terminal_eog",eog},{"reference_supplied",reference},{"source_horizon",2},{"CPU_layers",{2,24}},{"CPU_backend_threads",8},{"original_native_feature_cost_us",bank.native_feature_cost_us},{"feature_rows",bank.input_count},{"true_label_rows",bank.label_count},{"byte_forecasting",false},{"trained_weights",false},{"sampling_policy","native-greedy-temp0-seed42"},{"reasoning_effort","medium"},{"template_date","2026-09-30"},{"prefix_s",seconds(prepare,prepared)},{"capture_decode_s",seconds(begin,end)},{"initial",initial},{"final",final},{"scope","Training-data/original-router labels only; partial native prefix cap/EOS, no final task grading/useful throughput or productiontime claim"}});
    std::cout<<"PASS_ORIGINAL_R0_SCORE_CORPUS\n";return 0;
}catch(const std::exception &e){std::cerr<<"CORPUS_FAIL "<<e.what()<<"\n";return 1;}}

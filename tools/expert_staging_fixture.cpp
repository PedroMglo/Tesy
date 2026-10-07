#define TESY_C305_STAGE_TESTING
#include "llama-moe-stream.h"
#include "c305-cpu-stage.h"
#include "c291-expert-store.h"
#include "llama-impl.h"
#include "ggml-cpu.h"
#include <functional>
#include <iostream>
#include <thread>
#include <fstream>
using json=nlohmann::json;
using S=c305_cpu_stage;
void must(bool good,const char *why){if(!good)throw std::runtime_error(why);}
void rejects(const std::function<void()>&fn){bool bad=false;try{fn();}catch(const std::exception&){bad=true;}must(bad,"fault was accepted");}
ssize_t io_error(int,void*,size_t,off_t){errno=EIO;return -1;}
ssize_t io_short(int,void*,size_t,off_t){return 8;}
int interrupted=0;
ssize_t io_interrupt(int fd,void *p,size_t n,off_t off){if(interrupted++==0){errno=EINTR;return -1;}return pread(fd,p,n,off);}
void queues(){
 S s;s.journal_enabled=true;s.begin(false);must(s.request(1,2,7)==-1,"OFF issued work");s.begin(true);
 int i=s.request(1,2,7);auto t=s.entries[i].ticket;
 must(s.request(1,2,7)==i&&s.stats.deduplicated==1,"duplicate not deduplicated");
 rejects([&]{s.request(1,2,128);});rejects([&]{s.request(0,2,3);});rejects([&]{s.request(33,2,3);});rejects([&]{s.request(1,25,3);});rejects([&]{s.demand(-1,1);});rejects([&]{s.cancel(10);});
 must(!s.demand(i,t)&&s.idle(),"QUEUED demand cannot bypass primary priority");
 for(int e=0;e<4;e++)s.request(1,2,e);
 for(int k=0;k<3;k++)s.start(s.next());must(s.next()==-1&&s.speculative_running()==3,"one demand worker not reserved");
 i=0;t=s.entries[i].ticket;rejects([&]{s.claim(i,t);});rejects([&]{s.demand(i,t+1);});
 s.cancel(i);must(s.entries[i].status==S::READING&&s.entries[i].expired,"cancellation freed nonpreemptible IO");
 s.complete(i,t,true);must(s.entries[i].status==S::EMPTY,"late cancelled bytes resurrected");
 for(int k=0;k<S::slots;k++)if(s.entries[k].status==S::READING)s.complete(k,s.entries[k].ticket,true);
 s.finish();must(s.idle(),"finish left queued/ready bytes");s.begin(true);
 i=s.request(2,13,8);t=s.start(i);must(s.demand(i,t),"true demand did not attach");
 s.cancel(i);must(!s.entries[i].expired,"expiry cancelled attached truth");s.complete(i,t,true);s.claim(i,t);
 rejects([&]{s.begin(true);});rejects([&]{s.release(i,t+1);});s.finish();must(s.entries[i].status==S::CONSUMING,"finish freed consumer buffer");
 s.release(i,t);rejects([&]{s.bytes(i,0,t);});must(s.idle(),"consumer lifetime not released");
 s.begin(true);for(int e=0;e<10;e++)must(s.request(1,24,e)>=0,"capacity underfilled");must(s.request(1,24,10)<0&&s.stats.no_capacity==1,"arena overflow accepted");
 int32_t ids[]={0,1,2,3};s.expire(1,24,ids,4);must(s.entries[4].status==S::EMPTY,"wrong predictions survived true router");s.finish();
 s.begin(true);i=s.request(3,2,1);t=s.start(i);s.complete(i,t,false);must(s.idle()&&s.stats.errors==1,"error published readiness");rejects([&]{s.complete(i,t,true);});
 for(int kind=0;kind<7;kind++)must(!tesy_store_completion_valid(kind==0,kind!=1,7,kind==2?8:7,4,kind==3?5:4,kind==4?LLAMA_MOE_STREAM_SLOT_RESIDENT:kind==5?LLAMA_MOE_STREAM_SLOT_EMPTY:LLAMA_MOE_STREAM_SLOT_LOADING,kind!=6),"stale/cancelled primary completion accepted");
}
int main(int argc,char **argv){try{
 queues();if(argc==2&&std::string(argv[1])=="--queue-test"){std::cout<<"PASS_QUEUE_SCOPE_DUPLICATE_PRIORITY_STALE_CANCEL_LATE_LIFETIME_CAPACITY_ERROR\n";return 0;}
 must(argc==4,"usage MODEL OFFSET_FIXTURE NEW_RESULT");std::ifstream f(argv[2]);json meta;f>>meta;must(bool(f),"offset fixture absent");
 std::array<std::array<uint64_t,3>,36> offsets{};
 for(int l=2;l<=24;l++)for(int k=0;k<3;k++)offsets[l][k]=meta.at("offsets").at(l).at(k).get<uint64_t>();
 must(tesy_expert_store::identity(argv[1])==meta.at("model_stat"),"canonical model stat changed");
 S bytes(argv[1],offsets);bytes.begin(true);std::vector<uint8_t> canonical(S::slab);json checks=json::array();
 for(auto selected:std::array<std::pair<int,int>,3>{{{2,0},{13,63},{24,127}}}){
  const int l=selected.first,e=selected.second;int i=bytes.request(1,l,e);auto ticket=bytes.start(i);
  if(l==2)bytes.read(i,ticket,io_interrupt);else bytes.read(i,ticket);
  bytes.complete(i,ticket,true);must(bytes.demand(i,ticket),"fixture demand failed");bytes.claim(i,ticket);
  for(int k=0;k<3;k++){bytes.reader.read(canonical.data(),S::slab,offsets[l][k]+uint64_t(e)*S::slab);must(!memcmp(canonical.data(),bytes.bytes(i,k,ticket),S::slab),"original direct bytes mismatch");}
  bytes.release(i,ticket);checks.push_back({{"layer",l},{"expert",e},{"components",3},{"logical_bytes",3*S::slab}});
 }
 must(interrupted==4,"EINTR not retried before three components");
 for(auto fn:{io_error,io_short}){int i=bytes.request(2,2,1);auto t=bytes.start(i);rejects([&]{bytes.read(i,t,fn);});bytes.complete(i,t,false);}
 bytes.finish();must(bytes.idle(),"byte fixture lifetime failed");
 // Actual manager workers, priority queue, claimed primary generation, and shutdown.
 auto ctx=ggml_init({1024*1024,nullptr,true});must(ctx,"cache fixture metadata");
 json worker;
 {
  llama_moe_stream mgr(36,40,4,true);
  for(int k=0;k<3;k++){auto *tensor=ggml_new_tensor_3d(ctx,GGML_TYPE_MXFP4,2880,2880,128);mgr.create_cache_tensor(2,ggml_backend_cpu_buffer_type(),tensor,0,offsets[2][k]);}
  mgr.alloc_bufs(false);mgr.files.emplace_back(new llama_file(argv[1],"rb",true));must(mgr.files[0]->has_direct_io(),"actual worker fd not direct");
  mgr.prediction_stage=std::make_unique<S>(argv[1],offsets);mgr.prediction_stage->journal_enabled=true;mgr.prediction_begin(true);
  {
   std::unique_lock<std::mutex> lk(mgr.mtx);auto &stage=*mgr.prediction_stage;auto *sl=mgr.layer(2);
   int i=stage.request(1,2,7);auto t=stage.start(i);lk.unlock();stage.read(i,t);lk.lock();stage.complete(i,t,true);
   mgr.window.call.store(1);mgr.reserve_slot_locked(*sl,7,0);mgr.enqueue_locked(sl,7,0,sl->slot_gen[0]);
   // Wrong guesses are pending alongside truth. Native worker must dequeue truth first.
   stage.request(1,2,8);mgr.start_workers_locked();mgr.cv_work.notify_all();
   must(mgr.cv_done.wait_for(lk,std::chrono::seconds(10),[&]{return mgr.load_failed||sl->slot_state[0]==LLAMA_MOE_STREAM_SLOT_RESIDENT;}),"real primary worker deadline");
   must(!mgr.load_failed&&stage.stats.consumed==1&&sl->slot_expert[0]==7&&sl->slot_gen[0]==1&&!sl->slot_claimed[0],"actual delivery ownership/commit failure");
   for(int k=0;k<3;k++){stage.reader.read(canonical.data(),S::slab,offsets[2][k]+7*S::slab);must(!memcmp(canonical.data(),sl->weights[k].cache->data,S::slab),"actual cache consumer mismatch");}
   // First producer was completed manually before dispatch. No speculative START
   // from the pending wrong request may precede the true consumer release.
   size_t release=stage.journal_count,start_wrong=stage.journal_count;
   for(size_t j=0;j<stage.journal_count;j++){auto ev=stage.journal[j];if(ev.kind==7&&ev.expert==7)release=j;if(ev.kind==2&&ev.expert==8)start_wrong=j;}
   must(release<start_wrong,"actual worker starved demand behind wrong queued read");
   worker={{"delivered_expert",7},{"primary_slot",0},{"primary_generation",1},{"native_workers",4},{"consumed",stage.stats.consumed},{"priority_verified",true}};
  }
  mgr.prediction_finish();must(mgr.prediction_stage->idle(),"real workers failed cancellation cleanup");
  // Destructor joins these same native workers; no dummy ownership or guard shim.
 }
 ggml_free(ctx);std::this_thread::sleep_for(std::chrono::seconds(5));
 must(!std::ifstream(argv[3]).good(),"fixture output reused");std::ofstream out(argv[3]);out<<json({{"status","PASS_NATIVE_STAGE_BYTES_QUEUE_WORKER_LIFETIME"},{"slice_checks",checks},{"worker",worker},{"full_model_loaded",false},{"original_weight_slices_read",true},{"transformer_forwards",0},{"memory_alignment",bytes.reader.memory_alignment()},{"offset_alignment",bytes.reader.offset_alignment()},{"fd_O_DIRECT",bool(fcntl(bytes.reader.descriptor(),F_GETFL)&O_DIRECT)},{"arena_bytes",bytes.entry_stride*bytes.slots},{"metadata_bytes",sizeof(bytes)}}).dump(2)<<'\n';must(bool(out),"fixture receipt lost");
 return 0;
}catch(const std::exception &e){std::cerr<<"STAGE_FIXTURE_FAIL "<<e.what()<<'\n';return 1;}}

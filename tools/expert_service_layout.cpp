// Lossless expert-local transport probe. Existing C211 is the byte witness, not changed.
#include "c210_direct_reader.h"
#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml-cuda.h"
#include "json.hpp"
#include <openssl/sha.h>
#include <array>
#include <atomic>
#include <chrono>
#include <fstream>
#include <iostream>
#include <thread>
#include <vector>
#include <cstring>
#include <mutex>
#include <condition_variable>
#include <memory>
using json=nlohmann::ordered_json;using Clock=std::chrono::steady_clock;
constexpr size_t slab=4406400, bias=11520, weights=3*slab;
void check(bool v,const char *m){if(!v)throw std::runtime_error(m);}
json fd_identity(int fd){struct stat st{};check(fstat(fd,&st)==0,"fd identity lost");return {{"dev",st.st_dev},{"inode",st.st_ino},{"size_bytes",st.st_size},{"mtime_s",st.st_mtim.tv_sec},{"mtime_ns",st.st_mtim.tv_nsec},{"ctime_s",st.st_ctim.tv_sec},{"ctime_ns",st.st_ctim.tv_nsec}};}
json read_json(const char *p){std::ifstream f(p);json j;f>>j;check(bool(f),"manifest missing");return j;}
void save(const char *p,const json&j){check(access(p,F_OK)!=0,"receipt already exists");std::ofstream f(p);f<<j.dump(2)<<'\n';check(bool(f),"receipt write failed");}
std::string hash(const void*p,size_t n){unsigned char out[32];SHA256(static_cast<const unsigned char*>(p),n,out);const char*h="0123456789abcdef";std::string s;for(auto b:out){s+=h[b>>4];s+=h[b&15];}return s;}
struct aligned_scratch {
 void *data=nullptr;size_t bytes=16*1024*1024;
 explicit aligned_scratch(size_t alignment){check(posix_memalign(&data,alignment,bytes)==0,"aligned scratch allocation");}
 ~aligned_scratch(){free(data);}
 aligned_scratch(const aligned_scratch&)=delete;
};
// Transport has one bounded16MiB staging buffer, reused across all reads.
// Witness read() retains its original8MiB/16MiB contract for individual components.
const uint8_t *transport(const tesy_witness::direct_reader &r,aligned_scratch&s,uint64_t off,size_t len,uint64_t &calls,uint64_t &request_bytes,tesy_witness::direct_reader::read_fn fn=::pread){
 r.validate_range(off,len);auto a=r.offset_alignment();uint64_t start=off-off%a,end=off+len;
 check(end<=UINT64_MAX-(a-1),"transport rounding overflow");uint64_t amount=((end+a-1)/a)*a-start;
 check(amount<=s.bytes&&amount<=uint64_t(INT64_MAX)-start,"transport bounded/off_t overflow");
 ssize_t n;do{n=fn(r.descriptor(),s.data,amount,off_t(start));}while(n<0&&errno==EINTR);
 ++calls;request_bytes+=amount;check(n>=0&&uint64_t(n)>=end-start,"direct short/failed transport read");
 return static_cast<const uint8_t*>(s.data)+(off-start);
}
void pack(const json &input,const char *model,const char *output,const char *receipt){
 tesy_witness::direct_reader src;src.open_file(model);size_t a=src.offset_alignment();
 check(input["experts"].size()<=128,"sample experts bound");
 const uint64_t weight_window=((weights+a-1)/a)*a,bias_window=((3*bias+a-1)/a)*a,stride=weight_window+bias_window;
 check(stride*input["experts"].size()<=2ull*1024*1024*1024,"sample pack bound");
 int fd=open(output,O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC|O_DIRECT,0600);check(fd>=0,"new direct pack open");
 aligned_scratch staging(src.memory_alignment());json index=input;index["pack_path"]=output;index["stride"]=stride;index["weight_window"]=weight_window;index["alignment"]=a;
 auto start=Clock::now();uint64_t logical=0;SHA256_CTX pack_hash;SHA256_Init(&pack_hash);
 try{for(size_t e=0;e<input["experts"].size();e++){
   memset(staging.data,0,stride);index["experts"][e]["pack_offset"]=e*stride;
   for(size_t k=0;k<6;k++){
     const auto &c=input["experts"][e]["components"][k];size_t len=c["size_bytes"];check(len==(k<3?slab:bias),"component size changed");
     const size_t relative=k<3?k*slab:weight_window+(k-3)*bias;
     src.read(static_cast<uint8_t*>(staging.data)+relative,len,c["source_offset"]);
     index["experts"][e]["components"][k]["packed_relative_offset"]=relative;
     index["experts"][e]["components"][k]["sha256"]=hash(static_cast<uint8_t*>(staging.data)+relative,len);logical+=len;
   }
   SHA256_Update(&pack_hash,staging.data,stride);
   ssize_t n;do{n=pwrite(fd,staging.data,stride,off_t(e*stride));}while(n<0&&errno==EINTR);
   check(n==ssize_t(stride),"direct pack short write");
 }check(fsync(fd)==0,"pack fsync failed");check(close(fd)==0,"pack close failed");fd=-1;}catch(...){if(fd>=0)close(fd);throw;}
 unsigned char digest[32];SHA256_Final(digest,&pack_hash);std::string digest_hex;const char*hex="0123456789abcdef";for(auto byte:digest){digest_hex+=hex[byte>>4];digest_hex+=hex[byte&15];}
 index["pack_sha256_write_stream"]=digest_hex;index["source_fd_direct"]=bool(fcntl(src.descriptor(),F_GETFL)&O_DIRECT);index["memory_alignment"]=src.memory_alignment();
 index["status"]="PACK_CREATED_BYTES_NOT_YET_QUALIFIED";index["logical_bytes"]=logical;index["pack_bytes"]=stride*input["experts"].size();index["creation_s"]=std::chrono::duration<double>(Clock::now()-start).count();save(receipt,index);
}
struct destination {
 ggml_context *ctx=nullptr;ggml_backend_buffer_t buf=nullptr;std::array<ggml_tensor*,3> tensors{};
 destination(bool gpu){ggml_init_params p{32768,nullptr,true};ctx=ggml_init(p);check(ctx,"metadata allocation failed");for(auto &t:tensors){t=ggml_new_tensor_2d(ctx,GGML_TYPE_MXFP4,2880,2880);check(ggml_nbytes(t)==slab,"destination shape changed");}
 buf=ggml_backend_alloc_ctx_tensors_from_buft(ctx,gpu?ggml_backend_cuda_buffer_type(0):ggml_backend_cpu_buffer_type());check(buf,"destination allocation failed");}
 ~destination(){if(buf)ggml_backend_buffer_free(buf);if(ctx)ggml_free(ctx);}
};
int main(int argc,char **argv){try{
 check(argc==6,"usage pack MODEL INPUT_PACK_SPEC PACK NEW_INDEX | probe MODEL INDEX A|B NEW_RESULT");
 json spec=read_json(argv[3]);if(std::string(argv[1])=="pack"){pack(spec,argv[2],argv[4],argv[5]);return 0;}
 check(std::string(argv[1])=="probe"&&(std::string(argv[4])=="A"||std::string(argv[4])=="B"),"probe arm invalid");bool contiguous=std::string(argv[4])=="B";
 tesy_witness::direct_reader src,packed;src.open_file(argv[2]);packed.open_file(spec["pack_path"].get<std::string>().c_str());check(src.offset_alignment()==packed.offset_alignment(),"filesystem direct requirement differs");
 const auto source_identity=fd_identity(src.descriptor()),pack_identity=fd_identity(packed.descriptor());struct stat packed_stat{};check(fstat(packed.descriptor(),&packed_stat)==0 && !(packed_stat.st_mode&0222),"private pack must be readonly before probe");
 // All components revalidated outside timing from canonical C211, against stored hash and pack bytes.
 size_t checked=0;size_t expert_index=0;for(const auto &e:spec["experts"]){for(const auto &c:e["components"]){size_t n=c["size_bytes"];std::vector<uint8_t>a(n),b(n);
    const auto source_read=[&]{src.read(a.data(),n,c["source_offset"]);};const auto pack_read=[&]{packed.read(b.data(),n,uint64_t(e["pack_offset"])+uint64_t(c["packed_relative_offset"]));};
    if(expert_index%2){pack_read();source_read();}else{source_read();pack_read();}
    check(a==b&&hash(a.data(),n)==c["sha256"],"canonical component/pack byte mismatch");++checked;}++expert_index;}
 std::array<std::unique_ptr<aligned_scratch>,4> scratch;for(auto &p:scratch)p=std::make_unique<aligned_scratch>(src.memory_alignment());
 json reports=json::array();
 for(bool gpu:{false,true}){
   std::vector<size_t> requests;for(size_t i=0;i<spec["experts"].size();i++)if((int(spec["experts"][i]["layer"])>=25)==gpu)requests.push_back(i);
   check(requests.size()==32,"frozen CPU/GPU32 experts required");
   std::array<std::unique_ptr<destination>,4> dest;for(auto&p:dest)p=std::make_unique<destination>(gpu);
   std::array<uint64_t,4> read_calls{},requested_bytes{};std::array<double,4> read_elapsed{},set_elapsed{};std::exception_ptr failed;
   std::mutex job_lock;std::condition_variable wake,done;uint64_t generation=0;size_t job_first=0,completed=0;bool stop=false;
   std::array<std::thread,4> workers;
   for(size_t w=0;w<4;w++)workers[w]=std::thread([&,w]{uint64_t seen=0;std::unique_lock<std::mutex> lock(job_lock);
     while(true){wake.wait(lock,[&]{return stop||generation!=seen;});if(stop)return;seen=generation;size_t first=job_first;lock.unlock();
       try{const auto &e=spec["experts"][requests[first+w]];
         auto get=[&](const tesy_witness::direct_reader &reader,uint64_t offset,size_t len){auto a=Clock::now();auto*p=transport(reader,*scratch[w],offset,len,read_calls[w],requested_bytes[w]);read_elapsed[w]+=std::chrono::duration<double>(Clock::now()-a).count();return p;};
         auto put=[&](size_t k,const uint8_t*p){auto a=Clock::now();ggml_backend_tensor_set(dest[w]->tensors[k],p,0,slab);set_elapsed[w]+=std::chrono::duration<double>(Clock::now()-a).count();};
         if(contiguous){auto *p=get(packed,e["pack_offset"],weights);for(size_t k=0;k<3;k++)put(k,p+k*slab);}
         else for(size_t k=0;k<3;k++){auto *p=get(src,e["components"][k]["source_offset"],slab);put(k,p);}
       }catch(...){lock.lock();if(!failed)failed=std::current_exception();lock.unlock();}
       lock.lock();if(++completed==4)done.notify_one();
     }
   });
   auto start=Clock::now();
   // Four persistent workers, four-expert barriers, eight fixed rotations.
   for(int repetition=0;repetition<8&&!failed;repetition++)for(size_t first=0;first<requests.size();first+=4){
     std::unique_lock<std::mutex> lock(job_lock);job_first=first;completed=0;++generation;wake.notify_all();done.wait(lock,[&]{return completed==4;});
     if(failed)break;
   }
   auto end=Clock::now();
   {std::lock_guard<std::mutex>lock(job_lock);stop=true;wake.notify_all();}for(auto &w:workers)w.join();if(failed)std::rethrow_exception(failed);
   // Validate last destination per worker outside timing. Source canonical bytes include inline MXFP4 scales.
   for(size_t w=0;w<4;w++){const auto &e=spec["experts"][requests[28+w]];for(size_t k=0;k<3;k++){std::vector<uint8_t>a(slab),b(slab);src.read(a.data(),slab,e["components"][k]["source_offset"]);ggml_backend_tensor_get(dest[w]->tensors[k],b.data(),0,slab);check(a==b,"destination not original bytes");}}
   uint64_t calls=0,bytes=0;for(size_t w=0;w<4;w++){calls+=read_calls[w];bytes+=requested_bytes[w];}
   reports.push_back({{"tier",gpu?"GPU":"CPU"},{"service_s",std::chrono::duration<double>(end-start).count()},{"experts_served",256},{"logical_weight_bytes",256*weights},{"pread_calls",calls},{"aligned_request_bytes",bytes},{"destination_verified",true},{"worker_read_elapsed_s",read_elapsed},{"worker_set_elapsed_s",set_elapsed},{"worker_span_semantics","Per-worker elapsed intervals include blocking; concurrent across workers, never add these to end-to-end wall"},{"destination_shape",{2880,2880}},{"publication","worker return only after native tensor_set; barrier after four ready destinations"}});
 }
 check(fd_identity(src.descriptor())==source_identity && fd_identity(packed.descriptor())==pack_identity,"source/pack changed during probe");
 save(argv[5],{{"source_identity",source_identity},{"pack_identity",pack_identity},{"status","PASS_LOSSLESS_SAMPLE_SERVICE"},{"arm",argv[4]},{"component_checks",checked},{"source_fd_direct",bool(fcntl(src.descriptor(),F_GETFL)&O_DIRECT)},{"pack_fd_direct",bool(fcntl(packed.descriptor(),F_GETFL)&O_DIRECT)},{"memory_alignment",src.memory_alignment()},{"offset_alignment",src.offset_alignment()},{"reports",reports},{"scope","Native CPU/CUDA destination service microprobe; no compute contention, no production latency or physical NVMe byte claim"}});return 0;
}catch(const std::exception&e){std::cerr<<"SERVICE_LAYOUT_FAIL "<<e.what()<<'\n';return 1;}}

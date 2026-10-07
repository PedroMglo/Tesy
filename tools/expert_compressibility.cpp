// Fixed Zstd level1 characterization only; target bytes never modified.
#include "c210_direct_reader.h"
#include "json.hpp"
#include <zstd.h>
#include <openssl/sha.h>
#include <array>
#include <chrono>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>
using json=nlohmann::ordered_json;
using Clock=std::chrono::steady_clock;
void require(bool v,const char*m){if(!v)throw std::runtime_error(m);}
void zcheck(size_t v){if(ZSTD_isError(v))throw std::runtime_error(ZSTD_getErrorName(v));}
std::string sha(const void*p,size_t n){unsigned char d[32];SHA256(static_cast<const unsigned char*>(p),n,d);std::string s;const char*h="0123456789abcdef";for(auto b:d){s+=h[b>>4];s+=h[b&15];}return s;}
void save(const char*p,const json&j){require(access(p,F_OK)!=0,"new receipt required");std::ofstream f(p);f<<j.dump(2)<<'\n';require(bool(f),"receipt write");}
struct codec {
 std::unique_ptr<ZSTD_CCtx,decltype(&ZSTD_freeCCtx)> c{ZSTD_createCCtx(),ZSTD_freeCCtx};
 std::unique_ptr<ZSTD_DCtx,decltype(&ZSTD_freeDCtx)> d{ZSTD_createDCtx(),ZSTD_freeDCtx};
 codec(){require(bool(c)&&bool(d),"codec contexts");zcheck(ZSTD_CCtx_setParameter(c.get(),ZSTD_c_compressionLevel,1));zcheck(ZSTD_CCtx_setParameter(c.get(),ZSTD_c_checksumFlag,1));zcheck(ZSTD_CCtx_setParameter(c.get(),ZSTD_c_nbWorkers,0));}
 std::vector<uint8_t> encode(const std::vector<uint8_t>&in){std::vector<uint8_t> out(ZSTD_compressBound(in.size()));auto n=ZSTD_compress2(c.get(),out.data(),out.size(),in.data(),in.size());zcheck(n);out.resize(n);return out;}
 void decode(const std::vector<uint8_t>&in,std::vector<uint8_t>&out){require(ZSTD_getFrameContentSize(in.data(),in.size())==out.size(),"frame logical size");auto frame=ZSTD_findFrameCompressedSize(in.data(),in.size());zcheck(frame);require(frame==in.size(),"exact single frame");auto n=ZSTD_decompressDCtx(d.get(),out.data(),out.size(),in.data(),in.size());zcheck(n);require(n==out.size(),"decompressed logical size");}
};
json fd_identity(int fd){struct stat st{};require(fstat(fd,&st)==0,"source fd stat");return {{"dev",st.st_dev},{"inode",st.st_ino},{"size_bytes",st.st_size},{"mtime_ns",uint64_t(st.st_mtim.tv_sec)*1000000000+st.st_mtim.tv_nsec},{"ctime_ns",uint64_t(st.st_ctim.tv_sec)*1000000000+st.st_ctim.tv_nsec}};}
json mapped_codec(){std::ifstream maps("/proc/self/maps");std::string line;json out=json::object();while(std::getline(maps,line)){auto at=line.find("/");if(at==std::string::npos)continue;auto path=line.substr(at);if(path.find("libzstd.so")==std::string::npos&&path.find("libcrypto.so")==std::string::npos)continue;if(out.contains(path))continue;std::ifstream f(path,std::ios::binary);std::vector<uint8_t>b((std::istreambuf_iterator<char>(f)),{});require(!b.empty()&&b.size()<16*1024*1024,"codec mapped identity");out[path]=sha(b.data(),b.size());}require(out.size()==2,"exact two actual codec libraries");return out;}
json synthetic(){codec c;std::vector<uint8_t> v(65536),out(v.size());for(size_t i=0;i<v.size();i++)v[i]=uint8_t((i*17+i/13)%256);auto a=c.encode(v);c.decode(a,out);require(out==v,"synthetic exactness");
 int errors=0;auto rejected=[&](std::vector<uint8_t>b,std::vector<uint8_t>&dst){try{c.decode(b,dst);}catch(const std::exception&){errors++;return;}throw std::runtime_error("fault accepted");};
 auto bad=a;bad.back()^=1;rejected(bad,out);bad=a;bad.pop_back();rejected(bad,out);bad=a;bad.push_back(0);rejected(bad,out);std::vector<uint8_t> shortout(v.size()-1);rejected(a,shortout);
 for(int i=0;i<4;i++){c.decode(a,out);require(out==v,"reuse exactness");}require(errors==4,"fault cardinality");return {{"status","PASS_CODEC_SYNTHETIC_FAULTS"},{"faults_rejected",errors},{"reuse_repetitions",4},{"zstd_version",ZSTD_versionString()}};}
json characterize(const char*model,const char*spec){std::ifstream f(spec);json index;f>>index;require(bool(f),"sample index missing");require(index["schema"]=="tesy-expert-local-pack-sample-v1"&&index["experts"].size()==64,"original frozen64 sample");
 require(index["model_sha256_previous_verified"]=="582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d","target identity");
 tesy_witness::direct_reader reader;reader.open_file(model);const auto before=fd_identity(reader.descriptor());codec c;json rows=json::array();uint64_t total=0;auto begin=Clock::now();
 std::array<int,8> layers{0,8,16,24,25,29,32,35};std::array<int,8> experts{0,17,34,51,68,85,102,119};size_t ei=0;
 for(const auto&e:index["experts"]){require(int(e["layer"])==layers[ei/8]&&int(e["expert"])==experts[ei%8]&&e["components"].size()==6,"strata identity");size_t ci=0;
  for(const auto&component:e["components"]){size_t n=component["size_bytes"];require(n==(ci<3?4406400:11520),"exact component size");require(component["type"]==(ci<3?"mxfp4":"f32"),"exact component encoding");
   std::vector<uint8_t> original(n),decoded(n),destination(n);auto read_begin=Clock::now();reader.read(original.data(),n,component["source_offset"]);double read_s=std::chrono::duration<double>(Clock::now()-read_begin).count();require(sha(original.data(),n)==component["sha256"],"canonical source hash");
   auto t=Clock::now();auto encoded=c.encode(original);double compress_s=std::chrono::duration<double>(Clock::now()-t).count();json durations=json::array();
   for(int repetition=0;repetition<4;repetition++){t=Clock::now();c.decode(encoded,decoded);memcpy(destination.data(),decoded.data(),n);double elapsed=std::chrono::duration<double>(Clock::now()-t).count();require(destination==original&&sha(destination.data(),n)==component["sha256"],"restored target bytes");durations.push_back(elapsed);}
   uint64_t a=reader.offset_alignment();uint64_t padded=(encoded.size()+a-1)/a*a;
   json row={{"layer",e["layer"]},{"tier",e["tier"]},{"expert",e["expert"]},{"name",component["name"]},{"source_offset",component["source_offset"]},{"source_sha256",component["sha256"]},{"logical_bytes",n},{"encoded_bytes",encoded.size()},{"encoded_sha256",sha(encoded.data(),encoded.size())},{"aligned_encoded_bytes",padded},{"read_s",read_s},{"compress_s",compress_s},{"decompress_to_ready_s",durations},{"exact_bytes",true}};
   if(ci<3){std::vector<uint8_t> scales(n/17),qs(n/17*16);std::array<uint64_t,256> hist{};std::array<uint64_t,16> nibble_hist{};for(size_t k=0;k<n/17;k++){scales[k]=original[k*17];hist[scales[k]]++;memcpy(qs.data()+k*16,original.data()+k*17+1,16);}for(auto q:qs){nibble_hist[q&15]++;nibble_hist[q>>4]++;}auto es=c.encode(scales),eq=c.encode(qs);row["substreams"]={{"scale_bytes",scales.size()},{"scale_encoded_bytes",es.size()},{"qs_bytes",qs.size()},{"qs_encoded_bytes",eq.size()},{"scale_histogram",hist},{"nibble_histogram",nibble_hist},{"scope","Diagnostic separately compressed substreams, not the proposed whole-component codec layout"}};}
   rows.push_back(row);total+=n;ci++;
  }ei++;
 }
 require(total<2ull*1024*1024*1024,"sample bound");require(before==fd_identity(reader.descriptor()),"source identity changed");return {{"schema","tesy-fixed-zstd-characterization-v1"},{"status","PASS_CANONICAL_LOSSLESS_CHARACTERIZATION"},{"zstd_version",ZSTD_versionString()},{"compression_level",1},{"checksum",true},{"codec_workers",0},{"components",rows},{"component_count",rows.size()},{"logical_bytes",total},{"source_identity",before},{"source_fd_direct",bool(fcntl(reader.descriptor(),F_GETFL)&O_DIRECT)},{"memory_alignment",reader.memory_alignment()},{"offset_alignment",reader.offset_alignment()},{"elapsed_s",std::chrono::duration<double>(Clock::now()-begin).count()},{"mapped_codec_libraries_sha256",mapped_codec()},{"scope","CPU single-thread codec characterization; no H2D, target compute contention, compressed-file I/O or runtime latency claim. Biases characterized but not loaded per expert by current worker."}};
}
int main(int argc,char**argv){try{require(ZSTD_versionNumber()==10507,"pinned Zstd1.5.7 required");if(argc==3&&std::string(argv[1])=="synthetic"){save(argv[2],synthetic());return 0;}require(argc==5&&std::string(argv[1])=="sample","usage synthetic NEW_RECEIPT | sample MODEL INDEX NEW_RECEIPT");auto j=characterize(argv[2],argv[3]);save(argv[4],j);std::this_thread::sleep_for(std::chrono::seconds(5));return 0;}catch(const std::exception&e){std::cerr<<"LOSSLESS_CHARACTERIZATION_FAIL "<<e.what()<<'\n';return 1;}}

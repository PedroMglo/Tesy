#pragma once
#include <openssl/sha.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sstream>

static constexpr const char * component_roles[] = {"gate","down","up"};
static constexpr const char * derivation_sha = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9";
static constexpr const char * index_sha = "63b7a76c7063e51944ee8a6296aea43109a336330b3657ffa357cddb44b59813";
static constexpr const char * manifest_sha = "f9773869e644f536bf465873ef0c72992af43296171ea959f9379f23afb57565";
static constexpr const char * pack_sha = "f17e9fbf6f6aed1ad60ca7da3431c5156a946d2e0bf119722afc1f934cbc6b11";

static std::string digest(const void *data, size_t size) {
    unsigned char out[SHA256_DIGEST_LENGTH];
    need(SHA256(static_cast<const unsigned char *>(data), size, out) == out,"SHA256 failed");
    const char hex[] = "0123456789abcdef";
    std::string result;
    for (unsigned char b : out) { result += hex[b >> 4]; result += hex[b & 15]; }
    return result;
}

static json sealed_metadata(const fs::path &p, const char *expected) {
    const size_t size = fs::file_size(p);
    need(size > 0 && size <= (8U << 20), "bounded numerical metadata");
    const auto bytes = read<uint8_t>(p,size);
    need(digest(bytes.data(),size) == expected, "numerical manifest SHA256 changed");
    return json::parse(bytes.begin(),bytes.end());
}

static json pack_identity(int fd, const fs::path &path, const json &expected) {
    struct stat st{};
    need(fstat(fd,&st)==0 && S_ISREG(st.st_mode) && !(st.st_mode & 0222), "pack FD mode");
    const int flags = fcntl(fd,F_GETFL);
    need(flags>=0 && (flags & O_ACCMODE)==O_RDONLY && (flags & O_DIRECT), "pack FD not direct/read-only");
    const json held = {{"dev",st.st_dev},{"inode",st.st_ino},{"size_bytes",st.st_size},
        {"mtime_ns",int64_t(st.st_mtim.tv_sec)*1000000000+st.st_mtim.tv_nsec},
        {"ctime_ns",int64_t(st.st_ctim.tv_sec)*1000000000+st.st_ctim.tv_nsec}};
    need(held==expected && held==tesy_expert_store::identity(path.c_str()),"pack FD/path/placement mismatch");
    return {{"dev",held.at("dev")},{"ino",held.at("inode")},{"size",held.at("size_bytes")},
            {"mtime_ns",held.at("mtime_ns")},{"ctime_ns",held.at("ctime_ns")}};
}

struct PolicyState {
    std::string mode;
    fs::path manifest_dir, pack_path;
    json pack_stat, public_fd_stat;
    std::array<std::array<std::string,6>,128> component_sha{};
    std::array<std::vector<uint8_t>,5> backing;
    std::array<ggml_tensor *,3> biases{};
    ggml_tensor *logical_ids=nullptr;
    std::map<ggml_tensor *,std::pair<int,int>> adds;
    std::array<std::array<int,3>,8> seen_bias{};
    std::vector<std::pair<int,std::string>> mismatches;
    int weights_checked=0, biases_checked=0, seed_verified=0, bank_verified=0;
    bool swapped=false;
};
static PolicyState policy;

// This symbol is used only by the private C291 translation unit. References
// are installed only after seed bytes, including all five backups, validate.
bool policy_use_backing = false;
std::array<bool,128> policy_backed_experts{};

static void open_layer_store(tesy_expert_store &store, const json &prep) {
    const auto &dir = policy.manifest_dir;
    const auto seal = sealed_metadata(dir/"receipt.json",derivation_sha);
    const auto manifest = sealed_metadata(dir/"expert-store-runtime.json",manifest_sha);
    const auto index = sealed_metadata(dir/"integral-index.json",index_sha);
    policy.pack_path = seal.at("pack_path").get<std::string>();
    policy.pack_stat = seal.at("pack_stat");
    need(seal.at("status")=="PASS_DERIVED_C290_NVME_METADATA" && seal.at("pack_sha256")==pack_sha &&
        manifest.at("pack_stat")==policy.pack_stat && manifest.at("pack_sha256_write_stream")==pack_sha &&
        manifest.at("index_sha256")==index_sha && index.at("pack_sha256_write_stream")==pack_sha &&
        index.at("pack_path")==policy.pack_path.string() && index.at("experts").size()==4608 &&
        index.at("stride")==stride && fs::equivalent(manifest.at("index_path").get<std::string>(),
                                                     dir/"integral-index.json"),"derived store linkage");
    store.data.open_file(policy.pack_path.c_str());
    policy.public_fd_stat = pack_identity(store.data.descriptor(),policy.pack_path,policy.pack_stat);
    need(store.data.file_size()==4608ULL*stride && store.data.offset_alignment()==4096 &&
        store.data.memory_alignment()<=4096 && 4096%store.data.memory_alignment()==0,"pack DIO geometry");
    for (auto &record : store.entries[0]) record.offset=UINT64_MAX;
    for (int e=0; e<128; ++e) {
        const bool demand = std::find(selected.begin(),selected.end(),e)!=selected.end();
        if (e>=40 && !demand) continue;
        const auto &row=index.at("experts").at(e);
        need(row.at("layer")==0 && row.at("tier")=="CPU" && row.at("expert")==e &&
             row.at("pack_offset")==size_t(e)*stride && row.at("components").size()==6,"C290 record identity");
        auto &record=store.entries[0][e]; record.offset=size_t(e)*stride;
        for(int k=0;k<6;++k) {
            const auto &desc=row.at("components").at(k);
            const std::string name=std::string("blk.0.ffn_")+component_roles[k%3]+"_exps."+(k<3?"weight":"bias");
            need(desc.at("name")==name && desc.at("size_bytes")==(k<3?slab:width*sizeof(float)) &&
                 desc.at("type")==(k<3?"mxfp4":"f32"),"C290 component geometry");
            if (k<3) {
                need(desc.at("packed_relative_offset")==size_t(k)*slab &&
                     desc.at("source_offset")==prep.at("weight_bases").at(k).get<size_t>()+size_t(e)*slab,
                     "C290 canonical GGUF offset");
                record.relative[k]=size_t(k)*slab;
            }
            if (demand) need(desc==prep.at("components").at(std::to_string(e)).at(k),
                             "C290 preparation descriptor mismatch");
            policy.component_sha[e][k]=desc.at("sha256");
        }
    }
}

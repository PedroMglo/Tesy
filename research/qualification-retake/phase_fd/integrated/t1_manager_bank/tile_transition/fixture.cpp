// Two controlled tiles and a first decode through the pinned C291 manager.
#include "c291-expert-store.h"
#include "llama-moe-stream.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <fstream>
#include <limits>
#include <map>
#include <openssl/sha.h>
#include <set>
#include <sys/stat.h>
#include <unistd.h>

extern "C" ssize_t __real_pread(int, void *, size_t, off_t);
extern "C" void __real_ggml_backend_tensor_set(ggml_tensor *, const void *, size_t, size_t);

namespace {
using json = nlohmann::json;
using Store = tesy_expert_store;
using namespace std::chrono_literals;
constexpr size_t slab = Store::slab, width = Store::weights, stride = 13258752;
using Bytes = std::vector<uint8_t>;
using Hashes = std::array<std::string, 3>;
using Ranks = std::array<int32_t, 4>;
using Eight = std::array<int32_t, 8>;
constexpr const char *roles[] = {"gate", "down", "up"};
const Eight route_a{0, 1, 2, 3, 0, 1, 6, 40}, route_b{3, 5, 41, 42, 3, 5, 43, 44};
FILE *receipt;
void check(bool cond, const char *reason) {
    if (!cond) {
        if (receipt) {
            std::fprintf(receipt, "{\"status\":\"FAIL_PRESERVED\",\"reason\":\"%s\"}\n", reason);
            std::fflush(receipt);
        }
        std::fprintf(stderr, "%s\n", reason);
        std::_Exit(1);
    }
}
std::string hex(const unsigned char *data) {
    char out[65] = {};
    for (int i = 0; i < 32; ++i)
        std::snprintf(out + i * 2, 3, "%02x", data[i]);
    return out;
}
std::string hash(const void *data, size_t size) {
    unsigned char output[32];
    check(SHA256(static_cast<const unsigned char *>(data), size, output) != nullptr, "digest");
    return hex(output);
}
std::string file_digest(int fd, size_t bytes) {
    constexpr size_t chunk = 1024 * 1024;
    void *buf = nullptr;
    check(posix_memalign(&buf, 4096, chunk) == 0, "O_DIRECT proof");
    SHA256_CTX c;
    check(SHA256_Init(&c) == 1, "digest init");
    for (size_t offset = 0; offset < bytes; offset += chunk) {
        const size_t n = std::min(chunk, bytes - offset);
        check(__real_pread(fd, buf, n, offset) == ssize_t(n) && SHA256_Update(&c, buf, n) == 1,
              "pack proof");
    }
    std::free(buf);
    unsigned char output[32];
    check(SHA256_Final(output, &c) == 1, "digest finish");
    return hex(output);
}
int record(int expert) {
    check(expert >= 0 && expert <= 44, "expert in fixture");
    switch (expert) {
    case 0:
    case 6:
        return 1;
    case 1:
    case 7:
    case 43:
        return 2;
    case 2:
    case 40:
        return 3;
    case 3:
    case 41:
    case 44:
        return 4;
    case 42:
        return 5;
    default:
        return 0;
    }
}
struct Job {
    int expert, slot;
    uint64_t generation;
    std::string source;
    int sets = 0, reads = 0, publications = 0;
};
struct Run {
    std::string arm, phase = "warm";
    llama_moe_stream_layer *layer = nullptr;
    int pack_fd = -1;
    size_t alignment = 0, extent = 0;
    std::mutex gate;
    std::condition_variable cv;
    std::set<std::thread::id> held;
    bool release_set = false, release_reader = false, reader_done = false;
    std::map<std::pair<std::string, int>, Job> jobs;
    Bytes bank;
    std::map<int, Bytes> scratch;
    json gold, capture = nullptr;
} r;
thread_local Job *job = nullptr;
thread_local const uint8_t *job_bytes = nullptr;
Bytes copy_slot(int slot) {
    Bytes out(width);
    for (int k = 0; k < 3; ++k)
        ggml_backend_tensor_get(r.layer->weights[k].cache, out.data() + k * slab,
                                size_t(slot) * slab, slab);
    return out;
}
Hashes hashes(const Bytes &data) {
    check(data.size() == width, "record size");
    return {hash(data.data(), slab), hash(data.data() + slab, slab),
            hash(data.data() + 2 * slab, slab)};
}
void check_bytes(int expert, const Hashes &seen) {
    check(seen == r.gold.at("records").at(record(expert)).at("role_sha256").get<Hashes>(),
          "record hash");
}
void drain(llama_moe_stream &mgr) {
    std::unique_lock<std::mutex> lock(mgr.mtx);
    check(mgr.cv_done.wait_for(
              lock, 15s,
              [&] {
                  return mgr.load_failed ||
                         (mgr.q_demand.empty() &&
                          std::all_of(r.layer->slot_state.begin(), r.layer->slot_state.end(),
                                      [](auto s) { return s == LLAMA_MOE_STREAM_SLOT_RESIDENT; }) &&
                          std::none_of(r.layer->slot_claimed.begin(), r.layer->slot_claimed.end(),
                                       [](auto s) { return s != 0; }));
              }) &&
              !mgr.load_failed,
          "bounded complete drain");
}
json state() {
    const auto &sl = *r.layer;
    json result = json::array();
    for (int i = 0; i < 40; ++i) {
        const int e = sl.slot_expert[i];
        check(sl.slot_state[i] == 2 && !sl.slot_claimed[i] && sl.expert_slot.at(e) == i,
              "READY inverse map");
        result.push_back({{"slot", i}, {"expert", e}, {"generation", sl.slot_gen[i]}});
    }
    return result;
}
json wave(ggml_context *ctx, const Eight &ranks, int wave_no) {
    auto *ids = ggml_new_tensor_2d(ctx, GGML_TYPE_I32, 4, 2);
    auto *out = ggml_dup_tensor(ctx, ids);
    auto *mask = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, 4, 2);
    std::memcpy(ids->data, ranks.data(), sizeof(ranks));
    out->src[0] = mask->src[0] = ids;
    auto *ud = r.layer->wave_userdata(wave_no, 4);
    llama_moe_stream_wave_ids(out, 0, 1, ud);
    llama_moe_stream_wave_mask(mask, 0, 1, ud);
    auto *id = static_cast<int32_t *>(out->data);
    auto *m = static_cast<float *>(mask->data);
    std::vector<int> masks;
    for (int i = 0; i < 8; ++i) {
        check((m[i] == 0 || m[i] == 1) && id[i] >= 0 && id[i] < 40, "wave result range");
        masks.push_back(int(m[i]));
    }
    std::lock_guard<std::mutex> lk(r.layer->mgr->mtx);
    return {{"ids", std::vector<int>(id, id + 8)},
            {"mask", masks},
            {"demand_slots", r.layer->demand_slots},
            {"pool", r.layer->plan_pool},
            {"keep", r.layer->keep}};
}
Ranks remap(ggml_context *ctx, const Ranks &ranks) {
    auto *ids = ggml_new_tensor_2d(ctx, GGML_TYPE_I32, 4, 1);
    auto *out = ggml_dup_tensor(ctx, ids);
    std::memcpy(ids->data, ranks.data(), sizeof(ranks));
    llama_moe_stream_remap(out, ids, 0, 1, r.layer);
    Ranks result;
    std::memcpy(result.data(), out->data, sizeof(result));
    return result;
}
} // namespace

int fixture_tile_slot(llama_moe_stream_layer &sl, int expert, int original) {
    if (r.phase != "B" || r.arm == "reference")
        return original;
    int slot = -1;
    switch (expert) {
    case 41:
        slot = 2;
        break;
    case 42:
        slot = 4;
        break;
    case 43:
        slot = 6;
        break;
    case 44:
        slot = 7;
        break;
    default:
        check(false, "unexpected B miss");
    }
    check(original >= 0 && !sl.keep[slot] && sl.slot_state[slot] == 2 && !sl.slot_claimed[slot],
          "perturbed victim admissibility");
    return slot;
}
void witness_capture(llama_moe_stream_layer &sl, int slot) {
    if (r.phase != "B" || r.arm == "reference" || slot != 6)
        return;
    check(r.bank.empty() && sl.slot_expert[slot] == 6 && sl.slot_state[slot] == 2 &&
              !sl.slot_claimed[slot],
          "capture before eviction");
    r.bank = copy_slot(slot);
    auto h = hashes(r.bank);
    check_bytes(6, h);
    r.capture = {{"expert", 6}, {"slot", 6}, {"generation", sl.slot_gen[6]}, {"role_sha256", h}};
}
const uint8_t *witness_lookup(const llama_moe_stream_work &w) {
    auto scratch = r.scratch.find(w.expert);
    const bool restore = r.phase == "restore";
    const bool bank = restore && w.expert == 6 && r.arm != "disk";
    const bool move = restore && scratch != r.scratch.end();
    const uint8_t *ptr = move ? scratch->second.data() : (bank ? r.bank.data() : nullptr);
    check(!bank || r.bank.size() == width, "immutable bank");
    std::lock_guard<std::mutex> lk(r.gate);
    auto [where, ok] =
        r.jobs.emplace(std::make_pair(r.phase, w.expert),
                       Job{w.expert, w.slot, w.gen, move ? "scratch" : (bank ? "bank" : "disk")});
    check(ok, "one claim per phase/expert");
    job = &where->second;
    job_bytes = ptr;
    return ptr;
}
void witness_claim(const llama_moe_stream_work &, const uint8_t *) {
    if (r.phase != "B")
        return;
    std::unique_lock<std::mutex> lk(r.gate);
    check(r.held.insert(std::this_thread::get_id()).second, "four distinct held workers");
    r.cv.notify_all();
    check(r.cv.wait_for(lk, 15s, [] { return r.release_set; }), "held worker timeout");
}
void fixture_tile_publish(const llama_moe_stream_work &w) {
    check(job && job->expert == w.expert && job->slot == w.slot && job->generation == w.gen &&
              job->sets == 3,
          "valid generation completion");
    ++job->publications;
}
extern "C" ssize_t __wrap_pread(int fd, void *buf, size_t n, off_t off) {
    if (fd != r.pack_fd)
        return __real_pread(fd, buf, n, off);
    check(job && job->source == "disk" && off == off_t(record(job->expert) * stride) &&
              n == r.extent,
          "pack job extent");
    job_bytes = static_cast<const uint8_t *>(buf);
    ssize_t got = __real_pread(fd, buf, n, off);
    check(got == ssize_t(n), "short read or error");
    ++job->reads;
    return got;
}
extern "C" void __wrap_ggml_backend_tensor_set(ggml_tensor *t, const void *data, size_t off,
                                               size_t n) {
    int k = -1;
    if (r.layer)
        for (int i = 0; i < 3; ++i)
            if (t == r.layer->weights[i].cache)
                k = i;
    if (k >= 0)
        check(job && job_bytes && k == job->sets && data == job_bytes + k * slab &&
                  off == size_t(job->slot) * slab && n == slab,
              "SET input");
    __real_ggml_backend_tensor_set(t, data, off, n);
    if (k >= 0)
        ++job->sets;
}

namespace {
void setup_store(llama_moe_stream &mgr, const char *pack, json &output) {
    mgr.expert_store = std::make_unique<Store>();
    auto &store = *mgr.expert_store;
    store.data.open_file(pack);
    r.pack_fd = store.data.descriptor();
    struct stat st{};
    check(fstat(r.pack_fd, &st) == 0 && S_ISREG(st.st_mode) && !(st.st_mode & 0222) &&
              st.st_size == off_t(6 * stride) && (fcntl(r.pack_fd, F_GETFL) & O_DIRECT),
          "direct immutable pack");
    const auto id = Store::identity(pack);
    check(id["dev"] == st.st_dev && id["inode"] == st.st_ino, "FD identity");
    output["pack_sha256"] = file_digest(r.pack_fd, 6 * stride);
    check(output["pack_sha256"] == r.gold.at("pack_sha256"), "whole initial pack");
    for (int e = 0; e < 128; ++e) {
        auto &entry = store.entries[0][e];
        entry.offset = e <= 44 ? size_t(record(e)) * stride : std::numeric_limits<uint64_t>::max();
        entry.relative = {0, slab, 2 * slab};
    }
    r.alignment = store.data.offset_alignment();
    check(r.alignment && stride % r.alignment == 0, "pack offset alignment");
    r.extent = (width + r.alignment - 1) / r.alignment * r.alignment;
    check(r.extent <= stride && r.extent <= Store::staging_bytes, "window");
}
void transition_reader(llama_moe_stream &mgr, ggml_context *ctx, json &output) {
    auto &waves = output["waves"];
    json seen;
    std::thread observer([&] {
        {
            std::unique_lock<std::mutex> lk(r.gate);
            check(r.cv.wait_for(lk, 15s, [] { return r.release_reader; }), "reader start timeout");
        }
        // The same two physical indices were emitted both as masked parking and
        // as active ranks by the final wave of A. No concurrent write is allowed.
        seen["6"] = hashes(copy_slot(6));
        seen["4"] = hashes(copy_slot(4));
        std::lock_guard<std::mutex> lk(r.gate);
        r.reader_done = true;
        r.cv.notify_all();
    });
    json b0;
    std::thread remap_host([&] { b0 = wave(ctx, route_b, 0); });
    {
        std::unique_lock<std::mutex> lk(r.gate);
        check(r.cv.wait_for(lk, 15s, [] { return r.held.size() == 4; }),
              "four demand/preload claims");
    }
    output["held_distinct_workers"] = r.held.size();
    {
        std::lock_guard<std::mutex> lk(mgr.mtx);
        for (int e = 41; e <= 44; ++e) {
            int v = r.layer->expert_slot.at(e);
            check(r.layer->slot_claimed[v] && r.layer->slot_state[v] == 1, "held owner");
            output["held_jobs"].push_back({{"expert", e},
                                           {"slot", v},
                                           {"generation", r.layer->slot_gen[v]},
                                           {"claimed", int(r.layer->slot_claimed[v])},
                                           {"state", int(r.layer->slot_state[v])}});
        }
    }
    const auto release_reader = [&] {
        std::unique_lock<std::mutex> lk(r.gate);
        r.release_reader = true;
        r.cv.notify_all();
        check(r.cv.wait_for(lk, 15s, [] { return r.reader_done; }), "reader finish timeout");
    };
    if (r.arm != "broken")
        release_reader();
    {
        std::lock_guard<std::mutex> lk(r.gate);
        r.release_set = true;
        r.cv.notify_all();
    }
    remap_host.join();
    drain(mgr);
    if (r.arm == "broken")
        release_reader();
    observer.join();
    check_bytes(r.arm == "broken" ? 43 : 6, seen["6"].get<Hashes>());
    check_bytes(r.arm == "broken" ? 42 : 40, seen["4"].get<Hashes>());
    output["old_reader"] = seen;
    waves.push_back(b0);
    waves.push_back(wave(ctx, route_b, 1));
    drain(mgr);
}

void restore(llama_moe_stream &mgr) {
    // At this point all readers have joined. Four live records simplify the
    // physical cycle. Capture them all before detaching either end of a move.
    const std::array<std::pair<int, int>, 6> bindings{
        {{0, 43}, {1, 44}, {2, 42}, {4, 41}, {6, 6}, {7, 7}}};
    std::lock_guard<std::mutex> lk(mgr.mtx);
    auto &sl = *r.layer;
    check(mgr.q_demand.empty(), "restore FIFO");
    for (int e : {43, 44, 42, 41}) {
        auto &data = r.scratch[e];
        data = copy_slot(sl.expert_slot.at(e));
        check_bytes(e, hashes(data));
    }
    for (auto [slot, e] : bindings) {
        check(sl.slot_state[slot] == 2 && !sl.slot_claimed[slot],
              "restore requires drained resident");
        check(sl.expert_slot.erase(sl.slot_expert[slot]) == 1, "unbind source");
        sl.slot_expert[slot] = -1;
        sl.slot_state[slot] = LLAMA_MOE_STREAM_SLOT_EMPTY;
    }
    for (auto [slot, e] : bindings) {
        check(!sl.expert_slot.count(e), "duplicate after relocation");
        const uint64_t before = sl.slot_gen[slot];
        mgr.reserve_slot_locked(sl, e, slot);
        check(sl.slot_gen[slot] == before + 1, "fresh generation");
        mgr.q_demand.push_back({&sl, e, slot, sl.slot_gen[slot]});
    }
    mgr.cv_work.notify_all();
}

json execute(const char *pack) {
    ggml_context_ptr ctx(ggml_init({1024 * 1024, nullptr, true})),
        ids_ctx(ggml_init({1024 * 1024, nullptr, false}));
    check(ctx && ids_ctx, "contexts");
    json out = {{"arm", r.arm},
                {"workers", 4},
                {"held_jobs", json::array()},
                {"waves", json::array()},
                {"jobs", json::array()}};
    {
        llama_moe_stream mgr(1, 40, 4, true);
        for (int k = 0; k < 3; ++k) {
            auto *m = ggml_new_tensor_3d(ctx.get(), GGML_TYPE_MXFP4, 2880, 2880, 128);
            ggml_format_name(m, "blk.0.ffn_%s_exps.weight", roles[k]);
            mgr.create_cache_tensor(0, ggml_backend_cpu_buffer_type(), m, 0,
                                    size_t(k) * 128 * slab);
        }
        mgr.alloc_bufs(false);
        r.layer = mgr.layer(0);
        check(r.layer && r.layer->n_slots == 40 && r.layer->n_expert == 128 &&
                  r.layer->weights.size() == 3,
              "primary geometry");
        setup_store(mgr, pack, out);
        auto before_file = Store::identity(pack);
        for (int first : {0, 4})
            for (int e = first; e < 40; e += 4) {
                const Ranks ranks{e, e + 1, e + 2, e + 3};
                check(remap(ids_ctx.get(), ranks) == ranks, "warm fixed physical binding");
            }
        drain(mgr);
        r.phase = "A";
        out["waves"].push_back(wave(ids_ctx.get(), route_a, 0));
        drain(mgr);
        out["waves"].push_back(wave(ids_ctx.get(), route_a, 1));
        drain(mgr);
        r.phase = "B";
        transition_reader(mgr, ids_ctx.get(), out);
        out["before_restore"] = state();
        r.phase = "restore";
        if (r.arm != "reference") {
            restore(mgr);
            drain(mgr);
        }
        out["scratch_bytes"] = r.scratch.size() * width;
        out["capture_bytes"] = r.bank.size();
        out["capture"] = r.capture;
        // Release private transport records only after publication of all six jobs.
        r.scratch.clear();
        r.bank.clear();
        r.phase = "decode";
        out["decode_ids"] = remap(ids_ctx.get(), {6, 7, 42, 41});
        drain(mgr);
        auto terminal = state();
        for (auto &row : terminal) {
            int s = row.at("slot"), e = row.at("expert");
            auto h = hashes(copy_slot(s));
            check_bytes(e, h);
            row["role_sha256"] = h;
        }
        out["terminal"] = terminal;
        out["preloads"] = mgr.stats.n_preload_issued;
        for (const auto &[key, j] : r.jobs) {
            check(j.sets == 3 && j.reads == int(j.source == "disk") && j.publications == 1,
                  "job conservation");
            out["jobs"].push_back({{"phase", key.first},
                                   {"expert", j.expert},
                                   {"slot", j.slot},
                                   {"generation", j.generation},
                                   {"source", j.source},
                                   {"sets", j.sets},
                                   {"reads", j.reads},
                                   {"publications", j.publications}});
        }
        check(mgr.workers.size() == 4 && !mgr.load_failed && mgr.q_demand.empty(), "cleanup");
        check(out["pack_sha256"] == file_digest(r.pack_fd, 6 * stride) &&
                  before_file == Store::identity(pack),
              "final pack");
    }
    r.layer = nullptr;
    r.pack_fd = -1;
    auto provider = [](const void *symbol) {
        Dl_info d{};
        check(dladdr(symbol, &d) && d.dli_fname && *d.dli_fname == '/', "ELF path");
        std::unique_ptr<char, decltype(&std::free)> p(realpath(d.dli_fname, nullptr), &std::free);
        check(bool(p), "provider realpath");
        return json{{"path", p.get()}, {"identity", Store::identity(p.get())}};
    };
    out["providers"] = {
        {"ggml", provider(reinterpret_cast<const void *>(&__real_ggml_backend_tensor_set))},
        {"crypto", provider(reinterpret_cast<const void *>(&SHA256))}};
    out["pack_proof_bytes"] = 12 * stride;
    out["offset_alignment"] = r.alignment;
    out["read_extent"] = r.extent;
    out["destructor_returned"] = true;
    out["status"] = "PASS_C291_TILE_TRANSITION_CPU";
    return out;
}
} // namespace

int main(int argc, char **argv) {
    if (argc != 5)
        return 2;
    const int fd = open(argv[4], O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0 || !(receipt = fdopen(fd, "w")))
        return 2;
    alarm(175);
    try {
        r.arm = argv[1];
        check(r.arm == "reference" || r.arm == "disk" || r.arm == "bank" || r.arm == "broken",
              "arm");
        std::ifstream f(argv[3]);
        f >> r.gold;
        check(bool(f) && r.gold["slab"] == slab && r.gold["records"].size() == 6, "gold");
        const auto output = execute(argv[2]).dump();
        check(std::fprintf(receipt, "%s\n", output.c_str()) > 0 && std::fflush(receipt) == 0 &&
                  fsync(fd) == 0,
              "raw receipt");
        return std::fclose(receipt) == 0 ? 0 : 1;
    } catch (const std::exception &e) {
        std::fprintf(stderr, "native exception: %s\n", e.what());
        check(false, "native exception");
        return 1;
    }
}

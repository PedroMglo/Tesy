// Fixture-only callbacks used by the C291 manager selected by overlay.py.
// CLI: EXE off|on|eio|stale|shutdown PACK GOLD.json NEW_RECEIPT
#include "llama-moe-stream.h"
#include "c291-expert-store.h"
#include <openssl/sha.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <fstream>
#include <limits>
#include <map>
#include <set>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

namespace {
using json = nlohmann::json;
using Store = tesy_expert_store;
using namespace std::chrono_literals;
constexpr size_t S = Store::slab, W = 3 * S, stride = 13258752;
constexpr const char *roles[] = {"gate", "down", "up"};
using Rank = std::array<int32_t, 4>;
using Key = std::pair<int, int>; // (layer, authoritative expert)
using Sha = std::array<std::string, 3>;

FILE *receipt = nullptr;
void check(bool ok, const char *why) {
    if (!ok) {
        if (receipt) {
            std::fprintf(receipt, "{\"status\":\"FAIL_PRESERVED\",\"reason\":\"%s\"}\n", why);
            std::fflush(receipt);
        }
        std::fprintf(stderr, "FAIL %s\n", why);
        std::_Exit(1);
    }
}
std::string sha(const void *p, size_t n) {
    unsigned char digest[SHA256_DIGEST_LENGTH];
    char out[65] = {};
    check(SHA256(static_cast<const unsigned char *>(p), n, digest) != nullptr, "digest");
    for (int i = 0; i < 32; i++)
        std::snprintf(out + 2 * i, 3, "%02x", digest[i]);
    return out;
}
int record(int e) {
    check(e >= 0 && e <= 43, "target key");
    return e < 36 ? 0 : std::min(5, e - 35);
}
enum Phase { WARM, REPLACE, TARGET };
struct Job {
    int expert = -1, slot = -1, sets = 0, reads = 0;
    uint64_t generation = 0;
    const uint8_t *bank = nullptr;
    bool missed = false;
    size_t read_bytes = 0, returned_bytes = 0;
};
struct Run {
    std::string mode;
    bool active = false, sealed = false, claim_release = false, set_release = false;
    int at_claim = 0, at_last_set = 0, offers = 0, hits = 0;
    Phase phase = WARM;
    std::map<Key, std::vector<uint8_t>> bank;
    std::vector<Key> ages;
    llama_moe_stream *mgr = nullptr;
    llama_moe_stream_layer *sl = nullptr;
    std::mutex m;
    std::condition_variable cv;
    std::map<std::thread::id, Job> jobs;
    std::array<int, 3> reads{}, sets{}, claims{};
    std::array<size_t, 3> requested{}, returned{};
    int fd = -1;
    size_t offset_alignment = 0, read_extent = 0;
    json gold;
    json captured = json::array();
    size_t peak_bank_bytes = 0;
} r;
thread_local int target_expert = -1;
thread_local int target_slot = -1;
thread_local const uint8_t *source = nullptr;
thread_local const uint8_t *disk_source = nullptr;
Sha stored_hashes(const std::vector<uint8_t> &data) {
    check(data.size() == W, "bank bytes");
    return {sha(data.data(), S), sha(data.data() + S, S), sha(data.data() + 2 * S, S)};
}
void gold(int e, const Sha &hashes) {
    auto expected = r.gold.at("records").at(record(e)).at("role_sha256").get<Sha>();
    check(hashes == expected, "independent synthetic role hash");
}
bool seal_locked() {
    if (r.mgr->shutting_down || r.mgr->load_failed || !r.mgr->q_demand.empty())
        return false;
    for (const auto &l : r.mgr->layers)
        if (l)
            for (unsigned v = 0; v < l->n_slots; v++)
                if (l->slot_claimed[v] || l->slot_state[v] == LLAMA_MOE_STREAM_SLOT_LOADING)
                    return false;
    r.sealed = true;
    return true;
}
void observe_queue_gate(bool before_last) {
    {
        std::unique_lock<std::mutex> lock(r.m);
        check(r.cv.wait_for(lock, 20s,
                            [&] { return before_last ? r.at_last_set == 4 : r.at_claim == 4; }),
              "worker rendezvous");
    }
    std::lock_guard<std::mutex> state(r.mgr->mtx);
    std::lock_guard<std::mutex> events(r.m);
    std::array<uint8_t, 40> keep;
    keep.fill(1);
    check(r.jobs.size() == 4 && r.mgr->q_demand.empty() && r.mgr->workers.size() == 4,
          "four live workers");
    for (auto &[tid, j] : r.jobs) {
        keep.at(j.slot) = 0;
        check(r.sl->slot_expert[j.slot] == j.expert && r.sl->slot_gen[j.slot] == j.generation &&
                  r.sl->slot_state[j.slot] == LLAMA_MOE_STREAM_SLOT_LOADING &&
                  r.sl->slot_claimed[j.slot] == 1,
              "unpublished identity");
        if (before_last)
            check(j.sets == 2, "third SET not yet submitted");
    }
    check(r.mgr->pick_victim_locked(*r.sl, keep.data()) == -1, "outstanding victim");
    if (r.phase == REPLACE)
        check(!seal_locked(), "T2 opened before drain");
}
void enter(Phase p) {
    std::lock_guard<std::mutex> lock(r.m);
    r.phase = p;
    r.at_claim = r.at_last_set = 0;
    r.claim_release = r.set_release = false;
    r.jobs.clear();
}
void release_gate(bool claim) {
    std::lock_guard<std::mutex> lock(r.m);
    (claim ? r.claim_release : r.set_release) = true;
    r.cv.notify_all();
}
void drained_bank() {
    const std::vector<Key> expected =
        r.active ? std::vector<Key>{{0, 37}, {0, 38}, {0, 39}} : std::vector<Key>{};
    check(r.ages == expected && r.bank.size() == expected.size(), "causal bank identity");
    for (const auto &key : expected)
        gold(key.second, stored_hashes(r.bank.at(key)));
}
Sha inspect_slot(int v) {
    Sha hashes;
    std::vector<uint8_t> data(S);
    for (int k = 0; k < 3; k++) {
        auto &wt = r.sl->weights[k];
        ggml_backend_tensor_get(wt.cache, data.data(), size_t(v) * S, S);
        hashes[k] = sha(data.data(), S);
    }
    return hashes;
}
} // namespace

void witness_capture(llama_moe_stream_layer &layer, int v) {
    if (!r.active || r.sealed)
        return;
    if (layer.slot_state[v] == LLAMA_MOE_STREAM_SLOT_EMPTY)
        return;
    check(layer.slot_state[v] == LLAMA_MOE_STREAM_SLOT_RESIDENT && !layer.slot_claimed[v],
          "capture only READY");
    const Key key = {layer.il, layer.slot_expert[v]};
    check(layer.expert_slot.at(key.second) == v, "old binding");
    // The CPU tensors have no active consumers in this fixture. The mutex is not a CUDA fence.
    auto age = std::find(r.ages.begin(), r.ages.end(), key);
    if (age != r.ages.end())
        r.ages.erase(age);
    else if (r.ages.size() == 3) {
        r.bank.erase(r.ages.front());
        r.ages.erase(r.ages.begin());
    }
    auto &copy = r.bank[key];
    copy.resize(W);
    for (int k = 0; k < 3; k++) {
        auto &wt = layer.weights[k];
        check(wt.nb_expert == S && wt.cache->nb[2] == S, "dense slot geometry");
        auto b = reinterpret_cast<uintptr_t>(copy.data());
        for (const auto &owner : r.mgr->bufs) {
            auto a = reinterpret_cast<uintptr_t>(ggml_backend_buffer_get_base(owner.get()));
            check(b + W <= a || a + ggml_backend_buffer_get_size(owner.get()) <= b,
                  "alias with primary");
        }
        ggml_backend_tensor_get(wt.cache, copy.data() + k * S, size_t(v) * S, S);
    }
    const auto hashes = stored_hashes(copy);
    gold(key.second, hashes);
    r.captured.push_back({{"expert", key.second},
                          {"slot", v},
                          {"generation", layer.slot_gen[v]},
                          {"roles", hashes}});
    r.ages.push_back(key);
    r.offers++;
    r.peak_bank_bytes = std::max(r.peak_bank_bytes, r.bank.size() * W);
}
const uint8_t *witness_lookup(const llama_moe_stream_work &w) {
    if (!r.sealed || !r.active)
        return nullptr;
    auto it = r.bank.find({w.sl->il, w.expert});
    if (it == r.bank.end())
        return nullptr;
    r.hits++;
    return it->second.data();
}
void witness_claim(const llama_moe_stream_work &w, const uint8_t *p) {
    target_expert = w.expert;
    target_slot = w.slot;
    source = p;
    disk_source = nullptr;
    std::unique_lock<std::mutex> lock(r.m);
    r.claims[r.phase]++;
    if (r.phase == WARM)
        return;
    auto &j = r.jobs[std::this_thread::get_id()];
    check(j.expert < 0, "worker double claim");
    j.expert = w.expert;
    j.slot = w.slot;
    j.generation = w.gen;
    j.bank = p;
    r.at_claim++;
    r.cv.notify_all();
    check(r.cv.wait_for(lock, 20s, [] { return r.claim_release; }), "claim hold");
}
extern "C" ssize_t __real_pread(int, void *, size_t, off_t);
extern "C" ssize_t __wrap_pread(int fd, void *dst, size_t n, off_t off) {
    if (fd != r.fd || r.fd < 0)
        return __real_pread(fd, dst, n, off);
    check(!source && off == off_t(record(target_expert) * stride), "disk source identity");
    disk_source = static_cast<const uint8_t *>(dst);
    check(r.offset_alignment && off >= 0 && size_t(off) % r.offset_alignment == 0 &&
              n == r.read_extent,
          "pread extent and offset alignment");
    const bool injected_eio = r.phase == TARGET && r.mode == "eio" && target_expert == 36;
    ssize_t got;
    if (injected_eio) {
        errno = EIO;
        got = -1;
    } else
        got = __real_pread(fd, dst, n, off);
    const int saved = errno;
    check(injected_eio ? got == -1 && saved == EIO : got == ssize_t(r.read_extent),
          "per-read result");
    {
        std::lock_guard<std::mutex> lk(r.m);
        r.reads[r.phase]++;
        r.requested[r.phase] += n;
        if (got > 0)
            r.returned[r.phase] += size_t(got);
        if (r.phase != WARM) {
            auto &j = r.jobs.at(std::this_thread::get_id());
            j.reads++;
            j.read_bytes = n;
            j.returned_bytes = got > 0 ? size_t(got) : 0;
        }
    }
    errno = saved;
    return got;
}
extern "C" void __real_ggml_backend_tensor_set(ggml_tensor *, const void *, size_t, size_t);
extern "C" void __wrap_ggml_backend_tensor_set(ggml_tensor *tensor, const void *data, size_t off,
                                               size_t n) {
    int k = -1;
    if (r.sl)
        for (int i = 0; i < 3; i++)
            if (r.sl->weights[i].cache == tensor)
                k = i;
    if (k < 0) {
        __real_ggml_backend_tensor_set(tensor, data, off, n);
        return;
    }
    auto *base = source ? source : disk_source;
    check(base && n == S && data == base + k * S && off == size_t(target_slot) * S,
          "full unaliased source and destination");
    {
        std::unique_lock<std::mutex> lk(r.m);
        if (r.phase == TARGET && k == 2) {
            check(r.jobs.at(std::this_thread::get_id()).sets == 2, "two SETs completed");
            r.at_last_set++;
            r.cv.notify_all();
            check(r.cv.wait_for(lk, 20s, [] { return r.set_release; }), "third SET hold");
        }
    }
    __real_ggml_backend_tensor_set(tensor, data, off, n);
    {
        std::lock_guard<std::mutex> lk(r.m);
        r.sets[r.phase]++;
        if (r.phase != WARM) {
            auto &j = r.jobs.at(std::this_thread::get_id());
            check(j.sets == k, "native role order");
            j.sets++;
        }
    }
}

namespace {
std::string descriptor_hash(int fd, size_t size) {
    // Reuse the serviced fd (O_DIRECT), also before and after the experiment.
    void *p = nullptr;
    constexpr size_t chunk = 1024 * 1024;
    check(posix_memalign(&p, 4096, chunk) == 0, "pack digest buffer");
    SHA256_CTX c;
    check(SHA256_Init(&c) == 1, "sha init");
    for (size_t off = 0; off < size; off += chunk) {
        size_t n = std::min(chunk, size - off);
        check(__real_pread(fd, p, n, off_t(off)) == ssize_t(n), "digest read");
        check(SHA256_Update(&c, p, n) == 1, "digest update");
    }
    std::free(p);
    unsigned char sum[32];
    char out[65] = {};
    check(SHA256_Final(sum, &c) == 1, "sha final");
    for (int i = 0; i < 32; i++)
        std::snprintf(out + i * 2, 3, "%02x", sum[i]);
    return out;
}
json execute(const char *pack) {
    ggml_context_ptr ctx(ggml_init({1024 * 1024, nullptr, true})),
        idctx(ggml_init({1024 * 1024, nullptr, false}));
    check(ctx && idctx, "contexts");
    auto *ids = ggml_new_tensor_2d(idctx.get(), GGML_TYPE_I32, 4, 1);
    auto *out = ggml_dup_tensor(idctx.get(), ids);
    const bool normal = r.mode == "on" || r.mode == "off";
    json result;
    json terminal = json::array();
    {
        llama_moe_stream mgr(1, 40, 4, true);
        r.mgr = &mgr;
        for (int k = 0; k < 3; k++) {
            auto *m = ggml_new_tensor_3d(ctx.get(), GGML_TYPE_MXFP4, 2880, 2880, 128);
            ggml_format_name(m, "blk.0.ffn_%s_exps.weight", roles[k]);
            mgr.create_cache_tensor(0, ggml_backend_cpu_buffer_type(), m, 0, size_t(k) * 128 * S);
        }
        mgr.alloc_bufs(false);
        r.sl = mgr.layer(0);
        check(r.sl && r.sl->n_slots == 40 && r.sl->n_expert == 128 && r.sl->weights.size() == 3,
              "primary geometry");
        mgr.expert_store = std::make_unique<Store>();
        auto &store = *mgr.expert_store;
        store.data.open_file(pack);
        auto fd = store.data.descriptor();
        struct stat st{};
        check(fstat(fd, &st) == 0 && S_ISREG(st.st_mode) && !(st.st_mode & 0222) &&
                  st.st_size == off_t(6 * stride) && (fcntl(fd, F_GETFL) & O_DIRECT),
              "read-only direct pack");
        auto id = Store::identity(pack);
        check(st.st_ino == id["inode"] && st.st_dev == id["dev"], "pack path/fd identity");
        const auto hashed = descriptor_hash(fd, 6 * stride);
        check(hashed == r.gold.at("pack_sha256"), "pack gold");
        for (auto &e : store.entries[0])
            e.offset = std::numeric_limits<uint64_t>::max();
        for (int e = 0; e <= 43; e++) {
            auto &entry = store.entries[0][e];
            entry.offset = record(e) * stride;
            entry.relative = {0, S, 2 * S};
        }
        r.offset_alignment = store.data.offset_alignment();
        check(r.offset_alignment && stride % r.offset_alignment == 0,
              "usable direct offset alignment");
        r.read_extent = (W + r.offset_alignment - 1) / r.offset_alignment * r.offset_alignment;
        check(r.read_extent <= Store::staging_bytes && r.read_extent <= stride,
              "bounded read window");
        r.fd = fd;
        auto route = [&](Rank a, Rank expect) {
            std::memcpy(ids->data, a.data(), sizeof a);
            llama_moe_stream_remap(out, ids, 0, 1, r.sl);
            check(std::memcmp(out->data, expect.data(), sizeof expect) == 0, "route ranks");
        };
        route({36, 37, 38, 39}, {0, 1, 2, 3});
        for (int e = 0; e < 36; e += 4)
            route({e, e + 1, e + 2, e + 3}, {e + 4, e + 5, e + 6, e + 7});
        enter(REPLACE);
        std::thread t1([&] { route({40, 41, 42, 43}, {0, 1, 2, 3}); });
        observe_queue_gate(false);
        {
            std::lock_guard<std::mutex> lk(mgr.mtx);
            drained_bank();
        }
        release_gate(true);
        t1.join();
        {
            std::lock_guard<std::mutex> lk(mgr.mtx);
            check(seal_locked(), "T1 incomplete");
            drained_bank();
            for (int v = 0; v < 4; v++) {
                check(r.sl->slot_gen[v] == 2, "overwritten generation");
                gold(40 + v, inspect_slot(v));
            }
        }
        enter(TARGET);
        const Rank target = {39, 36, 38, 37};
        std::thread t2;
        if (normal)
            t2 = std::thread([&] { route(target, {4, 5, 6, 7}); });
        else {
            std::lock_guard<std::mutex> lk(mgr.mtx);
            std::array<uint8_t, 40> keep{};
            for (int i = 0; i < 4; i++) {
                int v = mgr.pick_victim_locked(*r.sl, keep.data());
                check(v == 4 + i, "fault target slot");
                mgr.reserve_slot_locked(*r.sl, target[i], v);
                keep[v] = 1;
                mgr.q_demand.push_back({r.sl, target[i], v, r.sl->slot_gen[v]});
            }
            mgr.cv_work.notify_all();
        }
        observe_queue_gate(false);
        release_gate(true);
        if (r.mode == "eio") {
            std::unique_lock<std::mutex> lk(r.m);
            check(r.cv.wait_for(lk, 20s, [] { return r.at_last_set == 3; }), "hits at last SET");
            lk.unlock();
            std::unique_lock<std::mutex> state(mgr.mtx);
            check(mgr.cv_done.wait_for(state, 20s, [&] { return mgr.load_failed; }),
                  "sticky disk error");
            check(r.sl->slot_state[5] == LLAMA_MOE_STREAM_SLOT_LOADING && !r.sl->slot_claimed[5],
                  "failed slot not published");
        } else {
            observe_queue_gate(true);
            std::lock_guard<std::mutex> state(mgr.mtx);
            if (r.mode == "stale")
                ++r.sl->slot_gen[4];
            if (r.mode == "shutdown") {
                mgr.shutting_down = true;
                mgr.cv_work.notify_all();
            }
        }
        release_gate(false);
        if (normal)
            t2.join();
        else {
            std::unique_lock<std::mutex> state(mgr.mtx);
            auto finished = [&] {
                for (int v = 4; v < 8; v++)
                    if (!(r.mode == "stale" && v == 4) && r.sl->slot_claimed[v])
                        return false;
                return r.mode != "stale" || mgr.load_failed;
            };
            check(mgr.cv_done.wait_for(state, 20s, finished), "terminal completion");
        }
        {
            std::lock_guard<std::mutex> lk(mgr.mtx);
            check(mgr.q_demand.empty() && mgr.workers.size() == 4, "native cleanup");
            if (normal)
                check(!mgr.shutting_down && !mgr.load_failed, "normal health");
            if (r.mode == "eio" || r.mode == "stale")
                check(mgr.load_failed, "fault sticky");
            if (r.mode == "shutdown")
                check(mgr.shutting_down && !mgr.load_failed, "shutdown sticky");
            for (int v = 0; v < 40; v++) {
                int e = v < 4 ? 40 + v : (v < 8 ? target[v - 4] : v - 4);
                const bool bad = (r.mode == "shutdown" && v >= 4 && v < 8) ||
                                 (r.mode == "eio" && v == 5) || (r.mode == "stale" && v == 4);
                check(r.sl->slot_expert[v] == e && r.sl->expert_slot.at(e) == v &&
                          r.sl->slot_gen[v] ==
                              uint64_t((v < 8 ? 2 : 1) + (r.mode == "stale" && v == 4)) &&
                          bool(r.sl->slot_claimed[v]) == (r.mode == "stale" && v == 4) &&
                          (r.sl->slot_state[v] ==
                           (bad ? LLAMA_MOE_STREAM_SLOT_LOADING : LLAMA_MOE_STREAM_SLOT_RESIDENT)),
                      "terminal binding");
                json x = {{"slot", v},
                          {"expert", e},
                          {"generation", r.sl->slot_gen[v]},
                          {"claimed", bool(r.sl->slot_claimed[v])},
                          {"resident", !bad}};
                if (!bad) {
                    auto hashes = inspect_slot(v);
                    gold(e, hashes);
                    x["role_sha256"] = hashes;
                }
                terminal.push_back(x);
            }
        }
        drained_bank();
        const int nr = r.active ? 1 : 4;
        check(r.claims == std::array<int, 3>{40, 4, 4} &&
                  r.reads == std::array<int, 3>{40, 4, nr} &&
                  r.sets == std::array<int, 3>{120, 12, r.mode == "eio" ? 9 : 12} &&
                  r.hits == (r.active ? 3 : 0) && r.offers == (r.active ? 4 : 0),
              "conservation");
        for (const auto &[t, j] : r.jobs) {
            bool bank = r.active && j.expert != 36;
            check(bool(j.bank) == bank && j.reads == (bank ? 0 : 1) &&
                      j.sets == (r.mode == "eio" && j.expert == 36 ? 0 : 3),
                  "individual T2 source and destination");
            if (bank)
                check(j.bank == r.bank.at({0, j.expert}).data(), "same immutable allocation");
        }
        check(id == Store::identity(pack) && descriptor_hash(fd, 6 * stride) == hashed,
              "pack postcheck");
        result["pack_sha256"] = hashed;
        result["pack_proof_bytes"] = 12 * stride;
        int published = 0;
        for (int v = 4; v < 8; v++)
            published += r.sl->slot_state[v] == LLAMA_MOE_STREAM_SLOT_RESIDENT;
        result["actual_publications_T2"] = published;
        result["manager_store_reads_committed"] = mgr.stats.n_store_loads;
    }
    r.fd = -1;
    r.sl = nullptr;
    r.mgr = nullptr;
    auto provider = [](const void *symbol) {
        Dl_info linkage{};
        check(dladdr(symbol, &linkage) != 0 && linkage.dli_fname && *linkage.dli_fname == '/',
              "absolute symbol provider");
        std::unique_ptr<char, decltype(&std::free)> path(realpath(linkage.dli_fname, nullptr),
                                                         &std::free);
        check(bool(path), "provider resolves");
        return json{{"path", path.get()}, {"identity", Store::identity(path.get())}};
    };
    // --wrap maps __real_ggml_backend_tensor_set to the original dynamic symbol.
    result["providers"] = {
        {"ggml", provider(reinterpret_cast<const void *>(&__real_ggml_backend_tensor_set))},
        {"crypto", provider(reinterpret_cast<const void *>(&SHA256))}};
    result["offset_alignment"] = r.offset_alignment;
    result["read_extent"] = r.read_extent;
    result["terminal_slots"] = terminal;
    result["capture"] = r.captured;
    result["source_layout"] = "C291 pack, dense independent CPU tensors";
    result["workers"] = 4;
    result["destructor_returned"] = true;
    result["claims"] = r.claims;
    result["preads"] = r.reads;
    result["requested_bytes"] = r.requested;
    result["returned_bytes"] = r.returned;
    result["sets"] = r.sets;
    result["bank_hits_T2"] = r.hits;
    result["bank_payload_captured_T1"] = r.offers * W;
    result["peak_bank_payload_bytes"] = r.peak_bank_bytes;
    result["mode"] = r.mode;
    result["status"] = "PASS_C291_T1_VICTIM_FIXTURE";
    return result;
}
} // namespace
int main(int argc, char **argv) {
    if (argc != 5)
        return 2;
    int fd = open(argv[4], O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
    if (fd < 0)
        return 2;
    receipt = fdopen(fd, "w");
    if (!receipt)
        return 2;
    alarm(175);
    try {
        r.mode = argv[1];
        check(r.mode == "off" || r.mode == "on" || r.mode == "eio" || r.mode == "stale" ||
                  r.mode == "shutdown",
              "case");
        r.active = r.mode != "off";
        std::ifstream g(argv[3]);
        g >> r.gold;
        check(bool(g) && r.gold.at("slab") == S && r.gold.at("records").size() == 6 &&
                  r.gold.at("roles") == json({"gate", "down", "up"}),
              "gold schema");
        auto result = execute(argv[2]);
        auto data = result.dump();
        check(std::fprintf(receipt, "%s\n", data.c_str()) > 0 && std::fflush(receipt) == 0 &&
                  fsync(fd) == 0,
              "receipt write");
        return std::fclose(receipt) == 0 ? 0 : 1;
    } catch (...) {
        check(false, "unexpected exception");
        return 1;
    }
}

// ELF observer for the pinned single-slot stock server. All inference calls are forwarded.
// No TESY_F32_DIR: pass through. Enabled: a private empty directory, separate ARM after READY.
// The controller must keep ARM until exit, then require PASS, row hash, child status and HTTP ID.
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <fstream>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

#include <openssl/evp.h>

namespace {
constexpr int width = 201088;
constexpr int expected_index = 15;
constexpr char arm_text[] = "tesy-first-prompt16-v1\n";
constexpr char common_sha[] = "7cf9543328e80642d8c5d2212b1926fa5dc66f551d3d1e4cf04ab7900622c5e3";
constexpr char stock_sha[] = "717a7e3dc18ae58585c6df1af2454c5b441c171258b7100ae7e11530e02265b8";
constexpr char derivative_sha[] = "34ce470fac8b70d58602ba979f014616b9a8b7a9593b55a5e8436116f6ceb767";
constexpr char sampler_name[] = "_Z21common_sampler_sampleP14common_samplerP13llama_contextib";
static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);
static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);
struct llama_context;
struct llama_model;
struct llama_vocab;
using Getter = float * (*)(llama_context *, int32_t);

void require(bool ok, const char *reason) {
    if (!ok) throw std::runtime_error(reason);
}
struct Fd {
    int value;
    explicit Fd(int f) : value(f) {}
    ~Fd() { if (value >= 0) close(value); }
    Fd(const Fd &) = delete;
    Fd &operator=(const Fd &) = delete;
};
std::string env(const char *key) {
    const auto *v = getenv(key);
    return v ? v : "";
}
std::string hex(const unsigned char *digest) {
    std::string s;
    constexpr char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < 32; ++i) {
        s += digits[digest[i] >> 4];
        s += digits[digest[i] & 15];
    }
    return s;
}
std::string digest(const void *bytes, size_t size) {
    std::array<unsigned char, 32> value{};
    unsigned int len = 0;
    require(EVP_Digest(bytes, size, value.data(), &len, EVP_sha256(), nullptr) == 1 &&
            len == value.size(), "row_digest");
    return hex(value.data());
}
// Check the actual mapping, including its backing inode and canonical pathname.
// stat.st_dev and the maps device field can differ on Btrfs.
std::string image_hash(const void *address, const Dl_info &info) {
    std::unique_ptr<char, decltype(&free)> path(realpath(info.dli_fname, nullptr), free);
    require(path != nullptr, "image_path");
    Fd fd(open(path.get(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
    struct stat s{}, end{};
    require(fd.value >= 0 && !fstat(fd.value, &s) && S_ISREG(s.st_mode), "image_fd");
    std::ifstream maps("/proc/self/maps");
    std::string line;
    bool matched = false;
    const auto pc = reinterpret_cast<uintptr_t>(address);
    while (std::getline(maps, line)) {
        unsigned long begin, finish, inode;
        char perms[5]{};
        int offset = 0;
        if (sscanf(line.c_str(), "%lx-%lx %4s %*s %*s %lu %n",
                   &begin, &finish, perms, &inode, &offset) == 4 && begin <= pc && pc < finish) {
            matched = perms[2] == 'x' && inode == s.st_ino && line.substr(offset) == path.get();
            break;
        }
    }
    require(matched, "mapped_image_identity");
    std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
    require(ctx && EVP_DigestInit_ex(ctx.get(), EVP_sha256(), nullptr) == 1, "hash_init");
    std::array<unsigned char, 65536> buf{};
    ssize_t n;
    do {
        n = read(fd.value, buf.data(), buf.size());
        if (n < 0 && errno == EINTR) continue;
        require(n >= 0, "image_read");
        if (n) require(EVP_DigestUpdate(ctx.get(), buf.data(), n) == 1, "image_digest");
    } while (n);
    std::array<unsigned char, 32> result{};
    unsigned int len = 0;
    require(!fstat(fd.value, &end) && s.st_size == end.st_size && s.st_ino == end.st_ino &&
            s.st_ctim.tv_sec == end.st_ctim.tv_sec && s.st_ctim.tv_nsec == end.st_ctim.tv_nsec &&
            EVP_DigestFinal_ex(ctx.get(), result.data(), &len) == 1 && len == result.size(),
            "image_changed");
    return hex(result.data());
}
struct State {
    std::mutex mutex;
    int dir = -1;
    pid_t pid = 0;
    unsigned prearm = 0, armed_calls = 0;
    bool mock = false, saw_arm = false;
    std::string error;
    std::string expected_provider, expected_caller, provider, caller, row_hash;
    uintptr_t caller_offset = 0;
    int argmax = -1;
    ino_t arm_inode = 0;
    dev_t arm_device = 0;
    timespec arm_ctime{};
};
State &state() {
    // Remain valid while ELF destructors run.
    static State *s = new State;
    return *s;
}
Getter native() {
    static Getter getter = reinterpret_cast<Getter>(dlsym(RTLD_NEXT, "llama_get_logits_ith"));
    if (!getter) _exit(125);
    return getter;
}
bool armed(State &s) {
    Fd f(openat(s.dir, "ARM", O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK));
    if (f.value < 0) {
        require(errno == ENOENT && !s.saw_arm, "arm_missing_or_replaced");
        return false;
    }
    struct stat st{};
    std::array<char, sizeof(arm_text)> text{};
    require(!fstat(f.value, &st) && S_ISREG(st.st_mode) && st.st_uid == geteuid() &&
            st.st_size == sizeof(arm_text)-1 && read(f.value, text.data(), text.size()) ==
            ssize_t(sizeof(arm_text)-1) && !strcmp(text.data(), arm_text), "bad_arm");
    if (s.saw_arm) {
        require(st.st_ino == s.arm_inode && st.st_dev == s.arm_device &&
                st.st_ctim.tv_sec == s.arm_ctime.tv_sec && st.st_ctim.tv_nsec == s.arm_ctime.tv_nsec,
                "arm_changed");
    } else {
        s.saw_arm = true;
        s.arm_inode = st.st_ino;
        s.arm_device = st.st_dev;
        s.arm_ctime = st.st_ctim;
    }
    return true;
}
void publish(State &s, const char *name, const void *data, size_t length) {
    const auto tmp = std::string(name) + ".part";
    Fd f(openat(s.dir, tmp.c_str(), O_WRONLY | O_CLOEXEC | O_CREAT | O_EXCL | O_NOFOLLOW, 0600));
    require(f.value >= 0, "output_collision");
    const auto *next = static_cast<const char *>(data);
    for (size_t left = length; left;) {
        auto n = write(f.value, next, left);
        if (n < 0 && errno == EINTR) continue;
        require(n > 0, "output_write");
        left -= n; next += n;
    }
    require(!fsync(f.value) && !linkat(s.dir, tmp.c_str(), s.dir, name, 0), "publish_collision");
    require(!unlinkat(s.dir, tmp.c_str(), 0) && !fsync(s.dir), "publish_sync");
}
__attribute__((constructor)) void initialize() {
    if (!getenv("TESY_F32_DIR")) return;
    try {
        State &s = state();
        const auto profile = env("TESY_F32_PROFILE");
        s.mock = profile == "mock";
        require(s.mock || profile == "stock120b", "profile");
        s.expected_caller = s.mock ? env("TESY_F32_CALLER_SHA256") : common_sha;
        s.expected_provider = env("TESY_F32_PROVIDER_SHA256");
        auto sha_ok = [](const std::string &x) {
            return x.size() == 64 && x.find_first_not_of("0123456789abcdef") == std::string::npos;
        };
        require(sha_ok(s.expected_provider) && sha_ok(s.expected_caller) &&
                (s.mock || s.expected_provider == stock_sha || s.expected_provider == derivative_sha),
                "unsealed_provider");
        s.dir = open(getenv("TESY_F32_DIR"), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        struct stat st{};
        require(s.dir >= 0 && !fstat(s.dir, &st) && (st.st_mode & 0777) == 0700 &&
                st.st_uid == geteuid(), "private_directory");
        DIR *entries = fdopendir(dup(s.dir));
        require(entries, "directory_open");
        errno = 0;
        while (auto *entry = readdir(entries)) {
            require(!strcmp(entry->d_name,".") || !strcmp(entry->d_name,".."), "directory_not_empty");
        }
        require(errno == 0, "directory_read");
        closedir(entries);
        s.pid = getpid();
    } catch (...) { _exit(125); }
}
template <typename T> T symbol(const char *name, const Dl_info &provider) {
    void *address = dlsym(RTLD_NEXT, name);
    Dl_info here{};
    require(address && dladdr(address, &here) && here.dli_fbase == provider.dli_fbase,
            "mixed_symbol_providers");
    return reinterpret_cast<T>(address);
}
void capture(State &s, llama_context *ctx, int32_t index, float *row, const void *return_pc) {
    require(index == expected_index && ctx && row, "row_or_index");
    Dl_info origin{}, caller{};
    const auto source = reinterpret_cast<const void *>(native());
    require(dladdr(source, &origin) && dladdr(return_pc, &caller), "unknown_source_or_caller");
    s.provider = image_hash(source, origin);
    s.caller = image_hash(return_pc, caller);
    s.caller_offset = reinterpret_cast<uintptr_t>(return_pc) - reinterpret_cast<uintptr_t>(caller.dli_fbase);
    require(s.provider == s.expected_provider && s.caller == s.expected_caller, "image_digest");
    require(caller.dli_sname && !strcmp(caller.dli_sname, sampler_name) &&
            (s.mock || s.caller_offset == 0x26951f || s.caller_offset == 0x269a6d), "wrong_caller");
    const auto model = symbol<const llama_model *(*)(const llama_context *)>("llama_get_model",origin)(ctx);
    require(model, "no_model");
    const auto vocab = symbol<const llama_vocab *(*)(const llama_model *)>("llama_model_get_vocab",origin)(model);
    require(vocab && symbol<int32_t (*)(const llama_vocab *)>("llama_vocab_n_tokens",origin)(vocab) == width,
            "vocab_shape");
    char arch[32]{};
    const auto meta = symbol<int32_t(*)(const llama_model *,const char *,char *,size_t)>("llama_model_meta_val_str",origin);
    require(meta(model,"general.architecture",arch,sizeof(arch)) == 7 && !strcmp(arch,"gpt-oss") &&
            symbol<int32_t(*)(const llama_model *)>("llama_model_n_layer",origin)(model) == 36 &&
            symbol<int32_t(*)(const llama_model *)>("llama_model_n_embd",origin)(model) == 2880, "model_shape");
    auto probs = symbol<Getter>("llama_get_sampled_probs_ith",origin);
    auto sampled_logits = symbol<Getter>("llama_get_sampled_logits_ith",origin);
    auto sampled_token = symbol<int32_t(*)(llama_context *,int32_t)>("llama_get_sampled_token_ith",origin);
    for (int i : {index, -1}) {
        require(!probs(ctx,i) && !sampled_logits(ctx,i) && sampled_token(ctx,i) == -1, "backend_sampled");
    }
    auto base = symbol<float *(*)(llama_context *)>("llama_get_logits",origin)(ctx);
    require(base == row && native()(ctx,-1) == base, "multiple_rows_or_nonraw");
    int best = 0;
    for (int i = 0; i < width; ++i) {
        require(std::isfinite(row[i]), "nonfinite");
        if (row[i] > row[best]) best = i;
    }
    s.row_hash = digest(row,width*sizeof(float));
    publish(s,"row.f32",row,width*sizeof(float));
    s.argmax = best;
}
} // namespace

extern "C" __attribute__((visibility("default"),noinline))
float *llama_get_logits_ith(llama_context *ctx, int32_t index) {
    const int before = errno;
    Getter original = native();
    State &s = state();
    bool observe = false;
    if (s.dir >= 0 && getpid() == s.pid) {
        std::lock_guard<std::mutex> hold(s.mutex);
        try {
            if (armed(s)) {
                ++s.armed_calls;
                require(s.armed_calls == 1, "duplicate");
                observe = s.error.empty();
            } else {
                ++s.prearm;
            }
        } catch (const std::runtime_error &) {
            if (s.error.empty()) s.error = "invalid_arm_or_duplicate";
        }
    }
    errno = before;
    float *row = original(ctx,index);
    const int after = errno;
    if (observe) {
        std::lock_guard<std::mutex> hold(s.mutex);
        try {
            capture(s,ctx,index,row,__builtin_extract_return_addr(__builtin_return_address(0)));
        } catch (const std::exception &e) {
            // Keep only reviewed static error labels. Preserve failure to the seal on process exit.
            if (s.error.empty()) s.error = e.what();
        }
    }
    errno = after;
    return row;
}

namespace {
__attribute__((destructor)) void seal() {
    if (!getenv("TESY_F32_DIR")) return;
    State &s = state();
    if (s.dir < 0 || getpid() != s.pid) return;
    std::lock_guard<std::mutex> hold(s.mutex);
    try {
        bool still_armed = false;
        try { still_armed = armed(s); }
        catch (const std::exception &) { if (s.error.empty()) s.error = "invalid_seal_arm"; }
        if ((!still_armed || s.armed_calls != 1 || s.argmax < 0) && s.error.empty()) {
            s.error = "missing_complete_capture";
        }
        const char *status = s.error.empty() ? "PASS" : "FAIL";
        if (s.error.find_first_not_of("abcdefghijklmnopqrstuvwxyz_") != std::string::npos)
            s.error = "unexpected_exception";
        std::string result = "{\"status\":\"" + std::string(status) + "\",\"reason\":\"" +
            s.error + "\",\"profile\":\"" + (s.mock ? "mock" : "stock120b") +
            "\",\"prearm_calls\":" + std::to_string(s.prearm) +
            ",\"armed_calls\":" + std::to_string(s.armed_calls) + ",\"row_index\":15,\"n_vocab\":201088" +
            ",\"row_bytes\":" + std::to_string(s.argmax < 0 ? 0 : width*sizeof(float)) +
            ",\"argmax\":" + std::to_string(s.argmax) + ",\"caller_offset\":" + std::to_string(s.caller_offset) +
            ",\"caller_sha256\":\"" + s.caller + "\",\"provider_sha256\":\"" + s.provider +
            "\",\"row_sha256\":\"" + s.row_hash + "\"}\n";
        publish(s,"capture.json",result.data(),result.size());
    } catch (...) {
        // A missing final receipt is a hard failure for the supervisor.
    }
    close(s.dir);
}
} // namespace

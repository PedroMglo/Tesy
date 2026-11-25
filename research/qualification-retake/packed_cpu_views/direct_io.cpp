// A fixture for C290 packed *weights* in one CPU AoS slot, without model or GPU.
#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <latch>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <linux/fiemap.h>
#include <linux/fs.h>
#include <linux/magic.h>
#include <openssl/evp.h>
#include <openssl/sha.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <unistd.h>

namespace {
constexpr size_t page = 4096, count = 40, component = 4406400, payload = 3 * component;
constexpr size_t window = 13221888, stride = 13258752, bias = 11520, tail = window - payload;
constexpr size_t arena_size = 2 * page + count * window, file_size = 2 * stride + window - page;
constexpr uint8_t guard = 0xd3;
static_assert(window % page == 0 && stride % page == 0 && tail == 2688);
using Gold = std::array<const char *, 4>;
constexpr std::array<Gold, 2> reference = {{
    { "9c0b02aa48dffcb6b879b02aec7883fd65f388e751b00870a9b4abbc723fdc77",
      "813fffee02d85727ae3a88f2338d2063678e50baae7a79662727d2677f5c73f3",
      "59eef4b28d9ec881ad7df0a0ccc8419c88db73b672233850714bd1e825a330ae",
      "f5afaef91d5da59009103c4522d370a9ad1bd9a971765cfcdbf0a2d51f1e5f28" },
    { "32d1e1df329e961c2a3e2ab8125737f02ef9e798c3380c9a723dfc173c9ea64a",
      "cedbdd816cce1862983e7e27f634b4df3226239ec84b78ac5e7a35656c36c695",
      "048588f6e3ca4995786d241dc92da3bd45f953ef829cd6ed5258a84884502e0d",
      "0a9fe4220c1a3f807f6742ffd0331f4dfa9ba7198d063b11a1d4c87ce7d7177f" }
}};

void require(bool ok, const char *label) {
    if (!ok) throw std::runtime_error(label);
}

struct FD {
    int value;
    explicit FD(int fd) : value(fd) { require(fd >= 0, "open"); }
    ~FD() { close(value); }
    FD(const FD&) = delete;
};

struct Map {
    void *addr;
    size_t size;
    Map(size_t n, int prot, int flags, int fd, off_t off = 0)
        : addr(mmap(nullptr, n, prot, flags, fd, off)), size(n) { require(addr != MAP_FAILED, "mmap"); }
    ~Map() { munmap(addr, size); }
    Map(const Map&) = delete;
    uint8_t *bytes() const { return static_cast<uint8_t *>(addr); }
};

std::string sha(const uint8_t *bytes, size_t n) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    require(SHA256(bytes, n, hash) != nullptr, "sha256");
    std::ostringstream s;
    for (uint8_t b : hash) s << std::hex << std::setw(2) << std::setfill('0') << unsigned(b);
    return s.str();
}

// Every part, including the alignment gaps, contains incompressible fixture bytes.
// The shrink at EOF is deliberate and applies to the third entry only.
void write_pack(int fd) {
    constexpr std::array<size_t, 8> sizes = {component, component, component, tail, bias, bias, bias,
                                             stride - window - 3 * bias};
    std::vector<uint8_t> buf(stride);
    for (int expert = 0; expert < 2; ++expert) {
        size_t off = 0;
        for (size_t k = 0; k < sizes.size(); ++k) {
            const std::string label = "Tesy-C290-direct-v1/expert" + std::to_string(expert)
                                    + "/area" + std::to_string(k);
            std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
            require(ctx && EVP_DigestInit_ex(ctx.get(), EVP_shake256(), nullptr) == 1 &&
                    EVP_DigestUpdate(ctx.get(), label.data(), label.size()) == 1 &&
                    EVP_DigestFinalXOF(ctx.get(), buf.data() + off, sizes[k]) == 1, "shake256");
            off += sizes[k];
        }
        require(off == stride && write(fd, buf.data(), stride) == ssize_t(stride), "write_fixture_record");
    }
    require(write(fd, buf.data(), window - page) == ssize_t(window - page) && fsync(fd) == 0,
            "write_and_sync_short_record");
}

std::string device_name(unsigned long long mount_id) {
    std::ifstream in("/proc/self/mountinfo");
    std::string line, word;
    while (std::getline(in, line)) {
        std::istringstream s(line);
        unsigned long long id = 0;
        s >> id;
        if (id != mount_id) continue;
        while (s >> word && word != "-") {}
        std::string filesystem, dev;
        s >> filesystem >> dev;
        require(filesystem == "btrfs" && dev.starts_with("/dev/nvme"), "not_nvme_btrfs_mount");
        std::string name = dev.substr(5);
        require(name.find_first_not_of("nvme0123456789p") == std::string::npos &&
                std::filesystem::exists("/sys/class/block/" + name), "missing_native_NVMe_device");
        return name;
    }
    throw std::runtime_error("mount_id_unresolved");
}

size_t fiemap_plain(int fd) {
    constexpr size_t max_extents = 256;
    std::vector<uint64_t> storage((sizeof(fiemap) + max_extents * sizeof(fiemap_extent) + 7) / 8);
    fiemap *map = reinterpret_cast<fiemap *>(storage.data());
    map->fm_length = file_size;
    map->fm_extent_count = max_extents;
    map->fm_flags = FIEMAP_FLAG_SYNC;
    require(ioctl(fd, FS_IOC_FIEMAP, map) == 0 && map->fm_mapped_extents > 0, "fiemap_missing");
    uint64_t covered = 0;
    for (unsigned i = 0; i < map->fm_mapped_extents; ++i) {
        const auto &e = map->fm_extents[i];
        require(e.fe_logical == covered && e.fe_length &&
                (e.fe_flags & ~(FIEMAP_EXTENT_LAST | FIEMAP_EXTENT_SHARED)) == 0,
                "compressed_sparse_inline_or_unqualified_extent");
        covered += e.fe_length;
    }
    require(covered >= file_size, "fiemap_coverage");
    return map->fm_mapped_extents;
}

size_t resident_pages(int fd) {
    Map file(file_size, PROT_NONE, MAP_SHARED, fd);
    std::vector<unsigned char> resident((file_size + page - 1) / page);
    require(mincore(file.addr, file_size, resident.data()) == 0, "mincore");
    return std::count_if(resident.begin(), resident.end(), [](uint8_t p){ return p & 1; });
}

struct Outcome {
    const char *status = "UNSET";
    size_t calls = 0;
    ssize_t returned = -1;
    int sys_errno = 0;
    bool published = false;
    unsigned generation = 0;
    std::array<std::string, 4> hashes;
};

struct ReadGate {
    std::latch claimed{1}, enter_syscall{1}, returned{1}, hand_back{1};
};
enum SlotState : unsigned { VACANT, LOADING, INVALID, RESIDENT };

struct Arena {
    Map memory{arena_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1};
    std::array<std::atomic<unsigned>, count> state{}, generation{};
    uint8_t *slot(size_t i) { return memory.bytes() + page + i * window; }

    Arena() {
        for (size_t i = 0; i < count; ++i) {
            std::memset(slot(i), guard, page);
            std::memset(slot(i) + window - page, guard, page);
        }
        std::memset(memory.bytes(), guard, page);
        std::memset(slot(count), guard, page);
    }

    Outcome read(int fd, size_t slot_id, size_t entry, size_t file_offset, const Gold &expected,
                 ReadGate *gate = nullptr) {
        Outcome r;
        require(slot_id < count, "bad_slot");
        uint8_t *dst = slot(slot_id);
        if (entry > 2 || file_offset != entry * stride ||
            file_offset % page || reinterpret_cast<uintptr_t>(dst) % page) {
            r.status = "REJECT_OFFSET";
            return r;
        }
        auto prior = state[slot_id].load(std::memory_order_acquire);
        if ((prior != VACANT && prior != INVALID) ||
            !state[slot_id].compare_exchange_strong(prior, LOADING)) {
            r.status = "REJECT_OWNED";
            return r;
        }
        r.generation = ++generation[slot_id];
        if (gate) { gate->claimed.count_down(); gate->enter_syscall.wait(); }
        r.calls = 1;
        r.returned = pread(fd, dst, window, static_cast<off_t>(file_offset));
        const int saved_errno = errno;
        if (gate) { gate->returned.count_down(); gate->hand_back.wait(); }
        if (r.returned < 0) {
            r.sys_errno = saved_errno;
            r.status = "REJECT_SYSCALL";
            state[slot_id].store(INVALID, std::memory_order_release);
            return r;
        }
        if (r.returned != ssize_t(window)) {
            r.status = "REJECT_SHORT";
            state[slot_id].store(INVALID, std::memory_order_release);
            return r;
        }
        for (size_t k = 0; k < 4; ++k) {
            r.hashes[k] = sha(dst + k * component, k < 3 ? component : tail);
            if (r.hashes[k] != expected[k]) {
                r.status = "REJECT_DIGEST";
                state[slot_id].store(INVALID, std::memory_order_release);
                return r;
            }
        }
        state[slot_id].store(RESIDENT, std::memory_order_release);
        r.status = "PUBLISHED";
        r.published = true;
        return r;
    }

    static bool page_ok(const uint8_t *p) {
        return std::all_of(p, p + page, [](uint8_t x){ return x == guard; });
    }
    void guards() {
        require(page_ok(memory.bytes()) && page_ok(slot(count)), "outer_guard");
        for (size_t i = 0; i < count; ++i) {
            if (i != 0 && i != 39 && i != 3 && i != 4 && i != 5 && i != 6)
                require(page_ok(slot(i)) && page_ok(slot(i) + window - page), "neighbour_guard");
        }
    }
    std::string live() {
        // All bytes of both immediate neighbours and both original positive controls.
        std::string out;
        for (size_t i : {0, 3, 5, 39}) {
            require(state[i].load(std::memory_order_acquire) == RESIDENT, "missing_live_slot");
            out += sha(slot(i), window);
        }
        return sha(reinterpret_cast<const uint8_t*>(out.data()), out.size());
    }
    std::string checkpoint() {
        guards();
        return live();
    }
};

void emit_row(const char *name, const Outcome &r) {
    std::cout << "\"" << name << "\":{\"status\":\"" << r.status << "\",\"pread_calls\":" << r.calls
              << ",\"return_bytes\":" << r.returned << ",\"errno\":" << r.sys_errno
              << ",\"published\":" << (r.published ? "true" : "false") << ",\"sha256\":[";
    for (size_t i = 0; i < r.hashes.size() && !r.hashes[i].empty(); ++i)
        std::cout << (i ? ",\"" : "\"") << r.hashes[i] << "\"";
    std::cout << "]}";
}

void trial(int dir, bool physical) {
    require(sysconf(_SC_PAGESIZE) == long(page), "host_page_size");
    constexpr const char *name = "synthetic-c290.pack";
    {
        FD create(openat(dir, name, O_CREAT | O_EXCL | O_NOFOLLOW | O_WRONLY | O_CLOEXEC, 0600));
        write_pack(create.value);
    }
    FD direct(openat(dir, name, O_NOFOLLOW | O_RDONLY | O_CLOEXEC | O_DIRECT));
    int flags = fcntl(direct.value, F_GETFL);
    require(flags >= 0 && (flags & O_DIRECT) != 0, "O_DIRECT_missing");
    struct statx st{};
    require(statx(direct.value, "", AT_EMPTY_PATH, STATX_SIZE | STATX_DIOALIGN | STATX_MNT_ID, &st) == 0
            && st.stx_size == file_size && (st.stx_mask & STATX_MNT_ID), "source_statx");
    if ((st.stx_mask & STATX_DIOALIGN) != 0) {
        require(st.stx_dio_mem_align && st.stx_dio_offset_align &&
                page % st.stx_dio_mem_align == 0 && page % st.stx_dio_offset_align == 0, "dio_alignment");
    }
    std::string device = "fixture";
    size_t extents = 0, before = 0, after = 0;
    if (physical) {
        struct statfs fs{};
        require(fstatfs(direct.value, &fs) == 0 && fs.f_type == BTRFS_SUPER_MAGIC, "not_Btrfs");
        device = device_name(st.stx_mnt_id);
        extents = fiemap_plain(direct.value);
        require(posix_fadvise(direct.value, 0, 0, POSIX_FADV_DONTNEED) == 0, "file_local_fadvise");
        before = resident_pages(direct.value);
        require(before == 0, "fixture_pages_not_cold");
    }

    Arena a;
    Outcome first, last;
    // Separate destination slots; the two jobs may overlap. No throughput inference.
    std::exception_ptr error[2];
    std::jthread t0([&] {
        try { first = a.read(direct.value, 0, 1, stride, reference[1]); }
        catch (...) { error[0] = std::current_exception(); }
    });
    std::jthread t1([&] {
        try { last = a.read(direct.value, 39, 0, 0, reference[0]); }
        catch (...) { error[1] = std::current_exception(); }
    });
    t0.join();
    t1.join();
    for (auto &e : error) if (e) std::rethrow_exception(e);
    require(first.published && last.published, "positive_slot_or_bytes");
    if (physical) {
        after = resident_pages(direct.value);
        require(after == 0, "page_cache_populated_by_reads");
    }
    Outcome left = a.read(direct.value, 3, 0, 0, reference[0]);
    Outcome right = a.read(direct.value, 5, 1, stride, reference[1]);
    require(left.published && right.published, "neighbours_not_live");
    std::vector<std::string> live = {a.checkpoint()};
    Outcome wrong = a.read(direct.value, 3, 1, 0, reference[1]);
    live.push_back(a.checkpoint());
    // The bad-fd destination is vacant. Slot 5 is now a live immediate neighbour.
    Outcome failed = a.read(-1, 8, 0, 0, reference[0]);
    live.push_back(a.checkpoint());
    uint8_t *const failed_dst = a.slot(4);
    std::memset(failed_dst, guard, window);
    Outcome short_read;
    ReadGate gate;
    std::jthread short_worker([&] {
        short_read = a.read(direct.value, 4, 2, 2 * stride, reference[0], &gate);
    });
    gate.claimed.wait();
    Outcome denied_pre = a.read(-1, 4, 0, 0, reference[0]);
    const auto gen_pre = a.generation[4].load();
    const auto state_pre = a.state[4].load();
    gate.enter_syscall.count_down();
    gate.returned.wait();
    Outcome denied_post = a.read(-1, 4, 0, 0, reference[0]);
    const auto gen_post = a.generation[4].load();
    const auto state_post = a.state[4].load();
    gate.hand_back.count_down();
    short_worker.join();
    require(denied_pre.calls == 0 && denied_post.calls == 0 && !denied_pre.published &&
            !denied_post.published && std::string(denied_pre.status) == "REJECT_OWNED" &&
            std::string(denied_post.status) == "REJECT_OWNED" && gen_pre == 1 && gen_post == 1 &&
            state_pre == LOADING && state_post == LOADING && short_read.generation == 1 &&
            a.state[4].load() == INVALID && a.generation[4].load() == 1, "failed_slot_ownership");
    live.push_back(a.checkpoint());
    const uint8_t *const last_page = failed_dst + window - page;
    std::array<size_t, 256> tail_counts{};
    std::string tail_hex;
    static constexpr char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < page; ++i) {
        const auto byte = last_page[i];
        ++tail_counts[byte]; tail_hex.push_back(digits[byte >> 4]); tail_hex.push_back(digits[byte & 15]);
    }
    const std::string tail_hash = sha(last_page, page);
    Outcome corrupt = a.read(direct.value, 6, 0, 0, reference[1]);
    live.push_back(a.checkpoint());
    require(wrong.calls == 0 && !wrong.published && short_read.returned == ssize_t(window - page) &&
            !short_read.published && failed.sys_errno == EBADF && !failed.published &&
            !corrupt.published && corrupt.hashes[0] == reference[0][0], "faults_or_publication");
    // Entry 2 was a truncated copy of expert 1. Expert 0 must replace every byte,
    // including the padding, in the same slot before generation 2 can publish.
    Outcome retry = a.read(direct.value, 4, 0, 0, reference[0]);
    live.push_back(a.checkpoint());
    require(std::all_of(live.begin(), live.end(), [&](const std::string &v){ return v == live[0]; }) &&
            failed_dst == a.slot(4) && retry.published && retry.generation == 2 &&
            retry.returned == ssize_t(window) && a.generation[4].load() == 2, "reassignment_or_live_bytes");
    for (size_t i = 0; i < count; ++i)
        require((a.state[i].load() == RESIDENT) == (i==0 || i==3 || i==4 || i==5 || i==39),
                "publication_count_or_identity");
    a.memory.bytes()[page-1] ^= 1;
    bool caught_bad_guard = false;
    try { a.guards(); } catch (const std::runtime_error &e) {
        caught_bad_guard = std::string(e.what()) == "outer_guard";
    }
    a.memory.bytes()[page-1] ^= 1;
    require(caught_bad_guard && a.checkpoint() == live[0], "guard_mutation_control");
    a.slot(3)[window-1] ^= 1; // isolated control after the live-data checks, restored before exit
    const bool caught_bad_neighbour = a.checkpoint() != live[0];
    a.slot(3)[window-1] ^= 1;
    require(caught_bad_neighbour && a.checkpoint() == live[0], "live_neighbour_mutation_control");
    require(unlinkat(dir, name, 0) == 0, "private_cleanup");

    std::cout << "{\"status\":\"" << (physical ? "PASS_BTRFS_NVME_DIRECT_FIXTURE" : "PASS_SYNTHETIC_ONLY")
              << "\",\"device\":\"" << device << "\",\"file_bytes\":" << file_size
              << ",\"component\":" << component << ",\"payload\":" << payload << ",\"slot_stride\":" << window
              << ",\"pack_stride\":" << stride << ",\"logical_slots\":" << count << ",\"arena_VMA\":" << arena_size
              << ",\"O_DIRECT\":true,\"guard_pages_intact\":true,\"private_pack_unlinked\":true"
              << ",\"DIOALIGN_known\":" << ((st.stx_mask & STATX_DIOALIGN) ? "true" : "false")
              << ",\"DIO_mem\":" << st.stx_dio_mem_align << ",\"DIO_offset\":" << st.stx_dio_offset_align
              << ",\"FIEMAP_count\":" << extents << ",\"mincore_checked\":" << (physical ? "true" : "false")
              << ",\"resident_before\":" << before << ",\"resident_after_positives\":" << after << ",\"cases\":{";
    emit_row("slot0_expert1", first); std::cout << ",";
    emit_row("slot39_expert0", last); std::cout << ",";
    emit_row("wrong_offset", wrong); std::cout << ",";
    emit_row("short_eof", short_read); std::cout << ",";
    emit_row("failed_fd", failed); std::cout << ",";
    emit_row("wrong_content_digest", corrupt);
    std::cout << "},\"failed_generation\":{\"slot\":4,\"first_generation\":" << short_read.generation
              << ",\"state_after_return\":\"INVALID\",\"generation_before_syscall\":" << gen_pre
              << ",\"generation_after_syscall_before_return\":" << gen_post
              << ",\"reassignment_generation\":" << retry.generation
              << ",\"same_destination\":true,\"guard_mutation_detected\":true,\"published_slots\":[0,3,4,5,39],"
              << "\"live_neighbour_mutation_detected\":true,\"tail_sha256\":\"" << tail_hash
              << "\",\"tail_hex\":\"" << tail_hex << "\",\"tail_histogram\":{";
    bool first_key = true;
    for (size_t k=0; k<tail_counts.size(); ++k) if (tail_counts[k]) {
        std::cout << (first_key ? "\"" : ",\"") << k << "\":" << tail_counts[k]; first_key = false;
    }
    std::cout << "},\"live_sha256_at_checkpoints\":[";
    for (size_t i=0; i<live.size(); ++i) std::cout << (i ? ",\"" : "\"") << live[i] << "\"";
    std::cout << "],"; emit_row("owned_before_syscall", denied_pre); std::cout << ",";
    emit_row("owned_before_handback", denied_post); std::cout << ",";
    emit_row("slot3_live", left); std::cout << ","; emit_row("slot5_live", right);
    std::cout << ","; emit_row("slot4_reassigned", retry); std::cout << "}}\n";
}
} // namespace

int main(int argc, char **argv) {
    try {
        require(argc == 3, "usage_direct_io_--nvme_or_--fixture_NEW_ABSOLUTE_DIR");
        const std::string mode = argv[1];
        const std::filesystem::path target(argv[2]);
        require((mode == "--nvme" || mode == "--fixture") && target.is_absolute() &&
                !target.filename().empty() && target.lexically_normal() == target, "invalid_mode_or_path");
        umask(0077);
        if (mode == "--nvme") {
            FD parent(open(target.parent_path().c_str(), O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
            struct statx st{};
            require(statx(parent.value, "", AT_EMPTY_PATH, STATX_MNT_ID, &st) == 0 &&
                    (st.stx_mask & STATX_MNT_ID), "parent_mount_id");
            (void)device_name(st.stx_mnt_id);
        }
        require(mkdir(target.c_str(), 0700) == 0, "exclusive_directory");
        FD dir(open(target.c_str(), O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
        trial(dir.value, mode == "--nvme");
        return 0;
    } catch (const std::exception &e) {
        std::cout << "{\"status\":\"FAIL_PRESERVED\",\"reason\":\""
                  << (dynamic_cast<const std::runtime_error *>(&e) && !dynamic_cast<const std::system_error *>(&e)
                      ? e.what() : "native_exception") << "\"}\n";
        return 1;
    }
}

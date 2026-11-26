#pragma once

#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <functional>
#include <limits>
#include <stdexcept>
#include <string>
#include <system_error>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>

namespace tesy {

enum class Source { mapped, ranges };

// One owner per context and backend stream. The caller authenticates the tensor
// interval against the target loader before submitting it.
class BankInput {
public:
    static constexpr size_t page = 4096;

    BankInput(int model_fd, size_t capacity, Source source, std::function<void()> synchronize)
        : capacity_(capacity), source_(source), synchronize_(std::move(synchronize)) {
        if (capacity == 0 || capacity % page || sysconf(_SC_PAGESIZE) != long(page) || !synchronize_) {
            throw std::invalid_argument("scratch geometry or missing backend fence");
        }
        struct stat authority{}, actual{};
        if (fstat(model_fd, &authority) < 0) system_failure("model descriptor");
        if (!S_ISREG(authority.st_mode) || authority.st_size < 0) throw std::invalid_argument("model file");
        // Opening the procfd gives the same inode a separate open-file description.
        const std::string path = "/proc/self/fd/" + std::to_string(model_fd);
        int fd = open(path.c_str(), O_RDONLY | O_CLOEXEC);
        if (fd < 0) system_failure("open range reader");
        try {
            if (fstat(fd, &actual) < 0) system_failure("range descriptor");
            if (actual.st_dev != authority.st_dev || actual.st_ino != authority.st_ino ||
                actual.st_size != authority.st_size) throw std::runtime_error("different model file");
            if (source == Source::ranges) {
                int rc = posix_fadvise(fd, 0, 0, POSIX_FADV_RANDOM);
                if (rc != 0) throw std::system_error(rc, std::generic_category(), "range advice");
            }
            void *ptr = mmap(nullptr, capacity, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (ptr == MAP_FAILED) system_failure("scratch allocation");
            scratch_ = static_cast<char *>(ptr);
            std::memset(scratch_, 0, capacity);
            fd_ = fd;
            size_ = actual.st_size;
        } catch (...) {
            close(fd);
            throw;
        }
    }

    BankInput(const BankInput &) = delete;
    BankInput &operator=(const BankInput &) = delete;

    ~BankInput() {
        // The supplied fence must still be live at teardown. A failed drain
        // must terminate the process before the backing memory can be released.
        if (pending_) synchronize_();
        munmap(scratch_, capacity_);
        close(fd_);
    }

    // Replaces the existing ID-read fence, including sites that emit no fills.
    void synchronize_ids() {
        synchronize_();
        pending_ = false;
        cursor_ = 0;
    }

    template<class Submit>
    void send(off_t offset, const void *mapped, size_t bytes, Submit submit) {
        if (failed_ || offset < 0 || offset > size_ || bytes == 0 ||
            bytes > uint64_t(size_ - offset) || bytes > size_t(std::numeric_limits<ssize_t>::max())) {
            throw std::invalid_argument("invalid or failed bank source");
        }
        const size_t head = size_t(offset) % page;
        if (head > capacity_ - cursor_ || bytes > capacity_ - cursor_ - head) {
            throw std::length_error("live bank inputs exceed frozen capacity");
        }
        const size_t start = cursor_ + head;
        const void *src = mapped;
        if (source_ == Source::ranges) {
            const ssize_t n = pread(fd_, scratch_ + start, bytes, offset);
            if (n != ssize_t(bytes)) {
                failed_ = true;
                if (n < 0) system_failure("bank pread");
                throw std::runtime_error("short bank pread");
            }
            src = scratch_ + start;
        } else if (!src) {
            throw std::invalid_argument("missing mapped source");
        }
        cursor_ = ((start + bytes - 1) / page + 1) * page;
        // A submit that throws may already have enqueued a copy.
        pending_ = true;
        try {
            submit(src, bytes);
        } catch (...) {
            failed_ = true;
            throw;
        }
    }

private:
    [[noreturn]] static void system_failure(const char *what) {
        throw std::system_error(errno, std::generic_category(), what);
    }
    size_t capacity_;
    Source source_;
    std::function<void()> synchronize_;
    int fd_ = -1;
    off_t size_ = 0;
    char *scratch_ = nullptr;
    size_t cursor_ = 0;
    bool pending_ = false;
    bool failed_ = false;
};

} // namespace tesy

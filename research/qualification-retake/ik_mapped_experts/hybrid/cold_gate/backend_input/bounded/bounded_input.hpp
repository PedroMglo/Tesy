#pragma once
#include "../bank_input.hpp"

namespace tesy {

// The existing owner still performs all reads, submissions and teardown.
// Only this context's stream may release the addresses it has submitted.
class BoundedBankInput {
public:
    BoundedBankInput(int fd, size_t capacity, Source source, std::function<void()> fence)
        : input_(fd, capacity, source, std::move(fence)), capacity_(capacity), remaining_(capacity) {}

    void synchronize_ids() {
        require_live();
        try {
            input_.synchronize_ids();
            remaining_ = capacity_;
        } catch (...) {
            failed_ = true;
            throw;
        }
    }

    template<class Submit>
    void send(off_t offset, const void *mapped, size_t bytes, Submit submit) {
        require_live();
        if (offset < 0 || bytes == 0) throw std::invalid_argument("invalid bank input");
        constexpr size_t page = BankInput::page;
        const size_t displacement = size_t(offset) % page;
        if (bytes > capacity_ - displacement) throw std::length_error("single SET exceeds scratch");
        const size_t reservation = ((bytes + displacement - 1) / page + 1) * page;
        if (reservation > remaining_) {
            synchronize_ids();
            ++extra_drains_;
        }
        try {
            input_.send(offset, mapped, bytes, std::move(submit));
            remaining_ -= reservation;
        } catch (...) {
            failed_ = true;
            throw;
        }
    }

    size_t extra_drains() const { return extra_drains_; }

private:
    void require_live() const {
        if (failed_) throw std::logic_error("bank reader failed");
    }
    BankInput input_;
    const size_t capacity_;
    size_t remaining_;
    size_t extra_drains_ = 0;
    bool failed_ = false;
};

} // namespace tesy

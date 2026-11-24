#pragma once

#include <array>
#include <cstdint>
#include <stdexcept>
#include <vector>

// Only the diagnostic harness constructs this object. Backend callbacks run under the manager mutex.
class prefix_routes {
public:
    static constexpr std::size_t max_bytes = 1024*1024;

    explicit prefix_routes(std::size_t limit = max_bytes) : limit_(limit) {
        if (limit < 4 || limit > max_bytes) throw std::invalid_argument("prefix route capacity");
        journal_.reserve(limit);
        for (const char c : {'T','P','R','1'}) byte(static_cast<uint8_t>(c));
    }

    bool begin_call(int rows) {
        if (!ok_ || sealed_ || !end_call() || rows < 1 || rows > 256 || calls_ >= 8192) return fail();
        ++calls_;
        in_call_ = true;
        expected_ = rows;
        received_ = 0;
        ubatches_ = 0;
        byte('C'); word(calls_); word(rows);
        return ok_;
    }

    bool begin_ubatch(int rows, const int32_t *pos, const int8_t *output) {
        if (!ok_ || !in_call_ || !end_ubatch() || rows < 1 || rows > 32 ||
                received_ + rows > expected_ || !pos || !output) return fail();
        byte('U'); word(++ubatches_); byte(rows);
        outputs_ = 0;
        for (int i=0; i<rows; ++i) {
            // The bounded C294 one-sequence harness appends each position once, starting at zero.
            if (pos[i] != next_pos_++ || pos[i] >= 8192 || (output[i] != 0 && output[i] != 1)) {
                return fail();
            }
            word(pos[i]); byte(output[i]); outputs_ += output[i];
        }
        received_ += rows;
        rows_ = rows;
        next_layer_ = 0;
        in_ubatch_ = true;
        return ok_;
    }

    bool route(int layer, bool multi, int64_t rows, int64_t topk, const int32_t *ids) {
        if (!ok_ || !in_ubatch_ || !ids || layer != next_layer_ || layer >= 36 || topk != 4 ||
                rows <= 0 || rows != (layer == 35 ? outputs_ : rows_)) return fail();
        byte('R'); byte(layer); byte(multi ? 'M' : 'S'); byte(rows);
        for (int i=0; i<rows; ++i) {
            std::array<int32_t,4> selected{};
            for (int k=0; k<4; ++k) {
                const int32_t expert = ids[4*i+k];
                if (expert < 0 || expert >= 128) return fail();
                for (int j=0; j<k; ++j) if (selected[j] == expert) return fail();
                selected[k] = expert;
                byte(expert);
            }
        }
        ++next_layer_;
        return ok_;
    }

    bool cut(char tag) {
        if (!ok_ || sealed_ || !in_call_ || !end_call() ||
                !((cuts_ == 0 && tag == 'P') || (cuts_ == 1 && tag == 'I'))) return fail();
        ++cuts_;
        byte(tag);
        return ok_;
    }

    bool finish() {
        if (!ok_ || sealed_ || !in_call_ || cuts_ != 2 || !end_call()) return fail();
        byte('F');
        sealed_ = ok_;
        return sealed_;
    }

    const std::vector<uint8_t> &data() const {
        if (!sealed_ || !ok_) throw std::logic_error("incomplete route observation");
        return journal_;
    }

private:
    bool fail() { ok_ = false; return false; }
    void byte(unsigned int value) {
        if (journal_.size() >= limit_) { fail(); return; }
        journal_.push_back(static_cast<uint8_t>(value));
    }
    void word(unsigned int value) { byte(value & 255u); byte(value >> 8); }

    bool end_ubatch() {
        if (!in_ubatch_) return true;
        if (next_layer_ == 35 && outputs_ == 0) { byte('Z'); ++next_layer_; }
        if (next_layer_ != 36) return fail();
        in_ubatch_ = false;
        byte('E');
        return ok_;
    }
    bool end_call() {
        if (!in_call_) return true;
        if (!end_ubatch() || received_ != expected_) return fail();
        in_call_ = false;
        byte('D');
        return ok_;
    }

    std::vector<uint8_t> journal_;
    std::size_t limit_;
    bool ok_ = true, sealed_ = false, in_call_ = false, in_ubatch_ = false;
    int calls_ = 0, expected_ = 0, received_ = 0, ubatches_ = 0, next_pos_ = 0;
    int rows_ = 0, outputs_ = 0, next_layer_ = 0, cuts_ = 0;
};

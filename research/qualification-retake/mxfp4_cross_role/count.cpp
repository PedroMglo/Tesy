// Count contexts for one expert in physical gate, down, up order. No floating-point weights.
#include <array>
#include <charconv>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <string_view>
#include <vector>

using Table = std::array<uint32_t, 16>;

struct Matrix {
    int width;
    std::vector<uint8_t> data;
    explicit Matrix(int n) : width(n), data(n * (n / 32) * 17) {}
    const uint8_t *block(int row, int col) const {
        return &data[17 * (row * (width / 32) + col / 32)];
    }
    int nibble(int row, int col) const {
        auto p = block(row, col);
        return (p[1 + col % 16] >> (4 * ((col % 32) / 16))) & 15;
    }
};

static void count(const Matrix &weight, const Matrix &gate, const Matrix &up, int peers) {
    constexpr int spatial_count = 256 * 2 * 17;
    const int alphabet = peers == 2 ? 256 : peers == 1 ? 16 : 1;
    std::vector<Table> base(spatial_count);
    std::vector<int> indices(spatial_count * alphabet, -1);
    std::vector<Table> joint;

    for (int row = 0; row < weight.width; ++row) {
        int previous = 16;
        for (int col = 0; col < weight.width; ++col) {
            int scale = weight.block(row, col)[0];
            int half = (col % 32) / 16;
            int context = (scale * 2 + half) * 17 + previous;
            int side = 0;
            if (peers == 1) {
                side = gate.nibble(row, col);
            } else if (peers == 2) {
                side = gate.nibble(col, row) * 16 + up.nibble(col, row);
            }
            int &index = indices[context * alphabet + side];
            if (index == -1) {
                index = static_cast<int>(joint.size());
                joint.emplace_back(Table{});
            }
            const auto symbol = weight.nibble(row, col);
            ++joint[index][symbol];
            ++base[context][symbol];
            previous = symbol;
        }
    }

    std::printf("ROLE %d %zu\n", peers, joint.size());
    for (int c = 0; c < spatial_count; ++c) {
        bool occupied = false;
        for (auto n : base[c]) occupied |= n > 0;
        if (!occupied) continue;
        std::printf("%d %d %d", c / 34, c / 17 % 2, c % 17);
        for (auto n : base[c]) std::printf(" %u", n);
        std::puts("");
    }
    // Sufficient statistics for sum_context [n log(n) - sum_symbol n_s log(n_s)].
    std::map<uint32_t, int64_t> terms;
    for (const Table &t : joint) {
        uint32_t sum = 0;
        for (auto n : t) {
            sum += n;
            if (n) --terms[n];
        }
        ++terms[sum];
    }
    std::puts("TERMS");
    for (auto [n, multiplicity] : terms) {
        if (multiplicity) std::printf("%u %lld\n", n, static_cast<long long>(multiplicity));
    }
    std::puts("END");
}

int main(int argc, char **argv) {
    int n = 0;
    if (argc != 2) return 1;
    std::string_view arg(argv[1]);
    auto parsed = std::from_chars(arg.begin(), arg.end(), n);
    if (parsed.ec != std::errc{} || parsed.ptr != arg.end() || n <= 0 || n % 32 || n > 2880) return 1;
    Matrix gate(n), down(n), up(n);
    for (auto m : {&gate, &down, &up}) {
        if (std::fread(m->data.data(), 1, m->data.size(), stdin) != m->data.size()) return 2;
    }
    if (std::fgetc(stdin) != EOF || std::ferror(stdin)) return 2;
    count(gate, gate, up, 0);
    count(up, gate, up, 1);
    count(down, gate, up, 2);
    return std::ferror(stdout) ? 3 : 0;
}

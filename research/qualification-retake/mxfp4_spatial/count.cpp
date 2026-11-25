// Count (scale, half-block, previous code in this row) -> next E2M1 code.
#include <array>
#include <charconv>
#include <cstdint>
#include <cstdio>
#include <string_view>

int main(int argc, char **argv) {
    if (argc != 2) return 1;
    unsigned blocks_per_row = 0;
    std::string_view arg(argv[1]);
    auto result = std::from_chars(arg.begin(), arg.end(), blocks_per_row);
    if (result.ec != std::errc{} || result.ptr != arg.end() ||
        blocks_per_row == 0 || blocks_per_row > 90) return 1;

    static uint32_t counts[256][2][17][16]{};
    std::array<unsigned char, 90 * 17> row{};
    unsigned rows = 0;
    const size_t row_bytes = blocks_per_row * 17;
    while (true) {
        const size_t n = std::fread(row.data(), 1, row_bytes, stdin);
        if (n == 0) break;
        if (n != row_bytes || ++rows > 2880) return 2;
        unsigned prev = 16;
        for (unsigned b = 0; b < blocks_per_row; ++b) {
            const unsigned char *block = row.data() + b * 17;
            for (unsigned half = 0; half < 2; ++half) {
                auto &table = counts[block[0]][half];
                for (unsigned j = 0; j < 16; ++j) {
                    const unsigned code = (block[1 + j] >> (4 * half)) & 15;
                    ++table[prev][code];
                    prev = code;
                }
            }
        }
    }
    if (rows == 0 || std::ferror(stdin)) return 2;
    for (unsigned s = 0; s < 256; ++s) {
        for (unsigned h = 0; h < 2; ++h) {
            for (unsigned p = 0; p < 17; ++p) {
                const auto &table = counts[s][h][p];
                uint32_t sum = 0;
                for (auto n : table) sum += n;
                if (!sum) continue;
                std::printf("%u %u %u", s, h, p);
                for (auto n : table) std::printf(" %u", n);
                std::puts("");
            }
        }
    }
    return std::ferror(stdout) ? 3 : 0;
}

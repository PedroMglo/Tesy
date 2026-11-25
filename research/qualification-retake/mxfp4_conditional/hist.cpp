// Count the 32 nibbles following each MXFP4 block's one-byte E8M0 scale.
// Protocol: one exact component on stdin. Output sparse [scale, counts[16]] rows.
#include <array>
#include <charconv>
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <string_view>

int main(int argc, char **argv) {
    if (argc != 2) {
        return 1;
    }
    const std::string_view count_text(argv[1]);
    unsigned int blocks = 0;
    const auto parsed = std::from_chars(count_text.begin(), count_text.end(), blocks);
    if (parsed.ec != std::errc{} || parsed.ptr != count_text.end() ||
        blocks == 0 || blocks > 259200) {
        return 1;
    }

    std::array<std::array<std::uint32_t, 16>, 256> counts{};
    constexpr unsigned int chunk_blocks = 1024;
    std::array<unsigned char, 17 * chunk_blocks> buffer{};
    for (unsigned int left = blocks; left > 0;) {
        const unsigned int n = left < chunk_blocks ? left : chunk_blocks;
        if (std::fread(buffer.data(), 1, 17 * n, stdin) != 17 * n) {
            return 2;
        }
        for (unsigned int block = 0; block < n; ++block) {
            const auto *data = buffer.data() + 17 * block;
            auto &row = counts[data[0]];
            for (unsigned int j = 1; j < 17; ++j) {
                ++row[data[j] & 15];
                ++row[data[j] >> 4];
            }
        }
        left -= n;
    }
    if (std::fgetc(stdin) != EOF || std::ferror(stdin)) {
        return 2;
    }

    std::cout << '[';
    bool first = true;
    for (unsigned int scale = 0; scale < counts.size(); ++scale) {
        const auto &row = counts[scale];
        if (row == std::array<std::uint32_t, 16>{}) {
            continue;
        }
        if (!first) {
            std::cout << ',';
        }
        first = false;
        std::cout << '[' << scale << ",[";
        for (unsigned int j = 0; j < row.size(); ++j) {
            if (j != 0) {
                std::cout << ',';
            }
            std::cout << row[j];
        }
        std::cout << "]]";
    }
    std::cout << "]\n";
    return std::cout ? 0 : 3;
}

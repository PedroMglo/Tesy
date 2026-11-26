// Verify the production guard using read-only file mappings. No GGML/CUDA linking or dlopen.
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

namespace fs = std::filesystem;
void need(bool value, const char *reason) {
    if (!value) throw std::runtime_error(reason);
}
#include "mapped.inc"

int main(int argc, char **argv) {
    try {
        need(argc == 2 && std::getenv("TESY_FIXTURE_MAP"), "passive probe arguments");
        std::ifstream table(std::getenv("TESY_FIXTURE_MAP"));
        unsigned ma, mi;
        unsigned long long ino;
        std::string path;
        const auto size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
        std::vector<void *> pages;
        while (table >> ma >> mi >> ino >> path) {
            const int fd = open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
            need(fd >= 0, "open ELF");
            auto *page = mmap(nullptr, size, PROT_READ, MAP_PRIVATE, fd, 0);
            close(fd);
            need(page != MAP_FAILED, "map ELF as data");
            pages.push_back(page);
        }
        need(!pages.empty() && table.eof(), "reference inventory");
        mapped(argv[1], "passive");
        for (auto *page : pages) need(munmap(page, size) == 0, "unmap");
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}

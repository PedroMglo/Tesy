#include <map>
#include <sstream>
#include <poll.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>

struct ElfIdentity {
    unsigned major_id, minor_id;
    unsigned long long inode;
};

// The launcher authenticates every target file by SHA-256 and stat before exec.
// Check the live ELF mappings against that table without reading any model files.
void mapped(const fs::path &dir, const std::string &phase) {
    const char *path = std::getenv("TESY_FIXTURE_MAP");
    need(path, "missing ELF table");
    std::map<std::string,ElfIdentity> allow, seen;
    std::ifstream table(path);
    std::string file;
    ElfIdentity id{};
    while (table >> id.major_id >> id.minor_id >> id.inode >> file) allow.emplace(file, id);
    need(table.eof() && !allow.empty(), "bad ELF table");
    std::ifstream maps("/proc/self/maps");
    std::string line;
    need(bool(maps), "process maps");
    while (std::getline(maps, line)) {
        const auto slash = line.find('/');
        if (slash == line.npos) continue;
        const auto name = line.substr(slash);
        if (fs::path(name).filename().string().find(".so") == std::string::npos) continue;
        std::istringstream fields(line.substr(0, slash));
        std::string range, permissions, offset, device;
        unsigned long long ino = 0;
        need(bool(fields >> range >> permissions >> offset >> device >> ino), "bad ELF VMA");
        unsigned ma = 0, mi = 0;
        need(std::sscanf(device.c_str(), "%x:%x", &ma, &mi) == 2, "VMA device");
        const auto it = allow.find(name);
        if (it == allow.end() || it->second.major_id != ma || it->second.minor_id != mi ||
            it->second.inode != ino) {
            std::ostringstream message;
            message << "unexpected ELF or VMA phase=" << phase << " path=" << name
                    << " actual=" << ma << ':' << mi << ':' << ino << " expected=";
            if (it == allow.end()) message << "absent";
            else message << it->second.major_id << ':' << it->second.minor_id << ':' << it->second.inode;
            throw std::runtime_error(message.str());
        }
        seen.emplace(name,it->second);
    }
    std::ofstream f(dir/(phase+".providers"));
    for (const auto &kv : seen) f << kv.first << '\n';
    f.flush();
    need(bool(f), "write provider witness");
    if (phase == "active" || phase == "finish") {
        const char *tx = std::getenv("TESY_TEST_TX"), *rx = std::getenv("TESY_TEST_RX");
        need(tx && rx, "monitor handoff");
        const char expected = phase == "active" ? 'A' : 'F';
        need(write(std::stoi(tx), &expected, 1) == 1, "notify monitor");
        pollfd ack{std::stoi(rx), POLLIN, 0};
        char value = 0;
        need(poll(&ack, 1, 3000) == 1 && (ack.revents & POLLIN) &&
             read(ack.fd, &value, 1) == 1 && value == expected, "monitor acknowledgement");
    }
}

#!/usr/bin/env python3
"""Exercise the pinned component reader on complete and interrupted synthetic inputs."""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

SOURCE_SHA = "9dea569987cae54cecaaf8ab6e3404fc22b8f2f2bfee8718329f7966e2094fa2"
INCLUDES = """
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <unistd.h>
#include <vector>
struct ggml_tensor;
"""
HARNESS = r"""
int main() {
    FILE *file = tmpfile();
    if (!file) return 2;
    int fd = fileno(file);
    std::array<uint8_t, 16> bytes{};
    for (int i = 0; i < 16; ++i) bytes[i] = uint8_t(i);
    if (write(fd, bytes.data(), bytes.size()) != 16) return 3;
    g_fds.push_back(fd);
    SlabInfo slab;
    slab.file_offset = 4; slab.expert_bytes = 4; slab.n_expert = 3;
    std::array<uint8_t, 4> buffer;
    ReadJob job{&slab, 2, 0, buffer.data(), false};
    for (bool interrupted : {false, true}) {
        if (interrupted && ftruncate(fd, 14) != 0) return 4;
        buffer.fill(255);
        do_read(job);
        for (auto byte : buffer) std::printf("%u ", unsigned(byte));
        std::puts("");
    }
    return fclose(file) == 0 ? 0 : 5;
}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    blob = (args.upstream / "src/llama-moestream.cpp").read_bytes()
    if hashlib.sha256(blob).hexdigest() != SOURCE_SHA:
        raise ValueError("source digest differs")
    cpp = blob.decode()
    structs = cpp[
        cpp.index("struct SlabInfo {") : cpp.index("static bool ", cpp.index("struct ReadJob {"))
    ]
    reader = cpp[cpp.index("static void do_read(") : cpp.index("// Simple parallel read")]
    program = INCLUDES + structs + "static std::vector<int> g_fds;\n" + reader + HARNESS
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        binary = root / "reader"
        src = root / "reader.cpp"
        src.write_text(program)
        subprocess.run(
            ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(binary)],
            check=True,
            timeout=25,
        )
        lines = subprocess.check_output([binary], text=True, timeout=5).splitlines()
    actual = [[int(n) for n in line.split()] for line in lines]
    if len(actual) != 2 or actual[0] != [12, 13, 14, 15]:
        raise ValueError("positive control or protocol failed")
    if actual[1] != [12, 13, 255, 255]:
        raise ValueError("short read did not reproduce the predicted partial fill")
    receipt = {
        "scope": "pinned component reader only",
        "source_sha256": SOURCE_SHA,
        "compiler": subprocess.check_output(["c++", "--version"], text=True).splitlines()[0],
        "fixture_sha256": hashlib.sha256(program.encode()).hexdigest(),
        "complete_bytes": actual[0],
        "eof_bytes": actual[1],
        "status": "NO_GO_SHORT_READ_NOT_PROPAGATED",
    }
    with args.output.open("x") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()

#pragma once
#include <cstdint>
namespace ob {
void worker(int ordinal);
void stage(int expert, uint64_t ticket);
void primary(int kind, int expert, int slot, uint64_t generation, int component);
void note(const char *kind, int expert=-1, int slot=-1, uint64_t generation=0,
          uint64_t ticket=0, int component=-1);
}

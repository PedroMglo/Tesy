// Shared only by the diagnostic's C++ translation units.
#pragma once
#include <cstddef>
#include <cstdint>
namespace observe {
extern int phase; // 0 inactive, 1 load, 2 context, 3 prefill, 4 supplied token, 5 teardown
extern thread_local unsigned long owner;
int64_t file_offset(const void *ptr, size_t n);
void transfer(const char *api, void *dst, const void *src, size_t n, int kind, int rc);
}

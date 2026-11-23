// No weights or graph: retain one real GGML mapping for the qualified monitor.
#include "ggml.h"
#include <cstdio>
#include <unistd.h>
int main() { std::printf("NO_MODEL_SMOKE %lld\n", (long long)ggml_time_us()); std::fflush(stdout); sleep(2); return 0; }

#include <nvtx3/nvToolsExt.h>
#include <time.h>

int main(void) {
    const struct timespec duration = {.tv_sec = 0, .tv_nsec = 100000000};
    nvtxRangePushA("C33_NVTX_SMOKE");
    nanosleep(&duration, 0);
    nvtxRangePop();
    return 0;
}

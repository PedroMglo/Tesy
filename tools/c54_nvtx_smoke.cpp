#include <nvtx3/nvToolsExt.h>

int main() {
    nvtxRangePushA("C46_SERVER_PREFILL_DECODE");
    nvtxMarkA("C46_WAVE_LAYER=0_WAVE=0_ACTIVE=1_OF=32");
    nvtxRangePop();
    return 0;
}

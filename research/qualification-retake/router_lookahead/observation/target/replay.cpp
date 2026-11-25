// Adapter for the archived-input calibration. All numerical work is from the live header.
#include "projector.h"
extern "C" int run_batch(int target,int rows,const float *x,const float *src,const float *dst,
                         const float *matrix,const float *bias,int *out) {
    using namespace target_probe;
    try {
        const bool half=reduced(target,rows);
        std::vector<float> w(matrix,matrix+width*experts);
        prepare_matrix(w,half);
        for (int i=0; i<rows; ++i) {
            const auto ids=project(x+i*width,src,dst,w.data(),bias,half);
            std::copy(ids.begin(),ids.end(),out+4*i);
        }
        return 0;
    } catch (...) { return -1; }
}

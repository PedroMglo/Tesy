#include "c269-last-use-order.h"
#include <cassert>
#include <iostream>
int main(){
    std::vector<int32_t> ids(4*153);
    for(int t=0;t<153;++t)for(int k=0;k<4;++k)ids[4*t+k]=(t<32?0:t<128?4:8)+k;
    // Experts0..3 recur in the last tile, so their single load moves later.
    ids[4*130]=0;ids[4*130+1]=1;ids[4*130+2]=2;ids[4*130+3]=3;
    const auto original=ids;std::vector<int32_t> order{0,1,2,3,4,5,6,7,8,9,10,11};
    assert(c269_last_use_order(order,ids.data(),ids.size(),128,4,32));
    assert((order==std::vector<int32_t>{4,5,6,7,8,9,10,11,0,1,2,3}));
    assert(ids==original);const auto expected=order;
    assert(c269_last_use_order(order,ids.data(),ids.size(),128,4,32)&&order==expected);
    auto bad=order;bad.pop_back();assert(!c269_last_use_order(bad,ids.data(),ids.size(),128,4,32));
    bad=order;bad.push_back(0);assert(!c269_last_use_order(bad,ids.data(),ids.size(),128,4,32));
    assert(!c269_last_use_order(order,ids.data(),ids.size()-1,128,4,32));
    assert(!c269_last_use_order(order,ids.data(),ids.size(),129,4,32));
    assert(!c269_last_use_order(order,ids.data(),ids.size(),128,4,64));
    ids[5]=128;assert(!c269_last_use_order(order,ids.data(),ids.size(),128,4,32));
    std::cout<<"PASS_MODEL_FREE_AUTHORITATIVE_LAST_USE_ORDER\n";
}

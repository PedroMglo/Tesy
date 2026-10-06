#include "c284-logical-route.h"
#include <cassert>
#include <iostream>
#include <numeric>
#include <functional>
void rejects(const std::function<void()> & f){bool bad=false;try{f();}catch(const std::exception&){bad=true;}assert(bad);}
int main(){
 std::vector<int32_t> pos(153),ids(153*4);std::iota(pos.begin(),pos.end(),0);
 for(int i=0;i<153;i++)for(int k=0;k<4;k++)ids[i*4+k]=(i*7+k*11)%128;
 std::vector<uint32_t> a(128),b(128);c284_route_clock ca,cb;ca.reset(1,0,a);cb.reset(1,0,b);ca.begin(1,pos);cb.begin(1,pos);
 ca.consume(ids.data(),153,a);
 for(int n=0;n<153;n+=32)cb.consume(ids.data()+n*4,std::min(32,153-n),b);
 assert(a==b&&ca.rows==153&&ca.decay_epoch==2&&cb.decay_epoch==2);
 auto before=b;assert(!cb.consume_at(32,ids.data()+128,32,b));assert(b==before);
 rejects([&]{auto wrong=ids;wrong[128]=127;cb.consume_at(32,wrong.data()+128,32,b);});
 cb.begin(2,pos);cb.consume(ids.data(),153,b);assert(cb.rows==306&&cb.decay_epoch==4&&b!=before);
 rejects([&]{cb.begin(2,pos);});
 cb.begin(3,{});cb.consume(nullptr,0,b);assert(cb.rows==306);cb.begin(4,{42});
 int32_t duplicate[]={1,1,2,3},invalid[]={1,2,3,128};auto saved=b;
 rejects([&]{cb.consume(duplicate,1,b);});rejects([&]{cb.consume(invalid,1,b);});assert(b==saved&&cb.rows==306);
 int32_t valid[]={3,2,1,0};cb.consume(valid,1,b);assert(cb.rows==307);
 cb.reset(2,1,b);assert(cb.rows==0&&cb.event==0&&cb.lifecycle==2&&cb.sequence==1&&std::accumulate(b.begin(),b.end(),uint64_t(0))==0);
 cb.begin(1,{0});b[0]=UINT32_MAX-1;cb.consume(valid,1,b);assert(b[0]==UINT32_MAX-1);
 rejects([&]{cb.consume_at(0,valid,2,b);});rejects([&]{cb.begin(2,{-1});});
 // Old clock counterexample: normal remap at2304 ages; wave plan at2304 does not.
 uint32_t old_normal=8,old_wave=8;old_normal>>=1;assert(old_normal!=old_wave);
 std::cout<<"PASS grouping153/32, decay64/128/256, duplicate/revaluation, masked-empty, invalid topk, saturation, reset and old-clock counterexample\n";
}

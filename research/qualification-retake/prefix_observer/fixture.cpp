#include "prefix_routes.h"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <vector>

static void check(bool ok) { if (!ok) throw std::runtime_error("fixture assertion"); }

static std::vector<int32_t> original(int layer, const std::vector<int32_t> &positions) {
    std::vector<int32_t> ids;
    for (int pos : positions) {
        for (int k : {11, 3, 17, 1}) ids.push_back((pos*4 + layer*5 + k) % 128);
    }
    return ids;
}

static void tile(prefix_routes *audit, int first, const std::vector<int8_t> &mask) {
    std::vector<int32_t> rows, outputs;
    for (size_t i=0; i<mask.size(); ++i) {
        rows.push_back(first+static_cast<int>(i));
        if (mask[i]) outputs.push_back(rows.back());
    }
    if (audit) check(audit->begin_ubatch(rows.size(),rows.data(),mask.data()));
    for (int layer=0; layer<36; ++layer) {
        const auto &pos = layer == 35 ? outputs : rows;
        if (pos.empty()) continue;
        auto ids = original(layer,pos);
        const auto untouched = ids;
        if (audit) check(audit->route(layer, pos.size()>10, pos.size(), 4, ids.data()));
        check(ids == untouched);
        // Exercise an independent, deterministic fixture consumer after the observer point.
        for (auto &id : ids) id = (id + 7) % 40;
        for (size_t i=0; i<ids.size(); ++i) check(ids[i] == (untouched[i]+7)%40);
    }
}

static void exercise(prefix_routes *audit) {
    if (audit) check(audit->begin_call(33));
    tile(audit,0,std::vector<int8_t>(32,0));
    tile(audit,32,{1});
    if (audit) { check(audit->cut('P')); check(audit->begin_call(3)); }
    tile(audit,33,{1,0,1});
    if (audit) { check(audit->cut('I')); check(audit->begin_call(1)); }
    tile(audit,36,{1});
    if (audit) check(audit->finish());
}

static void malformed() {
    int32_t pos[]={0}, good[]={3,2,1,0}, duplicate[]={3,2,3,0}, outside[]={3,2,1,128};
    int8_t mask[]={1};
    for (int problem=0; problem<7; ++problem) {
        prefix_routes a(problem==6 ? 20 : 512);
        check(a.begin_call(1));
        check(a.begin_ubatch(1,pos,mask));
        bool accepted=false;
        switch(problem) {
            case 0: accepted=a.route(0,false,1,4,duplicate); break;
            case 1: accepted=a.route(1,false,1,4,good); break;
            case 2: accepted=a.route(0,false,1,4,outside); break;
            case 3: accepted=a.route(0,false,1,3,good); break;
            case 4: accepted=a.cut('P'); break;
            case 5:
                for (int l=0;l<35;++l) check(a.route(l,false,1,4,good));
                accepted=a.cut('P'); break; // output mask requires the final layer
            case 6: accepted=a.route(0,false,1,4,good); break;
        }
        check(!accepted);
        bool refused=false;
        try { (void)a.data(); } catch (const std::logic_error &) { refused=true; }
        check(refused);
    }
    prefix_routes a;
    int32_t wrong[]={1};
    check(a.begin_call(1) && !a.begin_ubatch(1,wrong,mask));
}

int main(int argc,char **argv) {
    try {
        check(argc==2);
        exercise(nullptr);
        prefix_routes captured;
        exercise(&captured);
        malformed();
        const auto &bytes=captured.data();
        std::ofstream out(argv[1],std::ios::binary);
        out.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());out.close();
        check(bool(out));
        std::cout << "PASS fixture OFF/ON and eight fault checks\n";
        return 0;
    } catch (const std::exception &e) { std::cerr<<e.what()<<"\n";return 1; }
}

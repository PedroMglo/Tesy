// The Python supervisor authenticates the entire PFJ and its cut, plus the historical,
// pre-POST choice. Read exactly the sealed prefix; no new observation of the model.
struct PrefixRow {
    uint64_t ns, begin, gen;
    int64_t a,b,c;
    int32_t kind, call, tile, wave, layer, expert, slot, worker, component, fd, error, reserved;
};
static_assert(sizeof(PrefixRow) == 96 && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);

json selector_receipt(const retained::Selector &s) {
    return {{"offers",s.offers},{"ordered_keys",s.ordered()},{"held",s.held.size()},
            {"rejected",s.rejected},{"repeated",s.repeated},{"evictions",s.evictions},
            {"copies",{{"CPU",s.copies[0]},{"CUDA0",s.copies[1]}}}};
}
json replay(const char *file, uint64_t count) {
    std::ifstream f(file,std::ios::binary);
    f.seekg(64);
    retained::Selector lru(353,false), frequency(353,true);
    for(uint64_t j=0;j<count;++j) {
        PrefixRow r{};
        ensure(bool(f.read(reinterpret_cast<char *>(&r),sizeof(r))),"incomplete sealed prefix");
        if(r.kind==27 && r.call>=1 && r.call<=9) {
            int32_t rank[4];
            for(int i=0;i<4;++i) rank[i]=(uint64_t(r.a)>>(8*i))&255;
            frequency.ranks(r.layer,rank,4);
            lru.ranks(r.layer,rank,4);
        } else if(r.kind==11 && r.a>=0) {
            for(auto *s:{&lru,&frequency}) s->offer({r.layer,int(r.a)},[]{return retained::Lease{};});
        }
    }
    return {{"lru",selector_receipt(lru)},{"prefill",selector_receipt(frequency)},
            {"offered_keys",frequency.offered},{"prefix_records",count}};
}

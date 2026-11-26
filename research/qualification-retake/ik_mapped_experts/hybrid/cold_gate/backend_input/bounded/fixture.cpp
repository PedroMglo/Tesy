#include "bounded_input.hpp"
#include <array>
#include <cstdio>
#include <iostream>
#include <vector>

using Reader = tesy::BoundedBankInput;
using Source = tesy::Source;
static constexpr size_t page = tesy::BankInput::page;

static void require(bool condition, const char *reason) {
    if (!condition) throw std::runtime_error(reason);
}
template<class E, class F> static void rejects(F fn) {
    try { fn(); }
    catch (const E &) { return; }
    throw std::runtime_error("missing expected failure");
}
static unsigned char expected(size_t i) { return (53*i + i/13 + 19) % 251; }

struct Stream {
    struct Ticket { const unsigned char *src; size_t file, bytes; };
    std::vector<Ticket> pending;
    std::vector<std::pair<size_t,size_t>> completed;
    size_t attempts = 0;
    bool fail_next = false;

    void fence() {
        ++attempts;
        if (fail_next) {
            fail_next = false;
            throw std::runtime_error("injected fence failure");
        }
        for (auto t : pending) {
            for (size_t i=0; i<t.bytes; ++i)
                require(t.src[i] == expected(t.file+i), "source recycled before completion");
            completed.emplace_back(t.file,t.bytes);
        }
        pending.clear();
    }
};

static void send(Reader &reader, Stream &stream, const unsigned char *map, Source source,
                 size_t off, size_t bytes, bool fail_after_enqueue=false) {
    reader.send(off,map+off,bytes,[&](const void *p,size_t n) {
        require(n==bytes && uintptr_t(p)%page==off%page &&
                (p==map+off)==(source==Source::mapped), "effective origin or geometry");
        stream.pending.push_back({static_cast<const unsigned char *>(p),off,n});
        if (fail_after_enqueue) throw std::runtime_error("injected submission failure");
    });
}

static void normal(int fd, const unsigned char *map, Source source, size_t pages) {
    Stream stream, independent;
    const bool small = pages==2;
    {
        Reader r(fd,pages*page,source,[&]{stream.fence();});
        r.synchronize_ids();
        send(r,stream,map,source,page-1,2);
        if (small) {
            rejects<std::length_error>([&]{send(r,stream,map,source,page-1,page+2);});
            require(stream.attempts==1 && stream.pending.size()==1,"oversize consumed old work");
        }
        {
            Reader other(fd,page,source,[&]{independent.fence();});
            send(other,independent,map,source,19,51);
        }
        require(independent.completed.size()==1 && stream.completed.empty(), "wrong context fenced");
        send(r,stream,map,source,2*page+37,117);
        send(r,stream,map,source,3*page+8,3000);
        require(r.extra_drains()==size_t(small) && stream.completed.size()==size_t(small),
                "incorrect pressure drain");
        r.synchronize_ids();
        send(r,stream,map,source,4*page-1,2);
    }
    const std::vector<std::pair<size_t,size_t>> gold={
        {page-1,2},{2*page+37,117},{3*page+8,3000},{4*page-1,2}};
    require(stream.completed==gold && stream.pending.empty() &&
            stream.attempts==3+size_t(small),"order or cleanup");
    std::cout << (source==Source::mapped?"DIRECT":"PREAD_RANDOM") << ' ' << pages
              << ' ' << stream.attempts << " 4 3121\n";
}

static void faults(int fd, const unsigned char *map, Source src) {
    Stream failed;
    {
        Reader r(fd,page,src,[&]{failed.fence();});
        send(r,failed,map,src,81,64);
        failed.fail_next=true;
        rejects<std::runtime_error>([&]{send(r,failed,map,src,2*page,16);});
        require(failed.completed.empty() && failed.pending.size()==1 && r.extra_drains()==0,
                "unsuccessful fence released a source");
        rejects<std::logic_error>([&]{send(r,failed,map,src,16,3);});
    }
    Stream partial;
    {
        Reader r(fd,2*page,src,[&]{partial.fence();});
        send(r,partial,map,src,3,400);
        rejects<std::runtime_error>([&]{send(r,partial,map,src,page+7,100,true);});
        rejects<std::logic_error>([&]{send(r,partial,map,src,page+8,1);});
    }
    require(failed.attempts==2 && failed.completed.size()==1 &&
            partial.attempts==1 && partial.completed.size()==2,"pending fault cleanup");
}

int main() {
    FILE *f=std::tmpfile();
    if (!f) return 1;
    int fd=fileno(f);
    std::array<unsigned char,8*page> bytes{};
    for (size_t i=0;i<bytes.size();++i) bytes[i]=expected(i);
    if (pwrite(fd,bytes.data(),bytes.size(),0)!=ssize_t(bytes.size())) return 2;
    void *raw=mmap(nullptr,bytes.size(),PROT_READ,MAP_SHARED,fd,0);
    if (raw==MAP_FAILED) return 3;
    auto map=static_cast<const unsigned char *>(raw);
    try {
        for (auto src:{Source::mapped,Source::ranges}) {
            normal(fd,map,src,8);
            normal(fd,map,src,2);
            faults(fd,map,src);
        }
        Stream short_read;
        {
            Reader r(fd,2*page,Source::ranges,[&]{short_read.fence();});
            send(r,short_read,map,Source::ranges,80,17);
            require(ftruncate(fd,page+10)==0,"fixture truncation");
            rejects<std::runtime_error>([&]{send(r,short_read,map,Source::ranges,page,32);});
            rejects<std::logic_error>([&]{send(r,short_read,map,Source::ranges,80,17);});
        }
        require(short_read.attempts==1 && short_read.completed.size()==1,"short read lost pending SET");
        std::cout << "FAULTS 2_STREAMS PARTIAL_ENQUEUE FENCE_FAILURE SHORT_READ\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 4;
    }
    return munmap(raw,bytes.size()) || std::fclose(f);
}

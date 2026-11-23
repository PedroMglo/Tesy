#pragma once
// Canonical witness only: fail-closed positional O_DIRECT, no buffered fallback.
#include <sys/stat.h>
#include <sys/vfs.h>
#include <sys/ioctl.h>
#include <linux/btrfs.h>
#include <linux/magic.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>

namespace tesy_witness {
class direct_reader {
    int fd_=-1;
    uint64_t size_=0;
    size_t mem_align_=0, off_align_=0;
public:
    using read_fn=ssize_t(*)(int,void*,size_t,off_t);
    direct_reader()=default;
    direct_reader(const direct_reader&)=delete;
    direct_reader& operator=(const direct_reader&)=delete;
    ~direct_reader(){if(fd_>=0)::close(fd_);}
    void open_file(const char* path) {
        if(fd_>=0)throw std::runtime_error("reader already open");
        fd_=::open(path,O_RDONLY|O_CLOEXEC|O_DIRECT);
        if(fd_<0)throw std::runtime_error("canonical O_DIRECT open failed");
        struct stat st{};struct statx sx{};
        if(fstat(fd_,&st)||!S_ISREG(st.st_mode)||st.st_size<=0)
            throw std::runtime_error("canonical file invalid");
        size_=static_cast<uint64_t>(st.st_size);
        if(!statx(fd_,"",AT_EMPTY_PATH,STATX_DIOALIGN,&sx) &&
           (sx.stx_mask&STATX_DIOALIGN)&&sx.stx_dio_mem_align&&sx.stx_dio_offset_align) {
            mem_align_=sx.stx_dio_mem_align;off_align_=sx.stx_dio_offset_align;
        } else {
            // No generic guessed alignment: qualified Btrfs sectorsize from this inode's filesystem.
            struct statfs fs{};btrfs_ioctl_fs_info_args info{};
            if(fstatfs(fd_,&fs)||static_cast<unsigned long>(fs.f_type)!=BTRFS_SUPER_MAGIC||
               ioctl(fd_,BTRFS_IOC_FS_INFO,&info)||!info.sectorsize)
                throw std::runtime_error("DIO alignment unknown; no qualified filesystem fallback");
            mem_align_=off_align_=info.sectorsize;
        }
        if((mem_align_&(mem_align_-1))||mem_align_<sizeof(void*) || mem_align_>1024*1024 || off_align_>1024*1024 ||
           !(fcntl(fd_,F_GETFL)&O_DIRECT))throw std::runtime_error("DIO requirements invalid");
    }
    uint64_t file_size()const{return size_;}
    size_t memory_alignment()const{return mem_align_;}
    size_t offset_alignment()const{return off_align_;}
    int descriptor()const{return fd_;}
    void validate_range(uint64_t offset,uint64_t length)const {
        if(!length||offset>size_||length>size_-offset||
           offset>static_cast<uint64_t>(std::numeric_limits<off_t>::max()) ||
           length>static_cast<uint64_t>(std::numeric_limits<off_t>::max())-offset)
            throw std::runtime_error("canonical logical range/overflow");
    }
    void read(void* dst,size_t length,uint64_t offset,read_fn fn=::pread)const {
        validate_range(offset,length);
        if(!dst||fd_<0||!off_align_)throw std::runtime_error("reader not ready");
        const uint64_t begin=offset-offset%off_align_, end=offset+length;
        if(end>std::numeric_limits<uint64_t>::max()-(off_align_-1))throw std::runtime_error("DIO rounding overflow");
        const uint64_t rounded=(end+off_align_-1)/off_align_*off_align_, amount=rounded-begin;
        if(amount>8*1024*1024 || amount+2*length>16*1024*1024 || rounded>static_cast<uint64_t>(std::numeric_limits<off_t>::max()))
            throw std::runtime_error("DIO scratch/off_t bound");
        void* raw=nullptr;
        if(posix_memalign(&raw,mem_align_,static_cast<size_t>(amount)))throw std::runtime_error("DIO aligned allocation failed");
        struct free_guard{void* p;~free_guard(){std::free(p);}}guard{raw};
        ssize_t n;
        do {n=fn(fd_,raw,static_cast<size_t>(amount),static_cast<off_t>(begin));}while(n<0&&errno==EINTR);
        // One bounded aligned call. A short physical window is legal only if it covers all logical bytes.
        if(n<0||static_cast<uint64_t>(n)<end-begin)throw std::runtime_error("DIO error/short canonical interval; no fallback");
        std::memcpy(dst,static_cast<uint8_t*>(raw)+(offset-begin),length);
    }
};
}

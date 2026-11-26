#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <pthread.h>
#include <semaphore.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <unistd.h>

enum { PAGE=4096, WINDOW=13221888, SLAB=4406400, A=19, B=173, C=231 };
static size_t bytes_read;
static int preads;
static void need(int ok, const char *msg) {
    if (!ok) { fprintf(stderr,"FAIL %s (errno %d)\n",msg,errno); exit(2); }
}
static void *map_at(void *where,size_t len,int prot,int flags,int fd,off_t offset) {
    void *mapped=mmap(where,len,prot,flags,fd,offset);
    need(mapped!=MAP_FAILED && (!where || where==mapped),"mmap range");
    return mapped;
}
static ssize_t get(int fd,void *ptr,off_t offset,size_t n) {
    ssize_t got=pread(fd,ptr,WINDOW,offset);
    need(got==(ssize_t)n,"unaligned or short/long direct read");
    ++preads; bytes_read+=got; return got;
}
static int publish(int requested_gen,int current_gen,ssize_t returned) {
    return requested_gen==current_gen && returned==WINDOW;
}
static uint8_t pattern(size_t i,unsigned char seed) {
    unsigned at=i%PAGE;
    return (uint8_t)(37U*at+(at>>5)+seed);
}
static int range_ok(const uint8_t *p,size_t begin,size_t count,int seed) {
    for(size_t i=begin;i<begin+count;i++) if(p[i]!=pattern(i,seed)) return 0;
    return 1;
}
static int window_ok(const uint8_t *p,int seed) {
    // Three complete native components, followed by the record's alignment padding.
    for(unsigned k=0;k<3;k++) if(!range_ok(p,k*SLAB,SLAB,seed)) return 0;
    return range_ok(p,3*SLAB,WINDOW-3*SLAB,seed);
}
static long allocated(int fd) {
    struct stat st;
    need(fstat(fd,&st)==0,"memfd stat");
    return (long)st.st_blocks*512L;
}
struct reader {
    const uint8_t *ptr;
    sem_t acquired,release;
    int old_good;
};
static void *read_old(void *arg) {
    struct reader *r=arg;
    const uint8_t *p=r->ptr; // retain this VA before the writer is allowed to proceed.
    need(sem_post(&r->acquired)==0 && sem_wait(&r->release)==0,"reader gates");
    r->old_good=window_ok(p,A);
    return NULL;
}
static void retire(struct reader *r,pthread_t t) {
    need(sem_post(&r->release)==0 && pthread_join(t,NULL)==0,"join old reader");
}
int main(int argc,char **argv) {
    need(argc==3 && sysconf(_SC_PAGESIZE)==PAGE,"usage: fixture source safe|early|reuse");
    const int early=!strcmp(argv[2],"early"),reuse=!strcmp(argv[2],"reuse");
    need(early||reuse||!strcmp(argv[2],"safe"),"unknown arm");
    const int input=open(argv[1],O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_DIRECT);
    struct stat statfd,path;
    struct statfs fs;
    need(input>=0 && fstat(input,&statfd)==0 && stat(argv[1],&path)==0 &&
         S_ISREG(statfd.st_mode) && statfd.st_dev==path.st_dev && statfd.st_ino==path.st_ino &&
         statfd.st_size==2*WINDOW+PAGE && (fcntl(input,F_GETFL)&O_DIRECT) &&
         fstatfs(input,&fs)==0 && fs.f_type==BTRFS_SUPER_MAGIC,"NVMe fixture source");
    const int backing=memfd_create("tesy-expert-pages",MFD_CLOEXEC);
    need(backing>=0 && !ftruncate(backing,3L*WINDOW),"create private backing");
    const size_t reserve=40UL*WINDOW+3UL*PAGE;
    uint8_t *arena=map_at(NULL,reserve,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    uint8_t *slot=arena+PAGE+39UL*WINDOW;
    uint8_t *left=map_at(slot-PAGE,PAGE,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);
    uint8_t *tail=map_at(slot+WINDOW,PAGE,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);
    memset(left,0xa5,PAGE); memset(tail,0x5a,PAGE);
    map_at(slot,WINDOW,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,backing,0);
    need(publish(1,1,get(input,slot,0,WINDOW)) && window_ok(slot,A),"first expert delivery");
    long before=allocated(backing);
    const uint8_t *bank=map_at(NULL,WINDOW,PROT_READ,MAP_SHARED,backing,0);
    need(window_ok(bank,A),"retained victim payload");
    long after=allocated(backing);
    need(before>=WINDOW && before==after,"resident bank alias pages duplicated");
    uint8_t *incomplete=map_at(NULL,WINDOW,PROT_READ|PROT_WRITE,MAP_SHARED,backing,2L*WINDOW);
    const int short_ready=publish(2,2,get(input,incomplete,2L*WINDOW,PAGE));
    // The completion cannot publish. Short-read tail is unspecified even if initialized.
    need(!short_ready && range_ok(incomplete,0,PAGE,C) && window_ok(bank,A) && window_ok(slot,A),"short completion isolation");
    need(munmap(incomplete,WINDOW)==0,"scratch cleanup");
    struct reader rd={.ptr=slot};
    pthread_t thread;
    need(!sem_init(&rd.acquired,0,0) && !sem_init(&rd.release,0,0) &&
         !pthread_create(&thread,NULL,read_old,&rd) && !sem_wait(&rd.acquired),"acquire old VA");
    if(!early) retire(&rd,thread);
    map_at(slot,WINDOW,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,backing,reuse?0:WINDOW);
    need(publish(3,3,get(input,slot,WINDOW,WINDOW)) && window_ok(slot,B),"new expert delivery");
    if(early) retire(&rd,thread);
    const int retained=window_ok(bank,A);
    map_at(slot,WINDOW,PROT_READ,MAP_SHARED|MAP_FIXED,backing,0);
    const int recovered=window_ok(slot,A);
    need(rd.old_good==!early && retained==!reuse && recovered==!reuse,"negative control did not discriminate");
    for(size_t n=0;n<PAGE;++n) need(left[n]==0xa5 && tail[n]==0x5a,"adjacent page modified");
    const long final=allocated(backing);
    struct rusage used;
    need(!getrusage(RUSAGE_SELF,&used) && !sem_destroy(&rd.acquired) && !sem_destroy(&rd.release) &&
         !munmap((void *)bank,WINDOW) && !munmap(arena,reserve) && !close(backing) && !close(input),
         "resources/cleanup");
    printf("{\"status\":\"PASS\",\"arm\":\"%s\",\"reader_old\":%d,\"bank_old\":%d,\"restored_old\":%d,"
           "\"short_published\":false,\"new_primary_correct\":true,\"preads\":%d,\"returned_bytes\":%zu,\"short_returned_bytes\":%d,"
           "\"arena_virtual_bytes\":%zu,\"backing_before_alias\":%ld,\"backing_after_alias\":%ld,"
           "\"backing_after_replacement\":%ld,\"maxrss_kib\":%ld,\"source_dev\":%ju,\"source_ino\":%ju}\n",
           argv[2],rd.old_good,retained,recovered,preads,bytes_read,PAGE,reserve,before,after,final,
           used.ru_maxrss,(uintmax_t)statfd.st_dev,(uintmax_t)statfd.st_ino);
    return 0;
}

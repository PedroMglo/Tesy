#define _GNU_SOURCE
#include "ggml.h"

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static int trace_fd = -1;
static _Atomic int phase_id = 0;
static _Atomic size_t logged_bytes = 0;
static _Atomic bool overflow = false;
static const size_t trace_cap = 64u*1024u*1024u;

static uint64_t now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC,&t);
    return (uint64_t)t.tv_sec*1000000000ull+(uint64_t)t.tv_nsec;
}

static void log_line(const char * line,size_t size) {
    if (trace_fd<0 || atomic_load(&overflow)) return;
    const size_t prior=atomic_fetch_add(&logged_bytes,size);
    if (prior>trace_cap || size>trace_cap-prior) {
        atomic_store(&overflow,true);
        return;
    }
    if (write(trace_fd,line,size)!=(ssize_t)size) atomic_store(&overflow,true);
}

__attribute__((constructor)) static void trace_init(void) {
    const char * path=getenv("TESY_C3_TRACE_FILE");
    if (!path) return;
    trace_fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_APPEND|O_CLOEXEC,0600);
    if (trace_fd<0) {
        const char * error="C3_TRACE_OPEN_FAIL\n";
        write(STDERR_FILENO,error,strlen(error));
        atomic_store(&overflow,true);
        return;
    }
    const char * header="kind\tphase\tlayer_or_offset\trequested\treturned\tstart_ns\tduration_ns\tname\n";
    log_line(header,strlen(header));
}

__attribute__((destructor)) static void trace_close(void) {
    if (trace_fd>=0) close(trace_fd);
}

void tesy_c3_trace_phase(int phase) {
    atomic_store(&phase_id,phase);
    if (trace_fd<0) return;
    char line[128];
    const int n=snprintf(line,sizeof(line),"M\t%d\t0\t0\t0\t%llu\t0\tphase\n",
                         phase,(unsigned long long)now_ns());
    if (n>0 && (size_t)n<sizeof(line)) log_line(line,(size_t)n);
}

int tesy_c3_trace_overflow(void) {
    return atomic_load(&overflow) || trace_fd<0;
}

static ssize_t traced_pread(int fd,void * buffer,size_t count,off_t offset) {
    const int phase=atomic_load(&phase_id);
    const int flags=phase>0 ? fcntl(fd,F_GETFL) : -1;
    const bool record=phase>0 && flags>=0 && (flags&O_DIRECT) && count>=4096;
    const uint64_t start=record ? now_ns() : 0;
    const ssize_t result=syscall(SYS_pread64,fd,buffer,count,offset);
    if (record) {
        const int saved_errno=errno;
        char line[192];
        const int n=snprintf(line,sizeof(line),"R\t%d\t%lld\t%zu\t%zd\t%llu\t%llu\tfd%d\n",
                             phase,(long long)offset,count,result,
                             (unsigned long long)start,
                             (unsigned long long)(now_ns()-start),fd);
        if (n>0 && (size_t)n<sizeof(line)) log_line(line,(size_t)n);
        errno=saved_errno;
    }
    return result;
}

ssize_t pread(int fd,void * buffer,size_t count,off_t offset) {
    return traced_pread(fd,buffer,count,offset);
}

ssize_t pread64(int fd,void * buffer,size_t count,off64_t offset) {
    return traced_pread(fd,buffer,count,(off_t)offset);
}

void ggml_backend_tensor_set(struct ggml_tensor * tensor,const void * data,
                             size_t offset,size_t size) {
    typedef void (*original_fn)(struct ggml_tensor *,const void *,size_t,size_t);
    static original_fn original=NULL;
    if (!original) original=(original_fn)dlsym(RTLD_NEXT,"ggml_backend_tensor_set");
    if (!original) abort();
    const int phase=atomic_load(&phase_id);
    const bool record=phase>0 && tensor && strstr(tensor->name,".stream_cache")!=NULL;
    const uint64_t start=record ? now_ns() : 0;
    original(tensor,data,offset,size);
    if (record) {
        char line[256];
        const int n=snprintf(line,sizeof(line),"U\t%d\t%zu\t%zu\t%zu\t%llu\t%llu\t%s\n",
                             phase,offset,size,size,(unsigned long long)start,
                             (unsigned long long)(now_ns()-start),tensor->name);
        if (n>0 && (size_t)n<sizeof(line)) log_line(line,(size_t)n);
    }
}

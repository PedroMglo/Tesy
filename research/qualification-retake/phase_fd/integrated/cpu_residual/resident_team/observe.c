/* Observer for the specific, separately authenticated C269 CPU ELF on Linux x86_64.
 * Link this object into the client and export only ggml_barrier and
 * ggml_cpu_extra_compute_forward. No ELF or text mapping is modified.
 */
#define _GNU_SOURCE
#include "ggml.h"
#include <dlfcn.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

enum { WAVES = 8, ROLES = 3, LANES = 8, NODES = WAVES*ROLES, ROWS = NODES*LANES };
enum {
    EXTRA_RETURN = 0x68ed, BETWEEN_RETURN = 0x6931, LAST_RETURN = 0x6890,
    INNER_A_RETURN = 0x7676, INNER_B_RETURN = 0x7f2f, INNER_C_RETURN = 0x7f4f
};

struct ggml_compute_params;
struct ggml_threadpool;
static bool (*next_extra)(struct ggml_compute_params *, struct ggml_tensor *);
static void (*next_barrier)(struct ggml_threadpool *);
static uintptr_t image_base;
static int image_ok;
static pthread_once_t once = PTHREAD_ONCE_INIT;
static atomic_bool resolved;
static atomic_int active, fault;
static int pending_read, last_count;
static const struct ggml_tensor *nodes[NODES];

struct mark {
    int stage, tid, cpu_enter, cpu_leave, internal;
    int64_t begin, end;
};
static struct mark marks[ROWS];
static _Thread_local struct mark *current;

/* Compiler-generated x86_64 rel32 at a fixed, authenticated address. */
static int call_to(uintptr_t ret, uintptr_t target) {
    const unsigned char *ra = (const unsigned char *)(image_base + ret);
    int32_t displacement;
    memcpy(&displacement, ra - 4, sizeof(displacement));
    return ra[-5] == 0xe8 && (int64_t)ret + displacement == (int64_t)target;
}
static void bind_cpu(void) {
    Dl_info a, b;
    next_extra = dlsym(RTLD_NEXT, "ggml_cpu_extra_compute_forward");
    next_barrier = dlsym(RTLD_NEXT, "ggml_barrier");
    if (!next_extra || !next_barrier) {
        fputs("C269 original CPU hooks unresolved\n", stderr);
        abort();
    }
    if (dladdr((void *) next_extra, &a) && dladdr((void *) next_barrier, &b) &&
        a.dli_fbase == b.dli_fbase) {
        image_base = (uintptr_t)a.dli_fbase;
        if ((uintptr_t)next_extra == image_base + 0x445c0 &&
            (uintptr_t)next_barrier == image_base + 0x2970)
            image_ok = call_to(EXTRA_RETURN, 0x6b0) && call_to(BETWEEN_RETURN, 0x300) &&
                       call_to(LAST_RETURN, 0x300) && call_to(INNER_A_RETURN, 0x300) &&
                       call_to(INNER_B_RETURN, 0x300) && call_to(INNER_C_RETURN, 0x300);
    }
    atomic_store_explicit(&resolved, true, memory_order_release);
}
static inline void ensure_bound(void) {
    if (!atomic_load_explicit(&resolved, memory_order_acquire)) pthread_once(&once, bind_cpu);
}
static int64_t mono(void) {
    struct timespec n;
    if (clock_gettime(CLOCK_MONOTONIC, &n)) return -1;
    return (int64_t)n.tv_sec * INT64_C(1000000000) + n.tv_nsec;
}
static void reject(void) {atomic_store_explicit(&fault, 1, memory_order_relaxed);}

/* Configure from a single controller while graph execution is stopped.
 * Matrix roles are gate=0, down=1, up=2. A graph is registered once per process.
 */
int team_observe_init(void) {
    ensure_bound();
    return image_ok ? 0 : -1;
}
int team_observe_add(const struct ggml_tensor *t, int wave, int role) {
    if (atomic_load(&active) || !t || t->op != GGML_OP_MUL_MAT_ID ||
        wave < 0 || wave >= WAVES || role < 0 || role >= ROLES || nodes[wave*ROLES+role])
        return -1;
    for (int i=0;i<NODES;i++) if (nodes[i] == t) return -1;
    nodes[wave*ROLES+role] = t;
    return 0;
}
void team_observe_begin(int mode) {
    if (pending_read || atomic_load(&active)) {reject();return;}
    pending_read=1; last_count=-1; atomic_store(&fault, 0);
    if (mode != 0 && mode != 1) {reject();return;}
    if (!mode) return;
    if (!image_ok) {reject();return;}
    for(int i=0;i<NODES;i++) if (!nodes[i]) {reject();return;}
    memset(marks, 0, sizeof(marks));
    atomic_store_explicit(&active, 1, memory_order_release);
}
static void enter_node(const struct ggml_tensor *t, const int lane[2], uintptr_t pc, bool handled) {
    int i;
    for (i=0;i<NODES && nodes[i]!=t;i++) {}
    if (current || pc!=EXTRA_RETURN || handled || i==NODES ||
        lane[0]<0 || lane[0]>=LANES || lane[1]!=LANES) {reject();return;}
    struct mark *m=&marks[i*LANES+lane[0]];
    /* GGML assigns one ith per worker. Exchange also makes duplicate concurrent
     * assignments reject safely even if the upstream invariant breaks. */
    if (__atomic_exchange_n(&m->stage, 1, __ATOMIC_ACQ_REL) != 0) {reject();return;}
    m->tid=(int)syscall(SYS_gettid); m->cpu_enter=sched_getcpu(); m->begin=mono();
    if (m->tid<=0 || m->cpu_enter<0 || m->begin<0) reject();
    current=m;
}
static void barrier_edge(uintptr_t pc) {
    struct mark *m=current;
    if (!m) return;
    if (pc==INNER_A_RETURN || pc==INNER_B_RETURN || pc==INNER_C_RETURN) {
        if (++m->internal != 1) reject();
        return;
    }
    if (pc!=BETWEEN_RETURN && pc!=LAST_RETURN) {reject();return;}
    m->end=mono(); m->cpu_leave=sched_getcpu();
    if (m->internal!=1 || m->end<=m->begin || m->cpu_leave<0) reject();
    __atomic_store_n(&m->stage, 2, __ATOMIC_RELEASE);
    current=NULL;
}

/* Original op switch follows the false return from the extra-buffer dispatcher.
 * End is arrival at the original next graph barrier (before waiting); the op's
 * internal synchronization, dispatcher and short loop epilogue are included. */
__attribute__((noinline,visibility("default")))
bool ggml_cpu_extra_compute_forward(struct ggml_compute_params *params, struct ggml_tensor *t) {
    ensure_bound();
    bool handled=next_extra(params,t);
    if (atomic_load_explicit(&active,memory_order_acquire)) {
        if (current) reject();
        if (t->op==GGML_OP_MUL_MAT_ID) {
            int lane[2];
            /* C269 ggml-cpu-impl.h starts ggml_compute_params with int ith, nth. */
            memcpy(lane,params,sizeof(lane));
            enter_node(t,lane,(uintptr_t)__builtin_return_address(0)-image_base,handled);
        }
    }
    return handled;
}
__attribute__((noinline,visibility("default")))
void ggml_barrier(struct ggml_threadpool *tp) {
    ensure_bound();
    if (atomic_load_explicit(&active,memory_order_acquire) && current)
        barrier_edge((uintptr_t)__builtin_return_address(0)-image_base);
    next_barrier(tp);
}

/* Called only after the normal scheduler synchronize/join. */
int team_observe_end(void) {
    const int was_on=atomic_exchange_explicit(&active,0,memory_order_acq_rel);
    if (!pending_read || atomic_load(&fault)) {pending_read=0;last_count=-1;return -1;}
    pending_read=0;
    if (!was_on) return last_count=0;
    for(int i=0;i<ROWS;i++)
        if (__atomic_load_n(&marks[i].stage,__ATOMIC_ACQUIRE)!=2) return last_count=-1;
    return last_count=ROWS;
}
int team_observe_row(int i,int *wave,int *role,int *ith,int *nth,int *tid,int *cpu_enter,
                     int *cpu_leave,int64_t *start_ns,int64_t *end_ns) {
    if (i<0 || i>=last_count || pending_read || atomic_load(&active)) return -1;
    const struct mark *m=&marks[i];
    *wave=i/(LANES*ROLES); *role=i/LANES%ROLES; *ith=i%LANES; *nth=LANES;
    *tid=m->tid; *cpu_enter=m->cpu_enter; *cpu_leave=m->cpu_leave;
    *start_ns=m->begin; *end_ns=m->end;
    return 0;
}

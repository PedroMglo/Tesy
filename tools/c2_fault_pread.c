#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

// Test-only interposer. It never writes to the model or changes the backend.
// Exactly one sufficiently large O_DIRECT expert read is affected per process.
static int injected = 0;

static ssize_t fault_or_read(int fd, void * buf, size_t len, off_t offs) {
    const int flags = fcntl(fd, F_GETFL);
    const char * mode = getenv("TESY_C2_PREAD_FAULT");
    if (mode && flags >= 0 && (flags & O_DIRECT) && offs > 4096 && len > 8192 &&
        __atomic_exchange_n(&injected, 1, __ATOMIC_SEQ_CST) == 0) {
        const char * marker = "TESY_C2_FAULT_INJECTED\n";
        (void) write(STDERR_FILENO, marker, strlen(marker));
        if (strcmp(mode, "eio") == 0) {
            errno = EIO;
            return -1;
        }
        if (strcmp(mode, "eof") == 0) {
            return 0;
        }
        if (strcmp(mode, "short") == 0) {
            // 4096 is O_DIRECT-aligned and below the encoded expert slice.
            return syscall(SYS_pread64, fd, buf, (size_t)4096, offs);
        }
        if (strcmp(mode, "delay") == 0) {
            struct timespec pause = {.tv_sec = 0, .tv_nsec = 200000000};
            while (nanosleep(&pause, &pause) < 0 && errno == EINTR) {}
        } else {
            errno = EINVAL;
            return -1;
        }
    }
    return syscall(SYS_pread64, fd, buf, len, offs);
}

ssize_t pread(int fd, void * buf, size_t len, off_t offs) {
    return fault_or_read(fd, buf, len, offs);
}

ssize_t pread64(int fd, void * buf, size_t len, off64_t offs) {
    return fault_or_read(fd, buf, len, (off_t) offs);
}

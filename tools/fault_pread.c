#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/syscall.h>
#include <unistd.h>

// Test-only fault injector. It changes one O_DIRECT read into EIO inside the
// spawned process; it never writes to the file or changes the backend binary.
static int injected = 0;

static ssize_t fault_or_read(int fd, void * buf, size_t len, off_t offs) {
    const int flags = fcntl(fd, F_GETFL);
    if ((flags & O_DIRECT) && offs > 4096 &&
        __atomic_exchange_n(&injected, 1, __ATOMIC_SEQ_CST) == 0) {
        static const char marker[] = "TESY_FAULT_PREAD_DIRECT_EIO\n";
        (void) write(STDERR_FILENO, marker, sizeof(marker) - 1);
        errno = EIO;
        return -1;
    }
    return syscall(SYS_pread64, fd, buf, len, offs);
}

ssize_t pread(int fd, void * buf, size_t len, off_t offs) {
    return fault_or_read(fd, buf, len, offs);
}

ssize_t pread64(int fd, void * buf, size_t len, off64_t offs) {
    return fault_or_read(fd, buf, len, (off_t) offs);
}

#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char ** argv) {
    if (argc != 2) return 2;
    int fd = open(argv[1], O_RDONLY | O_DIRECT);
    if (fd < 0) return 3;
    void * buffer = NULL;
    if (posix_memalign(&buffer, 4096, 16384)) return 4;
    struct timespec a, b;
    clock_gettime(CLOCK_MONOTONIC, &a);
    ssize_t n = pread(fd, buffer, 16384, 8192);
    const int saved_errno = errno;
    clock_gettime(CLOCK_MONOTONIC, &b);
    const long elapsed_ms = (b.tv_sec-a.tv_sec)*1000 + (b.tv_nsec-a.tv_nsec)/1000000;
    printf("read=%zd errno=%d elapsed_ms=%ld\n", n, n < 0 ? saved_errno : 0, elapsed_ms);
    free(buffer);
    close(fd);
    return 0;
}

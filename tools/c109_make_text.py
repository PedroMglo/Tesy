#!/usr/bin/env python3
"""Synthetic, deterministic technical conversation for the decode discriminator."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    args.root.mkdir(exist_ok=False)
    rows = []
    for i in range(48):
        tenant = ['alpha', 'beta', 'gamma', 'delta'][i % 4]
        status = ['ok', 'retry', 'timeout', 'ok'][i % 4]
        rows.append(f'event {i:03d}: tenant={tenant}, batch={1000+i}, rows={800+i*3}, '
                    f'duration_ms={35+(i%11)*17}, status={status}, '
                    f'index=events_tenant_created_at, wal_pages={2+i%7}.')
    system = ('You are a technical assistant. Current date: 2026-09-29. '
              'Reasoning effort: medium. Preserve the evidence and distinguish a measurement from a hypothesis.')
    user = ('A SQLite ingestion service batches events by tenant. It has one writer, four readers, '
            'WAL mode, and a composite index on (tenant, created_at). Here is a synthetic trace. '
            'Explain why p95 write latency can rise when a reader holds an old snapshot, identify '
            'which observations support that explanation, and propose a bounded diagnostic and '
            'a safe mitigation. Do not claim that these rows alone prove a cause.\n\n' +
            '\n'.join(rows) + '\n\nReturn a concise technical answer with separate evidence and next tests.')
    answer = ('The trace shows occasional retries and timeouts while batch size and the chosen index '
              'remain fairly stable. That pattern is compatible with WAL checkpoint pressure, but it '
              'does not establish it. A reader holding an old snapshot can prevent a checkpoint from '
              'reclaiming WAL pages; the writer may then pay for larger WAL management and storage '
              'activity. The rows do not include snapshot age, checkpoint outcomes, fsync duration, '
              'or device queue latency, so lock contention and external I/O remain alternatives. '
              'First record WAL size, checkpoint busy counts, reader transaction ages, writer lock '
              'waits, fsync latency, and block-device activity on the same monotonic clock. Keep the '
              'batch and query mix fixed for a short control interval, then cap reader transaction '
              'lifetime and compare a second interval. Report every timeout and the entire latency '
              'distribution, not only the median. A safe operational mitigation is to close read '
              'transactions promptly, paginate long scans, and schedule checkpoints when readers are '
              'quiescent. If p95 improves but WAL size and checkpoint stalls do not, revisit the '
              'hypothesis; CPU scheduling, contention in application locks, or a noisy storage neighbor '
              'could still explain the change. Do not increase the busy timeout just to make the '
              'measurement look clean. Confirm correctness with concurrent readers before promoting '
              'the change. The causal question is whether the same workload, with reader lifetime '
              'controlled, reduces the time spent waiting for checkpoints and writing WAL pages.')
    for name, text in [('system.txt', system), ('user.txt', user), ('answer.txt', answer)]:
        with (args.root / name).open('x') as stream:
            stream.write(text + '\n')
    print(f'rows={len(rows)} user_characters={len(user)} answer_characters={len(answer)}')


if __name__ == '__main__':
    main()

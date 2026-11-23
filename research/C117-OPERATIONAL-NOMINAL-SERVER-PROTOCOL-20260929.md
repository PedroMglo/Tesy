# C117 — operational warm-start nominal session screen

Objective: obtain contemporary C35/C75 ON pairs for actual assistant-history reuse with an effective ~153-ID increment, after C113 and C114 could not complete the frozen 3/3/2 °C cold-matched starts. The alternative is that C111's teacher-forced gain does not transfer to free server final-content latency or that C100's decode regression persists.

This is a new **operational warm-start** regime, not a repair of C113/C114. No forced cooling or thermal matching is used. Before each arm the mature server preflight collects 60 s of valid host telemetry, verifies AC/profile and all resource guards, and records CPU/GPU/NVMe starts. Fresh processes alternate C35→C75 ON; C75 ON→C35. Start differences and order remain visible; two pairs provide a screening signal only. Existing C113/C114 incomplete decisions and C100 NO_GO are unchanged.

Primary: second-request first final content. Frozen screen gate: median paired gain ≥5%, both gains positive, median warm and cold decode regressions no worse than5%, full answers/prefix/telemetry/identity. Gain is `100*(control−candidate)/control` per pair. Workload/config are copied byte-for-byte from C114: two synthetic turns, 127 nominal beta words, medium 8K P12, exact assistant history, no idle, max output256. The official tokenization and actual increment must be reported. Completion is natural stop, not ignore-EOS.

E18 cap and workload swap0 remain frozen. At freeze the conservative epoch ledger admits 3240 s for four ≤600 s arms, four 60 s preflights and600 s closure; wall remainder3614.64 s. Admission is rechecked before each remaining arm. Any numerical/resource/evidence failure closes the family. No service/default change and no remote publication.

Base source/tree are those in the committed protocol. Model-free: five relevant repo tests passed, fresh 60 s C55 inventory admitted E18, and a small real user scope showed MemoryMax19327352832 and MemorySwapMax0. No 120B execution had occurred at freeze. These tests do not certify performance or the new operational comparison.

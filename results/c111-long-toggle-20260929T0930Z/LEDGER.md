# C111 ledger

- New flag-only C75 OFF/ON contrast after C110 cold matching expired. Order B→C; C→B. Same frozen long IDs and original C75 libraries. Operational starts matched within each pair.
- 22 model-free tests passed; fresh 60 s inventory and E18 policy frozen; 4,680 s worst case admitted within the existing epoch.
- Physical: all three canaries and four long arms PASS; every long arm's 193 full-logit rows bitwise match C110 B. Pair1 B→C: prefill gain +33.65%, full decode −6.83%, late decode −4.57%. Pair2 C→B: prefill gain +37.67%, full decode +1.04%, late decode +4.33%. Medians +35.66%, −2.89%, −0.12%. Resource guards, swap and OOM passed. This is `NO_PERSISTENT_LATE_DECODE_FLAG_PENALTY_IN_PROBE`, not server promotion; initial decode regressed in both pairs. Raw hashes in `manifest.json`. No remote publication or default change.

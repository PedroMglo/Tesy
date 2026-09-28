# C64 P14 canonical witness checkpoint

- Objective/base: the first six P14 resident FFN layers under frozen C64 measurement commit `0c28ec73f3f9787d87298feb4d54a0b0648ee0b4`, before the other 30 loads.
- Evidence class: `MEDIDO_NO_TARGET`, six distinct bounded processes, one canonical layer each, on the device observed by the P14 loader.
- Result: layers 23, 24, 22, 25, 0 and 35 all passed ordered router IDs, bitwise routing weights and bitwise FFN outputs. Coverage is 40 numerical rows and 2 explicit `N/A_MASKED` rows. No resource stop, swap or OOM.
- Alternative/decision: a P14 placement boundary defect was not observed in these witnesses. This does not imply that the other 30 layers pass, nor does it validate attention/KV or timing. Continue exactly the frozen remaining-layer list under a clean measurement commit; any first failure ends that phase.
- Tests/NOT_RUN: validator's historical positive/mutant control passed, and the 126-test model-free suite passed before physical execution. Remaining 30 layers, paired P12/P14 performance, quality and M4 remain `NOT_RUN` at this checkpoint. Raw witness hashes are in `witness-manifest.json`; raw stays local.

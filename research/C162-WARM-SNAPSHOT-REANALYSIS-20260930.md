# C161 → C162 warm instrumentation evidence

C161 original FAIL_UNIT_PRESERVED remains immutable: both model arms completed, analysis rejected valid planning state. C162 is a new analysis of the original hashed raw, with no model rerun.

Source llama-moe-stream.cpp emit_wave_slots pushes slot IDs into pool_used. Fixed graph waves execute even when w exceeds nonempty expert groups; plan_next_wave reflects graph progress. The reader incorrectly treated pool_used as booleans and bounded next_wave by nonempty n_waves. Corrected bounds preserve slot range, unique at most four IDs, touched booleans and finite graph upper bound ceil(128/plan_capacity). Native source-produced fixture mutations validate legal slots2/3 and empty waves; invalid slot, duplicate, negative and excessive wave indices rejected. Thirteen directed snapshot/capture tests PASS, two prospective overhead tests PASS. No numeric tolerance changed.

C162 reanalysis PASS: 1728 selected active witness files and57 full logit rows bitwise OFF/ON. Three snapshots total881372B; snapshot copy/write8392us. 67023 journal events,2144 loads,6768 decode demands. Journal calls9..57 rooted in actual before-warm state, complete generations/components/read/commit/barrier validation. Prefix history IDs/logits retained; unpublished prefix journal bounded at natural boundaries, full-prefix replay NOT_RUN.

Scope: direct C API2044+153+47 teacher-forced forwards, distinct from C142 free generation47 output IDs/46 subsequent decode evaluations and server expert state. Heavy numerical witnesses mean C161 timings are diagnostic, not production/overhead evidence. C159 original→loggerOFF bridge qualified the shorter189+32 set; C161/C162 samebinary OFF/ON covers this warm shape.

Next: two prospective alternating OFF/ON instrumentation-overhead pairs without witness observer, then frozen SQL/energy holdouts and actual seeded decode replay. M3partial/M4NOT_MET; no promotion or publication.

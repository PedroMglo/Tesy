# C86 E18 capacity spotcheck

- Read-only script/source freeze `b4361a4e17c3247ab37929add2b28953d91e42ec`; no model or full 60 s admission.
- At 20:18:22 UTC, MemAvailable was 19,767,382,016 B. Subtracting only the mandatory 2 GiB reserve and rounding down to 256 MiB gives an E18 cap upper bound of 17,448,304,640 B, short by 1,879,048,192 B. External variation and ancestor caps can only lower this bound.
- GPU query recovered: expected UUID, 12 MiB used, 43 °C. One earlier query failure was transient and is not classified as a driver crash.
- Decision: E18 necessary headroom absent; no 120B launch. Next: model-free trace attribution, then a fresh full admission only after material headroom change. C78 and C79/C82 statuses unchanged. No default or remote write.

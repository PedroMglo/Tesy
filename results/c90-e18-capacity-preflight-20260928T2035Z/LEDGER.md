# C90 E18 host preflight

- Freeze `80882e3e2fcdc7ccf7e7cbcb913ec2db74edf4a7`; `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c55_inventory.py results/c90-e18-capacity-preflight-20260928T2035Z` completed 61 samples across 60 s, maximum gap 1.000405 s.
- `MemAvailable_min` 22,293,942,272 B, variation 467,288,064 B, reserve 2,147,483,648 B; derived rounded cap max 20,132,659,200 B = 18.75 GiB, 805,306,368 B above E18. Memory PSI full avg10 0.0; AC/performance and sensors valid in snapshot.
- This admits E18 host capacity for a new bounded unit only. No model loaded; init/forward and full 8K bridge NOT_RUN. C78 remains FAIL.

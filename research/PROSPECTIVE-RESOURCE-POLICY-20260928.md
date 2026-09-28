# Tesy prospective physical resource policy — 2026-09-28

## Decision

Historical campaign guards remain part of their original protocols and are never reclassified.

For new physical campaigns, resource constraints are split into three classes:

- `DEVICE_LIMIT`: manufacturer, firmware, controller or device-reported threshold.
- `WARNING`: a valid operating region that requires telemetry and attribution; it is not an automatic correctness failure.
- `EXPERIMENT_ADMISSION`: a safety/comparability margin chosen prospectively for one experiment; it must never be described as a hardware limit.

The previous universal guards `CPU95 / GPU80 / NVMe70 / GPU7000MiB / MemAvailable6GiB / E18` are therefore **historical experiment policy**, not a description of the machine's physical limits.

## Hardware authority

Target observed by the laboratory: ASUS ProArt PX13 HN7306WV, Ryzen AI 9 HX 370, RTX 4060 Laptop 8 GiB class, 32 GB LPDDR5X and PCIe 4.0 NVMe.

Primary public sources:

- AMD HX 370: https://www.amd.com/en/products/processors/laptop/ryzen/ai-300-series/amd-ryzen-ai-9-hx-370.html
  - `Tjmax = 100 °C`
  - default TDP 28 W
  - cTDP 15–54 W
- ASUS PX13 HN7306: https://www.asus.com/pt/laptops/for-creators/proart/proart-px13-hn7306/techspec/
  - 32 GB LPDDR5X onboard
  - RTX 4060 Laptop 8 GB GDDR6
  - 1 TB M.2 2230 PCIe 4.0 NVMe
  - 200 W AC adapter
- ASUS thermal design: https://www.asus.com/pt/laptops/for-creators/proart/proart-px13-hn7306/
  - advertised combined CPU TDP + GPU TGP envelope up to 115 W; this is a platform capability, not a per-campaign power entitlement.
- NVIDIA telemetry semantics: https://docs.nvidia.com/deploy/nvidia-smi/
  - obtain Max Operating / Slowdown / Shutdown thresholds from the actual GPU when exposed.

Live device telemetry remains authoritative for the installed GPU, SSD, memory availability, firmware and process environment.

## Prospective rules

### CPU

- `95 °C`: `WARNING`.
- `100 °C`: HX 370 `DEVICE_LIMIT` (Tjmax).
- Do not call a run invalid merely because it entered 95–100 °C.
- Record clocks, package energy/power and observable thermal/cooling state when available.
- A thermal regime may make a profile slower; that is real sustained performance and should not be hidden.

### GPU temperature and power

Do not hardcode `80 °C`.

At preflight collect the actual NVIDIA temperature thresholds. Prefer:

- warning: GPU Max Operating Temp, when reported;
- stop/admission boundary: GPU Slowdown Temp when reported;
- shutdown remains a protection threshold, not a normal target.

If device thresholds cannot be obtained, classify them `UNKNOWN`; do not invent a vendor limit. A campaign that needs to approach the unknown region must first resolve it.

Collect current/default/max/enforced power limits when exposed. Do not manually raise power limits as part of a Tesy performance comparison.

### VRAM

Do not use `7000 MiB` or `6500 MiB` as universal hardware limits.

Prospective admission uses:

`memory.total - 512 MiB`

as an initial `EXPERIMENT_ADMISSION` margin. The 512 MiB reserve is not a device limit. It may only be changed by a new bounded capacity experiment with explicit accounting.

A bounded init and short forward must still prove workspace headroom before a long run.

### Host RAM

`E18`, `E20`, `E22`, `E24` are experiment profiles, not machine limits.

For new capacity exploration:

- read live `MemTotal` and `MemAvailable`;
- reserve initially 2 GiB for the host (`EXPERIMENT_ADMISSION`);
- suggest a cgroup maximum no larger than live `MemAvailable - reserve`, rounded down to 256 MiB;
- freeze one cgroup cap for all arms in a causal comparison;
- `memory.swap.max=0` remains the default for explicit-streaming campaigns so swap cannot become a hidden storage tier.

RSS is telemetry, not the sole capacity authority. `memory.current`, `memory.peak`, cgroup events, swap and host pressure are more important.

### NVMe

Do not hardcode `70 °C`.

Use the installed NVMe Composite sensor thresholds when plausible:

- `temp1_max` / WCTEMP-like threshold: warning;
- `temp1_crit` / CCTEMP-like threshold: stop/critical.

Reject implausible threshold encodings (for example values in the tens of thousands of degrees). Record the SSD model/firmware prospectively when available.

Requested `pread` bytes are not physical NVMe traffic.

## Implementation

`tools/host_resource_policy.py` derives the prospective policy from the live host/device snapshot.

New campaign preflights should persist this object and freeze the chosen experiment limits before model execution. Historical result roots and historical protocols are immutable.

Any new memory envelope, GPU reserve, or other admission change is a new profile/unit. Do not use this policy to retroactively turn historical FAILs into PASS.

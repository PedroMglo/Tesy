# C252 — Conversion inventory schema repair

C251 remains a PREMODEL failure: the first real inventory sample exposed that the policy file contained the runtime `tesy-resources-v2` schema instead of the derived inventory schema consumed by C118. No converter or model Popen occurred; 2.902085 s remains charged. This also identifies a latent preparation defect in the still NOT_RUN C248, which must be repaired under a new identity before B2 execution.

C252 regenerates only the inventory-policy representation from the original snapshot using the existing policy function. Its frozen runtime limits compare exactly to C251: 4 GiB, swap0 and all sensor/pressure/host guards unchanged. The real inventory sample validator accepts a preserved C247 sample with this representation and rejects the old schema; that model-free test is not a new live inventory or guard simulation. All pinned file/hash/schema bindings checked before starting. Full 60 s live inventory remains mandatory.

Same head/converter/exact value gate, 180 s conversion deadline, 360 s complete envelope, new output identity. No target or head forward, no runner modification. LOCAL_ONLY.

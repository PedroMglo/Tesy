# C254 — Independent RoPE row oracle repair

C253's artifact/resource/mapping measurement was valid, but the exact value gate failed; preserve FAIL and 88.876369 s. Source audit locates an error in the independent oracle: the original converter maps HF split-half Q/K rows to interleaved GGML rows. The gate used the inverse permutation. Its width4 synthetic fixture was self-inverse and missed this distinction.

REPRODUZIDO_MODEL_FREE: add explicit width8 two-head expected rows and the deliberately inverse mapping counterproof. Original source BF16 values, tensor shapes/dtypes, norm promotion and tolerance remain exact; no epsilon, converter, head values or production libraries change. The derived frequency tolerance is unchanged.

C254 rechecks the same frozen completed file under the corrected source-declared row mapping, using a new unit/receipt. Failure is not retroactively PASS and is not evidence of target arithmetic corruption. Same 4 GiB guards, inventory60s, audit90s, full envelope180s. No head/target forward. LOCAL_ONLY.

# C134b — slots40 8K boundary

C134b ran the original C42 synthetic retrieval prompt on C75 waves ON/slots40 under E18/zero swap. Source wrapper `aeab95e`; frozen measurement commit `733a17633c99183b7a742ce4e15c0c5bac7f8e47`. The model-free tokenizer bridge reproduced 7936 official input tokens before launch. The detached user service passed its scope smoke, survived the tool call, and exited with systemd `Result=success`, status0.

Measured on the target: 7936 official input IDs, 85 output IDs, natural stop, exact answer `Q7M2N9`, request wall 267.82 s, first final 266.58 s. The output cap was256; the model did **not** generate256 tokens. Cgroup peak 15,722,098,688 bytes, GPU peak 6877.0 MiB, swap zero. CPU peak 95.375 °C is above the95 °C warning and below the100 °C stop; the unit reported no resource stop.

Raw SHA256 `4ade0add6ef07ae24b808136dbde042d48f1bd23df2c8667c533f046350557e5`; receipt SHA256 `5089ce651620cf9d573b3ad474dccfe85cb467717455db49c1a078b50103a2f3`. Independent revalidation matched the receipt. Raw remains local. The result establishes this one 8K-boundary retrieval and forward admission for slots40, not general full-context numerical equivalence or a causal timing gain over C42. C134 remains interrupted and unchanged.

Physical charge 333.6 s; remaining lower-bound physical budget 7622.6 s. M4 is still not met on the nominal153 first-final and decode gates.

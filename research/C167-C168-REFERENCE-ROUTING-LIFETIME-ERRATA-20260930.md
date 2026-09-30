# C167 failure and C168 causal repair

C167 historical decision FAIL_UNIT_PRESERVED stays immutable. First canonical layer0: all five FFN outputs bitwise, but postgraph reads of routingIDs/weights fail; remaining35references NOT_RUN.64.770122s live. This is not evidence that native committed routing or weights were changed; C166 same-profile states/logits/bytechecks still pass.

SOURCE_AUDITED: pinned ggml-alloc.c frees/reuses intermediate graph storage after its last child unless GGML_TENSOR_FLAG_OUTPUT retains it. Expanding route_ids/route_weights into graph does not retain their values for postgraph tensor_get. The old reference included downstream FFN, then read unretained intermediates. Native FFN equality despite corrupt routing readout is consistent with correct computation and invalid later evidence.

REPRODUZIDO_MODEL_FREE: new reference_output_lifetime_test.cpp exercises actual pinned CPU scheduler/allocator with8scores/two rows,top4 and downstream scale,no GGUF/model. Unmarked readout fails; ggml_set_output protected routing survives. stdout {unmarked_route_read_valid:false,marked_route_read_valid:true}. Build commands/logs/results preserved C168. Only canonical reference adds output flags toids/weights/finalout; no weights,routerarithmetic,device,shape,grouping or tolerances change. C165 original referencebinary retained; new C168reference separatelyhashed. This is the single causal harness repair allowed for this branch.

Next: C169 fresh36referenceattempt; fullfamily bounded within remaining30minbranch and globalclosure. Any further failure stops without repeating until success. No historical result rewritten or correctness inherited beyond captured boundary.

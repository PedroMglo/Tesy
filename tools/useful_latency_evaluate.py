"""Prospective post-C198 portfolio gates, separate from native64 historical rules."""
from statistics import median
from c2_gate import GateError
from native64_evaluate import paired
PROTECTED=('T2_first_final_s','T2_completion_s','SQL_first_final_s','cold_prefill_s','cold_first_final_s','incremental_prefill_s','T2_seconds_per_output','SQL_seconds_per_output')
def evaluate(pairs,hypothesis,confirmation=False):
 if hypothesis not in ('H1','H2') or len(pairs)!=(3 if confirmation else 2):raise GateError('portfolio identity/cardinality')
 names=('SQL_validated_s',)+PROTECTED+(('holdout_validated_s','holdout_first_final_s','holdout_seconds_per_output') if confirmation else ())
 gains={k:[] for k in names}
 for a,b in pairs:
  if a['profile']!='A' or b['profile']!='B':raise GateError('wrong portfolio pair')
  if not all(x.get('valid') for x in (a,b)):return {'status':'FAIL_OR_INCOMPLETE_EVIDENCE'}
  if a['input_ids']!=b['input_ids']:return {'status':'INCONCLUSIVE_INPUT_OR_PREFIX'}
  if hypothesis=='H2' and a['trajectory']!=b['trajectory']:return {'status':'FAIL_SAME_PROFILE_OBSERVABLE_TRAJECTORY'}
  for k in names:gains[k].append(paired(a[k],b[k]))
 med={k:median(v) for k,v in gains.items()}
 checks={'SQL_median8':med['SQL_validated_s']>=8,'SQL_all_positive':all(g>0 for g in gains['SQL_validated_s']),
         'protected_medians':all(med[k]>=-5 for k in PROTECTED),
         'protected_individuals':all(g>=-15 for k in PROTECTED for g in gains[k])}
 if confirmation:
  checks.update(holdout_median5=med['holdout_validated_s']>=5,holdout_all_positive=all(g>0 for g in gains['holdout_validated_s']),
    holdout_protections=all(med[k]>=-5 and all(g>=-15 for g in gains[k]) for k in ('holdout_first_final_s','holdout_seconds_per_output')))
 return {'status':('GO' if all(checks.values()) else 'NO_GO')+('_CONFIRMATION' if confirmation else '_SCREEN'),
         'hypothesis':hypothesis,'gains':gains,'medians':med,'checks':checks,'scope':'Same supplied transcript, free outputs; no equal-compute claim'}

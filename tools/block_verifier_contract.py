"""Frozen greedy position/acceptance accounting, independent of model outputs."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Accepted:
    tokens: tuple
    matched_drafts: int
    rejected_at: int | None
    consumed_inputs: int
    next_pending_anchor: int | None
    terminal: str | None


def verify(target_rows, proposals, *, eos=(), remaining=None):
    """row j follows input position j; first input is the already known anchor.

    Every emitted correction/bonus is sampled from a target row. The returned
    consumed_inputs are anchor + matching proposals; rejected suffix KV must
    be removed. The final sampled token is pending input for the next call.
    """
    if not proposals or len(target_rows) != len(proposals)+1:
        raise ValueError('complete block logits required')
    if any(type(x) is not int or x < 0 for x in [*target_rows,*proposals]):
        raise ValueError('official nonnegative token IDs required')
    if remaining is None:remaining=len(target_rows)+1
    if type(remaining) is not int or remaining < 1:
        raise ValueError('positive output reserve required')
    result=[];matched=0;rejected=None;terminal=None
    for j, token in enumerate(target_rows):
        result.append(token)
        if j < len(proposals):
            if token==proposals[j]:matched+=1
            else:rejected=j
        if token in eos:terminal='EOS'
        elif len(result)==remaining:terminal='CAP'
        if terminal is not None or rejected is not None or j==len(proposals):break
    # A matched EOS/cap need not be retained in a continuing cache; no next call.
    consumed=1+matched
    return Accepted(tuple(result),matched,rejected,consumed,
                    result[-1] if terminal is None else None,terminal)


def budgets(sequential_s, positions, verify_s, *, accepted, draft_s=0, rollback_s=0, gain=.15):
    values=(sequential_s,verify_s,draft_s,rollback_s,gain)
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in values) or \
       sequential_s<=0 or verify_s<=0 or draft_s<0 or rollback_s<0 or not 0<=gain<1 or \
       type(positions) is not int or positions<1 or type(accepted) is not int or not 1<=accepted<=positions:
        raise ValueError('invalid measured amortization/accounting')
    per=sequential_s/positions
    return dict(T_AR_s=per,L_break_even=(verify_s+draft_s+rollback_s)/per,
                D_budget_s=(1-gain)*accepted*per-verify_s-rollback_s,
                accepted_tokens=accepted,positions=positions,
                idealized=draft_s==0 and rollback_s==0)


def paired_gain(control,candidate):
    if any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in (control,candidate)):
        raise ValueError('missing/nonfinite/nonpositive timing is not zero')
    return 100*(control-candidate)/control

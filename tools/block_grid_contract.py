"""Draft-independent fixed-grid R1 reference inputs; no backend or predictions."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Grid:
    start: int
    known_rows: int
    query_row: int
    inputs: tuple
    completed_grids: tuple


def reference_inputs(confirmed, *, origin, B, padding=0, context=8192):
    """R1 next-token query depends only on the complete confirmed prefix.

    Prefill [0,origin) is fixed. Completed decode grids always have B rows.
    The last grid is recomputed from its boundary, filled only with confirmed
    IDs then deterministic padding. No proposal or rejected suffix is an input.
    Future independence still requires source and native numeric qualification.
    """
    if type(origin) is not int or origin < 1 or B not in (2,4,8) or \
            type(B) is not int or type(context) is not int or context < origin+B or \
            type(padding) is not int or padding < 0 or \
            any(type(token) is not int or token < 0 for token in confirmed):
        raise ValueError('invalid fixed-grid metadata/official IDs')
    if len(confirmed) <= origin:
        raise ValueError('at least the pending anchor must be confirmed')
    tail=tuple(confirmed[origin:])
    start=origin+((len(tail)-1)//B)*B
    known=(len(tail)-1)%B+1
    if start+B > context:
        raise ValueError('fixed grid does not fit context; never silently shrink shape')
    completed=tuple(tuple(tail[i:i+B]) for i in range(0,len(tail)-known,B))
    inputs=tuple(tail[-known:])+(padding,)*(B-known)
    return Grid(start,known,known-1,inputs,completed)


def require_greedy(*, temperature, sampling_qualified=False):
    if temperature != 0 or type(temperature) not in (int,float):
        raise ValueError('unqualified sampling: reject before candidate execution; explicit R0 is separate')
    if sampling_qualified:
        raise ValueError('this experiment does not qualify stochastic distribution')


def retention_after_rejection(*, grid_start, confirmed_after, B):
    if type(grid_start) is not int or type(confirmed_after) is not int or B not in (2,4,8) or \
            not grid_start < confirmed_after <= grid_start+B:
        raise ValueError('invalid rollback boundary')
    # Preserve earlier completed grids; rebuild partial grid from confirmed IDs.
    return grid_start

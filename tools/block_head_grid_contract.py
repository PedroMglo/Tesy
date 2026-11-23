"""Greedy fixed-B8 acceptance plan; independent of the head's predictions."""
from block_grid_contract import reference_inputs


def proposal_inputs(confirmed, *, origin, proposals, context=8192):
    grid=reference_inputs(confirmed,origin=origin,B=8,context=context)
    if type(proposals) is not list or len(proposals)!=7 or any(type(x) is not int or not 0<=x<201088 for x in proposals):
        raise ValueError('real head must supply seven valid native proposals')
    remaining=8-grid.known_rows
    return grid,tuple(confirmed[-grid.known_rows:])+tuple(proposals[:remaining])


def accept_grid(known, inputs, winners, *, remaining_output, eos_ids=()):
    if type(known) is not int or not 1<=known<=8 or len(inputs)!=8 or len(winners)!=8 or \
       type(remaining_output) is not int or remaining_output<1 or any(type(x) is not int or not 0<=x<201088 for x in (*inputs,*winners)):
        raise ValueError('invalid grid rows/output budget')
    new=[];accepted=0;source_row=known-1;finish='CONTINUE'
    for row in range(known-1,8):
        token=winners[row];new.append(token);source_row=row
        matches = row<7 and token==inputs[row+1]
        if matches:accepted+=1
        if token in eos_ids:finish='EOS';break
        if len(new)==remaining_output:finish='CAP';break
        if row==7:break # last row is bonus, never counted again as an anchor
        if not matches:break # authoritative correction, no later draft commits
    return {'new_ids':new,'accepted_draft_count':accepted,'feature_row':source_row,'finish':finish}

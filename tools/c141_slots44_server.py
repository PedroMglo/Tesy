#!/usr/bin/env python3
"""Bounded uniform40/44 nominal153 families through the mature C120 entrypoint."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import c120_nominal_server as campaign
import c128_slots40_server as existing
import c112_nominal_session_base as base
from c2_gate import GateError,strict_json
from run_bounded import sha256

REPO=base.REPO
CAP=20*2**30
UNIT='c141'
ROOT_NAME='c141-uniform44-screen-20260929T2330Z'
NUMERIC=REPO/'results/c140-slots44-numeric-20260929T2324Z'
CHECKPOINT=NUMERIC/'epoch-checkpoint.json'
DEADLINE=datetime.fromisoformat('2026-09-30T01:31:15+00:00')
ORIGINAL_BASE=existing._base_make
ORIGINAL_MAKE=campaign.make
ORIGINAL_POLICY=campaign.screen_policy


def slot_make(root,arm):
    p,c=ORIGINAL_BASE(root,arm)
    cmd=c['server_command'];i=cmd.index('--moe-stream-cache')+1
    if cmd[i]!='32s':raise GateError('original inherited slot identity changed')
    cmd[i]='40s' if arm=='control' else '44s'
    c['total_timeout_s']=300;c['request_policy']['per_request_timeout_s']=240
    p['identity']['config_sha256']=campaign.server.digest(c)
    return p,c


def make(root,spec):
    p,c=ORIGINAL_MAKE(root,spec)
    p['c120']['c128_numeric_profile']={'backend':'C75','wave_skip_parked':'ON',
        'slots_per_layer':40 if spec[1]=='control' else 44,
        'numeric_decision_sha256':sha256(NUMERIC/'decision.json'),
        'claim':'distinct slot geometry numeric profiles; same original C75 binary; no eviction intervention'}
    p['family_envelope_s']=2250 if len(campaign.ORDER)==6 else 1500
    p['per_arm_envelope_s']=375;p['epoch_deadline_utc']=DEADLINE.isoformat()
    return p,c


def screen_policy(root):
    row=ORIGINAL_POLICY(root);n=len(campaign.ORDER)//2
    row.update(schema=f'{UNIT}-uniform44-policy-v1',pairs=n,primary='warm decode_s',
        protected=['warm first_final_content_s','warm prefill_s','cold decode_s','cold first_final_content_s','cold prefill_s','answer/prefix/resources/identity/inventory'],
        screen_go=f'median warm decode duration gain>=8%; all {n} primary gains positive; every protected median>=-5%; equal work and all gates PASS',
        profiles={'control':{'backend':'C75','slots':40,'wave':'ON'},'candidate':{'backend':'C75','slots':44,'wave':'ON'}},
        numeric_decision_sha256=sha256(NUMERIC/'decision.json'),
        server_timeout_s=300,request_timeout_s=240,cleanup_s=15,
        family_envelope_s=2250 if n==3 else 1500,deadline_utc=DEADLINE.isoformat())
    if n==3:
        prior=REPO/'results/c141-uniform44-screen-20260929T2330Z/decision.json'
        if strict_json(prior.read_text())['status']!='SCREEN_GO_UNIFORM44_NOMINAL153':
            raise GateError('valid uniform44 screen prerequisite absent')
        row['screen_decision_sha256']=sha256(prior)
    return row


def budget(root,remaining):
    old=strict_json(CHECKPOINT.read_text());now=datetime.now(timezone.utc)
    intervals=[]
    for rid,_,_ in campaign.ORDER:
        path=root/'raw'/f'{rid}.receipt.json'
        if path.is_file():
            row=strict_json(path.read_text());a,b=map(datetime.fromisoformat,(row['started_utc'],row['ended_utc']))
            if b<a:raise GateError('family receipt time reversed')
            intervals.append({'run':rid,'seconds':(b-a).total_seconds(),'status':row['status']})
    spent=sum(r['seconds'] for r in intervals)
    family_limit=2250 if len(campaign.ORDER)==6 else 1500
    physical=old['physical_remaining_lower_bound_s']-spent;wall=(DEADLINE-now).total_seconds()
    reserve=remaining*375+600
    if spent+remaining*375>family_limit+1e-6 or min(wall,physical)<reserve:
        raise GateError('uniform44 family envelope and closure not admitted')
    return {'utc':now.isoformat(),'remaining_arms':remaining,'completed':intervals,
        'physical_remaining_lower_bound_s':physical,'wall_remaining_s':wall,'worst_case_s':reserve,
        'family_elapsed_s':spent,'family_limit_s':family_limit,'checkpoint_sha256':sha256(CHECKPOINT)}


def configure(root):
    global ROOT_NAME,UNIT,CHECKPOINT
    ROOT_NAME=root.name;UNIT=root.name.split('-',1)[0]
    if UNIT not in ('c141','c142'):raise GateError('explicit screen/confirmation ID required')
    n=3 if UNIT=='c142' else 2
    if n==3:CHECKPOINT=REPO/'results/c141-uniform44-screen-20260929T2330Z/epoch-checkpoint.json'
    specs=[]
    for i in range(1,n+1):
        roles=('control','candidate') if i%2 else ('candidate','control')
        specs.extend((f'{UNIT}-p{i}-{role}',role,i) for role in roles)
    base.BACKENDS={'control':existing.BACKEND,'candidate':existing.BACKEND};base.CAP=CAP;base.make=slot_make
    campaign.CAP=CAP;campaign.ORDER=tuple(specs);campaign.ROOT_NAME=ROOT_NAME
    campaign.CAMPAIGN_WRAPPER_FILE=__file__;campaign.make=make;campaign.screen_policy=screen_policy;campaign.budget=budget


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('freeze','run'));ap.add_argument('root',type=Path)
    ap.add_argument('--run-id');ap.add_argument('--measurement-commit');a=ap.parse_args();root=a.root.resolve();configure(root)
    if a.mode=='freeze':
        if strict_json((NUMERIC/'decision.json').read_text())['status']!='PASS_UNIFORM44_NUMERIC_BOUNDARY_AND_36_FFN':
            raise GateError('uniform44 numeric gate missing')
        campaign.freeze(root)
    else:
        if not a.run_id or not a.measurement_commit:ap.error('run ID/measurement commit required')
        spec=next(s for s in campaign.ORDER if s[0]==a.run_id)
        raise SystemExit(campaign.run(root,spec,a.measurement_commit))

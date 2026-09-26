#!/usr/bin/env bash
set -u -o pipefail
cd "$(dirname "$0")/.." || exit 2
ulimit -c 0
mode="${1:?usage: c3_run_negative.sh wrong_id|stale_byte|bias_index|eio|eof|short|delay}"
run_id="c3-r2-negative-${mode}01"
options=()
case "$mode" in
  wrong_id|stale_byte|bias_index)
    options=(--env "TESY_C3_MUTANT=$mode")
    ;;
  eio|eof|short|delay)
    options=(--env "LD_PRELOAD=$PWD/tools/libc2_fault_pread.so"
             --env "TESY_C2_PREAD_FAULT=$mode"
             --env TESY_C2_FAULT_DEFER=1
             --env TESY_C3_ARM_READ_FAULT=1)
    ;;
  *) echo "unknown mode" >&2; exit 2;;
esac
systemd-run --user --scope --property=MemoryMax=18G --property=MemorySwapMax=0 \
  python3 tools/run_bounded.py --run-id "$run_id" \
  --model-id gpt-oss-120b-mxfp4-gguf --backend streaming \
  --variant "c3-negative-$mode-gpu8-slot32-ub32" \
  --workload results/c2-target-numeric-v1.ids \
  --cache-condition prior-target-and-reference-runs-page-cache-uncontrolled \
  --timeout-s 300 --max-rss-gib 17 --min-available-gib 6 --max-gpu-mib 7000 \
  --max-cpu-c 95 --max-gpu-c 80 --max-nvme-c 70 --require-telemetry \
  --env LLAMA_MOE_STREAM_NO_PRELOAD=1 "${options[@]}" -- \
  tools/c3_boundary_capture \
  /home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf \
  results/c2-target-numeric-v1.ids log_medium "results/$run_id.raw"
runner_rc=$?
python3 - "$mode" "$run_id" "$runner_rc" <<'PY'
import hashlib,json,pathlib,sys
mode,run_id,runner_rc=sys.argv[1],sys.argv[2],int(sys.argv[3])
root=pathlib.Path('results')
manifest_path=root/f'{run_id}.json'
stderr_path=root/f'{run_id}.stderr'
audit_path=root/f'{run_id}-audit.json'
manifest=json.loads(manifest_path.read_text())
stderr=stderr_path.read_text()
expected_marker=(f'TESY_C3_MUTANT_INJECTED {mode}' if mode in
                 ('wrong_id','stale_byte','bias_index') else 'TESY_C2_FAULT_INJECTED')
markers=stderr.count(expected_marker)
failed=manifest['returncode'] != 0 and runner_rc != 0
if mode=='delay':
    valid=manifest['returncode']==0 and runner_rc==0 and markers==1
else:
    valid=failed and markers==1
if mode in ('eio','eof','short'):
    valid &= stderr.count('TESY_C3_READ_FAULT_ARMED')==1 and \
             'expert load failed (I/O error)' in stderr
if mode in ('wrong_id','stale_byte','bias_index'):
    valid &= 'C3_CAPTURE_FAIL:' in stderr
start,end=manifest['cgroup_start'],manifest['cgroup_end']
valid &= manifest['stop_reason'] is None and end['swap_current']==0 and \
         manifest['maxima']['swap_bytes']==0
for group in ('events','events_local'):
    for event in ('oom','oom_kill'):
        valid &= start[group][event]==0 and end[group][event]==0
    valid &= start[group]['max']==end[group]['max']
report={'schema':'c3-negative-audit-v1','run_id':run_id,'mode':mode,
        'status':'PASS_EXPECTED_BEHAVIOR' if valid else 'FAIL_EVIDENCE',
        'target_run_status':'SUCCESS' if mode=='delay' and valid else 'EXPECTED_FAILURE',
        'returncode':manifest['returncode'],'runner_rc':runner_rc,
        'marker_count':markers,'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'stderr_sha256':hashlib.sha256(stderr_path.read_bytes()).hexdigest()}
with audit_path.open('x') as out:
    json.dump(report,out,indent=2,allow_nan=False);out.write('\n')
print(json.dumps(report,allow_nan=False))
sys.exit(0 if valid else 1)
PY

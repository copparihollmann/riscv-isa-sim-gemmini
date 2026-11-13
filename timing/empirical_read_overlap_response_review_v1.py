#!/usr/bin/env python3
"""Independent fixed-coefficient V8 source, readiness and same-ELF assessment."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def jsonl(p):return [json.loads(x)for x in Path(p).read_text().splitlines()]


def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 old=ROOT/'build/memory-routes-current-9b2-fixed-baseline-v1';off=ROOT/'build/memory-routes-response-read-OFF-v2';on=ROOT/'build/memory-routes-current-7bd5-read-overlap-ON-v1'
 comparison=ROOT/'build/memory-routes-current-7bd5-ON-comparison-v1';package=ROOT/'build/empirical-read-overlap-response-frozen-7bd58b4f'
 manifest=load(package/'manifest.json');inventory=load(package/'source-inventory.json')
 for name,value in manifest['artifact_sha256'].items():
  if sha(package/name)!=value:raise ValueError('Frozen native artifact changed')
 for folder in(old,off,on):
  r=load(folder/'run.json')
  if r.get('pass')is not True or r.get('regions')!=2592 or r.get('timed_out')is not False or r.get('debugger_exit_status')!=0:raise ValueError('All2592 typed regions required')
  for path,value in {**r['input_sha256'],**r['output_sha256']}.items():
   if sha(path)!=value:raise ValueError('Native evidence changed')
 for name in('features.jsonl','region-features.jsonl','regions.jsonl','stderr','stdout'):
  if(old/name).read_bytes()!=(off/name).read_bytes():raise ValueError('V8 OFF does not preserve full V6 baseline')
 ref=load(comparison/'report.json')
 if ref.get('pass')is not True or ref.get('parameter_fit_performed')is not False:raise ValueError('Fixed full comparison required')
 for path,value in ref['artifact_sha256'].items():
  if sha(comparison/path)!=value:raise ValueError('Comparison changed')
 qual=ROOT/'build/memory-routes-current-7bd5-ON-qualification-v1/report.json';q=load(qual)
 if q.get('pass')is not True or(q.get('counter_word_controls'),q.get('prefix_controls'))!=(14,8):raise ValueError('All22 typed refusals required')
 for path,value in q['input_sha256'].items():
  if sha(path)!=value:raise ValueError('Typed qualification changed')
 fixture=ROOT/'build/empirical-read-overlap-response-inputs-v2/on.fixture';prior=ROOT/'calibration/compute-fit-fadd-shape-store-9b2-selected-v2/runtime.fixture'
 normalize=lambda text:[l for l in text.splitlines()if not l.startswith(('empirical_profile ','empirical_read_overlap '))]
 if normalize(fixture.read_text())!=normalize(prior.read_text()):raise ValueError('Coefficient or unrelated model fixture changed')
 if fixture.read_text().splitlines().count('empirical_read_overlap response-ready-L1-read-only-v2')!=1:raise ValueError('Explicit V8 opt-in required')
 before=ROOT/'pipeline/riscv-isa-sim-fadd-shape-store-fixed-v1';after=ROOT/'pipeline/riscv-isa-sim-read-overlap-response-v2'
 source_map=lambda root:{str(x.relative_to(root)):sha(x)for x in root.rglob('*')if x.is_file()and'.git'not in x.parts}
 sa,sb=source_map(before),source_map(after);changed={k for k in set(sa)|set(sb)if sa.get(k)!=sb.get(k)}
 expected={'riscv/'+n for n in('iris_empirical_features.inc','iris_empirical_load.inc','iris_empirical_store.inc','iris_memory_adapter.cc','iris_timing_adapter.cc','iris_timing_adapter.h')}
 if changed!=expected:raise ValueError('Unexpected native delta')
 diffs=[]
 for name in sorted(expected):
  if inventory.get(str((after/name).relative_to(ROOT)))!=sb[name]:raise ValueError('Native source differs from frozen capsule')
  diffs.extend(difflib.unified_diff((before/name).read_text().splitlines(True),(after/name).read_text().splitlines(True),fromfile='9b2/'+name,tofile='7bd5/'+name))
 (out/'native-source-delta.patch').write_text(''.join(diffs))
 for name in('timing/empirical_cache_v8.cpp','timing/empirical_cache_v8.hpp'):
  if inventory.get(name)!=sha(ROOT/name):raise ValueError('Helper source differs from frozen capsule')
 helper=(ROOT/'timing/empirical_cache_v8.cpp').read_text();header=(ROOT/'timing/empirical_cache_v8.hpp').read_text();adapter=(after/'riscv/iris_timing_adapter.cc').read_text();loads=(after/'riscv/iris_empirical_load.inc').read_text();stores=(after/'riscv/iris_empirical_store.inc').read_text()
 checks={
  'default_OFF':'bool compatible_warm_reads=false' in header,
  'ordinary_scalar_reads_explicitly_classified':'vector?empirical_cache_->begin_vector(access):f.memory.kind==iris::AccessKind::load?empirical_cache_->begin_read(access):empirical_cache_->begin(access)' in adapter,
  'response_ready_required_for_private_hit':'!compatible_warm_reads_||cache.lines[at+way].response_ready' in helper,
  'acceptance_cannot_bless_fill':'copy->response_ready=false;copy->readiness_owner=a.id' in helper,
  'completion_requires_same_generation':'copy->readiness_owner==id' in helper,
  'failed_response_invalidates':'if(successful)copy->response_ready=true;else copy->valid=false' in helper,
  'pending_writer_unknowns_still_block':'compatible_warm_reads_&&p.ordinary_read' in helper,
  'only_ready_new_read_can_omit_dependencies':'warm_read&&p.ordinary_read' in helper,
  'real_load_fault_is_not_success':'clock_.now(),!r.exception' in loads,
  'actual_store_retirement_controls_success':'empirical_cache_->complete(owner,clock_.now(),retired)' in stores,
  'boundary_retirement_controls_success':'empirical_cache_->complete(id,clock_.now(),retired_[hart]==retired_before+1)' in adapter,
  'CPU_numerical_and_forwarding_paths_unchanged':all(sa[k]==sb[k]for k in('riscv/processor.cc','riscv/iris_shuttle_issue.cc','riscv/iris_rocket_packets.cc','riscv/iris_scalar_fadd.inc'))}
 if not all(checks.values()):raise ValueError('Independent source scope check failed')
 command=['g++','-std=c++20','-O2','-I'+str(ROOT/'timing'),str(ROOT/'timing/empirical_read_overlap_response_probe_v1.cpp'),str(ROOT/'timing/empirical_cache_v8.cpp'),'-o',str(out/'probe')]
 r=subprocess.run(command,capture_output=True);(out/'compile.stdout').write_bytes(r.stdout);(out/'compile.stderr').write_bytes(r.stderr)
 if r.returncode:raise ValueError('Independent readiness probe compile failed')
 r=subprocess.run([str(out/'probe')],capture_output=True);(out/'probe.stdout').write_bytes(r.stdout);(out/'probe.stderr').write_bytes(r.stderr)
 if r.returncode:raise ValueError('Independent readiness probe failed')
 probe=json.loads(r.stdout)
 if probe.get('pass')is not True or probe.get('checks')!=2027 or probe.get('refusals')!=1:raise ValueError('Readiness/generation controls missing')
 oldrows=jsonl(old/'region-features.jsonl');onrows=jsonl(on/'region-features.jsonl');joined=jsonl(comparison/'regions.jsonl')
 previous={(x['case_id'],x['hart']):x for x in oldrows};triples=[]
 for x in joined:
  if(x['target'],x['pattern'],x['kind'],x['n'],x['mask'])==('dram','bank0','chase',257,7):
   triples.append({**{k:x[k]for k in('case_id','hart','trial_id','hardware_cycles','native_cycles','signed_error_percent','actual_model_data_path_features')},'old_native_cycles':previous[x['case_id'],x['hart']]['native_cycles']})
 inputs=[Path(__file__).resolve(),ROOT/'timing/empirical_read_overlap_response_probe_v1.cpp',ROOT/'timing/empirical_cache_v8.cpp',ROOT/'timing/empirical_cache_v8.hpp',package/'manifest.json',package/'source-inventory.json',fixture,prior,comparison/'report.json',qual,*[x/'run.json'for x in(old,off,on)],*[after/x for x in expected]]
 result={'schema':'iris.empirical_read_overlap_response_independent_causal_review.v1','pass':True,'source_review_checks':checks,'source_review_findings':[],
  'actual_regions':2592,'all_independent_goldens':True,'actual_CSR_ELF_boundary_joins':5184,'typed_corruption_refusals':22,
  'OFF_entire_prefix_and_readback_byteidentical':True,'ON_changed_cycle_spans':sum(x['native_cycles']!=y['native_cycles']for x,y in zip(oldrows,onrows)),
  'fixed_coefficients_equal':True,'parameter_fit_performed':False,'parameters_changed':False,'global_heldout_timings_consumed':False,'hardware_contacted':False,
  'metrics_all':ref['metrics_all'],'metrics_by_target':ref['metrics_by_target'],'metrics_by_target_kind':ref['metrics_by_target_kind'],
  'matched_triples':triples,'independent_response_probe':probe,'assessment':'Actual same-ELF execution removes the identified shared-private-read serialization tail without coefficient changes. Other timing errors persist and no whole-model accuracy certificate follows.',
  'limitations':['Approximate timing tags, not source RTL cache permissions or a complete coherence protocol.','New epoch requires separate compute/OS/compiler qualification; no old acceptance transfer.','New memory reference is fitting/development evidence; global heldout observations were not consumed.','No absolute memory latency or serial service is inferred from this correction.'],
  'normal_guest_exit_verified_by_timed_replay':False,'intentional_post_ROI_debugger_stop':True,'full_2pct_certified':False,'source_image_association_verified':False,
  'input_sha256':{str(x):sha(x)for x in inputs},'compile_argv':command}
 result['artifact_sha256']={x.name:sha(x)for x in out.iterdir()if x.is_file()};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pass':True,'metrics':result['metrics_all'],'changed_spans':result['ON_changed_cycle_spans'],'output':str(out)}))


if __name__=='__main__':main()

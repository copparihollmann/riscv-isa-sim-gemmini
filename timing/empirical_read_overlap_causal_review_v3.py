#!/usr/bin/env python3
"""Independent fixed-parameter ON/OFF read-overlap review, without fitting."""
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
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    old=ROOT/'build/memory-routes-current-9b2-fixed-baseline-v1';off=ROOT/'build/memory-routes-read-overlap-OFF-v1'
    on=ROOT/'build/memory-routes-current-04c5-read-overlap-ON-v1';comparison=ROOT/'build/memory-routes-current-04c5-ON-comparison-v1'
    package=ROOT/'build/empirical-read-overlap-frozen-04c5e8da';manifest=load(package/'manifest.json');inventory=load(package/'source-inventory.json')
    for name,wanted in manifest['artifact_sha256'].items():
        if sha(package/name)!=wanted:raise ValueError('Frozen artifact mismatch')
    reports=[load(x/'run.json')for x in (old,off,on)]
    if any(r.get('pass')is not True or r.get('regions')!=2592 or r.get('debugger_exit_status')!=0 or r.get('timed_out')is not False for r in reports):
        raise ValueError('Complete typed same-ELF runs required')
    for r in reports:
        for name,wanted in {**r['input_sha256'],**r['output_sha256']}.items():
            if sha(name)!=wanted:raise ValueError('Replay source or evidence changed')
    derived=load(comparison/'report.json')
    if derived.get('pass')is not True or derived.get('parameter_fit_performed')is not False:raise ValueError('Complete fixed comparison required')
    for name,wanted in derived['artifact_sha256'].items():
        if sha(comparison/name)!=wanted:raise ValueError('Comparison artifact mismatch')
    fixture=ROOT/'build/empirical-read-overlap-inputs-v1/on.fixture';prior=ROOT/'calibration/compute-fit-fadd-shape-store-9b2-selected-v2/runtime.fixture'
    canonical=lambda p:[x for x in p.read_text().splitlines()if not x.startswith(('empirical_profile ','empirical_read_overlap '))]
    if canonical(fixture)!=canonical(prior):raise ValueError('Unrelated fixture/parameter change')
    if fixture.read_text().splitlines().count('empirical_read_overlap warm-private-L1-read-only-v1')!=1:raise ValueError('New explicit flag absent/duplicated')
    if any((old/n).read_bytes()!=(off/n).read_bytes()for n in ('features.jsonl','region-features.jsonl','stderr')):
        raise ValueError('OFF must preserve entire old prefixes, readback and feature rows')
    oldrows=jsonl(old/'region-features.jsonl');onrows=jsonl(on/'region-features.jsonl')
    if len(oldrows)!=2592 or len(onrows)!=2592:raise ValueError('Incomplete causal rows')
    changed=[{'case_id':x['case_id'],'hart':x['hart']}for x,y in zip(oldrows,onrows)if x!=y]
    prefix_a=jsonl(old/'features.jsonl');prefix_b=jsonl(on/'features.jsonl')
    normalize=lambda values:[{k:v for k,v in x.items()if k!='calibration_identity'}for x in values]
    normalized_equal=normalize(prefix_a)==normalize(prefix_b)
    before=ROOT/'pipeline/riscv-isa-sim-fadd-shape-store-fixed-v1';after=ROOT/'pipeline/riscv-isa-sim-read-overlap-v1'
    expected={'riscv/'+x for x in ('iris_empirical_features.inc','iris_empirical_load.inc','iris_memory_adapter.cc','iris_timing_adapter.cc','iris_timing_adapter.h')}
    source_files=lambda base:{str(p.relative_to(base)):sha(p)for p in base.rglob('*')if p.is_file()and'.git'not in p.parts}
    sources_a,sources_b=source_files(before),source_files(after)
    modified={k for k in set(sources_a)|set(sources_b)if sources_a.get(k)!=sources_b.get(k)}
    if modified!=expected:raise ValueError('Unreviewed native-source delta')
    diffs=[]
    for name in sorted(expected):
        p=after/name
        if inventory.get(str(p.relative_to(ROOT)))!=sha(p):raise ValueError('Source differs from frozen native inventory')
        diffs.extend(difflib.unified_diff((before/name).read_text().splitlines(True),p.read_text().splitlines(True),fromfile='9b2/'+name,tofile='04c5/'+name))
    (out/'native-source-delta.patch').write_text(''.join(diffs))
    for name in ('timing/empirical_cache_v7.cpp','timing/empirical_cache_v7.hpp'):
        if inventory.get(name)!=sha(ROOT/name):raise ValueError('Cache source differs from compiled closure')
    text=(ROOT/'timing/empirical_cache_v7.cpp').read_text();adapter=(after/'riscv/iris_timing_adapter.cc').read_text()
    checks={
        'explicit_default_OFF':'bool compatible_warm_reads=false' in (ROOT/'timing/empirical_cache_v7.hpp').read_text(),
        'ordinary_read_preclassification_before_tag_mutation':'compatible_warm_reads_&&ordinary_read&&!instruction&&!vector&&!a.write&&path==Path::DRAM&&data_hit' in text,
        'both_pending_and_new_owner_must_be_warm':'if(warm_read&&p.warm_read)' in text,
        'unknown_begin_is_not_ordinary':'begin(Access a){return begin_internal(a,false,false);}' in text,
        'vector_instruction_have_distinct_begin_methods':'begin_internal(a,false,true)' in text and 'begin_internal(a,true,false)' in text,
        'actual_boundary_dispatch_excludes_vector_and_LRSC_AMO':'vector?empirical_cache_->begin_vector(access):f.memory.kind==iris::AccessKind::load?empirical_cache_->begin_read(access):empirical_cache_->begin(access)' in adapter,
        'latched_private_load_response_reads_ordinary_only':'empirical_cache_->begin_read' in (after/'riscv/iris_empirical_load.inc').read_text(),
        'publication_and_store_completion_sources_unchanged':sources_a['riscv/iris_empirical_store.inc']==sources_b['riscv/iris_empirical_store.inc'] and sources_a['riscv/iris_shuttle_issue.cc']==sources_b['riscv/iris_shuttle_issue.cc'] and sources_a['riscv/iris_rocket_packets.cc']==sources_b['riscv/iris_rocket_packets.cc']}
    if not all(checks.values()):raise ValueError('Independent scoped source review failed')
    command=['g++','-std=c++20','-O2','-I'+str(ROOT/'timing'),str(ROOT/'timing/empirical_read_overlap_bootstrap_probe_v1.cpp'),str(ROOT/'timing/empirical_cache_v7.cpp'),'-o',str(out/'bootstrap-probe')]
    compiled=subprocess.run(command,capture_output=True);(out/'compile.stdout').write_bytes(compiled.stdout);(out/'compile.stderr').write_bytes(compiled.stderr)
    if compiled.returncode:raise ValueError('Independent probe compilation failed')
    tested=subprocess.run([str(out/'bootstrap-probe')],capture_output=True);(out/'bootstrap.stdout').write_bytes(tested.stdout);(out/'bootstrap.stderr').write_bytes(tested.stderr)
    if tested.returncode:raise ValueError('Independent bootstrap probe failed')
    bootstrap=json.loads(tested.stdout)
    if bootstrap.get('pass')is not True or bootstrap.get('checks')!=2012:raise ValueError('Independent bootstrap probe controls missing')
    metrics=derived['metrics_all'];rows=jsonl(comparison/'regions.jsonl')
    triples=[{k:x[k]for k in ('case_id','hart','trial_id','hardware_cycles','native_cycles','signed_error_percent','actual_model_data_path_features')}
        for x in rows if(x['target'],x['pattern'],x['kind'],x['n'],x['mask'])==('dram','bank0','chase',257,7)]
    paths=[Path(__file__).resolve(),package/'manifest.json',package/'source-inventory.json',fixture,prior,comparison/'report.json',
        *[x/'run.json'for x in(old,off,on)],ROOT/'timing/empirical_cache_v7.cpp',ROOT/'timing/empirical_cache_v7.hpp',ROOT/'timing/empirical_read_overlap_bootstrap_probe_v1.cpp',
        *[after/x for x in expected],* [ROOT/p for p in ('build/memory-routes-current-04c5-ON-qualification-v1/report.json',)]]
    report={'schema':'iris.empirical_read_overlap_independent_causal_review.v1','pass':True,
        'source_review_checks':checks,'fixed_coefficients_equal':True,'source_review_findings':[],
        'actual_regions':2592,'all_independent_goldens_passed':True,'instret_mismatches':metrics['instret_mismatches'],
        'typed_corruption_refusals':22,'OFF_full_prefix_and_readback_byteidentical':True,
        'ON_changed_region_feature_rows':len(changed),'ON_prefix_equal_except_calibration_identity':normalized_equal,
        'ON_complete_prefixes':len(prefix_b),'ON_absolute_counters_unchanged':all(x['start_cycle']==y['start_cycle']and x['end_cycle']==y['end_cycle']for x,y in zip(oldrows,onrows)),
        'ON_metrics':metrics,'matched_worst_family_triples':triples,'independent_bootstrap_probe':bootstrap,
        'assessment':'Scoped policy preserves strict hazards in the reviewed delta, but ON does not alter this actual workload. No runtime timing-fix claim is supported.',
        'unresolved_activation_cause':'The independent API witness proves an ordinary cold/unknown owner can seed an indefinitely self-propagating chain of nonwarm all-L1-hit readers. Actual native activation provenance still needs producer diagnostics; constructor/linkage or other blocker causes are not excluded by unchanged counters.',
        'hardware_policy_proved':False,'timing_accuracy_improved_on_this_workload':False,'parameter_fit_performed':False,'parameters_changed':False,
        'global_heldout_timings_consumed':False,'hardware_contacted':False,'full_2pct_certified':False,'source_image_association_verified':False,
        'normal_guest_exit_verified_by_timed_replay':False,'intentional_post_ROI_debugger_stop':True,
        'input_sha256':{str(p):sha(p)for p in paths},'compile_argv':command}
    report['artifact_sha256']={p.name:sha(p)for p in out.iterdir()if p.is_file()}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'changed_rows':len(changed),'metrics':metrics,'output':str(out)}))


if __name__=='__main__':main()

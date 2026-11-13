#!/usr/bin/env python3
"""Freeze NEW one-global-prepare evaluator; keep all parent proofs unchanged."""
from pathlib import Path
import hashlib
import json
import shutil
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/source-System-global-prepare-component-v1'
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def main():
    OUT.mkdir();inputs={};proofs=[]
    names=['source-global-prepare-resident-parity-v1','source-global-prepare-writeback-parity-v1','saturn-storefront-System-arena-global-check-v1','saturn-storefront-System-writeback-global-check-v1']
    for name in names:
        p=ROOT/'build'/name/'report.json';j=json.loads(p.read_text());assert j['pass']is True
        for key in ['input_sha256','compiled_dependency_sha256']:
            for source,digest in j.get(key,{}).items():assert sha(source)==digest;inputs[source]=digest
        for source,digest in j['output_sha256'].items():assert sha(source)==digest
        inputs[str(p)]=sha(p);proofs.append(dict(path=str(p),sha256=sha(p)));shutil.copytree(p.parent,OUT/'proofs'/name,ignore=shutil.ignore_patterns('old','global','check'))
    failed=ROOT/'build/saturn-storefront-System-global-diagnostic-v2';failure=json.loads((failed/'report.json').read_text());assert failure['pass']is False
    exact='IRIS_FASED_BACKING_EXTERNAL_FENCE_REQUIRED GLOBAL stage=1 tick=5019 AR=1 ARaddr=2147614720 AW=0 AWaddr=0\n';assert(failed/'positive.stderr').read_text()==exact
    shutil.copytree(failed,OUT/'preserved_high_window',ignore=shutil.ignore_patterns('check'));inputs[str(failed/'report.json')]=sha(failed/'report.json')
    base=ROOT/'timing/shuttle_memory_coupled_fixture_v1.hpp';text=base.read_text();inner=text.split('  void evaluate_control(){',1)[1].split('  void step(){',1)[0];assert 'service.prepare()'not in inner
    source_files=['shuttle_memory_coupled_fixture_v1.hpp','saturn_storefront_system_arena_v3.cpp','saturn_storefront_system_writeback_v3.cpp','check_saturn_storefront_system_arena_v3.py','check_saturn_storefront_system_writeback_v3.py','check_source_global_prepare_parity_v1.py','saturn_storefront_system_writeback_global_diagnostic_v2.cpp','check_saturn_storefront_system_writeback_global_diagnostic_v2.py','freeze_source_global_prepare_v1.py']
    anchors=[]
    for name in source_files:
        p=ROOT/'timing'/name;q=OUT/'src/timing'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);inputs[str(p)]=sha(p)
        if name in ['saturn_storefront_system_arena_v3.cpp','saturn_storefront_system_writeback_v3.cpp']:
            body=p.read_text().split('  void evaluate(){',1)[1].split('  void step(){',1)[0];assert body.count('f.service.prepare()')==1 and 'f.evaluate_control()'in body and 'f.evaluate()'not in body
            for i,line in enumerate(p.read_text().splitlines(),1):
                if 'f.service.prepare()'in line:anchors.append(dict(path=str(p),line=i,source=line))
    parents={}
    for name in ['saturn-storefront-System-arena-component-v1','saturn-storefront-System-writeback-component-v1','saturn-storefront-typed-component-v1','fased-write-backing-component-v1']:
        p=ROOT/'build'/name/'manifest.json';m=json.loads(p.read_text());assert m['pass']is True
        for relative,digest in m['artifact_sha256'].items():assert sha(p.parent/relative)==digest
        parents[name]=dict(path=str(p),sha256=sha(p));inputs[str(p)]=sha(p)
    report=dict(schema='iris.source_System_global_prepare_component.v1',**{'pass':True},parents=parents,proofs=proofs,source_anchors=anchors,
       inner_System_LP_evaluator_control_sample_only=True,one_host_ledger_prepare_after_outer_global_convergence=True,all_commits_held_preedge_without_reevaluation=True,
       old_parent_scope_correction='Parent inner evaluator staged ledger at inner convergence. No wrong committed data demonstrated; NEW evaluator prevents transient false refusal and implements the exact global-prepare contract. Parent bytes/proofs remain unchanged.',
       parity=dict(seed=1,resident_trace_bytes=4218056,resident_trace_sha256='8a70e9e68538838cd7819720a7908d739cc2225592dd7b0820780e92bfe9ff97',writeback_trace_bytes=13525648,writeback_trace_sha256='ac956e1ba5960aa7ee0f8ac9319ad32624404aec3268ef9307e7f47602a6af3c',old_observational_stdout_equals_old_frozen_normal=True,new_stdout_cycle_results_and_receipts_equal_old=True),
       fresh_corrected_normal_gates='Both seeds1/17, all resident and writeback byte goldens, four resident and three writeback typed negative controls.',
       high_window_visibility=dict(status='still refused at identical settled global edge/address',exact_diagnostic=exact.strip(),report=str(failed/'report.json'),report_sha256=sha(failed/'report.json'),restriction_not_removed=True),
       producer_scope='Conditional external source request client, circularROB sidecar+ordered release, line serialization for writeback case; not fullVMU/CPU/native initialization history.',
       source_RTL_or_latency_parameters_modified=False,frozen_ledger_policy_relaxed=False,native_System_backend_available=False,
       hardware_contacted=False,protected_performance_labels_consumed=False,parameters_fitted=False,current_native_provider_default_changed=False,source_image_association_verified=False,timing_certified=False,input_sha256=inputs)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');artifacts={str(p.relative_to(OUT)):sha(p)for p in OUT.rglob('*')if p.is_file()};manifest=dict(schema='iris.source_System_global_prepare_capsule.v1',**{'pass':True},report_sha256=sha(OUT/'report.json'),artifact_sha256=artifacts,external_input_sha256=inputs)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(pass_=True,report_sha256=sha(OUT/'report.json'),manifest_sha256=sha(OUT/'manifest.json'),artifacts=len(artifacts))))
if __name__=='__main__':main()

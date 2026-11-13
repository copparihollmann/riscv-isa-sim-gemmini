#!/usr/bin/env python3
"""Freeze the exact FASED target-component SDK, source audit and independent proofs."""
import argparse,hashlib,json,os,shutil,stat
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--checks',type=Path,default=R/'build/fased-service-check-v8');p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('fresh immutable capsule required')
    source=R/'build/fased-service-source-v2';native=R/'build/fased-service-native-v3';clock=R/'build/fased-service-clock-check-v1';audit=R/'build/fased-service-boundary-audit-v1';checks=a.checks.resolve()
    n=read(native/'build.json');c=read(checks/'report.json');k=read(clock/'report.json');b=read(audit/'report.json');s=read(source/'extraction.json')
    assert c['status']==k['status']=='passed' and n['exit_status']==0 and c['source_identity']==n['source_identity']
    assert all(x['passed']for x in c['cases'])and all(x['passed']for x in k['cases'])
    assert c['independent_ledger']['profiles']==100 and c['independent_ledger']['checks']>=4780311 and c['independent_ledger']['peak_read_beats_per_target_edge']==1
    assert k['clock_calendar']['checks']==1799946 and not b['default_full_service_available']
    assert b['candidate_startup_profile']['read_max_requests']is None and b['candidate_startup_profile']['write_max_requests']is None and b['candidate_startup_profile']['relax_functional_model']is None
    assert sha(R/'timing/fased_service.hpp')==sha(native/'sdk/fased_service.hpp')
    files={};checked={};metadata=[]
    def add(path,expected=None):
        path=Path(path).absolute();digest=sha(path)
        if expected is not None and digest!=expected:raise ValueError('changed source input '+str(path))
        files[str(path)]={'sha256':digest,'bytes':path.stat().st_size,'mode':stat.S_IMODE(path.stat().st_mode)}
    def tree(path):
        for q in sorted(Path(path).rglob('*')):
            if q.is_file():add(q)
    def meta(path):
        add(path);x=read(path);metadata.append(str(path))
        for key in ['input_sha256','compiled_dependency_sha256','host_runtime_sha256','RTL_sha256','source_context_sha256']:
            for name,digest in x.get(key,{}).items():
                if not isinstance(digest,str)or len(digest)!=64:continue
                q=Path(name);q=q if q.is_absolute()else R/q
                add(q,digest);checked[str(q)]=digest
        return x
    for q in sorted((R/'timing').glob('fased_service*')):
        if q.is_file():add(q)
    for directory in [source,native,checks,clock,audit,R/'build/fased-service-historical-source-v1']:tree(directory)
    for q in [source/'extraction.json',native/'build.json',checks/'report.json',clock/'report.json',audit/'report.json']:meta(q)
    # Earlier failures are preserved as historical evidence, not silently
    # relabeled as current-byte tests or included in the final positive counts.
    for directory in [R/'build/fased-service-check-v1',R/'build/fased-service-check-v2',R/'build/fased-service-check-v4']:
        tree(directory)
    inventory=Path(s['source_image_observability_inventory']);add(inventory,s['source_image_observability_inventory_sha256'])
    add(s['archived_SV'],s['archived_SV_sha256'])
    out.mkdir();(out/'snapshot').mkdir();(out/'cas').mkdir();artifacts=[]
    for name,item in sorted(files.items()):
        src=Path(name);blob=out/'cas'/(item['sha256']+'-'+format(item['mode'],'o'));target=out/'snapshot'/name.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True)
        if not blob.exists():shutil.copyfile(src,blob);blob.chmod(item['mode']);assert sha(blob)==item['sha256']
        os.link(blob,target);artifacts.append({'original':name,'snapshot':str(target.relative_to(out)),**item})
    report={'schema':'iris.fased_target_component_capsule.v1','status':'passed_archived_target_timing_component','SDK_source_identity':n['source_identity'],'SDK_library_sha256':n['library_sha256'],'SDK_path':str(native/'sdk'),'archived_SV_sha256':s['archived_SV_sha256'],'archived_bitstream_sha256':s['archived_bitstream_sha256'],'archived_driver_sha256':s['archived_driver_sha256'],'repositories':s['repositories'],'source_extraction_sha256':sha(source/'extraction.json'),'boundary_audit_sha256':sha(audit/'report.json'),'independent_transaction_ledger':c['independent_ledger'],'independent_clock_calendar':k['clock_calendar'],'negative_controls':{'wrong_latency_oracle':1,'wrong_clock_period':1,'unknown_physical_input':'exception before advance','oversized_burst':'exception before advance','invalid_parameter_envelope':'exception before model construction','operation_without_committed_reset':'exception before advance','stale_sample_or_duplicate_commit':'exception'},'candidate_startup_profile':b['candidate_startup_profile'],'integration_gaps':b['integration_gaps'],'metadata_checked':metadata,'checked_input_sha256':checked,'artifacts':artifacts,'artifact_count':len(artifacts),'bytes_before_CAS_dedup':sum(x['bytes']for x in artifacts),'snapshot_layout':'absolute paths below snapshot/; CAS hardlinks are internal only','historical_attempts':['v1 compile error: ambiguous nullptr commandArgs overload','v2 exact RTL rejected test request longer than archived eight-beat limit','v4 interleave comparator included raw values before a committed reset; final comparator is post-reset and uses stable owned traffic'],'full_FASED_bridge_modeled':False,'serial_TL_path_modeled':False,'observed_internal_state_or_readiness_injected':False,'default_full_service_available':False,'hardware_contacted':False,'source_image_association_verified':False,'loaded_image_verified':False,'timing_certified':False,'calibration_usable':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'report_sha256':sha(out/'report.json'),'artifact_count':len(artifacts),'checked_inputs':len(checked)}))
if __name__=='__main__':main()

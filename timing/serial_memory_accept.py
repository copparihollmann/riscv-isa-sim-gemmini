#!/usr/bin/env python3
"""Freeze the source-derived serial/Bringup conversion component and scoped proof."""
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
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('fresh immutable capsule required')
    source=R/'build/serial-memory-source-v3';native=R/'build/serial-memory-native-v4';checks=R/'build/serial-memory-check-v5';fased=R/'build/fased-service-native-v3'
    s=read(source/'extraction.json');n=read(native/'build.json');c=read(checks/'report.json');assert n['exit_status']==0 and c['status']=='passed'and c['source_identity']==n['source_identity']
    assert s['module_count']==113 and not s['unresolved_candidate_leaves']and len(s['joined_TL_ports'])==20
    assert all(x['passed']for x in c['cases']);rows=c['source_path_runs'];assert rows[-1]['checks']==528906
    runs=[x for x in rows if 'seed'in x];assert len(runs)==2
    for item in runs:assert item['AR']==36 and item['AW']==16 and item['R']==288 and item['W']==128
    phases=[x['source_virtual_ticks']for x in rows if 'case'in x];assert phases[:4]==phases[4:] and len(phases)==8
    files={};checked={};metadata=[]
    def add(path,expected=None):
        path=Path(path).absolute();digest=sha(path)
        if expected is not None and digest!=expected:raise ValueError('changed source input '+str(path))
        files[str(path)]={'sha256':digest,'bytes':path.stat().st_size,'mode':stat.S_IMODE(path.stat().st_mode)}
    def tree(path,patterns=('*',)):
        for pattern in patterns:
            for q in sorted(Path(path).rglob(pattern)):
                if q.is_file():add(q)
    def meta(path):
        add(path);j=read(path);metadata.append(str(path))
        for key in ['input_sha256','compiled_dependency_sha256','host_runtime_sha256','RTL_sha256']:
            for name,digest in j.get(key,{}).items():
                if not isinstance(digest,str)or len(digest)!=64:continue
                q=Path(name);q=q if q.is_absolute()else R/q;add(q,digest);checked[str(q)]=digest
        return j
    for q in sorted((R/'timing').glob('serial_memory*')):
        if q.is_file():add(q)
    for directory in [source,native,checks]:tree(directory)
    for q in [source/'extraction.json',native/'build.json',checks/'report.json',fased/'build.json']:meta(q)
    for q in (fased/'sdk').iterdir():add(q)
    add(s['archived_SV'],s['archived_SV_sha256']);add(source.parent/'fased-service-source-v2/extraction.json',s['source_extraction_sha256'])
    helper=s['external_blackbox_source'];add(helper['source'],helper['source_sha256']);add(helper['current_source'],helper['current_source_sha256'])
    for q in [R/'build/fased-service-component-v1/report.json',R/'build/fased-service-component-v1-verify/report.json',R/'build/fased-service-boundary-audit-v1/report.json',R/'hardware/manifest.json']:add(q)
    for directory in [R/'build/serial-memory-native-v1',R/'build/serial-memory-check-v1',R/'build/serial-memory-check-v2',R/'build/serial-memory-check-v3']:
        tree(directory,('*.json','*.log','*.stdout','*.stderr'))
    out.mkdir();(out/'snapshot').mkdir();(out/'cas').mkdir();artifacts=[]
    for name,item in sorted(files.items()):
        src=Path(name);blob=out/'cas'/(item['sha256']+'-'+format(item['mode'],'o'));target=out/'snapshot'/name.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True)
        if not blob.exists():shutil.copyfile(src,blob);blob.chmod(item['mode']);assert sha(blob)==item['sha256']
        os.link(blob,target);artifacts.append({'original':name,'snapshot':str(target.relative_to(out)),**item})
    limits=['Only physical source components and the scoped64B transaction fixtures are qualified; no whole-SoC CPU execution/reference replay is claimed.','The qualified reset fixture explicitly masks diagnostic STOP/PRINTF only while both external resets are asserted; source datapath/FIFOs/reset clocks are unmodified. SourceAlways remains default and its first-edge unreset monitor failure is preserved.','Full source four-state knownness and arbitrary unreset/RNG-order invariance remain unproved.','The FASED timing cut uses explicit synthetic30/30/16/16 and independent AXI backing data; host ingress/egress/token service and unmeasured actual runtime limits are not supplied.','Source clock phases are2/1/10; reported inclusive committed phase counts are notCPU counter deltas.','Additional physical clients are exported but idle in this initial test. Narrow/masked request shapes and actual3-hart producer contention remain next gates.','Loaded-image source association, calibration admission and whole-system2% timing remain false.']
    report={'schema':'iris.archived_serial_memory_component_capsule.v1','status':'passed_source_path_component_64B','SDK_source_identity':n['source_identity'],'SDK_library_sha256':n['library_sha256'],'SDK_path':str(native/'sdk'),'FASED_source_identity':c['fased_source_identity'],'FASED_SDK_path':str(fased/'sdk'),'archived_SV_sha256':s['archived_SV_sha256'],'source_extraction_sha256':sha(source/'extraction.json'),'source_repositories':s['source_repositories'],'independent_path_checks':rows,'typed_guard_checks':read(checks/'typed-external-and-phase-guards.stdout'),'negative_controls':c['cases'],'source_clock_periods':[2,1,10],'component_fixture_parameters':c['component_fixture_parameters'],'reset_assertion_policy':c['reset_assertion_policy'],'scope_limits':limits,'checked_input_sha256':checked,'metadata_checked':metadata,'artifacts':artifacts,'artifact_count':len(artifacts),'bytes_before_CAS_dedup':sum(x['bytes']for x in artifacts),'snapshot_layout':'absolute paths under snapshot/; internal CAS hardlinks only','automatic_external_memory_defaults':False,'observed_internal_state_or_readiness_injected':False,'whole_soc_reference_compared':False,'real_CPU_producers':False,'hardware_contacted':False,'source_image_association_verified':False,'loaded_image_verified':False,'whole_soc_timing_certified':False,'calibration_usable':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'report_sha256':sha(out/'report.json'),'artifacts':len(artifacts),'checked_inputs':len(checked)}))
if __name__=='__main__':main()

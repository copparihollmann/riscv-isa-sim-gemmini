#!/usr/bin/env python3
"""Freeze fixed-context composed SDK and its source-qualified parent closures."""
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
    if out.exists():raise ValueError('fresh immutable composed closure required')
    system=R/'build/serial-memory-system-native-v2';context=R/'build/serial-memory-context-sdk-v2';public=R/'build/serial-memory-system-check-v4';life=R/'build/serial-memory-context-check-v4';regress=R/'build/serial-memory-context-regress-v1';low=R/'build/serial-memory-fabric-check-v2'
    sy=read(system/'build.json');pub=read(public/'report.json');lc=read(life/'report.json');rg=read(regress/'report.json');ll=read(low/'report.json');cx=read(context/'report.json')
    assert sy['exit_status']==0 and all(x['status']=='passed'for x in [pub,lc,rg,ll])and pub['source_identity']==sy['source_identity']
    assert lc['lifecycle']['constructor_bad_alloc_injections']==44 and lc['lifecycle']['successful_constructions']==14
    assert rg['byte_identical_qualified_semantic_output']and rg['latency_ledger']['checks']==4780311 and rg['serial_rows'][-1]['checks']==528906
    assert pub['source_runs'][-1]['checks']==28515 and ll['source_runs'][-1]['checks']==42520 and pub['physical_ports']=={'inputs':276,'outputs':1150}
    files={};checked={};metadata=[]
    def add(path,expected=None):
        q=Path(path).absolute();h=sha(q)
        if expected is not None and h!=expected:raise ValueError('changed source input '+str(q))
        files[str(q)]={'sha256':h,'bytes':q.stat().st_size,'mode':stat.S_IMODE(q.stat().st_mode)}
    def tree(path,patterns=('*',)):
        for pattern in patterns:
            for q in sorted(Path(path).rglob(pattern)):
                if q.is_file():add(q)
    def meta(path):
        add(path);j=read(path);metadata.append(str(path))
        for key in ['input_sha256','compiled_dependency_sha256','host_runtime_sha256','required_child_library_sha256','exact_library_sha256']:
            for name,digest in j.get(key,{}).items():
                if not isinstance(digest,str)or len(digest)!=64:continue
                q=Path(name);q=q if q.is_absolute()else R/q;add(q,digest);checked[str(q)]=digest
        return j
    for q in sorted((R/'timing').glob('serial_memory*')):
        if q.is_file():add(q)
    for directory in [system,context,public,life,regress,low]:tree(directory)
    for path in [system/'build.json',context/'report.json',public/'report.json',life/'report.json',regress/'report.json',low/'report.json']:meta(path)
    for name,item in cx['components'].items():
        meta(context/name/'build.json');add(item['base_library'],item['base_library_sha256']);add(item['base_wrapper'],item['base_wrapper_sha256']);add(item['base_build_json'],item['base_build_json_sha256'])
        proof=item['single_host_thread_evidence'];add(proof['model_cpp'],proof['sha256'])
        for member,digest in item['unchanged_object_sha256'].items():add(context/name/'objects'/member,digest)
    for directory in pub['include_directories']:
        for q in Path(directory).glob('*.hpp'):add(q)
    # Child RTL/toolchain closures remain separately immutable and hash-bound.
    # This capsule is self-contained for SDK consumers, host rebuild and tests;
    # it deliberately does not duplicate every child's large RTL build tree.
    parents=[]
    for name in ['memory-fabric-component-v1','serial-memory-component-v1','fased-service-component-v1']:
        directory=R/'build'/name;path=directory/'report.json';j=read(path);add(path)
        for item in j['artifacts']:
            q=directory/item['snapshot'];assert q.is_file()and sha(q)==item['sha256'],item['original'];assert stat.S_IMODE(q.stat().st_mode)==item['mode']
        parents.append({'capsule':str(directory),'report_sha256':sha(path),'artifacts_verified':len(j['artifacts']),'source_scope':j['schema']})
    for directory in [R/'build/serial-memory-system-check-v2',R/'build/serial-memory-context-check-v2',R/'build/serial-memory-context-diagnose-v1']:
        tree(directory,('*.json','*.stdout','*.stderr','*.cpp'))
    out.mkdir();(out/'snapshot').mkdir();(out/'cas').mkdir();artifacts=[]
    for name,item in sorted(files.items()):
        q=Path(name);blob=out/'cas'/(item['sha256']+'-'+format(item['mode'],'o'));target=out/'snapshot'/name.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True)
        if not blob.exists():shutil.copyfile(q,blob);blob.chmod(item['mode']);assert sha(blob)==item['sha256']
        os.link(blob,target);artifacts.append({'original':name,'snapshot':str(target.relative_to(out)),**item})
    report={'schema':'iris.composed_source_memory_system_capsule.v1','status':'passed_fixed_context_source_component_system','System_SDK_source_identity':sy['source_identity'],'System_SDK_library_sha256':sy['library_sha256'],'System_SDK_path':str(system/'sdk'),'child_library_link_order':sy['required_static_libraries_in_link_order'],'child_library_sha256':sy['required_child_library_sha256'],'required_include_directories':sy['required_include_directories'],'FASED_SDK_path':str(context/'fased/sdk'),'FASED_source_identity':cx['components']['fased']['source_identity'],'physical_schema_path':str(public/'physical-port-schema.stdout'),'physical_schema_sha256':pub['physical_schema_sha256'],'physical_ports':pub['physical_ports'],'source_relative_periods':{'rocket':2,'uncore':2,'bringup':1,'serial':10},'public_system_checks':pub['source_runs'],'lower_level_independent_composition':ll['source_runs'],'context_failure_cleanup':lc['lifecycle'],'context_historical_controls':lc['cases'],'preserved_component_regressions':{'FASED':rg['latency_ledger'],'Serial':rg['serial_rows'][-1],'qualified_output_byte_identical':True},'unchanged_model_runtime_objects':{k:len(v['unchanged_object_sha256'])for k,v in cx['components'].items()},'negative_controls':pub['cases']+ll['cases'],'hash_bound_child_source_closures':parents,'SDK_consumer_and_host_source_self_contained':True,'complete_child_RTL_rebuild_requires_bound_parent_closures':True,'source_elaborations':sy['source_elaborations'],'scope_limits':['Real CPU producers, all3-hart traffic and wholeSoC reference replay are not claimed.','Source-components come from two explicitly bound elaborations; no wholeimage equivalence is inferred.','SourceAlways remains default; reference fixtures explicitly mask diagnostic STOP/PRINTF only while both external resets asserted; datapath/FIFOs/source clocks unchanged.','All target model/runtime objects are unchanged; only two host wrappers and a plain-C++ composition wrapper are new.','No FASED parameter/backing defaults in System. Fixtures explicitly use synthetic30/30/16/16.','Full FASED functional ingress/egress/hosttoken ordering and unmeasured runtime settings remain external; overlapping conflicts require a separately qualified policy.','Full internal fourstate knownness and arbitrary unreset/RNG-order invariance remain unproved.','Only scoped64B source-path tests are qualified; narrow/masked shapes and compiler/Zephyr native successor remain separate gates.'],'checked_input_sha256':checked,'metadata_checked':metadata,'artifacts':artifacts,'artifact_count':len(artifacts),'bytes_before_CAS_dedup':sum(x['bytes']for x in artifacts),'snapshot_layout':'absolute paths under snapshot/; CAS hardlinks internal only','hardware_contacted':False,'primary_or_frozen_epochs_changed':False,'source_image_association_verified':False,'loaded_image_verified':False,'timing_certified':False,'calibration_usable':False,'default_external_service_available':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'report_sha256':sha(out/'report.json'),'artifacts':len(artifacts),'checked_inputs':len(checked),'verified_parent_artifacts':sum(x['artifacts_verified']for x in parents)}))
if __name__=='__main__':main()

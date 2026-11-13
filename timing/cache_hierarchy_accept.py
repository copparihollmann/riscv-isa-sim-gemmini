#!/usr/bin/env python3
"""Close the scoped cache SDK proof, preserving explicit undefined-timing refusals."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text())
def record(path):path=Path(path);return {'sha256':sha(path),'bytes':path.stat().st_size,'mode':path.stat().st_mode&0o777}
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--model',type=Path,default=ROOT/'build/cache-hierarchy-native-v5');p.add_argument('--replay',type=Path,default=ROOT/'build/cache-hierarchy-replay-v5');p.add_argument('--output',type=Path,default=ROOT/'build/cache-hierarchy-component-v1');a=p.parse_args();model=a.model.resolve();replay=a.replay.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh cache proof output required')
    native=load(model/'build.json');observer=ROOT/'build/cache-hierarchy-observer-v2';whole=ROOT/'build/cache-hierarchy-rtl-v1';reference=ROOT/'build/cache-hierarchy-reference-v1';source=ROOT/'build/cache-hierarchy-source-v1';unknown=ROOT/'build/cache-hierarchy-unknown-v3';init=ROOT/'build/cache-hierarchy-init-audit-v2';audit=ROOT/'build/cache-hierarchy-audit-v1'
    if native['exit_status']or sha(model/'sdk/libiris_cache_hierarchy.a')!=native['library_sha256']:raise ValueError('SDK identity mismatch')
    if load(whole/'run.json')['status']!='passed_252_architectural_checks':raise ValueError('actual saved-RTL architectural probe failed')
    for name,expected in native['input_sha256'].items():
        if sha(name)!=expected:raise ValueError('native source input changed '+name)
    out.mkdir();(out/'runs').mkdir();commands=[];rows=[]
    def run(name,argv,expected):
        start=time.monotonic()
        with(out/'runs'/(name+'.stdout')).open('wb')as stdout,(out/'runs'/(name+'.stderr')).open('wb')as stderr:q=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=300)
        commands.append(argv);row={'name':name,'argv':argv,'exit_status':q.returncode,'expected_exit_status':expected,'host_seconds':time.monotonic()-start,'stdout':record(out/'runs'/(name+'.stdout')),'stderr':record(out/'runs'/(name+'.stderr'))}
        if q.returncode!=expected:raise ValueError(name+' returned unexpected status; raw evidence preserved')
        rows.append(row);return(out/'runs'/(name+'.stdout')).read_text(),(out/'runs'/(name+'.stderr')).read_text()
    compile=['/usr/bin/g++','-O3','-std=c++20','-I'+str(model/'sdk'),str(ROOT/'timing/cache_hierarchy_check.cpp'),str(model/'sdk/libiris_cache_hierarchy.a'),'-pthread','-latomic','-o',str(out/'check')]
    run('compile-selftest',compile,0);text,_=run('selftest',[str(out/'check')],0);selftest=json.loads(text)
    if selftest['checks']!=10912 or selftest['source_identity']!=native['source_identity']or selftest.get('default_unknown_control_refusal_tested')is not True:raise ValueError('source-policy semantic selftest coverage mismatch')
    trace=whole/'cache-ports.bin.gz';before=sha(trace);positive=[]
    for instance,expected_words in [('rocket2',1528308),('l2',2883998)]:
        text,_=run(instance,[str(replay/'replay'),str(trace),'--instance='+instance],0);result=json.loads(text)
        if result['frames']!=74903 or len(result['instances'])!=1 or result['instances'][0]['compared_words']!=expected_words or result['source_identity']!=native['source_identity']or result['instances'][0]['concretized_unknown_replay_timing']:raise ValueError('whole-SoC component comparison coverage mismatch')
        positive.append(result)
    _,error=run('strict-Shuttle-refusal',[str(replay/'replay'),str(trace)],2)
    if 'IRIS_SHUTTLE_INVALID_REPLAY_COMMAND_UNDEFINED queue=3 slot=0'not in error:raise ValueError('wrong strict undefined timing refusal')
    _,error=run('concrete-Shuttle-not-certified',[str(replay/'replay'),str(trace),'--explore-concrete-reset'],1)
    if 'instance=shuttle1 frame=3804 tb=7607 field=io_req_ready'not in error:raise ValueError('concrete reset failure fingerprint changed; audit required')
    for instance in ('rocket2','l2'):
        _,error=run('wrong-output-'+instance,[str(replay/'replay'),str(trace),'--instance='+instance,'--wrong-output'],1)
        if 'CACHE_BOUNDARY_MISMATCH'not in error:raise ValueError('output corruption was not independently detected')
    metadata=load(observer/'build.json');bytes_per_frame=metadata['frame_words']*8
    with gzip.open(trace,'rb')as stream:prefix=stream.read(bytes_per_frame*4+1)
    broken=out/'truncated-frame.bin.gz'
    with gzip.open(broken,'wb')as stream:stream.write(prefix)
    _,error=run('truncated-frame',[str(replay/'replay'),str(broken),'--instance=rocket2'],2)
    if 'truncated physical cache frame'not in error:raise ValueError('partial frame was not refused')
    transport=out/'truncated-transport.bin.gz';transport.write_bytes(trace.read_bytes()[:-8])
    _,error=run('truncated-transport',[str(replay/'replay'),str(transport),'--instance=rocket2'],2)
    if 'invalid compressed cache trace'not in error:raise ValueError('truncated compressed transport was not refused')
    # The otherwise excluded auxiliary vector-TLB payload is safe to exclude
    # only when its actual request is inactive. A tamper control proves refusal.
    field=next(x for x in metadata['fields']if x['instance']=='rocket2'and x['name']=='io_tlb_port_req_valid')
    auxiliary=out/'active-auxiliary-TLB.bin.gz'
    with gzip.open(trace,'rb')as original,gzip.open(auxiliary,'wb')as changed:
        for frame in range(450):
            data=bytearray(original.read(bytes_per_frame))
            if len(data)!=bytes_per_frame:raise ValueError('short positive trace')
            if frame==400:struct.pack_into('<Q',data,8*(field['word_offset']+1),1)
            changed.write(data)
    _,error=run('active-auxiliary-TLB',[str(replay/'replay'),str(auxiliary),'--instance=rocket2'],2)
    if 'auxiliary vector TLB request is outside scalar replay qualification'not in error:raise ValueError('inactive-payload qualification escaped its declared corpus')
    if sha(trace)!=before:raise ValueError('original trace changed during negative controls')
    # Archive exact local source and evidence. This is a component closure;
    # historical development attempts remain separate and are never relabeled.
    inputs=set((ROOT/'timing').glob('cache_hierarchy*'))
    inputs.update([model/'build.json',model/'cache_hierarchy.generated.cpp',model/'sdk/cache_hierarchy.hpp',model/'sdk/cache_hierarchy_identity.hpp',model/'sdk/libiris_cache_hierarchy.a',model/'cache-hierarchy',model/'benchmark',model/'benchmark.json',model/'linked-runtime.txt',replay/'build.json',replay/'replay',replay/'qualification.json',replay/'cache_hierarchy_replay_map.hpp',reference/'build.json',reference/'cache-ports-readonly.vlt',reference/'model/VTestDriver__ALL.a',reference/'model/VTestDriver___024root.h',reference/'model/VTestDriver.h',reference/'sim_files.f',source/'extraction.json',observer/'build.json',observer/'simulator-cache-boundary',observer/'main.cc',observer/'cache_hierarchy_observer.hpp',whole/'run.json',whole/'stdout',whole/'stderr',whole/'coherent.signature',whole/'cache-ports.bin.gz',whole/'all-harts-coherent.elf',whole/'guest-build.json',unknown/'report.json',unknown/'witness.json',unknown/'witness',unknown/'cache_hierarchy_zero_inputs.inc',unknown/'cache_hierarchy_queue_views.inc',unknown/'stderr',init/'report.json',audit/'audit.json',ROOT/'hardware/memory-paths.json',ROOT/'hardware/manifest.json',ROOT/'build/rtl-verilator/manifest.json',ROOT/'build/rtl-verilator/sim_files.f'])
    for directory in (source/'rtl',reference/'rtl',whole/'guest-inputs',init,audit):inputs.update(p for p in directory.rglob('*')if p.is_file())
    for receipt in [native,load(reference/'build.json'),load(observer/'build.json'),load(replay/'build.json'),load(unknown/'report.json')]:
        inputs.update(Path(name)for key in ('input_sha256','source_sha256','generated_model_sha256','host_link_runtime_sha256')for name in receipt.get(key,{}))
    extract=load(source/'extraction.json');inputs.add(Path(extract['source_capsule']));inputs.update(Path(x)for x in extract['source_files'])
    original_manifest=load(ROOT/'build/rtl-verilator/manifest.json')
    for name in ('source_fir','source_annotations'):inputs.add(Path(original_manifest[name]))
    inputs.add(Path(load(init/'report.json')['archived_generated_sv']['path']))
    closure={}
    for path in sorted(inputs):
        if not path.is_file():raise ValueError('missing closure input '+str(path))
        try:relative=Path('root')/path.relative_to(ROOT)
        except ValueError:relative=Path('external')/path.relative_to('/')
        data=path.read_bytes();target=out/'inputs'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);target.chmod(path.stat().st_mode&0o777)
        closure[str(path)]={'snapshot':str(Path('inputs')/relative),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'mode':path.stat().st_mode&0o777}
        if path.read_bytes()!=data:raise ValueError('input changed during closure capture '+str(path))
    artifacts={str(path.relative_to(out)):record(path)for path in out.rglob('*')if path.is_file()and'inputs'not in path.relative_to(out).parts}
    witness=load(unknown/'witness.json');acceptance=[row['cycles_until_four_accepts']for row in witness['seeds']]
    report={'schema':'iris.cache_hierarchy_component_accept.v1','status':'scoped_controller_proofs_with_explicit_Shuttle_undefined_timing_refusal','SDK_source_identity':native['source_identity'],'SDK_library_sha256':native['library_sha256'],'SDK_driver_sha256':native['binary_sha256'],'source_FIR_sha256':extract['source_fir_sha256'],'unmodified_RTL_modules':len(extract['extracted_files']),'selftest':selftest,'whole_SoC_guest_checks':252,'whole_SoC_components':positive,'physical_words_compared':sum(x['instances'][0]['compared_words']for x in positive),'commands':commands,'runs':rows,'unknown_control':{'witness_report_sha256':sha(unknown/'report.json'),'first_divergent_edge':load(unknown/'report.json')['first_divergent_edge'],'observed_concrete_acceptance_cycles_for_four_stores':sorted(set(acceptance)),'not_an_exhaustive_global_timing_interval':True,'default_policy':'refuse use of unwritten selected replay command before affected edge commits','knownness_bound':'Real accepted enqueues define only their physical RAM slots; dequeue can expose another unwritten slot','FPGA_INIT_attested':False,'initialization_audit_sha256':sha(init/'report.json')},'speed':load(model/'benchmark.json'),'inputs':closure,'artifacts':artifacts,'limitations':['Source-bound controller SDKs are not yet composed with tile arbiters/width/CDC adapters, full NoC, instruction/vector interference, PTW and serial/DRAM service.','Whole-SoC boundary replay supplies only genuine external component pins. It validates component behavior, not closed-loop workload cycle prediction.','Shuttle startup timing depends on an invalid unwritten replay-head command. Concrete seed selection cannot be promoted to a single certified timing count.','The replay knownness guard closes this one source dependency; it does not certify all four-state definedness.','Full ±2% held-out/end-to-end timing accuracy is unproved; no fitting or held-out data supplied model delays.','Saved standalone FIR/native memory lowering is not an attestation of Ethan image build association, FPGA INIT or selected FASED service settings.','Build receipts bind exact tool/source/output bytes. Arbitrary relocation can alter generated path strings and source identity; no bit-reproducible cross-path binary claim.'],'automatic_external_memory_service':False,'observed_internal_state_injected':False,'hardware_contacted':False,'full_RTL_certified':False,'full_model_certified':False,'timing_certified':False,'loaded_image_association_verified':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'checks':selftest['checks'],'physical_words_compared':report['physical_words_compared'],'inputs':len(closure),'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()

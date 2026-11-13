#!/usr/bin/env python3
"""Build only the composed source-peer host wrapper; all child RTL SDKs are frozen."""
import argparse,hashlib,json,shlex,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--serial-sdk',type=Path,default=R/'build/serial-memory-context-sdk-v2/serial/sdk');a=p.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('fresh composed SDK output required')
    memory=R/'build/memory-fabric-coupled-native-v4/sdk';serial=a.serial_sdk.resolve();ctx=R/'build/memory-fabric-context-sdk-v2';headers=[memory,serial,ctx/'cache/sdk',ctx/'noc/sdk',ctx/'adapters/sdk'];libraries=[memory/'libiris_memory_fabric.a',ctx/'cache/sdk/libiris_cache_hierarchy.a',ctx/'noc/sdk/libiris_noc.a',ctx/'adapters/sdk/libiris_memory_adapters.a',serial/'libiris_serial_memory.a']
    capsules=[R/'build/memory-fabric-component-v1/report.json',R/'build/serial-memory-component-v1/report.json'];checked={}
    for q in capsules:
        j=json.loads(q.read_text())
        for lib in libraries:
            matches=[x for x in j['artifacts']if x['original']==str(lib)]
            if matches:assert sha(lib)==matches[0]['sha256'];checked[str(lib)]=matches[0]['sha256']
    serial_receipt=serial.parent/'build.json'
    if str(libraries[-1])not in checked:
        derivative=json.loads(serial_receipt.read_text());assert derivative['RTL_model_and_runtime_objects_unchanged']and derivative['only_replaced_object']=='serial_memory.o';assert sha(libraries[-1])==derivative['library_sha256']
        original=json.loads(capsules[-1].read_text());matches=[x for x in original['artifacts']if x['original']==derivative['base_library']];assert len(matches)==1 and matches[0]['sha256']==derivative['base_library_sha256'];checked[str(libraries[-1])]=derivative['library_sha256']
    assert len(checked)==len(libraries)
    out.mkdir();(out/'sdk').mkdir();shutil.copy2(R/'timing/serial_memory_system.hpp',out/'sdk/serial_memory_system.hpp')
    inputs=[Path(__file__),R/'timing/serial_memory_system.hpp',R/'timing/serial_memory_system.cpp',Path('/usr/bin/g++'),Path('/usr/bin/ar'),serial_receipt,*capsules,*libraries]+[q for d in headers for q in sorted(d.glob('*.hpp'))]
    identity=hashlib.sha256(json.dumps({'input_sha256':{str(q):sha(q)for q in inputs},'configuration':'source-peer compose; actual4bank A/D; outer FASED AXI; explicit4clocks; no externalservice/defaultlatency; no childRTL edits'},sort_keys=True).encode()).hexdigest();(out/'sdk/serial_memory_system_identity.hpp').write_text('#pragma once\n#define IRIS_SERIAL_MEMORY_SYSTEM_SOURCE_ID "'+identity+'"\n')
    commands=[['/usr/bin/g++','-O3','-std=c++20','-MD','-MF',str(out/'wrapper.d'),'-I'+str(out/'sdk'),*['-I'+str(q)for q in headers],'-c',str(R/'timing/serial_memory_system.cpp'),'-o',str(out/'wrapper.o')],['/usr/bin/ar','rcs',str(out/'sdk/libiris_serial_memory_system.a'),str(out/'wrapper.o')]]
    start=time.monotonic();status=0
    with(out/'compile.stdout').open('w')as stdout,(out/'compile.stderr').open('w')as stderr:
        for command in commands:
            status=subprocess.run(command,stdout=stdout,stderr=stderr).returncode
            if status:break
    deps={Path(x)for x in shlex.split((out/'wrapper.d').read_text().replace('\\\n',' ').split(':',1)[1])}if(out/'wrapper.d').exists()else set()
    receipt={'schema':'iris.source_memory_system_host_SDK.v1','exit_status':status,'source_identity':identity,'argv':commands,'input_sha256':{str(q):sha(q)for q in inputs},'compiled_dependency_sha256':{str(q):sha(q)for q in sorted(deps)if q.is_file()},'library_sha256':sha(out/'sdk/libiris_serial_memory_system.a')if not status else None,'required_child_library_sha256':checked,'required_static_libraries_in_link_order':list(map(str,libraries)),'required_include_directories':list(map(str,headers)),'host_seconds':time.monotonic()-start,'added_child_RTL_or_queue_edges':0,'external_memory_service_supplied':False,'default_FASED_parameters_supplied':False,'source_elaborations':'saved standaloneIris FIR cache/fabric +archivedCombined SV externalpath; interface-coupled component, not proved wholeimageequivalence','hardware_contacted':False,'source_image_association_verified':False,'timing_certified':False,'calibration_usable':False}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:receipt[k]for k in ['exit_status','source_identity','library_sha256','host_seconds']}));raise SystemExit(status)
if __name__=='__main__':main()

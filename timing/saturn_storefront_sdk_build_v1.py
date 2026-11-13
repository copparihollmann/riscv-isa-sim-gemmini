#!/usr/bin/env python3
"""Build NEW typed host ownership adapter on frozen raw source objects."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'build/saturn-storefront-component-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    manifest=json.loads((RAW/'manifest.json').read_text());assert manifest['pass']is True
    for name,digest in manifest['artifact_sha256'].items():assert sha(RAW/name)==digest
    ports=json.loads((RAW/'extraction.json').read_text())['ports'];ins=[f for f in ports if f['direction']=='input'and f['name']!='clock'];outs=[f for f in ports if f['direction']=='output']
    source=out/'source';source.mkdir();sdk=out/'sdk';sdk.mkdir()
    h=ROOT/'timing/saturn_storefront_v1.hpp';cpp=ROOT/'timing/saturn_storefront_v1.cpp';shutil.copy2(h,source/h.name);shutil.copy2(cpp,source/cpp.name);shutil.copy2(h,sdk/h.name)
    code=[]
    for name,fields in [('input_catalog',ins),('output_catalog',outs)]:code.append('const std::vector<Field> '+name+'={'+','.join('{"'+f['name']+'",'+str(f['width'])+'}'for f in fields)+'};')
    code.append('void set_raw_inputs(VComputeStorefront&m,std::span<const Input>in){')
    for n,f in enumerate(ins):
        if f['width']<=64:code.append(f'm.{f["name"]}=in[{n}].value.limbs[0];')
        else:
            for w in range((f['width']+31)//32):code.append(f'm.{f["name"]}[{w}]=std::uint32_t(in[{n}].value.limbs[{w//2}]>>{32*(w%2)});')
    code.append('}');code.append('std::vector<Bits>get_raw_outputs(const VComputeStorefront&m){std::vector<Bits>out('+str(len(outs))+');')
    for n,f in enumerate(outs):
        if f['width']<=64:code.append(f'out[{n}].limbs[0]=m.{f["name"]};')
        else:
            for w in range((f['width']+31)//32):code.append(f'out[{n}].limbs[{w//2}]|=std::uint64_t(m.{f["name"]}[{w}])<<{32*(w%2)};')
    code.append('return out;}');generated=source/'saturn_storefront_ports.generated.inc';generated.write_text('\n'.join(code)+'\n')
    cmd=['/usr/bin/g++','-O2','-std=c++20','-Wall','-Wextra','-Werror','-MD','-MF',str(out/'host.d'),'-I'+str(source),'-I'+str(RAW/'sdk'),'-isystem','/scratch/eygao/iris-cy/.conda-env/share/verilator/include','-c',str(source/cpp.name),'-o',str(out/'host.o')]
    with(out/'compile.stdout').open('wb')as so,(out/'compile.stderr').open('wb')as se:rc=subprocess.run(cmd,stdout=so,stderr=se,timeout=120).returncode
    library=sdk/'libiris_saturn_storefront.a';mri='CREATE '+str(library)+'\nADDMOD '+str(out/'host.o')+'\nADDLIB '+str(RAW/'sdk/libiris_compute_storefront.a')+'\nSAVE\nEND\n'
    if rc==0:
        (out/'archive.mri').write_text(mri)
        with(out/'archive.stdout').open('wb')as so,(out/'archive.stderr').open('wb')as se:rc=subprocess.run(['/usr/bin/ar','-M'],input=mri.encode(),stdout=so,stderr=se,timeout=60).returncode
    inputs=[Path(__file__).resolve(),h,cpp,RAW/'manifest.json',RAW/'extraction.json',RAW/'sdk/VComputeStorefront.h',RAW/'sdk/libiris_compute_storefront.a',Path('/usr/bin/g++').resolve(),Path('/usr/bin/ar').resolve()]
    dep={}
    if(out/'host.d').exists():
        for x in shlex.split((out/'host.d').read_text().replace('\\\n',' ').split(':',1)[1]):
            path=Path(x)
            if path.is_file():dep[str(path)]=sha(path)
    report=dict(schema='iris.compute_Saturn_storefront_typed_build.v1',**{'pass':rc==0},exit_status=rc,argv=cmd,archive_mri=mri,input_sha256={str(x):sha(x)for x in inputs},compiled_dependency_sha256=dep,host_seconds=time.monotonic()-start,
      source_RTL_and_runtime_modified=False,raw_source_manifest_sha256=sha(RAW/'manifest.json'),native_backend_available=False,hardware_contacted=False,qualification_completed=False)
    if library.exists():report['library_sha256']=sha(library)
    (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=report['pass'],report_sha256=sha(out/'build.json'))));return rc
if __name__=='__main__':raise SystemExit(main())

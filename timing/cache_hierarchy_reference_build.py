#!/usr/bin/env python3
"""Build a separate whole SoC with read-only visibility of physical cache ports."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'build/rtl-memory-return-path-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,default=ROOT/'build/cache-hierarchy-source-v1');p.add_argument('--output',type=Path,default=ROOT/'build/cache-hierarchy-reference-v1');p.add_argument('--jobs',type=int,default=8);a=p.parse_args()
    out=a.output.resolve();extraction=a.source.resolve()/'extraction.json';j=json.loads(extraction.read_text())
    if out.exists():raise ValueError('fresh whole-SoC cache reference output required')
    original=ROOT/'build/rtl-verilator';manifest=json.loads((original/'manifest.json').read_text())
    out.mkdir();src=out/'rtl';src.mkdir();mapping={};sources=[]
    for line in (original/'sim_files.f').read_text().splitlines():
        path=Path(line);relative=path.relative_to(ROOT);frozen=CAP/relative;path=frozen if frozen.exists()else path
        expected=manifest['sim_source_sha256'][str(ROOT/relative)]
        if sha(path)!=expected:raise ValueError('changed saved whole RTL input '+str(path))
        target=src/path.name
        if target.exists():raise ValueError('source file name collision '+str(target))
        shutil.copyfile(path,target);mapping[str(path)]=expected;sources.append(target)
    for pattern in ('*.h','*.vh'):
        for path in (original/'gen-collateral').glob(pattern):
            target=src/path.name
            if not target.exists():shutil.copyfile(path,target);mapping[str(path)]=sha(path)
    cfg=out/'cache-ports-readonly.vlt'
    cfg.write_text('`verilator_config\n'+''.join('public_flat_rd -module "'+component['top']+'" -var "'+field['name']+'"\n'for component in j['components'].values()for field in component['physical_ports']))
    filelist=out/'sim_files.f';filelist.write_text('\n'.join(map(str,sources))+'\n');model=out/'model'
    command=manifest['verilator_argv'][:]
    replacement={str(original/'sim_files.f'):str(filelist),str(original/'gen-collateral'):str(src),str(original/'model'):str(model),str(original/'simulator-IrisConfig'):str(out/'simulator-generated-main')}
    command=[next((arg.replace(old,new)for old,new in replacement.items()if old in arg),arg)for arg in command]
    command.insert(command.index('-f'),str(cfg));started=time.monotonic()
    with(out/'verilate.log').open('w')as log:q=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    (out/'verilate-command.json').write_text(json.dumps(command,indent=2)+'\n')
    if q.returncode:raise RuntimeError('whole RTL cache port reference Verilation failed')
    compile=['make','-j'+str(a.jobs),'VM_PARALLEL_BUILDS=1','CXX=/usr/bin/g++','LINK=/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++','AR=/usr/bin/ar','RANLIB=/usr/bin/ranlib','PERL=/scratch/eygao/iris-cy/.conda-env/bin/perl','-f','VTestDriver.mk','VTestDriver__ALL.a']
    (out/'compile-command.json').write_text(json.dumps(compile,indent=2)+'\n')
    with(out/'compile.log').open('w')as log:q=subprocess.run(compile,cwd=model,stdout=log,stderr=subprocess.STDOUT)
    receipt={'schema':'iris.whole_rtl_cache_physical_visibility.v1','verilate_argv':command,'compile_argv':compile,'exit_status':q.returncode,'host_seconds':time.monotonic()-started,'source_sha256':mapping,'public_control_sha256':sha(cfg),'extraction_sha256':sha(extraction),'no_RTL_logic_changes':True,'only_physical_ports_readonly':True,'internal_state_injected':False,'hardware_contacted':False,'timing_certified':False,'loaded_image_association_verified':False}
    if not q.returncode:receipt['model_archive_sha256']=sha(model/'VTestDriver__ALL.a')
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'exit_status':q.returncode,'host_seconds':receipt['host_seconds'],'report_sha256':sha(out/'build.json')}))
    if q.returncode:raise SystemExit(1)
if __name__=='__main__':main()

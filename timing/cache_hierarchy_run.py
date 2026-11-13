#!/usr/bin/env python3
"""Run the frozen three-hart coherent guest on local saved RTL, with raw cache pins."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'build/noc-network-component-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--observer',type=Path,default=ROOT/'build/cache-hierarchy-observer-v2');p.add_argument('--output',type=Path,default=ROOT/'build/cache-hierarchy-rtl-v1');p.add_argument('--seed',type=int,default=1);a=p.parse_args();out=a.output.resolve();observer=a.observer.resolve()
    if out.exists():raise ValueError('fresh whole-SoC cache run directory required')
    guest_build=CAP/'build/noc-network-guests-v1/build.json';guest=guest_build.with_name('all-harts-coherent.elf');j=json.loads(guest_build.read_text())
    if sha(guest)!=j['elf_sha256']:raise ValueError('frozen guest ELF identity mismatch')
    build=json.loads((observer/'build.json').read_text());binary=observer/'simulator-cache-boundary'
    if sha(binary)!=build['binary_sha256']:raise ValueError('observer binary identity mismatch')
    out.mkdir();shutil.copyfile(guest,out/'all-harts-coherent.elf');shutil.copyfile(guest_build,out/'guest-build.json');closure={}
    for original,digest in j['input_sha256'].items():
        path=Path(original)
        try:relative=path.relative_to(ROOT);frozen=CAP/relative
        except ValueError:frozen=path;relative=Path('external')/path.name
        candidate=frozen if frozen.exists()else path
        if sha(candidate)!=digest:raise ValueError('guest source closure changed '+str(candidate))
        target=out/'guest-inputs'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(candidate,target);closure[str(relative)]={'source':str(candidate),'sha256':digest}
    argv=[str(binary),'+permissive','+verilator+seed+'+str(a.seed),'+verilator+rand+reset+2','+loadmem=1','+max-cycles=400000','+init_write=0x2000004:0x1','+init_write=0x2000008:0x1','+permissive-off','+signature='+str(out/'coherent.signature'),'+signature-granularity=8',str(out/'all-harts-coherent.elf')]
    (out/'command.json').write_text(json.dumps(argv,indent=2)+'\n');start=time.monotonic()
    with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
        try:q=subprocess.run(argv,cwd=ROOT,env=dict(os.environ,IRIS_CACHE_TRACE=str(out/'cache-ports.bin.gz')),stdout=stdout,stderr=stderr,timeout=600);code=q.returncode;timed=False
        except subprocess.TimeoutExpired:code=None;timed=True
    receipt={'schema':'iris.whole_cache_boundary_run.v1','argv':argv,'exit_status':code,'timed_out':timed,'host_seconds':time.monotonic()-start,'binary_sha256':sha(binary),'observer_build_sha256':sha(observer/'build.json'),'guest_build_sha256':sha(guest_build),'guest_source_closure':closure,'elf_sha256':sha(out/'all-harts-coherent.elf'),'stdout_sha256':sha(out/'stdout'),'stderr_sha256':sha(out/'stderr'),'trace_sha256':sha(out/'cache-ports.bin.gz')if(out/'cache-ports.bin.gz').exists()else None,'signature_sha256':sha(out/'coherent.signature')if(out/'coherent.signature').exists()else None,'source_FIR_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4','loader':'explicit native DRAM preload; existing FESVR PT_LOAD BSS zero-fill; real TSI/IPI/coherent signature transport','hardware_contacted':False,'timing_certified':False,'loaded_image_association_verified':False}
    if not code and not timed and(out/'coherent.signature').exists():
        words=[int(line,16)for line in(out/'coherent.signature').read_text().splitlines()]
        if len(words)!=28 or words[:4]!=[0x4952495350524f42,1,6,0]:raise ValueError('independent coherent signature framing/status failed')
        harts=[]
        for hart in range(3):
            row=words[4+8*hart:12+8*hart]
            if row[3:6]!=[0,0,0]or row[6:]!=[84,1]or row[1]!=row[2]:raise ValueError('three-hart source-computed checks failed')
            harts.append(dict(zip(['stage','actual','expected','cause','pc','tval','checks','done'],row)))
        receipt.update(status='passed_252_architectural_checks',harts=harts,checks=252)
    else:receipt['status']='failed_or_incomplete_saved_rtl_run'
    (out/'run.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'status':receipt['status'],'exit_status':code,'host_seconds':receipt['host_seconds'],'trace_sha256':receipt['trace_sha256'],'report_sha256':sha(out/'run.json')}))
    if receipt['status']!='passed_252_architectural_checks':raise SystemExit(1)
if __name__=='__main__':main()

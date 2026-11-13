#!/usr/bin/env python3
"""Actual saved Iris INT8/OFP8 cell versus independent integer arithmetic."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from hardware.fpcomp_unit.check import closure
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    if a.verify:
        receipt=json.loads((out/'results.json').read_text())
        for name,digest in receipt['artifact_sha256'].items():
            if sha(out/name)!=digest:raise ValueError('changed OPU proof artifact '+name)
        for path,digest in receipt['input_sha256'].items():
            if sha(out/'inputs'/digest)!=digest:raise ValueError('changed archived OPU proof input '+path)
        if json.loads((out/'stdout').read_text())!=receipt['checks']:raise ValueError('OPU check summary differs from raw output')
        for row in receipt['negative_controls']:
            if row['exit_status']==0 or not (out/row['stderr']).read_text().strip():raise ValueError('invalid negative control')
        print(json.dumps({'verified':True,**receipt['checks'],'full_rtl_certified':False}));return
    out.mkdir(parents=True,exist_ok=False)
    oracle=ROOT/'spike/generate_fp8_cases.py';spec=importlib.util.spec_from_file_location('independent_integer_oracle',oracle)
    math=importlib.util.module_from_spec(spec);spec.loader.exec_module(math)
    # Exhaust every input pair/format at RNE, with rotating independent FP32 seeds.
    seeds=[0,0x80000000,0x3f800000,0x3f800001,0xbf800000,0x4b800000,0xcb800000,
           0x7f7fffff,0xff7fffff,1,0x007fffff,0x00800000,0x7fc12345,0x7f812345,0x7f800000,0xff800000]
    corpus=out/'fp8-exhaustive.bin'
    with corpus.open('wb') as stream:
        for fa in (0,1):
            for fb in (0,1):
                for lhs in range(256):
                    for rhs in range(256):
                        acc=seeds[(lhs+rhs*3+fa+fb*2)%len(seeds)]
                        want=math.fma(lhs,rhs,acc,fa,fb,0)
                        stream.write(struct.pack('<12BII',lhs,0,0,0,rhs,0,0,0,fa,fb,1,0,acc,want))
    rtl=ROOT/'build/rtl-verilator';base=json.loads((rtl/'manifest.json').read_text());paths=closure('OuterProductCell',rtl/'gen-collateral')
    for path in paths:
        if sha(path)!=base['sim_source_sha256'].get(str(path)):raise ValueError('changed generated OPU RTL')
    tool=Path('/scratch/eygao/iris-cy/.conda-env');perl=tool/'bin/perl';verilator=tool/'bin/verilator';vroot=tool/'share/verilator'
    cc=Path(shutil.which('g++')).resolve();model=out/'model'
    argv=[perl,verilator,'--cc','--exe','--build','-j','4','--top-module','OuterProductCell','--prefix','VOuterCell',
          '-O3','-Wno-fatal','--Mdir',model,'-CFLAGS','-I'+str(ROOT/'spike'),
          '-MAKEFLAGS','CXX='+str(cc)+' LINK='+str(cc)+' AR=ar RANLIB=ranlib',*paths,HERE/'driver.cc']
    started=time.monotonic();r=subprocess.run(list(map(str,argv)),env=dict(os.environ,VERILATOR_ROOT=str(vroot)),capture_output=True,text=True,timeout=240)
    (out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('cell build failed; see build.log')
    binary=model/'VOuterCell';runstart=time.monotonic();run=subprocess.run([binary,corpus],capture_output=True,text=True,timeout=180)
    (out/'stdout').write_text(run.stdout);(out/'stderr').write_text(run.stderr)
    if run.returncode:raise RuntimeError('OPU cell mismatch; see stderr')
    checks=json.loads(run.stdout)
    if checks['integer_mac_cases']!=262144 or checks['exhaustive_fp8_pairs']!=262144:raise ValueError('coverage count mismatch')
    negatives=[]
    first=bytearray(corpus.read_bytes()[:20]);first[16]^=1
    for name,data in [('wrong-golden',bytes(first)),('truncated-record',corpus.read_bytes()[:19])]:
        bad=out/(name+'.bin');bad.write_bytes(data)
        control=subprocess.run([binary,bad],capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(control.stdout);(out/(name+'.stderr')).write_text(control.stderr)
        if control.returncode==0:raise ValueError('corrupted independent corpus was accepted')
        negatives.append({'name':name,'exit_status':control.returncode,'stderr':name+'.stderr'})
    paths += [Path(__file__),HERE/'driver.cc',oracle,ROOT/'spike/fp8_cases.hpp',ROOT/'hardware/fpcomp_unit/check.py',
              rtl/'manifest.json',ROOT/'hardware/manifest.json',ROOT/'third_party/saturn/src/main/scala/exu/OuterProductUnit.scala',
              ROOT/'third_party/saturn/src/main/scala/exu/fp/fp8ToE5M3.scala',ROOT/'third_party/saturn/src/main/scala/exu/fp/MXFType.scala',
              perl,verilator,vroot/'bin/verilator_bin',cc]
    paths += [path for path in (vroot/'include').rglob('*') if path.is_file() and path.suffix in ('.h','.cpp','.c')]
    ldd=subprocess.check_output(['ldd',binary],text=True);(out/'ldd.txt').write_text(ldd)
    import re
    for path in re.findall(r'(?:=>\s*)?(/[^\s]+)',ldd):
        if Path(path).is_file():paths.append(Path(path))
    inputs={str(path.resolve()):sha(path) for path in paths};(out/'inputs').mkdir()
    for path,digest in inputs.items():
        target=out/'inputs'/digest
        if not target.exists():shutil.copyfile(path,target)
    receipt={'schema':'iris.opu_cell_rtl_proof.v1','checks':checks,'build_argv':list(map(str,argv)),
             'host_build_and_run_seconds':time.monotonic()-started,'host_run_seconds':time.monotonic()-runstart,'negative_controls':negatives,
             'input_sha256':inputs,'source_fir_sha256':base['source_fir_sha256'],
             'audited_source_revisions':{k:v['commit'] for k,v in json.loads((ROOT/'hardware/manifest.json').read_text())['repositories'].items()},
             'oracle':'existing independent integer-only exact FP8 decode/FMA rounded to FP32; host integers for int8/wrapping int32',
             'full_rtl_certified':False,'ethan_image_association_verified':False,'timing_calibrated':False,'hardware_contacted':False,
             'limitations':['One compute-hart OuterProductCell, not instruction decode, full array/sequencer/tile edges, OS ownership or hart2 refusal.',
                            'All16 MRF entries explicitly initialized; no reset-value/unknown-state assertion.',
                            'Legal nonoverlapping same-entry FP8 operations; distinct-entry pipeline batches maintain constant rm.',
                            'No exception-flag output exists on this cell interface.']}
    receipt['artifact_sha256']={str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file()}
    (out/'results.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(checks))


if __name__=='__main__':main()

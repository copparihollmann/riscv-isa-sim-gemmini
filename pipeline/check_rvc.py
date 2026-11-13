#!/usr/bin/env python3
"""Compare the admitted RVC ALU subset against saved-Iris combinational RTL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/pipeline-rvc-source-check')
    parser.add_argument('--verilator',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator'))
    parser.add_argument('--perl',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/bin/perl'))
    args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=True,parents=True)
    (out/'results.json').write_text('{"status":"in_progress","timing_certified":false}\n')
    commands=[]
    tool=args.verilator.resolve();perl=args.perl.resolve()
    source=ROOT/'pipeline/evidence/rvc/RVCExpander.sv';test=ROOT/'pipeline/test_rvc_rtl.cpp'
    for name,argv in [('verilate',[str(perl),str(tool),'--cc','--exe','-Wno-fatal','--top-module','RVCExpander',
                                  '--Mdir',str(out/'obj'),str(source),str(test),'-CFLAGS','-std=c++20 -O2']),
                      ('build',['make','-C',str(out/'obj'),'-f','VRVCExpander.mk','-j8','CXX=g++','LINK=g++','AR=ar'])]:
        result=subprocess.run(argv,capture_output=True,text=True)
        (out/(name+'.log')).write_text(result.stdout+result.stderr)
        commands.append(dict(name=name,argv=argv,exit_status=result.returncode,log_sha256=sha(out/(name+'.log'))))
        if result.returncode:raise RuntimeError(name+' failed: '+result.stderr)
    binary=out/'obj/VRVCExpander'
    result=subprocess.run([str(binary)],capture_output=True,text=True)
    (out/'stdout').write_text(result.stdout);(out/'stderr').write_text(result.stderr)
    if result.returncode:raise RuntimeError('RVC expansion differs from saved RTL: '+result.stderr)
    findings=json.loads(result.stdout)
    if findings['inputs']!=65536 or findings['accepted']!=15899 or len(findings['mnemonics'])!=19:
        raise RuntimeError('admitted RVC corpus changed without source review')
    evidence={}
    definitions=[('shuttle','common/Consts.scala',[[40,44]]),('shuttle','ifu/Frontend.scala',[[278,326]]),
                 ('shuttle','ifu/FetchBuffer.scala',[[16,53],[97,129]]),('shuttle','common/MicroOp.scala',[[42,52]]),
                 ('rocket-chip','rocket/RVC.scala',[[19,43],[47,57],[77,111],[115,150],[218,240]])]
    for repository,name,lines in definitions:
        path=ROOT/'third_party'/repository/'src/main/scala'/name
        revision=subprocess.check_output(['git','-C',str(ROOT/'third_party'/repository),'rev-parse','HEAD'],text=True).strip()
        target=out/'source'/repository/name;target.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(path,target)
        evidence[str(path.relative_to(ROOT))]=dict(repository_sha=revision,sha256=sha(path),snapshot=str(target.relative_to(out)),lines=lines)
    inputs=[ROOT/'pipeline/rvc.hpp',test,source,Path(__file__).resolve(),ROOT/'pipeline/evidence/rvc/saved-rtl-manifest.json']
    saved=json.loads((ROOT/'pipeline/evidence/rvc/saved-rtl-manifest.json').read_text())
    receipt=dict(schema='iris.shuttle.rvc_expansion.v1',status=findings['status'],findings=findings,commands=commands,
                 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs},source_evidence=evidence,
                 simulator_sha256=sha(binary),stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),
                 verilator_sha256=sha(tool),perl_sha256=sha(perl),
                 verilator_version=subprocess.check_output([str(perl),str(tool),'--version'],text=True).strip(),
                 saved_design=saved['saved_design'],source_fir_sha256=saved['source_fir_sha256'],
                 source_build_association_verified=False,matches_ethan_firesim_image=False,
                 all_instruction_semantics_certified=False,timing_certified=False,
                 scope='All65536 low16 inputs classified; exact expansion checked for15899 admitted ALU encodings at four upper-halfword settings. Reserved/non-ALU/CFI/hint boundaries not redefined.')
    (out/'results.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(status=receipt['status'],receipt=str(out/'results.json'),accepted=findings['accepted'])))


if __name__=='__main__':main()

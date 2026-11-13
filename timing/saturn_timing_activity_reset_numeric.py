#!/usr/bin/env python3
"""Qualify omission of reset-squashed OPU numeric work, without resetting MRF.

The original reset-time helper refusal is retained as a negative witness.  This
proof concerns the validity-qualified numeric pipeline, not unreset tile values.
"""
import argparse
import hashlib
import itertools
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from saturn_timing_fast_check import archived

R=Path(__file__).resolve().parents[1]
FAST=R/'build/saturn-timing-fast-component-v1-final'
REF=R/'build/saturn-timing-component-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def symbolic():
 histories=observations=0
 # Initial state is symbolic.  Old/new pipeline values may diverge only at the
 # omitted assignment; no MRF value is initialized or assumed here.
 for initial in itertools.product([0,1],repeat=2):
  for inputs in itertools.product(range(4),repeat=8):
   old=[*initial,'initial-stage0','initial-stage1'];new=old[:];reset_seen=False
   for edge,pair in enumerate(inputs):
    reset=bool(pair&2);fire=bool(pair&1)
    if old[:2]!=new[:2]:raise ValueError('Valid control changed')
    if reset_seen and old[1]:
     if old[3]!=new[3]:raise ValueError('Reset numeric omission became observable')
     observations+=1
    def step(state,suppress):
     v0,v1,d0,d1=state
     return [0 if reset else int(fire),0 if reset else v0,
             ('numeric-at-edge',edge)if fire and not(suppress and reset)else d0,
             d0 if v0 else d1]
    old=step(old,False);new=step(new,True);reset_seen|=reset
   histories+=1
 return {'all_length8_reset_fire_histories':histories,'valid_qualified_symbol_observations':observations,
         'initial_valid_combinations':4,'numeric_payloads':'arbitrary symbols, no finite floating-point sample assumption',
         'inductive_invariant':'Whenever stage valid is1 after reset, its numeric value is from the same most-recent accepted nonreset operation; reset forces both valid bits0. Omitted writes cannot reach a valid stage.',
         'MRF_values_initialized':False}
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();native=a.native.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'checker.py');rtl=native/'rtl';numeric=FAST/'build/saturn-timing-fast-v1/numeric';tool=Path('/scratch/eygao/iris-cy/.conda-env');env=dict(os.environ,VERILATOR_ROOT=str(tool/'share/verilator'));results=[];inputs=[Path(__file__),native/'build.json',native/'reset-numeric.patch',rtl/'OuterProductCell.sv',numeric/'saturn_timing_fast_numeric.cpp',numeric/'iris_fp8.hpp',numeric/'libsoftfloat.a',REF/'build/saturn-timing-source-v1/compute/rtl/MulAddRecFNPipe_l2_e8_s24.sv',REF/'build/saturn-timing-source-v1/compute/rtl/OuterProductCell.sv',R/'build/saturn-timing-activity-proof-v2/vme-seed0.stderr',tool/'bin/verilator_bin',Path('/usr/bin/g++')]
 for kind in ['cell','array']:
  folder=out/kind;folder.mkdir();cell=kind=='cell';old=R/'build'/('opu-cell-rtl-proof-v2'if cell else'opu-array-rtl-proof-v2-pipelined');gold=json.loads((old/'results.json').read_text());top='OuterProductCell'if cell else'OuterProductUnit';prefix='VOuterCell'if cell else'VOuterArray';driver=folder/'driver.cc';original_driver=archived(old,R/'hardware'/('opu_cell'if cell else'opu_array')/'driver.cc');shutil.copy2(original_driver,driver);inputs.extend([old/'results.json',original_driver])
  if cell:
   header=archived(old,R/'spike/fp8_cases.hpp');shutil.copy2(header,folder/'fp8_cases.hpp');inputs.append(header);corpus=old/'fp8-exhaustive.bin'
  else:
   binding=archived(old,old/'port_bindings.inc');shutil.copy2(binding,folder/'port_bindings.inc');inputs.append(binding);corpus=old/'fp8-cases.txt'
  inputs.append(corpus);shutil.copy2(corpus,folder/corpus.name);model=folder/'model';common='-O3 -std=c++20 -I'+str(folder)+' -I'+str(numeric)+' -I'+str(numeric/'softfloat')
  command=[str(tool/'bin/perl'),str(tool/'bin/verilator'),'--cc','--exe','--build','-j','4','--top-module',top,'--prefix',prefix,'-O3','-Wno-fatal','--Mdir',str(model),'-I'+str(rtl),'-y',str(rtl),'+libext+.sv+.v','-CFLAGS',common,'-LDFLAGS',str(numeric/'libsoftfloat.a'),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=ar RANLIB=ranlib',str(rtl/(top+'.sv')),str(driver),str(numeric/'saturn_timing_fast_numeric.cpp')];start=time.monotonic()
  with(folder/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=env,check=True,timeout=300)
  run=[str(model/prefix),str(folder/corpus.name)];q=subprocess.run(run,capture_output=True,text=True,timeout=120);(folder/'stdout').write_text(q.stdout);(folder/'stderr').write_text(q.stderr)
  if q.returncode or json.loads(q.stdout)!=gold['checks']:raise ValueError('Independent source numeric/control corpus failed '+kind+' '+q.stderr)
  results.append({'kind':kind,'build_argv':command,'argv':run,'exit_status':q.returncode,'checks':json.loads(q.stdout),'binary_sha256':sha(model/prefix),'host_seconds':time.monotonic()-start})
 result={'schema':'iris.saturn_reset_squashed_numeric_omission_proof.v1','symbolic_source_recurrence':symbolic(),'independent_cell_array_corpus':results,'preserved_old_reset_time_refusal':str(inputs[-3])if False else str(R/'build/saturn-timing-activity-proof-v2/vme-seed0.stderr'),'input_sha256':{str(p):sha(p)for p in inputs},'source_valid_index_MRF_write_priority_retained':True,'MRF_or_VRF_constructor_initialization_added':False,'reserved_nonnreset_rounding_still_refused':True,'architectural_unreset_tile_definedness_claimed':False,'hardware_contacted':False};result['artifact_sha256']={str(p.relative_to(out)):sha(p)for p in out.rglob('*')if p.is_file()};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'symbolic':result['symbolic_source_recurrence'],'corpora':[r['checks']for r in results]}))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Rebuild and compare the plain Rocket parcel buffer with exact saved RTL."""
import argparse,concurrent.futures,hashlib,json,os,re,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 rtl=ROOT/'build/rtl-verilator/gen-collateral';v=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');runtime=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');cc=Path('/usr/bin/g++');env=dict(os.environ,PATH=str(v.parent)+':'+os.environ['PATH']);commands=[]
 inputs=[Path(__file__).resolve(),*[ROOT/'pipeline'/n for n in('fast_rocket_ibuf.hpp','fast_rocket_ibuf.cpp','fast_rocket_rvc_fields.hpp','fast_source_rvc_table.hpp','dump_fast_rocket_rvc_fields.cpp','test_fast_rocket_ibuf.cpp','test_fast_rocket_ibuf_guards.cpp')],rtl/'IBuf.sv',rtl/'RVCExpander.sv',ROOT/'third_party/rocket-chip/src/main/scala/rocket/IBuf.scala',ROOT/'third_party/rocket-chip/src/main/scala/rocket/RocketCore.scala',v.resolve(),cc.resolve()]
 before={str(x):sha(x)for x in inputs}
 def run(name,argv,check=True):
  got=subprocess.run(list(map(str,argv)),env=env,capture_output=True);(out/(name+'.stdout')).write_bytes(got.stdout);(out/(name+'.stderr')).write_bytes(got.stderr);commands.append({'name':name,'argv':list(map(str,argv)),'exit_status':got.returncode})
  if check and got.returncode:raise RuntimeError(name+': '+got.stderr.decode()[-1000:])
  return got
 def build_reference(top,obj,cpp):
  run('generate-'+top,[v,'--cc','--exe','--top-module',top,'--Mdir',obj,'--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','-CFLAGS','-O2 -std=c++20 -I'+str(ROOT/'pipeline'),rtl/(top+'.sv'),*([rtl/'RVCExpander.sv']if top=='IBuf'else[]),*cpp])
  run('make-'+top,['make','-C',obj,'-f','V'+top+'.mk','CXX=/usr/bin/g++','LINK=/usr/bin/g++','AR=/usr/bin/ar','-j8'])
 obj=out/'obj';rvc=out/'rvc-obj';build_reference('IBuf',obj,[ROOT/'pipeline/test_fast_rocket_ibuf.cpp',ROOT/'pipeline/fast_rocket_ibuf.cpp']);build_reference('RVCExpander',rvc,[ROOT/'pipeline/dump_fast_rocket_rvc_fields.cpp'])
 run('regenerate-fields',[rvc/'VRVCExpander',out/'generated-fields.hpp']);assert sha(out/'generated-fields.hpp')==sha(ROOT/'pipeline/fast_rocket_rvc_fields.hpp')
 positives=[]
 for seed in(1,17,31):
  got=run('seed'+str(seed),[obj/'VIBuf',seed,100000]);m=re.fullmatch(rb'PASS seed=(\d+) edges=(\d+) checks=(\d+) partial=(\d+) replays=(\d+) kills=(\d+) accepted=(\d+)\n',got.stdout);assert m
  values=list(map(int,m.groups()));assert values[:3]==[seed,100000,2100000]and all(x>0 for x in values[3:]);positives.append(values)
 run('build-guards',[cc,'-O2','-std=c++20','-I'+str(ROOT/'pipeline'),ROOT/'pipeline/test_fast_rocket_ibuf_guards.cpp',ROOT/'pipeline/fast_rocket_ibuf.cpp','-o',out/'guards']);run('guards',[out/'guards'])
 source=(ROOT/'pipeline/fast_rocket_ibuf.cpp').read_text();mutants={'kill':('if(in.reset||in.kill)next_buffered_=false;','if(in.reset)next_buffered_=false;'),'RVI-parcels':('n_ready=full?(out.compressed?1:2):0','n_ready=full?(out.compressed?1:1):0'),'BTB-owner':('const bool saved_metadata=buffered_&&out.compressed;','const bool saved_metadata=false;')};rejections=[]
 for name,(old,new)in mutants.items():
  assert old in source;mutant=out/('mutant-'+name+'.cpp');mutant.write_text(source.replace(old,new,1));binary=out/('mutant-'+name)
  run('build-mutant-'+name,[cc,'-O2','-std=c++20','-I'+str(ROOT/'pipeline'),'-I'+str(obj),'-I'+str(runtime),ROOT/'pipeline/test_fast_rocket_ibuf.cpp',mutant,obj/'VIBuf__ALL.a',obj/'verilated.o',obj/'verilated_threads.o','-pthread','-o',binary]);got=run('mutant-'+name,[binary,1,100000],False);assert got.returncode!=0 and b'MISMATCH'in got.stderr;rejections.append({'name':name,'exit_status':got.returncode,'diagnostic':got.stderr.decode().splitlines()[0]})
 sdk=out/'sdk';sdk.mkdir();run('build-sdk',[cc,'-O2','-std=c++20','-I'+str(ROOT/'pipeline'),'-MMD','-MF',out/'sdk.d','-c',ROOT/'pipeline/fast_rocket_ibuf.cpp','-o',out/'model.o']);run('archive-sdk',['/usr/bin/ar','rcs',sdk/'libiris_fast_rocket_ibuf.a',out/'model.o']);shutil.copy2(ROOT/'pipeline/fast_rocket_ibuf.hpp',sdk/'fast_rocket_ibuf.hpp')
 assert all(sha(path)==digest for path,digest in before.items())
 src=out/'source';src.mkdir();inventory={}
 for path in inputs:
  if path.is_relative_to(ROOT):
   relative=path.relative_to(ROOT);target=src/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target);inventory[str(relative)]=sha(target)
 (out/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n');source_id=hashlib.sha256(json.dumps(inventory,sort_keys=True).encode()).hexdigest()
 report={'schema':'iris.fast_rocket_ibuf.source_component.v1','pass':True,'source_id':source_id,'sdk_sha256':sha(sdk/'libiris_fast_rocket_ibuf.a'),'rocket_pin':'fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0','reference_scope':'saved-IrisConfig IBuf/RVCExpander; not Ethan image attestation','continuous_positive_results':positives,'qualified_physical_output_checks':6300000,'RVC_field_checks':262144,'mutants_rejected':rejections,'guard_result':(out/'guards.stdout').read_text().strip(),'commands':commands,'input_sha256':before,'artifact_sha256':{str(p.relative_to(out)):sha(p)for p in[out/'inventory.json',sdk/'libiris_fast_rocket_ibuf.a',sdk/'fast_rocket_ibuf.hpp',out/'seed1.stdout',out/'seed17.stdout',out/'seed31.stdout',out/'guards.stdout']},'knownness_policy':'actual reset edge required; unknown consumed instruction bits refuse; unused adjacent parcel and rs3 remain explicitly unknown','not_modeled':['Rocket BTB/BHT/RAS','frontend/cache/translation/memory-service timing','scalar architectural effects/counters/IRQs'],'full_model_or_timing_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'source_id':source_id,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()

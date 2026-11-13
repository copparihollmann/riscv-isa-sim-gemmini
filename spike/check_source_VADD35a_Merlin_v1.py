#!/usr/bin/env python3
"""Actual OOT→Merlin resolve/run plus matrix-affinity refusals for exact35a."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'integration/merlin/src'),str(ROOT)]
from spike import empirical_provider_source_VADD35a_v1 as P
from merlin.runtime.backends.zephyr_model import MatrixRouting
from merlin.runtime.backends import device_simulator

def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--guest',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();pkg,guest,out=[p.resolve()for p in(a.package,a.guest,a.output)];out.mkdir(exist_ok=False);rows=[];positives=[]
 for key in list(os.environ):
  if key.startswith('IRIS_EMPIRICAL_')or key=='IRIS_FATAL_PCS':os.environ.pop(key)
 os.environ.update(MERLIN_TARGET_PATH=str(ROOT/'integration/iris-mlir'),MERLIN_IRIS_TIMING='empirical',MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING='1');route=MatrixRouting(support_target='iris',unit='saturn_vme',config='IrisConfig')
 inputs={str(p):P.sha(p)for p in[Path(__file__).resolve(),Path(P.__file__).resolve(),Path(device_simulator.__file__),Path(sys.executable),guest,*P.HOST_CONTRACTS]}
 def refuse(name,fn,substring):
  try:fn()
  except device_simulator.DeviceSimulatorError as e:
   P.need(substring in str(e),'Unexpected refusal '+name+': '+str(e));rows.append(dict(name=name,refused=True,reason=str(e)));return
  raise ValueError('Merlin affinity/selection control admitted '+name)
 for profile in P.PROFILES:
  manifest=pkg/profile/'manifest.json';inputs[str(manifest)]=P.sha(manifest);os.environ['MERLIN_IRIS_MODEL_MANIFEST']=str(manifest);d=device_simulator.resolve(route)
  P.need(d['isa_extensions']==P.EXTENSIONS and d['matrix_hart_ids']==[0,1]and d['native_binary_sha256']==P.NATIVE_SHA and all(x not in d['per_hart_isa']['2'].split('_')for x in P.EXTENSIONS),'Actual35a ISA/provenance route')
  f=out/profile;f.mkdir();os.environ['IRIS_EMPIRICAL_FEATURES']=str(f/'features.jsonl');started=time.monotonic();result=device_simulator.run(route,guest,harts=3,active_hart_ids=(0,1),isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',memory=(0x80000000,0x100000000),timeout=90);(f/'stdout').write_bytes(result['stdout']);(f/'stderr').write_bytes(result['stderr']);P.need(result['returncode']==0,'Small actual Merlin native run failed')
  text=result['stdout'].decode();got=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_TIME_SENSITIVITY ')];done=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_TIME_DONE ')];P.need(len(got)==3 and{r['hart']for r in got}=={0,1,2}and all(r['failed']==0 and r['vl']==8 and r['checksum']==280 for r in got)and done==[dict(failed=0)],'Independent24word35 three-hart goldens');P.need(all('--hart-isa='+str(h)+':'+d['per_hart_isa'][str(h)]in result['argv']for h in range(3)),'All3actual perhartISA arguments');P.need(result['simulator']['provenance']['profile']==profile,'Cross-profile provenance')
  positives.append(dict(profile=profile,actual_OOT_Merlin_resolve_and_run=True,normal_exit=True,independent_words=24,all3harts=True,host_seconds=time.monotonic()-started,argv=result['argv'],regions=got,input_sha256=result['execution_input_sha256'],output_sha256={str(p):P.sha(p)for p in f.iterdir()if p.is_file()}))
  args=dict(harts=3,isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',memory=(0x80000000,0x100000000),timeout=1)
  refuse(profile+'-hart2-matrix',lambda:device_simulator.run(route,guest,active_hart_ids=(2,),**args),'without the selected matrix unit')
  refuse(profile+'-implicit-all3-matrix',lambda:device_simulator.run(route,guest,**args),'without the selected matrix unit')
  refuse(profile+'-duplicate-active',lambda:device_simulator.run(route,guest,active_hart_ids=(0,0),**args),'distinct physical harts')
  os.environ.pop('MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING');refuse(profile+'-missing-optin',lambda:device_simulator.resolve(route),'experimental empirical timing');os.environ['MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING']='1'
  os.environ['MERLIN_IRIS_TIMING']='off';refuse(profile+'-timing-off',lambda:device_simulator.resolve(route),'select empirical modeled time');os.environ['MERLIN_IRIS_TIMING']='empirical'
  bad=route.provider().device_simulator(unit='other',config='IrisConfig');P.need(bad['available']is False,'Wrong unit must refuse');rows.append(dict(name=profile+'-wrong-unit',refused=True,reason=bad['reason']))
  P.need(device_simulator.resolve(route)['available']is True,'Clean profile must remain available')
 P.need(all(P.sha(k)==v for k,v in inputs.items()),'Input changed during realAPI gates')
 report=dict(schema='iris.source_VADD35a_real_Merlin_API_gates.v1',**{'pass':True},positive_actual_runs=positives,refusals=rows,hardware_contacted=False,native_fixture_or_core_Merlin_files_changed=False,no_old_adapter_or_receipt_reused=True,input_sha256=inputs);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,actual_runs=2,refusals=len(rows),report_sha256=P.sha(out/'report.json'))))
if __name__=='__main__':main()

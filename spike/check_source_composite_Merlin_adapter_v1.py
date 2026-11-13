#!/usr/bin/env python3
"""Real OOT/Merlin resolver, affinity and immutable-adapter refusal controls."""
import argparse,copy,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'integration/merlin/src'),str(ROOT)]
from spike import empirical_provider_source_composite_merlin_v1 as A
from merlin.runtime.backends.zephyr_model import MatrixRouting
from merlin.runtime.backends import device_simulator

def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();pkg,out=a.package.resolve(),a.output.resolve();out.mkdir(exist_ok=False);P=A.base_module();rows=[];positive=[]
 os.environ.update(MERLIN_TARGET_PATH=str(ROOT/'integration/iris-mlir'),MERLIN_IRIS_TIMING='empirical',MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING='1');route=MatrixRouting(support_target='iris',unit='saturn_vme',config='IrisConfig')
 def refused(name,fn,contains):
  try:fn()
  except device_simulator.DeviceSimulatorError as e:
   assert contains in str(e),(name,str(e));rows.append(dict(name=name,refused=True,reason=str(e)));return
  raise ValueError('Real Merlin control admitted: '+name)
 for profile in A.BASES:
  manifest=pkg/profile/'manifest.json';m=P.document(manifest);os.environ['MERLIN_IRIS_MODEL_MANIFEST']=str(manifest);d=device_simulator.resolve(route)
  assert d['isa_extensions']==A.EXTENSIONS and d['matrix_hart_ids']==[0,1]and all(e not in d['per_hart_isa']['2'].split('_')for e in A.EXTENSIONS)
  positive.append(dict(profile=profile,actual_OOT_resolve=True,base_native_sha256=d['native_binary_sha256'],isa_extensions=d['isa_extensions'],per_hart_isa=d['per_hart_isa']))
  elf=ROOT/'build/hybrid7bd5-selected-merlin-gemm-h1-v1/shipped.elf'
  refused(profile+'-active-hart2',lambda:device_simulator.run(route,elf,harts=3,active_hart_ids=(2,),isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',memory=(0x80000000,0x100000000),timeout=1),'without the selected matrix unit')
  refused(profile+'-implicit-all3-matrix',lambda:device_simulator.run(route,elf,harts=3,isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',memory=(0x80000000,0x100000000),timeout=1),'without the selected matrix unit')
  refused(profile+'-duplicate-active',lambda:device_simulator.run(route,elf,harts=3,active_hart_ids=(0,0),isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',memory=(0x80000000,0x100000000),timeout=1),'distinct physical harts')
  os.environ['MERLIN_IRIS_MODEL_MANIFEST']=str(A.BASES[profile][0]);refused(profile+'-original-v2-gap-control',lambda:device_simulator.resolve(route),'lacks ISA/provenance');os.environ['MERLIN_IRIS_MODEL_MANIFEST']=str(manifest)
  os.environ.pop('MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING');refused(profile+'-missing-optin',lambda:device_simulator.resolve(route),'experimental empirical timing');os.environ['MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING']='1'
  os.environ['MERLIN_IRIS_TIMING']='off';refused(profile+'-timing-off',lambda:device_simulator.resolve(route),'select empirical modeled time');os.environ['MERLIN_IRIS_TIMING']='empirical'
  bad=route.provider().device_simulator(unit='other',config='IrisConfig');assert bad['available']is False;rows.append(dict(name=profile+'-wrong-unit',refused=True,reason=bad['reason']))
  def mutate(name,edit):
   x=copy.deepcopy(m);edit(x);p=out/(profile+'-'+name+'.json');p.write_text(json.dumps(x,indent=2)+'\n');r=A.experimental_empirical_simulator(p);assert r['available']is False,(name,r);rows.append(dict(name=profile+'-'+name,refused=True,reason=r['reason'],manifest=str(p),sha256=P.sha(p)))
  other='source_os'if profile=='source_compute'else'source_compute'
  mutate('wrong-base-SHA',lambda x:x.update(base_manifest_sha256='0'*64))
  mutate('cross-base-profile',lambda x:x.update(base_manifest=str(A.BASES[other][0])))
  mutate('cross-profile',lambda x:x.update(profile=other))
  mutate('cross-fixture',lambda x:x.update(fixture=str(P.PROFILES[other]['fixture'])))
  mutate('wrong-extension',lambda x:x.update(isa_extensions=['zvt32t']))
  mutate('hart2-VME-claim',lambda x:x['per_hart_isa'].update({'2':x['per_hart_isa']['2']+'_zvt32t'}))
  mutate('matrix-hart2',lambda x:x.update(matrix_hart_ids=[0,1,2]))
  mutate('accuracy-escalation',lambda x:x['qualification'].update(accuracy_2percent_certified=True))
  mutate('changed-identity',lambda x:x.update(calibration_identity='other'))
  mutate('remove-base-input',lambda x:x['input_sha256'].pop(str(A.BASES[profile][0])))
  mutate('base-provider-digest',lambda x:x['input_sha256'].update({str(A.BASE_PROVIDER):'0'*64}))
  mutate('remove-OOT-hook',lambda x:x['input_sha256'].pop(str(ROOT/'integration/iris-mlir/simulator.py')))
  mutate('adapter-digest',lambda x:x['input_sha256'].update({str(Path(A.__file__).resolve()):'0'*64}))
  assert device_simulator.resolve(route)['available']is True
 paths=[Path(__file__).resolve(),Path(A.__file__).resolve(),ROOT/'integration/iris-mlir/simulator.py',Path(device_simulator.__file__),ROOT/'integration/merlin/src/merlin/runtime/backends/zephyr_model.py',pkg/'source_compute/manifest.json',pkg/'source_os/manifest.json',Path(sys.executable)]
 report=dict(schema='iris.source_composite_additive_Merlin_adapter_controls.v1',**{'pass':True},positive_real_Merlin_resolves=positive,refusal_count=len(rows),controls=rows,core_Merlin_or_OOT_files_changed=False,native_or_fixture_changed=False,protected_timing_labels_opened=False,input_sha256={str(p):P.sha(p)for p in paths})
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,controls=len(rows),sha256=P.sha(out/'report.json'))))
if __name__=='__main__':main()

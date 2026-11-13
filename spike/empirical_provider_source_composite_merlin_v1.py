"""Additive Merlin ISA/provenance adapter for exact frozen02b4 v2 profiles."""
import copy,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
KIND='source-composite-02b4-Merlin-adapter-v1'
EXTENSIONS=['zvt32t','zvti8i32mm','zvtofp8fmm']
BASE_PROVIDER=ROOT/'spike/empirical_provider_source_composite_v1.py'
BASE_PROVIDER_SHA='11ad2dc9976bf025a3f5e8908dea16488ea63c10e6809c8acfddfe87cbda9905'
BASES={
 'source_compute':(ROOT/'build/C12-source-composite-optional-package-v2/source_compute/manifest.json','8380f5380582cb603b1f6718ad36525690c2f8eca31a8ff0b67d5cfb56df3a9b'),
 'source_os':(ROOT/'build/C12-source-composite-optional-package-v2/source_os/manifest.json','e916f7e6f4d39525cfe227386123fc92a74aa531b486b1ba6acbee833cd22c08')}
HOST_CONTRACTS=[ROOT/'integration/iris-mlir/simulator.py',ROOT/'integration/merlin/src/merlin/runtime/backends/device_simulator.py',ROOT/'integration/merlin/src/merlin/runtime/backends/zephyr_model.py',ROOT/'integration/iris-mlir/matrix_lowering.py',ROOT/'integration/iris-mlir/provider.yaml']

def base_module():
 import hashlib
 if hashlib.sha256(BASE_PROVIDER.read_bytes()).hexdigest()!=BASE_PROVIDER_SHA:raise ValueError('Frozen base provider changed')
 s=importlib.util.spec_from_file_location('frozen_source_composite_base',BASE_PROVIDER);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def verify(manifest):
 p=base_module();path=Path(manifest).resolve();m=p.document(path)
 p.need(m.get('schema')=='iris.empirical_simulator.v1'and m.get('package_kind')==KIND,'Fixed Merlin adapter schema required')
 profile=m.get('profile');p.need(profile in BASES,'Explicit source profile required');base_path,base_sha=BASES[profile]
 p.need(m.get('base_manifest')==str(base_path)and m.get('base_manifest_sha256')==base_sha and p.sha(base_path)==base_sha,'Exact original v2 profile manifest required')
 base=p.document(base_path);b=p.experimental_empirical_simulator(base_path);p.need(b.get('available')is True,'Frozen v2 base refused: '+str(b.get('reason')))
 # Preserve every base claim and launch choice exactly. The adapter changes
 # only provider/package identity and supplies the consumer-required ISA list.
 for key,value in base.items():
  if key not in('model_provider','package_kind','input_sha256'):
   p.need(key in m and json.dumps(m[key],sort_keys=True)==json.dumps(value,sort_keys=True),'Adapter changed base profile field: '+key)
 p.need(m.get('model_provider')==str(Path(__file__).resolve())and m.get('isa_extensions')==EXTENSIONS,'Exact source ISA metadata required')
 inputs=m.get('input_sha256');p.need(isinstance(inputs,dict)and inputs,'Adapter input closure required')
 for name,want in base['input_sha256'].items():p.need(inputs.get(name)==want,'Missing/changed base closure input '+name)
 for name,want in inputs.items():p.checked(inputs,name,want)
 p.checked(inputs,base_path,base_sha);p.checked(inputs,BASE_PROVIDER,BASE_PROVIDER_SHA);p.checked(inputs,Path(__file__).resolve())
 for item in HOST_CONTRACTS:p.checked(inputs,item)
 p.need(m.get('isa_metadata_scope')=='Iris source ISA declarations and actual frozen per-hart positive/refusal gates; not a timing/image certificate','Explicit ISA metadata scope required')
 for h in('0','1'):p.need(all(x in b['per_hart_isa'][h].split('_')for x in EXTENSIONS),'Compute hart lacks declared matrix extension')
 p.need(all(x not in b['per_hart_isa']['2'].split('_')for x in EXTENSIONS)and b['matrix_hart_ids']==[0,1],'Hart2 must remain without VME')
 result=copy.deepcopy(b);result['isa_extensions']=list(EXTENSIONS)
 result['execution_input_sha256']={**result['execution_input_sha256'],**inputs,str(path):p.sha(path)}
 result['provenance']={'adapter_manifest':str(path),'adapter_manifest_sha256':p.sha(path),'adapter_kind':KIND,'isa_metadata_scope':m['isa_metadata_scope'],'base':result['provenance']}
 result['Merlin_device_simulator_adapter']=True
 return result

def experimental_empirical_simulator(manifest):
 try:return verify(manifest)
 except(OSError,ValueError,KeyError,TypeError,AttributeError,IndexError)as e:return dict(available=False,reason='Source-composite Merlin adapter refused: '+str(e),timing_available=False,whole_model_certified=False)

if __name__=='__main__':
 import argparse
 a=argparse.ArgumentParser(__doc__);a.add_argument('--model',type=Path,required=True);x=a.parse_args();r=experimental_empirical_simulator(x.model);print(json.dumps(r,indent=2));raise SystemExit(0 if r['available']else 1)

#!/usr/bin/env python3
"""Build new optional dual-profile descriptors for exact35a source prototype."""
import argparse,hashlib,json,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike import empirical_provider_source_VADD35a_v1 as P

def write(p,value):p.write_text(json.dumps(value,indent=2)+'\n')
def build(output):
 output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False);inputs={}
 def add(path,want=None):
  p=Path(path).absolute();want=want or P.sha(p);P.need(P.sha(p)==want,'Changed package input '+str(p));P.need(str(p)not in inputs or inputs[str(p)]==want,'Conflicting package input');inputs[str(p)]=want
 def gather(obj):
  for name,want in P.evidence_files(obj).items():add(name,want)
 for file,want in P.CORE.values():add(file,want)
 add(*P.ROOT_QA);q=P.document(P.ROOT_QA[0]);P.need(q['pass']is True,'Root closure not available')
 # Validation remains opaque even to this builder. Only digest its exact bytes.
 add(q['validation_report']['path'],q['validation_report']['sha256'])
 for e in q['evidence'].values():add(e['path'],e['sha256'])
 functional=P.document(q['evidence']['functional32']['path']);gather(functional)
 for row in functional['rows']:
  base=Path(q['evidence']['functional32']['path']).parent
  add(base/(row['name']+'.stdout'),row['stdout_sha256']);add(base/(row['name']+'.stderr'),row['stderr_sha256'])
 for key in('five_OS','compiler8','native_finite_closure','native_readiness','compiler8_closure'):
  report=P.document(q['evidence'][key]['path']);gather(report)
  if key=='five_OS':
   for row in report['runs']:
    add(row['child_receipt'],row['child_receipt_sha256']);gather(P.document(row['child_receipt']))
 for gate in P.GATES.values():
  for file,want in gate.values():add(file,want);gather(P.document(file))
 capsule=P.document(P.CAPSULE/'manifest.json');add(P.CAPSULE/'manifest.json',P.CAPSULE_SHA)
 for name,want in capsule['artifact_sha256'].items():add(P.CAPSULE/name,want)
 add(P.CAPSULE/'verification.json')
 inventory=P.document(P.CAPSULE/'native-inventory.json');seen={}
 with tarfile.open(P.CAPSULE/'native-source.tar.gz','r:gz')as archive:
  for member in archive:
   link=(member.issym()and member.name=='spike_dasm/spike_dasm_option_parser.cc'and member.linkname=='../fesvr/option_parser.cc')
   P.need((member.isfile()or link)and member.name in inventory and member.name not in seen and not Path(member.name).is_absolute()and '..'not in Path(member.name).parts,'Unexpected/unsafe source archive member')
   seen[member.name]=hashlib.sha256(archive.extractfile(member).read()).hexdigest()
 P.need(seen==inventory and len(seen)==2142,'Exact2142 source inventory required')
 for name,want in P.document(P.CAPSULE/'compiled-inputs.json').items():add(name,want)
 gather(P.document(P.CAPSULE/'pipeline-build.json'))
 source_closure=output/'source-closure.json';write(source_closure,dict(schema='iris.source_composite_source_snapshot.v1',**{'pass':True},native_sources=len(seen),capsule_manifest_sha256=P.CAPSULE_SHA,native_binary_sha256=P.NATIVE_SHA,UART_sha256=P.UART_SHA,complete_source_image_attestation=False,rebuild_performed=False,scope='Archived exactsource reconstruction plus all declared external build/link/header inputs; no loaded-image claim',input_sha256={k:v for k,v in inputs.items()if k.startswith(str(P.CAPSULE))or k in P.document(P.CAPSULE/'compiled-inputs.json')}));add(source_closure)
 for item in P.HOST_CONTRACTS:add(item)
 for path in[Path(__file__).resolve(),Path(P.__file__).resolve(),ROOT/'spike/run_source_VADD35a_v1.py',ROOT/'spike/empirical_launch_v2.py',ROOT/'iris_model/empirical_run.py',P.ROOT_PYTHON]:add(path)
 for profile,p in P.PROFILES.items():
  add(p['fixture'],p['fixture_sha256'])
 manifests={}
 for profile,p in P.PROFILES.items():
  folder=output/profile;folder.mkdir();m=dict(schema='iris.empirical_simulator.v1',package_kind=P.MODEL_KIND,mode='experimental_source_prototype',profile=profile,calibration_identity=p['identity'],**{k:str(v[0])for k,v in P.CORE.items()},fixture=str(p['fixture']),fixture_sha256=p['fixture_sha256'],binary_sha256=P.CORE['binary'][1],native_binary_sha256=P.NATIVE_SHA,uart_library_sha256=P.UART_SHA,native_device_abi=4,model_provider=str(Path(P.__file__).resolve()),isa_extensions=P.EXTENSIONS,per_hart_isa=P.ISA,memory_regions=P.MEMORY,matrix_hart_ids=[0,1],launch_args=P.launch_args(profile),profile_scope={k:v for k,v in p.items()if k not in('fixture','fixture_sha256','identity')},qualification=P.QUALIFICATION,root_QA_closure=str(P.ROOT_QA[0]),opaque_validation_report=q['validation_report'],own_package_gates={k:str(v[0])for k,v in P.GATES[profile].items()},source_closure=str(source_closure),runtime_environment={k:None for k in('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')},input_sha256=inputs,optional_only=True,current_pointer_changed=False,limits=['Finite source prototype; no blanket2%/physical traffic/full CPU/image association/hart2accuracy claim.','Sourcecompute VADD/OPU/FADD finite contexts may refuse unsupported geometry, new FP flags or active interrupts.','SourceOS disables sourceVADD/sourceOPU and specializedFENCE; compute timing qualification does not transfer.','Successful CPUCOM+1 backend bridge is conservative and unqualified.','Inherited numerical costs remain unchanged; this source epoch is not refitted.','Validation report is byte-bound opaque evidence; this provider does not parse or expose protected timing labels.','Unstripped static RV64 ELF required; isolated automatic fatal handler resolution.','Local absolute paths are intentional; no claim of portable self-contained distribution.'])
  target=folder/'manifest.json';write(target,m);result=P.experimental_empirical_simulator(target);write(folder/'verification.json',dict(schema='iris.optional_source_composite_package_verification.v1',**{'pass':result['available']},profile=profile,manifest_sha256=P.sha(target),checked_inputs=len(inputs),provider_result=result));P.need(result['available'],result.get('reason','Unavailable'));manifests[profile]=dict(path=str(target),sha256=P.sha(target))
 write(output/'package.json',dict(schema='iris.optional_source_composite_dual_profile.v1',**{'pass':True},profiles=manifests,root_QA_closure_sha256=P.ROOT_QA[1],default_changed=False,source_image_attested=False))
 (output/'RUN.txt').write_text('Optional fixed35a source prototype; existing default is unchanged.\n\npython3 spike/run_source_VADD35a_v1.py --package '+str(output)+' --profile source_compute --elf YOUR_UNSTRIPPED_RV64_ELF --output NEW_DIRECTORY --timeout 600\n\nFor actual Zephyr/context control use --profile source_os. It has sourceOPU and specializedFENCE OFF; compute timing qualification does not transfer.\n\nGeneric API: python3 -m iris_model.empirical_run --model '+str(output/'source_compute/manifest.json')+' --elf YOUR_UNSTRIPPED_RV64_ELF --output NEW_DIRECTORY --timeout 600\n\nVerify: python3 spike/empirical_provider_source_VADD35a_v1.py --model '+str(output/'source_compute/manifest.json')+'\n\nNative summary JSON, CSR-feature JSONL, raw stdout/stderr and byte-bound provenance are written to the output directory. Normal exit alone is separate from independent output validation. Finite FADD/OPU scopes may refuse; no blanket timing/physical/image certificate.\n')
 print(json.dumps(manifests));return output
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.output)

#!/usr/bin/env python3
"""Freeze the new isolated opt-in native phase successor; no default publication."""
from pathlib import Path
import difflib,hashlib,json,shlex,shutil,subprocess,tarfile
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 src=R/'pipeline/riscv-isa-sim-warm-load-v2';parent=R/'pipeline/riscv-isa-sim-scalar-L2hit-v2';build=R/'build/warm-load-native-build-v2';out=R/'build/warm-load-phase-frozen-16184afc';out.mkdir(exist_ok=False)
 report=json.loads((build/'pipeline-build.json').read_text());assert sha(build/'spike')==report['binary_sha256']and sha(build/'libsifive_uart.so')==report['uart_sha256']
 original=json.loads((R/'build/warm-load-phase-native-source-v1/parent-source-inventory.json').read_text());assert all(sha(parent/k)==v for k,v in original.items())
 current={str(p.relative_to(src)):sha(p)for p in src.rglob('*')if p.is_file()and'.git'not in p.relative_to(src).parts};changed=[k for k in current if current[k]!=original.get(k)];assert sorted(changed)==['riscv/iris_empirical_features.inc','riscv/iris_empirical_load.inc','riscv/iris_shuttle_issue.cc','riscv/iris_timing_adapter.cc','riscv/iris_timing_adapter.h']
 patch=''.join(''.join(difflib.unified_diff((parent/k).read_text().splitlines(True),(src/k).read_text().splitlines(True),fromfile='a/'+k,tofile='b/'+k))for k in sorted(changed));(out/'warm-load-on-2b8.patch').write_text(patch)
 for n in ['spike','libsifive_uart.so','pipeline-build.json']:shutil.copy2(build/n,out/n)
 (out/'native-inventory.json').write_text(json.dumps(current,indent=2)+'\n')
 with tarfile.open(out/'native-source.tar.gz','w:gz')as t:
  for k in sorted(current):t.add(src/k,arcname=k,recursive=False)
 inputs={str(Path(__file__).resolve()):sha(Path(__file__).resolve()),str(R/'build/scalar-L2hit-outer-frozen-2b8b7cbf/manifest.json'):sha(R/'build/scalar-L2hit-outer-frozen-2b8b7cbf/manifest.json'),**report['input_sha256']}
 for d in build.glob('*.d'):
  for token in shlex.split(d.read_text().replace('\\\n',' ').split(':',1)[1]):
   if token.endswith(':'):continue
   p=Path(token);p=p if p.is_absolute()else build/p
   if p.is_file():inputs[str(p.resolve())]=sha(p)
 (out/'compiled-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 files=['spike','libsifive_uart.so','pipeline-build.json','warm-load-on-2b8.patch','native-inventory.json','native-source.tar.gz','compiled-inputs.json'];m=dict(schema='iris.warm_load_phase_native_capsule.v1',pass_=True,parent_manifest=str(R/'build/scalar-L2hit-outer-frozen-2b8b7cbf/manifest.json'),parent_native_sha256='2b8b7cbff543ddb9cd0916b8723baf6f65b3cf3754efcc238612ba230e754f7c',binary_sha256=sha(out/'spike'),uart_sha256=sha(out/'libsifive_uart.so'),base_commit='72958551566a30f19444bd7e354552824e4d0a98',source=str(src),changed_files=changed,source_frozen=True,native_device_abi=4,new_mode='empirical_load_front dram-L1-hit-Shuttle-COM-forward-v2',default_changed=False,legacy_v1_selector_preserved=True,arithmetic_or_memory_semantics_changed=False,Rocket_phase_changed=False,source_transport_latch_preserved=True,Shuttle_forwardable_at_COM_preedge=True,coherence_late_path_unchanged=True,parameters_refitted=False,reserved_hardware_timings_consumed=False,actual_whole_SoC_cycle_accuracy_qualified=False,artifact_sha256={f:sha(out/f)for f in files},input_sha256={str(R/'build/scalar-L2hit-outer-frozen-2b8b7cbf/manifest.json'):sha(R/'build/scalar-L2hit-outer-frozen-2b8b7cbf/manifest.json'),str(R/'build/warm-load-phase-source-proof-v1/report.json'):sha(R/'build/warm-load-phase-source-proof-v1/report.json')});m['pass']=m.pop('pass_');(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(dict(status='frozen',manifest_sha256=sha(out/'manifest.json'),changed_files=changed,compiled_input_files=len(inputs))))
if __name__=='__main__':main()

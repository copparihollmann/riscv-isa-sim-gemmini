#!/usr/bin/env python3
"""Freeze the exact default-OFF live store plumbing, with unavailable product backend."""
from pathlib import Path
import difflib,hashlib,json,shlex,shutil,subprocess,tarfile,tempfile
R=Path(__file__).resolve().parents[1];P=R/'build/C12-VADD-EG-frozen-35a80496-v2';B=R/'build/spike-VSE-live-boundary-v1';S=R/'pipeline/riscv-isa-sim-VSE-live-boundary-v1';O=R/'build/VSE-live-boundary-frozen-e24c891b-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def unpack_verified(archive,target,inventory):
 with tarfile.open(archive)as t:
  for name,h in inventory.items():
   assert not Path(name).is_absolute()and'..'not in Path(name).parts
   p=target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(name).read());assert sha(p)==h
def main():
 O.mkdir();old=json.loads((P/'native-inventory.json').read_text());inv={n:sha(S/n)for n in sorted(set(old)|{'riscv/iris_vse_live_boundary.inc'})};b=json.loads((B/'pipeline-build.json').read_text());assert b['binary_sha256']==sha(B/'spike')and b['uart_sha256']==sha(B/'libsifive_uart.so');overlay=subprocess.check_output(['git','diff','--binary','HEAD'],cwd=S);assert hashlib.sha256(overlay).hexdigest()==b['source_overlay_sha256'];(O/'source-overlay.patch').write_bytes(overlay);(O/'native-inventory.json').write_text(json.dumps(inv,sort_keys=True,indent=2)+'\n');changed=[n for n,h in inv.items()if old.get(n)!=h]
 with tempfile.TemporaryDirectory(prefix='VSE-live-reconstruct-')as tmp:
  tmp=Path(tmp);base=tmp/'base';base.mkdir();unpack_verified(P/'native-source.tar.gz',base,old);patch=''
  for name in changed:
   before=(base/name).read_text().splitlines(True)if name in old else[];patch+='diff --git a/'+name+' b/'+name+'\n'+('new file mode 100644\n'if name not in old else'')+''.join(difflib.unified_diff(before,(S/name).read_text().splitlines(True),fromfile='a/'+name if name in old else'/dev/null',tofile='b/'+name))
  (O/'VSE-boundary-on-35a.patch').write_text(patch);subprocess.run(['git','apply','--unsafe-paths',str(O/'VSE-boundary-on-35a.patch')],cwd=base,check=True)
  for name,h in inv.items():assert sha(base/name)==h,name
  root=tmp/'git-base';root.mkdir()
  with(tmp/'base.tar').open('wb')as f:subprocess.run(['git','archive',b['base_commit']],cwd=S,stdout=f,check=True)
  with tarfile.open(tmp/'base.tar')as t:t.extractall(root)
  subprocess.run(['git','apply','--unsafe-paths',str(O/'source-overlay.patch')],cwd=root,check=True)
  for name,h in inv.items():assert sha(root/name)==h,name
 with tarfile.open(O/'native-source.tar.gz','w:gz')as t:
  for name in inv:t.add(S/name,arcname=name,recursive=False)
 external={}
 for p in B.glob('*.d'):
  for word in shlex.split(p.read_text().replace('\\\n',' ').split(':',1)[1]):
   if word.endswith(':'):continue
   q=Path(word);q=(q if q.is_absolute()else B/q).resolve()
   if q.is_file()and q.is_relative_to(R)and not q.is_relative_to(S)and not q.is_relative_to(B):external[str(q)]=sha(q)
 assert external[str(R/'timing/vse_live_boundary_v1.hpp')]==sha(R/'timing/vse_live_boundary_v1.hpp');(O/'compiled-inputs.json').write_text(json.dumps(external,sort_keys=True,indent=2)+'\n')
 for n in('spike','libsifive_uart.so','pipeline-build.json','parent-object-reuse.json'):shutil.copy2(B/n,O/n)
 (O/'sdk').mkdir();shutil.copy2(R/'timing/vse_live_boundary_v1.hpp',O/'sdk')
 gates=[R/'build/VSE-live-boundary-directed-v2/report.json',R/'build/VSE-live-boundary-guards-v3/report.json',R/'build/VSE-live-boundary-ABI4-v2/report.json',R/'build/VSE-live-boundary-inflight-IRQ-v1/report.json']
 for p in gates:
  r=json.loads(p.read_text());assert r['pass']is True
  for n,h in r.get('input_sha256',{}).items():assert sha(n)==h,(p,n)
 evidence=[R/'third_party/saturn/src/main/scala/common/ReorderBuffer.scala',R/'third_party/saturn/src/main/scala/mem/Mem.scala',R/'timing/test_vse_live_boundary_v1.cpp',R/'build/VSE-live-boundary-ledger-v1/check',R/'build/VSE-live-boundary-ledger-v1/stdout',R/'benchmarks/vse_live_boundary_v1/build.py',R/'benchmarks/vse_live_boundary_v1/guest.c',R/'timing/prepare_VSE_live_boundary_v1.py',R/'timing/integrate_VSE_live_boundary_v1.py',Path(__file__),*gates]
 contract=dict(schema='iris.VSE_live_boundary_contract.v1',scope='h0/1 VSE32 only, Mbare DRAM, unmasked nf1, aligned16B base, VL1..64, e32 alignedLMUL1/2/4/8, fullyknown address and source, oneactivehart/quietWFIpeers/no enabled pendingIRQ; h2 control unchanged',selector='experimental_vse_boundary SYNTHETIC-DIRECTED-TEST-ONLY-v1 H ACK core_edges',source_System_selector='experimental_vse_boundary source-System-v6-production-v1',source_System_refusal='IRIS_VSE_BOUNDARY_SYSTEM_BACKEND_UNAVAILABLE',product_backend_available=False,available_via_provider=False,default_OFF=True,real_Spike_handler_quarantined_only_at_successful_COM=True,physical_VRF_value_and_knownness_leases='immutable full snapshot; exclusive whole-command CPU/vector drain prevents concurrent producer versions',owners='process epoch1, actual checked COM command, hart/PC/raw; circular tag+private generation; no generation bits on source wires',ordered_contract='circular reserve head; separate two-entry request FIFO; immutable accepted owner until unique response; out-of-order ACK does not free credit; ordered SIFQ/ROB release; final release completes inherited cache owner',inherited_cache='V9 approximate intent-time classification/cost begins before COM; retained owner is completed only at final ordered release. This is not a source System cache history.',CPU_execution='conservative whole-instruction front and whole-command drain; no early VU admission or source COM bridge qualification',service='synthetic-only request progression and explicit ACK delay plus fixed parity jitter3 to exercise OOO; not TL ready/ACK or memory latency',publication='real handler emits zero RAM effects; single-writer flat mirror publishes exact captured value+KnownMask on matching synthetic response; no coherent/architectural visibility-at-ACK proof',unsupported=['production System or physical backend','VLE or pending load versions','masked/strided/indexed/segment stores','unknown source bytes','concurrent CPU/peer memory or VRF producers','active IRQ/preemption/context save or in-flight reset','per-EG CPU/VU timing/ready/FENCE exactness','physical traffic/bandwidth/utilization or 2pct accuracy'])
 (O/'contract.json').write_text(json.dumps(contract,indent=2)+'\n');names=['spike','libsifive_uart.so','pipeline-build.json','parent-object-reuse.json','native-source.tar.gz','native-inventory.json','compiled-inputs.json','VSE-boundary-on-35a.patch','source-overlay.patch','contract.json','sdk/vse_live_boundary_v1.hpp'];m=dict(schema='iris.VSE_live_boundary_native_capsule.v1',**{'pass':True},source=str(S),binary_sha256=sha(O/'spike'),uart_sha256=sha(O/'libsifive_uart.so'),native_device_abi=4,source_frozen=True,parent_manifest_sha256=sha(P/'manifest.json'),base_commit=b['base_commit'],native_sources_reconstructed=len(inv),changed_native_files=changed,external_compiled_inputs=len(external),artifact_sha256={n:sha(O/n)for n in names},evidence_sha256={str(p):sha(p)for p in evidence},test_only=True,product_backend_available=False,default_OFF=True,source_VMU_timing_qualified=False,coherent_visibility_qualified=False,source_image_association=False,hardware_contacted=False,protected_labels_read=False,parameters_fitted=False,existing_providers_or_defaults_changed=False);(O/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');(O/'verification.json').write_text(json.dumps(dict(schema='iris.VSE_live_boundary_source_verification.v1',**{'pass':True},manifest_sha256=sha(O/'manifest.json'),parent_delta_and_full_overlay_independently_reconstructed=True,native_sources=len(inv),compiled_external_inputs=len(external)),indent=2)+'\n');print(json.dumps({'pass':True,'manifest_sha256':sha(O/'manifest.json'),'native_sha256':m['binary_sha256']}))
if __name__=='__main__':main()

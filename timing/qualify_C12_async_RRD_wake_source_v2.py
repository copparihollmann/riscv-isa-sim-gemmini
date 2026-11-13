#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,tarfile,difflib,tempfile,subprocess
R=Path(__file__).resolve().parents[1];P=R/'build/C12-scheduler-diagnostic-frozen-fca1eed2-v1';C=R/'build/C12-async-RRD-wake-frozen-8fcf4e98-v2';S=R/'pipeline/riscv-isa-sim-C12-async-RRD-wake-v2';O=R/'build/C12-async-RRD-wake-source-closure-v2';O.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();old=json.loads((P/'native-inventory.json').read_text());new=json.loads((C/'native-inventory.json').read_text());patch=O/'wake-on-fca1.patch';changed=[n for n,h in new.items()if old.get(n)!=h]
with tempfile.TemporaryDirectory(prefix='async-wake-reconstruct-',dir=R/'build')as temp:
 d=Path(temp)
 with tarfile.open(P/'native-source.tar.gz')as t:
  for m in t.getmembers():
   assert m.name in old and '..'not in Path(m.name).parts and not Path(m.name).is_absolute();p=d/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read());assert sha(p)==old[m.name]
 raw=''
 for n in changed:
  a=(d/n).read_text().splitlines(True)if(d/n).exists()else[];raw+=''.join(difflib.unified_diff(a,(S/n).read_text().splitlines(True),fromfile='a/'+n if a else'/dev/null',tofile='b/'+n))
 patch.write_text(raw);p=subprocess.run(['patch','--batch','-p1','-i',str(patch)],cwd=d,capture_output=True);(O/'patch.stdout').write_bytes(p.stdout);(O/'patch.stderr').write_bytes(p.stderr);assert p.returncode==0
 for n,h in new.items():assert sha(d/n)==sha(S/n)==h,n
for n in('riscv/iris_empirical_async.inc','riscv/iris_empirical_features.inc','riscv/iris_opu_entry_overlap.inc'):assert new[n]==old[n],n
helper=(S/'riscv/iris_async_RRD_wake.inc').read_text();assert 'head->opu_entry'in helper and 'retry<=clock_.now()||retry>=*event'in helper and 'node.physical'in helper and 'blocks_rrd(clock_.now())'in helper and 'clock_.issue'not in helper and 'latency='not in helper
inputs=[Path(__file__),P/'manifest.json',C/'manifest.json',patch,R/'pipeline/store_front_completion_runtime/empirical_engine.cpp',R/'pipeline/empirical_counter_clock.hpp',S/'riscv/processor.cc'];r={'schema':'iris.C12_async_RRD_wake_source_qualification.v2','pass':True,'source_files_reconstructed':len(new),'native_binary_sha256':sha(C/'spike'),'UART_sha256':sha(C/'libsifive_uart.so'),'changed_files':changed,'clean_patch':str(patch),'clean_patch_sha256':sha(patch),'source_parent_fca1_manifest_sha256':sha(P/'manifest.json'),'legacy_admission_function_backend_latencies_intervals_capacities_and_OPU_controller_source_unchanged':True,'no_timing_operations_created':True,'deadline_strictly_future_and_aligned':True,'OPU_entry_and_no_backend_heads_excluded':True,'no_fit_or_clock_scaling':True,'logging_gate_is_successful_MCYCLEROI_only_not_timing':True,'hardware_contacted':False,'full_CPU_timing_certified':False,'input_sha256':{str(p):sha(p)for p in inputs}};(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'pass':True,'source_files':len(new),'report_sha256':sha(O/'report.json'),'patch_sha256':sha(patch)}))

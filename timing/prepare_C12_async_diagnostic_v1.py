#!/usr/bin/env python3
from pathlib import Path
import subprocess,shutil,json,hashlib
R=Path(__file__).resolve().parents[1];P=R/'pipeline/riscv-isa-sim-C12-cpu-diagnostic-v1';S=R/'pipeline/riscv-isa-sim-C12-async-diagnostic-v1';C=R/'build/C12-CPU-diagnostic-frozen-777f31d9-v1';O=R/'build/C12-async-diagnostic-preparation-v1';O.mkdir();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inv=json.loads((C/'native-inventory.json').read_text());subprocess.run(['git','clone','--local','--no-hardlinks','--no-checkout',str(P),str(S)],check=True,stdout=subprocess.DEVNULL);subprocess.run(['git','-C',str(S),'checkout','--detach','72958551566a30f19444bd7e354552824e4d0a98'],check=True,stdout=subprocess.DEVNULL)
for n,h in inv.items():
 assert sha(P/n)==h,n;d=S/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/n,d)
p=S/'riscv/iris_empirical_async.inc';s=p.read_text();a='op.on_complete=[this,hart,actor]{actor->done=true;empirical_async_publish(hart,actor);};';b='''op.on_complete=[this,hart,actor,pc=r.pc,raw=r.uop.raw]{
  if(cpu_trace_){const auto&n=clock_.nodes().at(*actor->backend);std::ostringstream f;f<<"\\"backend_node\\":"<<*actor->backend<<",\\"submitted\\":"<<n.submitted<<",\\"start\\":"<<n.start<<",\\"end\\":"<<n.end<<",\\"latency\\":"<<n.op.latency<<",\\"interval\\":"<<n.op.interval<<",\\"resource\\":"<<std::quoted(n.op.resource);cpu_event(hart,"async_backend_complete",pc,raw,actor->instruction,f.str());}
  actor->done=true;empirical_async_publish(hart,actor);
 };''';assert s.count(a)==1;p.write_text(s.replace(a,b));(O/'preparation.json').write_text(json.dumps({'schema':'iris.C12_async_diagnostic_preparation.v1','pass':True,'source':str(S),'changed_source_sha256':{'riscv/iris_empirical_async.inc':sha(p)},'source_parent_manifest_sha256':sha(C/'manifest.json'),'no_timing_operations_or_modeled_state_changes':True,'default_trace_OFF':True},indent=2)+'\n');print('prepared')

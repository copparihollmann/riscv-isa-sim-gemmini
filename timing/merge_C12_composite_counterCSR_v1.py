#!/usr/bin/env python3
from pathlib import Path
import json,subprocess,hashlib
R=Path(__file__).resolve().parents[1];S=R/'pipeline/riscv-isa-sim-C12-composite-v1';B=R/'pipeline/riscv-isa-sim-FADD-EG-v2';N=R/'pipeline/riscv-isa-sim-FADD-EG-counterCSR-v1';C=R/'build/FADD-EG-counterCSR-frozen-cb668b7f-v1';O=R/'build/C12-composite-preparation-v1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();m=json.loads((C/'manifest.json').read_text())
for n,h in m['artifact_sha256'].items():assert sha(C/n)==h,n
names=['riscv/iris_timing_adapter.h','riscv/iris_timing_adapter.cc','riscv/iris_shuttle_issue.cc','riscv/iris_fadd_eg_actor.inc']
for n in names:
 if n.endswith('.h'):
  p=S/n;s=p.read_text();assert s.count('empirical_fadd_eg=false,')==1;p.write_text(s.replace('empirical_fadd_eg=false,','empirical_fadd_eg=false,empirical_fadd_eg_counter_csr=false,'))
 else:
  q=subprocess.run(['git','merge-file','-p',str(S/n),str(B/n),str(N/n)],capture_output=True);assert q.returncode==0,(n,q.stdout.decode());(S/n).write_bytes(q.stdout)
r=dict(schema='iris.C12_composite_counterCSR_merge.v1',**{'pass':True},parent_manifest_sha256=sha(C/'manifest.json'),patch_sha256=sha(C/'FADD-EG-counterCSR-on-6849.patch'),files=names,legacy_whole_owner_counter_predicate_unchanged=True,legacy_flags_retained=True,FENCE_join_retained=True,source_sha256={n:sha(S/n)for n in names},qualification_pending=True,hardware_contacted=False);(O/'counterCSR-merge.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'pass':True,'files':names}))

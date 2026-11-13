#!/usr/bin/env python3
"""Close standalone FADD retry calendar and defensive MM FENCE entry guard."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1];S=R/'pipeline/riscv-isa-sim-C12-composite-v1';O=R/'build/C12-composite-preparation-v1'
def edit(n,a,b):
 p=S/'riscv'/n;s=p.read_text();assert s.count(a)==1,(n,a);p.write_text(s.replace(a,b))
edit('iris_opu_fence.inc',' if(!profile_.empirical_opu_fence||h>=2)return false;',' if(!profile_.empirical_opu_fence||h>=2)return false;\n if(profile_.empirical_fadd_eg&&fadd_eg_fence_wait(h,fetch))return false;')
edit('iris_timing_adapter.cc','    if(profile_.empirical_opu_fence)for(unsigned h=0;h<2&&h<opu_fence_retry_.size();++h)','    if(profile_.empirical_opu_fence||profile_.empirical_fadd_eg)for(unsigned h=0;h<2&&h<opu_fence_retry_.size();++h)')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();(O/'FADD-FENCE-join-v2.json').write_text(json.dumps(dict(schema='iris.C12_composite_FADD_FENCE_join.v2',scope='ordinary FENCE generic plus MM-specialized; standalone FADD with OPU FENCE OFF also calendars final-write next-edge retry',pending_and_full_controller_veto=True,preedge_final_write_busy_until_following_edge=True,no_new_write_or_retire_event=True,hardware_contacted=False,prior_join_receipt_sha256=sha(O/'FADD-FENCE-join.json'),source_sha256={n:sha(S/'riscv'/n)for n in ['iris_timing_adapter.h','iris_timing_adapter.cc','iris_fadd_eg_actor.inc','iris_opu_fence.inc']}),indent=2)+'\n')

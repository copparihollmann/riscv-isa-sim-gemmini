#!/usr/bin/env python3
"""New source epoch adds retired counter records and FENCE admission receipts."""
from pathlib import Path
import hashlib,json,subprocess,shutil,os
R=Path(__file__).resolve().parents[1];C=R/'build/C12-source-composite-frozen-cb21e2d6-v1';P=R/'pipeline/riscv-isa-sim-C12-composite-v1';S=R/'pipeline/riscv-isa-sim-C12-composite-v2';B=R/'build/spike-C12-composite-v2';PB=R/'build/spike-C12-composite-v1';O=R/'build/C12-composite-preparation-v2';O.mkdir();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inv=json.loads((C/'native-inventory.json').read_text());subprocess.run(['git','clone','--local','--no-hardlinks','--no-checkout',str(P),str(S)],check=True,stdout=subprocess.DEVNULL);subprocess.run(['git','-C',str(S),'checkout','--detach','72958551566a30f19444bd7e354552824e4d0a98'],check=True,stdout=subprocess.DEVNULL)
for n,h in inv.items():
 assert sha(P/n)==h,n;d=S/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/n,d)
old=R/'pipeline/riscv-isa-sim-FADD-EG-counterCSR-v1/riscv/iris_counter_observations.cc';new=R/'pipeline/riscv-isa-sim-FADD-EG-counterCSR-v2/riscv/iris_counter_observations.cc';q=subprocess.run(['git','merge-file','-p',str(S/'riscv/iris_counter_observations.cc'),str(old),str(new)],capture_output=True);assert q.returncode==0;qfile=S/'riscv/iris_counter_observations.cc';qfile.write_bytes(q.stdout)
p=S/'riscv/iris_timing_adapter.cc';s=p.read_text();needle='  pending_[hart] = Pending{pc, fetch, {},profile_.empirical?empirical_feature(hart,fetch):Feature{}}; blocked_[hart] = true;';assert s.count(needle)==1
record='''  if(profile_.empirical_fadd_eg&&hart<2&&async_trace_&&empirical_instruction.length()==4&&(uint32_t(empirical_instruction.bits())&0x707f)==0x000f&&fadd_eg_last_edge_[hart])*async_trace_<<"{\\"event\\":\\"fadd_EG_fence_admit\\",\\"hart\\":"<<hart<<",\\"pc\\":"<<pc<<",\\"raw\\":"<<uint32_t(empirical_instruction.bits())<<",\\"cycle\\":"<<clock_.now()<<",\\"last_controller_edge\\":"<<*fadd_eg_last_edge_[hart]*profile_.harts[hart].divider<<",\\"last_preedge_busy\\":"<<(fadd_eg_prebusy_[hart]?"true":"false")<<",\\"pending\\":"<<fadd_eg_pending_[hart].size()<<",\\"controller_empty\\":"<<(fadd_eg_queues_[hart].empty()?"true":"false")<<"}\\n";\n'''
p.write_text(s.replace(needle,record+needle));subprocess.run(['git','-C',str(S),'add','-N','--',*sorted(inv)],check=True)
shutil.copytree(PB,B,symlinks=True)
for p in [B/'Makefile',B/'config.status',*B.glob('*.d')]:
 if not p.is_file():continue
 st=p.stat();text=p.read_text().replace(str(P),str(S)).replace(str(PB),str(B));p.write_text(text);os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
for n in('riscv','fesvr','fdt'):
 p=B/'sdk'/n
 if p.is_symlink():p.unlink();p.symlink_to(S/n)
(B/'parent-object-reuse.json').write_text(json.dumps(dict(parent_build=str(PB),parent_manifest_sha256=sha(C/'manifest.json'),object_sha256={str(p.relative_to(PB)):sha(p)for p in PB.glob('*.o')},new_clean_build=False),indent=2)+'\n')
(O/'preparation.json').write_text(json.dumps(dict(schema='iris.C12_composite_logging_epoch.v2',**{'pass':True},parent_manifest_sha256=sha(C/'manifest.json'),counterCSR_final_manifest_sha256=sha(R/'build/FADD-EG-counterCSR-frozen-8a8cf119-v2/manifest.json'),no_admission_timing_numeric_or_policy_changes=True,logging_only=['successful retired mcycle/minstret event','actual ordinaryFENCE admission receipt after eligibility checks'],source=str(S),changed_files=[n for n,h in inv.items()if sha(S/n)!=h],hardware_contacted=False),indent=2)+'\n');print(json.dumps({'pass':True,'source':str(S)}))

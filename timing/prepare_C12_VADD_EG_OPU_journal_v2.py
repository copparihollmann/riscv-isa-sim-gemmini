#!/usr/bin/env python3
"""Logging-only OPU COM/K-write successor; all source timings stay unchanged."""
from pathlib import Path
import hashlib,json,shutil,subprocess,os
R=Path(__file__).resolve().parents[1];P=R/'pipeline/riscv-isa-sim-C12-VADD-EG-v1';C=R/'build/C12-VADD-EG-frozen-3a5f5857-v1';S=R/'pipeline/riscv-isa-sim-C12-VADD-EG-v2';PB=R/'build/spike-C12-VADD-EG-v1';B=R/'build/spike-C12-VADD-EG-v2';O=R/'build/C12-VADD-EG-preparation-v2';O.mkdir();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inv=json.loads((C/'native-inventory.json').read_text());subprocess.run(['git','clone','--local','--no-hardlinks','--no-checkout',str(P),str(S)],check=True,stdout=subprocess.DEVNULL);subprocess.run(['git','-C',str(S),'checkout','--detach','72958551566a30f19444bd7e354552824e4d0a98'],check=True,stdout=subprocess.DEVNULL)
for n,h in inv.items():
 assert sha(P/n)==h,n;p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/n,p)
p=S/'riscv/iris_opu_entry_overlap.inc';s=p.read_text();needle=' if(clock_.now()!=a->com_cycle)throw std::logic_error("IRIS_OPU_QUEUE_COM_PHASE_CHANGED");\n opu_start_clock(h);';assert s.count(needle)==1
record=''' if(async_trace_){
  const auto&r=pure_[h].instructions.at(a->instruction);const auto i=r.fetch.insn;const uint32_t raw=uint32_t(i.bits());const unsigned rd=(raw>>7)&31;
  const bool fp=(raw&MASK_VTFMM_TVV)==MATCH_VTFMM_TVV||(raw&MASK_VTFMM_ALT_TVV)==MATCH_VTFMM_ALT_TVV;
  const bool signedA=(raw&MASK_VTMMS_TVV)==MATCH_VTMMS_TVV;
  *async_trace_<<"{\\"event\\":\\"opu_functional_COM\\",\\"hart\\":"<<h<<",\\"instruction\\":"<<a->instruction<<",\\"pc\\":"<<r.pc<<",\\"raw\\":"<<raw<<",\\"cycle\\":"<<clock_.now()<<",\\"geometry_authority\\":\\"checked_architectural_COM\\",\\"kind\\":\\"matrix_multiply\\",\\"family\\":"<<std::quoted(fp?"vme.fp8":"vme.int8")<<",\\"TM\\":"<<v.tm<<",\\"TN\\":"<<v.tn()<<",\\"TK\\":"<<v.tk<<",\\"SEW\\":"<<v.vsew<<",\\"widen\\":"<<v.widen<<",\\"altfmt\\":"<<(v.altfmt?"true":"false")<<",\\"tile\\":"<<a->opu_command.tile<<",\\"destination_encoding\\":"<<rd<<",\\"tile_accessor_td\\":"<<((rd>>1)&12)<<",\\"vs1\\":"<<((raw>>15)&31)<<",\\"vs2\\":"<<((raw>>20)&31)<<",\\"A_operand_register\\":"<<((raw>>20)&31)<<",\\"B_operand_register\\":"<<((raw>>15)&31)<<",\\"controller_TM\\":"<<a->opu_command.tm<<",\\"controller_TN\\":"<<a->opu_command.tn<<",\\"controller_TK\\":"<<a->opu_command.tk<<",\\"backend_available_cycle\\":"<<a->opu_available*profile_.harts[h].divider<<",\\"CPU_COMplus1_bridge_qualified\\":false";
  if(fp)*async_trace_<<",\\"format_A\\":"<<std::quoted((rd&1)?"E5M2":"E4M3")<<",\\"format_B\\":"<<std::quoted(v.altfmt?"E5M2":"E4M3");
  else *async_trace_<<",\\"signed_A\\":"<<(signedA?"true":"false")<<",\\"signed_B\\":"<<(v.altfmt?"true":"false");
  *async_trace_<<"}\\n";
 }
'''
s=s.replace(needle,needle.replace(' opu_start_clock(h);',record+' opu_start_clock(h);'))
old='write.on_complete=[this,h,a,offsets=std::move(offsets),pc=a->opu_pc,macs=m.macs,last_k=m.last_k,k=m.k_index]{opu_write(h,a,offsets,last_k,k);';assert s.count(old)==1
new='''write.on_complete=[this,h,a,offsets=std::move(offsets),pc=a->opu_pc,macs=m.macs,last_k=m.last_k,k=m.k_index,entry=m.entry]{opu_write(h,a,offsets,last_k,k);if(async_trace_)*async_trace_<<"{\\"event\\":\\"opu_K_write_owner\\",\\"hart\\":"<<h<<",\\"instruction\\":"<<a->instruction<<",\\"pc\\":"<<pc<<",\\"cycle\\":"<<clock_.now()<<",\\"entry\\":"<<entry<<",\\"k\\":"<<k<<",\\"last_k\\":"<<(last_k?"true":"false")<<",\\"cells\\":"<<offsets.size()<<",\\"macs\\":"<<macs<<",\\"projected_MRF_published\\":"<<(last_k?"true":"false")<<"}\\n";'''
s=s.replace(old,new);p.write_text(s);subprocess.run(['git','-C',str(S),'add','-N','--',*sorted(inv)],check=True)
shutil.copytree(PB,B,symlinks=True)
for p in [B/'Makefile',B/'config.status',*B.glob('*.d')]:
 if p.is_file():
  st=p.stat();p.write_text(p.read_text().replace(str(P),str(S)).replace(str(PB),str(B)));os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
for n in('riscv','fesvr','fdt'):
 p=B/'sdk'/n
 if p.is_symlink():p.unlink();p.symlink_to(S/n)
(B/'parent-object-reuse.json').write_text(json.dumps(dict(parent_build=str(PB),parent_manifest_sha256=sha(C/'manifest.json'),object_sha256={str(p.relative_to(PB)):sha(p)for p in PB.glob('*.o')},new_clean_build=False),indent=2)+'\n')
(O/'preparation.json').write_text(json.dumps(dict(schema='iris.C12_VADD_EG_OPU_journal_preparation.v2',parent_manifest_sha256=sha(C/'manifest.json'),changed_source=['riscv/iris_opu_entry_overlap.inc'],logging_only=True,no_timing_or_numeric_policy_change=True,actual_COM_kind_scope='finite sourceMM only; genericTMOVE journal remains unqualified/omitted',source=str(S),hardware_or_labels_consumed=False),indent=2)+'\n');print('prepared')

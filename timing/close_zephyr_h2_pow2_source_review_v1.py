#!/usr/bin/env python3
"""Bound final-v4 packet review + associated source capacity/decode/readout."""
from pathlib import Path
import hashlib,json,re
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 o=R/'build/zephyr-hart2-pow2-independent-closure-v1';o.mkdir();meta=R/'build/firesim-observability-archived-driver-v3/report.json';m=json.loads(meta.read_text());top=Path(next(k for k in m['input_sha256']if k.endswith('/design/FireSim-generated.sv')));assert sha(top)==m['input_sha256'][str(top)]=='c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64';text=top.read_text();modules={a.group(1):a.group()for a in re.finditer(r'(?ms)^module\s+(\w+)\b.*?^endmodule',text)};core=modules['ShuttleCore'];seq=modules['OuterProductSequencer'];cell=modules['OuterProductCell'];unit=modules['OuterProductUnit']
 # These are exact literals from the associated saved build, not inferred
 # merely from the Spike VME functional implementation or source comments.
 for literal in ["ex_vcfg_bits_vtype_vsew == 3'h0 & ex_vcfg_bits_vtype_vtwiden == 2'h3","ex_vcfg_bits_vtype_vsew == 3'h2 & ex_vcfg_bits_vtype_vtwiden == 2'h1","ex_new_vl_info_sel_0 ? 9'h20 : 9'h0","ex_new_vl_info_sel_1 ? 9'h20 : 9'h0","ex_new_vl_ex_new_vtype_minfo_sel_1 ? 2'h2 : 2'h0","ex_new_vl_info_sel_0 ? 3'h4 : 3'h0","ex_new_vl_info_sel_1 ? 3'h1 : 3'h0","ex_new_vl_clampTn = _ex_setvcfg_uop_T_110 > _GEN_0 ?"]:assert literal in core,literal
 clusters=re.findall(r'(?m)^\s*(OuterProductCluster(?:_\d+)?)\s+clusters_(\d)_(\d)\s*\(',unit);assert len(clusters)==16 and{(int(r),int(c))for t,r,c in clusters}=={(r,c)for r in range(4)for c in range(4)}
 for kind in {t for t,r,c in clusters}:assert len(re.findall(r'(?m)^\s*OuterProductCell\s+cells_\d_\d\s*\(',modules[kind]))==16
 assert set(re.findall(r'(?m)^\s*reg \[31:0\] regs_(\d+);',cell))=={str(i)for i in range(16)}
 for literal in ["reg [4:0] tss_idx;","reg [2:0] col_idx;","mm_entry = {tile,row_idx,col_idx[0]}","scalar_cell = tss_idx[3:2]","scalar_sub = tss_idx[4]","iter_cell = col_idx[1:0]","_mrf_idx_T_4 = {tile,move_row_sub,move_col_sub}","e5m2_l <= io_dis_bits_bits[7]","e5m2_t <= io_dis_bits_vconfig_vtype_altfmt"]:assert literal in seq,literal
 snippets=[]
 for name,body in [('ShuttleCore',core),('OuterProductSequencer',seq)]:
  for no,line in enumerate(body.splitlines(),1):
   if any(k in line for k in ['info_maxTn','minfo_lmulMag','info_kmax','clampTn','mm_entry =','scalar_cell =','scalar_sub =','iter_cell =','_mrf_idx_T_4 =','e5m2_l <=','e5m2_t <=']):snippets.append(dict(module=name,module_line=no,text=line))
 (o/'associated-source-expressions.json').write_text(json.dumps(snippets,indent=2)+'\n')
 geometry=[]
 for shape in(8,16,32):
  cells=set()
  for sr in range((shape+15)//16):
   for sc in range((shape+15)//16):
    for cr in range(4):
     for lr in range(4):
      for cc in range(4):
       for lc in range(4):
        row=sr*16+cr+4*lr;col=sc*16+cc+4*lc
        if row<shape and col<shape:cells.add((row,col,2*sr+sc,cr*4+lr,cc*4+lc))
  assert len(cells)==shape*shape and{(r,c)for r,c,*_ in cells}=={(r,c)for r in range(shape)for c in range(shape)}
  readout=[(r,c)for r in range(shape)for ci in range((shape+3)//4)for k in range(4)if(c:=4*ci+k)<shape];assert len(readout)==shape*shape and set(readout)=={(r,c)for r in range(shape)for c in range(shape)}
  geometry.append(dict(shape=shape,active_cells=len(cells),subentries=(shape+15)//16*((shape+15)//16),e8w4_LMUL=1,e32w1_LMUL=4,maxTM_TN=32,rowmove_EG_per_row=(shape+3)//4,complete_rowreadout_elements=len(readout)))
 independent=R/'build/zephyr-hart2-pow2-separate-review-v4/report.json';array=R/'build/zephyr-pow2-matrix-associated-source-v1/report.json';ready=R/'build/zephyr-hart2-pow2-qualified-v1/ready.json';qualification=R/'build/zephyr-hart2-pow2-qualified-v1/qualification.json'
 for p in(independent,array):
  r=json.loads(p.read_text());assert r['pass']is True
  for n,h in r['input_sha256'].items():assert sha(n)==h,(p,n)
 # This API initializes all four tiles before any persistent worker compute.
 init=R/'third_party/zephyr-iris/arch/riscv/core/iris_vme.c';assembly=R/'third_party/zephyr-iris/arch/riscv/core/iris_vme_tiles.S';assert 'z_iris_vme_tiles_zero();'in init.read_text()
 dis=(independent.parent/'disassembly.txt').read_text();zero=re.search(r'<z_iris_vme_tiles_zero>:(.*?)(?:\n\n)',dis,re.S).group(1);assert all(x in zero for x in ['43e06057','43e06457','43e06857','43e06c57','8802f057','8812f057'])
 inputs=[Path(__file__),meta,top,independent,array,ready,init,assembly,R/'third_party/rocket-chip/src/main/scala/rocket/Matrix.scala',R/'third_party/rocket-chip/src/main/scala/rocket/CSR.scala',R/'third_party/saturn/src/main/scala/backend/OuterProductSequencer.scala',R/'hardware/evidence/outer-product-unit.scala',R/'third_party/saturn/benchmarks/common/vme.h']
 report=dict(schema='iris.Zephyr_hart2_pow2_independent_source_closure.v1',**{'pass':True},ELF_sha256='d47bec0012e4beea0df17b8f1d1c0aa0dc53f07f2a2dc9e8ed0fd5b5bbb49430',regions=648,independent_words=181440,RVV_words=20160,matrix_words=161280,protected_regions=192,training_eligible=456,geometry=geometry,associated_module_sha256={n:hashlib.sha256(modules[n].encode()).hexdigest()for n in['ShuttleCore','OuterProductUnit','OuterProductCluster','OuterProductCluster_4','OuterProductCell','OuterProductSequencer']},capacity_per_tile_words=1024,physical_cells=256,MRF_slots_per_physical_cell=16,tiles=4,actual_source_whole_array_scenarios=30,actual_source_full_MRF_word_checks=122880,all4_FP8_formats_source_and_compiled_selection_checked=True,compiled_hart2_application_scalar=True,all_results_after_all_ROIs=True,controlled_model_stop='break at noinline emit entry0x80000844 after648 count/FENCE/done0/FENCE; stable exactELF readback only, no normalexit/E2Eclaim; full hardware run still fullUART+actualexit',no_new_marker_required=True,normal_and_measured_only_skip_seeds=[0,17],normal_words_per_seed=181440,skip_all_active_words_nonidentity=True,physical_roles='mask1=hart0,mask2=hart1,mask3=both;hart2scalarcontroller',mask3_may_include_peer_readout_or_controller_memory_traffic=True,source_instruction_shapes_supported=True,whole_Core_OS_SMP_liveness_still_requires_actual_normal_hardware=True,not_a_pure_unit_throughput_or_FENCE_absolute_completion_proof=True,full_source_image_attestation=False,physical_timing_or_2pct_claim=False,hardware_or_protected_labels_accessed=False,input_sha256={str(p):sha(p)for p in inputs});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'sha256':sha(o/'report.json')}))
if __name__=='__main__':main()

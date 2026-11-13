#!/usr/bin/env python3
"""Build independent source-qualified full unit internal activity replay."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

R=Path(__file__).resolve().parents[1]
REF=R/'build/saturn-timing-component-v1-final'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--contract',type=Path,required=True);p.add_argument('--schema',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 shutil.copy2(Path(__file__),out/'builder.py');sdk=a.sdk.resolve();contract_path=a.contract.resolve();schema_path=a.schema.resolve();contract=json.loads(contract_path.read_text());schema=json.loads(schema_path.read_text())
 physical={k:json.loads((REF/'build/saturn-timing-source-v1'/k/'ports.json').read_text())for k in ['compute','rocket']}
 header='#pragma once\n#include <span>\n#include <string>\n#include <vector>\n#include <array>\n#include <bit>\nusing namespace iris::saturn;\nstruct Word{unsigned index;std::uint64_t mask;};\nstruct Rule{std::string name;bool postreset;int valid;std::vector<unsigned> any;std::vector<Word> words;};\nstruct PhysicalRule{std::string name;unsigned index;int valid;bool input_valid;int lane_word;};\n'
 projection_names=['reset','VRF_scrub','backend_busy_source','RVV_integer_pipe_busy','RVV_FP_pipe_busy','RVV_unified_pipe_busy','VME_busy_union','dispatch_accept','VME_macro_accept','VME_micro_issue','VME_INT8_MAC_accept','VME_FP8_MAC_accept','VME_INT8_MAC_complete','VME_FP8_MAC_complete','VME_VRF_write_bits','RVV_pipe_write_beats','RVV_iter_write_beats','RVV_sequencer_issue_beats','VMU_load_request_accept','VMU_store_request_accept','VMU_load_response','VMU_store_ack','shared_FPU_request_accept','shared_FPU_response','VMU_LIQ_occupancy','VMU_SIQ_occupancy','VDQ_occupancy']
 header+='struct ActivityProjection{std::uint64_t known=0;std::array<std::uint64_t,'+str(len(projection_names))+'> values{};};\n'
 projections={}
 for key in ['compute','rocket']:
  fs={f['name']:f for f in schema['profiles'][key]['fields']};rules=[]
  for rule in contract['profiles'][key]['qualified_field_rules']:
   valid=-1 if rule['valid_when']is None else fs[rule['valid_when']]['words'][0]['index']
   anyof=[fs[n]['words'][0]['index']for n in rule.get('valid_any',[])]
   words=['{'+str(w['index'])+','+str((1<<w['width'])-1)+'ULL}'for w in rule['words']]
   rules.append('{'+json.dumps(rule['name'])+','+('true'if rule['phase_gate']=='after_postreset_edge'else'false')+','+str(valid)+',{'+','.join(map(str,anyof))+'},{'+','.join(words)+'}}')
  header+='static const Rule '+key+'_rules[]={'+','.join(rules)+'};\n'
  ins=physical[key]['words']['input'];outs=physical[key]['words']['output'];imap={f['word_name']:i for i,f in enumerate(ins)};omap={f['word_name']:i for i,f in enumerate(outs)}
  prefix='io_core_'if key=='rocket'else'io_';prules={}
  def add(name,valid=None,input_valid=False,lane_word=-1):
   if name not in omap:raise ValueError('Missing output '+name)
   vi=-1 if valid is None else(imap if input_valid else omap)[valid]
   prules[name]='{'+json.dumps(name)+','+str(omap[name])+','+str(vi)+','+('true'if input_valid else'false')+','+str(lane_word)+'}'
  for name in omap:
   if name.endswith('_valid')or name in [prefix+n for n in ['ex_ready','backend_busy','trap_check_busy','set_vxsat']]+(['io_com_retire_late','io_com_xcpt','io_com_scalar_check_ready','io_com_internal_replay','io_com_block_all']if key=='compute'else['io_core_mem_block_mem','io_core_mem_block_all','io_core_wb_replay','io_core_wb_retire','io_core_wb_xcpt']):add(name)
  add('auto_atl_out_d_ready','auto_atl_out_d_valid',True)
  for name in omap:
   if name.startswith('auto_atl_out_a_bits_')and not name.startswith('auto_atl_out_a_bits_data'):add(name,'auto_atl_out_a_valid')
   if name.startswith('auto_atl_out_a_bits_data'):add(name,'auto_atl_out_a_valid',lane_word=(int(name.rsplit('_',1)[1])if key=='compute'else 0))
  for group in ['resp','set_vstart','set_vconfig','set_fflags']:
   for name in omap:
    if name.startswith(prefix+group+'_bits'):add(name,prefix+group+'_valid')
  tlb='io_tlb_req_'if key=='rocket'else'io_mem_tlb_req_'
  for name in omap:
   if name.startswith(tlb+'bits_'):add(name,tlb+'valid')
  if key=='rocket':
   for group in ['io_dmem_req_','io_fp_req_']:
    for name in omap:
     if name.startswith(group+'bits_'):add(name,group+'valid')
  header+='static const PhysicalRule '+key+'_physical[]={'+','.join(prules.values())+'};\n'
  header+='static constexpr unsigned '+key+'_reset='+str(imap['reset'])+', '+key+'_scrub='+str(fs['vu.vrf.resetting']['words'][0]['index'])+', '+key+'_a_opcode='+str(omap['auto_atl_out_a_bits_opcode'])+', '+key+'_a_mask='+str(omap['auto_atl_out_a_bits_mask'])+';\n'
  index={name:f['words'][0]['index']for name,f in fs.items()}
  selected=set(rule['name']for rule in contract['profiles'][key]['qualified_field_rules'])
  def value(name):
   if name not in selected:raise ValueError('Unqualified projection field '+name)
   return 'w['+str(index[name])+']'
  def anynames(names):return '('+'||'.join(value(n)+'!=0'for n in names)+')'if names else'false'
  def sum_names(names):return '('+'+'.join(value(n)for n in names)+')'if names else'0ULL'
  def accept(unit,port):return '('+value(unit+'.io_'+port+'_valid')+'&&'+value(unit+'.io_'+port+'_ready')+')'
  projection=['inline ActivityProjection project_'+key+'(bool q,bool post,bool reset,const std::vector<std::uint64_t>&w){ActivityProjection out;auto put=[&](unsigned n,std::uint64_t v,bool known){out.values[n]=known?v:0;if(known)out.known|=1ULL<<n;};']
  def put(name,expr,gate='q'):
   projection.append('put('+str(projection_names.index(name))+','+expr+','+gate+');')
  put('reset','reset','true');put('VRF_scrub',value('vu.vrf.resetting'));put('backend_busy_source',value('vu.io_busy'));put('dispatch_accept',accept('dis','dis'))
  for unit,label in [('vu.vxuint','RVV_integer_pipe_busy'),('vu.vxufp','RVV_FP_pipe_busy'),('vu.vxufp_int','RVV_unified_pipe_busy')]:
   names=[n for n in selected if re.fullmatch(re.escape(unit)+r'\.io_(?:pipe|iter)_hazards_\d+_valid',n)]
   put(label,anynames(sorted(names)) if names else'0ULL')
  execution=['vu.vxuint','vu.vxufp']if key=='compute'else['vu.vxufp_int']
  put('RVV_pipe_write_beats',sum_names([u+'.io_pipe_write_valid'for u in execution]));put('RVV_iter_write_beats','('+'+'.join(accept(u,'iter_write')for u in execution)+')')
  sequences=['vu.vls','vu.vss','vu.vps']+(['vu.vxsint','vu.vxsfp']if key=='compute'else['vu.vxsfp_int'])
  put('RVV_sequencer_issue_beats','('+'+'.join(accept(u,'iss')for u in sequences)+')')
  for port,label in [('dmem_load_req','VMU_load_request_accept'),('dmem_store_req','VMU_store_request_accept')]:put(label,accept('vmu',port))
  for port,label in [('dmem_load_resp','VMU_load_response'),('dmem_store_ack','VMU_store_ack')]:put(label,value('vmu.io_'+port+'_valid'))
  put('shared_FPU_request_accept',accept('vu','fp_req')if key=='rocket'else'0ULL');put('shared_FPU_response',value('vu.io_fp_resp_valid')if key=='rocket'else'0ULL')
  for regex,label in [(r'vmu\.liq_valids_\d+','VMU_LIQ_occupancy'),(r'vmu\.siq_valids_\d+','VMU_SIQ_occupancy'),(r'vu\.vdq\.valids_\d+','VDQ_occupancy')]:put(label,sum_names(sorted(n for n in selected if re.fullmatch(regex,n))))
  if key=='compute':
   flags=[f'vu.vopu_ctrl_reg_{kind}_{r}'for kind in ['macc','zero','mvin','mvin_col']for r in range(4)]
   tails=sorted(n for n in selected if re.fullmatch(r'vu\.vopu\.clusters_\d_\d\.cells_\d_\d\.fma\.(?:io_validout_pipe_v|valid_stage0_pipe_v)',n))
   put('VME_busy_union',anynames(['vu.vos.valid','vu.vos.fp8_hist_valid','vu.vos.mvout_valids',*flags,*tails]),'q&&post')
   put('VME_macro_accept',accept('vu.vos','dis'));put('VME_micro_issue',value('vu.vos.io_iss_valid'))
   cells=[]
   for cr in range(4):
    for cc in range(4):
     for row in range(4):
      for col in range(4):cells.append('('+value(f'vu.vopu_ctrl_reg_macc_{cr}')+'&&'+value(f'vu.vopu_ctrl_reg_row_en_{cr}_{row}')+'&&'+value(f'vu.vopu_ctrl_reg_col_en_{cc}_{col}')+')')
   projection.append('const std::uint64_t MACs='+'+'.join(cells)+';')
   for label in ['VME_INT8_MAC_accept','VME_INT8_MAC_complete']:put(label,'(MACs?('+value('vu.vopu_ctrl_reg_fp8')+'?0:MACs):0)','q&&post')
   put('VME_FP8_MAC_accept','(MACs?('+value('vu.vopu_ctrl_reg_fp8')+'?MACs:0):0)','q&&post')
   put('VME_FP8_MAC_complete',sum_names([n for n in tails if n.endswith('io_validout_pipe_v')]))
   write=fs['vu.vos.io_write_mask'];writewords=['std::popcount(w['+str(w['index'])+'])'for w in write['words']]
   # write mask itself was not a protocol bits_ field, so source-qualify it
   # under its real write valid in the semantic contract, never unconditionally.
   if 'vu.vos.io_write_mask' not in selected:raise ValueError('Missing qualified VME VRF write mask')
   put('VME_VRF_write_bits','('+value('vu.vos.io_write_valid')+'?('+'+'.join(writewords)+'):0)')
  else:
   for name in projection_names:
    if name.startswith('VME_'):put(name,'0ULL')
  projection.append('return out;}');header+='\n'.join(projection)+'\n'
 header+='''inline auto activity_rules(Profile p){return p==Profile::Compute128?std::span<const Rule>(compute_rules):std::span<const Rule>(rocket_rules);}
inline auto physical_rules(Profile p){return p==Profile::Compute128?std::span<const PhysicalRule>(compute_physical):std::span<const PhysicalRule>(rocket_physical);}
inline unsigned reset_index(Profile p){return p==Profile::Compute128?compute_reset:rocket_reset;}
inline unsigned scrub_index(Profile p){return p==Profile::Compute128?compute_scrub:rocket_scrub;}
inline std::uint64_t physical_mask(const PhysicalRule&r,Profile p,const std::vector<std::uint64_t>&,const std::uint64_t*o){
 if(r.lane_word<0)return ~0ULL;const auto op=o[p==Profile::Compute128?compute_a_opcode:rocket_a_opcode];if(op!=0&&op!=1)return 0ULL;
 const auto lanes=o[p==Profile::Compute128?compute_a_mask:rocket_a_mask];std::uint64_t mask=0;for(unsigned b=0;b<8;++b)if(lanes>>(8*r.lane_word+b)&1)mask|=255ULL<<(8*b);return mask;
}
inline ActivityProjection project_activity(Profile p,bool q,bool post,bool reset,const std::vector<std::uint64_t>&w){return p==Profile::Compute128?project_compute(q,post,reset,w):project_rocket(q,post,reset,w);}
'''
 h=out/'activity_qualification.hpp';h.write_text(header);source=out/'replay.cpp';shutil.copy2(R/'timing/saturn_timing_activity_replay.cpp',source)
 command=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(out),'-I'+str(sdk/'sdk'),'-I/scratch/eygao/iris-cy/.conda-env/share/verilator/include',str(source),str(sdk/'sdk/libiris_saturn_timing.a'),'-latomic','-lz','-o',str(out/'replay')]
 with(out/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 inputs=[Path(__file__),R/'timing/saturn_timing_activity_replay.cpp',contract_path,schema_path,sdk/'build.json',sdk/'sdk/libiris_saturn_timing.a',h,source,Path('/usr/bin/g++')]
 projection_schema={'schema':'iris.saturn_qualified_activity_projection.v1','record_layout':['hart','source_edge','tb','known_mask',*projection_names],'value_knownness':'value i is meaningful iff known_mask bit i is1; zero otherwise is an unknown placeholder','phase':contract['phase'],'state_interval':contract['state_interval'],'contract_sha256':sha(contract_path),'units':{'VME_MAC':'one physical cell multiply-accumulate, not two operations','VME_VRF_write_bits':'actual source bit-mask popcount; not external memory bytes','VMU_request_response':'actual internal request/response beat counts; no PC owner inferred'},'busy':'boolean union, not sum of overlapping states','unsupported_profile_units':'known zero only because configured hardware has no such unit','numeric_definedness':'no numeric knownness or result-value certificate is implied by control-work counts','loaded_FPGA_or_full_timing_certified':False}
 (out/'projection-schema.json').write_text(json.dumps(projection_schema,indent=2)+'\n')
 result={'schema':'iris.saturn_activity_replay_build.v1','argv':command,'input_sha256':{str(p):sha(p)for p in inputs},'binary_sha256':sha(out/'replay'),'projection_schema_sha256':sha(out/'projection-schema.json'),'no_internal_state_or_readiness_inputs':True,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'binary_sha256':result['binary_sha256']}))
if __name__=='__main__':main()

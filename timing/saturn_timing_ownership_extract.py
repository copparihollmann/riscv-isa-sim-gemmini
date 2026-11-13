#!/usr/bin/env python3
"""Resolve read-only source ownership metadata without changing RTL objects."""
import argparse
import hashlib
import json
import re
import shutil
from collections import deque
from pathlib import Path
from saturn_timing_activity_extract import modules,cpp_fields
from saturn_timing_activity_schema import aliases,resolve

R=Path(__file__).resolve().parents[1]
BASE=R/'build/saturn-timing-activity-component-v1-final'
REF=R/'build/saturn-timing-component-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def source_port_member(name,top,prefix,available,width,graph):
 member=resolve(name,top,prefix,available,width,graph)
 if member is not None:return member
 # Verilator retains some expression-connected physical child inputs as
 # Vcellinp temporaries. Bind that exact source port, never recompute its RTL
 # expression or replace an optimized-away control with a guessed value.
 queue=deque([name]);seen={name}
 while queue:
  logical=queue.popleft()
  if '.'in logical:
   path,port=logical.rsplit('.',1)
   if port.startswith('io_')and'.'in path:
    parent,instance=path.rsplit('.',1);candidate=prefix+'__DOT__'.join(parent.split('.'))+'__DOT____Vcellinp__'+instance+'__'+port
    if available.get(candidate)==width:return candidate
  for alias in sorted(graph[logical]):
   if alias not in seen:seen.add(alias);queue.append(alias)
 return None
def identical_cell_input_aliases(definitions,top,graph):
 evidence=[]
 def visit(module,path):
  info=definitions[module]
  if module.startswith('OuterProductCluster'):
   groups={}
   for match in re.finditer(r'^  (\w+) (\w+) \((.*?)^  \);',info['path'].read_text(),re.M|re.S):
    child,instance,body=match.groups()
    if child!='OuterProductCell':continue
    for port in re.finditer(r'^\s*\.(\w+)\s*\((.*)\),?\s*(?://.*)?$',body,re.M):
     if port[1]!='io_mvin_data':continue
     expression=re.sub(r'\s+','',port[2]);groups.setdefault(expression,[]).append('.'.join([*path,instance,port[1]]))
   for expression,names in groups.items():
    for name in names[1:]:graph[names[0]].add(name);graph[name].add(names[0])
    evidence.append({'source_path':str(info['path']),'source_sha256':sha(info['path']),'parent_instance':'.'.join(path),'literal_identical_input_expression':expression,'equivalent_input_ports':names})
  for instance,child in info['instances'].items():
   if child in definitions:visit(child,[*path,instance])
 visit(top,[]);return evidence
def selected(module,name):
 if not name.startswith('io_'):return False
 if any(token in name for token in ['data','rs1','rs2'])and not any(token in name for token in ['debug_id','mask','ready','valid']):return False
 return bool(re.search(r'valid|ready|busy|fire|debug_id|vat|lsiq|tag|head|tail|mask|eidx|pc|bits_bits|bits_inst|pipe_depth|sew|fu_sel|mrf_idx|tss_idx|last|replay|retire|kill|segstart|segend|whole_reg|reserve_bits|_eg(?:$|_)|scalar_write_bits_rd',name))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'extractor.py')
 base_schema_path=BASE/'build/saturn-timing-activity-schema-v1/schema.json';base_schema=json.loads(base_schema_path.read_text())
 whole_path=BASE/'build/saturn-timing-activity-reference-v2/model/VTestDriver___024root.h';whole=cpp_fields(whole_path);result={'schema':'iris.saturn_ownership_readonly_boundary.v1','parent_activity_capsule_sha256':sha(BASE/'report.json'),'base_activity_schema_sha256':sha(base_schema_path),'profiles':{},'input_sha256':{str(Path(__file__)):sha(Path(__file__)),str(whole_path):sha(whole_path),str(base_schema_path):sha(base_schema_path)},'RTL_objects_modified':False,'model_inputs_added':False,'hardware_contacted':False}
 watch=('PipelinedFaultCheck','IterativeFaultCheck','VectorDispatcher','VectorBackend','LoadSequencer','StoreSequencer','ExecuteSequencer','SpecialSequencer','OuterProductSequencer','VectorMemUnit','AddrGen','LoadOrderBuffer','ReorderBuffer','LoadSegmenter','LoadSegmentBuffer','StoreSegmenter','Compactor','DCEQueue','Queue','Arbiter','TLInterface','TLSplitInterface','VectorTLReader','VectorTLWriter','ExecutionUnit','SharedScalarElementwiseFPFMA','MaskUnit','RegisterAccess','RegisterFile')
 for key,top,prefix,native_name in [('compute','SaturnShuttleUnit','VSaturnCompute','saturn-timing-activity-native-fast-v4'),('rocket','SaturnRocketUnit','VSaturnRocket','saturn-timing-activity-native-rocket-v2')]:
  header=BASE/'build'/native_name/'model'/(prefix+'___024root.h');native=cpp_fields(header);result['input_sha256'][str(header)]=sha(header);definitions=modules(REF/'build/saturn-timing-source-v1'/key/'rtl');graph=aliases(definitions,top);expression_aliases=identical_cell_input_aliases(definitions,top,graph);candidates={};word=0
  def visit(module,path):
   info=definitions[module]
   if module.startswith(watch):
    for name,d in info['declarations'].items():
     if not selected(module,name)or not re.match(r'\s*(?:input|output)\s',d['literal']):continue
     logical='.'.join([*path,name]);candidates[logical]={'name':logical,'module':module,'width':d['width'],'source':{'path':str(info['path']),'sha256':sha(info['path']),**d}}
   for instance,child in info['instances'].items():
    if child in definitions:visit(child,[*path,instance])
  visit(top,[])
  required=['vmu.liq_enq_ptr','vmu.liq_las_ptr','vmu.liq_lss_ptr','vmu.siq_enq_ptr','vmu.siq_sas_ptr','vmu.siq_sss_ptr','vmu.siq_deq_ptr','vmu.lifq.enq_ptr_value','vmu.lifq.deq_ptr_value']
  required+=['vmu.io_vu_lresp_q.do_enq','vmu.io_vu_lresp_q.do_deq']
  seg_module=definitions[definitions[definitions[top]['instances']['vmu']]['instances']['lss']]['instances']['segbuf'];seg_definition=definitions[seg_module]
  seg_modes=sorted(n for n in seg_definition['declarations']if re.fullmatch(r'modes_\d+',n))
  if len(seg_modes)not in[1,2]:raise ValueError('Review configured load segment buffer shape')
  required+=['vmu.lss.segbuf.'+name for name in seg_modes]
  required+=['vmu.lss.segbuf.wrow']
  if len(seg_modes)>1:required+=['vmu.lss.segbuf.in_sel','vmu.lss.segbuf.out_sel']
  required+=['vu.'+('vxuint'if key=='compute'else'vxufp_int')+'.fus_3.scalar_wb_busy']
  bank_module=definitions[definitions[definitions[definitions[top]['instances']['vu']]['instances']['vrf']]['instances']['vrf']]
  for instance,module in bank_module['instances'].items():
   if instance.startswith('vrf_')and module.startswith('RegisterFileBank'):required+=['vu.vrf.vrf.'+instance+'.write_bits_data']
  if key=='compute':required+=['vu.vos.tss_idx','vu.vos.inst_bits']
  if key=='compute':
   for cr in range(4):
    for cc in range(4):
     for row in range(4):
      for col in range(4):
       path=f'vu.vopu.clusters_{cr}_{cc}.cells_{row}_{col}.'
       required += [path+n for n in ['io_mrf_idx','io_macc','io_fp8','io_zero','io_mvin','io_mvin_data','_sum_int_T_1','sum_fp8','mrf_idx_pipe_pipe_pipe_b']]
  # These registered indices select real queue entries; they are observer
  # metadata and never supplied to the timing unit as reconstructed state.
  for logical in required:
   path,name=logical.rsplit('.',1);module=top
   for instance in path.split('.'):module=definitions[module]['instances'][instance]
   d=definitions[module]['declarations'][name];candidates[logical]={'name':logical,'module':module,'width':d['width'],'source':{'path':str(definitions[module]['path']),'sha256':sha(definitions[module]['path']),**d}}
  fields=[];unresolved=[]
  existing={f['name']for f in base_schema['profiles'][key]['fields']}
  for name,f in sorted(candidates.items()):
   if name in existing:continue
   member=source_port_member(name,top,top+'__DOT__',native,f['width'],graph);gold=[]
   for h in([0,1]if key=='compute'else[2]):
    parent='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain'+('_'+str(h)if h else'')+'__DOT__element_reset_domain_'+('rockettile'if h==2 else'shuttle_tile')+'__DOT__vector_unit__DOT__';gold.append({'hart':h,'member':source_port_member(name,top,parent,whole,f['width'],graph)})
   if member is None or any(x['member']is None for x in gold):unresolved.append({**f,'native_missing':member is None,'whole_missing':[x['hart']for x in gold if x['member']is None]});continue
   words=[]
   for lo in range(0,f['width'],64):words.append({'lo':lo,'width':min(64,f['width']-lo),'index':word});word+=1
   fields.append({**f,'member':member,'whole_members':gold,'words':words})
  missing=[name for name in required if name not in {f['name']for f in fields}|existing]
  row_count=seg_definition['declarations']['io_in_bits_data']['width']//8
  # Source wrow is fire ? (((1<<(mLenB>>eew))-1)<<sidx)[7:0] :0.
  # Every physical eew2/sidx3 encoding has at least bit sidx set.  This
  # exhaustive bit-width proof makes wrow!=0 an exact in.fire observer even
  # when Verilator eliminated the original boolean wire, without guessing it.
  row_cases=[]
  for eew in range(4):
   for sidx in range(8):
    mask=((((1<<(row_count>>eew))&255)-1)&255)<<sidx&255
    if not mask:raise ValueError('Cannot qualify segment-buffer input acceptance from physical row write mask')
    row_cases.append({'eew':eew,'sidx':sidx,'accepted_row_mask':mask})
  result['profiles'][key]={'top_module':top,'fields':fields,'word_count':word,'base_activity_fields_remain_available':True,'exact_expression_aliases':expression_aliases,'unresolved_candidate_fields':unresolved,'required_registered_indices':required,'required_unresolved':missing,'load_segment_buffer':{'module':seg_module,'slots':len(seg_modes),'selector_is_constant_zero':len(seg_modes)==1,'source_path':str(seg_definition['path']),'source_sha256':sha(seg_definition['path']),'input_acceptance_from_wrow_nonzero':{'source_physical_rows':row_count,'all_physical_eew_sidx_encodings':row_cases,'false_fire_always_zero':True}}}
 (out/'schema.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'sha256':sha(out/'schema.json'),'profiles':{k:{'fields':len(v['fields']),'words':v['word_count'],'unresolved_candidates':len(v['unresolved_candidate_fields']),'required_unresolved':v['required_unresolved']}for k,v in result['profiles'].items()}}))
 if any(v['required_unresolved']for v in result['profiles'].values()):raise SystemExit('Required source ownership state was optimized away; add a reviewed read-only visibility variant')
if __name__=='__main__':main()

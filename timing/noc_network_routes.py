#!/usr/bin/env python3
"""Add exact decoder-domain guards to the complete physical NoC wrapper."""
import argparse,copy,hashlib,json,re,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,default=R/'build/noc-network-source-v1');p.add_argument('--output',type=Path,default=R/'build/noc-network-source-v2');a=p.parse_args();source=a.source.resolve();out=a.output.resolve()
 if out.exists():raise ValueError('Fresh guarded source directory required')
 original=json.loads((source/'extraction.json').read_text());assert sha(source/'rtl/IrisNoCNetwork.sv')==original['wrapper_sha256'];anno=Path('/scratch/eygao/iris-cy/sims/vcs/generated-src/chipyard.harness.TestHarness.IrisConfig/chipyard.harness.TestHarness.IrisConfig.anno.json');tables={}
 for x in json.loads(anno.read_text()):
  if x.get('class')!='chisel3.util.experimental.decode.DecodeTableAnnotation':continue
  target=x.get('target','');m=re.search(r'\|(RouteComputer\w*)>(decoded_plaOutput(?:_\d+)?)$',target)
  if not m:continue
  index=0 if m[2]=='decoded_plaOutput'else int(m[2].rsplit('_',1)[1]);rows=[]
  for line in x['truthTable'].splitlines():
   if '->'not in line:continue
   key,val=line.split('->');assert re.fullmatch('[01]+',key)and re.fullmatch('[01]+',val);rows.append(key)
  assert rows;tables[(m[1],index)]=rows
 # Chisel decoder instance suffixes compress over empty route tables. Resolve
 # each annotation to its actual request index through the saved FIR wiring;
 # never assume suffixN == inputN (node4's unused C ingress is a counterexample).
 fir=next((R/'build/rtl-memory-return-path-v1-final/external').rglob('*.fir'));firtext=fir.read_text();assert sha(fir)=='f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4';resolved={};table_targets={}
 for rc in sorted({rc for rc,index in tables}):
  begin=firtext.index('  module '+rc+' :');end=firtext.find('\n  module ',begin+4);body=firtext[begin:end];addresses={name:int(slot)for name,slot in re.findall(r'node (\w+) = cat\(io.req.`(\d+)`.bits.src_virt_id',body)}
  for decoder,address in re.findall(r'connect (decoded_plaInput(?:_\d+)?), (\w+)',body):
   table_index=0 if decoder=='decoded_plaInput'else int(decoder.rsplit('_',1)[1]);slot=addresses[address];resolved[(rc,slot)]=tables[(rc,table_index)];table_targets[(rc,slot)]=table_index
 assert len(resolved)==len(tables);tables=resolved
 edgefiles={net:anno.with_name('chipyard.harness.TestHarness.IrisConfig.TLSplitACDxBENoC_'+net+'.noc.edgeprops')for net in['acd','be']};egress={}
 for net,file in edgefiles.items():
  nodes={}
  for line in file.read_text().splitlines():
   fields=line.split()
   if len(fields)>1 and fields[0].isdigit()and re.fullmatch('e\d+',fields[1]):nodes.setdefault(int(fields[0]),[]).append(int(fields[1][1:]))
  egress[net]=nodes
 guards=[];lines=['// Exact source annotation default-domain admission checks. No added flops.','always @(posedge clock) begin','  if (!'+original['reset_source_net']+') begin']
 from noc_network_extract import ports
 for inst in original['instances']:
  if 'router_'not in inst['module']:continue
  src=source/'rtl';domain=(src/(inst['module']+'.sv')).read_text();router=re.search(r'^  (Router\w*) routers \(',domain,re.M)[1];routertext=(src/(router+'.sv')).read_text();rc=re.search(r'^  (RouteComputer\w*) route_computer \(',routertext,re.M)[1];rcports=ports((src/(rc+'.sv')).read_text());rports=ports(routertext);network_prefix={int(m[1]or 0):n[:-5]for n in rports if(m:=re.fullmatch(r'auto_dest_nodes_in(?:_(\d+))?_flit_0_valid',n))};local_prefix={int(m[1]or 0):n[:-5]for n in rports if(m:=re.fullmatch(r'auto_ingress_nodes_in(?:_(\d+))?_flit_valid',n))};network_inputs=sorted(network_prefix);local_inputs=sorted(local_prefix);assert network_inputs==list(range(len(network_inputs)))and local_inputs==list(range(len(local_inputs)))
  net='acd'if'_acd_'in inst['name']else'be';node=int(re.search(r'_router_(\d+)Clock',inst['module'])[1]);widths=[]
  suffixes=['src_virt_id','flow_vnet_id','flow_ingress_node','flow_ingress_node_id','flow_egress_node','flow_egress_node_id']
  for suffix in suffixes:widths.append(rcports['io_req_0_bits_'+suffix]['width'])
  for index in network_inputs:
   key=(rc,index);rows=tables.get(key,[]);assert not rows or len(rows[0])==sum(widths)
   pfx=network_prefix[index];pieces=[inst['name']+'.routers.'+pfx+'bits_virt_channel_id']+[inst['name']+'.routers.'+pfx+'bits_'+suffix for suffix in suffixes[1:]];expression='{'+','.join(pieces)+'}';valid=inst['name']+'.routers.'+pfx+'valid';checks=' || '.join(expression+' == '+str(len(word))+"'b"+word for word in rows)or"1'b0";lines.append('    if ('+valid+') assert ('+checks+') else $fatal(1,"NoC routing flow outside source decoder domain '+rc+'/'+str(index)+'");');guards.append({'network':net,'node':node,'input':index,'kind':'network_flit','route_computer':rc,'annotation_table':table_targets.get(key),'key_widths':widths,'allowed_keys':rows,'source_valid':valid})
  for index in local_inputs:
   slot=len(network_inputs)+index;rows=tables.get((rc,slot),[]);node_width,id_width=widths[-2:];ids=sorted({egress[net][(int(word,2)>>id_width)&((1<<node_width)-1)][int(word,2)&((1<<id_width)-1)]for word in rows});pfx=local_prefix[index];valid=inst['name']+'.routers.'+pfx+'valid';signal=inst['name']+'.routers.'+pfx+'bits_egress_id';checks=' || '.join(signal+' == '+str(value)for value in ids)or"1'b0";lines.append('    if ('+valid+') assert ('+checks+') else $fatal(1,"NoC ingress egress ID outside source flow set '+rc+'/'+str(slot)+'");');guards.append({'network':net,'node':node,'input':index,'route_request_index':slot,'kind':'local_ingress','route_computer':rc,'annotation_table':table_targets.get((rc,slot)),'allowed_global_egress_ids':ids,'source_valid':valid})
 lines+=['  end','end'];guardtext='\n'.join(lines)+'\n';out.mkdir();shutil.copytree(source/'rtl',out/'rtl');top=(out/'rtl/IrisNoCNetwork.sv').read_text();assert top.count('endmodule')==1;top=top.replace('endmodule',guardtext+'endmodule');(out/'rtl/IrisNoCNetwork.sv').write_text(top)
 contract={'schema':'iris.complete_noc_routing_contract.v1','annotation':{'path':str(anno),'sha256':sha(anno)},'FIR_decoder_input_mapping':{'path':str(fir),'sha256':sha(fir)},'edgeprops':{net:{'path':str(path),'sha256':sha(path)}for net,path in edgefiles.items()},'flow_guards':guards,'default_policy':'Refuse outside exact declared decoder minterms and ingress destinations; no default unknown flow is invented','TL_address_policy':'Physical upstream endpoint contracts still apply; routing guards do not certify arbitrary invalid TL traffic/address semantics'};(out/'routing-contract.json').write_text(json.dumps(contract,indent=2)+'\n');report=copy.deepcopy(original);report.update(schema='iris.complete_noc_source_cut.v2',unguarded_source_extraction_sha256=sha(source/'extraction.json'),wrapper_sha256=sha(out/'rtl/IrisNoCNetwork.sv'),routing_contract_sha256=sha(out/'routing-contract.json'),route_guards=len(guards),source_guard_generator_sha256=sha(Path(__file__)));(out/'extraction.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'guards':len(guards),'extraction_sha256':sha(out/'extraction.json'),'wrapper_sha256':sha(out/'rtl/IrisNoCNetwork.sv')}))
if __name__=='__main__':main()

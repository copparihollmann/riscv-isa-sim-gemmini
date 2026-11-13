#!/usr/bin/env python3
"""Build the exact source-generated native Router_5 timing component."""
import argparse,hashlib,json,re,shutil,subprocess,os
from pathlib import Path
R=Path(__file__).resolve().parents[1];CAP=R/'build/rtl-memory-return-path-v1-final';SRC=CAP/'build/rtl-verilator/gen-collateral'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser(__doc__);parser.add_argument('--output',type=Path,default=R/'build/noc-full-router-v2');args=parser.parse_args();OUT=args.output.resolve()
 if OUT.exists():raise ValueError('Refuse to overwrite full router build')
 if sha(CAP/'report.json')!='2e32a62c428c8f434c7893beb419da576b1e3a7ff4f4574aef41dc2c1f1dac0c':raise ValueError('Wrong exact RTL capsule')
 sources={};pending=['Router_5']
 while pending:
  name=pending.pop()
  if name in sources:continue
  p=SRC/(name+'.sv')
  if not p.exists():p=R/'build/rtl-verilator/gen-collateral'/(name+'.v')
  if not p.exists():raise ValueError('Missing source module: '+name)
  text=p.read_text();sources[name]=p
  children=set(re.findall(r'^[ \t]*(\w+)[ \t]+\w+[ \t]*\(',text,re.M))
  children.update(re.findall(r'^[ \t]*(\w+)[ \t]*#\([\s\S]*?^[ \t]*\)[ \t]*(\w+)[ \t]*\(',text,re.M))
  for child in children:
   child=child[0] if isinstance(child,tuple) else child
   if child not in ['module','if','else','assert','case','always'] and ((SRC/(child+'.sv')).exists() or (R/'build/rtl-verilator/gen-collateral'/(child+'.v')).exists()):pending.append(child)
 OUT.mkdir();target=OUT/'rtl';target.mkdir()
 for name,p in sources.items():shutil.copyfile(p,target/p.name)
 top=(SRC/'Router_5.sv').read_text();ports=[]
 for direction,width,name in re.findall(r'^[ \t]*(input|output)[ \t]+(?:\[(\d+:\d+)\][ \t]+)?(\w+)[, \t]*//',top,re.M):
  bits=int(width.split(':')[0])+1 if width else 1;ports.append({'direction':direction,'name':name,'bits':bits})
 anno=Path('/scratch/eygao/iris-cy/sims/vcs/generated-src/chipyard.harness.TestHarness.IrisConfig/chipyard.harness.TestHarness.IrisConfig.anno.json')
 edgeprops=anno.with_name('chipyard.harness.TestHarness.IrisConfig.TLSplitACDxBENoC_acd.noc.edgeprops')
 tables={}
 for x in json.loads(anno.read_text()):
  if x.get('class')=='chisel3.util.experimental.decode.DecodeTableAnnotation' and '|RouteComputer_5>' in x['target']:
   route_target=x['target'].split('>')[1];index=0 if route_target=='decoded_plaOutput' else int(route_target.rsplit('_',1)[1]);entries={}
   for line in x['truthTable'].splitlines():
    if '->' not in line:continue
    key,value=line.split('->')
    if not re.fullmatch('[01]{16}',key) or not re.fullmatch('[01]{12}',value):raise ValueError('Unsupported annotated routing row')
    entries[int(key,2)]=value
   tables[index]=entries
 if set(tables)!={0,1,2,3}:raise ValueError('Missing exact node5 input routing domain')
 egress={}
 for line in edgeprops.read_text().splitlines():
  a,b=line.split()[:2]
  if a.isdigit() and b.startswith('e'):egress.setdefault(int(a),[]).append(int(b[1:]))
 ingress=[]
 for k in [2,3]:
  ids=sorted({egress[(v>>3)&7][v&7] for v in tables[k]});ingress.append(ids)
 contract={'source_annotation':{'path':str(anno),'sha256':sha(anno)},'source_edgeprops':{'path':str(edgeprops),'sha256':sha(edgeprops)},'input_route_truth_tables':{str(k):{str(key):v for key,v in entries.items()} for k,entries in tables.items()},'legal_ingress_egress_ids':ingress,'illegal_decoder_defaults':'Annotated12-bit? default is not invented; API refuses inputs outside declared minterms'}
 (R/'timing/noc_full_router_contract.json').write_text(json.dumps(contract,indent=2)+'\n')
 header='#pragma once\n#include <array>\n#include <algorithm>\nnamespace iris::noc::source_contract {\n'
 for k in range(2):header+='inline constexpr std::array<std::uint16_t,'+str(len(tables[k]))+'> network'+str(k)+'={'+','.join(map(str,sorted(tables[k])))+'};\n'
 for k,ids in enumerate(ingress):header+='inline constexpr std::array<std::uint8_t,'+str(len(ids))+'> ingress'+str(k)+'={'+','.join(map(str,ids))+'};\n'
 header+='template<class T> inline bool contains(const T& table,unsigned x){return std::find(table.begin(),table.end(),x)!=table.end();}\n}\n'
 (R/'timing/noc_full_router_contract.hpp').write_text(header)
 # Complete typed-port mapping, generated from fixed interface spelling.
 code=(R/'timing/noc_full_router.cpp').read_text();marker='// BEGIN GENERATED PORT MAP';code=code.split(marker)[0]+marker+'\n'
 for k in range(2):
  dst='m.auto_dest_nodes_in_'+str(k)+'_flit_0_';src='i.from_network['+str(k)+']'
  for field in ['valid','head','tail']:code+=dst+('bits_' if field!='valid' else '')+field+'='+src+'.'+field+';\n'
  for w in range(3):code+=dst+'bits_payload['+str(w)+']='+src+'.payload.words['+str(w)+'];\n'
  for port,field in [('vnet_id','vnet'),('ingress_node','ingress_node'),('ingress_node_id','ingress_id'),('egress_node','egress_node'),('egress_node_id','egress_id')]:code+=dst+'bits_flow_'+port+'='+src+'.flow.'+field+';\n'
  code+=dst+'bits_virt_channel_id='+src+'.vc;\n'
  dst='m.auto_ingress_nodes_in_'+str(k)+'_flit_';src='i.from_local['+str(k)+']'
  for field in ['valid','head','tail']:code+=dst+('bits_' if field!='valid' else '')+field+'='+src+'.'+field+';\n'
  for w in range(3):code+=dst+'bits_payload['+str(w)+']='+src+'.payload.words['+str(w)+'];\n'
  code+=dst+'bits_egress_id='+src+'.egress_id;\n'
  for f in ['credit_return','vc_free']:code+='m.auto_source_nodes_out_'+str(k)+'_'+f+'=i.downstream['+str(k)+'].'+f+';\n'
 code+='m.auto_egress_nodes_out_flit_ready=i.local_ready;\nm.eval();FullRouterOutputs o{};\n'
 for k in range(2):
  src='m.auto_source_nodes_out_'+str(k)+'_flit_0_';dst='o.to_network['+str(k)+']'
  for field in ['valid','head','tail']:code+=dst+'.'+field+'='+src+('bits_' if field!='valid' else '')+field+';\n'
  for w in range(3):code+=dst+'.payload.words['+str(w)+']='+src+'bits_payload['+str(w)+'];\n'
  for port,field in [('vnet_id','vnet'),('ingress_node','ingress_node'),('ingress_node_id','ingress_id'),('egress_node','egress_node'),('egress_node_id','egress_id')]:code+=dst+'.flow.'+field+'='+src+'bits_flow_'+port+';\n'
  code+=dst+'.vc='+src+'bits_virt_channel_id;\n'
  code+='o.local_ready['+str(k)+']=m.auto_ingress_nodes_in_'+str(k)+'_flit_ready;\n'
  for f in ['credit_return','vc_free']:code+='o.upstream['+str(k)+'].'+f+'=m.auto_dest_nodes_in_'+str(k)+'_'+f+';\n'
 for field in ['valid','head','tail']:code+='o.to_local.'+field+'=m.auto_egress_nodes_out_flit_'+('bits_' if field!='valid' else '')+field+';\n'
 for w in range(3):code+='o.to_local.payload.words['+str(w)+']=m.auto_egress_nodes_out_flit_bits_payload['+str(w)+'];\n'
 for k in range(4):code+='o.va_stalls['+str(k)+']=m.auto_debug_out_va_stall_'+str(k)+';o.sa_stalls['+str(k)+']=m.auto_debug_out_sa_stall_'+str(k)+';\n'
 code+='m.clock=1;m.eval();m.clock=0;m.eval();++impl_->edge_count;return o;\n}\n'
 code+='''void FullNode5Router::save(const std::filesystem::path& p)const{
 VerilatedSave out;out.open(p.string());out<<std::uint64_t{0x495249534e4f4335ULL}<<std::string(IRIS_NODE5_SOURCE_ID)<<impl_->edge_count<<*impl_->model;out.close();
}
void FullNode5Router::restore(const std::filesystem::path& p){
 SnapshotPrefix prefix(p);
 VerilatedRestore in;in.open(p.string());std::uint64_t magic=0;std::string id;in>>magic>>id;if(magic!=0x495249534e4f4335ULL||id!=IRIS_NODE5_SOURCE_ID)throw std::invalid_argument("Node5 snapshot source identity mismatch");in>>impl_->edge_count>>*impl_->model;in.close();
}
std::uint64_t FullNode5Router::edges()const{return impl_->edge_count;}
const char* FullNode5Router::source_identity(){return IRIS_NODE5_SOURCE_ID;}
} // namespace iris::noc
'''
 (R/'timing/noc_full_router.cpp').write_text(code)
 verilator=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator')
 identity=hashlib.sha256(json.dumps({'sv':{str(p):sha(p) for p in sorted(sources.values())},'annotation':sha(anno),'edgeprops':sha(edgeprops),'api_header':sha(R/'timing/noc_full_router.hpp'),'api_implementation':sha(R/'timing/noc_full_router.cpp'),'routing_guard':sha(R/'timing/noc_full_router_contract.hpp'),'verilator_bin':sha(verilator.with_name('verilator_bin')),'configuration':'savable/port-only/assert/x-initial-unique/x-assign-unique/OPT_FAST_O3/snapshot-prefix-v2'},sort_keys=True).encode()).hexdigest();(R/'timing/noc_full_router_identity.hpp').write_text('#pragma once\n#define IRIS_NODE5_SOURCE_ID "'+identity+'"\n')
 (OUT/'ports.json').write_text(json.dumps(ports,indent=2)+'\n');(R/'timing/noc_full_router_ports.json').write_text(json.dumps(ports,indent=2)+'\n')
 verilator=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');model=OUT/'model';cmd=[str(verilator.with_name('perl')),str(verilator),'--cc','--exe','--build','-j','6','--top-module','Router_5','--prefix','VNode5','--savable','--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(model),'-I'+str(target),'-y',str(target),'+libext+.sv+.v','+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT','+define+RANDOMIZE_GARBAGE_ASSIGN','+define+RANDOMIZE_INVALID_ASSIGN',str(target/'Router_5.sv'),str(R/'timing/noc_full_router.cpp'),str(R/'timing/noc_full_router_driver.cpp'),'-CFLAGS','-O3 -std=c++20 -I'+str(R/'timing'),'-MAKEFLAGS','OPT_FAST=-O3 OPT_SLOW=-O3','-o',str(OUT/'noc-full-router')]
 (OUT/'build-command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 with (OUT/'build.log').open('w') as log:q=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,PATH=str(verilator.parent)+os.pathsep+os.environ['PATH']))
 if q.returncode:raise RuntimeError('Source router build failed; see '+str(OUT/'build.log'))
 files=list(sources.values())+[Path(__file__),R/'timing/noc_full_router.hpp',R/'timing/noc_full_router.cpp',R/'timing/noc_full_router_driver.cpp',R/'timing/noc_full_router_identity.hpp',R/'timing/noc_full_router_contract.hpp',R/'timing/noc_full_router_contract.json',anno,edgeprops,verilator,verilator.with_name('verilator_bin')]
 (OUT/'build.json').write_text(json.dumps({'schema':'iris.full_source_generated_node5.v1','source_identity':identity,'source_files':{str(p):sha(p) for p in sorted(sources.values())},'compile_argv':cmd,'input_sha256':{str(p):sha(p) for p in files},'native_sha256':sha(OUT/'noc-full-router'),'source_design':'Router_5 saved standalone IrisConfig subtree','runtime_plusargs':{'noc_util_sample_rate':0},'hardware_contacted':False,'timing_calibrated':False},indent=2)+'\n');print('source modules',len(sources),'native',sha(OUT/'noc-full-router'))
if __name__=='__main__':main()

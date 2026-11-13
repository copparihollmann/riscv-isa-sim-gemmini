#!/usr/bin/env python3
"""Export the source connectivity graph and actual endpoint handshake coverage."""
import argparse,collections,hashlib,json,re
from pathlib import Path
import noc_network_check as check
from noc_network_extract import identifiers
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=R/'build/noc-network-graph-v1');a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('Fresh graph output required')
 out.mkdir();source=R/'build/noc-network-source-v2';j=json.loads((source/'extraction.json').read_text());nodes=[];producers={};consumers=collections.defaultdict(list);widths={}
 for inst in j['instances']:
  router='_router_'in inst['module'];kind='router_clock_domain'if router else'tl_master_adaptor'if'TLMaster'in inst['module']else'tl_slave_adaptor';node={'id':inst['name'],'module':inst['module'],'kind':kind,'fabric':'acd'if'_acd_'in inst['name']else'be','source_module_sha256':sha(source/'rtl'/(inst['module']+'.sv')),'source_DigitalTop_line':inst['source_start_line'],'source_update':'Full source-generated combinational settle plus shared uncore edge; no fitted latency'}
  if router:
   node['router_id']=int(re.search(r'_router_(\d+)Clock',inst['module'])[1]);text=(source/'rtl'/(inst['module']+'.sv')).read_text();node['inner_router_module']=re.search(r'^  (Router\w*) routers \(',text,re.M)[1];node['width_widgets']=[{'module':a,'instance':b}for a,b in re.findall(r'^  (\w+) (\w+) \(',text,re.M)if'width_widget'in b]
  nodes.append(node)
  for port,conn in inst['connections'].items():
   for net in identifiers(conn['expression']):
    widths[net]=max(widths.get(net,0),conn['width'])
    if conn['direction']=='output':producers[net]={'node':inst['name'],'port':port}
    else:consumers[net].append({'node':inst['name'],'port':port,'expression':conn['expression']})
 wire_widths={name:int(high)+1 if high else 1 for high,name in re.findall(r'^\s*wire\s+(?:\[(\d+):0\]\s+)?(\w+);',(source/'rtl/IrisNoCNetwork.sv').read_text(),re.M)}
 edges=[{'net':net,'wire_bits':wire_widths[net],'maximum_connected_port_width':widths[net],'producer':producers.get(net,{'node':'external_uncore_clock'if net==j['clock_source_net']else'external_physical_TL_or_reset','port':net}),'consumers':consumers.get(net,[{'node':'external_physical_TL_or_debug','port':net}]),'added_latency_edges':0}for net in sorted(set(producers)|set(consumers))]
 fields=j['physical_ports'];index={x['name']:(x['index']if x['direction']=='input'else 208+x['index'])for x in fields};channels=[]
 for inst in j['instances']:
  if'ToNoC'not in inst['module']:continue
  for port,c in inst['connections'].items():
   if not port.startswith('io_tilelink_')or not port.endswith('_valid'):continue
   ready=port[:-5]+'ready';assert ready in inst['connections'];v=c['expression'];r=inst['connections'][ready]['expression'];assert v in index and r in index,('Nontrivial physical handshake',v,r);channels.append({'instance':inst['name'],'fabric':'acd'if'_acd_'in inst['name']else'be','channel':port.split('_')[-2],'producer_direction':c['direction'],'valid_field':v,'ready_field':r,'valid_index':index[v],'ready_index':index[r]})
 coverage=[]
 for case in ['original9','control8','fenced9','peer','coherent']:
  counts=[0]*len(channels);cycles=[0]*len(channels)
  for tb,values in check.frames(case):
   if values[165]:continue
   for k,c in enumerate(channels):cycles[k]+=bool(values[c['valid_index']]);counts[k]+=bool(values[c['valid_index']]and values[c['ready_index']])
  rows=[{**{k:v for k,v in c.items()if not k.endswith('_index')},'valid_cycles':cycles[n],'accepted_TL_beats':counts[n]}for n,c in enumerate(channels)];coverage.append({'case':case,'endpoint_channels':rows,'accepted_beats_by_fabric':{fabric:sum(counts[k]for k,c in enumerate(channels)if c['fabric']==fabric)for fabric in['acd','be']}})
 memories=[]
 for file in(source/'rtl').glob('*.sv'):
  for high,depth in re.findall(r'reg\s+\[(\d+):0\]\s+Memory\[0:(\d+)\]',file.read_text()):memories.append({'module':file.stem,'word_bits':int(high)+1,'entries':int(depth)+1,'source_sha256':sha(file),'latency_policy':'Exact source RTL read/write and queue logic; not inferred solely from storage dimensions'})
 graph={'schema':'iris.complete_noc_source_graph.v1','extraction_sha256':sha(source/'extraction.json'),'source_FIR_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4','nodes':nodes,'signal_edges':edges,'native_storage_shapes':memories,'physical_TL_coverage':coverage,'coverage_counting':'Endpoint TL handshakes, including both fabric entry and exit; totals are not physical link flit counts or payload bytes','external_boundaries':['Tile/client CDCs and core/cache request generation','L2/cache/coherence managers','Peripherals and CLINT/PLIC','Serial-TL/DRAM/host memory path'],'NoC_complete_configured_instances':40,'whole_SoC_certified':False,'loaded_image_association':False,'idle_skipping':False,'hardware_contacted':False};(out/'graph.json').write_text(json.dumps(graph,indent=2)+'\n');print(json.dumps({'nodes':len(nodes),'signal_edges':len(edges),'storage_module_shapes':len(memories),'handshake_channels':len(channels),'coverage':[{k:x[k]for k in ['case','accepted_beats_by_fabric']}for x in coverage],'graph_sha256':sha(out/'graph.json')}))
if __name__=='__main__':main()

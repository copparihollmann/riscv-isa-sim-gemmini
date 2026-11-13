#!/usr/bin/env python3
"""Build physical external-boundary replay; joined readiness comes from source peers."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--model',type=Path,default=R/'build/memory-fabric-coupled-native-v4');p.add_argument('--context',type=Path,default=R/'build/memory-fabric-context-sdk-v2');p.add_argument('--observer',type=Path,default=R/'build/memory-fabric-observer-v1');p.add_argument('--output',type=Path,default=R/'build/memory-fabric-replay-v2');a=p.parse_args();out=a.output.resolve();model=a.model.resolve();ctx=a.context.resolve();observer=a.observer.resolve()
 if out.exists():raise ValueError('fresh replay output required')
 g=json.loads((R/'build/memory-fabric-graph-v1/graph.json').read_text());obs=json.loads((observer/'build.json').read_text());by_net={f['name']:f for f in obs['fields']};produced={f['global']['name'] for c in g['components'].values()for f in c['physical_ports']if f['direction']=='output'and f['global']['op']=='net'};external=sorted(n for n in by_net if n not in produced);assert len(external)==263
 def offset(e):
  if e['op']=='net':return by_net[e['name']]['word_offset']+1
  raise ValueError('observation requires an actual source net '+str(e))
 bindings=[]
 for index,n in enumerate(external):
  f=by_net[n];bindings.append([f['word_offset']+1,index,f['word_count'],f['width']])
 rules=[];skipped=[];resets=sorted(f['word_offset']+1 for f in obs['fields']if f['name'].endswith('_reset')or f['name'].endswith('/reset'));output_index=0;aux=None
 for name,c in g['components'].items():
  fields={f['name']:f for f in c['physical_ports']};off=lambda n:offset(fields[n]['global'])if n in fields and fields[n]['global']['op']=='net'else -1
  if name=='rocket_cache':aux=off('io_tlb_port_req_valid')
  for f in c['physical_ports']:
   if f['direction']!='output':continue
   index=output_index;output_index+=1;field=f['name'];valid=flag=opcode=-1;kind=0;reason='source-defined control output'
   if f['global']['op']=='unconnected':skipped.append({'component':name,'field':field,'reason':'source output is physically unconnected above DCache'});continue
   if name=='rocket_tile'and field=='auto_buffer_out_d_ready':
    valid=off('auto_buffer_out_d_valid');reason='Rocket source TLXbar.sv301 ready selects by D.source even while D.valid=0; source253/263/275 gate all D valid outputs and AsyncQueueSink only pops on valid&&ready. Compare ready only for a real D packet; raw invalid source may be unwritten FIFO RAM.'
   elif re.search(r'_[abcde]_mem_[0-3]_',field):kind=9;reason='opaque unreset async FIFO raw slot payload; decoded TL boundaries/control are checked separately'
   elif '_bits_'in field:
    prefix,payload=field.split('_bits_',1);valid=off(prefix+'_valid');opcode=off(prefix+'_bits_opcode')
    if field.startswith('io_cpu_resp_bits_'):
     valid=off('io_cpu_resp_valid');reason='CPU response payload while response valid'
     if payload in ['data','data_word_bypass','data_raw']:flag=off('io_cpu_resp_bits_has_data')
     elif payload=='store_data':kind=4;opcode=off('io_cpu_resp_bits_cmd')
    elif field.startswith('io_ptw_req_bits_'):valid=off('io_ptw_req_valid');reason='PTW request payload only while source request valid'
    else:
     channel=prefix.rsplit('_',1)[-1];reason='TL payload while source channel valid'
     if valid<0:raise ValueError('unclassified source payload '+str((name,field)))
     if payload=='data':
      kind={'a':1,'c':2,'d':3}.get(channel,9)
      if kind==9:reason='TL channel carries no data for this source specialization'
   elif field.startswith('io_tlb_port_s1_resp_'):kind=9;reason='inactive auxiliary TLB payload in scalar reference corpus; active requests explicitly refused'
   rules.append({'frame':offset(f['global']),'index':index,'words':(f['width']+63)//64,'valid':valid,'flag':flag,'opcode':opcode,'kind':kind,'name':name+'::'+field,'reason':reason})
 assert aux is not None and aux>=0;assert output_index==1046
 out.mkdir();code='#pragma once\nstatic constexpr unsigned FRAME_WORDS='+str(obs['frame_words'])+';\nstatic constexpr unsigned AUX_TLB_VALID='+str(aux)+';\nstatic const std::vector<unsigned>reset_offsets={'+','.join(map(str,resets))+'};\n'
 code+='static const std::vector<Binding>bindings={'+','.join('{'+','.join(map(str,b))+'}'for b in bindings)+'};\n'
 code+='static const std::vector<Rule>rules={'+','.join('{'+','.join(str(r[k])for k in ['frame','index','words','valid','flag','opcode','kind'])+','+json.dumps(r['name'])+'}'for r in rules)+'};\n';(out/'memory_fabric_replay_schema.hpp').write_text(code)
 (out/'qualification.json').write_text(json.dumps({'schema':'iris.memory_fabric_reference_qualification.v1','rules':rules,'skipped_unconnected':skipped,'input_boundary':'Only263 true external physical nets.730 joined source nets/20slices are computed by source peers, never replayed as readiness/state.','reset':'All edges from first actual asserted reset; compare after all source resets deassert.','opaque_async_FIFO_payload':'Raw unwritten slot storage excluded. Both decoded TL boundaries and public FIFO control/pointers remain compared; no fake known-zero storage.','two_state_boundary_values_are_not_four_state_certification':True},indent=2)+'\n')
 sdks=[model/'sdk',ctx/'cache/sdk',ctx/'noc/sdk',ctx/'adapters/sdk'];libs=[model/'sdk/libiris_memory_fabric.a',ctx/'cache/sdk/libiris_cache_hierarchy.a',ctx/'noc/sdk/libiris_noc.a',ctx/'adapters/sdk/libiris_memory_adapters.a'];argv=['/usr/bin/g++','-O3','-std=c++20',*['-I'+str(d)for d in sdks],'-I'+str(out),str(R/'timing/memory_fabric_replay.cpp'),*map(str,libs),'-pthread','-latomic','-lz','-o',str(out/'replay')]
 with(out/'compile.log').open('w')as f:status=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT).returncode
 if status:raise RuntimeError('memory replay compile failed')
 inputs=[Path(__file__),R/'timing/memory_fabric_replay.cpp',R/'build/memory-fabric-graph-v1/graph.json',observer/'build.json',model/'build.json',out/'memory_fabric_replay_schema.hpp',out/'qualification.json',*libs,Path('/usr/bin/g++')];receipt={'schema':'iris.memory_fabric_replay_build.v1','argv':argv,'binary_sha256':sha(out/'replay'),'input_sha256':{str(p):sha(p)for p in inputs},'external_fields':len(bindings),'source_rules':len(rules),'hardware_contacted':False,'timing_certified':False};(out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'binary_sha256':receipt['binary_sha256'],'source_rules':len(rules),'report_sha256':sha(out/'build.json')}))
if __name__=='__main__':main()

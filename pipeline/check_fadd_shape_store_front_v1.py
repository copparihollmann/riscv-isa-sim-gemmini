#!/usr/bin/env python3
"""Executed-ELF typed publication, coherence and IRQ checks for optional stores."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def events(p):return[json.loads(x)for x in p.read_text().splitlines()]
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);base=json.loads((ROOT/'build/rocket-packet-native-first-v1/report.json').read_text())['argv'];source=ROOT/'build/rocket-packet-native-first-v1/first.fixture';runs={};reports={};before_peers=after_peers=opaque=0;published_widths=set();compressed=set();all_IRQ=set()
 for name,history in[('parent','bounded'),('off','bounded'),('on','bounded'),('on-full','full'),('IRQ','bounded'),('IRQ-full','full')]:
  d=out/name;d.mkdir();parent=name=='parent';b=ROOT/'build/fadd-shape-frozen-7de1c02d/spike'if parent else a.binary.resolve();u=ROOT/'build/fadd-shape-frozen-7de1c02d/libsifive_uart.so'if parent else a.uart.resolve();irq=name.startswith('IRQ');enabled=name not in('parent','off');elf=ROOT/('build/empirical-owned-store-IRQ-guest-v2/guest.elf'if irq else'build/empirical-owned-store-guest-v2/guest.elf');text=source.read_text()+'\nempirical_scalar_fadd source-HSD-pipeline-v1\nempirical_vme_work source-shape-subtiles-v1\n';text=text.replace('unfitted-bounded-v1 bounded','unfitted-bounded-v1 '+history)
  if enabled:text+='\nempirical_store_front owned-dirty-L1-COM-v1\n'
  if irq:
   for h in range(3):text+=f'resource empirical.test-store{h} 1\nempirical_family {h} memory.DRAM.store empirical.test-store{h} 20 0 1 SYNTHETIC_STORE_IRQ '+('0'*64)+' core_cycles\n'
  fixture=d/'fixture';fixture.write_text(text);argv=[x for x in base if not x.startswith(('--iris-timing-fixture=','--iris-timing-trace='))];argv[0]=str(b);argv=['--extlib='+str(u)if x.startswith('--extlib=')else x for x in argv];argv[-1]=str(elf);argv[-1:-1]=['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(d/'graph.json')];inputs=[Path(__file__).resolve(),b,u,fixture,elf,source];hashes={str(x):sha(x)for x in inputs};t=time.monotonic();r=subprocess.run(argv,capture_output=True,env=dict(os.environ,IRIS_EMPIRICAL_ASYNC_TRACE=str(d/'async.jsonl'),IRIS_EMPIRICAL_FEATURES=str(d/'features.jsonl')),timeout=120);elapsed=time.monotonic()-t;(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr);assert r.returncode==0,(name,r.stderr.decode());numeric=[list(map(int,x.split()[1:]))for x in r.stdout.decode().splitlines()if x.startswith('IRIS_OWNED_STORE ')];assert len(numeric)==3 and all(row[1]==0 and row[2]==int(irq) and row[3]==(1040 if irq else 305419896)for row in numeric),numeric
  graph=json.loads((d/'graph.json').read_text());trace=events(d/'async.jsonl');observed={};stores={};defers={};pubs={};counts={}
  guest_build=json.loads((elf.parent/'build.json').read_text());nm=Path(guest_build['argv'][0]).with_name('riscv64-unknown-elf-nm');symbols=subprocess.run([str(nm),'-S',str(elf)],check=True,capture_output=True).stdout.decode();(d/'symbols.txt').write_text(symbols);targets=[]
  for line in symbols.splitlines():
   fields=line.split()
   if len(fields)==4 and fields[3]in('private_lines','shared'):targets.append((int(fields[0],16),int(fields[0],16)+int(fields[1],16)))
  assert len(targets)==2,targets

  if enabled:
   metrics=graph['owned_store_front']['per_hart'];assert all(x['RRD_accepted']>0 and x['published']>0 and not x['pending_accepted_response']for x in metrics)
   if irq:all_IRQ.update(h for h,m in enumerate(metrics)if m['IRQ_pending_before_publication']>0)
   for e in trace:
    key=(e['hart'],e.get('instruction',-1))
    if e['event']=='store_memory_observation':
     observed.setdefault(key,{})[e['phase']]=e
     if e['phase']=='after-publication':
      mask=(1<<(8*e['bytes']))-1;assert e['memory_known']&mask==e['source_known']&mask;assert(e['memory_value']^e['source_value'])&e['source_known']&mask==0;published_widths.add(e['bytes']);raw=e['raw']
      if(raw&3)!=3:compressed.add((raw&3,raw>>13))
      if e['source_known']&mask!=mask:opaque+=1
    elif e['event']=='store_defer':assert key not in defers;defers[key]=e
    elif e['event']=='store_publish':assert key not in pubs;pubs[key]=e
   assert set(pubs)=={k for k,v in observed.items()if'after-publication'in v}
   for key,e in defers.items():
    assert key in pubs and pubs[key]['cycle']>e['cycle'];o=observed[key];assert set(o)=={'accepted-deferred-COM','before-deferred-publication','after-publication'};assert o['before-deferred-publication']['cycle']==pubs[key]['cycle'];assert o['after-publication']['COM_node']==e['response']
   if history=='full':
    nodes={x['id']:x for x in graph['events']};accepted=[x for x in trace if x['event']=='scalar_cache_intent'];peerloads=[x for x in trace if x['event']=='pipeline_cache_load_value']
    for key,pub in pubs.items():
     o=observed[key]['after-publication'];node=nodes[o['COM_node']];assert node['completed']and node['end']==pub['cycle']and node['bytes']==pub['bytes']
    for key,e in defers.items():
     node=nodes[e['response']];old=nodes[e['old_COM']];assert old['completed']and old['bytes']==0 and node['completed']and node['bytes']==e['bytes']and not node.get('cancelled',False);assert node['start']>=e['cycle']and node['end']==pubs[key]['cycle']
     if not e['owned_at_COM']:
      assert len(node['deps'])==e['waiting_for_owners'];prior=[x for x in accepted if x['node']in node['deps']and x['hart']!=e['hart']and x['address']//64==e['address']//64];before_peers+=len(prior)
     for peer in accepted:
      if peer['hart']!=e['hart']and peer['address']//64==e['address']//64 and e['response']in peer['dependencies']:
       peer_node=nodes[peer['node']];assert peer_node['end']>=node['end'];after_peers+=1
    # Replay actual response-order values on every fully observed target byte.
    state={};load_checks=0
    for e in trace:
     if e['event']=='store_memory_observation'and e['phase']=='after-publication':write=True;value=e['memory_value'];known=e['memory_known']
     elif e['event']=='scalar_cache_store_value':write=True;value=e['value'];known=e['known']
     elif e['event']in('scalar_cache_load_value','pipeline_cache_load_value'):write=False;value=e['value'];known=e['known']
     else:continue
     for i in range(e['bytes']):
      at=e['address']+i
      if not any(lo<=at<hi for lo,hi in targets):continue
      byte=(value>>(8*i))&255;mask=(known>>(8*i))&255
      if write:state[at]=(byte,mask)
      elif at in state:expected,em=state[at];assert ((byte^expected)&mask&em)==0,(name,e,expected,em);assert mask&em==em,(name,e,mask,em);load_checks+=1
    counts['response_order_scope']='ELF private_lines/shared only; runtime barrier AMOs excluded';counts['observed_response_order_load_bytes']=load_checks;assert load_checks>0
  assert all(sha(p)==v for p,v in hashes.items());runs[name]={'stdout':r.stdout,'stderr':r.stderr,'prefix':(d/'features.jsonl').read_bytes(),'trace':(d/'async.jsonl').read_bytes(),'graph':graph};report={'schema':'iris.empirical.owned_store_actual_ELF.v1','pass':True,'argv':argv,'host_seconds':elapsed,'history':history,'input_sha256':hashes,'numeric':numeric,'deferred_accepted_stores':len(defers),'published_stores':len(pubs),'counts':counts,'scope':'V6 approximate intent-time ownership and simulated COM effects; no RTL coherence/timing qualification'};(d/'report.json').write_text(json.dumps(report,indent=2)+'\n');reports[name]=sha(d/'report.json');print(name,elapsed,len(defers),flush=True)
 assert runs['parent']==runs['off'],'storefrontOFF differs from7de'
 for b,f in[('on','on-full'),('IRQ','IRQ-full')]:
  for key in['stdout','stderr','prefix','trace']:assert runs[b][key]==runs[f][key],(b,key)
  for key in['cycles','retired_instructions','per_hart_features','per_hart_memory_features','owned_store_front']:assert runs[b]['graph'][key]==runs[f]['graph'][key],(b,key)
 assert published_widths=={1,2,4,8}and compressed.issuperset({(0,6),(0,7),(2,6),(2,7)}),(published_widths,compressed)
 assert opaque>=3 and all_IRQ=={0,1,2},(opaque,all_IRQ)
 assert before_peers>0 and after_peers>0,(before_peers,after_peers)
 result={'schema':'iris.empirical.owned_store_native_suite.v1','pass':True,'binary_sha256':sha(a.binary),'uart_sha256':sha(a.uart),'OFF_7de_byte_parity':True,'bounded_full_guest_counter_prefix_trace_parity':True,'integer_widths':sorted(published_widths),'compressed_store_quadrant_funct3':sorted(compressed),'opaque_publications_checked':opaque,'all3_IRQ_pending_before_owned_store_publication':True,'prior_peer_actor_dependencies_checked':before_peers,'later_peer_intents_waiting_on_store_checked':after_peers,'reports':reports,'timing_certified':False,'physical_coherence_qualified':False};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()

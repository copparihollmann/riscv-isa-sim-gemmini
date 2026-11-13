#!/usr/bin/env python3
"""Close complete-network physical replays, signatures, phase and subset proofs."""
import argparse,collections,hashlib,itertools,json,statistics,subprocess
from pathlib import Path
import noc_network_check as check
R=Path(__file__).resolve().parents[1];REPLAY=R/'build/noc-network-replay-v3';NATIVE=R/'build/noc-network-native-v3/noc-network';SDK=R/'build/noc-network-sdk-v1';LOCAL=R/'build/noc-router-component-v1-final';CAP=R/'build/rtl-memory-return-path-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(argv,body,out,name):
 q=subprocess.run(list(map(str,argv)),input=body,text=True,capture_output=True,timeout=60);(out/(name+'.stdout')).write_text(q.stdout);(out/(name+'.stderr')).write_text(q.stderr);return q
def architecture(case):
 receipt=json.loads((check.RTL/(case+'.json')).read_text());assert not receipt['timed_out'] and receipt['stderr_sha256']==sha(check.RTL/(case+'.stderr'))
 if case=='original9':
  assert receipt['exit_status']==1;old=(CAP/'build/rtl-loader-diag/vector-memory-h2-9-va2.stderr').read_text().splitlines();new=(check.RTL/(case+'.stderr')).read_text().splitlines();transcripts=[]
  for prefix in ['RTL_MEMTRACE ','RTL_NOC ','RTL_VA ','RTL_VA2 ']:
   a=[x for x in old if x.startswith(prefix)];b=[x for x in new if x.startswith(prefix)];assert a and a==b,('Original trigger changed',prefix);transcripts.append({'prefix':prefix,'lines':len(a),'sha256':hashlib.sha256(('\n'.join(a)+'\n').encode()).hexdigest()})
  return {'case':case,'bounded_incomplete':True,'tb_limit':130000,'preserved_original_transcripts':transcripts}
 words=[int(x,16)for x in(check.RTL/(case+'.signature')).read_text().splitlines()];kind=6 if case=='coherent'else 5 if case=='peer'else 4;assert receipt['exit_status']==0 and len(words)==28 and words[:4]==[0x4952495350524f42,1,kind,0];harts=[]
 for h in range(3):
  values=words[4+8*h:12+8*h];count=84 if case=='coherent'else (64 if case=='control8'else 72)if h==2 else 0;assert values[3:6]==[0,0,0]and values[6:]==[count,1];harts.append(dict(zip(['stage','actual','expected','cause','pc','tval','checks','done'],values)))
 return {'case':case,'coherent_TSI_signature_sha256':sha(check.RTL/(case+'.signature')),'kind':kind,'harts':harts}
def independent_mix(case):
 outputs=[x for x in check.schema()if x['direction']=='output'];indices={x['name']:208+x['index']for x in outputs};gates=[]
 for x in outputs:gates.append(indices[x['name'].split('_bits_')[0]+'_valid']if'_bits_'in x['name']else None)
 h=14695981039346656037;mask=(1<<64)-1
 for tb,values in check.frames(case):
  if values[165]:continue
  h=((h^tb)*1099511628211)&mask
  for index,gate in enumerate(gates):
   if gate is None or values[gate]:h=((h^values[208+index])*1099511628211)&mask
 return h
def subset(case,out):
 import noc_router_check as old
 labels,_=old.expected(collections.defaultdict(int));label={n:i for i,n in enumerate(labels)};q=run([LOCAL/'noc-router'],(LOCAL/(case+'.input')).read_text(),out,'handwritten-'+case);assert q.returncode==0 and q.stdout==(LOCAL/(case+'.stdout')).read_text();rows=iter([[int(x)for x in line.split()]for line in q.stdout.splitlines()]);current=next(rows,None);fields=[x for x in check.schema()if x['direction']=='output'];indices={x['name']:x['index']+1 for x in fields};prefix='_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_debug_out_';va=indices[prefix+'va_stall_0'];sa=indices[prefix+'sa_stall_0'];matched=0
 with(REPLAY/(case+'-step.stdout')).open()as f:
  for line in f:
   if current is None:break
   actual=[int(x)for x in line.split()]
   if actual[0]<current[0]:continue
   assert actual[0]==current[0];r={name:current[index]for name,index in label.items()};waiting=bin(r['waiting_vcs']).count('1');expected_va=waiting-int(bool(r['input_grants']&1));switch_valids=sum(r['vc'+str(k)+'_state']==3 and r['vc'+str(k)+'_local'] and r['egress_count']==0 and r['vc'+str(k)+'_count']>0 for k in range(6));expected_sa=switch_valids-bin(r['popped_vcs']).count('1');assert actual[va]==expected_va and actual[sa]==expected_sa,(case,actual[0],actual[va],expected_va,actual[sa],expected_sa);matched+=1;current=next(rows,None)
 assert current is None
 return {'case':case,'edges':matched,'independent_VA_SA_checks':2*matched,'handwritten_native_sha256':sha(LOCAL/'noc-router'),'exact_old_handwritten_stdout':True,'scope':'Local source-derived FIFO/arbiter model projected to full-network node5 VA/SA outputs; not an independent model of all other routers'}
def snapshot(out,source_id):
 lines=(REPLAY/'original9-step.input').read_text().splitlines();cut=45000;file=out/'active.snapshot';body='\n'.join(lines[:cut])+f'\nsave {file}\n'+'\n'.join(lines[cut:])+'\n';q=run([NATIVE,'--seed','1'],body,out,'snapshot-continuous');assert q.returncode==0;expected='\n'.join(q.stdout.splitlines()[cut:])+'\n';q=run([NATIVE,'--seed','42'],f'restore {file}\n'+'\n'.join(lines[cut:])+'\n',out,'snapshot-restored');assert q.returncode==0 and q.stdout==expected;data=file.read_bytes();assert data.count(source_id.encode())==1;bad=out/'wrong-source.snapshot';bad.write_bytes(data.replace(source_id.encode(),b'0'*64));q=run([NATIVE,'--seed','1'],f'restore {bad}\n',out,'reject-snapshot-source');assert q.returncode==2 and 'source identity mismatch'in q.stderr
 return {'snapshot_sha256':sha(file),'after_edges':cut,'exact_continuation_edges':len(lines)-cut,'restore_seed':42,'wrong_source_refused':True,'external_TL_inputs_replayed_not_restored':True}
def corruptions(out):
 fields=[x for x in check.schema()if x['direction']=='output'];cases=[('readiness',next(x['index']for x in fields if x['name'].endswith('_ready'))),('VA-debug',next(x['index']for x in fields if'debug_out_va_stall'in x['name'])),('SA-debug',next(x['index']for x in fields if'debug_out_sa_stall'in x['name'])),('TL-data',next(x['index']for x in fields if x['name'].endswith('_d_bits_data'))),('TL-source',next(x['index']for x in fields if x['name'].endswith('_d_bits_source')))];actual=(REPLAY/'coherent-step.stdout').read_text().splitlines();lookup={x['name']:208+x['index']for x in fields};proofs=[]
 for label,index in cases:
  field=fields[index];gate=lookup[field['name'].split('_bits_')[0]+'_valid']if'_bits_'in field['name']else None;chosen=next((n,tb)for n,(tb,values)in enumerate(check.frames('coherent'))if not values[165]and(gate is None or values[gate]));n,tb=chosen;copy=list(actual);numbers=copy[n].split();numbers[index+1]=str(int(numbers[index+1])^1);copy[n]=' '.join(numbers);file=out/('corrupt-'+label+'.stdout');file.write_text('\n'.join(copy)+'\n')
  try:check.compare('coherent',file)
  except ValueError as error:proofs.append({'mutation':label,'field':field['name'],'tb':tb,'rejection':str(error)})
  else:raise AssertionError('Missed corruption '+label)
 return proofs
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=R/'build/noc-network-accept-v1');a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('Fresh acceptance output required')
 out.mkdir();replays=[];architecture_proofs=[];subsets=[];benchmark_proofs=[]
 for case in ['original9','control8','fenced9','peer','coherent']:
  proof=json.loads((REPLAY/(case+'-step.json')).read_text());assert proof['native_sha256']==sha(NATIVE)and proof['stdout_sha256']==sha(REPLAY/(case+'-step.stdout'));proof.update(check.compare(case,REPLAY/(case+'-step.stdout')));replays.append(proof);architecture_proofs.append(architecture(case))
  if case in ['original9','control8','fenced9']:subsets.append(subset(case,out))
  if case not in ['control8','coherent']:continue
  digest=independent_mix(case)
  for mode in ['step','revised']:
   report=json.loads((SDK/(case+'-'+mode+'.stdout')).read_text());assert all(x['defined_field_mix64']==digest for x in report['passes']);report.update(independent_whole_RTL_mix64=digest,median_edges_per_second=statistics.median(x['edges_per_second']for x in report['passes']),case=case);benchmark_proofs.append(report)
 # Phased/repeated evaluation must produce every identical physical output,
 # including inactive data, compared with the ordinary step stream.
 phase_proofs=[]
 for case,mode in [('control8','phased'),('coherent','repeat')]:
  proof=check.run(case,NATIVE,out,mode);assert sha(out/(case+'-'+mode+'.stdout'))==sha(REPLAY/(case+'-step.stdout'));phase_proofs.append(proof)
 source_id=json.loads((R/'build/noc-network-native-v3/build.json').read_text())['source_identity'];snap=snapshot(out,source_id);q=run([SDK/'benchmark','selftest',REPLAY/'control8-step.input',out/'lifecycle.snapshot'],'',out,'lifecycle');assert q.returncode==0;lifecycle=json.loads(q.stdout);assert lifecycle['lifecycle_rejections']==8
 report={'schema':'iris.complete_network_accept.v1','pass':True,'native_sha256':sha(NATIVE),'source_identity':source_id,'actual_reset_replays':replays,'edges':sum(x['edges']for x in replays),'physical_signal_comparisons':sum(x['physical_signal_comparisons']for x in replays),'architectural_proofs':architecture_proofs,'handwritten_local_projection':subsets,'phase_proofs':phase_proofs,'readiness_revision_and_speed':benchmark_proofs,'active_snapshot':snap,'lifecycle':lifecycle,'output_corruptions':corruptions(out),'internal_state_or_eligibility_inputs':False,'idle_skipping':False,'whole_SoC_or_deployed_image_certified':False,'heldout_2percent_certified':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'edges':report['edges'],'physical_checks':report['physical_signal_comparisons'],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()

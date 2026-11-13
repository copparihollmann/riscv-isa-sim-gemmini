#!/usr/bin/env python3
"""Independent full-boundary, architectural-control and snapshot acceptance."""
import argparse,collections,hashlib,json,statistics,subprocess
from pathlib import Path
import noc_full_router_check as check
R=Path(__file__).resolve().parents[1];CAP=R/'build/rtl-memory-return-path-v1-final';LOCAL=R/'build/noc-router-component-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def invoke(argv,body,out,name):
 q=subprocess.run(list(map(str,argv)),input=body,text=True,capture_output=True,timeout=30)
 (out/(name+'.input')).write_text(body);(out/(name+'.stdout')).write_text(q.stdout);(out/(name+'.stderr')).write_text(q.stderr);return q
def digest(rows,names):
 h=14695981039346656037
 for x in rows:
  if x['i_reset']:continue
  keys=['tb']+names
  for prefix in ['o_net0_','o_net1_','o_local_']:
   if not x[prefix+'valid']:keys=[k for k in keys if not k.startswith(prefix) or k==prefix+'valid']
  for key in keys:
   value=x[key]
   for n in range(8):h=((h^((value>>(8*n))&255))*1099511628211)&((1<<64)-1)
 return h
def architecture(case):
 receipt=json.loads((check.RTL/(case+'.json')).read_text());assert not receipt['timed_out'];assert receipt['stderr_sha256']==sha(check.RTL/(case+'.stderr'))
 if case=='original9':
  assert receipt['exit_status']==1
  old=(CAP/'build/rtl-loader-diag/vector-memory-h2-9-va2.stderr').read_text().splitlines();new=(check.RTL/(case+'.stderr')).read_text().splitlines();items=[]
  for prefix in ['RTL_MEMTRACE ','RTL_NOC ','RTL_VA ','RTL_VA2 ']:
   a=[x for x in old if x.startswith(prefix)];b=[x for x in new if x.startswith(prefix)];assert a and a==b,('Architectural/observer transcript changed',prefix);items.append({'prefix':prefix,'exact_lines':len(a),'sha256':hashlib.sha256(('\n'.join(a)+'\n').encode()).hexdigest()})
  return {'case':case,'bounded_incomplete':True,'tb_limit':130000,'old_transcripts_byte_equal':items,'deployed_fpga_inference':False}
 assert receipt['exit_status']==0
 words=[int(x,16) for x in (check.RTL/(case+'.signature')).read_text().splitlines()];assert len(words)==28 and words[:4]==[0x4952495350524f42,1,5 if case=='peer' else 4,0]
 harts=[]
 for hart in range(3):
  values=words[4+8*hart:12+8*hart];assert values[3:6]==[0,0,0] and values[7]==1
  expected=(72 if case in ['peer','fenced9'] else 64) if hart==2 else 0;assert values[6]==expected
  harts.append(dict(zip(['stage','actual','expected','cause','pc','tval','checks','done'],values)))
 return {'case':case,'coherent_tsi_signature_sha256':sha(check.RTL/(case+'.signature')),'kind':words[2],'harts':harts,'full_hardware_certification':False}
def subset(rows,actual,output_names,case,out):
 # Independently handwritten local branch uses the same exact saved RTL/ELF.
 # Rerun its frozen executable/inputs, then compare physical ports to this full
 # native model over the common stable window, rather than trusting old PASS.
 argv=[LOCAL/'noc-router'];q=invoke(argv,(LOCAL/(case+'.input')).read_text(),out,'local-'+case);assert q.returncode==0 and q.stdout==(LOCAL/(case+'.stdout')).read_text()
 old=[[int(v) for v in line.split()] for line in q.stdout.splitlines()];mapped={x['tb']:dict(zip(output_names,a[1:])) for x,a in zip(rows,actual)};count=0
 import noc_router_check as local
 labels,_=local.expected(collections.defaultdict(int));indices={n:k for k,n in enumerate(labels)}
 for line in old:
  tb=line[0];full=mapped[tb]
  for a,b in [('popped_vcs','o_credit0'),('freed_vcs','o_free0'),('out_valid','o_local_valid')]:assert line[indices[a]]==full[b],(case,tb,a);count+=1
  if full['o_local_valid']:
   packed=sum(line[indices['out_word'+str(w)]]<<(32*w) for w in range(3));assert packed&1==full['o_local_head'] and (packed>>1)&1==full['o_local_tail'];assert (packed>>2)==sum(full['o_local_payload'+str(w)]<<(32*w) for w in range(3));count+=5
 return {'case':case,'edges':len(old),'physical_checks':count,'frozen_handwritten_native_sha256':sha(LOCAL/'noc-router'),'exact_old_native_stdout':True}
def guards(binary,rows,names,out):
 inputs=[x['name'] for x in json.loads((R/'timing/noc_full_router_observer_fields.json').read_text())['fields'][:44]];base=next(x for x in rows if not x['i_reset'] and x['i_net0_valid']);tests=[]
 for label,key,value,message in [('payload-width','i_net0_payload2',512,'elaborated width'),('credit-width','i_credit0',64,'six VCs'),('undeclared-network-flow','i_net0_vnet',3,'routing table'),('undeclared-local-A','i_local0_egress_id',31,'flow set'),('undeclared-local-C','i_local1_egress_id',0,'flow set')]:
  x=dict(base);x[key]=value
  if key.startswith('i_local'):x[key[:8]+'_valid']=1
  body='step '+str(x['tb'])+' '+' '.join(str(x[n]) for n in inputs)+'\n';q=invoke([binary,'--seed','1'],body,out,'reject-'+label);assert q.returncode!=0 and message in q.stderr,(label,q.stdout,q.stderr);tests.append({'name':label,'exit_status':q.returncode,'diagnostic':q.stderr.strip()})
 for label,body in [('negative','step 3 -1\n'),('missing-field','step 3 0\n')]:
  q=invoke([binary,'--seed','1'],body,out,'reject-'+label);assert q.returncode!=0;tests.append({'name':label,'exit_status':q.returncode,'diagnostic':q.stderr.strip()})
 return tests
def corruptions(rows,actual,names,out):
 tests=[]
 for name,key in [('network-nonlocal-payload','o_net1_payload0'),('local-return-payload','o_local_payload0'),('peer-credit','o_credit1'),('local-ingress-ready','o_ingress_ready1'),('VA-debug','o_va0')]:
  idx=next(i for i,x in enumerate(rows) if not x['i_reset'] and (x['o_net1_valid'] if name=='network-nonlocal-payload' else x['o_local_valid'] if name=='local-return-payload' else x[key] if name=='peer-credit' else True))
  mutated=list(actual);mutated[idx]=list(mutated[idx]);mutated[idx][1+names.index(key)]^=1
  try:check.compare(mutated,rows,names)
  except ValueError as e:tests.append({'name':name,'tb':rows[idx]['tb'],'field':key,'rejection':str(e)})
  else:raise AssertionError('Missed corruption '+name)
 (out/'corruptions.json').write_text(json.dumps(tests,indent=2)+'\n');return tests
def snapshots(binary,body,out,source_id):
 lines=body.splitlines();cut=45000;path=out/'middle.snapshot';q=invoke([binary,'--seed','1'],'\n'.join(lines[:cut])+f'\nsave {path}\n'+'\n'.join(lines[cut:])+'\n',out,'snapshot-full');assert q.returncode==0
 expected='\n'.join(q.stdout.splitlines()[cut:])+'\n';q=invoke([binary,'--seed','42'],f'restore {path}\n'+'\n'.join(lines[cut:])+'\n',out,'snapshot-restored');assert q.returncode==0 and q.stdout==expected
 data=path.read_bytes();assert data.count(source_id.encode())==1;bad=out/'wrong-source.snapshot';bad.write_bytes(data.replace(source_id.encode(),b'0'*64));q=invoke([binary,'--seed','1'],f'restore {bad}\n',out,'reject-snapshot-source');assert q.returncode!=0 and 'source identity mismatch' in q.stderr
 return {'cut_after_edges':cut,'continuation_edges':len(lines)-cut,'exact_stdout_suffix':True,'snapshot_sha256':sha(path),'source_id':source_id,'restore_seed':42,'wrong_source_refused':True,'mode':'Same frozen generated native snapshot; no whole-RTL state import'}
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,default=R/'build/noc-full-router-v2/noc-full-router');p.add_argument('--benchmark',type=Path,default=R/'build/noc-full-router-benchmark-v2/benchmark');p.add_argument('--output',type=Path,default=R/'build/noc-full-router-accept-v2');a=p.parse_args();out=a.output.resolve();binary=a.binary.resolve()
 if out.exists():raise ValueError('Refuse to overwrite acceptance evidence')
 out.mkdir();results=[];architectural=[];subsets=[];benchmarks=[]
 for case in ['original9','control8','fenced9','peer']:
  results.append(check.run(case,binary,out));architectural.append(architecture(case));schema,rows=check.read_frames(case);names=[x['name'] for x in schema['fields'][schema['input_count']:]];actual=[[int(v) for v in x.split()] for x in (out/(case+'.stdout')).read_text().splitlines() if x and not x.startswith('-')]
  if case!='peer':subsets.append(subset(rows,actual,names,case,out))
  argv=[str(a.benchmark.resolve()),str(out/(case+'.input')),'7','1'];q=subprocess.run(argv,text=True,capture_output=True,timeout=30);(out/('benchmark-'+case+'.stdout')).write_text(q.stdout);(out/('benchmark-'+case+'.stderr')).write_text(q.stderr);q.check_returncode();j=json.loads(q.stdout);d=digest(rows,names);assert all(x['defined_output_fnv64']==d for x in j['passes']);j.update(case=case,argv=argv,independent_whole_rtl_digest=d,median_edges_per_second=statistics.median(x['edges_per_second'] for x in j['passes']));benchmarks.append(j)
  if case=='original9':snapshot=snapshots(binary,(out/(case+'.input')).read_text(),out,j['source_identity'])
  if case=='peer':guard_results=guards(binary,rows,names,out);corruption_results=corruptions(rows,actual,names,out);coverage={key:sum(x[key] for x in rows) for key in ['i_net0_valid','i_net1_valid','i_local0_valid','i_local1_valid','o_net0_valid','o_net1_valid','o_local_valid']};assert all(coverage[k] for k in coverage)
 report={'schema':'iris.full_router_accept.v2','pass':True,'binary_sha256':sha(binary),'benchmark_sha256':sha(a.benchmark),'source_identity':snapshot['source_id'],'replays':results,'architectural_controls':architectural,'handwritten_local_differentials':subsets,'snapshot':snapshot,'source_guards':guard_results,'comparator_corruptions':corruption_results,'peer_all_four_input_coverage':coverage,'benchmarks':benchmarks,'actual_reset_replay':True,'internal_state_or_eligibility_reinjection':False,'idle_skipping':False,'whole_NoC_certification':False,'SoC_MIPS_measured':False,'cycle_2percent_certification':False,'deployed_image_certification':False,'hardware_contacted':False}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json'),'edges':sum(x['edges'] for x in results),'comparisons':sum(x['physical_signal_comparisons'] for x in results),'median_edges_per_second':{x['case']:x['median_edges_per_second'] for x in benchmarks}}))
if __name__=='__main__':main()

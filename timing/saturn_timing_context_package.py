#!/usr/bin/env python3
"""Freeze/verify host-only context derivatives and real interleaving evidence."""
import argparse,hashlib,json,os,shutil,stat,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];FINAL=R/'build/saturn-timing-context-component-v1-final'
DEPS=[R/'build/saturn-timing-component-v1-final',R/'build/saturn-timing-fast-component-v1-final']
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def rel(p):return p.relative_to(R)if p.is_relative_to(R)else Path('external')/str(p).lstrip('/')
def package(out):
 if out.exists():raise ValueError('Preserve prior context capsule')
 dependency=[{'path':str(p),'report_sha256':sha(p/'report.json')}for p in DEPS];mapping={}
 for base in DEPS:
  for x in json.loads((base/'report.json').read_text())['artifacts']:mapping[x['source_path']]=(base,x['path'],x['sha256'])
 names=['saturn-timing-context-fast-v1','saturn-timing-context-reference-v1','saturn-timing-context-fast-proof-v1','saturn-timing-context-reference-proof-v1','saturn-timing-context-lifecycle-v1'];files={p for n in names for p in(R/'build'/n).rglob('*')if p.is_file()};files.update(p for p in(R/'timing').glob('saturn_timing_context*')if p.is_file());depinputs={};digests={}
 def cached(p):
  if p not in digests:digests[p]=sha(p)
  return digests[p]
 for receipt in list(files):
  if receipt.suffix!='.json':continue
  j=json.loads(receipt.read_text())
  if not isinstance(j,dict):continue
  for name,digest in j.get('input_sha256',{}).items():
   p=Path(name)
   if not p.is_absolute():continue
   base=next((b for b in DEPS if p.is_relative_to(b)),None)
   if base:
    assert cached(p)==digest;depinputs[name]={'dependency':str(base),'path':str(p.relative_to(base)),'sha256':digest};continue
   if name in mapping:
    b,r,d=mapping[name];assert d==digest and cached(b/r)==digest;depinputs[name]={'dependency':str(b),'path':r,'sha256':digest};continue
   assert p.is_file()and cached(p)==digest,('Changed context input',name);files.add(p)
 out.mkdir();index=[];dedup={}
 for p in sorted(files):
  target=out/rel(p);target.parent.mkdir(parents=True,exist_ok=True);digest=cached(p);mode=stat.S_IMODE(p.stat().st_mode);key=(digest,mode)
  if key in dedup:os.link(dedup[key],target)
  else:shutil.copy2(p,target);dedup[key]=target
  index.append({'path':str(rel(p)),'source_path':str(p),'bytes':target.stat().st_size,'mode':mode,'sha256':digest})
 proofs=[json.loads((R/'build'/('saturn-timing-context-'+v+'-proof-v1')/'report.json').read_text())for v in['fast','reference']];report={'schema':'iris.saturn_own_context_frozen_capsule.v1','pass':True,'dependencies':dependency,'dependency_input_mapping':depinputs,'variant_builds':['build/saturn-timing-context-'+v+'-v1/build.json'for v in['fast','reference']],'proofs':['build/saturn-timing-context-'+v+'-proof-v1/report.json'for v in['fast','reference']],'lifecycle_proof':'build/saturn-timing-context-lifecycle-v1/report.json','source_core_edges':sum(p['source_core_edges']for p in proofs),'qualified_field_checks':sum(p['qualified_field_checks']for p in proofs),'caller_context_checks':sum(p['caller_context_checks']for p in proofs),'artifact_count':len(index),'logical_bytes':sum(x['bytes']for x in index),'unique_file_bytes':sum(p.stat().st_size for p in dedup.values()),'artifacts':index,'source_RTL_or_model_objects_modified':False,'global_Verilator_RNG_stream_isolated':False,'raw_unreset_bit_order_invariance_claimed':False,'whole_SoC_or_2percent_certified':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({**{k:report[k]for k in['artifact_count','source_core_edges','qualified_field_checks','caller_context_checks','unique_file_bytes']},'report_sha256':sha(out/'report.json')}))
def verify(out):
 report=json.loads((out/'report.json').read_text());dependency={}
 for d in report['dependencies']:
  base=Path(d['path']);assert sha(base/'report.json')==d['report_sha256'];dependency[str(base)]=json.loads((base/'report.json').read_text())
 for x in report['artifacts']:
  p=out/x['path'];assert p.is_relative_to(out)and p.stat().st_size==x['bytes']and stat.S_IMODE(p.stat().st_mode)==x['mode']and sha(p)==x['sha256'],x['path']
 for name,x in report['dependency_input_mapping'].items():assert sha(Path(x['dependency'])/x['path'])==x['sha256'],name
 reference=Path(report['dependencies'][0]['path']);ref=dependency[str(reference)];libs=[reference/'external'/str(Path(p).parent).lstrip('/')for p in ref['runtime_libraries']['sdk']['libraries']];env=dict(os.environ,LD_LIBRARY_PATH=os.pathsep.join(map(str,libs)));checks=0;edges=0
 for receipt in report['proofs']:
  proof=json.loads((out/receipt).read_text());variant=proof['variant'];folder=out/'build'/('saturn-timing-context-'+variant+'-proof-v1')
  original=proof['original_host_leak_control'];command=original['argv'][:];command[0]=str(folder/'original-host-control');q=subprocess.run(command,capture_output=True,text=True,timeout=30,env=env);assert q.returncode==original['exit_status']and q.stderr==original['diagnostic']
  for row in proof['runs']:
   command=row['argv'][:];command[0]=str(folder/'context-test');q=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=300,env=env);assert q.returncode==0,q.stderr;fresh=next(json.loads(x.split(' ',1)[1])for x in q.stderr.splitlines()if x.startswith('SATURN_CONTEXT_RESULT '))
   for key,value in fresh.items():assert row[key]==value,(variant,key)
   checks+=fresh['qualified_field_checks'];edges+=fresh['source_core_edges']
 lifecycle=json.loads((out/report['lifecycle_proof']).read_text())
 for row in lifecycle['runs']:
  q=subprocess.run([str(out/'build/saturn-timing-context-lifecycle-v1'/row['variant'])],capture_output=True,text=True,timeout=30,env=env);assert q.returncode==0 and json.loads(q.stdout)==row['result']
 print(json.dumps({'pass':True,'capsule_sha256':sha(out/'report.json'),'artifacts_verified':len(report['artifacts']),'source_core_edges':edges,'qualified_field_checks':checks,'original_host_leak_controls':2,'both_variant_lifecycle_verified':True,'global_RNG_or_raw_unreset_invariance_claimed':False,'hardware_contacted':False}))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=FINAL);p.add_argument('--verify',action='store_true');a=p.parse_args();(verify if a.verify else package)(a.output.resolve())
if __name__=='__main__':main()

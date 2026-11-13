#!/usr/bin/env python3
"""Immutable causal-ownership/numeric-bridge closure and relocated verification."""
import argparse,hashlib,json,os,re,shutil,stat,subprocess,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
DEPS=[R/'build'/name for name in ['saturn-timing-activity-component-v1-final','saturn-timing-component-v1-final','saturn-timing-fast-component-v1-final','saturn-timing-context-component-v1-final']]
PROOF='build/saturn-timing-ownership-proof-v2/report.json'
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def rel(p):return p.relative_to(R)if p.is_relative_to(R)else Path('external')/str(p).lstrip('/')
def package(out):
 if out.exists():raise ValueError('Preserve prior ownership capsule')
 proof=json.loads((R/PROOF).read_text())
 if not proof['pass']:raise ValueError('A complete positive/corruption proof is required')
 names=['saturn-timing-ownership-source-v11','saturn-timing-ownership-sdk-v7','saturn-timing-ownership-rtl-v7','saturn-timing-ownership-capture-v4','saturn-timing-ownership-replay-v12','saturn-timing-ownership-proof-v2','saturn-timing-ownership-lifecycle-v3','saturn-timing-live-bridge-v2','saturn-timing-live-bridge-fixture-v4','saturn-timing-live-bridge-wrap-v2','saturn-timing-live-bridge-guards-v1']
 files={p for n in names for p in(R/'build'/n).rglob('*')if p.is_file()};files.update(p for pattern in ['saturn_timing_ownership*','saturn_timing_live_bridge*']for p in(R/'timing').glob(pattern)if p.is_file())
 # Keep meaningful development failures, without treating partial runs as proof.
 for name in ['build/saturn-timing-ownership-proof-v1.log','build/saturn-timing-ownership-proof-v1/runner.py','build/saturn-timing-live-bridge-fixture-v1/compute-16.stderr','build/saturn-timing-live-bridge-fixture-v2/compute-16.stderr','build/saturn-timing-ownership-replay-v4/vme.stderr']:
  if(R/name).is_file():files.add(R/name)
 cache={}
 def digest(p):
  if p not in cache:cache[p]=sha(p)
  return cache[p]
 by_digest={};mapping={};dependencies=[]
 for base in DEPS:
  dep=json.loads((base/'report.json').read_text());dependencies.append({'path':str(base),'report_sha256':digest(base/'report.json')})
  for row in dep['artifacts']:by_digest.setdefault(row['sha256'],(base,row['path']));mapping[(row['source_path'],row['sha256'])]=(base,row['path'])
 local={digest(p):p for p in files};resolved={};queue=list(files);seen=set()
 while queue:
  receipt=queue.pop()
  if receipt in seen or receipt.suffix!='.json':continue
  seen.add(receipt)
  try:j=json.loads(receipt.read_text())
  except(ValueError,UnicodeDecodeError):continue
  if not isinstance(j,dict):continue
  for name,wanted in j.get('input_sha256',{}).items():
   original=Path(name);key=name+'#'+wanted
   if not original.is_absolute()or key in resolved:continue
   match=mapping.get((name,wanted))or by_digest.get(wanted);containing=next((b for b in DEPS if original.is_relative_to(b)),None)
   if containing:
    if digest(original)!=wanted:raise ValueError('Changed frozen dependency '+name)
    match=(containing,str(original.relative_to(containing)))
   if match:
    base,path=match
    if digest(base/path)!=wanted:raise ValueError('Invalid frozen input mapping '+name)
    resolved[key]={'dependency':str(base),'path':path,'sha256':wanted};continue
   actual=original if original.is_file()and digest(original)==wanted else local.get(wanted)
   if actual is None:raise ValueError('Missing exact historical ownership input '+key)
   if actual not in files:files.add(actual);queue.append(actual);local[wanted]=actual
   resolved[key]={'path':str(rel(actual)),'sha256':wanted}
 runtime={}
 for label,name in [('replay','build/saturn-timing-ownership-replay-v12/replay'),('wholeRTL','build/saturn-timing-ownership-rtl-v7/simulator-ownership'),('guards','build/saturn-timing-live-bridge-guards-v1/guards')]:
  text=subprocess.check_output(['ldd',str(R/name)],text=True);libraries={}
  for token in re.findall(r'(?:=>\s+)?(/[^\s()]+)',text):
   p=Path(token)
   if p.is_file():files.add(p);libraries[token]=digest(p)
  runtime[label]={'ldd':text,'libraries':libraries}
 out.mkdir();artifacts=[];dedup={}
 for original in sorted(files):
  target=out/rel(original);target.parent.mkdir(parents=True,exist_ok=True);value=digest(original);mode=stat.S_IMODE(original.stat().st_mode);key=(value,mode)
  if key in dedup:os.link(dedup[key],target)
  else:shutil.copy2(original,target);dedup[key]=target
  artifacts.append({'path':str(rel(original)),'source_path':str(original),'sha256':value,'mode':mode,'bytes':target.stat().st_size})
 result={'schema':'iris.saturn_causal_ownership_frozen_capsule.v1','pass':True,'dependencies':dependencies,'input_resolution':resolved,'runtime_libraries':runtime,'proof':PROOF,'SDK':'build/saturn-timing-live-bridge-v2/sdk','source_numeric_SDK':'build/saturn-timing-ownership-sdk-v7/sdk','source_identity':json.loads((R/'build/saturn-timing-ownership-sdk-v7/build.json').read_text())['source_identity'],'positive_replays':len(proof['positive_runs']),'source_edges':sum(h['edges']for row in proof['positive_runs']for h in row['result']['harts']),'corruptions':len(proof['negative_controls']),'actual_native_CPU_ELF_execution':False,'full_SoC_or_FPGA_or_2percent_certified':False,'numeric_definedness_from_raw_payload_claimed':False,'artifacts':artifacts,'artifact_count':len(artifacts),'unique_file_bytes':sum(p.stat().st_size for p in dedup.values()),'hardware_contacted':False};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k]for k in ['source_edges','artifact_count','unique_file_bytes','positive_replays','corruptions']}|{'report_sha256':sha(out/'report.json')}))
def verify(out):
 report=json.loads((out/'report.json').read_text())
 for dep in report['dependencies']:
  if sha(Path(dep['path'])/'report.json')!=dep['report_sha256']:raise ValueError('Changed dependency receipt')
 for row in report['artifacts']:
  p=out/row['path']
  if not p.is_relative_to(out)or p.stat().st_size!=row['bytes']or stat.S_IMODE(p.stat().st_mode)!=row['mode']or sha(p)!=row['sha256']:raise ValueError('Changed capsule artifact '+row['path'])
 for key,row in report['input_resolution'].items():
  p=(Path(row['dependency'])if'dependency'in row else out)/row['path']
  if sha(p)!=row['sha256']:raise ValueError('Changed exact input '+key)
 libraries={out/rel(Path(name)).parent for r in report['runtime_libraries'].values()for name in r['libraries']};env=dict(os.environ,LD_LIBRARY_PATH=os.pathsep.join(map(str,sorted(libraries))));proof=json.loads((out/report['proof']).read_text());replay=out/'build/saturn-timing-ownership-replay-v12/replay';edges=events=0
 with tempfile.TemporaryDirectory(prefix='iris-owned-replay-')as temp:
  temp=Path(temp)
  for row in proof['positive_runs']:
   if row['seed']!=91:continue
   case=row['case'];cmd=[str(replay),str(out/'build/saturn-timing-ownership-capture-v4'/case/'activity.bin.gz'),str(out/'build/saturn-timing-ownership-capture-v4'/case/'ownership.bin.gz'),'91',str(temp/'events.gz')]
   with(temp/'stdout').open('w')as stdout,(temp/'stderr').open('w')as stderr:q=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=600,env=env,cwd=temp)
   if q.returncode:raise ValueError('Relocated source replay failed '+(temp/'stderr').read_text().splitlines()[-1])
   actual=json.loads((temp/'stdout').read_text().splitlines()[-1])
   if actual!=row['result']:raise ValueError('Relocated ownership event counts differ')
   expected=out/'build/saturn-timing-ownership-proof-v2'/(case+'-seed91-events.ndjson.gz')
   if sha(temp/'events.gz')!=sha(expected):raise ValueError('Relocated event bytes differ')
   edges+=sum(h['edges']for h in actual['harts']);events+=actual['events']
  for row in proof['negative_controls']:
   args=[str(out/rel(Path(arg)))if Path(arg).is_absolute()and Path(arg).is_relative_to(R)else arg for arg in row['argv']];args[-1]=str(temp/'negative-events.gz')
   with(temp/'stdout').open('w')as stdout,(temp/'stderr').open('w')as stderr:q=subprocess.run(args,stdout=stdout,stderr=stderr,timeout=300,env=env,cwd=temp)
   if q.returncode==0 or(temp/'stderr').read_text().splitlines()[-1]!=row['reason']:raise ValueError('Relocated corruption refusal differs '+row['name'])
  for name in ['build/saturn-timing-live-bridge-guards-v1/guards','build/saturn-timing-ownership-lifecycle-v3/lifecycle']:
   q=subprocess.run([str(out/name)],capture_output=True,text=True,timeout=60,env=env,cwd=temp)
   if q.returncode:raise ValueError('Relocated lifecycle/phase guard failed '+q.stderr)
 print(json.dumps({'pass':True,'capsule_sha256':sha(out/'report.json'),'artifacts_verified':len(report['artifacts']),'fresh_source_edges':edges,'fresh_owned_events':events,'fresh_corruption_refusals':len(proof['negative_controls']),'fresh_lifecycle_and_phase_guards':True,'byte_identical_events':True,'hardware_contacted':False}))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();(verify if a.verify else package)(a.output.resolve())
if __name__=='__main__':main()

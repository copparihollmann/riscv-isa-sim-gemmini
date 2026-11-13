#!/usr/bin/env python3
"""Freeze activity source/tool closure and independently replay archived inputs."""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

R=Path(__file__).resolve().parents[1]
DEPS=[R/'build/saturn-timing-component-v1-final',R/'build/saturn-timing-fast-component-v1-final',R/'build/saturn-timing-context-component-v1-final']
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as stream:
  for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
 return h.hexdigest()
def rel(path):return path.relative_to(R)if path.is_relative_to(R)else Path('external')/str(path).lstrip('/')
def package(out):
 if out.exists():raise ValueError('Preserve previous activity capsule')
 proof=R/'build/saturn-timing-activity-proof-v3/report.json'
 if not proof.is_file():raise ValueError('Wait for complete actual replay/corruption/phase proof')
 names=['saturn-timing-activity-source-v1','saturn-timing-activity-source-v2','saturn-timing-activity-source-v3','saturn-timing-activity-ports-v1','saturn-timing-activity-schema-v1','saturn-timing-activity-contract-v2','saturn-timing-activity-reference-v2','saturn-timing-activity-rtl-v1','saturn-timing-activity-capture-v1','saturn-timing-activity-native-fast-v3','saturn-timing-activity-native-fast-v4','saturn-timing-activity-native-rocket-v2','saturn-timing-activity-sdk-v4','saturn-timing-activity-replay-v2','saturn-timing-activity-replay-v3','saturn-timing-activity-proof-v2','saturn-timing-activity-proof-v3','saturn-timing-activity-reset-numeric-v1']
 files={p for name in names for p in(R/'build'/name).rglob('*')if p.is_file()};files.update(p for p in(R/'timing').glob('saturn_timing_activity*')if p.is_file())
 dependency=[];by_digest={};mapping={};cache={}
 def cached(p):
  if p not in cache:cache[p]=sha(p)
  return cache[p]
 for base in DEPS:
  dep=json.loads((base/'report.json').read_text());dependency.append({'path':str(base),'report_sha256':sha(base/'report.json')})
  for row in dep['artifacts']:
   by_digest.setdefault(row['sha256'],(base,row['path']));mapping[(row['source_path'],row['sha256'])]=(base,row['path'])
 # Resolve earlier script versions by their saved builder.py bytes, not by
 # silently binding an old build to the current mutable utility.
 local_digest={cached(p):p for p in files}
 resolutions={};processed=set();queue=list(files)
 while queue:
  receipt=queue.pop()
  if receipt in processed or receipt.suffix!='.json':continue
  processed.add(receipt)
  try:j=json.loads(receipt.read_text())
  except (ValueError,UnicodeDecodeError):continue
  if not isinstance(j,dict):continue
  for name,digest in j.get('input_sha256',{}).items():
   original=Path(name)
   if not original.is_absolute():continue
   key=name+'#'+digest
   if key in resolutions:continue
   match=mapping.get((name,digest))or by_digest.get(digest)
   containing=next((base for base in DEPS if original.is_relative_to(base)),None)
   if containing:
    if cached(original)!=digest:raise ValueError('Changed frozen dependency '+name)
    match=(containing,str(original.relative_to(containing)))
   if match:
    base,path=match
    if cached(base/path)!=digest:raise ValueError('Invalid dependency mapping '+name)
    resolutions[key]={'dependency':str(base),'path':path,'sha256':digest};continue
   actual=original if original.is_file()and cached(original)==digest else local_digest.get(digest)
   if actual is None:raise ValueError('Missing exact historical activity input '+name+' '+digest)
   if actual not in files:files.add(actual);queue.append(actual);local_digest[digest]=actual
   resolutions[key]={'path':str(rel(actual)),'sha256':digest}
 runtime={}
 for label,program in [('replay',R/'build/saturn-timing-activity-replay-v3/replay'),('wholeRTL',R/'build/saturn-timing-activity-rtl-v1/simulator-activity')]:
  text=subprocess.check_output(['ldd',str(program)],text=True);libraries={}
  for token in re.findall(r'(?:=>\s+)?(/[^\s()]+)',text):
   path=Path(token)
   if path.is_file():files.add(path);libraries[token]=cached(path)
  runtime[label]={'ldd':text,'libraries':libraries}
 out.mkdir();artifacts=[];dedup={}
 for original in sorted(files):
  target=out/rel(original);target.parent.mkdir(parents=True,exist_ok=True);digest=cached(original);mode=stat.S_IMODE(original.stat().st_mode);key=(digest,mode)
  if key in dedup:os.link(dedup[key],target)
  else:shutil.copy2(original,target);dedup[key]=target
  artifacts.append({'path':str(rel(original)),'source_path':str(original),'sha256':digest,'mode':mode,'bytes':target.stat().st_size})
 j=json.loads(proof.read_text());report={'schema':'iris.saturn_qualified_activity_frozen_capsule.v1','pass':True,'dependencies':dependency,'input_resolution':resolutions,'runtime_libraries':runtime,'proof':'build/saturn-timing-activity-proof-v3/report.json','reset_numeric_proof':'build/saturn-timing-activity-reset-numeric-v1/report.json','contract':'build/saturn-timing-activity-contract-v2/contract.json','projection_schema':'build/saturn-timing-activity-replay-v3/projection-schema.json','SDK':'build/saturn-timing-activity-sdk-v4/sdk','source_identity':json.loads((R/'build/saturn-timing-activity-sdk-v4/build.json').read_text())['source_identity'],'actual_replay_count':len(j['positive_replays']),'actual_source_edges':sum(h['source_edges']for row in j['positive_replays']for h in row['harts']),'qualified_activity_words':sum(h['qualified_activity_words']for row in j['positive_replays']for h in row['harts']),'qualified_physical_words':sum(h['qualified_physical_words']for row in j['positive_replays']for h in row['harts']),'observation_corruptions':len(j['expected_observation_bit_corruptions']),'activity_phase_guards':j['phase_guards']['result'],'artifact_count':len(artifacts),'unique_file_bytes':sum(p.stat().st_size for p in dedup.values()),'artifacts':artifacts,'control_qualification_is_not_architectural_numeric_knownness':True,'raw_unreset_order_invariance_or_global_RNG_isolation_claimed':False,'full_SoC_or_FPGA_or_2percent_certified':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k]for k in ['artifact_count','unique_file_bytes','actual_source_edges','qualified_activity_words','qualified_physical_words','observation_corruptions','activity_phase_guards']}|{'report_sha256':sha(out/'report.json')}))
def verify(out):
 report=json.loads((out/'report.json').read_text());dependencies={}
 for dep in report['dependencies']:
  base=Path(dep['path']);assert sha(base/'report.json')==dep['report_sha256'];dependencies[str(base)]=base
 for row in report['artifacts']:
  p=out/row['path'];assert p.is_relative_to(out)and p.stat().st_size==row['bytes']and stat.S_IMODE(p.stat().st_mode)==row['mode']and sha(p)==row['sha256'],row['path']
 for key,row in report['input_resolution'].items():
  p=(Path(row['dependency'])if'dependency'in row else out)/row['path'];assert sha(p)==row['sha256'],key
 proof=json.loads((out/report['proof']).read_text());libs=[out/rel(Path(p)).parent for p in report['runtime_libraries']['replay']['libraries']];env=dict(os.environ,LD_LIBRARY_PATH=os.pathsep.join(map(str,libs)));replay=out/'build/saturn-timing-activity-replay-v3/replay';checks=edges=0
 for row in proof['positive_replays']:
  if row['seed']!=91:continue
  q=subprocess.run([str(replay),str(out/'build/saturn-timing-activity-capture-v1'/row['case']/'activity.bin.gz'),'91'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,timeout=240);assert q.returncode==0,q.stderr;actual=json.loads(q.stdout);assert actual['harts']==row['harts'];checks+=sum(h['qualified_activity_words']for h in actual['harts']);edges+=sum(h['source_edges']for h in actual['harts'])
 old=out/'build/saturn-timing-activity-replay-v2/replay';q=subprocess.run([str(old),str(out/'build/saturn-timing-activity-capture-v1/vme/activity.bin.gz'),'0'],capture_output=True,text=True,env=env,timeout=30);assert q.returncode==2 and'Unqualified OPU numeric format/rounding input'in q.stderr
 q=subprocess.run([str(out/'build/saturn-timing-activity-proof-v3/guards')],capture_output=True,text=True,env=env,timeout=30);assert q.returncode==0 and json.loads(q.stdout)==proof['phase_guards']['result']
 for row in proof['expected_observation_bit_corruptions']:
  command=[str(replay),str(out/'build/saturn-timing-activity-capture-v1/vme/activity.bin.gz'),'17','--projection','/dev/null','--mutate','0',str(row['edge']),str(row['word'])];q=subprocess.run(command,capture_output=True,text=True,env=env,timeout=90);assert q.returncode==2 and q.stderr.splitlines()[-1]==row['error']
 numeric=json.loads((out/report['reset_numeric_proof']).read_text())
 for row in numeric['independent_cell_array_corpus']:
  folder=out/'build/saturn-timing-activity-reset-numeric-v1'/row['kind'];q=subprocess.run([str(folder/'model'/('VOuterCell'if row['kind']=='cell'else'VOuterArray')),str(folder/Path(row['argv'][1]).name)],capture_output=True,text=True,env=env,timeout=120);assert q.returncode==0 and json.loads(q.stdout)==row['checks']
 print(json.dumps({'pass':True,'capsule_sha256':sha(out/'report.json'),'artifacts_verified':len(report['artifacts']),'fresh_source_edges':edges,'fresh_qualified_activity_words':checks,'all_six_corruptions_rejected':True,'old_reset_numeric_refusal_preserved':True,'activity_phase_guards':proof['phase_guards']['result'],'independent_cell_array_replayed':True,'hardware_contacted':False}))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=R/'build/saturn-timing-activity-component-v1-final');p.add_argument('--verify',action='store_true');a=p.parse_args();(verify if a.verify else package)(a.output.resolve())
if __name__=='__main__':main()

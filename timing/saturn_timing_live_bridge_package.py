#!/usr/bin/env python3
"""Freeze v4 inactive-input/lifetime successor without changing the v2 capsule."""
import argparse,hashlib,json,os,re,shutil,stat,subprocess,tempfile
from pathlib import Path
from saturn_timing_ownership_package import sha,rel,R,DEPS as OLD_DEPS
DEPS=[R/'build/saturn-timing-ownership-component-v1-final',*OLD_DEPS]
def package(out):
 if out.exists():raise ValueError('Preserve previous live bridge capsule')
 proof=json.loads((R/'build/saturn-timing-live-bridge-inactive-v1/report.json').read_text())
 if not proof['pass']:raise ValueError('Inactive-input proof incomplete')
 names=['saturn-timing-ownership-replay-v13','saturn-timing-ownership-replay-v14','saturn-timing-live-bridge-v4','saturn-timing-live-bridge-inactive-v1','saturn-timing-live-bridge-guards-v2'];files={p for name in names for p in(R/'build'/name).rglob('*')if p.is_file()};files.update(p for pattern in ['saturn_timing_live_bridge*','saturn_timing_ownership.hpp','saturn_timing_ownership.cpp','saturn_timing_ownership_replay.cpp']for p in(R/'timing').glob(pattern)if p.is_file());files.add(R/'timing/saturn_timing_ownership_package.py');cache={}
 def digest(p):
  if p not in cache:cache[p]=sha(p)
  return cache[p]
 deps=[];by_digest={};mapping={}
 for base in DEPS:
  report=json.loads((base/'report.json').read_text());deps.append({'path':str(base),'report_sha256':digest(base/'report.json')})
  for row in report['artifacts']:by_digest.setdefault(row['sha256'],(base,row['path']));mapping[(row['source_path'],row['sha256'])]=(base,row['path'])
 local={digest(p):p for p in files};resolved={};seen=set();queue=list(files)
 while queue:
  path=queue.pop()
  if path in seen or path.suffix!='.json':continue
  seen.add(path)
  try:j=json.loads(path.read_text())
  except(ValueError,UnicodeError):continue
  if not isinstance(j,dict):continue
  for name,wanted in j.get('input_sha256',{}).items():
   original=Path(name);key=name+'#'+wanted
   if not original.is_absolute()or key in resolved:continue
   match=mapping.get((name,wanted))or by_digest.get(wanted);containing=next((base for base in DEPS if original.is_relative_to(base)),None)
   if containing:
    if digest(original)!=wanted:raise ValueError('Changed frozen input '+name)
    match=(containing,str(original.relative_to(containing)))
   if match:
    base,relative=match
    if digest(base/relative)!=wanted:raise ValueError('Invalid historical dependency '+name)
    resolved[key]={'dependency':str(base),'path':relative,'sha256':wanted};continue
   actual=original if original.is_file()and digest(original)==wanted else local.get(wanted)
   if actual is None:raise ValueError('Missing exact historical successor input '+key)
   if actual not in files:files.add(actual);queue.append(actual);local[wanted]=actual
   resolved[key]={'path':str(rel(actual)),'sha256':wanted}
 runtime={}
 for name in ['build/saturn-timing-ownership-replay-v14/replay','build/saturn-timing-live-bridge-inactive-v1/inactive','build/saturn-timing-live-bridge-guards-v2/guards']:
  text=subprocess.check_output(['ldd',str(R/name)],text=True)
  for token in re.findall(r'(?:=>\s+)?(/[^\s()]+)',text):
   p=Path(token)
   if p.is_file():files.add(p);runtime[token]=digest(p)
 cases=[]
 for case in ['vme','rvv','fpcomp','shared-fpu']:
  old=R/'build/saturn-timing-ownership-component-v1-final/build/saturn-timing-ownership-replay-v12'/(case+'-events.ndjson.gz');new=R/'build/saturn-timing-ownership-replay-v14'/(case+'-events.ndjson.gz')
  if digest(old)!=digest(new):raise ValueError('Observational lifetime API changed existing event bytes')
  cases.append({'case':case,'result':json.loads((R/'build/saturn-timing-ownership-replay-v14'/(case+'.stdout')).read_text().splitlines()[-1]),'event_sha256':digest(new)})
 out.mkdir();rows=[];dedup={}
 for original in sorted(files):
  target=out/rel(original);target.parent.mkdir(parents=True,exist_ok=True);value=digest(original);mode=stat.S_IMODE(original.stat().st_mode);key=(value,mode)
  if key in dedup:os.link(dedup[key],target)
  else:shutil.copy2(original,target);dedup[key]=target
  rows.append({'path':str(rel(original)),'source_path':str(original),'sha256':value,'mode':mode,'bytes':target.stat().st_size})
 report={'schema':'iris.saturn_live_bridge_inactive_lifetime_capsule.v1','pass':True,'dependencies':deps,'input_resolution':resolved,'runtime_libraries':runtime,'SDK':'build/saturn-timing-live-bridge-v4/sdk','library_sha256':digest(R/'build/saturn-timing-live-bridge-v4/sdk/libiris_saturn_live_bridge.a'),'inactive_payload_proof':'build/saturn-timing-live-bridge-inactive-v1/report.json','strict_phase_lifecycle_proof':'build/saturn-timing-live-bridge-guards-v2/report.json','actual_whole_RTL_command_lifetime_replays':cases,'artifacts':rows,'artifact_count':len(rows),'unique_file_bytes':sum(p.stat().st_size for p in dedup.values()),'architectural_knownness_inferred':False,'actual_native_CPU_ELF_execution':False,'full_SoC_FPGA_or_2percent_certified':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'artifact_count':len(rows),'unique_file_bytes':report['unique_file_bytes']}))
def verify(out):
 report=json.loads((out/'report.json').read_text())
 for dep in report['dependencies']:
  if sha(Path(dep['path'])/'report.json')!=dep['report_sha256']:raise ValueError('Changed dependency identity')
 for row in report['artifacts']:
  p=out/row['path']
  if not p.is_relative_to(out)or p.stat().st_size!=row['bytes']or stat.S_IMODE(p.stat().st_mode)!=row['mode']or sha(p)!=row['sha256']:raise ValueError('Changed capsule artifact '+row['path'])
 for key,row in report['input_resolution'].items():
  if sha((Path(row['dependency'])if'dependency'in row else out)/row['path'])!=row['sha256']:raise ValueError('Changed exact historical input '+key)
 env=dict(os.environ,LD_LIBRARY_PATH=os.pathsep.join(map(str,sorted({(out/rel(Path(p))).parent for p in report['runtime_libraries']}))));proof=json.loads((out/report['inactive_payload_proof']).read_text())
 with tempfile.TemporaryDirectory(prefix='iris-live-bridge-')as folder:
  for row in proof['runs']:
   q=subprocess.run([str(out/'build/saturn-timing-live-bridge-inactive-v1/inactive'),str(row['seed'])],capture_output=True,text=True,cwd=folder,env=env,timeout=60)
   if q.returncode or json.loads(q.stdout.splitlines()[-1])!=row['result']:raise ValueError('Relocated inactive-payload source proof differs')
  q=subprocess.run([str(out/'build/saturn-timing-live-bridge-guards-v2/guards')],capture_output=True,text=True,cwd=folder,env=env,timeout=60)
  if q.returncode:raise ValueError('Relocated strict/lifecycle guard failure')
  count=events=refs=0;parent=Path(report['dependencies'][0]['path'])
  for row in report['actual_whole_RTL_command_lifetime_replays']:
   case=row['case'];cmd=[str(out/'build/saturn-timing-ownership-replay-v14/replay'),str(parent/'build/saturn-timing-ownership-capture-v4'/case/'activity.bin.gz'),str(parent/'build/saturn-timing-ownership-capture-v4'/case/'ownership.bin.gz'),'17',str(Path(folder)/'events.gz')]
   with(Path(folder)/'stdout').open('w')as stdout,(Path(folder)/'stderr').open('w')as stderr:q=subprocess.run(cmd,stdout=stdout,stderr=stderr,cwd=folder,env=env,timeout=600)
   if q.returncode or json.loads((Path(folder)/'stdout').read_text().splitlines()[-1])!=row['result']or sha(Path(folder)/'events.gz')!=row['event_sha256']:raise ValueError('Relocated actual-source lifetime/event proof differs '+case)
   count+=sum(h['edges']for h in row['result']['harts']);events+=row['result']['events'];refs+=row['result']['event_command_reference_checks']
 print(json.dumps({'pass':True,'capsule_sha256':sha(out/'report.json'),'artifacts_verified':len(report['artifacts']),'fresh_source_edges':count,'fresh_numeric_owned_events':events,'fresh_event_owner_reference_checks':refs,'fresh_inactive_payload_and_strict_lifecycle_checks':True,'hardware_contacted':False}))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();(verify if a.verify else package)(a.output.resolve())
if __name__=='__main__':main()

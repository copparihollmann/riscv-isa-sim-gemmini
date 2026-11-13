#!/usr/bin/env python3
"""Replay archived native/ELF/config bytes without the mutable native build."""
import argparse,gzip,hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--capsule',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();cap=a.capsule.resolve();out=a.output.resolve()
 if out.exists():raise ValueError('fresh archived verification required')
 j=json.loads((cap/'manifest.json').read_text());before=sha(cap/'manifest.json');out.mkdir();(out/'materialized').mkdir();source=j['files'];cached={}
 def materialize(name):
  name=str(Path(name).absolute());item=source[name];digest=item['sha256']
  if digest in cached:return cached[digest]
  obj=j['objects'][digest];old=cap/obj['path'];dest=out/'materialized'/digest;op=gzip.open if obj['encoding']=='gzip'else open
  with op(old,'rb')as f,dest.open('wb')as o:
   for b in iter(lambda:f.read(1048576),b''):o.write(b)
  assert sha(dest)==digest;cached[digest]=dest;return dest
 parent=R/'build/shuttle-memory-native-final-v2';receipt=json.loads(materialize(parent/'results.json').read_text());rows=[];env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']);env.pop('IRIS_FATAL_PCS',None);start=time.monotonic()
 selected=[receipt['rows'][0],*receipt['rows'][2:]]
 for row in selected:
  folder=out/row['name'];folder.mkdir();old_argv=row['argv'];elf=materialize(old_argv[-1]);argv=[str(cap/'spike')];profile=None
  for option in old_argv[1:-1]:
   if option.startswith('--extlib='):argv.append('--extlib='+str(cap/'libsifive_uart.so'))
   elif option.startswith('--iris-timing-trace='):argv.append('--iris-timing-trace='+str(folder/'graph.json'))
   elif option.startswith('--iris-timing-fixture='):
    old_profile=materialize(option.split('=',1)[1]);lines=[]
    for line in old_profile.read_text().splitlines():
     if line.startswith('rocket_serial '):
      fields=line.split();assert fields[10]==old_argv[-1];fields[10]=str(elf);line=' '.join(fields)
     lines.append(line)
    profile=folder/'explicit.fixture';profile.write_text('\n'.join(lines)+'\n');argv.append('--iris-timing-fixture='+str(profile))
   elif option.startswith(('--iris-bootrom=','--dtb=')):
    key,value=option.split('=',1);argv.append(key+'='+str(materialize(value)))
   else:argv.append(option)
  argv.append(str(elf));t=time.monotonic();p=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=180);(folder/'stdout').write_text(p.stdout);(folder/'stderr').write_text(p.stderr);assert p.returncode==row['exit_status'],(row['name'],p.stderr)
  if row['expected_refusal']:assert row['expected_refusal']in p.stderr
  g=json.loads((folder/'graph.json').read_text());old_graph=json.loads(materialize(next(x.split('=',1)[1]for x in old_argv if x.startswith('--iris-timing-trace='))).read_text());assert g['cycles']==old_graph['cycles'];assert g['shuttle_source_memory']==old_graph['shuttle_source_memory'];assert g['retired_instructions']==old_graph['retired_instructions']
  rows.append({'name':row['name'],'exit_status':p.returncode,'cycles':g['cycles'],'exact_Shuttle_transaction_and_retirement_records':True,'host_seconds':time.monotonic()-t,'argv':argv,'stdout_sha256':sha(folder/'stdout'),'stderr_sha256':sha(folder/'stderr')});print(row['name'],'passed',flush=True)
 phase=materialize(R/'build/shuttle-lsu-phase-check-v2/check');phase.chmod(0o755);p=subprocess.run([str(phase)],capture_output=True,text=True,timeout=60);(out/'source-phase.stdout').write_text(p.stdout);(out/'source-phase.stderr').write_text(p.stderr);assert p.returncode==0;assert [json.loads(x)for x in p.stdout.splitlines()]==j['receipts']['source_ShuttleCore_phase']['rows']
 assert sha(cap/'manifest.json')==before
 result={'schema':'iris.native_Shuttle_archived_replay.v1','status':'passed_archived_actual_ELF_and_source_phase','capsule_sha256':before,'binary_sha256':sha(cap/'spike'),'uart_sha256':sha(cap/'libsifive_uart.so'),'archived_native_ELF_ROM_DTB_and_profile_used':True,'initial_ELF_path_only_rebased_to_exact_archived_bytes':True,'rows':rows,'source_ShuttleCore_phase_exact':True,'input_sha256':{str(q):sha(q)for q in [Path(__file__),cap/'manifest.json']},'host_seconds':time.monotonic()-start,'capsule_unchanged':True,'hardware_contacted':False,'timing_certified':False,'calibration_usable':False};(out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'receipt_sha256':sha(out/'results.json')}))
if __name__=='__main__':main()

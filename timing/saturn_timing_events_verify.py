#!/usr/bin/env python3
"""Recheck typed projection bytes and replay every frozen external-port trace."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--events',type=Path,default=R/'build/saturn-timing-events-v3');a=p.parse_args();out=a.events.resolve();report=json.loads((out/'report.json').read_text());reference=R/'build/saturn-timing-component-v1-final';fast=R/'build/saturn-timing-fast-component-v1-final';ref=json.loads((reference/'report.json').read_text());fastj=json.loads((fast/'report.json').read_text());copies={x['source_path']:reference/x['path']for x in ref['artifacts']};copies.update({x['source_path']:fast/x['path']for x in fastj['artifacts']})
 for name,digest in report['artifact_sha256'].items():
  path=(out/name).resolve();assert path.is_relative_to(out)and sha(path)==digest,name
 for name,digest in report['input_sha256'].items():
  original=Path(name);archived=out/'source'/original.name
  if original.parent==R/'timing'and archived.is_file():target=archived
  elif name in copies:target=copies[name]
  else:target=original
  assert target.is_file()and sha(target)==digest,name
 libs=[reference/'external'/str(Path(p).parent).lstrip('/')for p in ref['runtime_libraries']['sdk']['libraries']];env=dict(os.environ,LD_LIBRARY_PATH=os.pathsep.join(map(str,libs)));edges=commands=beats=0
 for row in report['runs']:
  case,h=row['case'],row['hart'];folder=fast/'build/saturn-timing-fast-replay-v1'/case;command=[str(out/'events'),'rocket'if h==2 else'compute',str(h),str(folder/f'hart{h}.input'),str(folder/f'hart{h}.stdout')];q=subprocess.run(command,capture_output=True,text=True,timeout=60,env=env);assert q.returncode==0,q.stderr;fresh=json.loads(q.stdout)
  for key,value in fresh.items():assert row[key]==value,(case,h,key)
  edges+=fresh['edges'];commands+=fresh['command_identity_checks'];beats+=fresh['TL_event_checks']
 folder=fast/'build/saturn-timing-fast-replay-v1/rvv';ports=folder/'hart2.input';values=folder/'hart2.stdout';cases=[('wrong-A-size',ports,out/'wrong-A-size.stdout',2),('unowned-D-source',out/'wrong-D-source.input',values,2),('missing-edge',ports,out/'truncated.stdout',2),('wrong-hart-profile',ports,values,0),('overwide-input',out/'overwide-reset.input',values,2),('overwide-output',ports,out/'overwide-output.stdout',2),('missing-reset-history',out/'no-reset-history.input',out/'no-reset-history.stdout',2)]
 for name,ip,op,h in cases:
  q=subprocess.run([str(out/'events'),'rocket',str(h),str(ip),str(op)],capture_output=True,text=True,timeout=60,env=env);expected=next(x for x in report['corruption_refusals']if x['name']==name);assert q.returncode==expected['exit_status']and q.stderr==expected['diagnostic'],name
 print(json.dumps({'pass':True,'receipt_sha256':sha(out/'report.json'),'actual_source_core_edges':edges,'command_identity_checks':commands,'TL_event_checks':beats,'corruption_refusals':len(cases),'hardware_contacted':False}))
if __name__=='__main__':main()

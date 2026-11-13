#!/usr/bin/env python3
"""Check phase/width/hart guards without claiming idle source datapath initialized."""
import argparse,hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();sdk=a.sdk.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);reports=[]
 for profile,hart in [('compute',0),('compute',1),('rocket',2)]:
  j=json.loads((R/'build/saturn-timing-source-v1'/profile/'ports.json').read_text());fields=j['words']['input'];frame={f['word_name']:0 for f in fields};frame['reset']=1;reset='step 0 '+' '.join(str(frame[f['word_name']])for f in fields)+'\n';frame['reset']=0;idle='step 1 '+' '.join(str(frame[f['word_name']])for f in fields)+'\n';command=[str(sdk/'saturn-timing'),'--reference-two-state','--profile',profile,'--hart',str(hart),'--seed','17'];q=subprocess.run(command,input=reset+idle,text=True,capture_output=True,timeout=20);(out/f'{profile}-h{hart}.stdout').write_text(q.stdout);(out/f'{profile}-h{hart}.stderr').write_text(q.stderr);assert q.returncode==0;valid_lines=[x for x in q.stdout.splitlines()if x.startswith('SATURN_FRAME ')];assert len(valid_lines)==2
  negative=[]
  for label,payload in [('sample-before-evaluate','sample\n'),('commit-before-evaluate','commit\n'),('sample-after-commit',reset+'sample\n'),('double-commit',reset+'commit\n')]:
   run=subprocess.run(command,input=payload,text=True,capture_output=True,timeout=20);assert run.returncode==2;negative.append({'label':label,'exit_status':run.returncode,'stderr':run.stderr})
  frame['reset']=2;payload='step 0 '+' '.join(str(frame[f['word_name']])for f in fields)+'\n';run=subprocess.run(command,input=payload,text=True,capture_output=True,timeout=20);assert run.returncode==2;negative.append({'label':'overwide-reset','exit_status':run.returncode,'stderr':run.stderr})
  wrong=command[:];wrong[wrong.index('--hart')+1]=str(2 if profile=='compute'else 0);run=subprocess.run(wrong,input=reset,text=True,capture_output=True,timeout=20);assert run.returncode==2;negative.append({'label':'hart-profile-mismatch','exit_status':run.returncode,'stderr':run.stderr})
  missing=command[:];missing.remove('--reference-two-state');run=subprocess.run(missing,input=reset,text=True,capture_output=True,timeout=20);assert run.returncode==2;negative.append({'label':'implicit-two-state-scope-refused','exit_status':run.returncode,'stderr':run.stderr});reports.append({'profile':profile,'hart':hart,'argv':command,'edges':2,'negative_controls':negative,'numeric_payload_definedness_claimed':False})
 inputs=[Path(__file__),sdk/'saturn-timing',sdk/'build.json'];report={'schema':'iris.saturn_reference_boundary_smoke.v1','runs':reports,'input_sha256':{str(p):sha(p)for p in inputs},'active_workload_or_cycle_accuracy_claimed':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source_profiles':2,'physical_harts':3,'negative_controls':sum(len(x['negative_controls'])for x in reports),'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()

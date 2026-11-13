#!/usr/bin/env python3
"""Compare a full physical port replay with the independent whole-SoC capture."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];RTL=R/'build/noc-full-router-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read_frames(case):
 schema=json.loads((R/'timing/noc_full_router_observer_fields.json').read_text());names=[x['name'] for x in schema['fields']];rows=[]
 for line in (RTL/(case+'.stderr')).read_text().splitlines():
  if line.startswith('RTL_FULL_ROUTER '):
   fields=line[16:].split(',')
   if len(fields)!=len(names)+1:raise ValueError('Full physical frame width mismatch')
   rows.append(dict(tb=int(fields[0]),**dict(zip(names,[int(x,16) for x in fields[1:]]))))
 if not rows or rows[0]['tb']!=3 or rows[0]['i_reset']!=1 or any(b['tb']!=a['tb']+2 for a,b in zip(rows,rows[1:])):raise ValueError('Physical capture must start under actual reset and remain continuous')
 return schema,rows

def compare(actual,frames,output_names):
 if len(actual)!=len(frames):raise ValueError('Incomplete full-router native trace')
 comparisons=0;active=0
 for values,x in zip(actual,frames):
  if len(values)!=len(output_names)+1 or values[0]!=x['tb']:raise ValueError('Native physical row width/order mismatch')
  if x['i_reset']:continue
  got=dict(zip(output_names,values[1:]));keys=set(output_names)
  for prefix in ['o_net0_','o_net1_','o_local_']:
   if not x[prefix+'valid']:keys-=set(n for n in keys if n.startswith(prefix) and n!=prefix+'valid')
  for key in keys:
   comparisons+=1
   if got[key]!=x[key]:raise ValueError('TB'+str(x['tb'])+' '+key+' native='+str(got[key])+' wholeRTL='+str(x[key]))
  active+=1
 return {'physical_signal_comparisons':comparisons,'post_reset_edges':active}

def run(case,binary,out):
 schema,rows=read_frames(case);i_names=[x['name'] for x in schema['fields'][:schema['input_count']]];o_names=[x['name'] for x in schema['fields'][schema['input_count']:]];body=''.join('step '+str(x['tb'])+' '+' '.join(str(x[n]) for n in i_names)+'\n' for x in rows)
 out.mkdir(parents=True,exist_ok=True);(out/(case+'.input')).write_text(body);started=time.monotonic();p=subprocess.run([str(binary),'--seed','1'],input=body,text=True,capture_output=True,timeout=30);seconds=time.monotonic()-started;(out/(case+'.stdout')).write_text(p.stdout);(out/(case+'.stderr')).write_text(p.stderr)
 actual=[[int(v) for v in line.split()] for line in p.stdout.splitlines() if line and not line.startswith('-')];result=compare(actual,rows,o_names)
 if p.returncode:raise ValueError('Native full router refused: '+p.stderr)
 result.update(case=case,pass_result=True,edges=len(rows),first_tb=rows[0]['tb'],last_tb=rows[-1]['tb'],actual_reset=True,internal_seeds=0,host_seconds=seconds,rtl_trace_sha256=sha(RTL/(case+'.stderr')),input_sha256=sha(out/(case+'.input')),stdout_sha256=sha(out/(case+'.stdout')),stderr_sha256=sha(out/(case+'.stderr')))
 result['native_sha256']=sha(binary);result['native_cost']=json.loads(p.stderr.split('NODE5_COST ')[-1].splitlines()[0]);(out/(case+'.result.json')).write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result));return result

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--case',choices=['original9','control8','fenced9','peer'],default='original9');p.add_argument('--binary',type=Path,default=R/'build/noc-full-router-v2/noc-full-router');p.add_argument('--output',type=Path,default=R/'build/noc-full-router-replay-v2');a=p.parse_args();run(a.case,a.binary.resolve(),a.output.resolve())
if __name__=='__main__':main()

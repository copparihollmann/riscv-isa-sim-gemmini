#!/usr/bin/env python3
"""Validate a source-derived local node5 return branch against accepted-flit RTL traces."""
import argparse,hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];B=R/'build/noc-router-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def frames(case):
 names=[x['name'] for x in json.loads((R/'timing/noc_router_observer_fields.json').read_text())];rows=[]
 for line in (B/(case+'.stderr')).read_text().splitlines():
  if line.startswith('RTL_ROUTER '):
   a=line[11:].split(',')
   if len(a)!=len(names)+1:raise ValueError('Broken router frame')
   rows.append(dict(tb=int(a[0]),**dict(zip(names,[int(x,16) for x in a[1:]]))))
 if not rows or rows[0]['tb']!=90001 or any(b['tb']!=a['tb']+2 for a,b in zip(rows,rows[1:])):raise ValueError('Incomplete/unordered router observation')
 return rows

def count(x,prefix,depth):
 e=x[prefix+'enq'];d=x[prefix+'deq'];return depth if e==d and x[prefix+'maybe'] else(e-d)%depth

def seed(x):
 nums=[x[n] for n in ['input_mask','router_mask','output_mask','switch_mask','switch_lock','egress_sa_mask','egress_sa_lock','egress_empty']]
 for i in range(6):
  p='vc'+str(i)+'_';nums += [x[p+n] for n in ['state','local','enq','deq','maybe']]
  for slot in range(5):nums += [x[p+'mem'+str(slot)+'_'+str(w)] for w in range(3)]
 nums +=[x['egress_'+n] for n in ['enq','deq','maybe']]
 for slot in range(2):nums += [x['egress_mem'+str(slot)+'_'+str(w)] for w in range(3)]
 return 'seed '+' '.join(map(str,nums))+'\n'

def step(x):
 nums=[x['tb']]+[x[n] for n in ['arrival_valid','arrival_vc','arrival_dest','arrival_dest_id','arrival_word0','arrival_word1','arrival_word2','nif_ready']]
 for k in range(1,4):nums += [x['peer'+str(k)+'_eligible'],x['peer'+str(k)+'_outputs']]
 nums +=[x['route_fire'],x['route_vc'],1]
 return 'step '+' '.join(map(str,nums))+'\n'

def expected(x):
 labels=['tb','input_mask','router_mask','output_mask','switch_mask','switch_lock','egress_sa_mask','egress_sa_lock','egress_empty'];vals=[x[n] for n in labels];pops=freed=0
 for i in range(6):
  p='vc'+str(i)+'_';c=count(x,p,5)
  for n in ['state','local','enq','deq','maybe']:labels.append(p+n);vals.append(x[p+n])
  labels.append(p+'count');vals.append(c)
  for w in range(3):labels.append(p+'head'+str(w));vals.append(x[p+'head'+str(w)] if c else 0)
  if x[p+'pop']:pops|=1<<i
  if x[p+'pop'] and x[p+'head0']&2:freed|=1<<i
 for n in ['enq','deq','maybe']:labels.append('egress_'+n);vals.append(x['egress_'+n])
 labels.append('egress_count');vals.append(count(x,'egress_',2))
 for n in ['waiting_vcs','selected_vc','input_grants','output_grants']:labels.append(n);vals.append(x[n])
 labels+=['popped_vcs','freed_vcs','egress_push','egress_pop','out_valid'];vals +=[pops,freed,x['egress_push'],x['egress_pop'],x['out_valid']]
 packed=((x['out_payload2']<<64)|(x['out_payload1']<<32)|x['out_payload0'])<<2|(x['out_tail']<<1)|x['out_head']
 for w in range(3):labels.append('out_word'+str(w));vals.append(((packed>>(32*w))&0xffffffff) if x['out_valid'] else 0)
 return labels,vals

def validate(binary,case,out):
 rows=frames(case)
 for x in rows:
  if x['egress_sa_valids']&14:raise ValueError('Peer local switch contender outside branch')
  if any(x['peer'+str(k)+'_eligible'] and x['peer'+str(k)+'_outputs']&4096 for k in range(1,4)):raise ValueError('Peer local VA contender outside branch')
 body='profile 6 5 2 5 0 4 13 0 12\n'+seed(rows[0])+''.join(step(x) for x in rows)
 out.mkdir(parents=True,exist_ok=True);(out/(case+'.input')).write_text(body);q=subprocess.run([str(binary)],input=body,text=True,capture_output=True,timeout=15);(out/(case+'.stdout')).write_text(q.stdout);(out/(case+'.stderr')).write_text(q.stderr)
 actual=[[int(v) for v in line.split()] for line in q.stdout.splitlines()]
 for got,x in zip(actual,rows):
  labels,want=expected(x)
  if got!=want:
   bad=[(k,a,b) for k,a,b in zip(labels,got,want) if a!=b];raise ValueError('TB'+str(x['tb'])+' mismatch '+str(bad[:10]))
 if q.returncode or len(actual)!=len(rows):raise ValueError('Native router refused/incomplete after'+str(len(actual))+': '+q.stderr)
 return {'case':case,'cycles':len(rows),'first_tb':rows[0]['tb'],'last_tb':rows[-1]['tb'],'pass':True,'seed_count':body.count('seed '),'arrival_flits':sum(x['arrival_valid'] for x in rows),'egress_flits':sum(x['out_valid'] and x['nif_ready'] for x in rows),'hardware_contacted':False,'whole_router_model':False,'input_sha256':sha(out/(case+'.input')),'stdout_sha256':sha(out/(case+'.stdout'))}

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--case',choices=['original9','control8','fenced9'],default='original9');p.add_argument('--binary',type=Path,default=R/'build/noc-router-model-dev/noc-router');p.add_argument('--output',type=Path,default=R/'build/noc-router-model-dev');a=p.parse_args();print(json.dumps(validate(a.binary.resolve(),a.case,a.output.resolve())))
if __name__=='__main__':main()

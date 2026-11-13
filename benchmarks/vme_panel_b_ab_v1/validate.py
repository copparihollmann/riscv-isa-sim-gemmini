"""Independent exact-output and timing-window admission; no fitting."""
import argparse
import hashlib
import json
from pathlib import Path
import re

def validate(text,packet):
 meta=json.loads((packet/'manifest.json').read_text());expected={c['id']:c for c in meta['cases']}
 for p,h in meta['input_sha256'].items():
  if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Changed input '+p)
 if hashlib.sha256(Path(meta['ELF']).read_bytes()).hexdigest()!=meta['ELF_sha256']:raise ValueError('ELF changed')
 regions={};stages={};dispatch={};setups={};progress=[]
 for l in text.splitlines():
  if l.startswith('IRIS_REGION '):
   r=json.loads(l.split(' ',1)[1]);key=r['case_id']
   if key not in expected or key in regions or r.get('pass')is not True or r['hart']!=0 or r['warmup']is not False or r['region']!='packed_gemm_operator':raise ValueError('Bad region')
   if r['checksum']!=expected[key]['expected_checksums_by_hart'][0] or r['end_cycle']<=r['start_cycle'] or r['instret_delta']!=r['end_instret']-r['start_instret']:raise ValueError('Bad result/counter')
   regions[key]=r
  elif l.startswith('IRIS_PANEL_AB '):
   v=list(map(int,l.split()[1:]));
   if len(v)!=14:raise ValueError('Bad typed region')
   point,route,rep,status,tb,te,cb,ce,ib,ie,itb,ite,prep,finish=v;key=f'panel_p{point}_c{route}_r{rep}'
   if key not in expected or key in stages or status or not tb<=itb<=ite<=te or ce<=cb or ie<ib:raise ValueError('Bad primitive interval')
   stages[key]=dict(point=point,route=route,pass_id=rep,whole_ticks=te-tb,primitive_cycles=ce-cb,primitive_instret=ie-ib,primitive_ticks=ite-itb,prepare_ticks=prep,finish_ticks=finish,primitive_begin=cb,primitive_end=ce)
  elif l.startswith('IRIS_PANEL_DISPATCH '):
   point,route,rep,tb,te,registration=list(map(int,l.split()[1:]));key=f'panel_p{point}_c{route}_r{rep}'
   if key not in expected or key in dispatch or te<tb:raise ValueError('Bad dispatch interval')
   dispatch[key]=dict(whole_dispatch_ticks=te-tb,matrix_registration_cycles=registration)
  elif l.startswith('IRIS_PANEL_SETUP '):
   point,init,pack,end=list(map(int,l.split()[1:]));
   if point in setups or point>=len(meta['points'])or not init<=pack<=end:raise ValueError('Bad setup interval')
   setups[point]=dict(initialization_ticks=pack-init,weight_pack_ticks=end-pack)
  elif l.startswith('IRIS_PROGRESS v1 DONE '):
   _,_,_,count,key,checksum=l.split()
   if int(count)!=len(progress)+1 or key not in expected or int(checksum)!=expected[key]['expected_checksums_by_hart'][0]:raise ValueError('Bad progress')
   progress.append(key)
 if progress!=[c['id']for c in meta['cases']]or set(regions)!=set(expected)or set(stages)!=set(expected)or set(dispatch)!=set(expected)or len(setups)!=len(meta['points']):raise ValueError('Incomplete corpus')
 if text.count('IRIS_BATCH_DONE passed=54 failed=0')!=1 or not re.search(r'^DONE$',text,re.M):raise ValueError('Missing completion')
 rows=[]
 for c in meta['cases']:
  key=c['id'];r=regions[key];s=stages[key]
  if not r['start_cycle']<=s['primitive_begin']<=s['primitive_end']<=r['end_cycle']:raise ValueError('Non-nested clocks')
  p=meta['points'][s['point']];rows.append(dict(**p,**s,**dispatch[key],whole_cycles=r['end_cycle']-r['start_cycle'],whole_instret=r['instret_delta'],MACs_per_primitive_observed_cycle=p['MACs']/s['primitive_cycles'],physical_busy=None))
 return dict(schema='iris.vme_panel_b_ab_intake.v1',**{'pass':True},trials=54,regions=54,ELF_sha256=meta['ELF_sha256'],samples=rows,setups=setups,source_image_build_association_verified=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--packet',type=Path,required=True);p.add_argument('--console',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=validate(a.console.read_text(),a.packet);a.output.mkdir(exist_ok=False,parents=True);(a.output/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k not in ['samples','setups']}))

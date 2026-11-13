#!/usr/bin/env python3
"""Offline group-prefix controls; full-run validator remains strict."""
import copy,json
from pathlib import Path
from analyze_memory_footprints_mtime_groups import partial_groups
from batch_runner import digest
R=Path(__file__).resolve().parents[1]
def main():
 out=R/'build/memory-footprints-mtime-groups-prefix-controls-v1';out.mkdir(exist_ok=False);b=R/'build/memory-footprints-mtime-groups-fit-v7';corpus=json.loads((b/'corpus.json').read_text());text=(b/'seed0/stdout').read_text();lines=text.splitlines();front=[i for i,l in enumerate(lines)if l.startswith('IRIS_FOOTPRINT_GROUP ')];assert len(front)==15;prefix='\n'.join(lines[:front[2]+1]);rows,proof=partial_groups(prefix,corpus);assert len(rows)==72 and proof['complete_groups']==3 and proof['normal_completion']is False;controls=[]
 def reject(name,value):
  try:partial_groups(value,corpus)
  except(ValueError,TypeError,KeyError):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Accepted '+name)
 def replace_first(tag,key,value):
  ls=prefix.splitlines();i=next(i for i,s in enumerate(ls)if s.startswith(tag+' '));row=json.loads(ls[i][len(tag)+1:]);row[key]=value;ls[i]=tag+' '+json.dumps(row);return '\n'.join(ls)
 for key,value in [('mtime_before',True),('mtime_after',0),('mtime_hz',1000000),('source_core_cycles_per_mtime_tick',999),('mtime_scope','unknown'),('hart',True),('checksum',0),('pass_index',1),('instret_delta',True),('start_cycle',2**64)]:reject(key,replace_first('IRIS_REGION',key,value))
 reject('wrong-frontier-count',replace_first('IRIS_FOOTPRINT_GROUP','records',23));reject('bool-frontier',replace_first('IRIS_FOOTPRINT_GROUP','group',False));reject('no-frontier','\n'.join(s for s in lines[:front[0]]));reject('missing-first-row','\n'.join(prefix.splitlines()[1:]));reject('missing-first-frontier','\n'.join(s for i,s in enumerate(prefix.splitlines())if i!=front[0]));paths=[Path(__file__),R/'firesim/analyze_memory_footprints_mtime_groups.py',b/'corpus.json',b/'seed0/stdout'];r=dict(schema='iris.memory_footprint_group_prefix_controls.v1',**{'pass':True},positive_prefix=proof,corruption_controls=controls,input_sha256={str(p):digest(p)for p in paths},full_normal_success_required_for_fitting=True,hardware_contacted=False);(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(**{'pass':True},controls=len(controls),sha256=digest(out/'report.json'))))
if __name__=='__main__':main()

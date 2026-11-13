import copy,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'firesim'))
from flush_frontier_validate import timeout
R=Path(__file__).resolve().parents[1];O=R/'build/flush-frontier-snapshot-controls-v1';O.mkdir();text=(R/'build/flush-frontier-one-shot-negative-v2-enabled-run/stdout').read_text();assert timeout(text,True)['snapshots']==6;controls=[]
def reject(name,transform):
 try:timeout(transform(text),True)
 except(ValueError,TypeError,KeyError):controls.append(dict(name=name,rejected=True));return
 raise ValueError('Accepted '+name)
def change(tag,key,value):
 def f(t):
  ls=t.splitlines();i=next(i for i,l in enumerate(ls)if l.startswith(tag+' '));r=json.loads(ls[i].split(' ',1)[1]);r[key]=value;ls[i]=tag+' '+json.dumps(r);return'\n'.join(ls)
 return f
for tag,key,value in [('IRIS_FLUSH_ONESHOT','hart',0),('IRIS_FLUSH_ONESHOT','entry_mtime',0),('IRIS_FLUSH_ONESHOT','entry_mip',True),('IRIS_FLUSH_ONESHOT','before_timer_spinlock_and_announce',False),('IRIS_FLUSH_SNAPSHOT','slot',True),('IRIS_FLUSH_SNAPSHOT','metadata_race_possible',False),('IRIS_FLUSH_SNAPSHOT','current_PC_or_state_claimed',True),('IRIS_FLUSH_SNAPSHOT','last_recorded_mie',True),('IRIS_FLUSH_SNAPSHOT','begin',3),('IRIS_FLUSH_ARM','last_recorded_mie',8),('IRIS_FLUSH_ARM','last_recorded_mstatus',0),('IRIS_FLUSH_ARM','delay_ms',25)]:reject(tag+':'+key,change(tag,key,value))
reject('missing-snapshot',lambda t:'\n'.join(l for l in t.splitlines()if not(l.startswith('IRIS_FLUSH_SNAPSHOT ')and'"slot":5'in l)))
r=dict(schema='iris.flush_frontier_snapshot_controls.v1',**{'pass':True},forced_actual_snapshot_passed=True,controls=controls,hardware_contacted=False,metadata_race_possible=True,physical_completion_claimed=False);(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(**{'pass':True},controls=len(controls))))

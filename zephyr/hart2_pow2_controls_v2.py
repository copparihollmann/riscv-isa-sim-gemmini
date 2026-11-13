#!/usr/bin/env python3
"""Counterfactuals against actual packet bytes; no hardware/timing labels."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'))
from hart2_pow2_validate_v4 import validate

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def replace(text,token,index,fn):
 lines=text.splitlines();inds=[i for i,s in enumerate(lines)if s.startswith(token+' ')];i=inds[index];obj=json.loads(lines[i].partition(' ')[2]);result=fn(obj);lines[i]=token+' '+json.dumps(obj if result is None else result,separators=(',',':'));return'\n'.join(lines)+'\n'
def run(a):
 out=a.output.resolve();out.mkdir(parents=True);text=a.stdout.read_text();normal=validate(text);rows=[]
 def reject(name,change):
  modified=change(text)
  try:validate(modified)
  except(ValueError,KeyError,TypeError)as e:rows.append(dict(name=name,rejected=True,reason=str(e)));return
  raise AssertionError('Accepted '+name)
 for key,value in [('hart',2),('logical_cpu',True),('pin',True),('operations',16),('ack',0),('start_cycle',True),('checksum',0),('failed_elements',False),('guard_ok',1),('actual_vl',0),('role','scalar.control')]:
  reject('region_'+key,lambda t,k=key,v=value:replace(t,'IRIS_REGION',0,lambda d:d.update({k:v})))
 reject('numeric_word',lambda t:replace(t,'IRIS_DATA',0,lambda d:d.update(little_endian_hex=('01'if d['little_endian_hex'][:2]!='01'else'00')+d['little_endian_hex'][2:])))
 reject('missing_region',lambda t:'\n'.join(s for s in t.splitlines()if not s.startswith('IRIS_REGION ')or json.loads(s.partition(' ')[2])['region_index']!=0)+'\n')
 reject('missing_secondary_witness_chunk',lambda t:'\n'.join(s for s in t.splitlines()if not s.startswith('IRIS_DATA ')or json.loads(s.partition(' ')[2])['region_index']!=1)+'\n')
 reject('duplicate_chunk',lambda t:t+'\n'+next(s for s in t.splitlines()if s.startswith('IRIS_DATA '))+'\n')
 reject('wrong_chunk_hart',lambda t:replace(t,'IRIS_DATA',0,lambda d:d.update(hart=2)))
 reject('wrong_chunk_offset',lambda t:replace(t,'IRIS_DATA',0,lambda d:d.update(offset=1)))
 reject('short_chunk',lambda t:replace(t,'IRIS_DATA',0,lambda d:d.update(little_endian_hex=d['little_endian_hex'][:-2])))
 reject('bool_chunk_index',lambda t:replace(t,'IRIS_DATA',0,lambda d:d.update(region_index=False)))
 reject('footer_boolean_failed',lambda t:replace(t,'IRIS_BATCH_DONE',0,lambda d:d.update(failed=False)))
 reject('footer_wrong_trial',lambda t:replace(t,'IRIS_BATCH_DONE',0,lambda d:d.update(trials=2)))
 reject('missing_completion',lambda t:'\n'.join(s for s in t.splitlines()if not s.startswith('IRIS_BATCH_DONE '))+'\n')
 reject('controller_vector',lambda t:replace(t,'IRIS_H2_CONTROL_READY',0,lambda d:d.update(scalar_only=False)))
 reject('worker_bool_logical',lambda t:replace(t,'IRIS_COMPUTE_READY',1,lambda d:d.update(logical_cpu=True)))
 reject('injected_duplicate_key',lambda t:t.replace('IRIS_REGION {','IRIS_REGION {"hart":0,',1))
 reject('fake_fatal',lambda t:t+'IRIS_FATAL {"reason_code":5,"group":648,"physical_hart":2,"logical_cpu":2}\n')
 # Mutating the declared golden source cannot override the canonical corpus.
 from hart2_pow2_validate_v4 import m
 c=m.generate();c['regions'][0]['operations']=16
 try:validate(text,corpus=c)
 except ValueError as e:rows.append(dict(name='changed_corpus_golden',rejected=True,reason=str(e)))
 else:raise AssertionError('Accepted changed golden')
 # All three-trial groups are present and reserve identities never alias train.
 c=m.generate();reserved={r['region_index']for r in c['regions']if r['split']=='protected_validation'};train=set(range(648))-reserved;assert len(reserved)==192 and len(train)==456 and not reserved&train
 for r in c['regions']:assert(r['lmul']==4 if not r['kind']else r['shape']==16)==(r['region_index']in reserved)
 result=dict(schema='iris.zephyr_hart2_pow2_controls.v1',**{'pass':True},actual_normal_proof=normal,rejected_controls=rows,count=len(rows),split=dict(training=456,protected=192,frozen_before_hardware=True,label_access=False),input_sha256={str(p.resolve()):sha(p)for p in [a.stdout,Path(__file__),ROOT/'zephyr/hart2_pow2_validate_v4.py',ROOT/'benchmarks/zephyr_hart2_pow2_v4/cases.py',ROOT/'benchmarks/zephyr_hart2_pow2_v4/corpus.json',ROOT/'benchmarks/zephyr_hart2_pow2_v4/split.json']},hardware_contacted=False)
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stdout',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a);print(json.dumps({'pass':r['pass'],'rejected_controls':r['count']}))

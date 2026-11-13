"""Independent single-case output/stage oracle. Diagnostic counters are not timing data."""
import json
STAGES=['START','ACK','PREPARE_BEGIN','BEFORE_VSETVLI','AFTER_VSETVLI','BEFORE_VMV','AFTER_VMV','BEFORE_SETUP_FENCE','AFTER_SETUP_FENCE','SETUP','KERNEL_ISSUED','FENCE_COMPLETE','KERNEL_DRAIN','OUTPUT_COMPLETE','CHECK','DONE']
def need(ok,msg):
 if not ok:raise ValueError(msg)
def golden():
 v=14695981039346656037
 for x in range(3,67):v=((v^x)*1099511628211)&((1<<64)-1)
 return v
def validate(text,negative=False):
 marks=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_RVV_DIAG ')];boot=set();stages=[];wait=set();seen=set()
 for r in marks:
  need(set(r)=={'hart','case_index','stage'}and type(r['hart'])is int and type(r['case_index'])is int and type(r['stage'])is str,'Typed stage')
  h,i,s=r['hart'],r['case_index'],r['stage'];need(h in(0,1,2)and(h,i,s)not in seen,'Unique stage');seen.add((h,i,s))
  if s=='BOOT':need(i==1,'Boot sentinel');boot.add(h);continue
  need(h in boot and i==0,'Ownboot and singlecase')
  if s=='WAIT':need(h in(0,1),'Inactivewait');wait.add(h)
  else:need(h==2,'Activehart2');stages.append(s)
 need(boot=={0,1,2}and wait=={0,1}and stages==STAGES,'Full ordered setup/kernel/fence stages')
 rows=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_REGION ')];done=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_BATCH_DONE ')]
 need(len(rows)==1 and done==[dict(failed=int(negative),cases=1,regions=1,trials=1)],'Single diagnostic normalcompletion')
 r=rows[0];need((r['hart'],r['kind'],r['sew'],r['lmul'],r['operations'],r['vector_bytes'],r['vl'],r['checked_words'])==(2,2,32,8,16,256,64,64),'Exact targeted geometry')
 need(r['expected_checksum']==golden()and r['msip_before']==r['msip_after']==0,'Independent64word and quietpending golden')
 need((r['pass']is False and(r['mismatch_or']!=0 or r['checksum']!=golden()))if negative else(r['pass']is True and r['mismatch_or']==0 and r['checksum']==golden()),'Actual allword verification / omission')
 return dict(markers=len(marks),stages=stages,word_checks=64,diagnostic_only=True,calibration_usable=False,negative=negative)

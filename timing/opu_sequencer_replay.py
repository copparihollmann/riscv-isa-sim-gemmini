#!/usr/bin/env python3
"""Replay a whole-SoC controller boundary continuously, with no internal state input."""
import argparse,hashlib,json,re,subprocess,time
from collections import Counter
from pathlib import Path
from opu_sequencer_oracle import Oracle
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mailbox(path):
 lines=path.read_text().splitlines()
 if len(lines)!=28 or any(not re.fullmatch('[0-9a-f]{16}',s)for s in lines):raise ValueError('Malformed raw TSI signature')
 v=[int(s,16)for s in lines]
 if v[:4]!=[0x4952495350524f42,1,7,0]:raise ValueError('Failed or wrong guest signature')
 rows=[dict(zip(['stage','actual','expected','cause','pc','tval','checks','done'],v[4+8*h:12+8*h]),hart=h)for h in range(3)]
 for h,row in enumerate(rows):
  if row['done']!=1 or row['checks']!=[1472,1472,2][h]or row['actual']!=row['expected']or row['cause']!=(2 if h==2 else 0):raise ValueError('Guest numerical/refusal check incomplete: '+str(row))
 return rows

def capture(log,profile):
 records=[[],[]];output=[[],[]];tb=[[],[]];n=len(profile['input']);total=n+len(profile['output'])
 for line in log.open():
  if not line.startswith('RTL_OPU_SEQUENCER '):continue
  values=line.split(' ',1)[1].strip().split(',');time=int(values[0]);hart=int(values[1]);words=[int(v,16)for v in values[2:]]
  if hart not in [0,1]or len(words)!=total:raise ValueError('Invalid physical observer width/hart')
  if tb[hart]and time!=tb[hart][-1]+2:raise ValueError('Noncontinuous controller clock sequence')
  records[hart].append(dict(zip([f['name']for f in profile['input']],words[:n])));output[hart].append(words[n:]);tb[hart].append(time)
 if not tb[0]or tb[0]!=tb[1]or any(not rows[0]['reset']for rows in records):raise ValueError('Missing actual reset/paired clock history')
 return records,output,tb

def compare_physical(profile, lines, physical):
 if len(lines)!=len(physical):raise ValueError('Missing/extra native edge')
 checks=0
 for edge,(line,goldrow)in enumerate(zip(lines,physical)):
  words=line.split()
  if len(words)!=1+len(profile['output'])or int(words[0])!=edge:raise ValueError('Malformed native edge')
  for f,word,gold in zip(profile['output'],words[1:],goldrow):
   if word=='x':continue
   if int(word)!=gold:raise ValueError('Physical mismatch edge '+str(edge)+' '+f['name'])
   checks+=1
 return checks

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();native=a.native.resolve();run=a.run.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);r=json.loads(run.read_text());assert r['exit_status']==0 and not r['timed_out'];assert sha(r['argv'][0])==r['binary_sha256']and sha(r['argv'][-1])==r['elf_sha256'];harts=mailbox(run.with_suffix('.signature'));profile=json.loads((native.parent/'ports.json').read_text());records,physical,tbs=capture(run.with_suffix('.stderr'),profile);reports=[]
 for h in range(2):
  inputs=out/f'hart{h}.input';inputs.write_text(''.join('step '+str(e)+' '+' '.join(str(i[f['name']])for f in profile['input'])+'\n'for e,i in enumerate(records[h])));command=[str(native),'--seed','17'];start=time.monotonic()
  with inputs.open()as ins,(out/f'hart{h}.stdout').open('w')as stdout,(out/f'hart{h}.stderr').open('w')as stderr:q=subprocess.run(command,stdin=ins,stdout=stdout,stderr=stderr,timeout=120)
  if q.returncode:raise RuntimeError('Actual controller dispatch refused by native SDK')
  lines=(out/f'hart{h}.stdout').read_text().splitlines()
  if len(lines)!=len(records[h]):raise ValueError('Missing actual controller edges')
  assert compare_physical(profile,lines,physical[h])>0
  checks=0;oraclechecks=0;oracle=Oracle();coverage=Counter();active=[]
  for e,(line,i,expected)in enumerate(zip(lines,records[h],physical[h])):
   fields=line.split();assert len(fields)==1+len(expected)and int(fields[0])==e;semantic=oracle.evaluate(i)
   for f,word,gold in zip(profile['output'],fields[1:],expected):
    if word=='x':continue
    if int(word)!=gold:raise ValueError(f'Whole-SoC mismatch hart{h} edge{e}/TB{tbs[h][e]} {f["name"]}: SDK{word} RTL{gold}')
    checks+=1
    # The oracle consumes only accepted dispatch + external resource inputs.
    # Explicit SDK definedness avoids treating random reset payload as data.
    if f['name']not in semantic or semantic[f['name']]!=gold:raise ValueError(f'Independent semantic mismatch hart{h} edge{e} {f["name"]}')
    oraclechecks+=1
   if i['io_dis_valid']and semantic['io_dis_ready']:coverage['accepted_dispatches']+=1;active.append({'edge':e,'tb':tbs[h][e],'instruction':i['io_dis_bits_bits'],'tm':i['io_dis_bits_vconfig_vtype_tm'],'tn':i['io_dis_bits_vconfig_vl'],'tk':i['io_dis_bits_vconfig_vtype_tk']})
   if semantic['io_iss_valid']:coverage['issued_microops']+=1
   if semantic['io_write_valid']:coverage['readout_writebacks']+=1
   oracle.commit(i)
  (out/f'hart{h}.dispatches.json').write_text(json.dumps(active,indent=2)+'\n');reports.append({'hart':h,'edges':len(lines),'tb_start':tbs[h][0],'tb_end':tbs[h][-1],'defined_physical_checks':checks,'independent_semantic_checks':oraclechecks,'coverage':dict(coverage),'stats':dict(oracle.stats),'argv':command,'host_seconds':time.monotonic()-start})
 # Corrupt a meaningful late physical output, preserving complete trace shape.
 corruptions=[]
 for name in ['io_iss_valid','io_iss_bits_mrf_idx_0','io_write_mask','io_wsboard','io_rvs1_bits_eg']:
  f=next(f for f in profile['output']if f['name']==name);rows=(out/'hart0.stdout').read_text().splitlines();edge=next(e for e,row in enumerate(rows)if row.split()[1+f['index']]not in ['x','0']);gold=physical[0][edge][f['index']];bad=gold^1
  mutated=[row[:]for row in physical[0]];mutated[edge][f['index']]=bad
  try:compare_physical(profile,rows,mutated)
  except ValueError as ex:corruptions.append({'field':name,'hart':0,'edge':edge,'original':gold,'corrupted':bad,'rejected':True,'reason':str(ex)})
  else:raise ValueError('Checker missed physical mutation')
 inputs=[Path(__file__),R/'timing/opu_sequencer_oracle.py',native,native.parent/'build.json',native.parent/'ports.json',run,run.with_suffix('.stdout'),run.with_suffix('.stderr'),run.with_suffix('.signature'),Path(r['argv'][0]),Path(r['argv'][-1])];report={'schema':'iris.opu_sequencer_whole_rtl_replay.v1','input_sha256':{str(p):sha(p)for p in inputs},'harts':reports,'guest_mailbox':harts,'checker_corruptions':corruptions,'actual_reset':True,'internal_state_inputs':0,'injected_delay_edges':0,'hardware_contacted':False,'source_design_matches_ethan_image':False,'full_soc_certified':False,'timing_certified':False};report['artifact_sha256']={str(p.relative_to(out)):sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'harts':reports,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()

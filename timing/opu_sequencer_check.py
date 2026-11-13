#!/usr/bin/env python3
"""Generate legal dispatched operations independently, then compare every defined port."""
import argparse,hashlib,json,random,subprocess,time
from pathlib import Path
from opu_sequencer_oracle import Oracle
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def instruction(kind,tile=0,tn=32,tm=32,tk=4,index=0,column=0,fa=0,fb=0,rm=0,base=8,vat=0):
 bits={'int8':0xf0000077,'fp8':0xf0001077,'zero':0x41e06057,'discard':0x41c06057,'mvin':0x5c006057,'mvout':0x41f06057}[kind]
 if kind in ['int8','fp8']:bits|=(16<<20)|(8<<15)|((8*tile+fa)<<7)
 elif kind in ['zero','discard']:bits|=8*tile<<7
 elif kind=='mvin':bits|=base<<20|5<<15
 else:bits|=base<<7|5<<15
 return {'kind':kind,'bits':bits,'tn':tn,'tm':tm,'tk':tk,'tss':(tile<<29)|(column<<24)|index,'alt':fb,'sew':0 if kind in ['int8','fp8']else 2,'rm':rm,'emul':2 if kind in ['mvin','mvout']else 0,'vat':vat}
def corpus():
 ops=[]
 def add(kind,**kw):ops.append(dict(id='opu.%05d'%len(ops),**instruction(kind,vat=len(ops)%32,**kw)))
 # Directed history: adjacent distinct entries, repeated same entry, and the
 # transition from FP8 to every non-FP8 operation. No fitted stall constants.
 for t in [0,1,2,3,3,3,0,0]:add('fp8',tile=t,tm=1,tn=1,tk=1)
 for kind in ['int8','zero','discard','mvin','mvout']:
  add('fp8',tm=1,tn=1,tk=1);add(kind,tm=1,tn=1,tk=1)
 # Back-to-back readout positions deliberately target equal completion cycles.
 for q in [0,1,2,3,3,2,1,0]*3:add('mvout',index=q,tn=1,base=8)
 for kind in ['int8','fp8','zero']:
  for tm in [0,1,15,16,17,31,32]:
   for tn in [0,1,15,16,17,31,32]:
    for tk in ([0,1,2,3,4]if kind!='zero'else[0]):
     for tile in range(4):
      for fmt in (range(4)if kind!='zero'else[0]):add(kind,tile=tile,tn=tn,tm=tm,tk=tk,fa=fmt&1,fb=fmt>>1,rm=(tm+tn+tk+tile+fmt)%5)
 # Every TSS index, tile, direction, edge clamp, and row/column pattern.
 for kind in ['mvin','mvout']:
  for tile in range(4):
   for column in range(2):
    for index in range(32):
     for tn in [0,1,3,4,7,8,9,15,16,17,31,32]:add(kind,tile=tile,index=index,column=column,tn=tn,base=8+4*(index%4))
 for tile in range(4):add('discard',tile=tile,tm=0,tn=0,tk=0)
 return ops

def generate(out,profile):
 ops=corpus();(out/'instructions.json').write_text(json.dumps(ops,indent=2)+'\n');oracle=Oracle();at=0;records=[];expects=[];instructions={f['name']:f['index']for f in profile['input']}
 while at<len(ops)or oracle.busy or oracle.readouts or oracle.fp8 or oracle.edge<4:
  if oracle.edge>700000:raise RuntimeError('Finite corpus did not drain')
  i={f['name']:0 for f in profile['input']};i.update(reset=int(oracle.edge<2),io_rvs1_ready=1,io_rvs2_ready=1,io_pipe_write_req_available=1,io_vat_head=oracle.edge%32)
  if oracle.edge>=3 and at<len(ops):
   op=ops[at];i.update(io_dis_valid=1,io_dis_bits_bits=op['bits'],io_dis_bits_vconfig_vl=op['tn'],io_dis_bits_vconfig_vtype_tm=op['tm'],io_dis_bits_vconfig_vtype_tk=op['tk'],io_dis_bits_vconfig_vtype_altfmt=op['alt'],io_dis_bits_vconfig_vtype_vsew=op['sew'],io_dis_bits_rs1_data=op['tss'],io_dis_bits_vat=op['vat'],io_dis_bits_rm=op['rm'],io_dis_bits_emul=op['emul'])
  if oracle.current and oracle.busy:
   b,a,vd=oracle.current.eg()
   if oracle.edge%17==0:i['io_rvs1_ready']=0
   if oracle.edge%19==0:i['io_rvs2_ready']=0
   if oracle.edge%23==0:i['io_older_writes']=1<<b
   if oracle.edge%29==0:i['io_older_reads']=1<<vd
   if oracle.edge%31==0:i['io_pipe_write_req_available']=0
   if oracle.edge%37==0:i['io_older_writes']|=1<<a
   if oracle.edge%41==0:i['io_older_writes']|=1<<vd
  expected=oracle.evaluate(i);expects.append(expected);records.append(i)
  if i['io_dis_valid']and expected['io_dis_ready']:at+=1
  oracle.commit(i)
 (out/'inputs.txt').write_text(''.join('step '+str(e)+' '+' '.join(str(i[f['name']])for f in profile['input'])+'\n'for e,i in enumerate(records)))
 (out/'expected.json').write_text(json.dumps(expects,separators=(',',':'))+'\n');(out/'dispatches.json').write_text(json.dumps(oracle.dispatches,indent=2)+'\n');(out/'issues.json').write_text(json.dumps(oracle.issues,separators=(',',':'))+'\n')
 return records,expects,oracle

def compare(profile,lines,records,expects):
 if len(lines)!=len(records):raise ValueError('Missing/extra output edges')
 count=0;unknown=0
 for e,(line,i,expected)in enumerate(zip(lines,records,expects)):
  row=line.split();assert len(row)==1+len(profile['output'])and int(row[0])==e,'Malformed edge/output width'
  for f,t in zip(profile['output'],row[1:]):
   name=f['name']
   if t=='x':
    unknown+=1
    # These fields are required once an explicit reset has completed. Every
    # accepted dispatch initializes its later meaningful payload by construction.
    if e>=2 and name in expected:raise ValueError('Required defined output hidden at edge '+str(e)+' '+name)
    continue
   if e==0:raise ValueError('Invented definedness before any physical reset')
   if name not in expected:raise ValueError('Undefined payload advertised defined at edge '+str(e)+' '+name)
   if int(t)!=expected[name]:raise ValueError('OPU mismatch edge '+str(e)+' '+name+': '+t+' != '+str(expected[name]))
   count+=1
 return count,unknown

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();native=a.native.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);profile=json.loads((native.parent/'ports.json').read_text());started=time.monotonic();records,expects,oracle=generate(out,profile);runs=[]
 for seed in [0,17]:
  command=[str(native),'--seed',str(seed)];start=time.monotonic()
  with(out/'inputs.txt').open()as ins,(out/f'seed{seed}.stdout').open('w')as stdout,(out/f'seed{seed}.stderr').open('w')as stderr:q=subprocess.run(command,stdin=ins,stdout=stdout,stderr=stderr,timeout=120)
  if q.returncode:raise RuntimeError('Native controller refused valid corpus')
  checks,unknown=compare(profile,(out/f'seed{seed}.stdout').read_text().splitlines(),records,expects);runs.append({'seed':seed,'argv':command,'exit_status':q.returncode,'host_seconds':time.monotonic()-start,'edges':len(records),'defined_checks':checks,'unconsumed_undefined_words':unknown})
 if (out/'seed0.stdout').read_bytes()!=(out/'seed17.stdout').read_bytes():raise ValueError('Defined behavior depends on unknown reset bits')
 # Repeated combinational evaluation must not spend extra FP8/VRF/readout time.
 text=(out/'inputs.txt').read_text().replace('step ','repeat ');q=subprocess.run([str(native),'--seed','91'],input=text,text=True,capture_output=True,timeout=120);(out/'repeat.stdout').write_text(q.stdout);(out/'repeat.stderr').write_text(q.stderr)
 if q.returncode or q.stdout!=(out/'seed0.stdout').read_text():raise ValueError('Repeated settle changes meaningful sequencing')
 corruptions=[];raw=(out/'seed0.stdout').read_text().splitlines()
 for name in ['io_iss_bits_mrf_idx_0','io_rvs1_bits_eg','io_seq_hazard_bits_rintent','io_write_mask','io_wsboard','io_iss_valid']:
  f=next(f for f in profile['output']if f['name']==name);changed=raw[:];e=next(e for e in range(4,len(raw))if name in expects[e]and expects[e][name]!=0);row=changed[e].split();row[1+f['index']]=str(int(row[1+f['index']])^1);changed[e]=' '.join(row)
  try:compare(profile,changed,records,expects)
  except ValueError as ex:corruptions.append({'field':name,'edge':e,'rejected':True,'reason':str(ex)})
  else:raise ValueError('Checker missed corruption '+name)
 # Fail-closed dispatcher boundary and lifecycle errors, no accepted guest edge.
 negatives=[];valid=records[3].copy();ix={f['name']:f['index']for f in profile['input']}
 for label,field,value in [('bad_opcode','io_dis_bits_bits',0),('wrong_mm_sew','io_dis_bits_vconfig_vtype_vsew',2),('too_large_tm','io_dis_bits_vconfig_vtype_tm',33),('too_large_tn','io_dis_bits_vconfig_vl',33),('too_large_tk','io_dis_bits_vconfig_vtype_tk',5),('unresolved_frm','io_dis_bits_rm',7),('overwide_vat','io_dis_bits_vat',32)]:
  i=valid.copy();i[field]=value;payload=''.join((out/'inputs.txt').read_text().splitlines(True)[:3])+'step 3 '+' '.join(str(i[f['name']])for f in profile['input'])+'\n';q=subprocess.run([str(native),'--seed','0'],input=payload,text=True,capture_output=True);negatives.append({'label':label,'exit_status':q.returncode,'stderr':q.stderr});assert q.returncode==2
 for label,payload in [('sample_before_evaluate','sample\n'),('commit_before_evaluate','commit\n'),('double_commit',(out/'inputs.txt').read_text().splitlines(True)[0]+'commit\n'),('dispatch_before_reset','step 0 '+' '.join(str(valid[f['name']])for f in profile['input'])+'\n')]:
  q=subprocess.run([str(native),'--seed','0'],input=payload,text=True,capture_output=True);negatives.append({'label':label,'exit_status':q.returncode,'stderr':q.stderr});assert q.returncode==2
 report={'schema':'iris.opu_sequencer_semantic_proof.v1','input_sha256':{str(p):sha(p)for p in [native,native.parent/'build.json',native.parent/'ports.json',Path(__file__),R/'timing/opu_sequencer_oracle.py']},'instruction_count':len(oracle.dispatches),'edges':len(records),'runs':runs,'stats':dict(oracle.stats),'repeat_evaluate_equal':True,'seeds_defined_equal':True,'checker_corruptions':corruptions,'negative_controls':negatives,'host_seconds':time.monotonic()-started,'oracle_uses_generated_state':False,'hardware_contacted':False,'full_soc_certified':False,'timing_certified':False}
 report['artifact_sha256']={str(p.relative_to(out)):sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'instructions':len(oracle.dispatches),'edges':len(records),'stats':dict(oracle.stats),'defined_checks_per_seed':runs[0]['defined_checks'],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()

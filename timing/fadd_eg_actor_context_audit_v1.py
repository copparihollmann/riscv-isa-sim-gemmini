"""Read-only verification of native guest-context errors against actual ELFs."""
import hashlib,json,re,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(text,elf,hart):
 rows=re.findall(r'\bhart=(\d+) pc=(\d+) raw=(\d+) VL=(\d+) SEW=(\d+) LMUL=([0-9.]+) frm=(\d+) flags=(\d+)',text)
 if len(rows)!=1:raise ValueError('Exactly one typed actionable guest context required')
 h,pc,raw,vl,sew,lm,frm,flags=rows[0];h,pc,raw,vl,sew,frm,flags=map(int,(h,pc,raw,vl,sew,frm,flags))
 if h!=hart:raise ValueError('Wrong hart in context')
 data=elf.read_bytes();head=struct.unpack_from('<16sHHIQQQIHHHHHH',data);matches=[]
 for i in range(head[10]):
  s=struct.unpack_from('<IIQQQQQQ',data,head[5]+i*head[9])
  if s[0]==1 and s[1]&1 and s[3]<=pc and pc+4<=s[3]+s[5]:matches.append(int.from_bytes(data[s[2]+pc-s[3]:s[2]+pc-s[3]+4],'little'))
 if matches!=[raw]or raw&0xfc00707f!=0x1057:raise ValueError('Context PC/raw differs from actual VFADD instruction')
 return dict(hart=h,pc=pc,raw=raw,VL=vl,SEW=sew,LMUL=float(lm),frm=frm,flags=flags)
def main():
 d=ROOT/'build/FADD-EG-actor-corrective-directed-v2';out=ROOT/'build/FADD-EG-actor-context-audit-v1';out.mkdir(exist_ok=False)
 report=json.loads((d/'report.json').read_text());rows=[];inputs=[Path(__file__).resolve(),d/'report.json'];refusals=0
 for run in report['runs']:
  if not run['name'].startswith('refusal-'):continue
  hart=int(re.search(r'-h(\d+)-',run['name'])[1]);elf=Path(run['argv'][-1]);error=d/run['name']/'stderr';text=error.read_text();row=check(text,elf,hart);row['name']=run['name'];rows.append(row);inputs +=[elf,error]
  # The known error's context is mutated, never any native/ELF input.
  original=str(row['raw']);bad=text.replace('raw='+original,'raw='+str(row['raw']^128))
  for changed in [bad,text.replace('hart='+str(hart)+' pc=','hart='+str(1-hart)+' pc=')]:
   try:check(changed,elf,hart)
   except ValueError:refusals+=1
   else:raise ValueError('Changed context escaped independent ELF validation')
 if len(rows)!=16 or refusals!=32:raise ValueError('Complete context/refusal coverage')
 result=dict(schema='iris.FADD_EG_guest_context_ELF_audit.v1',**{'pass':True},contexts=rows,actual_context_ELF_matches=16,wrong_hart_or_opcode_controls=32,
    hardware_contacted=False,input_sha256={str(p):sha(p)for p in inputs})
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()

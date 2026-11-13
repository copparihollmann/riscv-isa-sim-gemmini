#!/usr/bin/env python3
"""Independent private-slot layout/kernel/typed metadata mutation controls."""
import copy,json,struct
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'firesim'))
from pow2_scalar_private_v2_campaign import inspect,Elf,validator
from batch_runner import digest

def main():
 out=ROOT/'build/pow2-scalar-private-guards-v2';out.mkdir();b=ROOT/'build/pow2-scalar-private-fit-v4';raw=(b/'scalar.elf').read_bytes();c=json.loads((b/'corpus.json').read_text());layout=json.loads((b/'layout.json').read_text());proof=inspect(raw,c,layout);controls=[]
 def reject(name,fn):
  try:fn()
  except(ValueError,TypeError,KeyError,struct.error):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Accepted '+name)
 e=Elf(raw)
 def alter(address):
  data=bytearray(raw);data[e.file_offset(address,1)]^=1;meta=copy.deepcopy(layout);meta['elf_sha256']=__import__('hashlib').sha256(data).hexdigest();return bytes(data),meta
 for name,address in [('table-golden',e.syms['experiments'][0]+24),('kernel-integer',e.syms['scalar_pow2_integer_dependent'][0]+8),('kernel-FADD',proof['kernels']['fp32_independent4']['body_address']),('CLINT-load',0x80000658),('sentinel',e.syms['scalar_measurements_done'][0])]:
  blob,meta=alter(address);reject(name,lambda:inspect(blob,c,meta))
 old=ROOT/'build/pow2-scalar-fit-v1';reject('shared-parent-not-private',lambda:inspect((old/'scalar.elf').read_bytes(),c,json.loads((old/'layout.json').read_text())))
 normal=(ROOT/'build/pow2-scalar-private-v4-seed0/stdout').read_text();lines=normal.splitlines();i=next(i for i,s in enumerate(lines)if s.startswith('IRIS_REGION '));row=json.loads(lines[i].split(' ',1)[1]);row['values'][1]=False;bad=lines[:];bad[i]='IRIS_REGION '+json.dumps(row);reject('boolean-outputword',lambda:validator().validate('\n'.join(bad),c))
 i=next(i for i,s in enumerate(lines)if s.startswith('IRIS_BATCH_DONE '));row=json.loads(lines[i].split(' ',1)[1]);row['failed']=False;bad=lines[:];bad[i]='IRIS_BATCH_DONE '+json.dumps(row);reject('boolean-DONE',lambda:validator().validate('\n'.join(bad),c))
 ids={str(p):digest(p)for p in[Path(__file__).resolve(),ROOT/'firesim/pow2_scalar_private_v2_campaign.py',b/'scalar.elf',b/'corpus.json',b/'layout.json',ROOT/'calibration/pow2-scalar-private-v2/split.json']};r=dict(schema='iris.pow2_scalar_private_guards.v2',status='passed',positive_compiled_private_slots=True,negative_controls=controls,no_hardware_contact=True,reserved_timing_labels_consumed=False,input_sha256=ids);(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status='passed',controls=len(controls),report_sha256=digest(out/'report.json'))))
if __name__=='__main__':main()

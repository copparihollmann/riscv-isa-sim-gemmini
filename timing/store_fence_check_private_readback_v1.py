#!/usr/bin/env python3
"""Independent corruption controls for complete intentional debugger readback."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'benchmarks/pow2_scalar_private_v2'));from readback import decode

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=ROOT/'build/pow2-scalar-private-readback-guards-v1';out.mkdir();b=ROOT/'build/pow2-scalar-private-fit-v4';run=ROOT/'build/pow2-scalar-private-e8ed-FADD-ON-readback-v1';c=json.loads((b/'corpus.json').read_text());layout=json.loads((b/'layout.json').read_text());text=(run/'stderr').read_text();assert len(decode(text,c,layout))==576;lines=text.splitlines();controls=[]
 def reject(name,changed):
  try:decode('\n'.join(changed)+'\n',c,layout)
  except(ValueError,TypeError,KeyError):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Accepted '+name)
 reject('missing-last-field',lines[:-1]);bad=lines[:];bad[2]='0x000000000000023f';reject('incomplete-count',bad);bad=lines[:];bad[3]='0x0000000000000001';reject('wrong-case-index',bad);bad=lines[:];bad[8]='0x0000000000000000';reject('omitted-numerical-word',bad);bad=lines[:];bad[6]=bad[5];reject('nonforward-cycle-window',bad);bad=lines[:];bad[-1]='0x0000000000000000';reject('unstable-trailing-count',bad)
 paths=[Path(__file__).resolve(),ROOT/'benchmarks/pow2_scalar_private_v2/readback.py',run/'run.json',run/'stderr',b/'layout.json',b/'corpus.json'];r=dict(schema='iris.pow2_scalar_private_readback_controls.v1',status='passed',normal_guest_exit_claimed=False,actual_full576_buffer_verified=True,negative_controls=controls,hardware_contacted=False,reserved_hardware_timing_labels_consumed=False,input_sha256={str(p):sha(p)for p in paths});(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status='passed',controls=len(controls),report_sha256=sha(out/'report.json'))))
if __name__=='__main__':main()

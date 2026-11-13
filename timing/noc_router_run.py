#!/usr/bin/env python3
import argparse,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];CAP=R/'build/rtl-memory-return-path-v1-final';B=R/'build/noc-router-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('case',choices=['original9','control8','fenced9']);a=p.parse_args();name={'original9':'vector-memory-h2-9.elf','control8':'vector-memory-h2-8.elf','fenced9':'vector-memory-h2-9-load-fences.elf'}[a.case];base=B/a.case
 if base.with_suffix('.json').exists():raise ValueError('Refuse to overwrite run')
 old=json.loads((CAP/'build/rtl-loader-diag/vector-memory-h2-9-va2.json').read_text())['argv'];old[0]=str(B/'simulator-router-boundary');old[-1]=str(CAP/'build/rtl-loader-diag'/name);old.insert(-1,'+signature='+str(base.with_suffix('.signature')));old.insert(-1,'+signature-granularity=8');t=time.monotonic()
 with base.with_suffix('.stdout').open('wb') as out,base.with_suffix('.stderr').open('wb') as err:
  try:q=subprocess.run(old,cwd=R,stdout=out,stderr=err,timeout=180);code=q.returncode;timed=False
  except subprocess.TimeoutExpired:code=None;timed=True
 j={'argv':old,'exit_status':code,'timed_out':timed,'host_seconds':time.monotonic()-t,'binary_sha256':sha(old[0]),'elf_sha256':sha(old[-1]),'build_sha256':sha(B/'build.json'),'stdout_sha256':sha(base.with_suffix('.stdout')),'stderr_sha256':sha(base.with_suffix('.stderr')),'rtl_modified':False,'hardware_contacted':False};base.with_suffix('.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps(j))
if __name__=='__main__':main()

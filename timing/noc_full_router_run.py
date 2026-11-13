#!/usr/bin/env python3
import argparse,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];CAP=R/'build/rtl-memory-return-path-v1-final';OUT=R/'build/noc-full-router-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('case',choices=['original9','control8','fenced9','peer']);a=p.parse_args();base=OUT/a.case
 if base.with_suffix('.json').exists():raise ValueError('Refuse to overwrite full physical run')
 elfs={'original9':CAP/'build/rtl-loader-diag/vector-memory-h2-9.elf','control8':CAP/'build/rtl-loader-diag/vector-memory-h2-8.elf','fenced9':CAP/'build/rtl-loader-diag/vector-memory-h2-9-load-fences.elf','peer':R/'build/noc-full-router-guests/peer-local-nonlocal.elf'}
 argv=json.loads((CAP/'build/rtl-loader-diag/vector-memory-h2-9-va2.json').read_text())['argv'];argv[0]=str(OUT/'simulator-full-boundary');argv[-1]=str(elfs[a.case]);argv=[x.replace('+max-cycles=130000','+max-cycles='+str(250000 if a.case=='peer' else 130000)) for x in argv];argv.insert(-1,'+signature='+str(base.with_suffix('.signature')));argv.insert(-1,'+signature-granularity=8');t=time.monotonic()
 with base.with_suffix('.stdout').open('wb') as out,base.with_suffix('.stderr').open('wb') as err:
  try:q=subprocess.run(argv,cwd=R,stdout=out,stderr=err,timeout=180);status=q.returncode;timed=False
  except subprocess.TimeoutExpired:status=None;timed=True
 j={'argv':argv,'exit_status':status,'timed_out':timed,'host_seconds':time.monotonic()-t,'binary_sha256':sha(argv[0]),'elf_sha256':sha(argv[-1]),'build_sha256':sha(OUT/'build.json'),'stdout_sha256':sha(base.with_suffix('.stdout')),'stderr_sha256':sha(base.with_suffix('.stderr')),'rtl_modified':False,'hardware_contacted':False};base.with_suffix('.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps(j))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Run finite independent whole-SoC physical TL captures, never an FPGA."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];OUT=R/'build/noc-network-rtl-v1';CAP=R/'build/rtl-memory-return-path-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('case',choices=['original9','control8','fenced9','peer','coherent']);a=p.parse_args();base=OUT/a.case
 if base.with_suffix('.json').exists():raise ValueError('Preserve prior whole-RTL run')
 elfs={'original9':CAP/'build/rtl-loader-diag/vector-memory-h2-9.elf','control8':CAP/'build/rtl-loader-diag/vector-memory-h2-8.elf','fenced9':CAP/'build/rtl-loader-diag/vector-memory-h2-9-load-fences.elf','peer':R/'build/noc-full-router-guests/peer-local-nonlocal.elf','coherent':R/'build/noc-network-guests-v1/all-harts-coherent.elf'};argv=json.loads((CAP/'build/rtl-loader-diag/vector-memory-h2-9-va2.json').read_text())['argv'][:];argv[0]=str(OUT/'simulator-network-boundary');argv[-1]=str(elfs[a.case]);argv=[x.replace('+max-cycles=130000','+max-cycles='+str(400000 if a.case=='coherent'else 250000 if a.case=='peer'else 130000))for x in argv];argv.insert(-1,'+signature='+str(base.with_suffix('.signature')));argv.insert(-1,'+signature-granularity=8');started=time.monotonic()
 with base.with_suffix('.stdout').open('wb')as stdout,base.with_suffix('.stderr').open('wb')as stderr:
  try:q=subprocess.run(argv,cwd=R,stdout=stdout,stderr=stderr,timeout=300);code=q.returncode;timed=False
  except subprocess.TimeoutExpired:code=None;timed=True
 report={'schema':'iris.network_whole_rtl_run.v1','argv':argv,'exit_status':code,'timed_out':timed,'host_seconds':time.monotonic()-started,'binary_sha256':sha(argv[0]),'elf_sha256':sha(argv[-1]),'build_sha256':sha(OUT/'build.json'),'stdout_sha256':sha(base.with_suffix('.stdout')),'stderr_sha256':sha(base.with_suffix('.stderr')),'signature_sha256':sha(base.with_suffix('.signature'))if base.with_suffix('.signature').exists()else None,'RTL_logic_modified':False,'hardware_contacted':False};base.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()

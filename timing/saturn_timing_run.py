#!/usr/bin/env python3
"""Finite independent actual three-hart runtime captures; no FPGA actions."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'build/saturn-timing-rtl-v1';CAP=R/'build/opu-sequencer-component-v2-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('case',choices=['vme','rvv','fpcomp','shared-fpu']);a=p.parse_args();base=O/a.case
 if base.with_suffix('.json').exists():raise ValueError('Preserve previous runtime capture')
 elfs={'vme':CAP/'build/opu-sequencer-guests-v1/all-harts-vme.elf','rvv':R/'build/saturn-timing-guests-v1/rvv-all-harts.elf','shared-fpu':R/'build/saturn-timing-fpu-guests-v1/shared-fpu-all-harts.elf','fpcomp':R/'build/rtl-selected-vector-references-v1/build/rtl-loader-diag/fpcomp-aggregate-load-fences.elf'};elf=elfs[a.case];assert elf.is_file();old=json.loads((CAP/'build/opu-sequencer-rtl-v1/all-harts-vme.json').read_text());argv=old['argv'][:];argv[0]=str(O/'simulator-saturn-boundary');argv[-1]=str(elf);argv=[x for x in argv if not x.startswith('+signature')];argv=[x.replace('+max-cycles=300000','+max-cycles=400000')for x in argv];argv.insert(-1,'+signature='+str(base.with_suffix('.signature')));argv.insert(-1,'+signature-granularity=8');start=time.monotonic()
 with base.with_suffix('.stdout').open('wb')as stdout,base.with_suffix('.stderr').open('wb')as stderr:
  try:q=subprocess.run(argv,cwd=R,stdout=stdout,stderr=stderr,timeout=360);code=q.returncode;timed=False
  except subprocess.TimeoutExpired:code=None;timed=True
 report={'schema':'iris.saturn_runtime_whole_rtl_run.v1','case':a.case,'argv':argv,'exit_status':code,'timed_out':timed,'host_seconds':time.monotonic()-start,'binary_sha256':sha(argv[0]),'elf_sha256':sha(argv[-1]),'observer_build_sha256':sha(O/'build.json'),'stdout_sha256':sha(base.with_suffix('.stdout')),'stderr_sha256':sha(base.with_suffix('.stderr')),'signature_sha256':sha(base.with_suffix('.signature'))if base.with_suffix('.signature').exists()else None,'RTL_logic_modified':False,'hardware_contacted':False,'whole_unit_definedness_certified':False};base.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()

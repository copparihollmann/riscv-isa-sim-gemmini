#!/usr/bin/env python3
"""Run the finite independent whole-SoC three-hart VME controller capture."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'build/opu-sequencer-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 base=O/'all-harts-vme'
 if base.with_suffix('.json').exists():raise ValueError('Preserve previous whole-RTL capture')
 old=json.loads((R/'build/rtl-memory-return-path-v1-final/build/rtl-loader-diag/vector-memory-h2-9-va2.json').read_text());argv=old['argv'][:];argv[0]=str(O/'simulator-opu-boundary');argv[-1]=str(R/'build/opu-sequencer-guests-v1/all-harts-vme.elf');argv=[x.replace('+max-cycles=130000','+max-cycles=300000')for x in argv];argv.insert(-1,'+signature='+str(base.with_suffix('.signature')));argv.insert(-1,'+signature-granularity=8');started=time.monotonic()
 with base.with_suffix('.stdout').open('wb')as stdout,base.with_suffix('.stderr').open('wb')as stderr:
  try:q=subprocess.run(argv,cwd=R,stdout=stdout,stderr=stderr,timeout=300);code=q.returncode;timed=False
  except subprocess.TimeoutExpired:code=None;timed=True
 report={'schema':'iris.opu_sequencer_whole_rtl_run.v1','argv':argv,'exit_status':code,'timed_out':timed,'host_seconds':time.monotonic()-started,'binary_sha256':sha(argv[0]),'elf_sha256':sha(argv[-1]),'observer_build_sha256':sha(O/'build.json'),'guest_build_sha256':sha(R/'build/opu-sequencer-guests-v1/build.json'),'stdout_sha256':sha(base.with_suffix('.stdout')),'stderr_sha256':sha(base.with_suffix('.stderr')),'signature_sha256':sha(base.with_suffix('.signature'))if base.with_suffix('.signature').exists()else None,'RTL_logic_modified':False,'hardware_contacted':False};base.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()

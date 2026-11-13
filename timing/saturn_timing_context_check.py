#!/usr/bin/env python3
"""Actual three-unit interleaving versus independent qualified whole-SoC ports."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();sdk=a.sdk.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);reference=R/'build/saturn-timing-component-v1-final';fast=R/'build/saturn-timing-fast-component-v1-final';receipt=json.loads((sdk/'build.json').read_text());base=fast/'build/saturn-timing-fast-v1/sdk'if receipt['variant']=='fast'else reference/'build/saturn-timing-sdk-v1';source=out/'test.cpp';shutil.copy2(R/'timing/saturn_timing_context_test.cpp',source);include=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');common=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(include),'-I'+str(include/'vltstd')];commands=[common+['-DIRIS_CONTEXT_API','-I'+str(sdk/'sdk'),str(source),str(sdk/'sdk/libiris_saturn_timing.a'),'-latomic','-o',str(out/'context-test')],common+['-I'+str(base/'sdk'),str(source),str(base/'sdk/libiris_saturn_timing.a'),'-latomic','-o',str(out/'original-host-control')]];inputs=[Path(__file__),R/'timing/saturn_timing_context_test.cpp',source,sdk/'sdk/saturn_timing.hpp',sdk/'sdk/libiris_saturn_timing.a',sdk/'build.json',base/'sdk/saturn_timing.hpp',base/'sdk/libiris_saturn_timing.a',reference/'report.json',fast/'report.json',Path('/usr/bin/g++'),include/'verilated.h',include/'verilated.cpp']
 with(out/'build.log').open('w')as log:
  for command in commands:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 def args(case):
  result=[]
  for h in range(3):
   folder=fast/'build/saturn-timing-fast-replay-v1'/case;mask=reference/'build/saturn-timing-replay-v2'/case/f'hart{h}.masks.bin';paths=[folder/f'hart{h}.input',folder/f'hart{h}.stdout',mask];inputs.extend(paths);result.extend(map(str,paths))
  return result
 control_command=[str(out/'original-host-control'),'0',*args('rvv')];q=subprocess.run(control_command,capture_output=True,text=True,timeout=30);(out/'original-host-control.stdout').write_text(q.stdout);(out/'original-host-control.stderr').write_text(q.stderr)
 if q.returncode!=2 or 'Construction changed caller context'not in q.stderr:raise ValueError('Expected original host context leak was not reproduced')
 control={'argv':control_command,'exit_status':q.returncode,'diagnostic':q.stderr};reports=[]
 for case,mode in[('rvv',0),('rvv',1),('rvv',2),('vme',0),('vme',1)]:
  command=[str(out/'context-test'),str(mode),*args(case)];label=case+'-mode'+str(mode)
  with(out/(label+'.stdout')).open('w')as stdout,(out/(label+'.stderr')).open('w')as stderr:q=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=300)
  if q.returncode:raise ValueError('Interleaved own-context test failed '+label)
  result=next(json.loads(x.split(' ',1)[1])for x in(out/(label+'.stderr')).read_text().splitlines()if x.startswith('SATURN_CONTEXT_RESULT '));reports.append({'case':case,'argv':command,**result})
 report={'schema':'iris.saturn_own_context_interleaving_proof.v1','pass':True,'variant':receipt['variant'],'runs':reports,'original_host_leak_control':control,'argv':commands,'input_sha256':{str(p):sha(p)for p in inputs},'native_sha256':sha(out/'context-test'),'source_core_edges':sum(r['source_core_edges']for r in reports),'qualified_field_checks':sum(r['qualified_field_checks']for r in reports),'caller_context_checks':sum(r['caller_context_checks']for r in reports),'raw_unreset_bit_order_invariance_claimed':False,'global_Verilator_RNG_stream_isolated':False,'initialized_active_field_order_invariance_verified':True,'source_RTL_or_model_objects_modified':False,'hardware_contacted':False};report['artifact_sha256']={str(p.relative_to(out)):sha(p)for p in out.rglob('*')if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k]for k in['variant','source_core_edges','qualified_field_checks','caller_context_checks','native_sha256']}));print(sha(out/'report.json'))
if __name__=='__main__':main()

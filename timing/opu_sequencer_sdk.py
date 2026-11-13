#!/usr/bin/env python3
"""Package a port-only C++ SDK and measure direct stepping without text IO."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--model',type=Path,required=True);p.add_argument('--proof',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();b=a.model.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sdk=out/'sdk';sdk.mkdir();c=Path('/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++');ar=c.with_name('x86_64-conda-linux-gnu-ar');objects=sorted((b/'model').glob('VOPUSequencer*.o'))+[b/'model/opu_sequencer.o']+sorted((b/'model').glob('verilated*.o'))
 for name in ['opu_sequencer.hpp','opu_sequencer_schema.hpp']:shutil.copyfile(b/'source'/name,sdk/name)
 commands=[[str(ar),'rcs',str(sdk/'libiris_opu_sequencer.a')]+list(map(str,objects)),[str(c),'-O3','-std=c++20','-I'+str(sdk),str(R/'timing/opu_sequencer_bench.cpp'),str(sdk/'libiris_opu_sequencer.a'),'-pthread','-latomic','-o',str(out/'benchmark')]]
 with(out/'build.log').open('w')as log:
  for command in commands:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 command=[str(out/'benchmark'),str(a.proof.resolve()/'inputs.txt')];q=subprocess.run(command,text=True,capture_output=True,timeout=120);(out/'benchmark.stdout').write_text(q.stdout);(out/'benchmark.stderr').write_text(q.stderr)
 if q.returncode:raise RuntimeError('SDK direct qualification failed')
 bench=json.loads(q.stdout);(out/'benchmarks.json').write_text(json.dumps(bench,indent=2)+'\n');inputs=objects+[Path(__file__),R/'timing/opu_sequencer_bench.cpp',sdk/'opu_sequencer.hpp',sdk/'opu_sequencer_schema.hpp',b/'build.json',a.proof.resolve()/'report.json',a.proof.resolve()/'inputs.txt',c,ar];report={'schema':'iris.opu_sequencer_sdk.v1','argv':commands,'benchmark_argv':command,'input_sha256':{str(p):sha(p)for p in inputs},'library_sha256':sha(sdk/'libiris_opu_sequencer.a'),'benchmark_sha256':sha(out/'benchmark'),'source_identity':json.loads((b/'build.json').read_text())['source_identity'],'public_flat_state_exposed':False,'benchmark_excludes':['parsing','output digest','text IO'],'benchmark_includes':['evaluate/sample/commit','definedness and output stores'],'idle_skipping':False,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'library_sha256':report['library_sha256'],'benchmark_sha256':report['benchmark_sha256'],'first_run':bench['runs'][0],'refusals':bench['lifecycle_refusals']}))
if __name__=='__main__':main()

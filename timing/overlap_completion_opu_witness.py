#!/usr/bin/env python3
"""Compare saved-RTL OPU entry hazards with frozen7bd5's entry-blind policy.

The component boundary is after frontend acceptance with explicit always-ready
VRF peers. This is not whole-CPU or FPGA timing and is not a fitted parameter.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'timing'))
from opu_sequencer_oracle import Oracle

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
 sdk=ROOT/'build/opu-sequencer-sdk-v1/sdk';ports=load(ROOT/'build/opu-sequencer-native-v3/ports.json')
 compiler=Path('/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++');exe=out/'witness'
 argv=[str(compiler),'-O2','-std=c++20','-I'+str(sdk),str(ROOT/'timing/overlap_completion_opu_witness.cpp'),str(sdk/'libiris_opu_sequencer.a'),'-pthread','-latomic','-o',str(exe)]
 c=subprocess.run(argv,text=True,capture_output=True);(out/'build.stdout').write_text(c.stdout);(out/'build.stderr').write_text(c.stderr)
 if c.returncode:raise RuntimeError('source witness build failed')
 results=[];corruption_controls=[]
 for kind in ('int8','fp8'):
  for size in (8,16,32):
   for count in (16,64):
    for pattern in ('same','rotate'):
     runs=[]
     for seed in (0,17):
      name=f'{kind}.m{size}.n{count}.{pattern}.seed{seed}';cmd=[str(exe),kind,str(size),str(count),pattern,str(seed)]
      q=subprocess.run(cmd,text=True,capture_output=True,timeout=10);(out/(name+'.stdout')).write_text(q.stdout);(out/(name+'.stderr')).write_text(q.stderr)
      if q.returncode:raise RuntimeError('valid source peer failed '+name)
      rows=[json.loads(l)for l in q.stdout.splitlines()];oracle=Oracle();checks=0
      for row in rows:
       values={f['name']:v for f,v in zip(ports['input'],row['input'])};expected=oracle.evaluate(values)
       if row['edge']>=2 and row['dis_ready']!=expected['io_dis_ready']:raise ValueError('independent dispatch-ready mismatch')
       if row['edge']>=3 and row['issued']!=bool(expected['io_iss_valid']):raise ValueError('independent issue-valid mismatch')
       if row['issued']:
        if row['entry']!=expected['io_iss_bits_mrf_idx_0']or row['vat']!=expected['io_vat']:raise ValueError('independent owner/entry mismatch')
        checks+=2
       oracle.commit(values)
      issued=[r for r in rows if r['issued']];accepted=[r for r in rows if r['accepted']]
      if len(accepted)!=count or len(issued)!=count*(4 if size==32 else 1):raise ValueError('source work count differs from geometry')
      runs.append({'seed':seed,'argv':cmd,'edges':len(rows),'dispatch_edges':[r['edge']for r in accepted],'microissue_edges':[r['edge']for r in issued],'entries':[r['entry']for r in issued],'independent_checks':checks})
     if runs[0]['dispatch_edges']!=runs[1]['dispatch_edges']or runs[0]['microissue_edges']!=runs[1]['microissue_edges']:raise ValueError('defined source behavior depends on reset seed')
     results.append({'kind':kind,'shape':[size,size,1],'commands':count,'pattern':pattern,'runs':runs})
 # Independent physical consequences: no timing constant is fed into the RTL.
 for count in(16,64):
  for size in(8,16):
   same=next(r for r in results if r['kind']=='fp8'and r['commands']==count and r['shape'][0]==size and r['pattern']=='same')['runs'][0]['microissue_edges']
   rotate=next(r for r in results if r['kind']=='fp8'and r['commands']==count and r['shape'][0]==size and r['pattern']=='rotate')['runs'][0]['microissue_edges']
   if set(b-a for a,b in zip(same,same[1:]))!={3}or set(b-a for a,b in zip(rotate,rotate[1:]))!={1}:raise ValueError('entry-history causal pattern absent')
   # A checker pretending tile-blind equal issue timing must fail these inputs.
   corruption_controls.append({'kind':'tile-blind-issue-sequence','size':size,'count':count,'rejected':same!=rotate})
 base=ROOT/'build/empirical-read-overlap-response-frozen-7bd58b4f/src/pipeline/riscv-isa-sim-read-overlap-response-v2/riscv'
 inputs=[Path(__file__),ROOT/'timing/overlap_completion_opu_witness.cpp',ROOT/'timing/opu_sequencer_oracle.py',sdk/'libiris_opu_sequencer.a',sdk/'opu_sequencer.hpp',ROOT/'build/opu-sequencer-native-v3/ports.json',ROOT/'build/opu-sequencer-component-v2-final/report.json',base/'iris_empirical_async.inc',base/'iris_empirical_features.inc',ROOT/'third_party/saturn/src/main/scala/backend/OuterProductSequencer.scala']
 report={'schema':'iris.overlap_completion_OPU_entry_witness.v1','pass':True,'source_cases':len(results),'source_runs':len(results)*2,'results':results,'corruption_controls':corruption_controls,'defect':'Frozen7bd5 async duration/admission has no tile/MRF-entry key; all heads must publish before the next command EX. It cannot express source FP8 same-entry3 versus distinct-entry1 microissue gaps.','source_boundary':'OuterProductSequencer+PipeScheduler after dispatcher, explicit always-ready VRF/write peer and no older VRF intents','CPU_or_FPGA_timing_validation':False,'source_instruction_frontend_included':False,'numeric_array_included':False,'hardware_contacted':False,'parameters_fitted':False,'global_heldout_timings_consumed':False,'native_changed':False,'build_argv':argv,'input_sha256':{str(p.resolve()):sha(p)for p in inputs},'host_seconds':time.monotonic()-started}
 report['artifact_sha256']={p.name:sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'cases':len(results),'source_runs':len(results)*2,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Report actual whole-command host elapsed and retired instructions, without extrapolation."""
import argparse,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);manifest=ROOT/'build/rocket-serial-frozen-15b10335/manifest.json';m=json.loads(manifest.read_text());rows=[];inputs={str(Path(__file__).resolve()):sha(__file__),str(manifest):sha(manifest)}
 for name in ['rocket-serial-native-final-v2','rocket-serial-writeback-v2']:
  receipt=ROOT/'build'/name/'results.json';r=json.loads(receipt.read_text());inputs[str(receipt)]=sha(receipt)
  if not r['status'].startswith('passed'):raise ValueError('successful exact executed guest receipt required')
  for row in r.get('rows',[r]):
   if row.get('expected_refusal'):continue
   if row['exit_status']!=0:raise ValueError('guest did not complete')
   binary=Path(row['argv'][0])
   if sha(binary)!=m['binary_sha256']:raise ValueError('native identity differs')
   graph=Path(next(x.split('=',1)[1]for x in row['argv']if x.startswith('--iris-timing-trace=')))
   if sha(graph)!=row['graph_sha256']:raise ValueError('raw graph changed')
   g=json.loads(graph.read_text());per_hart=g['retired_instructions'];retired=sum(per_hart);elapsed=row['host_seconds']
   if elapsed<=0 or not retired:raise ValueError('positive measured elapsed/retired counts required')
   inputs[str(graph)]=sha(graph);rows.append(dict(name=row.get('name','dirty-L2-writeback'),native_sha256=m['binary_sha256'],ELF_sha256=sha(row['argv'][-1]),host_seconds=elapsed,retired_instructions_per_hart=per_hart,retired_instructions_total=retired,simulated_MIPS=retired/elapsed/1e6,global_virtual_phases=g['cycles'],virtual_phases_per_host_second=g['cycles']/elapsed,host_elapsed_scope='whole native command including source construction/reset, ELF initialization, execution and graph output; excludes compiler build',active_compute_hart=2,physical_harts=3,other_harts='ROM boot then WFI; no truncation',sampling_or_fast_forward=False))
 inputs_dir=out/'inputs';inputs_dir.mkdir()
 for path,digest in inputs.items():
  dst=inputs_dir/digest
  if not dst.exists():shutil.copy2(path,dst)
 report=dict(schema='iris.rocket_serial.actual_executed_guest_speed.v1',status='measured_actual_executed_ELF_scope',rows=rows,input_sha256=inputs,timing_parameters='explicit LP30/30/16/16 and functional AXI/CBUS fixtures',production_tuning_speed_qualified=False,full_three_hart_source_memory_qualified=False,full_FASED_bridge=False,timing_calibrated=False,held_out_2pct=False);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(rows,indent=2))
if __name__=='__main__':main()

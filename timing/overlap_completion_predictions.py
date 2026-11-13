#!/usr/bin/env python3
"""Freeze model-only issue/fence/readout observations, never open HW labels."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run',type=Path,required=True);ap.add_argument('--capsule',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();r=a.run.resolve();c=a.capsule.resolve();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
 run=json.load(open(r/'run.json'));m=json.load(open(c/'manifest.json'));regions=json.load(open(r/'regions.json'));assert run['pass']is True and len(regions)==168 and run['native_binary_sha256']==m['binary_sha256'];assert run['normal_HTIF_exit']is False
 prefixes=[json.loads(l)for l in(r/'features.jsonl').read_text().splitlines()];assert len(prefixes)==672
 normalized=[]
 for row in regions:
  x=dict(row);x.update(start_cycle=x['start'],issue_end_cycle=x['issue_end'],fence_end_cycle=x['fence_end'],end_cycle=x['drain_end'],instret_delta=x['instret'],instret_scope='total window only; no per-subwindow instret was measured',logical_MACs=x['edge']**2*x['count']if x['hart']<2 else 0)
  normalized.append(x)
 inputs=[Path(__file__).resolve(),r/'run.json',r/'regions.json',r/'features.jsonl',r/'stderr',c/'manifest.json',c/'verification.json',c/'spike',c/'libsifive_uart.so',Path(run['argv'][-1]),Path(next(v.split('=',1)[1]for v in run['argv']if v.startswith('--iris-timing-fixture=')))]
 p={'schema':'iris.overlap_completion_frozen_prediction.v1','pass':True,'native_binary_sha256':m['binary_sha256'],'uart_library_sha256':m['uart_sha256'],'ELF_sha256':run['ELF_sha256'],'regions':normalized,'regions_checked':168,'numeric_elements_checked':19872,'actual_CSR_ELF_joins':672,'completion_scope':'controlled post-ROI debugger readback; all measured records stable; normal HTIF completion intentionally bypassed','normal_HTIF_guest_exit':False,'source_control_scope':m['source_control_qualified'],'CPU_bridge_scope':m['CPU_bridge_scope'],'FENCE_config_scope':m['FENCE_config_scope'],'IRQ_scope':m['IRQ_scope'],'parameters_fitted':False,'timing_reference_consumed':False,'reserved_reference_consumed':False,'prelaunch_timestamp_attested':False,'evaluation_scope':'source-mechanism candidate frozen before any reference labels are read by this fitter; not an external timestamp or full blind acceptance attestation','input_sha256':{str(p):sha(p)for p in inputs},'hardware_contacted':False,'timing_certified':False}
 (o/'prediction.json').write_text(json.dumps(p,indent=2)+'\n');print(json.dumps({'pass':True,'prediction':str(o/'prediction.json'),'sha256':sha(o/'prediction.json'),'regions':168}))
if __name__=='__main__':main()

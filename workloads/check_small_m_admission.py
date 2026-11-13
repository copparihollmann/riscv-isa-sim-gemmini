#!/usr/bin/env python3
"""Check the private explicit capability override without changing cost defaults."""
import hashlib,json,os
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=ROOT/'build/workload-small-M-admission-v1';out.mkdir(parents=True,exist_ok=False)
 target=ROOT/'workloads/iris-mlir-small-m';os.environ.update(MERLIN_TARGET_PATH=str(target),MERLIN_PROVIDER_BASE_PATH=str(ROOT/'third_party/rvv-mlir'),MERLIN_CHIPYARD_IRIS='/scratch/eygao/iris-cy')
 from merlin.runtime.backends.zephyr_model import MatrixRouting
 route=MatrixRouting(support_target='iris',unit='saturn_vme',config='IrisConfig');provider=route.provider();edge=route.tile_edge();checks=[]
 for forced,parallel,reduction,want in [(False,(2,32),(2880,),False),(False,(32,32),(2880,),True),(True,(1,32),(2880,),True),(True,(2,32),(2880,),True),(True,(3,32),(2880,),False),(True,(1,31),(2880,),False),(True,(1,64),(2880,),False),(True,(1,32),(0,),False),(True,(1,32),(5,),False),(True,(4,1,32),(2880,),False),(True,(32,64),(64,),True)]:
  if forced:os.environ['IRIS_EXPERIMENTAL_SMALL_M_VME']='1'
  else:os.environ.pop('IRIS_EXPERIMENTAL_SMALL_M_VME',None)
  result=provider.selector(edge)(SimpleNamespace(parallel=parallel,reduction=reduction))
  if bool(result)!=want:raise ValueError('Capability/cost selection mismatch')
  checks.append(dict(forced=forced,parallel=parallel,reduction=reduction,selected=bool(result)))
 try:provider.selector(16)
 except ValueError:checks.append(dict(changed_geometry_rejected=True))
 else:raise ValueError('Unknown geometry accepted')
 original=ROOT/'integration/iris-mlir';parent=json.load(open(target/'small-m-companion.json'))
 for name,digest in parent['parent_source_sha256'].items():
  if sha(original/name)!=digest:raise ValueError('Original bound target changed during companion work')
 r=dict(schema='iris.small_M_explicit_admission.v1',pass_=True,checks=checks,source_default_rule='min(shape.parallel[-2:]) >= tile_edge',default_rule_is_utilization_policy_not_hardware_capability=True,actual_experimental_domain='rank2 INT8; M1/2,N32,Kpositive multiple4; explicit opt-in only',default_cost_policy_changed=False,automatic_acceleration_profitability_claimed=False,original_bound_target_modified=False,input_sha256={str(p):sha(p)for p in[Path(__file__),target/'matrix_lowering.py',target/'small-m-companion.json',ROOT/'integration/merlin/src/merlin/llvmlower/int8_contractions.py',ROOT/'hardware/evidence/outer-product-sequencer.scala',target/'vme_kernel.py']},numerical_qualification='separate actual MLIR/native/golden receipts required',hardware_contacted=False)
 r['pass']=r.pop('pass_');(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(pass_=True,checks=len(checks),sha256=sha(out/'report.json'))))
if __name__=='__main__':main()

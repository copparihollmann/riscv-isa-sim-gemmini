#!/usr/bin/env python3
"""Synthetic estimator controls; never opens hardware/model results."""
import json
from pathlib import Path
from fit_pow2_scalar_cache_v1 import nnls
from scalar_l2_hit_run import ROOT,sha
def main():
    p,_=nnls([(1,0,3,10),(0,1,7,20),(2,1,13,30),(0,0,1000,2)])
    assert all(abs(x-y)<1e-9 for x,y in zip(p,(3,7)))
    q,_=nnls([(1,0,-3,10),(0,1,7,20)]);assert abs(q[0])<1e-12 and abs(q[1]-7)<1e-9
    refused=False
    try:nnls([(1,2,3,10),(2,4,6,20)])
    except ValueError:refused=True
    assert refused
    out=ROOT/'build/scalar-cache-NNLS-math-controls-v1';out.mkdir(exist_ok=False)
    paths=[Path(__file__).resolve(),Path(__file__).with_name('fit_pow2_scalar_cache_v1.py')]
    r={'pass':True,'synthetic_only':True,'no_hardware_or_model_inputs_opened':True,'positive_two_parameter_solution':p,'nonnegative_active_set':q,'rank_deficient_refused':True,'zero_basis_unexplained_residual_retained':True,'input_sha256':{str(p):sha(p)for p in paths}}
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(sha(out/'report.json'))
if __name__=='__main__':main()

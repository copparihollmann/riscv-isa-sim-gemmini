#!/usr/bin/env python3
"""Record reviewable companion patches without changing pristine source pins."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args])
def main():
    out=ROOT/'integration/patches';out.mkdir(exist_ok=True);repos={}
    pins={'merlin':'d56133b168bbee3d73cb8b4304d3622d4191fc6a','iris-mlir':'8447703ae5805271911e8ef232d8fd1aa7b6947d'}
    for name,pin in pins.items():
        baseline=ROOT/'third_party'/name;work=ROOT/'integration'/name
        if git(baseline,'rev-parse','HEAD').decode().strip()!=pin or git(baseline,'status','--porcelain'):
            raise RuntimeError('baseline changed: '+name)
        if git(work,'rev-parse','HEAD').decode().strip()!=pin or git(work,'ls-files','--others','--exclude-standard'):
            raise RuntimeError('worktree pin or source inventory unknown: '+name)
        patch=out/(name+'.patch');patch.write_bytes(git(work,'diff','--binary','HEAD'))
        subprocess.run(['git','-C',str(baseline),'apply','--check',str(patch)],check=True,capture_output=True)
        repos[name]={'baseline_commit':pin,'pristine_baseline':str(baseline),'derived_worktree':str(work),
                     'patch':str(patch.relative_to(ROOT)),'patch_sha256':sha(patch),'patch_applies':True,
                     'source_sha256':{line:sha(work/line) for line in git(work,'diff','--name-only','HEAD').decode().splitlines()}}
    evidence=[ROOT/'build/merlin-targeted-final-tests.log',ROOT/'build/merlin-integration-tests.log',ROOT/'build/merlin-baseline-board-tests.log',
              ROOT/'build/merlin-structure-check.log',ROOT/'build/llvm23-toolchain.json',ROOT/'build/merlin-evidence/closure.json',
              ROOT/'build/merlin-epilogue-crosscheck.json',ROOT/'zephyr/compiler-acceptance.json',ROOT/'build/merlin-workflow/current-memory-gemm-h2/results.json',
              ROOT/'workloads/model-inputs.json',ROOT/'workloads/operator-coverage.json']
    proof={'schema':'iris.companion_integration.v1','repositories':repos,'rvv_base_commit':'a80eea3eb749e5fd4cb822779a08d0d8ca09e5d5',
           'evidence_sha256':{str(p.relative_to(ROOT)):sha(p) for p in evidence},
           'tests':{'focused':'20 passed','broader':'106 passed,3 skipped,4 pre-existing board/source-assertion failures',
                    'baseline_reproduction':'same4 failures on pristine d561','structure':'passed'},
           'whole_model_qualified':False,'rtl_certified':False,'timing_calibrated':False,'published':False}
    (ROOT/'integration/manifest.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({k:v['patch_sha256'] for k,v in repos.items()}))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""No-kernel counterfactual must fail every poisoned accumulator word."""
import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 base=ROOT/'build/workload-small-M-v1/gpt-oss-20b-h1';out=ROOT/'build/workload-small-M-noop-v1';out.mkdir(parents=True,exist_ok=False);positive=json.load(open(base/'results.json'));argv=positive['runs'][0]['compile_argv'][:];argv[argv.index('-o')+1]=str(out/'skip.elf');argv+=['-DIRIS_WORKLOAD_SKIP_KERNEL','-Wno-unused-variable'];q=subprocess.run(argv,capture_output=True);(out/'build.log').write_bytes(q.stdout+q.stderr)
 if q.returncode:raise RuntimeError('Counterfactual build failed')
 os.environ.update(MERLIN_TARGET_PATH=str(ROOT/'workloads/iris-mlir-small-m'),MERLIN_IRIS_MODEL_MANIFEST=str(base/'selected-model.json'),MERLIN_IRIS_TIMING='empirical',MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING='1',MERLIN_CHIPYARD_IRIS='/scratch/eygao/iris-cy',MERLIN_PROVIDER_BASE_PATH=str(ROOT/'third_party/rvv-mlir'),IRIS_EXPERIMENTAL_SMALL_M_VME='1',IRIS_EMPIRICAL_FEATURES=str(out/'prefix.jsonl'))
 from merlin.runtime.backends.zephyr_model import MatrixRouting
 from merlin.runtime.backends import device_simulator
 route=MatrixRouting(support_target='iris',unit='saturn_vme',config='IrisConfig');start=time.monotonic();r=device_simulator.run(route,out/'skip.elf',harts=3,active_hart_ids=(0,),isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',memory=(0x80000000,0x100000000),timeout=180);stdout,stderr=r.pop('stdout'),r.pop('stderr');(out/'stdout').write_bytes(stdout);(out/'stderr').write_bytes(stderr);text=stdout.decode();row=next(x.split()for x in text.splitlines()if x.startswith('ACC_I32 '));actual=list(map(int,row[2:]));g=json.load(open(base/'golden.json'))['accumulator_u32'];want=[x^0xffffffff for x in g];failed=sum(a!=b for a,b in zip(actual,g));passed=r['returncode']!=0 and actual==want and failed==len(g)and('ERRORS '+str(len(g)))in text.splitlines();result=dict(schema='iris.model_operator_omitted_kernel_counterfactual.v1',pass_=passed,positive_receipt_sha256=sha(base/'results.json'),compile_argv=argv,actual_run=r,host_seconds=time.monotonic()-start,poisoned_accumulator_words=failed,expected_independent_poison_words=want,actual_accumulator_words=actual,kernel_omission_detected=passed,production_code_has_no_skip_branch=True,input_sha256={str(p):sha(p)for p in[Path(__file__),ROOT/'workloads/operator_execution_guest.c',base/'results.json',base/'golden.json',base/'selected-model.json',out/'skip.elf']},hardware_contacted=False);result['pass']=result.pop('pass_');(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(pass_=passed,failed_words=failed,report_sha256=sha(out/'report.json'))))
 if not passed:raise SystemExit(1)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Actual Merlin MLIR/provider gates for source-derived synthetic INT8 tiles."""
from __future__ import annotations
import argparse,ast,hashlib,importlib.util,json,os,shutil,struct,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OOT=ROOT/'workloads/iris-mlir-small-m'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def s8(x):return(x&255)-(256 if x&128 else 0)
def write_json(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def golden(m,n,k):
 acc=[sum(s8(i*17+q*11+3)*s8(q*13+j*7+5)for q in range(k))for i in range(m)for j in range(n)]
 words=[x&0xffffffff for x in acc];quant=[struct.unpack('<I',struct.pack('<f',max(-128,min(127,(x+512)//1024))))[0]for x in acc]
 h=14695981039346656037
 for b in bytes([(i*17+q*11+3)&255 for i in range(m)for q in range(k)]+[(q*13+j*7+5)&255 for q in range(k)for j in range(n)]):h=((h^b)*1099511628211)&((1<<64)-1)
 return dict(accumulator_u32=words,w8a8_f32_words=quant,producer_fnv1a64=h)
def mlir(m,n,k):return f'''module {{
 func.func @forward(%a: tensor<{m}x{k}xi8>, %b: tensor<{k}x{n}xi8>) -> tensor<{m}x{n}xi32> attributes {{llvm.emit_c_interface}} {{
  %z = arith.constant 0 : i32
  %e = tensor.empty() : tensor<{m}x{n}xi32>
  %f = linalg.fill ins(%z : i32) outs(%e : tensor<{m}x{n}xi32>) -> tensor<{m}x{n}xi32>
  %v = linalg.matmul ins(%a, %b : tensor<{m}x{k}xi8>, tensor<{k}x{n}xi8>) outs(%f : tensor<{m}x{n}xi32>) -> tensor<{m}x{n}xi32>
  return %v : tensor<{m}x{n}xi32>
 }}
}}
'''
def model_cases():
 manifest=json.loads((ROOT/'workloads/model-inputs.json').read_text());by={m['model_id']:m for m in manifest['models']};cases=[]
 for key,identity in [('gpt-oss-20b','openai/gpt-oss-20b'),('gemma4-e4b','google/gemma-4-E4B-it'),('tinyllama-base','TinyLlama/TinyLlama-1.1B-intermediate-step-1431k-3T')]:
  record=by[identity];source=ROOT/record['files']['config.json']['path'];expected=record['files']['config.json']['sha256']
  if sha(source)!=expected:raise RuntimeError('Pinned model configuration changed')
  config=json.loads(source.read_text());text=config.get('text_config',config);k=text['hidden_size'];n=text.get('num_local_experts',32)if key=='gpt-oss-20b'else 32
  role='router.linear-contraction-without-bias'if key=='gpt-oss-20b'else'attention.q.output-column-tile'
  cases.append(dict(case_id=key,model_id=identity,revision=record['revision'],source_config=str(source),source_config_sha256=expected,role=role,shape_mnk=[2,n,k],output_columns=[0,n],full_output_width=(text['num_local_experts']if key=='gpt-oss-20b'else text['num_attention_heads']*(text.get('head_dim')or(k//text['num_attention_heads']))),scope='full router contraction only; bias/top-k excluded'if key=='gpt-oss-20b'else'first32 output columns, full reduction K; no attention/whole-projection claim',validation_only=record['validation_only'],fit_eligible=False,weights_used=False,checkpoint_numeric_policy_qualified=False))
 # No gated-checkpoint dimensions are manufactured. The reference-code test is
 # labeled separately and never counts as exact Llama2-checkpoint admission.
 official=ROOT/'third_party/meta-llama/llama/model.py';tree=ast.parse(official.read_text());args=next(x for x in tree.body if isinstance(x,ast.ClassDef)and x.name=='ModelArgs');dim=next(x.value.value for x in args.body if isinstance(x,ast.AnnAssign)and isinstance(x.target,ast.Name)and x.target.id=='dim')
 cases.append(dict(case_id='meta-official-reference',model_id=None,requested_model_id='meta-llama/Llama-2-7b-hf',exact_checkpoint_admitted=False,unknown='Pinned checkpoint config remains gated HTTP401; this is ONLY the official code default contraction',source_config=str(official),source_config_sha256=sha(official),revision=manifest['implementations']['meta-llama']['commit'],role='official-reference-code projection tile',shape_mnk=[2,32,dim],output_columns=[0,32],full_output_width=None,scope='primary official ModelArgs.dim reference code, not Llama2-7B checkpoint coverage',validation_only=False,fit_eligible=False,weights_used=False,checkpoint_numeric_policy_qualified=False))
 return cases
def parse_output(text,g,workers,count):
 out={}
 for tag,key in [('ACC_I32','accumulator_u32'),('OUT','w8a8_f32_words')]:
  rows=[x.split()for x in text.splitlines()if x.startswith(tag+' ')]
  if len(rows)!=1 or len(rows[0])!=count+2 or int(rows[0][1])!=count:raise RuntimeError('Missing full output '+tag)
  values=list(map(int,rows[0][2:]));
  if values!=g[key]:raise RuntimeError('Independent full numerical mismatch '+tag)
 if text.splitlines().count('DONE')!=1 or 'ERRORS 0'not in text.splitlines():raise RuntimeError('No successful unique guest completion')
 producer=[x.split()for x in text.splitlines()if x.startswith('PRODUCER ')]
 if producer!=[['PRODUCER','2',str(g['producer_fnv1a64'])]]:raise RuntimeError('Hart2 producer identity/checksum')
 regions=[list(map(int,x.split()[1:]))for x in text.splitlines()if x.startswith('REGION ')]
 if len(regions)!=workers or {r[0]for r in regions}!=set(range(workers))or any(len(r)!=5 or r[2]<=r[1]or r[3]<=0 or r[4]>524288 for r in regions):raise RuntimeError('Actual counter/heap regions incomplete')
 return regions
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--case',choices=[c['case_id']for c in model_cases()],required=True);p.add_argument('--harts',type=int,choices=[1,2],required=True);p.add_argument('--timeout',type=int,default=180);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 case=next(c for c in model_cases()if c['case_id']==a.case);m,n,k=case['shape_mnk'];local=m//a.harts;case['shape_mnk']=[m,n,k]
 if m%a.harts or m*n>4096 or n>64:raise RuntimeError('Explicit output/worker bound')
 selected=ROOT/'spike/empirical-current/manifest.json';manifest=json.loads(selected.read_text())
 if not manifest['native_binary_sha256'].startswith('28a0a52b'):raise RuntimeError('This execution epoch explicitly selects frozen28 guard')
 frozen=out/'selected-model.json';shutil.copy2(selected,frozen);env=dict(os.environ,MERLIN_TARGET_PATH=str(OOT),MERLIN_IRIS_MODEL_MANIFEST=str(frozen),MERLIN_IRIS_TIMING='empirical',MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING='1',MERLIN_CHIPYARD_IRIS='/scratch/eygao/iris-cy',MERLIN_PROVIDER_BASE_PATH=str(ROOT/'third_party/rvv-mlir'),MERLIN_COMPILER_PYTHON=sys.executable,IRIS_EXPERIMENTAL_SMALL_M_VME='1')
 source=out/'input.mlir';source.write_text(mlir(local,n,k));compile_argv=[sys.executable,str(OOT/'compile_model.py'),'--input',str(source),'--op','gemm','--output',str(out/'compiled'),'--clang',str(ROOT/'build/llvm23/bin/clang-23'),'--llvm-source',str(ROOT/'third_party/llvm-project')]
 compiled=subprocess.run(compile_argv,env=env,capture_output=True,timeout=300);(out/'compiler.stdout').write_bytes(compiled.stdout);(out/'compiler.stderr').write_bytes(compiled.stderr)
 if compiled.returncode:raise RuntimeError('Real Merlin compiler failed; see compiler.stderr')
 artifact=json.loads((out/'compiled/artifacts.json').read_text());kernel=Path(artifact['kernel']['source']);shutil.copy2(kernel,out/'kernel.c');g=golden(m,n,k);write_json(out/'golden.json',g)
 (out/'operator_case.h').write_text(f'#define CASE_M {m}\n#define CASE_N {n}\n#define CASE_K {k}\n#define CASE_LOCAL_M {local}\n#define CASE_WORKERS {a.harts}\n#define CASE_ARENA_BYTES {((artifact['kernel']['scratch_bytes']+2*local*n*4+4095)//4096+1)*4096}\nstatic const uint32_t case_golden[CASE_M*CASE_N]={{'+','.join(map(str,g['accumulator_u32']))+'};\n')
 case.update(workers=a.harts,physical_harts=3,cpu_producer_hart=2,batch_size_policy=m,explicit_small_M_capability_route=True,source_shape_not_checkpoint_values=True,compiler_argv=compile_argv,actual_Merlin_MLIR_compiler=True,selected_manifest_sha256=sha(frozen),whole_model_execution_qualified=False);write_json(out/'case.json',case)
 compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');baseline=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-I'+str(ROOT/'benchmarks'),'-I'+str(out),'-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(ROOT/'workloads/operator_execution_guest.c'),artifact['artifacts']['model_object']['path'],artifact['artifacts']['bridge_object']['path'],'-lgcc']
 inputs=[Path(__file__),ROOT/'workloads/operator_execution_guest.c',ROOT/'workloads/model-inputs.json',ROOT/'workloads/operator-coverage.json',ROOT/'workloads/README.md',Path(case['source_config']),compiler,frozen,source,out/'operator_case.h',out/'kernel.c',out/'golden.json',out/'compiled/artifacts.json',ROOT/'benchmarks/start.S',ROOT/'benchmarks/runtime.c',ROOT/'benchmarks/runtime.h',ROOT/'benchmarks/uart_drain.h',ROOT/'benchmarks/link.ld'];identities={str(q):sha(q)for q in inputs};identities.update(artifact['source_sha256']);identities.update({v['path']:v['sha256']for v in artifact['artifacts'].values()});runs=[]
 os.environ.update(env)
 from merlin.runtime.backends.zephyr_model import MatrixRouting
 from merlin.runtime.backends import device_simulator
 route=MatrixRouting(support_target='iris',unit='saturn_vme',config='IrisConfig')
 for kind,flags in [('shipped',[]),('twin',['-DMERLIN_MATRIX_SCALAR_TILE','-DMERLIN_MATRIX_TILE_EDGE=32'])]:
  elf=out/(kind+'.elf');argv=[*baseline,*flags,'-o',str(elf)];q=subprocess.run(argv,capture_output=True);(out/(kind+'.build.log')).write_bytes(q.stdout+q.stderr)
  if q.returncode:raise RuntimeError('Actual RV64 ELF build failed '+kind)
  prefix=out/(kind+'.prefix.jsonl');os.environ['IRIS_EMPIRICAL_FEATURES']=str(prefix)
  t=time.monotonic();r=device_simulator.run(route,elf,harts=3,active_hart_ids=tuple(range(a.harts)),isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',memory=(0x80000000,0x100000000),timeout=a.timeout);stdout,stderr=r.pop('stdout'),r.pop('stderr');(out/(kind+'.stdout')).write_bytes(stdout);(out/(kind+'.stderr')).write_bytes(stderr)
  if r['returncode']:raise RuntimeError('Actual Merlin frontdoor run failed '+kind+': '+stderr.decode(errors='replace')[-800:])
  regions=parse_output(stdout.decode(),g,a.harts,m*n);r.update(kind=kind,compile_argv=argv,elf_sha256=sha(elf),regions=regions,host_seconds=time.monotonic()-t,all_int32_and_W8A8_words_match=True,stdout_sha256=sha(out/(kind+'.stdout')),stderr_sha256=sha(out/(kind+'.stderr')),prefix_sha256=sha(prefix),fit_eligible=False);runs.append(r);write_json(out/(kind+'.run.json'),r)
 if any(sha(Path(q))!=d for q,d in identities.items()):raise RuntimeError('Source/config/compiler/model inputs changed during run')
 result=dict(schema='iris.source_bound_model_operator_execution.v1',pass_=True,case=case,runs=runs,input_sha256=identities,full_accumulator_words_per_kind=m*n,full_W8A8_words_per_kind=m*n,hart2_producer_checked=True,actual_Merlin_MLIR_to_LLVM_executed=True,actual_Merlin_device_simulator_hook_executed=True,checkpoint_weights_executed=False,checkpoint_quantization_conversion_qualified=False,complete_operator_qualified=False,complete_attention_or_MoE_qualified=False,whole_model_execution_qualified=False,calibration_or_fit_inputs=False,validation_only=case['validation_only'],timing_accuracy_for_this_shape_qualified=False,hardware_contacted=False)
 result['pass']=result.pop('pass_');write_json(out/'results.json',result);print(json.dumps(dict(pass_=True,case=a.case,workers=a.harts,outputs=m*n,receipt=str(out/'results.json'))))
if __name__=='__main__':main()

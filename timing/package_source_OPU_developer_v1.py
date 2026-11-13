#!/usr/bin/env python3
"""Stage an explicitly uncalibrated native experiment without provider publication."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.empirical_provider_v4 import document
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__)
 for n in('capsule','on-fixture','off-fixture','readiness','compiler-gates','launcher','launcher-tests','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);capsule=a.capsule.resolve();meta=document(capsule/'manifest.json');ready=document(a.readiness);compiler=document(a.compiler_gates);lt=document(a.launcher_tests)
 if meta.get('pass')is not True or ready.get('pass')is not True or compiler.get('passed')is not True or lt.get('pass')is not True:raise ValueError('Typed successful parent gates required')
 native=capsule/'spike';uart=capsule/'libsifive_uart.so';native_sha=sha(native);uart_sha=sha(uart)
 if native_sha!=meta['binary_sha256']or uart_sha!=meta['uart_sha256']or ready['native_binary_sha256']!=native_sha or ready['manifest_sha256']!=sha(capsule/'manifest.json')or lt['native_binary_sha256']!=native_sha or lt['launcher_sha256']!=sha(a.launcher):raise ValueError('Exact native/launcher/readiness binding required')
 for name,h in meta['artifact_sha256'].items():
  if sha(capsule/name)!=h:raise ValueError('Frozen source/native artifact changed '+name)
 expected={(op,h,kind)for op in('gemm','conv2d')for h in(1,2)for kind in('shipped','twin')}
 if len(compiler['cases'])!=8 or {(x['op'],x['workers'],x['kind'])for x in compiler['cases']}!=expected or any(type(x['returncode'])is not int or x['returncode']!=0 or x['accumulator_words']!=4096 or x['w8a8_words']!=4096 for x in compiler['cases']):raise ValueError('Eight exact independent compiler-image gates required')
 original=lt['runs'][0]['argv'];boot=Path(next(x.split('=',1)[1]for x in original if x.startswith('--iris-bootrom=')));dtb=Path(next(x.split('=',1)[1]for x in original if x.startswith('--dtb=')));fixed=[x for x in original[1:-1]if not x.startswith(('--extlib=','--iris-bootrom=','--dtb=','--iris-timing-fixture=','--iris-timing-trace='))]
 roles={k:{'path':str(v.resolve()),'sha256':sha(v)}for k,v in{'native':native,'UART':uart,'launcher':a.launcher,'bootrom':boot,'dtb':dtb}.items()};fixtures={k:{'path':str(v.resolve()),'sha256':sha(v)}for k,v in{'off':a.off_fixture,'tk124':a.on_fixture}.items()}
 inputs={str(p.resolve()):sha(p)for p in[Path(__file__),ROOT/'timing/source_OPU_developer_v1.py',ROOT/'spike/empirical_provider_v4.py',ROOT/'spike/empirical_launch_v2.py',ROOT/'iris_model/graph_run_buffered.py',ROOT/'iris_model/empirical_run.py',capsule/'manifest.json',capsule/'verification.json',a.readiness,a.compiler_gates,a.launcher_tests]}
 inputs.update({str((capsule/n).resolve()):h for n,h in meta['artifact_sha256'].items()})
 for item in[*roles.values(),*fixtures.values()]:inputs[item['path']]=item['sha256']
 evidence={}
 for name,item in ready['evidence'].items():
  if sha(item['path'])!=item['sha256']:raise ValueError('Readiness evidence changed '+name)
  evidence[name]=item;inputs[item['path']]=item['sha256']
 for name,h in compiler['input_sha256'].items():
  if sha(name)!=h:raise ValueError('Compiler input changed '+name)
  inputs[name]=h
 for case in compiler['cases']:
  for name,h in case['output_sha256'].items():
   if sha(name)!=h:raise ValueError('Compiler output changed '+name)
   inputs[name]=h
 evidence['compiler_images']={'path':str(a.compiler_gates.resolve()),'sha256':sha(a.compiler_gates)}
 m={'schema':'iris.source_OPU_developer_package.v1','ready':True,'native_experiment_available':True,'calibrated_provider_available':False,'calibrated_provider_blocker':'C12 native/mode lacks its own actual timing calibration replay and empirical runtime binding; inherited family/memory costs are not newly qualified. Existing providers remain unchanged and must refuse.', 'default_selection_changed':False,'roles':roles,'fixtures':fixtures,'fixed_arguments':fixed,'capabilities':{'physical_harts':[0,1,2],'hart0_1':{'scalar':'RV64 + IEEEH/S/D; BF16 scalar conversions remain precise illegal','RVV':'functional per-hart ISA in fixed_arguments; timing is a limited hybrid','VME_finite_ON':'INT8 products toINT32 and FP8 products toFP32, positive TM/TN<=32, TK1/2/4, four tiles; readout/config/zero/move are conservative drain boundaries'},'hart2':{'VME':False,'RVV':'functional RVV including LMUL8 is ISA legal; e32 LMUL8 256B load liveness is not qualified on FPGA'}},'limitations':['Opt-in finite M-mode/stable-defined-VRF bare-metal OPU domain; active IRQ and unsupported CPU fetch boundaries refuse.','Only last-K per-entry architectural MRF projection; intermediate-K values unavailable. Non-MM readers and operand replacement drain all pending OPU writes.','COM+1 ingress/predictive CPU admission and conservative FENCE/config boundaries remain experimental; no whole-CPU timing proof.','Five Zephyr gates and launcher7 qualify OPU-OFF FADD+warm mode only; OPU-ON is not a Zephyr context timing model.','Eight preserved compiled GEMM/conv2d1/2-worker shipped+twin ON executions pass full int32/W8A8 checks. These are not fresh compiler invocations or timing accuracy gates.','Memory/family coefficients are inherited priors or effective fits from a different native/mode epoch; source/image association and physical bandwidth are unknown.','Actual hart2 e32/m8 VL64 repeated-load FPGA liveness failure remains open; clean-reset Saturn component tests with explicit synthetic responses do not reproduce it.'],'parameters_fitted_for_this_native':False,'evidence':evidence,'input_sha256':inputs,'hardware_contacted':False,'whole_CPU_timing_certified':False,'source_image_association':False,'timing_2pct_certified':False}
 (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');(out/'build.json').write_text(json.dumps({'schema':'iris.source_OPU_developer_stage.v1','pass':True,'argv':sys.argv,'manifest_sha256':sha(out/'manifest.json'),'native_binary_sha256':native_sha,'new_native_build':False,'existing_frozen_native_reused':True,'provider_available':False,'hardware_contacted':False},indent=2)+'\n');print(json.dumps({'manifest':str(out/'manifest.json'),'sha256':sha(out/'manifest.json'),'native_experiment_available':True,'calibrated_provider_available':False}))
if __name__=='__main__':main()

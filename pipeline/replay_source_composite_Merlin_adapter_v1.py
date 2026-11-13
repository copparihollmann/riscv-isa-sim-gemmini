#!/usr/bin/env python3
"""Actual Merlin device_simulator.run on eight preserved compiler images."""
import argparse,concurrent.futures,hashlib,importlib.util,json,multiprocessing,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'integration/merlin/src'),str(ROOT)]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def worker(job):
 out=Path(job['output']);out.mkdir(exist_ok=False);elf=Path(job['ELF']);manifest=Path(job['manifest']);start=time.monotonic()
 for key in list(os.environ):
  if key.startswith('IRIS_EMPIRICAL_')or key=='IRIS_FATAL_PCS':os.environ.pop(key)
 os.environ.update(MERLIN_TARGET_PATH=str(ROOT/'integration/iris-mlir'),MERLIN_IRIS_TIMING='empirical',MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING='1',MERLIN_IRIS_MODEL_MANIFEST=str(manifest),IRIS_EMPIRICAL_FEATURES=str(out/'features.jsonl'))
 from merlin.runtime.backends.zephyr_model import MatrixRouting
 from merlin.runtime.backends import device_simulator
 route=MatrixRouting(support_target='iris',unit='saturn_vme',config='IrisConfig');record=dict(name=job['name'],op=job['op'],workers=job['workers'],kind=job['kind'],ELF_sha256=sha(elf),shape_mnk=job['shape'],physical_harts=3,active_hart_ids=list(range(job['workers'])),actual_Merlin_device_simulator_run=True,**{'pass':False})
 try:
  assert sha(elf)==job['ELF_sha256'],'Preserved ELF changed'
  descriptor=device_simulator.resolve(route);assert descriptor['isa_extensions']==['zvt32t','zvti8i32mm','zvtofp8fmm']and descriptor['matrix_hart_ids']==[0,1]
  result=device_simulator.run(route,elf,harts=3,active_hart_ids=tuple(range(job['workers'])),isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',memory=(0x80000000,0x100000000),timeout=job['timeout'])
  (out/'stdout').write_bytes(result['stdout']);(out/'stderr').write_bytes(result['stderr']);record.update(argv=result['argv'],returncode=result['returncode'],execution_input_sha256=result['execution_input_sha256'],simulator_provenance=result['simulator']['provenance'])
  assert result['returncode']==0,'Native guest exit failed'
  spec=importlib.util.spec_from_file_location('independent_iris_golden',ROOT/'integration/iris-mlir/examples/iris/run.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g);m,n,k=job['shape'];want_i,want_w=g.inputs_and_golden(job['op'],m,n,k);parsed=g.parse(result['stdout'].decode(),m*n)
  assert parsed['ACC_I32']==want_i and parsed['OUT']==want_w,'Every INT32/W8A8 word must match independent semantics'
  rows=[list(map(int,line.split()[1:]))for line in result['stdout'].decode().splitlines()if line.startswith('REGION ')]
  assert sorted(x[0]for x in rows)==list(range(job['workers']))and all(len(x)==4 and x[2]>x[1]and x[3]>0 for x in rows),'All active hart CSR intervals'
  expected={str(h):'--hart-isa='+str(h)+':'+descriptor['per_hart_isa'][str(h)]for h in range(3)}
  assert all(x in result['argv']for x in expected.values())and all(e not in descriptor['per_hart_isa']['2'].split('_')for e in descriptor['isa_extensions'])
  record.update(**{'pass':True},normal_guest_exit=True,accumulator_words=len(want_i),W8A8_words=len(want_w),regions=rows,all_per_hart_ISAs_preserved=True)
 except Exception as e:
  record['error']=str(e)
  for name,value in [('stdout',getattr(e,'stdout',None)),('stderr',getattr(e,'stderr',None))]:
   if value is not None:(out/name).write_bytes(value)
 record['host_seconds']=time.monotonic()-start;record['output_sha256']={str(p):sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(record,indent=2)+'\n');return record

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=420);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False);jobs=[];inputs={str(Path(__file__).resolve()):sha(__file__),str(a.manifest.resolve()):sha(a.manifest),str(Path(sys.executable)):sha(sys.executable)}
 for op in('gemm','conv2d'):
  for workers in(1,2):
   source=ROOT/f'build/hybrid7bd5-selected-merlin-{op}-h{workers}-v1/results.json';old=json.loads(source.read_text());assert old['pass'];inputs[str(source)]=sha(source)
   for row in old['runs']:
    elf=Path(row['argv'][-1]);assert sha(elf)==row['elf_sha256'];inputs[str(elf)]=sha(elf);name=f'{op}-h{workers}-'+row['kind'];jobs.append(dict(name=name,op=op,workers=workers,kind=row['kind'],ELF=str(elf),ELF_sha256=sha(elf),shape=old['shape_mnk'],manifest=str(a.manifest.resolve()),output=str(out/name),timeout=a.timeout))
 for p in[ROOT/'integration/iris-mlir/simulator.py',ROOT/'integration/iris-mlir/matrix_lowering.py',ROOT/'integration/iris-mlir/examples/iris/run.py',ROOT/'integration/merlin/src/merlin/runtime/backends/device_simulator.py',ROOT/'integration/merlin/src/merlin/runtime/backends/zephyr_model.py']:inputs[str(p)]=sha(p)
 report=dict(schema='iris.source_composite_Merlin_device_simulator_eight_gates.v1',status='running',**{'pass':False},actual_OOT_MatrixRouting_and_device_simulator=True,hardware_contacted=False,fresh_compiler_invocation=False,no_parameter_fitting=True,protected_timing_labels_opened=False,cases=[],input_sha256=inputs)
 path=out/'report.json';save=lambda:path.write_text(json.dumps(report,indent=2)+'\n');save();start=time.monotonic()
 with concurrent.futures.ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn'))as pool:
  futures=[pool.submit(worker,j)for j in jobs]
  for f in concurrent.futures.as_completed(futures):report['cases'].append(f.result());save()
 report['cases'].sort(key=lambda r:r['name']);report['unchanged_inputs']=all(sha(p)==h for p,h in inputs.items());report['pass']=len(report['cases'])==8 and all(r['pass']for r in report['cases'])and report['unchanged_inputs'];report['status']='passed_all_eight_real_Merlin_runs'if report['pass']else'failed';report['host_seconds']=time.monotonic()-start;save();print(json.dumps(dict(pass_=report['pass'],cases=len(report['cases']),host_seconds=report['host_seconds'],report_sha256=sha(path))));return 0 if report['pass']else 1
if __name__=='__main__':raise SystemExit(main())

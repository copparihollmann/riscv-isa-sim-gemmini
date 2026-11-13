#!/usr/bin/env python3
"""Disjoint two-phase mailbox/watchdog diagnostic; never read reference labels."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--force-stall-negative',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);parent=R/'build/fast-heldout-zephyr-compact-v6';m=json.loads((parent/'manifest.json').read_text());app=out/'app';(app/'src').mkdir(parents=True);gen=out/'generated';gen.mkdir();inputs={str(parent/'manifest.json'):sha(parent/'manifest.json'),str(Path(__file__)):sha(__file__)}
 def frozen(name):
  source=R/name;v=m['inputs'][str(source)];data=(parent/v['object']).read_bytes();assert hashlib.sha256(data).hexdigest()==v['sha256'];inputs[str(source)]=v['sha256'];return data
 for name in ['CMakeLists.txt','Kconfig','prj.conf']:(app/name).write_bytes(frozen('zephyr/heldout-batch/'+name))
 text=frozen('zephyr/heldout-batch/src/main.c').decode();body=R/'zephyr/heldout-phase-diagnostic-v1/diagnostic.inc';inputs[str(body)]=sha(body)
 def replace(old,new):
  nonlocal text
  assert text.count(old)==1,old;text=text.replace(old,new,1)
 replace('static void compute(void *arg,void *b,void *c){',body.read_text()+'\nstatic void compute(void *arg,void *b,void *c){')
 replace('  if(hart()!=id||(!twin()&&merlin_target_compute_task_setup()))fail(0,1);','  diag_mark(1,100,0);if(hart()!=id||(!twin()&&merlin_target_compute_task_setup()))fail(0,1);diag_mark(1,101,0);')
 replace('    k_sem_take(&work[id],K_FOREVER);unsigned buffer=job&1;','    diag_mark(1,110,job);k_sem_take(&work[id],K_FOREVER);diag_mark(1,111,job);unsigned buffer=job&1;')
 replace('      batch_models[op()*2+twin()](&a,&bdesc,&out);','      diag_mark(1,120+row/32*2,job);batch_models[op()*2+twin()](&a,&bdesc,&out);diag_mark(1,121+row/32*2,job);')
 replace('    atomic_and(&active,~(1u<<id));k_sem_give(&completed);','    atomic_and(&active,~(1u<<id));diag_mark(1,130,job);k_sem_give(&completed);diag_mark(1,131,job);')
 replace('  k_sem_give(&finished);\n}','  diag_mark(1,140,JOBS);k_sem_give(&finished);diag_mark(1,141,JOBS);\n}')
 replace('  if(hart()!=2||merlin_target_cpu_producer_setup())fail(0,4);','  diag_mark(2,200,0);if(hart()!=2||merlin_target_cpu_producer_setup())fail(0,4);diag_mark(2,201,0);')
 replace('  uint64_t initial=retired();e2e_begin=cycles();prepare(0);','  uint64_t initial=retired();e2e_begin=cycles();diag_mark(2,210,0);prepare(0);diag_mark(2,211,0);')
 replace('    for(unsigned id=0;id<worker_count;++id)k_sem_give(&work[id]);','    diag_mark(2,220,job);for(unsigned id=0;id<worker_count;++id)k_sem_give(&work[id]);diag_mark(2,221,job);')
 replace('    for(unsigned id=0;id<worker_count;++id)k_sem_take(&started,K_FOREVER);','    diag_mark(2,222,job);for(unsigned id=0;id<worker_count;++id)k_sem_take(&started,K_FOREVER);diag_mark(2,223,job);')
 replace('    __asm__ volatile("vsetivli','    diag_mark(2,230,job);__asm__ volatile("vsetivli')
 replace('    for(unsigned n=0;n<8;++n){if(out[n]!=in[n]+7)','    diag_mark(2,231,job);for(unsigned n=0;n<8;++n){if(out[n]!=in[n]+7)')
 replace('    for(unsigned id=0;id<worker_count;++id)k_sem_take(&completed,K_FOREVER);','    diag_mark(2,240,job);for(unsigned id=0;id<worker_count;++id)k_sem_take(&completed,K_FOREVER);diag_mark(2,241,job);')
 replace('mtime));k_sem_give(&finished);','mtime));diag_mark(2,250,JOBS);k_sem_give(&finished);diag_mark(2,251,JOBS);')
 replace('  for(phase=0;phase<8;++phase){','  k_tid_t watcher=k_thread_create(&diag_thread,diag_stack,K_THREAD_STACK_SIZEOF(diag_stack),diag_watchdog,NULL,NULL,NULL,-1,0,K_FOREVER);if(k_thread_cpu_pin(watcher,1))fail(0,90);k_thread_start(watcher);\n  for(phase=0;phase<2;++phase){\n    diag_mark(0,1,0);\n#ifdef IRIS_DIAG_FORCE_STALL\n    if(phase==1)for(;;)k_sleep(K_MSEC(50));\n#endif')
 replace('    for(unsigned id=0;id<worker_count;++id){k_sem_init','    diag_mark(0,2,0);for(unsigned id=0;id<worker_count;++id){diag_mark(0,3,id);k_sem_init')
 replace('k_thread_start(t);}\n    k_tid_t t=','k_thread_start(t);diag_mark(0,4,id);}\n    diag_mark(0,5,0);k_tid_t t=')
 replace('if(k_thread_cpu_pin(t,2))fail(0,9);k_thread_start(t);','if(k_thread_cpu_pin(t,2))fail(0,9);k_thread_start(t);diag_mark(0,6,0);')
 replace('    for(unsigned i=0;i<worker_count+1;++i)k_sem_take(&finished,K_FOREVER);','    for(unsigned i=0;i<worker_count+1;++i){diag_mark(0,7,i);k_sem_take(&finished,K_FOREVER);diag_mark(0,8,i);}')
 replace('    for(unsigned id=0;id<worker_count;++id)if(k_thread_join(&workers[id],K_FOREVER))fail(0,10);','    for(unsigned id=0;id<worker_count;++id){diag_mark(0,9,id);if(k_thread_join(&workers[id],K_FOREVER))fail(0,10);diag_mark(0,10,id);}')
 replace('    if(k_thread_join(&producer,K_FOREVER))fail(0,11);','    diag_mark(0,11,0);if(k_thread_join(&producer,K_FOREVER))fail(0,11);diag_mark(0,12,0);')
 replace('    print_phase();','    diag_mark(0,13,0);print_phase();diag_mark(0,14,0);')
 replace('  printk("IRIS_BATCH_DONE','  atomic_set(&diag_complete,1);k_sem_take(&diag_joined,K_FOREVER);if(k_thread_join(&diag_thread,K_FOREVER))fail(0,91);printk("IRIS_DIAG_DONE {\\"phases\\":2,\\"failed\\":0}\\n");\n  printk("IRIS_BATCH_DONE')
 text=text.replace('\\"cases\\":128,\\"regions\\":188','\\"cases\\":32,\\"regions\\":32');text=text.replace('heldout.batch.','diagnostic.handoff.batch.').replace('merlin.zephyr.','diagnostic.parent.merlin.zephyr.');(app/'src/main.c').write_text(text)
 for name,item in m['inputs'].items():
  path=Path(name)
  if path.parent==parent/'generated':
   data=(parent/item['object']).read_bytes();assert hashlib.sha256(data).hexdigest()==item['sha256'];(gen/path.name).write_bytes(data);inputs[name]=item['sha256']
 # Use the parent's exact compiled object and generated source bytes.
 cases=json.loads((parent/'cases.json').read_text());cases=cases[:32]
 for c in cases:
  for key in ['id','case_id']:c[key]=c[key].replace('heldout.batch.','diagnostic.handoff.batch.')
  c['parent_case_id']='diagnostic.parent.'+c['parent_case_id'];c['fitting_allowed']=False;c['corpus_split']='iris-phase-handoff-diagnostic-v1'
 (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');shutil.copyfile(parent/'golden.json',out/'golden.json');extra=out/'negative.conf';extra.write_text('CONFIG_COMPILER_OPT="-DIRIS_DIAG_FORCE_STALL -DIRIS_DIAG_TIMEOUT_MS=10"\n'if a.force_stall_negative else '')
 env=dict(os.environ);cmd=[sys.executable,str(R/'zephyr/context_build.py'),'--source',str(R/'third_party/zephyr-iris'),'--patch',str(R/'zephyr/patches/0002-iris-vme-context.patch'),'--uart-profile','ethan-firesim','--app',str(app),'--output',str(out/'build'),'--cmake=-DIRIS_KERNEL_DIR='+str(gen),'--cmake=-DIRIS_TARGET_DIR='+str(R/'integration/iris-mlir')]
 if a.force_stall_negative:cmd+=['--extra-conf',str(extra)]
 for name in [Path(__file__),body,*[p for p in gen.iterdir()if p.is_file()]]:cmd+=['--input',str(name)]
 with(out/'build.log').open('w')as f:r=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT)
 if r.returncode:raise RuntimeError('See diagnostic build.log')
 built=json.loads((out/'build/build.json').read_text());original=out/'build/zephyr/zephyr.elf';data=bytearray(original.read_bytes());tools=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin');syms=subprocess.check_output([str(tools/'riscv64-unknown-elf-nm'),'-S','--defined-only',str(original)],text=True);row=next(x.split()for x in syms.splitlines()if x.endswith(' iris_heldout_full_output'));address=int(row[0],16)
 import struct
 phoff=struct.unpack_from('<Q',data,32)[0];size,count=struct.unpack_from('<HH',data,54);hits=[]
 for i in range(count):
  f=struct.unpack_from('<IIQQQQQQ',data,phoff+i*size)
  if f[0]==1 and f[3]<=address<f[3]+f[5]:hits.append(f[2]+address-f[3])
 assert len(hits)==1 and data[hits[0]]==1;data[hits[0]]=0;elf=out/'diagnostic.elf';elf.write_bytes(data);inputs[str(R/'zephyr/context_build.py')]=sha(R/'zephyr/context_build.py');inputs[str(out/'build/build.json')]=sha(out/'build/build.json');inputs[str(parent/'cases.json')]=sha(parent/'cases.json');inputs[str(parent/'golden.json')]=sha(parent/'golden.json')
 manifest=dict(schema='iris.phase_handoff_diagnostic_build.v1',status='built',ELF=str(elf),ELF_sha256=sha(elf),parent_ELF_sha256=m['ELF_sha256'],parent_manifest_sha256=sha(parent/'manifest.json'),phases=m['phases'][:2],cases=32,regions=32,trials=5,compact_output=True,source_frozen=True,force_stall_negative=a.force_stall_negative,watchdog_no_progress_ms=10 if a.force_stall_negative else 5000,watchdog_hart=1,physical_harts=[0,1,2],shipped_and_twin_objects_unchanged=True,phase_main_recreation_quantization_unchanged=True,perturbation='Integerstage stores, CPU1watchdog/timers/printing, two-phasebound and newlayout; no originaltiming equivalence',input_sha256=inputs,global_v6_reference_timing_labels_consumed=False,fitting_allowed=False,hardware_contacted=False,commands=[cmd]);(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(status='built',ELF_sha256=sha(elf))))
if __name__=='__main__':main()

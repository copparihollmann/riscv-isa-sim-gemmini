#!/usr/bin/env python3
"""Build/run actual FP/RVV/VME context corpus and two deliberate failure ELFs."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/zephyr-context-suite');p.add_argument('--binary',type=Path,default=ROOT/'build/zephyr-binary-snapshot/spike');p.add_argument('--uart',type=Path);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);(out/'results.json').unlink(missing_ok=True)
    binary=a.binary.resolve();uart=a.uart.resolve() if a.uart else binary.parent/'libsifive_uart.so';identity=[sha(binary),sha(uart)]
    own=Path(__file__).read_bytes();(out/'runner-source.py').write_bytes(own);commands=[];reports=[]
    def execute(script,*args,expected=0):
        argv=[sys.executable,str(ROOT/'zephyr'/script),*[str(x) for x in args]];log=out/('command'+str(len(commands))+'.log')
        with log.open('w') as stream:r=subprocess.run(argv,stdout=stream,stderr=subprocess.STDOUT)
        commands.append({'argv':argv,'exit_status':r.returncode,'log':str(log.relative_to(out)),'log_sha256':sha(log)})
        if r.returncode!=expected:raise RuntimeError('Unexpected command result; see '+str(log))
    patch=ROOT/'zephyr/patches/0002-iris-vme-context.patch';derived=ROOT/'third_party/zephyr-iris'
    execute('prepare_context_tree.py')
    def guest(name,app,source,source_patch=None,extra=None,negative=None):
        build=out/(name+'-build');run=out/(name+'-run')
        args=['--source',source,'--app',ROOT/'zephyr'/app,'--output',build]
        if source_patch:args+=['--patch',source_patch]
        if extra:args+=['--extra-conf',extra]
        execute('context_build.py',*args)
        execute('context_run.py' if app=='context-stress' else 'vme_context_run.py','--elf',build/'zephyr/zephyr.elf','--output',run,'--binary',binary,'--uart',uart,expected=1 if negative else 0)
        receipt=run/'results.json';data=json.loads(receipt.read_text())
        if negative:
            stdout=(run/'stdout').read_text();stderr=(run/'stderr').read_text()
            correct='read of uninitialized tile cell' in stderr if negative=='omitted-ownership' else 'IRIS_VME_CONTEXT_FATAL' in stdout and any('"field":'+str(x) in stdout for x in range(200,204))
            if data['exit_status']==0 or data['timed_out'] or not correct:raise RuntimeError('Expected hardware-state failure was not observed')
            result={'status':'passed_expected_failure','case':negative,'actual_exit_status':data['exit_status'],'run_receipt_sha256':sha(receipt),'rtl_certified':False}
            receipt=run/'negative-results.json';receipt.write_text(json.dumps(result,indent=2)+'\n')
        elif data['status']!='passed':raise RuntimeError('Context corpus did not pass')
        reports.append({'case':name,'path':str(receipt.relative_to(ROOT)),'sha256':sha(receipt)})
    guest('ordinary-base','context-stress',ROOT/'third_party/zephyr')
    guest('ordinary-derived','context-stress',derived,patch,ROOT/'zephyr/configs/vme-context.conf')
    guest('competing-vme','vme-context-stress',derived,patch)
    guest('omitted-ownership','vme-ownership-negative',derived,patch,negative='omitted-ownership')
    # Isolated fault injection leaves the production derived kernel untouched.
    negative_tree=out/'negative-tree';negative_patch=out/'no-tile-restore.patch'
    if not negative_patch.exists():
        execute('prepare_context_tree.py','--output',negative_tree)
        source=negative_tree/'arch/riscv/core/fpu.c';content=source.read_text();call='\t\tz_iris_vme_tiles_restore(restore_from->iris_tiles);'
        if content.count(call)!=1:raise RuntimeError('Tile restore hook changed; review negative test')
        source.write_text(content.replace(call,'\t\t/* Deliberate negative corpus: omit tile restore. */'))
        negative_patch.write_bytes(subprocess.check_output(['git','-C',str(negative_tree),'diff','--binary','HEAD']))
    guest('omitted-tile-restore','vme-context-stress',negative_tree,negative_patch,negative='omitted-kernel-tile-restore')
    if identity!=[sha(binary),sha(uart)] or Path(__file__).read_bytes()!=own:raise RuntimeError('Test inputs changed during context suite')
    result={'schema_version':1,'status':'passed_context_corpus','base_zephyr_sha':'cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0','patch_sha256':sha(patch),'binary_sha256':identity[0],'uart_sha256':identity[1],'runner_sha256':hashlib.sha256(own).hexdigest(),'reports':reports,'commands':commands,'positive_cpu_elf_tests':3,'negative_cpu_elf_tests':2,'rtl_certified':False,'timing_certified':False}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'positive_cpu_elf_tests':3,'negative_cpu_elf_tests':2,'receipt':str(out/'results.json')}))
if __name__=='__main__':main()

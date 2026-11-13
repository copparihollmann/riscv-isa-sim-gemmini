#!/usr/bin/env python3
"""Verify source UART deployment contracts and actual compiled Zephyr readbacks."""
import argparse,hashlib,json
from pathlib import Path
from uart_profiles import profile,inputs,check_report

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/zephyr-firesim-uart/5e6'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_build(path):
    data=json.loads(path.read_text());folder=path.parent
    if data['status']!='built':raise RuntimeError('Unsuccessful Zephyr build')
    for name,digest in data['input_sha256'].items():
        if sha(folder/'input-snapshot'/name)!=digest:raise RuntimeError('Changed compiled Zephyr input')
    elf=folder/'zephyr/zephyr.elf';expected=data.get('elf_sha256') or data['artifact_sha256']['zephyr/zephyr.elf']
    if sha(elf)!=expected:raise RuntimeError('Changed compiled Zephyr ELF')
    return data

def make_record():
    paths=set(inputs('physical')+inputs('ethan-firesim')+[Path(__file__),ROOT/'zephyr/source-audit.json'])
    profiles={name:profile(name) for name in ['physical','ethan-firesim']}
    for name in ['iris_uart_profile.h','uart-profiles.json','boards/chipyard/iris/ethan-firesim.overlay']:
        p=ROOT/'integration/iris-mlir/zephyr'/name
        if sha(p)!=sha(ROOT/'zephyr'/name):raise RuntimeError('OOT UART deployment copy differs')
        paths.add(p)
    rows={};identities=set()
    for name,chosen,count in [('physical','physical',6),('mixed','ethan-firesim',9)]:
        path=BASE/(name+'-run/results.json');data=json.loads(path.read_text());build=BASE/(name+'-build/build.json');proof=verify_build(build)
        if not data['status'].startswith('passed') or len(data['regions'])!=count or data['errors'] or data['exit_status'] or data['harts']!=[0,1,2]:raise RuntimeError('Wrong three-hart UART profile result')
        raw=path.parent/'stdout';report=check_report(raw.read_text().splitlines(),chosen)
        if data['uart_readback']!=report or proof['uart_profile']['name']!=chosen or sha(raw)!=data['stdout_sha256'] or sha(build)!=data['build_receipt_sha256']:raise RuntimeError('Changed UART/ELF result')
        rows[name]={'path':str(path.relative_to(ROOT)),'sha256':sha(path),'profile':chosen,'harts':[0,1,2],'regions':count,'readback':report,'elf_sha256':data['elf_sha256']}
        identities.add((data['binary_sha256'],data['uart_sha256']));paths.update([path,raw,path.parent/'stderr',build,build.parent/'zephyr/zephyr.elf'])
    directory=BASE/'workflow-gemm-h2';workflow=json.loads((directory/'results.json').read_text());execution=directory/'execution';path=execution/'results.json';data=json.loads(path.read_text())
    if not workflow['pass'] or not data['pass'] or not data['real_merlin_mlir_executed'] or data['workers']!=2 or data['physical_harts']!=3 or data['cpu_producer_hart']!=2 or workflow['uart_profile']['name']!='ethan-firesim' or sha(path)!=workflow['execution_receipt_sha256']:raise RuntimeError('Wrong real compiler workflow')
    source_index=BASE/'emission-source-index.json';archives=json.loads(source_index.read_text())['artifacts'];paths.add(source_index)
    for name,digest in data['source_sha256'].items():
        item=archives.get(name)
        if not item or item['sha256']!=digest or sha(ROOT/item['path'])!=digest:raise RuntimeError('Missing frozen compiler emission source: '+name)
        paths.add(ROOT/item['path'])
    runner=archives[str(ROOT/'integration/iris-mlir/examples/iris/run.py')]
    if runner['sha256']!=workflow['runner_sha256']:raise RuntimeError('Wrong compiler front-door source')
    paths.add(ROOT/runner['path'])
    from compiler_pipeline import golden,producer_golden
    expected=[golden('gemm',j,64,64,64) for j in range(3)]
    for run in data['runs']:
        folder=execution/(run['kind']+'-run');proof=verify_build(execution/(run['kind']+'-build/build.json'))
        if not run['pass'] or run['exit_status'] or run['full_output_elements']!=12288 or sha(folder/'stdout')!=run['stdout_sha256'] or sha(folder/'stderr')!=run['stderr_sha256']:raise RuntimeError('Changed compiled GEMM output')
        lines=(folder/'stdout').read_text().splitlines();report=check_report(lines,'ethan-firesim')
        values=[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_COMPILER_RESULT ')]
        if values!=expected or run['uart_readback']!=report or run['producer']['vector_checksum']!=producer_golden() or not any(run['producer']['overlap_masks'][:2]):raise RuntimeError('Numerical/producer/UART mismatch')
    identities.add((data['binary_sha256'],data['uart_sha256']))
    if len(identities)!=1:raise RuntimeError('UART deployment gates use different native identities')
    provenance=ROOT/'build/snapshot-5e6cc309/provenance.json';model=json.loads(provenance.read_text());binary,uart=next(iter(identities))
    if model['binary_sha256']!=binary or sha(BASE/'bin/spike-iris-functional')!=binary or sha(BASE/'bin/libsifive_uart.so')!=uart:raise RuntimeError('Frozen model/provenance identity differs')
    paths.update([provenance,BASE/'bin/spike-iris-functional',BASE/'bin/libsifive_uart.so'])
    paths.update(x for x in directory.rglob('*') if x.is_file() and ('input-snapshot' in x.parts or x.suffix in ['.json','.mlir','.ll','.o','.c','.h','.elf'] or x.name in ['stdout','stderr','disassembly','build.log']))
    paths.update(x for d in [BASE/'physical-build/input-snapshot',BASE/'mixed-build/input-snapshot'] for x in d.rglob('*') if x.is_file())
    # Deliberately reject using a valid physical-profile receipt as Ethan proof.
    try:check_report((BASE/'physical-run/stdout').read_text().splitlines(),'ethan-firesim')
    except RuntimeError:negative=True
    else:raise RuntimeError('Physical baud wrongly admitted as Ethan bridge compatible')
    return {'schema':'iris.zephyr_uart_profile_acceptance.v1','pass':True,'profiles':profiles,'source_uart_clock_hz':500000000,'source_init_baud':3686400,'ethan_bridge_key':135,'driver_requested_baud_for_div135':3676470,'source_formula_verified':True,'rows':rows,'real_compiler_workflow':{'path':str((directory/'results.json').relative_to(ROOT)),'sha256':sha(directory/'results.json'),'real_merlin_mlir':True,'workers':2,'producer_hart':2,'physical_harts':3,'programs':2,'int32_values_per_program':12288,'w8a8_values_per_program':12288},'physical_profile_as_ethan_rejected':negative,'binary_sha256':binary,'uart_sha256':uart,'frozen_native_provenance_sha256':sha(provenance),'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)},'rtl_certified':False,'timing_calibrated':False,'fpga_zephyr_validated':False,'loaded_image_association_verified':False}

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--verify',action='store_true');a=p.parse_args();path=ROOT/'zephyr/uart-profile-acceptance.json';j=make_record()
    if a.verify:
        if json.loads(path.read_text())!=j:raise RuntimeError('UART profile acceptance is stale')
    else:path.write_text(json.dumps(j,indent=2)+'\n')
    print(json.dumps({'pass':True,'profiles':list(j['profiles']),'binary_sha256':j['binary_sha256'],'fpga_zephyr_validated':False}))

if __name__=='__main__':main()

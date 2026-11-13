#!/usr/bin/env python3
"""Freeze one independent three-hart Zephyr/real-Merlin heldout ELF before timing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import struct

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'zephyr'))
from compiler_pipeline import golden,producer_golden
from freeze_heldouts import output_hash
from uart_profiles import inputs as uart_inputs

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gemm',type=Path,required=True)
    parser.add_argument('--conv2d',type=Path,required=True)
    parser.add_argument('--skip-kernel',action='store_true',help='Numerical negative only; never a deployable holdout')
    parser.add_argument('--compact',action='store_true',help='Patch only retained output-mode byte; preserve original full-output ELF')
    a=parser.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    generated=out/'generated';generated.mkdir();snap=out/'objects';snap.mkdir()
    recorded={}
    def retain(p,expected=None):
        p=Path(p).resolve();h=sha(p)
        if expected and h!=expected:raise ValueError('Changed source '+str(p))
        dest=snap/h
        if not dest.exists():shutil.copyfile(p,dest)
        recorded[str(p)]={'sha256':h,'object':str(dest.relative_to(out))}
        return h
    frozen=ROOT/'build/frozen-heldouts-zephyr-v2/manifest.json'
    retain(frozen,'1b3bbe5e0c585beff4905761547964073bb177ac97c1145aa9722dfcb016c78e')
    os.environ['MERLIN_TARGET_PATH']=str(ROOT/'integration/iris-mlir')
    os.environ.setdefault('MERLIN_CHIPYARD_IRIS','/scratch/eygao/iris-cy')
    from merlin.runtime.backends.zephyr_model import MatrixRouting
    route=MatrixRouting(support_target='iris',unit='saturn_vme',config='IrisConfig')
    shim=route.provider().vme_shim;contract=shim.load_contract(route.unit)
    tools=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin')
    objcopy=tools/'riscv64-unknown-elf-objcopy';nm=tools/'riscv64-unknown-elf-nm'
    commands=[];prototypes=[];model_symbols=[];goldens=[];op_artifacts={}
    for op,receipt_path in [('gemm',a.gemm),('conv2d',a.conv2d)]:
        receipt_path=receipt_path.resolve();d=json.loads(receipt_path.read_text());retain(receipt_path)
        k=64 if op=='gemm' else 72
        if d['op']!=op or d['local_shape_mnk']!=[32,64,k] or d['pointer_symbol']!='merlin_vme_gemm_i8_0_pointers':raise ValueError('Unexpected compiler ABI')
        for path,h in d['source_sha256'].items():retain(path,h)
        for item in d['artifacts'].values():retain(item['path'],item['sha256'])
        op_artifacts[op]={'receipt_sha256':sha(receipt_path),'shape_mnk':[64,64,k],
            'MLIR_scope':'Actual compiled32x64xK contraction; caller supplies convolution im2col indexing' if op=='conv2d' else 'Actual compiled32x64x64 contraction'}
        goldens.append([golden(op,dataset,64,64,k) for dataset in range(3)])
        for kind in ['shipped','twin']:
            stem='batch_'+op+'_'+kind
            unit,enc=shim.emit_translation_unit({stem:(32,64,k)},contract,alignment_bytes=16)
            (generated/(stem+'.c')).write_text(str(unit))
            (generated/(stem+'-encodings.json')).write_text(json.dumps(enc.to_dict(),indent=2)+'\n')
            for p in enc.sources:retain(p)
            mapping={'forward':stem+'_forward','_mlir_ciface_forward':stem+'_ciface',
                'dealloc_helper':stem+'_dealloc','merlin_vme_gemm_i8_0':stem+'_raw',
                'merlin_vme_gemm_i8_0_pointers':stem+'_pointers'}
            mapfile=generated/(stem+'.syms');mapfile.write_text(''.join(x+' '+y+'\n' for x,y in mapping.items()))
            for key,name in [('model_object','model'),('bridge_object','bridge')]:
                src=d['artifacts'][key]['path'];dest=generated/(stem+'_'+name+'.o')
                cmd=[str(objcopy),'--redefine-syms='+str(mapfile),src,str(dest)]
                subprocess.run(cmd,check=True);commands.append(cmd)
                listing=subprocess.check_output([str(nm),'-g',str(dest)],text=True)
                (generated/(stem+'_'+name+'.nm')).write_text(listing)
                if any(line.split()[-1] in mapping for line in listing.splitlines()):raise ValueError('Unrenamed compiler symbols')
            prototypes.append('extern void '+stem+'_ciface(void*,void*,void*);')
            model_symbols.append(stem+'_ciface')
    config='#pragma once\n#include <stdint.h>\n#define BATCH_TRIALS 5\nstruct batch_memref2 {void *allocated,*aligned;int64_t offset,sizes[2],strides[2];};\n'
    config+='\n'.join(prototypes)+'\nstatic void(*const batch_models[4])(void*,void*,void*)={'+','.join(model_symbols)+'};\n'
    config+='static const uint32_t batch_expected[2][3][4096]={\n'+',\n'.join('{'+',\n'.join('{'+','.join(str(x)+'u' for x in g['accumulator_u32'])+'}' for g in group)+'}' for group in goldens)+'\n};\n'
    config+='static const uint32_t batch_expected_w8[2][3][4096]={\n'+',\n'.join('{'+',\n'.join('{'+','.join(str(x)+'u' for x in g['w8a8_f32_words'])+'}' for g in group)+'}' for group in goldens)+'\n};\n'
    (generated/'batch_config.h').write_text(config)
    (out/'golden.json').write_text(json.dumps(goldens)+'\n')
    cases=[];phases=[]
    for phase in range(8):
        op='conv2d' if phase//4 else 'gemm';workers=1+(phase%4)//2;kind='twin' if phase&1 else 'shipped';prefix=f'heldout.batch.{op}.h{workers}.{kind}'
        parent=f'merlin.zephyr.{op}.{workers}compute'
        phases.append({'phase':phase,'op':op,'workers':workers,'kind':kind,'parent_case_id':parent})
        for job in range(15):
            checks=[0,0,0];acc=goldens[phase//4][job%3]['accumulator_u32']
            for h in range(workers):checks[h]=output_hash(acc[64*h//workers*64:64*(h+1)//workers*64])
            cases.append({'case_id':prefix+'.job'+str(job),'id':prefix+'.job'+str(job),'parent_case_id':parent,
                'region':'job'+str(job),'trial_id':job//3,'dataset_id':job%3,'active_harts':list(range(workers)),
                'expected_checksums_by_hart':checks,'corpus_split':'iris-fast-heldout-zephyr-batch-v1','fitting_allowed':False})
        cases.append({'case_id':prefix+'.e2e','id':prefix+'.e2e','parent_case_id':parent,'region':'pipeline_end_to_end',
            'active_harts':[2],'expected_checksums_by_hart':[0,0,producer_golden(5)],'corpus_split':'iris-fast-heldout-zephyr-batch-v1','fitting_allowed':False})
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    app=ROOT/'zephyr/heldout-batch';extra=generated/'extra.conf'
    extra.write_text('CONFIG_COMPILER_OPT="-DIRIS_TEST_SKIP_KERNEL"\n' if a.skip_kernel else '')
    inputs=[Path(__file__),ROOT/'zephyr/compiler_pipeline.py',ROOT/'zephyr/freeze_heldouts.py',
        ROOT/'integration/iris-mlir/zephyr/task_setup.h',ROOT/'integration/iris-mlir/zephyr/iris_uart_profile.h',
        ROOT/'integration/iris-mlir/zephyr/uart-profiles.json',ROOT/'integration/iris-mlir/vme_kernel.py',
        ROOT/'integration/iris-mlir/vme_shim.py',ROOT/'integration/iris-mlir/source_facts.py',objcopy,nm,
        *[p for p in generated.iterdir() if p.is_file()],out/'golden.json',out/'cases.json',
        *[p for p in app.rglob('*') if p.is_file()],*uart_inputs('ethan-firesim')]
    for p in inputs:retain(p)
    subprocess.run([sys.executable,str(ROOT/'zephyr/prepare_context_tree.py')],check=True)
    cmd=[sys.executable,str(ROOT/'zephyr/context_build.py'),'--source',str(ROOT/'third_party/zephyr-iris'),
        '--patch',str(ROOT/'zephyr/patches/0002-iris-vme-context.patch'),'--uart-profile','ethan-firesim',
        '--app',str(app),'--output',str(out/'build'),'--cmake=-DIRIS_KERNEL_DIR='+str(generated),
        '--cmake=-DIRIS_TARGET_DIR='+str(ROOT/'integration/iris-mlir')]
    if a.skip_kernel:cmd+=['--extra-conf',str(extra)]
    for p in inputs:
        if ROOT in p.resolve().parents:cmd+=['--input',str(p)]
    commands.append(cmd)
    with(out/'build.log').open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
    build=json.loads((out/'build/build.json').read_text());elf=out/'build/zephyr/zephyr.elf';full_elf=elf
    retain(out/'build/build.json');retain(elf,build['elf_sha256']);byte_derivative=None
    if a.compact:
        names=subprocess.check_output([str(nm),'-S','--defined-only',str(elf)],text=True)
        rows=[x.split()for x in names.splitlines()if x.endswith(' iris_heldout_full_output')]
        if len(rows)!=1 or int(rows[0][1],16)!=1 or rows[0][2].upper()not in ('D','R'):raise ValueError('Exact one-byte data symbol required')
        address=int(rows[0][0],16);data=bytearray(elf.read_bytes());phoff=struct.unpack_from('<Q',data,32)[0];size,count=struct.unpack_from('<HH',data,54);offsets=[]
        for i in range(count):
            typ,flags,offset,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',data,phoff+i*size)
            if typ==1 and va<=address<va+fs:
                offsets.append(offset+address-va)
        shoff=struct.unpack_from('<Q',data,40)[0];shsize,shcount=struct.unpack_from('<HH',data,58);sections=[]
        for i in range(shcount):
            _,typ,flags,va,offset,sz,*_=struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*shsize)
            if va<=address<va+sz and typ==1 and flags&2:sections.append({'index':i,'flags':flags})
        if len(sections)!=1 or sections[0]['flags']&4:raise ValueError('Mode byte must be in an allocated non-instruction section')
        if len(offsets)!=1 or data[offsets[0]]!=1:raise ValueError('Expected one mapped initialized full-output byte')
        data[offsets[0]]=0;elf=out/'compact.elf';elf.write_bytes(data);retain(elf)
        diffs=[i for i,(x,y)in enumerate(zip(full_elf.read_bytes(),data))if x!=y]
        if diffs!=offsets:raise ValueError('Console selection changed other bytes')
        byte_derivative={'parent_full_ELF':str(full_elf),'parent_sha256':sha(full_elf),'mode_symbol':'iris_heldout_full_output',
            'symbol_address':address,'file_offset':offsets[0],'old_byte':1,'new_byte':0,'different_file_bytes':1,
            'instruction_section_bytes_identical':True,'data_section':sections[0],'ROI_and_kernel_code_identical':True}
    for p,h in build['input_sha256'].items():retain(ROOT/p,h)
    for p,item in recorded.items():
        if sha(p)!=item['sha256']:raise ValueError('Input changed during freeze '+p)
    report={'schema':'iris.frozen_compatible_Zephyr_Merlin_heldout_batch.v1','status':'frozen_not_executed',
        'split_id':'iris-fast-heldout-zephyr-batch-v1','fitting_allowed':False,'timing_observed':False,
        'negative_skip_kernel':a.skip_kernel,'compact_output':a.compact,'one_byte_derivative':byte_derivative,'trials':5,'datasets':3,'physical_harts':3,'phases':phases,
        'cases':128,'expected_regions':188,'expected_output_elements':8*15*4096,
        'ELF':str(elf),'ELF_sha256':sha(elf),'cases_sha256':sha(out/'cases.json'),'golden_sha256':sha(out/'golden.json'),
        'uart_profile':'ethan-firesim','MLIR_artifacts':op_artifacts,
        'context_ABI':'Explicit iris_vme_enable on0/1 only; hart2 positive RVV producer plus VME ownership refusal',
        'scope':'One ZephyrSMP ELF serializes8phases, all3CPUs online, doublebuffer producer overlaps1/2compute tasks. Full outputs poisoned before eachphase outsideROI. Threadjoin before reuse. Compute/e2e scopes preserved; ELF layout/phases differ from original globalheldouts. No claim originaltimings interchangeable.',
        'global_elapsed_source':'Actual CLINT.mtime MMIO 0x0200bff8;500kHz;1000sourcecorecycles/tick. Two timer reads enclose producer mcycle/minstret interval; tick quantization and read-boundary scope explicit.',
        'end_to_end_scope':'Perphase hart2 producerentry throughoutputsconsumed, excludes boot/mainthreadcreation/finalprinting. Hartmcycle can stop during WFI; globalelapsed uses separate CLINT interval. Wholebatch endtoend not claimed.',
        'inactive_hart_policy':'Unused compute CPU retains normal Zephyr scheduler/idle/WFI',
        'new_workload_identity_frozen_before_timing':True,'holdout_retirement_policy':'Retire before any parameter update informed by its timing errors',
        'commands':commands,'inputs':recorded,'hardware_contacted':False,'timing_certified':False}
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'ELF_sha256':sha(elf),'manifest_sha256':sha(out/'manifest.json'),'regions':188}))

if __name__=='__main__':main()

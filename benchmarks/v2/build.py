#!/usr/bin/env python3
"""Build a separate v2 identifying corpus without changing any v1 artifact."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from cases import cases, KINDS, PENDING

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'))
    parser.add_argument('--output',type=Path,default=HERE/'build')
    parser.add_argument('--select-regex',help='Debug subset; does not overwrite the complete frozen v2 corpus')
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    selected=[case for case in cases() if not args.select_regex or re.search(args.select_regex,case['case_id'])]
    if not selected: raise SystemExit('empty case selection')
    include=out/'cases.inc'
    fields=('n','mask','sew','lmul','mode','bytes','protocol','edge','tk','tiles')
    records=[]
    for case in selected:
        records.append('{'+json.dumps(case['case_id'])+',K_'+case['kind']+','+','.join(str(case[k]) for k in fields)+
                       ',{'+','.join(str(x)+'ULL' for x in case['expected_checksums'])+'}}')
    include.write_text('static const case_t experiments[] = {\n'+',\n'.join(records)+'\n};\n')
    refs={
      'scalar':['hart0.scalar.native-integers','hart2.scalar.native-integers'],
      'memory':['hart0.scalar.native-integers','hart2.scalar.native-integers'],
      'scalar_fp':['hart0.scalar.ieee-floating','hart2.scalar.ieee-floating'],
      'vector_int':['hart0.vector.integer-arithmetic','hart2.vector.integer-arithmetic'],
      'vector_fp':['hart0.vector.ieee-fma','hart2.vector.ieee-fma'],
      'vme_int':['hart0.vme.int8-mac','hart1.vme.int8-mac'],
      'vme_fp8':['hart0.vme.fp8-mac','hart1.vme.fp8-mac'],
      'row_read':['hart0.vme.tile-row-transport'], 'row_write':['hart0.vme.tile-row-transport'],
      'tile_zero':['hart0.vme.tile-row-transport'],'vme_memory':['hart0.vme.int8-mac'],
      'shared_fpu':['hart2.vector.ieee-fma','hart2.scalar.ieee-floating'],
      'pipeline':['hart0.vector.integer-arithmetic','hart1.vector.integer-arithmetic','hart2.vector.integer-arithmetic'],
      'pipeline_vme':['hart0.vme.int8-mac','hart1.vme.int8-mac','hart2.scalar.native-integers'],
      'vme_refusal':['hart2.vme.int8-mac'],
    }
    dtypes=json.loads((ROOT/'hardware/dtypes.json').read_text())
    valid_ids={r['id'] for r in dtypes['capabilities']}
    for case in selected:
        case['hardware_capability_ids']=refs.get(case['kind'],refs['scalar'])
        if not set(case['hardware_capability_ids'])<=valid_ids: raise SystemExit('unknown source capability')
        case['jobs']=[]
        for hart in range(3):
            if not case['mask']&(1<<hart): continue
            role='kernel';units=['scalar']
            if case['kind'].startswith('vector'): units=['saturn_vector']
            if case['kind'].startswith('vme') or case['kind'] in ('row_read','row_write','tile_zero'): units=['saturn_vector','vme']
            if case['kind']=='shared_fpu': units=['scalar_fpu','saturn_vector_shared_fpu']
            if case['kind']=='memory' and case['mode'] in (3,4):
                role='reader' if hart!=2 else 'scalar_writer' if case['mode']==3 else 'vector_writer'
                if role=='vector_writer': units=['saturn_vector']
            if case['kind'] in ('pipeline','pipeline_vme'):
                role='producer' if hart==case['metadata']['producer_hart'] else 'compute' if hart==case['metadata']['compute_hart'] else 'consumer'
                if role=='compute': units=['saturn_vector'] if case['kind']=='pipeline' else ['saturn_vector','vme']
            if case['kind']=='vme_refusal': role='expected_illegal_instruction_probe'
            case['jobs'].append({'job_id':case['case_id']+'.hart'+str(hart),'hart':hart,
                                 'core_kind':'Shuttle' if hart<2 else 'Rocket','role':role,'units':units,
                                 'expected_checksum':case['expected_checksums'][hart]})
        if case['kind'] in ('pipeline','pipeline_vme'):
            jobs={j['role']:j['job_id'] for j in case['jobs']}
            case['dependencies']={'repetitions':case['n'],'within_iteration':[[jobs['producer'],jobs['compute']],[jobs['compute'],jobs['consumer']]],
                                  'between_iterations':[[jobs['consumer'],jobs['producer']]],'ordering':'acquire/release monotonically numbered phase'}
        else: case['dependencies']={'within_iteration':[]}
    corpus={'schema_version':2,'split_id':'iris-identifying-v2','purpose':'fitting experiments and functional placement legality; no heldout timings consumed',
            'hardware_manifest_sha256':sha(ROOT/'hardware/manifest.json'),'dtype_manifest_sha256':sha(ROOT/'hardware/dtypes.json'),
            'physical_harts':3,'arithmetic_harts':[0,1,2],'matrix_harts':[0,1],'rocket_hart':2,
            'hart2_vector_config_name':'dmaParams; arithmetic is present despite the config nickname',
            'cases':selected,'pending_cases':PENDING,
            'expected_region_count':sum(bin(case['mask']).count('1') for case in selected),
            'hart_subsets_tested':sorted({case['mask'] for case in selected}),
            'counter_policy':'raw target mcycle/minstret, completion drains included, verification outside region; no overhead subtraction',
            'cache_protocols':{'0':'no special cache preparation',
                               '1':'initialize private target then read complete working set before region',
                               '2':'initialize target then read 2MiB of disjoint per-hart eviction storage at 64-byte stride; an eviction attempt, not guaranteed cold'},
            'inactive_policy':'WFI; last active hart wakes inactive harts via CLINT MSIP; no busy idle readers',
            'coverage_limits':['Eviction is not a cache flush or a guaranteed replacement-state reset',
                               'Function-call, loop and drain instructions remain inside measured regions',
                               'Checksum arithmetic is outside regions; per-hart early completion waits may affect peers',
                               'Native vector BF16/FP8 arithmetic/conversion remains pending in this corpus',
                               'No Zephyr or heldout performance is fit by this suite'],
            'timing_certified':False}
    corpus['v1_frozen_input_sha256']={str(p.relative_to(ROOT)):sha(p) for p in
        [HERE.parent/'batch.c',HERE.parent/'calibration-corpus.json',HERE.parent/'heldout-corpus.json']}
    common=HERE.parent
    compiler=args.compiler.resolve()
    elf=out/'batch-v2.elf'
    command=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin',
             '-fno-tree-vectorize','-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-fno-common',
             '-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static',
             '-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-I'+str(common),'-I'+str(out),
             '-I'+str(ROOT/'third_party/saturn/benchmarks/common'),'-T',str(common/'link.ld'),
             str(common/'start.S'),str(common/'runtime.c'),str(HERE/'batch.c'),'-lgcc','-o',str(elf)]
    completed=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (out/'build.log').write_text(completed.stdout)
    if completed.returncode: raise SystemExit(completed.stdout)
    inputs=[HERE/'cases.py',HERE/'batch.c',Path(__file__),common/'runtime.h',common/'runtime.c',common/'uart_drain.h',common/'start.S',common/'link.ld',include,
            ROOT/'third_party/saturn/benchmarks/common/vme.h']
    libgcc=Path(subprocess.check_output([str(compiler),'-print-file-name=libgcc.a']).decode().strip())
    if not libgcc.is_file(): raise SystemExit('missing linked libgcc.a')
    inputs.append(libgcc)
    provenance={'schema_version':1,'elf':str(elf),'elf_sha256':sha(elf),'compiler':str(compiler),'compiler_sha256':sha(compiler),
                'compiler_version':subprocess.check_output([str(compiler),'--version']).decode().splitlines()[0],
                'command':command,'input_sha256':{str(p):sha(p) for p in inputs},'executed':False}
    corpus['source_sha256']={str(p.relative_to(ROOT)):sha(p) for p in inputs if p.is_relative_to(ROOT) and p!=include}
    (out/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n')
    (out/'build.json').write_text(json.dumps(provenance,indent=2)+'\n')
    if not args.select_regex: (HERE/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n')
    print(json.dumps({'cases':len(selected),'regions':corpus['expected_region_count'],'elf':str(elf),'sha256':sha(elf)}))

if __name__=='__main__': main()

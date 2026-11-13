#!/usr/bin/env python3
"""Exact three-hart placement acceptance; no timing or Zephyr certification.

Reuses the existing v2 runner/console validator, adding job/dependency checks and
only the missing LR/SC, IPI and explicit-fence placement guest.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
_spec=importlib.util.spec_from_file_location('distribution_v2_validate',HERE/'validate.py')
_base=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_base)
MASKS=(1,2,4,3,5,6,7)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rows(text):
    return [json.loads(line.split(' ',1)[1]) for line in text.splitlines() if line.startswith('IRIS_REGION ')]


def verify_case_table(corpus,text):
    """Bind declaration fields to the exact generated table included in the ELF."""
    fields=('n','mask','sew','lmul','mode','bytes','protocol','edge','tk','tiles')
    pattern=re.compile(r'^\{("[^"]+"),K_(\w+),([0-9,]+),\{([0-9UL,]+)\}\},?$')
    records={}
    for raw in text.splitlines():
        line=raw.strip()
        if not line.startswith('{'): continue
        match=pattern.fullmatch(line)
        if not match: raise ValueError('unrecognized compiled case initializer')
        name=json.loads(match[1]);values=[int(v) for v in match[3].split(',')]
        if name in records or len(values)!=len(fields): raise ValueError('duplicate or malformed compiled case')
        records[name]={'kind':match[2],**dict(zip(fields,values)),
                       'expected_checksums':[int(v.removesuffix('ULL')) for v in match[4].split(',')]}
    if set(records)!={c['case_id'] for c in corpus['cases']}: raise ValueError('compiled case coverage mismatch')
    for case in corpus['cases']:
        for key,value in records[case['case_id']].items():
            if case.get(key)!=value: raise ValueError('corpus differs from compiled case table: '+case['case_id']+' '+key)


def audit_distribution(text,corpus):
    result=_base.validate(text,corpus)
    if corpus.get('physical_harts')!=3 or corpus.get('arithmetic_harts')!=[0,1,2] or corpus.get('matrix_harts')!=[0,1]:
        raise ValueError('exact heterogeneous three-hart contract missing')
    for family in ('dependent','independent','vector_int','vector_fp','memory','atomic'):
        if {c['mask'] for c in corpus['cases'] if c['kind']==family}!=set(MASKS):
            raise ValueError('missing hart subset for '+family)
    seen_jobs=set();positive=[0,0,0];negative=[];pipelines=[]
    observed={(r['case_id'],r['hart']) for r in _rows(text)}
    for case in corpus['cases']:
        if type(case['mask']) is not int or not 1<=case['mask']<=7: raise ValueError('invalid placement mask')
        active={h for h in range(3) if case['mask']&(1<<h)}
        jobs=case.get('jobs',[])
        if len(jobs)!=len(active) or {j['hart'] for j in jobs}!=active:
            raise ValueError('missing or misrouted job ledger for '+case['case_id'])
        for job in jobs:
            h=job['hart']
            if type(h) is not int or job['job_id'] in seen_jobs: raise ValueError('invalid/duplicate job identity')
            seen_jobs.add(job['job_id'])
            if job['core_kind']!=('Shuttle' if h<2 else 'Rocket'): raise ValueError('wrong core kind')
            if job['expected_checksum']!=case['expected_checksums'][h] or (case['case_id'],h) not in observed:
                raise ValueError('job result or expected checksum missing')
            if case['kind']=='vme_refusal':
                if h!=2 or job['role']!='expected_illegal_instruction_probe' or case['metadata'].get('expected_exception')!='illegal_instruction':
                    raise ValueError('invalid negative VME legality probe')
                negative.append({'case_id':case['case_id'],'hart':h,'expected_exception':'illegal_instruction','observed_trap_count':1})
            else:
                if 'vme' in job['units'] and h==2: raise ValueError('positive VME work misrouted to hart 2')
                positive[h]+=1
        if case['kind'] in ('pipeline','pipeline_vme'):
            by_role={j['role']:j for j in jobs}
            if set(by_role)!= {'producer','compute','consumer'}: raise ValueError('missing pipeline role')
            mode=case['mode']
            route={'producer':mode,'compute':(mode+1)%3,'consumer':(mode+2)%3} if case['kind']=='pipeline' else {'producer':2,'compute':mode,'consumer':1-mode}
            for role in by_role:
                if by_role[role]['hart']!=case['metadata'][role+'_hart'] or by_role[role]['hart']!=route[role]:
                    raise ValueError('pipeline role/hart mismatch')
            p,c,r=[by_role[role]['job_id'] for role in ('producer','compute','consumer')]
            dep=case.get('dependencies',{})
            if dep.get('within_iteration')!=[[p,c],[c,r]] or dep.get('between_iterations')!=[[r,p]] or dep.get('repetitions')!=case['n']:
                raise ValueError('pipeline dependency contract missing or misrouted')
            pipelines.append({'case_id':case['case_id'],'kind':case['kind'],'producer_hart':by_role['producer']['hart'],
                              'compute_hart':by_role['compute']['hart'],'consumer_hart':by_role['consumer']['hart'],
                              'repetitions':case['n'],'result':'source-bound phase protocol and final checksums passed',
                              'dynamic_dependency_timing_instrumented':False})
    for family in ('scalar_fp','vector_fp'):
        for sew in (16,32,64):
            if not any(c['kind']==family and c['sew']==sew and c['mask']&4 for c in corpus['cases']):
                raise ValueError('positive Rocket FP work missing')
    for sew in (8,16,32,64):
        if not any(c['kind']=='vector_int' and c['sew']==sew and c['mask']&4 for c in corpus['cases']):
            raise ValueError('positive Rocket vector integer width missing')
    if {p['compute_hart'] for p in pipelines if p['kind']=='pipeline'}!={0,1,2}:
        raise ValueError('three-hart rotating vector pipeline missing')
    matrix=[p for p in pipelines if p['kind']=='pipeline_vme']
    if {p['compute_hart'] for p in matrix}!={0,1} or any(p['producer_hart']!=2 for p in matrix):
        raise ValueError('concurrent VME producer/consumer placement missing')
    if not negative or not all(positive): raise ValueError('positive/negative placement evidence missing')
    return {**result,'positive_work_regions_per_hart':positive,'negative_legality_probes':negative,
            'pipeline_results':pipelines,'job_count':len(seen_jobs),'all_seven_nonempty_subsets_verified':True,
            'dependency_assurance':'Known hashed guest protocol plus independent final results; not a dependency timing trace'}


def sync_corpus():
    cases=[]
    for kind,golden,iterations in [('lrsc',64,64),('ipi',8,8),('fence_messages',136,16),('lrsc_invalidated',1,1)]:
        for mask in MASKS:
            if kind=='lrsc_invalidated' and bin(mask).count('1')<2: continue
            case={'case_id':'distribution.'+kind+'.mask'+str(mask),'mask':mask,'kind':kind,'iterations':iterations,
                  'expected_checksums':[golden]*3,'region':'kernel','status':'ready'}
            if kind=='lrsc': case['shared_counter_golden']=64*bin(mask).count('1')
            if kind=='lrsc_invalidated': case['shared_counter_golden']=7
            cases.append(case)
    return {'schema_version':2,'purpose':'functional synchronization placement; no timing calibration','cases':cases,
            'expected_region_count':sum(bin(c['mask']).count('1') for c in cases),'timing_certified':False}


def validate_sync(text,corpus):
    result=_base.validate(text,corpus)
    expected={c['case_id']:c['shared_counter_golden'] for c in corpus['cases'] if 'shared_counter_golden' in c}
    seen=set()
    for line in text.splitlines():
        if not line.startswith('IRIS_SYNC_ASSERT '): continue
        row=json.loads(line.split(' ',1)[1]);key=row['case_id']
        if key not in expected or key in seen or row.get('name')!='shared_counter': raise ValueError('unexpected synchronization assertion')
        if type(row.get('actual')) is not int or row['actual']!=expected[key] or row.get('expected')!=expected[key] or row.get('pass') is not True:
            raise ValueError('global LR/SC counter mismatch')
        seen.add(key)
    if seen!=set(expected): raise ValueError('missing global LR/SC counter assertion')
    return {**result,'global_counter_assertions':len(seen),
            'families':{'lrsc':list(MASKS),'ipi':list(MASKS),'fence_messages':list(MASKS),
                        'lrsc_invalidated':[3,5,6,7]},
            'fence_assurance':'Explicit fenced messages under the simulator functional ordering; not exhaustive RVWMO certification'}


def zephyr_audit():
    base=ROOT/'benchmarks/zephyr';source=base/'src/main.c';kconfig=base/'Kconfig'
    code=source.read_text();config=kconfig.read_text()
    match=re.search(r'config IRIS_BENCH_WORKERS.*?\brange\s+(\d+)\s+(\d+)',config,re.S)
    inputs={str(p.relative_to(ROOT)):sha(p) for p in [source,kconfig,base/'prj.conf',base/'CMakeLists.txt']}
    return {'source_sha256':inputs,'declared_worker_range':[int(match[1]),int(match[2])] if match else None,
            'unconditional_hart2_rejection_detected':bool(re.search(r'if\s*\(\s*actual\s*>\s*1\s*\)',code)),
            'built':False,'executed':False,'all_three_hart_zephyr_acceptance_passed':False,
            'limits':['Board port, exact CPU-index-to-hart mapping and deployed ELF have not been built or exercised here.',
                      'Baremetal all-three-hart acceptance does not establish Zephyr SMP, preemption or vector/tile context handling.',
                      'Source-pattern observations are hints for review, not a Zephyr implementation certification.']}


def build_sync(out,compiler):
    common=HERE.parent;elf=out/'distribution-sync.elf'
    command=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize',
             '-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-mcmodel=medany','-mabi=lp64d',
             '-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3',
             '-I'+str(common),'-T',str(common/'link.ld'),str(common/'start.S'),str(common/'runtime.c'),
             str(HERE/'distribution_sync.c'),'-lgcc','-o',str(elf)]
    completed=subprocess.run(command,text=True,capture_output=True)
    (out/'sync-build.log').write_text(completed.stdout+completed.stderr)
    if completed.returncode: raise RuntimeError('supplemental guest build failed; see sync-build.log')
    libgcc=Path(subprocess.check_output([str(compiler),'-print-file-name=libgcc.a']).decode().strip())
    inputs=[HERE/'distribution_sync.c',Path(__file__),common/'runtime.h',common/'runtime.c',common/'start.S',common/'link.ld',libgcc]
    record={'command':command,'compiler_sha256':sha(compiler),'input_sha256':{str(p):sha(p) for p in inputs},
            'elf':str(elf),'elf_sha256':sha(elf)}
    (out/'sync-build.json').write_text(json.dumps(record,indent=2)+'\n')
    return elf,record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,default=HERE/'build')
    parser.add_argument('--output',type=Path,default=HERE/'distribution-results')
    parser.add_argument('--spike',type=Path,default=ROOT/'spike/bin/spike-iris-functional')
    parser.add_argument('--compiler',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'))
    parser.add_argument('--dtc',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/bin/dtc'))
    parser.add_argument('--timeout',type=int,default=120)
    parser.add_argument('--seed',type=int,default=0)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    # Replace any previous success before reading inputs or starting a subprocess.
    # An interrupted or failed rerun must never leave an earlier pass in place.
    (out/'acceptance.json').write_text(json.dumps({
        'schema_version':1,'scope':'baremetal exact-three-hart functional distribution',
        'status':'in_progress','acceptance_passed':False,'timing_certified':False,
        'overall_project_goal_complete':False},indent=2)+'\n')
    compiler=args.compiler.resolve();binary=args.spike.resolve();build=args.build.resolve()
    corpus=json.loads((build/'corpus.json').read_text())
    verify_case_table(corpus,(build/'cases.inc').read_text())
    initial_binary_hash=sha(binary)
    uart=ROOT/'spike/bin/libsifive_uart.so'
    initial_uart_hash=sha(uart)
    provenance=ROOT/'spike/provenance.json'
    initial_provenance_hash=sha(provenance)
    sync_elf,sync_build=build_sync(out,compiler)
    command=['python3',str(HERE/'run.py'),'--build',str(build),'--spike',str(binary),'--dtc',str(args.dtc.resolve()),
             '--timeout',str(args.timeout),'--seed',str(args.seed)]
    driver=subprocess.run(command,text=True,capture_output=True)
    (out/'v2-driver.stdout').write_text(driver.stdout);(out/'v2-driver.stderr').write_text(driver.stderr)
    if driver.returncode: raise SystemExit('existing v2 runner failed; see v2-driver logs')
    for suffix in ('stdout','stderr','json'): shutil.copy2(build/('run.'+suffix),out/('v2.'+suffix))
    v2_record=json.loads((out/'v2.json').read_text())
    if (v2_record['spike_sha256']!=initial_binary_hash or
        v2_record['uart_plugin_sha256']!=initial_uart_hash or
        v2_record['spike_provenance_sha256']!=initial_provenance_hash or
        v2_record['timing_certified'] is not False):
        raise SystemExit('unexpected v2 simulator identity or certification status')
    distribution=audit_distribution((out/'v2.stdout').read_text(),corpus)
    sync_definition=sync_corpus();(out/'sync-corpus.json').write_text(json.dumps(sync_definition,indent=2)+'\n')
    sync_command=list(v2_record['command']);sync_command[-1]=str(sync_elf)
    env=dict(os.environ);env['PATH']=str(args.dtc.resolve().parent)+os.pathsep+env['PATH'];env.pop('IRIS_FATAL_PCS',None)
    start=time.perf_counter()
    try: proc=subprocess.run(sync_command,cwd=out,env=env,text=True,capture_output=True,timeout=args.timeout)
    except subprocess.TimeoutExpired as error:
        for kind,value in [('stdout',error.stdout),('stderr',error.stderr)]:
            (out/('sync.'+kind)).write_bytes(value if isinstance(value,bytes) else (value or '').encode())
        raise SystemExit('supplemental synchronization guest timed out')
    elapsed=time.perf_counter()-start
    (out/'sync.stdout').write_text(proc.stdout);(out/'sync.stderr').write_text(proc.stderr)
    if proc.returncode: raise SystemExit('supplemental synchronization guest failed; see sync logs')
    synchronization=validate_sync(proc.stdout,sync_definition)
    if sha(binary)!=initial_binary_hash or sha(uart)!=initial_uart_hash or sha(provenance)!=initial_provenance_hash:
        raise SystemExit('simulator, UART plugin or package provenance changed during acceptance')
    report={'schema_version':1,'scope':'baremetal exact-three-hart functional distribution',
            'status':'passed','acceptance_passed':True,'timing_certified':False,'overall_project_goal_complete':False,
            'instruction_based_times_are_uncalibrated':True,'seed':args.seed or None,
            'spike_sha256':initial_binary_hash,'uart_plugin_sha256':v2_record['uart_plugin_sha256'],
            'spike_provenance_sha256':initial_provenance_hash,
            'v2_elf_sha256':v2_record['elf_sha256'],'v2_corpus_sha256':sha(build/'corpus.json'),
            'v2_compiled_case_table_sha256':sha(build/'cases.inc'),
            'v2_source_input_sha256':json.loads((build/'build.json').read_text())['input_sha256'],
            'runner_source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'run.py',HERE/'validate.py']},
            'distribution':distribution,'synchronization':synchronization,'sync_build':sync_build,
            'sync_command':sync_command,'sync_host_elapsed_seconds':elapsed,'host_elapsed_is_target_time':False,
            'zephyr':zephyr_audit(),
            'output_sha256':{p.name:sha(p) for p in [out/'v2.stdout',out/'v2.stderr',out/'sync.stdout',out/'sync.stderr']},
            'limits':['No placement speed ranking or Iris cycle accuracy is certified.',
                      'Static dependency ledgers are checked against known source protocols/results, not dynamic per-edge traces.']}
    (out/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'acceptance_passed':True,'scope':report['scope'],'v2_cases':distribution['cases'],
                      'v2_regions':distribution['regions'],'sync_cases':synchronization['cases'],'sync_regions':synchronization['regions'],
                      'positive_work_regions_per_hart':distribution['positive_work_regions_per_hart'],
                      'negative_legality_probes':distribution['negative_legality_probes'],
                      'timing_certified':False,'zephyr_acceptance_passed':False,'report':str(out/'acceptance.json')},indent=2))


if __name__=='__main__': main()

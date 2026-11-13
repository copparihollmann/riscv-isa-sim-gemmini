#!/usr/bin/env python3
"""Freeze two functional schedules and adversarial checks before FPGA setup."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benchmarks.compute_fit.validate import validate

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'benchmarks/compute_fit'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify(build):
    corpus=json.loads((build/'corpus.json').read_text());built=json.loads((build/'build.json').read_text())
    if (build/'qualification.json').exists() or (build/'ready.json').exists(): raise ValueError('Qualification already frozen')
    inputs={str(build/name):sha(build/name) for name in ('campaign.elf','build.json','corpus.json','disassembly.txt','readback-layout.json')}
    if built['elf_sha256']!=inputs[str(build/'campaign.elf')]:raise ValueError('Changed ELF')
    for path,digest in built['input_sha256'].items():
        if sha(path)!=sha(build/'inputs'/digest) or sha(path)!=digest:raise ValueError('Changed exact build input '+path)
    runs=[]
    for seed in (0,17):
        directory=build/f'seed{seed}';r=json.loads((directory/'run.json').read_text())
        if (r.get('status')!='passed' or r['seed']!=seed or r['exit_status']!=0 or not r['functional_checks_passed']
                or r['stdout_sha256']!=sha(directory/'run.stdout') or r['stderr_sha256']!=sha(directory/'run.stderr')):
            raise ValueError('Actual successful byte-bound functional schedule required')
        for path,digest in r['input_sha256'].items():
            if sha(path)!=digest:raise ValueError('Changed functional execution input '+path)
        text=(directory/'run.stdout').read_text();result=validate(text,corpus)
        runs.append({'seed':seed,'results_sha256':sha(directory/'run.json'),'stdout_sha256':sha(directory/'run.stdout'),
            'stderr_sha256':sha(directory/'run.stderr'),'exit_status':0,'regions':result['regions'],
            'host_seconds':r['host_seconds'],'functional_checks_passed':True})
        inputs.update({str(directory/name):sha(directory/name) for name in ('run.json','run.stdout','run.stderr')})
        inputs.update(r['input_sha256'])
    lines=text.splitlines();index=next(i for i,line in enumerate(lines) if line.startswith('IRIS_REGION '))
    original=json.loads(lines[index].split(' ',1)[1]);mutations=[]
    for field,value in [('checksum',original['checksum']+1),('expected_checksum',original['expected_checksum']+1),
                        ('parent_case_id','wrong'),('trial_id',99),('suite','wrong'),('hart',3),('pass',False),
                        ('start_cycle',True),('end_cycle',original['start_cycle'])]:
        row=dict(original);row[field]=value;changed=lines.copy();changed[index]='IRIS_REGION '+json.dumps(row)
        mutations.append((field,'\n'.join(changed)))
    mutations += [('missing_region','\n'.join(lines[:index]+lines[index+1:])),
        ('duplicate_region',text+'\n'+lines[index]),
        ('missing_completion','\n'.join(line for line in lines if not line.startswith('IRIS_BATCH_DONE '))),
        ('duplicate_completion',text+'\n'+next(line for line in lines if line.startswith('IRIS_BATCH_DONE '))),
        ('fatal',text+'\nIRIS_FATAL {"hart":2,"cause":2}')]
    guards=[]
    for name,body in mutations:
        try:validate(body,corpus)
        except (ValueError,KeyError,TypeError) as error:guards.append({'name':name,'rejected':True,'reason':str(error)})
        else:raise AssertionError('Corrupt result admitted '+name)
    review=ROOT/'calibration/compute-fit-v1/review.json'
    split=build/'split.json'
    reviewed=json.loads(review.read_text())
    if (reviewed.get('schema')!='iris.compute_fitting_independent_review.v1'
            or reviewed.get('pass')is not True
            or any(reviewed.get(k)is not True for k in ('kernel_preparation_window_source_equal',
                  'compiled_table_identity_order_verified','independent_goldens_verified','no_bulk_memory_cases'))
            or reviewed.get('elf_sha256')!=sha(build/'campaign.elf')
            or reviewed.get('corpus_sha256')!=sha(build/'corpus.json')
            or reviewed.get('regions')!=1008 or reviewed.get('cases')!=456
            or reviewed.get('split_sha256')!=sha(split)):
        raise ValueError('Independent exact compute semantic/source/ELF review required')
    for path,digest in reviewed['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('Changed prelaunch review input '+path)
    inputs.update(reviewed['input_sha256'])
    inputs.update({str(review):sha(review),str(split):sha(split)})
    support={str(p):sha(p)for p in [HERE/'build.py',HERE/'run.py',HERE/'validate.py',HERE/'replay.py',
        ROOT/'benchmarks/campaign_buffered/buffered.h',ROOT/'benchmarks/campaign_buffered/replay_v2.py',
        ROOT/'benchmarks/campaign_buffered/validate_priority.py',Path(__file__).resolve(),
        ROOT/'hardware/manifest.json',ROOT/'hardware/dtypes.json',ROOT/'hardware/memory-paths.json']}
    inputs.update(support)
    qualification={'schema':'iris.compute_fitting_qualification.v1','status':'passed','pass':True,
        'functional_runs':runs,'negative_controls':guards,'support_source_sha256':support,
        'independent_prelaunch_review_sha256':sha(review),'frozen_split_sha256':sha(split),
        'elf_sha256':sha(build/'campaign.elf'),'build_sha256':sha(build/'build.json'),
        'corpus_sha256':sha(build/'corpus.json'),'input_sha256':inputs,
        'hardware_contacted':False,'old_campaign_timings_reused':False,
        'source_image_association_verified':False,'timing_accuracy_certified':False}
    (build/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
    ready={'schema':'iris.compute_fitting_ready.v1','status':'ready_for_root_managed_preparation',
        'elf':str(build/'campaign.elf'),'elf_sha256':sha(build/'campaign.elf'),
        'corpus_path':str(build/'corpus.json'),'corpus_sha256':sha(build/'corpus.json'),
        'build_sha256':sha(build/'build.json'),'qualification_sha256':sha(build/'qualification.json'),
        'required_cases':len(corpus['cases']),'required_regions':corpus['expected_region_count'],'trials':corpus['trials'],
        'source_inputs_sha256':{**built['input_sha256'],**inputs},'support_source_sha256':support,
        'readback_layout_sha256':sha(build/'readback-layout.json'),'frozen_split_sha256':sha(split),
        'independent_prelaunch_review_sha256':sha(review),
        'fitting_only':True,'global_heldout':False,'hardware_contacted':False,
        'independent_prelaunch_review':str(review),'frozen_split':str(split),
        'timing_accuracy_certified':False,'source_image_association_verified':False}
    (build/'ready.json').write_text(json.dumps(ready,indent=2)+'\n')
    print(json.dumps({'ready':str(build/'ready.json'),'elf_sha256':ready['elf_sha256'],
        'regions':ready['required_regions'],'functional_seeds':2,'negative_controls':len(guards)}))


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True)
    qualify(p.parse_args().build.resolve())


if __name__=='__main__':main()

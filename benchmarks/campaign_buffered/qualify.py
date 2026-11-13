#!/usr/bin/env python3
"""Freeze two functional schedules and adversarial checks before FPGA setup."""
import argparse
import hashlib
import json
from pathlib import Path
from validate import validate

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


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
    review=ROOT/'calibration/empirical-buffered-v1/review.json'
    split=ROOT/'calibration/empirical-buffered-v1/split.json'
    reviewed=json.loads(review.read_text())
    if (reviewed.get('status')!='source_golden_split_review_passed_functional_and_reference_pending'
            or reviewed.get('golden_values_by_active_hart_independently_checked')!=corpus['expected_region_count']
            or reviewed.get('ELF_symbols_record_stride_and_initial_sentinel_independently_checked')is not True
            or reviewed.get('split_sha256')!=sha(split)):
        raise ValueError('Independent semantic/golden review is required')
    inputs.update({str(review):sha(review),str(split):sha(split)})
    support={str(p):sha(p) for p in [HERE/'build.py',HERE/'main.c',HERE/'buffered.h',HERE/'run.py',
        HERE/'replay.py',HERE/'validate.py',Path(__file__).resolve(),ROOT/'hardware/manifest.json',
        ROOT/'hardware/dtypes.json',ROOT/'hardware/memory-paths.json']}
    inputs.update(support)
    qualification={'schema':'iris.buffered_campaign_qualification.v1','status':'passed','pass':True,
        'functional_runs':runs,'negative_controls':guards,'support_source_sha256':support,
        'independent_prelaunch_review_sha256':sha(review),'frozen_split_sha256':sha(split),
        'elf_sha256':sha(build/'campaign.elf'),'build_sha256':sha(build/'build.json'),
        'corpus_sha256':sha(build/'corpus.json'),'input_sha256':inputs,
        'hardware_contacted':False,'old_campaign_timings_reused':False,
        'source_image_association_verified':False,'timing_accuracy_certified':False}
    (build/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
    ready={'schema':'iris.buffered_campaign_ready.v1','status':'ready_for_root_managed_preparation',
        'elf':str(build/'campaign.elf'),'elf_sha256':sha(build/'campaign.elf'),
        'corpus_path':str(build/'corpus.json'),'corpus_sha256':sha(build/'corpus.json'),
        'build_sha256':sha(build/'build.json'),'qualification_sha256':sha(build/'qualification.json'),
        'required_cases':len(corpus['cases']),'required_regions':corpus['expected_region_count'],'trials':corpus['trials'],
        'source_inputs_sha256':{**built['input_sha256'],**inputs},'support_source_sha256':support,
        'readback_layout_sha256':sha(build/'readback-layout.json'),'frozen_split_sha256':sha(split),
        'independent_prelaunch_review_sha256':sha(review),
        'fitting_only':True,'global_heldout':False,'hardware_contacted':False,
        'timing_accuracy_certified':False,'source_image_association_verified':False}
    (build/'ready.json').write_text(json.dumps(ready,indent=2)+'\n')
    print(json.dumps({'ready':str(build/'ready.json'),'elf_sha256':ready['elf_sha256'],
        'regions':ready['required_regions'],'functional_seeds':2,'negative_controls':len(guards)}))


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True)
    qualify(p.parse_args().build.resolve())


if __name__=='__main__':main()

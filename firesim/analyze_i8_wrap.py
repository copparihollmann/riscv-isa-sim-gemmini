#!/usr/bin/env python3
"""Validate actual emitted compiler kernel/twin evidence from the managed archive."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile

from analyze_campaign import read_archive,repetitions,select_guest_uart
from batch_runner import digest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks/compiler_i8_wrap'))
from validate import validate


def analyze(job,output):
    if output.exists()or job==output or job in output.parents:
        raise ValueError('Fresh analysis directory outside job required')
    output.mkdir(parents=True)
    current=json.loads((job/'run.json').read_text())
    sources=[Path(__file__).resolve(),Path(__file__).with_name('analyze_campaign.py').resolve(),
        Path(__file__).with_name('batch_runner.py').resolve(),ROOT/'benchmarks/compiler_i8_wrap/validate.py',
        ROOT/'benchmarks/compiler_i8_wrap/cases.py']
    report={'schema':'iris.compiler_i8_wrap_archive_analysis.v1','pass':False,'hardware_contacted':False,
        'calibration_usable':False,'timing_certified':False,'full_functional_certified':False,
        'source_image_association_verified':False,'input_sha256':{str(p):digest(p)for p in sources},
        'current_manifest_sha256':digest(job/'run.json'),'archive_verified':False}
    try:
        capture=current['capture'];archive=Path(capture['archive'])
        if capture['status']!='captured'or digest(archive)!=capture['archive_sha256']:
            raise ValueError('Exact quiescent archive required')
        data,identities=read_archive(archive,capture['captured_run_manifest_sha256'])
        manifest=json.loads(data['job/run.json'])
        report.update(archive_verified=True,archive_sha256=capture['archive_sha256'])
        if (manifest['status']!=current['status']or manifest['cleanup_status']!=current['cleanup_status']
                or manifest['campaign_role']!='compiler_i8_wrapping_functional'
                or manifest['require_goldens']is not True or manifest['require_regions']is not True):
            raise ValueError('Archived outcome or numerical contract mismatch')
        frozen_analyzer=manifest['input_sha256'][str(sources[0])]
        if frozen_analyzer not in identities.values():
            raise ValueError('Original prelaunch analyzer bytes missing from archive')
        report['analysis_identity']={'prelaunch_analyzer_sha256':frozen_analyzer,
            'executed_analyzer_sha256':digest(sources[0]),
            'post_run_analyzer_changed':frozen_analyzer!=digest(sources[0]),
            'note':'Tool identity repair may follow collection; exact validator/corpus/runner and every archived measurement remain strictly bound.'}
        for path in sources[1:]:
            expected=manifest['runner_sha256']if path.name=='batch_runner.py'else manifest['input_sha256'].get(str(path))
            if expected!=digest(path)or digest(path)not in identities.values():
                raise ValueError('Archived analysis/corpus source mismatch: '+str(path))
        if identities['job/corpus.json']!=manifest['corpus_sha256']:
            raise ValueError('Archived independent corpus mismatch')
        corpus=json.loads(data['job/corpus.json'])
        elf_name='job/manager/workloads/iris-batch/batch.elf'
        if identities.get(elf_name)!=manifest['elf_sha256']:
            raise ValueError('Archived actual ELF binding mismatch')
        with tarfile.open(archive,'r:gz')as stream:elf=stream.extractfile(elf_name).read()
        if hashlib.sha256(elf).hexdigest()!=manifest['elf_sha256']:
            raise ValueError('Archived ELF changed during extraction')
        (output/'observed.elf').write_bytes(elf)
        member,report['guest_uart']=select_guest_uart(data,identities)
        uart=data[member].decode('utf-8',errors='strict')
        (output/'uartlog').write_bytes(data[member]);(output/'corpus.json').write_bytes(data['job/corpus.json'])
        report['guest_proof']=validate(uart,corpus,'combined')
        report['guest_proof']['counter_policy']='Actual FPGA mcycle/minstret observations; instrumented functional corpus, not admitted calibration or model predictions.'
        report['repetitions']=repetitions(uart,3)
        report['lifecycle']=[{k:row.get(k)for k in
            ('task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out')}for row in manifest['commands']]
        if ([(r['task'],r['status'])for r in manifest['commands']]!=[
                ('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')]
                or current['status']!='completed_uncertified'or current['cleanup_status']!='passed'
                or current.get('error')is not None or current.get('cleanup_error')is not None):
            raise ValueError('Complete successful managed lifecycle required')
        if digest(archive)!=capture['archive_sha256']:
            raise ValueError('Archive changed during analysis')
        if any(digest(name)!=expected for name,expected in report['input_sha256'].items()):
            raise ValueError('Analysis input changed')
        report['pass']=True
        report['qualification']='Actual emitted VME/scalar-twin numerical corpus passed on selected FPGA image with all3harts active; source/image equivalence, complete compiler/Zephyr certification and calibrated timing remain unproven.'
    except(OSError,ValueError,KeyError,TypeError,UnicodeError,tarfile.TarError)as error:
        report['error']=str(error)
    report['artifact_sha256']={p.name:digest(p)for p in output.iterdir()if p.is_file()}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k)for k in ('pass','archive_verified','guest_proof','error')}))
    return 0 if report['pass']else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();raise SystemExit(analyze(a.job.resolve(),a.output.resolve()))

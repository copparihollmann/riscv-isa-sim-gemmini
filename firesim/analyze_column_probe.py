#!/usr/bin/env python3
"""Archive-bound row validation and explicitly nonprescriptive column classification."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile

from analyze_campaign import read_archive, repetitions, select_guest_uart
from batch_runner import digest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks/vme_column_probe'))
from console_validate import validate


def analyze(job,output):
    if output.exists() or job==output or job in output.parents:
        raise ValueError('Fresh analysis directory outside job required')
    output.mkdir(parents=True)
    current=json.loads((job/'run.json').read_text())
    sources=[Path(__file__).resolve(),Path(__file__).with_name('analyze_campaign.py').resolve(),
        Path(__file__).with_name('batch_runner.py').resolve(),
        ROOT/'benchmarks/vme_column_probe/console_validate.py',
        ROOT/'benchmarks/vme_column_probe/validate.py',ROOT/'benchmarks/vme_column_probe/cases.py']
    report={'schema':'iris.vme_column_archive_analysis.v1','pass':False,
        'hardware_contacted_by_analysis':False,'calibration_usable':False,
        'timing_certified':False,'full_functional_certified':False,
        'source_image_association_verified':False,'column_golden_assumed':False,
        'current_manifest_sha256':digest(job/'run.json'),
        'input_sha256':{str(p):digest(p) for p in sources},'archive_verified':False}
    try:
        capture=current['capture'];archive=Path(capture['archive'])
        if capture['status']!='captured' or digest(archive)!=capture['archive_sha256']:
            raise ValueError('Exact quiescent archive required')
        data,identities=read_archive(archive,capture['captured_run_manifest_sha256'])
        manifest=json.loads(data['job/run.json'])
        report.update(archive_verified=True,archive_sha256=capture['archive_sha256'])
        if (manifest['status']!=current['status'] or manifest['cleanup_status']!=current['cleanup_status']
                or manifest['campaign_role']!='vme_column_observation_diagnostic'
                or manifest['require_goldens'] is not True or manifest['require_regions'] is not True
                or manifest.get('unknown_column_outcome_is_observation_not_golden') is not True
                or manifest.get('native_full_positive_execution_claimed') is not False):
            raise ValueError('Archived outcome or explicitly observational contract mismatch')
        for path in sources[3:]:
            if digest(path)!=manifest['input_sha256'].get(str(path)) or digest(path) not in identities.values():
                raise ValueError('Archived independent validation source mismatch')
        if identities['job/corpus.json']!=manifest['corpus_sha256']:
            raise ValueError('Archived corpus binding mismatch')
        elf_name='job/manager/workloads/iris-batch/batch.elf'
        if identities.get(elf_name)!=manifest['elf_sha256']:
            raise ValueError('Actual archived ELF mismatch')
        with tarfile.open(archive,'r:gz') as stream:
            elf=stream.extractfile(elf_name).read()
        if hashlib.sha256(elf).hexdigest()!=manifest['elf_sha256']:
            raise ValueError('ELF changed during extraction')
        elf_path=output/'observed.elf';elf_path.write_bytes(elf)
        member,report['guest_uart']=select_guest_uart(data,identities)
        text=data[member].decode('utf-8',errors='strict')
        (output/'uartlog').write_bytes(data[member])
        (output/'corpus.json').write_bytes(data['job/corpus.json'])
        proof=validate(text,json.loads(data['job/corpus.json']),elf_path)
        frames=proof.pop('frames')
        # Do not publish reconstructed row goldens as observed row words.
        controls,observations=[],[]
        for row in frames:
            if row['kind']==1:
                observations.append(row)
            else:
                row['expected_row_words']=row.pop('words')
                controls.append(row)
        (output/'column-observations.json').write_text(json.dumps(observations,indent=2)+'\n')
        (output/'row-controls.json').write_text(json.dumps(controls,indent=2)+'\n')
        report['guest_proof']=proof
        report['row_repetitions']=repetitions(text,3)
        report['lifecycle']=[{k:r.get(k) for k in ('task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out')}
                             for r in manifest['commands']]
        if ([(r['task'],r['status']) for r in manifest['commands']]!=[
                ('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')]
                or current['status']!='completed_uncertified' or current['cleanup_status']!='passed'
                or current.get('error') is not None or current.get('cleanup_error') is not None):
            raise ValueError('Full successful four-phase lifecycle and owned cleanup required')
        if digest(archive)!=capture['archive_sha256'] or any(digest(p)!=h for p,h in report['input_sha256'].items()):
            raise ValueError('Analysis inputs changed')
        report['pass']=True
        report['qualification']='Known row checksum controls and raw column classifications only; no assumed correct-column or illegal-column semantics, no full source/image/functional/timing certificate.'
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,tarfile.TarError) as error:
        report['error']=str(error)
    report['artifact_sha256']={p.name:digest(p) for p in output.iterdir() if p.is_file()}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('pass','archive_verified','guest_proof','error')}))
    return 0 if report['pass'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    raise SystemExit(analyze(a.job.resolve(),a.output.resolve()))

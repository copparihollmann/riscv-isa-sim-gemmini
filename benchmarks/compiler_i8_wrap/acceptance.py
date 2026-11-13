#!/usr/bin/env python3
"""Bind actual combined functional runs and reject corrupted numerical evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from validate import validate
from cases import checksum


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(build, gates, noop_build, noop_gate, output):
    output.mkdir(parents=True, exist_ok=False)
    elf = build/'combined.elf'
    built = json.loads((build/'build.json').read_text())
    supplied = json.loads((build/'corpus.json').read_text())
    if (digest(elf) != built['binaries']['combined']['sha256']
            or built.get('deliberate_noop_negative_control') is not False):
        raise ValueError('Combined compiler kernel/twin ELF changed')
    paths = [Path(__file__), Path(__file__).with_name('validate.py'),
             Path(__file__).with_name('cases.py'), build/'build.json', build/'corpus.json', elf]
    inputs = dict(built['input_sha256'])
    inputs.update({str(p.resolve()):digest(p) for p in paths})
    reports = []
    for gate in gates:
        report = json.loads((gate/'report.json').read_text())
        if (report.get('pass') is not True or report.get('variant') != 'combined'
                or report['elf_sha256'] != digest(elf)
                or report.get('hardware_contacted') is not False):
            raise ValueError('Exact actual combined functional gate required')
        for name, expected in report['input_sha256'].items():
            if digest(name) != expected:
                raise ValueError('Functional gate input changed: '+name)
        for name in ('stdout', 'stderr'):
            if digest(gate/name) != report[name+'_sha256']:
                raise ValueError('Functional transcript changed')
        proof = validate((gate/'stdout').read_text(), supplied, 'combined')
        if proof != report['proof']:
            raise ValueError('Independent functional proof changed')
        reports.append({'seed':report['seed'], 'report_sha256':digest(gate/'report.json'),
                        'elf_sha256':digest(elf), 'proof':proof})
        inputs.update(report['input_sha256'])
        inputs.update({str((gate/name).resolve()):digest(gate/name)
                       for name in ('report.json', 'stdout', 'stderr')})
    if len(reports) != 2 or {r['seed'] for r in reports} != {0,17}:
        raise ValueError('Both actual independent scheduling seeds required')
    negative_build=json.loads((noop_build/'build.json').read_text())
    negative_gate=json.loads((noop_gate/'report.json').read_text())
    if (negative_build.get('deliberate_noop_negative_control')is not True
            or negative_build['input_sha256']!=built['input_sha256']
            or negative_build['kernel_sha256']!=built['kernel_sha256']
            or negative_build['corpus_sha256']!=built['corpus_sha256']
            or negative_gate.get('pass')is not False or negative_gate.get('variant')!='combined'
            or negative_gate.get('returncode')!=1 or negative_gate.get('timed_out')is not False
            or negative_gate['elf_sha256']!=digest(noop_build/'combined.elf')
            or negative_gate['native_sha256']!=json.loads((gates[0]/'report.json').read_text())['native_sha256']):
        raise ValueError('Exact deliberate no-op must fail without timeout on the same native model')
    for name in ('stdout','stderr'):
        if digest(noop_gate/name)!=negative_gate[name+'_sha256']:
            raise ValueError('Negative execution transcript changed')
    negative_text=(noop_gate/'stdout').read_text()
    negative_rows=[json.loads(line.split(' ',1)[1])for line in negative_text.splitlines()if line.startswith('IRIS_REGION ')]
    negative_done=[json.loads(line.split(' ',1)[1])for line in negative_text.splitlines()if line.startswith('IRIS_BATCH_DONE ')]
    order=[(case,h,v,t)for t in range(3)for v in ('vme','twin')for case in supplied['cases']for h in range(3)]
    failed_total=0
    if len(negative_rows)!=len(order)or 'IRIS_FATAL 'in negative_text:
        raise ValueError('Complete numerical no-op failure, rather than a trap or truncated run, required')
    for row,(case,hart,variant,trial)in zip(negative_rows,order):
        parent=case['case_id']+'.variant-'+variant
        failed=case['m']*case['n']if hart<2 else 0
        expected=checksum([word^0xffffffff for word in case['expected_words'][str(hart)]])if hart<2 else case['expected_checksums']['2']
        if (row.get('case_id')!=parent+'.trial'+str(trial)or row.get('parent_case_id')!=parent
                or type(row.get('hart'))is not int or row['hart']!=hart
                or row.get('variant')!=variant or type(row.get('trial_id'))is not int or row['trial_id']!=trial
                or type(row.get('failed_words'))is not int or row['failed_words']!=failed
                or row.get('pass')is not(hart==2)or row['checksum']!=expected
                or row['expected_checksum']!=case['expected_checksums'][str(hart)]):
            raise ValueError('Every skipped compute output must retain poison and fail, while hart2 producer passes')
        failed_total+=failed
    if negative_done!=[{'failed':failed_total,'regions':126}]or failed_total!=63984:
        raise ValueError('Exact full no-op output failure count required')
    inputs.update(negative_gate['input_sha256'])
    inputs.update({str(p.resolve()):digest(p)for p in [noop_build/'build.json',noop_build/'combined.elf',
        noop_gate/'report.json',noop_gate/'stdout',noop_gate/'stderr']})
    text = (gates[0]/'stdout').read_text()
    lines = text.splitlines()
    first = next(i for i,s in enumerate(lines) if s.startswith('IRIS_REGION '))
    row = json.loads(lines[first].split(' ',1)[1])
    bad_rows = [('checksum',row['checksum']^1), ('expected_checksum',row['expected_checksum']^1),
                ('failed_words',1), ('pass',False), ('variant','twin'), ('hart',True),
                ('trial_id',True), ('trial_id_wrong',99), ('parent_case_id','unowned'),
                ('case_id','unowned'), ('suite','foreign'), ('end_cycle',0), ('instret_delta',0)]
    mutations = []
    for label,value in bad_rows:
        field = 'trial_id' if label == 'trial_id_wrong' else label
        changed = dict(row); changed[field] = value
        modified = list(lines); modified[first] = 'IRIS_REGION '+json.dumps(changed)
        mutations.append((label,'\n'.join(modified)+'\n'))
    mutations.extend([
        ('missing_region','\n'.join(lines[:first]+lines[first+1:])+'\n'),
        ('duplicate_region',text+lines[first]+'\n'),
        ('fatal',text+'IRIS_FATAL {}\n'),
        ('missing_done','\n'.join(s for s in lines if not s.startswith('IRIS_BATCH_DONE '))+'\n'),
        ('failed_done','\n'.join('IRIS_BATCH_DONE {"failed":1,"regions":126}'
            if s.startswith('IRIS_BATCH_DONE ') else s for s in lines)+'\n'),
        ('boolean_done','\n'.join('IRIS_BATCH_DONE {"failed":false,"regions":126}'
            if s.startswith('IRIS_BATCH_DONE ') else s for s in lines)+'\n')])
    results = []
    for label,modified in mutations:
        try:
            validate(modified,supplied,'combined')
        except (ValueError,KeyError,TypeError) as error:
            reason = str(error)
        else:
            raise ValueError('Corrupted transcript admitted: '+label)
        path = output/(label+'.stdout'); path.write_text(modified)
        results.append({'case':label,'rejected':True,'reason':reason,'transcript_sha256':digest(path)})
    snapshots=output/'inputs'; snapshots.mkdir()
    for name,expected in inputs.items():
        if digest(name) != expected:
            raise ValueError('Acceptance source changed: '+name)
        if not (snapshots/expected).exists():
            shutil.copyfile(name,snapshots/expected)
        if digest(snapshots/expected) != expected:
            raise ValueError('Snapshot mismatch')
    report = {'schema':'iris.compiler_i8_wrap_acceptance.v1','pass':True,
              'variant':'combined','elf_sha256':digest(elf),'gates':reports,
              'negative_controls':results,'input_sha256':inputs,'hardware_contacted':False,
              'fresh_output_noop_control':{'pass':True,'actual_executed_negative':True,
                  'elf_sha256':digest(noop_build/'combined.elf'),'gate_report_sha256':digest(noop_gate/'report.json'),
                  'regions':126,'failed_compute_words':failed_total,'hart2_producer_passed':True,
                  'every_compute_word_retained_independent_poison':True},
              'calibration_usable':False,'full_functional_certified':False}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':True,'actual_seeded_gates':2,'negative_controls':len(results)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--gate',type=Path,action='append',required=True)
    p.add_argument('--noop-build',type=Path,required=True)
    p.add_argument('--noop-gate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.build.resolve(),[v.resolve() for v in a.gate],
        a.noop_build.resolve(),a.noop_gate.resolve(),a.output.resolve())

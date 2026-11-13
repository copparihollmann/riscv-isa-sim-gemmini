#!/usr/bin/env python3
"""Replay archived evidence and prove the host validator rejects corrupt consoles."""
import argparse
import json
from pathlib import Path
from build import sha, ROOT
from run import validator


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);a=p.parse_args();out=a.build.resolve()
    build=json.loads((out/'build.json').read_text());run=json.loads((out/'run.json').read_text())
    if sha(out/'build.json')!=run['build_sha256'] or sha(out/'memory-routes.elf')!=run['elf_sha256']:
        raise ValueError('changed build/ELF')
    if build['elf_sha256']!=run['elf_sha256'] or run['exit_status']!=0 or run['functional_checks_passed'] is not True:
        raise ValueError('unsuccessful functional evidence')
    for path,digest in build['input_sha256'].items():
        if sha(Path(path))!=digest or sha(out/'inputs'/digest)!=digest:raise ValueError('changed build input '+path)
    for path,digest in run['input_sha256'].items():
        if sha(out/'inputs'/digest)!=digest:raise ValueError('corrupt archived execution input '+path)
    for ext in ('stdout','stderr'):
        if sha(out/('run.'+ext))!=run[ext+'_sha256']:raise ValueError('changed console '+ext)
    corpus=json.loads((out/'corpus.json').read_text());text=(out/'run.stdout').read_text()
    checked=validator.validate(text,corpus)
    for key,value in checked.items():
        if run.get(key)!=value:raise ValueError('replayed result mismatch '+key)
    lines=text.splitlines();first=next(i for i,line in enumerate(lines) if line.startswith('IRIS_REGION '))
    observed_harts={json.loads(line.split(' ',1)[1])['hart'] for line in lines if line.startswith('IRIS_REGION ')}
    removed_hart=2 if 2 in observed_harts else min(observed_harts)
    corruptions=[lines+[lines[first]], [line for line in lines if not(line.startswith('IRIS_REGION ') and json.loads(line.split(' ',1)[1])['hart']==removed_hart)]]
    for field in ('checksum','expected_checksum'):
        changed=list(lines);row=json.loads(changed[first].split(' ',1)[1]);row[field]^=1
        changed[first]='IRIS_REGION '+json.dumps(row);corruptions.append(changed)
    for changed in corruptions:
        try:validator.validate('\n'.join(changed)+'\n',corpus)
        except ValueError:pass
        else:raise ValueError('corrupted console accepted')
    print(json.dumps({'status':'verified_archived_functional_evidence','cases':checked['cases'],'regions':checked['regions'],
                      'checker_negative_controls':len(corruptions),
                      'live_execution_inputs_match':all(sha(Path(p))==d for p,d in run['input_sha256'].items()),
                      'calibration_usable':False,'timing_certified':False}))


if __name__=='__main__':main()

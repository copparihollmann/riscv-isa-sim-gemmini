#!/usr/bin/env python3
"""Run the unchanged localRTL ELF with a read-only frontend observer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1048576),b''):h.update(data)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--observer',type=Path,required=True);p.add_argument('--probe',type=Path,required=True)
    p.add_argument('--unobserved',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=240);a=p.parse_args()
    observer=json.loads(a.observer.read_text());probe=json.loads(a.probe.read_text());reference=json.loads((a.unobserved/'results.json').read_text())
    out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);binary=Path(observer['binary']);elf=Path(probe['elf'])
    if sha(binary)!=observer['binary_sha256'] or sha(elf)!=probe['elf_sha256'] or reference['elf_sha256']!=probe['elf_sha256'] or observer['probe_elf_sha256']!=probe['elf_sha256']:
        raise ValueError('observer/probe/reference identities differ')
    inputs={**observer['input_sha256'],**probe['input_sha256'],str(a.observer.resolve()):sha(a.observer),str(a.probe.resolve()):sha(a.probe),
            str(a.unobserved.resolve()/'results.json'):sha(a.unobserved/'results.json'),str(a.unobserved.resolve()/'signature'):sha(a.unobserved/'signature'),
            str(Path(__file__).resolve()):sha(__file__),str(binary):sha(binary),str(elf):sha(elf)}
    for path,digest in inputs.items():
        if sha(path)!=digest:raise ValueError('changed actual source/build input: '+path)
    ldd=subprocess.check_output(['ldd',binary],text=True);(out/'ldd.txt').write_text(ldd)
    if 'not found' in ldd:raise ValueError('missing observer library')
    for path in re.findall(r'(?:=>\s*)?(/[^\s]+)',ldd):
        if Path(path).is_file():inputs[path]=sha(path)
    argv=list(reference['argv']);argv[0]=str(binary);argv=['+signature='+str(out/'signature') if x.startswith('+signature=') else x for x in argv]
    if argv[-1]!=str(elf):raise ValueError('unobserved launch ELF changed')
    record=dict(schema='iris.frontend_observer.run.v1',argv=argv,input_sha256=inputs,hardware_contacted=False,rtl_design_changed=False,
                binary_sha256=sha(binary),elf_sha256=sha(elf),calibrated=False,ethan_image_association_verified=False)
    started=time.monotonic()
    with (out/'stdout').open('w') as stdout,(out/'stderr').open('w') as stderr:
        try:r=subprocess.run(argv,cwd=out,stdout=stdout,stderr=stderr,timeout=a.timeout);record.update(exit_status=r.returncode,timed_out=False)
        except subprocess.TimeoutExpired:record.update(exit_status=None,timed_out=True)
    record['host_seconds']=time.monotonic()-started;count=0
    with (out/'phase.jsonl').open('w') as dest,(out/'stderr').open() as source:
        for line in source:
            if line.startswith('FRONT_PHASE '):json.loads(line.split(' ',1)[1]);dest.write(line.split(' ',1)[1]);count+=1
    changed=[path for path,digest in inputs.items() if sha(path)!=digest];signature=out/'signature'
    matches=signature.exists() and sha(signature)==sha(a.unobserved/'signature')
    record.update(status='passed_readonly_frontend_signature_requires_analysis' if record['exit_status']==0 and matches and not changed else 'failed',
                  phase_rows=count,changed_inputs=changed,full448B_signature_matches_unobserved=matches,
                  signature_sha256=sha(signature) if signature.exists() else None,original_signature_sha256=sha(a.unobserved/'signature'))
    (out/'inputs').mkdir()
    for path,digest in inputs.items():
        if Path(path).suffix in ('.a','.o'):continue
        target=out/'inputs'/digest
        if not target.exists():shutil.copy2(path,target)
    record['reused_compiled_object_inputs']={path:digest for path,digest in inputs.items() if Path(path).suffix in ('.a','.o')}
    record['base_rtl_source_capsule']={'path':str(ROOT/'build/rtl-reference-hpm-rdtime-final/reference.json'),'sha256':sha(ROOT/'build/rtl-reference-hpm-rdtime-final/reference.json')}
    record['artifact_sha256']={str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file()}
    (out/'results.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({key:record[key] for key in ('status','host_seconds','phase_rows','full448B_signature_matches_unobserved')}))
    if record['status']=='failed':raise SystemExit(1)


if __name__=='__main__':main()

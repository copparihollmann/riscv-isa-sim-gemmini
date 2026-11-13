#!/usr/bin/env python3
"""Bounded local RTL phase observation; no FPGA or source counter changes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--observer',type=Path,required=True)
    p.add_argument('--probe',type=Path,default=ROOT/'build/scalar-rtl-probe-v1/build.json')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=240)
    a=p.parse_args();observer=a.observer.resolve();base=json.loads(observer.read_text());probe=json.loads(a.probe.read_text())
    binary=Path(base['binary']);elf=Path(probe['elf']);out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    if sha(binary)!=base['binary_sha256'] or sha(elf)!=probe['elf_sha256']:raise ValueError('changed binary/ELF')
    for path,digest in base['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('changed observer source input '+path)
    for path,digest in probe['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('changed guest build input '+path)
    inputs={**base['input_sha256'],**probe['input_sha256'],str(observer):sha(observer),
            str(a.probe.resolve()):sha(a.probe),str(binary):sha(binary),str(elf):sha(elf),str(Path(__file__).resolve()):sha(Path(__file__))}
    ldd=subprocess.check_output(['ldd',binary],text=True);(out/'ldd.txt').write_text(ldd)
    if 'not found' in ldd:raise ValueError('unresolved runtime library')
    for path in re.findall(r'(?:=>\s*)?(/[^\s]+)',ldd):
        if Path(path).is_file():inputs[path]=sha(path)
    signature=out/'signature'
    argv=[str(binary),'+permissive','+verilator+seed+1','+verilator+rand+reset+2','+loadmem=1','+max-cycles=400000',
          '+init_write=0x2000004:0x1','+init_write=0x2000008:0x1','+signature='+str(signature),
          '+signature-granularity=8','+permissive-off',str(elf)]
    record={'schema':'iris.whole_cpu_csr_phase.v1','argv':argv,'input_sha256':inputs,'hardware_contacted':False,
            'rtl_design_changed':False,'counter_policy_changed':False,'source_build_association_verified':False,
            'ethan_image_association_verified':False,'timing_calibrated':False,'full_functional_certification':False}
    started=time.monotonic()
    with (out/'stdout').open('w') as stdout,(out/'stderr').open('w') as stderr:
        try:r=subprocess.run(argv,cwd=out,stdout=stdout,stderr=stderr,timeout=a.timeout);record.update(exit_status=r.returncode,timed_out=False)
        except subprocess.TimeoutExpired:record.update(exit_status=None,timed_out=True)
    record['host_seconds']=time.monotonic()-started
    rows=[]
    for line in (out/'stderr').read_text().splitlines():
        if line.startswith('CSR_PHASE '):rows.append(json.loads(line.split(' ',1)[1]))
    (out/'phase.json').write_text(json.dumps(rows,indent=2)+'\n')
    if signature.exists():
        old=ROOT/'build/scalar-rtl-reference-v1/signature'
        record.update(signature_sha256=sha(signature),original_signature_sha256=sha(old),
                      full_signature_matches_unobserved_run=sha(signature)==sha(old))
    changed=[path for path,digest in inputs.items() if sha(path)!=digest]
    record.update(status='completed_phase_observation_requires_analysis' if record['exit_status']==0 and not changed else 'failed',
                  changed_inputs=changed,phase_rows=len(rows))
    # Full compiled-source closure is already frozen in the named base capsule.
    capsule=ROOT/'build/rtl-reference-hpm-rdtime-final/reference.json'
    record['base_rtl_source_capsule']={'path':str(capsule),'sha256':sha(capsule)}
    (out/'inputs').mkdir()
    for path,digest in inputs.items():
        if Path(path).suffix in ('.a','.o'):continue
        target=out/'inputs'/digest
        if not target.exists():shutil.copyfile(path,target)
    record['reused_compiled_object_inputs']={path:digest for path,digest in inputs.items() if Path(path).suffix in ('.a','.o')}
    record['artifact_sha256']={str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file()}
    (out/'results.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({key:record[key] for key in ['status','host_seconds','phase_rows','exit_status']}))
    if record['status']=='failed':raise SystemExit(1)


if __name__=='__main__':main()

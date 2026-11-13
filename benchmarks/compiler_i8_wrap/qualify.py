#!/usr/bin/env python3
"""Execute emitted compiler kernels and their twin on the exact functional SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from validate import validate

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from spike.run_functional import command


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(build,output,variant,seed):
    built=json.loads((build/'build.json').read_text());elf=build/(variant+'.elf')
    if built.get('status')!='built' or digest(elf)!=built['binaries'][variant]['sha256'] or digest(build/'corpus.json')!=built['corpus_sha256']:
        raise ValueError('Exact successful compiled kernel build required')
    for name,expected in built['input_sha256'].items():
        if digest(name)!=expected:raise ValueError('Build source changed: '+name)
    output.mkdir(parents=True,exist_ok=False)
    native=(ROOT/'spike/bin/spike-iris-functional').resolve();uart=(ROOT/'spike/bin/libsifive_uart.so').resolve()
    rom,dtb=ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'
    argv=command(native,elf)
    argv=[('--extlib='+str(uart))if word.startswith('--extlib=')else word for word in argv]
    argv=argv[:-1]+['--iris-bootrom='+str(rom),'--dtb='+str(dtb),'--iris-schedule-seed='+str(seed)]+argv[-1:]
    paths=[Path(__file__),Path(__file__).with_name('validate.py'),Path(__file__).with_name('cases.py'),
           build/'build.json',build/'corpus.json',elf,native,uart,rom,dtb,ROOT/'spike/run_functional.py']
    identities=dict(built['input_sha256']);identities.update({str(p.resolve()):digest(p)for p in paths})
    snapshots=output/'inputs';snapshots.mkdir()
    for name,expected in identities.items():
        if not(snapshots/expected).exists():shutil.copyfile(name,snapshots/expected)
    started=time.monotonic()
    with(output/'stdout').open('wb')as stdout,(output/'stderr').open('wb')as stderr:
        try:
            result=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=300,
                env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']))
            code=result.returncode;timed_out=False
        except subprocess.TimeoutExpired:
            code=None;timed_out=True
    record={'schema':'iris.compiler_i8_wrap_functional_gate.v1','pass':False,'variant':variant,'seed':seed,
            'argv':argv,'returncode':code,'timed_out':timed_out,'host_seconds':time.monotonic()-started,
            'elf_sha256':digest(elf),'native_sha256':digest(native),'uart_sha256':digest(uart),
            'input_sha256':identities,'stdout_sha256':digest(output/'stdout'),'stderr_sha256':digest(output/'stderr'),
            'corpus_sha256':digest(build/'corpus.json'),'hardware_contacted':False,'timing_certified':False}
    try:
        if code!=0 or timed_out:raise ValueError('Guest failed or timed out')
        record['proof']=validate((output/'stdout').read_text(),json.loads((build/'corpus.json').read_text()),variant)
        if any(digest(name)!=expected for name,expected in identities.items()):raise ValueError('Source changed during execution')
        record['pass']=True
    except(ValueError,KeyError,TypeError,UnicodeError)as error:record['error']=str(error)
    (output/'report.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:record.get(k)for k in ('pass','variant','seed','proof','error','host_seconds')}))
    return 0 if record['pass']else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--variant',choices=['vme','twin','combined'],required=True)
    p.add_argument('--seed',type=int,required=True);a=p.parse_args()
    raise SystemExit(run(a.build.resolve(),a.output.resolve(),a.variant,a.seed))

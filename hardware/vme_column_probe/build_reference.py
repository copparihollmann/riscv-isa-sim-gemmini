#!/usr/bin/env python3
"""Link the frozen preload host harness to unchanged qualified whole-RTL objects."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
CAP = ROOT / 'build/saturn-timing-component-v1-final'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024), b''):
            h.update(data)
    return h.hexdigest()


def archived(path):
    try:
        saved = CAP / Path(path).relative_to(ROOT)
        if saved.exists():
            return str(saved)
    except ValueError:
        pass
    return path


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    receipt_path = CAP / 'build/saturn-timing-rtl-v1/build.json'
    old = json.loads(receipt_path.read_text())
    source = CAP / 'build/opu-sequencer-component-v2-final/board/rtl-loader/main.cc'
    if not source.exists():
        source = ROOT / 'build/opu-sequencer-component-v2-final/board/rtl-loader/main.cc'
    local_source = output / 'main.cc'
    shutil.copyfile(source, local_source)
    if 'iris_rtl_load_write' not in local_source.read_text() or 'iris_rtl_load_read' not in local_source.read_text():
        raise ValueError('Qualified native-RAM preload harness required')
    compile_argv = [archived(x[2:]) if x.startswith('-I') else archived(x) for x in old['compile_argv']]
    compile_argv = [('-I'+new) if old_arg.startswith('-I') else new for old_arg,new in zip(old['compile_argv'],compile_argv)]
    compile_argv[compile_argv.index('-c')+1] = str(local_source)
    compile_argv[compile_argv.index('-o')+1] = str(output / 'main.o')
    compile_argv += ['-MD', '-MF', str(output / 'main.d'), '-save-temps=obj']
    link_argv = [archived(x) for x in old['link_argv']]
    link_argv[1] = str(output / 'main.o')
    link_argv[link_argv.index('-o')+1] = str(output / 'simulator-preload')
    started = time.monotonic()
    for name, argv in [('compile', compile_argv), ('link', link_argv)]:
        result = subprocess.run(argv, capture_output=True)
        (output / (name+'.stdout')).write_bytes(result.stdout)
        (output / (name+'.stderr')).write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError('Reference host build failed: '+name)
    sources = [Path(__file__).resolve(), source, receipt_path, CAP/'report.json', local_source,
               Path(compile_argv[0]).resolve(), Path(link_argv[0]).resolve()]
    for path, expected in old['input_sha256'].items():
        actual = Path(archived(path))
        if digest(actual) != expected:
            raise ValueError('Qualified whole-RTL input changed: '+str(actual))
        sources.append(actual)
    for token in (output/'main.d').read_text().replace('\\\n',' ').split(':',1)[1].split():
        path = Path(token)
        if path.is_file():
            sources.append(path.resolve())
    for token in link_argv:
        if token.endswith(('.o','.a')) and Path(token).is_file():
            sources.append(Path(token))
    for tool in ('cc1plus','as','collect2','ld'):
        name = subprocess.check_output([compile_argv[0], '-print-prog-name='+tool], text=True).strip()
        sources.append(Path(name if '/' in name else shutil.which(name)).resolve())
    binary = output/'simulator-preload'
    ldd = subprocess.check_output(['ldd',str(binary)],text=True)
    (output/'ldd.txt').write_text(ldd)
    if 'not found' in ldd:
        raise ValueError('Missing reference dynamic library')
    for token in re.findall(r'(?:=>\s*)?(/[^\s]+)',ldd):
        if Path(token).is_file():
            sources.append(Path(token))
    inputs = {str(p):digest(p) for p in sources}
    snapshots = output/'inputs'
    snapshots.mkdir()
    for name,expected in inputs.items():
        if not (snapshots/expected).exists():
            shutil.copyfile(name,snapshots/expected)
        if digest(snapshots/expected)!=expected:
            raise ValueError('Reference snapshot changed')
    record = {'schema':'iris.vme_column_preload_whole_reference.v1','status':'built',
        'compile_argv':compile_argv,'link_argv':link_argv,'input_sha256':inputs,
        'binary_sha256':digest(binary),'host_seconds':time.monotonic()-started,
        'source_fir_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4',
        'RTL_logic_modified':False,'source_Model_archive_unchanged':True,
        'preload_scope':'Explicit ELF load/signature access to native saved-FIR backing RAM; not live internal CPU/cache/tile state injection.',
        'hardware_contacted':False,'source_image_association_verified':False,'calibration_usable':False}
    (output/'build.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'status':'built','binary_sha256':record['binary_sha256'],'host_seconds':record['host_seconds']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    build(a.output.resolve())

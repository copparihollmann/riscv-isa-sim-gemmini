#!/usr/bin/env python3
"""Prepare a complete isolated primary-publication candidate; never switch it."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    root=out/'root';root.mkdir();spike=root/'spike'
    shutil.copytree(ROOT/'spike',spike,ignore=shutil.ignore_patterns('build','bin','include','__pycache__'))
    legacy=spike/'historical-5e6-dispatch';legacy.mkdir()
    for name in ['build.py','provider.py','provenance.json','iris.patch','run_functional.py','run_selftest.sh','run_native_selftest.sh','run_csr_selftest.sh']:
        shutil.copyfile(ROOT/'spike'/name,legacy/name)
    for name in ['build.py','provider.py','selftest.py']:shutil.copyfile(HERE/name,spike/name)
    for name,kind in [('run_selftest.sh','guests'),('run_native_selftest.sh','handlers'),('run_csr_selftest.sh','handlers')]:
        (spike/name).write_text('#!/usr/bin/env bash\nset -euo pipefail\nspike_dir=$(cd -- "$(dirname -- "$0")" && pwd)\nexec "${PYTHON:-python3}" "$spike_dir/selftest.py" --kind '+kind+' "$@"\n');(spike/name).chmod(0o755)
    helper=spike/'run_functional.py';text=helper.read_text()
    old="if __name__=='__main__':main()"
    if text.count(old)!=1:raise ValueError('Changed old functional entrypoint')
    text=text.replace(old,"if __name__=='__main__':\n    import sys\n    os.execv(sys.executable,[sys.executable,str(HERE/'selftest.py'),'--kind','guests',*sys.argv[1:]])")
    helper.write_text(text)
    releases=spike/'releases';releases.mkdir();release=releases/'combined-359-sdk4'
    shutil.copytree(ROOT/'build/combined-sdk4-package-v2',release,ignore=shutil.ignore_patterns('__pycache__'))
    (spike/'current').symlink_to('releases/combined-359-sdk4',target_is_directory=True)
    for name,target in [('provenance.json','current/provenance.json'),('iris.patch','current/iris.patch')]:
        (spike/name).unlink();(spike/name).symlink_to(target)
    (spike/'include').symlink_to('current/sdk',target_is_directory=True)
    (spike/'source').symlink_to('current/source/third_party/riscv-isa-sim-combined',target_is_directory=True)
    bin=spike/'bin';bin.mkdir()
    for name,target in [('spike-iris-functional','../current/bin/spike'),('libsifive_uart.so','../current/bin/libsifive_uart.so'),('spike-iris-launch','../current/launch.py')]:
        (bin/name).symlink_to(target)
    shutil.copy2(ROOT/'spike/bin/spike-zvt-reference',bin/'spike-zvt-reference')
    # Keep existing SDK include/link conventions source-matched to ABI4.
    capsule=json.loads((release/'evidence/combined/manifest.json').read_text());compat=release/'compat-sdk';compat.mkdir()
    for name in ['libriscv.a','libdisasm.a','libsoftfloat.a','libfesvr.a','libfdt.a','libspike_main.a','config.h']:
        entry=capsule['files']['build/spike-combined/'+name];raw=(release/'evidence/combined'/entry['object']).read_bytes()
        data=gzip.decompress(raw)if entry['compression']=='gzip'else raw
        if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('SDK archive mismatch')
        (compat/name).write_bytes(data)
    (compat/'spike').symlink_to('../bin/spike');(compat/'libsifive_uart.so').symlink_to('../bin/libsifive_uart.so')
    (spike/'build').symlink_to('current/compat-sdk',target_is_directory=True)
    # Canonical Git inspection view is separate from the locked portable build
    # snapshot, whose source-file bytes preserve the base symlink's contents.
    source=release/'git-source'
    subprocess.run(['git','clone','--no-checkout','--no-hardlinks',str(ROOT/'third_party/riscv-isa-sim-combined'),str(source)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    subprocess.run(['git','-C',str(source),'checkout','--detach','72958551566a30f19444bd7e354552824e4d0a98'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    subprocess.run(['git','-C',str(source),'apply','--intent-to-add',str(release/'iris.patch')],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    # Normalize the index after a no-checkout clone; retain all working bytes.
    subprocess.run(['git','-C',str(source),'reset','--mixed','72958551566a30f19444bd7e354552824e4d0a98'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    for name in subprocess.check_output(['git','-C',str(source),'ls-files','--others','--exclude-standard','-z']).split(b'\0'):
        if name:subprocess.run(['git','-C',str(source),'add','-N','--',name.decode()],check=True)
    diff=subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD'])
    if hashlib.sha256(diff).hexdigest()!='e33269e90102a8a9137473eb4d6a0c7c276a2553972ab4e668ab62f041a82060':raise ValueError('Publication source git diff differs from combined overlay')
    third=root/'third_party';third.mkdir()
    for path in (ROOT/'third_party').iterdir():
        (third/path.name).symlink_to(path.resolve(),target_is_directory=path.is_dir())
    (third/'riscv-isa-sim-current').symlink_to('../spike/current/git-source',target_is_directory=True)
    for name in ['board','hardware','benchmarks','workloads']:(root/name).symlink_to(ROOT/name,target_is_directory=True)
    shutil.copytree(ROOT/'zephyr',root/'zephyr',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT/'integration/iris-mlir',root/'integration/iris-mlir',ignore=shutil.ignore_patterns('__pycache__'))
    for name in ['manifest.json','README.md']:shutil.copyfile(ROOT/'integration'/name,root/'integration'/name)
    (root/'integration/merlin').mkdir()
    for path in (ROOT/'integration/merlin').iterdir():
        if path.name not in ['src','merlin']:(root/'integration/merlin'/path.name).symlink_to(path.resolve(),target_is_directory=path.is_dir())
    shutil.copytree(ROOT/'integration/merlin/src',root/'integration/merlin/src',ignore=shutil.ignore_patterns('__pycache__'))
    (root/'integration/merlin/merlin/python/merlin/runtime/backends').mkdir(parents=True)
    subprocess.run([sys.executable,str(HERE/'stage_integration.py'),'--root',str(root)],check=True)
    subprocess.run([sys.executable,str(HERE/'finish.py'),'--root',str(root)],check=True)
    report={'schema':'iris.primary_sdk4.publication_candidate.v1','status':'prepared_not_published','root':str(root),
        'source_overlay_sha256':hashlib.sha256(diff).hexdigest(),'base_spike_sha':'72958551566a30f19444bd7e354552824e4d0a98',
        'binary_sha256':sha(bin/'spike-iris-functional'),'uart_sha256':sha(bin/'libsifive_uart.so'),'launcher_sha256':sha(bin/'spike-iris-launch'),
        'source_git_head':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
        'source_view_policy':'Canonical git inspection projection preserves base symlink type; source rebuild uses immutable byte-locked portable snapshot. Editing either requires a new qualified release.',
        'primary_published':False,'hardware_contacted':False,'rtl_certified':False,'timing_certified':False,
        'input_sha256':{str(path):sha(path)for path in HERE.glob('*.py')}}
    (out/'candidate.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'candidate.json')
if __name__=='__main__':main()

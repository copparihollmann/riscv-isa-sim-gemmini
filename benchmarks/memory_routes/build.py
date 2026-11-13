#!/usr/bin/env python3
"""Build source-routed, all-three-hart memory experiments without hardware access."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
from cases import cases, REGIONS

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--select-regex')
    p.add_argument('--compiler',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'))
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    selected=[c for c in cases() if not a.select_regex or re.search(a.select_regex,c['case_id'])]
    if not selected:raise ValueError('empty case selection')
    routes=json.loads((ROOT/'hardware/memory-paths.json').read_text());ids={r['id'] for r in routes['routes']}
    for case in selected:
        if not set(case['source_route_ids'])<=ids:raise ValueError('unsourced memory route')
    records=[]
    for c in selected:
        fields=','.join(str(c[k]) for k in ['stride','spread','n','mask'])
        records.append('{'+json.dumps(c['case_id'])+','+str(c['base'])+'ULL,K_'+c['kind']+','+fields+',{'+','.join(str(v)+'ULL' for v in c['expected_checksums'])+'}}')
    table=out/'cases.inc';table.write_text('static const case_t experiments[]={\n'+',\n'.join(records)+'\n};\n')
    corpus={'schema_version':2,'split_id':'iris-memory-routes-fit-v1','purpose':'identifying fitting suite, independent of held-out timing',
            'cases':selected,'expected_region_count':sum(bin(c['mask']).count('1') for c in selected),'physical_harts':3,
            'memory_paths_sha256':sha(ROOT/'hardware/memory-paths.json'),
            'hardware_manifest_sha256':sha(ROOT/'hardware/manifest.json'),
            'counter_policy':'mcycle/minstret; kernel call, branches, counter reads and fence included; no subtraction',
            'cache_protocol':'initialize each active hart private target window, fence, global barrier; no cache flush or cold/hit assertion',
            'inactive_policy':'WFI with final active hart MSIP wake; early finishers may spin outside own ROI at barrier',
            'bank_policy':'addresses differ at source bank bit6; DRAM bank mapping is NOT inferred from bit6',
            'accounting_policy':'kernel payload bytes exclude preparation/verification/control/stack/cache-line transport',
            'v1_frozen_input_sha256':{str(path.relative_to(ROOT)):sha(path) for path in
                [HERE.parent/'batch.c',HERE.parent/'calibration-corpus.json',HERE.parent/'heldout-corpus.json']},
            'timing_certified':False,'calibrated':False}
    (out/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n')
    common=HERE.parent;compiler=a.compiler.resolve();elf=out/'memory-routes.elf'
    argv=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize',
          '-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-fno-common','-mcmodel=medany',
          '-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections',
          '-DIRIS_HARTS=3','-I'+str(common),'-I'+str(out),'-T',str(common/'link.ld'),str(common/'start.S'),
          str(common/'runtime.c'),str(HERE/'guest.c'),'-lgcc','-o',str(elf)]
    result=subprocess.run(argv,capture_output=True,text=True)
    (out/'build.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('compiler failed; see build.log')
    # Fixed target windows must not overwrite any ELF load segment/BSS/stack.
    raw=elf.read_bytes();phoff=struct.unpack_from('<Q',raw,32)[0];phsize,phnum=struct.unpack_from('<HH',raw,54)
    for i in range(phnum):
        typ,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,phoff+i*phsize)
        if typ!=1:continue
        for name,(base,size) in REGIONS.items():
            if max(base,pa)<min(base+size,pa+memsz):raise ValueError('ELF overlaps benchmark target '+name)
    libgcc=Path(subprocess.check_output([compiler,'-march=rv64gcv_zicsr_zifencei','-mabi=lp64d','-print-libgcc-file-name'],text=True).strip()).resolve()
    inputs=[HERE/'cases.py',HERE/'guest.c',HERE/'build.py',HERE/'run.py',HERE/'verify.py',table,out/'corpus.json',compiler,libgcc,
            *[common/name for name in ['runtime.c','runtime.h','start.S','uart_drain.h','link.ld']],
            ROOT/'hardware/memory-paths.json',ROOT/'hardware/manifest.json',ROOT/'benchmarks/v2/validate.py']
    receipt={'schema_version':1,'argv':argv,'input_sha256':{str(path):sha(path) for path in inputs},
             'elf_sha256':sha(elf),'compiler_version':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
             'executed':False,'timing_certified':False,'cases':len(selected),'regions':corpus['expected_region_count']}
    (out/'inputs').mkdir()
    for path,digest in receipt['input_sha256'].items():
        target=out/'inputs'/digest
        if not target.exists():target.write_bytes(Path(path).read_bytes())
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'elf':str(elf),'cases':len(selected),'regions':corpus['expected_region_count']}))


if __name__=='__main__':main()

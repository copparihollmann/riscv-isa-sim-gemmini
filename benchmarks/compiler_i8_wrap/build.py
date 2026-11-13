#!/usr/bin/env python3
"""Build the actual OOT-emitted kernel and scalar twin with independent wrap goldens."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from cases import corpus

ROOT=Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(output, deliberate_noop=False):
    output.mkdir(parents=True,exist_ok=False)
    os.environ['MERLIN_CHIPYARD_IRIS']='/scratch/eygao/iris-cy'
    from merlin.targetgen.plugins import load_module
    oot=ROOT/'integration/iris-mlir'
    shim=load_module(oot,'vme_shim.py',package_name='iris_i8_wrapping_kernel')
    contract=shim.load_contract('saturn_vme');derived=shim.derive_encodings(contract)
    if not derived.ok:
        raise ValueError('Exact source-derived instruction encodings required')
    (output/'kernel.h').write_text(shim.vme_kernel.emit_kernel(derived.encodings,contract.kernel_spec(),derivation_ok=True))
    data=corpus();(output/'corpus.json').write_text(json.dumps(data,indent=2)+'\n')
    (output/'encodings.json').write_text(json.dumps(derived.to_dict(),indent=2)+'\n')
    maximum=max(max(c['m']*c['k'],c['n']*c['k']) for c in data['cases'])
    include=[f'#define MAX_INPUT {maximum}',f'#define MAX_OUTPUT {max(c["m"]*c["n"] for c in data["cases"])}',
             f'#define MAX_N {max(c["n"] for c in data["cases"])}']
    for i,c in enumerate(data['cases']):
        for h in range(3):
            include.append(f'static const uint32_t golden_{i}_{h}[]={{'+','.join(str(v)+'u' for v in c['expected_words'][str(h)])+'};')
    include.append('static const case_t cases[]={')
    for i,c in enumerate(data['cases']):
        include.append('{'+json.dumps(c['case_id'])+','+','.join(str(c[k]) for k in ('m','n','k','pattern','bias'))
                       +',{'+','.join(f'golden_{i}_{h}' for h in range(3))+'},{'
                       +','.join(str(c['expected_checksums'][str(h)])+'ULL' for h in range(3))+'}},')
    include.append('};');(output/'cases.inc').write_text('\n'.join(include)+'\n')
    (output/'twin_kernel.c').write_text('#include "kernel.h"\n')
    cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
    flags=['-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin',
           '-fno-tree-vectorize','-fno-tree-slp-vectorize','-fno-common','-mcmodel=medany',
           '-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-save-temps=obj',
           '-I'+str(ROOT/'benchmarks'),'-I'+str(output)]
    sources=[Path(__file__).resolve(),Path(__file__).with_name('cases.py'),oot/'vme_kernel.py',oot/'vme_shim.py',
             oot/'source_facts.py',oot/'contracts/matrix_units.yaml',ROOT/'hardware/manifest.json',
             ROOT/'benchmarks/link.ld',cc,Path(sys.executable).resolve()]
    tile_edge,alignment=contract.geometry('IrisConfig')
    commands=[]
    for name,source,extra in [('start',ROOT/'benchmarks/start.S',[]),('runtime',ROOT/'benchmarks/runtime.c',[]),
            ('vme',Path(__file__).with_name('guest.c'),['-DVARIANT_NAME="vme"']),
            ('twin',Path(__file__).with_name('guest.c'),['-DMERLIN_MATRIX_SCALAR_TILE','-DMERLIN_MATRIX_TILE_EDGE='+str(tile_edge),'-DVARIANT_NAME="twin"']),
            ('combined',Path(__file__).with_name('guest.c'),['-DIRIS_COMBINED']),
            ('twin_kernel',output/'twin_kernel.c',['-DMERLIN_MATRIX_SCALAR_TILE','-DMERLIN_MATRIX_TILE_EDGE='+str(tile_edge),
                '-Dmerlin_vme_gemm_i8=merlin_vme_gemm_i8_twin'])]:
        control=['-DIRIS_TEST_SKIP_KERNEL']if deliberate_noop and name in ('vme','twin','combined')else[]
        argv=[str(cc),*flags,*extra,*control,'-MD','-MF',str(output/(name+'.d')),'-c',str(source),'-o',str(output/(name+'.o'))]
        run=subprocess.run(argv,capture_output=True);(output/(name+'.stdout')).write_bytes(run.stdout);(output/(name+'.stderr')).write_bytes(run.stderr)
        commands.append({'argv':argv,'exit_status':run.returncode})
        if run.returncode:
            raise RuntimeError('Compilation failed: '+name)
        deps=(output/(name+'.d')).read_text().replace('\\\n',' ').split(':',1)[1]
        sources.extend(Path(p) for p in shlex.split(deps))
    binaries={}
    for variant in ('vme','twin','combined'):
        elf=output/(variant+'.elf')
        argv=[str(cc),*flags,'-nostdlib','-static','-Wl,--build-id=none','-Wl,-Map,'+str(output/(variant+'.map')),
              '-T',str(ROOT/'benchmarks/link.ld'),*[str(output/(name+'.o')) for name in ('start','runtime',variant)],
              *([str(output/'twin_kernel.o')]if variant=='combined'else[]),
              '-lgcc','-o',str(elf)]
        run=subprocess.run(argv,capture_output=True);(output/(variant+'-link.stdout')).write_bytes(run.stdout);(output/(variant+'-link.stderr')).write_bytes(run.stderr)
        commands.append({'argv':argv,'exit_status':run.returncode})
        if run.returncode:
            raise RuntimeError('Link failed: '+variant)
        binaries[variant]={'path':str(elf),'sha256':digest(elf)}
    for tool in ('cc1','as','collect2','ld'):
        name=subprocess.check_output([str(cc),'-print-prog-name='+tool],text=True).strip()
        sources.append(Path(name if '/' in name else shutil.which(name)).resolve())
    sources.append(Path(subprocess.check_output([str(cc),'-print-libgcc-file-name'],text=True).strip()))
    identities={str(p.resolve()):digest(p) for p in sources if output not in p.resolve().parents}
    identities.update(derived.sources)
    snapshots=output/'inputs';snapshots.mkdir()
    for name,expected in identities.items():
        if not (snapshots/expected).exists():shutil.copyfile(name,snapshots/expected)
        if digest(name)!=expected or digest(snapshots/expected)!=expected:raise ValueError('Build source changed')
    report={'schema':'iris.compiler_i8_wrap_build.v1','status':'built','commands':commands,'binaries':binaries,
        'corpus_sha256':digest(output/'corpus.json'),'input_sha256':identities,
        'kernel_sha256':digest(output/'kernel.h'),'instruction_derivation_ok':True,
        'derived_tile_edge':tile_edge,'derived_operand_alignment':alignment,
        'target_source_repositories':shim.source_facts.source_identity(contract),
        'deliberate_noop_negative_control':deliberate_noop,
        'hardware_contacted':False,'calibration_usable':False,'full_functional_certified':False}
    (output/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':'built','binaries':binaries,'single_regions':21,'combined_regions':126}))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--deliberate-noop-negative-control',action='store_true',
        help='Disable compute-kernel calls; this ELF MUST fail and is never for hardware admission.')
    a=p.parse_args();build(a.output.resolve(),a.deliberate_noop_negative_control)

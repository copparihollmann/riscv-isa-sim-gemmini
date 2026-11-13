#!/usr/bin/env python3
"""Close native BTB/BHT and RVC helpers against saved source RTL; no fitting."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    parser = argparse.ArgumentParser(__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    collateral = ROOT/'build/rtl-verilator/gen-collateral'
    rvc_obj = ROOT/'build/pipeline-rvc-source-check/obj'
    runtime = Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
    perl = Path('/scratch/eygao/iris-cy/.conda-env/bin/perl'); verilator = perl.with_name('verilator')
    cxx = Path(shutil.which('g++')).resolve()
    inputs = [Path(__file__), ROOT/'pipeline/fast_shuttle_predictor.hpp', ROOT/'pipeline/fast_shuttle_predictor.cpp',
        ROOT/'pipeline/test_fast_shuttle_predictor.cpp', ROOT/'pipeline/frontend_rtl_peer.hpp',
        ROOT/'pipeline/dump_fast_rvc_table.cpp', ROOT/'pipeline/fast_source_rvc_table.hpp',
        collateral/'ShuttleBTB.sv', collateral/'table_512x2.sv',
        ROOT/'pipeline/evidence/rvc/RVCExpander.sv', ROOT/'pipeline/evidence/rvc/saved-rtl-manifest.json',
        ROOT/'build/pipeline-rvc-source-check/results.json', perl, verilator, perl.with_name('verilator_bin'), cxx,
        *[rvc_obj/n for n in ('VRVCExpander__ALL.a', 'VRVCExpander.h', 'verilated.o', 'verilated_threads.o')]]
    saved = json.loads((ROOT/'pipeline/evidence/rvc/saved-rtl-manifest.json').read_text())
    source_hashes = saved['sim_source_sha256']
    for module in ('ShuttleBTB.sv', 'table_512x2.sv', 'RVCExpander.sv'):
        path = ROOT/'pipeline/evidence/rvc/RVCExpander.sv' if module == 'RVCExpander.sv' else collateral/module
        if sha(path) != source_hashes[str(collateral/module)]: raise ValueError('Saved module source changed: '+module)
    before = {str(p.resolve()): sha(p) for p in inputs}
    commands = []
    def run(name, argv, timeout=180, expected=0):
        started = time.monotonic()
        result = subprocess.run(argv, capture_output=True, preexec_fn=no_core, timeout=timeout)
        (out/(name+'.stdout')).write_bytes(result.stdout); (out/(name+'.stderr')).write_bytes(result.stderr)
        commands.append({'name': name, 'argv': list(map(str, argv)), 'exit_status': result.returncode,
                         'host_seconds': time.monotonic()-started})
        if expected == 0 and result.returncode: raise ValueError(name+' failed; preserved raw logs')
        return result
    obj = out/'obj'
    run('verilate-btb', [str(perl), str(verilator), '--cc', '--exe', '--top-module', 'ShuttleBTB',
        '-Wno-fatal', '--Mdir', str(obj), '-y', str(collateral), '+libext+.sv', str(collateral/'ShuttleBTB.sv'),
        str(ROOT/'pipeline/test_fast_shuttle_predictor.cpp'), str(ROOT/'pipeline/fast_shuttle_predictor.cpp'),
        '-CFLAGS', '-std=c++20 -O2 -I'+str(ROOT/'pipeline')])
    run('build-btb', ['make', '-C', str(obj), '-f', 'VShuttleBTB.mk', '-j8', 'CXX='+str(cxx),
        'LINK='+str(cxx), 'AR=ar', 'RANLIB=ranlib', 'PERL='+str(perl)])
    positives = []
    for seed in (1, 17, 31):
        result = run('btb-seed'+str(seed), [str(obj/'VShuttleBTB'), str(seed)])
        row = json.loads(result.stdout)
        if row.get('pass') is not True or row['edges'] != 200000 or row['duplicate_clear_edges'] < 1000:
            raise ValueError('Continuous source-predictor test scope insufficient')
        positives.append(dict(row, seed=seed))
    text = (ROOT/'pipeline/fast_shuttle_predictor.cpp').read_text()
    mutations = [('history-hash', '((history*221)&255)>>5', '((history*220)&255)>>5'),
        ('duplicate-invalidation', 'std::popcount(hit)>=2', 'false'),
        ('registered-update', 'update_=in.btb;previous_response_=response;', 'update_={};previous_response_=response;'),
        ('replacement-plru', '|((!(way&half))<<(ways-2))', '|((!!(way&half))<<(ways-2))'),
        ('bht-direction-bit', 'out.taken=!isbranch||bool(out.value&1);', 'out.taken=!isbranch||bool(out.value&2);')]
    include = ['-I'+str(ROOT/'pipeline'), '-I'+str(obj), '-I'+str(runtime), '-I'+str(runtime/'vltstd')]
    controls = []
    for name, old, new in mutations:
        if text.count(old) != 1: raise ValueError('Mutation anchor changed: '+name)
        folder = out/'mutations'/name; folder.mkdir(parents=True)
        source = folder/'model.cpp'; source.write_text(text.replace(old, new, 1)); binary = folder/'check'
        run('build-mutant-'+name, [str(cxx), '-std=c++20', '-O2', *include,
            str(ROOT/'pipeline/test_fast_shuttle_predictor.cpp'), str(source), str(obj/'VShuttleBTB__ALL.a'),
            str(obj/'verilated.o'), str(obj/'verilated_threads.o'), '-pthread', '-o', str(binary)])
        result = run('reject-mutant-'+name, [str(binary), '1'], expected=None)
        if result.returncode == 0 or b'predictor ' not in result.stderr or b'expected=' not in result.stderr:
            raise ValueError('Mutation did not reach a qualified oracle mismatch: '+name)
        controls.append({'name': name, 'rejected': True, 'source_sha256': sha(source),
                         'exit_status': result.returncode, 'diagnostic': result.stderr.decode().strip()})
    generated = out/'source_rvc_table.hpp'
    run('build-rvc-generator', [str(cxx), '-std=c++20', '-O2', '-I'+str(rvc_obj), '-I'+str(runtime),
        '-I'+str(runtime/'vltstd'), str(ROOT/'pipeline/dump_fast_rvc_table.cpp'), str(rvc_obj/'VRVCExpander__ALL.a'),
        str(rvc_obj/'verilated.o'), str(rvc_obj/'verilated_threads.o'), '-pthread', '-o', str(out/'generate-rvc')])
    result = run('generate-rvc', [str(out/'generate-rvc'), str(generated)])
    rvc = json.loads(result.stdout)
    if rvc.get('pass') is not True or rvc['checks'] != 262144 or generated.read_bytes() != (ROOT/'pipeline/fast_source_rvc_table.hpp').read_bytes():
        raise ValueError('Source RVC table generation differs')
    # The release helper's own indexing/passthrough is compared independently
    # with the compiled source decoder, including every reserved low pattern.
    driver = out/'rvc-helper-check.cpp'
    driver.write_text('#include "fast_source_rvc_table.hpp"\n#include "VRVCExpander.h"\n#include <stdexcept>\n#include <iostream>\n'
        'int main(){VRVCExpander d;unsigned n=0;for(unsigned x=0;x<65536;++x)for(uint32_t h:{0u,0x12340000u,0xa5a50000u,0xffff0000u}){uint32_t raw=x|h;d.io_in=raw;d.eval();if(iris::frontend::expand_source_rvc(raw)!=d.io_out_bits)throw std::runtime_error("RVC helper index/passthrough mismatch");++n;}std::cout<<n<<"\\n";}\n')
    run('build-rvc-helper', [str(cxx), '-std=c++20', '-O2', '-I'+str(ROOT/'pipeline'), '-I'+str(rvc_obj),
        '-I'+str(runtime), '-I'+str(runtime/'vltstd'), str(driver), str(rvc_obj/'VRVCExpander__ALL.a'),
        str(rvc_obj/'verilated.o'), str(rvc_obj/'verilated_threads.o'), '-pthread', '-o', str(out/'check-rvc-helper')])
    if run('check-rvc-helper', [str(out/'check-rvc-helper')]).stdout.strip() != b'262144':
        raise ValueError('Incomplete release RVC helper comparison')
    if any(sha(p) != wanted for p, wanted in before.items()): raise ValueError('Primitive input changed during checks')
    report = {'schema': 'iris.fast_source_frontend_primitives.v1', 'pass': True,
        'predictor_continuous_edges_per_seed': 200000, 'predictor_results': positives,
        'source_qualified_mutation_controls': controls, 'rvc_source_generation': rvc,
        'release_RVC_helper_differential_checks': 262144,
        'commands': commands, 'input_sha256': before,
        'source_fir_sha256': saved['source_fir_sha256'],
        'scope': 'Plain C++ BTB/BHT control and decoder-only bit-pattern table. Continuous source-reset+update histories; qualified BTB payload only when valid. No fitted cycles or PC lookup tables.',
        'unreset_scope': 'Concrete RTL unreset seeds1/17/31; reset validity/BHT sweep qualify observations. No general four-state power-on certification.',
        'unknowns': ['RAS/F0/F1/F2/FIFO/cache/native integration are separate components.', 'RVC expansion does not decide architectural instruction legality.'],
        'production_RTL_evaluation_required': False, 'timing_certified': False,
        'hardware_contacted': False, 'source_image_association_verified': False}
    report['artifact_sha256'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'pass': True, 'report_sha256': sha(out/'report.json'), 'mutations': len(controls)}))


if __name__ == '__main__': main()

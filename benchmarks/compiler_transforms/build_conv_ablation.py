"""Create fresh, source-bound full-versus-tiled im2col benchmark packets.

This deliberately consumes the exact previously admitted v9 fixture producer,
then snapshots a separately identified candidate. It never edits that producer,
contacts an FPGA, chooses an offload policy or changes production lowering.
Native run_job.py and freeze.py remain separate admission steps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('unsupported producer version at seam: ' + old[:60])
    return text.replace(old, new, 1)


def create(source: Path, output: Path):
    source, output = source.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    selected = ('prepare.py', 'build.py', 'run_job.py', 'freeze.py', 'postgate.py',
                'coverage.py', 'generate_kernels.py', 'rvv_profile.c', 'vme_profile.c',
                'work_stats.h', 'work_schema.json', 'softmax-lut.h',
                'hardware-input-manifest.json')
    original = {}
    for name in selected:
        shutil.copy2(source / name, output / name)
        original[str(source / name)] = sha(source / name)
    shutil.copytree(source / 'frozen-v8', output / 'frozen-v8')
    for f in (source / 'frozen-v8').rglob('*'):
        if f.is_file():
            original[str(f)] = sha(f)
    original_driver = source / 'incremental-records-v2/driver_incremental_v2.c'
    original[str(original_driver)] = sha(original_driver)
    driver = original_driver.read_text()
    driver = replace_once(driver, '#include "work_stats.h"',
                          '#include "work_stats.h"\n#include "conv_pack.h"')
    insertion = '''
 if(t->kind==1 && t->tile_m){
  struct iris_conv_shape shape={t->batch,t->ci,t->co,t->h,t->w,t->kh,t->kw,t->stride,t->pt,t->pl,t->oh,t->ow,t->layout,t->weight};
  uint64_t s=cyc();iris_conv_pack_b(&shape,z->b,z->pb);phase[0]+=cyc()-s;
  for(size_t first=0;first<t->m;first+=t->tile_m){
   size_t count=t->m-first;if(count>t->tile_m)count=t->tile_m;
   s=cyc();iris_conv_pack_a(&shape,z->a,z->pa,first,count);phase[0]+=cyc()-s;
   s=cyc();primitive(vi,out+first*t->n,z->pa,z->pb,count,t->n,t->k);phase[1]+=cyc()-s;
  }return;
 }
'''
    driver = replace_once(driver, ' if(t->kind==1){uint64_t s=cyc();',
                          insertion + ' if(t->kind==1){uint64_t s=cyc();')
    driver = replace_once(driver, 'z.pa=alloc((size_t)t->k*t->m);',
                          'z.pa=alloc((size_t)t->k*(t->tile_m&&t->tile_m<t->m?t->tile_m:t->m));')
    begin, end = driver.index('static void execute('), driver.index('\nstruct result{')
    driver = driver[:begin] + driver[begin:end].replace('cyc()', 'phase_clock(vi)') + driver[end:]
    driver = replace_once(driver, 'struct buffers{',
                          'static inline uint64_t phase_clock(unsigned vi){return vi<2?0:cyc();}\nstruct buffers{')
    (output / 'driver.c').write_text(driver)
    header = Path(__file__).with_name('conv_pack.h')
    shutil.copy2(header, output / 'conv_pack.h')
    original[str(header)] = sha(header)
    original[str(Path(__file__).resolve())] = sha(__file__)

    coverage = json.loads((source / 'coverage.json').read_text())
    original[str(source / 'coverage.json')] = sha(source / 'coverage.json')
    cases, groups = [], {}
    for base, label in [('conv_Ciaxis_16', 'nchw'), ('conv_layout_NHWC_HWIO', 'nhwc')]:
        geometry = next(c for c in coverage['cases'] if c['name'] == base)
        names = []
        for tile in (0, 32, 128, 512):
            c = dict(geometry, name=f'conv_transform_{label}_T{tile}', tile_m=tile,
                     split='fitting', warmup=1, measured=2, input_identity=base,
                     compiler_policy_role='transform_development')
            cases.append(c)
            names.append(c['name'])
        groups['transform-' + label] = names
    controls = []
    # Tail, batch, stride and asymmetric-layout boundaries use all-word goldens.
    for i, (batch, nhwc, hwio, stride, tile) in enumerate(
            [(1, 0, 0, 1, 7), (2, 1, 1, 2, 16), (1, 1, 0, 1, 32), (2, 0, 1, 2, 7)]):
        h, w, ci, co, kh, kw, pads = 7, 9, 3, 5, 3, 2, [1, 0, 2, 0]
        oh, ow = (h+pads[0]+pads[1]-kh)//stride+1, (w+pads[2]+pads[3]-kw)//stride+1
        c = dict(name=f'control_conv_transform_{i}', kind='conv_im2col_i8', split='control',
                 batch=batch, ci=ci, co=co, h=h, w=w, kh=kh, kw=kw,
                 stride=stride, pads=pads, oh=oh, ow=ow, m=batch*oh*ow, n=co,
                 k=ci*kh*kw, MACs=batch*oh*ow*co*ci*kh*kw, layout='NHWC' if nhwc else 'NCHW',
                 weight_layout='HWIO' if hwio else 'OIHW', tile_m=tile, warmup=0, measured=1,
                 compiler_policy_role='functional_control')
        cases.append(c)
        controls.append(c['name'])
    groups['control'] = controls
    (output / 'coverage.json').write_text(json.dumps(dict(schema='iris.conv_transform_cases.v1', cases=cases), indent=2)+'\n')
    prepare = (output / 'prepare.py').read_text()
    start, stop = prepare.index('def groups():'), prepare.index('\n\ndef prepare(')
    prepare = prepare[:start] + 'def groups():\n    return ' + repr(groups) + '\n' + prepare[stop:]
    prepare = replace_once(prepare, "c['name'].encode()", "c.get('input_identity',c['name']).encode()")
    prepare = replace_once(prepare, "fields=['m','n','k'", "fields=['tile_m','m','n','k'")
    prepare = replace_once(prepare, "['driver.c','rvv_profile.c','vme_profile.c','work_stats.h','postgate.py']",
                          "['driver.c','rvv_profile.c','vme_profile.c','work_stats.h','postgate.py','conv_pack.h']")
    (output / 'prepare.py').write_text(prepare)
    manifest = dict(schema='iris.conv_transform_campaign.v1', status='prepared_not_executed',
                    groups=groups, source_input_sha256=original,
                    numerical_contract='signed-I8xI8 into wrapping-I32; zero padding; no requantization',
                    clean_timing_scope='whole operator including B packing, A unfolding, all GEMM calls and final fence; no inner phase CSR reads',
                    profile_scope='same loop geometry plus per-panel phase CSR and work counters; overhead never subtracted by assumption',
                    packing_rows=[0, 32, 128, 512], zero_means='original full unfolding',
                    unchanged_primitive_objects_required=True, transform_is_compiler_default=False,
                    compiler_generalization_proven=False, hardware_contacted=False)
    (output / 'campaign.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({'created': str(output), 'groups': groups, 'hardware_contacted': False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--source-v9', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    create(a.source_v9, a.output)

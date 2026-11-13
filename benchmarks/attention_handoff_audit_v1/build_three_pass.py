"""Prepare a separate three-pass attention measurement candidate, not a certified fix."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from build import A, PARENT, SDK, ROOT, once, sha


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    parent = json.loads((PARENT / 'build.json').read_text())
    for path, digest in parent['input_sha256'].items():
        if sha(path) != digest:
            raise ValueError('Changed parent input: ' + path)
    app = out / 'app'
    app.mkdir()
    cmake = (PARENT / 'app/CMakeLists.txt').read_text()
    original_entry = PARENT / 'app/src/main.c'
    entry = original_entry.read_text().replace('ATTN_BEGIN 3 2 7 2 5', 'ATTN_BEGIN 3 2 3 0 3').replace('completed+=7', 'completed+=3')
    if entry == original_entry.read_text() or cmake.count(str(original_entry)) != 2:
        raise ValueError('Unexpected entrypoint')
    (app / 'main.c').write_text(entry)
    cmake = cmake.replace(str(original_entry), str(app / 'main.c'))
    for meta in parent['cases_meta']:
        index = meta['index']
        original = A / f'attn/single-worker-next3-v1/app/src/case{index}/main.c'
        source = original.read_text()
        source = once(source, '#include "attn_data.h"', '#include "' + str(original.parent / 'attn_data.h') + '"')
        source = once(source, '#include "out_b64.h"', '#include "' + str(original.parent / 'out_b64.h') + '"')
        if source.count('rep<7') != 2 or source.count('records[7]') != 1:
            raise ValueError('Unexpected repetition loops')
        source = source.replace('rep<7', 'rep<3').replace('records[7]', 'records[3]')
        source = once(source, 'uint32_t actual,expected;} record;',
                      'uint32_t actual,expected;uint64_t dispatch_begin,dispatch_end;} record;')
        source = once(source, 'static int noop(void*x)',
                      'static uint64_t controller_ticks(void){return *(volatile const uint64_t *)DT_REG_ADDR_BY_IDX(DT_NODELABEL(mtimer),0);}\nstatic int noop(void*x)')
        source = once(source, 'r->status=operation(route,r);',
                      'memset(final+G,0xa7,HQ*LQ*D*4);__asm__ volatile("fence rw,rw":::"memory");'
                      'r->dispatch_begin=controller_ticks();r->status=operation(route,r);r->dispatch_end=controller_ticks();')
        source = once(source, 'rep<2?"true":"false"', '"false"')
        source = once(source, '   for(unsigned p=0;p<PHASES;p++){',
                      f'   printk("ATTN_DISPATCH v1 {index} %u %u %llu %llu\\n",route,rep,r->dispatch_begin,r->dispatch_end);\n'
                      '   for(unsigned p=0;p<PHASES;p++){')
        source = once(source, f'if(failed){{printk("ATTN_FAIL case{index} route%u\\n",route);return 1;}}',
                      f'if(failed){{dump(route);printk("ATTN_FAIL case{index} route%u\\n",route);return 1;}}')
        replacement = app / f'case{index}.c'
        replacement.write_text(source)
        if cmake.count(str(original)) != 2:
            raise ValueError('Unexpected case/flags binding')
        cmake = cmake.replace(str(original), str(replacement))
    (app / 'CMakeLists.txt').write_text(cmake)
    (app / 'prj.conf').write_bytes((PARENT / 'app/prj.conf').read_bytes())
    reader_dir = out / 'readers'
    reader_dir.mkdir()
    reader_sources = A / 'attn/target-tools-i8-v2'
    substitutions = {
        'case_reader_i8.py': [('ATTN_BEGIN 1 2 7 2 5', 'ATTN_BEGIN 1 2 3 0 3'),
                              ('ATTN_DONE 0 14', 'ATTN_DONE 0 6'), ('==14', '==6'),
                              ('range(7)', 'range(3)'), ("j['warmup']==(rep<2)", "j['warmup']is False"),
                              ('warmup_trials_validated=2,measured_trials_validated=5', 'warmup_trials_validated=0,measured_trials_validated=3'),
                              ('trials=14,canonical_regions=14,phase_windows=14*', 'trials=6,canonical_regions=6,phase_windows=6*'),
                              ('words*14', 'words*6')],
        'postgate.py': [('ATTN_BEGIN {n} 2 7 2 5', 'ATTN_BEGIN {n} 2 3 0 3'), ('n*14', 'n*6'),
                        ('[0-6]', '[0-2]'), ('ATTN_BEGIN 1 2 7 2 5', 'ATTN_BEGIN 1 2 3 0 3'),
                        ('ATTN_DONE 0 14', 'ATTN_DONE 0 6')],
    }
    for name, edits in substitutions.items():
        source = (reader_sources / name).read_text()
        for old, new in edits:
            if old not in source:
                raise ValueError('Unexpected numerical reader: ' + old)
            source = source.replace(old, new)
        (reader_dir / name).write_text(source)
    configure = json.loads((PARENT / 'commands.json').read_text())[1]['argv']
    configure = [str(app) if x == str(PARENT / 'app') else str(out / 'build') if x == str(PARENT / 'build') else x for x in configure]
    commands = [configure, [str(SDK / 'bin/cmake'), '--build', str(out / 'build'), '--parallel', '4']]
    env = dict(os.environ, PATH=str(SDK / 'bin') + ':' + os.environ['PATH'],
               ZEPHYR_BASE=str(ROOT / 'third_party/zephyr-iris'), ZEPHYR_TOOLCHAIN_VARIANT='cross-compile',
               CROSS_COMPILE=str(SDK / 'riscv-tools/bin/riscv64-unknown-elf-'))
    for name, cmd in zip(('configure', 'build'), commands):
        with (out / (name + '.stdout')).open('xb') as stdout, (out / (name + '.stderr')).open('xb') as stderr:
            subprocess.run(cmd, env=env, stdout=stdout, stderr=stderr, check=True, timeout=300)
    elf = out / 'build/zephyr/zephyr.elf'
    pins = parent['input_sha256'].copy()
    for p in [Path(__file__).resolve(), Path(__file__).with_name('build.py'), PARENT / 'build.json',
              *app.iterdir(), *reader_dir.iterdir(), out / 'build/zephyr/.config',
              out / 'build/zephyr/zephyr.dts', out / 'build/compile_commands.json']:
        pins[str(p)] = sha(p)
    report = dict(parent, schema='iris.attention_three_pass_candidate.v1', elf=str(elf), elf_sha256=sha(elf),
                  input_sha256=pins, commands=commands, trials=18,
                  repetitions=3, warmup_trials=0, primary_pass_index=2,
                  output_poisoning_and_preclock_fence_outside_operation=True,
                  H2_whole_dispatch_mtime_includes_initial_final_wake_and_registration=True,
                  H2_PMU=False, physical_busy=None, certified_cold=False,
                  arithmetic_objects_changed=False, default_IRQ_policy_preserved=True,
                  production_failure_retest_required=True, hardware_pass=False, native_pass=False)
    (out / 'build-receipt.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(ELF=str(elf), ELF_sha256=sha(elf), trials=18, hardware_pass=False)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output.resolve())

"""Build a separate attention handoff diagnostic; never alter production inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

A = Path('/users/copparihollmann/iris-work/out/artifacts/probes/utilization-correction-v1/approved-operator-campaign-20261110-v1')
PARENT = A / 'attn/i8-only-next3-v1'
SDK = Path('/scratch/eygao/iris-cy/.conda-env')
ROOT = Path('/scratch/copparihollmann/iris-model')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unexpected source shape: ' + old)
    return text.replace(old, new, 1)


AUDIT = r'''
/* Diagnostic only: ordinary integer metadata, never RVV/VME payload copies.
 * Reads of thread-owned software switch counts do not enable FP/vector CSRs.
 * Any timing/layout perturbation makes this image performance-ineligible. */
#define HANDOFF_MAX 65536u
typedef struct {
 unsigned command,hart;int status;unsigned registered;
 uint64_t sequence,mstatus_before,mstatus_after;
 uint32_t saves_before,restores_before,saves_after,restores_after;
} handoff_record;
static handoff_record handoffs[HANDOFF_MAX];
static unsigned handoff_count,handoff_overflow;
static unsigned long audit_mstatus(void){
 unsigned long value;__asm__ volatile("csrr %0,mstatus":"=r"(value));return value;
}
static handoff_record *handoff_begin(correction_pool *p,unsigned command){
 if(command!=CMD_TEAM && command!=CMD_ENABLE_MATRIX)return 0;
 if(handoff_count==HANDOFF_MAX){handoff_overflow++;return 0;}
 handoff_record *r=&handoffs[handoff_count++];
 r->command=command;r->hart=actual_hart(0);r->mstatus_before=audit_mstatus();
 iris_vme_switch_counts(&r->saves_before,&r->restores_before);
 if(command==CMD_TEAM){
  merlin_staged_team *t=atomic_load_explicit(&p->team,memory_order_acquire);
  if(t)r->sequence=t->config.sequence;
 }
 return r;
}
static void handoff_end(handoff_record *r,correction_pool *p,int status){
 if(!r)return;
 r->status=status;r->registered=p->matrix_registered;r->mstatus_after=audit_mstatus();
 iris_vme_switch_counts(&r->saves_after,&r->restores_after);
}
void pool_handoff_audit_dump(void){
 if(actual_hart(0)!=2 || pool_runtime_idle())k_panic();
 for(unsigned i=0;i<handoff_count;i++){
  const handoff_record*r=&handoffs[i];
  printk("ATTN_HANDOFF v1 %u %u %u %d %u %llu %llu %llu %u %u %u %u\n",
   i,r->command,r->hart,r->status,r->registered,r->sequence,
   r->mstatus_before,r->mstatus_after,r->saves_before,r->restores_before,
   r->saves_after,r->restores_after);
 }
 printk("ATTN_HANDOFF_DONE v1 %u %u\n",handoff_count,handoff_overflow);
 if(handoff_overflow)k_panic();
}
'''


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    parent = json.loads((PARENT / 'build.json').read_text())
    if sha(PARENT / 'suite.elf') != parent['elf_sha256'] or parent['elf_sha256'] != '08e652a4accc395c0799d9667dfffd2b6c2432dbdff678336a732de1a1ed69dd':
        raise ValueError('Original production ELF changed')
    for path, digest in parent['input_sha256'].items():
        if sha(path) != digest:
            raise ValueError('Parent input changed: ' + path)
    app = out / 'app'
    app.mkdir()
    pool_original = PARENT / 'app/src/pool_runtime.c'
    pool = once(pool_original.read_text(), 'static void worker(', AUDIT + '\nstatic void worker(')
    pool = once(pool, '    int rc=0;', '    handoff_record *trace=handoff_begin(p,command);\n    int rc=0;')
    pool = once(pool, '    atomic_store_explicit(&p->worker_status[hart],rc,memory_order_release);',
                '    handoff_end(trace,p,rc);\n    atomic_store_explicit(&p->worker_status[hart],rc,memory_order_release);')
    (app / 'pool_runtime.c').write_text(pool)
    entry_original = PARENT / 'app/src/main.c'
    entry = once(entry_original.read_text(), 'static unsigned failed,completed;',
                 'extern void pool_handoff_audit_dump(void);\nstatic unsigned failed,completed;')
    entry = once(entry, 'if(pool_runtime_idle())failed=1;', 'if(pool_runtime_idle())failed=1;pool_handoff_audit_dump();')
    (app / 'main.c').write_text(entry)
    cmake = (PARENT / 'app/CMakeLists.txt').read_text()
    # Each source occurs in both target_sources and its scalar-only flags.
    for original, replacement in ((pool_original, app / 'pool_runtime.c'),
                                  (entry_original, app / 'main.c')):
        if cmake.count(str(original)) != 2:
            raise ValueError('Unexpected source/compile-flags bindings: ' + str(original))
        cmake = cmake.replace(str(original), str(replacement))
    dispatch_counts = []
    for meta in parent['cases_meta']:
        index = meta['index']
        original = A / f'attn/single-worker-next3-v1/app/src/case{index}/main.c'
        source = original.read_text()
        # Failure output is serialized only after the measured operation ends.
        source = once(source, '#include "attn_data.h"', '#include "' + str(original.parent / 'attn_data.h') + '"')
        source = once(source, '#include "out_b64.h"', '#include "' + str(original.parent / 'out_b64.h') + '"')
        source = once(source, f'if(failed){{printk("ATTN_FAIL case{index} route%u\\n",route);return 1;}}',
                      f'if(failed){{dump(route);printk("ATTN_FAIL case{index} route%u\\n",route);return 1;}}')
        replacement = app / f'case{index}.c'
        replacement.write_text(source)
        if cmake.count(str(original)) != 2:
            raise ValueError('Unexpected case source/flags bindings')
        cmake = cmake.replace(str(original), str(replacement))
        wrappers = (original.parent / 'wrappers.c').read_text()
        counts = []
        for job in range(4):
            function = wrappers.split('static int run_0_' + str(job) + '(', 1)[1].split('\n\n', 1)[0]
            counts.append(int(re.search(r'completed_dispatches!=(\d+)', function).group(1)))
        soft = int(re.search(r'completed_dispatches!=(\d+)', wrappers.split('int attn_softmax(', 1)[1]).group(1))
        params = meta['parameters']
        per_operation = params['Hkv'] * (counts[1] + counts[3]) + params['Hq'] * (counts[0] + counts[2] + soft + 2)
        dispatch_counts.append(dict(index=index, quant_job_dispatches=counts, softmax_dispatches=soft,
                                    per_operation_team_commands=per_operation,
                                    all_14_operations_team_commands=14 * per_operation))
    # Case-local quoted headers retain their original directories and precedence.
    (app / 'CMakeLists.txt').write_text(cmake)
    (app / 'prj.conf').write_bytes((PARENT / 'app/prj.conf').read_bytes())
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
    for path in [Path(__file__).resolve(), PARENT / 'build.json', *app.glob('*.c'),
                 app / 'CMakeLists.txt', app / 'prj.conf', out / 'build/zephyr/.config',
                 out / 'build/zephyr/zephyr.dts', out / 'build/compile_commands.json']:
        pins[str(path)] = sha(path)
    report = dict(schema='iris.attention_handoff_audit_build.v1', ELF=str(elf), ELF_sha256=sha(elf),
                  parent_ELF_sha256=parent['elf_sha256'], input_sha256=pins, commands=commands,
                  expected_handoffs=1 + sum(x['all_14_operations_team_commands'] for x in dispatch_counts),
                  dispatch_count_derivation=dispatch_counts, handoff_capacity=65536,
                  preserves_original_case_route_trial_order=True, trials=42,
                  arithmetic_objects_changed=False, timed_operation_body_changed=False,
                  failure_full_output_dump_added_outside_timing=True,
                  context_registration_and_IRQ_policy_changed=False,
                  extra_FP_RVV_VME_CSR_reads=False, payload_copies_added=False,
                  UART_only_after_all_operations=True, performance_ineligible=True,
                  physical_busy=None, native_pass=False, hardware_pass=False,
                  limitation='A passing diagnostic is not a production fix. Thread/IRQ timing and ELF layout change.')
    (out / 'build-receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('input_sha256', 'commands')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output.resolve())

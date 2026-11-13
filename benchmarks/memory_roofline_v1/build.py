#!/usr/bin/env python3
"""Build a standalone Zephyr memory roofline packet. No hardware access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SDK = Path('/scratch/eygao/iris-cy/.conda-env')
PERIOD = 65536
KINDS = ['rvv_read_sum_u32', 'rvv_write_u8', 'rvv_copy_u8',
         'rvv_triad_u32', 'dependent_chase64', 'rvv_panel_read_sum_u32', 'scalar_read_sum_u32']
TIERS = ['dram_mapped', 'h0_tcm_upper64K', 'system_scratchpad']

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, value): Path(p).write_text(json.dumps(value, indent=2) + '\n')

def cases(smoke=False):
    result = []
    for tier, powers in [(0, range(11, 24)), (1, range(11, 15)), (2, range(11, 16))]:
        for power in ([min(powers)] if smoke else powers):
            n = 1 << power
            for kind in [0, 1, 2, 3, 4, 6]:
                repeats = max(1, 65536 // n) if kind != 4 else max(1, 1024 // (n // 64))
                result.append(dict(tier=tier, kind=kind, bytes=n, repeats=repeats, pitch=0, rows=0))
    for width in ([32] if smoke else [32, 64]):
        for pitch in [64, 2048, 8192]:
            for rows in ([128] if smoke else [128, 1024]):
                result.append(dict(tier=0, kind=5, bytes=width, repeats=max(1, 65536 // (width * rows)), pitch=pitch, rows=rows))
    return result

def weighted(n, values):
    """sum(value[i]*(i+1)) modulo 2**64, exploiting the exact pattern period."""
    q, rem = divmod(n, len(values))
    s = sum(values); w = sum(v * (i + 1) for i, v in enumerate(values))
    return (q * w + len(values) * s * q * (q - 1) // 2 +
            sum(v * (q * len(values) + i + 1) for i, v in enumerate(values[:rem]))) & ((1 << 64) - 1)

def oracle(c, base):
    n = c['bytes'] // 4; kind = c['kind']; repeats = c['repeats']
    av = lambda i: (17 * i + 11) & 65535
    bv = lambda i: (29 * i + 23) & 65535
    if kind == 4:
        nodes = c['bytes'] // 64
        return repeats * (nodes * base + 64 * nodes * (nodes - 1) // 2) & ((1 << 64) - 1)
    if kind == 5:
        return sum(av(row * c['pitch'] // 4 + i) for row in range(c['rows']) for i in range(n)) * repeats & 0xffffffff
    if kind in [0, 6]:
        q, r = divmod(n, PERIOD)
        return (q * sum(av(i) for i in range(PERIOD)) + sum(av(i) for i in range(r))) * repeats & 0xffffffff
    if kind == 1:
        return 0x3c3c3c3c * n * (n + 1) // 2 & ((1 << 64) - 1)
    values = [av(i) if kind == 2 else av(i) + 3 * bv(i) for i in range(PERIOD)]
    return weighted(n, values)

def accounting(c):
    n, r, kind = c['bytes'], c['repeats'], c['kind']
    streams = 2 if kind == 2 else 3 if kind == 3 else 1
    footprint = c['pitch'] * c['rows'] if kind == 5 else n * streams
    loads = n // 64 * r if kind == 4 else 0
    requested = loads * 8 if kind == 4 else n * (c['rows'] if kind == 5 else 1) * r * streams
    return dict(requested_bytes=requested, active_data_address_span_bytes=footprint,
                per_stream_bytes=n, dependent_loads=loads, physical_bus_bytes=None)

def build(out, smoke=False, negative=False):
    out.mkdir(parents=True, exist_ok=False); app = out/'app'; app.mkdir()
    rows = cases(smoke)
    fields = ['tier', 'kind', 'bytes', 'repeats', 'pitch', 'rows']
    (app/'cases.inc').write_text('#define ROOF_CASES '+str(len(rows))+'\nstatic const roof_case roof_cases[] = {\n'+
        ',\n'.join('{'+','.join(str(c[k]) for k in fields)+'}' for c in rows)+'\n};\n')
    source = [HERE/'main.c', HERE/'kernels.c', HERE/'kernels.h', HERE/'build.py', HERE/'validate.py', HERE/'run_native.py']
    before = {str(p):sha(p) for p in source}
    (app/'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(iris_memory_roofline)
target_sources(app PRIVATE "'''+str(HERE/'main.c')+'" "'+str(HERE/'kernels.c')+'''")
target_include_directories(app PRIVATE "'''+str(app)+'" "'+str(HERE)+'''")
zephyr_compile_options(-fno-tree-vectorize -fno-tree-slp-vectorize)
set_source_files_properties("'''+str(HERE/'main.c')+'''" PROPERTIES COMPILE_FLAGS "-march=rv64gc -O2'''+(' -DROOF_SKIP_KERNEL' if negative else '')+'''")
set_source_files_properties("'''+str(HERE/'kernels.c')+'''" PROPERTIES COMPILE_FLAGS "-march=rv64gcv_zvl256b -O3")
''')
    (app/'prj.conf').write_text('''CONFIG_SMP=y
CONFIG_SCHED_CPU_MASK=y
CONFIG_PRINTK=y
CONFIG_ASSERT=y
CONFIG_MAIN_STACK_SIZE=8192
CONFIG_RISCV_ISA_EXT_V=y
CONFIG_RISCV_VECTOR_MAX_LEN=256
CONFIG_RISCV_IRIS_VME_CONTEXT=y
CONFIG_FPU_SHARING=y
CONFIG_TICKLESS_KERNEL=n
CONFIG_SYS_CLOCK_TICKS_PER_SEC=1000
''')
    env = dict(os.environ, PATH=str(SDK/'bin')+':'+os.environ['PATH'],
        ZEPHYR_BASE=str(ROOT/'third_party/zephyr-iris'), ZEPHYR_TOOLCHAIN_VARIANT='cross-compile',
        CROSS_COMPILE=str(SDK/'riscv-tools/bin/riscv64-unknown-elf-'))
    cmake = str(SDK/'bin/cmake')
    commands = [[cmake, '-GNinja', '-S', str(app), '-B', str(out/'build'), '-DBOARD=iris',
        '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DBOARD_ROOT='+str(ROOT/'zephyr'), '-DDTS_ROOT='+str(ROOT/'zephyr'),
        '-DPython3_EXECUTABLE='+str(SDK/'bin/python3'), '-DDTC='+str(SDK/'bin/dtc'),
        '-DEXTRA_DTC_OVERLAY_FILE='+str(ROOT/'zephyr/boards/chipyard/iris/ethan-firesim.overlay')],
        [cmake, '--build', str(out/'build'), '--parallel', '2']]
    for stage, cmd in zip(['configure', 'compile'], commands):
        r = subprocess.run(cmd, capture_output=True, env=env, timeout=600)
        (out/(stage+'.stdout')).write_bytes(r.stdout); (out/(stage+'.stderr')).write_bytes(r.stderr)
        if r.returncode: raise RuntimeError(stage+' failed: '+r.stderr.decode()[-1800:]+r.stdout.decode()[-1800:])
    elf = out/'build/zephyr/zephyr.elf'; tools = SDK/'riscv-tools/bin'
    if any(sha(p)!=h for p,h in before.items()): raise ValueError('Source changed during build')
    nm = subprocess.check_output([str(tools/'riscv64-unknown-elf-nm'), '-n', str(elf)], text=True)
    symbols = {p[2]: int(p[0], 16) for line in nm.splitlines() if len(p := line.split()) == 3}
    bases = [symbols['roof_dram']+64, 0x70010040, 0x580000040]
    host_cases = []
    for i, c in enumerate(rows):
        c.update(case_index=i, tier_name=TIERS[c['tier']], kind_name=KINDS[c['kind']], **accounting(c))
        c['expected_checksum'] = oracle(c, bases[c['tier']])
        for rep in range(3): host_cases.append(dict(id=f'memroof_c{i}_r{rep}', region='memory_kernel',
            active_harts=[0], expected_checksums_by_hart=[c['expected_checksum']], pass_id=rep, warmup=False))
    (out/'disassembly.txt').write_bytes(subprocess.check_output([str(tools/'riscv64-unknown-elf-objdump'), '-d', str(elf)]))
    # Preserve actual compiler dependencies and the Zephyr/linker inputs,
    # rather than identifying the application sources alone.
    deps = subprocess.check_output([str(SDK/'bin/ninja'), '-C', str(out/'build'), '-t', 'deps'], text=True)
    (out/'compiler-dependencies.txt').write_text(deps)
    closure = {str(p.resolve()) for p in source+[app/'cases.inc', app/'CMakeLists.txt', app/'prj.conf',
        tools/'riscv64-unknown-elf-gcc', tools/'riscv64-unknown-elf-ld',
        out/'build/zephyr/.config', out/'build/zephyr/linker.cmd', out/'build/compile_commands.json']}
    for line in deps.splitlines():
        if line.startswith('    '):
            p=Path(line.strip());p=p if p.is_absolute() else out/'build'/p
            if p.is_file():closure.add(str(p.resolve()))
    closure.update(str(p.resolve()) for p in (ROOT/'zephyr/boards/chipyard/iris').iterdir() if p.is_file())
    inputs={name:sha(name) for name in sorted(closure)}
    save(out/'cases.json', host_cases)
    save(out/'manifest.json', dict(schema='iris.memory_roofline_packet.v1', cases=rows, expected_regions=len(host_cases),
        ELF=str(elf), ELF_sha256=sha(elf), negative_omitted_kernel=negative, smoke=smoke,
        input_sha256=inputs,
        memory_bases=bases, compute_harts=[0], controller_hart=2, inactive_compute_harts=[1],
        scope='Zephyr IRQs enabled. H2 initializes/validates/prints outside H0 kernel windows and blocks during kernels. No flush, no certified cold/hit/residency. Three ordered observations; validation conditions subsequent memory state. Fences and counter instrumentation retained. Store fence is not DRAM writeback.',
        physical_bus_bytes=None, physical_busy=None, cycle_clock_attested=False, source_image_association_verified=False))
    if not negative and 'roof_kernel' not in symbols:raise ValueError('Positive kernel missing from linked ELF')
    save(out/'build-receipt.json', dict(commands=commands, ELF_sha256=sha(elf), compiler=str(tools/'riscv64-unknown-elf-gcc'),
        compiler_sha256=sha(tools/'riscv64-unknown-elf-gcc'), symbols={k:symbols[k] for k in ['roof_dram','roof_kernel'] if k in symbols},
        zephyr_config_sha256=sha(out/'build/zephyr/.config')))
    return dict(packet=str(out), configurations=len(rows), observations=len(host_cases), ELF_sha256=sha(elf), hardware_actions=False)

if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--smoke', action='store_true'); p.add_argument('--negative-omit-kernel', action='store_true'); a=p.parse_args()
    print(json.dumps(build(a.output.resolve(), a.smoke, a.negative_omit_kernel)))

#!/usr/bin/env python3
"""Exercise the isolated live Shuttle subset; never certify RTL timing."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spike.run_functional import command, symbols
from pipeline.alu_corpus import corpus, assembly, evaluate, NAMES
from pipeline import rvc_corpus


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def rows(text, prefix):
    return [json.loads(line[len(prefix):]) for line in text.splitlines() if line.startswith(prefix)]


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT/'build/spike-shuttle-pipeline/spike')
    parser.add_argument('--uart', type=Path, default=ROOT/'build/spike-shuttle-pipeline/libsifive_uart.so')
    parser.add_argument('--compiler', type=Path, default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'))
    parser.add_argument('--baseline-binary', type=Path, default=ROOT/'build/snapshot-db964603/spike-iris-functional')
    parser.add_argument('--baseline-uart', type=Path, default=ROOT/'build/snapshot-db964603/libsifive_uart.so')
    parser.add_argument('--parent-source', type=Path, default=ROOT/'build/pipeline-parent-db964603')
    parser.add_argument('--parent-overlay', type=Path, default=ROOT/'build/snapshot-db964603/iris.patch')
    parser.add_argument('--guest-root', type=Path, default=ROOT/'build/pipeline-guest-db964603')
    parser.add_argument('--native-build', type=Path, default=ROOT/'build/spike-shuttle-pipeline')
    parser.add_argument('--source', type=Path, default=ROOT/'pipeline/riscv-isa-sim')
    parser.add_argument('--rvc', action='store_true', help='Enable the independently RTL-checked compressed ALU domain')
    parser.add_argument('--counter-pipeline',action='store_true',help='Also admit source-checked zero-operand counter reads')
    parser.add_argument('--rocket-pipeline',action='store_true',help='Also enable the distinct single-issue Rocket domain')
    parser.add_argument('--private-values',action='store_true',help='Check optional private result forwarding in the explicit pure pipeline')
    parser.add_argument('--output', type=Path, default=ROOT/'build/pipeline-directed')
    args = parser.parse_args()
    if args.rocket_pipeline:args.counter_pipeline=True
    if args.counter_pipeline:args.rvc=True
    binary, uart, compiler, out = [p.resolve() for p in (args.binary, args.uart, args.compiler, args.output)]
    out.mkdir(parents=True, exist_ok=True)
    (out/'results.json').write_text('{"status":"in_progress","calibrated":false}\n')
    binary_hash, uart_hash = sha(binary), sha(uart)
    env = dict(os.environ, PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
    flags = [str(compiler), '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-fno-builtin',
             '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-mcmodel=medany', '-mabi=lp64d',
             '-march=rv64gcv_zicsr_zifencei', '-DIRIS_HARTS=3', '-I'+str(args.guest_root.resolve()/'benchmarks')]
    commands = []

    def build(name, sources, extra=(), link=True):
        target = out/(name+('.elf' if link else '.o'))
        argv = flags+list(extra)
        if link:
            argv += ['-nostdlib', '-static', '-T', str(args.guest_root.resolve()/'benchmarks/link.ld')]
        else:
            argv += ['-c']
        for s in sources:
            path = Path(s)
            if not path.is_absolute():
                path = (args.guest_root.resolve() if str(s).startswith('benchmarks/') else ROOT)/path
            argv.append(str(path))
        if link:
            argv += ['-lgcc']
        argv += ['-o', str(target)]
        p = subprocess.run(argv, capture_output=True, text=True, env=env)
        (out/(name+'.build.log')).write_text(p.stdout+p.stderr)
        require(p.returncode == 0, 'guest build failed: '+name+'\n'+p.stderr)
        commands.append(argv)
        return target

    streams = build('streams', ['benchmarks/start.S', 'benchmarks/runtime.c', 'pipeline/guest.c', 'pipeline/streams.S'])
    runtime = build('irq-runtime', ['benchmarks/runtime.c'], ['-Dtrap_dispatch=base_trap_dispatch'], False)
    precision = build('precision', ['benchmarks/start.S', runtime, 'pipeline/irq_guest.c', 'pipeline/irq_streams.S'],
                      ['-DIRIS_ROCKET_PULSE=1'] if args.rocket_pipeline else [])
    pure = (ROOT/'pipeline/pure.fixture').read_text()
    mode = 'pure-integer-rvc-sequential-frontend' if args.rvc else 'pure-integer-sequential-frontend'
    if args.counter_pipeline:mode='pure-integer-rvc-counter-sequential-frontend'
    pure = pure.replace('pure-integer-sequential-frontend',mode)
    if args.rocket_pipeline:pure+='rocket_pipeline pure-integer-rvc-counter-sequential-frontend\n'
    if args.private_values:pure+='pipeline_values private-pure-integer\n'
    conservative = '\n'.join(line for line in pure.splitlines() if not line.startswith(('shuttle_pipeline ','rocket_pipeline ','pipeline_values ')))+'\n'
    results, negatives = [], []

    def run(name, elf, fixture, seed=None, primary=False):
        fp, gp = out/(name+'.fixture'), out/(name+'.graph.json')
        fp.write_text(fixture)
        executable = args.baseline_binary.resolve() if primary else binary
        plugin = args.baseline_uart.resolve() if primary else uart
        argv = command(executable, elf)
        argv = ['--extlib='+str(plugin) if a.startswith('--extlib=') else a for a in argv]
        argv[-1:-1] = ['--iris-timing-fixture='+str(fp), '--iris-timing-trace='+str(gp)]
        if seed is not None:
            argv.insert(-1, '--iris-schedule-seed='+str(seed))
        start = time.perf_counter()
        p = subprocess.run(argv, text=True, capture_output=True, env=env, timeout=60)
        elapsed = time.perf_counter()-start
        (out/(name+'.stdout')).write_text(p.stdout)
        (out/(name+'.stderr')).write_text(p.stderr)
        require(p.returncode == 0, name+' failed: '+p.stdout+p.stderr)
        graph = json.loads(gp.read_text())
        results.append(dict(name=name, argv=argv, binary_sha256=sha(executable), uart_sha256=sha(plugin),
                            elf_sha256=sha(elf), fixture_sha256=sha(fp), graph_sha256=sha(gp),
                            stdout_sha256=sha(out/(name+'.stdout')), stderr_sha256=sha(out/(name+'.stderr')),
                            host_seconds=elapsed, retired_instructions=graph['retired_instructions'],
                            simulated_mips=sum(graph['retired_instructions'])/elapsed/1e6))
        results[-1]['pass'] = True
        return p.stdout, graph

    optimized = run('pure', streams, pure)
    baseline = run('conservative', streams, conservative)
    primary = run('primary-conservative', streams, conservative, primary=True)
    require(baseline[0] == primary[0], 'pipeline-disabled behavior differs from frozen primary')
    before, after = [rows(v[0], 'PIPELINE_CASE ') for v in (baseline, optimized)]
    require(len(before) == len(after) == 12, 'missing per-hart/directed stream')
    for a, b in zip(before, after):
        require({k:v for k,v in a.items() if k!='cycles'} == {k:v for k,v in b.items() if k!='cycles'},
                'functional/counter retirement mismatch between adapters')
        require(b['cycles'] < a['cycles'] if b['hart'] < 2 or args.rocket_pipeline else b['cycles'] == a['cycles'],
                'Shuttle overlap missing or Rocket timing changed')
    for hart in (0,1):
        r = {(v['hart'],v['kind']):v for v in after}
        require(r[hart,0]['cycles'] < r[hart,1]['cycles'], 'RAW does not change throughput')
    graph = optimized[1]
    events = {e['id']:e for e in graph['events']}
    metadata = graph['shuttle_pipeline']
    require(metadata['enabled'] is True and metadata['calibrated'] is False, 'incorrect pipeline status')
    require(metadata['peak_packets'] == [4,4,0], 'multiple live packets not demonstrated')
    table = symbols(streams)
    pure_instructions = metadata['instructions']
    require(pure_instructions, 'pipeline records missing')
    retimed_without_raw = 0
    same_cycle_retire = {}
    for row in pure_instructions:
        require(row['hart'] < 2 and row['retired'] and row['released'] and not row['latched_exception'], 'incomplete pure instruction')
        result, commit, wb = [events[row[name]] for name in ('result_node','COM_node','WB_node')]
        divider = graph['hart_cycle_dividers'][row['hart']]
        if row.get('counter_read',False):
            require(args.counter_pipeline and row['lane']==0 and row['result_node']==row['COM_node'] and row['result_stage']=='COM',
                    'counter result/pairing differs from source')
            require(commit['end']==row['EX_release']+2*divider and wb['end']==commit['end']+divider,
                    'counter EX/COM/WB phase mismatch')
            continue
        require(result['end'] == row['RRD']+divider*(1 if row['result_stage']=='EX' else 2), 'result-ready phase mismatch')
        require(commit['end'] == row['RRD']+3*divider and wb['end'] == row['RRD']+4*divider, 'COM/WB phase mismatch')
        require(result['end'] <= commit['start'] and commit['end'] <= wb['start'], 'stage causality violated')
        require(result['pc'] == commit['pc'] == wb['pc'] == row['pc'], 'instruction attribution mismatch')
        require((row.get('expanded',row['raw']) & 0x7f) in (0x13,0x1b,0x33,0x3b,0x17,0x37), 'non-pure instruction batched')
        if table['unused_field_begin'] <= row['pc'] < table['unused_field_end'] and row['raw']&0x7f==0x37:
            if row['result_stage']=='MEM' and not row['raw_producers']:
                retimed_without_raw += 1
        key = row['hart'], commit['end']
        same_cycle_retire[key] = same_cycle_retire.get(key, 0)+1
    require(retimed_without_raw > 0, 'unused RTL source fields did not retime LUI')
    require(max(same_cycle_retire.values()) == 2, 'actual COM dual retirement missing')
    if args.rocket_pipeline:
        rocket=graph['rocket_pipeline'];require(rocket['enabled'] and rocket['peak_packets']==3,'Rocket overlapping single-issue stages missing')
        retirement_edges=set();body_ops={}
        for row in rocket['instructions']:
            require(row['hart']==2 and row['retired'] and row['released'] and not row['latched_exception'],'incomplete Rocket operation')
            ex,mem,wb=[events[row[key]] for key in ('EX_node','MEM_node','WB_node')];divider=graph['hart_cycle_dividers'][2]
            require((ex['start'],ex['end'],mem['start'],mem['end'],wb['start'],wb['end'])==tuple(row['ID']+n*divider for n in (0,1,1,2,2,3)),
                    'Rocket stage boundaries changed')
            require(row['result_node']==row['WB_node'] if row['counter_read'] else row['result_node']==row['EX_node'],'Rocket result readiness wrong')
            require(wb['end'] not in retirement_edges,'Rocket retired more than one instruction per edge');retirement_edges.add(wb['end'])
            body_ops.setdefault(row['pc'],[]).append(row)
        for name in ('independent','dependent'):
            body=[row for row in rocket['instructions'] if table[name+'_begin']<=row['pc']<table[name+'_end']]
            require(len(body)==512 and all(b['ID']-a['ID']==graph['hart_cycle_dividers'][2] for a,b in zip(body,body[1:])),
                    'Rocket pure-ALU issue did not sustain1 per hart edge')
    seq = run('seed17', streams, pure, 17)
    replay = run('seed17-repeat', streams, pure, 17)
    require(seq == replay, 'recorded-seed replay differs')
    irq_text, irq_graph = run('precision', precision, pure.replace('hart 2 2 1','hart 2 1 1').replace('rule 2 0 0 scalar2 3 1','rule 2 0 0 scalar2 1 1'))
    directed = rows(irq_text, 'PIPELINE_PRECISION ')
    require(len(directed)==1 and directed[0]['failed']==0, 'precise trap guest failed')
    labels = symbols(precision)
    sentinels = [r for r in irq_graph['shuttle_pipeline']['instructions'] if r['latched_exception']]
    require(len(sentinels)==2 and all(not r['retired'] and r['released'] for r in sentinels), 'IPI/timer sentinel retirement invalid')
    ievents = {e['id']:e for e in irq_graph['events']}
    ipi = next(r for r in sentinels if r['pc']==directed[0]['ipi_pc'])
    pulse_clear = next(e for e in irq_graph['events'] if e['hart']==2 and e['pc']==labels['pulse_clear'])
    require(ipi['RRD'] < pulse_clear['end'] < ievents[ipi['COM_node']]['end'], 'IRQ line did not clear between capture and COM')
    edge = [r for r in irq_graph['shuttle_pipeline']['instructions'] if r['pc']==0x7003fffc]
    require(len(edge)==1 and edge[0]['retired'], 'last mapped TCM instruction not committed')
    require(not any(r['pc']==labels['illegal_pc'] for r in irq_graph['shuttle_pipeline']['instructions']), 'illegal instruction entered pure pipeline')
    alu_program = corpus()
    alu_assembly = out/'alu-corpus.S'
    alu_assembly.write_text(assembly(alu_program))
    (out/'alu-program.json').write_text(json.dumps(alu_program,indent=2)+'\n')
    alu_elf = build('alu-corpus', ['benchmarks/start.S','benchmarks/runtime.c','pipeline/alu_guest.c',alu_assembly])
    alu_symbols = symbols(alu_elf)
    expected_registers = evaluate(alu_program,alu_symbols['alu_corpus_begin'])
    for name, fixture in [('alu-pure',pure),('alu-conservative',conservative)]:
        text, trace = run(name,alu_elf,fixture)
        actual = rows(text,'PIPELINE_ALU ')
        require(len(actual)==3 and {r['hart'] for r in actual}=={0,1,2} and
                all(r['registers']==expected_registers for r in actual), 'independent full-RV64I ALU oracle mismatch: '+name)
        if name=='alu-pure':
            for hart in (0,1):
                observed = [r for r in trace['shuttle_pipeline']['instructions'] if r['hart']==hart and
                            alu_symbols['alu_corpus_begin']<=r['pc']<alu_symbols['alu_corpus_end']]
                require(len(observed)==len(alu_program['instructions']), 'ALU corpus instruction escaped the pure subset')
                require([r['raw'] for r in observed]==[r['word'] for r in alu_program['instructions']], 'ALU corpus trace attribution differs from independent encoding')

    rvc_evidence = None
    if args.rvc:
        require((args.source.resolve()/'riscv/iris_shuttle_rvc.h').read_bytes()==(ROOT/'pipeline/rvc.hpp').read_bytes(),
                'native compressed expander differs from RTL-checked source')
        proof=ROOT/'build/pipeline-rvc-source-check/results.json'
        evidence=json.loads(proof.read_text())
        require(evidence['status']=='passed_exhaustive_RVC_ALU_expansion' and
                evidence['source_sha256']['pipeline/rvc.hpp']==sha(ROOT/'pipeline/rvc.hpp'), 'RVC RTL proof is stale')
        program=rvc_corpus.corpus();source=out/'rvc-corpus.S';source.write_text(rvc_corpus.assembly(program))
        (out/'rvc-program.json').write_text(json.dumps(program,indent=2)+'\n')
        elf=build('rvc-corpus',['benchmarks/start.S','benchmarks/runtime.c','pipeline/rvc_guest.c',source])
        table=symbols(elf)
        reference_rows=None
        for name,fixture in [('rvc-pure',pure),('rvc-conservative',conservative)]:
            text,trace=run(name,elf,fixture)
            actual=rows(text,'PIPELINE_RVC ')
            require(len(actual)==3 and {r['hart'] for r in actual}=={0,1,2},'compressed per-hart corpus missing')
            if reference_rows is None:
                reference_rows=actual
            else:
                require(actual==reference_rows,'compressed initial SP or final register state differs from conservative execution')
            for row in actual:
                require(len(row['registers'])==17 and row['registers']==rvc_corpus.evaluate(program,row['registers'][15]),
                        'independent compressed register/SP oracle mismatch: '+name+' hart='+str(row['hart']))
            if name=='rvc-pure':
                for hart in (0,1):
                    observed=[r for r in trace['shuttle_pipeline']['instructions'] if r['hart']==hart and
                              table['rvc_corpus_begin']<=r['pc']<table['rvc_corpus_end']]
                    require(len(observed)==len(program['instructions']),'compressed corpus escaped the pure pipeline')
                    pc=table['rvc_corpus_begin']
                    for row,op in zip(observed,program['instructions']):
                        require(row['pc']==pc and row['raw']==op['word'] and row['length']==op['length'],
                                'mixed16/32 instruction frontier or raw attribution mismatch')
                        pc+=op['length']
                    require(pc==table['rvc_corpus_end'],'mixed16/32 frontier ended at the wrong address')
        rvc_evidence=dict(source_rtl_proof_sha256=sha(proof),program_sha256=sha(out/'rvc-program.json'),
                          assembly_sha256=sha(source),compressed_instructions=2048,total_mixed_instructions=len(program['instructions']),
                          covered_names=rvc_corpus.NAMES,compared_register_values=2*3*17)
        edge_elf=build('rvc-edge',['benchmarks/start.S',runtime,'pipeline/rvc_edge_guest.c','pipeline/rvc_edge.S'])
        edge_text,edge_graph=run('rvc-edge',edge_elf,pure)
        edge_results=rows(edge_text,'PIPELINE_RVC_EDGE ')
        require(len(edge_results)==1 and edge_results[0]['failed']==0,'compressed edge/reserved trap guest failed')
        edge_rows=[r for r in edge_graph['shuttle_pipeline']['instructions'] if r['pc']==0x7003fffe]
        require(len(edge_rows)==1 and edge_rows[0]['raw']==0xe05 and edge_rows[0]['length']==2 and edge_rows[0]['retired'],
                'last mapped compressed instruction did not commit precisely')
        reserved=symbols(edge_elf)['rvc_reserved_pc']
        require(not any(r['pc']==reserved for r in edge_graph['shuttle_pipeline']['instructions']),
                'reserved compressed instruction entered the pure pipeline')

    for name, fixture, expected in [
            ('unknown-mode', pure.replace(mode,'magic'), 'unsupported experimental Shuttle pipeline fixture'),
            ('duplicate-mode', pure+'shuttle_pipeline '+mode+'\n', 'unsupported experimental Shuttle pipeline fixture'),
            ('false-certification', pure.replace('uncalibrated-integration-fixture','calibrated'), 'only explicit uncalibrated integration fixtures')]:
        fp = out/(name+'.fixture'); fp.write_text(fixture)
        argv = command(binary, streams)
        argv = ['--extlib='+str(uart) if a.startswith('--extlib=') else a for a in argv]
        argv.insert(-1, '--iris-timing-fixture='+str(fp))
        p = subprocess.run(argv, text=True, capture_output=True, env=env, timeout=10)
        (out/(name+'.stderr')).write_text(p.stderr)
        require(p.returncode!=0 and expected.lower() in p.stderr.lower(), 'fixture did not fail closed: '+name+' '+p.stderr)
        negatives.append(dict(name=name, argv=argv, exit_status=p.returncode, fixture_sha256=sha(fp), stderr_sha256=sha(out/(name+'.stderr'))))

    native_build = args.native_build.resolve()
    native_source = ROOT/'pipeline/test_context.cpp'
    host_compiler = Path(shutil.which('g++')).resolve()
    native_command = [str(host_compiler), '-std=c++20', '-O2', '-iquote', str(native_build)]
    if args.rvc:
        native_command.append('-DIRIS_TEST_RVC')
    if args.rocket_pipeline:native_command.append('-DIRIS_TEST_SPLIT_FETCH')
    for directory in ('','riscv','fesvr','fdt'):
        native_command += ['-iquote', str(args.source.resolve()/directory)]
    native_command += [str(native_source), '-L'+str(native_build), '-lriscv', '-ldisasm', '-lsoftfloat', '-lfesvr', '-lfdt', '-lpthread',
                       '-o', str(out/'test_context')]
    p = subprocess.run(native_command, capture_output=True, text=True)
    (out/'context.build.log').write_text(p.stdout+p.stderr)
    require(p.returncode==0, 'actual native processor guard build failed: '+p.stderr)
    p = subprocess.run([str(out/'test_context')], capture_output=True, text=True, timeout=10)
    (out/'context.stdout').write_text(p.stdout); (out/'context.stderr').write_text(p.stderr)
    require(p.returncode==0 and 'PASS actual processor' in p.stdout, 'actual native processor guard test failed')
    native_test = dict(argv=native_command, exit_status=p.returncode, executable_sha256=sha(out/'test_context'),
                       host_compiler_sha256=sha(host_compiler), stdout_sha256=sha(out/'context.stdout'),
                       library_sha256={name:sha(native_build/name) for name in
                                       ('libriscv.a','libdisasm.a','libsoftfloat.a','libfesvr.a','libfdt.a')})
    source_names = ['pipeline/check.py','pipeline/test_context.cpp','pipeline/alu_corpus.py','pipeline/alu_guest.c','pipeline/guest.c','pipeline/streams.S','pipeline/irq_guest.c','pipeline/irq_streams.S','pipeline/pure.fixture',
                    'spike/run_functional.py',
                    str(args.parent_overlay.resolve().relative_to(ROOT)),'timing/PIPELINED_SHUTTLE.md','pipeline/evidence/source-design.json']
    # Retain actual compiled timing dependencies. A broad directory glob also
    # binds unrelated router experiments which cannot affect this native.
    for dependency in native_build.glob('*.d'):
        for word in dependency.read_text().replace('\\\n',' ').split()[1:]:
            if word.endswith(':'):continue
            path=(native_build/word).resolve()
            if path.is_file() and path.is_relative_to(ROOT/'timing'):
                source_names.append(str(path.relative_to(ROOT)))
    if args.rvc:
        source_names += ['pipeline/rvc.hpp','pipeline/rvc_corpus.py','pipeline/rvc_guest.c','pipeline/rvc_edge.S','pipeline/rvc_edge_guest.c',
                         'build/pipeline-rvc-source-check/results.json']
    source_names += [str((args.guest_root.resolve()/p).relative_to(ROOT)) for p in
                     ('benchmarks/start.S','benchmarks/runtime.c','benchmarks/runtime.h','benchmarks/link.ld')]
    checkout = args.source.resolve()
    changed = subprocess.check_output(['git','-C',str(checkout),'diff','--name-only'],text=True).splitlines()
    if 'riscv/iris_shuttle_issue.cc' not in changed:
        changed.append('riscv/iris_shuttle_issue.cc')
    for name in changed:
        source_names.append(str((checkout/name).relative_to(ROOT)))
    patch = ''
    parent_sources = args.parent_source.resolve()
    require(subprocess.check_output(['git','-C',str(parent_sources),'rev-parse','HEAD'],text=True).strip() ==
            '72958551566a30f19444bd7e354552824e4d0a98', 'parent source pin mismatch')
    require(subprocess.check_output(['git','-C',str(parent_sources),'diff','--binary','HEAD']) == args.parent_overlay.read_bytes(),
            'parent source differs from the explicit prerequisite overlay; include intent-to-add source files')
    for name in changed:
        old = (parent_sources/name).read_text().splitlines(True) if (parent_sources/name).exists() else []
        new = (checkout/name).read_text().splitlines(True)
        if old != new:
            patch += ''.join(difflib.unified_diff(old, new, fromfile='a/'+name if old else '/dev/null', tofile='b/'+name))
    extension=out/'pipeline-on-parent-epoch.patch'
    extension.write_text(patch)
    require(sha(binary)==binary_hash and sha(uart)==uart_hash, 'binary/plugin changed during tests')
    receipt = dict(schema='iris.shuttle.live_pipeline.v1', status='passed_directed_integration', calibrated=False,
                   rtl_certified=False, held_out_2pct=False, binary_sha256=binary_hash, uart_sha256=uart_hash,
                   base_git_sha=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip(),
                   prerequisite_primary_overlay_sha256=sha(args.parent_overlay), extension_patch_sha256=sha(extension),
                   source_sha256={n:sha(ROOT/n) for n in sorted(set(source_names))}, compiler_sha256=sha(compiler),
                   compiler_version=subprocess.check_output([str(compiler),'--version'],text=True).splitlines()[0], build_commands=commands,
                   results=results, negative_results=negatives, native_context_test=native_test,
                   compressed_alu_corpus=rvc_evidence,private_forwarded_values=args.private_values,
                   alu_corpus=dict(seed=alu_program['seed'],instructions=len(alu_program['instructions']),covered_names=NAMES,
                                   independent_expected_registers=expected_registers,source_sha256=sha(alu_assembly),
                                   program_sha256=sha(out/'alu-program.json'),compared_register_values=2*3*len(expected_registers)),
                   peak_packets=metadata['peak_packets'], retimed_LUI_without_RAW=retimed_without_raw,
                   streams=after, trap_results=directed[0], irq_capture=ipi['RRD'], irq_line_clear=pulse_clear['end'], irq_COM=ievents[ipi['COM_node']]['end'],
                   scope='Live RV64I32 pure ALUs on Shuttle0/1, sequential-frontend fixture, exact program-order Spike effects at COM; no frontend/cache/vector/VME/RTL calibration.')
    (out/'results.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':receipt['status'],'receipt':str(out/'results.json'),'positive_runs':len(results),'negative_runs':len(negatives)}))


if __name__=='__main__':
    main()

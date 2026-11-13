#!/usr/bin/env python3
"""New source-bound coupling of frozen OPU sequencer and whole-array objects."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    seq = ROOT / 'build/opu-sequencer-native-v3'
    array = ROOT / 'build/opu-array-rtl-proof-v2-pipelined'
    s_header = (seq / 'model/VOPUSequencer.h').read_text()
    a_header = (array / 'model/VOuterArray.h').read_text()
    used_seq = set()
    used_array = set()
    backend_sv = ROOT / 'build/rtl-verilator/gen-collateral/VectorBackend.sv'
    backend = backend_sv.read_text()
    # Copy exact register statements from the co-located generated Backend.
    regs = []
    for match in re.finditer(r'^\s*reg\s+(\[[^\]]+\]\s+)?(vopu_ctrl_reg_\w+);', backend, re.M):
        width, name = match.groups()
        if name.startswith(('vopu_ctrl_reg_in_l_', 'vopu_ctrl_reg_in_t_')):
            continue  # Matrix arithmetic/move-in VRF operands are outside this readout-only cut.
        assignment = re.findall(r'^\s*' + re.escape(name) + r'\s*<=\s*(_vos_io_iss_bits_\w+);[^\n]*', backend, re.M)
        if len(assignment) != 1:
            raise ValueError('Backend register is not an exact unconditional assignment: ' + name)
        regs.append((width or '', name, assignment[0]))
    source_capture = 'vrf_io_pipe_writes_2_bits_data_r <= {_vopu_io_out_3, _vopu_io_out_2, _vopu_io_out_1, _vopu_io_out_0};'
    if source_capture not in backend or 'if (_vos_io_write_reg_enable)' not in backend:
        raise ValueError('Actual Backend readout register expression changed')
    ports = ['input clock', 'input _vos_io_write_reg_enable']
    ports += ['input [31:0] _vopu_io_out_' + str(i) for i in range(4)]
    for width, name, rhs in regs:
        ports += ['input ' + width + rhs, 'output reg ' + width + name]
    ports += ['output reg [127:0] vrf_io_pipe_writes_2_bits_data_r']
    glue_sv = out / 'IrisColumnBackendRegisters.sv'
    glue_sv.write_text('module IrisColumnBackendRegisters(\n' + ',\n'.join(ports) + '\n);\nalways @(posedge clock) begin\n' +
                       '\n'.join(name + ' <= ' + rhs + ';' for width, name, rhs in regs) +
                       '\nif (_vos_io_write_reg_enable)\n' + source_capture + '\nend\nendmodule\n')
    tool_env = Path('/scratch/eygao/iris-cy/.conda-env')
    env = dict(os.environ, PATH=str(tool_env / 'bin') + os.pathsep + os.environ['PATH'])
    glue_argv = [str(tool_env / 'bin/verilator'), '--cc', '--build', '--top-module',
                 'IrisColumnBackendRegisters', '--prefix', 'VColumnBackendRegs',
                 '-Mdir', str(out / 'glue-model'), '-Wno-fatal', '-O3', str(glue_sv)]
    glue_build = subprocess.run(glue_argv, capture_output=True, env=env)
    (out / 'glue-build.stdout').write_bytes(glue_build.stdout)
    (out / 'glue-build.stderr').write_bytes(glue_build.stderr)
    if glue_build.returncode:
        raise ValueError('Exact Backend register cut build failed')

    def sf(name):
        if name not in s_header:
            raise ValueError('Missing actual source sequencer port ' + name)
        used_seq.add(name)
        return 'seq.' + name

    def af(name):
        if name not in a_header:
            raise ValueError('Missing actual full array port ' + name)
        used_array.add(name)
        return 'array.' + name

    bindings = 'std::array<IData*,4> out{{' + ','.join('&' + af('io_out_' + str(i)) for i in range(4)) + '}};\n'
    bindings += 'Controls snapshot(){Controls c;\n'
    fields = [('mrf', 'mrf_idx'), ('row', 'row_idx'), ('col', 'col_idx'),
              ('macc', 'macc'), ('zero', 'zero'), ('mvin', 'mvin'),
              ('mvin_col', 'mvin_col'), ('mv_en', 'mv_en')]
    for member, port in fields:
        for i in range(4):
            bindings += 'c.' + member + '[' + str(i) + ']=' + sf('io_iss_bits_' + port + '_' + str(i)) + ';\n'
    for i in range(1, 4):
        bindings += 'c.shift[' + str(i) + ']=' + sf('io_iss_bits_shift_' + str(i)) + ';\n'
    for member, port in [('row_en', 'row_en'), ('col_en', 'col_en')]:
        for i in range(4):
            for j in range(4):
                bindings += 'c.' + member + '[' + str(i) + '][' + str(j) + ']=' + sf('io_iss_bits_' + port + '_' + str(i) + '_' + str(j)) + ';\n'
    scalar = ('signed_l', 'signed_t', 'fp8', 'e5m2_l', 'e5m2_t', 'rm')
    for name in scalar:
        bindings += 'c.' + name + '=' + sf('io_iss_bits_' + name) + ';\n'
    bindings += 'return c;}\nvoid drive(const Controls&c){\n'
    for member, port in fields:
        for i in range(4):
            bindings += af('io_op_' + port + '_' + str(i)) + '=c.' + member + '[' + str(i) + '];\n'
    for i in range(1, 4):
        bindings += af('io_op_shift_' + str(i)) + '=c.shift[' + str(i) + '];\n'
    for member, port in [('left', 'in_l'), ('top', 'in_t'), ('row_en', 'row_en'), ('col_en', 'col_en')]:
        for i in range(4):
            for j in range(4):
                bindings += af('io_op_' + port + '_' + str(i) + '_' + str(j)) + '=c.' + member + '[' + str(i) + '][' + str(j) + '];\n'
    for name in scalar:
        bindings += af('io_op_' + name) + '=c.' + name + ';\n'
    bindings += '}\n'
    bindings += 'void glue_inputs(){\n'
    for width, name, rhs in regs:
        bindings += 'glue.' + rhs + '=' + sf(rhs.removeprefix('_vos_')) + ';\n'
    bindings += 'glue._vos_io_write_reg_enable=seq.io_write_reg_enable;\n'
    for i in range(4):
        bindings += 'glue._vopu_io_out_' + str(i) + '=*out[' + str(i) + '];\n'
    bindings += '}\nvoid glue_compare(const Controls&c){\n'
    for width, name, rhs in regs:
        suffix = name.removeprefix('vopu_ctrl_reg_')
        found = False
        for member, port in fields + [('shift', 'shift')]:
            if suffix.startswith(port + '_') and suffix[len(port) + 1:].isdigit():
                expression = 'c.' + member + '[' + suffix[len(port) + 1:] + ']'
                found = True
                break
        if not found:
            for member in ('row_en', 'col_en'):
                if suffix.startswith(member + '_'):
                    i, j = suffix[len(member) + 1:].split('_')
                    expression = 'c.' + member + '[' + i + '][' + j + ']'
                    found = True
                    break
        if not found and suffix in scalar:
            expression = 'c.' + suffix
            found = True
        if not found:
            raise ValueError('Unmodeled source Backend register ' + name)
        bindings += 'if(' + expression + '!=glue.' + name + ')throw std::runtime_error("source Backend control register mismatch");++backend_register_checks;\n'
    bindings += '}\n'
    (out / 'vme_column_history_bindings.inc').write_text(bindings)
    # Every actual numeric/control array input must be accounted for explicitly.
    ports = re.findall(r'VL_IN\d*\(&([^,]+),', a_header)
    require_ports = set(ports) - {'clock', 'reset'}
    if require_ports != used_array - {'io_out_' + str(i) for i in range(4)}:
        raise ValueError('Unbound or invented array inputs ' + repr(require_ports ^ used_array))
    cases = []
    for col in range(2):
        for tile in range(4):
            for index in range(32):
                for policy in range(4):
                    cases.append((policy, [(col, tile, index, 8)]))
    for index in range(32):
        for first_col, second_col in ((1, 1), (1, 0), (0, 1)):
            for policy in range(2):
                cases.append((policy, [(first_col, 2, index, 8),
                                       (second_col, 3, (index + 11) % 32, 16)]))
    (out / 'scenarios.txt').write_text(''.join(' '.join(map(str, [i, p, len(c), *[x for row in c for x in row]])) + '\n' for i, (p, c) in enumerate(cases)))
    cases_json = [dict(id=i, availability_policy=p, commands=[dict(column=x[0], tile=x[1], index=x[2], vd=x[3]) for x in c]) for i, (p, c) in enumerate(cases)]
    (out / 'scenarios.json').write_text(json.dumps(cases_json, indent=2) + '\n')
    tool = Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
    argv = ['/usr/bin/g++', '-std=c++20', '-O2', '-I' + str(out), '-I' + str(seq / 'model'),
            '-I' + str(array / 'model'), '-I' + str(tool), '-I' + str(tool / 'vltstd'),
            '-I' + str(out / 'glue-model'),
            str(ROOT / 'timing/vme_column_history.cpp'), str(seq / 'model/VOPUSequencer__ALL.a'),
            str(array / 'model/VOuterArray__ALL.a'), str(seq / 'model/verilated.o'),
            str(out / 'glue-model/VColumnBackendRegs__ALL.a'),
            str(seq / 'model/verilated_threads.o'), '-pthread',
            '-L/scratch/eygao/iris-cy/.conda-env/lib',
            '-Wl,-rpath,/scratch/eygao/iris-cy/.conda-env/lib', '-lstdc++',
            '-o', str(out / 'check')]
    start = time.monotonic()
    r = subprocess.run(argv, capture_output=True)
    (out / 'build.stdout').write_bytes(r.stdout)
    (out / 'build.stderr').write_bytes(r.stderr)
    if r.returncode:
        raise ValueError('Component consumer build failed')
    inputs = {str(p): sha(p) for p in (Path(__file__), ROOT / 'timing/vme_column_history.cpp',
              ROOT / 'hardware/evidence/outer-product-unit.scala',
              ROOT / 'hardware/evidence/outer-product-sequencer.scala',
              Path('/scratch/eygao/iris-cy/generators/saturn/src/main/scala/backend/Backend.scala'),
              Path('/scratch/eygao/iris-cy/.conda-env/lib/libstdc++.so.6'),
              seq / 'model/VOPUSequencer.h', array / 'model/VOuterArray.h',
              tool / 'verilated.h',
              backend_sv, glue_sv, tool_env / 'bin/verilator', tool_env / 'bin/verilator_bin',
              seq / 'build.json', array / 'results.json', out / 'vme_column_history_bindings.inc',
              out / 'scenarios.json', out / 'scenarios.txt')}
    for token in argv:
        q = Path(token)
        if q.is_file():
            inputs[str(q)] = sha(q)
    for name, digest in json.loads((array / 'results.json').read_text())['input_sha256'].items():
        if name.endswith('.sv'):
            if sha(name) != digest:
                raise ValueError('Frozen actual array source changed')
            inputs[name] = digest
    for name, digest in json.loads((seq / 'build.json').read_text())['input_sha256'].items():
        if name.endswith('.sv'):
            if sha(name) != digest:
                raise ValueError('Frozen actual sequencer source changed')
            inputs[name] = digest
    record = dict(schema='iris.vme_column_history_component_build.v1', status='built',
                  argv=argv, input_sha256=inputs, binary_sha256=sha(out / 'check'),
                  scenarios=len(cases), all_target_RTL_objects_unchanged=True,
                  backend_glue='source-transcribed unconditional controlReg and RegEnable vertical readout',
                  backend_exact_SV_glue_differential=True, backend_glue_build_argv=glue_argv,
                  useOpuColReadout=False, full_VRF_arbiter_modeled=False,
                  physical_array_initialization='4096 words through public mvin ports, full physical readback',
                  source_OPU='hardware/evidence/outer-product-unit.scala; actual snapshot gated_clock=clock',
                  old_OPU_clock_gate_variant_is_not_claimed=True,
                  host_seconds=time.monotonic() - start, hardware_contacted=False)
    (out / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(dict(status='built', scenarios=len(cases), binary_sha256=record['binary_sha256'])))


if __name__ == '__main__':
    main()

"""Check 18 real observations and dispatch boundaries, then exact output/phase gates."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, '/scratch/copparihollmann/merlin-gather-compat-integration-v1/src')
from build import sha


def dispatches(text):
    frames, trials, kept, group = {}, {}, [], None
    for line in text.splitlines():
        if line.startswith('ATTN_GROUP '):
            group = tuple(map(int, line.split()[1:]))
        if line.startswith('ATTN_DISPATCH v1 '):
            values = list(map(int, line.split()[2:]))
            if len(values) != 5:
                raise ValueError('Bad dispatch frame')
            case, route, rep, begin, end = values
            key = (case, route, rep)
            if group != (case, route) or key in frames or begin < 0 or end <= begin:
                raise ValueError('Wrong group, duplicate or invalid dispatch interval')
            frames[key] = (begin, end)
        elif line.startswith('ATTN_DISPATCH'):
            raise ValueError('Unknown dispatch marker')
        else:
            kept.append(line)
            if line.startswith('ATTN_TRIAL '):
                values = line.split()[1:]
                if len(values) != 22 or group is None:
                    raise ValueError('Bad trial frame')
                key = (group[0], int(values[0]), int(values[1]))
                if key in trials:
                    raise ValueError('Duplicate trial')
                trials[key] = (int(values[14]), int(values[19]))
    expected = {(c, r, p) for c in range(3) for r in range(2) for p in range(3)}
    if set(frames) != expected or set(trials) != expected:
        raise ValueError('Exactly 18 trial and dispatch boundaries required')
    last = -1
    for r in range(2):
        for c in range(3):
            for p in range(3):
                begin, end = frames[c, r, p]
                inner_begin, inner_end = trials[c, r, p]
                if not last <= begin <= inner_begin <= inner_end <= end:
                    raise ValueError('Non-nested or overlapping whole-operation boundaries')
                last = end
    return frames, '\n'.join(kept)+'\n'


def qualify(packet, console, output, semantics):
    output.mkdir(parents=True, exist_ok=False)
    result = dict(pass_=False, trials=0, production_failure_retest_required=True,
                  hardware_performance_qualified=False, physical_busy=None, certified_cold=False)
    try:
        build = json.loads((packet/'build-receipt.json').read_text())
        if sha(build['elf']) != build['elf_sha256']:
            raise ValueError('ELF changed')
        for p, h in build['input_sha256'].items():
            if sha(p) != h:
                raise ValueError('Source changed: '+p)
        raw = console.read_bytes()
        text = io.TextIOWrapper(io.BytesIO(raw), encoding='utf-8', newline=None).read()
        frames, normalized = dispatches(text)
        (output/'attention-only.console').write_text(normalized)
        spec = importlib.util.spec_from_file_location('attention_three_pass_reader', packet/'readers/postgate.py')
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        numerical = reader.check(output/'attention-only.console', output/'numerical', semantics, packet/'build-receipt.json')
        if not numerical['pass'] or numerical['trials'] != 18:
            raise ValueError('Numerical/phase gate failed: '+str(numerical.get('error')))
        (output/'dispatch-windows.json').write_text(json.dumps([
            dict(case=c, route=r, pass_id=p, whole_dispatch_ticks=z-a)
            for (c, r, p), (a, z) in frames.items()], indent=2)+'\n')
        result.update(pass_=True, trials=18, host_full_output_certificates=numerical['host_full_output_certificates'],
                      phase_windows=numerical['phase_windows'], ELF_sha256=build['elf_sha256'],
                      console_sha256=hashlib.sha256(raw).hexdigest(), reader_sha256=sha(__file__),
                      numerical_report_sha256=sha(output/'numerical/report.json'),
                      normalization='Only validated H2 dispatch-mtime metadata removed; all actual 3-pass numerical values/order preserved.')
    except Exception as exc:
        result['error'] = repr(exc)
    (output/'report.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)
    return result['pass_']


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--packet', type=Path, required=True)
    p.add_argument('--console', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--counter-semantics', choices=['target_mcycle_uncalibrated', 'instruction_count_not_modeled_cycles'], required=True)
    args = p.parse_args()
    sys.exit(0 if qualify(args.packet, args.console, args.output, args.counter_semantics) else 1)

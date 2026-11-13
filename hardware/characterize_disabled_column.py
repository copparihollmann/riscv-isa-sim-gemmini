#!/usr/bin/env python3
"""Characterize the recorded isolated column probe; never enable emulation.

The configured OPU has no horizontal readout. During contiguous move issue,
the backend's vertical-pipe capture observes later controls, or idle controls.
This finite source-derived rule is deliberately restricted to the original
linear-tile, VL32, isolated eight-issue probe. It is not a general ISA rule:
VRF scheduling and competing work can change which controls are sampled.
"""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''): digest.update(block)
    return digest.hexdigest()


def sampled_cell(index, destination_group, lane):
    """One word in the isolated probe, from the disabled horizontal path.

    Four physical cluster rows/columns, four cells per cluster dimension.
    The OPU register and backend capture account for two of the source
    sequencer's (yDim+1-position) stages. The remaining delay selects a later
    issue. In an idle issue slot, controls select tile0/subtile0/cell(0,0);
    the backend still reads the last vertical cluster row.
    """
    if (type(index) is not int or not 0 <= index < 32
            or type(destination_group) is not int or not 0 <= destination_group < 8
            or type(lane) is not int or not 0 <= lane < 4):
        raise ValueError('Exact isolated32-element probe coordinates required')
    source_issue = destination_group + 3 - (index & 3)
    if source_issue >= 8:
        return {'source_issue': None, 'sample': 'idle_controls', 'tile': 0, 'row': 3, 'column': lane}
    return {'source_issue': source_issue, 'sample': 'later_or_same_move_controls', 'tile': 0,
            'row': (source_issue // 4) * 16 + ((index // 4) & 3) * 4 + 3,
            'column': (index // 16) * 16 + (source_issue % 4) * 4 + lane}


def fnv(words):
    result = 14695981039346656037
    for word in words:
        for byte in range(4): result = ((result ^ ((word >> (8 * byte)) & 255)) * 1099511628211) & ((1 << 64) - 1)
    return result


def compare(rows):
    if not isinstance(rows, list) or len(rows) != 384:
        raise ValueError('Complete384 actual column observations required')
    expected = set(itertools.product(range(2), range(3), range(2), range(32)))
    seen, details = set(), []
    for record in rows:
        names = ('hart', 'trial_id', 'pattern', 'index')
        if not isinstance(record, dict) or any(type(record.get(k)) is not int for k in names):
            raise ValueError('Typed observation coordinates required')
        key = tuple(record[k] for k in names)
        if key not in expected or key in seen: raise ValueError('Duplicate or unexpected observation')
        seen.add(key)
        words = record.get('words')
        if (record.get('vl') != 32 or record.get('illegal_delta') != 0
                or record.get('outcome') != 'accepted_other_data' or not isinstance(words, list)
                or len(words) != 32 or any(type(w) is not int or not 0 <= w < 1 << 32 for w in words)
                or type(record.get('checksum')) is not int or record['checksum'] != fnv(words)):
            raise ValueError('Actual complete nontrapping probe words/checksum required')
        hart, trial, pattern, index = key
        base = 0x12000000 + (hart << 20) + (pattern << 16) + (trial << 12)
        for element, word in enumerate(words):
            cell = sampled_cell(index, element // 4, element % 4)
            predicted = base + cell['row'] * 64 + cell['column']
            if predicted != word: raise ValueError('Source-derived isolated-probe rule does not match actual words')
            details.append(dict(zip(names, key), element=element, observed=word,
                                predicted=predicted, **cell))
    if seen != expected: raise ValueError('Missing actual observation')
    return details


def evidence(path, fragments):
    text = path.read_text(); lines = text.splitlines(); result = []
    for fragment in fragments:
        matches = [i + 1 for i, line in enumerate(lines) if fragment in line]
        if not matches: raise ValueError('Required source expression absent: ' + fragment)
        result.append({'expression': fragment, 'lines': matches})
    return {'path': str(path), 'sha256': sha(path), 'expressions': result}


def run(output):
    output = Path(output).resolve()
    if output.exists(): raise ValueError('Fresh characterization output required')
    observation = ROOT / 'hardware/actual-vme-column-observation.json'
    actual = ROOT / 'build/fpga-vme-column-probe-v1-archive-analysis/column-observations.json'
    hardware = ROOT / 'hardware/manifest.json'
    instrumentation = ROOT / 'build/firesim-observability-archived-driver-v3/report.json'
    manifest = json.loads(hardware.read_text()); observed = json.loads(observation.read_text())
    if observed['input_sha256'].get(str(actual)) != sha(actual): raise ValueError('Actual archive observation changed')
    if observed.get('source_image_association_verified') is not False:
        raise ValueError('This characterization does not establish full source/image association')
    unit = ROOT / 'hardware/evidence/outer-product-unit.scala'
    sequencer = ROOT / 'hardware/evidence/outer-product-sequencer.scala'
    params = ROOT / 'hardware/evidence/saturn-parameters.scala'
    backend = Path(manifest['repositories']['saturn']['local_path']) / 'src/main/scala/backend/Backend.scala'
    for key, path in [('outer-product-unit', unit), ('outer-product-sequencer', sequencer), ('saturn-parameters', params)]:
        if sha(path) != manifest['sources'][key]['sha256']: raise ValueError('Pinned source snapshot changed: ' + key)
    sources = [
        evidence(unit, ['cell_outs(io.row_idx)(io.col_idx)', 'io.out(j) := clusters(yDim-1)(j).io.out_pipe', 'val gated_clock = clock']),
        evidence(sequencer, ['val move_latency = ((yDim+1).U - move_cluster)', 'Mux(fire, mrf_idx, 0.U)',
            'Mux(fire, scalar_cell, 0.U)', 'Mux(fire, iter_cell, 0.U)', 'mvout_valids(i-1) && !mvout_col_pipe(i-1)',
            'io.write_reg_enable := mvout_valids(yDim)']),
        evidence(params, ['useOpuColReadout: Boolean = false']),
        evidence(backend, ['if (useOpuColReadout) Mux(vos.io.write_col', 'else vopu.get.io.out.asUInt']),
    ]
    obs = json.loads(instrumentation.read_text()); paths = [Path(k) for k in obs['input_sha256'] if k.endswith('/design/FireSim-generated.sv')]
    if len(paths) != 1 or sha(paths[0]) != obs['input_sha256'][str(paths[0])]:
        raise ValueError('Exact co-located archived-build RTL required')
    sv = paths[0]; text = sv.read_text(); start = text.index('module OuterProductUnit('); end = text.index('endmodule', start)
    if 'io_out_col' in text[start:end]: raise ValueError('This RTL has horizontal outputs; disabled-path rule is inapplicable')
    details = compare(json.loads(actual.read_text()))
    controls = []
    original = json.loads(actual.read_text())
    for kind in ('word_changed_with_valid_checksum', 'missing_observation', 'duplicate_observation', 'bool_coordinate'):
        rows = json.loads(json.dumps(original))
        if kind == 'word_changed_with_valid_checksum': rows[0]['words'][0] ^= 1; rows[0]['checksum'] = fnv(rows[0]['words'])
        elif kind == 'missing_observation': rows.pop()
        elif kind == 'duplicate_observation': rows[-1] = rows[0]
        else: rows[0]['hart'] = False
        try: compare(rows)
        except ValueError: controls.append({'case': kind, 'rejected': True})
        else: raise ValueError('Invalid characterization input accepted: ' + kind)
    output.mkdir(parents=True)
    csv_path = output / 'sampled-words.csv'
    with csv_path.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(details[0])); writer.writeheader(); writer.writerows(details)
    inputs = [Path(__file__).resolve(), observation, actual, hardware, instrumentation, unit, sequencer, params, backend, sv]
    report = {'schema': 'iris.disabled_column_isolated_probe_characterization.v1', 'pass': True,
        'actual_observations': 384, 'actual_words_compared': len(details), 'all_observed_words_match': True,
        'source_evidence': sources, 'matched_RTL_module_has_horizontal_output': False,
        'source_pins': observed['source_pins'], 'image_archive_sha256': observed['selected_image']['sha256'],
        'source_image_association_verified': False, 'hardware_contacted_by_this_analysis': False,
        'universal_functional_semantics_certified': False, 'timing_certified': False,
        'native_column_emulation_enabled': False, 'parser_corruption_controls': controls,
        'scope': 'Exact original linear-tile, isolated VL32 eight-issue probe only. Source sampling geometry predicts all retained words without a per-index lookup table.',
        'interpretation': 'Disabled horizontal readout leaves the backend sampling the vertical pipe, whose cells change with later issue or idle controls. Competing issue gaps or VRF arbitration can change the samples; arbitrary instruction emulation remains unsupported.',
        'input_sha256': {str(p): sha(p) for p in inputs}, 'output_sha256': {str(csv_path): sha(csv_path)}}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = run(args.output)
    print(json.dumps({k: result[k] for k in ('pass', 'actual_observations', 'actual_words_compared')}))

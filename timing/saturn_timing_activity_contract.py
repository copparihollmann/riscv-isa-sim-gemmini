#!/usr/bin/env python3
"""Source-bound, deliberately partial semantic qualification of activity words.

The raw activity schema is a visibility interface, not an assertion that every
unreset payload is meaningful.  This contract selects reset-controlled protocol
state and explicitly valid-qualified payload.  Unselected words remain unknown.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

R = Path(__file__).resolve().parents[1]
REF = R/'build/saturn-timing-component-v1-final'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--schema', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__), out/'builder.py')
    schema_path = args.schema.resolve()
    schema = json.loads(schema_path.read_text())
    result = {
        'schema': 'iris.saturn_activity_semantic_contract.v1',
        'input_sha256': {str(p): sha(p) for p in [Path(__file__), schema_path,
                                                               REF/'report.json']},
        'phase': 'pre-edge sample; all events commit on this exact source edge',
        'state_interval': 'State sampled before source edge E describes the interval since the preceding supplied source edge; the first sample has no preceding modeled interval. Handshakes commit at E; do not create extra edges.',
        'time': {'source_edge': 'per-hart actual supplied source-clock rising edge',
                 'uncore_tick': 'actual whole-RTL TestDriver trace_count; SDK caller metadata only',
                 'no_frequency_or_extra_edges_inferred': True},
        'qualification': {
            'reset': 'No semantic counters or unknown payload comparisons while reset=1.',
            'after_reset': 'Require an observed source edge with reset=1; resettable valid bits are then known.',
            'after_postreset_edge': 'Unreset RegNext controls need a preceding non-reset edge whose source control is qualified.',
            'payload': 'Only the listed valid-qualified fields are meaningful; inactive payload is unknown.',
            'numeric': 'Neither raw numeric values nor protocol byte masks certify initialized architectural values.',
            'unselected_fields': 'unknown; mask zero',
            'warmup': 'Only caller region policy can label warmup. Reset and actual VRF scrub are separate source events.',
            'snapshot': 'A snapshot requires external reset/definedness provenance; this contract does not infer it.'},
        'ownership': {
            'debug_id': '16-bit source counter, allocated on dis.io_dis_valid && dis.io_dis_ready; not globally unique.',
            'vat': 'finite source slot, reused after releases; not globally unique.',
            'vat_release': 'A tail issue frees the dispatch slot before some physical pipe completions. It is not architectural or backend completion.',
            'EX_MEM_COM': 'Use separate qualified PhysicalEventLedger command identity; dispatch is not scalar retirement.',
            'TL_or_FPU_PC_owner': None,
            'TL_or_FPU_PC_owner_reason': 'No complete source token chain has yet been qualified; do not infer from closest PC.'},
        'profiles': {}, 'hardware_contacted': False,
        'whole_SoC_or_FPGA_timing_certified': False}
    source_inputs = set()
    for profile, p in schema['profiles'].items():
        fields = {f['name']: f for f in p['fields']}
        rules = {}

        def add(name, gate='after_reset', valid=None, purpose=None):
            if name not in fields:
                raise ValueError('Missing exact source field '+profile+':'+name)
            f = fields[name]
            if valid is not None and valid not in fields:
                raise ValueError('Missing actual validity field '+valid)
            source_inputs.add(Path(f['source']['path']))
            rules[name] = {'name': name, 'phase_gate': gate, 'valid_when': valid,
                           'width': f['width'], 'words': f['words'],
                           'source': f['source'], 'module': f['module'],
                           'purpose': purpose}

        # These valid/pointer state machines are reset-controlled.  Readiness
        # is compared only for a meaningful presented operation, since idle
        # payload may legally steer unobservable combinational ready outputs.
        for name in ['dis.debug_id_ctr', 'dis.vat_head', 'dis.vat_tail',
                     'vu.vrf.resetting', 'vu.vrf.reset_ctr']:
            add(name, purpose='reset-controlled state')
        for name in fields:
            if re.fullmatch(r'dis.vat_valids_\d+|vmu\.[ls]iq_valids_\d+|vu\.[^.]+(?:\.q)?\.valids_\d+', name):
                add(name, purpose='reset-controlled occupancy valid')
        sequences = ['vu.vls', 'vu.vss', 'vu.vps'] + (
            ['vu.vxsint', 'vu.vxsfp', 'vu.vos'] if profile == 'compute'
            else ['vu.vxsfp_int'])
        protocols = [('dis', 'dis'), ('dis', 'issue'), ('dis', 'mem'),
                     ('vu', 'dis'), ('vmu', 'enq'), ('vmu', 'dmem_load_req'),
                     ('vmu', 'dmem_store_req'), ('vmu', 'vu_lresp'),
                     ('tl_if', 'vec_load_req'), ('tl_if', 'vec_store_req')]
        for seq in sequences:
            add(seq+'.valid', purpose='sequencer occupancy')
            protocols += [(seq, 'dis'), (seq, 'iss')]
            for n in ['inst_vat', 'inst_debug_id', 'eidx', 'inst_rm',
                      'inst_vconfig_vtype_tm', 'inst_vconfig_vtype_vsew']:
                if seq+'.'+n in fields:
                    add(seq+'.'+n, valid=seq+'.valid', purpose='active sequencer identity/configuration')
        execution = ['vu.vxuint', 'vu.vxufp'] if profile == 'compute' else ['vu.vxufp_int']
        for unit in execution:
            protocols += [(unit, 'iss'), (unit, 'iter_write')]
            add(unit+'.io_pipe_write_valid', purpose='scheduled VRF write completion')
            for name in fields:
                if re.fullmatch(re.escape(unit)+r'\.io_(?:pipe|iter)_hazards_\d+_valid', name):
                    add(name, purpose='live finite pipe/iterative occupancy')
        if profile == 'rocket':
            protocols += [('vu', 'fp_req')]
            add('vu.io_fp_resp_valid', purpose='actual external shared FPU response')
        for unit, port in protocols:
            valid = unit+'.io_'+port+'_valid'
            add(valid, purpose='protocol valid')
            ready = unit+'.io_'+port+'_ready'
            if ready in fields:
                add(ready, valid=valid, purpose='meaningful protocol readiness')
            elif not (profile == 'compute' and unit == 'vu.vos' and port == 'iss'):
                raise ValueError('Unexpected missing ready '+ready)
            for name in fields:
                if name.startswith(unit+'.io_'+port+'_bits_'):
                    add(name, valid=valid, purpose='valid-qualified protocol payload')
        for unit in ['vmu', 'tl_if']:
            for port in ['dmem_load_resp', 'dmem_store_ack'] if unit == 'vmu' else ['vec_load_resp', 'vec_store_ack']:
                valid = unit+'.io_'+port+'_valid'
                add(valid, purpose='actual matching memory response valid')
                for name in fields:
                    if name.startswith(unit+'.io_'+port+'_bits_'):
                        add(name, valid=valid, purpose='valid-qualified response tag')
        add('vu.io_busy', purpose='source backend busy flag, not global drain criterion')
        vme = None
        if profile == 'compute':
            for n in ['vu.vos.fp8_hist_valid', 'vu.vos.mvout_valids', 'vu.vos.wsboard',
                      'vu.vos.io_write_valid']:
                add(n, purpose='reset-controlled VME tail/write state')
            add('vu.vos.io_write_mask', valid='vu.vos.io_write_valid', purpose='valid-qualified physical VRF write bit mask')
            opflags = [f'vu.vopu_ctrl_reg_{kind}_{r}' for kind in
                       ['macc', 'zero', 'mvin', 'mvin_col'] for r in range(4)]
            for n in opflags:
                add(n, gate='after_postreset_edge', purpose='unreset RegNext operation enable after known source propagation')
            # Geometry is not read when all operation enables are false.
            # Its gate is an explicit any-of expression, encoded below.
            for n in fields:
                if n.startswith('vu.vopu_ctrl_reg_') and n not in rules:
                    add(n, gate='after_postreset_edge', purpose='operation-qualified unreset backend control')
                    rules[n]['valid_any'] = opflags
                if re.fullmatch(r'vu\.vopu\.clusters_\d_\d\.cells_\d_\d\.fma\.(?:io_validout_pipe_v|valid_stage0_pipe_v)', n):
                    add(n, purpose='reset-controlled physical FP8 pipeline valid')
            vme = {
                'macro_accept': {'all': ['vu.vos.io_dis_valid', 'vu.vos.io_dis_ready']},
                'micro_issue': {'all': ['vu.vos.io_iss_valid'], 'ready': 'source constant 1; no IO ready pin'},
                'sequencer_active': ['vu.vos.valid'],
                'busy_union': {'any': ['vu.vos.valid', 'vu.vos.fp8_hist_valid',
                                       'vu.vos.mvout_valids', *opflags],
                               'also_any_field_regex': r'vu\.vopu\.clusters_\d_\d\.cells_\d_\d\.fma\.(?:io_validout_pipe_v|valid_stage0_pipe_v)'},
                'MAC_accept_per_cell': 'ctrl_macc[cluster_row] && ctrl_row_en[cluster_row][cell_row] && ctrl_col_en[cluster_col][cell_col]',
                'INT8_MAC_completion': 'same source edge as accepted cell when ctrl_fp8=0; source cell commit, distinct from scalar COM',
                'FP8_MAC_completion': 'count actual physical cell fma.io_validout_pipe_v before this edge; not issue count or source io_busy',
                'FP8_tail': 'two source-valid stages; backend RegNext adds one source edge before array acceptance',
                'tile_move_completion': 'VRF destination write is vu.vos.io_write_valid; tile writes/zero are separate physical array work',
                'peak_eligible_MAC_per_source_edge': 256,
                'peak_scope': '4x4 clusters x4x4 cells; requires full legal row/column enables and operands; not guaranteed sustained throughput',
                'same_entry_FP8_constraint': 'two-entry history rejects same entry until issue distance3; distinct entries can issue consecutively'}
        queue_valids = [n for n in rules if rules[n]['purpose'] == 'reset-controlled occupancy valid']
        pipe_valids = [n for n in rules if rules[n]['purpose'] == 'live finite pipe/iterative occupancy']
        result['profiles'][profile] = {
            'configured_harts': [0, 1] if profile == 'compute' else [2],
            'VLEN_bits': 256, 'DLEN_bits': 128 if profile == 'compute' else 256,
            'VRF_scrub_source_edges': 64 if profile == 'compute' else 32,
            'qualified_field_rules': list(rules.values()),
            'all_other_activity_words_known_mask': 0,
            'metrics': {
                'reset': 'input.reset', 'VRF_scrub': 'vu.vrf.resetting',
                'backend_busy_source_flag': 'vu.io_busy',
                'live_pipeline_union': pipe_valids,
                'queue_occupancy_valids': queue_valids,
                'sequencer_waiting': 'seq.valid && !(seq.io_iss_valid && seq.io_iss_ready), with OPU ready constant1; not an attributed stall reason',
                'beat_accept': 'io_iss_valid && io_iss_ready (OPU ready is constant1)',
                'scheduled_pipe_completion': [u+'.io_pipe_write_valid' for u in execution],
                'iterative_completion': [u+'.io_iter_write_valid && '+u+'.io_iter_write_ready' for u in execution],
                'busy_aggregation': 'boolean union per source edge; never sum overlapping stage counts into a fraction',
                'RVV_elements_or_ops_peak': None,
                'RVV_peak_reason': 'FU/op/dtype/lane-mask mapping not yet qualified; DLEN/SEW alone is insufficient, especially Rocket shared scalar FMA',
                'memory_bytes': 'Use PhysicalEventLedger v3 accepted A/D significant-lane masks; masks are protocol significance, intersect producer knownness for values',
                'VME': vme}}
    for path in sorted(source_inputs):
        result['input_sha256'][str(path)] = sha(path)
    # Freeze the actual equations as well as declarations used by descriptors.
    evidence = {}
    needles = {
        'OuterProductSequencer.sv': ['assign io_busy', 'assign io_iss_valid', 'assign io_write_valid',
                                     'valid <=', 'fp8_hist_valid <=', 'mvout_valids <=', 'assign iss_valid'],
        'VectorBackend.sv': ['vopu_ctrl_reg_macc_0 <=', 'vopu_ctrl_reg_row_en_0_0 <=', 'assign io_busy'],
        'OuterProductUnit.sv': ['OuterProductCluster clusters_', '.io_op_row_en_', '.io_op_col_en_'],
        'OuterProductCluster.sv': ['.io_macc      (io_macc &', 'wire             en ='],
        'OuterProductCell.sv': ['if (_fma_io_validout', 'else if (hit & int_macc)', 'wire              f8macc'],
        'MulAddRecFNPipe_l2_e8_s24.sv': ['valid_stage0_pipe_v <=', 'io_validout_pipe_v <='],
        'RegisterAccess.sv': ['resetting <=', 'reset_ctr <=']}
    for filename, tokens in needles.items():
        path = REF/'build/saturn-timing-source-v1/compute/rtl'/filename
        text = path.read_text().splitlines()
        evidence[filename] = {'path': str(path), 'sha256': sha(path),
            'lines': [{'line': i+1, 'literal': line} for i, line in enumerate(text)
                      if any(token in line for token in tokens)]}
        if not evidence[filename]['lines']:
            raise ValueError('Missing equation evidence '+filename)
    result['source_equation_evidence'] = evidence
    (out/'contract.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'sha256': sha(out/'contract.json'),
                      'qualified_fields': {k:len(p['qualified_field_rules']) for k,p in result['profiles'].items()}}))


if __name__ == '__main__':
    main()

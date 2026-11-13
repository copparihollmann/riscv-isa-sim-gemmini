#!/usr/bin/env python3
"""Source-declared read-only control observables common to cut and whole RTL."""
import argparse
import hashlib
import json
import re
from pathlib import Path

R = Path(__file__).resolve().parents[1]
REFERENCE = R / 'build/saturn-timing-component-v1-final'
FAST = R / 'build/saturn-timing-fast-component-v1-final'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def cpp_fields(path):
    return {m[3]: int(m[1])-int(m[2])+1 for m in re.finditer(
        r'/\*(\d+):(\d+)\*/\s+(\w+);', path.read_text())}

def modules(folder):
    result = {}
    for path in folder.glob('*.sv'):
        text = path.read_text()
        match = re.search(r'^module (\w+)\(', text, re.M)
        if not match:
            continue
        instances = {m[2]: m[1] for m in re.finditer(r'^  (\w+) (\w+) \(', text, re.M)}
        declarations = {}
        for number, line in enumerate(text.splitlines(), 1):
            m = re.match(r'\s*(?:input|output|wire|reg|logic)\s+(?:\[(\d+):(\d+)\]\s+)?(\w+)\s*[,;=]', line)
            if m:
                declarations[m[3]] = {'width': int(m[1])-int(m[2])+1 if m[1] else 1,
                                      'line': number, 'literal': line}
        result[match[1]] = {'path': path, 'instances': instances,
                            'declarations': declarations}
    return result

def role(path, module):
    variable = path[-1]
    # Numeric payload and opaque generated compiler temporaries are excluded.
    # Named source address/tag/config/hazard/control state remains observable.
    if variable.startswith('__V') or variable.startswith('_GEN'):
        return None
    if 'data' in variable and 'debug_id' not in variable:
        return None
    if path[0] == 'dis':
        if re.fullmatch(r'vat_(?:valids_\d+|tail|head)|debug_id_ctr', variable):
            return 'dispatch_state'
    if module.startswith(('DCEQueue', 'IssueQueue')):
        if re.fullmatch(r'valids_\d+|enq_ptr_value|deq_ptr_value|maybe_full|ram_\d+_(?:vat|debug_id)', variable):
            return 'queue_state'
    if module.startswith(('LoadOrderBuffer', 'StoreOrderBuffer')):
        if re.search(r'valid|ptr|full|replay|entries_\d+_(?:head|tail|lsiq_id|page_offset)|rob_idxs', variable):
            return 'memory_order_state'
    if module.startswith(('LoadSequencer', 'StoreSequencer', 'ExecuteSequencer', 'SpecialSequencer', 'PermuteSequencer', 'OuterProductSequencer')):
        if re.search(r'valid|^inst_(?:vat|debug_id|.*vtype.*|vl|vstart|rm)|^eidx|hist|state|sboard|old.*(?:read|write)|_io_iss_(?:valid|ready|bits_(?:vat|debug_id|tail|eidx|wmask|rm|fu))', variable):
            return 'sequencer_state'
    if module.startswith('VectorBackend'):
        if variable.startswith('vopu_ctrl_reg_') and not re.search(r'_in_[lt]_', variable):
            return 'OPU_array_control'
        if re.search(r'_(?:vxs\w*|vls|vss|vps|vos|vxu\w*)_io_(?:iss_(?:valid|ready|bits_(?:vat|debug_id|tail|eidx|wmask|rm|fu))|pipe_write_(?:valid|bits_(?:eg|vat|mask))|iter_write_(?:valid|bits_(?:eg|vat|mask)))$', variable):
            return 'backend_event'
    if module.startswith('VectorMemUnit'):
        if re.search(r'^(?:liq|siq)_valids_|(?:liq|siq)_\d+_op_debug_id|(?:liq|siq)_\d+_.*dep_mask|_io_(?:req|resp|reserve|deq|push)_(?:valid|ready|bits_(?:tag|debug_id|addr|size))', variable):
            return 'VMU_state'
    if module.startswith('RegisterAccess') and variable in ['resetting', 'reset_ctr']:
        return 'VRF_reset'
    if module.startswith('RegisterFileBank') and variable in ['write_valid', 'write_bits_eg', 'write_bits_mask', 'll_write_valid', 'll_write_bits_eg', 'll_write_bits_mask']:
        return 'VRF_bank_write'
    if module.startswith('RegisterFile') and re.search(r'(?:read|out_\d+_req|bank_write|scheduler).*?(?:valid|ready|request|fire|bits_eg|mask)', variable):
        return 'VRF_arbitration'
    if module.startswith(('PipeScheduler', 'OldestRRArbiter')):
        return 'port_reservation_arbitration'
    if module.startswith(('IntegerPipe', 'ShiftPipe', 'BitwisePipe', 'BitmanipPipe', 'SegmentedMultiplyPipe', 'FPFMAPipe', 'FPCompPipe', 'FPConvPipe', 'FPDivSqrt', 'IterativeIntegerDivider', 'SharedScalarElementwiseFPFMA', 'MulAddRecFNPipe')):
        if re.search(r'(?:^|_)valid(?:s?_|out_|out$|$)|busy|state|_vat|debug_id|eidx|counter|count', variable):
            return 'functional_pipe_control'
    if module.startswith('TLInterface') and variable == 'inflights':
        return 'TL_inflight'
    return None

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fast-compute-model', type=Path)
    parser.add_argument('--whole-header', type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    whole_header = args.whole_header.resolve() if args.whole_header else REFERENCE / 'build/saturn-timing-reference-v1/model/VTestDriver___024root.h'
    whole = cpp_fields(whole_header)
    report = {'schema': 'iris.saturn_internal_activity_source_schema.v1', 'profiles': {},
              'source_reference_sha256': sha(REFERENCE/'report.json'),
              'source_fast_sha256': sha(FAST/'report.json'),
              'whole_header_sha256': sha(whole_header), 'hardware_contacted': False,
              'activity_knownness_automatically_certified': False}
    for profile, top, prefix in [('compute', 'SaturnShuttleUnit', 'VSaturnCompute'),
                                  ('rocket', 'SaturnRocketUnit', 'VSaturnRocket')]:
        native = REFERENCE/'build/saturn-timing-native-v1'/profile/'model'/(prefix+'___024root.h')
        fast_native = (FAST/'build/saturn-timing-fast-v1/native/compute/model'/(prefix+'___024root.h')) if profile == 'compute' else native
        if profile == 'compute' and args.fast_compute_model:
            fast_native = args.fast_compute_model.resolve()/(prefix+'___024root.h')
        fields, fast_fields = cpp_fields(native), cpp_fields(fast_native)
        source = modules(REFERENCE/'build/saturn-timing-source-v1'/profile/'rtl')
        selected, missing = [], []
        for member, width in fields.items():
            if not member.startswith(top+'__DOT__'):
                continue
            path = member.split('__DOT__')[1:]
            module = top
            for instance in path[:-1]:
                module = source.get(module, {}).get('instances', {}).get(instance)
                if module is None:
                    break
            if module not in source:
                continue
            kind = role(path, module)
            declaration = source[module]['declarations'].get(path[-1])
            if kind is None or declaration is None:
                continue
            if declaration['width'] != width:
                raise ValueError('Source/C++ physical width differs '+member)
            logical = '.'.join(path)
            item = {'name': logical, 'width': width, 'role': kind, 'member': member,
                    'module': module, 'source': {'path': str(source[module]['path']),
                                               'sha256': sha(source[module]['path']),
                                               **declaration}}
            gold = []
            for hart in ([0, 1] if profile == 'compute' else [2]):
                parent = 'TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain'+('_'+str(hart) if hart else '')+'__DOT__element_reset_domain_'+('rockettile' if hart == 2 else 'shuttle_tile')+'__DOT__vector_unit__DOT__'
                gold.append({'hart': hart, 'member': parent+'__DOT__'.join(path)})
            fast_member = member
            if member not in fast_fields and '.vopu.' in '.'+logical:
                if logical.endswith('.fma.valid_stage0_pipe_v'):
                    fast_member = member.replace('__DOT__fma__DOT__valid_stage0_pipe_v', '__DOT__fast_valid_stage0')
                elif logical.endswith('.fma.io_validout_pipe_v'):
                    fast_member = member.replace('__DOT__fma__DOT__io_validout_pipe_v', '__DOT__fast_valid_stage1')
            if fast_member not in fast_fields:
                missing.append({**item, 'missing_from_fast': member not in fast_fields,
                                'missing_from_whole_harts': [g['hart']for g in gold if g['member']not in whole]})
                continue
            assert fast_fields[fast_member] == width and all(whole[g['member']] == width for g in gold if g['member'] in whole)
            item['fast_member'] = fast_member
            item['requires_whole_visibility'] = any(g['member'] not in whole for g in gold)
            item['whole_members'] = gold
            item['words'] = [{'lo': lo, 'width': min(64, width-lo)} for lo in range(0, width, 64)]
            selected.append(item)
        required = ['dis.vat_tail', 'dis.vat_head', 'dis.debug_id_ctr', 'vu.vrf.resetting']
        for name in required:
            if name not in [f['name']for f in selected]:
                raise ValueError('Required source activity state missing '+profile+' '+name)
        report['profiles'][profile] = {'top_module': top, 'prefix': prefix,
                                       'native_header_sha256': sha(native),
                                       'fast_header_sha256': sha(fast_native),
                                       'fields': selected, 'optimized_missing': missing,
                                       'word_count': sum(len(f['words'])for f in selected)}
    (out/'schema.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'profiles': {k: {'fields': len(v['fields']), 'words': v['word_count'],
                                      'missing': len(v['optimized_missing']),
                                      'new_visibility': sum(f['requires_whole_visibility']for f in v['fields'])}for k,v in report['profiles'].items()},
                      'schema_sha256': sha(out/'schema.json')}))

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Exact source protocol ports for internal ownership/issue/VRF/VMU telemetry."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from saturn_timing_activity_extract import modules

R = Path(__file__).resolve().parents[1]
REFERENCE = R/'build/saturn-timing-component-v1-final'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def watched(module):
    return module.startswith(('VectorDispatcher', 'VectorBackend', 'DCEQueue',
        'IssueQueue', 'LoadSequencer', 'StoreSequencer', 'SpecialSequencer',
        'ExecuteSequencer', 'OuterProductSequencer', 'RegisterAccess',
        'RegisterFileBank', 'RegisterFile', 'RegisterReadXbar', 'OldestRRArbiter',
        'PipeScheduler', 'VectorMemUnit', 'LoadOrderBuffer', 'StoreOrderBuffer',
        'TLSplitInterface', 'TLInterface', 'ExecutionUnit', 'IntegerPipe',
        'ShiftPipe', 'BitwisePipe', 'BitmanipPipe', 'SegmentedMultiplyPipe',
        'FPFMAPipe', 'FPCompPipe', 'FPConvPipe', 'FPDivSqrt',
        'IterativeIntegerDivider', 'SharedScalarElementwiseFPFMA',
        'SaturnShuttleFrontend', 'SaturnRocketFrontend', 'PipelinedFaultCheck',
        'IterativeFaultCheck'))

def selected(name):
    if not name.startswith('io_') or 'data' in name and 'debug_id' not in name:
        return False
    return (re.search(r'(?:valid|ready|request|available|fire|depth|busy|vat|debug_id|eidx|wmask|mask|source|tag|addr|release|retire|pc|inst_bits)', name)
            or re.search(r'(?:dis|issue|enq|deq|entry|iss)_bits_(?:bits|vl|vstart|segstart|segend|fu|rm|.*vconfig.*|store)', name))

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema':'iris.saturn_internal_protocol_port_schema.v1',
              'reference_sha256':sha(REFERENCE/'report.json'), 'profiles':{},
              'hardware_contacted':False, 'ports_are_readonly_not_model_inputs':True}
    for profile,top in [('compute','SaturnShuttleUnit'),('rocket','SaturnRocketUnit')]:
        definitions = modules(REFERENCE/'build/saturn-timing-source-v1'/profile/'rtl')
        fields = []
        def visit(module,path):
            definition = definitions[module]
            if watched(module):
                for name,decl in definition['declarations'].items():
                    if not selected(name) or not re.match(r'\s*(?:input|output)\s',decl['literal']):
                        continue
                    fields.append({'name':'.'.join([*path,name]),'module':module,
                        'variable':name,'width':decl['width'],
                        'source':{'path':str(definition['path']),'sha256':sha(definition['path']),**decl},
                        'words':[{'lo':lo,'width':min(64,decl['width']-lo)}for lo in range(0,decl['width'],64)]})
            for instance,child in definition['instances'].items():
                if child in definitions:
                    visit(child,[*path,instance])
        visit(top,[])
        result['profiles'][profile] = {'top_module':top,'fields':fields,
                                      'word_count':sum(len(f['words'])for f in fields)}
    (out/'ports.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'profiles':{k:{'ports':len(p['fields']),'words':p['word_count']}
                                 for k,p in result['profiles'].items()},
                      'schema_sha256':sha(out/'ports.json')}))

if __name__ == '__main__':
    main()

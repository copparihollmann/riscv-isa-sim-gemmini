#!/usr/bin/env python3
"""Adversarial package metadata checks using fresh copies, without guest execution."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from spike import empirical_provider_v3 as provider
from spike.check_empirical_parser_v2 import check_parser


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(manifest, output):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    original = json.loads(Path(manifest).read_text())
    baseline = copy.deepcopy(original)
    # This is a draft verifier replay, not publication: retain the input package
    # and explicitly bind the new verifier epoch in a separate candidate.
    source = Path(provider.__file__).resolve()
    baseline['model_provider'] = str(source); baseline['input_sha256'][str(source)] = sha(source)
    base = output / 'baseline.json'; base.write_text(json.dumps(baseline))
    if provider.experimental_empirical_simulator(base).get('available') is not True:
        raise ValueError('New verifier rejected valid byte-bound baseline: ' + str(provider.experimental_empirical_simulator(base)))
    records = []
    def assert_refused(name, value=None, raw=None):
        path = output / (name + '.json')
        path.write_text(raw if raw is not None else json.dumps(value))
        result = provider.experimental_empirical_simulator(path)
        if result.get('available') is not False or not isinstance(result.get('reason'), str):
            raise ValueError('Malformed package accepted: ' + name)
        records.append({'name': name, 'pass': True, 'reason': result['reason']})
    for name, data in [('null_manifest', None), ('list_manifest', []), ('number_manifest', 1)]:
        assert_refused(name, data)
    assert_refused('duplicate_JSON_key', raw='{"schema":"a","schema":"b"}')
    assert_refused('nonfinite_JSON', raw='{"schema":NaN}')
    for name, key, value in [
        ('list_input_map', 'input_sha256', []), ('list_environment', 'runtime_environment', []),
        ('boolean_matrix_harts', 'matrix_hart_ids', [False, True]), ('float_device_ABI', 'native_device_abi', 4.0),
        ('boolean_device_ABI', 'native_device_abi', True), ('missing_launcher', 'native_launcher', None),
        ('list_qualification', 'qualification', []), ('wrong_ISA_extensions', 'isa_extensions', ['zvt32t']),
        ('list_calibration', 'calibration', []), ('list_built_from', 'built_from', [])]:
        changed = copy.deepcopy(baseline); changed[key] = value; assert_refused(name, changed)
    def receipt_case(name, mutate):
        changed = copy.deepcopy(baseline)
        receipt = json.loads(Path(changed['native_launcher']['selftest']).read_text())
        def evidence(path, data):
            path = output / (name + '-' + path)
            path.write_text(json.dumps(data)); identity = sha(path)
            changed['input_sha256'][str(path)] = identity
            receipt['output_sha256'][str(path)] = identity
            return str(path)
        mutate(changed, receipt, evidence)
        path = output / (name + '-receipt.json'); path.write_text(json.dumps(receipt))
        changed['native_launcher']['selftest'] = str(path)
        changed['native_launcher']['selftest_sha256'] = sha(path)
        changed['input_sha256'][str(path)] = sha(path)
        assert_refused(name, changed)
    receipt_case('boolean_fatal_harts', lambda m,r,e:r.update(fatal_harts_verified=[False,True,2]))
    receipt_case('missing_executions', lambda m,r,e:r.update(runs=[]))
    receipt_case('duplicate_execution_names', lambda m,r,e:r['runs'][0].update(name='direct'))
    receipt_case('boolean_exit_status', lambda m,r,e:r['runs'][0].update(exit_status=True))
    receipt_case('boolean_timed_out', lambda m,r,e:r['runs'][0].update(timed_out=0))
    receipt_case('list_output_map', lambda m,r,e:r.update(output_sha256=[]))
    receipt_case('boolean_fatal_PC', lambda m,r,e:r['runs'][0].update(fatal_symbol_pc=True))
    receipt_case('wrong_actual_binary', lambda m,r,e:r['runs'][0]['argv'].__setitem__(0,m['native_binary']))
    receipt_case('empty_execution_receipt', lambda m,r,e:r['runs'][0].update(execution_receipt=e('execution.json',{})))
    def mismatch(m,r,e):
        execution=json.loads(Path(r['runs'][0]['execution_receipt']).read_text())
        execution['exit_status']=0
        r['runs'][0]['execution_receipt']=e('execution.json',execution)
    receipt_case('execution_outcome_mismatch', mismatch)
    # A manifest can supply arbitrary template bytes. Verification compares them
    # as data; it must never import them. No wrapper or guest is executed here.
    marker = output / 'TEMPLATE_WAS_EXECUTED'
    template = output / 'sentinel-template.py'
    template.write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("executed")\n')
    changed=copy.deepcopy(baseline); info=changed['native_launcher']
    info['template']=str(template); info['template_sha256']=sha(template)
    changed['input_sha256'][str(template)]=sha(template)
    wrapper=output/'sentinel-wrapper'
    wrapper.write_text('#!'+info['python']+' -IS\n'+template.read_text()+
        '\nif __name__ == "__main__":\n    launch('+repr(changed['native_binary'])+', '+repr(changed['native_binary_sha256'])+', '+
        repr(info['python'])+', '+repr(info['python_sha256'])+', sys.argv[1:])\n')
    changed['binary']=str(wrapper);changed['binary_sha256']=sha(wrapper)
    changed['input_sha256'][str(wrapper)]=sha(wrapper)
    assert_refused('template_is_data_not_imported',changed)
    if marker.exists():raise ValueError('Metadata verifier executed manifest-supplied Python')
    parser=check_parser(output/'ELF-parser-controls')
    report={'schema':'iris.empirical_package_refusal_audit.v2','pass':True,'valid_package_baseline_passed':True,
        'controls':records,'metadata_refusals':len(records),'ELF_parser_negative_controls':parser['negative_controls'],
        'template_not_executed':True,'guest_executed':False,'hardware_contacted':False,
        'model_fit_or_holdout_analysis_performed':False,
        'input_sha256':{str(p.resolve()):sha(p)for p in (Path(__file__),source,Path(manifest))},
        'draft_verifier_rebinding_explicit':True}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(check(args.manifest,args.output),indent=2))

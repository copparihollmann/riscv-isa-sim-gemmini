"""Explicit, byte-bound experimental FPGA-empirical simulator selection.

This provider never promotes an empirical fit to full Iris/RTL/2% certification.
The ordinary functional and full-model providers retain their existing gates.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def digest(value):
    if not isinstance(value,str)or not re.fullmatch('[0-9a-f]{64}',value):
        raise ValueError('Full SHA256 identity required')
    return value


def document(path):
    def reject(value):raise ValueError('Non-finite JSON value: '+value)
    def finite(value):
        result=float(value)
        if not math.isfinite(result):reject(value)
        return result
    return json.loads(Path(path).read_text(),parse_constant=reject,parse_float=finite)


def bound_file(manifest,path,expected=None):
    path=Path(path)
    if not path.is_absolute()or not path.is_file():raise ValueError('Absolute existing model input required')
    expected=digest(expected or manifest['input_sha256'].get(str(path)))
    if manifest['input_sha256'].get(str(path))!=expected or sha(path)!=expected:
        raise ValueError('Empirical model input changed: '+str(path))
    return path


def runtime_binding_inputs(binding, ancestors=()):
    """Verify declared inputs and preserve a normalization's original packet."""
    if not isinstance(binding,dict):raise ValueError('Runtime binding object required')
    declared=binding.get('input_sha256',{})
    if not isinstance(declared,dict):raise ValueError('Runtime binding input map required')
    inputs={}
    for name,expected in declared.items():
        path=Path(name)
        if not path.is_absolute()or not path.is_file()or sha(path)!=digest(expected):
            raise ValueError('Runtime binding declared input changed or missing: '+str(path))
        inputs[str(path)]=expected
    normalization=binding.get('canonicalization')
    if normalization is None:return inputs
    if not isinstance(normalization,dict)or normalization.get('parameters_or_model_changed')is not False:
        raise ValueError('Explicit parameter-preserving binding normalization required')
    source=normalization.get('source');expected=digest(normalization.get('source_sha256'))
    if not isinstance(source,str)or inputs.get(source)!=expected:
        raise ValueError('Normalization original binding must be declared in its input map')
    if source in ancestors:raise ValueError('Cyclic runtime binding normalization')
    original=document(source)
    if not isinstance(original,dict)or original.get('schema')!='iris.empirical_runtime_binding.v1':
        raise ValueError('Recognized original runtime binding required')
    for name,value in original.items():
        if name not in ('input_sha256','canonicalization')and binding.get(name)!=value:
            raise ValueError('Normalization changed an original binding field: '+name)
    partitions=original.get('parent_split_ids',{})
    if binding.get('split')!={'training_parent_case_ids':partitions.get('train'),
                             'validation_parent_case_ids':partitions.get('internal_validation')}:
        raise ValueError('Normalized split differs from original parent partitions')
    for name,expected in runtime_binding_inputs(original,(*ancestors,source)).items():
        if name in inputs and inputs[name]!=expected:
            raise ValueError('Conflicting nested runtime binding input identity: '+name)
        inputs[name]=expected
    return inputs


def experimental_empirical_simulator(manifest_path):
    try:
        path=Path(manifest_path).resolve();manifest=document(path)
        if manifest.get('schema')!='iris.empirical_simulator.v1':raise ValueError('Unknown empirical model schema')
        if manifest.get('mode')!='experimental_fpga_empirical':raise ValueError('Explicit empirical mode required')
        for name in ('LD_LIBRARY_PATH','LD_PRELOAD','LD_AUDIT'):
            if os.environ.get(name)!=manifest.get('runtime_environment',{}).get(name):
                raise ValueError('Native loader environment changed: '+name)
        for name,expected in manifest['input_sha256'].items():bound_file(manifest,name,expected)
        native=bound_file(manifest,manifest['native_binary'],manifest['native_binary_sha256'])
        binary=bound_file(manifest,manifest['binary'],manifest['binary_sha256'])
        uart=bound_file(manifest,manifest['uart_library'],manifest['uart_library_sha256'])
        if manifest.get('native_device_abi')!=4:raise ValueError('Matched Iris native/device ABI4 required')
        isa=manifest['per_hart_isa']
        if set(isa)!={'0','1','2'}or any(not isinstance(v,str)or not v.startswith('rv64')for v in isa.values()):
            raise ValueError('All three heterogeneous hart ISA strings required')
        if (any('zvti8i32mm'not in isa[h]for h in('0','1'))
                or any(ext in isa['2']for ext in('zvt32t','zvti8i32mm','zvtofp8fmm'))):
            raise ValueError('Matrix support must be restricted to harts0/1')
        if manifest.get('matrix_hart_ids')!=[0,1]:raise ValueError('Actual matrix hart IDs required')
        memory=manifest['memory_regions']
        if memory!=[[0x70000000,0x40000],[0x80000000,0x100000000],[0x580000000,0x20000]]:
            raise ValueError('Exact Iris TCM/DRAM/scratchpad regions required')
        qualification=manifest['qualification']
        for field in('rtl_certified','accuracy_2percent_certified','whole_model_certified'):
            if qualification.get(field)is not False:raise ValueError('Empirical package may not assert '+field)
        calibration=manifest['calibration']
        parameters=bound_file(manifest,calibration['parameters'],calibration['parameters_sha256'])
        fixture=bound_file(manifest,calibration['fixture'],calibration['fixture_sha256'])
        fit_path=bound_file(manifest,calibration['fit_report'],calibration['fit_report_sha256'])
        binding_path=bound_file(manifest,calibration['runtime_binding'],calibration['runtime_binding_sha256'])
        fitted=document(parameters);fit=document(fit_path);binding=document(binding_path)
        for name,expected in runtime_binding_inputs(binding).items():
            bound_file(manifest,name,expected)
        if (binding.get('schema')!='iris.empirical_runtime_binding.v1'
                or binding.get('actual_parameter_fit_performed')is not True
                or fitted.get('actual_parameter_fit_performed')is not True):
            raise ValueError('Actual completed empirical fit required')
        for field,target in [('native_binary_sha256',native),('uart_library_sha256',uart),
                ('fixture_sha256',fixture),('parameters_sha256',parameters),('fit_report_sha256',fit_path)]:
            if binding.get(field)!=sha(target):
                raise ValueError('Calibration runtime input identity mismatch: '+field)
        if binary!=native:
            raise ValueError('This empirical provider launches the native binary directly')
        if binding.get('global_heldout_timings_consumed')is not False:
            raise ValueError('Fitting must preserve untouched global held-out timings')
        if fitted.get('full_2pct_certified')is not False or fit.get('full_2pct_certified')is not False:
            raise ValueError('Experimental fit must preserve unresolved whole-model accuracy')
        if binding.get('calibration_identity')!=manifest.get('calibration_identity'):
            raise ValueError('Calibration native/fixture identity mismatch')
        identity=binding.get('calibration_identity')
        if not isinstance(identity,str)or not identity:
            raise ValueError('Nonempty runtime calibration identity required')
        directives=[line.split('#',1)[0].split()for line in fixture.read_text().splitlines()]
        profiles=[row for row in directives if row and row[0]=='empirical_profile']
        if (len(profiles)!=1 or profiles[0][1:]!=['experimental-effective-services',identity,'bounded']
                or [row for row in directives if row and row[0]=='counter_policy']!=[['counter_policy','source-ungated-stall']]
                or [row for row in directives if row and row[0]=='base_hz']!=[['base_hz','500000000']]
                or [row for row in directives if row and row[0]=='rtc_divider']!=[['rtc_divider','1000']]
                or sorted(row for row in directives if row and row[0]=='hart')!=
                   [['hart',str(h),'1','source']for h in range(3)]):
            raise ValueError('Matched bounded empirical fixture with actual source-counter policy required')
        split=binding['split'];training=split['training_parent_case_ids'];validation=split['validation_parent_case_ids']
        if (not training or not validation or any(not isinstance(v,str)or not v for v in training+validation)
                or len(set(training))!=len(training)or len(set(validation))!=len(validation)
                or set(training)&set(validation)):
            raise ValueError('Disjoint nonempty parent-level fit/validation split required')
        reference=calibration['reference']
        for field in('image_archive_sha256','bitstream_sha256','driver_sha256','capture_archive_sha256'):
            digest(reference[field])
        if reference.get('source_image_association_verified')is not False:
            raise ValueError('This empirical release has no full source/image attestation')
        tests=manifest['selftest'];test_path=bound_file(manifest,tests['receipt'],tests['sha256'])
        tested=document(test_path)
        if (tested.get('schema')!='iris.empirical_package_selftest.v1'or tested.get('pass')is not True
                or tested.get('native_binary_sha256')!=sha(native)
                or tested.get('uart_library_sha256')!=sha(uart)
                or tested.get('fixture_sha256')!=sha(fixture)
                or tested.get('three_harts_numerically_verified')is not True
                or tested.get('modeled_time_sensitivity_verified')is not True):
            raise ValueError('Actual byte-bound three-hart/numeric/modeled-time selftest required')
        arguments=manifest['launch_args']
        if not isinstance(arguments,list)or any(not isinstance(v,str)for v in arguments):
            raise ValueError('Native launch argument list required')
        boot={}
        for prefix in ('--iris-bootrom=','--dtb='):
            selected=[v[len(prefix):]for v in arguments if v.startswith(prefix)]
            if len(selected)!=1:raise ValueError('Unique byte-bound boot ROM and DTB required')
            boot[prefix]=bound_file(manifest,selected[0])
        allowed=['--iris-vme','--device=sifive_uart,0x10020000',
                 '--iris-timing-fixture='+str(fixture),'--extlib='+str(uart),
                 *[prefix+str(target)for prefix,target in boot.items()]]
        if sorted(arguments)!=sorted(allowed):
            raise ValueError('Only the exact Iris boot/device/fixture/UART launch arguments are allowed; no competing overrides')
        test_inputs=tested.get('input_sha256',{})
        for target in boot.values():
            if test_inputs.get(str(target))!=sha(target):
                raise ValueError('Selected boot ROM/DTB was not bound by the actual package selftest')
        tested_runs=tested.get('runs',[])
        if not tested_runs or any(not isinstance(run.get('argv'),list)or
                any(run['argv'].count('--hart-isa='+h+':'+isa[h])!=1 for h in ('0','1','2'))
                for run in tested_runs):
            raise ValueError('Selftest must execute the selected three-hart ISA configuration')
        built=manifest.get('built_from',{})
        if built.get('source_snapshot_verified')is not True:
            raise ValueError('Verified source/build provenance closure required')
        closure_path=bound_file(manifest,built['receipt'],built['receipt_sha256'])
        closure=document(closure_path)
        if (closure.get('schema')!='iris.empirical.source_closure_verification.v1'
                or closure.get('pass')is not True
                or closure.get('native_binary_sha256',closure.get('binary_sha256'))!=sha(native)
                or closure.get('uart_library_sha256',closure.get('uart_sha256'))!=sha(uart)):
            raise ValueError('Source closure verification differs from selected native epoch')
        return {'available':True,'binary':str(binary),'binary_sha256':sha(binary),
            'native_binary':str(native),'native_binary_sha256':sha(native),'native_device_abi':4,
            'isa_extensions':manifest['isa_extensions'],'per_hart_isa':isa,'matrix_hart_ids':[0,1],
            'memory_regions':memory,'launch_args':arguments,
            'execution_input_sha256':{**manifest['input_sha256'],str(path):sha(path)},
            'timing_available':True,'timing_status':'experimental_fpga_empirical',
            'empirical_fit_available':True,'timing_calibrated':False,'rtl_certified':False,
            'accuracy_2percent_certified':False,'zephyr_smp_certified':False,'whole_model_certified':False,
            'timing_scope':manifest['timing_scope'],'validation_metrics':binding.get('validation_metrics'),
            'provenance':{'manifest':str(path),'manifest_sha256':sha(path),'calibration':calibration,
                'built_from':manifest['built_from'],'qualification':qualification},
            'functional_scope':tested.get('functional_scope','byte-bound experimental three-hart subset')}
    except(OSError,ValueError,KeyError,TypeError)as error:
        return {'available':False,'reason':'Invalid empirical Iris model: '+str(error),
            'timing_available':False,'rtl_certified':False,'whole_model_certified':False}

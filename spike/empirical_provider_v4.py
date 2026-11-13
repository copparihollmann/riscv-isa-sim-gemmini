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
    def pairs(items):
        result={}
        for name,value in items:
            if name in result:raise ValueError('Duplicate JSON key: '+name)
            result[name]=value
        return result
    value=json.loads(Path(path).read_text(),parse_constant=reject,parse_float=finite,object_pairs_hook=pairs)
    if not isinstance(value,dict):raise ValueError('JSON object required')
    return value


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
    if len(ancestors)>32:raise ValueError('Runtime binding normalization depth exceeded')
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



def validate_reference_metadata(manifest, binding):
    """Cross-check declared reference facts against already byte-bound evidence.

    The observability report's inner member digests were established by the
    publishing archive audit. Runtime never substitutes bundle-TAR identity for
    its executable member, or infers deployed-image/source attestation.
    """
    from urllib.parse import urlparse, unquote
    reference = manifest['calibration']['reference']
    declared = binding.get('reference')
    if not isinstance(reference, dict) or not isinstance(declared, dict):
        raise ValueError('Actual calibration reference objects required')
    documents = {}
    for key in ('run_manifest', 'analysis'):
        path = bound_file(manifest, reference[key], reference[key + '_sha256'])
        if (declared.get(key) != str(path) or declared.get(key + '_sha256') != sha(path)
                or binding.get('input_sha256', {}).get(str(path)) != sha(path)):
            raise ValueError('Reference ' + key + ' differs from bound fitting input')
        documents[key] = document(path)
    run, analysis = documents['run_manifest'], documents['analysis']
    observation_path = bound_file(manifest, reference['observability_report'],
                                  reference['observability_report_sha256'])
    observation = document(observation_path)
    audit = run.get('observability_audit', {})
    if (audit.get('verified') is not True or audit.get('report') != str(observation_path)
            or audit.get('sha256') != sha(observation_path)
            or binding.get('input_sha256', {}).get(str(observation_path)) != sha(observation_path)):
        raise ValueError('Reference observability report differs from actual managed run')
    if (observation.get('schema') != 'iris.candidate_image_observability.v3'
            or observation.get('candidate_only') is not True
            or observation.get('loaded_image_verified') is not False
            or observation.get('complete_source_image_provenance') is not False
            or reference.get('source_image_association_verified') is not False
            or analysis.get('source_image_association_verified') is not False):
        raise ValueError('Reference must preserve unresolved loaded-image/source association')
    allowed = {'iris.compute_fitting_archive_analysis.v1': 'compute_fitting_campaign_v1',
               'iris.buffered_fitting_archive_analysis.v1': 'buffered_fitting_campaign_v1',
               'iris.buffered_priority_fitting_archive_analysis.v2': 'buffered_priority_fitting_campaign_v2'}
    if (analysis.get('schema') not in allowed
            or run.get('campaign_role') != allowed[analysis['schema']]
            or run.get('fitting_only') is not True or run.get('global_heldout') is not False
            or analysis.get('fitting_only') is not True or analysis.get('global_heldout') is not False
            or any(analysis.get(k) is not True for k in
                   ('pass', 'archive_verified', 'managed_run_passed', 'functional_checks_passed'))):
        raise ValueError('Actual independently checked fitting-only reference required')
    if (run.get('status') != 'completed_uncertified' or run.get('cleanup_status') != 'passed'
            or run.get('error') is not None or run.get('cleanup_error') is not None
            or [(c.get('task'), c.get('status')) for c in run.get('commands', [])] !=
               [('kill', 'passed'), ('infrasetup', 'passed'), ('runworkload', 'passed'), ('kill', 'passed')]
            or any(type(c.get('returncode')) is not int or c['returncode'] != 0
                   or c.get('timed_out') is not False for c in run['commands'])):
        raise ValueError('Reference complete owned managed lifecycle required')
    capture = run.get('capture', {})
    archive = bound_file(manifest, capture['archive'], capture['archive_sha256'])
    if (capture.get('status') != 'captured' or type(capture.get('returncode')) is not int
            or capture['returncode'] != 0
            or reference.get('capture_archive_sha256') != sha(archive)
            or declared.get('capture_archive_sha256') != sha(archive)
            or analysis.get('archive_sha256') != sha(archive)
            or analysis.get('current_run_manifest_sha256') != sha(reference['run_manifest'])):
        raise ValueError('Reference actual capture/run/analysis identity mismatch')
    if (reference.get('elf_sha256') != run.get('elf_sha256')
            or reference.get('elf_sha256') != declared.get('elf_sha256')):
        raise ValueError('Reference ELF differs from actual fitted program')
    digest(reference['elf_sha256'])
    count = reference.get('independently_checked_regions')
    actual_count = run.get('expected_regions')
    analyzed_count = analysis.get('guest_proof', {}).get('regions')
    if (type(count) is not int or count <= 0 or type(actual_count) is not int
            or type(analyzed_count) is not int or count != actual_count or count != analyzed_count
            or len(run.get('regions', [])) != count):
        raise ValueError('Reference exact typed independently checked region count required')
    members = {}
    for field, basename in (('image', 'firesim.bit'), ('driver', 'FireSim-corigine_mimicturbo_gt')):
        info = run[field]; uri = urlparse(info['uri'])
        if uri.scheme != 'file' or uri.netloc:
            raise ValueError('Reference artifact must be an exact local file')
        path = bound_file(manifest, str(Path(unquote(uri.path)).resolve()), info['sha256'])
        if observation.get('input_sha256', {}).get(str(path)) != sha(path):
            raise ValueError('Reference ' + field + ' archive differs from bound observability')
        rows = observation.get(field + '_members')
        if not isinstance(rows, list):
            raise ValueError('Reference archived-member list required')
        selected = [row for row in rows if isinstance(row, dict)
                    and isinstance(row.get('name'), str) and Path(row['name']).name == basename]
        if (len(selected) != 1 or type(selected[0].get('bytes')) is not int
                or selected[0]['bytes'] <= 0):
            raise ValueError('Unique typed observed inner artifact required')
        digest(selected[0]['sha256']); members[field] = selected[0]
        if field == 'image' and reference.get('image_archive_sha256') != sha(path):
            raise ValueError('Reference image TAR differs from actual managed image')
    if (reference.get('bitstream_sha256') != members['image']['sha256']
            or observation.get('build_collateral_association', {}).get('archived_bit_sha256')
               != members['image']['sha256']):
        raise ValueError('Reference bitstream differs from observed actual image member')
    if (reference.get('driver_sha256') != members['driver']['sha256']
            or observation.get('driver_binary_sha256') != members['driver']['sha256']
            or observation.get('driver_policy', {}).get('selected_binary_sha256')
               != members['driver']['sha256']
            or observation.get('driver_policy', {}).get('bundle_sha256') != run['driver']['sha256']):
        raise ValueError('Reference driver executable differs from actual bundle member')
    return {'verified': True, 'policy': 'bound-managed-reference-identities-v4',
            'observability_report': str(observation_path),
            'observability_report_sha256': sha(observation_path),
            'independently_checked_regions': count,
            'driver_binary_sha256': members['driver']['sha256'],
            'driver_bundle_sha256': run['driver']['sha256'],
            'source_image_association_verified': False}

def integer_list(value, expected):
    return isinstance(value,list)and all(type(v)is int for v in value)and value==expected


def validate_manifest_shapes(manifest):
    for name in ('input_sha256','runtime_environment','per_hart_isa','qualification','calibration','selftest','built_from'):
        if not isinstance(manifest.get(name),dict):raise ValueError('Object required: '+name)
    if not isinstance(manifest.get('native_launcher'),dict):
        raise ValueError('Launcher object required')
    for name,value in manifest['input_sha256'].items():
        if not isinstance(name,str):raise ValueError('Input filename must be a string')
        digest(value)
    extensions=manifest.get('isa_extensions')
    if (not isinstance(extensions,list)or not extensions or any(not isinstance(v,str)or not v for v in extensions)
            or len(set(extensions))!=len(extensions)or set(extensions)!={'zvt32t','zvti8i32mm','zvtofp8fmm'}):
        raise ValueError('Unique ISA extension string list required')
    memory=manifest.get('memory_regions')
    if (not isinstance(memory,list)or any(not isinstance(row,list)or len(row)!=2
            or any(type(v)is not int for v in row)for row in memory)):
        raise ValueError('Integer memory region pairs required')


def validate_launcher_selftest(manifest,checked,native,binary,fixture):
    if (checked.get('schema')!='iris.empirical_fatal_launcher_selftest.v2'or checked.get('pass')is not True
            or checked.get('native_binary_sha256')!=sha(native)or checked.get('launcher_sha256')!=sha(binary)
            or checked.get('fixture_sha256')!=sha(fixture)
            or not integer_list(checked.get('fatal_harts_verified'),[0,1,2])
            or any(checked.get(k)is not True for k in ('recoverable_trap_verified',
                'normal_numeric_counter_parity_verified','stripped_ELF_refused',
                'fatal_symbol_pc_exact_match_verified','parser_negative_controls_passed'))
            or checked.get('parser_policy')!='fatal-ELF-exec-v2'):
        raise ValueError('Actual v2 three-hart/fatal-PC/recoverable/numeric/parser selftest required')
    for key in ('input_sha256','output_sha256'):
        if not isinstance(checked.get(key),dict)or not checked[key]:raise ValueError('Nonempty selftest evidence map required')
        for name,wanted in checked[key].items():bound_file(manifest,name,wanted)
    runs=checked.get('runs')
    names={'automatic-fatal-hart0','automatic-fatal-hart1','automatic-fatal-hart2',
           'recoverable-illegal-instruction','direct','wrapped','stripped-ELF-refusal'}
    if (not isinstance(runs,list)or len(runs)!=7 or any(not isinstance(r,dict)for r in runs)
            or {r.get('name')for r in runs}!=names):
        raise ValueError('Exactly seven unique actual launcher executions required')
    for run in runs:
        if (run.get('pass')is not True or run.get('timed_out')is not False
                or type(run.get('exit_status'))is not int
                or not isinstance(run.get('argv'),list)or not run['argv']
                or any(not isinstance(v,str)for v in run['argv'])):
            raise ValueError('Typed actual launcher execution required')
        expected_binary=native if run['name']=='direct'else binary
        if run['argv'][0]!=str(expected_binary):raise ValueError('Actual selftest used another launcher/native binary')
        if run['argv'].count('--iris-timing-fixture='+str(fixture))!=1:
            raise ValueError('Actual launcher selftest used another fixture')
        for hart,isa in manifest['per_hart_isa'].items():
            if run['argv'].count('--hart-isa='+hart+':'+isa)!=1:
                raise ValueError('Launcher selftest omitted selected heterogeneous ISA')
        guest=bound_file(manifest,run['argv'][-1])
        if checked['input_sha256'].get(str(guest))!=sha(guest):
            raise ValueError('Actual selftest guest ELF must be an input')
        success=run['name']in ('direct','wrapped','recoverable-illegal-instruction')
        if (run['exit_status']==0)!=success:raise ValueError('Launcher outcome contradicts tested case')
        execution=bound_file(manifest,run['execution_receipt'])
        if checked['output_sha256'].get(str(execution))!=sha(execution):
            raise ValueError('Execution receipt must be in output evidence map')
        recorded=document(execution)
        fields={'argv','exit_status','timed_out','host_seconds','stdout_sha256','stderr_sha256',
                'stdout_path','stderr_path','execution_receipt'}
        if set(recorded)!=fields:raise ValueError('Complete actual execution receipt required')
        if type(recorded.get('host_seconds'))not in (int,float)or recorded['host_seconds']<0:
            raise ValueError('Finite nonnegative execution duration required')
        for key,value in recorded.items():
            if run.get(key)!=value or type(run.get(key))is not type(value):
                raise ValueError('Selftest run differs from actual execution receipt: '+key)
        for stream in ('stdout','stderr'):
            path=bound_file(manifest,run[stream+'_path'],run[stream+'_sha256'])
            if checked['output_sha256'].get(str(path))!=sha(path):
                raise ValueError('Raw execution stream must be in output evidence map')
        if run['name'].startswith('automatic-fatal-hart'):
            hart=int(run['name'][-1]);pc=run.get('fatal_symbol_pc')
            if type(pc)is not int or pc<=0 or pc&1:raise ValueError('Exact integer fatal symbol PC required')
            text=Path(run['stderr_path']).read_text()
            matches=re.findall(r'IRIS_FATAL hart=(\d+) pc=0x([0-9a-f]+) .*cause=',text)
            if not any(int(h)==hart and int(p,16)==pc for h,p in matches):
                raise ValueError('Actual fatal record does not match requested hart and symbol PC')
        if run['name']=='stripped-ELF-refusal' and 'IRIS_LAUNCH_REFUSED'not in Path(run['stderr_path']).read_text():
            raise ValueError('Actual stripped ELF refusal missing')
    direct=next(r for r in runs if r['name']=='direct');wrapped=next(r for r in runs if r['name']=='wrapped')
    if Path(direct['stdout_path']).read_bytes()!=Path(wrapped['stdout_path']).read_bytes():
        raise ValueError('Actual direct/wrapped program output differs')


def experimental_empirical_simulator(manifest_path):
    try:
        path=Path(manifest_path).resolve();manifest=document(path)
        validate_manifest_shapes(manifest)
        provider=bound_file(manifest,manifest['model_provider'])
        if sha(provider)!=sha(Path(__file__)):raise ValueError('Selected provider differs from verifier implementation')
        if manifest.get('schema')!='iris.empirical_simulator.v1':raise ValueError('Unknown empirical model schema')
        if manifest.get('mode')!='experimental_fpga_empirical':raise ValueError('Explicit empirical mode required')
        for name in ('LD_LIBRARY_PATH','LD_PRELOAD','LD_AUDIT'):
            if os.environ.get(name)!=manifest.get('runtime_environment',{}).get(name):
                raise ValueError('Native loader environment changed: '+name)
        for name,expected in manifest['input_sha256'].items():bound_file(manifest,name,expected)
        native=bound_file(manifest,manifest['native_binary'],manifest['native_binary_sha256'])
        binary=bound_file(manifest,manifest['binary'],manifest['binary_sha256'])
        uart=bound_file(manifest,manifest['uart_library'],manifest['uart_library_sha256'])
        if type(manifest.get('native_device_abi'))is not int or manifest['native_device_abi']!=4:raise ValueError('Matched Iris native/device ABI4 required')
        isa=manifest['per_hart_isa']
        if set(isa)!={'0','1','2'}or any(not isinstance(v,str)or not v.startswith('rv64')for v in isa.values()):
            raise ValueError('All three heterogeneous hart ISA strings required')
        if (any('zvti8i32mm'not in isa[h].split('_')for h in('0','1'))
                or any(ext in isa['2'].split('_')for ext in('zvt32t','zvti8i32mm','zvtofp8fmm'))):
            raise ValueError('Matrix support must be restricted to harts0/1')
        if not integer_list(manifest.get('matrix_hart_ids'),[0,1]):raise ValueError('Actual matrix hart IDs required')
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
        launcher=manifest.get('native_launcher')
        if launcher is None:
            if binary!=native:raise ValueError('Unbound empirical launcher')
        else:
            if launcher.get('kind')!='automatic-fatal-ELF-v2' or binary==native:
                raise ValueError('Distinct byte-bound v2 fatal-aware launcher required')
            if launcher.get('isolated_python')is not True or launcher.get('parser_policy')!='fatal-ELF-exec-v2':
                raise ValueError('Isolated v2 executable fatal-symbol policy required')
            template=bound_file(manifest,launcher['template'],launcher['template_sha256'])
            python=bound_file(manifest,launcher['python'],launcher['python_sha256'])
            # Metadata verification must never execute Python supplied by a manifest.
            expected=('#!'+str(python)+' -IS\n'+template.read_text()+
                '\nif __name__ == "__main__":\n    launch('+repr(str(native))+', '+repr(sha(native))+', '+
                repr(str(python))+', '+repr(sha(python))+', sys.argv[1:])\n')
            if binary.read_text()!=expected:
                raise ValueError('Launcher differs from bound native/template/interpreter rendering')
            check=bound_file(manifest,launcher['selftest'],launcher['selftest_sha256'])
            checked=document(check)
            validate_launcher_selftest(manifest,checked,native,binary,fixture)
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
        if (not isinstance(training,list)or not isinstance(validation,list)or not training or not validation or any(not isinstance(v,str)or not v for v in training+validation)
                or len(set(training))!=len(training)or len(set(validation))!=len(validation)
                or set(training)&set(validation)):
            raise ValueError('Disjoint nonempty parent-level fit/validation split required')
        reference=calibration['reference']
        for field in('image_archive_sha256','bitstream_sha256','driver_sha256','capture_archive_sha256'):
            digest(reference[field])
        if reference.get('source_image_association_verified')is not False:
            raise ValueError('This empirical release has no full source/image attestation')
        validate_reference_metadata(manifest, binding)
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
            'automatic_fatal_handler_resolution':launcher is not None,
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
    except(OSError,ValueError,KeyError,TypeError,AttributeError,IndexError,UnicodeError)as error:
        return {'available':False,'reason':'Invalid empirical Iris model: '+str(error),
            'timing_available':False,'rtl_certified':False,'whole_model_certified':False}

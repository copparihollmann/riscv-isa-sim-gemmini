"""Fail-closed packaging adapter for the experimental Merlin functional workflow."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def _sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def _device_simulator(unit=None):
    """Contract-shaped result: full Iris model is unavailable until certified."""
    manifest=HERE/'provenance.json'
    provenance=json.loads(manifest.read_text()) if manifest.exists() else {}
    return {'available':False,'binary':None,'binary_sha256':None,'isa_extensions':[],
            'provenance':provenance,
            'reason':'Experimental functional subset: Iris timing is uncalibrated; RTL certification, Zephyr SMP certification, and deployed-image association remain pending.'}

def _experimental_functional_simulator():
    """Explicit opt-in only; never masquerades as the full device simulator."""
    path=HERE/'provenance.json'
    if not path.exists():return {'available':False,'reason':'Missing build/selftest provenance'}
    data=json.loads(path.read_text());binary=Path(data['binary'])
    if not binary.exists() or _sha(binary)!=data['binary_sha256']:
        return {'available':False,'reason':'Binary missing or digest mismatch'}
    if _sha(HERE/'iris.patch')!=data['target_patch_sha256']:
        return {'available':False,'reason':'Source overlay digest mismatch'}
    required_inputs={'iris.patch','build.py','provider.py','functional_selftest.cc','decoder_cases.hpp'}
    if not required_inputs.issubset(data['source_inputs']):
        return {'available':False,'reason':'Required source input provenance missing'}
    for name,digest in data['source_inputs'].items():
        candidate=HERE/name
        if not candidate.is_file() or _sha(candidate)!=digest:
            return {'available':False,'reason':f'Source input digest mismatch: {name}'}
    for name,digest in data['external_source_inputs'].items():
        if not Path(name).is_file() or _sha(name)!=digest:
            return {'available':False,'reason':'External input digest mismatch'}
    for name,digest in data.get('external_evidence_inputs',{}).items():
        if not Path(name).is_file() or _sha(name)!=digest:
            return {'available':False,'reason':'External evidence digest mismatch'}
    reference=HERE/'bin/spike-zvt-reference'
    if not reference.is_file() or _sha(reference)!=data['reference_binary_sha256']:
        return {'available':False,'reason':'Reference binary digest mismatch'}
    hardware=HERE.parent/'hardware/manifest.json'
    if not hardware.is_file() or _sha(hardware)!=data['hardware_manifest_sha256']:
        return {'available':False,'reason':'Hardware manifest digest mismatch'}
    for name,digest in data['decoder_source_inputs'].items():
        if not Path(name).is_file() or _sha(name)!=digest:
            return {'available':False,'reason':'Decoder source digest mismatch'}
    device=HERE/'bin/libsifive_uart.so'
    if not device.is_file() or _sha(device)!=data['device_binary_sha256']:
        return {'available':False,'reason':'UART binary digest mismatch'}
    uart=data.get('uart_device_integration',{})
    if (data.get('device_implementation')!='iris-clocked-uart-source-bound' or
            uart.get('tested') is not True or uart.get('process_cases')!=12 or
            uart.get('unknown_rx_refusals')!=2 or uart.get('native_device_abi')!=1 or
            uart.get('native_plugin_mismatch_refused') is not True):
        return {'available':False,'reason':'Required finite-UART source/clock/ABI/process evidence missing'}
    for name,digest in data['evidence_inputs'].items():
        artifact=HERE/name
        if not artifact.is_file() or _sha(artifact)!=digest:
            return {'available':False,'reason':f'Evidence input digest mismatch: {name}'}
    tests=data['selftest']
    csr=tests.get('configured_csrs',{})
    if (csr.get('pass') is not True or csr.get('checks')!=1656 or csr.get('actual_csr_instructions')!=2031 or
            csr.get('harts')!=3 or csr.get('isa_profiles')!=2 or csr.get('hardware_hpm_count')!=0 or
            csr.get('generic_preserved') is not True or csr.get('binary_sha256')!=data['binary_sha256'] or
            csr.get('overlay_sha256')!=data['target_patch_sha256']):
        return {'available':False,'reason':'Required source-configured CSR handler coverage missing or stale'}
    native=tests.get('native_fp8',{})
    if native.get('pass') is not True or native.get('forms')!=45 or native.get('narrow_cases')!=20480 or native.get('wide_cases')!=11520 or native.get('reduction_cases')!=640:
        return {'available':False,'reason':'Required native FP8 oracle coverage missing or failed'}
    ieee=tests.get('ieee_fma',{})
    if ieee.get('pass') is not True or ieee.get('forms')!=45 or ieee.get('operation_cases')!=23360 or ieee.get('reduction_cases')!=1120 or ieee.get('scalar_bf16_illegal_cases')!=6 or ieee.get('hart2_ieee_flags') is not True:
        return {'available':False,'reason':'Required IEEE/BF16 source-policy oracle coverage missing or failed'}
    shared=tests.get('shared_fpu',{})
    if shared.get('pass') is not True or shared.get('forms')!=45 or shared.get('operation_cases')!=21000 or shared.get('reduction_cases')!=1200 or any(shared.get(key) is not True for key in ['masked_exception_flags','raw_vf_input','vstart_zero_required','fs_dirty_checked']):
        return {'available':False,'reason':'Required shared scalar-FPU source-policy oracle coverage missing or failed'}
    cmp=tests.get('fpcomp',{})
    cmp_counts={'forms':22,'operation_cases':8448,'handler_executions':12672,'illegal_sew8_cases':132,'generic_semantics_cases':9,'core_priority_cases':6,'vector_config_refusals':2}
    if cmp.get('pass') is not True or any(cmp.get(key)!=value for key,value in cmp_counts.items()) or any(cmp.get(key) is not True for key in ['source_selected_chunk_flags','mask_tail_checked','source_altfmt_checked']):
        return {'available':False,'reason':'Required FPComp source-policy oracle coverage missing or failed'}
    handler_modes={item.get('mode') for item in tests['handler_results'] if item.get('functional_handlers')=='pass'}
    if handler_modes!={'upstream-zvt','iris-experimental'} or not all(item.get('functional_handlers')=='pass' for item in tests['handler_results']):
        return {'available':False,'reason':'Required handler modes missing or failed'}
    required={'smoke','batch','batch-seed-1','batch-seed-1-repeat','batch-seed-2','fatal-entry','vme-directed','vme-directed-reference','vme-fused-lm2-gemm-transpose','vme-fused-lm2-gemm-transpose-reference','miles-heldout','miles-heldout-reference','miles-i8-heldout','miles-i8-heldout-reference','hart2-vector-arithmetic','hart2-vector-move','cpu-dtypes','vme-directed-mx','vme-directed-mx-reference','vme-fp8-directed','vme-fp8-directed-reference','vme-fp8-gemm','vme-fp8-gemm-reference','native-fp8','wide-reduce-fp8','ieee-bf16','shared-fpu','fpcomp','bitmanip','cease-capability','cpu_config'}
    required.add('csr_config')
    if not required.issubset({item['name'] for item in tests['guest_results']}):
        return {'available':False,'reason':'Required guest coverage missing'}
    for test in tests['guest_results']:
        elf=Path(test['argv'][-1]);out=HERE/'results'/f"{test['name']}.stdout";err=HERE/'results'/f"{test['name']}.stderr"
        if any(not p.is_file() or _sha(p)!=h for p,h in [(elf,test['elf_sha256']),(out,test['stdout_sha256']),(err,test['stderr_sha256'])]):
            return {'available':False,'reason':f"Selftest evidence digest mismatch: {test['name']}"}

    if not tests['handler_results'] or not tests['guest_results'] or not all(t['pass'] is True for t in tests['guest_results']):
        return {'available':False,'reason':'Functional selftests incomplete or failed'}
    return {'available':True,'binary':str(binary),'binary_sha256':data['binary_sha256'],
            'isa_extensions':['zfh','zvfh','zba','zbb','zbs','zvbb','zvt32t','zvti8i32mm','zvtofp8fmm','zvfofp8min','zvfbfmin','zvfbfa'],
            'per_hart_isa':data.get('launch_isa',{}),'datatype_coverage':data.get('datatype_coverage',{}),
            'provenance':data,'uart_device_tested':True,'uart_rx_pin_sampling_qualified':False,'timing_available':False,'timing_adapter_available':data.get('live_integration_fixture',{}).get('tested') is True,'timing_calibrated':False,'physical_board_adapter_tested':data.get('physical_board_integration',{}).get('tested') is True,'plic_adapter_tested':data.get('plic_process_integration',{}).get('tested') is True,'scalar_memory_adapter_tested':data.get('scalar_memory_live_integration',{}).get('tested') is True,'scalar_memory_scope':data.get('scalar_memory_live_integration',{}).get('scope'),'scalar_memory_timing_calibrated':False,'vector_memory_timing_qualified':False,'cache_coherence_timing_qualified':False,'zephyr_smp_certified':False}

def device_simulator(unit=None):
    try:return _device_simulator(unit)
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:
        return {'available':False,'binary':None,'binary_sha256':None,'isa_extensions':[],'provenance':{},'reason':f'Invalid provenance: {error}'}

def experimental_functional_simulator():
    try:return _experimental_functional_simulator()
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:
        return {'available':False,'reason':f'Invalid provenance: {error}'}

if __name__=='__main__':print(json.dumps(device_simulator(),indent=2))

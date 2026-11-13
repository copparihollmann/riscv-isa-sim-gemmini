"""Fixed-schema optional finite RVV7108 model; no default/full provider changes."""
import hashlib
import json
import math
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MODEL_KIND = 'fitted7108-finite-RVV1320-TRAIN978-v1'
CORE = {
 'native_binary': ('build/warm-OPU-frozen-7108a6ec-v1/spike', '7108a6ecfd98e6d8c4c983f7b089dbda99d4a143e7e189a7b99eedc322d79d27'),
 'uart_library': ('build/warm-OPU-frozen-7108a6ec-v1/libsifive_uart.so', 'bfa133c06eadfacf29d816df844b1ee18eb51da249e7668d77aac78415cc0d30'),
 'fixture': ('calibration/rvv-compute1320-TRAIN-runtime-v1/runtime.fixture', 'd509e5d3bfb3f44c0ae017fabea5c07946e0404df62eea1483bcec7e72cf0999'),
 'binary': ('build/rvv-compute1320-fitted-launcher-v1/spike', '319e76dc035d6c6ce316ac753531d5321bd673a8d1646f92ea16b665381cf61a'),
 'bootrom': ('board/evidence/bootrom.rv64.img', '5f6ae520d6612da2b31c2ee70bc872b743a77bbde0abba87bf96aa5fc249a216'),
 'dtb': ('board/build/iris.dtb', '622c099a1dbcc87473d0760b1ec5b366c296d964aec834722d3c5ba0e4a95c78')}
EVIDENCE = {'capsule': ('build/warm-OPU-frozen-7108a6ec-v1/manifest.json', '7391e5fd64327d0179ee86c130f71f894b3f13655586b932606ad4d00a8e3a43'), 'source_verification': ('build/warm-OPU-frozen-7108a6ec-v1/verification.json', '17c6553b58e777d26fb1463a4773a007ec5adc48901c70407be6f3976532eda6'), 'replay': ('build/rvv-compute1320-fitted-replay-closure-v1/report.json', '35d731de3ce7b52bd76b27cbadc0fc2e2893514d865507810dc4639877c2134f'), 'runtime_QA': ('build/rvv-compute1320-fitted-runtime-QA-closure-v1/report.json', '5e5bb9a48db9a26eb8bedf6df92062fa6ad6065dba0a31eeeb598741ebf5cf55'), 'compiler': ('build/rvv-compute1320-fitted-compiler-images-parallel-v1/report.json', '3d1d54657ef9e6b95bd2cd35ccd805a2d77705194e55994e9b62a464206831cf'), 'Zephyr': ('build/rvv-compute1320-fitted-Zephyr-five-v1/report.json', '32b2fd2ab4ae3998b4135342a58f744e1ca00fa9d29bcc743b9c2767d55e0f0a'), 'smoke_time': ('build/rvv-compute1320-fitted-smoke-time-selftest-v3/report.json', '374676bc3500d93501a0f4a45fff50d381c495528fbb1edf37d29c8840211ff3'), 'fatal': ('build/rvv-compute1320-fitted-launcher-fatal-gates-v1/report.json', '9c7370478affd94421a9aba9d64cf66fdba2daf697373e9ee1c9077f86cde78f'), 'TRAIN_comparison': ('build/rvv-compute1320-TRAIN-fitted-comparison-v1/report.json', '2e92ad84fdec40aba53213dcda2d3e33a19431b63255a5f8407c21deebdbbda1'), 'fit_proposal': ('calibration/rvv-compute1320-TRAIN-proposal-v1/report.json', '922e62bee4b5e1dc4ddfc75d2b3f20b3463e1f7bbcfb7fc4b2a84230118a909f'), 'mapping': ('calibration/rvv-compute1320-TRAIN-runtime-v1/mapping.json', '021d6c3008baffafb281e674a4f20d8bb58fc796e951065019c6a56445d3371c'), 'fit_plan': ('calibration/rvv-compute1320-v1/fit-plan.json', '75703735513a44552eb0565e902048e236642b6eebe99d7db0ce4c5960c5c16f'), 'parameters': ('calibration/rvv-compute1320-TRAIN-runtime-v1/parameters.json', '95cebff8a4d87a88e2e505c5dca631b0822d4eebb555133c318af79ab9a0efd9')}
COMPUTE_ISA = 'rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
ISA = {'0':COMPUTE_ISA,'1':COMPUTE_ISA,'2':'rv64gcv_zfh_zvfh_zvl256b_zvbb'}
MEMORY = [[0x70000000,0x40000],[0x80000000,0x100000000],[0x580000000,0x20000]]
QUALIFICATION = {k:False for k in ('full_model_certified','accuracy_2percent_certified','physical_traffic_certified','source_image_association_verified','hart2_timing_accuracy_certified','heldout_acceptance_claimed')}

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def document(path):
    def pairs(rows):
        out={}
        for k,v in rows:
            if k in out:raise ValueError('Duplicate JSON key: '+k)
            out[k]=v
        return out
    def bad(v):raise ValueError('Nonfinite JSON: '+v)
    def finite(v):
        x=float(v)
        if not math.isfinite(x):bad(v)
        return x
    d=json.loads(Path(path).read_text(),object_pairs_hook=pairs,parse_constant=bad,parse_float=finite)
    if not isinstance(d,dict):raise ValueError('JSON object required')
    return d

def need(ok,message):
    if not ok:raise ValueError(message)

def checked(inputs,path,expected=None):
    p=Path(path);key=str(p)
    want=expected if expected is not None else inputs.get(key)
    need(p.is_absolute() and p.is_file() and isinstance(want,str) and re.fullmatch('[0-9a-f]{64}',want), 'Missing typed absolute input: '+key)
    need(inputs.get(key)==want and sha(p)==want,'Changed model input: '+key)
    return p

def evidence_files(value):
    """Keep every declared source/raw execution proof in the runtime closure."""
    result={}
    def visit(obj):
        if isinstance(obj,dict):
            for key,items in obj.items():
                if key.endswith('sha256') and isinstance(items,dict):
                    for name,want in items.items():
                        if isinstance(name,str) and name.startswith('/') and isinstance(want,str) and re.fullmatch('[0-9a-f]{64}',want):
                            need(name not in result or result[name]==want,'Conflicting evidence file identity')
                            result[name]=want
                visit(items)
        elif isinstance(obj,list):
            for item in obj:visit(item)
    visit(value)
    return result

def launch_args():
    p={k:str(ROOT/v[0])for k,v in CORE.items()}
    return ['--iris-vme','--extlib='+p['uart_library'],'--device=sifive_uart,0x10020000',
            '--iris-bootrom='+p['bootrom'],'--dtb='+p['dtb'],'--iris-timing-fixture='+p['fixture']]

def verify(manifest):
    path=Path(manifest).resolve();m=document(path)
    need(m.get('schema')=='iris.empirical_simulator.v1' and m.get('package_kind')==MODEL_KIND,'Only fixed fitted7108 finite model schema is accepted')
    need(m.get('mode')=='experimental_finite_calibration' and m.get('calibration_identity')==MODEL_KIND,'Explicit experimental model selection required')
    inputs=m.get('input_sha256');need(isinstance(inputs,dict) and bool(inputs),'Full nonempty input closure required')
    for name,want in inputs.items():checked(inputs,name,want)
    need(m.get('model_provider')==str(Path(__file__).resolve()),'Wrong fixed-schema provider')
    checked(inputs,Path(__file__).resolve())
    for key,(relative,want)in CORE.items():
        need(m.get(key)==str(ROOT/relative),'Wrong fixed '+key)
        checked(inputs,ROOT/relative,want)
    need(m.get('binary_sha256')==CORE['binary'][1] and m.get('native_binary_sha256')==CORE['native_binary'][1] and m.get('uart_library_sha256')==CORE['uart_library'][1],'Executable identity fields mismatch')
    need(m.get('native_device_abi')==4 and type(m['native_device_abi'])is int,'Device ABI4 required')
    need(m.get('per_hart_isa')==ISA and m.get('memory_regions')==MEMORY and m.get('matrix_hart_ids')==[0,1],'Fixed real three-hart ISA/memory geometry required')
    need(m.get('launch_args')==launch_args(),'Fixed boot/device/fixture arguments required')
    need(m.get('qualification')==QUALIFICATION and all(type(v)is bool for v in m['qualification'].values()),'Unqualified experimental scope must remain explicit')
    need(m.get('runtime_environment')=={k:None for k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')},'Fixed loader environment required')
    need(not any(os.environ.get(k) for k in m['runtime_environment']),'Loader overrides are not admitted')
    reports={}
    need(m.get('evidence')=={k:str(ROOT/v[0])for k,v in EVIDENCE.items()},'Fixed evidence paths required')
    for k,(relative,want)in EVIDENCE.items():reports[k]=document(checked(inputs,ROOT/relative,want))
    for name,want in evidence_files(reports).items():checked(inputs,name,want)
    need(all(reports[k].get('pass')is True for k in ('capsule','source_verification','replay','runtime_QA','Zephyr','smoke_time','fatal','mapping')),'Bound source/replay/runtime gates must pass')
    need(reports['compiler'].get('passed')is True and len(reports['compiler'].get('cases',[]))==8 and all(c.get('passed')is True and c.get('normal_guest_exit_verified')is True and c.get('returncode')==0 for c in reports['compiler']['cases']),'All eight actual compiler image gates required')
    need(len(reports['Zephyr'].get('runs',[]))==5 and all(r.get('pass')is True and r.get('exit_status')==0 and r.get('timed_out')is False for r in reports['Zephyr']['runs']),'All five actual normal Zephyr/context gates required')
    need(reports['replay'].get('regions')==1320 and reports['replay'].get('per_element_word_checks')==184128 and reports['replay'].get('actual_CSR_ELF_endpoint_joins')==3960 and reports['replay'].get('intentional_postmeasurement_debugger_stop')is True and reports['replay'].get('normal_native_guest_exit_verified')is False,'Exact1320 debugger readback scope required')
    f=reports['fatal']
    need(f.get('fatal_harts_verified')==[0,1,2] and f.get('parser_policy')=='fatal-ELF-exec-v2' and all(f.get(k)is True for k in ('recoverable_trap_verified','normal_numeric_counter_parity_verified','stripped_ELF_refused','parser_negative_controls_passed')) and len(f.get('runs',[]))==7,'Seven fatal-aware launcher controls required')
    need(reports['smoke_time'].get('three_harts_numerically_verified')is True and reports['smoke_time'].get('modeled_time_sensitivity_verified')is True,'Actual three-hart numerical and clock sensitivity proof required')
    for key in ('replay','runtime_QA','Zephyr','smoke_time','fatal'):
        r=reports[key]
        need(r.get('fixture_sha256')==CORE['fixture'][1],'Evidence bound to another fitted fixture: '+key)
    need(reports['parameters'].get('protected_or_reserved_labels_consumed')is False,'Fit must preserve blind reserved labels')
    need(reports['parameters'].get('plan_sha256')==EVIDENCE['fit_plan'][1],'Frozen978 plan mismatch')
    # Validate the actual source reconstruction receipt and fixed archived inputs.
    capsule=ROOT/'build/warm-OPU-frozen-7108a6ec-v1'
    for name,want in reports['capsule']['artifact_sha256'].items():checked(inputs,capsule/name,want)
    for name,want in document(capsule/'compiled-inputs.json').items():checked(inputs,name,want)
    for name,want in evidence_files(document(capsule/'pipeline-build.json')).items():checked(inputs,name,want)
    closure=document(checked(inputs,m['source_closure']))
    need(closure.get('schema')=='iris.rvv7108_source_snapshot_verification.v1' and closure.get('pass')is True and closure.get('native_sources')==2138 and closure.get('manifest_sha256')==EVIDENCE['capsule'][1],'Verified fixed source snapshot required')
    for name,want in closure.get('input_sha256',{}).items():checked(inputs,name,want)
    return {'available':True,'binary':m['binary'],'binary_sha256':m['binary_sha256'],
        'native_binary':m['native_binary'],'native_binary_sha256':m['native_binary_sha256'],
        'automatic_fatal_handler_resolution':True,'native_device_abi':4,
        'per_hart_isa':ISA,'matrix_hart_ids':[0,1],'memory_regions':MEMORY,'launch_args':launch_args(),
        'execution_input_sha256':{**inputs,str(path):sha(path)},
        'timing_available':True,'timing_status':'experimental_finite_calibration',
        'timing_calibrated':False,'rtl_certified':False,'accuracy_2percent_certified':False,
        'whole_model_certified':False,'hart2_timing_accuracy_certified':False,
        'timing_scope':'harts0/1 RVV finite978-TRAIN fit; whole-VRF/blocked-memory structural limits; hart2 functional control only',
        'training_metrics':reports['TRAIN_comparison']['groups']['all'],
        'validation_metrics':None,
        'functional_scope':'Eight preserved compiler image gates; five actual Zephyr/context groups; three-hart smoke/time/fatal controls',
        'provenance':{'manifest':str(path),'manifest_sha256':sha(path),'evidence':m['evidence'],'source_closure':m['source_closure'],'qualification':QUALIFICATION}}

def experimental_empirical_simulator(manifest):
    try:return verify(manifest)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,IndexError) as e:
        return {'available':False,'reason':'Fixed fitted7108 model refused: '+str(e),'timing_available':False,'whole_model_certified':False}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(__doc__);p.add_argument('--model',type=Path,required=True);a=p.parse_args()
    result=experimental_empirical_simulator(a.model);print(json.dumps(result,indent=2));raise SystemExit(0 if result['available']else 1)

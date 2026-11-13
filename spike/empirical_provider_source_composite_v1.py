"""Optional fixed02b4 source prototype with separate compute and OS profiles."""
import hashlib,json,math,os,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike.empirical_launch_v2 import launcher_text
MODEL_KIND='source-composite-02b4-finite-v1'
CAPSULE=ROOT/'build/C12-source-composite-frozen-02b4a9ab-v2'
NATIVE_SHA='02b4a9ab4c00a506e6ed3def6cb33ca0d9cc697951afaa02afc47e9ddce64577'
UART_SHA='8903d961a7b07265b6040fc43b761f3e10328d4ee34dab7919a2c59fa89375c4'
CAPSULE_SHA='4dc93c84b3d2e52dbc0a3af1d48e22d3bd613dc122e5e11d022d019a6f59b1d4'
ROOT_QA=(ROOT/'build/C12-source-composite-runtime-QA-root-closure-v1/report.json','c94687ed4369b0b67e2b0b3d228c20da8fa9018df44d783fe686e53b574b8d4e')
CORE={
 'native_binary':(CAPSULE/'spike',NATIVE_SHA),
 'uart_library':(CAPSULE/'libsifive_uart.so',UART_SHA),
 'binary':(ROOT/'build/C12-source-composite-launcher-v1/spike','619a8c114fe56400b4515a2d72f90ecbd86f432d58cb02f6fa818fe5903a8eb4'),
 'bootrom':(ROOT/'board/evidence/bootrom.rv64.img','5f6ae520d6612da2b31c2ee70bc872b743a77bbde0abba87bf96aa5fc249a216'),
 'dtb':(ROOT/'board/build/iris.dtb','622c099a1dbcc87473d0760b1ec5b366c296d964aec834722d3c5ba0e4a95c78')}
PROFILES={
 'source_compute':dict(fixture=ROOT/'build/C12-source-composite-inputs-v1/fixed-costs-ON.fixture',fixture_sha256='cce26e362f96374abb992b2062781ad46a75734185ab7c8cb02a135c31bfd260',identity='iris-C12-source-composite-fixed-costs-v1',source_OPU=True,specialized_OPU_FENCE=True,normal_Zephyr_qualification_claimed=False,compute_timing_qualification_transferred=False),
 'source_os':dict(fixture=ROOT/'build/C12-source-composite-inputs-v1/fixed-costs-OPU-OFF.fixture',fixture_sha256='97ef45bb2cfb7144a1798e594df8065a55989980c8b406d0fe1e221597ef1bcb',identity='iris-C12-source-composite-fixed-costs-OPU-OFF-v1',source_OPU=False,specialized_OPU_FENCE=False,normal_Zephyr_qualification_claimed=True,compute_timing_qualification_transferred=False)}
GATES={'source_compute': {'smoke_time': ('/scratch/copparihollmann/iris-model/build/C12-source-composite-compute-selftest-v2/report.json', 'd1590c2517ecd806a155b0c522c0f49294e78272e1acc2d1f667edf036794ebe'), 'fatal_launcher': ('/scratch/copparihollmann/iris-model/build/C12-source-composite-compute-launcher-gates-v1/report.json', 'edc3b75b690ecb7184718d306f5fbf64bbb78909d8e6972af9ac2a59475fab4a')}, 'source_os': {'smoke_time': ('/scratch/copparihollmann/iris-model/build/C12-source-composite-OS-selftest-v2/report.json', '9312e5d272b4f34c69040d84d85fde90d19610350e920add82c34af41da36a41'), 'fatal_launcher': ('/scratch/copparihollmann/iris-model/build/C12-source-composite-OS-launcher-gates-v1/report.json', '1ec7837ad65dbb9ea17932960a25a39b04af470c3d239aa8357bc4b8acaf438e')}}
COMPUTE_ISA='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
ISA={'0':COMPUTE_ISA,'1':COMPUTE_ISA,'2':'rv64gcv_zfh_zvfh_zvl256b_zvbb'}
MEMORY=[[0x70000000,0x40000],[0x80000000,0x100000000],[0x580000000,0x20000]]
QUALIFICATION={k:False for k in('full_model_certified','accuracy_2percent_certified','physical_traffic_certified','source_image_association_verified','hart2_timing_accuracy_certified','active_per_EG_FADD_preemption_certified','blanket_heldout_acceptance_claimed')}
ROOT_PYTHON=Path('/usr/bin/python3.9')
ROOT_PYTHON_SHA='fc5d8335739e1ef3358c84b0d36945c7e489a2be2dd7dfd7a8f6c2aaf3f6d009'
LAUNCHER_TEMPLATE_SHA='5537a44f86a31855954cdf3c2fbdbdd5c9205f4393faaa2e6e72f75f38051c6d'
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


def launch_args(profile):
 p=PROFILES[profile]
 return ['--iris-vme','--extlib='+str(CORE['uart_library'][0]),'--device=sifive_uart,0x10020000','--iris-bootrom='+str(CORE['bootrom'][0]),'--dtb='+str(CORE['dtb'][0]),'--iris-timing-fixture='+str(p['fixture'])]

def verify(manifest):
 path=Path(manifest).resolve();m=document(path)
 need(m.get('schema')=='iris.empirical_simulator.v1'and m.get('package_kind')==MODEL_KIND,'Fixed02b4 finite source prototype required')
 profile=m.get('profile');need(profile in PROFILES,'Explicit source_compute or source_os profile required');p=PROFILES[profile]
 need(m.get('mode')=='experimental_source_prototype'and m.get('calibration_identity')==p['identity'],'Explicit profile identity required')
 scope={k:v for k,v in p.items()if k not in('fixture','fixture_sha256','identity')}
 need(m.get('profile_scope')==scope and all(type(m['profile_scope'][k])is type(v)for k,v in scope.items()),'Cross-profile scope transfer refused')
 inputs=m.get('input_sha256');need(isinstance(inputs,dict)and inputs,'Full input closure required')
 for name,want in inputs.items():checked(inputs,name,want)
 need(m.get('model_provider')==str(Path(__file__).resolve()),'Fixed provider required');checked(inputs,Path(__file__).resolve())
 for key,(file,want)in CORE.items():need(m.get(key)==str(file),'Wrong fixed '+key);checked(inputs,file,want)
 need(m.get('fixture')==str(p['fixture']),'Cross-profile fixture refused');checked(inputs,p['fixture'],p['fixture_sha256'])
 need(m.get('native_binary_sha256')==NATIVE_SHA and m.get('uart_library_sha256')==UART_SHA and m.get('binary_sha256')==CORE['binary'][1],'Executable identity mismatch')
 need(m.get('native_device_abi')==4 and type(m['native_device_abi'])is int,'DeviceABI4 required')
 need(m.get('per_hart_isa')==ISA and m.get('memory_regions')==MEMORY and m.get('matrix_hart_ids')==[0,1],'Fixed3hart ISA/memory required')
 need(m.get('launch_args')==launch_args(profile),'Fixed profile boot/fixture arguments required')
 need(m.get('qualification')==QUALIFICATION and all(type(v)is bool for v in m['qualification'].values()),'Experimental limits must remain explicit')
 need(m.get('runtime_environment')=={k:None for k in('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')},'Fixed loader policy required');need(not any(os.environ.get(k)for k in m['runtime_environment']),'Loader overrides refused')
 need(m.get('root_QA_closure')==str(ROOT_QA[0]),'Fixed root QA closure required');q=document(checked(inputs,*ROOT_QA))
 need(q.get('schema')=='iris.source_composite_runtime_QA_root_closure.v1'and q.get('pass')is True and q.get('native_binary_sha256')==NATIVE_SHA and q.get('UART_sha256')==UART_SHA and q.get('capsule_manifest_sha256')==CAPSULE_SHA,'Root native QA closure must pass')
 need(q.get('compute_fixture_sha256')==PROFILES['source_compute']['fixture_sha256']and q.get('OS_fixture_sha256')==PROFILES['source_os']['fixture_sha256'],'Root profile fixtures mismatch')
 need(q.get('default_pointer_changed')is False and q.get('all_accuracy_2percent_certified')is False and q.get('source_image_association_verified')is False,'Root finite qualification scope required')
 need(m.get('opaque_validation_report')==q['validation_report'],'Opaque root validation binding required')
 # Deliberately digest only: no validation JSON parse or timing fields accessed.
 checked(inputs,q['validation_report']['path'],q['validation_report']['sha256'])
 for e in q['evidence'].values():checked(inputs,e['path'],e['sha256'])
 f=document(Path(q['evidence']['functional32']['path']));need(f.get('status')=='passed_frozen_functional32_exact_stdout'and f.get('binary_sha256')==NATIVE_SHA and len(f.get('rows',[]))==32 and all(r.get('pass_')is True for r in f['rows']),'Exact02b4 canonical32OFF proof required')
 own=document(Path(q['evidence']['compiler8'if profile=='source_compute'else'five_OS']['path']))
 if profile=='source_compute':
  need(own.get('pass')is True and len(own.get('cases',[]))==8 and all(r.get('pass')is True and r.get('normal_guest_exit')is True and r.get('exit_status')==0 and '--iris-timing-fixture='+str(p['fixture'])in r['argv']for r in own['cases']),'Eight exact compute profile normal compiler gates required')
 else:
  need(own.get('pass')is True and own.get('native_sha256')==NATIVE_SHA and own.get('fixture_sha256')==p['fixture_sha256']and len(own.get('runs',[]))==5 and all(r.get('pass')is True and r.get('exit_status')==0 and r.get('timed_out')is False for r in own['runs']),'Five exact OS profile normal context gates required')
 for name,want in evidence_files({'functional32':f,'profile_QA':own}).items():checked(inputs,name,want)
 for row in f['rows']:
  base=Path(q['evidence']['functional32']['path']).parent
  checked(inputs,base/(row['name']+'.stdout'),row['stdout_sha256']);checked(inputs,base/(row['name']+'.stderr'),row['stderr_sha256'])
 if profile=='source_os':
  for row in own['runs']:
   child=document(checked(inputs,row['child_receipt'],row['child_receipt_sha256']))
   for name,want in evidence_files(child).items():checked(inputs,name,want)
 need(profile in GATES and m.get('own_package_gates')=={k:str(v[0])for k,v in GATES[profile].items()},'Own profile package gates required')
 gates={k:document(checked(inputs,*v))for k,v in GATES[profile].items()}
 s=gates['smoke_time'];g=gates['fatal_launcher']
 need(s.get('pass')is True and s.get('native_binary_sha256')==NATIVE_SHA and s.get('fixture_sha256')==p['fixture_sha256']and s.get('three_harts_numerically_verified')is True and s.get('modeled_time_sensitivity_verified')is True,'Exact own threehart normal/sensitivity gate required')
 need(g.get('pass')is True and g.get('native_binary_sha256')==NATIVE_SHA and g.get('fixture_sha256')==p['fixture_sha256']and g.get('launcher_sha256')==CORE['binary'][1]and g.get('fatal_harts_verified')==[0,1,2]and g.get('stripped_ELF_refused')is True and len(g.get('runs',[]))==7,'Exact own fatal-aware launcher gates required')
 for name,want in evidence_files(gates).items():checked(inputs,name,want)
 capsule=document(checked(inputs,CAPSULE/'manifest.json',CAPSULE_SHA))
 for name,want in capsule['artifact_sha256'].items():checked(inputs,CAPSULE/name,want)
 for name,want in document(CAPSULE/'compiled-inputs.json').items():checked(inputs,name,want)
 need(m.get('source_closure')==str(path.parent.parent/'source-closure.json'),'Fixed package source-closure path required')
 closure=document(checked(inputs,m['source_closure']))
 need(closure.get('schema')=='iris.source_composite_source_snapshot.v1'and closure.get('pass')is True and closure.get('native_sources')==2141 and closure.get('capsule_manifest_sha256')==CAPSULE_SHA,'Actual source snapshot verification required')
 for name,want in closure['input_sha256'].items():checked(inputs,name,want)
 py=ROOT_PYTHON
 checked(inputs,py,ROOT_PYTHON_SHA);checked(inputs,ROOT/'spike/empirical_launch_v2.py',LAUNCHER_TEMPLATE_SHA)
 need(CORE['binary'][0].read_text()==launcher_text(CORE['native_binary'][0],NATIVE_SHA,py,ROOT_PYTHON_SHA),'Exact isolated fatal-aware launcher template required')
 return dict(available=True,binary=m['binary'],binary_sha256=m['binary_sha256'],native_binary=m['native_binary'],native_binary_sha256=NATIVE_SHA,native_device_abi=4,automatic_fatal_handler_resolution=True,per_hart_isa=ISA,matrix_hart_ids=[0,1],memory_regions=MEMORY,launch_args=launch_args(profile),execution_input_sha256={**inputs,str(path):sha(path)},timing_available=True,timing_status='experimental_source_prototype',timing_calibrated=False,rtl_certified=False,accuracy_2percent_certified=False,whole_model_certified=False,hart2_timing_accuracy_certified=False,timing_scope='Explicit'+profile+' finite harts0/1 source control with inherited effective costs; no blanket accuracy/physical/full-CPU qualification',validation_metrics=None,functional_scope=q['profiles'][profile],provenance=dict(manifest=str(path),manifest_sha256=sha(path),profile=profile,root_QA_closure=str(ROOT_QA[0]),root_QA_closure_sha256=ROOT_QA[1],opaque_validation_report=q['validation_report'],source_closure=m['source_closure'],qualification=QUALIFICATION))

def experimental_empirical_simulator(manifest):
 try:return verify(manifest)
 except(OSError,ValueError,KeyError,TypeError,AttributeError,IndexError)as e:return dict(available=False,reason='Fixed02b4 source profile refused: '+str(e),timing_available=False,whole_model_certified=False)

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(__doc__);p.add_argument('--model',type=Path,required=True);a=p.parse_args();result=experimental_empirical_simulator(a.model);print(json.dumps(result,indent=2));raise SystemExit(0 if result['available']else 1)

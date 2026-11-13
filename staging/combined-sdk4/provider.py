"""Byte-bound SDK4 provider. Full Iris timing certification remains unavailable."""
import gzip
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PIN='72958551566a30f19444bd7e354552824e4d0a98'
BINARY='35901887c93ab80aa92e68aac2f26cefa6cc785ae8251d5dc283471aa97faf5d'
UART='cc9e38b8df42c0f482f94213a0f58747e1e1c66bd17d54eef154e3ea9748a34b'
OVERLAY='e33269e90102a8a9137473eb4d6a0c7c276a2553972ab4e668ab62f041a82060'
FROZEN='ef1214f25a2db5a01b6dd9aa1180b002c0f4da74ec987ac0a5b90bff10ed7088'
OS_COMPANION='0d690772b1708e548add3afba012b8fa39fd8ae17c3497c2dd51eafb97eaf9fe'
COMPUTE='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
DMA='rv64gcv_zfh_zvfh_zvl256b_zvbb'
GROUPS={'combined-mask-final','combined-mask-pipeline','combined-knownness-functional','combined-knownness-pipeline',
    'combined-handlers','combined-functional','combined-counter-directed','combined-counter-forms','combined-pipeline-directed',
    'combined-csr-signatures','combined-csr-generic','combined-live-initialized','combined-memory','combined-counter-edges',
    'combined-uart','combined-sdk','combined-address-knownness','combined-physical','combined-plic'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def local(name):
    path=(HERE/name).resolve()
    if not path.is_relative_to(HERE.resolve())or not path.is_file():raise ValueError('Package file absent/outside closure: '+str(name))
    return path

def load(name):return json.loads(local(name).read_text())
def require(condition,message):
    if not condition:raise ValueError(message)

def verify():
    p=load('provenance.json')
    require(p.get('schema')=='iris.combined_sdk4.package.v1'and p.get('status')=='experimental_functional_ready','Package not ready')
    require(p['upstream_spike_sha']==PIN and p['target_patch_sha256']==OVERLAY,'Wrong source epoch')
    require(p['binary_sha256']==BINARY and p['device_binary_sha256']==UART and p['native_device_abi']==4,'Wrong SDK4 byte epoch')
    require(p['launch_isa']=={'0':COMPUTE,'1':COMPUTE,'2':DMA},'Per-hart ISA policy changed')
    require(p['memory_regions']==[[0x70000000,0x40000],[0x80000000,0x100000000],[0x580000000,0x20000]],'Board memory policy changed')
    require(set(p['per_hart'])=={'0','1','2'}and all(p['per_hart'][str(h)]['vlen_bits']==256
        and p['per_hart'][str(h)]['dlen_bits']==(128 if h<2 else 256)
        and p['per_hart'][str(h)]['matrix_unit']is(h<2)for h in range(3)),'Per-hart core metadata changed')
    require(all(p.get(k)is False for k in ['rtl_certified','timing_calibrated','held_out_2pct','deployed_image_association_verified',
        'full_knownness_certified','full_zephyr_or_model_certified']),'Unqualified certification flags')
    required={'provider.py','build.py','launch.py','iris.patch','source-lock.json','bin/spike','bin/libsifive_uart.so',
        'evidence/rebuild.json','evidence/packaged-rebuild.json','evidence/combined/manifest.json','evidence/os/report.json','selftest/results.json'}
    require(required.issubset(p['input_sha256']),'Required package closure absent')
    for name,value in p['input_sha256'].items():require(sha(local(name))==value,'Package input changed: '+name)
    require(sha(local('bin/spike'))==BINARY and sha(local('bin/libsifive_uart.so'))==UART,'Binary/UART mismatch')
    require(sha(local('iris.patch'))==OVERLAY,'Wrong overlay')
    lock=load('source-lock.json')
    require(lock['base_commit']==PIN and lock['source_overlay_sha256']==OVERLAY and lock['native_device_abi']==4,'Source-lock identity mismatch')
    for name,value in lock['input_sha256'].items():require(sha(local('source/'+name))==value,'Source snapshot changed: '+name)
    rebuild=load('evidence/rebuild.json')
    require(rebuild['binary_byte_identical']is True and rebuild['uart_byte_identical']is True,'Rebuild is a different byte epoch')
    require(rebuild['binary_sha256']==BINARY and rebuild['uart_sha256']==UART and rebuild['source_overlay_sha256']==OVERLAY,'Rebuild identity mismatch')
    packaged=load('evidence/packaged-rebuild.json')
    require(packaged['source_mode']=='packaged_source_snapshot'and packaged['binary_byte_identical']is True
        and packaged['uart_byte_identical']is True and packaged['binary_sha256']==BINARY and packaged['uart_sha256']==UART,
        'Packaged builder does not reproduce this native/UART epoch')
    capsule=load('evidence/combined/manifest.json')
    require(sha(local('evidence/combined/manifest.json'))==FROZEN,'Combined proof identity mismatch')
    require(capsule['binary_sha256']==BINARY and capsule['uart_sha256']==UART and capsule['native_device_abi']==4,'Combined proof pair mismatch')
    objects={};receipt_payloads={};receipt_hashes={item['sha256']for item in capsule['local_receipts'].values()}
    for name,item in capsule['files'].items():
        value=item['sha256']
        if value not in objects:
            raw=local('evidence/combined/'+item['object']).read_bytes()
            require(hashlib.sha256(raw).hexdigest()==item['object_sha256'],'Proof object changed: '+name)
            data=gzip.decompress(raw)if item['compression']=='gzip'else raw
            require(len(data)==item['bytes']and hashlib.sha256(data).hexdigest()==value,'Proof payload changed: '+name)
            objects[value]=True
            if value in receipt_hashes:receipt_payloads[value]=data
    receipts=capsule['local_receipts']
    require({Path(name).parent.name for name in receipts}==GROUPS,'Required19 local proof groups absent')
    for name,item in receipts.items():
        value=capsule['files'][name]['sha256'];require(value==item['sha256'],'Receipt hash association mismatch')
        receipt=json.loads(receipt_payloads[value]);require(receipt['status']==item['status']and receipt['status'].startswith('passed'),'Local proof failed')
        if 'binary_sha256'in receipt:require(receipt['binary_sha256']==BINARY,'Local proof belongs to another native')
        if 'uart_sha256'in receipt:require(receipt['uart_sha256']==UART,'Local proof belongs to another UART')
    companion=load('evidence/os/report.json')
    require(sha(local('evidence/os/report.json'))==OS_COMPANION,'OS companion identity mismatch')
    require(companion['pass']is True and companion['binary_sha256']==BINARY and companion['uart_sha256']==UART
        and companion['source_closure_sha256']==FROZEN,'OS evidence not bound to native/source pair')
    require(len(companion['gates'])==7 and companion['profiled_regions']==9,'Required OS/compiler/profile gates absent')
    for name,value in companion['artifact_sha256'].items():require(sha(local('evidence/os/'+name))==value,'OS evidence changed: '+name)
    test=load('selftest/results.json')
    require(test['pass']is True and test['binary_sha256']==sha(local('launch.py'))and test['native_binary_sha256']==BINARY
        and test['uart_sha256']==UART and test['region_count']==12,'Fresh smoke evidence missing')
    require(sha(local('selftest/stdout'))==test['stdout_sha256']and sha(local('selftest/stderr'))==test['stderr_sha256'],'Smoke raw evidence changed')
    return p

def device_simulator(unit=None,config=None):
    """Default full-model contract: unavailable until complete accuracy proof."""
    return {'available':False,'binary':None,'binary_sha256':None,'isa_extensions':[],
        'provenance':{'mode':'full_model','native_device_abi':4},
        'reason':'Full Iris model unavailable: experimental functional coverage; full RTL/image association and calibrated timing remain unqualified.'}

def experimental_functional_simulator():
    """Explicitly selected functional mode, with immutable complete proof closure."""
    try:
        p=verify()
        return {'available':True,'binary':str(local('launch.py')),'binary_sha256':sha(local('launch.py')),
            'native_binary':str(local('bin/spike')),'native_binary_sha256':BINARY,
            'isa_extensions':p['isa_extensions'],'per_hart_isa':p['launch_isa'],'datatype_coverage':p['datatype_coverage'],
            'matrix_hart_ids':[0,1],'launch_args':['--iris-vme','--extlib='+str(local('bin/libsifive_uart.so')),
                '--device=sifive_uart,0x10020000','--iris-bootrom='+str(local('board/bootrom.rv64.img')),'--dtb='+str(local('board/iris.dtb'))],
            'memory_regions':p['memory_regions'],'provenance':p,'native_device_abi':4,
            'timing_available':False,'timing_adapter_available':True,'timing_calibrated':False,'rtl_certified':False,
            'zephyr_smp_certified':False,'zephyr_vme_context_certified':False,'full_knownness_certified':False,
            'positive_zephyr_compiler_tests':True,'deployed_image_association_verified':False}
    except (OSError,ValueError,KeyError,TypeError,AttributeError,EOFError)as error:
        return {'available':False,'reason':'Invalid SDK4 package: '+str(error),'timing_available':False,'rtl_certified':False}

if __name__=='__main__':print(json.dumps(device_simulator(),indent=2))

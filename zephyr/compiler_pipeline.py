#!/usr/bin/env python3
"""Emit real Merlin OOT kernels and verify shipped/twin three-hart Zephyr pipelines."""
import argparse,hashlib,json,os,struct,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OOT=ROOT/'integration/iris-mlir'
sys.path.insert(0,str(ROOT))
from spike.run_functional import command,symbols
from uart_profiles import profile as uart_profile,inputs as uart_inputs,check_report
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def s8(x):return (x&255)-256 if x&128 else x&255
def golden(op,job,m,n,k):
    def a(i,q):
        if op=='gemm':return s8(i*17+q*11+3+job*5)
        oy,ox=divmod(i,8);fy,q=divmod(q,24);fx,c=divmod(q,8)
        return s8((((oy+fy)*10+ox+fx)*8+c)*17+3+job*5)
    b=[[s8(q*13+j*7+5+job*9) for j in range(n)] for q in range(k)]
    acc=[sum(a(i,q)*b[q][j] for q in range(k)) for i in range(m) for j in range(n)]
    quant=[max(-128,min(127,(x+512)//1024)) for x in acc]
    return {'job':job,'accumulator_u32':[x&0xffffffff for x in acc],'w8a8_f32_words':[struct.unpack('<I',struct.pack('<f',x))[0] for x in quant]}
def producer_golden(trials=1):
    h=14695981039346656037
    for job in range(3*trials):
        for byte in struct.pack('<8I',*[(job%3)*8+n+7 for n in range(8)]):h=((h^byte)*1099511628211)&((1<<64)-1)
    return h
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--op',choices=['gemm','conv2d'],required=True);p.add_argument('--harts',type=int,choices=[1,2],required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--binary',type=Path,default=ROOT/'build/zephyr-binary-snapshot/spike');p.add_argument('--uart',type=Path);p.add_argument('--timeout',type=int,default=120)
    p.add_argument('--mlir-receipt',type=Path,help='Exact descriptor model/bridge artifact manifest')
    p.add_argument('--app-source',type=Path,default=ROOT/'zephyr/compiler-pipeline')
    p.add_argument('--trials',type=int,default=1,help='Repeated three-input groups; derived app required for more than one')
    p.add_argument('--require-end-to-end',action='store_true',help='Require the derived pinned-hart pipeline region')
    p.add_argument('--build-only',action='store_true',help='Build both ELF variants without executing or observing timing')
    p.add_argument('--uart-profile',choices=['physical','ethan-firesim'],default='ethan-firesim');a=p.parse_args()
    app=a.app_source.resolve()
    if a.trials<1 or a.trials>32 or (a.trials!=1 and app==(ROOT/'zephyr/compiler-pipeline').resolve()):p.error('Trials1..32; repeated trials require a derived app')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);(out/'results.json').unlink(missing_ok=True)
    os.environ['MERLIN_TARGET_PATH']=str(OOT);os.environ.setdefault('MERLIN_CHIPYARD_IRIS','/scratch/eygao/iris-cy');os.environ.setdefault('MERLIN_PROVIDER_BASE_PATH',str(ROOT/'third_party/rvv-mlir'))
    from merlin.runtime.backends.zephyr_model import MatrixRouting
    from merlin.runtime.boards import load_boards
    import merlin.runtime.backends.zephyr_model as routing_module
    import merlin.runtime.boards as boards_module
    from merlin.kernels import matrix_shim
    route=MatrixRouting(support_target='iris',unit='saturn_vme',config='IrisConfig');board=load_boards(OOT/'boards.yaml')['iris_rtl'];board.check_matrix_image(a.harts)
    shim=route.provider().vme_shim;contract=shim.load_contract(route.unit);edge,alignment=contract.geometry(route.config)
    if (edge,alignment)!=(32,16) or board.harts!=3:raise RuntimeError('Iris geometry changed; review the actual board/harness')
    m,n,k=64,64,64 if a.op=='gemm' else 72
    mlir=json.loads(a.mlir_receipt.read_text()) if a.mlir_receipt else None
    if mlir:
        if mlir.get('schema')!='iris.mlir.zephyr_artifacts.v1' or mlir.get('op')!=a.op or mlir.get('local_shape_mnk')!=[32,64,k] or mlir.get('pointer_symbol')!='merlin_vme_gemm_i8_0_pointers' or mlir.get('ciface_symbol')!='_mlir_ciface_forward':raise RuntimeError('Unsupported MLIR artifact schema/shape/symbol contract')
        for item in mlir['artifacts'].values():
            if sha(item['path'])!=item['sha256']:raise RuntimeError('MLIR object differs from manifest')
        if any(sha(path)!=digest for path,digest in mlir['source_sha256'].items()):raise RuntimeError('MLIR source differs from manifest')
    signatures=[(m*h//a.harts,m*(h+1)//a.harts-m*h//a.harts,'pipeline_h'+str(h)) for h in range(a.harts)]
    kernel_signatures={'merlin_vme_gemm_i8_0':(32,n,k)} if mlir else {symbol:(rows,n,k) for _,rows,symbol in signatures}
    unit,enc=shim.emit_translation_unit(kernel_signatures,contract,alignment_bytes=alignment)
    generated=out/'generated';generated.mkdir(exist_ok=True);(generated/'kernel.c').write_text(str(unit));(generated/'encodings.json').write_text(json.dumps(enc.to_dict(),indent=2)+'\n')
    workspace=(unit.scratch_bytes+alignment-1)//alignment*alignment
    config='#include "kernel.c"\n'+f'#define PIPE_M {m}\n#define PIPE_N {n}\n#define PIPE_K {k}\n#define PIPE_WORKERS {a.harts}\n#define PIPE_MAX_ROWS {max(r for _,r,_ in signatures)}\n#define PIPE_WORKSPACE {workspace}\n#define PIPE_CONV {int(a.op=="conv2d")}\n#define PIPE_OP "{a.op}"\n#define PIPE_TRIALS {a.trials}\n'
    if mlir:
        config+='struct pipeline_memref2 {void *allocated,*aligned;int64_t offset,sizes[2],strides[2];};\nextern void _mlir_ciface_forward(void*,void*,void*);\n'
        config+='static inline int pipeline_compute(unsigned h,int32_t*c,const int8_t*a,const int8_t*b,void*w,size_t bytes){(void)w;(void)bytes;unsigned rows=PIPE_M*(h+1)/PIPE_WORKERS-PIPE_M*h/PIPE_WORKERS;for(unsigned r=0;r<rows;r+=32){'
        config+='struct pipeline_memref2 ad={(void*)(a+r*PIPE_K),(void*)(a+r*PIPE_K),0,{32,PIPE_K},{PIPE_K,1}},bd={(void*)b,(void*)b,0,{PIPE_K,PIPE_N},{PIPE_N,1}},cd={c+r*PIPE_N,c+r*PIPE_N,0,{32,PIPE_N},{PIPE_N,1}};_mlir_ciface_forward(&ad,&bd,&cd);}return 0;}\n'
    else:
        config+='static inline int pipeline_compute(unsigned h,int32_t*c,const int8_t*a,const int8_t*b,void*w,size_t bytes){switch(h){'
        for h,(_,_,symbol) in enumerate(signatures):config+=f'case {h}:return {symbol}_pointers(c,a,b,{k},1,{n},1,{n},1,0,0,0,w,bytes);'
        config+='default:return -1;}}\n'
    (generated/'pipeline_config.h').write_text(config)
    expected=[]
    for job in range(3*a.trials):
        item=golden(a.op,job%3,m,n,k);item['job']=job;expected.append(item)
    (generated/'golden.json').write_text(json.dumps(expected)+'\n')
    sources=[Path(__file__),OOT/'zephyr/task_setup.h',OOT/'boards.yaml',OOT/'source_facts.py',OOT/'vme_kernel.py',OOT/'vme_shim.py',OOT/'contracts/matrix_units.yaml',*generated.iterdir()]
    sources+=list(app.rglob('*'));sources=[x for x in sources if x.is_file()]
    sources += [Path(module.__file__) for module in (routing_module,boards_module,matrix_shim)]
    sources += uart_inputs(a.uart_profile)
    sources += [OOT/'zephyr/iris_uart_profile.h',OOT/'zephyr/uart-profiles.json']
    if mlir:sources += [a.mlir_receipt.resolve()]+[Path(item['path']) for item in mlir['artifacts'].values()]
    source_hashes={str(x):sha(x) for x in sources};source_hashes.update({str(path):sha(path) for path in enc.sources})
    if mlir:source_hashes.update(mlir['source_sha256'])
    (out/'emission.json').write_text(json.dumps({'schema':'iris.zephyr.compiler_emission.v1','op':a.op,'shape_mnk':[m,n,k],'workers':a.harts,'workspace_bytes_per_worker':workspace,'signatures':signatures,'kernel_signatures':kernel_signatures,'source_sha256':source_hashes,'source_derived_instruction_encodings':enc.to_dict(),'real_merlin_mlir':bool(mlir),'whole_model_mlir_qualified':False},indent=2)+'\n')
    subprocess.run([sys.executable,str(ROOT/'zephyr/prepare_context_tree.py')],check=True,stdout=subprocess.DEVNULL)
    binary=a.binary.resolve();uart=a.uart.resolve() if a.uart else binary.parent/'libsifive_uart.so';identity=[sha(binary),sha(uart)];runs=[]
    for kind,twin in [('shipped',False),('twin',True)]:
        build=out/(kind+'-build');run=out/(kind+'-run');run.mkdir(exist_ok=True);conf=generated/(kind+'.conf');conf.write_text('CONFIG_IRIS_PIPELINE_SCALAR_TWIN='+('y' if twin else 'n')+'\n'+('CONFIG_COMMON_LIBC_MALLOC=y\nCONFIG_COMMON_LIBC_MALLOC_ARENA_SIZE=262144\nCONFIG_HEAP_MEM_POOL_SIZE=131072\n' if mlir else ''))
        argv=[sys.executable,str(ROOT/'zephyr/context_build.py'),'--source',str(ROOT/'third_party/zephyr-iris'),'--patch',str(ROOT/'zephyr/patches/0002-iris-vme-context.patch'),'--uart-profile',a.uart_profile,'--app',str(app),'--output',str(build),'--extra-conf',str(conf),'--cmake=-DIRIS_KERNEL_DIR='+str(generated),'--cmake=-DIRIS_TARGET_DIR='+str(OOT)]
        for path in [*generated.iterdir(),OOT/'zephyr/task_setup.h',OOT/'zephyr/iris_uart_profile.h',OOT/'zephyr/uart-profiles.json',Path(__file__)]:argv+=['--input',str(path)]
        if mlir:
            for name,cache in [('model_object','IRIS_MLIR_MODEL_OBJECT'),('bridge_object','IRIS_MLIR_BRIDGE_OBJECT')]:argv+=['--cmake=-D'+cache+'='+mlir['artifacts'][name]['path'],'--input',mlir['artifacts'][name]['path']]
            argv+=['--input',str(a.mlir_receipt.resolve())]
        built=subprocess.run(argv,capture_output=True);(run/'build.log').write_bytes(built.stdout+built.stderr)
        if built.returncode:raise RuntimeError('Zephyr compiler pipeline build failed: '+str(run/'build.log'))
        elf=build/'zephyr/zephyr.elf'
        if a.build_only:
            runs.append({'kind':kind,'elf':str(elf),'elf_sha256':sha(elf),'build_receipt_sha256':sha(build/'build.json'),'executed':False})
            continue
        cmd=command(binary,elf);cmd=['--extlib='+str(uart) if x.startswith('--extlib=') else x for x in cmd];cmd[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb')]
        env=dict(os.environ,IRIS_FATAL_PCS=','.join(hex(v) for key,v in symbols(elf).items() if key in ['z_fatal_error','z_riscv_fatal_error']))
        start=time.perf_counter();r=subprocess.run(cmd,env=env,capture_output=True,timeout=a.timeout);elapsed=time.perf_counter()-start;(run/'stdout').write_bytes(r.stdout);(run/'stderr').write_bytes(r.stderr)
        lines=r.stdout.decode(errors='replace').splitlines();values=[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_COMPILER_RESULT ')];regions=[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_REGION ')];producer=[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_COMPILER_PRODUCER ')]
        if r.returncode or values!=expected or 'PASSED compiler Zephyr double-buffer pipeline' not in lines:raise RuntimeError(kind+' numerical/exit failure; see '+str(run))
        uart_readback=check_report(lines,a.uart_profile)
        kernel_regions=[x for x in regions if x['region']!='pipeline_end_to_end'];end_to_end=[x for x in regions if x['region']=='pipeline_end_to_end']
        if len(kernel_regions)!=3*a.trials*a.harts or {(x['region'],x['hart']) for x in kernel_regions}!={(f'job{job}',h) for job in range(3*a.trials) for h in range(a.harts)}:raise RuntimeError('Missing/duplicate compute regions')
        if any(x['role']!=('scalar.compute' if twin else 'vme.compute') or x['end_cycle']<=x['start_cycle'] or x['instret_delta']<=0 for x in kernel_regions):raise RuntimeError('Invalid compute attribution/counters')
        if len(end_to_end)!=int(a.require_end_to_end) or any(x['hart']!=2 or x['role']!='pipeline.end_to_end' or x['end_cycle']<=x['start_cycle'] or x['instret_delta']<=0 for x in end_to_end):raise RuntimeError('Missing/invalid end-to-end pipeline region')
        if len(producer)!=1 or producer[0]['hart']!=2 or producer[0]['jobs']!=3*a.trials or not producer[0]['vme_refused'] or producer[0]['vector_checksum']!=producer_golden(a.trials) or not any(producer[0]['overlap_masks'][:2]):raise RuntimeError('CPU producer did not overlap or match golden')
        objdump=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-objdump');listing=subprocess.check_output([str(objdump),'-d',str(elf)],text=True);(run/'disassembly').write_text(listing)
        hits={role:0 for role in contract.kernel_roles};function=''
        for line in listing.splitlines():
            if line.endswith('>:') and '<' in line:function=line.rsplit('<',1)[1][:-2]
            if not function.startswith(('merlin_vme_','pipeline_h')):continue
            fields=line.split()
            if len(fields)<2 or len(fields[1])!=8:continue
            try:instruction=int(fields[1],16)
            except ValueError:continue
            for role,key in contract.kernel_roles.items():
                e=enc.encodings[key]
                if instruction&e.mask==e.match:hits[role]+=1
        if (not twin and any(v==0 for v in hits.values())) or (twin and any(hits.values())):raise RuntimeError('Compiled kernel instruction audit failed: '+str(hits))
        result={'kind':kind,'pass':True,'argv':cmd,'exit_status':r.returncode,'host_seconds':elapsed,'elf_sha256':sha(elf),'build_receipt_sha256':sha(build/'build.json'),'stdout_sha256':sha(run/'stdout'),'stderr_sha256':sha(run/'stderr'),'regions':regions,'producer':producer[0],'all_int32_and_w8a8_values_match':True,'full_output_elements':3*a.trials*m*n,'kernel_instruction_audit':hits,'disassembly_sha256':sha(run/'disassembly'),'objdump_sha256':sha(objdump),'real_merlin_mlir':bool(mlir),'rtl_certified':False,'timing_certified':False}
        result.update(uart_profile=uart_profile(a.uart_profile),uart_readback=uart_readback)
        (run/'results.json').write_text(json.dumps(result,indent=2)+'\n');runs.append(result)
    if identity!=[sha(binary),sha(uart)] or any(sha(path)!=digest for path,digest in source_hashes.items()):raise RuntimeError('Compiler gate inputs changed during execution')
    if a.build_only:
        result={'schema':'iris.zephyr.compiler_pipeline_build_only.v1','status':'built_not_executed','op':a.op,'shape_mnk':[m,n,k],'workers':a.harts,'physical_harts':3,'jobs':3*a.trials,'trials':a.trials,'app_source':str(app),'require_end_to_end':a.require_end_to_end,'source_sha256':source_hashes,'emission_sha256':sha(out/'emission.json'),'artifacts':runs,'executed':False,'timing_observed':False,'hardware_contacted':False,'rtl_certified':False,'timing_certified':False}
        (out/'build-only.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'built_not_executed','receipt':str(out/'build-only.json')}));return
    result={'schema':'iris.zephyr.compiler_pipeline_gate.v1','pass':True,'op':a.op,'shape_mnk':[m,n,k],'workers':a.harts,'physical_harts':3,'cpu_producer_hart':2,'jobs':3*a.trials,'trials':a.trials,'source_sha256':source_hashes,'emission_sha256':sha(out/'emission.json'),'binary_sha256':identity[0],'uart_sha256':identity[1],'ownership_api':'merlin_target_compute_task_setup -> iris_vme_enable','runs':runs,'kernel_pointer_workspace_abi_qualified':True,'real_merlin_mlir_executed':bool(mlir),'mlir_artifact_receipt_sha256':sha(a.mlir_receipt) if mlir else None,'whole_model_mlir_qualified':False,'rtl_certified':False,'timing_certified':False}
    result['uart_profile']=uart_profile(a.uart_profile)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pass':True,'op':a.op,'workers':a.harts,'full_output_elements_per_kind':3*m*n,'receipt':str(out/'results.json')}))
if __name__=='__main__':main()

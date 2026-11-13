#!/usr/bin/env python3
"""Bundle exact qualified MLIR objects with unique exports, not rebuilt kernels."""
import argparse, hashlib, json, shlex, shutil, struct, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CC=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
OBJCOPY=CC.with_name('riscv64-unknown-elf-objcopy')
NM=CC.with_name('riscv64-unknown-elf-nm')
sys.path.insert(0,str(ROOT/'workloads'))
from check_operator_execution import numerical_oracle,executable_instructions
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def fnv(data):
 h=14695981039346656037
 for b in data:h=((h^b)*1099511628211)&((1<<64)-1)
 return h
def oracle(k,trial):
 a=[(17*i+11*q+3+19*trial)&255 for i in range(2)for q in range(k)];b=[(13*q+7*j+5+23*trial)&255 for q in range(k)for j in range(32)];words=[]
 for i in range(2):
  for j in range(32):
   total=0
   for q in range(k):
    x=a[i*k+q];y=b[q*32+j];total+=(x-256 if x>=128 else x)*(y-256 if y>=128 else y)
   words.append(total&0xffffffff)
 quant=[]
 for x in words:
  x=x if x<1<<31 else x-(1<<32);quant.append(struct.unpack('<I',struct.pack('<f',max(-128,min(127,(x+512)//1024))))[0])
 poison=b''.join(struct.pack('<I',x^0xffffffff)for x in words)
 return dict(accumulator_u32=words,W8A8_f32_words=quant,producer_hash=fnv(bytes(a+b)+poison))
def text_sections(p):
 b=Path(p).read_bytes();off=struct.unpack_from('<Q',b,40)[0];size,count=struct.unpack_from('<HH',b,58);out=[]
 for i in range(count):
  f=struct.unpack_from('<IIQQQQIIQQ',b,off+i*size)
  if f[2]&4:out.append(b[f[4]:f[4]+f[5]])
 return out
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--skip-kernel-negative',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 qualified=ROOT/'build/workload-operator-qualification-v2/report.json';q=json.loads(qualified.read_text())
 if not q['pass']:raise ValueError('Qualified actual MLIR inputs required')
 inputs={str(qualified):sha(qualified)};commands=[];guards=[];objects=[];exports=[];metadata=[]
 flags=['-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-fno-common','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-I'+str(ROOT/'benchmarks'),'-I'+str(out)]
 def run(argv,name):
  r=subprocess.run(argv,capture_output=True);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);commands.append(dict(argv=argv,returncode=r.returncode))
  if r.returncode:raise RuntimeError('Failed command '+name)
 for case_index,entry in enumerate(q['cases']):
  base=Path(entry['receipt']).parent;r=json.loads(Path(entry['receipt']).read_text());c=r['case'];artifact=json.loads((base/'compiled/artifacts.json').read_text());metadata.append(c)
  for name,expected in r['input_sha256'].items():
   if sha(name)!=expected:raise ValueError('Changed qualified source '+name)
   if name in inputs and inputs[name]!=expected:raise ValueError('Conflicting input')
   inputs[name]=expected
  inputs[str(base/'results.json')]=sha(base/'results.json');inputs[str(base/'compiled/matrix/encodings.json')]=sha(base/'compiled/matrix/encodings.json')
  for kind in ('shipped','twin'):
   prefix=f'op{case_index}_{kind}';names=['_mlir_ciface_forward','forward','dealloc_helper','merlin_vme_gemm_i8_0','merlin_vme_gemm_i8_0_pointers','merlin_vme_gemm_i8'];mapping=out/(prefix+'.renames');mapping.write_text(''.join(name+' '+prefix+'_'+name+'\n'for name in names));entry_symbol=prefix+'__mlir_ciface_forward';exports.append(entry_symbol)
   for part,key in [('model','model_object'),('bridge','bridge_object')]:
    source=Path(artifact['artifacts'][key]['path']);dest=out/(prefix+'_'+part+'.o');run([str(OBJCOPY),'--redefine-syms='+str(mapping),str(source),str(dest)],prefix+'_'+part);unchanged=text_sections(source)==text_sections(dest)
    if not unchanged:raise ValueError('Object rename changed compiled instruction bytes')
    guards.append(dict(kind=part,source=str(source),source_sha256=sha(source),renamed=str(dest),renamed_sha256=sha(dest),all_executable_sections_byte_identical=True));objects.append(dest)
   extra=['-DMERLIN_MATRIX_SCALAR_TILE','-DMERLIN_MATRIX_TILE_EDGE=32']if kind=='twin'else[]
   remaps=['-D'+name+'='+prefix+'_'+name for name in ['merlin_vme_gemm_i8_0_pointers','merlin_vme_gemm_i8']]
   obj=out/(prefix+'_kernel.o');deps=out/(prefix+'_kernel.d');argv=[str(CC),*flags,*extra,*remaps,'-MD','-MF',str(deps),'-c',str(base/'kernel.c'),'-o',str(obj)];run(argv,prefix+'_kernel');objects.append(obj)
   for dep in shlex.split(deps.read_text().replace('\\\n',' ').split(':',1)[1]):inputs[str(Path(dep).resolve())]=sha(dep)
   enc=json.loads((base/'compiled/matrix/encodings.json').read_text())['encodings']['SF_MM_INT'];hits=[pc for pc,raw in executable_instructions(obj)if raw&enc['mask']==enc['match']]
   if bool(hits)!=(kind=='shipped'):raise ValueError('Kernel static VME/twin body distinction')
   guards.append(dict(kind=kind,source_kernel_sha256=sha(base/'kernel.c'),object_sha256=sha(obj),static_INT8_VME_instructions=len(hits),compiler_pointer_symbol=prefix+'_merlin_vme_gemm_i8_0_pointers',entry=entry_symbol))
 cases=[];header=['#define MAX_K 4096','#define MAX_ARENA 196608',f'#define MODEL_BATCH_CASES 48','#define MODEL_BATCH_REGIONS 120']
 for symbol in exports:header.append('extern void '+symbol+'(void*,void*,void*);')
 for trial in range(3):
  for i,c in enumerate(metadata):
   k=c['shape_mnk'][2];gold=oracle(k,trial)
   for kind_index,kind in enumerate(('shipped','twin')):
    idx=len(cases);name=f'model.operator.batch.v1.{c["case_id"]}.workers{c["workers"]}.{kind}.trial{trial}';workers=c['workers'];checks={str(h):fnv(b''.join(struct.pack('<I',x)for x in gold['accumulator_u32'][h*(64//workers):(h+1)*(64//workers)]))for h in range(workers)};checks['2']=gold['producer_hash'];symbol=f'op{i}_{kind}__mlir_ciface_forward'
    item=dict(case_id=name,semantic_parent_case_id=c['case_id']+'.workers'+str(workers)+'.'+kind,source_case=c,trial_id=trial,variant=kind,workers=workers,active_harts=list(range(workers))+[2],expected_checksums=checks,expected_words=gold,entry_symbol=symbol,calibration_usable=False,validation_only=True);cases.append(item)
    header.append('static const uint32_t golden_'+str(idx)+'[]={'+','.join(str(x)+'u'for x in gold['accumulator_u32'])+'};')
 header.append('static const case_t cases[]={')
 for idx,c in enumerate(cases):header.append('{'+json.dumps(c['case_id'])+','+','.join(str(v)for v in [c['source_case']['shape_mnk'][2],c['workers'],c['variant']=='twin',c['trial_id']])+','+c['entry_symbol']+',golden_'+str(idx)+',{'+','.join(str(c['expected_checksums'].get(str(h),0))+'ULL'for h in range(3))+'}},')
 # bools must be C integers, not Python spellings.
 header=[line.replace(',False,',',0,').replace(',True,',',1,')for line in header];header.append('};');(out/'model_operator_batch_cases.h').write_text('\n'.join(header)+'\n')
 corpus=dict(schema='iris.model_operator_validation_batch.v1',split_id='iris-model-operator-protected-validation-v1',cases=cases,trials=3,required_regions=120,full_int32_words=3072,full_W8A8_words=3072,all_cases_validation_only=True,TinyLlama_protected_validation_only=True,calibration_usable=False,full_model_qualified=False,exact_Llama2_checkpoint_admitted=False,source_qualification_sha256=sha(qualified));save(out/'corpus.json',corpus)
 for name,source in [('start',ROOT/'benchmarks/start.S'),('runtime',ROOT/'benchmarks/runtime.c'),('guest',ROOT/'workloads/model_operator_batch_guest.c')]:
  obj=out/(name+'.o');dep=out/(name+'.d');control=['-DIRIS_MODEL_BATCH_SKIP_KERNEL']if a.skip_kernel_negative and name=='guest'else[];run([str(CC),*flags,*control,'-MD','-MF',str(dep),'-DIRIS_HARTS=3','-c',str(source),'-o',str(obj)],name);objects.insert(0,obj)
  for word in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):inputs[str(Path(word).resolve())]=sha(word)
 elf=out/'batch.elf';run([str(CC),*flags,'-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-Wl,-Map,'+str(out/'batch.map'),'-T',str(ROOT/'benchmarks/link.ld'),*[str(obj)for obj in objects],'-lgcc','-o',str(elf)],'link')
 globals=subprocess.check_output([str(NM),'-g',str(elf)],text=True);(out/'symbols').write_text(globals)
 if any(globals.count(' T '+name+'\n')!=1 for name in exports):raise ValueError('Unique actual compiled export binding')
 inputs.update({str(p.resolve()):sha(p)for p in [Path(__file__),ROOT/'workloads/check_operator_execution.py',ROOT/'benchmarks/link.ld',CC,OBJCOPY,NM]})
 for tool in ('cc1','as','collect2','ld'):
  name=subprocess.check_output([str(CC),'-print-prog-name='+tool],text=True).strip();p=Path(name if '/'in name else shutil.which(name)).resolve();inputs[str(p)]=sha(p)
 lib=Path(subprocess.check_output([str(CC),'-print-libgcc-file-name'],text=True).strip());inputs[str(lib)]=sha(lib)
 save(out/'binary-proof.json',dict(schema='iris.model_operator_batch_binary_proof.v1',**{'pass':True},actual_MLIR_object_export_renames=guards,source_instruction_bytes_unchanged=True,unique_compiled_exports=exports,elf_sha256=sha(elf),no_guessed_merged_kernel=True,hardware_contacted=False))
 save(out/'build.json',dict(schema='iris.model_operator_batch_build.v1',status='built',elf=str(elf),elf_sha256=sha(elf),corpus_sha256=sha(out/'corpus.json'),binary_proof_sha256=sha(out/'binary-proof.json'),deliberate_noop_negative=a.skip_kernel_negative,commands=commands,input_sha256=inputs,calibration_usable=False,hardware_contacted=False))
 print(json.dumps(dict(status='built',elf_sha256=sha(elf),cases=len(cases),regions=120)))
if __name__=='__main__':main()

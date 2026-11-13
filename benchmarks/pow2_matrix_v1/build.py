#!/usr/bin/env python3
"""Build an exact, bounded TK1 tiled signed-INT8/FP8 power-of-two matrix packet."""
import argparse,hashlib,json,struct,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SHAPES=[(n,n,n)for n in (8,16,32,64,128,256)]+[(32,32,n)for n in (8,16,64,128,256)]
RESERVED=[(16,16,16),(128,128,128),(32,32,64)]
SPLIT=ROOT/'calibration/pow2-matrix-v1/split.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fnv(raw):
 h=14695981039346656037
 for b in raw:h=((h^b)*1099511628211)&((1<<64)-1)
 return h
def goldens(m,n,k,h):
 # Independently execute every mathematical MAC; no model/kernel import.
 a=[(-1 if i&1 else 1)*(1+(i+h)%3)for i in range(m)]
 b=[(-1 if j&1 else 1)*(1+(j+2*h)%4)for j in range(n)]
 return [sum(a[i]*b[j]for _ in range(k))for i in range(m)for j in range(n)]
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--negative-skip-kernel',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 cached={(s,h):goldens(*s,h)for s in SHAPES for h in(0,1)};cases=[];rawgold=bytearray()
 for trial in range(3):
  for m,n,k in SHAPES:
   for fp8 in(0,1):
    for h in(0,1):
     values=cached[((m,n,k),h)];raw=b''.join(struct.pack('<f',v)if fp8 else struct.pack('<I',v&0xffffffff)for v in values);parent='matrix.pow2.%dx%dx%d.%s.hart%d'%(m,n,k,'fp8-e4m3'if fp8 else'int8-signed',h)
     cases.append(dict(id=parent+'.trial%d'%trial,parent_case_id=parent,m=m,n=n,k=k,fp8=fp8,hart=h,trial=trial,words=m*n,macs=m*n*k,checksum=fnv(raw),golden_offset=len(rawgold),golden_bytes=len(raw),internal_split='reserved_holdout'if(m,n,k)in RESERVED else'train',split_group_id='shape:%dx%dx%d'%(m,n,k)));rawgold+=raw
 (out/'golden-words.bin').write_bytes(rawgold)
 c=dict(schema='iris.pow2_single_matrix_corpus.v1',split_id='iris-pow2-single-matrix-v1',frozen_split_sha256=sha(SPLIT),cases=cases,required_regions=132,physical_harts_booted=[0,1,2],active_compute_harts=[0,1],hart2_VME_illegal_refusal_required=True,trials=3,source_tile_edge=32,reduction_rows_per_MM=1,source_kmax=4,strategy='32x32 single accumulator tile; exact TM/TN edges8/16/32; TK1; operand rows loaded once per output tile and reused across every real K MAC instruction; no scalar replacement.',dtypes=['signed-int8-to-int32','E4M3-E4M3-to-FP32'],full_golden_words=len(rawgold)//4,per_word_independent_MAC_oracle=True,poison_all_destination_words_before_ROI=True,negative_skip_kernel=a.negative_skip_kernel,output='All words checked on target, host independent FNV of every little-endian output word; full expected words archived separately.',reserved_timing_labels_root_only=True,train_regions=96,reserved_regions=36,global_heldout=False,new_exact_reference_required=True,source_image_association_verified=False,physical_MAC_count_measured=False,scope='Baremetal single-active-hart matrix kernel scaling; not Merlin compiler or full model; rowreadout only. Source exact integer-valued finite FP8 operands/results, no special-value/rounding coverage claim.',history='No warmup/flush. Each compute hart initializes all four32x32 tiles once at boot; each output block zeros tile0 inside ROI; poison outside ROI; kernel includes config/loads/realMM/rowmoves/vectorstores/scatter/fences. Inactiveharts WFI; console after each case perturbs nextcase cache history.',mtime_hz=500000,mtime_scope='encloses_CSR_ROI_with_sampling_overhead',mtime_quantization_error_bound_core_cycles=1000)
 (out/'corpus.json').write_text(json.dumps(c,indent=2)+'\n');inc=['enum{CASE_COUNT=132};','static const case_t cases[CASE_COUNT]={']+['{'+json.dumps(t['id'])+','+','.join(str(t[k])for k in('m','n','k','fp8','hart','trial'))+','+str(t['checksum'])+'ULL},'for t in cases]+['};'];(out/'cases.inc').write_text('\n'.join(inc)+'\n')
 cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');rt=HERE/'runtime';header=ROOT/'third_party/saturn/benchmarks/common/vme.h';argv=[str(cc),'-O2','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-Wno-unused-function','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none','-DIRIS_HARTS=3','-I'+str(out),'-I'+str(rt),'-I'+str(header.parent),'-T',str(rt/'link.ld'),str(rt/'start.S'),str(rt/'runtime.c'),str(HERE/'guest.c'),'-lgcc','-o',str(out/'matrix.elf')]
 if a.negative_skip_kernel:argv.insert(1,'-DIRIS_MATRIX_SKIP_KERNEL')
 r=subprocess.run(argv,capture_output=True);(out/'build.stdout').write_bytes(r.stdout);(out/'build.stderr').write_bytes(r.stderr)
 if r.returncode:raise ValueError(r.stderr.decode())
 nm=cc.with_name('riscv64-unknown-elf-nm');(out/'symbols.txt').write_bytes(subprocess.check_output([str(nm),'-S','--defined-only',str(out/'matrix.elf')]))
 lib=Path(subprocess.check_output([str(cc),'-mabi=lp64d','-march=rv64gcv_zfh_zvfh','-print-libgcc-file-name'],text=True).strip()).resolve();inputs=[Path(__file__).resolve(),HERE/'guest.c',HERE/'validate.py',SPLIT,cc,nm,lib,header,*[rt/n for n in('runtime.c','runtime.h','start.S','uart_drain.h','link.ld')],out/'corpus.json',out/'cases.inc',out/'golden-words.bin'];report=dict(schema='iris.pow2_single_matrix_build.v1',status='passed',argv=argv,elf_sha256=sha(out/'matrix.elf'),cases=132,full_golden_words=len(rawgold)//4,negative_skip_kernel=a.negative_skip_kernel,input_sha256={str(p):sha(p)for p in inputs},hardware_contacted=False)
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(elf_sha256=report['elf_sha256'],cases=132,full_golden_words=report['full_golden_words'])))
if __name__=='__main__':main()

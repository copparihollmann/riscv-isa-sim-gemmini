#!/usr/bin/env python3
import argparse,hashlib,json,subprocess
from pathlib import Path
from cases import generate,golden
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--skip-kernel',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);cases=generate();split=ROOT/'calibration/rvv-identify-tk-v2/split.json'
 for c in cases:c['expected_checksum']=golden(c)
 corpus=dict(schema='iris.rvv_identify_corpus.v1',cases=cases,regions=1,trials=1,physical_harts=3,single_active_hart=True,all_output_after_measurements=False,diagnostic_only=True,calibration_usable=False,ROI_contains_progress_and_is_not_calibration=True,source_image_association_verified=False,new_exact_reference_required=True,global_heldout=False,fitting_only=False,skip_kernel=a.skip_kernel,frozen_split_sha256=sha(split),reserved_timing_labels_root_only=True,arithmetic='VADD/VFADD IEEEHSD only; unmasked; VLmax; SEW8/16/32/64 andLMUL1/2/4/8 wherelegal; dependent/twoindependent/producerconsumer',memory='VLE32/VSE32 andload-use/load-independent/store-compute; bufferswarm initializedbyactivehart only; wholeinstruction issueretirement andFENCEdrain observedseparately',rowmove='TM=TN32 TK1 INT8tileinitializedzero+one2x3MMoutsideROI; rowmovesonlyinside; outputVSE32afterbothcounters',clock_scope='mcycle/minstret actualCSRreads; sourceCLINToutside; nooverheadsubtraction',requested_work_not_physical_traffic=True,LSU_requests_measured=False,TL_transactions_measured=False,DLEN_bits_by_hart=[128,128,256],external_ATL_bits_by_hart=[256,256,64])
 (out/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n');fields=('kind_id','sew','lmul','mode','n','bytes','hart','trial_id','vl','streams');(out/'cases.inc').write_text('static const case_t experiments[]={\n'+',\n'.join('{'+json.dumps(c['case_id'])+','+','.join(str(c[k])for k in fields)+'}'for c in cases)+'\n};\nstatic const char*const parent_ids[]={'+','.join(json.dumps(c['parent_case_id'])for c in cases)+'};\n')
 cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');rt=HERE/'runtime';elf=out/'guest.elf';argv=[str(cc),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-I'+str(rt),'-I'+str(out),'-I'+str(ROOT/'third_party/saturn/benchmarks/common'),'-T',str(rt/'link.ld'),str(rt/'start.S'),str(rt/'runtime.c'),str(HERE/'guest.c'),'-lgcc','-o',str(elf)]
 if a.skip_kernel:argv.insert(1,'-DIRIS_SKIP_RVV_KERNEL')
 r=subprocess.run(argv,capture_output=True);(out/'build.stdout').write_bytes(r.stdout);(out/'build.stderr').write_bytes(r.stderr)
 if r.returncode:raise ValueError(r.stderr.decode())
 nm=cc.with_name('riscv64-unknown-elf-nm');objdump=cc.with_name('riscv64-unknown-elf-objdump');syms=subprocess.check_output([str(nm),'-S','--defined-only',str(elf)],text=True);(out/'symbols.txt').write_text(syms);(out/'disassembly.txt').write_bytes(subprocess.check_output([str(objdump),'-d',str(elf)]))
 def sym(name):
  rows=[x.split()for x in syms.splitlines()if x.split()[-1]==name]
  if len(rows)!=1:raise ValueError('Unique symbol '+name)
  return dict(address=int(rows[0][0],16),size=int(rows[0][1],16))
 objects={n:sym(n)for n in('rvv_records','rvv_record_count','rvv_measurements_done','parked','completion')};stride=objects['rvv_records']['size']//1
 if stride!=192 or objects['rvv_records']['address']%64:raise ValueError('Actualpadded192B recordABI')
 layout=dict(schema='iris.rvv_identify_readback_layout.v1',record_bytes=stride,records=1,fields=['case_index','hart','start','issued','end','ir0','ir1','ir2','checksum','expected','mismatch','checked','vl','mtime_before','mtime_after','msip_before','msip_after'],objects=objects,sentinel_initial_value=2**64-1,sentinel_complete_value=0,ELF_sha256=sha(elf),debugger_stop_is_normal_guest_exit=False)
 (out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n');lib=Path(subprocess.check_output([str(cc),'-march=rv64gcv_zicsr_zifencei','-mabi=lp64d','-print-libgcc-file-name'],text=True).strip()).resolve();paths=[Path(__file__).resolve(),HERE/'cases.py',HERE/'guest.c',HERE/'validate.py',split,cc,nm,objdump,lib,ROOT/'third_party/saturn/benchmarks/common/vme.h',*[rt/n for n in('runtime.c','runtime.h','start.S','link.ld','uart_drain.h')],out/'corpus.json',out/'cases.inc',out/'layout.json'];ids={str(p):sha(p)for p in paths};(out/'inputs').mkdir()
 for name,h in ids.items():(out/'inputs'/h).write_bytes(Path(name).read_bytes())
 (out/'build.json').write_text(json.dumps(dict(schema='iris.rvv_identify_build.v1',**{'pass':True},ELF_sha256=sha(elf),argv=argv,input_sha256=ids,skip_kernel=a.skip_kernel,hardware_contacted=False),indent=2)+'\n');print(json.dumps(dict(ELF_sha256=sha(elf),cases=1,record_bytes=stride)))
if __name__=='__main__':main()

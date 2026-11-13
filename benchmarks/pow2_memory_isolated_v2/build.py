#!/usr/bin/env python3
import argparse,hashlib,json,struct,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SIZES=tuple(1<<k for k in range(10,23));RESERVED=(4096,65536,524288)
SPLIT=ROOT/'calibration/pow2-memory-isolated-v2/split.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--negative-skip-kernel',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 cases=[]
 for trial in range(3):
  for size in SIZES:
   for h in range(3):
    n=size//64;loads=max(1024,n);stem='memory.pow2.isolated.%d.hart%d'%(size,h)
    cases.append(dict(id=stem+'.trial%d'%trial,case_id=stem+'.trial%d'%trial,semantic_parent_case_id=stem,footprint_bytes=size,nodes=n,loads=loads,whole_laps=loads//n,hart=h,active_harts=[h],mask=1<<h,trial_id=trial,base=0x90000000+h*0x02000000,expected_checksum=0x90000000+h*0x02000000+64*((17*trial+7*h)%n),internal_split='reserved_holdout'if size in RESERVED else'train',split_group_id='footprint-bytes:'+str(size)))
 corpus=dict(schema='iris.pow2_isolated_memory_corpus.v2',split_id='iris-pow2-isolated-memory-v2',frozen_split_sha256=sha(SPLIT),cases=cases,trials=3,passes=2,physical_harts=3,required_regions=234,reserved_sizes=list(RESERVED),reserved_timing_labels_root_only=True,fitting_only=True,global_heldout=False,negative_skip_kernel=a.negative_skip_kernel,source_image_association_verified=False,physical_DRAM_miss_or_traffic_measured=False,buffered_all_output=True,min_dependent_loads=1024,eviction_bytes=8388608,eviction_loads=131072,record_bytes=128,protocol='Onlyactivehart preparesownpool/warmscode/reads8MiBevictionpool; inactive MIE-maskedWFI afterreleaseparkack. NoIPIsorforeignwrites until bothROIs complete. ConsumeactualMSIPbefore nextack. Alloutputafter234measurements.',cold_definition='Firstwhole-lap measurement afteractive-only8MiBlinewise eviction conditioning; notarchitecturalflush orprovenphysicalcold.',steady_definition='Equal-length secondtraversal immediatelyafterfirstROI/privaterecordstores, withno foreignactivity/preparation/eviction.',requested_byte_scope='8bytes per architecturaldependentLD; addressfootprint andconditioningloads are NOTmeasuredphysicaltraffic.',mtime_hz=500000,source_core_cycles_per_mtime_tick=1000,overhead_subtracted=False,new_exact_reference_required=True)
 (out/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n');(out/'cases.inc').write_text('static const case_t experiments[]={\n'+',\n'.join('{'+json.dumps(c['id'])+','+','.join(str(c[k])for k in('nodes','loads','hart','trial_id'))+'}'for c in cases)+'\n};\n')
 common=HERE/'runtime';cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');elf=out/'footprints.elf';argv=[str(cc),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-fno-common','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-I'+str(common),'-I'+str(out),'-T',str(common/'link.ld'),str(common/'start.S'),str(common/'runtime.c'),str(HERE/'guest.c'),'-lgcc','-o',str(elf)]
 if a.negative_skip_kernel:argv.insert(1,'-DIRIS_FOOTPRINT_SKIP_KERNEL')
 r=subprocess.run(argv,capture_output=True);(out/'build.stdout').write_bytes(r.stdout);(out/'build.stderr').write_bytes(r.stderr)
 if r.returncode:raise ValueError(r.stderr.decode())
 nm=cc.with_name('riscv64-unknown-elf-nm');listing=subprocess.check_output([str(nm),'-S','--defined-only',str(elf)],text=True);(out/'symbols.txt').write_text(listing)
 objdump=cc.with_name('riscv64-unknown-elf-objdump');(out/'disassembly.txt').write_bytes(subprocess.check_output([str(objdump),'-d',str(elf)]))
 def sym(name):
  rows=[x.split()for x in listing.splitlines()if x.split()[-1]==name]
  if len(rows)!=1:raise ValueError('Unique ELFsymbol '+name)
  return dict(address=int(rows[0][0],16),size=int(rows[0][1],16))
 layout=dict(schema='iris.pow2_isolated_memory_layout.v2',record_bytes=128,records=234,fields=['case_index','phase','hart','start','end','instret','checksum','expected','mtime_before','mtime_after','loads','evict_sum','msip_before','msip_after'],objects={n:sym(n)for n in('footprint_records','footprint_record_count','footprint_measurements_done')},control_objects={n:sym(n)for n in('parked','completion')},stop_sentinel_initial_value=2**64-1,stop_sentinel_complete_value=0,elf_sha256=sha(elf),intentional_debugger_stop_is_normal_guest_exit=False)
 (out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
 lib=Path(subprocess.check_output([str(cc),'-march=rv64gcv_zicsr_zifencei','-mabi=lp64d','-print-libgcc-file-name'],text=True).strip()).resolve()
 paths=[Path(__file__).resolve(),HERE/'guest.c',HERE/'validate.py',cc,nm,objdump,lib,SPLIT,*[common/n for n in('runtime.c','runtime.h','start.S','uart_drain.h','link.ld')],out/'corpus.json',out/'cases.inc',out/'layout.json'];ids={str(p):sha(p)for p in paths};(out/'inputs').mkdir()
 for name,h in ids.items():(out/'inputs'/h).write_bytes(Path(name).read_bytes())
 report=dict(schema='iris.pow2_isolated_memory_build.v2',**{'pass':True},argv=argv,elf=str(elf),elf_sha256=sha(elf),input_sha256=ids,negative_skip_kernel=a.negative_skip_kernel,hardware_contacted=False,source_image_association_verified=False)
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(elf=str(elf),elf_sha256=sha(elf),cohorts=117,regions=234)))
if __name__=='__main__':main()

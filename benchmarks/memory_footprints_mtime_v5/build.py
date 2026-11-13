#!/usr/bin/env python3
"""Freeze a larger-than-cache fitting experiment, without asserting cache misses."""
import argparse,hashlib,json,struct,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
FOOTPRINTS=(2048,16384,131072,1048576,4194304)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def generate():
 out=[]
 for trial in range(3):
  for size in FOOTPRINTS:
   for mask in range(1,8):
    parent='memory.footprint.%d.mask%d'%(size,mask)
    out.append(dict(id=parent+'.trial%d'%trial,case_id=parent+'.trial%d'%trial,semantic_parent_case_id=parent,footprint_bytes=size,nodes=size//64,mask=mask,active_harts=[h for h in range(3)if mask>>h&1],trial_id=trial,base_by_hart=[0x90000000+h*0x02000000 for h in range(3)],expected_checksums_by_hart=[0x90000000+h*0x02000000+64*((17*trial+7*h)%(size//64))for h in range(3)],internal_split='internal_validation'if int(hashlib.sha256(parent.encode()).hexdigest()[:8],16)%5==0 else'train'))
 return out
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--negative-skip-kernel',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);cases=generate();assert len(cases)==105 and sum(len(c['active_harts'])*2 for c in cases)==360
 corpus=dict(schema='iris.memory_footprint_mtime_fitting.v1',split_id='iris-memory-footprint-mtime-fit-v1',cases=cases,trials=3,passes=2,physical_harts=3,required_regions=360,fitting_only=True,global_heldout=False,negative_skip_kernel=a.negative_skip_kernel,source_image_association_verified=False,physical_DRAM_miss_or_traffic_measured=False,protocol='All3harts initialize disjoint footprints once per size/trial; fence andbarrier; masks1..7, two back-to-back traversals each. No cacheflush/missassertion. Earlier passes/masks affect cache history.',counter_scope='Raw mcycle/minstret; fullN dependent LD body, call, counter instructions and fence included; no overhead subtraction.',requested_byte_scope='8bytes per architectural LD; 64-byte line footprint is address geometry, not measured physical traffic.',mtime_hz=500000,source_core_cycles_per_mtime_tick=1000,mtime_scope='encloses_CSR_ROI_with_sampling_overhead',mtime_quantization_error_bound_core_cycles=1000,overhead_subtraction=False,parent_semantic_cases_unchanged=True,identifiability='Footprints bracket source8/16KiB L1D and512KiB sharedL2; this does not prove physical hit/miss or independently identify every latency/MLP parameter.')
 (out/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n');(out/'cases.inc').write_text('static const case_t experiments[]={\n'+',\n'.join('{'+json.dumps(c['id'])+','+','.join(str(c[k])for k in('nodes','mask','trial_id'))+'}'for c in cases)+'\n};\n')
 common=HERE.parent;cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');elf=out/'footprints.elf';argv=[str(cc),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-fno-common','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-I'+str(common),'-I'+str(out),'-T',str(common/'link.ld'),str(common/'start.S'),str(common/'runtime.c'),str(HERE/'guest.c'),'-lgcc','-o',str(elf)]
 if a.negative_skip_kernel:argv.insert(1,'-DIRIS_FOOTPRINT_SKIP_KERNEL')
 r=subprocess.run(argv,capture_output=True);(out/'build.stdout').write_bytes(r.stdout);(out/'build.stderr').write_bytes(r.stderr)
 if r.returncode:raise ValueError('Compiler failed: '+r.stderr.decode())
 raw=elf.read_bytes();po=struct.unpack_from('<Q',raw,32)[0];ps,pn=struct.unpack_from('<HH',raw,54)
 for i in range(pn):
  typ,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',raw,po+i*ps)
  if typ==1:
   for base in cases[0]['base_by_hart']:
    if max(base,pa)<min(base+4194304,pa+ms):raise ValueError('ELF overlaps target')
 nm=cc.with_name('riscv64-unknown-elf-nm');listing=subprocess.check_output([str(nm),'-S','--defined-only',str(elf)],text=True);(out/'symbols.txt').write_text(listing)
 def sym(name):
  rows=[x.split()for x in listing.splitlines()if x.split()[-1]==name]
  if len(rows)!=1:raise ValueError('Unique symbol '+name)
  return dict(address=int(rows[0][0],16),size=int(rows[0][1],16))
 def readaddr(addr,n):
  for i in range(pn):
   typ,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',raw,po+i*ps)
   if typ==1 and va<=addr and addr+n<=va+fs:return raw[off+addr-va:off+addr-va+n]
  raise ValueError('Address not filebacked')
 body=sym('footprint_chase')if not a.negative_skip_kernel else None
 if body:
  expected=struct.pack('<4I',0x00053503,0xfff58593,0xfe059ce3,0x00008067)
  if body['size']!=16 or readaddr(body['address'],16)!=expected:raise ValueError('Exact4instruction LD loop body changed')
 layout=dict(schema='iris.memory_footprint_buffer_layout.v2',record_bytes=80,records=360,fields=['case_index','pass','hart','start','end','instret','checksum','expected','mtime_before','mtime_after'],objects={name:sym(name)for name in('footprint_records','footprint_record_count','footprint_measurements_done')},stop_sentinel_initial_value=2**64-1,stop_sentinel_complete_value=0,elf_sha256=sha(elf),intentional_debugger_stop_is_normal_guest_exit=False)
 if readaddr(layout['objects']['footprint_measurements_done']['address'],8)!=b'\xff'*8:raise ValueError('Sentinel not file-backed -1')
 (out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n');lib=Path(subprocess.check_output([str(cc),'-march=rv64gcv_zicsr_zifencei','-mabi=lp64d','-print-libgcc-file-name'],text=True).strip()).resolve();paths=[Path(__file__).resolve(),HERE/'guest.c',HERE/'validate.py',cc,lib,nm,*[common/n for n in('runtime.c','runtime.h','start.S','uart_drain.h','link.ld')],ROOT/'hardware/manifest.json',ROOT/'hardware/memory-paths.json',out/'corpus.json',out/'cases.inc',out/'layout.json'];ids={str(p):sha(p)for p in paths};(out/'inputs').mkdir()
 for name,h in ids.items():(out/'inputs'/h).write_bytes(Path(name).read_bytes())
 report=dict(schema='iris.memory_footprint_mtime_build.v1',**{'pass':True},argv=argv,elf=str(elf),elf_sha256=sha(elf),input_sha256=ids,exact_loop=body,loop_instructions_per_node=3,loop_ret_instructions=1,loop_loads_per_node=1,negative_skip_kernel=a.negative_skip_kernel,hardware_contacted=False,source_image_association_verified=False);(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(elf=str(elf),elf_sha256=sha(elf),cases=105,regions=360)))
if __name__=='__main__':main()

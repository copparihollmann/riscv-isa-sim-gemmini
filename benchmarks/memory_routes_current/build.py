#!/usr/bin/env python3
"""New repeated buffered copy of the unchanged scalar memory-route kernels."""
import argparse,copy,hashlib,importlib.util,json,struct,subprocess
from pathlib import Path
from validate import ELF,check_elf,admitted
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def build(out):
 out.mkdir(parents=True,exist_ok=False);old=ROOT/'benchmarks/memory_routes';spec=importlib.util.spec_from_file_location('original_memory_cases',old/'cases.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);parents=module.cases();assert len(parents)==504
 cases=[];split={}
 for c in parents:
  semantic='.'.join(c['case_id'].split('.')[:4])+'.mask'+str(c['mask'])
  split[semantic]='internal_validation'if int(hashlib.sha256(semantic.encode()).hexdigest()[:8],16)%5==0 else'train'
  for trial in range(3):
   row=copy.deepcopy(c);row.update(case_id='memroute.current.v1.'+c['case_id']+'.r'+str(trial),parent_case_id=c['case_id'],semantic_parent_case_id=semantic,trial_id=trial,suite='memory_routes_current');cases.append(row)
 corpus={'schema':'iris.memory_routes_current_corpus.v1','split_id':'iris-memory-routes-current-v1','physical_harts':3,'trials':3,'cases':cases,'expected_region_count':2592,'fitting_only':True,'global_heldout':False,'source_cases_sha256':sha(old/'cases.py'),'memory_paths_sha256':sha(ROOT/'hardware/memory-paths.json'),'hardware_manifest_sha256':sha(ROOT/'hardware/manifest.json'),'memory_regions':module.REGIONS,'cache_protocol':'prepare64nodes/fence/globalbarrier; no flush or asserted hit/cold state','inactive_policy':'source WFI/MSIP; early finishers spin outside ROI','bank_scope':'TCM/scratch source bit6 geometry only; NOT a DRAM device bank map','old_ELF_or_campaign_timings_applicable':False,'new_exact_ELF_reference_required':True,'source_image_association_verified':False}
 admitted(corpus);(out/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n');(out/'split.json').write_text(json.dumps({'schema':'iris.memory_routes_current_split.v1','frozen_before_hardware':True,'timing_labels_consumed':False,'grouping':'target/pattern/kind/hartmask; bothN andalltrials staytogether','global_heldout':False,'split':split},indent=2)+'\n')
 table='static const case_t experiments[]={\n'+',\n'.join('{'+json.dumps(c['case_id'])+','+str(c['base'])+'ULL,K_'+c['kind']+','+','.join(str(c[k])for k in ('stride','spread','n','mask'))+',{'+','.join(str(v)+'ULL'for v in c['expected_checksums'])+'}}'for c in cases)+'\n};\n'
 table+='static const char *const parent_ids[]={'+','.join(json.dumps(c['parent_case_id'])for c in cases)+'};\n'
 table+='static const unsigned trial_ids[]={'+','.join(str(c['trial_id'])for c in cases)+'};\n';(out/'cases.inc').write_text(table)
 original=(old/'guest.c').read_text();source=original;mark='static unsigned complete, done, failed;';assert source.count(mark)==1
 source=source.replace(mark,mark+'\ntypedef struct {uint64_t case_index,hart,start,end,instret,checksum,expected,pass;}record_t;\nvolatile record_t buffered_records[2592];\nvolatile uint64_t buffered_measurements_done=UINT64_MAX,buffered_record_count,buffered_case_count;\n')
 begin=source.index('  if(h==0) for(unsigned i=0;i<3;++i) if(c->mask&(1U<<i)) {');end=source.index('\n  barrier();\n}\nvoid benchmark_main',begin)
 replacement='''  if(h==0) {
    const uint64_t case_index=c-experiments;
    for(unsigned i=0;i<3;++i)if(c->mask&(1U<<i)){
      result_t r=results[i];unsigned pass=r.checksum==c->expected[i];if(!pass)++failed;
      buffered_records[buffered_record_count++]=(record_t){case_index,i,r.begin,r.end,r.instructions,r.checksum,c->expected[i],pass};
    }
    buffered_case_count=case_index+1;
  }'''
 source=source[:begin]+replacement+source[end:];main=source.index('void benchmark_main(unsigned h) {');source=source[:main]+'''void benchmark_main(unsigned h) {
  for(unsigned i=0;i<sizeof(experiments)/sizeof(experiments[0]);++i)run(&experiments[i],h);
  barrier();
  if(h==0){
    memory_fence();buffered_measurements_done=0;memory_fence();
    for(unsigned i=0;i<buffered_record_count;++i){record_t r=buffered_records[i];const case_t*c=&experiments[r.case_index];
      putstr("IRIS_REGION {\\"case_id\\":\\"");putstr(c->id);putstr("\\",\\"parent_case_id\\":\\"");putstr(parent_ids[r.case_index]);
      putstr("\\",\\"suite\\":\\"memory_routes_current\\",\\"trial_id\\":");putuint(trial_ids[r.case_index]);
      putstr(",\\"region\\":\\"kernel\\",\\"hart\\":");putuint(r.hart);putstr(",\\"start_cycle\\":");putuint(r.start);
      putstr(",\\"end_cycle\\":");putuint(r.end);putstr(",\\"instret_delta\\":");putuint(r.instret);
      putstr(",\\"checksum\\":");putuint(r.checksum);putstr(",\\"expected_checksum\\":");putuint(r.expected);
      putstr(",\\"pass\\":");putstr(r.pass?"true":"false");putstr("}\\n");
    }
    putstr("IRIS_BATCH_DONE {\\"failed\\":");putuint(failed);putstr(",\\"cases\\":1512,\\"regions\\":2592}\\n");finish(failed?1:0);
  }
  for(;;)__asm__ volatile("wfi");
}
'''
 old_window=original[original.index('static uintptr_t address('):original.index('  if(h==0) for(unsigned i=0;i<3;++i) if(c->mask&(1U<<i)) {')];assert old_window==source[source.index('static uintptr_t address('):source.index('  if(h==0) {\n    const uint64_t case_index')];(out/'guest.c').write_text(source)
 prior=ROOT/'build/memory-routes-fit-v1-final';args=json.loads((prior/'build.json').read_text())['argv'];args=['-I'+str(out)if x=='-I'+str(prior)else str(out/'guest.c')if x==str(old/'guest.c')else x for x in args];args[-1]=str(out/'memory-routes.elf');r=subprocess.run(args,capture_output=True);(out/'build.stdout').write_bytes(r.stdout);(out/'build.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr
 e=ELF(out/'memory-routes.elf');objects={k:{a:v for a,v in e.symbols[k].items()if a in('address','size')}for k in ('buffered_records','buffered_measurements_done','buffered_record_count','buffered_case_count')};layout={'schema':'iris.buffered_campaign_readback_layout.v1','elf_sha256':sha(out/'memory-routes.elf'),'objects':objects,'record_bytes':64,'records':2592,'fields':['case_index','hart','start','end','instret','checksum','expected','pass'],'stop_sentinel_initial_value':2**64-1,'stop_sentinel_complete_value':0,'file_backed_initial_sentinel_verified':True,'intentional_debugger_stop_is_normal_guest_exit':False};check_elf(out/'memory-routes.elf',corpus,layout);(out/'readback-layout.json').write_text(json.dumps(layout,indent=2)+'\n')
 previous=ELF(prior/'memory-routes.elf');a,b=e.symbols['kernel'],previous.symbols['kernel'];equal=a['size']==b['size']and e.read(a['address'],a['size'])==previous.read(b['address'],b['size']);assert equal,'Original scalar kernel code changed'
 objdump=Path(args[0]).with_name('riscv64-unknown-elf-objdump');(out/'disassembly.txt').write_bytes(subprocess.check_output([str(objdump),'-d',str(out/'memory-routes.elf')]))
 inputs=[Path(__file__).resolve(),Path(__file__).with_name('validate.py'),old/'cases.py',old/'guest.c',old/'build.py',prior/'build.json',prior/'memory-routes.elf',Path(args[0]),objdump,*[ROOT/'benchmarks'/x for x in ('runtime.c','runtime.h','start.S','uart_drain.h','link.ld')],ROOT/'hardware/memory-paths.json',ROOT/'hardware/manifest.json',out/'guest.c',out/'cases.inc',out/'corpus.json',out/'split.json',out/'readback-layout.json'];identities={str(p):sha(p)for p in inputs};(out/'inputs').mkdir()
 for p,h in identities.items():(out/'inputs'/h).write_bytes(Path(p).read_bytes())
 report={'schema':'iris.memory_routes_current_build.v1','pass':True,'argv':args,'elf_sha256':sha(out/'memory-routes.elf'),'input_sha256':identities,'cases':1512,'regions':2592,'semantic_parents':252,'trials':3,'unchanged_window_source_sha256':hashlib.sha256(old_window.encode()).hexdigest(),'kernel_preparation_and_measured_window_source_unchanged':True,'compiled_kernel_byteidentical_original':equal,'kernel_bytes':a['size'],'bss_bytes':e.symbols['__bss_end']['address']-e.symbols['__bss_start']['address'],'old_timing_labels_applicable':False,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=build(a.output.resolve());print(json.dumps({k:r[k]for k in ('elf_sha256','cases','regions','kernel_bytes','bss_bytes')}))

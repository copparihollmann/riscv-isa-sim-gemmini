#!/usr/bin/env python3
"""Derive one broad fitting ELF; leave every parent suite and holdout unchanged."""
import argparse,copy,hashlib,importlib.util,json,re,struct,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;R=HERE.parents[1];COMMON=HERE.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--trials',type=int,default=5);p.add_argument('--compiler',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'));a=p.parse_args();out=a.output.resolve()
 if out.exists() or not 1<=a.trials<=20:raise ValueError('Fresh output and1..20trials required')
 out.mkdir();parents={};baseline=json.loads((COMMON/'calibration-corpus.json').read_text());golden=module('campaign_baseline_golden',COMMON/'golden.py');golden.verify(baseline)
 for c in baseline['cases']:
  x=copy.deepcopy(c);expr=x['active_hart_mask_expression'];x['mask']={'all':7,'compute':3,'1':1,'4':4}[expr];x['expected_checksums']=x['expected_checksums_by_hart'];parents.setdefault('baseline',[]).append(x)
 parents['distribution']=module('campaign_distribution_cases',COMMON/'v2/cases.py').cases();memory=module('campaign_memory_cases',COMMON/'memory_routes/cases.py');parents['memory']=memory.cases();assert [len(parents[x]) for x in parents]==[24,208,504]
 source_paths=[COMMON/'batch.c',COMMON/'calibration-corpus.json',COMMON/'heldout-corpus.json',COMMON/'v2/batch.c',COMMON/'v2/cases.py',COMMON/'memory_routes/guest.c',COMMON/'memory_routes/cases.py'];parent_hashes={str(p.relative_to(R)):sha(p) for p in source_paths};rows=[];per_suite={}
 for suite,cases in parents.items():
  for trial in range(a.trials):
   for c in cases:
    row=copy.deepcopy(c);row.update(parent_case_id=c['case_id'],case_id=c['case_id']+'.trial.'+str(trial),trial_id=trial,suite=suite,region='kernel',split='fitting');rows.append(row)
  per_suite[suite]={'parent_cases':len(cases),'cases':len(cases)*a.trials,'regions':sum(c['mask'].bit_count() if hasattr(int,'bit_count') else bin(c['mask']).count('1') for c in cases)*a.trials}
 assert len({c['case_id'] for c in rows})==len(rows)
 for c in rows:
  if (c.get('kind','').startswith('vme') or c.get('kernel')=='vme_mm') and c.get('kind')!='vme_refusal':assert not(c['mask']&4)
 fields=('n','mask','sew','lmul','mode','bytes','protocol','edge','tk','tiles');distribution=[c for c in rows if c['suite']=='distribution'];memrows=[c for c in rows if c['suite']=='memory']
 (out/'distribution_cases.inc').write_text('static const case_t experiments[]={\n'+',\n'.join('{'+json.dumps(c['case_id'])+',K_'+c['kind']+','+','.join(str(c[k]) for k in fields)+',{'+','.join(str(v)+'ULL' for v in c['expected_checksums'])+'}}' for c in distribution)+'\n};\n')
 (out/'memory_cases.inc').write_text('static const case_t experiments[]={\n'+',\n'.join('{'+json.dumps(c['case_id'])+','+str(c['base'])+'ULL,K_'+c['kind']+','+','.join(str(c[k]) for k in ['stride','spread','n','mask'])+',{'+','.join(str(v)+'ULL' for v in c['expected_checksums'])+'}}' for c in memrows)+'\n};\n')
 baseline_ids='static const char *const campaign_baseline_ids['+str(a.trials)+'][24]={\n'+',\n'.join('{'+','.join(json.dumps(c['case_id']+'.trial.'+str(t)) for c in parents['baseline'])+'}' for t in range(a.trials))+'\n};\n';(out/'baseline_ids.inc').write_text(baseline_ids)
 preservation=[]
 for suite,path in [('baseline',COMMON/'batch.c'),('distribution',COMMON/'v2/batch.c'),('memory',COMMON/'memory_routes/guest.c')]:
  original=path.read_text();text=original;boundary=text.index('static void run(');original_prefix=text[:boundary]
  text=text.replace('#include "runtime.h"','#include "runtime.h"\n#include "campaign.h"\n#include "campaign_counts.h"',1)
  if suite!='baseline':text=text.replace('#include "cases.inc"','#include "'+suite+'_cases.inc"',1)
  else:text=text.replace('#include "vme.h"','#include "vme.h"\n#include "baseline_ids.inc"',1)
  current_prefix=text[:text.index('static void run(')];normalized=current_prefix.replace('#include "campaign.h"\n#include "campaign_counts.h"\n','').replace('#include "baseline_ids.inc"\n','').replace('#include "'+suite+'_cases.inc"','#include "cases.inc"');assert normalized==original_prefix
  preservation.append({'suite':suite,'original_source_sha256':sha(path),'all_kernel_and_preparation_prefix_bytes':len(original_prefix),'prefix_sha256':hashlib.sha256(original_prefix.encode()).hexdigest(),'derived_prefix_normalized_byte_equal':True})
  # A new identity field is printed after the original numeric hart field,
  # outside measured intervals. Original kernels/prepare/checksum stay intact.
  anchor='putuint(i);';assert text.count(anchor)==1;text=text.replace(anchor,anchor+' campaign_identity("'+suite+'",'+('id' if suite=='baseline' else 'c->id')+');',1)
  begin=text.index('void benchmark_main(unsigned h) {');text=text[:begin]+text[begin:].replace('void benchmark_main(unsigned h) {','void campaign_'+suite+'_run(unsigned h'+(',unsigned trial' if suite=='baseline' else '')+') {',1)
  if suite=='baseline':
   text=text.replace('void campaign_baseline_run(unsigned h,unsigned trial) {','void campaign_baseline_run(unsigned h,unsigned trial) {\n  campaign_phase("baseline",trial,1);',1)
   for n,c in enumerate(parents['baseline']):
    token='run('+json.dumps(c['case_id'])+',';assert text.count(token)==1;text=text.replace(token,'run(campaign_baseline_ids[trial]['+str(n)+'],',1)
   marker='  barrier();\n  if(h==0) { putstr("IRIS_BATCH_DONE';end=text.rindex(marker);text=text[:end]+'  barrier();\n  if(!h&&failed)campaign_abort("baseline",failed);\n  campaign_phase("baseline",trial,0);barrier();\n}\n'
  elif suite=='distribution':
   text=text[:text.index('void campaign_distribution_run')]+'''void campaign_distribution_run(unsigned h) {
  for(unsigned trial=0;trial<CAMPAIGN_TRIALS;++trial){
    campaign_phase("distribution",trial,1);
    for(unsigned i=0;i<524288;++i)eviction[h][i]=1;
    if(!h)for(unsigned i=0;i<262144;++i)shared_data[i]=1;
    barrier();
    for(unsigned i=trial*CAMPAIGN_DISTRIBUTION_PER_TRIAL;i<(trial+1)*CAMPAIGN_DISTRIBUTION_PER_TRIAL;++i)run(&experiments[i]);
    if(!h&&failed)campaign_abort("distribution",failed);
    campaign_phase("distribution",trial,0);barrier();
  }
}
'''
  else:
   text=text[:text.index('void campaign_memory_run')]+'''void campaign_memory_run(unsigned h) {
  for(unsigned trial=0;trial<CAMPAIGN_TRIALS;++trial){
    campaign_phase("memory",trial,1);
    for(unsigned i=trial*CAMPAIGN_MEMORY_PER_TRIAL;i<(trial+1)*CAMPAIGN_MEMORY_PER_TRIAL;++i)run(&experiments[i],h);
    if(!h&&failed)campaign_abort("memory",failed);
    campaign_phase("memory",trial,0);barrier();
  }
}
'''
  # Fail on the first numerical case failure, after reporting its active harts.
  run_start=text.index('static void run(');run_end=text.index('void campaign_'+suite+'_run');section=text[run_start:run_end];last=section.rindex('  barrier();');section=section[:last]+'  if(!h&&failed)campaign_abort("'+suite+'",failed);\n'+section[last:];text=text[:run_start]+section+text[run_end:]
  assert 'void benchmark_main' not in text and 'IRIS_BATCH_DONE' not in text and 'finish(' not in text
  (out/(suite+'.c')).write_text(text)
 count=sum(bin(c['mask']).count('1') for c in rows);(out/'campaign_counts.h').write_text('#pragma once\n#define CAMPAIGN_TRIALS '+str(a.trials)+'\n#define CAMPAIGN_CASES '+str(len(rows))+'\n#define CAMPAIGN_REGIONS '+str(count)+'\n#define CAMPAIGN_DISTRIBUTION_PER_TRIAL 208\n#define CAMPAIGN_MEMORY_PER_TRIAL 504\n')
 corpus={'schema_version':2,'split_id':'iris-broad-fit-campaign-v1','purpose':'fitting only, all heldout sources remain separate','cases':rows,'trials':a.trials,'physical_harts':3,'expected_region_count':count,'suites':per_suite,'parent_source_sha256':parent_hashes,'source_preservation':preservation,'inactive_policy':'Parent WFI+CLINT wake, early finishers barrier outside own ROI','order':'baseline trials0..N; distribution trials0..N; memory trials0..N','cache_policy':'Parent preparation and warm/eviction attempt semantics retained; no guaranteed cold/reset claim','counter_policy':'Raw parent mcycle/minstret intervals and drain policy; no subtraction','memory_regions':memory.REGIONS,'timing_certified':False,'hardware_contacted':False}
 (out/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n');elf=out/'campaign.elf';compiler=a.compiler.resolve();argv=[str(compiler),'-O2','-g','-Wall','-Wextra','-Wno-unused-function','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-fno-common','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-I'+str(COMMON),'-I'+str(HERE),'-I'+str(out),'-I'+str(R/'third_party/saturn/benchmarks/common'),'-T',str(COMMON/'link.ld'),str(COMMON/'start.S'),str(COMMON/'runtime.c'),str(HERE/'main.c')]+[str(out/(suite+'.c')) for suite in parents]+['-lgcc','-o',str(elf)];q=subprocess.run(argv,capture_output=True,text=True);(out/'build.log').write_text(q.stdout+q.stderr)
 if q.returncode:raise RuntimeError('Build failed; see '+str(out/'build.log'))
 raw=elf.read_bytes();phoff=struct.unpack_from('<Q',raw,32)[0];phsize,phnum=struct.unpack_from('<HH',raw,54);segments=[]
 for k in range(phnum):
  typ,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',raw,phoff+k*phsize)
  if typ!=1:continue
  segments.append({'physical_base':pa,'memory_bytes':ms,'file_bytes':fs})
  for name,(base,size) in memory.REGIONS.items():assert max(base,pa)>=min(base+size,pa+ms),('ELF target overlap',name)
 objdump=compiler.with_name('riscv64-unknown-elf-objdump');disassembly=out/'campaign.disassembly';subprocess.run([str(objdump),'-d',str(elf)],stdout=disassembly.open('w'),check=True);libgcc=Path(subprocess.check_output([str(compiler),'-print-libgcc-file-name'],text=True).strip())
 inputs=source_paths+[HERE/'build.py',HERE/'campaign.h',HERE/'main.c',*[COMMON/n for n in ['runtime.h','runtime.c','uart_drain.h','start.S','link.ld']],R/'third_party/saturn/benchmarks/common/vme.h',compiler,objdump,libgcc]+[p for p in out.iterdir() if p.suffix in ['.c','.h','.inc']]+[out/'corpus.json'];identities={str(p):sha(p) for p in inputs};(out/'inputs').mkdir()
 for name,d in identities.items():
  target=out/'inputs'/d
  if not target.exists():target.write_bytes(Path(name).read_bytes())
 receipt={'schema':'iris.broad_campaign_build.v1','argv':argv,'input_sha256':identities,'elf_sha256':sha(elf),'disassembly_sha256':sha(disassembly),'compiler_version':subprocess.check_output([str(compiler),'--version'],text=True).splitlines()[0],'ELF_load_segments':segments,'cases':len(rows),'regions':count,'trials':a.trials,'parent_sources_unchanged':all(sha(R/name)==d for name,d in parent_hashes.items()),'source_preservation':preservation,'executed':False,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'cases':len(rows),'regions':count,'elf_sha256':sha(elf),'build':str(out)}))
if __name__=='__main__':main()

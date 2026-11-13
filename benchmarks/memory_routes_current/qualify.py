#!/usr/bin/env python3
"""Review compiled geometry, exact kernels and independently corrupt real outputs."""
import argparse,copy,hashlib,json
from pathlib import Path
from build import ROOT,sha
from validate import admitted,validate,check_elf,ELF
def qualify(build):
 corpus=json.loads((build/'corpus.json').read_text());layout=json.loads((build/'readback-layout.json').read_text());b=json.loads((build/'build.json').read_text());elf=build/'memory-routes.elf';checks=check_elf(elf,corpus,layout)
 for p,h in b['input_sha256'].items():
  if sha(p)!=h or sha(build/'inputs'/h)!=h:raise ValueError('Changed build input '+p)
 original=(ROOT/'benchmarks/memory_routes/guest.c').read_text();new=(build/'guest.c').read_text();start='static uintptr_t address(';stop='  if(h==0) for(unsigned i=0;i<3;++i) if(c->mask&(1U<<i)) {';window=original[original.index(start):original.index(stop)]
 if window!=new[new.index(start):new.index('  if(h==0) {\n    const uint64_t case_index')]:raise ValueError('Preparation/kernel/counter/WFI window changed')
 old=ELF(ROOT/'build/memory-routes-fit-v1-final/memory-routes.elf');current=ELF(elf);a,z=old.symbols['kernel'],current.symbols['kernel']
 if a['size']!=z['size']or old.read(a['address'],a['size'])!=current.read(z['address'],z['size']):raise ValueError('Compiled original kernel changed')
 reports=[];identities=dict(b['input_sha256']);rows=None;text=None
 for seed in (0,17):
  d=build/f'seed{seed}';r=json.loads((d/'run.json').read_text())
  if not r['pass']or r['exit_status']!=0 or r['seed']!=seed or r['elf_sha256']!=sha(elf)or r['argv'][-1]!=str(elf):raise ValueError('Both exact successful functional schedules required')
  for p,h in r['input_sha256'].items():
   if sha(p)!=h:raise ValueError('Functional dependency changed')
  text=(d/'run.stdout').read_text();validate(text,corpus)
  if sha(d/'run.stdout')!=r['stdout_sha256']or sha(d/'run.stderr')!=r['stderr_sha256']:raise ValueError('Console changed')
  identities.update(r['input_sha256']);identities.update({str(p):sha(p)for p in (d/'run.json',d/'run.stdout',d/'run.stderr')});reports.append({'seed':seed,'host_seconds':r['host_seconds'],'normal_guest_exit_verified':True});rows=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_REGION ')]
 negatives=[]
 def refuse(label,action):
  try:action()
  except (ValueError,AssertionError,KeyError,TypeError):negatives.append({'name':label,'rejected':True})
  else:raise ValueError('Corruption accepted '+label)
 for field in ('checksum','expected_checksum','hart','trial_id','parent_case_id','start_cycle','instret_delta'):
  changed=copy.deepcopy(rows)
  if field=='hart':changed[0][field]=2
  elif field=='parent_case_id':changed[0][field]='wrong-parent'
  elif field=='start_cycle':changed[0][field]=changed[0]['end_cycle']
  elif field=='instret_delta':changed[0][field]=0
  else:changed[0][field]^=1
  console=''.join('IRIS_REGION '+json.dumps(r)+'\n'for r in changed)+'IRIS_BATCH_DONE {"failed":0,"cases":1512,"regions":2592}\n';refuse(field,lambda:validate(console,corpus))
 refuse('duplicate-region',lambda:validate(text+'IRIS_REGION '+json.dumps(rows[0])+'\n',corpus))
 refuse('missing-hart2',lambda:validate('\n'.join(l for l in text.splitlines()if not(l.startswith('IRIS_REGION ')and json.loads(l.split(' ',1)[1])['hart']==2)),corpus))
 refuse('missing-terminal',lambda:validate('\n'.join(l for l in text.splitlines()if not l.startswith('IRIS_BATCH_DONE ')),corpus))
 for field,value in [('mask',4),('base',0x85000000),('expected_checksums',[0,0,0]),('trial_id',17)]:
  changed=copy.deepcopy(corpus);changed['cases'][0][field]=value;refuse('corpus-'+field,lambda c=changed:admitted(c))
 wrong=copy.deepcopy(layout);wrong['objects']['buffered_records']['size']+=8;refuse('ELF-layout',lambda:check_elf(elf,corpus,wrong))
 (build/'negative-controls.json').write_text(json.dumps(negatives,indent=2)+'\n')
 split=json.loads((build/'split.json').read_text());counts={k:sum(v==k for v in split['split'].values())for k in ('train','internal_validation')}
 identities.update({str(p):sha(p)for p in (Path(__file__).resolve(),Path(__file__).with_name('validate.py'),build/'corpus.json',build/'split.json',build/'build.json',build/'readback-layout.json',build/'negative-controls.json',elf)})
 review={'schema':'iris.memory_routes_current_independent_review.v1','pass':True,'elf_sha256':sha(elf),'corpus_sha256':sha(build/'corpus.json'),'split_sha256':sha(build/'split.json'),'kernel_preparation_window_source_equal':True,'compiled_kernel_byteidentical_original':True,'compiled_kernel_bytes':160,'compiled_table_identity_order_verified':True,'independent_goldens_verified':True,'all_targets_and_masks_checked':True,'cases':1512,'semantic_parents':252,'regions':2592,'split_parent_counts':counts,**checks,'input_sha256':identities};(build/'independent-review.json').write_text(json.dumps(review,indent=2)+'\n')
 qualification={'schema':'iris.memory_routes_current_qualification.v1','pass':True,'elf_sha256':sha(elf),'functional_schedules':reports,'negative_controls':negatives,'input_sha256':identities,'hardware_contacted':False};(build/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
 ready={'schema':'iris.memory_routes_current_ready.v1','fitting_only':True,'global_heldout':False,'elf_sha256':sha(elf),'corpus_sha256':sha(build/'corpus.json'),'build_sha256':sha(build/'build.json'),'qualification_sha256':sha(build/'qualification.json'),'readback_layout_sha256':sha(build/'readback-layout.json'),'independent_prelaunch_review':str(build/'independent-review.json'),'independent_prelaunch_review_sha256':sha(build/'independent-review.json'),'required_cases':1512,'required_regions':2592,'trials':3,'new_exact_ELF_reference_required':True,'old_timing_labels_applicable':False};(build/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');return ready
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);a=p.parse_args();r=qualify(a.build.resolve());print(json.dumps({'pass':True,'ready_sha256':sha(a.build.resolve()/'ready.json'),'regions':r['required_regions']}))

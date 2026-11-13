#!/usr/bin/env python3
"""Close source/functional evidence only; does not prepare or launch hardware."""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'zephyr'))
from hart2_pow2_validate_v4 import validate,m
from elftools.elf.elffile import ELFFile

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def raw_symbols(p):
 with Path(p).open('rb')as f:
  e=ELFFile(f);out={}
  for s in e.get_section_by_name('.symtab').iter_symbols():
   if type(s['st_shndx'])is not int:continue
   sec=e.get_section(s['st_shndx'])
   if sec['sh_type']=='SHT_NOBITS':continue
   out[s.name]=sec.data()[s['st_value']-sec['sh_addr']:s['st_value']-sec['sh_addr']+s['st_size']]
  return out

def run(a):
 out=a.output.resolve();out.mkdir(parents=True);app=ROOT/'benchmarks/zephyr_hart2_pow2_v4';normal=ROOT/'build/zephyr-hart2-pow2-normal-v4';negative=ROOT/'build/zephyr-hart2-pow2-skip-v4';inputs={};artifacts={};runs=[]
 def bind(p):
  p=Path(p).resolve();h=sha(p)
  if str(p)in inputs and inputs[str(p)]!=h:raise ValueError('Conflicting input '+str(p))
  inputs[str(p)]=h;return h
 for b in [normal,negative]:
  receipt=read(b/'build.json');assert receipt['status']=='built'and receipt['elf_sha256']==sha(b/'zephyr/zephyr.elf')
  for p,h in receipt['input_sha256'].items():assert sha(ROOT/p)==h;bind(ROOT/p)
  bind(b/'build.json');bind(b/'zephyr/zephyr.elf')
 for mode in ['normal','skip']:
  for seed in [0,17]:
   folder=ROOT/('build/zephyr-hart2-pow2-%s-seed%d-v4'%(mode,seed));r=read(folder/'report.json');assert r['pass']is True and r['seed']==seed and r['expect_failure']==(mode=='skip')and not r['timed_out']and r['exit_status']==(1 if mode=='skip'else 0)
   for p,h in r['input_sha256'].items():assert sha(p)==h;bind(p)
   assert sha(folder/'stdout')==r['stdout_sha256']and sha(folder/'stderr')==r['stderr_sha256']
   proof=validate((folder/'stdout').read_text(),mode=='skip');assert proof==r['proof']
   assert proof['failed_regions']==(648 if mode=='skip'else 0)and proof['failed_elements']==(181440 if mode=='skip'else 0)
   runs.append(dict(mode=mode,seed=seed,results=str(folder/'report.json'),results_sha256=bind(folder/'report.json'),stdout_sha256=bind(folder/'stdout'),stderr_sha256=bind(folder/'stderr'),exit_status=r['exit_status'],host_seconds=r['host_seconds'],regions=648,independent_elements=181440,failed_elements=proof['failed_elements']))
 source=ROOT/'build/zephyr-hart2-pow2-source-proof-v4/report.json';sp=read(source);assert sp['pass']is True and sp['ELF_sha256']==sha(normal/'zephyr/zephyr.elf')and sp['controller_no_FP_or_vector']is True;bind(source)
 for p,h in sp['input_sha256'].items():assert sha(p)==h;bind(p)
 control=ROOT/'build/zephyr-hart2-pow2-controls-v2/report.json';ctrl=read(control);assert ctrl['pass']is True and ctrl['count']>=27 and all(x['rejected']is True for x in ctrl['rejected_controls']);bind(control)
 for p,h in ctrl['input_sha256'].items():assert sha(p)==h;bind(p)
 n=raw_symbols(normal/'zephyr/zephyr.elf');g=raw_symbols(negative/'zephyr/zephyr.elf')
 for name in ['packet_vadd','packet_mm_int','packet_mm_e4','packet_mm_e5']:assert n[name]==g[name]
 call=(0x000480e7).to_bytes(4,'little');assert n['packet_measure'].count(call)==1 and not g['packet_measure'].count(call)and n['packet_measure'].replace(call,b'')==g['packet_measure']
 assert 'packet_reset_output' in n and 'packet_reset_output'in g
 corpus=m.generate();assert corpus==read(app/'corpus.json');assert read(app/'split.json')==read(ROOT/'benchmarks/zephyr_hart2_pow2_v1/split.json')
 bind(app/'README.md');bind(Path(__file__).resolve());bind(ROOT/'zephyr/hart2_pow2_controls_v2.py');bind(app/'split.json')
 independent=None
 if a.independent_review:
  q=read(a.independent_review)
  if q.get('pass')is not True:raise ValueError('Independent review not PASS')
  independent=dict(path=str(a.independent_review.resolve()),sha256=bind(a.independent_review))
 for p,h in sorted(inputs.items()):
  target=out/'input-snapshot'/h[:2]/h
  if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
  assert sha(target)==h
 artifacts={str(Path(p).relative_to(ROOT)) if Path(p).is_relative_to(ROOT)else p:h for p,h in inputs.items()}
 result=dict(schema='iris.zephyr_hart2_pow2_qualification.v1',**{'pass':True},status='source_functional_qualified',ELF_sha256=sha(normal/'zephyr/zephyr.elf'),normal_build=str(normal),negative_build=str(negative),groups=486,regions=648,active_elements=181440,raw_active_bytes=sum(r['bytes']for r in corpus['regions']),sentinel_regions=648,worker_harts=[0,1],controller_hart=2,training_eligible=456,protected_validation=192,split_sha256=sha(app/'split.json'),functional_runs=runs,measured_call_only_omission=dict(actual_negative_runs=2,all648_regions_fail=True,all181440_elements_fail=True,warm_call_and_reset_retained=True,actual_terminal_exit=1,normal_vs_negative_target_bodies_identical=True,only_measured_indirect_call_removed=True),source_proof=dict(path=str(source),sha256=sha(source)),controls=dict(path=str(control),sha256=sha(control),rejections=ctrl['count']),independent_review=independent,input_sha256=inputs,retained_bytes='CAS input-snapshot contains each bound current source/evidence input',calibration_authorized=False,hardware_prepared=False,hardware_contacted=False,normal_hardware_completion_required=True,source_image_association=False,timing_certified=False,scope_limits=['single persistent VME owner per compute hart','no context migration or competing-owner qualification','INT8 unsigned TK1 and finite exact FP8 all4 pairs only','active MxN cells and guards; no arbitrary MRF padding/columns','ordinary hart2 scalar orchestration; no hart2 vector or detailed timing','conditioned pre-execution/reset; no physical cache-hit/cold claim','each new ELF/history requires its own future hardware reference'])
 (out/'qualification.json').write_text(json.dumps(result,indent=2)+'\n')
 ready=dict(schema='iris.zephyr_hart2_pow2_ready.v1',status='source_functional_qualified',**{'pass':True},elf=str(normal/'zephyr/zephyr.elf'),elf_sha256=sha(normal/'zephyr/zephyr.elf'),build=str(normal/'build.json'),build_sha256=sha(normal/'build.json'),corpus_path=str(app/'corpus.json'),corpus_sha256=sha(app/'corpus.json'),split_path=str(app/'split.json'),split_sha256=sha(app/'split.json'),qualification=str(out/'qualification.json'),qualification_sha256=sha(out/'qualification.json'),required_regions=648,dispatch_groups=486,required_elements=181440,training_eligible=456,protected_validation=192,hardware_preparation_requires_root_review=True,independent_review=independent,calibration_authorized=False,hardware_contacted=False)
 (out/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');return ready
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--independent-review',type=Path);a=p.parse_args();r=run(a);print(json.dumps(r))

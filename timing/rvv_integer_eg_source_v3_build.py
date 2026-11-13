#!/usr/bin/env python3
"""Finish finite integer proof; preserve/reconstruct already-passed full-unit runs."""
from pathlib import Path
import argparse,hashlib,importlib.util,itertools,json,os,shutil,subprocess,time
R=Path(__file__).resolve().parents[1];SDK=R/'build/saturn-timing-ownership-sdk-v7/sdk';RTL=R/'build/saturn-timing-component-v1-final/build/saturn-timing-source-v1/compute/rtl'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);old=R/'build/rvv-integer-EG-source-v1';commands=[];initial={};inputs=[Path(__file__).resolve(),R/'timing/rvv_integer_eg_source_v1_build.py',R/'timing/rvv_integer_eg_source_v1.hpp',R/'timing/rvv_integer_eg_source_v1_probe.cpp',R/'timing/rvv_integer_eg_source_v1_numeric.cpp',R/'timing/rvv_integer_eg_source_v1_guards.cpp',R/'timing/rvv_integer_eg_source_v2_sequence_check.cpp',SDK/'saturn_timing.hpp',SDK/'libiris_saturn_timing.a',SDK/'ownership-schema.json',SDK.parent/'build.json',Path('/usr/bin/g++')];initial={str(p):sha(p)for p in inputs}
 def run(argv,folder,timeout=120):
  folder.mkdir(parents=True,exist_ok=False);argv=list(map(str,argv));start=time.monotonic()
  with(folder/'stdout').open('wb')as so,(folder/'stderr').open('wb')as se:p=subprocess.run(argv,stdout=so,stderr=se,timeout=timeout,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ.get('PATH','')))
  row=dict(argv=argv,exit_status=p.returncode,host_seconds=time.monotonic()-start,stdout_sha256=sha(folder/'stdout'),stderr_sha256=sha(folder/'stderr'));commands.append(row);(folder/'run.json').write_text(json.dumps(row,indent=2)+'\n');return p.returncode
 # Fresh compile; this reproducer does not consume prior test outcomes.
 for name,src in [('probe','rvv_integer_eg_source_v1_probe.cpp'),('numeric-probe','rvv_integer_eg_source_v1_numeric.cpp')]:
  assert run(['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(SDK),'-I'+str(R/'timing'),R/'timing'/src,SDK/'libiris_saturn_timing.a','-latomic','-o',out/name],out/('compile-'+name))==0
 def result(folder):
  runrow=json.loads((folder/'run.json').read_text());assert runrow['exit_status']==0;assert sha(folder/'stdout')==runrow['stdout_sha256']and sha(folder/'stderr')==runrow['stderr_sha256'];rows=[x for x in reversed((folder/'stderr').read_text().splitlines())if x.startswith('{')];r=json.loads(rows[0]);assert r['pass']is True;return r
 rows=[];numeric=[];positive_inputs={}
 for sew,lm,mode,seed in itertools.product((8,16,32,64),(1,2,4,8),range(4),(1,17)):
  for prefix,dest,count in [('',rows,96),('numeric-',numeric,64)]:
   folder=out/f'{prefix}H{sew}-M{lm}-mode{mode}-seed{seed}';assert run([out/('numeric-probe'if prefix else'probe'),sew,lm,mode,seed,count],folder)==0;r=result(folder);assert(r['SEW'],r['LMUL'],r['mode'],r['seed'],r['commands'])==(sew,lm,mode,seed,count);assert r['microissues']==r['physical_write_beats']==count*2*lm
   if prefix:assert r['output_bytes']==3*32*lm and r['output_Put_requests']==3*2*lm and r['source_reset_and_VMV_initialization_only']is True
   dest.append(r)
   for n in('run.json','stdout','stderr'):positive_inputs[str(folder/n)]=sha(folder/n)
 header=R/'timing/rvv_integer_eg_source_v1.hpp';probe=R/'timing/rvv_integer_eg_source_v1_probe.cpp';numericprobe=R/'timing/rvv_integer_eg_source_v1_numeric.cpp';guard=R/'timing/rvv_integer_eg_source_v1_guards.cpp';mutants=[]
 for name,oldtext,newtext,args in [('extra-IQ-entry','iq_capacity=3','iq_capacity=4',[8,8,0,1,96]),('whole-register-EG','d=2*c.vd+index_','d=2*c.vd',[32,1,1,1,32]),('flow-full-VDQ','e.input_ready=vdq_.size()<vdq_capacity;','e.input_ready=vdq_.size()<vdq_capacity||e.vdq_dequeue;',[8,8,0,1,96])]:
  folder=out/'mutants'/name;folder.mkdir(parents=True);text=header.read_text();assert text.count(oldtext)==1;(folder/header.name).write_text(text.replace(oldtext,newtext));shutil.copy2(probe,folder/probe.name);assert run(['/usr/bin/g++','-O2','-std=c++20','-pthread','-I'+str(SDK),'-I'+str(folder),folder/probe.name,SDK/'libiris_saturn_timing.a','-latomic','-o',folder/'probe'],folder/'compile')==0;assert run([folder/'probe',*args],folder/'check')==2;assert'model='in(folder/'check/stderr').read_text();mutants.append(dict(name=name,scope='actual saved full-unit field differential',mismatch_detected=True))
 for name,text,source,args,expected in [
  ('wrong-depth2',header.read_text().replace('std::array<std::optional<Micro>,1>','std::array<std::optional<Micro>,2>').replace('write_depth=1','write_depth=2'),probe,[32,1,0,1,32],'model='),
  ('corrupt-independent-output-golden',header.read_text(),numericprobe,[32,1,0,1,16],'actual output byte disagrees')]:
  folder=out/'mutants'/name;folder.mkdir(parents=True);(folder/header.name).write_text(text);source_text=source.read_text()
  if name.startswith('corrupt'):source_text=source_text.replace('byte==logical[32*(8+8*group)+offset]','byte==(logical[32*(8+8*group)+offset]^1)')
  (folder/source.name).write_text(source_text);assert run(['/usr/bin/g++','-O2','-std=c++20','-pthread','-I'+str(SDK),'-I'+str(folder),folder/source.name,SDK/'libiris_saturn_timing.a','-latomic','-o',folder/'probe'],folder/'compile')==0;assert run([folder/'probe',*args],folder/'check')==2;assert expected in(folder/'check/stderr').read_text();mutants.append(dict(name=name,scope='actual source full-unit differential'if name=='wrong-depth2'else'actual source output independent-golden verifier',mismatch_detected=True))
 # Original integer ExecuteSequencer: no RVD port or altfmt specialization.
 # All external hazard/ready/data inputs are explicit, with no state injection.
 seq=out/'sequencer';seq.mkdir();svs=[RTL/'ExecuteSequencer.sv',RTL/'PipeScheduler.sv'];inputs+=svs
 for p in svs:shutil.copy2(p,seq/p.name)
 verilator=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');perl=verilator.with_name('perl');inputs.extend([verilator,perl]);source=R/'timing/rvv_integer_eg_source_v2_sequence_check.cpp';argv=[perl,verilator,'--cc','--exe','--build','-j','4','--top-module','ExecuteSequencer','--prefix','VIntegerSourceSeq','--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',seq/'obj','+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT',*[seq/p.name for p in svs],source,'-CFLAGS','-std=c++20 -O2 -I'+str(R/'timing'),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O2 OPT_SLOW=-O2'];assert run(argv,seq/'compile')==0
 sequence=[]
 for seed in(1,17,31):
  folder=seq/f'seed{seed}';assert run([seq/'obj/VIntegerSourceSeq',seed],folder)==0;sequence.append(json.loads(next(x for x in reversed((folder/'stdout').read_text().splitlines())if x.startswith('{'))))
 guards=[]
 for name,flags in [('optimized',['-O2']),('checked',['-O1','-D_GLIBCXX_ASSERTIONS'])]:
  assert run(['/usr/bin/g++',*flags,'-std=c++20',guard,'-o',out/('guards-'+name)],out/('guard-compile-'+name))==0;folder=out/('guard-check-'+name);assert run([out/('guards-'+name)],folder)==0;guards.append(dict(mode=name,**json.loads((folder/'stdout').read_text())))
 api_mutants=[]
 for name,oldtext,newtext in [('no-RAW','e.raw=bool((bit(s1)|bit(s2))&writes);','e.raw=false;'),('no-WAW','e.waw=bool(bit(d)&writes);','e.waw=false;'),('no-WAR','e.war=bool(bit(d)&ports.older_reads);','e.war=false;')]:
  folder=out/'API-mutants'/name;folder.mkdir(parents=True);text=header.read_text();assert text.count(oldtext)==1;(folder/header.name).write_text(text.replace(oldtext,newtext));shutil.copy2(guard,folder/guard.name);assert run(['/usr/bin/g++','-O2','-std=c++20',folder/guard.name,'-o',folder/'guard'],folder/'compile')==0;assert run([folder/'guard'],folder/'check')==1;api_mutants.append(dict(name=name,independent_guard_refused=True,source_counterpart='original source sequencer randomized boundary differential'))
 schema=R/'build/saturn-timing-activity-component-v1-final/build/saturn-timing-activity-schema-v1/schema.json';inputs.append(schema);fields=json.loads(schema.read_text())['profiles']['compute']['fields'];witness=[]
 for name in('vu.vxsint.valid','vu.vxuint.io_pipe_hazards_0_valid','vu.vxuint.io_pipe_hazards_1_valid','vu.vdq.valids_0','vu.vxissq_int.q.valids_0'):
  q=next(f for f in fields if f['name']==name)['source'];p=Path(q['path']);assert sha(p)==q['sha256']and p.read_text().splitlines()[q['line']-1]==q['literal'];inputs.append(p);witness.append(dict(field=name,**q))
 for rel in ('backend/Backend.scala','backend/ExecuteSequencer.scala','backend/IssueQueue.scala','backend/RegisterAccess.scala','backend/RegisterFile.scala','exu/ExecutionUnit.scala','exu/int/IntegerPipe.scala','common/Parameters.scala'):inputs.append(R/'third_party/saturn/src/main/scala'/rel)
 inputs.extend([RTL/'IntegerPipe.sv',RTL/'ExecutionUnitint.sv',RTL/'VectorBackend.sv'])
 for p,h in initial.items():assert sha(p)==h,'Input changed during qualification: '+p
 snapshots=out/'inputs';snapshots.mkdir()
 for p in dict.fromkeys(inputs):
  if p.stat().st_size<8*1024*1024:shutil.copy2(p,snapshots/sha(p))
 r=dict(schema='iris.rvv_integer_VADD_per_EG_source_differential.v2',**{'pass':True},profile='saved Compute128, identical configured harts0/1 geometry; no detailedhart2 timing',fresh_clean_qualification_run=True,full_unit_control_runs=len(rows),full_unit_numeric_runs=len(numeric),control_commands=sum(x['commands']for x in rows),numeric_commands=sum(x['commands']for x in numeric),control_field_checks=sum(x['edge_checks']for x in rows),numeric_field_checks=sum(x['edge_checks']for x in numeric),control_microissues=sum(x['microissues']for x in rows),numeric_microissues=sum(x['microissues']for x in numeric),physical_VRF_write_beats=sum(x['physical_write_beats']for x in rows+numeric),independent_output_bytes=sum(x['output_bytes']for x in numeric),source_VADD_issue_to_write_edges=1,source_integer_unit_physical_maxslots=2,source_VADD_secondslot_always_inactive=True,source_VDQ_capacity=4,source_IQ_capacity=3,source_queue_pipe_flow='VDQ no pipe/no flow; IQ pipe/no flow',geometry=dict(SEW=[8,16,32,64],LMUL=[1,2,4,8],modes=['dependent','independent','chaining','WAW'],reset_seeds=[1,17]),full_unit_rows=rows,numeric_rows=numeric,sequencer_port_rows=sequence,finite_API_guards=guards,source_mutation_controls=mutants,API_guard_mutation_controls=api_mutants,source_witnesses=witness,observed_readiness_or_internal_state_injected=False,original_RTL_modified=False,fresh_reference_executable_sha256={n:sha(out/n)for n in('probe','numeric-probe')},native_integrated=False,hardware_contacted=False,FPGA_or_protected_timing_labels_consumed=False,parameters_fitted=False,numerical_VADD_outputs_verified=True,full_CPU_knownness_flags_IRQ_publication_qualified=False,source_image_association=False,timing_certified=False,limitations=['Only integerVADD.VV fullVLmax unmasked vstart0 aligned groups; no reductions/widening/otherALU/masking/fractionalLMUL.','Controlinput begins at actual saved backend dispatch boundary. Fullunit EX/PFC sends/replays are reference stimulus, not an independently implemented CPUbridge.','Numeric initial values enter through actual VMV.VX after source reset/scrub; no RAM or internalstate writes. Final allbytes checked on actual accepted VSE8Put payload/masks after VADD full drain.','Memory output service is explicitly synthetic identityTLB, periodic Aready and ACK delay2+seedmod5; it makes no DRAM/L2/cyclecost claim.','External hazards/read/write port backpressure qualify original sequencer inputs; arbitrary simultaneous otherunit/SMP conflict is not fullunit-qualified.','No native architectural visibility/cancellation/context/IRQ or complete fourstate definedness policy is provided; existingdefault/refusals unchanged.','Initial observer absent-field/TLB-before-reset failures and exact integersequencer absent-port compile failure remain preserved.'],argv=commands,input_sha256={str(p):sha(p)for p in dict.fromkeys(inputs)},prior_positive_raw_sha256=positive_inputs,executable_sha256={str(p):sha(p)for p in (out/'probe',out/'numeric-probe',seq/'obj/VIntegerSourceSeq',out/'guards-optimized',out/'guards-checked')})
 (out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k]for k in('pass','full_unit_control_runs','full_unit_numeric_runs','control_field_checks','numeric_field_checks','independent_output_bytes')}))
if __name__=='__main__':main()

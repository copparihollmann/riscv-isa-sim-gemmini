#!/usr/bin/env python3
"""Real three-hart observer parity, source ownership joins, and bounded refusals."""
import argparse,copy,concurrent.futures,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from iris_model.source_profile_run_v1 import run,sha
from iris_model.source_event_profile_v1 import profile
NM=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm')
ROM=ROOT/'board/evidence/bootrom.rv64.img'
def need(v,s):
 if not v:raise ValueError(s)
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--model',type=Path,required=True);p.add_argument('--guest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);x=p.parse_args();model,elf,out=[v.resolve()for v in(x.model,x.guest,x.output)];out.mkdir(exist_ok=False)
 inputs={str(v):sha(v)for v in(model,elf,Path(__file__).resolve(),ROOT/'iris_model/source_profile_run_v1.py',ROOT/'iris_model/source_event_profile_v1.py',ROM,NM,ROOT/'iris_model/empirical_run.py')};checks=[]
 def check(name,condition):need(condition,name);checks.append(dict(name=name,pass_=True))
 # Same model/ELF/seed: observer only; no source-model, fixture or output mutation.
 def execute(name,journal=True,program=elf,timeout=90):return run(program,model,out/name,timeout,0,'source-events.jsonl'if journal else None)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
  f=pool.submit(execute,'ON');g=pool.submit(execute,'OFF',False);on,off=f.result(),g.result()
 check('normal three-hart ON/OFF exits',on['pass']and off['pass']and on['profile_pass']is True and off['source_profile']is None)
 for name in('stdout','stderr','native-summary.json','features.jsonl'):check('trace toggle byte parity '+name,(out/'ON'/name).read_bytes()==(out/'OFF'/name).read_bytes())
 text=(out/'ON/stdout').read_text();rows=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_REGION ')];check('independent complete 136-word goldens',len(rows)==3 and all(r['pass']is True and r['failed']==0 and r['hart']==i and r['vl']==(64 if i<2 else 8)and r['checksum']==(64*0x42000000 if i<2 else 8*35)for i,r in enumerate(rows))and text.endswith('IRIS_SOURCE_PROFILE_DONE 0\n'))
 summary=json.loads((out/'ON/source-profile/summary.json').read_text());fadd=summary['FADD'];check('actual COM and all16B source writes',fadd['authoritative_COM_commands']==64 and fadd['completed_EG_writes']==1024 and fadd['completed_logical_add_elements']==4096 and fadd['internal_VRF_write_bytes']==16384 and fadd['pending_commands']==0 and fadd['pipeline_union_complete']is True and summary['journal_complete']is True)
 check('ELF per-function attribution',len(fadd['per_function'])==2 and all(r['function']=='source_fadd_body'and r['completed_EG_writes']==512 for r in fadd['per_function']))
 check('actual explicit CSR regions',len(summary['regions'])==3 and[r['FADD_actual_completed_EG_writes']for r in summary['regions']]==[512,512,0]and all(r['physical_memory_bytes']is None for r in summary['regions']))
 check('wrongpath reservations uncredited',fadd['canceled_reservations_without_work_credit']>0)
 check('no physical or OPU MAC inference',summary['source_image_attested']is False and summary['timing_accuracy_certified']is False and summary['OPU']['logical_MAC_work']is None and summary['OPU']['physical_MAC_peak']is None)
 trace=json.loads((out/'ON/source-profile/trace.json').read_text())['traceEvents'];check('Perfetto actual source write/function events',sum(t['name']=='actual16B VRF publication'for t in trace)==1024)
 # Offline re-render identical captured source events with explicit maps, never guessed pairs.
 event=out/'ON/source-events.jsonl';features=out/'ON/features.jsonl';console=out/'ON/stdout';native=out/'ON/native-summary.json'
 def render(name,events=event,feats=features,con=console,regmap=None,fmt='iris-json',complete=True):return profile(events,feats,con,native,elf,ROM,out/name,NM,regmap,fmt,complete)
 mapping=out/'regions.json';mapping.write_text(json.dumps(dict(schema='iris.source_event_region_map.v1',regions=[{k:r[k]for k in('case_id','hart','start_cycle','end_cycle')}for r in rows]))+'\n');mapped=render('mapped',regmap=mapping)
 check('provided map actual CSR joins',mapped['regions']==summary['regions'])
 none=render('wholeprogram',fmt='none');check('no guessed CSR pairing',none['regions']==[]and none['FADD']==fadd)
 mutations=[];raw=[json.loads(l)for l in event.read_text().splitlines()];ep=[json.loads(l)for l in features.read_text().splitlines()]
 def rejected(name,mutate,kind='event'):
  v=copy.deepcopy(raw if kind=='event'else ep);mutate(v);path=out/(name+'.jsonl');path.write_text(''.join(json.dumps(r)+'\n'for r in v));reason=None
  try:render('reject-'+name,events=path if kind=='event'else event,feats=path if kind=='prefix'else features)
  except(ValueError,KeyError,TypeError)as e:reason=str(e)
  need(reason,'Corrupt observation admitted '+name);mutations.append(dict(name=name,refused=True,reason=reason,input_sha256=sha(path)))
 def first(v,kind):return next(e for e in v if e['event']==kind)
 rejected('duplicate-write',lambda v:v.append(copy.deepcopy(first(v,'fadd_EG_physical_write'))))
 rejected('unowned-write',lambda v:first(v,'fadd_EG_physical_write').update(generation=999999))
 rejected('write-wrong-phase',lambda v:first(v,'fadd_EG_physical_write').update(cycle=first(v,'fadd_EG_physical_write')['cycle']+1))
 rejected('wrong-COM-raw',lambda v:first(v,'fadd_EG_functional_COM').update(raw=0))
 rejected('wrong-COM-geometry',lambda v:first(v,'fadd_EG_functional_COM').update(VL=63))
 rejected('wrong-COM-authority',lambda v:first(v,'fadd_EG_functional_COM').update(geometry_authority='reservation'))
 rejected('wrong-EG-destination',lambda v:first(v,'fadd_EG_microissue').update(destination_EG=0))
 rejected('new-IEEE-flags',lambda v:first(v,'fadd_EG_functional_COM').update(new_flags=1))
 rejected('committed-wrongpath',lambda v:v.append(dict(event='fadd_EG_wrongpath_cancel',hart=first(v,'fadd_EG_functional_COM')['hart'],generation=first(v,'fadd_EG_functional_COM')['generation'])))
 rejected('prefix-ELF-raw',lambda v:v[0].update(raw=0),'prefix')
 rejected('prefix-ambiguous-endpoint',lambda v:v.insert(1,dict(v[0],sequence=v[0]['sequence']+1)),'prefix')
 badmap=out/'bad-map.json';badmap.write_text(json.dumps(dict(schema='iris.source_event_region_map.v1',regions=[dict(rows[0],start_cycle=0)])))
 try:render('bad-map',regmap=badmap)
 except ValueError:checks.append(dict(name='missing explicit map endpoint refused',pass_=True))
 else:raise ValueError('Missing map endpoint admitted')
 # A final partial observer record never receives credits; trace completeness remains explicit.
 partial=out/'partial-journal.jsonl';partial.write_bytes(event.read_bytes()+b'{"event":');tail=render('partial',events=partial,complete=False)
 check('unterminated journal tail explicit/no work',tail['journal_complete']is False and tail['unterminated_tail_bytes']==9 and tail['FADD']['completed_EG_writes']==1024 and tail['FADD']['pipeline_union_complete']is False and tail['normal_execution_complete']is False)
 # Remove a real final publication: remaining work is pending rather than fabricated.
 wi=max(i for i,e in enumerate(raw)if e['event']=='fadd_EG_physical_write');pending=raw[:wi]+raw[wi+1:];pp=out/'pending.jsonl';pp.write_text(''.join(json.dumps(e)+'\n'for e in pending));ps=render('pending',events=pp,complete=False)
 check('missing physical write never receives completion credit',ps['FADD']['completed_EG_writes']==1023 and ps['FADD']['pending_commands']==1 and ps['FADD']['pipeline_union_complete']is False)
 prior=ROOT/'build/C12-source-composite-compute-launcher-gates-v1';negative=[]
 def badrun(name,program,timeout=15):
  inputs[str(program)]=sha(program);r=execute(name,True,program,timeout);negative.append(r);return r
 for h in range(3):
  r=badrun('fatal-h'+str(h),prior/('fatal'+str(h)+'.elf'));check('automatic fatal h'+str(h),not r['pass']and not r.get('timed_out',False)and('IRIS_FATAL hart='+str(h))in(out/('fatal-h'+str(h))/'stderr').read_text())
 r=badrun('recoverable',prior/'recoverable.elf');check('recoverable illegal trap resumes',r['pass']and not r['timed_out'])
 r=badrun('stripped',prior/'stripped.elf');check('unstripped ELF coverage required',not r['pass']and'IRIS_LAUNCH_REFUSED'in(out/'stripped/stderr').read_text())
 r=run(elf,model,out/'bad-region-execution',90,0,'source-events.jsonl',badmap);check('profile join failure preserves normal guest evidence',r['pass']and r['profile_pass']is False and r['source_profile']['available']is False and(out/'bad-region-execution/stdout').read_bytes()==(out/'ON/stdout').read_bytes())
 # Alter only NEW descriptor copy; frozen manifests and all bound native inputs stay untouched.
 bad=out/'corrupt-manifest.json';m=json.loads(model.read_text());m['native_binary_sha256']='0'*64;bad.write_text(json.dumps(m));r=run(elf,bad,out/'bad-digest',15,0,'events.jsonl');check('digest mutation refused before native',not r['pass']and'pid'not in r)
 outside=out.parent/'forbidden-source-profile-output.jsonl';need(not outside.exists(),'Refusal control path must not exist');r=run(elf,model,out/'outside-path',15,0,outside);check('journal output confined to owned fresh directory',not r['pass']and'pid'not in r and not outside.exists())
 r=badrun('owned-timeout',elf,.05);check('bounded owned process cleanup',not r['pass']and r['timed_out']and r['exit_status']!=0)
 try:os.killpg(r['pid'],0)
 except ProcessLookupError:checks.append(dict(name='owned process group absent after timeout',pass_=True))
 else:raise ValueError('Timeout left an owned process group alive')
 check('all exact input bytes retained',all(sha(k)==v for k,v in inputs.items()))
 outputs={str(p):sha(p)for p in out.rglob('*')if p.is_file()};report=dict(schema='iris.source_profile_frontend_checks.v1',**{'pass':True},checks=checks,negative_join_controls=mutations,hardware_contacted=False,new_fitting_or_source_model_changes=False,independent_goldens_words=136,source_add_elements=4096,trace_toggle_numeric_CSR_summary_byte_parity=True,existing_generic_provider_package_bytes_unchanged=True,input_sha256=inputs,output_sha256=outputs)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,checks=len(checks),negative_joins=len(mutations),report_sha256=sha(out/'report.json'))))
if __name__=='__main__':main()

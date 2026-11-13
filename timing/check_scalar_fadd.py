#!/usr/bin/env python3
"""Actual ELF scalar-FADD staged-publication checks, independent of fitting."""
import argparse,hashlib,json,os,re,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--case',action='append',required=True,help='name=/absolute/ELF');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);base=json.loads((ROOT/'build/scalar-fadd-first-v2/argv.json').read_text());reports=[]
 for spec in a.case:
  name,elfname=spec.split('=',1);elf=Path(elfname).resolve();where=out/name;where.mkdir();argv=[str(a.native.resolve()),'--extlib='+str(a.uart.resolve()),*[x for x in base[1:-1]if not x.startswith(('--extlib=','--iris-timing-fixture=','--iris-timing-trace='))],'--iris-timing-fixture='+str(a.fixture.resolve()),'--iris-timing-trace='+str(where/'summary.json'),str(elf)]
  inputs=[a.native.resolve(),a.uart.resolve(),a.fixture.resolve(),elf,Path(__file__).resolve(),ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'];build=elf.with_name('build.json');
  if build.exists():inputs.append(build)
  identities={str(p):sha(p)for p in inputs};env=dict(os.environ)
  for key in list(env):
   if key.startswith('IRIS_EMPIRICAL_'):del env[key]
  env.update(IRIS_EMPIRICAL_ASYNC_TRACE=str(where/'events.jsonl'),IRIS_EMPIRICAL_FEATURES=str(where/'prefix.jsonl'))
  (where/'argv.json').write_text(json.dumps(argv,indent=2)+'\n');started=time.monotonic()
  with(where/'stdout').open('w')as stdout,(where/'stderr').open('w')as stderr:
   try:status=subprocess.run(argv,env=env,stdout=stdout,stderr=stderr,timeout=90).returncode;timeout=False
   except subprocess.TimeoutExpired:status=None;timeout=True
  r=dict(case=name,argv=argv,environment={k:env[k]for k in ['IRIS_EMPIRICAL_ASYNC_TRACE','IRIS_EMPIRICAL_FEATURES']},input_sha256=identities,exit_status=status,timed_out=timeout,host_seconds=time.monotonic()-started,pass_=False)
  try:
   require(all(sha(Path(p))==d for p,d in identities.items()),'input changed')
   text=(where/'stdout').read_text();err=(where/'stderr').read_text();negative=name.startswith('unknown-h')
   if negative:
    hart=int(name[-1]);require(status not in (0,None) and not timeout,'unknown operand must refuse');require('undefined' in err.lower() and ('hart='+str(hart)in err or 'hart '+str(hart)in err),'named actual undefined FPR hart');r.update(expected_capability_refusal=True,hardware_trap_claimed=False)
   else:
    require(status==0 and not timeout,'positive ELF must exit0')
    lines=text.splitlines();require(len(lines)==(9 if name in ('dep','indep') else 3),'all numeric rows')
    if name in ('dep','indep'):
     parsed=[]
     for line in lines:
      require(bool(re.fullmatch(r'SCALAR_FADD [012] [012] [0-9]+ [0-9]+ [0-9]+ [0-9]+',line)),'numeric chain row');h,w,b,e,ir,value=map(int,line.split()[1:]);golden=([0x3c00,0x3f800000,0x3ff0000000000000]if name=='indep'else[0x5000,0x42000000,0x4040000000000000])[w];require(value==golden and b<e,'independent chain golden');parsed.append(dict(hart=h,width=[16,32,64][w],cycles=e-b,instret=ir))
     require(len({(r['hart'],r['width'])for r in parsed})==9,'unique hart/width');r['regions']=parsed
    else:
     seen=set()
     for line in lines:
      require(bool(re.fullmatch(r'SCALAR_EDGE [012] 0 [0-9]+ [0-9]+ [0-9]+',line)),'edge case row');h,bad,v0,v1,v2=map(int,line.split()[1:]);require(h not in seen,'unique hart');seen.add(h)
      if name=='flags':require([v0,v1,v2]==[17,17,17],'NV+NX OR all widths')
      if name=='round':require([v0,v1,v2]==[5,5,5],'all5 legal rounding modes all widths')
      if name=='irq':require(v0==1 and v1==0x4090000000000000,'IRQ result1024 exact')
      if name=='kill':require(v0==0,'wrongpath FADD not published')
     require(seen=={0,1,2},'all3 harts')
    summary=json.loads((where/'summary.json').read_text());metrics=summary['scalar_fadd_metrics'];require('source-HSD' in summary['scalar_fadd_scope'],'actual mode selected');require(len(metrics)==3 and all(not m['pending']for m in metrics),'actual FP unit drain')
    events=[json.loads(x)for x in (where/'events.jsonl').read_text().splitlines()];ex={(x['hart'],x['instruction']):x for x in events if x['event']=='scalar_fadd_EX'};com={(x['hart'],x['instruction']):x for x in events if x['event']=='scalar_fadd_COM'};wr={(x['hart'],x['instruction']):x for x in events if x['event']=='scalar_fadd_FPR_WRITE'}
    require(set(ex)==set(com)==set(wr),'all actual accepts COM/write exactly once')
    for key,x in ex.items():require(x['write']==x['cycle']+(3 if key[0]==2 else 4) and wr[key]['cycle']==x['write'] and com[key]['cycle']==x['cycle']+2,'source l4/l3 actual phase')
    counts={'dep':96,'indep':192,'flags':6,'round':15,'irq':1024,'kill':0};expected=counts[name]
    require(all(m['accepted']==expected and m['published']==expected for m in metrics),'exact perhart FADD count')
    if name=='indep':require(all(m['peak']==(3 if m['hart']==2 else 4)for m in metrics),'source finite pipe occupancy')
    if name=='irq':require(all(m['irq_drain_edges']>0 for m in metrics),'actual IRQ crosses pending FADD onall3')
    prefixes=[json.loads(x)for x in (where/'prefix.jsonl').read_text().splitlines()];sc=[x for x in prefixes if x.get('hart',3)<2 and x.get('csr')in(0xb00,0xb02,0xc00,0xc02)];require(all(x['scalar_fadd_pending']['accepted_live']==0 and x['scalar_fadd_pending']['front_queued']==0 for x in sc),'Shuttle counter drains source FP')
    r.update(actual_phase_joins=len(ex),metrics=metrics,all_numeric_checks_passed=True)
   r['pass_']=True
  except (ValueError,KeyError,TypeError)as e:r['error']=str(e)
  r['pass']=r.pop('pass_');r['output_sha256']={str(p):sha(p)for p in where.iterdir()if p.is_file()};(where/'report.json').write_text(json.dumps(r,indent=2)+'\n');reports.append(r);print(name,r['pass'],r.get('error',''))
 result=dict(schema='iris.scalar_fadd_actual_directed_checks.v1',pass_=all(r['pass']for r in reports),cases=reports,hardware_contacted=False,calibrated=False,global_heldout_timings_consumed=False,full_2pct_certified=False);result['pass']=result.pop('pass_');(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');
 if not result['pass']:raise SystemExit(1)
if __name__=='__main__':main()

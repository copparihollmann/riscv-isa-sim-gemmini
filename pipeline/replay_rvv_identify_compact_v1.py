#!/usr/bin/env python3
"""Controlled postmeasurement readback; no normal-exit or end-to-end timing claim."""
import argparse,hashlib,importlib.util,json,os,re,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'firesim'))
from rvv_identify_compact_review import validator,inspect,ELF
from iris_model.guest_regions import Instructions
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def decode(text,c,layout):
 lines=text.splitlines();need(lines and lines[0]==':'and all(re.fullmatch(r'0x[0-9a-f]{16}',x)for x in lines[1:]),'Exact debugger value stream')
 values=[int(x,16)for x in lines[1:]];need(len(values)==2+1908*17+3 and values[:2]==[0,1908],'All1908 completed numeric records')
 expected=validator().canonical(c);rows=[]
 for i,wanted in enumerate(expected):
  ci,h,start,issue,end,ir0,ir1,ir2,actual,program_expected,mismatch,checked,vl,t0,t1,ip0,ip1=values[2+17*i:2+17*(i+1)]
  need(ci==i and h==wanted['hart'],'Actual compiled role/order')
  row=dict(wanted);row.update(start_cycle=start,issue_cycle=issue,end_cycle=end,instret_delta=ir2-ir0,issue_instret_delta=ir1-ir0,drain_instret_delta=ir2-ir1,checksum=actual,expected_checksum=program_expected,mismatch_or=mismatch,checked_words=checked,vl=vl,mtime_before=t0,mtime_after=t1,msip_before=ip0,msip_after=ip1)
  need(all(type(row[k])is type(v)and row[k]==v for k,v in wanted.items()),'Independent fullword/count/checksum golden')
  need(start<issue<=end and ir0<=ir1<=ir2 and t0<=t1 and row['issue_instret_delta']>=wanted['operations'],'Ordered actual phase counters')
  rows.append(row)
 return rows
def qualify_prefix(path,rows,elf,rom):
 raw=path.read_bytes();need(raw.endswith(b'\n'),'Every actualCSR prefix record flushed')
 records=[json.loads(x)for x in raw.splitlines()];need(len(records)==5724,'Exactly3mcycle reads per1908cases')
 code=Instructions(elf,rom);lookup={};previous={}
 for p in records:
  h,seq=p['hart'],p['sequence'];need(type(h)is int and 0<=h<3 and type(seq)is int and seq>previous.get(h,-1),'Typed ordered hart/sequence');previous[h]=seq
  for k in('value','read_cycle','pc','raw','csr','destination'):need(type(p[k])is int and p[k]>=0,'Typed actualCSR field')
  word=p['raw'];need(word==code.read(p['pc'])and word&127==0x73 and(word>>20)in(0xb00,0xc00)and p['csr']==word>>20 and p['destination']==(word>>7)&31 and p['result_discarded']is False,'Exact returning mcycle opcode/ELF')
  key=h,p['value'];need(key not in lookup,'Unique actual counter observation');lookup[key]=p
 for r in rows:
  points=[lookup[r['hart'],r[key]]for key in('start_cycle','issue_cycle','end_cycle')]
  need(points[0]['sequence']<points[1]['sequence']<points[2]['sequence']and points[0]['read_cycle']<points[1]['read_cycle']<=points[2]['read_cycle'],'Actual phase endpoint order')
  for name,p in zip(('begin','issue','drain'),points):r[name+'_pc']=p['pc'];r[name+'_global_read_cycle']=p['read_cycle']
 identities={r['calibration_identity']for r in records};need(len(identities)==1,'One executed fixture identity')
 return dict(actual_mcycle_prefix_records=5724,actual_CSR_ELF_endpoint_joins=5724,issue_and_drain_intervals=3816,total_intervals=1908,calibration_identity=next(iter(identities)))
def main(a):
 build,out,cap,fixture=[p.resolve()for p in(a.build,a.output,a.capsule,a.fixture)];out.mkdir(parents=True,exist_ok=False)
 ready=json.loads((build/'ready.json').read_text());need(sha(build/'ready.json')=='778f1f21210505df0566f1c325615a8d2a7e436d710d5ee7a580f545710cb47a','Frozen1908ready')
 for name,digest in ready['artifact_sha256'].items():need(sha(build/name)==digest,'Frozen experiment artifact')
 manifest=json.loads((cap/'manifest.json').read_text())
 for name,digest in manifest['artifact_sha256'].items():need(sha(cap/name)==digest,'Frozen native capsule')
 elf=build/'guest.elf';need(sha(elf)==ELF,'Exact frozen ELF');c=json.loads((build/'corpus.json').read_text());layout=json.loads((build/'layout.json').read_text());inspect(elf.read_bytes(),c,layout)
 objects=layout['objects'];address=lambda n:objects[n]['address'];commands=['rs 0',f'while mem {address("rvv_measurements_done"):x} ffffffffffffffff',f'mem {address("rvv_measurements_done"):x}',f'mem {address("rvv_record_count"):x}']
 for i in range(1908):commands +=[f'mem {address("rvv_records")+192*i+8*j:x}'for j in range(17)]
 commands+=['pc 0','pc 1','pc 2','quit'];(out/'commands.txt').write_text('\n'.join(commands)+'\n')
 dma='rv64gcv_zfh_zvfh_zvl256b_zvbb';compute='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm';rom=ROOT/'board/evidence/bootrom.rv64.img';dtb=ROOT/'board/build/iris.dtb'
 argv=[str(cap/'spike'),'-d','--debug-cmd='+str(out/'commands.txt'),'--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(out/'native-summary.json'),'--extlib='+str(cap/'libsifive_uart.so'),'--iris-vme','--isa='+dma,'--hart-isa=0:'+compute,'--hart-isa=1:'+compute,'--hart-isa=2:'+dma,'-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000','--device=sifive_uart,0x10020000','--iris-bootrom='+str(rom),'--dtb='+str(dtb),str(elf)]
 files=[Path(__file__).resolve(),cap/'manifest.json',cap/'spike',cap/'libsifive_uart.so',fixture,elf,build/'ready.json',build/'corpus.json',build/'layout.json',build/'qualification.json',out/'commands.txt',rom,dtb,ROOT/'firesim/rvv_identify_compact_review.py',ROOT/'benchmarks/rvv_identify_compact_v1/validate.py']
 inputs={str(p):sha(p)for p in files};q=json.loads((build/'qualification.json').read_text())
 for p,digest in q['input_sha256'].items():need(sha(p)==digest,'Bound functional source changed')
 inputs.update(q['input_sha256']);env=dict(os.environ);env['IRIS_EMPIRICAL_FEATURES']=str(out/'features.jsonl');env.pop('IRIS_EMPIRICAL_ASYNC_TRACE',None)
 spec=importlib.util.spec_from_file_location('fatal_elf_helper',ROOT/'spike/empirical_launch_v2.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);fatal=mod.fatal_addresses(elf);env['IRIS_FATAL_PCS']=','.join(hex(v)for v in sorted(set(fatal.values())))
 r=dict(schema='iris.rvv_identify_model_prediction.v1',status='running',argv=argv,input_sha256=inputs,hardware_contacted=False,reserved_timing_labels_consumed=False,normal_guest_exit_verified=False,intentional_postmeasurement_debugger_stop=True,whole_run_timing_or_speed_claim=False)
 def save():(out/'run.json').write_text(json.dumps(r,indent=2)+'\n')
 save();started=time.monotonic()
 with(out/'stdout').open('w')as stdout,(out/'stderr').open('w')as stderr:
  proc=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,start_new_session=True);r['pid']=proc.pid;save()
  try:r['debugger_exit_status']=proc.wait(timeout=a.timeout);r['timed_out']=False
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=1)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
   r.update(debugger_exit_status=proc.returncode,timed_out=True)
 r['host_seconds']=time.monotonic()-started
 try:
  need(r['debugger_exit_status']==0 and not r['timed_out'],'Model stopped before completed measurement readback')
  rows=decode((out/'stderr').read_text(),c,layout);r.update(qualify_prefix(out/'features.jsonl',rows,elf,rom))
  wanted=[l.split()[2]for l in fixture.read_text().splitlines()if l.startswith('empirical_profile ')];need(wanted==[r['calibration_identity']],'Executed fixture identity')
  for p,digest in inputs.items():need(sha(p)==digest,'Execution input changed '+p)
  (out/'regions.jsonl').write_text(''.join(json.dumps(row,sort_keys=True)+'\n'for row in rows));r.update(status='completed_all1908_measurements_with_controlled_debugger_stop',**{'pass':True},regions=1908,complete_per_element_goldens=225888)
 except(Exception)as exc:r.update(status='failed',**{'pass':False},error=str(exc))
 r['output_sha256']={str(p):sha(p)for p in out.iterdir()if p.name in('stdout','stderr','features.jsonl','regions.jsonl','native-summary.json')};save();print(json.dumps({k:r.get(k)for k in('pass','status','regions','host_seconds','error')}));return 0 if r['pass']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__)
 for key in('build','output','capsule','fixture'):p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--timeout',type=float,default=900);raise SystemExit(main(p.parse_args()))

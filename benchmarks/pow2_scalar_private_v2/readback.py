#!/usr/bin/env python3
"""Intentional postmeasurement debugger readback; never claims normal HTIF exit."""
import argparse,collections,hashlib,json,os,re,subprocess,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));from iris_model.guest_regions import Instructions
from validate import expected

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def decode(stderr,c,layout):
 lines=stderr.splitlines()
 if not lines or lines[0]!=':'or any(not re.fullmatch('0x[0-9a-f]{16}',s)for s in lines[1:]):raise ValueError('Unexpected debugger/trap output')
 words=[int(s,16)for s in lines[1:]]
 if len(words)!=2+576*11+2 or words[:2]!=[0,576]or words[-2:]!=[0,576]:raise ValueError('Complete sentinel/count/stablebuffer required')
 rows=[];prior={}
 for i,spec in enumerate(c['cases']):
  index,h,b,e,ir,*payload=words[2+11*i:2+11*(i+1)];values=payload[:4];tb,ta=payload[4:]
  if index!=i or h!=spec['hart']or values!=expected(spec['kind'],spec['n'])or not prior.get(h,0)<=b<e or ir<3*spec['n']or tb>ta:raise ValueError('Actual complete perword/role/counter golden')
  prior[h]=e;rows.append(dict(case_id=spec['id'],hart=h,kind=spec['kind'],n=spec['n'],trial_id=spec['trial_id'],internal_split=spec['internal_split'],start_cycle=b,end_cycle=e,cycles=e-b,instret_delta=ir,values=values,mtime_before=tb,mtime_after=ta,observation_source='intentional_postmeasurement_debugger_readback',normal_guest_exit_claimed=False))
 return rows

def prefix_proof(p,rows,elf,rom):
 raw=p.read_bytes();end=raw.rfind(b'\n')+1;records=[json.loads(s)for s in raw[:end].splitlines()];bykey={};last={};instructions=Instructions(elf,rom)
 for x in records:
  h=x['hart'];seq=x['sequence']
  if type(seq)is not int or seq<=last.get(h,-1)or x['raw']!=instructions.read(x['pc']):raise ValueError('Typed monotonic actual ELFprefix')
  last[h]=seq
  if x['csr']!=0xb00:continue
  if(x['raw']>>20)!=0xb00 or x['raw']&127!=0x73 or x['result_discarded']:raise ValueError('Actual returning mcycle CSR')
  key=h,x['value']
  if key in bykey:raise ValueError('Ambiguous actual CSRvalue')
  bykey[key]=x
 for r in rows:
  a,b=[bykey[r['hart'],r[k]]for k in('start_cycle','end_cycle')]
  if a['sequence']>=b['sequence']or a['read_cycle']>=b['read_cycle']:raise ValueError('ForwardactualCSRpair')
  r.update(begin_pc=a['pc'],end_pc=b['pc'],begin_read_cycle=a['read_cycle'],end_read_cycle=b['read_cycle'])
 return dict(actual_CSR_ELF_endpoint_joins=1152,complete_prefix_records=len(records),unterminated_tail_bytes_preserved=len(raw)-end)

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--native-dir',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=180);a=p.parse_args();b=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);build=json.loads((b/'build.json').read_text());layout=json.loads((b/'layout.json').read_text());c=json.loads((b/'corpus.json').read_text());elf=b/'scalar.elf';native=a.native_dir.resolve()/'spike';uart=native.with_name('libsifive_uart.so');fixture=a.fixture.resolve();rom=ROOT/'board/evidence/bootrom.rv64.img';dtb=ROOT/'board/build/iris.dtb'
 if build['negative_skip_kernel']is not False or sha(elf)!=build['elf_sha256']or c.get('all_measurements_before_UART')is not True:raise ValueError('ExactpositivebufferedprivateELF')
 def address(n):return layout['objects'][n]['address']
 commands=['rs 0','while mem %x ffffffffffffffff'%address('scalar_measurements_done'),'mem %x'%address('scalar_measurements_done'),'mem %x'%address('scalar_record_count')]
 commands+=['mem %x'%v for v in range(address('scalar_records'),address('scalar_records')+576*88,8)];commands+=['mem %x'%address('scalar_measurements_done'),'mem %x'%address('scalar_record_count'),'quit'];(out/'commands.txt').write_text('\n'.join(commands)+'\n')
 dma='rv64gcv_zfh_zvfh_zvl256b_zvbb';compute='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm';argv=[str(native),'-d','--debug-cmd='+str(out/'commands.txt'),'--iris-vme','--isa='+dma,'--hart-isa=0:'+compute,'--hart-isa=1:'+compute,'--hart-isa=2:'+dma,'-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000','--extlib='+str(uart),'--device=sifive_uart,0x10020000','--iris-bootrom='+str(rom),'--dtb='+str(dtb),'--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(out/'summary.json'),str(elf)]
 ids=dict(build['input_sha256']);ids.update({str(q):sha(q)for q in[Path(__file__).resolve(),b/'build.json',b/'layout.json',elf,native,uart,fixture,rom,dtb,out/'commands.txt']});env={k:v for k,v in os.environ.items()if not k.startswith('IRIS_EMPIRICAL_')and k!='IRIS_FATAL_PCS'};env['IRIS_EMPIRICAL_FEATURES']=str(out/'features.jsonl');start=time.monotonic();code=None;timed=False
 with(out/'stdout').open('wb')as so,(out/'stderr').open('wb')as se:
  try:code=subprocess.run(argv,env=env,stdout=so,stderr=se,timeout=a.timeout).returncode
  except subprocess.TimeoutExpired:timed=True
 report=dict(schema='iris.pow2_scalar_private_intentional_readback.v2',status='failed',argv=argv,input_sha256=ids,debugger_process_exit_status=code,timed_out=timed,host_seconds=time.monotonic()-start,normal_guest_exit_verified=False,intentional_postmeasurement_debugger_stop=True,whole_run_timing_claim=False,hardware_contacted=False,reserved_hardware_timing_labels_consumed=False)
 try:
  if timed or code!=0:raise ValueError('Bounded successful debugger exit required')
  if any(sha(p)!=h for p,h in ids.items()):raise ValueError('Inputs changed')
  rows=decode((out/'stderr').read_text(),c,layout);proof=prefix_proof(out/'features.jsonl',rows,elf,rom);(out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in rows));report.update(status='passed',regions=576,words=2304,all_numerical_goldens_passed=True,**proof)
 except(ValueError,KeyError,TypeError)as e:report['error']=str(e)
 report['output_sha256']={str(q):sha(q)for q in out.iterdir()if q.is_file()};(out/'run.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in['status','regions','host_seconds','error']}));return 0 if report['status']=='passed'else 1
if __name__=='__main__':raise SystemExit(main())

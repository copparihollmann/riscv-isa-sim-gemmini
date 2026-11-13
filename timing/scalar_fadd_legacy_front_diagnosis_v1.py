#!/usr/bin/env python3
"""Independent fixed-parameter OFF controls and source phase summary; no hardware."""
import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=ROOT/'build/scalar-FADD-legacy-front-e8ed-OFF-controls-v1';out.mkdir();base=json.loads((ROOT/'build/scalar-fadd-first-v2/argv.json').read_text());native=ROOT/'build/scalar-L2hit-frozen-e8edb584/spike';uart=native.with_name('libsifive_uart.so');fixture=ROOT/'build/scalar-FADD-legacy-front-e8ed-inputs-v1/OFF.fixture';cases=[]
 for name in('dep','indep'):
  d=out/name;d.mkdir();elf=ROOT/('build/scalar-fadd-guest-'+name+'-v2/guest.elf');argv=[str(native),'--extlib='+str(uart),*[x for x in base[1:-1]if not x.startswith(('--extlib=','--iris-timing-fixture=','--iris-timing-trace='))],'--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(d/'summary.json'),str(elf)];paths=[Path(__file__).resolve(),native,uart,fixture,elf,ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'];ids={str(p):sha(p)for p in paths};env={k:v for k,v in os.environ.items()if not k.startswith('IRIS_EMPIRICAL_')};start=time.monotonic()
  with(d/'stdout').open('wb')as so,(d/'stderr').open('wb')as se:r=subprocess.run(argv,env=env,stdout=so,stderr=se,timeout=90)
  rows=[]
  for line in(d/'stdout').read_text().splitlines():
   fields=line.split();assert fields[0]=='SCALAR_FADD';h,w,b,e,ir,value=map(int,fields[1:]);expected=([0x3c00,0x3f800000,0x3ff0000000000000]if name=='indep'else[0x5000,0x42000000,0x4040000000000000])[w];assert value==expected and e>b;rows.append(dict(hart=h,width=[16,32,64][w],cycles=e-b,instret=ir))
  summary=json.loads((d/'summary.json').read_text());assert r.returncode==0 and len(rows)==9 and len({(x['hart'],x['width'])for x in rows})==9 and summary['scalar_fadd_scope']=='disabled'and all(x['accepted']==0 for x in summary['scalar_fadd_metrics']);assert all(sha(p)==h for p,h in ids.items());report=dict(case=name,status='passed',argv=argv,exit_status=r.returncode,host_seconds=time.monotonic()-start,regions=rows,scalar_fadd_enabled=False,input_sha256=ids,output_sha256={p.name:sha(p)for p in d.iterdir()if p.is_file()});(d/'report.json').write_text(json.dumps(report,indent=2)+'\n');cases.append(report)
 report=dict(schema='iris.scalar_FADD_legacy_front_OFF_controls.v1',status='passed',cases=cases,parameter_fit_performed=False,hardware_contacted=False,reserved_hardware_timing_labels_consumed=False);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status='passed',report_sha256=sha(out/'report.json'))))
if __name__=='__main__':main()

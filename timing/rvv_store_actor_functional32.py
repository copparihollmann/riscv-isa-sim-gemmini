#!/usr/bin/env python3
"""Canonical32 OFF-mode compatibility, preserving exact per-case environment."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(exist_ok=False);n=a.native.resolve();c=R/'build/rocket-source-functional32-v3/results.json';q=json.loads(c.read_text());assert len(q['rows'])==32 and all(x['pass']is True for x in q['rows']);rows=[]
 for row in q['rows']:
  argv=row['argv'][:];reference=row['name'].endswith('-reference')
  if not reference:argv[0]=str(n/'spike');argv=['--extlib='+str(n/'libsifive_uart.so')if x.startswith('--extlib=')else x for x in argv]
  assert sha(argv[-1])==row['elf_sha256'];env=dict(os.environ,PATH="/scratch/eygao/iris-cy/.conda-env/bin:"+os.environ["PATH"]);env.pop('IRIS_FATAL_PCS',None);env.pop('IRIS_UART_RX_FRAMES',None);env.update(row.get('environment',{}));start=time.perf_counter();r=subprocess.run(argv,env=env,capture_output=True,timeout=120);so=o/(row['name']+'.stdout');se=o/(row['name']+'.stderr');so.write_bytes(r.stdout);se.write_bytes(r.stderr);ok=r.returncode==row['expected_exit_status']and all(x in r.stderr.decode(errors='replace')for x in row.get('expected_diagnostics',[]));rows.append(dict(name=row['name'],pass_=ok,argv=argv,environment=row.get('environment',{}),exit_status=r.returncode,expected_exit_status=row['expected_exit_status'],host_seconds=time.perf_counter()-start,binary_sha256=sha(argv[0]),ELF_sha256=sha(argv[-1]),stdout_sha256=sha(so),stderr_sha256=sha(se)))
 report=dict(schema='iris.VSE_actor_canonical_functional32_OFF.v1',status='passed'if all(x['pass_']for x in rows)else'failed',rows=rows,ON_mode_qualified=False,input_sha256={str(p):sha(p)for p in[Path(__file__),n/'spike',n/'libsifive_uart.so',n/'manifest.json',c]},hardware_contacted=False);(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],sha(o/'report.json'))
if __name__=='__main__':main()

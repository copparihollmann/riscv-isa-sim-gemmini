#!/usr/bin/env python3
"""Replay existing independent temporal/numeric oracles with explicit packet fixtures."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--shuttle-mode',choices=['source','legacy'],default='source');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);fixtures=out/'fixtures';fixtures.mkdir()
 suffix='\nempirical_rocket_packets source-IBuf-demand-4B-v1\n'
 if a.shuttle_mode=='source':suffix+='shuttle_frontend source-C++-M-mode 1 16\nicache_service empirical-shared-L2 1 1 explicit-unfitted-direct-source-Icache-service\n'
 inputs=[Path(__file__).resolve(),a.binary.resolve(),a.uart.resolve()];reports={}
 for kind,tool in [('fadd','check_empirical_fadd_async.py'),('async','check_empirical_async_queue.py')]:
  source=ROOT/'pipeline'/tool;text=source.read_text();inputs.append(source)
  if kind=='fadd':
   for mode in['base','long']:
    original=ROOT/f'build/empirical-fadd-first-v1/{mode}.fixture';inputs.append(original);(fixtures/(mode+'.fixture')).write_text(original.read_text()+suffix)
   old="ROOT=Path(__file__).resolve().parents[1]";assert text.count(old)==1;text=text.replace(old,'ROOT=Path('+repr(str(ROOT))+')')
   old="fixture=None if mode=='functional'else ROOT/f'build/empirical-fadd-first-v1/{mode}.fixture'";assert text.count(old)==1;text=text.replace(old,"fixture=None if mode=='functional'else Path("+repr(str(fixtures))+ ")/(mode+'.fixture')")
  else:
   mapping={}
   for n,original in enumerate([ROOT/'build/empirical-async-two-first-v1/two.fixture',ROOT/'build/empirical-async-two-guards-v1/irq.fixture']):
    dest=fixtures/('async'+str(n)+'.fixture');dest.write_text(original.read_text()+suffix);inputs.append(original);mapping[str(original)]=str(dest)
   old='R=pathlib.Path(__file__).resolve().parents[1]';assert text.count(old)==1;text=text.replace(old,'R=pathlib.Path('+repr(str(ROOT))+')')
   old='o=root/name;o.mkdir();a=';assert text.count(old)==1;text=text.replace(old,'o=root/name;o.mkdir();fixture=pathlib.Path('+repr(mapping)+'[str(fixture)]);a=')
  derived=out/('derived-'+tool);derived.write_text(text);inputs.append(derived);runout=out/kind;argv=[sys.executable,str(derived),'--binary',str(a.binary.resolve()),'--uart',str(a.uart.resolve()),'--output',str(runout)];t=time.monotonic();r=subprocess.run(argv,capture_output=True,timeout=600);(out/(kind+'.stdout')).write_bytes(r.stdout);(out/(kind+'.stderr')).write_bytes(r.stderr);assert r.returncode==0,(kind,r.returncode,r.stderr.decode(),r.stdout.decode()[-2000:]);reports[kind]={'report':str(runout/'report.json'),'sha256':sha(runout/'report.json'),'host_seconds':time.monotonic()-t}
 inputs+=list(fixtures.iterdir());report={'schema':'iris.empirical.Rocket_packets.actual_ELF_guards.v1','pass':True,'binary_sha256':sha(a.binary),'uart_sha256':sha(a.uart),'shuttle_mode':a.shuttle_mode,'reports':reports,'input_sha256':{str(x):sha(x)for x in inputs},'oracle_scope':'existing18FADD+4two-owner numeric/knownness/IRQ invariants with only explicit fixture frontend directives added; no accuracy fitting','timing_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()

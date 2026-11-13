#!/usr/bin/env python3
"""Freeze the observed313 K1 prediction before any exact-ELF RTL timing exposure."""
import argparse,gzip,hashlib,io,json,shlex,shutil,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
 if a.verify:
  m=json.loads((out/'report.json').read_text())
  for digest,row in m['objects'].items():
   f=out/row['path'];data=gzip.open(f,'rb').read()if row['encoding']=='gzip'else f.read_bytes()
   if sha(f)!=row['encoded_sha256']or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('prediction closure object changed')
  for name,digest in m['top_sha256'].items():
   if sha(out/name)!=digest:raise ValueError('top prediction artifact changed')
  print(json.dumps(dict(status='verified_pre_reference_K1_prediction',files=len(m['files']),objects=len(m['objects']))));return
 out.mkdir(exist_ok=False,parents=True);(out/'objects').mkdir();snap=ROOT/'build/saturn-native-pre-guard-31324c3a';run=ROOT/'build/saturn-native-first-v2';source=ROOT/'pipeline/riscv-isa-sim-saturn-live';b=json.loads((snap/'pipeline-build.json').read_text());r=json.loads((run/'results.json').read_text())
 if b['binary_sha256']!='31324c3accae8ad6a15197e6c424e109539b2d368e04c3d0c85667c08c7d98ca'or sha(snap/'spike')!=b['binary_sha256']or sha(snap/'source-overlay.patch')!=b['source_overlay_sha256']:raise ValueError('saved pre-guard313 identity differs')
 if not r['status'].startswith('passed')or r['binary_sha256']!=b['binary_sha256']:raise ValueError('313 raw prediction missing')
 reconstruction=out/'source';reconstruction.mkdir();raw=subprocess.check_output(['git','-C',str(source),'archive','72958551566a30f19444bd7e354552824e4d0a98'])
 with tarfile.open(fileobj=io.BytesIO(raw))as tar:tar.extractall(reconstruction,filter='data')
 # An explicit nested repository prevents git apply from silently filtering
 # paths relative to the enclosing workspace repository.
 subprocess.run(['git','init','--quiet',str(reconstruction)],check=True,capture_output=True)
 subprocess.run(['git','apply',str(snap/'source-overlay.patch')],cwd=reconstruction,check=True,capture_output=True)
 files={};objects={}
 def keep(path,expected=None,label=None):
  path=Path(path);digest=sha(path)
  if expected and digest!=expected:raise ValueError('prediction input changed: '+str(path))
  files[label or str(path)]=dict(sha256=digest,bytes=path.stat().st_size)
  if digest not in objects:
   zipped=path.stat().st_size>1048576;dst=out/'objects'/(digest+('.gz'if zipped else''))
   if zipped:
    with path.open('rb')as src,dst.open('wb')as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0)as target:shutil.copyfileobj(src,target,1048576)
   else:shutil.copy2(path,dst)
   objects[digest]=dict(path=str(dst.relative_to(out)),encoding='gzip'if zipped else'raw',encoded_sha256=sha(dst))
  return digest
 for path in reconstruction.rglob('*'):
  if path.is_file()and'.git'not in path.relative_to(reconstruction).parts:keep(path,label='reconstructed313/'+str(path.relative_to(reconstruction)))
 for path in snap.iterdir():
  if path.is_file():keep(path)
 for path in run.iterdir():
  if path.is_file():keep(path)
 for path,digest in b['input_sha256'].items():keep(path,digest)
 for path,digest in r['input_sha256'].items():
  path=Path(path)
  if str(path)==r['argv'][0]:keep(snap/'spike',digest,label=str(path)+'@313')
  elif path.name=='libsifive_uart.so':keep(snap/'libsifive_uart.so',digest,label=str(path)+'@313')
  else:keep(path,digest)
 # MMD source closure: native-core paths come from exact reconstructed313,
 # never the guard successor at the original mutable source pathname.
 build=ROOT/'build/spike-saturn-live-v1'
 for depfile in build.glob('*.d'):
  keep(depfile)
  for word in shlex.split(depfile.read_text().replace('\\\n',' ').split(':',1)[1]):
   if word.endswith(':'):continue # compiler -MP phony target, not an input
   path=(build/word).resolve()
   if path.is_relative_to(source):keep(reconstruction/path.relative_to(source),label=str(path)+'@313')
   elif path.is_file():keep(path)
 for name in ['config.h','Makefile','config.log']:keep(build/name)
 for name in ['spike','libsifive_uart.so','pipeline-build.json','source-overlay.patch']:shutil.copy2(snap/name,out/name)
 top={name:sha(out/name)for name in ['spike','libsifive_uart.so','pipeline-build.json','source-overlay.patch']}
 g=json.loads((run/'graph.json').read_text());macs=[e for e in g['events']if e['name']=='INT8_MAC_edge'];overlap=[]
 for point in macs:
  scalar=[e for e in g['events']if e['hart']==0 and e['resource']in('shuttle0.EX','shuttle0.MEM_ALU')and e['start']<=point['start']<e['end']and e['completed']and not e.get('squashed')]
  if not scalar:raise ValueError('source MAC point lacks originally observed scalar overlap')
  overlap.append(dict(source_MAC_edge=point['start'],MACs=point['macs'],scalar_events=[dict(node=e['id'],resource=e['resource'],pc=e['pc'])for e in scalar]))
 keep(Path(__file__).resolve());report=dict(schema='iris.saturn.pre_reference_actual_ELF_prediction.v1',status='frozen_before_exact_ELF_RTL_timing_exposure',native_sha256=b['binary_sha256'],uart_sha256=b['uart_sha256'],ELF_sha256=r['input_sha256'][r['argv'][-1]],actual_run_receipt_sha256=sha(run/'results.json'),actual_graph_sha256=sha(run/'graph.json'),source_overlay_sha256=b['source_overlay_sha256'],source_reconstructed_from_exact729=True,ROI_counter_stdout=(run/'stdout').read_text(),actual_source_MAC_scalar_overlap=overlap,host_seconds=r['host_seconds'],retired_instructions=g['retired_instructions'],files=files,objects=objects,top_sha256=top,dependencies=[dict(path=str(ROOT/'build/rocket-serial-frozen-15b10335'),manifest_sha256='ce745287d2cf9a068f35aad8ce5c7f2406d87ab1d80b6959ce8f2f78d4d6a8e6'),dict(path=str(ROOT/'build/saturn-timing-live-bridge-component-v1-final'),report_sha256='4111c76e87ff546ed75c21e17360b1428ba269ade89f2ac667a607e288af7210')],memory_fixture_matches_whole_RTL=False,timing_fit=False,full_timing_certified=False,held_out_2pct=False,hardware_contacted=False);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],report_sha256=sha(out/'report.json'),files=len(files),objects=len(objects))))
if __name__=='__main__':main()

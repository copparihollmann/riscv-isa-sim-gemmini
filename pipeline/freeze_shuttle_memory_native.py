#!/usr/bin/env python3
"""Freeze narrow real-ELF Shuttle integration without publishing any primary."""
import argparse,difflib,gzip,hashlib,io,json,shlex,shutil,subprocess,tarfile,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
 if a.verify:
  j=json.loads((out/'manifest.json').read_text())
  for digest,x in j['objects'].items():
   q=out/x['path'];assert sha(q)==x['encoded_sha256'];h=hashlib.sha256();op=gzip.open if x['encoding']=='gzip'else open
   with op(q,'rb')as f:
    for b in iter(lambda:f.read(1048576),b''):h.update(b)
   assert h.hexdigest()==digest
  for name,digest in j['top_artifact_sha256'].items():assert sha(out/name)==digest
  for x in j['parent_closures']:assert sha(Path(x['path']))==x['sha256']
  print(json.dumps({'status':'verified','files':len(j['files']),'objects':len(j['objects'])}));return
 if out.exists():raise ValueError('fresh immutable capsule required')
 src=R/'pipeline/riscv-isa-sim-shuttle-memory';old=R/'pipeline/riscv-isa-sim-rocket-serial';build=R/'build/spike-shuttle-memory-v1';br=json.loads((build/'pipeline-build.json').read_text());assert br['binary_sha256']==sha(build/'spike')and br['uart_sha256']==sha(build/'libsifive_uart.so');overlay=subprocess.check_output(['git','-C',str(src),'diff','--binary','HEAD']);assert hashlib.sha256(overlay).hexdigest()==br['source_overlay_sha256']
 out.mkdir();(out/'objects').mkdir();files={};objects={};receipts={};parent=[]
 def keep(p,expected=None,label=None):
  p=Path(p).absolute();h=sha(p)
  if expected and h!=expected:raise ValueError('input changed '+str(p))
  key=label or str(p)
  if key in files:assert files[key]['sha256']==h
  files[key]={'sha256':h,'bytes':p.stat().st_size}
  if h not in objects:
   zipped=p.stat().st_size>1048576;q=out/'objects'/(h+('.gz'if zipped else''))
   if zipped:
    with p.open('rb')as f,q.open('wb')as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0)as z:shutil.copyfileobj(f,z,1048576)
   else:shutil.copy2(p,q)
   objects[h]={'path':str(q.relative_to(out)),'encoding':'gzip'if zipped else'raw','encoded_sha256':sha(q)}
  return h
 def tree(d):
  for p in Path(d).rglob('*'):
   if p.is_file():keep(p)
 def inputs(j):
  for n,h in j.get('input_sha256',{}).items():keep(n,h)
 for n in ['shuttle-memory-native-final-v2','shuttle-memory-native-final-seed17-v2','shuttle-memory-functional32-final-v2']:
  d=R/'build'/n;j=json.loads((d/'results.json').read_text());assert j['status'].startswith('passed');inputs(j);tree(d);receipts[n]={'sha256':sha(d/'results.json'),'status':j['status']}
  for row in j['rows']:
   assert row.get('pass',row.get('pass_'))is True
   if row.get('elf_sha256'):keep(row['argv'][-1],row['elf_sha256'])
  assert j.get('input_sha256',{}).get(str(build/'spike'),br['binary_sha256'])==br['binary_sha256']
 a1=json.loads((R/'build/shuttle-memory-native-final-v2/results.json').read_text());a17=json.loads((R/'build/shuttle-memory-native-final-seed17-v2/results.json').read_text());assert len(a1['rows'])==11 and len(a17['rows'])==2
 for x,y in zip(a1['rows'][:2],a17['rows']):assert x['findings']['cycles']==y['findings']['cycles']and x['findings']['transactions']==134
 phase=R/'build/shuttle-lsu-phase-check-v2';j=json.loads((phase/'results.json').read_text());assert j['exit_status']==0;inputs(j);tree(phase);tree(R/'build/shuttle-lsu-phase-source-v1');keep(R/'pipeline/shuttle_lsu_phase_build.py');keep(R/'pipeline/test_shuttle_lsu_phase.cpp');receipts['source_ShuttleCore_phase']={'sha256':sha(phase/'results.json'),'rows':j['rows']}
 inputs(br)
 for p in build.glob('*.d'):
  keep(p)
  for n in shlex.split(p.read_text().replace('\\\n',' ').split(':',1)[1]):
   q=Path(n);q=q if q.is_absolute()else build/q
   if q.is_file():keep(q)
 for p in (R/'pipeline').glob('shuttle_*'):
  if p.is_file():keep(p)
 for p in [Path(__file__),R/'pipeline/build_native_shuttle_memory.py',R/'pipeline/SHUTTLE_MEMORY_INTEGRATION.md']:keep(p)
 for name in ['pipeline-build.json','Makefile','config.h','config.log','libriscv.a','libfesvr.a','libfdt.a','libdisasm.a','libsoftfloat.a']:keep(build/name)
 for n,expected in [('build/rocket-serial-frozen-15b10335/manifest.json','ce745287d2cf9a068f35aad8ce5c7f2406d87ab1d80b6959ce8f2f78d4d6a8e6'),('build/shuttle-memory-system-component-v1/report.json','ba93541057adb7ab276db15b794107efe2a34d12f8bf126b82da3ee523e7434b'),('build/shuttle-memory-system-component-v1-verify/report.json','dad7207adb8953d59524231bb502b3bf1c98ac0c5c257336c352aa47fdf8d46b')]:
  keep(R/n,expected);parent.append({'path':str(R/n),'sha256':expected})
 # Keep exact source of preserved failures; do not relabel old bytes as gates.
 for d in ['shuttle-memory-readonly-be722289','shuttle-memory-early-discard-39d6cd98','shuttle-memory-native-e8f11377','shuttle-memory-native-compile-guard-failure-v1']:tree(R/'build'/d)
 for d in ['shuttle-memory-native-elf-v2','shuttle-memory-native-store-v1']:
  for p in(R/'build'/d).rglob('*'):
   if p.is_file()and p.name in ['graph.json','stdout','stderr']:keep(p)
 # Reconstruct the exact five native-file delta on frozen15b independently.
 names=set(subprocess.check_output(['git','-C',str(src),'diff','--name-only','HEAD'],text=True).splitlines())|set(subprocess.check_output(['git','-C',str(old),'diff','--name-only','HEAD'],text=True).splitlines());delta=[];changed=[]
 for n in sorted(names):
  x,y=old/n,src/n;before=x.read_text()if x.exists()else'';after=y.read_text()if y.exists()else''
  if before==after:continue
  changed.append(n);keep(y);delta.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+n if x.exists()else'/dev/null',tofile='b/'+n))
 (out/'source-overlay.patch').write_bytes(overlay);(out/'delta-on-15b.patch').write_text(''.join(delta));base=subprocess.check_output(['git','-C',str(src),'archive','72958551566a30f19444bd7e354552824e4d0a98']);(out/'spike-base.tar').write_bytes(base)
 with tempfile.TemporaryDirectory(prefix='iris-shuttle-reconstruct-')as temp:
  with tarfile.open(fileobj=io.BytesIO(base))as tar:
   try:tar.extractall(temp,filter='data')
   except TypeError:tar.extractall(temp)
  for p in [R/'build/rocket-serial-frozen-15b10335/source-overlay.patch',out/'delta-on-15b.patch']:subprocess.run(['git','apply',str(p)],cwd=temp,check=True,capture_output=True)
  assert all(sha(Path(temp)/n)==sha(src/n)for n in changed)
 for n in ['spike','libsifive_uart.so','pipeline-build.json']:shutil.copy2(build/n,out/n)
 tops={n:sha(out/n)for n in ['spike','libsifive_uart.so','pipeline-build.json','spike-base.tar','source-overlay.patch','delta-on-15b.patch']}
 speed=[]
 for r in a1['rows'][:2]+a17['rows']:
  g=json.loads(Path(next(x.split('=',1)[1]for x in r['argv']if x.startswith('--iris-timing-trace='))).read_text());speed.append({'case':r['name'],'retired_instructions':sum(g['retired_instructions']),'virtual_phases':g['cycles'],'host_seconds':r['host_seconds'],'simulated_MIPS':sum(g['retired_instructions'])/r['host_seconds']/1e6})
 result={'schema':'iris.native_Shuttle_shared_memory_capsule.v1','status':'frozen_experimental_actual_ELF_Shuttle_memory','binary_sha256':br['binary_sha256'],'uart_sha256':br['uart_sha256'],'source_overlay_sha256':br['source_overlay_sha256'],'base_commit':br['base_commit'],'native_device_abi':4,'minimal_native_files':changed,'minimal_delta_applied_and_reconstructed':True,'top_artifact_sha256':tops,'receipts':receipts,'parent_closures':parent,'speed':speed,'files':files,'objects':objects,'qualified_scope':'bare M-mode aligned32-bit-encoded LD/SD DRAM; source-proven early discard-to-x0 plus draining FENCE rw,rw; both Shuttle workers at seeds1/17; ordinary functional32 without timing','diagnostic_ROM_explicit':True,'hidden_cache_warmup':False,'individual_tag0_response_PC_qualified':False,'general_Shuttle_LSU_overlap_or_throughput_qualified':False,'CPU_fault_staging_qualified':False,'new_mode_all_three_concurrent_CPU_memory_qualified':False,'new_mode_Zephyr_qualified':False,'full_internal_knownness_certified':False,'FASED_full_host_functional_bridge':False,'image_association_verified':False,'calibrated':False,'held_out_2pct':False,'full_model_available':False,'hardware_contacted':False,'primary_or_frozen_sources_changed':False}
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'manifest_sha256':sha(out/'manifest.json'),'binary_sha256':br['binary_sha256'],'files':len(files),'objects':len(objects),'native_delta_files':changed}))
if __name__=='__main__':main()

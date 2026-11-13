#!/usr/bin/env python3
import argparse,difflib,hashlib,json,shlex,shutil,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--build',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();b=Path(a.build).resolve();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False);r=json.load(open(b/'pipeline-build.json'));s=Path(r['source']);parent=ROOT/'build/warm-OPU-frozen-7108a6ec-v1';parentmeta=json.load(open(parent/'manifest.json'));ps=Path(parentmeta['source']);pi=json.load(open(parent/'native-inventory.json'));opu=ROOT/'build/opu-entry-overlap-frozen-b6ee38ea-v2';expected={'riscv/iris_timing_adapter.h','riscv/iris_timing_adapter.cc','riscv/iris_opu_entry_overlap.inc'};assert sha(b/'spike')==r['binary_sha256']and sha(b/'libsifive_uart.so')==r['uart_sha256']
 inv={n:sha(s/n)for n in set(pi)|expected};changed=[n for n in inv if pi.get(n)!=inv[n]];assert set(changed)==expected,changed;patch=''
 for n in sorted(changed):
  before=(ps/n).read_text().splitlines(True)if n in pi else[];after=(s/n).read_text().splitlines(True);patch+='diff --git a/'+n+' b/'+n+'\n'+('new file mode 100644\n'if n not in pi else'')+''.join(difflib.unified_diff(before,after,fromfile='a/'+n if n in pi else'/dev/null',tofile='b/'+n))
 (o/'TK124-on-7108.patch').write_text(patch);full=subprocess.check_output(['git','diff','--binary','HEAD'],cwd=s);(o/'source-overlay.patch').write_bytes(full);assert sha(o/'source-overlay.patch')==r['source_overlay_sha256'];(o/'native-inventory.json').write_text(json.dumps(inv,sort_keys=True,indent=2)+'\n')
 with tarfile.open(o/'native-source.tar.gz','w:gz')as t:
  for n in sorted(inv):t.add(s/n,arcname=n,recursive=False)
 external={};copied={};oldinputs=json.load(open(parent/'compiled-inputs.json'))
 for dep in b.glob('*.d'):
  text=dep.read_text().replace('\\\n',' ')
  for x in shlex.split(text.split(':',1)[1]):
   if x.endswith(':'):continue
   p=Path(x);p=p if p.is_absolute()else b/p;p=p.resolve()
   if p.is_file()and p.is_relative_to(ROOT)and not p.is_relative_to(s)and not p.is_relative_to(b):external[str(p)]=sha(p)
 for p in[Path(__file__).resolve(),ROOT/'timing/compose_warm_opu_v2.py',ROOT/'build/warm-OPU-application-v1/report.json']:
  external[str(p)]=sha(p)
 for p,h in external.items():
  if oldinputs.get(p)==h:continue
  q=Path(p);rel=str(q.relative_to(ROOT));dst=o/'src'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(q,dst);copied[rel]=h
 (o/'compiled-inputs.json').write_text(json.dumps(external,sort_keys=True,indent=2)+'\n')
 for n in('spike','libsifive_uart.so','pipeline-build.json'):shutil.copy2(b/n,o/n)
 with tempfile.TemporaryDirectory(prefix='warm-OPU-reconstruct-')as tmp:
  d=Path(tmp)
  with(d/'base.tar').open('wb')as f:subprocess.run(['git','archive',r['base_commit']],cwd=s,stdout=f,check=True)
  with tarfile.open(d/'base.tar')as t:t.extractall(d/'native')
  subprocess.run(['git','apply','--unsafe-paths',str(o/'source-overlay.patch')],cwd=d/'native',check=True)
  for n,h in inv.items():assert sha(d/'native'/n)==h,n
 for n,h in pi.items():assert sha(ps/n)==h,n
 m={'schema':'iris.warm_OPU_TK124_native_capsule.v1','pass':True,'source_frozen':True,'source':str(s),'base_commit':r['base_commit'],'binary_sha256':r['binary_sha256'],'uart_sha256':r['uart_sha256'],'native_device_abi':4,'parent_manifest_sha256':{str(p):sha(p)for p in(parent/'manifest.json',opu/'manifest.json')},'changed_files_on7108':sorted(changed),'native_sources_reconstructed':len(inv),'external_compiled_inputs':len(external),'new_source_sha256':copied,'artifact_sha256':{n:sha(o/n)for n in('spike','libsifive_uart.so','pipeline-build.json','TK124-on-7108.patch','source-overlay.patch','native-inventory.json','native-source.tar.gz','compiled-inputs.json')},'FADD_warm_baseline':'source-HSD-pipeline-v1 + dram-L1-hit-Shuttle-COM-forward-v2','OPU_selector_default':'OFF','OPU_selector':'source-VDQ4-IQ3-entry-MM-TK124-COMplus1-v3','legacy_TK1_selector_preserved':True,'intermediate_K_MRF_projection':'unavailable; only perentrylastK publishes; nonMMreadsdrain; activeIRQrefused','scalar_alpha_beta_default':'OFF/no rules','ShuttleRandom_default':'OFF','parameters_fitted':False,'new_clean_native_build':False,'own_clean_parent_build_and_scoped_recompile':True,'OPU_CPU_FENCE_bridge_qualified':False,'OPU_active_IRQ_refused':True,'source_image_association':False,'timing_2pct_certified':False,'hardware_contacted':False,'qualification_scope':'Source reconstruction only; combined numeric/OS/phase gates are separately required.'};(o/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');(o/'verification.json').write_text(json.dumps({'schema':'iris.warm_OPU_reconstruction.v1','pass':True,'manifest_sha256':sha(o/'manifest.json'),'native_sources_reconstructed':len(inv),'parents_unchanged':True,'source_or_timing_certification':False},indent=2)+'\n');print(json.dumps({'pass':True,'native':r['binary_sha256'],'UART':r['uart_sha256'],'manifest_sha256':sha(o/'manifest.json')}))
if __name__=='__main__':main()
